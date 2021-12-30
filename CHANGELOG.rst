0.6.4 - Released at 2021-12-29
------------------------------
* Change the timeout exception outside httpx context manager 

0.6.3 - Released at 2021-12-29
------------------------------
* Expose the HttpCachingMiddleware in blacksmith namespace

0.6.2 - Released at 2021-12-29
------------------------------
* Fix case sensitivity in cache header

0.6.1 - Released at 2021-12-29
------------------------------
* make http caching serializer in middleware configurable

0.6.0 - Released at 2021-12-29
------------------------------
* Add a http caching middleware based on redis
* Update zipkin integration for starlette-zipkin 0.2

0.5.0 - Released at 2021-12-13
------------------------------
* Reverse order of middleware to be natural and intuitive on insert

0.4.2 - Released at 2021-12-13
------------------------------
* Update httpx version ^0.21.1

0.4.1 - Released at 2021-12-12
------------------------------
* Collect circuit breaker metrics in prometheus

0.4.0 - Released at 2021-12-12
------------------------------
 * Rename project to blacksmith (prometheus metrics name updated too)
 * Implement middleware as a pattern to inject data in http request and response

    * Breaking changes: auth keyword is replace by middleware. (Documentation updated)
    * Breaking changes: auth keyword is replace by middleware. (Documentation updated)


0.3.0 - Released at 2021-12-08
------------------------------
 * Replace `aioli_http_requests` Gauge by `aioli_request_latency_seconds` Histogram. (prometheus)

0.2.1 - Released at 2021-12-05
------------------------------
 * Add metadata in pyproject.toml for pypi

0.2.0 - Released at 2021-12-05
------------------------------
 * Implement consul discovery (see consul example)
 * Implement router discovery (see consul template example)
 * Add prometheus metrics support
 * Add zipkin tracing support

0.1.0 - Released at 2021-11-14
------------------------------
 * Initial release
