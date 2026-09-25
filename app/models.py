from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship
from .database import Base


class Source(Base):
    __tablename__ = "sources"

    id = Column(Integer, primary_key=True, index=True)
    company_name = Column(String, nullable=False)
    url = Column(String, nullable=False, unique=True)
    source_type = Column(String, nullable=False, default="custom")  # greenhouse | lever | workday | ashby | custom
    status = Column(String, default="active")  # active | syncing | error
    job_count = Column(Integer, default=0)
    last_sync = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)
    detection_debug = Column(JSON, nullable=True)  # method breakdown, for admin transparency
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    jobs = relationship("Job", back_populates="source", cascade="all, delete-orphan")


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, ForeignKey("sources.id"))
    external_id = Column(String, nullable=True)
    title = Column(String, nullable=True)
    location = Column(String, nullable=True)
    department = Column(String, nullable=True)
    url = Column(String, nullable=True)
    raw = Column(JSON, nullable=True)

    source = relationship("Source", back_populates="jobs")
