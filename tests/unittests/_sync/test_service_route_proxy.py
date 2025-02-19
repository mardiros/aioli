from collections.abc import Mapping
from typing import Any, Union

import pytest
from pydantic import BaseModel, Field, ValidationError
from result import Result
from typing_extensions import Literal

from blacksmith import Request
from blacksmith.domain.exceptions import (
    HTTPError,
    NoContractException,
    UnregisteredRouteException,
    WrongRequestTypeException,
)
from blacksmith.domain.model import (
    CollectionParser,
    HTTPRequest,
    HTTPResponse,
    HTTPTimeout,
)
from blacksmith.domain.model.params import CollectionIterator
from blacksmith.domain.registry import ApiRoutes
from blacksmith.middleware._sync.auth import SyncHTTPAuthorizationMiddleware
from blacksmith.middleware._sync.base import SyncHTTPAddHeadersMiddleware
from blacksmith.service._sync.base import SyncAbstractTransport
from blacksmith.service._sync.route_proxy import (
    SyncRouteProxy,
    build_request,
    build_timeout,
    is_instance_with_union,
    is_union,
)
from blacksmith.typing import ClientName, Path
from tests.unittests.dummy_registry import GetParam, GetResponse, PostParam


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


def test_build_timeout() -> None:
    timeout = build_timeout(HTTPTimeout())
    assert timeout == HTTPTimeout(30.0, 15.0)
    timeout = build_timeout(5.0)
    assert timeout == HTTPTimeout(5.0, 15.0)
    timeout = build_timeout((5.0, 2.0))
    assert timeout == HTTPTimeout(5.0, 2.0)


@pytest.mark.parametrize(
    "params",
    [
        pytest.param({"type": int, "expected": False}, id="int"),
        pytest.param({"type": str, "expected": False}, id="str"),
        pytest.param({"type": Union[int, str], "expected": True}, id="Union[int, str]"),
    ],
)
def test_is_union(params: Mapping[str, Any]):
    assert is_union(params["type"]) is params["expected"]


try:

    @pytest.mark.parametrize(
        "params",
        [
            pytest.param({"type": int | str, "expected": True}, id="int | str"),
        ],
    )
    def test_is_union_py310(params: Mapping[str, Any]):
        assert is_union(params["type"]) is params["expected"]

except TypeError:
    ...


@pytest.mark.parametrize(
    "params",
    [
        pytest.param({"type": str, "value": "bob", "expected": True}, id="str"),
        pytest.param({"type": str, "value": 0.42, "expected": False}, id="str / float"),
        pytest.param(
            {"type": Union[int, str], "value": "bob", "expected": True},
            id="int | str / str",
        ),
        pytest.param(
            {"type": Union[int, str], "value": 42, "expected": True},
            id="int | str / int",
        ),
        pytest.param(
            {"type": Union[int, str], "value": 0.42, "expected": False},
            id="int | str / float",
        ),
    ],
)
def test_is_instance_with_union(params: Mapping[str, Any]):
    resp = is_instance_with_union(params["value"], params["type"])
    assert resp == params["expected"]


class Foo(BaseModel):
    typ: Literal["foo"]


class Bar(BaseModel):
    typ: Literal["bar"]


@pytest.mark.parametrize(
    "params",
    [
        pytest.param(
            {"type": Foo, "params": {"typ": "foo"}, "expected": Foo(typ="foo")},
            id="simple",
        ),
        pytest.param(
            {
                "type": Union[Foo, Bar],
                "params": {"typ": "foo"},
                "expected": Foo(typ="foo"),
            },
            id="union",
        ),
        pytest.param(
            {
                "type": Union[Foo, Bar],
                "params": {"typ": "bar"},
                "expected": Bar(typ="bar"),
            },
            id="union",
        ),
    ],
)
def test_build_request(params: Mapping[str, Any]):
    req = build_request(params["type"], params["params"])
    assert req == params["expected"]


@pytest.mark.parametrize(
    "params",
    [
        pytest.param(
            {"type": Foo, "params": {"typ": "bar"}, "err": "Input should be 'foo'"},
            id="simple",
        ),
        pytest.param(
            {
                "type": Union[Foo, Bar],
                "params": {"typ": "baz"},
                "err": "Input should be 'bar'",
            },
            id="union",
        ),
    ],
)
def test_build_request_error(params: Mapping[str, Any]):
    with pytest.raises(ValidationError) as ctx:
        build_request(params["type"], params["params"])
    assert str(ctx.value.errors()[0]["msg"]) == params["err"]


