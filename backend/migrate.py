"""Create all database tables using SQLAlchemy metadata."""
import sys
import os

# Ensure backend is importable
sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import inspect, text

from app.core.database import engine, Base
from app.models import *  # noqa: F401, F403 — registers all models

Base.metadata.create_all(bind=engine)

inspector = inspect(engine)

if "tools" in inspector.get_table_names():
    column_names = {column["name"] for column in inspector.get_columns("tools")}
    if "description" not in column_names:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE tools ADD COLUMN description TEXT"))
        print("[OK] Added tools.description")

table_names = set(inspector.get_table_names())
if "agent_skill" in table_names and "skills" in table_names:
    skills_columns = {column["name"]: column for column in inspector.get_columns("skills")}
    dialect = engine.dialect.name
    if "agent_id" in skills_columns:
        with engine.begin() as connection:
            connection.execute(text("""
                INSERT INTO agent_skill (agent_id, skill_id)
                SELECT agent_id, id
                FROM skills
                WHERE agent_id IS NOT NULL
                ON CONFLICT DO NOTHING
            """))
        print("[OK] Synced skills.agent_id links into agent_skill")

        if dialect == "postgresql":
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE skills DROP COLUMN agent_id"))
            print("[OK] Dropped skills.agent_id")
        elif dialect == "sqlite":
            print("[INFO] SQLite cannot drop skills.agent_id with this simple migration")

# `platforms` starts empty on an install that was configured through .env, so
# the DeepSeek values there are copied in once. After that the panel owns the
# connection and this does nothing.
from app.core.database import SessionLocal
from app.core.llm import ensure_default_platform

_session = SessionLocal()
try:
    _platform = ensure_default_platform(_session)
finally:
    _session.close()

if _platform is not None:
    print(f"[OK] Added platform '{_platform.name}' ({_platform.model}) from .env")

print("[OK] All tables created successfully.")
print(f"  Tables: {list(Base.metadata.tables.keys())}")
