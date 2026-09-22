from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class GeneratedDocument(Base):
    __tablename__ = "generated_documents"
    __table_args__ = (UniqueConstraint("job_id", "type", "version", name="uq_generated_documents_job_type_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    type: Mapped[str | None] = mapped_column(String)
    file_path: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    claim_check_passed: Mapped[bool | None] = mapped_column(Boolean)
    ats_check_passed: Mapped[bool | None] = mapped_column(Boolean)
    # JSON-encoded source content the .docx was written from — a list of
    # {section, content, evidence_ids_used} dicts for "resume", a bare
    # JSON string for "cover_letter". Exists so app/services/
    # document_editor.py can read back "what does this document currently
    # say" without parsing the .docx file itself; not exposed as a
    # queryable/filterable column, just app-level storage.
    content_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    job: Mapped["Job"] = relationship(back_populates="generated_documents")
