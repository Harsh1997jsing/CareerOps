# CareerOps REST API Layer

## Overview

The FastAPI layer (`app/api/`) serves as the HTTP backend for the frontend interface (`frontend/`).
It is intentionally **read-heavy and decoupled from LLM logic**:
- It never calls Anthropic or executes LLM scoring/generation directly.
- It exposes results already produced by the pipeline services (`dashboard_data`, `tracker`, `mcp`).
- It strictly enforces CareerOps human-approval principles (CLAUDE.md Rules 1 and 5).
- Provides a **Multi-Tenant Stateless JWT Authentication** system with protected system admin and tenant isolation.

---

## Completion Status

- **Total Endpoints Completed:** 16 endpoints across 4 route modules (100% complete)
- **Test Coverage:**
  - `tests/test_auth.py`: 13 service-level tests (password hashing, stateless JWT encoding/decoding, tenant isolation, protected default admin deletion prevention).
  - `tests/test_api_auth.py`: 13 route-level tests (login, profile `/auth/me`, admin user provisioning, forbidden regular user operations, blocked admin deletion).
  - `tests/test_api_jobs.py`: 6 tests.
  - `tests/test_api_applications.py`: 5 tests.
  - `tests/test_api_explore.py`: 5 tests.

---

## Endpoint Inventory

| # | HTTP Method | Route | Module | Purpose | Status |
|---|-------------|-------|--------|---------|:------:|
| 1 | `POST` | `/auth/login` | `routes/auth.py` | Authenticate email/password and issue stateless signed JWT access token | **Completed** |
| 2 | `GET` | `/auth/me` | `routes/auth.py` | Fetch authenticated user profile and tenant claims from Bearer token | **Completed** |
| 3 | `POST` | `/auth/users` | `routes/auth.py` | Admin-only: Provision a new user within administrator's tenant | **Completed** |
| 4 | `GET` | `/auth/users` | `routes/auth.py` | Admin-only: List all users belonging to administrator's tenant | **Completed** |
| 5 | `DELETE` | `/auth/users/{user_id}` | `routes/auth.py` | Admin-only: Delete tenant user (Default admin is immutable/protected) | **Completed** |
| 6 | `POST` | `/auth/tenants` | `routes/auth.py` | Admin-only: Register a new tenant organization | **Completed** |
| 7 | `GET` | `/jobs` | `routes/jobs.py` | List jobs with match analysis summaries and optional `?status=` filtering | **Completed** |
| 8 | `GET` | `/jobs/{job_id}` | `routes/jobs.py` | Retrieve full job details, complete description, and linked application record | **Completed** |
| 9 | `GET` | `/jobs/{job_id}/documents` | `routes/jobs.py` | List generated resumes and cover letters with claim/ATS check statuses | **Completed** |
| 10 | `POST` | `/applications/{application_id}/approve` | `routes/applications.py` | Transition an application status to `APPROVED` | **Completed** |
| 11 | `POST` | `/applications/{application_id}/reject` | `routes/applications.py` | Transition an application status to `REJECTED` | **Completed** |
| 12 | `POST` | `/applications/{application_id}/open` | `routes/applications.py` | Open the posting URL in the host's default web browser | **Completed** |
| 13 | `POST` | `/applications/{application_id}/mark-applied` | `routes/applications.py` | Record manual human submission (`APPLIED`), update company cooldown | **Completed** |
| 14 | `GET` | `/explore/capabilities` | `routes/explore.py` | Inspect configured remote MCP servers and return supported filter/search flags | **Completed** |
| 15 | `POST` | `/explore/search` | `routes/explore.py` | Fan-out distributed job search across connected MCP connectors | **Completed** |
| 16 | `POST` | `/explore/save` | `routes/explore.py` | Recompute SHA-256 hash server-side and insert explored job into `jobs` table | **Completed** |

---

## Endpoint Details

