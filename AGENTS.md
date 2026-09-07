# AGENTS.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`modern-di-litestar` is a [Litestar](https://litestar.dev) integration for
[`modern-di`](https://github.com/modern-python/modern-di); [`CONTEXT.md`](CONTEXT.md) opens with
what it does and owns the vocabulary — read it before naming a concept in code, a test name, or an
issue title. It is one of that project's integrations, each of which lives in a separate repository
and ships as a separate PyPI package.

## Commands

`just` (task runner) and `uv` (package manager). The [`justfile`](justfile) is the source of truth —
`just --list`, or read it; never invoke `pytest` or `ruff` directly. The one thing it does not say:
a `ty` suppression is written `# ty: ignore`, never `# type: ignore`.

## Architecture

All implementation is `modern_di_litestar/main.py`, short enough to read whole. Read it.

### Testing patterns

`tests/dependencies.py` is the fixture model every test builds on: one `Group` spanning APP,
SESSION, REQUEST and ACTION scopes, plus two creators that read the live `Request`/`WebSocket`.
Behaviour is exercised end to end through Litestar's own `TestClient`: a test defines a handler,
registers it on the `app` fixture from `tests/conftest.py`, and calls it.

## Workflow

Real work **not scheduled** becomes a GitHub issue.

Every link in `README.md` must be absolute: `https://github.com/modern-python/<repo>/blob/main/<path>`,
or `.../tree/main/<path>` for a directory. Never a relative path: `README.md` is also the PyPI long
description, and PyPI does not rewrite relative links, so a relative one 404s on the package page.

An invariant is a test whose name is the claim, with a docstring opening `INVARIANT:` and a second
paragraph naming **what breaks it** — design rationale, not a report of what this one test catches.
