import json
import warnings
from datetime import datetime
from typing import Any, Optional

import pytest
from pydantic import BaseModel, Field, SecretStr
from result import Err, Ok, UnwrapError

from blacksmith.domain.error import default_error_parser

# type: ignore
from blacksmith.domain.exceptions import HTTPError, NoResponseSchemaException
from blacksmith.domain.model import (
    CollectionIterator,
    CollectionParser,
    HeaderField,
    HTTPRequest,
    HTTPResponse,
    PathInfoField,
    PostBodyField,
    QueryStringField,
    Request,
    Response,
    ResponseBox,
)
from blacksmith.domain.model.http import HTTPTimeout, parse_header_links
from blacksmith.domain.model.params import (
    QUERY,
    JSONEncoder,
    get_location,
    serialize_part,
)


class MyErrorFormat(BaseModel):
    status_code: int = Field(...)
    message: str = Field(...)
    detail: str = Field(...)


def error_parser(error: HTTPError) -> MyErrorFormat:
    return MyErrorFormat(
        status_code=error.status_code,
        **error.json,  # type: ignore
    )


class GetResponse(Response):
    name: str
    age: int


def test_json_encoder() -> None:
    assert (
        json.dumps({"date": datetime(2020, 10, 5)}, cls=JSONEncoder)
        == '{"date": "2020-10-05T00:00:00"}'
    )

    with pytest.raises(TypeError) as ctx:
        json.dumps({"oops": object()}, cls=JSONEncoder)
    assert str(ctx.value) == "Object of type object is not JSON serializable"


def test_timeout_eq() -> None:
    assert HTTPTimeout() == HTTPTimeout()
    assert HTTPTimeout(10) == HTTPTimeout(10)
    assert HTTPTimeout(10, 20) == HTTPTimeout(10, 20)


def test_timeout_neq() -> None:
    assert HTTPTimeout() != HTTPTimeout(42)
    assert HTTPTimeout(42) != HTTPTimeout(42, 42)
    assert HTTPTimeout(42, 42) != HTTPTimeout(42, 43)


def test_request_url() -> None:
    req = HTTPRequest(
        method="GET",
        url_pattern="/foo/{name}/bar/{id}",
        path={"id": 42, "name": "John"},
        querystring={},
        headers={"H": "h"},
        body="",
    )

    assert req.url == "/foo/John/bar/42"


def test_serialize_part() -> None:
    class Dummy(Request):
        x_message_id: int = HeaderField(default=123, alias="X-Message-Id")
        name: str = PostBodyField()
        age: int = PostBodyField(default=10)
        city: Optional[str] = PostBodyField(None)
        state: Optional[str] = PostBodyField(None)
        country: str = PostBodyField()

    dummy = Dummy(name="Jane", country="FR", city="Saint Palais s/mer", state=None)
    obj = serialize_part(
        dummy,
        {
            "name": ...,
            "age": ...,
            "city": ...,
            "state": ...,
            "country": ...,
        },
    )
    assert obj == {
        "name": "Jane",
        "age": 10,
        "city": "Saint Palais s/mer",
        "state": None,
        "country": "FR",
    }


def test_serialize_part_default_with_none() -> None:
    class Dummy(Request):
        name: str = PostBodyField()
        age: Optional[int] = PostBodyField(default=10)

    dummy = Dummy(name="Jane", age=None)
    obj = serialize_part(
        dummy,
        {
            "name": ...,
            "age": ...,
            "created_at": ...,
        },
    )
    assert obj == {
        "name": "Jane",
        "age": None,
    }


def test_get_location_from_pydantic_v2() -> None:
    class DummyFieldInfo:
        json_schema_extra = {"location": QUERY}

    assert get_location(DummyFieldInfo()) == QUERY


def test_get_location_from_pydantic_v1() -> None:
    class DummyFieldInfo:
        class field_info:
            extra = {"location": QUERY}

    assert get_location(DummyFieldInfo()) == QUERY


def test_get_location_raises_value_error() -> None:
    class Dummy:
        def __str__(self):
            return "dummy"

    with pytest.raises(ValueError) as ctx:
        get_location(Dummy())
    assert str(ctx.value) == "dummy is not a FieldInfo"


