import collections.abc
import contextlib
import dataclasses
import logging
import typing
import warnings

import anyio
import litestar
from litestar.config.app import AppConfig
from litestar.connection import ASGIConnection
from litestar.di import NamedDependency, Provide
from litestar.exceptions import ImproperlyConfiguredException
from litestar.params import SkipValidation
from litestar.plugins import InitPlugin
from modern_di import Container, Group, Scope, integrations, providers


T_co = typing.TypeVar("T_co", covariant=True)

_DI_CONTAINER_DEPENDENCY = "di_container"


litestar_request_provider = providers.ContextProvider(scope=Scope.REQUEST, context_type=litestar.Request)
litestar_websocket_provider = providers.ContextProvider(scope=Scope.SESSION, context_type=litestar.WebSocket)

# The single source of the connection-kind mapping. Each provider pairs a connection
# type (``context_type``) with the scope its child container opens at; the plugin
# registers them and ``build_di_container`` dispatches off them. Add a connection
# kind by adding its provider here — nothing else changes.
_CONNECTION_PROVIDERS = (litestar_request_provider, litestar_websocket_provider)
_CHILD_CLOSE_TIMEOUT = 10.0
_logger = logging.getLogger(__name__)


def fetch_di_container(app_: litestar.Litestar) -> Container:
    return typing.cast(Container, app_.state.di_container)


@contextlib.asynccontextmanager
async def _open_root(app_: litestar.Litestar) -> collections.abc.AsyncGenerator[None]:
    fetch_di_container(app_).open()
    # Closed by _close_root, an on_shutdown hook, which Litestar runs after every lifespan manager exits.
    yield


async def _close_root(app_: litestar.Litestar) -> None:
    await fetch_di_container(app_).close_async()


def _autowired_dependencies(groups: list[type[Group]], *, existing: typing.Iterable[str] = ()) -> dict[str, Provide]:
    result: dict[str, Provide] = {}
    seen: set[str] = set(existing)
    for group in groups:
        for name, provider in group.get_named_providers().items():
            if name == _DI_CONTAINER_DEPENDENCY:
                msg = (
                    f"Group {group.__name__!r} declares a provider named {name!r}, "
                    "which is reserved by ModernDIPlugin for its own dependency; rename the provider."
                )
                raise ImproperlyConfiguredException(msg)
            if name in seen:
                # stacklevel=3: warn -> _autowired_dependencies -> on_app_init -> caller,
                # matching the attribution of the original in-place warning in on_app_init.
                warnings.warn(
                    f"Duplicate dependency name '{name}' from group {group.__name__!r}; overwriting.",
                    stacklevel=3,
                )
            seen.add(name)
            result[name] = FromDI(provider)
    return result


class ModernDIPlugin(InitPlugin):
    __slots__ = ("container", "groups", "manage_lifespan")

    def __init__(
        self,
        container: Container,
        autowired_groups: list[type[Group]] | None = None,
        *,
        manage_lifespan: bool = True,
    ) -> None:
        self.container = container
        self.groups = autowired_groups or []
        self.manage_lifespan = manage_lifespan

    def on_app_init(self, app_config: AppConfig) -> AppConfig:
        if _DI_CONTAINER_DEPENDENCY in app_config.dependencies:
            msg = (
                f"The app already has a dependency named {_DI_CONTAINER_DEPENDENCY!r}, "
                "which is reserved by ModernDIPlugin for its own dependency; rename the dependency."
            )
            raise ImproperlyConfiguredException(msg)
        self.container.add_providers(*_CONNECTION_PROVIDERS)
        app_config.state.di_container = self.container
        app_config.dependencies[_DI_CONTAINER_DEPENDENCY] = Provide(build_di_container)
        app_config.dependencies.update(_autowired_dependencies(self.groups, existing=app_config.dependencies))
        if self.manage_lifespan:
            app_config.lifespan.insert(0, _open_root)
            app_config.on_shutdown.append(_close_root)
        return app_config


async def build_di_container(
    request: ASGIConnection[typing.Any, typing.Any, typing.Any, typing.Any],
) -> typing.AsyncIterator[Container]:
    match = integrations.classify_connection(request, _CONNECTION_PROVIDERS)
    container = fetch_di_container(request.app).build_child_container(
        scope=match.scope if match else None,
        context=match.context if match else None,
    )
    try:
        yield container
    finally:
        with anyio.move_on_after(_CHILD_CLOSE_TIMEOUT, shield=True) as close_scope:
            await container.close_async()
        if close_scope.cancel_called:
            _logger.warning(
                "Closing the child container did not finish within %s s; its remaining finalizers did not run",
                _CHILD_CLOSE_TIMEOUT,
            )


@dataclasses.dataclass(slots=True, frozen=True)
class _Dependency(typing.Generic[T_co]):
    marker: integrations.Marker[T_co]

    async def __call__(self, di_container: NamedDependency[SkipValidation[Container]]) -> T_co:
        return self.marker.resolve(di_container)


def FromDI(dependency: providers.AbstractProvider[T_co] | type[T_co]) -> Provide:  # noqa: N802
    return Provide(dependency=_Dependency(integrations.Marker(dependency)), use_cache=False)
