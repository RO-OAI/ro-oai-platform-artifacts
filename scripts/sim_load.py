#!/usr/bin/env python3
"""Closed-form-calibrated discrete-event simulation of the MLCompete evaluation
pipeline under synthetic contest-day load.

This is a MODEL, not a benchmark against the live system. It is calibrated with
the empirical end-to-end evaluation service-time distribution measured read-only
from production (81,489 evaluated submissions): mean 0.80 s, p50 0.31 s,
p90 0.78 s, p95 1.19 s, p99 10.53 s, ~0.17% > 60 s. We reconstruct a service-time
sampler matching these quantiles, then drive the pipeline at submission rates far
above anything observed in production (peak real rate was ~0.7 submissions/s) to
see how the decoupled, horizontally-scaled evaluator tier behaves.

Model: submissions arrive as a Poisson process at rate lambda. A pool of c
identical evaluator workers (RabbitMQ competing consumers) each process one
submission at a time; service times are drawn from the empirical mixture. We
report the queue waiting time (time from enqueue to start of evaluation), which
is the component the platform's scaling controls; total latency is wait + service.
"""

import argparse
import heapq
import json
import math
import os
import random

# Empirical service-time mixture calibrated to the measured production quantiles.
# 97.1% of jobs <= 2 s, 98.3% <= 5 s, 0.17% > 60 s, mean ~0.80 s.
#   - body: log-normal for the common fast path
#   - tail: heavier log-normal for the rare slow problems
def sample_service_time(rng):
    u = rng.random()
    if u < 0.971:
        # fast path: median ~0.31 s, p90 ~0.78 s  -> lognormal(mu,sigma)
        return rng.lognormvariate(math.log(0.31), 0.62)
    elif u < 0.998:
        # slow problems: a few seconds to ~tens of seconds
        return rng.lognormvariate(math.log(6.0), 0.7)
    else:
        # rare stragglers (heavy training-style jobs), tens to hundreds of seconds
        return rng.lognormvariate(math.log(90.0), 0.9)


def simulate(lam, c, n_jobs, seed=0):
    """M/G/c queue. Returns waiting-time percentiles and utilisation."""
    rng = random.Random(seed)
    # worker availability times (heap of when each of c workers is free)
    free = [0.0] * c
    heapq.heapify(free)
    t = 0.0
    waits = []
    busy_time = 0.0
    last_finish = 0.0
    for _ in range(n_jobs):
        t += rng.expovariate(lam)            # next arrival
        worker_free = heapq.heappop(free)    # earliest-available worker
        start = max(t, worker_free)
        wait = start - t
        svc = sample_service_time(rng)
        finish = start + svc
        heapq.heappush(free, finish)
        waits.append(wait)
        busy_time += svc
        last_finish = max(last_finish, finish)
    waits.sort()

    def pct(p):
        return waits[min(len(waits) - 1, int(p * len(waits)))]

    return {
        "lambda_per_s": lam,
        "workers": c,
        "wait_p50_s": round(pct(0.50), 3),
        "wait_p95_s": round(pct(0.95), 3),
        "wait_p99_s": round(pct(0.99), 3),
        "wait_max_s": round(waits[-1], 2),
        "frac_wait_under_1s": round(sum(w < 1.0 for w in waits) / len(waits), 4),
        "worker_utilisation": round(busy_time / (c * last_finish), 3),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--jobs", type=int, default=200_000)
    ap.add_argument("--out", default="data/sim_load.json")
    args = ap.parse_args()

    # Contest-day load scenarios. Real peak was ~0.7 sub/s; we sweep well past it.
    # A national contest of N active students submitting on average every T seconds
    # gives lambda = N / T. E.g. 600 students, one submission / 40 s -> 15 sub/s.
    rates = [0.5, 1, 2, 3, 5, 7, 10, 12, 15, 20, 25]   # submissions per second
    worker_counts = [2, 4, 10]                  # HPA range for the evaluator tier

    results = []
    for c in worker_counts:
        for lam in rates:
            # a worker clears ~1.25 jobs/s on average (mean service ~0.8 s); skip
            # points past rho ~= 1.05 where an unscaled queue is unstable by design
            if lam / (c * 1.25) > 1.05:
                continue
            results.append(simulate(lam, c, args.jobs))

    out = {
        "note": "Discrete-event M/G/c simulation of the evaluation pipeline, "
                "calibrated to production service-time quantiles. Model, not a "
                "live benchmark. Real observed peak was ~0.7 submissions/s.",
        "calibration": {"mean_s": 0.80, "p50_s": 0.31, "p90_s": 0.78,
                        "p95_s": 1.19, "p99_s": 10.53, "frac_le_2s": 0.971},
        "results": results,
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(out, f, indent=2)
        f.write("\n")
    # console summary
    print(f"{'workers':>7} {'lambda':>7} {'p50':>7} {'p95':>7} {'p99':>7} {'util':>6}")
    for r in results:
        print(f"{r['workers']:>7} {r['lambda_per_s']:>7} {r['wait_p50_s']:>7} "
              f"{r['wait_p95_s']:>7} {r['wait_p99_s']:>7} {r['worker_utilisation']:>6}")
    print("wrote", args.out)


if __name__ == "__main__":
    main()
