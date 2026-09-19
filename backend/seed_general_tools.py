"""Seed the tools and skills that are not about any particular business.

These are the general parts of an agentic project: look back over the
conversation, remember things about the user, describe the environment the run
happens in, call an HTTP API, search the web, and hand a task to another agent.
They arrive already attached to skills, so a new agent only has to be given the
skill.

The definitions live in ``seed_general_tools.json`` beside this file: a tool is
a JSON function spec plus a Python body, which is data the database stores, so
keeping it as data avoids quoting Python inside Python string literals.

Idempotent: a tool or skill is matched by name and updated in place, so running
this again after fixing a body pushes the fix.

    python seed_general_tools.py
"""

import json
import os
import sys

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
# .env is resolved relative to the process directory, so settle that before the
# app package is imported.
os.chdir(BACKEND_DIR)
sys.path.insert(0, BACKEND_DIR)

import app.models  # noqa: F401,E402 - registers every model on Base.metadata
from app.core.database import SessionLocal  # noqa: E402
from app.models.skill import Skill  # noqa: E402
from app.models.tool import Tool  # noqa: E402

DATA_FILE = os.path.join(BACKEND_DIR, "seed_general_tools.json")


def _load():
    with open(DATA_FILE, encoding="utf-8") as handle:
        return json.load(handle)


def seed():
    data = _load()
    db = SessionLocal()
    try:
        for item in data["tools"]:
            tool = db.query(Tool).filter(Tool.name == item["name"]).first()
            created = tool is None
            if created:
                tool = Tool(name=item["name"])
                db.add(tool)
            tool.description = item["description"]
            tool.body = item["body"]
            tool.type = item.get("type") or "function"
            tool.is_active = item.get("is_active", True)
            # autoflush is off for this session, so the skill lookups below
            # would not see a tool added in this same pass without this.
            db.flush()
            print(f"[{'new' if created else 'upd'}] tool  {tool.name}")

        for item in data["skills"]:
            skill = db.query(Skill).filter(Skill.name == item["name"]).first()
            created = skill is None
            if created:
                skill = Skill(name=item["name"])
                db.add(skill)
            skill.description = item["description"]
            skill.is_active = item.get("is_active", True)

            attached = []
            for name in item["tools"]:
                tool = db.query(Tool).filter(Tool.name == name).first()
                if tool is None:
                    # A skill may name a tool another seeder owns (call_agent
                    # comes with the System project). Run that one first.
                    print(f"[!! ] tool '{name}' is not in this database; skipping it")
                    continue
                attached.append(tool)
            skill.tools = attached
            print(f"[{'new' if created else 'upd'}] skill {skill.name} ({len(attached)} tools)")

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    print()
    print("General tools and skills are in place. Give an agent the skill that")
    print("carries the tools it needs; the tools come with it.")


if __name__ == "__main__":
    seed()