def test_route_proxy_prepare_middleware(
    dummy_http_request: HTTPRequest, echo_middleware: SyncAbstractTransport
):
    proxy: SyncRouteProxy[Any, Any, Any] = SyncRouteProxy(
        "dummy",
        "dummies",
        "http://dummy/",
        ApiRoutes(
            path="/",
            contract={"GET": (Request, None)},
            collection_path=None,
            collection_contract=None,
            collection_parser=None,
        ),
        transport=echo_middleware,
        timeout=HTTPTimeout(),
        collection_parser=CollectionParser,
        middlewares=[
            SyncHTTPAuthorizationMiddleware("Bearer", "abc"),
            SyncHTTPAddHeadersMiddleware({"foo": "bar"}),
            SyncHTTPAddHeadersMiddleware({"Eggs": "egg"}),
        ],
        error_parser=error_parser,
    )
    result = proxy._handle_req_with_middlewares(
        dummy_http_request,
        HTTPTimeout(4.2),
        "/",
    )
    assert result.is_ok()
    resp = result.unwrap()
    assert resp.headers == {
        "Authorization": "Bearer abc",
        "X-Req-Id": "42",
        "Eggs": "egg",
        "foo": "bar",
    }


def test_route_proxy_prepare_unregistered_method_resource() -> None:
    http_resp = HTTPResponse(200, {}, "")
    tp = FakeTransport(http_resp)

    proxy: SyncRouteProxy[Any, Any, Any] = SyncRouteProxy(
        "dummy",
        "dummies",
        "http://dummy/",
        ApiRoutes(
            path="/",
            contract={},
            collection_path=None,
            collection_contract=None,
            collection_parser=None,
        ),
        transport=tp,
        timeout=HTTPTimeout(),
        collection_parser=CollectionParser,
        middlewares=[],
        error_parser=error_parser,
    )
    with pytest.raises(NoContractException) as exc:
        proxy._prepare_request("GET", {}, proxy.routes.resource)
    assert (
        str(exc.value)
        == "Unregistered route 'GET' in resource 'dummies' in client 'dummy'"
    )


def test_route_proxy_prepare_unregistered_method_collection() -> None:
    http_resp = HTTPResponse(200, {}, "")
    tp = FakeTransport(http_resp)

    proxy: SyncRouteProxy[Any, Any, Any] = SyncRouteProxy(
        "dummy",
        "dummies",
        "http://dummy/",
        ApiRoutes(
            None,
            None,
            "/",
            {},
            collection_parser=None,
        ),
        transport=tp,
        timeout=HTTPTimeout(),
        collection_parser=CollectionParser,
        middlewares=[],
        error_parser=error_parser,
    )
    with pytest.raises(NoContractException) as exc:
        proxy._prepare_request("GET", {}, proxy.routes.collection)
    assert (
        str(exc.value)
        == "Unregistered route 'GET' in resource 'dummies' in client 'dummy'"
    )


def test_route_proxy_prepare_unregistered_resource() -> None:
    http_resp = HTTPResponse(200, {}, "")
    tp = FakeTransport(http_resp)

    proxy: SyncRouteProxy[Any, Any, Any] = SyncRouteProxy(
        "dummy",
        "dummies",
        "http://dummy/",
        ApiRoutes(
            None,
            None,
            "/",
            {},
            collection_parser=None,
        ),
        transport=tp,
        timeout=HTTPTimeout(),
        collection_parser=CollectionParser,
        middlewares=[],
        error_parser=error_parser,
    )
    with pytest.raises(UnregisteredRouteException) as exc:
        proxy._prepare_request("GET", {}, proxy.routes.resource)
    assert (
        str(exc.value)
        == "Unregistered route 'GET' in resource 'dummies' in client 'dummy'"
    )


def test_route_proxy_prepare_unregistered_collection() -> None:
    http_resp = HTTPResponse(200, {}, "")
    tp = FakeTransport(http_resp)

    proxy: SyncRouteProxy[Any, Any, Any] = SyncRouteProxy(
        "dummy",
        "dummies",
        "http://dummy/",
        ApiRoutes(
            "/",
            {},
            None,
            None,
            collection_parser=None,
        ),
        transport=tp,
        timeout=HTTPTimeout(),
        collection_parser=CollectionParser,
        middlewares=[],
        error_parser=error_parser,
    )
    with pytest.raises(UnregisteredRouteException) as exc:
        proxy._prepare_request("GET", {}, proxy.routes.collection)
    assert (
        str(exc.value)
        == "Unregistered route 'GET' in resource 'dummies' in client 'dummy'"
    )


