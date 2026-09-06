import warnings

import litestar
from litestar import status_codes
from litestar.di import Provide
from litestar.testing import TestClient
from modern_di import Container, Group, Scope, providers

import modern_di_litestar
from modern_di_litestar.main import _autowired_dependencies
from tests.dependencies import Dependencies, DependentCreator, SimpleCreator


class OverlappingGroup(Group):
    app_factory = providers.Factory(creator=SimpleCreator, kwargs={"dep1": "second"}, bound_type=None)


def _make_app(*groups: type[Group]) -> litestar.Litestar:
    all_groups = [Dependencies, *groups]
    return litestar.Litestar(
        debug=True,
        plugins=[modern_di_litestar.ModernDIPlugin(Container(groups=all_groups), autowired_groups=all_groups)],
    )


def test_group_autowiring() -> None:
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


def test_autowiring_resolves_inherited_provider() -> None:
    """INVARIANT: a provider inherited from a base ``Group`` is autowired under its declared name.

    Broken by recovering names from a subclass's own ``__dict__`` rather than from
    ``Group.get_named_providers()``, which walks the MRO. The two agree for every flat group, so
    the mistake is invisible until someone factors shared providers into a base class -- and then
    it lands as an error while their app is being constructed, not on this suite.
    """

    class BaseGroup(Group):
        inherited = providers.Factory(creator=SimpleCreator, kwargs={"dep1": "inherited"})

    class ChildGroup(BaseGroup): ...

    groups: list[type[Group]] = [ChildGroup]
    di_container = Container(groups=groups)
    app = litestar.Litestar(
        debug=True,
        plugins=[modern_di_litestar.ModernDIPlugin(di_container, autowired_groups=groups)],
    )

    @litestar.get("/")
    async def read_root(inherited: SimpleCreator) -> None:
        assert isinstance(inherited, SimpleCreator)
        assert inherited.dep1 == "inherited"

    app.register(read_root)

    with TestClient(app=app, raise_server_exceptions=True) as client:
        response = client.get("/")
        assert response.status_code == status_codes.HTTP_200_OK, response.text


def test_autowired_dependencies_maps_provider_names_to_provides() -> None:
    result = _autowired_dependencies([Dependencies])
    assert isinstance(result["app_factory"], Provide)
    assert {"app_factory", "request_factory", "session_factory"} <= set(result)


async def test_a_colliding_autowired_name_resolves_to_the_last_group() -> None:
    """INVARIANT: when two autowired groups declare one name, the last group's provider wins.

    Broken by any collision policy that keeps the first binding -- a ``setdefault``, a guard that
    skips a name already seen. The duplicate-name warning does not catch that: it fires either way,
    and its text promises "overwriting". Last-write-wins is also what ``dependencies.update()`` does
    with the returned mapping, so a first-wins mapping would make the plugin's outcome depend on
    which of the two layers deduplicated.
    """
    groups: list[type[Group]] = [Dependencies, OverlappingGroup]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        dependencies = _autowired_dependencies(groups)

    async with Container(groups=groups) as container:
        with container.build_child_container(scope=Scope.REQUEST) as child:
            resolved = await dependencies["app_factory"].dependency(child)

    assert resolved.dep1 == "second"


def test_autowired_dependencies_warns_on_existing_name_collision() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _autowired_dependencies([Dependencies], existing={"app_factory"})

    collisions = [w for w in caught if issubclass(w.category, UserWarning) and "app_factory" in str(w.message)]
    assert len(collisions) == 1
    assert "Dependencies" in str(collisions[0].message)
