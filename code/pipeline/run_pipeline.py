"""Run the full extraction-and-verification pipeline.

Input : JSONL of model responses, one per line, with fields
        response_id, task_id, model, condition (baseline|guardrail),
        prompt_language (english|hindi), prog_language (python|javascript),
        sample, temperature, text
Output: references.csv - one row per third-party package reference, labelled
        Valid / Hallucinated / Suspect-squatted / Ambiguous.

Usage:
  # first run at T0: query registries and freeze the snapshot
  python -m pipeline.run_pipeline responses.jsonl --snapshot snapshot.json --build-snapshot \
      --cutoffs cutoffs.json --out references.csv
  # later runs re-use the frozen snapshot
  python -m pipeline.run_pipeline responses.jsonl --snapshot snapshot.json --cutoffs cutoffs.json
"""
from __future__ import annotations

import argparse
import csv
import json

from .extract import extract
from .filter_map import filter_and_map
from .verify import build_snapshot, classify

FIELDS = ["response_id", "task_id", "model", "condition", "prompt_language", "prog_language",
          "sample", "temperature", "ecosystem", "kind", "name", "dist", "label"]


def load_responses(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def references_for(responses: list[dict]) -> list[dict]:
    rows = []
    for r in responses:
        refs = filter_and_map(extract(r["text"], r["prog_language"]), r["text"])
        if not refs:  # keep a marker so response-level denominators stay correct
            rows.append({**{k: r.get(k) for k in FIELDS[:8]}, "ecosystem": "", "kind": "",
                         "name": "", "dist": "", "label": "NoThirdParty"})
        for ref in refs:
            rows.append({**{k: r.get(k) for k in FIELDS[:8]}, "ecosystem": ref["ecosystem"],
                         "kind": ref["kind"], "name": ref["name"], "dist": ref["dist"]})
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("responses")
    ap.add_argument("--snapshot", required=True, help="frozen registry snapshot (JSON)")
    ap.add_argument("--build-snapshot", action="store_true", help="query registries now and freeze at T0")
    ap.add_argument("--cutoffs", help='JSON {"model name": "YYYY-MM-DD"} training cutoffs')
    ap.add_argument("--out", default="references.csv")
    a = ap.parse_args(argv)

    responses = load_responses(a.responses)
    rows = references_for(responses)

    if a.build_snapshot:
        names = {(r["ecosystem"], r["dist"]) for r in rows if r["dist"]}
        snapshot = build_snapshot(names, a.snapshot)
    else:
        with open(a.snapshot, encoding="utf-8") as f:
            snapshot = json.load(f)
    cutoffs = {}
    if a.cutoffs:
        with open(a.cutoffs, encoding="utf-8") as f:
            cutoffs = json.load(f)

    for row in rows:
        if row["dist"]:
            row["label"] = classify(row["ecosystem"], row["dist"], snapshot, cutoffs.get(row["model"]))

    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    counts = {}
    for row in rows:
        counts[row["label"]] = counts.get(row["label"], 0) + 1
    print(f"{len(responses)} responses -> {sum(v for k, v in counts.items() if k != 'NoThirdParty')} "
          f"third-party references: {counts}")
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
