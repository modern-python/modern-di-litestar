import litestar
from litestar import status_codes
from litestar.testing import TestClient

from modern_di_litestar import FromDI, fetch_di_container
from tests.dependencies import Dependencies, SimpleCreator


def test_lifespan_reopens_container_across_cycles(app: litestar.Litestar) -> None:
    @litestar.get("/", dependencies={"instance": FromDI(Dependencies.app_factory)})
    async def read_root(instance: SimpleCreator) -> None:
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
