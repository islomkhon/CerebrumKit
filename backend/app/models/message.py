from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship

from app.core.database import Base


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(Integer, ForeignKey("chats.id", ondelete="CASCADE"), nullable=False)
    sender_type = Column(String(50), nullable=False)  # "user" or "agent"
    sender_id = Column(Integer, nullable=True)  # polymorphic FK
    receiver_type = Column(String(50), nullable=True)  # "user" or "agent"
    receiver_id = Column(Integer, nullable=True)  # polymorphic FK
    sender_name = Column(String(255), nullable=True)
    receiver_name = Column(String(255), nullable=True)
    message_type = Column(String(50), default="text")
    content = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    chat = relationship("Chat", back_populates="messages", foreign_keys=[chat_id])
