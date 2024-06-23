from typing import Any, cast

import pytest
from _pytest._code.code import ExceptionInfo  # type: ignore
from prometheus_client import CollectorRegistry  # type: ignore
from pydantic import BaseModel, Field

from blacksmith.domain.exceptions import (
    HTTPError,
    HTTPTimeoutError,
    NoContractException,
    UnregisteredResourceException,
    UnregisteredRouteException,
    WrongRequestTypeException,
)
from blacksmith.domain.model import (
    CollectionParser,
    HTTPRequest,
    HTTPResponse,
    HTTPTimeout,
    ResponseBox,
)
from blacksmith.domain.model.middleware.prometheus import PrometheusMetrics
from blacksmith.domain.registry import ApiRoutes
from blacksmith.middleware._sync.auth import SyncHTTPAuthorizationMiddleware
from blacksmith.middleware._sync.base import SyncHTTPMiddleware
from blacksmith.middleware._sync.prometheus import SyncPrometheusMiddleware
from blacksmith.sd._sync.base import SyncAbstractServiceDiscovery
from blacksmith.service._sync.base import SyncAbstractTransport
from blacksmith.service._sync.client import SyncClient, SyncClientFactory
from blacksmith.typing import ClientName, Path, Proxies
from tests.unittests.dummy_registry import (
    GetParam,
    GetResponse,
    PostParam,
    dummy_registry,
)


class MyErrorFormat(BaseModel):
    message: str = Field(...)
    detail: str = Field(...)


def error_parser(error: HTTPError) -> MyErrorFormat:
    return MyErrorFormat(**error.json)  # type: ignore


class FakeTransport(SyncAbstractTransport):
    def __init__(self, resp: HTTPResponse) -> None:
        super().__init__()
        self.resp = resp

    def __call__(
        self,
        req: HTTPRequest,
        client_name: ClientName,
        path: Path,
        timeout: HTTPTimeout,
    ) -> HTTPResponse:

        if self.resp.status_code >= 400:
            raise HTTPError(f"{self.resp.status_code} blah", req, self.resp)
        return self.resp


class FakeTimeoutTransport(SyncAbstractTransport):
    def __call__(
        self,
        req: HTTPRequest,
        client_name: ClientName,
        path: Path,
        timeout: HTTPTimeout,
    ) -> HTTPResponse:
        raise HTTPTimeoutError(f"ReadTimeout while calling {req.method} {req.url}")


def test_client(static_sd: SyncAbstractServiceDiscovery):

    resp = HTTPResponse(
        200,
        {},
        {
            "name": "Barbie",
            "age": 42,
            "hair_color": "blond",
        },
    )

    routes = ApiRoutes(
        "/dummies/{name}", {"GET": (GetParam, GetResponse)}, None, None, None
    )

    client: SyncClient[MyErrorFormat] = SyncClient(
        "api",
        "https://dummies.v1",
        {"dummies": routes},
        transport=FakeTransport(resp),
        timeout=HTTPTimeout(),
        collection_parser=CollectionParser,
        middlewares=[],
        error_parser=error_parser,
    )
    api_resp = client.dummies.get({"name": "barbie"})
    assert isinstance(api_resp, ResponseBox)
    assert isinstance(api_resp.response, GetResponse)
    assert api_resp.response.model_dump() == {"name": "Barbie", "age": 42}
    assert api_resp.json == {
        "name": "Barbie",
        "age": 42,
        "hair_color": "blond",
    }
    assert api_resp.response.model_dump() == {"name": "Barbie", "age": 42}

    ctx: ExceptionInfo[Any]
    with pytest.raises(UnregisteredResourceException) as ctx:
        client.daemon
    assert str(ctx.value) == "Unregistered resource 'daemon' in client 'api'"

    with pytest.raises(NoContractException) as ctx:
        client.dummies.post({"name": "Barbie", "age": 42})

    assert (
        str(ctx.value)
        == "Unregistered route 'POST' in resource 'dummies' in client 'api'"
    )

    with pytest.raises(UnregisteredRouteException) as ctx:
        client.dummies.collection_post({"name": "Barbie", "age": 42})
    assert (
        str(ctx.value)
        == "Unregistered route 'POST' in resource 'dummies' in client 'api'"
    )

    with pytest.raises(WrongRequestTypeException) as ctx:
        client.dummies.get(PostParam(name="barbie", age=42))
    assert (
        str(ctx.value) == "Invalid type 'tests.unittests.dummy_registry.PostParam' "
        "for route 'GET' in resource 'dummies' in client 'api'"
    )


