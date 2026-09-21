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
4. Update the frontend's TypeScript types (`../CareerOps-frontend/src/types/api.ts`)
   and API client (`../CareerOps-frontend/src/api/*.ts`) before merging, not after.

This file is a snapshot for quick cross-checking, not a replacement for
reading the real source when in doubt: `app/api/schemas.py` (exact
request/response models) and `app/api/routes/*.py` (routes). `memory/api.md`
has the full narrative version with rationale for *why* each thing is
shaped the way it is.

**Contract version: 7 — 2026-09-21**

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
| GET | `/jobs` | bearer | query: `status?`, `q?` (description substring, case-insensitive), `posted_within_days?` (≥1), `limit=50` (1-200), `offset=0` | `JobListItemOut[]` | `posted_within_days` matches on `posted_at`, falling back to `collected_at` when a job has no known posting date |
| GET | `/jobs/{job_id}` | bearer | — | `JobDetailOut` | 404 |
| GET | `/jobs/{job_id}/documents` | bearer | — | `GeneratedDocumentOut[]` | — |
| POST | `/jobs/{job_id}/reject` | bearer | — | `JobStatusActionOut` | 404. Sets `Job.status = "REJECTED"` directly — a separate mechanism from `/applications/{id}/reject` below (hiding a job from the Dashboard isn't an application-workflow decision), not a stand-in for it anymore. Dashboard's "hide"/bulk-reject action. |
| POST | `/jobs/{job_id}/restore` | bearer | — | `JobStatusActionOut` | 404. Undoes reject — sets `Job.status` back to `"DISCOVERED"` |
| POST | `/jobs/{job_id}/analyze` | bearer | — | `JobDetailOut` | 404. Scores the job (`job_scorer`) against candidate skills/evidence/constraints, persists a new `JobAnalysis` row (additive — re-analyzing keeps history, doesn't replace), and updates `Job.status` to the resulting REJECT/READY_FOR_REVIEW/REVIEW_REQUIRED. Real Claude call — takes several seconds. |
| POST | `/jobs/{job_id}/documents` | bearer | `GenerateDocumentRequest` | `GeneratedDocumentOut` | 404 job not found, 422 bad `type`. Generates a tailored resume or cover letter, writes it to `.docx` under `documents_dir` (local filesystem path, not a downloadable URL — see "Known gaps"), and runs claim/ATS validation. **Get-or-creates the job's `Application` row** — this, not a separate action, is what makes `/applications/{id}/*` reachable for a job. Several real Claude calls — can take 20s+. `claim_check_passed`/`ats_check_passed` can come back `null` if that specific check itself failed to run (e.g. ATS check needs LibreOffice on `PATH`) — `null` is "didn't run", not "passed". |
| POST | `/jobs/{job_id}/documents/{document_id}/suggest-edit` | bearer | `SuggestDocumentEditRequest` | `DocumentEditSuggestionOut` | 404 job/document not found (document must belong to `job_id`). **Read-only** — one Claude call, no database write. Proposes a revision from free-text feedback; exactly one pair of `current_sections`/`proposed_sections` (resume) or `current_content`/`proposed_content` (cover letter) is set, matching the document's own type. |
| POST | `/jobs/{job_id}/documents/{document_id}/apply-edit` | bearer | `ApplyDocumentEditRequest` | `GeneratedDocumentOut` | 404 job/document not found, 422 if the wrong field (`sections` vs `content`) was sent for this document's type. **No Claude call** — persists exactly the `sections`/`content` sent (intended to be a prior suggest-edit response's `proposed_sections`/`proposed_content`, unmodified) as a new document version, re-running claim/ATS validation the same as a fresh generation. |
| POST | `/applications/{application_id}/approve` | bearer | — | `ApplicationActionOut` | 404 |
| POST | `/applications/{application_id}/reject` | bearer | — | `ApplicationActionOut` | 404 |
| POST | `/applications/{application_id}/open` | bearer | — | `ApplicationActionOut` | 404. Opens the posting URL **server-side** (`webbrowser.open`) — only meaningful when the frontend and API run on the same machine |
| POST | `/applications/{application_id}/mark-applied` | bearer | — | `ApplicationActionOut` | 404. The only route that sets status `APPLIED` |
| GET | `/explore/capabilities` | bearer | — | `Record<string, CapabilityMatrixOut>` keyed by MCP source name | — |
| POST | `/explore/search` | bearer | `ExploreSearchRequest` | `ExploreResultOut[]` | `filters.posted_within_days` (number) drops results older than that many days, applied after merging every source's results — works even for a source (e.g. HasData's Glassdoor tool) whose own search API has no date parameter. `filters.experience` (string) is passed through to whichever connected MCP tool has a matching param (`experience`/`seniority`/`years`) — see `GET /explore/capabilities`' `experience_filter` flag. |
| POST | `/explore/save` | bearer | `ExploreSaveRequest` | `ExploreSaveResponseOut` | **Shared save route** for every discovery source, not Explore-only — see route docstring. The only way a job from Explore, `/targets/search`, `/scrape/jobspy`, or AI Search enters `jobs` |
| GET | `/targets` | bearer | — | `CompanyTargetOut[]` | Configured Greenhouse/Lever targets from `data/companies.yaml` |
| POST | `/targets/search` | bearer | query: `experience?` (string, matched against title/description — targets have no structured experience facet to filter on upstream) | `ExploreResultOut[]` | Fetches every configured target — **does not insert**; save selected results via `POST /explore/save` |
| POST | `/scrape/jobspy` | bearer | `ScrapeJobspyRequest` | `ExploreResultOut[]` | Multi-site scrape (never `linkedin` — dropped server-side even if requested), up to ~90s — **does not insert**; save selected results via `POST /explore/save`. `experience` (string) is matched app-side against whichever of `job_level`/`experience_range` a given site returned (not every site has one) |
| POST | `/chat/message` | bearer | `ChatMessageRequest` | `ChatMessageResponse` | One structured Claude call extracts search filters + which source(s) to use (`explore`/`scrape`/`targets`) from the message; a second batches one-line JD summaries for whatever gets staged. Ready searches call the same Explore/Scrape/Targets functions the dedicated pages use and stage results server-side (`chat_search_results`, replaced wholesale per `session_id` on each new search) — nothing is inserted into `jobs` until a result is posted to `/explore/save` (a `ChatSearchResultOut` is a superset of `ExploreResultOut`'s fields). Can take several seconds to tens of seconds depending on which source(s) get picked. |
| GET | `/chat/results/{session_id}` | bearer | — | `ChatSearchResultOut[]` | Re-lists a session's currently staged results (e.g. after a page refresh) without another chat turn — no LLM call. |

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
JobListItemOut          { job_id: number, company: string, title: string, location: string, url: string, status: string, posted_at?: string, fit_score?: number, confidence?: string, strong_matches: any[], missing_skills: any[], risks: any[] }
JobDetailOut             = JobListItemOut & { description: string, application?: ApplicationOut }
GeneratedDocumentOut    { id: number, type: string, file_path: string, version: number, claim_check_passed?: boolean, ats_check_passed?: boolean }
ApplicationActionOut    { application_id: number, status: string }
JobStatusActionOut      { job_id: number, status: string }

ExploreSearchRequest    { query: string, filters?: object = {} }  // filters.posted_within_days?: number, filters.experience?: string
ExploreResultOut         { source: string, source_job_id: string, company: string, title: string, location: string, url: string, description: string, employment_type?: string, salary_min?: number, salary_max?: number, posted_at?: string }
ExploreSaveRequest       = ExploreResultOut  (same shape, posted back to /explore/save)
ExploreSaveResponseOut  { inserted: boolean }
CapabilityMatrixOut     { flags: Record<string, boolean>, required_filters: string[] }

CompanyTargetOut        { source: string, company: string, identifier: string }
ScrapeJobspyRequest     { search_term: string, location?: string, sites?: string[], results_wanted?: number = 50, experience?: string }

GenerateDocumentRequest { type: "resume" | "cover_letter" }

ResumeSectionOut        { section: string, content: string, evidence_ids_used: string[] }
SuggestDocumentEditRequest { feedback: string }
DocumentEditSuggestionOut { change_summary: string, current_sections?: ResumeSectionOut[], proposed_sections?: ResumeSectionOut[], current_content?: string, proposed_content?: string }
ApplyDocumentEditRequest { sections?: ResumeSectionOut[], content?: string }

ChatSearchResultOut      = ExploreResultOut & { id: number, summary?: string }  // id = staged-row id (see GET /chat/results); summary = one-line AI summary, batched per search
ChatMessageRequest      { session_id: string, message: string, known_filters?: object = {} }  // known_filters: pass back the prior turn's `filters` verbatim
ChatMessageResponse     { reply: string, filters: object, ready: boolean, results: ChatSearchResultOut[] }  // filters may include query/location/experience/posted_within_days/company/sources
```

## Known gaps the frontend needs to design around

- **No `tenant_id` on jobs/applications/documents.** Auth gates *who* can call these routes, not *which tenant's data* they see — every authenticated user currently sees every job. See `memory/known-gaps.md`.
- **Timestamps are ISO 8601 strings** in the JSON response (pydantic serializes `datetime` fields that way) — parse client-side, don't assume a specific format beyond ISO 8601.
- **No logout/refresh-token endpoint.** A token is valid until it expires (8h default, `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`); there's nothing server-side to invalidate it early.
- **`/applications/{id}/open` opens a browser tab on the API's host**, not the caller's — only correct when frontend dev/prod server and the API process share a machine.
- **`ExploreResultOut.posted_at` is approximate for HasData**, derived from an integer `ageInDays` HasData's Glassdoor tool returns (its API has no absolute date field at all) — "now minus N days", not the posting's real timestamp. Jobo's shape is unconfirmed (its MCP auth is currently broken — see `memory/known-gaps.md`). Either way, `posted_at` can be `null` when no date info was derivable — don't assume every result has one.
- **An `Application` row is only created by `POST /jobs/{job_id}/documents`** (as of contract v6 — previously nothing created one at all, so every `/applications/{id}/*` route was unreachable). `job.application` in `JobDetailOut` is still `null` until that job's first document has been generated; don't call `/applications/{id}/*` before then. `/jobs/{id}/reject`/`/jobs/{id}/restore` remain a separate mechanism (hiding a job from the Dashboard is not an application-workflow decision), not a stand-in for a missing one anymore.
- **Generated documents are written to a local filesystem path, not served over HTTP.** `GeneratedDocumentOut.file_path` is a path on the machine running the API (`documents_dir` setting, default `data/generated_documents/`) — there is no download route. Consistent with this being a local-first tool (frontend and API on the same machine); don't build a "download" button that fetches `file_path` as a URL, it isn't one.
- **`claim_check_passed`/`ats_check_passed` can be `null` even after a document is generated** — that means the check itself didn't complete (e.g. the ATS check needs LibreOffice's `soffice` on `PATH`, which may not be installed), not that it passed. Only `true` means passed; render `null` distinctly from both `true` and `false`.
