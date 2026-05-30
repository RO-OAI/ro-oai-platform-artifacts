# MLCompete reproducibility artifacts

This repository holds the data-collection scripts and the frozen measurements
behind the empirical sections of our paper on MLCompete, the platform that runs
the Romanian National AI Olympiad (ONIA). It is **not** the platform source; it
is the material needed to reproduce or audit the numbers we report.

If you only want to check the figures, everything is already here:
the collected data and the raw API snapshots are committed. If you want to re-run
the collection against a live cluster, see [Running the collection](#running-the-collection).

## What's in the paper, and where it comes from

Every quantitative claim is derived from a Prometheus instance that scrapes the
production cluster (Traefik for ingress, kube-state-metrics and node-exporter
for the workloads, and postgres-exporter for the database). We never queried the
database directly for the paper; the DB facts come from the exporter.

The retention on that Prometheus is about 15 days, which matters: the window we
report is mostly steady state plus the National Team Selection Camp (21-25 May
2026). The large spring stages (local/county/national) had already aged out of
the series by the time we collected, so we report them qualitatively and treat
the camp as our peak-load evidence.

## Layout

```
scripts/
  promclient.py          read-only Prometheus HTTP API client
  collect_telemetry.py   steady-state traffic, latency, resources, DB health
  collect_camp_spike.py  backend request rate around the team camp
  snapshot_raw.py        freeze verbatim API responses (see data/raw_snapshots)
  make_figures.py        render the figures from the collected data
data/
  telemetry.json         output of collect_telemetry.py
  camp_spike.json        output of collect_camp_spike.py
  raw_snapshots/         one JSON per query: the verbatim API payload + metadata
figures/                 generated PDFs/PNGs used in the paper
```

## Reproducing the figures (no cluster needed)

```
pip install -r requirements.txt
python scripts/make_figures.py
```

This reads `data/telemetry.json` and `data/camp_spike.json` and writes the
figures into `figures/`.

## Running the collection

Point the scripts at any Prometheus that scrapes an equivalent stack. The
endpoint is read from an environment variable so nothing is hard-coded:

```
export PROMETHEUS_URL=https://your-prometheus.example.org
python scripts/collect_telemetry.py      # -> data/telemetry.json
python scripts/collect_camp_spike.py     # -> data/camp_spike.json
python scripts/snapshot_raw.py           # -> data/raw_snapshots/*.json
```

`collect_camp_spike.py` defaults to the 18-29 May 2026 window; override it with
`--start`/`--end`. If your Prometheus uses a self-signed certificate, set
`PROMETHEUS_INSECURE=1` (development only).

## A note on the raw snapshots

`data/raw_snapshots/` is the authoritative record. Each file pins one query, the
endpoint it ran against, a capture timestamp, and the response, so the numbers
stay checkable after the live series expire. Two caveats worth knowing:

- Long-range `increase()` extrapolates at the window edges, so a value can drift
  by a fraction between captures (e.g. the backend 5xx count sits around
  569-597 over the window; both round to a 0.007% error rate). The snapshots fix
  a single point in time.
- Network identifiers (hostnames, IPs, pod names) have been redacted from the
  committed snapshots. Metric values are untouched. Re-running `snapshot_raw.py`
  against your own endpoint regenerates them with your labels.

## Citing

If you use this material, please cite the paper (see [CITATION.cff](CITATION.cff)).

## License

Code is released under the MIT License; the data files under
CC BY 4.0. See [LICENSE](LICENSE) and [LICENSE-data](LICENSE-data).

- `data/engagement_queries.sql` and `data/engagement.json` — aggregate-only
  platform-usage figures (counts, distributions, leaderboard population). No
  personal data, usernames, IPs, or row-level records.
- `data/onia_stages.json` — per-stage ONIA 2026 figures from the official
  public results on olimpiada-ai.ro.
- `data/availability.json` — per-service availability and HTTP-success ratios.
