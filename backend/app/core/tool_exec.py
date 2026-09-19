from __future__ import annotations

import ast
import hashlib
import inspect
import json
import threading
from typing import Any, Mapping

from sqlalchemy.orm import Session, selectinload

from app.core.database import SessionLocal
from app.models import Agent, Chat, Project, Tool

# Compiled tool bodies, keyed by (tool id, body hash, function name). A body only
# changes when an admin edits the tool, so re-parsing and re-compiling the same
# source on every call was pure overhead. The cache is process-wide and bounded;
# editing a body simply misses and stores a second entry.
#
# What is cached is the compiled code, not the function object: every call execs
# the body into a namespace of its own, so the system variables below are the
# calling run's and two calls of one tool can never read each other's values.
_COMPILED_CACHE: dict[tuple[int | None, str, str], Any] = {}
_COMPILED_CACHE_LOCK = threading.Lock()
_MAX_CACHED_BODIES = 128

# Handed to every tool body, so a tool can scope itself to the run that called it
# without the model supplying anything. They are deliberately absent from the
# tool's JSON schema: a model that could pass `project_id` could read any
# project. `ToolExec.execute` is the only place that fills them in, and
# `routers/generator.py` documents them to the tool generator from this mapping.
SYSTEM_VARIABLES: dict[str, str] = {
    "project_id": "int, the id of the project the run belongs to",
    "chat_id": "int, the id of the chat the run belongs to",
    "agent_id": "int, the id of the agent that called the tool",
    "user_id": (
        "int, the id of the user the run answers: the owner of the chat, not "
        "whoever typed the message, because an administrator can post into "
        "another user's chat"
    ),
    "call_depth": (
        "int, how many agents deep this run is: 0 for a run started by a "
        "person, 1 for an agent a tool delegated to, and so on. A tool that "
        "calls another agent must refuse to go past "
        "app.core.agent_loop.MAX_DELEGATION_DEPTH, or two agents can call "
        "each other forever"
    ),
}


