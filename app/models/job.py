from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.models.base import Base

# JSONB on Postgres (indexable, binary-stored), plain JSON everywhere else
# (e.g. SQLite in tests) — same column, dialect-appropriate storage.
JobJSON = JSON().with_variant(JSONB(), "postgresql")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String, nullable=False)
    source_job_id: Mapped[str | None] = mapped_column(String)
    company: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    location: Mapped[str | None] = mapped_column(String)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    description_hash: Mapped[str | None] = mapped_column(String, unique=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime)
    collected_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    employment_type: Mapped[str | None] = mapped_column(String)
    salary_min: Mapped[int | None] = mapped_column(Integer)
    salary_max: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String, default="DISCOVERED", server_default="DISCOVERED", index=True)

    analyses: Mapped[list["JobAnalysis"]] = relationship(
        back_populates="job", cascade="all, delete-orphan", order_by="JobAnalysis.analyzed_at.desc()"
    )
    generated_documents: Mapped[list["GeneratedDocument"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
    applications: Mapped[list["Application"]] = relationship(back_populates="job", cascade="all, delete-orphan")


class JobAnalysis(Base):
    __tablename__ = "job_analysis"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    fit_score: Mapped[int | None] = mapped_column(Integer)
    confidence: Mapped[str | None] = mapped_column(String)
    eligible: Mapped[bool | None] = mapped_column(Boolean)
    strong_matches: Mapped[list | None] = mapped_column(JobJSON)
    missing_skills: Mapped[list | None] = mapped_column(JobJSON)
    risks: Mapped[list | None] = mapped_column(JobJSON)
    analyzed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)

    job: Mapped["Job"] = relationship(back_populates="analyses")
