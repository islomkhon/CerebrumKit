from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.orm import relationship

from app.core.database import Base


class Memory(Base):
    """A note an agent has stored about a user.

    Memory is keyed by (agent, user) rather than by chat. A user can hold
    several conversations with the same agent, and a fact learned in one of them
    - a preference, a decision, an id - is worth having in the others, so what
    one chat taught the agent is readable from that user's other chats too. The
    agent is part of the key, so two agents answering the same user keep their
    own notes instead of reading each other's.

    Deleting the agent or the user takes the memories with them. Deleting a chat
    does not, which is the point of taking the scope off the chat.
    """

    __tablename__ = "memory"

    id = Column(Integer, primary_key=True, index=True)
    # The owning agent. Deleting the agent takes its memories with it.
    agent_id = Column(
        Integer,
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # The user the note is about, and half of what every read is scoped to.
    # Deleting the user takes the notes written about them with it.
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    note = Column(Text, nullable=False)
    # server_default as well as default: anything that inserts a row without
    # naming the column - the storage editor, a raw SQL insert - still records
    # the moment the note was stored instead of being asked for it by hand.
    timestamp = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )

    agent = relationship("Agent", back_populates="memories")
    user = relationship("User", back_populates="memories")
