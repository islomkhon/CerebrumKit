from datetime import datetime, timezone

from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False, unique=True, index=True)
    password = Column(String(255), nullable=False)
    role = Column(String(50), default="client")
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=True)
    language = Column(String(10), default="en")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    country = relationship("Country", back_populates="users")
    projects = relationship("Project", secondary="user_project", back_populates="users")
    chats = relationship("Chat", back_populates="user", passive_deletes=True)
    # Mirrors Agent.memories: the FK carries ON DELETE CASCADE, so the database
    # clears rows the ORM never loaded, while any memory already in the session is
    # deleted rather than having user_id set to NULL - the column is NOT NULL, so
    # nulling it fails the delete.
    memories = relationship(
        "Memory",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
