"""Operations the Project Manager agent performs on the system itself.

The agent does not call the REST API: each of its tools calls one function here,
passing its own database session. Keeping the logic out of the routers leaves it
callable from a tool body, a script or a test, while the REST layer stays the
authority on what an HTTP caller may do.

TRUST MODEL
-----------
Everything here is admin-equivalent - a caller can create users, projects,
agents, skills and tools, and a tool body is arbitrary Python (see
`app.core.tool_exec`). Those tools are therefore only ever attached to the
Project Manager agent, which lives in the system project that only admins can
reach. Two refusals are still enforced here, because they are the mistakes a
model actually makes:

* the system project's own row is never edited or deleted - otherwise the agent
  could delete its own home;
* an agent may not delete or deactivate itself, nor detach the skill or tool it
  is running on - that would leave the run half-finished with no way back.

Nothing here raises for bad input: each public `manage_*` returns either the
result or `{"error": "..."}`, because the caller is a model and a sentence is
more useful to it than a traceback.
"""

from __future__ import annotations

import ast
import json
import logging
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import String, cast, func, or_, select, text
from sqlalchemy.orm import Session, selectinload

from app.core.security import hash_password
from app.models import Agent, Project, ProjectTable, Skill, Tool, User

logger = logging.getLogger(__name__)

# Tool specs and bodies are long. `manage_tools action=get` is the one place a
# model reads them back, and a whole body in the transcript would crowd out the
# rest of the turn, so text is cut at this many characters.
MAX_TEXT_CHARS = 4000


# ── output helpers ───────────────────────────────────────────────────────────

def _stamp(value: Any) -> Any:
    """Datetimes as ISO strings, because these dicts get JSON-encoded."""
    return value.isoformat() if isinstance(value, datetime) else value


def _clip(value: Optional[str], limit: int = MAX_TEXT_CHARS) -> Optional[str]:
    if value is None or len(value) <= limit:
        return value
    return value[:limit] + f"... [{len(value) - limit} more characters]"


def _user_out(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "language": user.language,
        "country_id": user.country_id,
        "is_active": bool(user.is_active),
        "project_ids": sorted(project.id for project in user.projects),
    }


def _project_out(project: Project, *, workflow: bool = False) -> dict[str, Any]:
    out = {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "is_active": bool(project.is_active),
        "is_system": bool(project.is_system),
        "user_ids": sorted(user.id for user in project.users),
        "agent_ids": sorted(agent.id for agent in project.agents),
        "created_at": _stamp(project.created_at),
    }
    if workflow:
        out["workflow"] = project.workflow or {"nodes": [], "wires": []}
    return out


def _agent_out(agent: Agent) -> dict[str, Any]:
    return {
        "id": agent.id,
        "name": agent.name,
        "description": agent.description,
        "is_active": bool(agent.is_active),
        "skill_ids": sorted(skill.id for skill in agent.skills),
        "tool_ids": sorted(tool.id for tool in agent.tools),
        "project_ids": sorted(project.id for project in agent.projects),
    }


def _skill_out(skill: Skill) -> dict[str, Any]:
    return {
        "id": skill.id,
        "name": skill.name,
        "description": skill.description,
        "is_active": bool(skill.is_active),
        "tool_ids": sorted(tool.id for tool in skill.tools),
        "agent_ids": sorted(agent.id for agent in skill.agents),
    }


def _tool_out(tool: Tool, *, full: bool = False) -> dict[str, Any]:
    out = {
        "id": tool.id,
        "name": tool.name,
        "type": tool.type,
        "is_active": bool(tool.is_active),
        "skill_ids": sorted(skill.id for skill in tool.skills),
    }
    if full:
        out["description"] = tool.description
        out["body"] = tool.body
        return out
    # A spec is a couple of kilobytes of JSON. A list of them would crowd out
    # the rest of the turn, so only the part a model needs to pick a tool is
    # returned here; action=get gives the whole thing.
    out["function_name"] = _function_name_of(tool)
    out["summary"] = _function_summary(tool)
    return out


def _function_name_of(tool: Tool) -> Optional[str]:
    try:
        spec = json.loads(tool.description or "{}")
    except (json.JSONDecodeError, TypeError):
        return None
    function_def = spec.get("function")
    if isinstance(function_def, dict) and function_def.get("name"):
        return str(function_def["name"])
    return None


def _function_summary(tool: Tool) -> Optional[str]:
    try:
        spec = json.loads(tool.description or "{}")
    except (json.JSONDecodeError, TypeError):
        return _clip(tool.description, 300)
    function_def = spec.get("function")
    if isinstance(function_def, dict) and function_def.get("description"):
        return _clip(str(function_def["description"]), 300)
    return None


def _error(exc: Exception) -> dict[str, str]:
    logger.warning("Project Manager action failed: %s", exc)
    return {"error": str(exc)}


# ── lookups and guards ───────────────────────────────────────────────────────

def _need(db: Session, model: Any, entity_id: Optional[int], label: str) -> Any:
    if entity_id is None:
        raise ValueError(f"{label}_id is required for this action")
    row = db.query(model).filter(model.id == entity_id).first()
    if row is None:
        raise ValueError(f"There is no {label} with id {entity_id}")
    return row


