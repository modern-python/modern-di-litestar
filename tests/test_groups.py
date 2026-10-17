import warnings

import litestar
import pytest
from litestar import status_codes
from litestar.config.app import AppConfig
from litestar.di import NamedDependency, Provide
from litestar.exceptions import ImproperlyConfiguredException
from litestar.plugins import InitPlugin
from litestar.testing import TestClient
from modern_di import Container, Group, Scope, providers

import modern_di_litestar
from modern_di_litestar.main import _autowired_dependencies
from tests.dependencies import Dependencies, DependentCreator, SimpleCreator


class OverlappingGroup(Group):
    app_factory = providers.Factory(creator=SimpleCreator, kwargs={"dep1": "second"}, bound_type=None)


class ReservedNameGroup(Group):
    di_container = providers.Factory(creator=SimpleCreator, kwargs={"dep1": "reserved"}, bound_type=None)


class _UserDiContainerPlugin(InitPlugin):
    def on_app_init(self, app_config: AppConfig) -> AppConfig:
        app_config.dependencies["di_container"] = Provide(dict, sync_to_thread=False)
        return app_config


def _make_app(*groups: type[Group]) -> litestar.Litestar:
    all_groups = [Dependencies, *groups]
    return litestar.Litestar(
        debug=True,
        plugins=[modern_di_litestar.ModernDIPlugin(Container(groups=all_groups), autowired_groups=all_groups)],
    )


def test_group_autowiring() -> None:
    app = _make_app()

    @litestar.get("/")
    async def read_root(
        app_factory: NamedDependency[SimpleCreator], request_factory: NamedDependency[DependentCreator]
    ) -> None:
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
    async def read_root(inherited: NamedDependency[SimpleCreator]) -> None:
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


def test_autowired_name_di_container_is_rejected() -> None:
    with pytest.raises(ImproperlyConfiguredException, match="ReservedNameGroup") as exc_info:
        _make_app(ReservedNameGroup)

    assert "'di_container'" in exc_info.value.detail
    assert "reserved" in exc_info.value.detail


def test_user_dependency_named_di_container_is_rejected() -> None:
    with pytest.raises(ImproperlyConfiguredException, match="'di_container'") as exc_info:
        litestar.Litestar(
            dependencies={"di_container": Provide(dict, sync_to_thread=False)},
            plugins=[modern_di_litestar.ModernDIPlugin(Container())],
        )

    assert "reserved by ModernDIPlugin" in exc_info.value.detail


def test_earlier_plugin_dependency_named_di_container_is_rejected() -> None:
    with pytest.raises(ImproperlyConfiguredException, match="reserved by ModernDIPlugin"):
        litestar.Litestar(plugins=[_UserDiContainerPlugin(), modern_di_litestar.ModernDIPlugin(Container())])
