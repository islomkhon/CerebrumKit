# CerebrumKit backend

FastAPI + SQLAlchemy. Serves the admin and client panels, the chat websocket
with the agent loop, and the storage library.

## Setup

```bash
python -m venv venv
venv/Scripts/python.exe -m pip install -r requirements.txt
cp .env.example .env
```

`.env` keys:

| Key | Meaning |
| --- | --- |
| `DATABASE_URL` | `postgresql://user:pass@host:5432/cerebrumkit`, or a `sqlite:///` path |
| `SECRET_KEY` | signs the JWTs; generate a fresh one per install |
| `ALGORITHM` | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | session lifetime |
| `DEEPSEEK_API_KEY` | model provider key used by the agent loop |
| `DEEPSEEK_MODEL` | model name |

A missing or placeholder `SECRET_KEY` logs a warning at startup: tokens signed
with it are forgeable.

## Scripts

Run them from this directory with the venv's Python. Every one is idempotent.

| Script | Does |
| --- | --- |
| `migrate.py` | creates the tables from the models (`Base.metadata.create_all`) |
| `seed_all.py` | runs the six steps below in order - the fresh-install command |
| `seed_countries.py` | the ISO country list with calling codes |
| `seed.py` | the admin and client accounts (`--force` wipes and reseeds) |
| `seed_general_tools.py` | the general tools and skills, from `seed_general_tools.json` |
| `seed_system_project.py` | the System project, its Project Manager agent, the `manage_*` tools and the delegation skill |
| `seed_system_descriptions.py` | comments for the system tables and columns, shown in the storage library |
| `export_for_deploy.py` | dumps every table to gzipped CSV for another install |
| `load_for_deploy.py` | loads such a dump, parent-first, fixing sequences |

## Run

```bash
venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Swagger at <http://localhost:8000/docs>, ReDoc at `/redoc`.

## API

All routes need `Authorization: Bearer <token>` unless noted.

- `/auth` - login, current user
- `/admin/projects`, `/client/projects` - the two panels' project APIs,
  including agents, skills, tools, chats, workflow and messages
- `/admin/users` - user management
- `/admin/storage` - the storage library: tables, rows, Excel import/export
- `/admin/tools`, `/admin/skills`, `/admin/agents` - definitions and the tool
  generator
- `/chats` - legacy chat endpoints, still used by the older views
- `/ws/chats/{id}?token=...` - the chat websocket; carries `message`, `stop`,
  `typing` and `ping` inbound, and message, tool-card, typing and
  `agent_loop_status` events outbound
- `/health` - no token needed

## The agent loop

`app/core/agent_loop.py` runs one turn:

1. Resolve the project's workflow and the agent (or group) that answers.
2. Build the system prompt: the agent's description, the text of each skill it
   carries, and the output of any **pre-run context tools** configured on the
   agent (`agent_context_tools`, capped at 24k characters).
3. Call the model with the agent's tools as function specs.
4. Execute the tool calls it asks for through `app/core/tool_exec.py`, which
   checks that the project, chat, agent and tool all exist, are active and
   belong together, validates the arguments against the spec, and only then runs
   the body.
5. Feed the results back and repeat until the model answers in text, then
   broadcast it.

### Tool bodies

A tool body is Python stored in `tools.body`. It defines a function whose name
must match `function.name` in `tools.description`. Beyond its own parameters it
sees these names already bound, injected per call by `ToolExec`:

| Name | Value |
| --- | --- |
| `project_id` | the project the run belongs to |
| `chat_id` | the chat the run belongs to |
| `agent_id` | the agent that called the tool |
| `user_id` | the chat's owner - who the run answers for |
| `call_depth` | delegation depth, 0 for a user-initiated run |

Tools therefore scope themselves instead of being told what to look at, and a
tool can never reach another project, chat, agent or user.

### Delegation

`call_agent` (`app/core/delegation.py`) runs another agent with a self-contained
message and returns its answer. It is refused when called from the event loop
thread, because the answer arrives on that same loop, and it is depth-limited.

## Notes for operating it

- **One uvicorn worker.** The websocket registry and in-flight agent tasks live
  in process memory; a second worker would broadcast into a chat it cannot see.
- **Tool, skill and agent rows live in the database.** A code-only deploy leaves
  them behind - see `DEPLOY.md` for how to move them.