def _guard_system_project(project: Project) -> None:
    if project.is_system:
        raise ValueError(
            "The system project's own row cannot be changed or deleted: the Project "
            "Manager agent lives in it. Its members, agents, skills and tools can "
            "still be managed freely."
        )


def _guard_self(caller_agent_id: Optional[int], agent: Agent) -> None:
    if caller_agent_id is not None and agent.id == caller_agent_id:
        raise ValueError(
            f"Refusing to change agent {agent.id} ('{agent.name}') because it is the "
            "agent running this call. Ask a person to do it."
        )


def _guard_home_project(
    caller_agent_id: Optional[int],
    agent: Agent,
    project: Project,
) -> None:
    """Refuse to take the calling agent out of its own home project.

    Leaving any other project is fine - that is a normal cleanup - but the agent
    that is running this call must stay reachable in the project it lives in.
    """
    if caller_agent_id is not None and agent.id == caller_agent_id and project.is_system:
        raise ValueError(
            f"Refusing to remove agent {agent.id} ('{agent.name}') from the system "
            "project, which is its home. Ask a person to do it."
        )


def _guard_own_skill(caller_agent_id: Optional[int], skill: Skill) -> None:
    if caller_agent_id is None:
        return
    if any(agent.id == caller_agent_id for agent in skill.agents):
        raise ValueError(
            f"Refusing to change skill {skill.id} ('{skill.name}') because the agent "
            "running this call depends on it. Ask a person to do it."
        )


def _guard_own_tool(db: Session, caller_agent_id: Optional[int], tool: Tool) -> None:
    if caller_agent_id is None:
        return
    agent = (
        db.query(Agent)
        .options(selectinload(Agent.tools))
        .filter(Agent.id == caller_agent_id)
        .first()
    )
    if agent is not None and any(agent_tool.id == tool.id for agent_tool in agent.tools):
        raise ValueError(
            f"Refusing to change tool {tool.id} ('{tool.name}') because the agent "
            "running this call uses it. Ask a person to do it."
        )


def _active_skills(db: Session, skill_ids: list[int]) -> list[Skill]:
    wanted = {int(skill_id) for skill_id in skill_ids}
    if not wanted:
        return []
    skills = db.query(Skill).filter(Skill.id.in_(wanted)).all()
    missing = sorted(wanted - {skill.id for skill in skills})
    if missing:
        raise ValueError(f"These skills do not exist: {missing}")
    return skills


def _active_tools(db: Session, tool_ids: list[int]) -> list[Tool]:
    wanted = {int(tool_id) for tool_id in tool_ids}
    if not wanted:
        return []
    tools = db.query(Tool).filter(Tool.id.in_(wanted)).all()
    missing = sorted(wanted - {tool.id for tool in tools})
    if missing:
        raise ValueError(f"These tools do not exist: {missing}")
    return tools


def _search_filter(rows: list[Any], search: Optional[str]) -> list[Any]:
    query = (search or "").strip().lower()
    if not query:
        return rows
    return [
        row
        for row in rows
        if query in str(getattr(row, "name", "")).lower()
        or query in str(getattr(row, "email", "")).lower()
    ]


def _limit(rows: list[Any], limit: Optional[int], default: int = 25) -> list[Any]:
    size = default if limit in (None, 0) else int(limit)
    return rows[: max(1, min(size, 200))]


# ── users ────────────────────────────────────────────────────────────────────

