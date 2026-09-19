"""Seed the protected system project and the Project Manager agent that runs it.

Run from the backend directory:

    python seed_system_project.py

It is idempotent: rows are matched by name and updated in place, so running it
again after editing a tool body here pushes the new body to the database.

What it creates
---------------
* Project "System", marked `is_system`, so `routers/projects.py` refuses to edit
  or delete the row itself. Everything inside it - members, agents, skills,
  tools, its workflow - stays editable, which is what lets the Project Manager
  manage the rest of the system.
* The tools that do that managing: users, projects, agents, skills, tools and
  storage tables, plus one that hands a message to another agent.
* Skill "System Administration" holding those tools.
* Agent "Project Manager" carrying that skill, wired into the project workflow.
* Context tools on that agent: the lookups it runs by itself before it reads
  the message, each under the heading it is placed in the prompt with.

The tools it installs call `app.system_management`; the delegation tool calls
`app.core.delegation`. Nothing here talks to the REST API.
"""

import json
import sys

from app.core.agent_loop import DELEGATION_TOOL_NAMES
from app.core.database import Base, SessionLocal, engine
from app.models import Agent, AgentContextTool, Project, Skill, Tool, User
from app.system_management import ensure_workflow, workflow_with_agent

PROJECT_NAME = "System"
PROJECT_DESCRIPTION = (
    "The system's own project. It holds the Project Manager agent, which manages "
    "users, projects, agents, skills, tools and tables for the whole system. This "
    "project cannot be edited or deleted."
)
MANAGER_AGENT_NAME = "Project Manager"
MANAGER_AGENT_DESCRIPTION = (
    "Administrator of this system. Manages users, projects, agents, skills, tools and "
    "storage tables, and can hand a task to any other agent in this project."
)
ADMIN_SKILL_NAME = "System Administration"
ADMIN_SKILL_DESCRIPTION = (
    "Full administration of the system: users, projects, agents, skills, tools, "
    "storage tables, and delegating work to other agents."
)
# Delegation is its own skill rather than part of system administration, because
# every agent in a project can usefully hand work to another one - it is not an
# administrative privilege.
DELEGATION_SKILL_NAME = "Delegate a Self-Contained Task to Another Agent"
DELEGATION_SKILL_DESCRIPTION = """# Delegating Tasks to Another Agent

## Purpose
Hand a self-contained piece of work to another agent in the current project and receive that agent's answer back, so specialized knowledge or parallel effort can be used without losing the context of the current conversation.

## When to Use This Skill
- The work belongs to another agent's scope, expertise, or data in this project.
- You can state the whole request in writing, with no reliance on this conversation or the user's original message.
- You already know the integer id of a target agent that is a member of this project.

Do not use this skill for work you can complete yourself, for clarifying questions with the user, or for long chains of delegation. Agents may call agents, but only a few levels deep.

## Instructions
1. **Pick the target agent.** `agent_id` must be an integer id of an agent that is a member of this project. If you do not have a valid project member id, do the work yourself instead.
2. **Write a standalone message.** The other agent does not see this conversation, the user's message, or any prior tool output. The `message` string must therefore carry everything needed: background, the exact deliverable, constraints, and the expected output format.
3. **Make the call.**
   ```
   call_agent(agent_id=<project member id>, message="<complete, self-contained request>")
   ```
4. **Use the answer.** The return value is the other agent's reply. Check it against your own requirements and fold it into your work or your response to the user.
5. **Keep delegation shallow.** Because nesting is only a few levels deep, prefer doing the work locally or flattening the request rather than chaining multiple agent calls.

## Notes
- Both `agent_id` and `message` are required; a call without either is invalid.
- One call returns one answer. For multiple independent deliverables, issue separate calls with separate, self-contained messages.
- Never assume the target agent shares your state, files, or chat history."""
# The delegation tool's name comes from the agent loop, because that is where the
# longer tool timeout is keyed off it.
DELEGATION_TOOL_NAME = sorted(DELEGATION_TOOL_NAMES)[0]

