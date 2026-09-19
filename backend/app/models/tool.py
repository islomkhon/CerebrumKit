from sqlalchemy import Column, Integer, String, Boolean, Text
from sqlalchemy.orm import relationship

from app.core.database import Base


class Tool(Base):
    __tablename__ = "tools"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    type = Column(String(100), nullable=True)
    body = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)

    skills = relationship("Skill", secondary="skill_tool", back_populates="tools")
