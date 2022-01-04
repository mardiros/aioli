"""Cut the circuit in case a service is down."""

from typing import Any, Iterable, Optional, cast

from purgatory import AsyncAbstractUnitOfWork, AsyncCircuitBreakerFactory
from purgatory.typing import TTL, Hook, Threshold

from blacksmith.domain.exceptions import HTTPError
from blacksmith.domain.model.http import HTTPRequest, HTTPResponse
from blacksmith.typing import ClientName, HttpMethod, Path

from .base import AsyncHTTPMiddleware, AsyncMiddleware
from .prometheus import AsyncPrometheusMetrics

Listeners = Optional[Iterable[Hook]]


def exclude_httpx_4xx(exc: HTTPError):
    """Exclude client side http errors."""
    return exc.is_client_error


class GaugeStateValue:
    CLOSED = 0
    HALF_OPEN = 1
    OPEN = 2


class PrometheusHook:
    def __init__(self, prometheus_metrics: AsyncPrometheusMetrics):
        self.prometheus_metrics = prometheus_metrics

    def __call__(self, circuit_name: str, evt_type: str, payload: Any) -> None:
        if evt_type == "state_changed":
            state = {
                "closed": GaugeStateValue.CLOSED,
                "half-opened": GaugeStateValue.HALF_OPEN,
                "opened": GaugeStateValue.OPEN,
            }[payload.state]
            self.prometheus_metrics.blacksmith_circuit_breaker_state.labels(
                circuit_name
            ).set(state)
        elif evt_type == "failed":
            self.prometheus_metrics.blacksmith_circuit_breaker_error.labels(
                circuit_name
            ).inc()


class AsyncCircuitBreaker(AsyncHTTPMiddleware):
    """
    Prevent cascading failure.

    The circuit breaker is based on `purgatory`_, the middleware create
    one circuit breaker per client_name. The parameters are forwarded
    to all the clients. This middleware does not give the possibility to
    adapt a threshold or the time the circuit is opened per clients.

    .. _`purgatory`: https://pypi.org/project/purgatory-circuitbreaker/
    """

    def __init__(
        self,
        threshold: Threshold = 5,
        ttl: TTL = 30,
        listeners: Listeners = None,
        uow: Optional[AsyncAbstractUnitOfWork] = None,
        prometheus_metrics: Optional[AsyncPrometheusMetrics] = None,
    ):
        self.circuit_breaker = AsyncCircuitBreakerFactory(
            default_threshold=threshold,
            default_ttl=ttl,
            exclude=[(HTTPError, exclude_httpx_4xx)],
            uow=uow,
        )
        if prometheus_metrics:
            self.circuit_breaker.add_listener(PrometheusHook(prometheus_metrics))
        if listeners:
            for listener in listeners:
                self.circuit_breaker.add_listener(listener)

    async def initialize(self):
        await self.circuit_breaker.initialize()

    def __call__(self, next: AsyncMiddleware) -> AsyncMiddleware:
        async def handle(
            req: HTTPRequest, method: HttpMethod, client_name: ClientName, path: Path
        ) -> HTTPResponse:

            async with await self.circuit_breaker.get_breaker(client_name):
                resp = await next(req, method, client_name, path)
            return cast(HTTPResponse, resp)

        return handle