def manage_users(
    db: Session,
    action: str,
    caller_agent_id: Optional[int] = None,
    **params: Any,
) -> Any:
    """Create, edit and deactivate user accounts."""
    try:
        action = (action or "").strip().lower()
        user_id = params.get("user_id")

        if action == "list":
            users = db.query(User).order_by(User.id.asc()).all()
            if not params.get("include_inactive"):
                users = [user for user in users if user.is_active]
            users = _limit(_search_filter(users, params.get("search")), params.get("limit"))
            return {"users": [_user_out(user) for user in users]}

        if action == "get":
            return {"user": _user_out(_need(db, User, user_id, "user"))}

        if action == "create":
            name = (params.get("name") or "").strip()
            email = (params.get("email") or "").strip().lower()
            password = params.get("password") or ""
            if not name or not email or not password:
                raise ValueError("name, email and password are required to create a user")
            if db.query(User).filter(User.email == email).first():
                raise ValueError(f"A user with email {email} already exists")
            user = User(
                name=name,
                email=email,
                password=hash_password(password),
                role=(params.get("role") or "client"),
                country_id=params.get("country_id"),
                language=(params.get("language") or "en"),
                is_active=True if params.get("is_active") is None else bool(params.get("is_active")),
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            return {"user": _user_out(user), "created": True}

        if action == "update":
            user = _need(db, User, user_id, "user")
            if params.get("email"):
                email = params["email"].strip().lower()
                clash = db.query(User).filter(User.email == email, User.id != user.id).first()
                if clash:
                    raise ValueError(f"Email {email} already belongs to user {clash.id}")
                user.email = email
            if params.get("name") is not None:
                user.name = params["name"]
            if params.get("role") is not None:
                user.role = params["role"]
            if params.get("language") is not None:
                user.language = params["language"]
            if params.get("country_id") is not None:
                user.country_id = params["country_id"]
            if params.get("password"):
                user.password = hash_password(params["password"])
            db.commit()
            db.refresh(user)
            return {"user": _user_out(user), "updated": True}

        if action == "set_active":
            user = _need(db, User, user_id, "user")
            active = bool(params.get("is_active"))
            if not active and user.role == "admin":
                other_admins = [
                    other
                    for other in db.query(User).filter(User.role == "admin").all()
                    if other.is_active and other.id != user.id
                ]
                if not other_admins:
                    raise ValueError(
                        "Refusing to deactivate the last active admin: nobody would be "
                        "able to sign in and manage the system"
                    )
            user.is_active = active
            db.commit()
            db.refresh(user)
            return {"user": _user_out(user), "updated": True}

        raise ValueError(f"Unknown action '{action}' for manage_users")
    except Exception as exc:
        db.rollback()
        return _error(exc)


# ── projects ─────────────────────────────────────────────────────────────────

def manage_projects(
    db: Session,
    action: str,
    caller_agent_id: Optional[int] = None,
    **params: Any,
) -> Any:
    """Create, edit, wire up and delete projects."""
    try:
        action = (action or "").strip().lower()
        project_id = params.get("project_id")

        if action == "list":
            projects = db.query(Project).order_by(Project.id.asc()).all()
            if not params.get("include_inactive"):
                projects = [project for project in projects if project.is_active]
            projects = _limit(_search_filter(projects, params.get("search")), params.get("limit"))
            return {"projects": [_project_out(project) for project in projects]}

        if action == "get":
            project = _need(db, Project, project_id, "project")
            out = _project_out(project, workflow=True)
            out["agents"] = [_agent_out(agent) for agent in project.agents]
            out["users"] = [_user_out(user) for user in project.users]
            return {"project": out}

        if action == "create":
            name = (params.get("name") or "").strip()
            if not name:
                raise ValueError("name is required to create a project")
            project = Project(
                name=name,
                description=params.get("description"),
                is_active=True if params.get("is_active") is None else bool(params.get("is_active")),
                workflow=_parse_workflow(params.get("workflow")),
            )
            for user in _users_by_ids(db, params.get("user_ids")):
                project.users.append(user)
            for agent in _agents_by_ids(db, params.get("agent_ids")):
                project.agents.append(agent)
            db.add(project)
            db.commit()
            db.refresh(project)
            return {"project": _project_out(project, workflow=True), "created": True}

        if action == "update":
            project = _need(db, Project, project_id, "project")
            _guard_system_project(project)
            for field in ("name", "description", "is_active"):
                if params.get(field) is not None:
                    setattr(project, field, params[field])
            if params.get("workflow") is not None:
                project.workflow = _parse_workflow(params["workflow"])
            db.commit()
            db.refresh(project)
            return {"project": _project_out(project, workflow=True), "updated": True}

        if action == "set_workflow":
            project = _need(db, Project, project_id, "project")
            project.workflow = _parse_workflow(params.get("workflow"))
            db.commit()
            db.refresh(project)
            return {"project": _project_out(project, workflow=True), "updated": True}

        if action == "delete":
            project = _need(db, Project, project_id, "project")
            _guard_system_project(project)
            db.delete(project)
            db.commit()
            return {"deleted": True, "project_id": project_id}

        if action == "assign_user":
            project = _need(db, Project, project_id, "project")
            user = _need(db, User, params.get("user_id"), "user")
            if all(member.id != user.id for member in project.users):
                project.users.append(user)
                db.commit()
            return {"project": _project_out(project), "assigned": True}

        if action == "remove_user":
            project = _need(db, Project, project_id, "project")
            user = _need(db, User, params.get("user_id"), "user")
            if any(member.id == user.id for member in project.users):
                project.users.remove(user)
                db.commit()
            return {"project": _project_out(project), "removed": True}

        if action == "assign_agent":
            project = _need(db, Project, project_id, "project")
            agent = _need(db, Agent, params.get("agent_id"), "agent")
            if all(member.id != agent.id for member in project.agents):
                project.agents.append(agent)
                db.commit()
            return {"project": _project_out(project), "assigned": True}

        if action in ("attach_agent", "detach_agent"):
            project = _need(db, Project, project_id, "project")
            agent = _need(db, Agent, params.get("agent_id"), "agent")
            if action == "detach_agent":
                _guard_home_project(caller_agent_id, agent, project)
            if action == "attach_agent":
                if all(member.id != agent.id for member in project.agents):
                    project.agents.append(agent)
                project.workflow = workflow_with_agent(project.workflow, agent)
            else:
                project.workflow = _workflow_without_agent(project.workflow, agent.id)
                if any(member.id == agent.id for member in project.agents):
                    project.agents.remove(agent)
            db.commit()
            db.refresh(project)
            return {"project": _project_out(project, workflow=True), "updated": True}

        if action == "remove_agent":
            return manage_projects(
                db, "detach_agent", caller_agent_id=caller_agent_id, **params
            )

        if action == "list_tables":
            project = _need(db, Project, project_id, "project")
            return {
                "project_id": project.id,
                "table_names": sorted(row.table_name for row in project.tables),
            }

        if action == "assign_table":
            project = _need(db, Project, project_id, "project")
            name = (params.get("table_name") or "").strip()
            if not name:
                raise ValueError("table_name is required")
            existing = (
                db.query(ProjectTable)
                .filter(ProjectTable.project_id == project.id, ProjectTable.table_name == name)
                .first()
            )
            if existing is None:
                db.add(
                    ProjectTable(
                        project_id=project.id,
                        table_name=name,
                        description=params.get("description"),
                    )
                )
                db.commit()
            return {"project_id": project.id, "table_name": name, "assigned": True}

        if action == "remove_table":
            project = _need(db, Project, project_id, "project")
            name = (params.get("table_name") or "").strip()
            db.query(ProjectTable).filter(
                ProjectTable.project_id == project.id, ProjectTable.table_name == name
            ).delete()
            db.commit()
            return {"project_id": project.id, "table_name": name, "removed": True}

        raise ValueError(f"Unknown action '{action}' for manage_projects")
    except Exception as exc:
        db.rollback()
        return _error(exc)


def _users_by_ids(db: Session, user_ids: Optional[list[int]]) -> list[User]:
    wanted = {int(user_id) for user_id in (user_ids or [])}
    if not wanted:
        return []
    users = db.query(User).filter(User.id.in_(wanted)).all()
    missing = sorted(wanted - {user.id for user in users})
    if missing:
        raise ValueError(f"These users do not exist: {missing}")
    return users


def _agents_by_ids(db: Session, agent_ids: Optional[list[int]]) -> list[Agent]:
    wanted = {int(agent_id) for agent_id in (agent_ids or [])}
    if not wanted:
        return []
    agents = db.query(Agent).filter(Agent.id.in_(wanted)).all()
    missing = sorted(wanted - {agent.id for agent in agents})
    if missing:
        raise ValueError(f"These agents do not exist: {missing}")
    return agents


def _parse_workflow(value: Any) -> Any:
    """Accept the workflow as a JSON string (what a model sends) or as a dict."""
    if value is None or isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        text_value = value.strip()
        if not text_value:
            return None
        try:
            return json.loads(text_value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"workflow is not valid JSON: {exc}") from exc
    raise ValueError("workflow must be a JSON string or an object")


def _workflow_nodes(workflow: Any) -> dict[str, Any]:
    if not isinstance(workflow, dict):
        return {"nodes": [], "wires": []}
    nodes = workflow.get("nodes")
    wires = workflow.get("wires")
    return {
        "nodes": nodes if isinstance(nodes, list) else [],
        "wires": wires if isinstance(wires, list) else [],
    }


def _new_group_workflow() -> dict[str, Any]:
    """The minimal shape the agent loop can walk: start -> group -> stop.

    The canvas reads top to bottom -- ports are on the top and bottom edges of a
    node -- so the skeleton is stacked, not laid out left to right, and the stop
    sits one minimum gap under an empty group (78px tall, see GROUP_MIN_HEIGHT in
    the panel). A horizontal skeleton left the panel drawing a chain that ran off
    the right edge of its column.
    """
    return {
        "nodes": [
            {"id": 1, "type": "start", "label": "Start", "x": 60, "y": 40, "outputs": []},
            {"id": 2, "type": "group", "label": "Default Group", "x": 30, "y": 104, "agents": []},
            {"id": 3, "type": "stop", "label": "Stop", "x": 60, "y": 210, "outputs": []},
        ],
        "wires": [
            {"id": "1-out->2-in", "fromNode": 1, "fromPort": "1-out", "toNode": 2, "toPort": "2-in"},
            {"id": "2-out->3-in", "fromNode": 2, "fromPort": "2-out", "toNode": 3, "toPort": "3-in"},
        ],
    }


def _next_node_id(workflow: dict[str, Any]) -> int:
    ids = [node.get("id") for node in workflow["nodes"] if isinstance(node.get("id"), int)]
    return (max(ids) + 1) if ids else 1


def ensure_workflow(workflow: Any) -> dict[str, Any]:
    """Return a walkable workflow, adding the start/stop skeleton when missing."""
    current = _workflow_nodes(workflow)
    if not current["nodes"] or not any(node.get("type") == "start" for node in current["nodes"]):
        return _new_group_workflow()
    for node in current["nodes"]:
        if node.get("type") == "group" and not isinstance(node.get("agents"), list):
            node["agents"] = []
    return current


def _first_group(workflow: dict[str, Any]) -> dict[str, Any]:
    group = next((node for node in workflow["nodes"] if node.get("type") == "group"), None)
    if group is None:
        group = {
            "id": _next_node_id(workflow),
            "type": "group",
            "label": "Default Group",
            "agents": [],
        }
        workflow["nodes"].append(group)
    return group


def workflow_with_agent(workflow: Any, agent: Agent) -> dict[str, Any]:
    current = ensure_workflow(workflow)
    group = _first_group(current)
    if not any(entry.get("id") == agent.id for entry in group["agents"]):
        group["agents"].append({"id": agent.id, "name": agent.name})
    return current


def _workflow_without_agent(workflow: Any, agent_id: int) -> dict[str, Any]:
    current = ensure_workflow(workflow)
    for node in current["nodes"]:
        if node.get("type") != "group" or not isinstance(node.get("agents"), list):
            continue
        node["agents"] = [entry for entry in node["agents"] if entry.get("id") != agent_id]
    return current


# ── agents ───────────────────────────────────────────────────────────────────

def _agents_query(db: Session) -> Any:
    return db.query(Agent).options(
        selectinload(Agent.skills),
        selectinload(Agent.tools),
        selectinload(Agent.projects),
    )


def manage_agents(
    db: Session,
    action: str,
    caller_agent_id: Optional[int] = None,
    **params: Any,
) -> Any:
    """Create, edit, connect and delete agents."""
    try:
        action = (action or "").strip().lower()
        agent_id = params.get("agent_id")

        if action == "list":
            agents = _agents_query(db).order_by(Agent.id.asc()).all()
            if not params.get("include_inactive"):
                agents = [agent for agent in agents if agent.is_active]
            if params.get("project_id") is not None:
                wanted = int(params["project_id"])
                agents = [
                    agent
                    for agent in agents
                    if any(project.id == wanted for project in agent.projects)
                ]
            agents = _limit(_search_filter(agents, params.get("search")), params.get("limit"))
            return {"agents": [_agent_out(agent) for agent in agents]}

        if action == "get":
            agent = _agents_query(db).filter(Agent.id == agent_id).first()
            if agent is None:
                raise ValueError(f"There is no agent with id {agent_id}")
            return {"agent": _agent_out(agent)}

        if action == "create":
            name = (params.get("name") or "").strip()
            if not name:
                raise ValueError("name is required to create an agent")
            agent = Agent(
                name=name,
                description=params.get("description"),
                is_active=True if params.get("is_active") is None else bool(params.get("is_active")),
            )
            agent.skills = _active_skills(db, params.get("skill_ids") or [])
            if params.get("project_id") is not None:
                project = _need(db, Project, int(params["project_id"]), "project")
                agent.projects.append(project)
            db.add(agent)
            db.commit()
            db.refresh(agent)
            return {"agent": _agent_out(agent), "created": True}

        if action == "update":
            agent = _need(db, Agent, agent_id, "agent")
            if params.get("name") is not None:
                agent.name = params["name"]
            if params.get("description") is not None:
                agent.description = params["description"]
            if params.get("is_active") is not None:
                if not bool(params["is_active"]):
                    _guard_self(caller_agent_id, agent)
                agent.is_active = bool(params["is_active"])
            if params.get("skill_ids") is not None:
                _guard_self(caller_agent_id, agent)
                agent.skills = _active_skills(db, params["skill_ids"])
            db.commit()
            db.refresh(agent)
            return {"agent": _agent_out(agent), "updated": True}

        if action == "set_skills":
            agent = _need(db, Agent, agent_id, "agent")
            _guard_self(caller_agent_id, agent)
            agent.skills = _active_skills(db, params.get("skill_ids") or [])
            db.commit()
            db.refresh(agent)
            return {"agent": _agent_out(agent), "updated": True}

        if action == "set_active":
            agent = _need(db, Agent, agent_id, "agent")
            _guard_self(caller_agent_id, agent)
            agent.is_active = bool(params.get("is_active"))
            db.commit()
            db.refresh(agent)
            return {"agent": _agent_out(agent), "updated": True}

        if action == "delete":
            agent = _need(db, Agent, agent_id, "agent")
            _guard_self(caller_agent_id, agent)
            project_ids = sorted(project.id for project in agent.projects)
            for project in list(agent.projects):
                project.workflow = _workflow_without_agent(project.workflow, agent.id)
            agent.projects.clear()
            db.delete(agent)
            db.commit()
            return {"deleted": True, "agent_id": agent_id, "projects_unwired": project_ids}

        if action == "assign_to_project":
            agent = _need(db, Agent, agent_id, "agent")
            project = _need(db, Project, params.get("project_id"), "project")
            if all(member.id != agent.id for member in project.agents):
                project.agents.append(agent)
            project.workflow = workflow_with_agent(project.workflow, agent)
            db.commit()
            return {"agent": _agent_out(agent), "assigned": True}

        if action == "remove_from_project":
            agent = _need(db, Agent, agent_id, "agent")
            project = _need(db, Project, params.get("project_id"), "project")
            _guard_home_project(caller_agent_id, agent, project)
            project.workflow = _workflow_without_agent(project.workflow, agent.id)
            if any(member.id == agent.id for member in project.agents):
                project.agents.remove(agent)
            db.commit()
            return {"agent": _agent_out(agent), "removed": True}

        raise ValueError(f"Unknown action '{action}' for manage_agents")
    except Exception as exc:
        db.rollback()
        return _error(exc)


# ── skills ───────────────────────────────────────────────────────────────────

def _skills_query(db: Session) -> Any:
    return db.query(Skill).options(selectinload(Skill.tools), selectinload(Skill.agents))


def manage_skills(
    db: Session,
    action: str,
    caller_agent_id: Optional[int] = None,
    **params: Any,
) -> Any:
    """Create skills and decide which tools each one carries.

    A tool only reaches an agent through a skill, so `set_tools` is how a newly
    created tool is handed to an agent.
    """
    try:
        action = (action or "").strip().lower()
        skill_id = params.get("skill_id")

        if action == "list":
            skills = _skills_query(db).order_by(Skill.id.asc()).all()
            if not params.get("include_inactive"):
                skills = [skill for skill in skills if skill.is_active]
            if params.get("agent_id") is not None:
                wanted = int(params["agent_id"])
                skills = [
                    skill for skill in skills if any(agent.id == wanted for agent in skill.agents)
                ]
            skills = _limit(_search_filter(skills, params.get("search")), params.get("limit"))
            return {"skills": [_skill_out(skill) for skill in skills]}

        if action == "get":
            skill = _need(db, Skill, skill_id, "skill")
            out = _skill_out(skill)
            out["tools"] = [_tool_out(tool) for tool in skill.tools]
            return {"skill": out}

        if action == "create":
            name = (params.get("name") or "").strip()
            if not name:
                raise ValueError("name is required to create a skill")
            skill = Skill(
                name=name,
                description=params.get("description"),
                is_active=True if params.get("is_active") is None else bool(params.get("is_active")),
            )
            skill.tools = _active_tools(db, params.get("tool_ids") or [])
            db.add(skill)
            db.commit()
            db.refresh(skill)
            return {"skill": _skill_out(skill), "created": True}

        if action == "update":
            skill = _need(db, Skill, skill_id, "skill")
            if params.get("name") is not None:
                skill.name = params["name"]
            if params.get("description") is not None:
                skill.description = params["description"]
            if params.get("tool_ids") is not None:
                _guard_own_skill(caller_agent_id, skill)
                skill.tools = _active_tools(db, params["tool_ids"])
            if params.get("is_active") is not None:
                if not bool(params["is_active"]):
                    _guard_own_skill(caller_agent_id, skill)
                skill.is_active = bool(params["is_active"])
            db.commit()
            db.refresh(skill)
            return {"skill": _skill_out(skill), "updated": True}

        if action == "set_tools":
            skill = _need(db, Skill, skill_id, "skill")
            _guard_own_skill(caller_agent_id, skill)
            skill.tools = _active_tools(db, params.get("tool_ids") or [])
            db.commit()
            db.refresh(skill)
            return {"skill": _skill_out(skill), "updated": True}

        if action == "set_active":
            skill = _need(db, Skill, skill_id, "skill")
            _guard_own_skill(caller_agent_id, skill)
            skill.is_active = bool(params.get("is_active"))
            db.commit()
            db.refresh(skill)
            return {"skill": _skill_out(skill), "updated": True}

        if action == "delete":
            skill = _need(db, Skill, skill_id, "skill")
            _guard_own_skill(caller_agent_id, skill)
            db.delete(skill)
            db.commit()
            return {"deleted": True, "skill_id": skill_id}

        if action == "attach_to_agent":
            skill = _need(db, Skill, skill_id, "skill")
            agent = _need(db, Agent, params.get("agent_id"), "agent")
            if all(member.id != skill.id for member in agent.skills):
                agent.skills.append(skill)
                db.commit()
            return {"skill": _skill_out(skill), "attached": True}

        if action == "detach_from_agent":
            skill = _need(db, Skill, skill_id, "skill")
            agent = _need(db, Agent, params.get("agent_id"), "agent")
            _guard_self(caller_agent_id, agent)
            if any(member.id == skill.id for member in agent.skills):
                agent.skills.remove(skill)
                db.commit()
            return {"skill": _skill_out(skill), "detached": True}

        raise ValueError(f"Unknown action '{action}' for manage_skills")
    except Exception as exc:
        db.rollback()
        return _error(exc)


# ── tools ────────────────────────────────────────────────────────────────────

def manage_tools(
    db: Session,
    action: str,
    caller_agent_id: Optional[int] = None,
    **params: Any,
) -> Any:
    """Create tools, which means writing their JSON spec and their Python body.

    `description` is the OpenAI function spec as a JSON string and `body` is
    Python source that must define a function of the same name - the same shape
    the /admin tools screen edits. A tool only reaches an agent through a skill,
    so creating one is normally followed by
    `manage_skills action=set_tools skill_id=... tool_ids=[...]`.
    """
    try:
        action = (action or "").strip().lower()
        tool_id = params.get("tool_id")

        if action == "list":
            tools = (
                db.query(Tool)
                .options(selectinload(Tool.skills))
                .order_by(Tool.id.asc())
                .all()
            )
            if not params.get("include_inactive"):
                tools = [tool for tool in tools if tool.is_active]
            tools = _limit(_search_filter(tools, params.get("search")), params.get("limit"))
            return {"tools": [_tool_out(tool) for tool in tools]}

        if action == "get":
            tool = _need(db, Tool, tool_id, "tool")
            return {"tool": _tool_out(tool, full=True)}

        if action == "create":
            name = (params.get("name") or "").strip()
            if not name:
                raise ValueError("name is required to create a tool")
            description = _tool_spec(params.get("description"), name, params.get("body"))
            tool = Tool(
                name=name,
                description=description,
                type=(params.get("type") or "python"),
                body=params.get("body"),
                is_active=True if params.get("is_active") is None else bool(params.get("is_active")),
            )
            db.add(tool)
            db.commit()
            db.refresh(tool)
            return {"tool": _tool_out(tool), "created": True}

        if action == "update":
            tool = _need(db, Tool, tool_id, "tool")
            if params.get("name") is not None:
                tool.name = params["name"]
            if params.get("type") is not None:
                tool.type = params["type"]
            if params.get("body") is not None:
                tool.body = params["body"]
            if params.get("description") is not None or params.get("body") is not None:
                tool.description = _tool_spec(
                    tool.description if params.get("description") is None else params["description"],
                    tool.name,
                    tool.body,
                )
            if params.get("is_active") is not None:
                if not bool(params["is_active"]):
                    _guard_own_tool(db, caller_agent_id, tool)
                tool.is_active = bool(params["is_active"])
            db.commit()
            db.refresh(tool)
            return {"tool": _tool_out(tool, full=True), "updated": True}

        if action == "set_active":
            tool = _need(db, Tool, tool_id, "tool")
            _guard_own_tool(db, caller_agent_id, tool)
            tool.is_active = bool(params.get("is_active"))
            db.commit()
            db.refresh(tool)
            return {"tool": _tool_out(tool), "updated": True}

        if action == "delete":
            tool = _need(db, Tool, tool_id, "tool")
            _guard_own_tool(db, caller_agent_id, tool)
            db.delete(tool)
            db.commit()
            return {"deleted": True, "tool_id": tool_id}

        raise ValueError(f"Unknown action '{action}' for manage_tools")
    except Exception as exc:
        db.rollback()
        return _error(exc)


def _tool_spec(description: Any, name: str, body: Any) -> Optional[str]:
    """Check the function spec and the body agree before they are stored.

    A mismatch is the mistake that costs the most time here: `tool_exec` refuses
    to run a tool whose body does not define the declared function, and the
    failure only shows up when the agent calls it.
    """
    if description is None:
        return None
    source = description if isinstance(description, str) else json.dumps(description)
    try:
        spec = json.loads(source)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "description must be the OpenAI function spec as JSON, for example "
            '{"type": "function", "function": {"name": "do_thing", "description": '
            '"...", "parameters": {"type": "object", "properties": {}, "required": []}}}: '
            + str(exc)
        ) from exc
    if not isinstance(spec, dict):
        raise ValueError("description JSON must be an object")
    function_def = spec.get("function")
    if not isinstance(function_def, dict) or not function_def.get("name"):
        raise ValueError('description JSON must carry function.name, e.g. {"function": {"name": "do_thing"}}')
    function_name = str(function_def["name"])
    if body:
        if not isinstance(body, str):
            raise ValueError("body must be Python source as a string")
        try:
            tree = ast.parse(body)
        except SyntaxError as exc:
            raise ValueError(f"body is not valid Python: {exc}") from exc
        defined = [node.name for node in tree.body if isinstance(node, ast.FunctionDef)]
        if function_name not in defined:
            raise ValueError(
                f"body must define a function called '{function_name}' to match "
                f"function.name; it defines {defined or 'nothing'}"
            )
    return source


