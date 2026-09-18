# CareerOps REST API Layer

## Overview

The FastAPI layer (`app/api/`) serves as the HTTP backend for the frontend interface (`frontend/`).
It is intentionally **read-heavy and decoupled from LLM logic**:
- It never calls Anthropic or executes LLM scoring/generation directly.
- It exposes results already produced by the pipeline services (`app/services/jobs.py`,
  `applications.py`, `tracker.py`, `app/sources/mcp/`).
- It strictly enforces CareerOps human-approval principles (CLAUDE.md Rules 1 and 5).
- Provides a **Multi-Tenant Stateless JWT Authentication** system with protected system admin and tenant isolation.
- Every DB-touching route and service function is `async` — see "Async SQLAlchemy" below.

**`app/services/dashboard_data.py` no longer exists.** It originally mixed jobs,
applications, and generated-document queries under a name left over from the
deleted Streamlit dashboard. Split into `app/services/jobs.py` (list_jobs,
get_job, list_generated_documents) and `app/services/applications.py`
(get_application_for_job, get_application_context, approve/reject/
set_application_status, check_cooldown_for_company) — one module per resource,
matching the route split below.

---

## Async SQLAlchemy

Every route handler and every DB-touching service function is `async def`,
using SQLAlchemy's async engine/session (`app/core/database.py`) — `asyncpg`
for Postgres, `aiosqlite` for SQLite (tests, and any local dev use of a
`sqlite:///` DATABASE_URL). `get_engine()` auto-upgrades a plain
`postgresql://`/`sqlite://` DATABASE_URL to its async-driver form
(`_to_async_url()`), so `.env` never needs to name the driver explicitly.
Alembic (`migrations/env.py`) is the one deliberate exception — it keeps
using the plain sync URL with `psycopg2`, since a one-off CLI migration run
has no need for an async driver.

`app/api/routes/__init__.py` exposes one aggregating `api_router` that
`main.py` mounts once, instead of `main.py` importing and including each
route module's router individually.

---

## Backend audit fixes (F1-F12)

