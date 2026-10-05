import dataclasses

import litestar
from modern_di import Group, Scope, providers


@dataclasses.dataclass(kw_only=True, slots=True)
class SimpleCreator:
    dep1: str


@dataclasses.dataclass(kw_only=True, slots=True)
class DependentCreator:
    dep1: SimpleCreator


def fetch_method_from_request(request: litestar.Request) -> str:
    return request.method


def fetch_url_from_websocket(websocket: litestar.WebSocket) -> str:
    return websocket.url.path


class Dependencies(Group):
    app_factory = providers.Factory(creator=SimpleCreator, kwargs={"dep1": "original"})
    session_factory = providers.Factory(scope=Scope.SESSION, creator=DependentCreator, bound_type=None)
    request_factory = providers.Factory(
        scope=Scope.REQUEST, creator=DependentCreator, cache=providers.CacheSettings(), bound_type=None
    )
    action_factory = providers.Factory(scope=Scope.ACTION, creator=DependentCreator, bound_type=None)
    request_method = providers.Factory(scope=Scope.REQUEST, creator=fetch_method_from_request, bound_type=None)
    websocket_path = providers.Factory(scope=Scope.SESSION, creator=fetch_url_from_websocket, bound_type=None)