def test_route_proxy_prepare_wrong_type() -> None:
    http_resp = HTTPResponse(200, {}, "")
    tp = FakeTransport(http_resp)

    proxy: SyncRouteProxy[Any, Any, Any] = SyncRouteProxy(
        "dummy",
        "dummies",
        "http://dummy/",
        ApiRoutes(
            "/",
            {"GET": (GetParam, GetResponse)},
            None,
            None,
            collection_parser=None,
        ),
        transport=tp,
        timeout=HTTPTimeout(),
        collection_parser=CollectionParser,
        middlewares=[],
        error_parser=error_parser,
    )
    with pytest.raises(WrongRequestTypeException) as exc:
        proxy._prepare_request(
            "GET", PostParam(name="barbie", age=42), proxy.routes.resource
        )

    assert (
        str(exc.value) == "Invalid type 'tests.unittests.dummy_registry.PostParam' "
        "for route 'GET' in resource 'dummies' in client 'dummy'"
    )


def test_route_proxy_collection_head() -> None:
    http_resp = HTTPResponse(200, {}, "")
    tp = FakeTransport(http_resp)
    proxy: SyncRouteProxy[Any, Any, Any] = SyncRouteProxy(
        "dummy",
        "dummies",
        "http://dummy/",
        ApiRoutes(
            None,
            None,
            collection_path="/",
            collection_contract={"HEAD": (Request, None)},
            collection_parser=None,
        ),
        transport=tp,
        timeout=HTTPTimeout(),
        collection_parser=CollectionParser,
        middlewares=[],
        error_parser=error_parser,
    )
    resp = (proxy.collection_head({"name": "baby"})).json
    assert resp == ""


def test_route_proxy_collection_get() -> None:
    httpresp = HTTPResponse(
        200, {"Total-Count": "10"}, [{"name": "alice"}, {"name": "bob"}]
    )
    tp = FakeTransport(httpresp)

    proxy: SyncRouteProxy[Any, Any, Any] = SyncRouteProxy(
        "dummy",
        "dummies",
        "http://dummy/",
        ApiRoutes(
            None,
            None,
            collection_path="/",
            collection_contract={"GET": (Request, None)},
            collection_parser=None,
        ),
        transport=tp,
        timeout=HTTPTimeout(),
        collection_parser=CollectionParser,
        middlewares=[],
        error_parser=error_parser,
    )
    result: Result[CollectionIterator[Any], MyErrorFormat] = proxy.collection_get()
    assert result.is_ok()
    resp = result.unwrap()
    assert resp.meta.total_count == 10
    assert resp.meta.count == 2
    lresp = list(resp)  # type: ignore
    assert lresp == [{"name": "alice"}, {"name": "bob"}]


def test_route_proxy_collection_get_with_parser() -> None:
    class MyCollectionParser(CollectionParser):
        total_count_header: str = "X-Total-Count"

    httpresp = HTTPResponse(
        200, {"X-Total-Count": "10"}, [{"name": "alice"}, {"name": "bob"}]
    )
    tp = FakeTransport(httpresp)

    proxy: SyncRouteProxy[Any, Any, Any] = SyncRouteProxy(
        "dummy",
        "dummies",
        "http://dummy/",
        ApiRoutes(
            None,
            None,
            collection_path="/",
            collection_contract={"GET": (Request, None)},
            collection_parser=MyCollectionParser,
        ),
        transport=tp,
        timeout=HTTPTimeout(),
        collection_parser=CollectionParser,
        middlewares=[],
        error_parser=error_parser,
    )
    result: Result[CollectionIterator[Any], MyErrorFormat] = proxy.collection_get()
    assert result.is_ok()
    resp = result.unwrap()
    assert resp.meta.total_count == 10
    assert resp.meta.count == 2
    lresp = list(resp)  # type: ignore
    assert lresp == [{"name": "alice"}, {"name": "bob"}]


def test_route_proxy_collection_post() -> None:
    http_resp = HTTPResponse(202, {}, {"detail": "accepted"})
    tp = FakeTransport(http_resp)

    proxy: SyncRouteProxy[Any, Any, Any] = SyncRouteProxy(
        "dummy",
        "dummies",
        "http://dummy/",
        ApiRoutes(
            None,
            None,
            collection_path="/",
            collection_contract={"POST": (Request, None)},
            collection_parser=None,
        ),
        transport=tp,
        timeout=HTTPTimeout(),
        collection_parser=CollectionParser,
        middlewares=[],
        error_parser=error_parser,
    )
    resp = (proxy.collection_post({})).json
    assert resp == {"detail": "accepted"}


