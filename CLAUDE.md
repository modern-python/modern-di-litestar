# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
just test                        # run tests with coverage
just test tests/test_routes.py   # run a single test file
just test -k test_name           # run a single test by name
just lint                        # format + lint + type-check
just lint-ci                     # lint without auto-fixing (CI mode)
```

All commands use `uv` under the hood. Do not call `pytest` or `ruff` directly — use `just`.

## Architecture

This is a single-module library (`modern_di_litestar/main.py`) that integrates [modern-di](https://github.com/modern-python/modern-di) with Litestar.

**Key concepts:**

- `ModernDIPlugin` — a Litestar `InitPlugin` that wires a `modern_di.Container` into Litestar's lifecycle. Accepts an optional `autowired_groups` list of `modern_di.Group` subclasses; their providers are auto-registered as app-level Litestar dependencies keyed by attribute name.
- `FromDI(provider)` — returns a Litestar `Provide` that resolves a provider from the request-scoped DI container. Accepts either an `AbstractProvider` instance or a type.
- `build_di_container` — a Litestar dependency that creates a child `Container` per request/websocket, scoped to `REQUEST` or `SESSION` respectively, and tears it down after the response.
- `litestar_request_provider` / `litestar_websocket_provider` — `ContextProvider` instances that make the raw Litestar `Request` / `WebSocket` objects resolvable via DI.
- `fetch_di_container(app)` — retrieves the app-level container from `app.state`.

**Data flow:** App startup → `ModernDIPlugin.on_app_init` stores the root container in `app.state` → each request, `build_di_container` creates a child container with the request/websocket bound → `FromDI` callables resolve from that child container → child container closed on response teardown.

**Type annotation:** Use `ty: ignore` for type suppression (not `# type: ignore`).
