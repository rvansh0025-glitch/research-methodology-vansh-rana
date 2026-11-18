"""Descriptive metrics from references.csv (Section III-F of the paper).

  * package-level hallucination rate  = hallucinated refs / all third-party refs
  * response-level rate               = share of responses with >= 1 hallucinated ref
  * within-model repeat rate          = share of hallucinated names (per task-cell)
                                        that appear in >= 2 of the 6 samples
  * cross-model overlap               = Jaccard similarity of hallucinated-name sets
All proportions carry Wilson 95% confidence intervals.

Usage: python -m pipeline.metrics references.csv [--by model,prog_language]
"""
from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from itertools import combinations


def wilson(k: int, n: int, z: float = 1.959964) -> tuple[float, float, float]:
    if n == 0:
        return float("nan"), float("nan"), float("nan")
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return p, max(0.0, centre - half), min(1.0, centre + half)


def load(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def package_rate(rows):
    refs = [r for r in rows if r["label"] not in ("NoThirdParty", "Ambiguous")]
    k = sum(r["label"] == "Hallucinated" for r in refs)
    return k, len(refs), wilson(k, len(refs))


def response_rate(rows):
    by_resp = defaultdict(bool)
    for r in rows:
        by_resp[r["response_id"]] |= r["label"] == "Hallucinated"
    k = sum(by_resp.values())
    return k, len(by_resp), wilson(k, len(by_resp))


def repeat_rate(rows, min_repeats: int = 2):
    """Within one task-cell (task x model x condition x language), how many of the
    hallucinated names were produced in at least `min_repeats` samples?"""
    cell_name_samples = defaultdict(set)
    for r in rows:
        if r["label"] == "Hallucinated":
            cell = (r["task_id"], r["model"], r["condition"], r["prompt_language"])
            cell_name_samples[(cell, r["ecosystem"], r["dist"])].add(r["sample"])
    total = len(cell_name_samples)
    k = sum(len(s) >= min_repeats for s in cell_name_samples.values())
    return k, total, wilson(k, total)


def jaccard_overlap(rows):
    names = defaultdict(set)
    for r in rows:
        if r["label"] == "Hallucinated":
            names[r["model"]].add((r["ecosystem"], r["dist"]))
    pairs = {}
    for a, b in combinations(sorted(names), 2):
        union = names[a] | names[b]
        pairs[(a, b)] = len(names[a] & names[b]) / len(union) if union else 0.0
    shared_all = set.intersection(*names.values()) if names else set()
    return pairs, shared_all


def _fmt(label, k, n, ci):
    p, lo, hi = ci
    return f"{label:<34} {k:>6}/{n:<6} {100*p:6.2f}%  [95% CI {100*lo:.2f}-{100*hi:.2f}]"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("references")
    ap.add_argument("--by", default="", help="comma-separated columns to break down by")
    a = ap.parse_args(argv)
    rows = load(a.references)

    print(_fmt("Package-level hallucination rate", *package_rate(rows)))
    print(_fmt("Response-level hallucination rate", *response_rate(rows)))
    print(_fmt("Within-model repeat rate (>=2/6)", *repeat_rate(rows)))
    pairs, shared = jaccard_overlap(rows)
    for (m1, m2), j in pairs.items():
        print(f"Jaccard({m1}, {m2}) = {j:.3f}")
    print(f"Names hallucinated by every model: {len(shared)}")

    if a.by:
        cols = a.by.split(",")
        groups = defaultdict(list)
        for r in rows:
            groups[tuple(r[c] for c in cols)].append(r)
        print(f"\nBreakdown by {', '.join(cols)}:")
        for key in sorted(groups):
            print(_fmt(" / ".join(key), *package_rate(groups[key])))


if __name__ == "__main__":
    main()
