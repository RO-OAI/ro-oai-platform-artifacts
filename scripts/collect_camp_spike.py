#!/usr/bin/env python3
"""Recover the contest-load spike from the National Team Selection Camp.

The camp (21-25 May 2026) ran two timed selection contests that fall inside the
Prometheus retention window, so the backend request rate during those days is a
genuine contest-load signal rather than baseline traffic. This script samples
the backend request rate per hour over the surrounding window, summarises it per
day, and locates the busiest minute. Output: ``camp_spike.json``.

Usage:
    PROMETHEUS_URL=https://prometheus.example.org python collect_camp_spike.py
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os

from promclient import Prometheus

BACKEND = "default-ro-oai-backend-service-8080@kubernetes"
RATE = f'sum(rate(traefik_service_requests_total{{service="{BACKEND}"}}[5m]))'


def _ts(year: int, month: int, day: int, hour: int = 0) -> int:
    return int(dt.datetime(year, month, day, hour, tzinfo=dt.timezone.utc).timestamp())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2026-05-18")
    parser.add_argument("--end", default="2026-05-29")
    parser.add_argument("--out", default="data/camp_spike.json")
    args = parser.parse_args()

    prom = Prometheus()
    start = _ts(*map(int, args.start.split("-")))
    end = _ts(*map(int, args.end.split("-")))

    series = prom.query_range(RATE, start, end, step=3600)
    by_day: dict[str, list[float]] = {}
    peak_ts, peak_val = None, 0.0
    if series:
        for ts, val in series[0]["values"]:
            day = dt.datetime.fromtimestamp(int(ts), dt.timezone.utc).strftime("%Y-%m-%d")
            value = float(val)
            by_day.setdefault(day, []).append(value)
            if value > peak_val:
                peak_ts, peak_val = int(ts), value

    out = {"by_day": {}}
    for day in sorted(by_day):
        samples = by_day[day]
        out["by_day"][day] = {
            "peak_req_s": round(max(samples), 1),
            "mean_req_s": round(sum(samples) / len(samples), 1),
        }

    if peak_ts is not None:
        out["overall_peak"] = {
            "ts": dt.datetime.fromtimestamp(peak_ts, dt.timezone.utc).isoformat(),
            "req_s": round(peak_val, 1),
        }
        # refine to a one-minute peak around the busiest hour
        fine = prom.query_range(
            f'sum(rate(traefik_service_requests_total{{service="{BACKEND}"}}[1m]))',
            peak_ts - 6 * 3600, peak_ts + 6 * 3600, step=60)
        if fine:
            out["fine_1m_peak_req_s"] = round(
                max(float(v) for _, v in fine[0]["values"]), 1)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(out, fh, indent=2)
        fh.write("\n")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
