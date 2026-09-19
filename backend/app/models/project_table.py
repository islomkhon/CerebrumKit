from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.core.database import Base


class ProjectTable(Base):
    """Assignment registry: links a physical database table to a project.

    A table can be assigned to multiple projects (multiple rows with the same
    table_name). The list of available tables itself is read directly from the
    database, not from this registry.
    """

    __tablename__ = "project_tables"
    __table_args__ = (
        UniqueConstraint("project_id", "table_name", name="uq_project_table_assignment"),
    )

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    table_name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    project = relationship("Project", back_populates="tables")