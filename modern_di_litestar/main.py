import contextlib
import dataclasses
import typing
import warnings

import litestar
from litestar.config.app import AppConfig
from litestar.di import NamedDependency, Provide
from litestar.params import SkipValidation
from litestar.plugins import InitPlugin
from modern_di import Container, Group, Scope, providers


T_co = typing.TypeVar("T_co", covariant=True)


litestar_request_provider = providers.ContextProvider(scope=Scope.REQUEST, context_type=litestar.Request)
litestar_websocket_provider = providers.ContextProvider(scope=Scope.SESSION, context_type=litestar.WebSocket)

# The single source of the connection-kind mapping. Each provider pairs a connection
# type (``context_type``) with the scope its child container opens at; the plugin
# registers them and ``build_di_container`` dispatches off them. Add a connection
# kind by adding its provider here — nothing else changes.
_CONNECTION_PROVIDERS = (litestar_request_provider, litestar_websocket_provider)


def fetch_di_container(app_: litestar.Litestar) -> Container:
    return typing.cast(Container, app_.state.di_container)


@contextlib.asynccontextmanager
async def _lifespan_manager(app_: litestar.Litestar) -> typing.AsyncIterator[None]:
    # ``async with`` reopens the root container on each startup (``__aenter__``)
    # and closes it on shutdown, so a second lifespan cycle against the same
    # container works instead of raising ContainerClosedError.
    async with fetch_di_container(app_):
        yield


def _autowired_dependencies(groups: list[type[Group]], *, existing: typing.Iterable[str] = ()) -> dict[str, Provide]:
    result: dict[str, Provide] = {}
    seen: set[str] = set(existing)
    for group in groups:
        for name, provider in group.get_named_providers().items():
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
    __slots__ = ("container", "groups")

    def __init__(self, container: Container, autowired_groups: list[type[Group]] | None = None) -> None:
        self.container = container
        self.groups = autowired_groups or []

    def on_app_init(self, app_config: AppConfig) -> AppConfig:
        self.container.add_providers(*_CONNECTION_PROVIDERS)
        app_config.state.di_container = self.container
        app_config.dependencies["di_container"] = Provide(build_di_container)
        app_config.dependencies.update(_autowired_dependencies(self.groups, existing=app_config.dependencies))
        app_config.lifespan.append(_lifespan_manager)
        return app_config


async def build_di_container(
    request: litestar.Request[typing.Any, typing.Any, typing.Any],
) -> typing.AsyncIterator[Container]:
    context: dict[type[typing.Any], typing.Any] = {}
    scope = None
    for provider in _CONNECTION_PROVIDERS:
        if isinstance(request, provider.context_type):
            context[provider.context_type] = request
            scope = provider.scope
            break
    container = fetch_di_container(request.app).build_child_container(context=context, scope=scope)
    try:
        yield container
    finally:
        await container.close_async()


@dataclasses.dataclass(slots=True, frozen=True)
class _Dependency(typing.Generic[T_co]):
    dependency: providers.AbstractProvider[T_co] | type[T_co]

    async def __call__(self, di_container: NamedDependency[SkipValidation[Container]]) -> T_co:
        return di_container.resolve_dependency(self.dependency)


def FromDI(dependency: providers.AbstractProvider[T_co] | type[T_co]) -> Provide:  # noqa: N802
    return Provide(dependency=_Dependency(dependency), use_cache=False)
