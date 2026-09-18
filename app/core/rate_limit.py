"""
Login rate limiting (audit finding F6 — `/auth/login` had none). Built on
`pyrate-limiter` rather than hand-rolled bookkeeping.

One thing this needed that isn't the library's default: `Limiter(Rate(...))`
alone wraps the rate in a `SingleBucketFactory` — ONE shared bucket for
every key, verified directly (two independent keys exhausted each other's
budget). `_KeyedBucketFactory` below creates one `InMemoryBucket` per key
instead, which is the documented extension point for this, not an
undocumented library bug.

Design choice: every login attempt (successful or failed) consumes a slot,
not just failures. pyrate-limiter has no non-consuming "peek" — checking
whether a key is currently limited without also counting that check as an
attempt isn't possible — so "only count failures, reset the budget on
success" isn't cleanly expressible here. Counting every attempt is simpler
and still closes the brute-force gap the audit flagged; the only cost is a
legitimate user who mistypes their password a few times has less budget
left over for a subsequent real login shortly after.

In-memory bucket — single-process, no external dependency. Fine for this
app's actual deployment model (a local-first tool, one `uvicorn` process);
would need `RedisBucket`/`PostgresBucket` (both ship with this library) if
this ever ran as multiple workers.
"""

import time

from pyrate_limiter import BucketFactory, Duration, InMemoryBucket, Limiter, Rate, RateItem

MAX_ATTEMPTS = 5
WINDOW_SECONDS = 300  # 5 minutes

_RATE = Rate(MAX_ATTEMPTS, Duration.SECOND * WINDOW_SECONDS)


class _KeyedBucketFactory(BucketFactory):
    """One InMemoryBucket per distinct key, created lazily on first use."""

    def __init__(self, rates: list[Rate]) -> None:
        self._rates = rates
        self._buckets: dict[str, InMemoryBucket] = {}

    def wrap_item(self, name: str, weight: int = 1) -> RateItem:
        return RateItem(name, time.time() * 1000, weight=weight)

    def get(self, item: RateItem) -> InMemoryBucket:
        bucket = self._buckets.get(item.name)
        if bucket is None:
            bucket = self.create(InMemoryBucket, self._rates)
            self._buckets[item.name] = bucket
        return bucket


_limiter = Limiter(_KeyedBucketFactory([_RATE]))


def is_allowed(key: str) -> bool:
    """True if `key` (e.g. "<client-ip>:<email>") has an attempt slot
    available in the current window; consumes one if so. Non-blocking —
    never sleeps/waits inside a request handler, just reports whether a
    slot was available right now."""
    return _limiter.try_acquire(key, blocking=False)


def reset_all_for_tests() -> None:
    """Test-only: wipe every key's bucket. `TestClient` always reports the
    same client host ("testclient"), so a test that deliberately trips the
    429 for one key would otherwise leak into every later test's login
    attempts for the rest of the pytest session — see test_api_auth.py's
    `auth_client` fixture."""
    global _limiter
    _limiter = Limiter(_KeyedBucketFactory([_RATE]))