# Tools that already exist in most installs and are just as useful to the Project
# Manager. They are attached when present and skipped with a note when not.
SHARED_TOOL_NAMES = ["environment_info", "conversation_lookup", "memory_write", "memory_lookup"]

# What the Project Manager looks up on its own before it reads the message, in
# the order the prompt should read. Each entry is the tool name, the heading
# written above that tool's output, and the JSON arguments for a tool that needs
# them. The tool has to reach the agent through a skill first, which is why these
# are all in SHARED_TOOL_NAMES above.
MANAGER_CONTEXT_TOOLS = [
    ("environment_info", "The environment you are running in", None),
    ("memory_lookup", "The things you learned", None),
]


# ── function specs ───────────────────────────────────────────────────────────

def _spec(function_name, description, properties, required=("action",)):
    """Build the OpenAI function spec stored in `tools.description`."""
    return json.dumps(
        {
            "type": "function",
            "function": {
                "name": function_name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": list(required),
                },
            },
        },
        ensure_ascii=False,
        indent=2,
    )


def _enum(values, description):
    return {"type": "string", "enum": values, "description": description}


ACTION_REQUIRED = "Which operation to perform."

USER_ID = {"type": "integer", "description": "User id, for actions that target one user."}
PROJECT_ID = {"type": "integer", "description": "Project id, for actions that target one project."}
AGENT_ID = {"type": "integer", "description": "Agent id, for actions that target one agent."}
SKILL_ID = {"type": "integer", "description": "Skill id, for actions that target one skill."}
TOOL_ID = {"type": "integer", "description": "Tool id, for actions that target one tool."}
TABLE_NAME = {"type": "string", "description": "Table name, for actions that target one table."}
SEARCH = {"type": "string", "description": "Only return rows whose name (or email) contains this text."}
LIMIT = {"type": "integer", "description": "Maximum number of rows to return. Defaults to 25, at most 200."}
INCLUDE_INACTIVE = {
    "type": "boolean",
    "description": "Also include inactive rows. Defaults to false, which lists only active ones.",
}
IS_ACTIVE = {"type": "boolean", "description": "Whether the row should be active."}

USER_PROPERTIES = {
    "action": _enum(
        ["list", "get", "create", "update", "set_active"],
        "list users, get one user, create a user, update a user, or activate/deactivate one.",
    ),
    "user_id": USER_ID,
    "name": {"type": "string", "description": "Full name of the user."},
    "email": {"type": "string", "description": "Login email. Must be unique across the system."},
    "password": {"type": "string", "description": "Password. Required by create; on update it is only changed when given."},
    "role": _enum(["admin", "client"], "admin can open the admin panel; client only sees their own projects."),
    "language": {"type": "string", "description": "Two-letter language code, for example en, ru or zh."},
    "country_id": {"type": "integer", "description": "Country id, when the user has one."},
    "is_active": IS_ACTIVE,
    "search": SEARCH,
    "limit": LIMIT,
    "include_inactive": INCLUDE_INACTIVE,
}

PROJECT_PROPERTIES = {
    "action": _enum(
        [
            "list",
            "get",
            "create",
            "update",
            "set_workflow",
            "delete",
            "assign_user",
            "remove_user",
            "assign_agent",
            "attach_agent",
            "detach_agent",
            "list_tables",
            "assign_table",
            "remove_table",
        ],
        "list projects, get one project, create one, rename or describe one, replace its "
        "workflow, delete one, add or remove a member user, add or remove an agent, "
        "attach an agent to the workflow group, list or change its assigned tables.",
    ),
    "project_id": PROJECT_ID,
    "name": {"type": "string", "description": "Project name."},
    "description": {"type": "string", "description": "Short description of the project."},
    "is_active": IS_ACTIVE,
    "workflow": {
        "type": "string",
        "description": 'The workflow as a JSON string: {"nodes": [...], "wires": [...]} with '
        "start, group and stop nodes. Ask for the current one with action=get first; "
        "attach_agent/detach_agent edit it for you.",
    },
    "user_id": USER_ID,
    "agent_id": AGENT_ID,
    "table_name": TABLE_NAME,
    "user_ids": {"type": "array", "items": {"type": "integer"}, "description": "User ids to add a new project to."},
    "agent_ids": {"type": "array", "items": {"type": "integer"}, "description": "Agent ids to add a new project to."},
    "search": SEARCH,
    "limit": LIMIT,
    "include_inactive": INCLUDE_INACTIVE,
}

