import base64

from blacksmith import (
    AsyncClientFactory,
    AsyncConsulDiscovery,
    AsyncHTTPAuthorizationMiddleware,
)


class AsyncBasicAuthorization(AsyncHTTPAuthorizationMiddleware):
    def __init__(self, username, password):
        userpass = f"{username}:{password}".encode()
        b64head = base64.b64encode(userpass).decode("ascii")
        header = f"Basic {b64head}"
        return super().__init__("Basic", header)


sd = AsyncConsulDiscovery()
auth = AsyncBasicAuthorization("alice", "secret")
cli = AsyncClientFactory(sd).add_middleware(auth)
