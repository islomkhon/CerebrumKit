"""Create the accounts you sign in with.

A fresh install has no users, and without a user there is no way into the
panels. This creates one administrator and one client, each in a country, and
stops there: projects, agents, skills and tools are built from the admin panel
or by asking the Project Manager agent - that is the point of the framework.

Countries come from seed_countries.py, which must run first; the country a user
is put in is matched by ISO code, and a missing country is reported rather than
invented.

    python seed.py
    python seed.py --force     # wipe the data and seed again

The accounts are configuration, not source: the emails and the password are read
from SEED_ADMIN_EMAIL, SEED_CLIENT_EMAIL and SEED_PASSWORD (see .env.example),
so no working credential is ever committed and two installs never share one.
"""

import sys
import os

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
# .env is resolved relative to the process directory, so settle that before the
# app package is imported.
os.chdir(BACKEND_DIR)
sys.path.insert(0, BACKEND_DIR)

from sqlalchemy import text  # noqa: E402

import app.models  # noqa: F401,E402 - registers every model on Base.metadata
from app.core.database import SessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models.country import Country  # noqa: E402
from app.models.user import User  # noqa: E402

ADMINS = [
    {
        "name": "Admin",
        "email": os.getenv("SEED_ADMIN_EMAIL", ""),
        "country_code": os.getenv("SEED_ADMIN_COUNTRY", "CN"),
    },
]

CLIENTS = [
    {
        "name": "Client",
        "email": os.getenv("SEED_CLIENT_EMAIL", ""),
        "country_code": os.getenv("SEED_CLIENT_COUNTRY", "CN"),
    },
]

PASSWORD = os.getenv("SEED_PASSWORD", "")


def _require_credentials() -> None:
    """Refuse to seed until the accounts to create are supplied via the environment.

    There is deliberately no fallback value for any of these. A default email or
    password in the source tree is a credential that ships with every checkout
    and is identical on every install, which is exactly what an attacker who has
    read the repository tries first.
    """
    missing = [
        name
        for name, value in (
            ("SEED_ADMIN_EMAIL", ADMINS[0]["email"]),
            ("SEED_CLIENT_EMAIL", CLIENTS[0]["email"]),
            ("SEED_PASSWORD", PASSWORD),
        )
        if not value
    ]
    if missing:
        raise SystemExit(
            "Set " + ", ".join(missing) + " before seeding - the accounts to create "
            "come from the environment. See backend/.env.example."
        )

# Every table the seeder owns, child-first, so --force can empty the database
# without tripping a foreign key.
WIPE_ORDER = [
    "UPDATE chats SET last_message_id = NULL",
    "DELETE FROM messages",
    "DELETE FROM chats",
    "DELETE FROM memory",
    "DELETE FROM agent_context_tools",
    "DELETE FROM project_tables",
    "DELETE FROM user_project",
    "DELETE FROM agent_project",
    "DELETE FROM agent_skill",
    "DELETE FROM skill_tool",
    "DELETE FROM projects",
    "DELETE FROM skills",
    "DELETE FROM tools",
    "DELETE FROM agents",
    "DELETE FROM users",
]


def _country(db, code):
    country = db.query(Country).filter(Country.code == code).first()
    if country is None:
        raise SystemExit(
            f"No country with code '{code}' is in the database. Run "
            "seed_countries.py first, or change the SEED_*_COUNTRY value in .env."
        )
    return country


def _add_users(db, rows, role):
    created = []
    for row in rows:
        email = row["email"]
        if db.query(User).filter(User.email == email).first() is not None:
            print(f"  [..] {role:<6} {email} already exists")
            continue
        user = User(
            name=row["name"],
            email=email,
            password=hash_password(PASSWORD),
            role=role,
            country_id=_country(db, row["country_code"]).id,
            language="en",
            is_active=True,
        )
        db.add(user)
        created.append(user)
        print(f"  [new] {role:<6} {user.name} <{user.email}>")
    return created


def seed(force=False):
    _require_credentials()
    db = SessionLocal()
    try:
        existing = db.query(User).count()
        if existing and not force:
            print(f"[SKIP] {existing} users are already in this database.")
            print("       Run with --force to wipe the data and seed again.")
            return
        if existing and force:
            print(f"[WIPE] Removing {existing} users and the data around them...")
            for statement in WIPE_ORDER:
                db.execute(text(statement))
            db.commit()
            print("[WIPE] Done.")

        _add_users(db, ADMINS, "admin")
        _add_users(db, CLIENTS, "client")
        db.commit()

        print()
        print("Sign in with the SEED_ADMIN_EMAIL / SEED_PASSWORD you configured.")
    finally:
        db.close()


if __name__ == "__main__":
    seed(force="--force" in sys.argv)
