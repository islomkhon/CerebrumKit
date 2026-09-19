from sqlalchemy import Column, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.core.database import Base


class AgentContextTool(Base):
    """A tool an agent runs by itself before it reads the user's message.

    Some of what an agent needs is knowable before the message is read - the
    environment it runs in, the project data it works against, what it learned
    earlier. Those lookups do not depend on the wording of the message, so
    leaving them to the model to ask for costs a tool round and is skipped
    whenever the model decides it already knows enough. A row here makes the
    lookup part of how the agent starts: the tool runs, and its output is placed
    in the agent's system prompt.

    `comment` is the heading written above that output, so the agent is told
    what it is looking at instead of being handed an unlabelled blob.
    `arguments` is the JSON object the tool is called with, which is how a
    context tool that needs a parameter (a search term, a limit) is filled in;
    it is empty for a tool that takes none.

    `position` keeps the order the admin arranged the entries in, so the prompt
    reads the same way on every run.

    A tool only reaches an agent through a skill, so a row is only valid for a
    tool the agent already has; the router checks that on save.
    """

    __tablename__ = "agent_context_tools"
    __table_args__ = (
        UniqueConstraint(
            "agent_id", "tool_id", name="uq_agent_context_tools_agent_tool"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    # Deleting the agent takes its context rows with it.
    agent_id = Column(
        Integer,
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Deleting the tool takes it out of every agent's context list.
    tool_id = Column(
        Integer,
        ForeignKey("tools.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # The heading shown above this tool's output in the system prompt.
    comment = Column(Text, nullable=True)
    # JSON object of arguments, or NULL for a tool that takes none.
    arguments = Column(Text, nullable=True)
    position = Column(Integer, nullable=False, default=0, server_default="0")

    agent = relationship("Agent", back_populates="context_tool_links")
    tool = relationship("Tool")
