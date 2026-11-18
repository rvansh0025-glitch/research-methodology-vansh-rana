"""Draw the 240-prompt study corpus from the Spracklen et al. prompt dataset.

Dataset: https://zenodo.org/records/14676377 (also github.com/Spracks/PackageHallucination)

Stratified by programming language (python/javascript) x source
(stackoverflow/llm-generated) x time segment (2023/pre-2023): 8 cells x 30
prompts = 240, using a fixed seed so the sample is reproducible and can be
pre-registered.

The dataset ships as separate prompt files per language/source/segment. Point
this script at a CSV that lists them with one prompt per row; column names are
configurable because the release layout may differ between versions.

Usage:
  python -m pipeline.sample_prompts all_prompts.csv --out tasks.csv --seed 20261101
"""
from __future__ import annotations

import argparse
import csv
import random
from collections import defaultdict


def stratified_sample(rows, strata_cols, per_cell, seed):
    cells = defaultdict(list)
    for r in rows:
        cells[tuple(r[c].strip().lower() for c in strata_cols)].append(r)
    rng = random.Random(seed)
    out = []
    for key in sorted(cells):
        pool = sorted(cells[key], key=lambda r: r["_id"])  # order-independent of file order
        if len(pool) < per_cell:
            raise SystemExit(f"cell {key} has only {len(pool)} prompts (< {per_cell})")
        out.extend(rng.sample(pool, per_cell))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("prompts_csv")
    ap.add_argument("--out", default="tasks.csv")
    ap.add_argument("--seed", type=int, default=20261101)
    ap.add_argument("--per-cell", type=int, default=30)
    ap.add_argument("--id-col", default="prompt_id")
    ap.add_argument("--text-col", default="prompt")
    ap.add_argument("--lang-col", default="language")
    ap.add_argument("--source-col", default="source")
    ap.add_argument("--segment-col", default="segment")
    a = ap.parse_args(argv)

    with open(a.prompts_csv, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["_id"] = r[a.id_col]
    strata = [a.lang_col, a.source_col, a.segment_col]
    sample = stratified_sample(rows, strata, a.per_cell, a.seed)

    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["task_id", "prog_language", "source", "segment", "difficulty", "prompt_en", "prompt_hi"])
        for i, r in enumerate(sample, 1):
            # difficulty and Hindi translation are filled in by the annotators
            w.writerow([f"T{i:03d}", r[a.lang_col], r[a.source_col], r[a.segment_col], "",
                        r[a.text_col], ""])
    print(f"sampled {len(sample)} prompts from {len(rows)} (seed={a.seed}) -> {a.out}")


if __name__ == "__main__":
    main()