### 1. Authentication & Multi-Tenancy (`app/api/routes/auth.py`)

Stateless JWT authentication and tenant-scoped user management. No server-side session tables or Redis storage are utilized.

#### `POST /auth/login`
- **Request Body:** `LoginRequest` (`email: str`, `password: str`, `tenant_slug: str = "default"`)
- **Response Schema:** `TokenOut` (`access_token`, `token_type: "bearer"`, `tenant_id`, `tenant_slug`, `role`, `email`)
- **Underlying Service:** `app.services.auth.authenticate_user(engine, email, password, tenant_slug)` & `create_access_token(...)`
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
- **Underlying Service:** `app.services.auth.create_user(engine, tenant_id, email, password, role)`
- **Behavior:** Only administrators can create users. Newly created users are automatically scoped strictly to the administrator's tenant. Returns `403 Forbidden` if requested by a non-admin, and `409 Conflict` if the email already exists in that tenant.

#### `GET /auth/users`
- **Headers:** `Authorization: Bearer <token>` (Must have `role == "admin"`)
- **Response Schema:** `list[UserOut]`
- **Underlying Service:** `app.services.auth.list_users(engine, tenant_id)`
- **Behavior:** Returns all user accounts scoped to the requesting administrator's tenant organization.

#### `DELETE /auth/users/{user_id}`
- **Headers:** `Authorization: Bearer <token>` (Must have `role == "admin"`)
- **Path Parameters:** `user_id: int`
- **Response Schema:** `dict` (`{"deleted": true, "user_id": int}`)
- **Underlying Service:** `app.services.auth.delete_user(engine, tenant_id, user_id)`
- **Security Invariant:** **The default administrator (`is_default_admin=True`) CAN NEVER BE DELETED under any circumstances.**
  - If a user attempts to delete the default admin, the service raises `ProtectedAdminError`, and the endpoint responds with `403 Forbidden` (`"The default administrator user is protected and cannot be deleted"`).
  - Non-existent user returns `404 Not Found`.

#### `POST /auth/tenants`
- **Headers:** `Authorization: Bearer <token>` (Must have `role == "admin"`)
- **Request Body:** `TenantCreateRequest` (`name: str`, `slug: str`)
- **Response Schema:** `TenantOut` (Status code: `201 Created`)
- **Underlying Service:** `app.services.auth.create_tenant(engine, name, slug)`
- **Behavior:** Registers a new tenant organization. Returns `409 Conflict` if the slug is already registered.

---

### 2. Jobs (`app/api/routes/jobs.py`)

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

### 3. Applications (`app/api/routes/applications.py`)

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

### 4. Explore & MCP Connectors (`app/api/routes/explore.py`)

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

1. **Stateless JWT Security:**
   - Cryptographically signed with HMAC-SHA256 (`HS256`).
   - PBKDF2-HMAC-SHA256 password hashing with 100,000 iterations and 16-byte random salts.
   - Zero server-side session persistence tables needed.
2. **Protected Default Administrator:**
   - Seeded on initial startup with `is_default_admin = true`.
   - Immutable security guarantee: cannot be deleted by any route or user.
3. **Tenant Boundary Isolation:**
   - User queries and creation strictly bound to `tenant_id`.
4. **Local-First Separation of Concerns:**
   - LLM schema definitions live in `app/llm/schemas.py`.
   - Wire API schema definitions live in `app/api/schemas.py`.
   - LLM prompt adjustments cannot accidentally break frontend contract contracts.
5. **CORS Configuration:**
   - Managed in `app/api/main.py`.
   - Supports GET, POST, DELETE, PUT, PATCH, OPTIONS.
   - Configurable via `FRONTEND_ORIGIN` environment variable (defaults to `http://localhost:5173`).
6. **Database Dependencies:**
   - Injected via FastAPI's `Depends(get_db_engine)`.
   - Tested seamlessly with both PostgreSQL and SQLite in-memory with `StaticPool`.
