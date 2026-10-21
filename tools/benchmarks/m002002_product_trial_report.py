"""Export auditable pilot facts and unjudged source/wording review packets."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
from collections import Counter
from pathlib import Path
from typing import Any


def latency(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    return {"min": min(values), "median": statistics.median(values),
            "p95_nearest_rank": ordered[math.ceil(0.95 * len(values)) - 1], "max": max(values)}


def markdown(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def export(run: Path, prefix: Path) -> dict[str, Any]:
    manifest = json.loads((run / "manifest.json").read_text())
    attempts = [json.loads(line) for line in (run / "attempts.jsonl").read_text().splitlines()]
    if len(attempts) != 20 or len({row["lemma"] for row in attempts}) != 20:
        raise ValueError("Expected complete approved pilot with no duplicate attempts")
    records = {row["normalized_lemma"]: row for row in manifest["records"]}
    for attempt in attempts:
        if attempt["evidence_set_hash"] != records[attempt["lemma"]]["evidence_set_hash"]:
            raise ValueError("Attempt evidence differs from frozen manifest")
    strata = {}
    for name in ("normal", "complexity", "challenge"):
        group = [row for row in attempts if row["stratum"] == name]
        strata[name] = {
            "attempts": len(group), "validated": sum(row["status"] == "validated" for row in group),
            "latency_seconds": latency([row["synthesis_elapsed_seconds"] for row in group]),
        }
    review = []
    files = []
    for path in sorted(run.rglob("*.json")) + [run / "attempts.jsonl"]:
        content = path.read_bytes()
        if b'"message_thinking"' in content or b'"thinking":' in content:
            raise ValueError(f"Private reasoning key found in benchmark output: {path}")
        files.append({"path": str(path.relative_to(run)), "sha256": hashlib.sha256(content).hexdigest()})
    for attempt in attempts:
        directory = run / f"{attempt['order']:02d}-{attempt['lemma']}"
        for index, row in enumerate(json.loads((directory / "review.json").read_text()), 1):
            review.append(dict(row, review_id=f"{attempt['lemma']}-{index:03d}",
                               lemma=attempt["lemma"], stratum=attempt["stratum"],
                               attempt_status=attempt["status"]))
    summary = {
        "run_path": str(run), "corpus_sha256": manifest["corpus_sha256"],
        "manifest_sha256": hashlib.sha256((run / "manifest.json").read_bytes()).hexdigest(),
        "model": json.loads((run / "model.json").read_text()),
        "identities": manifest["identities"], "source_sha256": manifest["source_sha256"],
        "word_attempts": len(attempts), "fresh_attempts": len(attempts),
        "structurally_validated": sum(row["status"] == "validated" for row in attempts),
        "strata": strata,
        "errors": dict(Counter(row["error_code"] for row in attempts if row["status"] == "rejected")),
        "latency_seconds": latency([row["synthesis_elapsed_seconds"] for row in attempts]),
        "synthesis_seconds_total": sum(row["synthesis_elapsed_seconds"] for row in attempts),
        "evidence_preparation_seconds_total": sum(row["evidence_preparation_seconds"] for row in attempts),
        "provider_seconds_by_stage": {
            stage: sum(call["elapsed_seconds"] for row in attempts for call in row["provider_calls"]
                       if call["stage"] == stage)
            for stage in ("scaffold", "grouping", "core_selection")
        },
        "review_rows_by_stage": dict(Counter(row["stage"] for row in review)),
        "human_reviewed_meanings": 0, "semantic_classifications": {"UNJUDGED": len(review)},
        "semantic_verdict": "PENDING_HUMAN_REVIEW",
        "attempts": attempts, "artifact_hashes": files,
    }
    with Path(str(prefix) + "_attempts.json").open("x") as stream:
        json.dump(summary, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write("\n")
    fields = ["review_id", "lemma", "stratum", "attempt_status", "stage", "pos",
              "bucket", "order", "call", "alias", "wording", "exact_sources",
              "semantic_classification", "semantic_flags", "human_reviewed", "human_reviewer"]
    with Path(str(prefix) + "_review.csv").open("x", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in review:
            projected = {key: row.get(key, "") for key in fields}
            projected["exact_sources"] = json.dumps(row["sources"], ensure_ascii=False, sort_keys=True)
            projected["semantic_flags"] = json.dumps(row["semantic_flags"])
            writer.writerow(projected)
    packet = [
        "# M002.002 pilot human-review packet",
        "",
        "**All semantic classifications remain UNJUDGED; zero new human-reviewed meanings.**",
        "These are exact source/output pairs selected for review, not model-assigned truth labels.",
        "Do not interpret structural validation as source fidelity.",
        "",
        "## Structural outcomes",
        "",
        "| Stratum | Attempts | Validated | Rejected | Median s | p95 s |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, group in strata.items():
        packet.append(f"| {name} | {group['attempts']} | {group['validated']} | "
                      f"{group['attempts'] - group['validated']} | "
                      f"{group['latency_seconds']['median']:.3f} | "
                      f"{group['latency_seconds']['p95_nearest_rank']:.3f} |")
    rejected = [row for row in attempts if row["status"] == "rejected"]
    packet += [
        "",
        "Rejection counts: " + json.dumps(summary["errors"], sort_keys=True) + ".",
        "Rejected words: " + ", ".join(row["lemma"] for row in rejected) + ". No final learner",
        "candidate was produced for them; scaffold review must not be called final acceptance.",
        "",
        "## Lantern critical review",
        "",
        "Fresh scaffold aliases S006..S011 show the same suspected forward-shift pattern",
        "as accepted M002.001 evidence. Review the exact pairs below to confirm or reject",
        "that interpretation. Semantic omission/duplication/cross-POS flags are not",
        "automatically scored. No further current-model expansion is authorized here.",
        "",
    ]

    def add_rows(rows: list[dict[str, Any]]) -> None:
        packet.extend(["| Review ID / placement | Exact source POS/order, IDs and glosses | Generated wording |",
                       "|---|---|---|"])
        for row in rows:
            sources = " / ".join(
                f"{source['pos']}/{source['source_order']} `{source['source_sense_id']}`: "
                + " ; ".join(source["glosses"]) for source in row["sources"])
            placement = row.get("alias") or f"{row.get('bucket')}/{row.get('order')}"
            packet.append(f"| {row['review_id']} {row['stage']} {placement} | "
                          f"{markdown(sources)} | {markdown(row['wording'])} |")

    add_rows([row for row in review if row["lemma"] == "lantern" and row["stage"] == "scaffold"
              and row["alias"] in {f"S{i:03d}" for i in range(6, 13)}])
    packet += [
        "",
        "The full CSV also includes all twelve final lantern meanings and their exact",
        "references/Core/Additional placement. Compare scaffold and final to distinguish",
        "model errors from grouping/assembly. This single new attempt is not a three-repeat estimate.",
        "",
        "## Fixed stratified sample (initial compact view)",
        "",
        "Bread/useful, staff/draft, phone/quartz were fixed before inference. Below are",
        "the first two final meanings per word (all when fewer), or the first two scaffold",
        "rows if rejected. Remaining rows for these words are in the CSV; this excerpt",
        "does not imply whole-word review or certify omitted rows.",
        "",
    ]
    sample = []
    for lemma in ("bread", "useful", "staff", "draft", "phone", "quartz"):
        rows = [row for row in review if row["lemma"] == lemma]
        stage = "final" if any(row["stage"] == "final" for row in rows) else "scaffold"
        sample.extend([row for row in rows if row["stage"] == stage][:2])
    add_rows(sample)
    packet += [
        "",
        "## Requested human decisions",
        "",
        "1. Confirm/reject the lantern-class shift, omission and cross-POS contamination;",
        "   mark exact review IDs with ALIGNED, QUALIFIED, MISALIGNED or UNSUPPORTED.",
        "2. Review the fixed stratified sample and any additional suspected critical cases;",
        "   leave unreviewed rows UNJUDGED. Do not extrapolate full-dataset prevalence.",
        "3. Decide the current-role early-stop gate before any further inference.",
        "",
        "All scaffold/final rows, exact source identities and blank reviewer fields are",
        "in the paired review CSV. Failed grouping responses, complete source prompts",
        "and schemas are retained in the isolated run, with hashes in the attempt JSON.",
        "No private thinking is included. No alternate-model run/download has occurred.",
    ]
    Path(str(prefix) + "_review.md").write_text("\n".join(packet) + "\n")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("output_prefix", type=Path)
    args = parser.parse_args()
    summary = export(args.run, args.output_prefix)
    print(json.dumps({key: summary[key] for key in
                      ("word_attempts", "structurally_validated", "strata", "latency_seconds",
                       "review_rows_by_stage", "semantic_verdict")}, sort_keys=True))


if __name__ == "__main__":
    main()
