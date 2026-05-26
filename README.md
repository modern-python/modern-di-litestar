"Modern-DI-LiteStar"
==
[![Test Coverage](https://codecov.io/gh/modern-python/modern-di-litestar/branch/main/graph/badge.svg)](https://codecov.io/gh/modern-python/modern-di-litestar)
[![Supported versions](https://img.shields.io/pypi/pyversions/modern-di-litestar.svg)](https://pypi.python.org/pypi/modern-di-litestar)
[![downloads](https://img.shields.io/pypi/dm/modern-di-litestar.svg)](https://pypistats.org/packages/modern-di-litestar)
[![GitHub stars](https://img.shields.io/github/stars/modern-python/modern-di-litestar)](https://github.com/modern-python/modern-di-litestar/stargazers)

Integration of [Modern-DI](https://github.com/modern-python/modern-di) with [Litestar](https://litestar.dev).

Usage example: [litestar-sqlalchemy-template](https://github.com/modern-python/litestar-sqlalchemy-template)

## Part of `modern-python`

Browse the full list of templates and libraries in
[`modern-python`](https://github.com/modern-python) — see the org profile for the
categorized index.

## 📚 [Documentation](https://modern-di.readthedocs.io)

## Installation

```bash
pip install modern-di-litestar
```

## Quick start

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

## Public API

| Symbol | Description |
|---|---|
| `ModernDIPlugin(container, autowired_groups=None)` | Litestar `InitPlugin` — wires the DI container into app lifecycle |
| `FromDI(provider)` | Returns a Litestar `Provide` that resolves a provider per request |
| `litestar_request_provider` | `ContextProvider` for the current `litestar.Request` |
| `litestar_websocket_provider` | `ContextProvider` for the current `litestar.WebSocket` |
| `fetch_di_container(app)` | Retrieves the root container from `app.state` |
| `build_di_container` | Internal Litestar dependency — creates a scoped child container per request |