# ── storage ──────────────────────────────────────────────────────────────────

def _storage_api() -> Any:
    """The storage router, whose helpers own table/row knowledge.

    Imported at call time: `app.routers.storage` pulls in the schemas and the
    engine, and nothing here needs that to be loaded just to import the module.
    """
    from app import routers

    return routers.storage


def _all_table_names() -> list[str]:
    return sorted(_storage_api()._physical_table_names())


def _require_table(table_name: str) -> str:
    if not table_name:
        raise ValueError("table_name is required")
    if table_name not in _storage_api()._physical_table_names():
        raise ValueError(f"There is no table named '{table_name}'")
    return table_name


def _require_new_table_name(table_name: str, db: Session) -> str:
    api = _storage_api()
    name = api._slug(table_name, "")
    if not name:
        raise ValueError("table_name is required")
    if name in api._INTERNAL_TABLES or name in api._SYSTEM_TABLES:
        raise ValueError(f"'{name}' is a reserved table name")
    if table_name != name:
        raise ValueError(f"Table names are lower-case slugs; use '{name}'")
    if name in api._physical_table_names():
        raise ValueError(f"Table '{name}' already exists")
    return name


def _physical_table(db: Session, table_name: str) -> Any:
    api = _storage_api()
    return api._reflect_table(_require_table(table_name), db.connection())


