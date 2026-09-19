# CerebrumKit

A starting point for agentic projects. You get an admin panel where agents are
built out of **skills** and **tools**, a storage library of business tables you
can hand those agents, and a client panel where the people the project is for
talk to them.

Nothing in here belongs to any particular business: no catalogue, no orders, no
product tables. What is here is the machinery every such project needs, so a new
project starts at "what should the agents do" instead of at "how do I run an
agent loop".

## What you get

- **Projects** - a project groups members, agents and the storage tables they
  may use, and holds the **workflow**: start / groups / stop, wired on a canvas,
  which decides which agents answer a message and in what order.
- **Agents** - a name, a description that is its system prompt, and the skills
  it carries. It answers chats in the project it belongs to.
- **Skills and tools** - a tool is an OpenAI function spec plus a Python body
  (both stored in the database, both editable in the panel). A skill is a
  written instruction plus the tools it needs. Give an agent the skill and the
  tools come with it. A generator turns a description into a first draft spec.
- **Storage** - create tables in the panel and they exist in the database, with
  import/export to Excel and row editing. Tables are assigned to projects, and a
  tool can read and write them.
- **Chats** - a websocket per chat drives the agent loop: it picks the agents
  from the workflow, runs the tools they ask for, streams tool cards and text
  into the transcript, and can be stopped mid-run.
- **Memory** - agents can write notes about a user, keyed by agent and user so a
  note written in one chat is readable in that user's other chats with the same
  agent.
- **Delegation** - one agent can hand a self-contained task to another agent in
  the project and use the answer.
- **Users and roles** - `admin` sees everything and builds the projects;
  `client` sees their own projects and chats and nothing else.
- **The System project** - a project that cannot be renamed or deleted, holding
  a **Project Manager** agent whose tools let it create and edit users,
  projects, agents, skills, tools and storage tables. An install can be
  administered by asking it in chat.

## Requirements

- Python 3.12+ and Node 20+
- PostgreSQL (or SQLite for a quick look, by leaving `DATABASE_URL` on its
  default)

## Quickstart

```bash
# 1. Database
docker compose up -d              # or point DATABASE_URL at an existing server
createdb cerebrumkit              # when you run Postgres yourself

# 2. Backend
cd backend
python -m venv venv
venv/Scripts/python.exe -m pip install -r requirements.txt      # Windows
# source venv/bin/activate && pip install -r requirements.txt   # macOS / Linux
cp .env.example .env              # then set DATABASE_URL, SECRET_KEY,
                                  # DEEPSEEK_* and the SEED_* accounts
venv/Scripts/python.exe seed_all.py

# 3. Frontend
cd ../frontend/cerebrumkit-vue
npm install
npm run dev
```

Open <http://localhost:5173> and sign in with the `SEED_ADMIN_EMAIL` /
`SEED_PASSWORD` you set in `backend/.env`.

`seed_all.py` creates the tables, the country list, the admin and client
accounts, the general tools and skills, and the System project with its Project
Manager agent. Every step is idempotent, so running it again is safe.

It also copies `DEEPSEEK_*` into the `platforms` table, which is what the system
actually runs on. After that, Admin -> Settings -> LLM Connections is the place
to change provider, base URL, API key or model: the active row is used by the
whole system, and the `DEEPSEEK_*` values only matter while the table is empty.

On Windows you can also double-click through `run.ps1`, which starts both
servers and `stop.ps1` stops them.

## First project

Either build it in the panel (Projects -> Create Project), or ask the Project
Manager in the System project's chat to do it for you. The order that works:

1. **Storage** - create the tables the project owns, with a description on the
   table and on each column. Tools read these, and the agent sees the
   descriptions.
2. **Tools** - one per thing an agent should be able to do. Write the Python
   body if you know it, or describe the tool and let the generator draft the
   spec. Bodies run with `project_id`, `chat_id`, `agent_id`, `user_id` and
   `call_depth` already in scope.
3. **Skills** - group the tools under written instructions: when to use them,
   what to pass, how to read the result.
4. **Agents** - a description that is the agent's standing brief, plus the
   skills it carries. Optional: tools to run *before* every message, whose
   output is injected into the prompt (useful for "always know the catalogue").
5. **Project** - assign the tables, add the agents, and wire the workflow so
   messages reach them.
6. **Users** - create client accounts and add them to the project; they see only
   their own projects and chats.

Change the seeded passwords before anyone else can reach the install.

## Layout

```
backend/
  app/
    core/          agent loop, tool execution, delegation, auth, config
    models/        SQLAlchemy models: users, projects, agents, skills, tools,
                   chats, messages, memory, storage registry
    routers/       REST + websocket API
    schemas/       request/response models
    system_management.py   the manage_* tools the Project Manager uses
  seed_all.py      fresh install in one command
  seed_*.py        the individual seed steps
  export_for_deploy.py, load_for_deploy.py   move data between installs
frontend/cerebrumkit-vue/
  src/views/admin/     Projects (agents, chats, workflow), Skills, Tools,
                       Storage, Users
  src/views/client/    Projects and the chat with the agents
  src/locales/         en, zh, ru, es, fr, de
```

## How it fits together

A message arrives on the chat websocket. The agent loop reads the project
workflow, picks the agent or group that should answer, builds the system prompt
from the agent's description plus its skills plus any pre-run tool output, and
calls the model. Tool calls come back as function calls; each is executed
against the tool body stored in the database, with the project, chat, agent and
user ids injected so a tool can only ever touch its own run. Results go back to
the model, and the text it produces is broadcast to the chat.

Tool and skill definitions live in the database rather than in the code, so
editing one in the panel takes effect on the next run with no restart and no
deploy.

## Deploying

See `DEPLOY.md` for nginx, systemd and a rebuild path that keeps the database
rows (tools, skills, agents) in step with the code.

## Adding a business domain

Add your models under `backend/app/models/`, register them in
`app/models/__init__.py`, add routers and schemas the same way, and create the
tables with `backend/migrate.py`. Anything a project needs at runtime is better
as a tool over the storage library, because then the people who own the project
can change it without a deploy.
