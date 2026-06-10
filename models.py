"""SQLAlchemy models and session setup for the get-job app (SQLite)."""

from __future__ import annotations

import os
from datetime import datetime, date

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

DB_PATH = os.environ.get("GETJOB_DB", os.path.join(os.path.dirname(__file__), "jobs.db"))

engine = create_engine(f"sqlite:///{DB_PATH}", future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)

# Kanban columns, in display order.
STATUSES = ["to_apply", "applied", "interviewing", "offer", "rejected"]


class Base(DeclarativeBase):
    pass


class ScrapedJob(Base):
    """A job listing pulled from one of the public remote-job feeds."""

    __tablename__ = "scraped_jobs"
    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_source_external"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(50), index=True)
    external_id: Mapped[str] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(300))
    company: Mapped[str] = mapped_column(String(200), default="")
    location: Mapped[str] = mapped_column(String(200), default="")
    salary: Mapped[str] = mapped_column(String(200), default="")
    tags: Mapped[str] = mapped_column(Text, default="")  # comma-separated
    description: Mapped[str] = mapped_column(Text, default="")  # plain text, HTML stripped
    url: Mapped[str] = mapped_column(Text, default="")
    posted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    scraped_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source": self.source,
            "title": self.title,
            "company": self.company,
            "location": self.location,
            "salary": self.salary,
            "tags": [t for t in (self.tags or "").split(",") if t],
            "description": self.description,
            "url": self.url,
            "posted_at": self.posted_at.isoformat() if self.posted_at else None,
            "scraped_at": self.scraped_at.isoformat() if self.scraped_at else None,
        }


class TrackedJob(Base):
    """A job the user is tracking on the Kanban board."""

    __tablename__ = "tracked_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    company: Mapped[str] = mapped_column(String(200), default="")
    salary_range: Mapped[str] = mapped_column(String(200), default="")
    url: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="to_apply", index=True)
    date_applied: Mapped[date | None] = mapped_column(Date, nullable=True)
    scraped_job_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "company": self.company,
            "salary_range": self.salary_range,
            "url": self.url,
            "notes": self.notes,
            "status": self.status,
            "date_applied": self.date_applied.isoformat() if self.date_applied else None,
            "scraped_job_id": self.scraped_job_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class SourceState(Base):
    """Per-source scrape bookkeeping, used to honor polite-use cooldowns."""

    __tablename__ = "source_state"

    source: Mapped[str] = mapped_column(String(50), primary_key=True)
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_status: Mapped[str] = mapped_column(String(30), default="never")  # ok | error | cooldown
    last_error: Mapped[str] = mapped_column(Text, default="")
    last_count: Mapped[int] = mapped_column(Integer, default=0)


class Profile(Base):
    """Single-row table holding the user's resume text and skill keywords."""

    __tablename__ = "profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    resume_text: Mapped[str] = mapped_column(Text, default="")
    skills: Mapped[str] = mapped_column(Text, default="")  # comma-separated keywords
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def to_dict(self) -> dict:
        return {
            "resume_text": self.resume_text,
            "skills": self.skills,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


def init_db() -> None:
    """Create tables and seed the profile from seed/resume.txt on first run."""
    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        if session.get(Profile, 1) is None:
            seed_path = os.path.join(os.path.dirname(__file__), "seed", "resume.txt")
            resume_text = ""
            if os.path.exists(seed_path):
                with open(seed_path, encoding="utf-8") as fh:
                    resume_text = fh.read()
            session.add(Profile(id=1, resume_text=resume_text, skills=""))
            session.commit()
