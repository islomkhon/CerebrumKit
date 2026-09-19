from sqlalchemy import Column, Integer, String, Boolean, Text
from sqlalchemy.orm import relationship

from app.core.database import Base


class Skill(Base):
    __tablename__ = "skills"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)

    agents = relationship("Agent", secondary="agent_skill", back_populates="skills")
    tools = relationship("Tool", secondary="skill_tool", back_populates="skills")

    @property
    def tool_ids(self) -> list[int]:
        return [tool.id for tool in self.tools]
