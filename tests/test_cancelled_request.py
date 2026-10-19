import logging
import typing

import anyio
import litestar
import pytest
from litestar.di import NamedDependency
from modern_di import Container, Group, Scope, providers

from modern_di_litestar import FromDI, ModernDIPlugin, main


class _First: ...


class _Second: ...


def _app(log: list[str], *, finalizer_delay: float) -> litestar.Litestar:
    async def finalize_first(_: _First) -> None:
        await anyio.sleep(finalizer_delay)
        log.append("first")

    async def finalize_second(_: _Second) -> None:
        await anyio.sleep(finalizer_delay)
        log.append("second")

    class G(Group):
        first = providers.Factory(
            scope=Scope.REQUEST, creator=_First, cache=providers.CacheSettings(finalizer=finalize_first)
        )
        second = providers.Factory(
            scope=Scope.REQUEST, creator=_Second, cache=providers.CacheSettings(finalizer=finalize_second)
        )

    @litestar.get("/", dependencies={"first": FromDI(_First), "second": FromDI(_Second)})
    async def endpoint(first: NamedDependency[_First], second: NamedDependency[_Second]) -> None:
        assert isinstance(first, _First)
        assert isinstance(second, _Second)
        await anyio.sleep_forever()

    return litestar.Litestar(
        [endpoint],
        plugins=[ModernDIPlugin(Container(groups=[G]), manage_lifespan=False)],
        logging_config=None,  # Litestar's own config would replace the handler caplog listens on.
    )


async def _call_cancelled_mid_handler(app: litestar.Litestar) -> None:
    async def receive() -> dict[str, typing.Any]:
        return {
            "type": "http.request",
            "body": b"",
            "more_body": False,
        }  # pragma: no cover -- GET handlers never read the body

    async def send(_: typing.Any) -> None: ...  # noqa: ANN401

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "path": "/",
        "raw_path": b"/",
        "root_path": "",
        "scheme": "http",
        "query_string": b"",
        "headers": [],
        "client": ("testclient", 1),
        "server": ("testserver", 80),
        "state": {},
    }

    async def call() -> None:
        with anyio.move_on_after(0.05):
            await app(scope, receive, send)  # ty: ignore[invalid-argument-type]

    # Its own task keeps the cancellation out of the test's frame, where 3.11 coverage loses a line.
    async with anyio.create_task_group() as task_group:
        task_group.start_soon(call)


async def test_a_cancelled_request_still_runs_every_child_finalizer() -> None:
    log: list[str] = []

    await _call_cancelled_mid_handler(_app(log, finalizer_delay=0.01))

    assert sorted(log) == ["first", "second"]


async def test_a_hung_child_finalizer_is_abandoned_after_the_bound(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(main, "_CHILD_CLOSE_TIMEOUT", 0.05)
    caplog.set_level(logging.WARNING, logger=main.__name__)
    log: list[str] = []

    await _call_cancelled_mid_handler(_app(log, finalizer_delay=10))

    assert log == []
    assert [record.getMessage() for record in caplog.records] == [
        "Closing the child container did not finish within 0.05 s; its remaining finalizers did not run"
    ]
