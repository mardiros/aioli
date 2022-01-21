"""Collect metrics based on prometheus."""
from typing import TYPE_CHECKING, Any, List, Optional

import pkg_resources

if TYPE_CHECKING:
    try:
        import prometheus_client  # type: ignore
    except ImportError:
        pass
    Registry = Optional["prometheus_client.CollectorRegistry"]
else:
    Registry = Any


class PrometheusMetrics:
    def __init__(
        self, buckets: Optional[List[float]] = None, registry: Registry = None
    ) -> None:
        from prometheus_client import (  # type: ignore
            REGISTRY,
            Counter,
            Gauge,
            Histogram,
        )

        if registry is None:
            registry = REGISTRY
        if buckets is None:
            buckets = [0.05 * 2 ** x for x in range(10)]
        version_info = {"version": pkg_resources.get_distribution("blacksmith").version}
        self.blacksmith_info = Gauge(
            "blacksmith_info",
            "Blacksmith Information",
            registry=registry,
            labelnames=list(version_info.keys()),
        )
        self.blacksmith_info.labels(**version_info).set(1)

        self.blacksmith_request_latency_seconds = Histogram(
            "blacksmith_request_latency_seconds",
            "Latency of http requests in seconds",
            buckets=buckets,
            registry=registry,
            labelnames=["client_name", "method", "path", "status_code"],
        )

        self.blacksmith_circuit_breaker_error = Counter(
            "blacksmith_circuit_breaker_error",
            "Count the circuit breaker exception raised",
            registry=registry,
            labelnames=["client_name"],
        )

        self.blacksmith_circuit_breaker_state = Gauge(
            "blacksmith_circuit_breaker_state",
            "State of the circuit breaker. 0 is closed, 1 is half-opened, 2 is opened.",
            registry=registry,
            labelnames=["client_name"],
        )