def test_param_to_req() -> None:
    class Dummy(Request):
        x_message_id: int = HeaderField(default=123, alias="X-Message-Id")
        x_token: SecretStr = HeaderField(alias="X-Token")
        x_sub_id: Optional[int] = HeaderField(default=None, alias="X-Sub-Id")
        name: str = PathInfoField()
        country: str = QueryStringField()
        state: Optional[str] = QueryStringField(default=None)
        age: int = PostBodyField()
        birthdate: datetime = PostBodyField()
        password: SecretStr = PostBodyField()

    dummy = Dummy(
        name="Jane",
        country="FR",
        age=23,
        birthdate=datetime(1956, 12, 13),
        password=SecretStr("myownsecret"),
        **{"X-Token": "plokiploki"},  # type: ignore
    )
    req = dummy.to_http_request("GET", "/dummies/{name}")
    assert req.url == "/dummies/Jane"
    assert req.headers == {"X-Message-Id": "123", "X-Token": "plokiploki"}
    assert req.querystring == {"country": "FR"}
    assert json.loads(req.body) == {
        "age": 23,
        "birthdate": "1956-12-13T00:00:00",
        "password": "myownsecret",
    }


def test_patch_none_values() -> None:
    class Dummy(Request):
        x_message_id: int = HeaderField(default=123, alias="X-Message-Id")
        x_sub_id: Optional[int] = HeaderField(None, alias="X-Sub-Id")
        name: str = PathInfoField()
        country: str = PostBodyField()
        age: int = PostBodyField(default=10)
        state: Optional[str] = PostBodyField(None)
        city: Optional[str] = PostBodyField(None)

    dummy = Dummy(name="Jane", country="FR", state=None)
    req = dummy.to_http_request("GET", "/dummies/{name}")
    assert req.url == "/dummies/Jane"
    assert req.headers == {"X-Message-Id": "123"}
    assert req.querystring == {}
    assert json.loads(req.body) == {"age": 10, "country": "FR", "state": None}


def test_parse_header_links() -> None:
    links = parse_header_links("")
    assert links == []
    links = parse_header_links(
        '<https://ne.xt/>; rel="next", <https://la.st/>; rel="last"'
    )
    assert links == [
        {"rel": "next", "url": "https://ne.xt/"},
        {"rel": "last", "url": "https://la.st/"},
    ]

    links = parse_header_links("<https://la.st/>")
    assert links == [{"url": "https://la.st/"}]


def test_collection_parser() -> None:
    resp = HTTPResponse(
        200,
        {
            "Total-Count": "20",
            "link": '<https://dummy/?page=2>; rel="next", '
            '<https://dummy/?page=4>; rel="last"',
        },
        [{"id": 1}, {"id": 1}],
    )
    parsed = CollectionParser(resp)
    assert parsed.meta.count == 2
    assert parsed.meta.total_count == 20
    assert parsed.meta.links == {
        "last": {"rel": "last", "url": "https://dummy/?page=4"},
        "next": {"rel": "next", "url": "https://dummy/?page=2"},
    }


def test_response_box() -> None:
    resp: ResponseBox[GetResponse, MyErrorFormat] = ResponseBox(
        Ok(
            HTTPResponse(
                200,
                {},
                {
                    "name": "Alice",
                    "age": 24,
                    "useless": True,
                },
            )
        ),
        GetResponse,
        "GET",
        "",
        "",
        "",
        error_parser=error_parser,
    )
    alice = GetResponse(name="Alice", age=24)
    bob = GetResponse(name="Bob", age=40)
    assert resp.is_ok()
    assert resp.is_err() is False
    assert resp.as_result() == Ok(alice)
    assert resp.as_optional() == Ok(alice)
    assert resp.unwrap() == alice
    with pytest.raises(UnwrapError):
        assert resp.unwrap_err()

    assert resp.unwrap_or(bob) == alice
    assert resp.unwrap_or_else(lambda err: bob) == alice
    assert resp.unwrap_or_raise(ValueError) == alice

    assert resp.map(lambda x: x.name) == Ok("Alice")  # type: ignore
    assert resp.map_or("Bob", lambda x: x.name) == "Alice"  # type: ignore
    assert resp.map_or_else(lambda: "Bob", lambda x: x.name) == "Alice"  # type: ignore
    assert resp.map_err(lambda err: err.status_code) == Ok(alice)  # type: ignore

    assert resp.and_then(lambda x: x.name) == "Alice"  # type: ignore
    assert resp.or_else(lambda err: err.status_code) == Ok(alice)  # type: ignore

    assert resp.expect("To never fail") == alice
    with pytest.raises(UnwrapError):
        assert resp.expect_err("To always fail")

    with warnings.catch_warnings(record=True) as ctx:
        warnings.simplefilter("always")
        assert resp.response.dict() == {"age": 24, "name": "Alice"}
    assert [str(w.message) for w in ctx][0] == (
        ".response is deprecated, use .unwrap() instead"
    )

    assert resp.json == {"age": 24, "name": "Alice", "useless": True}


