from sqlalchemy import Column, Integer, ForeignKey, Table

from app.core.database import Base


# pivot: user <-> project (many-to-many)
user_project = Table(
    "user_project",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("project_id", Integer, ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True),
)

# pivot: agent <-> project (many-to-many)
agent_project = Table(
    "agent_project",
    Base.metadata,
    Column("agent_id", Integer, ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True),
    Column("project_id", Integer, ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True),
)

# pivot: agent <-> skill (many-to-many)
agent_skill = Table(
    "agent_skill",
    Base.metadata,
    Column("agent_id", Integer, ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True),
    Column("skill_id", Integer, ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True),
)

# pivot: skill <-> tool (many-to-many)
skill_tool = Table(
    "skill_tool",
    Base.metadata,
    Column("skill_id", Integer, ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True),
    Column("tool_id", Integer, ForeignKey("tools.id", ondelete="CASCADE"), primary_key=True),
)

__all__ = ["user_project", "agent_project", "agent_skill", "skill_tool"]