def _normalized_columns(columns: list[Any]) -> list[dict[str, Any]]:
    from app.schemas.schemas import StorageColumnInput

    if not isinstance(columns, list):
        raise ValueError("columns must be a list of column objects")
    parsed = []
    for column in columns:
        if not isinstance(column, dict):
            raise ValueError("each column must be an object")
        try:
            parsed.append(StorageColumnInput(**column))
        except Exception as exc:
            raise ValueError(f"Could not read column {column}: {exc}") from exc
    return _storage_api()._normalize_columns(parsed)


def _row_values(physical: Any, data: Any, *, partial: bool) -> dict[str, Any]:
    api = _storage_api()
    if not isinstance(data, dict) or not data:
        raise ValueError("data must be an object of column name to value")
    values: dict[str, Any] = {}
    unknown = []
    for name, value in data.items():
        if name in ("id", "created_at", "updated_at"):
            continue
        if name not in physical.c:
            unknown.append(name)
            continue
        values[name] = api._coerce_value(value, physical.c[name])
    if unknown:
        raise ValueError(
            f"These columns do not exist on '{physical.name}': {unknown}; "
            f"it has {[column.name for column in physical.c]}"
        )
    if "created_at" in physical.c and not partial:
        values["created_at"] = func.now()
    if "updated_at" in physical.c:
        values["updated_at"] = func.now()
    return values


