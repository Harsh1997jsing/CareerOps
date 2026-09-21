"""
HTTP request/response shapes for app/api routes — distinct from
app/llm/schemas.py, which is LLM output shapes. Keeping them separate
means an LLM schema change (job_scorer's prompt, say) can't silently
change what the frontend receives over the wire.

Timestamp fields are typed `datetime | str | None`, not `str | None`:
routes build these directly from ORM/domain objects via
`Out.model_validate(obj, from_attributes=True)`, and pydantic only
serializes a `datetime` to an ISO 8601 string in the JSON response when
the field's declared type actually accepts one — a `str`-only field
raises a validation error on a real `datetime` value instead of
formatting it. The `| str` half covers domain objects that already pass
a pre-formatted string.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ApplicationOut(BaseModel):
    """Application status summary returned to the frontend.

    Attributes:
        application_id: Primary key of the application.
        status: Application workflow status (e.g., 'READY_FOR_REVIEW', 'APPROVED', 'APPLIED').
        applied_at: Timestamp when human manually submitted, if applied.
    """
    application_id: int
    status: str
    applied_at: datetime | str | None


class JobListItemOut(BaseModel):
    """Job summary item for list and filtering views.

    Attributes:
        job_id: Unique database identifier of the job.
        company: Employer / organization name.
        title: Position or role title.
        location: Normalized location string (e.g., 'Remote', 'Bangalore').
        url: Direct link to the original job posting.
        status: Current pipeline status of the job.
        fit_score: Numerical fit score (0-100) from LLM analysis, if scored.
        confidence: Analysis confidence level ('high', 'medium', 'low', or None).
        strong_matches: List of candidate skills explicitly matching requirements.
        missing_skills: List of required or desired skills not present in evidence.
        risks: List of potential risks or concerns identified in the posting.
    """
    job_id: int
    company: str
    title: str
    location: str
    url: str
    status: str
    posted_at: datetime | str | None = None
    fit_score: int | None
    confidence: str | None
    strong_matches: list
    missing_skills: list
    risks: list


class JobDetailOut(JobListItemOut):
    """Full detail of a job, including full description and linked application.

    Attributes:
        description: Full text description of the job posting.
        application: Associated application record, if an application exists.
    """
    description: str
    application: ApplicationOut | None


class JobStatusActionOut(BaseModel):
    """Result of directly setting a job's own status (reject/restore).

    Attributes:
        job_id: Identifier of the updated job.
        status: The job's status after the action.
    """
    job_id: int
    status: str


class GeneratedDocumentOut(BaseModel):
    """Metadata and validation status for a generated resume or cover letter.

    Attributes:
        id: Primary key of the generated document record.
        type: Document type ('resume' or 'cover_letter').
        file_path: Filesystem path to the generated DOCX file.
        version: Monotonically increasing version number for this job and type.
        claim_check_passed: Whether all claims were verified against evidence.
        ats_check_passed: Whether ATS structural and round-trip text checks passed.
    """
    id: int
    type: str
    file_path: str
    version: int
    claim_check_passed: bool | None
    ats_check_passed: bool | None


class GenerateDocumentRequest(BaseModel):
    """Request to generate a tailored resume or cover letter for a job.

    Attributes:
        type: Which document to generate.
    """
    type: Literal["resume", "cover_letter"]


class ApplicationActionOut(BaseModel):
    """Result of an application state transition action (approve, reject, open, mark-applied).

    Attributes:
        application_id: Identifier of the updated application.
        status: Resulting application status after applying the action.
    """
    application_id: int
    status: str


class ExploreSearchRequest(BaseModel):
    """Search request payload for searching jobs across remote MCP connectors.

    Attributes:
        query: Free-text search term or keywords.
        filters: Optional filter dictionary (e.g., location, remote, employment_type).
    """
    query: str
    filters: dict = {}


class ExploreResultOut(BaseModel):
    """A normalized, not-yet-saved job posting — the shared shape every
    discovery source (MCP Explore, Greenhouse/Lever targets, JobSpy) hands
    back to the frontend before the user picks which ones to add to the
    Dashboard. Despite the name, this isn't Explore-specific: `/targets/search`
    and `/scrape/jobspy` return the same shape, and all three pages save
    through the same `/explore/save` route — see that route's docstring.

    Attributes:
        source: Name of the originating source ('jobo', 'hasdata', 'greenhouse', 'lever', 'indeed', 'glassdoor', ...).
        source_job_id: Unique identifier for the job on the originating platform.
        company: Employer / company name.
        title: Job role or position title.
        location: Normalized location string.
        url: Link to apply or view the job.
        description: Job description text.
        employment_type: Normalized employment type (e.g., 'Full-time'), if available.
        salary_min: Minimum compensation figure, if provided.
        salary_max: Maximum compensation figure, if provided.
        posted_at: When the job was posted, if known (see mcp/explore.py for
            how approximate this can be for some sources).
    """
    source: str
    source_job_id: str
    company: str
    title: str
    location: str
    url: str
    description: str
    employment_type: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    # Deliberately `datetime | None`, not `datetime | str | None` like the
    # ORM-backed *Out models elsewhere in this file. This type is used as a
    # REQUEST body (ExploreSaveRequest extends it) as well as a response —
    # live bug (2026-09-19): with `| str` in the union, pydantic's smart-
    # union matching kept an incoming JSON date string as plain `str`
    # rather than coercing it to `datetime`, so a search result's
    # `posted_at` round-tripped back through POST /explore/save reached
    # asyncpg as a raw string for a TIMESTAMP column and 500'd
    # (`invalid input ... expected a datetime.date or datetime.datetime
    # instance, got 'str'`) — which surfaces in a browser as a misleading
    # CORS error, not the real 500, since the failed response never gets
    # CORS headers. `datetime | None` alone parses an ISO string into a
    # real `datetime` correctly; nothing here ever legitimately needs to
    # pass a pre-formatted string (every source already produces
    # `datetime | None` before this model is built).
    posted_at: datetime | None = None


class ChatSearchResultOut(BaseModel):
    """A staged chat-search result — ExploreResultOut's shape plus the staged
    row's own id, so a chat turn can reference it (e.g. to save it) without
    resending its full description back through the API or the model.

    Attributes:
        id: Database id of this staged row (see app/models/chat_search.py).
        source, source_job_id, company, title, location, url, description,
            employment_type, salary_min, salary_max, posted_at: Same as
            ExploreResultOut.
        summary: One-line AI summary of the JD (see
            app/services/chat_search.py's summarize_results), or None if
            summarization wasn't run for this result.
    """
    id: int
    source: str
    source_job_id: str
    company: str
    title: str
    location: str
    url: str
    description: str
    employment_type: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    posted_at: datetime | None = None
    summary: str | None = None


class ChatMessageRequest(BaseModel):
    """One turn of the chat search — a message plus filters already confirmed
    in this conversation, carried forward by the caller rather than
    reconstructed server-side from a stored transcript (see
    app/services/chat_search.py's module docstring).

    Attributes:
        session_id: Client-generated id identifying this chat conversation
            (also scopes staged results — see GET /chat/results/{session_id}).
        message: The user's latest chat message.
        known_filters: Filters already confirmed earlier in this
            conversation, as returned by a prior turn's `filters`.
    """
    session_id: str
    message: str
    known_filters: dict = {}


class ChatMessageResponse(BaseModel):
    """Result of one chat search turn.

    Attributes:
        reply: Short natural-language reply — either a clarifying question
            or a summary of what the search found.
        filters: The filters now confirmed for this conversation (pass
            back as `known_filters` on the next turn).
        ready: True if a search was actually run this turn.
        results: Newly staged results, if `ready` is true; empty otherwise.
    """
    reply: str
    filters: dict
    ready: bool
    results: list[ChatSearchResultOut] = []


class ExploreSaveRequest(ExploreResultOut):
    """Payload to persist any discovered job (Explore, a company target, or a
    JobSpy scrape result) into the local `jobs` database table."""
    pass


class ExploreSaveResponseOut(BaseModel):
    """Response indicating whether an explored job was inserted into the database.

    Attributes:
        inserted: True if inserted; False if skipped as a duplicate.
    """
    inserted: bool


class CapabilityMatrixOut(BaseModel):
    """Supported search and filter capabilities for an MCP job connector.

    Attributes:
        flags: Mapping of capability names (e.g. 'search', 'location_filter') to support booleans.
        required_filters: Canonical filter keys (e.g. 'location') this
            source's search tool requires — omitting one guarantees a
            failed search against this source, not just a broader one.
    """
    flags: dict[str, bool]
    required_filters: list[str] = []


class LoginRequest(BaseModel):
    """Credentials submitted to obtain a stateless JWT access token.

    Attributes:
        email: Registered account email address.
        password: Raw password.
        tenant_slug: Slug of the target organization (defaults to 'default').
    """
    email: str
    password: str
    tenant_slug: str = "default"


class TokenOut(BaseModel):
    """Stateless JWT access token response.

    Attributes:
        access_token: Encoded JWT bearer token string.
        token_type: Token type identifier ('bearer').
        tenant_id: Numerical tenant ID.
        tenant_slug: Tenant organization slug.
        role: User role ('admin' or 'user').
        email: Authenticated user email.
    """
    access_token: str
    token_type: str = "bearer"
    tenant_id: int
    tenant_slug: str
    role: str
    email: str


class UserOut(BaseModel):
    """User account details returned across API routes.

    Attributes:
        id: Unique user primary key ID.
        tenant_id: Tenant organization ID.
        email: User email address.
        role: Account role ('admin' or 'user').
        is_default_admin: Whether account is the protected system administrator.
        is_active: Whether user account is enabled.
        created_at: Account creation timestamp string if available.
    """
    id: int
    tenant_id: int
    email: str
    role: str
    is_default_admin: bool
    is_active: bool
    created_at: datetime | str | None = None


class UserCreateRequest(BaseModel):
    """Payload to provision a new user under the current admin's tenant.

    Attributes:
        email: New user's email address.
        password: Initial password (min 8 characters — audit finding F7,
            previously unvalidated).
        role: User role ('user' or 'admin', defaults to 'user').
    """
    email: str
    password: str = Field(min_length=8)
    role: str = "user"


class TenantCreateRequest(BaseModel):
    """Payload to register a new tenant organization.

    Attributes:
        name: Organization display name.
        slug: Normalized identifier slug — lowercase letters, digits, and
            hyphens only (audit finding F7, previously unvalidated: any
            string, including spaces/uppercase, was accepted and merely
            lowercased, not rejected).
    """
    name: str
    slug: str = Field(min_length=1, max_length=63, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")


class CompanyTargetOut(BaseModel):
    """One configured company target from data/companies.yaml.

    Attributes:
        source: Which adapter ingests this target ('greenhouse' or 'lever').
        company: Display name of the company.
        identifier: The board token (Greenhouse) or company slug (Lever)
            used to fetch its postings.
    """
    source: str
    company: str
    identifier: str


class ScrapeJobspyRequest(BaseModel):
    """Request to run a multi-site JobSpy scrape.

    Attributes:
        search_term: Keywords or title query to scrape for.
        location: Optional location query.
        sites: Job sites to scrape — anything outside jobspy_source's
            ALLOWED_SITES (no 'linkedin', ever — CLAUDE.md rule 2) is
            silently dropped server-side, not rejected.
        results_wanted: Target number of postings (capped server-side at
            MAX_JOBS_PER_RUN = 50).
        experience: Optional free-text experience-level filter (e.g.
            "senior", "3-5 yrs"), applied app-side after scraping — jobspy
            has no matching input parameter, so this only narrows results
            from sites that report an experience field in the first place
            (see app/sources/jobspy_source.py's _matches_experience).
    """
    search_term: str
    location: str | None = None
    sites: list[str] | None = None
    results_wanted: int = 50
    experience: str | None = None


class TenantOut(BaseModel):
    """Tenant organization representation returned across API routes.

    Attributes:
        id: Unique tenant ID.
        name: Organization display name.
        slug: Tenant identifier slug.
        is_active: Whether organization is active.
        created_at: Creation timestamp string if available.
    """
    id: int
    name: str
    slug: str
    is_active: bool
    created_at: datetime | str | None = None

