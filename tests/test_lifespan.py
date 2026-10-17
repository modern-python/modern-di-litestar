import collections.abc
import contextlib
import dataclasses

import litestar
from litestar import status_codes
from litestar.di import NamedDependency
from litestar.testing import AsyncTestClient, TestClient
from modern_di import Container, Group, Scope, providers

from modern_di_litestar import FromDI, ModernDIPlugin, fetch_di_container
from tests.dependencies import Dependencies, SimpleCreator


def test_lifespan_reopens_container_across_cycles(app: litestar.Litestar) -> None:
    @litestar.get("/", dependencies={"instance": FromDI(Dependencies.app_factory)})
    async def read_root(instance: NamedDependency[SimpleCreator]) -> None:
        assert isinstance(instance, SimpleCreator)

    app.register(read_root)
    container = fetch_di_container(app)

    # First lifespan cycle: shutdown closes the root container.
    with TestClient(app=app, raise_server_exceptions=True) as client:
        assert client.get("/").status_code == status_codes.HTTP_200_OK
    assert container.closed

    # Second cycle must reopen the same container instead of raising ContainerClosedError.
    with TestClient(app=app, raise_server_exceptions=True) as client:
        assert client.get("/").status_code == status_codes.HTTP_200_OK


@dataclasses.dataclass(kw_only=True, slots=True)
class AppResource:
    finalized: int = 0


@dataclasses.dataclass(kw_only=True, slots=True)
class RequestResource:
    finalized: int = 0


def _finalize(resource: AppResource | RequestResource) -> None:
    resource.finalized += 1


class Resources(Group):
    app_resource = providers.Factory(creator=AppResource, cache=providers.CacheSettings(finalizer=_finalize))
    request_resource = providers.Factory(
        scope=Scope.REQUEST, creator=RequestResource, cache=providers.CacheSettings(finalizer=_finalize)
    )


def _unmanaged_app(container: Container, seen: list[RequestResource]) -> litestar.Litestar:
    @litestar.get("/")
    async def read_root(
        app_resource: NamedDependency[AppResource], request_resource: NamedDependency[RequestResource]
    ) -> None:
        assert app_resource.finalized == 0
        seen.append(request_resource)

    return litestar.Litestar(
        route_handlers=[read_root],
        plugins=[ModernDIPlugin(container, autowired_groups=[Resources], manage_lifespan=False)],
    )


def test_manage_lifespan_false_leaves_the_root_alone() -> None:
    container = Container(groups=[Resources])
    seen: list[RequestResource] = []
    app = _unmanaged_app(container, seen)

    with TestClient(app=app, raise_server_exceptions=True) as client:
        assert client.get("/").status_code == status_codes.HTTP_200_OK

    assert not container.closed
    assert container.resolve(AppResource).finalized == 0
    assert [resource.finalized for resource in seen] == [1]


async def test_manage_lifespan_false_lets_the_user_own_the_root() -> None:
    container = Container(groups=[Resources])
    seen: list[RequestResource] = []
    app = _unmanaged_app(container, seen)

    async with container:
        async with AsyncTestClient(app=app, raise_server_exceptions=True) as client:
            assert (await client.get("/")).status_code == status_codes.HTTP_200_OK
        app_resource = container.resolve(AppResource)
        assert app_resource.finalized == 0

    assert container.closed
    assert app_resource.finalized == 1
    assert [resource.finalized for resource in seen] == [1]


def _user_code_app(container: Container, events: list[tuple[str, int]]) -> litestar.Litestar:
    def record(event: str, app_: litestar.Litestar) -> None:
        events.append((event, fetch_di_container(app_).resolve(AppResource).finalized))

    @contextlib.asynccontextmanager
    async def user_lifespan(app_: litestar.Litestar) -> collections.abc.AsyncGenerator[None]:
        record("lifespan enter", app_)
        yield
        record("lifespan exit", app_)

    return litestar.Litestar(
        lifespan=[user_lifespan],
        on_startup=[lambda app_: record("startup", app_)],
        on_shutdown=[lambda app_: record("shutdown", app_)],
        plugins=[ModernDIPlugin(container, autowired_groups=[Resources])],
    )


def test_root_is_open_for_all_user_lifespan_code_across_cycles() -> None:
    container = Container(groups=[Resources])
    events: list[tuple[str, int]] = []
    app = _user_code_app(container, events)
    one_cycle = [("lifespan enter", 0), ("startup", 0), ("lifespan exit", 0), ("shutdown", 0)]

    for cycle in (1, 2):
        with TestClient(app=app, raise_server_exceptions=True):
            pass
        assert events == one_cycle * cycle
        assert container.closed


def test_app_finalizer_runs_after_user_shutdown_code() -> None:
    container = Container(groups=[Resources])
    events: list[tuple[str, int]] = []
    app = _user_code_app(container, events)

    with TestClient(app=app, raise_server_exceptions=True):
        app_resource = container.resolve(AppResource)

    assert events[-1] == ("shutdown", 0)
    assert app_resource.finalized == 1