def test_client_timeout(static_sd: SyncAbstractServiceDiscovery):

    routes = ApiRoutes(
        "/dummies/{name}", {"GET": (GetParam, GetResponse)}, None, None, None
    )

    client: SyncClient[MyErrorFormat] = SyncClient(
        "api",
        "http://dummies.v1",
        {"dummies": routes},
        transport=FakeTimeoutTransport(),
        timeout=HTTPTimeout(),
        collection_parser=CollectionParser,
        middlewares=[],
        error_parser=error_parser,
    )
    with pytest.raises(HTTPTimeoutError) as exc:
        client.dummies.get({"name": "barbie"})
    assert (
        str(exc.value)
        == "ReadTimeout while calling GET http://dummies.v1/dummies/barbie"
    )


def test_client_factory_config(static_sd: SyncAbstractServiceDiscovery):
    tp = FakeTimeoutTransport()
    client_factory: SyncClientFactory[Any] = SyncClientFactory(
        static_sd, tp, registry=dummy_registry
    )

    cli = client_factory("api")

    assert cli.name == "api"
    assert cli.endpoint == "https://dummy.v1/"
    assert set(cli.resources.keys()) == {"dummies"}
    assert cli.transport == tp


def test_client_factory_configure_transport(static_sd: SyncAbstractServiceDiscovery):
    client_factory: SyncClientFactory[Any] = SyncClientFactory(
        static_sd, verify_certificate=False
    )
    assert client_factory.transport.verify_certificate is False


def test_client_factory_configure_proxies(static_sd: SyncAbstractServiceDiscovery):
    proxies: Proxies = {
        "http://": "http://localhost:8030",
        "https://": "http://localhost:8031",
    }
    client_factory: SyncClientFactory[Any] = SyncClientFactory(
        static_sd, proxies=proxies
    )
    assert client_factory.transport.proxies is proxies


def test_client_factory_add_middleware(
    static_sd: SyncAbstractServiceDiscovery, dummy_middleware: SyncHTTPMiddleware
):
    tp = FakeTimeoutTransport()
    auth = SyncHTTPAuthorizationMiddleware("Bearer", "abc")
    metrics = PrometheusMetrics(registry=CollectorRegistry())
    prom = SyncPrometheusMiddleware(metrics=metrics)
    client_factory: SyncClientFactory[Any] = (
        SyncClientFactory(static_sd, tp, registry=dummy_registry)
        .add_middleware(prom)
        .add_middleware(auth)
    )
    assert client_factory.middlewares == [auth, prom]

    cli = client_factory("api")
    assert cli.middlewares == [auth, prom]

    client_factory.add_middleware(dummy_middleware)
    assert client_factory.middlewares == [dummy_middleware, auth, prom]
    assert cli.middlewares == [auth, prom]
    assert cast(SyncHTTPAuthorizationMiddleware, cli.middlewares[0]).headers == {
        "Authorization": "Bearer abc"
    }
    cast(SyncHTTPAuthorizationMiddleware, client_factory.middlewares[0]).headers[
        "Authorization"
    ] = "Bearer xyz"
    assert cast(SyncHTTPAuthorizationMiddleware, cli.middlewares[0]).headers == {
        "Authorization": "Bearer abc"
    }


def test_client_add_middleware(
    static_sd: SyncAbstractServiceDiscovery, dummy_middleware: SyncHTTPMiddleware
):
    tp = FakeTimeoutTransport()
    metrics = PrometheusMetrics(registry=CollectorRegistry())
    prom = SyncPrometheusMiddleware(metrics)
    auth = SyncHTTPAuthorizationMiddleware("Bearer", "abc")
    client_factory: SyncClientFactory[Any] = SyncClientFactory(
        static_sd, tp, registry=dummy_registry
    ).add_middleware(prom)

    cli = client_factory("api")
    assert cli.middlewares == [prom]
    cli.add_middleware(auth)

    assert cli.middlewares == [auth, prom]
    assert client_factory.middlewares == [prom]

    cli2 = (client_factory("api")).add_middleware(dummy_middleware)
    assert cli2.middlewares == [dummy_middleware, prom]
    assert cli.middlewares == [auth, prom]
    assert client_factory.middlewares == [prom]


def test_client_factory_initialize_middlewares(
    echo_middleware: SyncAbstractTransport,
    static_sd: SyncAbstractServiceDiscovery,
    dummy_middleware: Any,
):
    client_factory: SyncClientFactory[Any] = SyncClientFactory(
        static_sd, echo_middleware, registry=dummy_registry
    ).add_middleware(dummy_middleware)
    assert dummy_middleware.initialized == 0
    client_factory.initialize()
    assert dummy_middleware.initialized == 1
