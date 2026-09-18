# Backend Engineering Standard

This is the mandatory engineering standard for every backend change in this
repository. Re-read the relevant sections before starting any backend
coding task — not just once at the start of a session.

Priority order when these principles conflict:

**Correctness → Security → Reliability → Maintainability → Observability → Performance.**

Optimize for predictable production behavior, not for the amount of code
written. Preserve working patterns unless there's a concrete technical
reason to change them — don't replace architecture because you'd prefer
a different one.

## 1. Audit mindset

Judge code on: correctness, security, reliability, maintainability,
scalability, performance, observability, testability, API consistency,
database correctness, concurrency behavior, failure behavior, backward
compatibility. Not just "does it work."

## 2. Endpoints and parameters

For every endpoint: verify method, path, path/query params, headers,
auth, authorization, request body, response model, status codes.

For every parameter: name, type, optional/required, default, `None`
behavior, validation (min/max, length, regex, format, enum), whether
it's actually used, whether the default makes sense, whether it should
exist at all. Flag: unused params, mutable defaults, missing validation,
wrong `Optional` usage, duplicate/inconsistent naming, missing
cross-field validation.

## 3. Pydantic schemas

Required vs optional, defaults, `None` semantics, field constraints,
nested schemas, validators, enums, serialization, ORM conversion
(`from_attributes`), response filtering, sensitive-field exposure.
Invalid client data must never silently reach business logic.

## 4. Async correctness

No blocking calls (`requests`, sync file I/O, sync DB calls, subprocess,
heavy CPU work, sync third-party SDKs) inside an `async def` request
path without deliberately offloading them (threadpool/background task).
Don't convert sync code to async reflexively — use the correct execution
model for what the code actually does. Check for task leaks, race
conditions, shared mutable state, missing timeouts/cancellation.

## 5. Database

Engine creation, connection pooling, session lifecycle, transaction
boundaries, commit/rollback correctness, connection leaks, async/sync
consistency, N+1 queries, missing eager/lazy-load control, missing
indexes/unique constraints/FKs, pagination, locking, race conditions,
migration safety. For important queries, know: how many DB round-trips
per request, and what happens at 10x/100x/1000x the current row count.

## 6. Transactions

For every write: where it starts, where it commits, rollback behavior on
exception, duplicate-request behavior, retry behavior, partial-failure
behavior, whether external API calls happen inside the transaction.
Writes that should be idempotent must actually be idempotent.

## 7. AuthN/AuthZ

Login, tokens, expiration, password hashing, roles, permissions,
resource ownership. For every protected endpoint: can one user reach
another user's resource by changing an ID/parameter (IDOR/BOLA)? Check
for privilege escalation, inconsistent role checks, auth bypass,
unintentionally-unprotected internal endpoints.

## 8. Security

SQL/command injection, SSRF, path traversal, insecure file upload,
unsafe deserialization, secret/token leakage, weak auth, insecure CORS,
debug mode left on, insecure cookies, dangerous dynamic SQL, sensitive
data in logs. Never let secrets reach logs or API responses.

## 9. External API calls

Connect/read/total timeouts, retry policy (bounded, with backoff+jitter,
never infinite), idempotency before retrying, rate-limit handling,
connection pooling, response validation, failure mapping, dependency
outage behavior. Never blindly retry non-idempotent operations.

## 10. Error handling

No bare `except Exception` that swallows a real failure silently. Every
`try/except` should map to the right status code and not leak stack
traces. Distinguish validation failure, auth failure, authz failure, not
found, conflict, business-rule failure, external-service failure,
timeout, internal error — each should look different to the caller.

## 11. Performance

DB round-trips, network calls, loops doing redundant work, large JSON
payloads, repeated calculations, caching, connection pooling,
pagination. Every performance recommendation must explain the actual
bottleneck mechanism, not just assert something is slow.

## 12. API design consistency

URL naming, REST resource structure, HTTP verbs, status codes,
pagination/filtering/sorting conventions, error shape, versioning,
idempotency. Match the project's existing convention rather than
introducing a new one without a documented reason.

## 13. Logging and observability

Structured logs that can answer: what happened, which request, which
user, where it failed, why, how long it took. Request/correlation IDs
where they matter. Never log credentials, tokens, passwords, or private
keys.

## 14. Testing

Every important endpoint needs meaningful success *and* failure-path
coverage, including boundary conditions. Prefer tests against real
(if disposable) infrastructure over hand-mocked query chains where
practical — a mock only proves a function was called with the right
args, never that the SQL/logic was actually correct.

## 15. Dependencies

Check `requirements.txt`/lockfiles/Dockerfile for incompatible versions,
deprecated APIs, unnecessary deps, unbounded version ranges. Don't
upgrade packages as a side effect of an unrelated task.

## 16. Deployment

Docker image, startup command, worker config, graceful shutdown/signals,
env/secrets handling, health checks, resource use, restart behavior,
debug settings that must never run in production.

## 17. Code-level review

Function signatures, type hints, return values, error handling, side
effects, global state, duplicated logic, dead code, naming. No cosmetic
refactors for style alone.

---

## Before any future backend code change

1. Re-read the relevant section(s) of this file.
2. Re-inspect the affected code (don't rely on memory of an earlier read).
3. Identify dependencies and downstream effects of the change.
4. Make the smallest correct change.
5. Validate all parameters at the boundary.
6. Check error handling.
7. Check security implications.
8. Check database behavior (queries, transactions, migrations).
9. Check async/concurrency behavior.
10. Add or update tests.
11. Actually run the relevant tests/checks — never claim they passed without running them.
12. Review the final diff before calling the change done.

Never claim an issue is fixed without verifying the affected behavior.
