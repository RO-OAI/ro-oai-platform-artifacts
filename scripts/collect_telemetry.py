#!/usr/bin/env python3
"""Collect the steady-state platform telemetry reported in the paper.

Aggregates per-service traffic, latency percentiles, reliability, resource use
and database health over a trailing window (default 15 days, matching the
Prometheus retention of the production cluster) and writes ``telemetry.json``.

Usage:
    PROMETHEUS_URL=https://prometheus.example.org python collect_telemetry.py
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os

from promclient import Prometheus

# Traefik service identifiers for the user-facing components.
SERVICES = {
    "backend": "default-ro-oai-backend-service-8080@kubernetes",
    "frontend": "default-ro-oai-frontend-service-80@kubernetes",
    "website": "default-ro-oai-website-service-80@kubernetes",
    "admin": "default-ro-oai-admin-80@kubernetes",
    "keycloak": "keycloak-keycloak-8080@kubernetes",
    "evaluator": "default-ro-oai-evaluator-8000@kubernetes",
}

# Workload pod prefixes for resource accounting.
APPS = [
    "ro-oai-backend", "ro-oai-frontend", "ro-oai-evaluator",
    "ro-oai-website", "ro-oai-admin", "rabbitmq", "neural-empires",
]

DATABASES = ("ro_oai_prod", "keycloak", "neural_empires")


def mb(value: float | None) -> float | None:
    return round(value / 1e6, 1) if value else None


def collect_http(prom: Prometheus, window: str) -> dict:
    traffic = {}
    for name, svc in SERVICES.items():
        total = prom.scalar(
            f'sum(increase(traefik_service_requests_total{{service="{svc}"}}[{window}]))')
        err5 = prom.scalar(
            f'sum(increase(traefik_service_requests_total'
            f'{{service="{svc}",code=~"5.."}}[{window}]))') or 0.0
        err4 = prom.scalar(
            f'sum(increase(traefik_service_requests_total'
            f'{{service="{svc}",code=~"4.."}}[{window}]))') or 0.0
        latency = {}
        for quantile in (0.5, 0.95, 0.99):
            latency[f"p{int(quantile * 100)}"] = prom.scalar(
                f'histogram_quantile({quantile}, sum by (le) (rate('
                f'traefik_service_request_duration_seconds_bucket'
                f'{{service="{svc}"}}[{window}])))')
        traffic[name] = {
            "requests_total": total,
            "errors_5xx": err5,
            "errors_4xx": err4,
            "err_rate_5xx_pct": (100.0 * err5 / total) if total else None,
            "latency_seconds": latency,
        }
    return traffic


def collect_resources(prom: Prometheus, window: str) -> dict:
    resources = {}
    for app in APPS:
        sel = f'namespace="default",pod=~"{app}.*",container!=""'
        resources[app] = {
            "mem_avg_mb": mb(prom.scalar(
                f'avg(avg_over_time(container_memory_working_set_bytes{{{sel}}}[{window}]))')),
            "mem_peak_mb": mb(prom.scalar(
                f'max(max_over_time(container_memory_working_set_bytes{{{sel}}}[{window}]))')),
            "cpu_avg_cores": _round3(prom.scalar(
                f'sum(rate(container_cpu_usage_seconds_total{{{sel}}}[{window}]))')),
            "cpu_peak_cores": _round3(prom.scalar(
                f'max_over_time(sum(rate(container_cpu_usage_seconds_total'
                f'{{{sel}}}[5m]))[{window}:5m])')),
            "restarts": prom.scalar(
                f'sum(increase(kube_pod_container_status_restarts_total'
                f'{{namespace="default",pod=~"{app}.*"}}[{window}]))'),
            "replicas_min": prom.scalar(
                f'min_over_time(count(kube_pod_info'
                f'{{namespace="default",pod=~"{app}.*"}})[{window}:5m])'),
            "replicas_max": prom.scalar(
                f'max_over_time(count(kube_pod_info'
                f'{{namespace="default",pod=~"{app}.*"}})[{window}:5m])'),
        }
    return resources


def collect_database(prom: Prometheus, window: str) -> dict:
    db = {}
    for name in DATABASES:
        db[name] = {
            "size_mb": mb(prom.scalar(f'pg_database_size_bytes{{datname="{name}"}}')),
            "peak_connections": prom.scalar(
                f'max_over_time(pg_stat_activity_count{{datname="{name}"}}[{window}])'),
            "commits": prom.scalar(
                f'increase(pg_stat_database_xact_commit{{datname="{name}"}}[{window}])'),
        }
    db["max_connections"] = prom.scalar("pg_settings_max_connections")
    db["cache_hit_ratio_prod"] = prom.scalar(
        'sum(rate(pg_stat_database_blks_hit{datname="ro_oai_prod"}[15d])) / '
        '(sum(rate(pg_stat_database_blks_hit{datname="ro_oai_prod"}[15d])) + '
        'sum(rate(pg_stat_database_blks_read{datname="ro_oai_prod"}[15d])))')
    return db


def _round3(value: float | None) -> float | None:
    return round(value, 3) if value else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--window", default="15d",
                        help="trailing range for aggregation (default: 15d)")
    parser.add_argument("--out", default="data/telemetry.json")
    args = parser.parse_args()

    prom = Prometheus()
    snapshot = {
        "collected_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "window": args.window,
        "http_traffic": collect_http(prom, args.window),
        "peak_agg_req_per_s": prom.scalar(
            f'max_over_time(sum(rate(traefik_service_requests_total[5m]))[{args.window}:5m])'),
        "resources": collect_resources(prom, args.window),
        "database": collect_database(prom, args.window),
        "cluster": {
            "nodes": prom.scalar("count(count by (instance) (node_uname_info))"),
            "cpu_capacity": prom.scalar(
                'sum(kube_node_status_capacity{resource="cpu"}) / 2'),
            "mem_capacity_gb": mb(prom.scalar(
                'sum(kube_node_status_capacity{resource="memory"}) / 2')),
        },
    }

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(snapshot, fh, indent=2)
        fh.write("\n")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
