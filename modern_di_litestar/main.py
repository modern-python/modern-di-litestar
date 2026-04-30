import contextlib
import dataclasses
import typing
import warnings

import litestar
from litestar.config.app import AppConfig
from litestar.di import Provide
from litestar.params import Dependency
from litestar.plugins import InitPlugin
from modern_di import Container, Group, providers
from modern_di.scope import Scope
from modern_di.scope import Scope as DIScope


T_co = typing.TypeVar("T_co", covariant=True)


litestar_request_provider = providers.ContextProvider(scope=Scope.REQUEST, context_type=litestar.Request)
litestar_websocket_provider = providers.ContextProvider(scope=Scope.SESSION, context_type=litestar.WebSocket)


def fetch_di_container(app_: litestar.Litestar) -> Container:
    return typing.cast(Container, app_.state.di_container)


@contextlib.asynccontextmanager
async def _lifespan_manager(app_: litestar.Litestar) -> typing.AsyncIterator[None]:
    container = fetch_di_container(app_)
    try:
        yield
    finally:
        await container.close_async()


class ModernDIPlugin(InitPlugin):
    __slots__ = ("container", "groups")

    def __init__(self, container: Container, autowired_groups: list[type[Group]] | None = None) -> None:
        self.container = container
        self.groups = autowired_groups or []

    def on_app_init(self, app_config: AppConfig) -> AppConfig:
        self.container.providers_registry.add_providers(litestar_request_provider, litestar_websocket_provider)
        app_config.state.di_container = self.container
        app_config.dependencies["di_container"] = Provide(build_di_container)
        for group in self.groups:
            name_by_provider_id = {
                id(v): k for k, v in group.__dict__.items() if isinstance(v, providers.AbstractProvider)
            }
            for provider in group.get_providers():
                name = name_by_provider_id[id(provider)]
                if name in app_config.dependencies:
                    warnings.warn(
                        f"Duplicate dependency name '{name}' from group {group.__name__!r}; overwriting.",
                        stacklevel=2,
                    )
                app_config.dependencies[name] = FromDI(provider)
        app_config.lifespan.append(_lifespan_manager)
        return app_config


async def build_di_container(
    request: litestar.Request[typing.Any, typing.Any, typing.Any],
) -> typing.AsyncIterator[Container]:
    context: dict[type[typing.Any], typing.Any] = {}
    scope: DIScope | None
    if isinstance(request, litestar.WebSocket):
        context[litestar.WebSocket] = request
        scope = DIScope.SESSION
    else:
        context[litestar.Request] = request
        scope = DIScope.REQUEST
    container = fetch_di_container(request.app).build_child_container(context=context, scope=scope)
    try:
        yield container
    finally:
        await container.close_async()


@dataclasses.dataclass(slots=True, frozen=True)
class _Dependency(typing.Generic[T_co]):
    dependency: providers.AbstractProvider[T_co] | type[T_co]

    async def __call__(
        self, di_container: typing.Annotated[Container, Dependency(skip_validation=True)]
    ) -> T_co | None:
        if isinstance(self.dependency, providers.AbstractProvider):
            return di_container.resolve_provider(self.dependency)
        return di_container.resolve(dependency_type=self.dependency)


def FromDI(dependency: providers.AbstractProvider[T_co] | type[T_co]) -> Provide:  # noqa: N802
    return Provide(dependency=_Dependency(dependency), use_cache=False)
