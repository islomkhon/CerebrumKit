from datetime import datetime, timezone

from sqlalchemy import Column, Integer, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship

from app.core.database import Base


class Chat(Base):
    __tablename__ = "chats"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    new_messages_count = Column(Integer, default=0)
    last_message_id = Column(Integer, ForeignKey("messages.id"), nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="chats")
    project = relationship("Project", back_populates="chats")
    last_message = relationship("Message", foreign_keys=[last_message_id], post_update=True)
    messages = relationship("Message", back_populates="chat",
                            foreign_keys="Message.chat_id",
                            cascade="all, delete-orphan")
    # No memories relationship here on purpose: memory is keyed by (agent,
    # user), not by chat, so deleting a chat leaves the agent's notes about that
    # user alone and they stay readable from the user's other chats.
