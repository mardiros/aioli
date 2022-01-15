from blacksmith import AsyncHTTPMiddleware, AsyncMiddleware
from blacksmith.domain.model import HTTPRequest, HTTPResponse
from blacksmith.typing import ClientName, HttpMethod, Path


class AsyncHTTPPrintMiddleware(AsyncHTTPMiddleware):
    """Inject data in http query on every requests."""

    def __call__(self, next: AsyncMiddleware) -> AsyncMiddleware:
        async def handle(
            req: HTTPRequest, method: HttpMethod, client_name: ClientName, path: Path
        ) -> HTTPResponse:
            print(f">>> {req}")
            resp = await next(req, method, client_name, path)
            print(f"<<< {resp}")
            return resp

        return handle