import warnings

import litestar
from litestar import status_codes
from litestar.testing import TestClient
from modern_di import Container, Group, providers

import modern_di_litestar
from tests.dependencies import Dependencies, DependentCreator, SimpleCreator


class OverlappingGroup(Group):
    app_factory = providers.Factory(creator=SimpleCreator, kwargs={"dep1": "second"}, bound_type=None)


def _make_app(*groups: type[Group]) -> litestar.Litestar:
    all_groups = [Dependencies, *groups]
    return litestar.Litestar(
        debug=True,
        plugins=[modern_di_litestar.ModernDIPlugin(Container(groups=all_groups), autowired_groups=all_groups)],
    )


def test_group_auto_wiring() -> None:
    app = _make_app()

    @litestar.get("/")
    async def read_root(app_factory: SimpleCreator, request_factory: DependentCreator) -> None:
        assert isinstance(app_factory, SimpleCreator)
        assert app_factory.dep1 == "original"
        assert isinstance(request_factory, DependentCreator)

    app.register(read_root)

    with TestClient(app=app, raise_server_exceptions=True) as client:
        response = client.get("/")
        assert response.status_code == status_codes.HTTP_200_OK, response.text


def test_group_duplicate_name_warning() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _make_app(OverlappingGroup)

    duplicate_warnings = [w for w in caught if issubclass(w.category, UserWarning) and "app_factory" in str(w.message)]
    assert len(duplicate_warnings) == 1
    assert "OverlappingGroup" in str(duplicate_warnings[0].message)