A full backend audit (`backend.md`'s checklist) found 12 issues, all fixed
in this pass — see `git log`/the conversation for the full finding-by-
finding writeup. The ones that changed externally-visible behavior:

- **F1 — every route now requires auth.** `jobs.py`/`applications.py`/
  `explore.py` had zero authentication before this; `Depends(get_current_user)`
  is now set at the `APIRouter(dependencies=[...])` level on each, so no
  individual route can be added later and accidentally skip it. `/health`
  is the one deliberate exception (see below).
- **F2 — tenant scoping documented, not implemented.** Auth now gates
  *who* can call these routes, not *which tenant's* jobs they see —
  `Job`/`Application`/etc. still carry no `tenant_id`. Deliberate scope
  boundary, not an oversight; see `memory/known-gaps.md`.
- **F4 — the redundant Application re-fetch is gone.** `approve`/`reject`/
  `mark-applied` used to fetch the same `Application` row twice (measured:
  4 SQL statements, one a pure duplicate) because SQLAlchemy's identity
  map holds only weak references and the first fetch's local variable went
  out of scope. `applications_service.get_application()` now loads it once
  per request and every route/service function downstream reuses that
  same object. Measured after the fix: 3 statements.
- **F6 — `/auth/login` is now rate limited**, via `pyrate-limiter`
  (`app/core/rate_limit.py`): 5 attempts per client-ip+email per 5
  minutes, 429 past that. Every attempt counts against the budget, not
  just failures — pyrate-limiter has no non-consuming "peek," so "reset on
  success" wasn't cleanly expressible. Needed a custom per-key
  `BucketFactory`: the library's default `Limiter(Rate(...))` construction
  wraps a *single shared bucket* for every key (verified directly — two
  independent keys exhausted each other's budget), which would have made
  every login attempt on the whole server share one 5-per-5-minute budget.
- **F7 — password/slug validation.** `UserCreateRequest.password` now
  requires 8+ characters; `TenantCreateRequest.slug` now requires
  `^[a-z0-9]+(-[a-z0-9]+)*$`. Both were unconstrained `str` before.
- **F8 — `GET /jobs` is paginated.** `limit` (1-200, default 50) and
  `offset` query params; was previously unbounded.
- **F9 — `GET /health`** now exists (unauthenticated on purpose), calling
  `check_database_health()` — which existed already but nothing called
  it, and had its own bug fixed alongside (it called `get_engine()`
  *outside* its own try/except, so a missing `DATABASE_URL` crashed the
  health check instead of reporting "degraded").

---

## Completion Status

- **Total Endpoints Completed:** 17 endpoints across 5 route modules (100% complete)
- **Test Coverage** (all async, using `tests/conftest.py`'s `db_session` —
  a real aiosqlite in-memory session — instead of hand-mocked Session objects):
  - `tests/test_auth.py`: 14 service-level tests (password hashing, stateless JWT encoding/decoding, tenant isolation, protected default admin deletion prevention).
  - `tests/test_api_auth.py`: 17 route-level tests (login incl. rate limiting, profile `/auth/me`, admin user provisioning incl. F7 validation, forbidden regular user operations, blocked admin deletion).
  - `tests/test_api_jobs.py`: 11 tests (incl. F1 auth-required and F8 pagination).
  - `tests/test_api_applications.py`: 6 tests (incl. F1 auth-required).
  - `tests/test_api_explore.py`: 6 tests (incl. F1 auth-required).
  - `tests/test_api_health.py`: 3 tests.
  - `tests/test_jobs.py`: 8 tests (app/services/jobs.py).
  - `tests/test_applications.py`: 10 tests (app/services/applications.py).

---

## Endpoint Inventory

| # | HTTP Method | Route | Auth | Module | Purpose | Status |
|---|-------------|-------|:---:|--------|---------|:------:|
| 1 | `GET` | `/health` | none | `routes/health.py` | Report service + DB connectivity | **Completed** |
| 2 | `POST` | `/auth/login` | none (rate limited) | `routes/auth.py` | Authenticate email/password and issue stateless signed JWT access token | **Completed** |
| 3 | `GET` | `/auth/me` | JWT | `routes/auth.py` | Fetch authenticated user profile and tenant claims from Bearer token | **Completed** |
| 4 | `POST` | `/auth/users` | JWT+admin | `routes/auth.py` | Admin-only: Provision a new user within administrator's tenant | **Completed** |
| 5 | `GET` | `/auth/users` | JWT+admin | `routes/auth.py` | Admin-only: List all users belonging to administrator's tenant | **Completed** |
| 6 | `DELETE` | `/auth/users/{user_id}` | JWT+admin | `routes/auth.py` | Admin-only: Delete tenant user (Default admin is immutable/protected) | **Completed** |
| 7 | `POST` | `/auth/tenants` | JWT+admin | `routes/auth.py` | Admin-only: Register a new tenant organization | **Completed** |
| 8 | `GET` | `/jobs` | JWT | `routes/jobs.py` | List jobs with match analysis summaries, `?status=` filter, `?limit=&offset=` pagination | **Completed** |
| 9 | `GET` | `/jobs/{job_id}` | JWT | `routes/jobs.py` | Retrieve full job details, complete description, and linked application record | **Completed** |
| 10 | `GET` | `/jobs/{job_id}/documents` | JWT | `routes/jobs.py` | List generated resumes and cover letters with claim/ATS check statuses | **Completed** |
| 11 | `POST` | `/applications/{application_id}/approve` | JWT | `routes/applications.py` | Transition an application status to `APPROVED` | **Completed** |
| 12 | `POST` | `/applications/{application_id}/reject` | JWT | `routes/applications.py` | Transition an application status to `REJECTED` | **Completed** |
| 13 | `POST` | `/applications/{application_id}/open` | JWT | `routes/applications.py` | Open the posting URL in the host's default web browser | **Completed** |
| 14 | `POST` | `/applications/{application_id}/mark-applied` | JWT | `routes/applications.py` | Record manual human submission (`APPLIED`), update company cooldown | **Completed** |
| 15 | `GET` | `/explore/capabilities` | JWT | `routes/explore.py` | Inspect configured remote MCP servers and return supported filter/search flags | **Completed** |
| 16 | `POST` | `/explore/search` | JWT | `routes/explore.py` | Fan-out distributed job search across connected MCP connectors | **Completed** |
| 17 | `POST` | `/explore/save` | JWT | `routes/explore.py` | Recompute SHA-256 hash server-side and insert explored job into `jobs` table | **Completed** |

---

## Endpoint Details

### 1. Authentication & Multi-Tenancy (`app/api/routes/auth.py`)

Stateless JWT authentication and tenant-scoped user management. No server-side session tables or Redis storage are utilized.

#### `POST /auth/login`
- **Request Body:** `LoginRequest` (`email: str`, `password: str`, `tenant_slug: str = "default"`)
- **Response Schema:** `TokenOut` (`access_token`, `token_type: "bearer"`, `tenant_id`, `tenant_slug`, `role`, `email`)
- **Underlying Service:** `app.services.auth.authenticate_user(session, email, password, tenant_slug)` & `create_access_token(...)`
- **Behavior:** Validates password using PBKDF2-HMAC-SHA256 (100,000 iterations). Returns a stateless JWT bearer token encoded with claims (`sub`, `tenant_id`, `tenant_slug`, `email`, `role`, `is_default_admin`). Returns `401 Unauthorized` on mismatch.

#### `GET /auth/me`
- **Headers:** `Authorization: Bearer <token>`
- **Response Schema:** `UserOut` (`id`, `tenant_id`, `email`, `role`, `is_default_admin`, `is_active`, `created_at`)
- **Underlying Dependency:** `get_current_user` extracts and cryptographically validates the token.
- **Behavior:** Returns current account details for the authenticated user.

#### `POST /auth/users`
- **Headers:** `Authorization: Bearer <token>` (Must have `role == "admin"`)
- **Request Body:** `UserCreateRequest` (`email: str`, `password: str`, `role: str = "user"`)
- **Response Schema:** `UserOut` (Status code: `201 Created`)
- **Underlying Service:** `app.services.auth.create_user(session, tenant_id, email, password, role)`
- **Behavior:** Only administrators can create users. Newly created users are automatically scoped strictly to the administrator's tenant. Returns `403 Forbidden` if requested by a non-admin, and `409 Conflict` if the email already exists in that tenant.

#### `GET /auth/users`
- **Headers:** `Authorization: Bearer <token>` (Must have `role == "admin"`)
- **Response Schema:** `list[UserOut]`
- **Underlying Service:** `app.services.auth.list_users(session, tenant_id)`
- **Behavior:** Returns all user accounts scoped to the requesting administrator's tenant organization.

#### `DELETE /auth/users/{user_id}`
- **Headers:** `Authorization: Bearer <token>` (Must have `role == "admin"`)
- **Path Parameters:** `user_id: int`
- **Response Schema:** `dict` (`{"deleted": true, "user_id": int}`)
- **Underlying Service:** `app.services.auth.delete_user(session, tenant_id, user_id)`
- **Security Invariant:** **The default administrator (`is_default_admin=True`) CAN NEVER BE DELETED under any circumstances.**
  - If a user attempts to delete the default admin, the service raises `ProtectedAdminError`, and the endpoint responds with `403 Forbidden` (`"The default administrator user is protected and cannot be deleted"`).
  - Non-existent user returns `404 Not Found`.

#### `POST /auth/tenants`
- **Headers:** `Authorization: Bearer <token>` (Must have `role == "admin"`)
- **Request Body:** `TenantCreateRequest` (`name: str`, `slug: str`)
- **Response Schema:** `TenantOut` (Status code: `201 Created`)
- **Underlying Service:** `app.services.auth.create_tenant(session, name, slug)`
- **Behavior:** Registers a new tenant organization. Returns `409 Conflict` if the slug is already registered.

---

### 2. Jobs (`app/api/routes/jobs.py`)

All three routes below require auth (`Depends(get_current_user)` at the
router level — audit finding F1) but apply no tenant filter (finding F2).

#### `GET /jobs`
- **Query Parameters:** `status: str | None` (e.g., `READY_FOR_REVIEW`, `APPROVED`, `REJECT`); `limit: int = 50` (1-200); `offset: int = 0` (audit finding F8 — previously unbounded)
- **Response Schema:** `list[JobListItemOut]`
- **Underlying Service:** `app.services.jobs.list_jobs(session, status, limit=limit, offset=offset)`
- **Behavior:** Queries `jobs` (via SQLAlchemy `selectinload`, not a hand-written `LEFT JOIN LATERAL`) joined with the latest `job_analysis` row per job. Omits `description` to keep listing queries performant.

#### `GET /jobs/{job_id}`
- **Path Parameters:** `job_id: int`
- **Response Schema:** `JobDetailOut`
- **Underlying Service:** `app.services.jobs.get_job(session, job_id)`
- **Behavior:** Returns full job description, scoring analysis (strong matches, missing skills, risks), and associated `ApplicationOut` record if one exists. Returns `404 Not Found` if missing.

#### `GET /jobs/{job_id}/documents`
- **Path Parameters:** `job_id: int`
- **Response Schema:** `list[GeneratedDocumentOut]`
- **Underlying Service:** `app.services.jobs.list_generated_documents(session, job_id)`
- **Behavior:** Returns all versions of generated resumes and cover letters, including filesystem path and validation booleans (`claim_check_passed`, `ats_check_passed`).

---

### 3. Applications (`app/api/routes/applications.py`)

All four routes require auth (audit finding F1) and share one
`_get_application_or_404()` helper that loads the `Application` ORM row
once (with its `Job` eager-loaded) — every route reuses that same object
for both reading (url/company) and mutating it, instead of a second
by-id lookup (audit finding F4).

#### `POST /applications/{application_id}/approve`
- **Path Parameters:** `application_id: int`
- **Response Schema:** `ApplicationActionOut` (`application_id`, `status: "APPROVED"`)
- **Underlying Service:** `app.services.applications.set_status(session, application, "APPROVED")`
- **Behavior:** Sets status to `APPROVED`. Indicates a human has reviewed the tailored resume/cover letter and approved them for submission.

#### `POST /applications/{application_id}/reject`
- **Path Parameters:** `application_id: int`
- **Response Schema:** `ApplicationActionOut` (`application_id`, `status: "REJECTED"`)
- **Underlying Service:** `app.services.applications.set_status(session, application, "REJECTED")`
- **Behavior:** Sets status to `REJECTED`.

#### `POST /applications/{application_id}/open`
- **Path Parameters:** `application_id: int`
- **Response Schema:** `ApplicationActionOut` (`application_id`, `status: "OPENED"`)
- **Underlying Service:** `app.services.tracker.open_job_url(application.job.url)`
- **Behavior:** Resolves the application's job URL and invokes Python's standard `webbrowser.open(url)` on the machine running the API. Never automates form submission (adhering to Hard Rule 1).

#### `POST /applications/{application_id}/mark-applied`
- **Path Parameters:** `application_id: int`
- **Response Schema:** `ApplicationActionOut` (`application_id`, `status: "APPLIED"`)
- **Underlying Service:** `app.services.tracker.mark_applied(session, application_id, job_id, company, confirmed=True, application=application)`
- **Behavior:** The **only** endpoint allowed to set `status = "APPLIED"`. Calls `mark_applied()` with `confirmed=True` in a single transaction that also updates `company_application_history` to trigger cooldown protections (Hard Rules 1 & 5). The `application=` kwarg is the F4 fix — passes the already-loaded row through instead of `mark_applied()` fetching it again.

---

### 4. Explore & MCP Connectors (`app/api/routes/explore.py`)

All three routes require auth (audit finding F1).

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
- **Underlying Service:** `app.sources.common.insert_jobs(session, [job])`
- **Behavior:** Recomputes the deterministic SHA-256 `description_hash` server-side before inserting into `jobs`. Returns `inserted: true` on success, or `inserted: false` if already in the database — `insert_jobs()` attempts each row inside its own SAVEPOINT (`async with session.begin_nested()`) and catches `IntegrityError` on the `description_hash` unique constraint, a portable check-then-write rather than a Postgres-specific `ON CONFLICT`.

---

## Architectural Guarantees

1. **Stateless JWT Security:**
   - Cryptographically signed with HMAC-SHA256 (`HS256`), `algorithms=[...]` pinned explicitly on decode (no algorithm-confusion risk).
   - PBKDF2-HMAC-SHA256 password hashing with 100,000 iterations and 16-byte random salts.
   - Zero server-side session persistence tables needed.
   - Default token lifetime is 8h, not 24h (audit finding F5 — shortened; still no revocation/refresh-token mechanism, a leaked token is valid until it expires).
   - `/auth/login` is rate limited via `pyrate-limiter` — 5 attempts per client-ip+email per 5 minutes (audit finding F6).
2. **Protected Default Administrator:**
   - Seeded on initial startup with `is_default_admin = true`.
   - Immutable security guarantee: cannot be deleted by any route or user.
3. **Tenant isolation — users only, not pipeline data (audit finding F2):**
   - User queries and creation are strictly bound to `tenant_id`.
   - `Job`/`JobAnalysis`/`Application`/`GeneratedDocument`/`CompanyApplicationHistory`
     carry **no** `tenant_id` — any authenticated user of any tenant can read/act on
     every job and application. Deliberate scope boundary for now, not an
     oversight; see `memory/known-gaps.md`.
4. **Local-First Separation of Concerns:**
   - LLM schema definitions live in `app/llm/schemas.py`.
   - Wire API schema definitions live in `app/api/schemas.py`.
   - LLM prompt adjustments cannot accidentally break frontend contract contracts.
5. **CORS Configuration:**
   - Managed in `app/api/main.py`.
   - Supports GET, POST, DELETE, PUT, PATCH, OPTIONS.
   - Configurable via `FRONTEND_ORIGIN` environment variable (defaults to `http://localhost:5173`).
6. **Database Dependencies:**
   - Injected via FastAPI's `Depends(get_db)`, an `AsyncSession` — see "Async SQLAlchemy" above.
   - Tested against a real aiosqlite in-memory session (`tests/conftest.py`'s `db_session`, or a
     per-fixture engine in `tests/test_api_auth.py`). No `StaticPool` needed — a single
     `sqlite+aiosqlite:///:memory:` `AsyncEngine` already shares one underlying connection across
     every session opened from it, the same way the sync engine defaults to `SingletonThreadPool`
     for `sqlite:///:memory:`.