class ToolExec:
    """Execute an agent tool after checking project/chat/agent/tool access.

    SECURITY / TRUST MODEL
    ----------------------
    A tool body is arbitrary Python that this class compiles and executes with
    full builtins (see `_load_function`). It is deliberately not sandboxed,
    because the tools shipped with this project import `requests`, SQLAlchemy
    and app internals, and one of them passes model-authored SQL straight to the
    database - a restricted-builtins sandbox would break all of them.

    The consequence is that authoring a tool is equivalent to running code on
    the server, so the /admin tool endpoints must stay admin-only (see
    `require_admin`) and `tools.body` should be reviewed like source code.
    Callers still cannot reach a tool that is not attached to their agent.

    A body also starts with the calling run's `project_id`, `chat_id`,
    `agent_id` and `user_id` already in scope, which is what lets a tool scope
    itself instead of being told what to look at - see SYSTEM_VARIABLES.
    """

    def execute(
        self,
        project_id: int,
        chat_id: int,
        agent_id: int,
        tool_id: int,
        tool_parameters: Mapping[str, Any] | None = None,
        db: Session | None = None,
        user_id: int | None = None,
        call_depth: int = 0,
    ) -> Any:
        owns_session = db is None
        session = db or SessionLocal()
        try:
            parameters = dict(tool_parameters or {})
            project = (
                session.query(Project)
                .options(selectinload(Project.agents))
                .filter(Project.id == project_id)
                .first()
            )
            chat = session.query(Chat).filter(Chat.id == chat_id).first()
            agent = (
                session.query(Agent)
                .options(selectinload(Agent.tools))
                .filter(Agent.id == agent_id)
                .first()
            )
            tool = session.query(Tool).filter(Tool.id == tool_id).first()

            missing_message = self._missing_message(project, chat, agent, tool)
            if missing_message:
                return missing_message

            inactive_message = self._inactive_message(project, chat, agent, tool)
            if inactive_message:
                return inactive_message

            relation_message = self._relation_message(project, chat, agent, tool)
            if relation_message:
                return relation_message

            definition = self._tool_definition(tool)
            parameter_message = self._parameter_message(definition, parameters)
            if parameter_message:
                return parameter_message

            function_name = self._function_name(definition, tool)
            function = self._load_function(
                tool.body or "",
                function_name,
                tool_id=tool.id,
                # Must cover every name in SYSTEM_VARIABLES.
                system={
                    "project_id": project_id,
                    "chat_id": chat_id,
                    "agent_id": agent_id,
                    "user_id": user_id,
                    "call_depth": call_depth,
                },
            )
            return self._call_function(function, parameters)
        finally:
            if owns_session:
                session.close()

    def _inactive_message(
        self,
        project: Project,
        chat: Chat,
        agent: Agent,
        tool: Tool,
    ) -> str | None:
        inactive = []
        if not project.is_active:
            inactive.append("project")
        if not agent.is_active:
            inactive.append("agent")
        if not tool.is_active:
            inactive.append("tool")
        if inactive:
            return "Cannot execute tool because these are not active: " + ", ".join(inactive)
        return None

    def _missing_message(
        self,
        project: Project | None,
        chat: Chat | None,
        agent: Agent | None,
        tool: Tool | None,
    ) -> str | None:
        missing = []
        if not project:
            missing.append("project")
        if not chat:
            missing.append("chat")
        if not agent:
            missing.append("agent")
        if not tool:
            missing.append("tool")
        if missing:
            return "Cannot execute tool because these do not exist: " + ", ".join(missing)
        return None

    def _relation_message(
        self,
        project: Project,
        chat: Chat,
        agent: Agent,
        tool: Tool,
    ) -> str | None:
        problems = []
        if chat.project_id != project.id:
            problems.append("chat does not belong to project")
        if not any(project_agent.id == agent.id for project_agent in project.agents):
            problems.append("agent does not belong to project")
        if not any(agent_tool.id == tool.id for agent_tool in agent.tools):
            problems.append("tool does not belong to agent through its skills")
        if problems:
            return "Cannot execute tool because " + "; ".join(problems)
        return None

    def _tool_definition(self, tool: Tool) -> dict[str, Any]:
        if not tool.description or not tool.description.strip():
            return {}
        try:
            parsed = json.loads(tool.description)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Tool description is not valid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise ValueError("Tool description JSON must be an object")
        return parsed

    def _parameter_message(
        self,
        definition: Mapping[str, Any],
        parameters: Mapping[str, Any],
    ) -> str | None:
        schema = self._parameters_schema(definition)
        if not schema:
            return None

        properties = schema.get("properties") or {}
        required = schema.get("required") or []
        if not isinstance(properties, Mapping):
            return "Cannot execute tool because parameters.properties must be an object"
        if not isinstance(required, list):
            return "Cannot execute tool because parameters.required must be a list"

        missing = [name for name in required if name not in parameters]
        unknown = [name for name in parameters if name not in properties]
        type_errors = [
            f"{name} must be {properties[name].get('type')}"
            for name in parameters
            if isinstance(properties.get(name), Mapping)
            and not self._matches_json_type(parameters[name], properties[name].get("type"))
        ]

        problems = []
        if missing:
            problems.append("missing required parameters: " + ", ".join(missing))
        if unknown:
            problems.append("unknown parameters: " + ", ".join(unknown))
        if type_errors:
            problems.append("parameter type problems: " + "; ".join(type_errors))
        if problems:
            return "Cannot execute tool because " + "; ".join(problems)
        return None

    def _parameters_schema(self, definition: Mapping[str, Any]) -> Mapping[str, Any]:
        function_def = definition.get("function")
        if isinstance(function_def, Mapping):
            parameters = function_def.get("parameters")
            if isinstance(parameters, Mapping):
                return parameters
        parameters = definition.get("parameters")
        if isinstance(parameters, Mapping):
            return parameters
        return {}

    def _function_name(self, definition: Mapping[str, Any], tool: Tool) -> str:
        function_def = definition.get("function")
        if isinstance(function_def, Mapping) and function_def.get("name"):
            return str(function_def["name"])
        if definition.get("name"):
            return str(definition["name"])
        return tool.name

    def _load_function(
        self,
        body: str,
        function_name: str,
        tool_id: int | None = None,
        system: Mapping[str, Any] | None = None,
    ) -> Any:
        """Compile `body` and return the callable named `function_name`.

        Bodies are cached compiled, by tool id, source hash and function name, so
        repeat calls skip `ast.parse`/`compile`; only the `exec` repeats.

        `system` is what the body sees beyond its own parameters, and it is how
        `project_id`, `chat_id` and `agent_id` reach a tool (SYSTEM_VARIABLES).
        Each call execs into a namespace of its own, so concurrent calls of one
        tool cannot read each other's values - at the cost of a body's
        module-level state no longer surviving between calls.

        SECURITY: executes untrusted-by-design, admin-authored Python. Do not
        expose this path to non-admin callers.
        """
        if not body.strip():
            raise ValueError("Tool body is empty")

        key = (tool_id, hashlib.sha256(body.encode("utf-8")).hexdigest(), function_name)
        code = _COMPILED_CACHE.get(key)
        if code is None:
            tree = ast.parse(body)
            functions = [node.name for node in tree.body if isinstance(node, ast.FunctionDef)]
            if function_name not in functions:
                raise ValueError(f'Tool body does not define function "{function_name}"')
            code = compile(tree, filename=f"<tool:{function_name}>", mode="exec")
            with _COMPILED_CACHE_LOCK:
                if len(_COMPILED_CACHE) >= _MAX_CACHED_BODIES:
                    _COMPILED_CACHE.clear()
                _COMPILED_CACHE[key] = code

        scope: dict[str, Any] = dict(system or {})
        exec(code, scope, scope)
        function = scope.get(function_name)
        if not callable(function):
            raise ValueError(f'Tool body did not load callable "{function_name}"')
        return function

    def _call_function(self, function: Any, parameters: Mapping[str, Any]) -> Any:
        try:
            inspect.signature(function).bind(**parameters)
        except TypeError as exc:
            return f"Cannot execute tool because parameters do not match function signature: {exc}"
        try:
            return function(**parameters)
        except Exception as exc:
            return f"Cannot execute tool because the function raised an error: {exc}"

    def _matches_json_type(self, value: Any, expected_type: Any) -> bool:
        if not expected_type:
            return True
        if isinstance(expected_type, list):
            return any(self._matches_json_type(value, one_type) for one_type in expected_type)
        if expected_type == "string":
            return isinstance(value, str)
        if expected_type == "integer":
            return isinstance(value, int) and not isinstance(value, bool)
        if expected_type == "number":
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        if expected_type == "boolean":
            return isinstance(value, bool)
        if expected_type == "object":
            return isinstance(value, dict)
        if expected_type == "array":
            return isinstance(value, list)
        return True

    # `ute` was the original name of `execute` (a port artifact); keep it working
    # for any caller that still uses it.
    ute = execute


tool_exec = ToolExec()
