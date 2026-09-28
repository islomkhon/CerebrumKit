"""Write `frontend/cerebrumkit-vue/src/demo/fixtures.json` from the live database.

The hosted demo is a static build of the real panel. GitHub Pages can serve the
Vue bundle but it cannot run FastAPI, so the panel in that build reads its data
from a JSON snapshot taken here instead of from the API. Everything in it is
read through the application's own schemas, so the snapshot cannot drift from
the shapes the panel expects.

Run it against a database that is already seeded:

    python seed_all.py
    python seed_demo_showcase.py
    python export_demo_fixtures.py

Two things this deliberately does not do:

* It never writes a real API key. Every platform key is replaced with a
  placeholder before it reaches the file, because the file is published to a
  public site. Re-running this against a development database that holds a live
  key is therefore safe.
* It does not copy memory rows or anything else the demo cannot show.

    python export_demo_fixtures.py [output-path]
"""

import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import app.models  # noqa: F401  registers every table on Base.metadata
from app.core.database import SessionLocal, engine
from app.models import Agent, Chat, Message, Platform, Project, ProjectTable, Skill, Tool, User
from app.routers.storage import _physical_table_names, _reflect_table, _row_to_out, _table_info
from app.schemas.auth import UserOut
from app.schemas.schemas import (
    AgentOut,
    ChatOut,
    MessageOut,
    ProjectOut,
    SkillOut,
    StorageRowOut,
    ToolOut,
)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUT = os.path.join(
    REPO, "frontend", "cerebrumkit-vue", "src", "demo", "fixtures.json"
)

# What replaces a real key. Published, so it says what it is.
REDACTED_KEY = "sk-demo-placeholder-not-a-real-key"


def dump(model, rows):
    """Serialise ORM rows through the schema the API would have used."""
    return [model.model_validate(row).model_dump(mode="json") for row in rows]


def platform_rows(db):
    platforms = db.query(Platform).order_by(Platform.id).all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "base_url": p.base_url,
            "api_key": REDACTED_KEY,
            "model": p.model,
            "temperature": p.temperature,
            "max_tokens": p.max_tokens,
            "thinking": bool(p.thinking),
            "is_active": bool(p.is_active),
            "effective": bool(p.is_active) or index == 0,
        }
        for index, p in enumerate(platforms)
    ]


def storage_tables(db):
    tables = []
    rows = {}
    for name in _physical_table_names():
        info = _table_info(db, name)
        tables.append(info.model_dump(mode="json"))
        if info.is_system or name in _SKIP_ROW_EXPORT:
            continue
        physical = _reflect_table(name)
        try:
            result = db.execute(physical.select()).fetchall()
        except Exception as exc:  # a table the demo cannot read is not worth failing over
            print("  [warn] could not read rows from %s: %s" % (name, exc))
            continue
        rows[name] = [
            _row_to_out(row, physical).model_dump(mode="json") for row in result
        ]
    return tables, rows


# Tables whose contents are configuration, not sample business data.
_SKIP_ROW_EXPORT = {"countries"}


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.role == "admin").order_by(User.id).first()
        if admin is None:
            print("!! no admin account in this database - run seed_all.py first")
            return 1

        users = db.query(User).order_by(User.id).all()
        projects = db.query(Project).order_by(Project.id).all()
        agents = db.query(Agent).order_by(Agent.id).all()
        skills = db.query(Skill).order_by(Skill.id).all()
        tools = db.query(Tool).order_by(Tool.id).all()
        chats = db.query(Chat).order_by(Chat.id).all()
        messages = db.query(Message).order_by(Message.id).all()

        project_agents, project_users, project_tables = {}, {}, {}
        for project in projects:
            project_agents[str(project.id)] = [a.id for a in project.agents]
            project_users[str(project.id)] = [u.id for u in project.users]
        for link in db.query(ProjectTable).order_by(ProjectTable.id).all():
            project_tables.setdefault(str(link.project_id), []).append(link.table_name)

        by_chat = {}
        for message in messages:
            by_chat.setdefault(str(message.chat_id), []).append(
                MessageOut.model_validate(message).model_dump(mode="json")
            )

        tables, rows = storage_tables(db)

        fixtures = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "database": engine.dialect.name,
            "user": UserOut.model_validate(admin).model_dump(mode="json"),
            "users": dump(UserOut, users),
            "projects": dump(ProjectOut, projects),
            "agents": dump(AgentOut, agents),
            "skills": dump(SkillOut, skills),
            "tools": dump(ToolOut, tools),
            "platforms": platform_rows(db),
            "project_agents": project_agents,
            "project_users": project_users,
            "project_tables": project_tables,
            "storage_tables": tables,
            "storage_rows": rows,
            "chats": dump(ChatOut, chats),
            "chat_messages": by_chat,
        }
    finally:
        db.close()

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(fixtures, handle, indent=1, ensure_ascii=False)
        handle.write("\n")

    size = os.path.getsize(out_path)
    print("wrote %s" % out_path)
    print("  %d bytes" % size)
    print("  %d projects, %d agents, %d skills, %d tools, %d users"
          % (len(fixtures["projects"]), len(fixtures["agents"]), len(fixtures["skills"]),
             len(fixtures["tools"]), len(fixtures["users"])))
    print("  %d storage tables, %d chats, %d messages"
          % (len(fixtures["storage_tables"]), len(fixtures["chats"]), len(messages)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