AGENT_PROPERTIES = {
    "action": _enum(
        [
            "list",
            "get",
            "create",
            "update",
            "set_skills",
            "set_active",
            "delete",
            "assign_to_project",
            "remove_from_project",
        ],
        "list agents, get one agent, create one, rename or describe one, replace the skills "
        "it carries, activate/deactivate one, delete one, or add/remove it from a project.",
    ),
    "agent_id": AGENT_ID,
    "name": {"type": "string", "description": "Agent name."},
    "description": {"type": "string", "description": "What this agent is for. It is given to the agent as its instructions."},
    "skill_ids": {
        "type": "array",
        "items": {"type": "integer"},
        "description": "Skill ids this agent should carry. This replaces its current skills.",
    },
    "project_id": PROJECT_ID,
    "is_active": IS_ACTIVE,
    "search": SEARCH,
    "limit": LIMIT,
    "include_inactive": INCLUDE_INACTIVE,
}

SKILL_PROPERTIES = {
    "action": _enum(
        ["list", "get", "create", "update", "set_tools", "set_active", "delete", "attach_to_agent", "detach_from_agent"],
        "list skills, get one skill, create one, rename or describe one, replace the tools it "
        "carries, activate/deactivate one, delete one, or give/remove it from an agent.",
    ),
    "skill_id": SKILL_ID,
    "agent_id": AGENT_ID,
    "name": {"type": "string", "description": "Skill name."},
    "description": {"type": "string", "description": "What the skill covers."},
    "tool_ids": {
        "type": "array",
        "items": {"type": "integer"},
        "description": "Tool ids this skill should contain. This replaces its current tools.",
    },
    "is_active": IS_ACTIVE,
    "search": SEARCH,
    "limit": LIMIT,
    "include_inactive": INCLUDE_INACTIVE,
}

TOOL_PROPERTIES = {
    "action": _enum(
        ["list", "get", "create", "update", "set_active", "delete"],
        "list tools, get one tool with its spec and body, create one, update one, "
        "activate/deactivate one, or delete one.",
    ),
    "tool_id": TOOL_ID,
    "name": {"type": "string", "description": "Tool name."},
    "description": {
        "type": "string",
        "description": 'Required by create: the OpenAI function spec as a JSON string, for example '
        '{"type": "function", "function": {"name": "do_thing", "description": "...", '
        '"parameters": {"type": "object", "properties": {...}, "required": [...]}}}.',
    },
    "type": {"type": "string", "description": 'Tool type, normally "function".'},
    "body": {
        "type": "string",
        "description": "Python source for the tool. It must define a function with the same name "
        "as function.name. ToolExec puts project_id, chat_id, agent_id and call_depth in scope, "
        "so a body can scope itself to the run that called it without the model passing ids.",
    },
    "is_active": IS_ACTIVE,
    "search": SEARCH,
    "limit": LIMIT,
    "include_inactive": INCLUDE_INACTIVE,
}

STORAGE_PROPERTIES = {
    "action": _enum(
        [
            "list_tables",
            "get_table",
            "create_table",
            "add_column",
            "delete_table",
            "list_rows",
            "insert_row",
            "update_row",
            "delete_row",
            "assign_table",
            "remove_table",
        ],
        "list the tables, read one table with its columns, create a table, add a column, "
        "drop a table, read rows, insert a row, update a row, delete a row, or assign/unassign "
        "a table to/from a project.",
    ),
    "table_name": TABLE_NAME,
    "description": {"type": "string", "description": "Table or column description, shown in the storage screen."},
    "columns": {
        "type": "array",
        "items": {"type": "object"},
        "description": "Columns for create_table: objects with name, data_type "
        "(string, text, integer, bigInteger, float, boolean, date, datetime or json), "
        "nullable (default true), length and default_value.",
    },
    "column": {
        "type": "object",
        "description": "One column for add_column, in the same shape as an item of columns.",
    },
    "data": {
        "type": "object",
        "description": "Column name to value, for insert_row and update_row. Unknown columns are refused.",
    },
    "row_id": {"type": "integer", "description": "Row id, for update_row and delete_row."},
    "project_id": PROJECT_ID,
    "search": SEARCH,
    "limit": LIMIT,
    "offset": {"type": "integer", "description": "Rows to skip when listing. Defaults to 0."},
    "sort_by": {"type": "string", "description": "Column to sort by when listing rows. Defaults to id."},
    "sort_dir": _enum(["asc", "desc"], "Sort direction when listing rows. Defaults to asc."),
}

