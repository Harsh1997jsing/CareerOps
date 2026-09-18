"""
HTTP request/response shapes for app/api routes — distinct from
app/llm/schemas.py, which is LLM output shapes. Keeping them separate
means an LLM schema change (job_scorer's prompt, say) can't silently
change what the frontend receives over the wire.
"""

from pydantic import BaseModel


class ApplicationOut(BaseModel):
    """Application status summary returned to the frontend.

    Attributes:
        application_id: Primary key of the application.
        status: Application workflow status (e.g., 'READY_FOR_REVIEW', 'APPROVED', 'APPLIED').
        applied_at: ISO 8601 formatted timestamp when human manually submitted, if applied.
    """
    application_id: int
    status: str
    applied_at: str | None


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
    """Normalized job posting returned from an MCP exploration search.

    Attributes:
        source: Name of the MCP source connector providing the job.
        source_job_id: Unique identifier for the job on the originating platform.
        company: Employer / company name.
        title: Job role or position title.
        location: Normalized location string.
        url: Link to apply or view the job.
        description: Job description text.
        employment_type: Normalized employment type (e.g., 'Full-time'), if available.
        salary_min: Minimum compensation figure, if provided.
        salary_max: Maximum compensation figure, if provided.
    """
    source: str
    source_job_id: str
    company: str
    title: str
    location: str
    url: str
    description: str
    employment_type: str | None
    salary_min: int | None
    salary_max: int | None


class ExploreSaveRequest(ExploreResultOut):
    """Payload to persist an explored MCP job into the local `jobs` database table."""
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
    """
    flags: dict[str, bool]
