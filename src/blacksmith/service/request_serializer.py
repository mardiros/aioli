import abc
import json
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    List,
    Mapping,
    Optional,
    Sequence,
    Union,
    cast,
)
from urllib.parse import urlencode

from pydantic import BaseModel, SecretBytes, SecretStr
from pydantic.fields import FieldInfo

from blacksmith.domain.exceptions import UnregisteredContentTypeException
from blacksmith.domain.model.http import HTTPRequest
from blacksmith.domain.model.params import Request
from blacksmith.typing import HttpLocation, HTTPMethod, Url

# assume we can use deprecated stuff until we support both version
try:
    # pydantic 2
    from pydantic.deprecated.json import ENCODERS_BY_TYPE  # type: ignore
except ImportError:  # type: ignore # coverage: ignore
    # pydantic 1
    from pydantic.json import ENCODERS_BY_TYPE  # type: ignore  # coverage: ignore

if TYPE_CHECKING:
    from pydantic.typing import IntStr
else:
    IntStr = str


PATH: HttpLocation = "path"
HEADER: HttpLocation = "headers"
QUERY: HttpLocation = "querystring"
BODY: HttpLocation = "body"
simpletypes = Union[str, int, float, bool]


class AbstractRequestBodySerializer(abc.ABC):
    """Request body serializer."""

    @abc.abstractmethod
    def accept(self, content_type: str) -> bool:
        """Return true in case it can handle the request."""

    @abc.abstractmethod
    def serialize(self, body: Union[Dict[str, Any], Sequence[Any]]) -> str:
        """
        Serialize a python simple types to a python request body.

        The body received here is the extracted object from the request model.
        """


class JsonRequestSerializer(AbstractRequestBodySerializer):
    """The default serializer that serialize to json"""

    def accept(self, content_type: str) -> bool:
        return content_type.startswith("application/json")

    def serialize(self, body: Union[Dict[str, Any], Sequence[Any]]) -> str:
        return json.dumps(body, cls=JSONEncoder)


class UrlencodedRequestSerializer(AbstractRequestBodySerializer):
    """A serializer for application/x-www-form-urlencoded request."""

    def accept(self, content_type: str) -> bool:
        return content_type == "application/x-www-form-urlencoded"

    def serialize(self, body: Union[Dict[str, Any], Sequence[Any]]) -> str:
        return urlencode(body, doseq=True)


class JSONEncoder(json.JSONEncoder):
    def default(self, o: Any) -> Any:
        for typ, serializer in ENCODERS_BY_TYPE.items():
            if isinstance(o, typ):
                return serializer(o)
        return super(JSONEncoder, self).default(o)


def get_fields(model: BaseModel) -> Mapping[str, FieldInfo]:
    if hasattr(model, "model_fields"):
        return model.model_fields
    return model.__fields__  # coverage: ignore - pydantic 1


def get_location(field: Any) -> HttpLocation:
    # field is of type FieldInfo, which differ on pydantic 2 and pydantic 1
    if hasattr(field, "json_schema_extra"):
        extra = field.json_schema_extra
    elif hasattr(field, "field_info"):
        extra = field.field_info.extra
    else:
        raise ValueError(f"{field} is not a FieldInfo")
    return extra["location"]


def get_value(v: Union[simpletypes, SecretStr, SecretBytes]) -> simpletypes:
    if hasattr(v, "get_secret_value"):
        return getattr(v, "get_secret_value")()
    return v  # type: ignore


def serialize_part(req: "Request", part: Dict[IntStr, Any]) -> Dict[str, simpletypes]:
    return {
        **{
            k: get_value(v)
            for k, v in req.dict(  # pydantic 1
                include=part,
                by_alias=True,
                exclude_none=True,
                exclude_defaults=False,
            ).items()
            if v is not None
        },
        **{
            k: get_value(v)
            for k, v in req.dict(  # pydantic 1
                include=part,
                by_alias=True,
                exclude_none=False,
                exclude_unset=True,
                exclude_defaults=False,
            ).items()
        },
    }


_SERIALIZERS: List[AbstractRequestBodySerializer] = [
    JsonRequestSerializer(),
    UrlencodedRequestSerializer(),
]


def register_request_body_serializer(serializer: AbstractRequestBodySerializer) -> None:
    """Register a serializer to serialize some kind of request."""
    _SERIALIZERS.insert(0, serializer)


def unregister_request_body_serializer(
    serializer: AbstractRequestBodySerializer,
) -> None:
    """
    Unregister a serializer previously added.

    Usefull for testing purpose.
    """
    _SERIALIZERS.remove(serializer)


def serialize_body(
    req: "Request", body: Dict[str, str], content_type: Optional[str] = None
) -> str:
    """
    Serialize the body of the request.

    Note that the content_type is optional, but if it is set,

    the request will contains
    """
    if not body and not content_type:
        return ""
    content_type = content_type or "application/json"
    for serializer in _SERIALIZERS:
        if serializer.accept(content_type):
            return serializer.serialize(serialize_part(req, body))
    raise UnregisteredContentTypeException(content_type, req)


def serialize_request(
    method: HTTPMethod,
    url_pattern: Url,
    request_model: Request,
) -> HTTPRequest:
    """
    Serialize :class:`blacksmith.Request` subclasses to :class:`blacksmith.HTTPRequest`.

    While processing an http request, the request models are serialize to an
    intermediate object :class:`blacksmith.HTTPRequest`, that will be passed over
    middleware and finally to the transport in order to build the final http request.

    Note that the body of the :class:`blacksmith.HTTPRequest` is a string, here,
    serialized by a registered serializer.
    """
    req = HTTPRequest(method=method, url_pattern=url_pattern)
    fields_by_loc: Dict[HttpLocation, Dict[IntStr, Any]] = {
        HEADER: {},
        PATH: {},
        QUERY: {},
        BODY: {},
    }
    for name, field in get_fields(request_model).items():
        loc = get_location(field)
        fields_by_loc[loc].update({name: ...})

    headers = serialize_part(request_model, fields_by_loc[HEADER])
    req.headers = {key: str(val) for key, val in headers.items()}
    req.path = serialize_part(request_model, fields_by_loc[PATH])
    req.querystring = cast(
        Dict[str, Union[simpletypes, List[simpletypes]]],
        serialize_part(request_model, fields_by_loc[QUERY]),
    )

    req.body = serialize_body(
        request_model,
        fields_by_loc[BODY],
        cast(Optional[str], headers.get("Content-Type")),
    )
    return req