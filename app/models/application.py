from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("job_id", name="uq_applications_job_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="READY_FOR_REVIEW", server_default="READY_FOR_REVIEW"
    )
    applied_at: Mapped[datetime | None] = mapped_column(DateTime)
    resume_version: Mapped[int | None] = mapped_column(Integer)
    cover_letter_version: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)

    job: Mapped["Job"] = relationship(back_populates="applications")


class CompanyApplicationHistory(Base):
    __tablename__ = "company_application_history"
    __table_args__ = (UniqueConstraint("company", "job_id", name="uq_company_application_history_company_job"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company: Mapped[str] = mapped_column(String, nullable=False, index=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"))
    applied_at: Mapped[datetime | None] = mapped_column(DateTime)
