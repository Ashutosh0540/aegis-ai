"""
Prometheus metrics middleware.

Sibling to `AuditRequestMiddleware` rather than a merge into it: audit
events are business/security records (who did what, stored in Postgres,
queried per-org through a normal service+router), while these are
process-level counters/histograms scraped by Prometheus over HTTP. Same
per-request timing shape, different storage model and consumer, so two
small middlewares are clearer than one middleware serving two concerns.

Route *templates* are used for the `path` label (e.g.
`/api/v1/organizations/{org_id}/documents`), not raw request paths — using
raw paths would let path params (UUIDs) explode metric cardinality.
Starlette resolves `request.scope["route"]` during `call_next`, so it's
read after awaiting, mirroring how `AuditRequestMiddleware` reads
`request.path_params` only after the response comes back.
"""
import time

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

_SKIP_PATHS = {"/metrics", "/health", "/api/docs", "/api/redoc", "/openapi.json"}

# A dedicated registry (rather than the global default) so repeated app
# creation in tests doesn't hit prometheus_client's "duplicated timeseries"
# error across test modules that each import app.main.
REGISTRY = CollectorRegistry()

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests processed",
    ["method", "path", "status_code"],
    registry=REGISTRY,
)

REQUEST_LATENCY_SECONDS = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "path"],
    registry=REGISTRY,
)


def _route_template(request: Request) -> str:
    """Best-effort route template for the path label; falls back to the
    raw path for unmatched routes (404s) since there's no template then."""
    route = request.scope.get("route")
    if route is not None and getattr(route, "path", None):
        return route.path
    return request.url.path


class PrometheusMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in _SKIP_PATHS:
            return await call_next(request)

        started = time.monotonic()
        response = await call_next(request)
        elapsed = time.monotonic() - started

        path_label = _route_template(request)
        REQUEST_COUNT.labels(
            method=request.method, path=path_label, status_code=response.status_code
        ).inc()
        REQUEST_LATENCY_SECONDS.labels(method=request.method, path=path_label).observe(elapsed)

        return response


def render_metrics() -> bytes:
    """Serialize the current registry in Prometheus text-exposition format."""
    return generate_latest(REGISTRY)


METRICS_CONTENT_TYPE = CONTENT_TYPE_LATEST