CALL_AGENT_PROPERTIES = {
    "agent_id": {"type": "integer", "description": "Id of the agent to call. It must be a member of this project."},
    "message": {
        "type": "string",
        "description": "The request for that agent, written on its own: it does not see this "
        "conversation or the user's message, only what you put here.",
    },
}


# ── tool bodies ──────────────────────────────────────────────────────────────

def _manage_body(function_name, module_function, summary):
    """A body that is only wiring: the rules live in app.system_management.

    A body is compiled from a string by `tool_exec`, so it imports what it needs
    itself. `project_id`, `chat_id`, `agent_id` and `call_depth` arrive as system
    variables rather than parameters (see `tool_exec.SYSTEM_VARIABLES`), which is
    why the caller's own agent id can be passed to the guards below without the
    model ever supplying it.
    """
    return f'''def {function_name}(action, **params):
    """{summary}"""
    _caller_agent_id = agent_id

    from app.core.database import SessionLocal
    from app import system_management

    db = SessionLocal()
    try:
        return system_management.{module_function}(
            db, action, caller_agent_id=_caller_agent_id, **params
        )
    finally:
        db.close()
'''


CALL_AGENT_BODY = '''# The run's own ids are system variables (see app.core.tool_exec.SYSTEM_VARIABLES).
# They are read into module level here because this tool's `agent_id` parameter
# is the agent to call, not the agent doing the calling.
_caller_agent_id = agent_id
_project_id = project_id
_chat_id = chat_id
_call_depth = call_depth


def call_agent(agent_id, message):
    """Hand a request to another agent and return its answer."""
    from app.core import delegation

    return delegation.call_agent(
        target_agent_id=agent_id,
        message=message,
        chat_id=_chat_id,
        project_id=_project_id,
        caller_agent_id=_caller_agent_id,
        call_depth=_call_depth,
    )
'''


