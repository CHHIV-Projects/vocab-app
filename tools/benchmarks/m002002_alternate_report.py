"""Export A3 cross-model evidence without inference or semantic grading."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
from collections import Counter
from pathlib import Path

from tools.benchmarks.m002002_alternate_trial import MODELS, WORDS
from tools.benchmarks.m002002_product_trial import public_payload, write_json


def export(run: Path, pilot: Path, prefix: Path) -> dict:
    results = json.loads((run / "results.json").read_text())
    baseline = [json.loads(line) for line in (pilot / "attempts.jsonl").read_text().splitlines()]
    baseline = [row for row in baseline if row["lemma"] in WORDS]
    if len(baseline) != 8:
        raise ValueError("Expected eight baseline attempts on the frozen subset")
    expected = {row["lemma"]: row for row in baseline}
    identities = set()
    for attempt in results["attempts"]:
        identity = (attempt["model"], attempt["lemma"], attempt["repeat"])
        if (identity in identities or identity[0] not in MODELS or identity[1] not in WORDS
                or identity[2] not in (1, 2, 3)):
            raise ValueError("Unexpected or duplicate approved alternate attempt")
        identities.add(identity)
        original = expected[attempt["lemma"]]
        if attempt["evidence_set_hash"] != original["evidence_set_hash"]:
            raise ValueError("Alternate evidence differs from frozen baseline")
        original_call = json.loads(
            (pilot / f"{original['order']:02d}-{original['lemma']}" / "call-001.json").read_text())
        alternate_call = json.loads((run / identity[0].replace(":", "-") /
                                    f"r{identity[2]}-{identity[1]}" / "call-001.json").read_text())
        for field in ("prompt", "schema", "seed"):
            if original_call[field] != alternate_call[field]:
                raise ValueError(f"Initial scaffold contract differs: {identity}/{field}")
    rows = []
    comparisons = []
    for model, attempts in [("gpt-oss:20b", baseline)] + [
        (model, [row for row in results["attempts"] if row["model"] == model]) for model in MODELS
    ]:
        if not attempts:
            raise ValueError(f"Missing model disposition: {model}")
        latencies = sorted(row["synthesis_elapsed_seconds"] for row in attempts)
        comparisons.append({
            "model": model, "attempts": len(attempts),
            "structural_validated": sum(row["status"] == "validated" for row in attempts),
            "errors": dict(Counter(row.get("error_code", "") for row in attempts
                                   if row["status"] != "validated")),
            "synthesis_seconds": sum(row["synthesis_elapsed_seconds"] for row in attempts),
            "median_seconds": statistics.median(latencies),
            "p95_nearest_rank_seconds": latencies[math.ceil(len(latencies) * 0.95) - 1],
            "max_seconds": max(latencies),
            "semantic_classification": "UNJUDGED; baseline lantern overlay separately applicable",
        })
        for attempt in attempts:
            if model == "gpt-oss:20b":
                directory = pilot / f"{attempt['order']:02d}-{attempt['lemma']}"
            else:
                directory = run / model.replace(":", "-") / f"r{attempt['repeat']}-{attempt['lemma']}"
            review = json.loads((directory / "review.json").read_text())
            for item in review or [{}]:
                rows.append({
                    "model": model, "lemma": attempt["lemma"], "repeat": attempt.get("repeat", 1),
                    "status": attempt["status"], "error_code": attempt.get("error_code", ""),
                    "stage": item.get("stage", ""), "alias": item.get("alias", ""),
                    "pos": item.get("pos", ""), "wording": item.get("wording", ""),
                    "sources_json": json.dumps(item.get("sources", []), ensure_ascii=False),
                    "evidence_set_hash": attempt["evidence_set_hash"],
                    "semantic_classification": "UNJUDGED",
                    "human_reviewed": False,
                })
    report = {
        "comparisons": comparisons, "alternate_results": results,
        "alternate_models": {
            model: json.loads((run / model.replace(":", "-") / "model.json").read_text())
            for model in MODELS
        },
        "artifact_sha256": {
            str(path.relative_to(run)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(run.rglob("*")) if path.is_file()
        },
        "interpretation": "Provider incompatibility is not a semantic failure or quality comparison. "
                          "No new human semantic review; preserve prior A2 lantern overlay.",
    }
    for path in run.rglob("*.json"):
        value = json.loads(path.read_text())
        if public_payload(value) != value:
            raise ValueError(f"Private reasoning field persisted: {path.name}")
    write_json(Path(f"{prefix}_attempts.json"), public_payload(report))
    with Path(f"{prefix}_review.csv").open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    lines = [
        "# M002.002 A3 cross-model review packet", "",
        "Equivalent-contract lane only. No tuning, replacement retries or production changes.",
        "The GPT-OSS row is the historical eight-word subset (one attempt each), not a new run.",
        "Alternate candidates stop on provider/settings incompatibility; do not count these",
        "as semantic failures, claim inferiority, or infer full-corpus success rates.", "",
        "| Model | Word attempts | Structurally validated | Rejections/stops | Synthesis seconds |",
        "|---|---:|---:|---|---:|",
    ]
    for row in comparisons:
        lines.append(f"| {row['model']} | {row['attempts']} | {row['structural_validated']} | "
                     f"{json.dumps(row['errors'])} | {row['synthesis_seconds']:.3f} |")
    lines += ["", "## Exact alternate stops and identities", ""]
    for model in MODELS:
        identity = report["alternate_models"][model]
        lines += [f"- `{model}`: `{identity['digest']}`; installed bundle {identity['size']} bytes."]
        for attempt in results["attempts"]:
            if attempt["model"] == model and attempt.get("error_code"):
                lines.append(f"  - {attempt['lemma']}, repeat {attempt['repeat']}: "
                             f"`{attempt['error_code']}`: {attempt.get('error', '')}")
    lines += [
        "", "## Review boundary", "",
        f"Exact source/output rows: [{prefix.name}_review.csv]({prefix.name}_review.csv).",
        f"Machine identities, timing and hashes: [{prefix.name}_attempts.json]({prefix.name}_attempts.json).",
        "All newly exported semantic fields remain UNJUDGED. The six prior PO-corroborated",
        "lantern dispositions remain in the separate A2 adjudication overlay; they are not",
        "new independent review. No alternate prose is reviewable when rejected before generation.",
        "The separate narrow-role packet still needs human semantic review.",
        "Model fit and generation latency remain unmeasured for candidates rejected before loading.",
        "No automatic expansion or settings adaptation is authorized by this packet.", "",
    ]
    with Path(f"{prefix}_review.md").open("x", encoding="utf-8") as stream:
        stream.write("\n".join(lines))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--pilot", type=Path, required=True)
    parser.add_argument("--prefix", type=Path, required=True)
    args = parser.parse_args()
    export(args.run, args.pilot, args.prefix)
