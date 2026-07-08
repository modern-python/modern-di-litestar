---
summary: Add direct unit tests for _Dependency.__call__'s provider-vs-type dispatch, pinning the FromDI seam without a TestClient round-trip.
---

# Change: Direct tests for the `FromDI` dispatch seam

**Lane:** lightweight — ≲30 LOC net, ≤2 files, no new file, no public-API
change, a single straightforward test. If it outgrows this, split into
`design.md` + `plan.md`.

## Goal

`_Dependency.__call__` (behind `FromDI`) dispatches on whether its argument is
an `AbstractProvider` (→ `resolve_provider`) or a type (→ `resolve` by type).
Both branches are exercised today only through full Litestar `TestClient`
round-trips. Add focused unit tests that hit the seam directly, so the
dispatch contract is pinned and fast to test. No behavior change — coverage is
already 100%; this deepens the *test surface*, not the code.

## Approach

Build a `Container(groups=[Dependencies])`, enter it, and call
`_Dependency(...)` directly with a request-scoped child container — once with a
provider (`Dependencies.app_factory`) and once with a type (`SimpleCreator`) —
asserting each resolves. The seam is `_Dependency` in
`modern_di_litestar/main.py`; no capability contract moves, so
`architecture/` is untouched.

## Files

- `tests/test_routes.py` — two `async` unit tests added; imports extended with
  `Scope` and `_Dependency`.

## Verification

- [ ] Both tests pass (the behavior already exists; these pin it directly) —
  `just test tests/test_routes.py -k dependency -v`.
- [ ] `just test-ci` — full suite green at 100% line coverage.
- [ ] `just lint-ci` — clean (incl. planning validator).
