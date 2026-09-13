"""M004.6.13.3 Relation-Only Exit Gate Benchmark tool."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

# Ensure repo root is in sys.path
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import requests

from vocab_synthesis import response_content, strict_json_object

QWEN_MODEL = "qwen3:8b"
QWEN_EXPECTED_DIGEST = "500a1f067a9f782620b40bee6f7b0c89e17ae61f686b92c24933e4ca4b2b8b41"
OLLAMA_URL = os.environ.get("VOCAB_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")

QWEN_SEMANTIC_OPTIONS = {
    "think": False,
    "temperature": 0,
    "seed": 5100,
    "num_predict": 256,
    "num_ctx": 16384,
}

ALLOWED_RELATIONS = [
    "paraphrase_or_duplicate",
    "contextual_variant",
    "specialized_subsense",
    "broader_or_narrower",
    "related_but_distinct",
    "materially_different",
    "insufficient_evidence",
]

RELATION_DEFINITIONS = {
    "paraphrase_or_duplicate": (
        "The two senses express effectively the same lexical meaning. "
        "Differences are primarily wording, phrasing, or redundant dictionary decomposition."
    ),
    "contextual_variant": (
        "The two senses express the same underlying lexical meaning in different ordinary contexts "
        "or applications. The contextual difference does not create a materially different lexical concept."
    ),
    "specialized_subsense": (
        "The senses share a semantic core, but one carries a specialized domain, scope, "
        "technical meaning, or usage distinction that represents a meaningful lexical specialization."
    ),
    "broader_or_narrower": (
        "One sense semantically contains, generalizes, specializes, or is a subtype/instance "
        "of the other rather than expressing the same scope."
    ),
    "related_but_distinct": (
        "The senses are semantically related but represent meaningfully different concepts or uses."
    ),
    "materially_different": (
        "The senses represent substantively different lexical meanings."
    ),
    "insufficient_evidence": (
        "The available evidence is insufficient to classify the relationship confidently."
    ),
}

DETERMINISTIC_ACTION_MAP = {
    "paraphrase_or_duplicate": "merge",
    "contextual_variant": "merge",
    "specialized_subsense": "keep_separate",
    "broader_or_narrower": "keep_separate",
    "related_but_distinct": "keep_separate",
    "materially_different": "keep_separate",
    "insufficient_evidence": "uncertain",
}

RELATION_ONLY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "relation": {
            "type": "string",
            "enum": ALLOWED_RELATIONS,
        }
    },
    "required": ["relation"],
}


def compute_sha256(data: Any) -> str:
    if isinstance(data, (bytes, bytearray)):
        return hashlib.sha256(data).hexdigest()
    if isinstance(data, str):
        return hashlib.sha256(data.encode("utf-8")).hexdigest()
    text = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compute_file_sha256(filepath: str | Path) -> str:
    return hashlib.sha256(Path(filepath).read_bytes()).hexdigest()


def selection_hash_for_pair(pair_id: str) -> str:
    return compute_sha256(f"m004.6.13.3-final-exit-v1|{pair_id}")


def select_exit_gate_sample(
    reference_data: Mapping[str, Any],
    m132_selection_data: Mapping[str, Any],
) -> dict[str, Any]:
    """Select 20 MERGE, 40 KEEP, and up to 6 UNCERTAIN pairs excluding M004.6.13.2 pairs."""
    m132_sample = m132_selection_data.get("sample", [])
    excluded_ids = {item["pair_id"] for item in m132_sample}

    all_pairs = reference_data.get("candidate_pairs", [])
    merges = []
    keeps = []
    uncertains = []

    for item in all_pairs:
        pair_id = item["pair_id"]
        if pair_id in excluded_ids:
            continue

        decision = item["reference_decision"]
        s_hash = selection_hash_for_pair(pair_id)
        record = {
            "pair_id": pair_id,
            "word": item["word"],
            "pos": item["pos"],
            "reference_decision": decision,
            "reference_reason": item.get("reference_reason") or item.get("review_notes", ""),
            "selection_hash": s_hash,
            "first": item["first"],
            "second": item["second"],
            "partition_id": item.get("partition_id", ""),
        }
        if decision == "merge":
            merges.append(record)
        elif decision == "keep_separate":
            keeps.append(record)
        elif decision == "uncertain":
            uncertains.append(record)

    merges.sort(key=lambda x: x["selection_hash"])
    keeps.sort(key=lambda x: x["selection_hash"])
    uncertains.sort(key=lambda x: x["selection_hash"])

    if len(merges) < 20 or len(keeps) < 40:
        raise ValueError(
            f"Insufficient pairs available after excluding M004.6.13.2: got {len(merges)} merges, {len(keeps)} keeps"
        )

    selected_merges = merges[:20]
    selected_keeps = keeps[:40]
    selected_uncertains = uncertains[:6]

    primary_sample = selected_merges + selected_keeps
    primary_sample.sort(key=lambda x: x["pair_id"])

    return {
        "excluded_m132_count": len(excluded_ids),
        "primary_sample": primary_sample,
        "auxiliary_uncertain_sample": selected_uncertains,
    }


def build_sense_view(node: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "source_sense_id": node["source_sense_id"],
        "definitions": list(node.get("definition", node.get("glosses", []))),
        "labels": sorted(node.get("labels", [])),
        "examples": [
            ex.get("text") if isinstance(ex, Mapping) else ex
            for ex in node.get("examples", [])
        ],
        "relations": [
            {"type": rel.get("type"), "target": rel.get("target")}
            for rel in node.get("relations", [])
            if isinstance(rel, Mapping)
        ],
    }


def build_relation_only_prompt(pair_record: Mapping[str, Any]) -> str:
    payload = {
        "task": "Classify the semantic relationship between these two dictionary senses. Return exactly one relation from the allowed relation set.",
        "allowed_relation_definitions": RELATION_DEFINITIONS,
        "word": pair_record["word"],
        "part_of_speech": pair_record["pos"],
        "material_partition": list(pair_record["first"].get("material_partition", [])),
        "sense_a": build_sense_view(pair_record["first"]),
        "sense_b": build_sense_view(pair_record["second"]),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def derive_action_from_relation(relation: str | None) -> str | None:
    if not relation or relation not in ALLOWED_RELATIONS:
        return None
    return DETERMINISTIC_ACTION_MAP.get(relation)


def evaluate_exit_gate_metrics(
    primary_results: list[dict[str, Any]],
) -> dict[str, Any]:
    total_scored = len(primary_results)
    ref_merge_count = 0
    ref_keep_count = 0

    derived_merge_count = 0
    derived_keep_count = 0
    derived_uncertain_count = 0

    malformed_count = 0
    invalid_relation_count = 0

    action_agreement_count = 0

    merge_tp = 0
    merge_fn = 0

    keep_correct = 0
    keep_to_merge_disagreement = 0
    keep_to_uncertain_disagreement = 0

    merge_to_keep_disagreement = 0
    merge_to_uncertain_disagreement = 0

    relation_counts = {rel: 0 for rel in ALLOWED_RELATIONS}

    for item in primary_results:
        ref_dec = item["reference_decision"]
        if ref_dec == "merge":
            ref_merge_count += 1
        elif ref_dec == "keep_separate":
            ref_keep_count += 1

        is_parse_error = item.get("parse_error", False)
        if is_parse_error:
            malformed_count += 1

        rel = item.get("relation")
        if rel in relation_counts:
            relation_counts[rel] += 1
        elif not is_parse_error:
            invalid_relation_count += 1

        derived_act = item.get("derived_action")
        if derived_act == "merge":
            derived_merge_count += 1
        elif derived_act == "keep_separate":
            derived_keep_count += 1
        elif derived_act == "uncertain":
            derived_uncertain_count += 1

        if derived_act == ref_dec:
            action_agreement_count += 1

        if ref_dec == "merge":
            if derived_act == "merge":
                merge_tp += 1
            elif derived_act == "keep_separate":
                merge_fn += 1
                merge_to_keep_disagreement += 1
            elif derived_act == "uncertain":
                merge_fn += 1
                merge_to_uncertain_disagreement += 1
        elif ref_dec == "keep_separate":
            if derived_act == "keep_separate":
                keep_correct += 1
            elif derived_act == "merge":
                keep_to_merge_disagreement += 1
            elif derived_act == "uncertain":
                keep_to_uncertain_disagreement += 1

    action_agreement_rate = (
        action_agreement_count / total_scored if total_scored > 0 else 0.0
    )
    merge_recall = merge_tp / ref_merge_count if ref_merge_count > 0 else 0.0
    keep_recall = keep_correct / ref_keep_count if ref_keep_count > 0 else 0.0

    keep_to_merge_rate = (
        keep_to_merge_disagreement / ref_keep_count if ref_keep_count > 0 else 0.0
    )
    merge_to_keep_rate = (
        merge_to_keep_disagreement / ref_merge_count if ref_merge_count > 0 else 0.0
    )
    uncertain_rate = (
        derived_uncertain_count / total_scored if total_scored > 0 else 0.0
    )

    return {
        "total_primary_scored": total_scored,
        "ref_merge_count": ref_merge_count,
        "ref_keep_count": ref_keep_count,
        "derived_merge_count": derived_merge_count,
        "derived_keep_count": derived_keep_count,
        "derived_uncertain_count": derived_uncertain_count,
        "overall_action_agreement_count": action_agreement_count,
        "overall_action_agreement_rate": action_agreement_rate,
        "merge_reference_recall": merge_recall,
        "merge_tp": merge_tp,
        "merge_fn": merge_fn,
        "keep_reference_recall": keep_recall,
        "keep_correct": keep_correct,
        "keep_to_merge_disagreement_count": keep_to_merge_disagreement,
        "keep_to_merge_disagreement_rate": keep_to_merge_rate,
        "merge_to_keep_disagreement_count": merge_to_keep_disagreement,
        "merge_to_keep_disagreement_rate": merge_to_keep_rate,
        "merge_to_uncertain_disagreement_count": merge_to_uncertain_disagreement,
        "keep_to_uncertain_disagreement_count": keep_to_uncertain_disagreement,
        "derived_uncertain_rate": uncertain_rate,
        "malformed_output_count": malformed_count,
        "invalid_relation_count": invalid_relation_count,
        "relation_distribution": relation_counts,
    }


def evaluate_gate_pass(metrics: Mapping[str, Any]) -> dict[str, Any]:
    cond_malformed = metrics["malformed_output_count"] == 0
    cond_invalid = metrics["invalid_relation_count"] == 0
    cond_no_collapse = (
        metrics["derived_merge_count"] > 0 and metrics["derived_keep_count"] > 0
    )
    cond_merge_recall = metrics["merge_reference_recall"] >= 0.60  # >= 12 / 20
    cond_keep_to_merge = (
        metrics["keep_to_merge_disagreement_count"] <= 4
    )  # <= 10% (4 / 40)
    cond_uncertain_rate = (
        metrics["derived_uncertain_count"] <= 6
    )  # <= 10% (6 / 60)

    is_go = (
        cond_malformed
        and cond_invalid
        and cond_no_collapse
        and cond_merge_recall
        and cond_keep_to_merge
        and cond_uncertain_rate
    )

    disposition = "GO" if is_go else "NO_GO"

    return {
        "disposition": disposition,
        "is_go": is_go,
        "zero_malformed": cond_malformed,
        "zero_invalid_relations": cond_invalid,
        "no_semantic_collapse": cond_no_collapse,
        "merge_recall_gte_60_pct": cond_merge_recall,
        "keep_to_merge_lte_10_pct": cond_keep_to_merge,
        "uncertain_rate_lte_10_pct": cond_uncertain_rate,
    }


def generate_review_packet(
    primary_results: list[dict[str, Any]],
    auxiliary_results: list[dict[str, Any]],
) -> tuple[dict[str, Any], str]:
    """Generate review_packet.json data and review_packet.md Markdown string."""
    keep_to_merge = []
    merge_to_keep = []
    merge_to_uncertain = []
    keep_to_uncertain = []
    aux_uncertain_results = []

    for item in primary_results:
        ref_dec = item["reference_decision"]
        derived_act = item.get("derived_action")
        rel = item.get("relation")

        entry = {
            "pair_id": item["pair_id"],
            "word": item["word"],
            "pos": item["pos"],
            "returned_relation": rel,
            "derived_action": derived_act,
            "reference_decision": ref_dec,
            "reference_reason": item.get("reference_reason", ""),
            "sense_a_definitions": list(
                item["first"].get("definition", item["first"].get("glosses", []))
            ),
            "sense_b_definitions": list(
                item["second"].get("definition", item["second"].get("glosses", []))
            ),
        }

        if ref_dec == "keep_separate" and derived_act == "merge":
            keep_to_merge.append(entry)
        elif ref_dec == "merge" and derived_act == "keep_separate":
            merge_to_keep.append(entry)
        elif ref_dec == "merge" and derived_act == "uncertain":
            merge_to_uncertain.append(entry)
        elif ref_dec == "keep_separate" and derived_act == "uncertain":
            keep_to_uncertain.append(entry)

    for item in auxiliary_results:
        entry = {
            "pair_id": item["pair_id"],
            "word": item["word"],
            "pos": item["pos"],
            "returned_relation": item.get("relation"),
            "derived_action": item.get("derived_action"),
            "reference_decision": item["reference_decision"],
            "reference_reason": item.get("reference_reason", ""),
            "sense_a_definitions": list(
                item["first"].get("definition", item["first"].get("glosses", []))
            ),
            "sense_b_definitions": list(
                item["second"].get("definition", item["second"].get("glosses", []))
            ),
        }
        aux_uncertain_results.append(entry)

    json_data = {
        "keep_to_merge_disagreements": keep_to_merge,
        "merge_to_keep_disagreements": merge_to_keep,
        "merge_to_uncertain_disagreements": merge_to_uncertain,
        "keep_to_uncertain_disagreements": keep_to_uncertain,
        "auxiliary_uncertain_results": aux_uncertain_results,
    }

    # Build Markdown document
    lines = [
        "# M004.6.13.3 Relation-Only Exit Gate — Human Review Packet",
        "",
        f"**Generated:** {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Summary of Disagreements",
        f"- **KEEP→MERGE Disagreements:** {len(keep_to_merge)}",
        f"- **MERGE→KEEP Disagreements:** {len(merge_to_keep)}",
        f"- **MERGE→UNCERTAIN Results:** {len(merge_to_uncertain)}",
        f"- **KEEP→UNCERTAIN Results:** {len(keep_to_uncertain)}",
        f"- **Auxiliary UNCERTAIN Pair Evaluations:** {len(aux_uncertain_results)}",
        "",
    ]

    def _render_entries(title: str, entries: list[dict[str, Any]]):
        lines.append(f"## {title}")
        lines.append("")
        if not entries:
            lines.append("*(None)*")
            lines.append("")
            return

        for idx, e in enumerate(entries, 1):
            lines.append(f"### {idx}. `{e['word']}` ({e['pos']}) — Pair ID: `{e['pair_id']}`")
            lines.append(f"- **Returned Relation:** `{e['returned_relation']}`")
            lines.append(f"- **Derived Action:** `{e['derived_action']}`")
            lines.append(f"- **Reference Decision:** `{e['reference_decision']}`")
            if e.get("reference_reason"):
                lines.append(f"- **Reference Notes:** {e['reference_reason']}")
            lines.append("- **Sense A Glosses:**")
            for g in e["sense_a_definitions"]:
                lines.append(f"  - {g}")
            lines.append("- **Sense B Glosses:**")
            for g in e["sense_b_definitions"]:
                lines.append(f"  - {g}")
            lines.append("")

    _render_entries("KEEP→MERGE Disagreements (Safety Critical)", keep_to_merge)
    _render_entries("MERGE→KEEP Disagreements (Recall)", merge_to_keep)
    _render_entries("MERGE→UNCERTAIN Results", merge_to_uncertain)
    _render_entries("KEEP→UNCERTAIN Results", keep_to_uncertain)
    _render_entries("Auxiliary Reference UNCERTAIN Pair Results", aux_uncertain_results)

    return json_data, "\n".join(lines)


def invoke_qwen_relation_chat(
    prompt: str,
    endpoint: str = OLLAMA_URL,
    model: str = QWEN_MODEL,
    options: Mapping[str, Any] = QWEN_SEMANTIC_OPTIONS,
) -> dict[str, Any]:
    url = f"{endpoint}/api/chat"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "format": RELATION_ONLY_SCHEMA,
        "think": bool(options.get("think", False)),
        "keep_alive": "5m",
        "options": {
            "temperature": options.get("temperature", 0),
            "seed": options.get("seed"),
            "num_predict": options.get("num_predict", 256),
            "num_ctx": options.get("num_ctx", 16384),
        },
    }

    start_time = time.time()
    for attempt in range(1, 3):
        try:
            resp = requests.post(url, json=payload, timeout=120)
            if resp.status_code == 200:
                body = resp.json()
                content = response_content(body)
                parsed = strict_json_object(content)
                relation = parsed.get("relation")
                derived_act = derive_action_from_relation(relation)
                return {
                    "status": "provider_success",
                    "raw_body": body,
                    "content": content,
                    "parsed": parsed,
                    "relation": relation,
                    "derived_action": derived_act,
                    "eval_count": body.get("eval_count"),
                    "done_reason": body.get("done_reason"),
                    "attempt": attempt,
                    "elapsed_sec": round(time.time() - start_time, 3),
                }
            elif resp.status_code >= 500 and attempt == 1:
                time.sleep(1)
                continue
            else:
                return {
                    "status": "http_error",
                    "status_code": resp.status_code,
                    "error": resp.text[:500],
                    "attempt": attempt,
                    "elapsed_sec": round(time.time() - start_time, 3),
                }
        except Exception as err:
            if attempt == 1 and isinstance(err, requests.RequestException):
                time.sleep(1)
                continue
            return {
                "status": "failure",
                "parse_error": True,
                "error": str(err),
                "attempt": attempt,
                "elapsed_sec": round(time.time() - start_time, 3),
            }

    return {"status": "failure", "parse_error": True, "error": "Exhausted attempts", "attempt": 2}


def run_benchmark(
    reference_path: Path,
    m132_selection_path: Path,
    output_dir: Path,
    endpoint: str = OLLAMA_URL,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)

    ref_data = json.loads(reference_path.read_text())
    m132_data = json.loads(m132_selection_path.read_text())

    sample_dict = select_exit_gate_sample(ref_data, m132_data)
    primary_sample = sample_dict["primary_sample"]
    auxiliary_sample = sample_dict["auxiliary_uncertain_sample"]

    # Save frozen selection.json BEFORE any inference!
    selection_file = output_dir / "selection.json"
    selection_payload = {
        "primary_sample": primary_sample,
        "auxiliary_uncertain_sample": auxiliary_sample,
        "excluded_m132_count": sample_dict["excluded_m132_count"],
    }
    selection_file.write_text(json.dumps(selection_payload, indent=2, sort_keys=True))
    selection_sha256 = compute_file_sha256(selection_file)

    requests_file = output_dir / "requests.jsonl"
    responses_file = output_dir / "responses.jsonl"
    results_file = output_dir / "results.json"
    csv_file = output_dir / "results.csv"
    summary_file = output_dir / "summary.json"
    review_pkt_json_file = output_dir / "review_packet.json"
    review_pkt_md_file = output_dir / "review_packet.md"

    primary_results = []
    auxiliary_results = []
    csv_rows = []

    total_calls_made = 0

    with requests_file.open("w") as req_out, responses_file.open("w") as resp_out:
        # Run Primary Sample (60 pairs)
        for pair in primary_sample:
            pair_id = pair["pair_id"]
            prompt = build_relation_only_prompt(pair)

            req_record = {
                "sample_group": "primary",
                "pair_id": pair_id,
                "prompt": prompt,
                "schema": RELATION_ONLY_SCHEMA,
                "model": QWEN_MODEL,
                "options": QWEN_SEMANTIC_OPTIONS,
                "prompt_sha256": compute_sha256(prompt),
                "schema_sha256": compute_sha256(RELATION_ONLY_SCHEMA),
            }
            req_out.write(json.dumps(req_record) + "\n")
            req_out.flush()

            res = invoke_qwen_relation_chat(
                prompt=prompt,
                endpoint=endpoint,
                model=QWEN_MODEL,
                options=QWEN_SEMANTIC_OPTIONS,
            )
            total_calls_made += res.get("attempt", 1)

            resp_record = {
                "sample_group": "primary",
                "pair_id": pair_id,
                "response": res,
            }
            resp_out.write(json.dumps(resp_record) + "\n")
            resp_out.flush()

            relation = res.get("relation")
            derived_act = res.get("derived_action")
            parse_err = res.get("parse_error", False)

            res_entry = {
                **pair,
                "relation": relation,
                "derived_action": derived_act,
                "parse_error": parse_err,
                "provider_status": res.get("status"),
                "elapsed_sec": res.get("elapsed_sec"),
            }
            primary_results.append(res_entry)

            csv_rows.append(
                {
                    "group": "primary",
                    "pair_id": pair_id,
                    "word": pair["word"],
                    "pos": pair["pos"],
                    "reference_decision": pair["reference_decision"],
                    "relation": relation or "",
                    "derived_action": derived_act or "",
                    "action_match": (derived_act == pair["reference_decision"]),
                    "elapsed_sec": res.get("elapsed_sec", 0.0),
                }
            )

        # Run Auxiliary Sample (up to 6 pairs)
        for pair in auxiliary_sample:
            pair_id = pair["pair_id"]
            prompt = build_relation_only_prompt(pair)

            req_record = {
                "sample_group": "auxiliary_uncertain",
                "pair_id": pair_id,
                "prompt": prompt,
                "schema": RELATION_ONLY_SCHEMA,
                "model": QWEN_MODEL,
                "options": QWEN_SEMANTIC_OPTIONS,
                "prompt_sha256": compute_sha256(prompt),
                "schema_sha256": compute_sha256(RELATION_ONLY_SCHEMA),
            }
            req_out.write(json.dumps(req_record) + "\n")
            req_out.flush()

            res = invoke_qwen_relation_chat(
                prompt=prompt,
                endpoint=endpoint,
                model=QWEN_MODEL,
                options=QWEN_SEMANTIC_OPTIONS,
            )
            total_calls_made += res.get("attempt", 1)

            resp_record = {
                "sample_group": "auxiliary_uncertain",
                "pair_id": pair_id,
                "response": res,
            }
            resp_out.write(json.dumps(resp_record) + "\n")
            resp_out.flush()

            relation = res.get("relation")
            derived_act = res.get("derived_action")
            parse_err = res.get("parse_error", False)

            res_entry = {
                **pair,
                "relation": relation,
                "derived_action": derived_act,
                "parse_error": parse_err,
                "provider_status": res.get("status"),
                "elapsed_sec": res.get("elapsed_sec"),
            }
            auxiliary_results.append(res_entry)

            csv_rows.append(
                {
                    "group": "auxiliary_uncertain",
                    "pair_id": pair_id,
                    "word": pair["word"],
                    "pos": pair["pos"],
                    "reference_decision": pair["reference_decision"],
                    "relation": relation or "",
                    "derived_action": derived_act or "",
                    "action_match": (derived_act == pair["reference_decision"]),
                    "elapsed_sec": res.get("elapsed_sec", 0.0),
                }
            )

    # Save results.json
    results_payload = {
        "primary_results": primary_results,
        "auxiliary_uncertain_results": auxiliary_results,
    }
    results_file.write_text(json.dumps(results_payload, indent=2, sort_keys=True))
    results_sha256 = compute_file_sha256(results_file)

    # Save results.csv
    fieldnames = [
        "group",
        "pair_id",
        "word",
        "pos",
        "reference_decision",
        "relation",
        "derived_action",
        "action_match",
        "elapsed_sec",
    ]
    with csv_file.open("w", newline="") as f_csv:
        writer = csv.DictWriter(f_csv, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(csv_rows)

    metrics = evaluate_exit_gate_metrics(primary_results)
    gate = evaluate_gate_pass(metrics)

    # Generate review packet
    pkt_json, pkt_md = generate_review_packet(primary_results, auxiliary_results)
    review_pkt_json_file.write_text(json.dumps(pkt_json, indent=2, sort_keys=True))
    review_pkt_md_file.write_text(pkt_md)

    review_pkt_json_sha256 = compute_file_sha256(review_pkt_json_file)
    review_pkt_md_sha256 = compute_file_sha256(review_pkt_md_file)

    summary_data = {
        "benchmark": "M004.6.13.3 Relation-Only Exit Gate",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": QWEN_MODEL,
        "model_expected_digest": QWEN_EXPECTED_DIGEST,
        "options": QWEN_SEMANTIC_OPTIONS,
        "total_calls_made": total_calls_made,
        "selection_sha256": selection_sha256,
        "results_sha256": results_sha256,
        "review_packet_json_sha256": review_pkt_json_sha256,
        "review_packet_md_sha256": review_pkt_md_sha256,
        "metrics": metrics,
        "exit_gate": gate,
    }

    summary_file.write_text(json.dumps(summary_data, indent=2, sort_keys=True))

    return summary_data


if __name__ == "__main__":
    default_ref = Path(
        "/home/chuck/.local/share/vocab-app/benchmarks/m004.6.6/20260910T234324Z/reference_adjudicated_v3.json"
    )
    default_m132 = Path(
        "/home/chuck/.local/share/vocab-app/benchmarks/m004.6.13.2/20260913T162300Z/selection.json"
    )
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    default_out = Path(f"/home/chuck/.local/share/vocab-app/benchmarks/m004.6.13.3/{ts}")

    out_summary = run_benchmark(default_ref, default_m132, default_out)
    print("\n" + "=" * 60)
    print(f"M004.6.13.3 Benchmark Completed: {default_out}")
    print(f"Disposition: {out_summary['exit_gate']['disposition']}")
    print(f"Total Calls: {out_summary['total_calls_made']}")
    print(f"Metrics: {json.dumps(out_summary['metrics'], indent=2)}")
    print(f"Gate Evaluation: {json.dumps(out_summary['exit_gate'], indent=2)}")
    print("=" * 60)
