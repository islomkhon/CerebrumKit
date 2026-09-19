from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON, Text
from sqlalchemy.orm import relationship

from app.core.database import Base


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    # The project the system administers itself from. Its own row is neither
    # editable nor deletable - see routers/projects.py - so the Project Manager
    # agent that lives in it always has a home. Everything *inside* it (agents,
    # skills, tools, its members) stays editable, which is what lets that agent
    # manage the rest of the system.
    is_system = Column(Boolean, default=False, nullable=False, server_default="false")
    workflow = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # M:N relationships (string refs so SQLAlchemy resolves from metadata)
    users = relationship("User", secondary="user_project", back_populates="projects")
    agents = relationship("Agent", secondary="agent_project", back_populates="projects")

    # 1:N
    chats = relationship("Chat", back_populates="project", passive_deletes=True)
    tables = relationship("ProjectTable", back_populates="project", cascade="all, delete-orphan")
