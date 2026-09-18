# API Contract

Keeps `CareerOps` (backend) and `../CareerOps-frontend` in sync. This file
and `../CareerOps-frontend/CONTRACT.md` describe the *same* wire contract,
one from each side. If they disagree, one of them is wrong — fix both in
the same change, never just one.

**Rule:** any change to a route's path, method, request/response shape,
status codes, or auth requirement is a contract change. When you make one
here:
1. Update the table and type block below.
2. Make the matching edit in `../CareerOps-frontend/CONTRACT.md` — same
   endpoint, same fields, same version number.
3. Bump `Contract version`.
4. If the frontend already has TypeScript types / an API client (it
   doesn't yet — still just a README, see `../CareerOps-frontend/README.md`),
   update those before merging, not after.

This file is a snapshot for quick cross-checking, not a replacement for
reading the real source when in doubt: `app/api/schemas.py` (exact
request/response models) and `app/api/routes/*.py` (routes). `memory/api.md`
has the full narrative version with rationale for *why* each thing is
shaped the way it is.

**Contract version: 1 — 2026-09-18**

---

## Base URL, auth, errors

- Base URL: wherever `uvicorn app.api.main:app` is running (`http://localhost:8000` by default).
- Auth: `Authorization: Bearer <token>` required on every route **except** `GET /health` and `POST /auth/login`.
- `POST /auth/login` is rate limited: 5 attempts / 5 minutes / (client ip + email) → `429`.
- 4xx error body: `{"detail": "<message>"}` (FastAPI's default via `HTTPException`).
- `422` (request validation failure, e.g. a bad field type or a `Field()` constraint like `TenantCreateRequest.slug`'s pattern) uses FastAPI's own shape instead: `{"detail": [{"loc": [...], "msg": "...", "type": "..."}]}`.

## Endpoints

| Method | Path | Auth | Request body | Response | Notes |
|---|---|---|---|---|---|
| GET | `/health` | none | — | `{"status": "ok"\|"degraded", "database": "ok"\|"unreachable"}` | Always 200 |
| POST | `/auth/login` | none (rate limited) | `LoginRequest` | `TokenOut` | 401 bad credentials, 429 rate limited |
| GET | `/auth/me` | bearer | — | `UserOut` | 404 if user record gone |
| POST | `/auth/users` | bearer + admin | `UserCreateRequest` | `UserOut` (201) | 400 bad role, 403 non-admin, 409 duplicate email |
| GET | `/auth/users` | bearer + admin | — | `UserOut[]` | 403 non-admin |
| DELETE | `/auth/users/{user_id}` | bearer + admin | — | `{"deleted": bool, "user_id": int}` | 403 protected default admin, 404 not found |
| POST | `/auth/tenants` | bearer + admin | `TenantCreateRequest` | `TenantOut` (201) | 409 duplicate slug |
| GET | `/jobs` | bearer | query: `status?`, `limit=50` (1-200), `offset=0` | `JobListItemOut[]` | — |
| GET | `/jobs/{job_id}` | bearer | — | `JobDetailOut` | 404 |
| GET | `/jobs/{job_id}/documents` | bearer | — | `GeneratedDocumentOut[]` | — |
| POST | `/applications/{application_id}/approve` | bearer | — | `ApplicationActionOut` | 404 |
| POST | `/applications/{application_id}/reject` | bearer | — | `ApplicationActionOut` | 404 |
| POST | `/applications/{application_id}/open` | bearer | — | `ApplicationActionOut` | 404. Opens the posting URL **server-side** (`webbrowser.open`) — only meaningful when the frontend and API run on the same machine |
| POST | `/applications/{application_id}/mark-applied` | bearer | — | `ApplicationActionOut` | 404. The only route that sets status `APPLIED` |
| GET | `/explore/capabilities` | bearer | — | `Record<string, CapabilityMatrixOut>` keyed by MCP source name | — |
| POST | `/explore/search` | bearer | `ExploreSearchRequest` | `ExploreResultOut[]` | — |
| POST | `/explore/save` | bearer | `ExploreSaveRequest` | `ExploreSaveResponseOut` | — |

## Types

Mirrors `app/api/schemas.py` exactly — field name, wire type. `?` = optional/nullable.

```
LoginRequest          { email: string, password: string, tenant_slug?: string = "default" }
TokenOut               { access_token: string, token_type: "bearer", tenant_id: number, tenant_slug: string, role: string, email: string }
UserOut                 { id: number, tenant_id: number, email: string, role: string, is_default_admin: boolean, is_active: boolean, created_at?: string }
UserCreateRequest       { email: string, password: string (min 8 chars), role?: string = "user" }
TenantOut               { id: number, name: string, slug: string, is_active: boolean, created_at?: string }
TenantCreateRequest     { name: string, slug: string (pattern ^[a-z0-9]+(-[a-z0-9]+)*$, max 63 chars) }

ApplicationOut          { application_id: number, status: string, applied_at?: string }
JobListItemOut          { job_id: number, company: string, title: string, location: string, url: string, status: string, fit_score?: number, confidence?: string, strong_matches: any[], missing_skills: any[], risks: any[] }
JobDetailOut             = JobListItemOut & { description: string, application?: ApplicationOut }
GeneratedDocumentOut    { id: number, type: string, file_path: string, version: number, claim_check_passed?: boolean, ats_check_passed?: boolean }
ApplicationActionOut    { application_id: number, status: string }

ExploreSearchRequest    { query: string, filters?: object = {} }
ExploreResultOut         { source: string, source_job_id: string, company: string, title: string, location: string, url: string, description: string, employment_type?: string, salary_min?: number, salary_max?: number }
ExploreSaveRequest       = ExploreResultOut  (same shape, posted back to /explore/save)
ExploreSaveResponseOut  { inserted: boolean }
CapabilityMatrixOut     { flags: Record<string, boolean> }
```

## Known gaps the frontend needs to design around

- **No `tenant_id` on jobs/applications/documents.** Auth gates *who* can call these routes, not *which tenant's data* they see — every authenticated user currently sees every job. See `memory/known-gaps.md`.
- **Timestamps are ISO 8601 strings** in the JSON response (pydantic serializes `datetime` fields that way) — parse client-side, don't assume a specific format beyond ISO 8601.
- **No logout/refresh-token endpoint.** A token is valid until it expires (8h default, `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`); there's nothing server-side to invalidate it early.
- **`/applications/{id}/open` opens a browser tab on the API's host**, not the caller's — only correct when frontend dev/prod server and the API process share a machine.
