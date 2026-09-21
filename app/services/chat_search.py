"""Chat-driven job search.

A single structured_call() (extract_intent, below) turns a free-text
message into search filters — that's the only place an LLM touches this
feature. Once enough is known to search, the extracted filters are
dispatched straight to app/sources/mcp/explore.py's search(), the same
broad multi-source search Explore's page uses. Staging and listing
results are plain CRUD, kept out of the model's hands entirely —
conversation history and filter carry-forward live client-side (the
caller passes back `known_filters` each turn) so no chat-transcript state
has to round-trip through the model either, which keeps token use to one
short call per turn regardless of how long the conversation runs.

Saving a staged result into the Dashboard is deliberately NOT handled
here: `/explore/save` is the single shared save path for every discovery
source (Explore, `/targets/search`, `/scrape/jobspy`, and now this) — see
app/api/routes/explore.py's module docstring. A ChatSearchResultOut is
already a superset of ExploreResultOut's fields, so the frontend posts a
staged result straight to /explore/save like any other discovered result.
"""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.anthropic_client import structured_call
from app.llm.prompts import CHAT_SEARCH_INTENT_PROMPT
from app.llm.schemas import ChatSearchIntent
from app.models import ChatSearchResult
from app.sources.mcp import explore as mcp_explore


def extract_intent(message: str, known_filters: dict) -> ChatSearchIntent:
    """Extract search filters from a chat message via one structured Claude call.

    Args:
        message: The user's latest chat message.
        known_filters: Filters already confirmed earlier in this
            conversation (as returned by a prior call's `intent_filters()`),
            supplied by the caller rather than reconstructed from a stored
            transcript.

    Returns:
        ChatSearchIntent: Extracted/merged filters and whether they're
            enough to search on yet.
    """
    known_filters_text = ", ".join(f"{k}={v}" for k, v in known_filters.items() if v) or "(none yet)"
    prompt = CHAT_SEARCH_INTENT_PROMPT.format(known_filters=known_filters_text, message=message)
    return structured_call(prompt, ChatSearchIntent)  # type: ignore[return-value]


def intent_filters(intent: ChatSearchIntent) -> dict:
    """Collapse a ChatSearchIntent into the compact filter dict the frontend carries forward.

    Args:
        intent: Extracted search intent.

    Returns:
        dict: Non-empty filter fields only (query plus whichever of
            location/experience/posted_within_days/company were set).
    """
    filters = {"query": intent.query}
    if intent.location:
        filters["location"] = intent.location
    if intent.experience:
        filters["experience"] = intent.experience
    if intent.posted_within_days:
        filters["posted_within_days"] = intent.posted_within_days
    if intent.company:
        filters["company"] = intent.company
    return filters


async def run_search(intent: ChatSearchIntent) -> list[dict]:
    """Dispatch a ready ChatSearchIntent to the same MCP search Explore's page uses.

    Args:
        intent: A ready_to_search=True intent.

    Returns:
        list[dict]: Normalized job postings, not yet staged or persisted.
    """
    filters = {k: v for k, v in intent_filters(intent).items() if k != "query"}
    return await mcp_explore.search(intent.query, filters)


async def stage_results(session: AsyncSession, session_id: str, jobs: list[dict]) -> list[ChatSearchResult]:
    """Replace a chat session's staged results with a fresh search's results.

    Wholesale replacement, not an append — a session's staged list is
    "what the last search found," not an accumulating history (unlike the
    `jobs` table itself, which every save is additive into).

    Args:
        session: Database session.
        session_id: Client-generated id identifying this chat conversation.
        jobs: Normalized job dicts from run_search().

    Returns:
        list[ChatSearchResult]: The newly inserted staged rows, in order.
    """
    await session.execute(delete(ChatSearchResult).where(ChatSearchResult.session_id == session_id))
    rows = [
        ChatSearchResult(
            session_id=session_id,
            source=job["source"],
            source_job_id=job.get("source_job_id"),
            company=job["company"],
            title=job["title"],
            location=job.get("location"),
            url=job["url"],
            description=job["description"],
            employment_type=job.get("employment_type"),
            salary_min=job.get("salary_min"),
            salary_max=job.get("salary_max"),
            posted_at=job.get("posted_at"),
        )
        for job in jobs
    ]
    session.add_all(rows)
    await session.commit()
    for row in rows:
        await session.refresh(row)
    return rows


async def get_staged_results(session: AsyncSession, session_id: str) -> list[ChatSearchResult]:
    """List a chat session's currently staged results, most recent search first.

    Args:
        session: Database session.
        session_id: Client-generated id identifying this chat conversation.

    Returns:
        list[ChatSearchResult]: Staged rows for this session.
    """
    result = await session.execute(
        select(ChatSearchResult)
        .where(ChatSearchResult.session_id == session_id)
        .order_by(ChatSearchResult.id)
    )
    return list(result.scalars().all())
