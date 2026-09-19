from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.pivot import agent_skill, skill_tool


class Agent(Base):
    __tablename__ = "agents"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    skills = relationship("Skill", secondary="agent_skill", back_populates="agents")
    tools = relationship(
        "Tool",
        secondary=agent_skill.join(skill_tool, agent_skill.c.skill_id == skill_tool.c.skill_id),
        primaryjoin=id == agent_skill.c.agent_id,
        secondaryjoin="Tool.id == skill_tool.c.tool_id",
        viewonly=True,
    )
    projects = relationship("Project", secondary="agent_project", back_populates="agents")
    # delete-orphan and passive_deletes together: the FK carries ON DELETE
    # CASCADE, so the database clears rows the ORM never loaded, while any
    # memory already in the session is deleted rather than having agent_id
    # set to NULL - the column is NOT NULL, so nulling it fails the delete.
    memories = relationship(
        "Memory",
        back_populates="agent",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # Tools this agent runs on its own before it reads a message, with the
    # output placed in its system prompt. Same cascade shape as `memories`:
    # the FK carries ON DELETE CASCADE, so the database clears rows the ORM
    # never loaded, while reassigning this collection still deletes the rows
    # it replaced. `order_by` is what keeps the injected block in the order
    # the admin arranged it.
    context_tool_links = relationship(
        "AgentContextTool",
        back_populates="agent",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="AgentContextTool.position, AgentContextTool.id",
    )

    # sender_id / receiver_id are a polymorphic pointer rather than a real
    # foreign key, so each join is spelled out and marked with foreign() to
    # say which side points at the agent. Both are viewonly: a message row
    # is written through the chat, never through the agent it mentions, so
    # appending here would silently re-address somebody else's message.
    sent_messages = relationship(
        "Message",
        primaryjoin=(
            "and_(Agent.id == foreign(Message.sender_id), "
            "Message.sender_type == 'agent')"
        ),
        order_by="Message.id",
        viewonly=True,
    )
    received_messages = relationship(
        "Message",
        primaryjoin=(
            "and_(Agent.id == foreign(Message.receiver_id), "
            "Message.receiver_type == 'agent')"
        ),
        order_by="Message.id",
        viewonly=True,
    )
    # Both directions in one collection, for the common "everything this
    # agent was involved in" read. Tool cards count as received: they are
    # addressed back to the agent that called the tool.
    messages = relationship(
        "Message",
        primaryjoin=(
            "or_("
            "and_(Agent.id == foreign(Message.sender_id), "
            "Message.sender_type == 'agent'), "
            "and_(Agent.id == foreign(Message.receiver_id), "
            "Message.receiver_type == 'agent'))"
        ),
        order_by="Message.id",
        viewonly=True,
    )

    @property
    def skill_ids(self) -> list[int]:
        return [skill.id for skill in self.skills]

    @property
    def tool_ids(self) -> list[int]:
        return [tool.id for tool in self.tools]

    @property
    def context_tools(self) -> list[dict]:
        """The configured pre-run tools, shaped for AgentOut.

        Kept as a read-only property rather than a second relationship so the
        API payload is built in one place and the tool's own name and active
        flag travel with the id.
        """
        return [
            {
                "tool_id": link.tool_id,
                "name": link.tool.name if link.tool is not None else "",
                "comment": link.comment,
                "arguments": link.arguments,
                "position": link.position,
                "is_active": bool(link.tool is not None and link.tool.is_active),
            }
            for link in self.context_tool_links
        ]
