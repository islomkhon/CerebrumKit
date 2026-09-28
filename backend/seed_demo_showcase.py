"""Add the showcase content the hosted demo shows.

``seed_all.py`` ships the machinery: the System project, the Project Manager
agent, the general skills and tools. It deliberately ships no business data,
because CerebrumKit is not tied to any business - that is the point of the
project. The hosted demo still needs *some* business data to be worth looking
at, so this script adds one small, obviously sample slice: a customer-support
project with two agents on a canvas, a ``customers`` table, an ``orders`` table,
a demo chat, and a placeholder LLM row.

Nothing here is real, and the demo site says so on every screen. This script
runs only against the database ``DATABASE_URL`` points at, and it is
idempotent: running it again leaves what is already there alone.

    python seed_demo_showcase.py
"""

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text

import app.models  # noqa: F401  registers every table on Base.metadata
from app.core.database import SessionLocal, engine
from app.models import Agent, Chat, Message, Platform, Project, ProjectTable, Skill, User

NOW = datetime.now(timezone.utc)

# Explicit ids so re-running cannot duplicate rows, and so the fixtures the
# panel is built against are stable between runs.
CUSTOMERS = [
    (1, "Mira Halvorsen", "mira.halvorsen@example.com", "NO", "Prefers email."),
    (2, "Tomas Beaulieu", "tomas.b@example.com", "FR", None),
    (3, "Ravi Chandrasekhar", "ravi.c@example.com", "IN", "Buys in bulk."),
    (4, "Anne Okafor", "anne.okafor@example.com", "NG", None),
]

ORDERS = [
    (1, 1, "AC-10471", "delivered", 249.00, "EUR", -21, "Left with neighbour."),
    (2, 1, "AC-10477", "delayed", 189.50, "EUR", -4, "Warehouse pushed the date; customer not told."),
    (3, 2, "AC-10502", "shipped", 74.25, "EUR", 2, None),
    (4, 3, "AC-10520", "packed", 1310.00, "EUR", 3, "Palletised."),
    (5, 4, "AC-10531", "processing", 58.90, "EUR", 6, None),
    (6, 2, "AC-10544", "cancelled", 22.00, "EUR", None, "Customer cancelled after the delay."),
]

WORKFLOW = {
    "nodes": [
        {"id": 1, "type": "start", "label": "Start", "x": 60, "y": 40, "outputs": []},
        {
            "id": 2,
            "type": "group",
            "label": "Support Group",
            "x": 30,
            "y": 104,
            "agents": [{"id": 2, "name": "Support Agent"}, {"id": 3, "name": "Order Reviewer"}],
        },
        {"id": 3, "type": "stop", "label": "Stop", "x": 60, "y": 210, "outputs": []},
    ],
    "wires": [
        {"id": "1-out->2-in", "fromNode": 1, "fromPort": "1-out", "toNode": 2, "toPort": "2-in"},
        {"id": "2-out->3-in", "fromNode": 2, "fromPort": "2-out", "toNode": 3, "toPort": "3-in"},
    ],
}

MESSAGES = [
    ("user", 1, "Mira Halvorsen", "agent", 2, "Support Agent",
     "Order AC-10477 was meant to arrive on Tuesday and it still has not turned up. "
     "Can you apply the late-delivery credit?"),
    ("agent", 2, "Support Agent", "user", 1, "Mira Halvorsen",
     "Sorry about the wait. I have applied the late-delivery credit to AC-10477 - it "
     "should show against the order within the hour."),
    ("agent", 3, "Order Reviewer", None, None, None,
     "Checking that before it goes out: AC-10477 is in `delayed`, and the credit only "
     "applies while an order is `shipped` or `packed`. So there is no credit to give on "
     "this one. What it needs is a new promised date - the warehouse moved it four days "
     "and nobody told the customer."),
    ("user", 1, "Mira Halvorsen", "agent", 3, "Order Reviewer",
     "So what happens now?"),
    ("agent", 3, "Order Reviewer", "user", 1, "Mira Halvorsen",
     "Two things: AC-10477 gets a confirmed date from the warehouse, and because the "
     "delay was ours you get the goodwill credit manually - which is a decision for a "
     "person, not something either of us should apply on its own."),
]


def _table_exists(db, name):
    sql = "select name from sqlite_master where type='table' and name=:n"
    if not engine.dialect.name == "sqlite":
        sql = "select table_name from information_schema.tables where table_name=:n"
    return db.execute(text(sql), {"n": name}).first() is not None