def test_route_proxy_collection_put() -> None:
    http_resp = HTTPResponse(202, {}, {"detail": "accepted"})
    tp = FakeTransport(http_resp)

    proxy: SyncRouteProxy[Any, Any, Any] = SyncRouteProxy(
        "dummy",
        "dummies",
        "http://dummy/",
        ApiRoutes(
            None,
            None,
            collection_path="/",
            collection_contract={"PUT": (Request, None)},
            collection_parser=None,
        ),
        transport=tp,
        timeout=HTTPTimeout(),
        collection_parser=CollectionParser,
        middlewares=[],
        error_parser=error_parser,
    )
    resp = (proxy.collection_put({})).json
    assert resp == {"detail": "accepted"}


def test_route_proxy_collection_patch() -> None:
    http_resp = HTTPResponse(202, {}, {"detail": "accepted"})
    tp = FakeTransport(http_resp)

    proxy: SyncRouteProxy[Any, Any, Any] = SyncRouteProxy(
        "dummy",
        "dummies",
        "http://dummy/",
        ApiRoutes(
            None,
            None,
            collection_path="/",
            collection_contract={"PATCH": (Request, None)},
            collection_parser=None,
        ),
        transport=tp,
        timeout=HTTPTimeout(),
        collection_parser=CollectionParser,
        middlewares=[],
        error_parser=error_parser,
    )
    resp = (proxy.collection_patch({})).json
    assert resp == {"detail": "accepted"}


def test_route_proxy_collection_delete() -> None:
    http_resp = HTTPResponse(202, {}, {"detail": "accepted"})
    tp = FakeTransport(http_resp)

    proxy: SyncRouteProxy[Any, Any, Any] = SyncRouteProxy(
        "dummy",
        "dummies",
        "http://dummy/",
        ApiRoutes(
            None,
            None,
            collection_path="/",
            collection_contract={"DELETE": (Request, None)},
            collection_parser=None,
        ),
        transport=tp,
        timeout=HTTPTimeout(),
        collection_parser=CollectionParser,
        middlewares=[],
        error_parser=error_parser,
    )
    resp = (proxy.collection_delete({})).json
    assert resp == {"detail": "accepted"}


def test_route_proxy_collection_options() -> None:
    http_resp = HTTPResponse(202, {}, {"detail": "accepted"})
    tp = FakeTransport(http_resp)

    proxy: SyncRouteProxy[Any, Any, Any] = SyncRouteProxy(
        "dummy",
        "dummies",
        "http://dummy/",
        ApiRoutes(
            None,
            None,
            collection_path="/",
            collection_contract={"OPTIONS": (Request, None)},
            collection_parser=None,
        ),
        transport=tp,
        timeout=HTTPTimeout(),
        collection_parser=CollectionParser,
        middlewares=[],
        error_parser=error_parser,
    )
    resp = (proxy.collection_options({})).json
    assert resp == {"detail": "accepted"}


def test_route_proxy_head() -> None:
    http_resp = HTTPResponse(200, {}, "")
    tp = FakeTransport(http_resp)
    proxy: SyncRouteProxy[Any, Any, Any] = SyncRouteProxy(
        "dummy",
        "dummies",
        "http://dummy/",
        ApiRoutes(
            path="/",
            contract={"HEAD": (Request, None)},
            collection_contract=None,
            collection_path=None,
            collection_parser=None,
        ),
        transport=tp,
        timeout=HTTPTimeout(),
        collection_parser=CollectionParser,
        middlewares=[],
        error_parser=error_parser,
    )
    resp = (proxy.head({"name": "baby"})).json
    assert resp == ""


def test_route_proxy_get() -> None:
    http_resp = HTTPResponse(200, {}, [{"name": "alice"}, {"name": "bob"}])
    tp = FakeTransport(http_resp)

    proxy: SyncRouteProxy[Any, Any, Any] = SyncRouteProxy(
        "dummy",
        "dummies",
        "http://dummy/",
        ApiRoutes(
            path="/",
            contract={"GET": (Request, None)},
            collection_contract=None,
            collection_path=None,
            collection_parser=None,
        ),
        transport=tp,
        timeout=HTTPTimeout(),
        collection_parser=CollectionParser,
        middlewares=[],
        error_parser=error_parser,
    )
    resp = (proxy.get({})).json
    assert resp == [{"name": "alice"}, {"name": "bob"}]