def test_response_box_err() -> None:
    bob = GetResponse(name="Bob", age=40)
    http_error = HTTPError(
        "500 Internal Server Error",
        HTTPRequest(method="GET", url_pattern="/"),
        HTTPResponse(
            500,
            {},
            {
                "message": "Internal Server Error",
                "detail": "too many connections",
            },
        ),
    )
    my_parsed_error = MyErrorFormat(
        status_code=500,
        message="Internal Server Error",
        detail="too many connections",
    )
    resp: ResponseBox[GetResponse, MyErrorFormat] = ResponseBox(
        Err(http_error),
        GetResponse,
        "GET",
        "/",
        "",
        "",
        error_parser=error_parser,
    )
    assert resp.is_err()
    assert resp.is_ok() is False
    assert resp.unwrap_err() == my_parsed_error
    assert resp.json == {
        "message": "Internal Server Error",
        "detail": "too many connections",
    }

    assert resp.unwrap_or(bob) == bob
    assert resp.unwrap_or_else(lambda err: bob) == bob
    with pytest.raises(ValueError) as ctx:
        resp.unwrap_or_raise(ValueError)
    assert ctx.value.args[0] == my_parsed_error

    assert resp.map(lambda x: x.name) == Err(my_parsed_error)  # type: ignore
    assert resp.map_or("Bob", lambda x: x.name) == "Bob"  # type: ignore
    assert resp.map_or_else(lambda: "Bob", lambda x: x.name) == "Bob"  # type: ignore
    assert resp.map_err(lambda err: err.status_code) == Err(500)  # type: ignore

    assert resp.and_then(lambda x: x.name) == Err(my_parsed_error)  # type: ignore
    assert resp.or_else(lambda err: err.status_code) == 500  # type: ignore

    with pytest.raises(UnwrapError):
        assert resp.expect("To never fail")
    assert resp.expect_err("To always fail") == my_parsed_error

    with warnings.catch_warnings(record=True) as ctx_warn:
        warnings.simplefilter("always")
        with pytest.raises(HTTPError) as ctx_err:
            resp.response.dict()
    assert [str(w.message) for w in ctx_warn] == [
        ".response is deprecated, use .unwrap() instead"
    ]
    assert ctx_err.value.json == {
        "detail": "too many connections",
        "message": "Internal Server Error",
    }

    with pytest.raises(UnwrapError):
        assert resp.unwrap()


def test_response_box_err_default_handler() -> None:
    http_error = HTTPError(
        "500 Internal Server Error",
        HTTPRequest(method="GET", url_pattern="/"),
        HTTPResponse(
            500,
            {},
            {
                "message": "Internal Server Error",
                "detail": "too many connections",
            },
        ),
    )
    resp = ResponseBox(
        Err(http_error),
        GetResponse,
        "GET",
        "/",
        "",
        "",
        error_parser=default_error_parser,  # type: ignore
    )
    assert resp.unwrap_err() == http_error


def test_response_box_no_schema() -> None:
    resp: ResponseBox[GetResponse, MyErrorFormat] = ResponseBox(
        Ok(
            HTTPResponse(
                200,
                {},
                {
                    "name": "Alice",
                    "age": 24,
                    "useless": True,
                },
            )
        ),
        None,
        "GET",
        "/dummies",
        "Dummy",
        "api",
        error_parser=error_parser,
    )

    with pytest.raises(NoResponseSchemaException) as ctx:
        assert resp.as_result()
    assert (
        str(ctx.value)
        == "No response schema in route 'GET /dummies' in resource'Dummy' "
        "in client 'api'"
    )

    assert resp.as_optional() == Ok(None)

    with pytest.raises(NoResponseSchemaException) as ctx:
        assert resp.unwrap()

    with warnings.catch_warnings(record=True) as ctx_warn:
        warnings.simplefilter("always")
        with pytest.raises(NoResponseSchemaException) as ctx:
            assert resp.response
    assert (
        str(ctx.value)
        == "No response schema in route 'GET /dummies' in resource'Dummy' "
        "in client 'api'"
    )
    assert [str(w.message) for w in ctx_warn] == [
        ".response is deprecated, use .unwrap() instead"
    ]


def test_collection_iterator() -> None:
    collec: CollectionIterator[Any] = CollectionIterator(
        HTTPResponse(
            200,
            {"Total-Count": "5"},
            [
                {
                    "name": "Alice",
                    "age": 24,
                    "useless": True,
                },
                {
                    "name": "Bob",
                    "age": 42,
                },
            ],
        ),
        GetResponse,
        CollectionParser,
    )
    assert collec.meta.count == 2
    assert collec.meta.total_count == 5
    list_collec = [res.dict() for res in collec]
    assert list_collec == [
        {
            "name": "Alice",
            "age": 24,
        },
        {
            "name": "Bob",
            "age": 42,
        },
    ]
