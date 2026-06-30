# modern-di-litestar

[![PyPI version](https://img.shields.io/pypi/v/modern-di-litestar.svg)](https://pypi.org/project/modern-di-litestar/)
[![Supported Python versions](https://img.shields.io/pypi/pyversions/modern-di-litestar.svg)](https://pypi.org/project/modern-di-litestar/)
[![Downloads](https://static.pepy.tech/badge/modern-di-litestar/month)](https://pepy.tech/projects/modern-di-litestar)
[![Coverage](https://img.shields.io/badge/coverage-100%25-brightgreen.svg)](https://github.com/modern-python/modern-di-litestar/actions/workflows/ci.yml)
[![CI](https://github.com/modern-python/modern-di-litestar/actions/workflows/ci.yml/badge.svg)](https://github.com/modern-python/modern-di-litestar/actions/workflows/ci.yml)
[![License](https://img.shields.io/github/license/modern-python/modern-di-litestar.svg)](https://github.com/modern-python/modern-di-litestar/blob/main/LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/modern-python/modern-di-litestar)](https://github.com/modern-python/modern-di-litestar/stargazers)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![ty](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ty/main/assets/badge/v0.json)](https://github.com/astral-sh/ty)

[Modern-DI](https://github.com/modern-python/modern-di) integration for [Litestar](https://litestar.dev).

Usage example: [litestar-sqlalchemy-template](https://github.com/modern-python/litestar-sqlalchemy-template)

## Installation

```bash
uv add modern-di-litestar      # or: pip install modern-di-litestar
```

## Usage

### 1. Define providers

```python
import dataclasses
from modern_di import Group, Scope, providers


@dataclasses.dataclass(kw_only=True)
class Database:
    url: str


@dataclasses.dataclass(kw_only=True)
class UserRepository:
    db: Database


class AppDependencies(Group):
    database = providers.Factory(creator=Database, kwargs={"url": "sqlite:///app.db"})
    user_repo = providers.Factory(scope=Scope.REQUEST, creator=UserRepository, bound_type=None)
```

### 2. Wire the plugin

```python
import litestar
from modern_di import Container
from modern_di_litestar import ModernDIPlugin

groups = [AppDependencies]

app = litestar.Litestar(
    plugins=[ModernDIPlugin(Container(groups=groups), autowired_groups=groups)],
)
```

Passing `autowired_groups` to `ModernDIPlugin` auto-registers each provider as a Litestar dependency keyed by its attribute name (`database`, `user_repo`), so routes can declare them directly as parameters.

### 3. Inject into routes

**Using `FromDI` (explicit, per-route)**

```python
from modern_di_litestar import FromDI

@litestar.get(
    "/users",
    dependencies={"repo": FromDI(AppDependencies.user_repo)},
)
async def list_users(repo: UserRepository) -> list[str]:
    ...
```

`FromDI` accepts either a provider instance (`AppDependencies.user_repo`) or a type (`UserRepository`).

**Using auto-wired group names (implicit)**

When `autowired_groups` is passed to `ModernDIPlugin`, provider names become available as route parameters directly:

```python
@litestar.get("/users")
async def list_users(user_repo: UserRepository) -> list[str]:
    ...
```

### 4. Access the raw request or websocket via DI

```python
from modern_di_litestar import litestar_request_provider, litestar_websocket_provider

class AppDependencies(Group):
    ...
    request_method = providers.Factory(
        scope=Scope.REQUEST,
        creator=lambda request: request.method,
        bound_type=None,
    )
```

`litestar_request_provider` and `litestar_websocket_provider` are pre-built `ContextProvider` instances that make the current `Request` / `WebSocket` objects resolvable within DI.

### 5. Sub-request (action) scopes

For work that should live shorter than a request, build a child container inside a route:

```python
@litestar.get("/")
async def handler(di_container: Container) -> None:
    action_container = di_container.build_child_container()
    result = action_container.resolve_provider(AppDependencies.some_action_scoped_factory)
```

### 6. Retrieve the app-level container

```python
from modern_di_litestar import fetch_di_container

container = fetch_di_container(app)
```

## API

| Symbol | Description |
|---|---|
| `ModernDIPlugin(container, autowired_groups=None)` | Litestar `InitPlugin` — wires the DI container into app lifecycle |
| `FromDI(provider)` | Returns a Litestar `Provide` that resolves a provider per request |
| `litestar_request_provider` | `ContextProvider` for the current `litestar.Request` |
| `litestar_websocket_provider` | `ContextProvider` for the current `litestar.WebSocket` |
| `fetch_di_container(app)` | Retrieves the root container from `app.state` |
| `build_di_container` | Litestar dependency (registered as `di_container`) — yields a scoped child container per request |

## 📦 [PyPI](https://pypi.org/project/modern-di-litestar)

## 📝 [License](LICENSE)

## Part of `modern-python`

Built on [`modern-di`](https://github.com/modern-python/modern-di), a dependency-injection framework with IoC container and scopes.

Browse the full list of templates and libraries in
[`modern-python`](https://github.com/modern-python) — see the org profile for the categorized index.