TOOLS = [
    {
        "name": "manage_users",
        "spec": _spec(
            "manage_users",
            "Create, edit and deactivate the system's user accounts. Use action=list to find "
            "ids, then action=get for one user in detail. New users get a password you choose; "
            "action=set_active is how an account is disabled, because deleting a user would "
            "take their chats with it.",
            USER_PROPERTIES,
        ),
        "body": _manage_body("manage_users", "manage_users", "Create, edit and deactivate user accounts."),
    },
    {
        "name": "manage_projects",
        "spec": _spec(
            "manage_projects",
            "Create, rename, describe and delete projects, and control who and what belongs to "
            "them. attach_agent both adds an agent to the project and wires it into the "
            "workflow group, which is what makes the project answer messages; a project with an "
            "empty group runs nothing. The system project cannot be edited or deleted.",
            PROJECT_PROPERTIES,
        ),
        "body": _manage_body("manage_projects", "manage_projects", "Create, edit, wire up and delete projects."),
    },
    {
        "name": "manage_agents",
        "spec": _spec(
            "manage_agents",
            "Create and edit agents and control which skills each one carries. An agent needs at "
            "least one skill to have any tools, and must be attached to a project before it can "
            "answer. An agent cannot change or delete itself.",
            AGENT_PROPERTIES,
        ),
        "body": _manage_body("manage_agents", "manage_agents", "Create, edit, connect and delete agents."),
    },
    {
        "name": "manage_skills",
        "spec": _spec(
            "manage_skills",
            "Create skills, decide which tools each skill contains, and give skills to agents. A "
            "tool is only reachable by an agent through a skill, so a new tool is handed over "
            "with action=set_tools.",
            SKILL_PROPERTIES,
        ),
        "body": _manage_body("manage_skills", "manage_skills", "Create skills and decide which tools each one carries."),
    },
    {
        "name": "manage_tools",
        "spec": _spec(
            "manage_tools",
            "Create and edit tools. A tool is two things that must agree: `description`, the "
            "OpenAI function spec as JSON, and `body`, Python that defines a function with the "
            "same name. ToolExec runs the body with project_id, chat_id, agent_id and call_depth "
            "in scope. Reading a tool with action=get returns both so you can edit it.",
            TOOL_PROPERTIES,
        ),
        "body": _manage_body("manage_tools", "manage_tools", "Create and edit tools, their JSON spec and their Python body."),
    },
    {
        "name": "manage_storage",
        "spec": _spec(
            "manage_storage",
            "Create and edit the database tables behind the storage screen, and read or write "
            "their rows. Every table gets id, created_at and updated_at automatically. Create a "
            "table, then assign it to a project so that project's tools can query it.",
            STORAGE_PROPERTIES,
        ),
        "body": _manage_body("manage_storage", "manage_storage", "Create tables and read or write their rows."),
    },
    {
        "name": DELEGATION_TOOL_NAME,
        "spec": _spec(
            DELEGATION_TOOL_NAME,
            "Hand a piece of work to another agent in this project and get its answer back. The "
            "other agent does not see this conversation, so the message must stand on its own. "
            "Agents can call agents, but only a few levels deep, so do not use this for work you "
            "can do yourself.",
            CALL_AGENT_PROPERTIES,
            required=("agent_id", "message"),
        ),
        "body": CALL_AGENT_BODY,
    },
]


# ── seeding ──────────────────────────────────────────────────────────────────

def _upsert_tool(db, spec):
    """Create the tool, or update it in place so re-runs push new bodies."""
    tool = db.query(Tool).filter(Tool.name == spec["name"]).first()
    created = tool is None
    if created:
        tool = Tool(name=spec["name"])
        db.add(tool)
    tool.description = spec["spec"]
    tool.body = spec["body"]
    tool.type = "function"
    tool.is_active = True
    db.flush()
    return tool, created


def _upsert_context_tools(db, agent):
    """Match an agent's pre-run lookups to MANAGER_CONTEXT_TOOLS, in order.

    Rows are matched by (agent, tool), so re-running updates the heading and the
    position in place. An entry this file no longer lists is dropped, the same
    way `skills` is set rather than appended to - the seeded state stays the
    state this file describes.
    """
    links = []
    for position, (name, comment, arguments) in enumerate(MANAGER_CONTEXT_TOOLS):
        tool = db.query(Tool).filter(Tool.name == name).first()
        if tool is None:
            print(f"[!!] context tool '{name}' is not in this database; skipping it")
            continue
        link = next(
            (row for row in agent.context_tool_links if row.tool_id == tool.id),
            None,
        )
        if link is None:
            # Appending through the relationship is what fills in agent_id.
            link = AgentContextTool(tool_id=tool.id)
            agent.context_tool_links.append(link)
            print(f"[new] context tool '{tool.name}' -> {agent.name}")
        else:
            print(f"[upd] context tool '{tool.name}' -> {agent.name}")
        link.comment = comment
        link.arguments = json.dumps(arguments) if arguments is not None else None
        link.position = position
        links.append(link)

    wanted = {link.tool_id for link in links}
    for link in list(agent.context_tool_links):
        if link.tool_id not in wanted:
            db.delete(link)
            print(f"[del] context tool id {link.tool_id} -> {agent.name}")
    db.flush()
    return links


def _resolve_system_project(db):
    """The project marked is_system, or the one named 'System', or a new row."""
    project = db.query(Project).filter(Project.is_system.is_(True)).first()
    if project is not None:
        return project, False
    project = db.query(Project).filter(Project.name == PROJECT_NAME).first()
    if project is not None:
        return project, False
    return Project(name=PROJECT_NAME), True


