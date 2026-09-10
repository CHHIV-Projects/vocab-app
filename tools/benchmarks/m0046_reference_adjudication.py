"""Recompute M004.6.4 metrics against an adjudicated reference derivative."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any


CHANGES = {
    "P010": ("uncertain", "insufficient_evidence", "Powder/shot and explosive charges may or may not warrant one learner container; leave policy-sensitive."),
    "P029": ("uncertain", "insufficient_evidence", "Pus and mucus discharge are related medical applications; leave the learner-policy boundary for review."),
    "P045": ("keep_separate", "related_but_distinct", "Making/accomplishing by cutting is not automatically the generic intransitive sense to split."),
    "P054": ("keep_separate", "related_but_distinct", "Transitive splitting/severing with a sharp instrument is not automatically the generic intransitive sense to split."),
}


def adjudicate(reference: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    corrected = json.loads(json.dumps(reference))
    changes = []
    for item in corrected:
        item["reference_status"] = "adjudicated_v2_pending_product_owner_validation"
        if item["pair_id"] not in CHANGES:
            continue
        decision, reason, note = CHANGES[item["pair_id"]]
        changes.append({
            "pair_id": item["pair_id"], "word": item["word"], "pos": item["pos"],
            "old_decision": item["reference_decision"], "new_decision": decision,
            "old_reason": item["reference_reason"], "new_reason": reason, "adjudication_note": note,
        })
        item["reference_decision"] = decision
        item["reference_reason"] = reason
        item["reference_status"] = "adjudicated_v2_pending_product_owner_validation"
        item["adjudication_note"] = note
    return corrected, changes


def recompute(decisions: dict[str, dict[str, Any]], reference: list[dict[str, Any]]) -> dict[str, Any]:
    resolved = [item for item in reference if item["reference_decision"] != "uncertain"]
    output: dict[str, Any] = {}
    for key, values in decisions.items():
        experiment, remainder = key.split(":", 1)
        model, pair_id = remainder.rsplit(":", 1)
        output.setdefault(experiment, {}).setdefault(model, {})[pair_id] = values
    summary: dict[str, Any] = {}
    for experiment, models in output.items():
        summary[experiment] = {}
        for model, pair_values in models.items():
            rows = [(item["reference_decision"], pair_values[item["pair_id"]]["majority_decision"]) for item in resolved]
            merge_tp = sum(expected == actual == "merge" for expected, actual in rows)
            merge_fp = sum(expected != "merge" and actual == "merge" for expected, actual in rows)
            merge_fn = sum(expected == "merge" and actual != "merge" for expected, actual in rows)
            separate = [(expected, actual) for expected, actual in rows if expected == "keep_separate"]
            summary[experiment][model] = {
                "reference_pairs_total": len(reference), "resolved_pairs": len(resolved), "excluded_uncertain_pairs": len(reference) - len(resolved),
                "reference_agreement": sum(expected == actual for expected, actual in rows) / len(rows),
                "merge_precision": merge_tp / (merge_tp + merge_fp) if merge_tp + merge_fp else None,
                "merge_recall": merge_tp / (merge_tp + merge_fn) if merge_tp + merge_fn else None,
                "false_merges": merge_fp, "false_splits": merge_fn,
                "keep_separate_accuracy": sum(actual == "keep_separate" for _, actual in separate) / len(separate),
                "uncertain_rate": sum(pair_values[item["pair_id"]]["majority_decision"] == "uncertain" for item in reference) / len(reference),
                "seed_disagreement_pairs": sum(pair_values[item["pair_id"]]["disagreement"] for item in reference),
            }
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact_root", type=Path)
    args = parser.parse_args()
    reference_path = args.artifact_root / "reference_pairs.json"
    reference = json.loads(reference_path.read_text())
    corrected, changes = adjudicate(reference)
    for item in corrected:
        item["pair_hash"] = hashlib.sha256(json.dumps(
            {"ids": [item["first"]["source_sense_id"], item["second"]["source_sense_id"]],
             "reference": [item["reference_decision"], item["reference_reason"]]},
            sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    decisions = json.loads((args.artifact_root / "decisions.json").read_text())
    (args.artifact_root / "reference_pairs_adjudicated_v2.json").write_text(json.dumps(corrected, indent=2, sort_keys=True))
    with (args.artifact_root / "reference_adjudication_changes.csv").open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=list(changes[0]))
        writer.writeheader()
        writer.writerows(changes)
    (args.artifact_root / "summary_adjudicated_v2.json").write_text(json.dumps(recompute(decisions, corrected), indent=2, sort_keys=True))
    print(args.artifact_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
