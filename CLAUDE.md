# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

`just --list` (or read the `Justfile`) is the source of truth for recipes; all run via `uv`. Do not call `pytest`/`ruff` directly — use `just`.

- `just test [args]` runs pytest **without** coverage; extra args pass through (e.g. `just test tests/test_routes.py -k test_name`).
- The 100% coverage gate lives in `just test-ci` (line) and `just test-branch` (branch) — not in `just test`.
- `just lint` auto-fixes; `just lint-ci` is the non-fixing CI check (also validates planning bundles).
- `just check-planning` validates planning bundles; `just index` prints the change listing.

## Architecture

> Authoritative, code-current capability prose lives in [`architecture/`](architecture/) — one file per capability. **When a change alters a capability's behavior, update the matching `architecture/<capability>.md` in the same PR** — that promotion is what keeps `architecture/` true. The summary below is quick orientation only.

This is a single-module library (`modern_di_litestar/main.py`) that integrates [modern-di](https://github.com/modern-python/modern-di) with Litestar.

**Key concepts:**

- `ModernDIPlugin` — a Litestar `InitPlugin` that wires a `modern_di.Container` into Litestar's lifecycle. Accepts an optional `autowired_groups` list of `modern_di.Group` subclasses; their providers are auto-registered as app-level Litestar dependencies keyed by attribute name.
- `FromDI(provider)` — returns a Litestar `Provide` that resolves a provider from the request-scoped DI container. Accepts either an `AbstractProvider` instance or a type.
- `build_di_container` — a Litestar dependency that creates a child `Container` per request/websocket, scoped to `REQUEST` or `SESSION` respectively, and tears it down after the response.
- `litestar_request_provider` / `litestar_websocket_provider` — `ContextProvider` instances that make the raw Litestar `Request` / `WebSocket` objects resolvable via DI.
- `fetch_di_container(app)` — retrieves the app-level container from `app.state`.

**Data flow:** App startup → `ModernDIPlugin.on_app_init` stores the root container in `app.state` → each request, `build_di_container` creates a child container with the request/websocket bound → `FromDI` callables resolve from that child container → child container closed on response teardown.

**Type annotation:** Use `ty: ignore` for type suppression (not `# type: ignore`).

## Workflow

Planning uses a portable two-axis convention — `architecture/` (repo root) is
the living **truth home** and promotion target; `planning/changes/` holds the
per-change bundles. **Start at the
[Quick path](planning/README.md#quick-path-start-here)** in `planning/README.md`
to choose a lane, create a bundle, and ship — that file is the authoritative
spec. Run `just check-planning` to validate bundles and `just index` to print
the change listing.
