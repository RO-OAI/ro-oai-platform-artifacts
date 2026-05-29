#!/usr/bin/env python3
"""Freeze the raw Prometheus API responses behind every number in the paper.

The production Prometheus keeps only ~15 days of data, so the verbatim API
payloads are archived under ``data/raw_snapshots/`` to keep the results
verifiable after the live series age out. Each file stores the query, the
endpoint, a capture timestamp, and the response.

Note: the snapshots shipped in this repository have had network identifiers
(hostnames, IPs, pod names) redacted; metric values are unchanged. Re-running
this script against a live endpoint regenerates them with that endpoint's own
labels.

Usage:
    PROMETHEUS_URL=https://prometheus.example.org python snapshot_raw.py
"""

from __future__ import annotations

import datetime as dt
import json
import os

from promclient import Prometheus

BACKEND = "default-ro-oai-backend-service-8080@kubernetes"
FRONTEND = "default-ro-oai-frontend-service-80@kubernetes"
WEBSITE = "default-ro-oai-website-service-80@kubernetes"
WINDOW = "15d"

# (key, query) pairs: instant queries backing the tables and scalar claims.
INSTANT = [
    ("buildinfo_status", "prometheus_build_info"),
    ("tsdb_head_series", "prometheus_tsdb_head_series"),
    ("node_uname", "node_uname_info"),
    ("node_cpu_capacity", 'kube_node_status_capacity{resource="cpu"}'),
    ("node_mem_capacity", 'kube_node_status_capacity{resource="memory"}'),
    ("deployment_replicas", 'kube_deployment_spec_replicas{namespace="default"}'),
    ("svc_requests_total_15d",
     'sum by (service) (increase(traefik_service_requests_total[15d]))'),
    ("backend_requests_15d",
     f'sum(increase(traefik_service_requests_total{{service="{BACKEND}"}}[{WINDOW}]))'),
    ("backend_5xx_15d",
     f'sum(increase(traefik_service_requests_total{{service="{BACKEND}",code=~"5.."}}[{WINDOW}]))'),
    ("frontend_requests_15d",
     f'sum(increase(traefik_service_requests_total{{service="{FRONTEND}"}}[{WINDOW}]))'),
    ("frontend_5xx_15d",
     f'sum(increase(traefik_service_requests_total{{service="{FRONTEND}",code=~"5.."}}[{WINDOW}]))'),
    ("website_requests_15d",
     f'sum(increase(traefik_service_requests_total{{service="{WEBSITE}"}}[{WINDOW}]))'),
    ("peak_agg_req_per_s",
     'max_over_time(sum(rate(traefik_service_requests_total[5m]))[15d:5m])'),
    ("backend_p50",
     f'histogram_quantile(0.5, sum by (le) (rate(traefik_service_request_duration_seconds_bucket{{service="{BACKEND}"}}[{WINDOW}])))'),
    ("backend_p95",
     f'histogram_quantile(0.95, sum by (le) (rate(traefik_service_request_duration_seconds_bucket{{service="{BACKEND}"}}[{WINDOW}])))'),
    ("backend_p99",
     f'histogram_quantile(0.99, sum by (le) (rate(traefik_service_request_duration_seconds_bucket{{service="{BACKEND}"}}[{WINDOW}])))'),
    ("frontend_p95",
     f'histogram_quantile(0.95, sum by (le) (rate(traefik_service_request_duration_seconds_bucket{{service="{FRONTEND}"}}[{WINDOW}])))'),
    ("pg_db_size", "pg_database_size_bytes"),
    ("pg_max_connections", "pg_settings_max_connections"),
    ("pg_commits_prod_15d",
     'increase(pg_stat_database_xact_commit{datname="ro_oai_prod"}[15d])'),
    ("pg_cache_hit_prod_15d",
     'sum(rate(pg_stat_database_blks_hit{datname="ro_oai_prod"}[15d])) / '
     '(sum(rate(pg_stat_database_blks_hit{datname="ro_oai_prod"}[15d])) + '
     'sum(rate(pg_stat_database_blks_read{datname="ro_oai_prod"}[15d])))'),
    ("pg_peak_activity_prod",
     'max_over_time(pg_stat_activity_count{datname="ro_oai_prod"}[15d])'),
    ("mem_avg_by_pod",
     'avg by (pod) (avg_over_time(container_memory_working_set_bytes{namespace="default",container!=""}[15d]))'),
    ("mem_peak_by_pod",
     'max by (pod) (max_over_time(container_memory_working_set_bytes{namespace="default",container!=""}[15d]))'),
    ("restarts_by_pod_15d",
     'sum by (pod) (increase(kube_pod_container_status_restarts_total{namespace="default"}[15d]))'),
]


def capture_instant(prom: Prometheus, out_dir: str, key: str, query: str) -> str:
    payload = prom.raw("/api/v1/query", {"query": query})
    record = {
        "key": key,
        "endpoint": "query",
        "params": {"query": query},
        "captured_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": payload.get("status"),
        "response": payload,
    }
    _write(out_dir, key, record)
    return key


def capture_range(prom: Prometheus, out_dir: str, key: str, query: str,
                  start: int, end: int, step: int) -> str:
    payload = prom.raw("/api/v1/query_range",
                       {"query": query, "start": start, "end": end, "step": step})
    record = {
        "key": key,
        "endpoint": "query_range",
        "params": {"query": query, "start": start, "end": end, "step": step},
        "captured_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": payload.get("status"),
        "response": payload,
    }
    _write(out_dir, key, record)
    return key


def _write(out_dir: str, key: str, record: dict) -> None:
    with open(os.path.join(out_dir, f"{key}.json"), "w") as fh:
        json.dump(record, fh, indent=2)
        fh.write("\n")
    n = len(record["response"]["data"]["result"]) if record["status"] == "success" else "?"
    print(f"[{record['status']}] {key}: {n} series")


def main() -> None:
    prom = Prometheus()
    out_dir = os.path.join("data", "raw_snapshots")
    os.makedirs(out_dir, exist_ok=True)

    keys = [capture_instant(prom, out_dir, key, query) for key, query in INSTANT]

    backend_rate = f'sum(rate(traefik_service_requests_total{{service="{BACKEND}"}}[5m]))'
    keys.append(capture_range(
        prom, out_dir, "spike_backend_rate_hourly", backend_rate,
        _ts(2026, 5, 18), _ts(2026, 5, 29), 3600))
    keys.append(capture_range(
        prom, out_dir, "spike_backend_rate_1m_busiest",
        f'sum(rate(traefik_service_requests_total{{service="{BACKEND}"}}[1m]))',
        _ts(2026, 5, 23, 3), _ts(2026, 5, 23, 15), 60))

    index = {
        "captured_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "window": WINDOW,
        "note": "Verbatim Prometheus API responses backing the paper's empirical "
                "claims, archived before retention aged the data out.",
        "keys": keys,
    }
    _write_index(out_dir, index)
    print(f"captured {len(keys)} snapshots into {out_dir}")


def _write_index(out_dir: str, index: dict) -> None:
    with open(os.path.join(out_dir, "index.json"), "w") as fh:
        json.dump(index, fh, indent=2)
        fh.write("\n")


def _ts(year: int, month: int, day: int, hour: int = 0) -> int:
    return int(dt.datetime(year, month, day, hour, tzinfo=dt.timezone.utc).timestamp())


if __name__ == "__main__":
    main()
