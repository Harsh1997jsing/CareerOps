# CareerOps REST API Layer

## Overview

The FastAPI layer (`app/api/`) serves as the HTTP backend for the frontend interface (`frontend/`).
It is intentionally **read-heavy and decoupled from LLM logic**:
- It never calls Anthropic or executes LLM scoring/generation directly.
- It exposes results already produced by the pipeline services (`dashboard_data`, `tracker`, `mcp`).
- It strictly enforces CareerOps human-approval principles (CLAUDE.md Rules 1 and 5).

---

## Completion Status

- **Total Endpoints Planned:** 9
- **Total Endpoints Completed:** 9 (100% complete)
- **Test Coverage:** 16 unit tests across `tests/test_api_jobs.py`, `tests/test_api_applications.py`, and `tests/test_api_explore.py` (all mocked, zero external dependencies required).

---

## Endpoint Inventory

| # | HTTP Method | Route | Module | Purpose | Status |
|---|-------------|-------|--------|---------|:------:|
| 1 | `GET` | `/jobs` | `routes/jobs.py` | List jobs with match analysis summaries and optional `?status=` filtering | **Completed** |
| 2 | `GET` | `/jobs/{job_id}` | `routes/jobs.py` | Retrieve full job details, complete description, and linked application record | **Completed** |
| 3 | `GET` | `/jobs/{job_id}/documents` | `routes/jobs.py` | List generated resumes and cover letters with claim/ATS check statuses | **Completed** |
| 4 | `POST` | `/applications/{application_id}/approve` | `routes/applications.py` | Transition an application status to `APPROVED` | **Completed** |
| 5 | `POST` | `/applications/{application_id}/reject` | `routes/applications.py` | Transition an application status to `REJECTED` | **Completed** |
| 6 | `POST` | `/applications/{application_id}/open` | `routes/applications.py` | Open the posting URL in the host's default web browser | **Completed** |
| 7 | `POST` | `/applications/{application_id}/mark-applied` | `routes/applications.py` | Record manual human submission (`APPLIED`), update company cooldown | **Completed** |
| 8 | `GET` | `/explore/capabilities` | `routes/explore.py` | Inspect configured remote MCP servers and return supported filter/search flags | **Completed** |
| 9 | `POST` | `/explore/search` | `routes/explore.py` | Fan-out distributed job search across connected MCP connectors | **Completed** |
| 10 | `POST` | `/explore/save` | `routes/explore.py` | Recompute SHA-256 hash server-side and insert explored job into `jobs` table | **Completed** |

---

## Endpoint Details

### 1. Jobs (`app/api/routes/jobs.py`)

#### `GET /jobs`
- **Query Parameters:** `status: str | None` (e.g., `READY_FOR_REVIEW`, `APPROVED`, `REJECT`)
- **Response Schema:** `list[JobListItemOut]`
- **Underlying Service:** `app.services.dashboard_data.list_jobs(engine, status)`
- **Behavior:** Queries `jobs` joined with latest `job_analysis` row via `LEFT JOIN LATERAL`. Omits `description` to keep listing queries performant.

#### `GET /jobs/{job_id}`
- **Path Parameters:** `job_id: int`
- **Response Schema:** `JobDetailOut`
- **Underlying Service:** `app.services.dashboard_data.get_job(engine, job_id)`
- **Behavior:** Returns full job description, scoring analysis (strong matches, missing skills, risks), and associated `ApplicationOut` record if one exists. Returns `404 Not Found` if missing.

#### `GET /jobs/{job_id}/documents`
- **Path Parameters:** `job_id: int`
- **Response Schema:** `list[GeneratedDocumentOut]`
- **Underlying Service:** `app.services.dashboard_data.list_generated_documents(engine, job_id)`
- **Behavior:** Returns all versions of generated resumes and cover letters, including filesystem path and validation booleans (`claim_check_passed`, `ats_check_passed`).

---

### 2. Applications (`app/api/routes/applications.py`)

#### `POST /applications/{application_id}/approve`
- **Path Parameters:** `application_id: int`
- **Response Schema:** `ApplicationActionOut` (`application_id`, `status: "APPROVED"`)
- **Underlying Service:** `app.services.dashboard_data.approve_application(engine, application_id)`
- **Behavior:** Sets status to `APPROVED`. Indicates a human has reviewed the tailored resume/cover letter and approved them for submission.

#### `POST /applications/{application_id}/reject`
- **Path Parameters:** `application_id: int`
- **Response Schema:** `ApplicationActionOut` (`application_id`, `status: "REJECTED"`)
- **Underlying Service:** `app.services.dashboard_data.reject_application(engine, application_id)`
- **Behavior:** Sets status to `REJECTED`.

#### `POST /applications/{application_id}/open`
- **Path Parameters:** `application_id: int`
- **Response Schema:** `ApplicationActionOut` (`application_id`, `status: "OPENED"`)
- **Underlying Service:** `app.services.tracker.open_job_url(context.url)`
- **Behavior:** Resolves the application's job URL and invokes Python's standard `webbrowser.open(url)` on the machine running the API. Never automates form submission (adhering to Hard Rule 1).

#### `POST /applications/{application_id}/mark-applied`
- **Path Parameters:** `application_id: int`
- **Response Schema:** `ApplicationActionOut` (`application_id`, `status: "APPLIED"`)
- **Underlying Service:** `app.services.tracker.mark_applied(engine, application_id, job_id, company, confirmed=True)`
- **Behavior:** The **only** endpoint allowed to set `status = "APPLIED"`. Calls `mark_applied()` with `confirmed=True` in a single transaction that also updates `company_application_history` to trigger cooldown protections (Hard Rules 1 & 5).

---

### 3. Explore & MCP Connectors (`app/api/routes/explore.py`)

#### `GET /explore/capabilities`
- **Response Schema:** `dict[str, CapabilityMatrixOut]`
- **Underlying Service:** `app.sources.mcp.explore.get_all_capabilities()`
- **Behavior:** Discovers tool capabilities on configured MCP servers (e.g., JOBO, HasData) in parallel. Failed or unresponsive servers are skipped without breaking the response.

#### `POST /explore/search`
- **Request Body:** `ExploreSearchRequest` (`query: str`, `filters: dict`)
- **Response Schema:** `list[ExploreResultOut]`
- **Underlying Service:** `app.sources.mcp.explore.search(query, filters)`
- **Behavior:** Fans out the query to all responsive, search-capable MCP servers in parallel. Results are normalized into the standard schema. Results are not saved to the DB automatically.

#### `POST /explore/save`
- **Request Body:** `ExploreSaveRequest` (full posting payload)
- **Response Schema:** `ExploreSaveResponseOut` (`inserted: bool`)
- **Underlying Service:** `app.sources.common.insert_jobs(engine, [job])`
- **Behavior:** Recomputes the deterministic SHA-256 `description_hash` server-side before inserting into `jobs`. Returns `inserted: true` on success, or `inserted: false` if already in the database (via `ON CONFLICT (description_hash) DO NOTHING`).

---

## Architectural Guarantees

1. **Local-First Separation of Concerns:**
   - LLM schema definitions live in `app/llm/schemas.py`.
   - Wire API schema definitions live in `app/api/schemas.py`.
   - LLM prompt adjustments cannot accidentally break frontend contract contracts.
2. **CORS Configuration:**
   - Managed in `app/api/main.py`.
   - Configurable via `FRONTEND_ORIGIN` environment variable (defaults to `http://localhost:5173`).
3. **Database Dependencies:**
   - Injected via FastAPI's `Depends(get_db_engine)`.
   - Easily mocked in unit tests without touching a live PostgreSQL container.
