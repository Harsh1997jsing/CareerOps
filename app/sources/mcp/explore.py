"""
Live MCP job search backing the frontend's Explore page (see
frontend/README.md). Results here are never inserted into `jobs`
automatically — only a future /explore/{id}/save endpoint does that, via
the same insert_jobs() dedup path every other source uses. A source that
errors, times out, or lacks a search tool is skipped, never fatal to the
whole search — see CAPABILITY DETECTION in the original spec and
CLAUDE.md rule 2 (no LinkedIn/Naukri MCP connector, ever).
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

from app.sources.common import (
    description_hash,
    normalize_employment_type,
    normalize_location,
    safe_int,
    strip_html,
)
from app.sources.mcp.capabilities import (
    FILTER_PARAM_CANDIDATES,
    CapabilityMatrix,
    build_capability_matrix,
)
from app.sources.mcp.client import call_tool, list_tools
from app.sources.mcp.registry import McpSource, configured_sources

logger = logging.getLogger(__name__)

# Common keys a tool's JSON payload might nest its result list under.
RESULT_LIST_KEYS = ("results", "jobs", "items", "data")


async def get_capability_matrix(source: McpSource) -> CapabilityMatrix:
    """Retrieve advertised tools and build a capability matrix for a single MCP source.

    Args:
        source: McpSource configuration object with URL and API key.

    Returns:
        CapabilityMatrix: Discovered capability flags and assigned search tools.
    """
    tools = await list_tools(source.url, source.api_key, source.auth_header)
    return build_capability_matrix(tools)


async def get_all_capabilities() -> dict[str, CapabilityMatrix]:
    """Retrieve capability matrices for all configured MCP sources in parallel.

    Backs GET /explore/capabilities. Checks every configured source in
    parallel; a source whose capability check fails is omitted rather
    than raising, since the frontend treats "absent" the same as
    "unsupported" when disabling filters per source.

    Returns:
        dict[str, CapabilityMatrix]: Map of source name to its CapabilityMatrix.
    """
    sources = configured_sources()
    outcomes = await asyncio.gather(
        *(get_capability_matrix(source) for source in sources),
        return_exceptions=True,
    )

    matrix: dict[str, CapabilityMatrix] = {}
    for source, outcome in zip(sources, outcomes):
        if isinstance(outcome, Exception):
            logger.warning("capability check failed for %s: %s", source.name, outcome)
            continue
        matrix[source.name] = outcome
    return matrix


def _first_present(input_schema: dict, candidates: tuple[str, ...]) -> str | None:
    """Find the first matching candidate property name in an input schema.

    Args:
        input_schema: JSON Schema dictionary for tool parameters.
        candidates: Preferred property names in priority order.

    Returns:
        str | None: First candidate key found in schema properties, or None.
    """
    properties = (input_schema or {}).get("properties", {})
    return next((name for name in candidates if name in properties), None)


def _build_search_arguments(tool, query: str, filters: dict) -> dict:
    """Map search query and filter dictionary onto tool's input schema parameters.

    Args:
        tool: Selected Tool definition for the server's search operation.
        query: Free-text search string.
        filters: Filter key-value pairs (location, remote, company, etc.).

    Returns:
        dict: Mapped argument dictionary matching the tool's parameter names.
    """
    schema = tool.input_schema or {}
    arguments: dict = {}

    query_param = _first_present(schema, ("query", "search_term", "keyword", "keywords", "q", "title"))
    if query_param:
        arguments[query_param] = query

    for filter_key, candidates in FILTER_PARAM_CANDIDATES.items():
        if filter_key not in filters:
            continue
        param_name = _first_present(schema, candidates)
        if param_name:
            arguments[param_name] = filters[filter_key]

    return arguments


def _as_text(value) -> str:
    """Coerce a raw field that may be a plain string or a nested object into text.

    HasData's Glassdoor/Indeed tools nest company info as an object
    (`employer: {"name": "...", ...}`) rather than a flat string like
    Jobo's shape — confirmed against a live response. `.strip()`ing that
    dict directly would raise; this pulls a `name`/`title` out of it first.

    Args:
        value: A string, a dict possibly containing "name"/"title", or None.

    Returns:
        str: Best-effort plain text, "" if nothing usable was found.
    """
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return str(value.get("name") or value.get("title") or "").strip()
    return ""


def _parse_posted_at(raw: dict) -> datetime | None:
    """Derive a posting's timestamp from whatever date shape a source actually returns.

    Confirmed live against HasData's Glassdoor tool: it has no absolute
    date field at all, only an integer `ageInDays` (e.g. `10`) — so this
    derives an approximate UTC timestamp from "now minus ageInDays" rather
    than guessing at a date string format that doesn't exist for this
    source. `posted_at`/`date_posted`/`postedDate` are kept as fallbacks
    for a source that does return an absolute date (unconfirmed for Jobo —
    its MCP auth is broken today, see registry.py's docstring — but a
    plain ISO-ish string is the most common shape if it ever works).

    Args:
        raw: Raw job dict extracted from the MCP tool output.

    Returns:
        datetime | None: UTC timestamp, or None if no usable date info exists.
    """
    age_in_days = raw.get("ageInDays")
    if isinstance(age_in_days, (int, float)):
        return datetime.now(timezone.utc) - timedelta(days=age_in_days)

    for key in ("posted_at", "date_posted", "postedDate", "posted_date"):
        value = raw.get(key)
        if not value:
            continue
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            continue
    return None


def normalize_result(source_name: str, raw: dict) -> dict:
    """Normalize raw job dictionary from an MCP tool invocation into standard schema.

    Args:
        source_name: Name of the originating MCP connector.
        raw: Raw job dict extracted from the MCP tool output.

    Returns:
        dict: Normalized job dictionary ready for Explore presentation or DB persistence.
    """
    description = strip_html(raw.get("description") or raw.get("summary") or "")
    url = raw.get("apply_url") or raw.get("url") or raw.get("job_url") or raw.get("link") or ""
    # HasData nests salary as {"min": ..., "max": ..., ...}; Jobo (and the
    # DB schema) expect flat salary_min/salary_max — confirmed against a
    # live HasData Glassdoor response.
    salary = raw.get("salary") if isinstance(raw.get("salary"), dict) else {}

    return {
        "source": source_name,
        "source_job_id": str(raw.get("id") or raw.get("job_id") or description_hash(url or description)[:16]),
        "company": _as_text(raw.get("company") or raw.get("employer")),
        "title": (raw.get("title") or raw.get("job_title") or "").strip(),
        "location": normalize_location(raw.get("location") or ""),
        "url": url,
        "description": description,
        "description_hash": description_hash(description),
        "employment_type": normalize_employment_type(raw.get("employment_type") or raw.get("job_type")),
        "posted_at": _parse_posted_at(raw),
        "salary_min": safe_int(raw.get("salary_min") or salary.get("min")),
        "salary_max": safe_int(raw.get("salary_max") or salary.get("max")),
    }


def _find_result_list(payload: dict) -> list | None:
    """Search a result dict for a job list, one "json" wrapper level deep.

    Handles two shapes seen from real servers: a job list directly under
    one of RESULT_LIST_KEYS (Jobo), or a raw-passthrough scrape response
    (HasData: `{"url", "status", "json": {..., "jobs": [...]}}`) where the
    actual payload sits one level inside a "json" key. Checked here rather
    than added to RESULT_LIST_KEYS itself, since "json" isn't a result-list
    key — it's a wrapper that itself needs re-searching.

    Args:
        payload: A result dict to search.

    Returns:
        list | None: The first matching list found, or None.
    """
    for key in RESULT_LIST_KEYS:
        if isinstance(payload.get(key), list):
            return payload[key]
    nested = payload.get("json")
    if isinstance(nested, dict):
        return _find_result_list(nested)
    return None


def _extract_results(call_result) -> list[dict]:
    """Extract list of raw job dictionaries from an MCP CallToolResult.

    Prefers `structured_content` (present when the server declares an
    output schema); falls back to parsing JSON out of the text content
    blocks. Gives up to an empty list rather than guessing at a shape
    that isn't there.

    Args:
        call_result: CallToolResult returned from client.call_tool().

    Returns:
        list[dict]: Extracted job dictionaries.
    """
    payload = call_result.structured_content
    if payload is not None:
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            return _find_result_list(payload) or []
        return []

    results: list[dict] = []
    for block in call_result.content or []:
        text = getattr(block, "text", None)
        if not text:
            continue
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, list):
            results.extend(parsed)
        elif isinstance(parsed, dict):
            results.extend(_find_result_list(parsed) or [])
    return results


async def search_source(source: McpSource, query: str, filters: dict) -> list[dict]:
    """Search a single MCP source connector and normalize its responses.

    Args:
        source: Target McpSource configuration.
        query: Query string.
        filters: Filter criteria dictionary.

    Returns:
        list[dict]: Normalized job postings, or empty list if source fails or has no search tool.
    """
    tools = await list_tools(source.url, source.api_key, source.auth_header)
    matrix = build_capability_matrix(tools)
    if matrix.search_tool is None:
        logger.warning("%s exposes no recognizable search tool; skipping", source.name)
        return []

    missing_required = [key for key in matrix.required_filters if key not in filters]
    if missing_required:
        # A call without these is guaranteed to fail against this source's
        # own schema (e.g. HasData's Glassdoor tool requires "location") —
        # skip the doomed round trip rather than making it and logging a
        # tool-level error every time.
        logger.warning(
            "%s search skipped: missing required filter(s) %s", source.name, missing_required
        )
        return []

    arguments = _build_search_arguments(matrix.search_tool, query, filters)
    call_result = await call_tool(
        source.url, source.api_key, matrix.search_tool.name, arguments, source.auth_header
    )
    if call_result.is_error:
        logger.warning("%s search returned an error: %s", source.name, call_result.content)
        return []

    return [normalize_result(source.name, raw) for raw in _extract_results(call_result)]


async def search(query: str, filters: dict | None = None) -> list[dict]:
    """Fan out search query to all configured, search-capable MCP sources in parallel.

    Fans `query` out to every configured, search-capable MCP source in
    parallel (backs POST /explore/search). A source that errors, times
    out, or turns out not to support search is skipped, not fatal.

    Args:
        query: User search query or keywords.
        filters: Optional dictionary of filter options.

    Returns:
        list[dict]: Aggregated list of normalized job results.
    """
    filters = filters or {}
    sources = configured_sources()
    if not sources:
        return []

    outcomes = await asyncio.gather(
        *(search_source(source, query, filters) for source in sources),
        return_exceptions=True,
    )

    results: list[dict] = []
    for source, outcome in zip(sources, outcomes):
        if isinstance(outcome, Exception):
            logger.warning("%s search failed: %s", source.name, outcome)
            continue
        results.extend(outcome)

    posted_within_days = filters.get("posted_within_days")
    if posted_within_days is not None:
        results = _filter_by_recency(results, posted_within_days)
    return results


def _filter_by_recency(results: list[dict], posted_within_days) -> list[dict]:
    """Drop results whose posted_at is missing or older than the cutoff.

    Applied here — after every source's results are merged — rather than
    only as a per-source request argument (FILTER_PARAM_CANDIDATES'
    "posted_within_days" entry still tries that too, for a source whose
    tool actually accepts it), because HasData's Glassdoor search tool has
    no date parameter at all (confirmed live: its schema is just
    `keyword`/`location`/`sort`/`domain`/`nextPageToken`) — the only way to
    honor "recent jobs only" against it is to filter its own results by
    the `ageInDays` this derived posted_at from, after the fact.

    A result with no derivable posted_at is dropped rather than kept "just
    in case" when this filter is active — the caller explicitly asked for
    recent-only, and an unknown age can't be confirmed to satisfy that.

    Args:
        results: Normalized results from every source, already merged.
        posted_within_days: Maximum age in days, from ExploreSearchRequest.filters.

    Returns:
        list[dict]: Only the results posted within the cutoff.
    """
    try:
        max_age_days = float(posted_within_days)
    except (TypeError, ValueError):
        return results

    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    kept = []
    for result in results:
        posted_at = result.get("posted_at")
        if posted_at is None:
            continue
        if posted_at.tzinfo is None:
            posted_at = posted_at.replace(tzinfo=timezone.utc)
        if posted_at >= cutoff:
            kept.append(result)
    return kept