def ensure_business_tables(db):
    """The two physical tables the storage library shows.

    They are created the way the storage router creates one - a plain table with
    the reserved `id`, `created_at`, `updated_at` columns - so the panel treats
    them exactly like tables an operator made by hand.
    """
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY,
            created_at DATETIME,
            updated_at DATETIME,
            name TEXT NOT NULL,
            email TEXT,
            country TEXT,
            notes TEXT
        )
    """))
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY,
            created_at DATETIME,
            updated_at DATETIME,
            customer_id INTEGER NOT NULL,
            reference TEXT NOT NULL,
            status TEXT NOT NULL,
            total REAL,
            currency TEXT,
            promised_on DATE,
            notes TEXT
        )
    """))
    db.commit()

    if db.execute(text("select count(*) from customers")).scalar() == 0:
        for cid, name, email, country, notes in CUSTOMERS:
            db.execute(
                text("insert into customers (id, created_at, updated_at, name, email, country, notes) "
                     "values (:id, :now, :now, :name, :email, :country, :notes)"),
                {"id": cid, "now": NOW, "name": name, "email": email, "country": country, "notes": notes},
            )
        print("[new] customers: %d rows" % len(CUSTOMERS))
    else:
        print("[skip] customers already has rows")

    if db.execute(text("select count(*) from orders")).scalar() == 0:
        for oid, cust, ref, status, total, cur, offset, notes in ORDERS:
            promised = None if offset is None else (NOW + timedelta(days=offset)).date()
            db.execute(
                text("insert into orders (id, created_at, updated_at, customer_id, reference, status, "
                     "total, currency, promised_on, notes) values (:id, :now, :now, :cust, :ref, "
                     ":status, :total, :cur, :promised, :notes)"),
                {"id": oid, "now": NOW, "cust": cust, "ref": ref, "status": status,
                 "total": total, "cur": cur, "promised": promised, "notes": notes},
            )
        print("[new] orders: %d rows (one is AC-10477, the delayed order)" % len(ORDERS))
    else:
        print("[skip] orders already has rows")
    db.commit()


def ensure_platform(db):
    if db.query(Platform).count() > 0:
        print("[skip] a platform row already exists")
        return
    # A placeholder, not a key. The demo has no model behind it, and shipping a
    # real key to a public site is not something this project is willing to do.
    db.add(Platform(
        name="DeepSeek (demo placeholder)",
        base_url="https://api.deepseek.com/v1",
        api_key="sk-demo-placeholder-not-a-real-key",
        model="deepseek-chat",
        is_active=True,
    ))
    db.commit()
    print("[new] platform row with a placeholder key")


def ensure_project(db):
    existing = db.query(Project).filter(Project.name == "Customer Support").first()
    if existing:
        print("[skip] project 'Customer Support' already exists")
        return existing

    project = Project(
        name="Customer Support",
        description="Sample project for the hosted demo: a support agent answers, a second "
                    "agent reviews the answer against the orders table before it is trusted.",
        is_active=True,
        is_system=False,
        workflow=WORKFLOW,
    )
    db.add(project)
    db.flush()

    support = Agent(
        id=2,
        name="Support Agent",
        description="Answers customer questions about their orders. Reads the orders table and "
                    "the customer's history, and is quick to promise a resolution.",
        is_active=True,
    )
    reviewer = Agent(
        id=3,
        name="Order Reviewer",
        description="Reviews what the Support Agent produced against the order's actual status "
                    "and the published policy, and says so when the two disagree.",
        is_active=True,
    )
    db.add_all([support, reviewer])
    db.flush()

    for agent, skill_names in (
        (support, ["Context & Memory Awareness", "REST API Requests"]),
        (reviewer, ["Context & Memory Awareness"]),
    ):
        for name in skill_names:
            skill = db.query(Skill).filter(Skill.name == name).first()
            if skill and skill not in agent.skills:
                agent.skills.append(skill)

    project.agents.extend([support, reviewer])

    client = db.query(User).filter(User.role == "client").order_by(User.id).first()
    if client:
        project.users.append(client)

    for table_name in ("customers", "orders"):
        db.add(ProjectTable(project_id=project.id, table_name=table_name,
                            description="Sample table for the hosted demo."))

    db.commit()
    print("[new] project 'Customer Support' with 2 agents on one canvas")
    return project


def ensure_chat(db, project):
    if not project:
        return
    existing = db.query(Chat).filter(Chat.project_id == project.id).first()
    if existing:
        print("[skip] a chat already exists for this project")
        return

    client = db.query(User).filter(User.role == "client").order_by(User.id).first()
    if not client:
        print("[skip] no client account to hang a chat off")
        return

    chat = Chat(
        user_id=client.id,
        project_id=project.id,
        new_messages_count=0,
        description="Sample conversation (static demo) - AC-10477, a delayed order",
    )
    db.add(chat)
    db.flush()

    last = None
    for i, (stype, sid, sname, rtype, rid, rname, content) in enumerate(MESSAGES):
        last = Message(
            chat_id=chat.id,
            sender_type=stype, sender_id=sid, sender_name=sname,
            receiver_type=rtype, receiver_id=rid, receiver_name=rname,
            message_type="text", content=content,
            created_at=NOW + timedelta(minutes=i),
        )
        db.add(last)
        db.flush()
    chat.last_message_id = last.id
    db.commit()
    print("[new] chat with a %d-message sample conversation" % len(MESSAGES))


def main():
    db = SessionLocal()
    try:
        print("database: %s" % str(engine.url))
        ensure_business_tables(db)
        ensure_platform(db)
        project = ensure_project(db)
        ensure_chat(db, project)
    finally:
        db.close()
    print()
    print("Showcase content ready. Export it with export_demo_fixtures.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
