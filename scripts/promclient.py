"""Minimal read-only client for the Prometheus HTTP API.

The endpoint is taken from the ``PROMETHEUS_URL`` environment variable so the
scripts carry no infrastructure detail. Point it at any Prometheus that scrapes
an equivalent stack (Traefik, kube-state-metrics, node-exporter,
postgres-exporter) to reproduce the collection end to end::

    export PROMETHEUS_URL=https://your-prometheus.example.org
"""

from __future__ import annotations

import json
import os
import ssl
import urllib.parse
import urllib.request
from typing import Any


class PrometheusError(RuntimeError):
    pass


def _ssl_context() -> ssl.SSLContext | None:
    """Verify TLS using certifi's bundle when available; otherwise fall back to
    the system store. Set PROMETHEUS_INSECURE=1 to skip verification for
    self-signed endpoints (development only)."""
    if os.environ.get("PROMETHEUS_INSECURE") == "1":
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    try:
        import certifi  # optional dependency
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return None


class Prometheus:
    def __init__(self, base_url: str | None = None, timeout: int = 60):
        base_url = base_url or os.environ.get("PROMETHEUS_URL")
        if not base_url:
            raise PrometheusError(
                "Set PROMETHEUS_URL (e.g. https://prometheus.example.org) "
                "before running the collection scripts."
            )
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._ssl = _ssl_context()

    def _get(self, path: str, params: dict[str, Any]) -> dict:
        url = f"{self.base_url}{path}?{urllib.parse.urlencode(params)}"
        with urllib.request.urlopen(url, timeout=self.timeout, context=self._ssl) as resp:
            payload = json.load(resp)
        if payload.get("status") != "success":
            raise PrometheusError(f"query failed: {payload.get('error', payload)}")
        return payload

    def query(self, expr: str) -> list[dict]:
        """Instant query. Returns the raw ``result`` list."""
        return self._get("/api/v1/query", {"query": expr})["data"]["result"]

    def query_range(self, expr: str, start: int, end: int, step: int) -> list[dict]:
        """Range query over [start, end] (unix seconds) at ``step`` seconds."""
        return self._get(
            "/api/v1/query_range",
            {"query": expr, "start": start, "end": end, "step": step},
        )["data"]["result"]

    def scalar(self, expr: str) -> float | None:
        """First sample of an instant query as a float, or None if empty."""
        result = self.query(expr)
        if not result:
            return None
        return float(result[0]["value"][1])

    def raw(self, path: str, params: dict[str, Any]) -> dict:
        """Verbatim API payload, used when capturing snapshots."""
        return self._get(path, params)
