---
summary: Single-source the connection→scope mapping — build_di_container derives each child container's scope from the ContextProviders instead of repeating the Request↔REQUEST / WebSocket↔SESSION literals; collapse the redundant Scope import.
---

# Change: Single-source the connection→scope mapping

**Lane:** lightweight — ≲30 LOC net, ≤2 files, no new file, no public-API
change, a single straightforward test. If it outgrows this, split into
`design.md` + `plan.md`.

## Goal

The Request↔REQUEST / WebSocket↔SESSION pairing is written twice: in the two
module-level `ContextProvider`s (`litestar_request_provider`,
`litestar_websocket_provider`) and again, hardcoded, in `build_di_container`'s
`isinstance` branch. The two must agree — the scope a connection's child
container is built at has to match the scope its `ContextProvider` reads from —
but nothing enforces it, so they can drift. Derive the scope in
`build_di_container` from the providers so the pairing lives in exactly one
place. (Same drift hazard `modern-di-faststream` already eliminated by naming
its shared container keys — applied here to the scope mapping.)

This is candidate 2 from the session's architecture review (`Worth exploring`),
shaped lightweight per that review and the FastStream precedent. `Option A`:
no new types, no upstream change. `modern-di-fastapi` carries the identical
pattern — a fast-follow, not in scope here.

## Approach

`build_di_container` keeps its `isinstance(request, WebSocket)` branch (the
`else` still defaults non-WebSocket connections to Request/REQUEST), but takes
`scope` from `litestar_websocket_provider.scope` / `litestar_request_provider.scope`
(`AbstractProvider.scope` is public) rather than the `DIScope.SESSION` /
`DIScope.REQUEST` literals. The scope pairing then has one home: the
`ContextProvider` definitions. Also collapse the redundant double import
(`from modern_di.scope import Scope` + `... as DIScope`) into the existing
`from modern_di import Container, Group, Scope, providers` line — matching
`modern-di-fastapi`'s import style.

No behavior change: the scopes produced are identical, so the end-to-end
context resolution is unchanged. No `architecture/` capability contract moves.

### Before / after (`build_di_container`)

```python
# before
    context: dict[type[typing.Any], typing.Any] = {}
    scope: DIScope | None
    if isinstance(request, litestar.WebSocket):
        context[litestar.WebSocket] = request
        scope = DIScope.SESSION
    else:
        context[litestar.Request] = request
        scope = DIScope.REQUEST

# after
    context: dict[type[typing.Any], typing.Any]
    if isinstance(request, litestar.WebSocket):
        context = {litestar.WebSocket: request}
        scope = litestar_websocket_provider.scope
    else:
        context = {litestar.Request: request}
        scope = litestar_request_provider.scope
```

## Files

- `modern_di_litestar/main.py` — derive `scope` from the providers in
  `build_di_container`; consolidate the `Scope` import (drop the two
  `from modern_di.scope import Scope` / `as DIScope` lines).

## Why no new test

Behavior is unchanged and drift is now eliminated *by construction* (the scope
is read from the provider, not restated), so there is nothing new to assert.
The existing integration tests already prove the mapping end-to-end —
`test_context_provider` resolves `request.method` at REQUEST scope and
`test_context_adapter` resolves `websocket.url.path` at SESSION scope — and both
`build_di_container` branches stay covered (HTTP via `test_routes`, WebSocket
via `test_websockets`), so the 100% line gate holds.

## Verification

- [x] `just lint-ci` — clean (ruff, `ty`, planning validator). The derived-scope
  inference type-checks; the consolidated `Scope` import is used by the
  `ContextProvider` definitions.
- [x] `just test-ci` — 14 passed, 100% line coverage (both branches covered).
- [ ] `just check-planning` — `planning: OK` (run in the final gate before PR).
