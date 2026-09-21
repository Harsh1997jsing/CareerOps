"""Chat-driven job search.

A structured_call() (app/services/chat_search.py's extract_intent) turns
each message into search filters plus which of Explore/Scrape/Targets to
run it against; a second structured_call (summarize_results) batches
one-line JD summaries for whatever gets staged. Those two calls are the
only place an LLM touches this feature — everything else is plain CRUD
through the DB, same as Explore's search-then-select-then-save flow (see
explore.py's module docstring): the chat is a natural-language front end
onto the same searches, not a new save path — saving a staged result goes
through the existing shared POST /explore/save (ChatSearchResultOut is a
superset of ExploreResultOut's fields), not a route defined here.

Every route requires a valid bearer token (`Depends(get_current_user)` at
the router level, same pattern as every other route module).
"""

import asyncio

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.api.schemas import ChatMessageRequest, ChatMessageResponse, ChatSearchResultOut
from app.core import get_db
from app.services import chat_search

router = APIRouter(prefix="/chat", tags=["chat"], dependencies=[Depends(get_current_user)])


@router.post("/message", response_model=ChatMessageResponse)
async def send_message(payload: ChatMessageRequest, session: AsyncSession = Depends(get_db)):
    """Handle one chat turn: extract filters, and search once enough is known.

    Args:
        payload: The message plus filters already confirmed this conversation.
        session: Database session dependency.

    Returns:
        ChatMessageResponse: A clarifying reply (if more is needed) or a
            summary of newly staged results (if a search ran).
    """
    intent = await asyncio.to_thread(chat_search.extract_intent, payload.message, payload.known_filters)
    filters = chat_search.intent_filters(intent)

    if not intent.ready_to_search:
        return ChatMessageResponse(
            reply=intent.clarification_question
            or "Could you tell me a bit more about what you're looking for?",
            filters=filters,
            ready=False,
            results=[],
        )

    raw_results = await chat_search.run_search(intent)
    summaries = await asyncio.to_thread(chat_search.summarize_results, raw_results)
    staged = await chat_search.stage_results(session, payload.session_id, raw_results, summaries)
    reply = (
        f"Found {len(staged)} matching job{'' if len(staged) == 1 else 's'}."
        if staged
        else "No matches found for that search — try loosening a filter."
    )
    return ChatMessageResponse(
        reply=reply,
        filters=filters,
        ready=True,
        results=[ChatSearchResultOut.model_validate(row, from_attributes=True) for row in staged],
    )


@router.get("/results/{session_id}", response_model=list[ChatSearchResultOut])
async def list_results(session_id: str, session: AsyncSession = Depends(get_db)):
    """List a chat session's currently staged results (survives a page refresh).

    Args:
        session_id: Client-generated id identifying the chat conversation.
        session: Database session dependency.

    Returns:
        list[ChatSearchResultOut]: Staged results for this session.
    """
    staged = await chat_search.get_staged_results(session, session_id)
    return [ChatSearchResultOut.model_validate(row, from_attributes=True) for row in staged]