def _table_out(db: Session, table_name: str) -> dict[str, Any]:
    info = _storage_api()._table_info(db, table_name)
    # Column names are left to get_table: a list of tables with every column on
    # each one would be pages of text for a question like "what tables are there".
    return {
        "name": info.name,
        "row_count": info.row_count,
        "column_count": len(info.columns),
        "is_system": info.is_system,
        "project_ids": sorted(project.id for project in info.projects),
    }


def _dump(model: Any) -> dict[str, Any]:
    """A pydantic model as a plain dict, safe to hand to json.dumps.

    `mode="json"` because a row can carry a datetime; ToolExec serialises these
    returns itself, and would fail on anything json cannot encode.
    """
    return model.model_dump(mode="json")


def _table_info_out(db: Session, table_name: str) -> dict[str, Any]:
    return _dump(_storage_api()._table_info(db, table_name))


def manage_storage(
    db: Session,
    action: str,
    caller_agent_id: Optional[int] = None,
    **params: Any,
) -> Any:
    """Create tables, edit their columns and read or write their rows."""
    try:
        action = (action or "").strip().lower()
        table_name = (params.get("table_name") or "").strip()

        if action == "list_tables":
            return {"tables": [_table_out(db, name) for name in _all_table_names()]}

        if action == "get_table":
            _require_table(table_name)
            return {"table": _table_info_out(db, table_name)}

        if action == "create_table":
            name = _require_new_table_name(table_name, db)
            columns = _normalized_columns(params.get("columns") or [])
            _storage_api()._create_physical_table(db, name, columns, params.get("description"))
            return {"table": _table_info_out(db, name), "created": True}

        if action == "add_column":
            _require_table(table_name)
            columns = _normalized_columns([params.get("column") or {}])
            _storage_api()._add_column(db, table_name, columns[0])
            db.commit()
            return {"table": _table_info_out(db, table_name), "added": True}

        if action == "delete_table":
            _require_table(table_name)
            if table_name in _storage_api()._SYSTEM_TABLES:
                raise ValueError(f"'{table_name}' is a system table and cannot be dropped")
            db.execute(text(f'DROP TABLE "{table_name}"'))
            db.query(ProjectTable).filter(ProjectTable.table_name == table_name).delete()
            db.commit()
            return {"deleted": True, "table_name": table_name}

        if action == "list_rows":
            physical = _physical_table(db, table_name)
            search = (params.get("search") or "").strip()
            query = select(physical)
            if search:
                like = f"%{search}%"
                conditions = [
                    cast(column, String).ilike(like) for column in physical.c if column.name != "id"
                ]
                if conditions:
                    query = query.where(or_(*conditions))
            sort_by = params.get("sort_by") or "id"
            if sort_by not in physical.c:
                raise ValueError(
                    f"Unknown sort column '{sort_by}'; the table has "
                    f"{[column.name for column in physical.c]}"
                )
            direction = str(params.get("sort_dir") or "asc").lower()
            order = physical.c[sort_by].desc() if direction == "desc" else physical.c[sort_by].asc()
            limit = max(1, min(int(params.get("limit") or 25), 200))
            offset = max(0, int(params.get("offset") or 0))
            rows = db.execute(query.order_by(order).offset(offset).limit(limit)).all()
            total = db.execute(select(func.count()).select_from(query.subquery())).scalar() or 0
            api = _storage_api()
            return {
                "table_name": table_name,
                "total": total,
                "limit": limit,
                "offset": offset,
                "rows": [_dump(api._row_to_out(row, physical)) for row in rows],
            }

        if action == "insert_row":
            physical = _physical_table(db, table_name)
            values = _row_values(physical, params.get("data") or {}, partial=False)
            _storage_api()._ensure_required_columns(physical, values)
            result = db.execute(physical.insert().values(**values))
            db.commit()
            return {
                "inserted": True,
                "table_name": table_name,
                "id": result.inserted_primary_key[0],
            }

        if action == "update_row":
            physical = _physical_table(db, table_name)
            row_id = params.get("row_id")
            if row_id is None:
                raise ValueError("row_id is required for update_row")
            values = _row_values(physical, params.get("data") or {}, partial=True)
            if values:
                db.execute(physical.update().where(physical.c.id == int(row_id)).values(**values))
                db.commit()
            return {"updated": True, "table_name": table_name, "id": int(row_id)}

        if action == "delete_row":
            physical = _physical_table(db, table_name)
            row_id = params.get("row_id")
            if row_id is None:
                raise ValueError("row_id is required for delete_row")
            db.execute(physical.delete().where(physical.c.id == int(row_id)))
            db.commit()
            return {"deleted": True, "table_name": table_name, "id": int(row_id)}

        if action == "assign_table":
            project = _need(db, Project, params.get("project_id"), "project")
            _require_table(table_name)
            existing = (
                db.query(ProjectTable)
                .filter(ProjectTable.project_id == project.id, ProjectTable.table_name == table_name)
                .first()
            )
            if existing is None:
                db.add(ProjectTable(project_id=project.id, table_name=table_name))
                db.commit()
            return {"project_id": project.id, "table_name": table_name, "assigned": True}

        if action == "remove_table":
            project = _need(db, Project, params.get("project_id"), "project")
            db.query(ProjectTable).filter(
                ProjectTable.project_id == project.id, ProjectTable.table_name == table_name
            ).delete()
            db.commit()
            return {"project_id": project.id, "table_name": table_name, "removed": True}

        raise ValueError(f"Unknown action '{action}' for manage_storage")
    except Exception as exc:
        db.rollback()
        return _error(exc)
