"""A4 consolidated human review: exact evidence and blank semantic labels."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

from tools.benchmarks.m002002_alternate_trial import MODELS, WORDS, frozen_evidence
from tools.benchmarks.m002002_compatibility_trial import CONTRACT, PINNED
from tools.benchmarks.m002002_product_trial import public_payload, source_rows, write_json
from vocab_lexical_engine import evidence_set_hash


def review_row(**values: Any) -> dict[str, Any]:
    return dict(values, semantic_classification="", human_reviewer="",
                semantic_flags="", learner_value="", human_reviewed=False)


def checked_sources(evidence: dict[str, Any], sources: list[dict[str, Any]]) -> None:
    exact = source_rows(evidence, [row["source_sense_id"] for row in sources])
    if exact != sources:
        raise ValueError("Review source wording/POS/order differs from frozen evidence")


def export(run: Path, pilot: Path, narrow: Path, prefix: Path) -> dict[str, Any]:
    frozen = frozen_evidence(pilot)
    result = json.loads((run / "results.json").read_text())
    narrow_manifest = json.loads((narrow / "manifest.json").read_text())
    narrow_records = [json.loads(path.read_text()) for path in sorted(narrow.glob("repeat-*-sense-*.json"))]
    if len(narrow_records) != 21:
        raise ValueError("Expected all 21 retained narrow attempts")
    rows = []
    all_evidence = dict(frozen)
    for record in narrow_records:
        evidence = frozen.get(record["lemma"])
        if evidence is None:
            evidence = json.loads((pilot / "evidence" / f"{record['lemma']}.json").read_text())
        all_evidence[record["lemma"]] = evidence
        if evidence_set_hash(evidence) != record["evidence_set_hash"]:
            raise ValueError("Narrow evidence identity mismatch")
        checked_sources(evidence, [record["source"]])
        rows.append(review_row(
            lane="A2 narrow NON-EQUIVALENT", model=narrow_manifest["model"]["name"],
            model_digest=narrow_manifest["model"]["digest"], lemma=record["lemma"],
            repeat=record["repeat"], attempt_status=record["status"],
            error_code=record.get("error_code", ""), stage="one-fixed-source",
            alias="", pos=record["source"]["pos"], bucket="",
            wording=record.get("wording", ""), sources=[record["source"]],
            evidence_set_hash=record["evidence_set_hash"], seconds=record["total_seconds"],
        ))
    summaries = []
    seen = set()
    baseline = {row["lemma"]: row for row in
                (json.loads(line) for line in (pilot / "attempts.jsonl").read_text().splitlines())}
    for model in MODELS:
        directory = run / model.replace(":", "-")
        model_attempts = [row for row in result["attempts"] if row["model"] == model]
        if not model_attempts:
            raise ValueError(f"Missing A4 candidate disposition: {model}")
        model_info = json.loads((directory / "model.json").read_text())
        if model_info["digest"] != PINNED[model]:
            raise ValueError("Candidate digest mismatch")
        first = model_attempts[0]
        if first["lemma"] != "lantern" or first["repeat"] != 1 or not first["is_probe"]:
            raise ValueError("First attempt must be the lantern probe")
        if first["status"] != "validated" and len(model_attempts) != 1:
            raise ValueError("Invalid probe was followed by unauthorized expansion")
        request_index = 0
        for attempt in model_attempts:
            identity = (model, attempt["repeat"], attempt["lemma"])
            if (identity in seen or attempt["lemma"] not in WORDS
                    or attempt["repeat"] not in (1, 2, 3)):
                raise ValueError("Duplicate or out-of-scope A4 attempt")
            seen.add(identity)
            evidence = frozen[attempt["lemma"]]
            if (attempt["evidence_set_hash"] != evidence_set_hash(evidence)
                    or attempt["comparison"] != CONTRACT or attempt["model_digest"] != PINNED[model]):
                raise ValueError("A4 evidence/contract/identity mismatch")
            attempt_dir = directory / f"r{attempt['repeat']}-{attempt['lemma']}"
            calls = [json.loads(path.read_text()) for path in sorted(attempt_dir.glob("call-*.json"))]
            original = baseline[attempt["lemma"]]
            initial = json.loads((pilot / f"{original['order']:02d}-{attempt['lemma']}" /
                                  "call-001.json").read_text())
            if not calls or any(calls[0][key] != initial[key] for key in ("prompt", "schema", "seed")):
                raise ValueError("Initial scaffold contract differs from frozen baseline")
            for call in calls:
                request_index += 1
                request = json.loads((directory / f"request-{request_index:03d}.json").read_text())
                expected = {
                    "model": model, "messages": [{"role": "user", "content": call["prompt"]}],
                    "stream": False, "format": call["schema"], "think": False, "keep_alive": "5m",
                    "options": {"temperature": 0, "num_ctx": 16384, "num_predict": 3200},
                }
                if request != expected or call["seed"] is not None:
                    raise ValueError("A4 transport changed more than the thinking option")
            review = json.loads((attempt_dir / "review.json").read_text())
            for item in review or [{}]:
                sources = item.get("sources", [])
                checked_sources(evidence, sources)
                rows.append(review_row(
                    lane=CONTRACT, model=model, model_digest=PINNED[model],
                    lemma=attempt["lemma"], repeat=attempt["repeat"],
                    attempt_status=attempt["status"], error_code=attempt.get("error_code", ""),
                    stage=item.get("stage", "no-reviewable-output"), alias=item.get("alias", ""),
                    pos=item.get("pos", ""), bucket=item.get("bucket", ""),
                    wording=item.get("wording", ""), sources=sources,
                    evidence_set_hash=attempt["evidence_set_hash"],
                    seconds=attempt["synthesis_elapsed_seconds"],
                ))
        summaries.append({
            "model": model, "attempts": len(model_attempts),
            "validated": sum(row["status"] == "validated" for row in model_attempts),
            "errors": dict(Counter(row.get("error_code") for row in model_attempts
                                   if row["status"] != "validated")),
            "median_seconds": statistics.median(row["synthesis_elapsed_seconds"] for row in model_attempts),
            "total_seconds": sum(row["synthesis_elapsed_seconds"] for row in model_attempts),
        })
    artifacts = {}
    for label, directory in (("A4", run), ("A2-narrow", narrow)):
        for path in sorted(directory.rglob("*.json")):
            value = json.loads(path.read_text())
            if public_payload(value) != value:
                raise ValueError(f"Private reasoning field persisted: {path}")
            artifacts[f"{label}/{path.relative_to(directory)}"] = hashlib.sha256(path.read_bytes()).hexdigest()
    for index, row in enumerate(rows, 1):
        row["row_id"] = f"R{index:04d}"
    report = {
        "contract": CONTRACT, "alternate_summary": summaries, "alternate_results": result,
        "narrow_attempts": 21, "narrow_validated": sum(row["status"] == "validated" for row in narrow_records),
        "narrow_median_seconds": statistics.median(row["total_seconds"] for row in narrow_records),
        "human_reviewed": 0, "semantic_classification": "", "rows": rows,
        "frozen_source_evidence": all_evidence,
        "artifact_sha256": artifacts,
    }
    write_json(Path(f"{prefix}_attempts.json"), report)
    with Path(f"{prefix}_review.csv").open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row, sources=json.dumps(row["sources"], ensure_ascii=False)))
    lines = [
        "# M002.002 consolidated human review (A4)", "",
        "## Scope and interpretation", "",
        "**Inference is stopped. Semantic labels below are intentionally blank.**",
        "A2 GPT-OSS narrow outputs and A4 alternate multi-sense outputs are NON-EQUIVALENT",
        "roles/settings. A4 changes only `think=low` to boolean `false`; no identical-contract",
        "superiority or adoption claim is supported. A3 portability failures were not",
        "semantic-quality verdicts. Prior A2 lantern corroborations remain separate.",
        "Partial scaffold wording from a rejected attempt is marked scaffold/rejected;",
        "it is not a complete validated candidate and must not be treated as saveable.",
        "Seconds shown per meaning repeat the whole word-attempt time (do not sum rows).",
        "Narrow seconds measure one sense, not a whole word.", "",
        "## Structural status and latency", "",
        "| Lane/model | Attempts | Validated final candidates | Median seconds | Errors |",
        "|---|---:|---:|---:|---|",
        f"| A2 GPT-OSS narrow | 21 | {report['narrow_validated']} | "
        f"{report['narrow_median_seconds']:.3f} / sense | four empty-content rejections |",
    ]
    for item in summaries:
        lines.append(f"| A4 {item['model']} | {item['attempts']} | {item['validated']} | "
                     f"{item['median_seconds']:.3f} / word attempt | {json.dumps(item['errors'])} |")
    lines += [
        "", "## Human review instructions", "",
        "Review exact source wording and each repeat independently. Fill the CSV's blank",
        "semantic_classification/human_reviewer/semantic_flags/learner_value fields in a",
        "review copy or return row IDs through Repo Control; original evidence is immutable.",
        "Use the governing rubric: ALIGNED / QUALIFIED / MISALIGNED / UNSUPPORTED;",
        "leave unreviewed classifications blank (UNJUDGED in the original run records).",
        "Record omission, duplication, cross-sense/POS shift, grouping and ranking as separate flags.",
        "A structurally rejected row without wording is not a semantic failure to classify.",
        "Review introduced/removed uncertainty, factual additions, omissions, alias shifts",
        "and whether wording is genuinely clearer than the source, not merely fluent.",
        f"CSV: [{prefix.name}_review.csv]({prefix.name}_review.csv).",
        f"Machine evidence: [{prefix.name}_attempts.json]({prefix.name}_attempts.json).",
        "The machine report also preserves full frozen evidence (including examples, labels",
        "and relations); the tables show exact linked glosses, not the entire source context.",
        "", "## Exact source/output rows", "",
    ]

    def cell(value: Any) -> str:
        return str(value).replace("|", "\\|").replace("\n", "<br>")

    for index, row in enumerate(rows, 1):
        lines += [
            f"### {row['row_id']}: {row['model']} / {row['lemma']} / repeat {row['repeat']}",
            f"- Lane: {row['lane']}",
            f"- Structural status: **{row['attempt_status']}**; stage `{row['stage']}`; "
            f"alias `{row['alias']}`; POS `{row['pos']}`; bucket `{row['bucket']}`; "
            f"error `{row['error_code']}`; {row['seconds']:.3f} seconds.",
            f"- Evidence hash: `{row['evidence_set_hash']}`; model digest: `{row['model_digest']}`.",
            "", "| Exact source ID / POS / order | Exact source glosses |",
            "|---|---|",
        ]
        for source in row["sources"]:
            lines.append(f"| `{source['source_sense_id']}` / {source['pos']} / "
                         f"{source['source_order']} | {cell(json.dumps(source['glosses'], ensure_ascii=False))} |")
        lines += ["", f"**Exact output:** {cell(json.dumps(row['wording'], ensure_ascii=False))}",
                  "", "Semantic classification: ______ ; reviewer: ______ ; learner value: ______", ""]
    with Path(f"{prefix}_review.md").open("x", encoding="utf-8") as stream:
        stream.write("\n".join(lines))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("run", "pilot", "narrow", "prefix"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    export(args.run, args.pilot, args.narrow, args.prefix)
