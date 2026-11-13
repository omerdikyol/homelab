#!/usr/bin/env python3
"""Compare two labelled windows of metrics-sample.py output, with statistics
that survive autocorrelated samples.

  python3 metrics-compare.py metrics.csv before-label after-label [block_minutes]
  SELFCHECK=1 python3 metrics-compare.py

Samples 10 s apart are not independent (a backup or a download spans many of
them), so tests on raw samples overstate certainty. Each window is cut into
blocks (10 min by default) and every statistic runs on block means:
- difference of means, with a 95% bootstrap confidence interval over blocks;
- a two-sided permutation test on the block means (20,000 shuffles), which
  needs no normality assumption;
- lag-1 autocorrelation of the block means, as a warning when blocks are still
  correlated (above 0.2: use longer blocks);
- Holm-adjusted p-values across all metrics compared, since testing twenty
  metrics at 0.05 finds one "effect" by chance.
A label may be a comma-separated list; a row counts if its phase matches any.
"""
import csv, random, statistics as st, sys
from collections import defaultdict
from itertools import combinations
from math import comb

METRICS = ["cpu_user", "cpu_sys", "cpu_iowait", "ctxt_s", "psi_cpu_some", "psi_mem_some", "psi_io_some", "psi_io_full",
           "mem_used_mb", "swap_used_mb", "swapin_kb_s", "swapout_kb_s", "majflt_s", "disk_read_kb_s", "disk_write_kb_s",
           "disk_util", "wan_rx_kb_s", "wan_tx_kb_s", "conntrack", "pkg_watts", "temp_c", "load1"]
ROUNDS = 20000


def blocks(rows, labels, minutes):
    """Block means per metric: consecutive rows of the window, cut every
    `minutes`. Incomplete trailing blocks (under half full) are dropped."""
    size = minutes * 6
    picked = [r for r in rows if r["phase"] in labels]
    out = defaultdict(list)
    for i in range(0, len(picked), size):
        chunk = picked[i:i + size]
        if len(chunk) < size / 2:
            continue
        for m in METRICS:
            vals = [float(r[m]) for r in chunk if r.get(m) not in ("", None)]
            if vals:
                out[m].append(st.fmean(vals))
    return out, len(picked)


def permutation_p(a, b, rng):
    """Exact over every split when there are at most ROUNDS of them (8 vs 6
    blocks: 3,003, so p cannot be below 1/3003), else ROUNDS random shuffles."""
    observed = abs(st.fmean(a) - st.fmean(b))
    pool, n, hits = a + b, len(a), 0
    if comb(len(pool), n) <= ROUNDS:
        total = sum(pool)
        splits = [sum(c) for c in combinations(pool, n)]
        hits = sum(abs(s / n - (total - s) / (len(pool) - n)) >= observed - 1e-12 for s in splits)
        return hits / len(splits)
    for _ in range(ROUNDS):
        rng.shuffle(pool)
        if abs(st.fmean(pool[:n]) - st.fmean(pool[n:])) >= observed - 1e-12:
            hits += 1
    return (hits + 1) / (ROUNDS + 1)


def bootstrap_ci(a, b, rng):
    diffs = sorted(st.fmean(rng.choices(b, k=len(b))) - st.fmean(rng.choices(a, k=len(a))) for _ in range(ROUNDS))
    return diffs[int(0.025 * ROUNDS)], diffs[int(0.975 * ROUNDS)]


def lag1(xs):
    """nan when undefined: too few blocks, or either shifted series is constant."""
    try:
        return st.correlation(xs[:-1], xs[1:]) if len(xs) > 3 else float("nan")
    except st.StatisticsError:
        return float("nan")


def compare(rows, before, after, minutes=10, seed=1):
    rng = random.Random(seed)
    a, na = blocks(rows, set(before.split(",")), minutes)
    b, nb = blocks(rows, set(after.split(",")), minutes)
    result = {"samples": (na, nb), "blocks": (len(a[METRICS[0]]), len(b[METRICS[0]])), "metrics": {}}
    for m in METRICS:
        if len(a[m]) < 2 or len(b[m]) < 2:
            continue
        ma, mb = st.fmean(a[m]), st.fmean(b[m])
        lo, hi = bootstrap_ci(a[m], b[m], rng)
        result["metrics"][m] = dict(before=ma, after=mb, change=(mb - ma) / ma * 100 if ma else float("nan"),
                                    ci=(lo, hi), p=permutation_p(a[m], b[m], rng), lag1=(lag1(a[m]), lag1(b[m])))
    for m, p_holm in holm({m: x["p"] for m, x in result["metrics"].items()}).items():
        result["metrics"][m]["p_holm"] = p_holm
    return result


def holm(ps):
    """Holm step-down adjustment: {name: p} to {name: adjusted p}."""
    order = sorted(ps, key=ps.get)
    out, running = {}, 0.0
    for i, name in enumerate(order):
        running = max(running, min(1.0, (len(order) - i) * ps[name]))
        out[name] = running
    return out


def main(path, before, after, minutes=10):
    rows = list(csv.DictReader(open(path)))
    r = compare(rows, before, after, int(minutes))
    print(f"before '{before}': {r['samples'][0]} samples, {r['blocks'][0]} blocks | after '{after}': "
          f"{r['samples'][1]} samples, {r['blocks'][1]} blocks | block = {minutes} min")
    print(f"{'metric':16} {'before':>10} {'after':>10} {'change':>8} {'95% CI of after-before':>26} {'p':>8} {'p Holm':>8} {'lag1 b/a':>12}")
    for m, x in r["metrics"].items():
        print(f"{m:16} {x['before']:10.2f} {x['after']:10.2f} {x['change']:7.1f}% "
              f"[{x['ci'][0]:10.2f}, {x['ci'][1]:10.2f}] {x['p']:8.4f} {x['p_holm']:8.4f} {x['lag1'][0]:5.2f}/{x['lag1'][1]:5.2f}")


def selfcheck():
    rng = random.Random(7)
    rows = []
    for phase, level in (("A", 50.0), ("B", 20.0)):
        for _ in range(60 * 8):
            row = {m: rng.gauss(level, 5) for m in METRICS}
            row["phase"] = phase
            rows.append({k: str(v) for k, v in row.items()})
    r = compare(rows, "A", "B")
    x = r["metrics"]["cpu_user"]
    assert r["blocks"] == (8, 8) and abs(x["before"] - 50) < 1 and abs(x["after"] - 20) < 1
    assert x["p"] < 0.001 and x["ci"][0] < -29 < x["ci"][1] + 1 and -61 < x["change"] < -59
    same = compare([dict(r_, phase="C") for r_ in rows if r_["phase"] == "A"] + [dict(r_, phase="D") for r_ in rows if r_["phase"] == "A"][::-1], "C", "D")
    assert same["metrics"]["cpu_user"]["p"] > 0.05          # identical distributions: no false difference
    assert lag1([0.0, 0.0, 0.0, 5.0]) != lag1([0.0, 0.0, 0.0, 5.0])   # constant head: nan, not a crash
    assert holm({"a": 0.01, "b": 0.04, "c": 0.03}) == {"a": 0.03, "c": 0.06, "b": 0.06}
    assert permutation_p([1.0, 2.0], [3.0, 4.0], rng) == 2 / 6   # exact: 2 of 6 splits as extreme
    print("selfcheck ok")


if __name__ == "__main__":
    selfcheck() if __import__("os").environ.get("SELFCHECK") else main(*sys.argv[1:])
