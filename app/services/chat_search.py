"""Chat-driven job search.

A single structured_call() (extract_intent, below) turns a free-text
message into search filters AND which of the app's three search sources
to run it against — that's the only place an LLM makes a *decision* in
this feature. Once enough is known to search, run_search() dispatches
straight to whichever of mcp_explore.search() / jobspy_source.fetch_jobs()
/ targets.search_all() the model picked (concurrently, if it picked more
than one) — the same functions Explore/Job Scraping/Target's pages call
directly. A second, optional structured_call (summarize_results) batches
one-line summaries for every staged result in a single call rather than
one call per job, so token cost stays flat regardless of result count.
Staging and listing results are plain CRUD, kept out of the model's hands
entirely — conversation history and filter carry-forward live
client-side (the caller passes back `known_filters` each turn) so no
chat-transcript state round-trips through the model either.

Saving a staged result into the Dashboard is deliberately NOT handled
here: `/explore/save` is the single shared save path for every discovery
source (Explore, `/targets/search`, `/scrape/jobspy`, and now this) — see
app/api/routes/explore.py's module docstring. A ChatSearchResultOut is
already a superset of ExploreResultOut's fields, so the frontend posts a
staged result straight to /explore/save like any other discovered result.
"""

import asyncio
import logging

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.anthropic_client import structured_call
from app.llm.prompts import CHAT_RESULT_SUMMARY_PROMPT, CHAT_SEARCH_INTENT_PROMPT
from app.llm.schemas import ChatResultSummaries, ChatSearchIntent
from app.models import ChatSearchResult
from app.sources import jobspy_source
from app.sources import targets as targets_source
from app.sources.mcp import explore as mcp_explore

logger = logging.getLogger(__name__)

# How much of a job's description to feed into the summary prompt per
# posting — a one-line summary doesn't need the full JD, and this is the
# single biggest lever on that call's token cost when many results are
# staged at once.
_SUMMARY_DESCRIPTION_CHARS = 400


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
    """Dispatch a ready ChatSearchIntent to whichever source(s) the model picked.

    Runs every selected source concurrently (asyncio.gather) and merges
    their results — same fan-out/partial-failure handling as
    mcp_explore.search() itself: one source failing is logged and
    skipped, not allowed to fail the whole turn.

    Args:
        intent: A ready_to_search=True intent, including `sources`.

    Returns:
        list[dict]: Normalized job postings, not yet staged or persisted.
    """
    filters = {k: v for k, v in intent_filters(intent).items() if k != "query"}
    sources = intent.sources or ["explore"]

    tasks = []
    if "explore" in sources:
        tasks.append(mcp_explore.search(intent.query, filters))
    if "scrape" in sources:
        tasks.append(
            asyncio.to_thread(
                jobspy_source.fetch_jobs, intent.query, location=intent.location, experience=intent.experience
            )
        )
    if "targets" in sources:
        tasks.append(targets_source.search_all(experience=intent.experience))

    outcomes = await asyncio.gather(*tasks, return_exceptions=True)
    results: list[dict] = []
    for source_name, outcome in zip(sources, outcomes):
        if isinstance(outcome, Exception):
            logger.warning("chat search source %r failed: %s", source_name, outcome)
            continue
        results.extend(outcome)
    return results


def summarize_results(jobs: list[dict]) -> list[str]:
    """Write a one-line AI summary for every staged result in a single call.

    Batches the whole result set into one structured_call rather than one
    call per job — token cost is flat (one call) instead of growing with
    result count. Each description is truncated before it goes into the
    prompt (see _SUMMARY_DESCRIPTION_CHARS); a one-line summary doesn't
    need the full JD.

    Args:
        jobs: Normalized job dicts from run_search(), in staging order.

    Returns:
        list[str]: One summary per job, same order as `jobs` ("" for any
            job the model's response didn't cover).
    """
    if not jobs:
        return []

    listing = "\n".join(
        f"{i}. {job['title']} @ {job['company']}\n{job['description'][:_SUMMARY_DESCRIPTION_CHARS]}"
        for i, job in enumerate(jobs)
    )
    prompt = CHAT_RESULT_SUMMARY_PROMPT.format(listing=listing)
    result: ChatResultSummaries = structured_call(
        prompt, ChatResultSummaries, max_tokens=max(1024, len(jobs) * 60)
    )  # type: ignore[assignment]

    by_index = {item.index: item.summary for item in result.summaries}
    return [by_index.get(i, "") for i in range(len(jobs))]


async def stage_results(
    session: AsyncSession, session_id: str, jobs: list[dict], summaries: list[str] | None = None
) -> list[ChatSearchResult]:
    """Replace a chat session's staged results with a fresh search's results.

    Wholesale replacement, not an append — a session's staged list is
    "what the last search found," not an accumulating history (unlike the
    `jobs` table itself, which every save is additive into).

    Args:
        session: Database session.
        session_id: Client-generated id identifying this chat conversation.
        jobs: Normalized job dicts from run_search().
        summaries: One-line summaries from summarize_results(), same
            order as `jobs`; omitted (None) leaves every row's summary
            null rather than blocking staging on the summary call.

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
            summary=(summaries[i] if summaries and i < len(summaries) else None) or None,
        )
        for i, job in enumerate(jobs)
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
