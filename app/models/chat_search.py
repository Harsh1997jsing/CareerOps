"""Temporary staging for chat-driven search results.

A chat search's results aren't jobs yet — same "found but not saved" state
Explore/Scrape/Targets results are in before /explore/save (see
app/api/routes/explore.py's module docstring) — but the chat needs them to
survive a page refresh and to be referenced by id (so the model never has
to re-see a full job description just to save or list them). Rows are
scoped by session_id, not by user/tenant; a stale session's rows are
replaced wholesale on its next search rather than accumulating (see
app/services/chat_search.py's stage_results()).
"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ChatSearchResult(Base):
    __tablename__ = "chat_search_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    source: Mapped[str] = mapped_column(String, nullable=False)
    source_job_id: Mapped[str | None] = mapped_column(String)
    company: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    location: Mapped[str | None] = mapped_column(String)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    employment_type: Mapped[str | None] = mapped_column(String)
    salary_min: Mapped[int | None] = mapped_column(Integer)
    salary_max: Mapped[int | None] = mapped_column(Integer)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