def test_route_proxy_post() -> None:
    http_resp = HTTPResponse(202, {}, {"detail": "accepted"})
    tp = FakeTransport(http_resp)

    proxy: SyncRouteProxy[Any, Any, Any] = SyncRouteProxy(
        "dummy",
        "dummies",
        "http://dummy/",
        ApiRoutes(
            path="/",
            contract={"POST": (Request, None)},
            collection_contract=None,
            collection_path=None,
            collection_parser=None,
        ),
        transport=tp,
        timeout=HTTPTimeout(),
        collection_parser=CollectionParser,
        middlewares=[],
        error_parser=error_parser,
    )
    resp = (proxy.post({})).json
    assert resp == {"detail": "accepted"}


def test_route_proxy_put() -> None:
    http_resp = HTTPResponse(202, {}, {"detail": "accepted"})
    tp = FakeTransport(http_resp)

    proxy: SyncRouteProxy[Any, Any, Any] = SyncRouteProxy(
        "dummy",
        "dummies",
        "http://dummy/",
        ApiRoutes(
            path="/",
            contract={"PUT": (Request, None)},
            collection_contract=None,
            collection_path=None,
            collection_parser=None,
        ),
        transport=tp,
        timeout=HTTPTimeout(),
        collection_parser=CollectionParser,
        middlewares=[],
        error_parser=error_parser,
    )
    resp = (proxy.put({})).json
    assert resp == {"detail": "accepted"}


def test_route_proxy_patch() -> None:
    http_resp = HTTPResponse(202, {}, {"detail": "accepted"})
    tp = FakeTransport(http_resp)

    proxy: SyncRouteProxy[Any, Any, Any] = SyncRouteProxy(
        "dummy",
        "dummies",
        "http://dummy/",
        ApiRoutes(
            path="/",
            contract={"PATCH": (Request, None)},
            collection_contract=None,
            collection_path=None,
            collection_parser=None,
        ),
        transport=tp,
        timeout=HTTPTimeout(),
        collection_parser=CollectionParser,
        middlewares=[],
        error_parser=error_parser,
    )
    resp = (proxy.patch({})).json
    assert resp == {"detail": "accepted"}


def test_route_proxy_delete() -> None:
    http_resp = HTTPResponse(202, {}, {"detail": "accepted"})
    tp = FakeTransport(http_resp)

    proxy: SyncRouteProxy[Any, Any, Any] = SyncRouteProxy(
        "dummy",
        "dummies",
        "http://dummy/",
        ApiRoutes(
            path="/",
            contract={"DELETE": (Request, None)},
            collection_contract=None,
            collection_path=None,
            collection_parser=None,
        ),
        transport=tp,
        timeout=HTTPTimeout(),
        collection_parser=CollectionParser,
        middlewares=[],
        error_parser=error_parser,
    )
    resp = (proxy.delete({})).json
    assert resp == {"detail": "accepted"}


def test_route_proxy_options() -> None:
    http_resp = HTTPResponse(202, {}, {"detail": "accepted"})
    tp = FakeTransport(http_resp)

    proxy: SyncRouteProxy[Any, Any, Any] = SyncRouteProxy(
        "dummy",
        "dummies",
        "http://dummy/",
        ApiRoutes(
            path="/",
            contract={"OPTIONS": (Request, None)},
            collection_contract=None,
            collection_path=None,
            collection_parser=None,
        ),
        transport=tp,
        timeout=HTTPTimeout(),
        collection_parser=CollectionParser,
        middlewares=[],
        error_parser=error_parser,
    )
    resp = (proxy.options({})).json
    assert resp == {"detail": "accepted"}


def test_unregistered_collection(echo_middleware: SyncAbstractTransport):
    proxy: SyncRouteProxy[Any, Any, Any] = SyncRouteProxy(
        "dummy",
        "dummies",
        "http://dummy/",
        ApiRoutes(
            path="/",
            contract={"GET": (Request, None)},
            collection_path=None,
            collection_contract=None,
            collection_parser=None,
        ),
        transport=echo_middleware,
        timeout=HTTPTimeout(),
        collection_parser=CollectionParser,
        middlewares=[
            SyncHTTPAuthorizationMiddleware("Bearer", "abc"),
            SyncHTTPAddHeadersMiddleware({"foo": "bar"}),
            SyncHTTPAddHeadersMiddleware({"Eggs": "egg"}),
        ],
        error_parser=error_parser,
    )
    for verb in ("get", "post", "put", "patch", "delete", "options", "head"):
        with pytest.raises(UnregisteredRouteException) as ctx:
            meth = getattr(proxy, f"collection_{verb}")
            meth({})
        assert (
            str(ctx.value) == f"Unregistered route '{verb.upper()}' "
            f"in resource 'dummies' in client 'dummy'"
        )