def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        project, created_project = _resolve_system_project(db)
        if created_project:
            db.add(project)
        project.name = project.name or PROJECT_NAME
        project.description = PROJECT_DESCRIPTION
        project.is_system = True
        project.is_active = True
        db.flush()
        print(f"[{'new' if created_project else '..'}] project {project.id} '{project.name}' (is_system=True)")

        # Admins are the people who are meant to reach this project.
        admins = (
            db.query(User)
            .filter(User.role == "admin", User.is_active.is_(True))
            .order_by(User.id.asc())
            .all()
        )
        added_users = []
        for admin in admins:
            if all(member.id != admin.id for member in project.users):
                project.users.append(admin)
                added_users.append(admin.email)
        if added_users:
            print(f"[..] added admins to the project: {', '.join(added_users)}")

        # Tools, then the skill that carries them.
        tool_rows = []
        for spec in TOOLS:
            tool, created = _upsert_tool(db, spec)
            tool_rows.append(tool)
            print(f"[{'new' if created else 'upd'}] tool {tool.id} '{tool.name}'")

        skill = db.query(Skill).filter(Skill.name == ADMIN_SKILL_NAME).first()
        if skill is None:
            skill = Skill(name=ADMIN_SKILL_NAME)
            db.add(skill)
            print(f"[new] skill '{ADMIN_SKILL_NAME}'")
        else:
            print(f"[upd] skill {skill.id} '{skill.name}'")
        skill.description = ADMIN_SKILL_DESCRIPTION
        skill.is_active = True

        shared = []
        for name in SHARED_TOOL_NAMES:
            tool = db.query(Tool).filter(Tool.name == name).first()
            if tool is None:
                print(f"[!!] tool '{name}' is not in this database; skipping it")
                continue
            shared.append(tool)
        if shared:
            print(f"[..] also attaching: {', '.join(tool.name for tool in shared)}")
        skill.tools = tool_rows + shared
        db.flush()

        # The delegation skill travels with the tool it describes.
        delegation_skill = (
            db.query(Skill).filter(Skill.name == DELEGATION_SKILL_NAME).first()
        )
        if delegation_skill is None:
            delegation_skill = Skill(name=DELEGATION_SKILL_NAME)
            db.add(delegation_skill)
            print(f"[new] skill '{DELEGATION_SKILL_NAME}'")
        else:
            print(f"[upd] skill {delegation_skill.id} '{delegation_skill.name}'")
        delegation_skill.description = DELEGATION_SKILL_DESCRIPTION
        delegation_skill.is_active = True
        delegation_tool = (
            db.query(Tool).filter(Tool.name == DELEGATION_TOOL_NAME).first()
        )
        delegation_skill.tools = [delegation_tool] if delegation_tool else []
        db.flush()

        # The agent that runs all of it.
        agent = db.query(Agent).filter(Agent.name == MANAGER_AGENT_NAME).first()
        if agent is None:
            agent = Agent(name=MANAGER_AGENT_NAME)
            db.add(agent)
            print(f"[new] agent '{MANAGER_AGENT_NAME}'")
        else:
            print(f"[upd] agent {agent.id} '{agent.name}'")
        agent.description = MANAGER_AGENT_DESCRIPTION
        agent.is_active = True
        agent.skills = [skill, delegation_skill]
        db.flush()

        context_links = _upsert_context_tools(db, agent)

        if all(member.id != agent.id for member in project.agents):
            project.agents.append(agent)

        # Wire it into the workflow, creating the start/group/stop skeleton when
        # the project has none.
        project.workflow = workflow_with_agent(project.workflow, agent)
        db.commit()

        print()
        print(f"System project : {project.id}  ({project.name})")
        print(f"Project Manager: {agent.id}  ({agent.name})")
        print(f"Skill          : {skill.id}  ({len(skill.tools)} tools)")
        print(f"Skill          : {delegation_skill.id}  ({len(delegation_skill.tools)} tools)")
        print(f"Context tools  : {len(context_links)} on the Project Manager")
        print(f"Workflow       : {json.dumps(project.workflow)[:160]}")
        print()
        print("Open the admin panel, pick this project's chat and ask the Project Manager.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(seed())
