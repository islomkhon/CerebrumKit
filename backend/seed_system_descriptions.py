"""Seed descriptive comments for system tables and their columns.

Re-runnable: overwrites COMMENT ON TABLE / COMMENT ON COLUMN for the
application-owned system tables. Run from backend/:

    venv/Scripts/python.exe seed_system_descriptions.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import inspect, text  # noqa: E402

from app.core.database import engine  # noqa: E402


SYSTEM_DESCRIPTIONS = {
    "users": {
        "table": "Application user accounts with authentication and access control.",
        "columns": {
            "id": "Unique user identifier.",
            "name": "Display name of the user.",
            "email": "Login email address of the user.",
            "password": "Hashed password of the user.",
            "role": "Access role: admin or regular user.",
            "country_id": "Reference to the user's country (countries.id).",
            "language": "Preferred UI language code of the user.",
            "is_active": "Whether the user account is active.",
            "created_at": "Timestamp when the user was created.",
            "updated_at": "Timestamp of the last user update.",
        },
    },
    "agents": {
        "table": "AI agents that can be assigned to projects and conversations.",
        "columns": {
            "id": "Unique agent identifier.",
            "name": "Display name of the agent.",
            "description": "Short description of the agent's purpose.",
            "is_active": "Whether the agent is active.",
            "created_at": "Timestamp when the agent was created.",
            "updated_at": "Timestamp of the last agent update.",
        },
    },
    "skills": {
        "table": "Reusable skills that agents can use.",
        "columns": {
            "id": "Unique skill identifier.",
            "name": "Display name of the skill.",
            "description": "Short description of what the skill does.",
            "is_active": "Whether the skill is active.",
        },
    },
    "tools": {
        "table": "External tools and integrations available to agents.",
        "columns": {
            "id": "Unique tool identifier.",
            "name": "Display name of the tool.",
            "type": "Tool type or integration kind.",
            "body": "Tool configuration or prompt body.",
            "is_active": "Whether the tool is active.",
            "description": "Short description of what the tool does.",
        },
    },
    "chats": {
        "table": "Conversations between users, projects and agents.",
        "columns": {
            "id": "Unique chat identifier.",
            "user_id": "Reference to the chat owner (users.id).",
            "project_id": "Reference to the associated project (projects.id).",
            "new_messages_count": "Number of unread messages in the chat.",
            "last_message_id": "Reference to the most recent message (messages.id).",
            "description": "Short description of the chat.",
            "created_at": "Timestamp when the chat was created.",
            "updated_at": "Timestamp of the last chat update.",
        },
    },
    "messages": {
        "table": "Individual messages inside chats.",
        "columns": {
            "id": "Unique message identifier.",
            "chat_id": "Reference to the parent chat (chats.id).",
            "sender_type": "Sender kind: user, agent, tool or system.",
            "sender_id": "Reference to the sender record.",
            "message_type": "Message kind, e.g. text or tool output.",
            "content": "Text content of the message.",
            "created_at": "Timestamp when the message was created.",
            "receiver_type": "Receiver kind: user, agent or system.",
            "receiver_id": "Reference to the receiver record.",
            "sender_name": "Human-readable name of the message sender.",
            "receiver_name": "Human-readable name of the message receiver.",
        },
    },
    "projects": {
        "table": "Projects that group agents, users and assigned storage tables.",
        "columns": {
            "id": "Unique project identifier.",
            "name": "Display name of the project.",
            "description": "Short description of the project.",
            "is_active": "Whether the project is active.",
            "workflow": "JSON workflow configuration used by the project.",
            "created_at": "Timestamp when the project was created.",
            "updated_at": "Timestamp of the last project update.",
        },
    },
    "countries": {
        "table": "Reference list of countries used for user profiles.",
        "columns": {
            "id": "Unique country identifier.",
            "name": "Display name of the country.",
            "code": "ISO country code.",
            "phone_code": "JSON list of phone calling codes for the country.",
            "is_active": "Whether the country is active.",
            "created_at": "Timestamp when the country was created.",
        },
    },
    "agent_context_tools": {
        "table": (
            "Tools an agent runs by itself before each message, whose output is "
            "added to its instructions."
        ),
        "columns": {
            "id": "Unique entry identifier.",
            "agent_id": "Reference to the agent that runs the tool (agents.id).",
            "tool_id": "Reference to the tool that is run (tools.id).",
            "comment": "Heading written above the tool's output in the prompt.",
            "arguments": "JSON object of arguments, or NULL for a tool that takes none.",
            "position": "Order in which the entries appear in the prompt.",
        },
    },
    "memory": {
        "table": (
            "Notes an agent has stored about a user, kept across that user's "
            "conversations with it."
        ),
        "columns": {
            "id": "Unique memory identifier.",
            "agent_id": "Reference to the agent that wrote the note (agents.id).",
            "user_id": "Reference to the user the note is about (users.id).",
            "note": "Text the agent chose to remember.",
            "timestamp": "Timestamp when the note was last written.",
        },
    },
}


def main() -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    with engine.begin() as connection:
        for table_name, meta in SYSTEM_DESCRIPTIONS.items():
            if table_name not in table_names:
                print(f"[SKIP] {table_name}: table does not exist")
                continue
            connection.execute(
                text('COMMENT ON TABLE "%s" IS :comment' % table_name),
                {"comment": meta.get("table") or ""},
            )
            columns = {c["name"] for c in inspector.get_columns(table_name)}
            for column_name, column_desc in meta.get("columns", {}).items():
                if column_name not in columns:
                    print(f"[SKIP] {table_name}.{column_name}: column does not exist")
                    continue
                connection.execute(
                    text('COMMENT ON COLUMN "%s"."%s" IS :comment' % (table_name, column_name)),
                    {"comment": column_desc},
                )
            print(f"[OK] {table_name}: table comment + {len(meta.get('columns', {}))} column comments")
    print("[OK] System descriptions seeded.")


if __name__ == "__main__":
    main()
