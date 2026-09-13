"""M004.6.13.2 Semantic Contract Calibration Benchmark tool."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping

# Ensure repo root is in sys.path
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import requests

from vocab_consolidation import (
    PAIR_JUDGMENT_CONTRACT_V1,
    PAIR_JUDGMENT_CONTRACT_V2,
    VALID_DECISION_REASONS,
    ConsolidationPartition,
    SensePair,
    build_partitions,
    enumerate_pairs,
)
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

POLICY_V1 = (
    "Merge only near-paraphrase, duplicate, or contextual-application variants. "
    "Keep specialized, broader/narrower, related-but-distinct, materially different, "
    "and uncertain senses separate. Prefer false splits."
)

POLICY_V2 = (
    "Merge only near-paraphrase, duplicate, or contextual-application variants. "
    "Keep specialized, broader/narrower, related-but-distinct, materially different, "
    "and uncertain senses separate. Prefer false splits. "
    "The decision and reason must be internally consistent: if the senses have a "
    "specialized, broader/narrower, related-but-distinct, or materially different "
    "relationship, the decision must be keep_separate, not merge. The decision "
    "merge is permitted only when the reason is paraphrase_or_duplicate or "
    "contextual_variant."
)

SCHEMA_V1 = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "decision": {"type": "string", "enum": ["merge", "keep_separate", "uncertain"]},
        "reason": {
            "type": "string",
            "enum": [
                "paraphrase_or_duplicate",
                "contextual_variant",
                "specialized_subsense",
                "broader_or_narrower",
                "related_but_distinct",
                "materially_different",
                "insufficient_evidence",
            ],
        },
    },
    "required": ["decision", "reason"],
}

SCHEMA_V2 = {
    "oneOf": [
        {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "decision": {"const": "merge"},
                "reason": {
                    "type": "string",
                    "enum": ["paraphrase_or_duplicate", "contextual_variant"],
                },
            },
            "required": ["decision", "reason"],
        },
        {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "decision": {"const": "keep_separate"},
                "reason": {
                    "type": "string",
                    "enum": [
                        "specialized_subsense",
                        "broader_or_narrower",
                        "related_but_distinct",
                        "materially_different",
                    ],
                },
            },
            "required": ["decision", "reason"],
        },
        {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "decision": {"const": "uncertain"},
                "reason": {"const": "insufficient_evidence"},
            },
            "required": ["decision", "reason"],
        },
    ],
}

CONFIGURATIONS = {
    "A": {"name": "Historical Baseline", "prompt_version": "v1", "policy": POLICY_V1, "schema": SCHEMA_V1, "schema_version": "v1_flat"},
    "B": {"name": "Schema-Only Hardening", "prompt_version": "v1", "policy": POLICY_V1, "schema": SCHEMA_V2, "schema_version": "v2_oneof"},
    "C": {"name": "Prompt-Only Hardening", "prompt_version": "v2", "policy": POLICY_V2, "schema": SCHEMA_V1, "schema_version": "v1_flat"},
    "D": {"name": "Current v2", "prompt_version": "v2", "policy": POLICY_V2, "schema": SCHEMA_V2, "schema_version": "v2_oneof"},
}

SENTINELS = {
    "charge:noun:8b49b912413a:c1f8d19006ac7ddf",
    "cleave:verb:06bbcdfef61b:b90d5075d1e6ab47",
    "charge:noun:8b49b912413a:5a79e6778413c507",
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
    return compute_sha256(f"m004.6.13.2-calibration-v1|{pair_id}")


def select_calibration_sample(reference_data: Mapping[str, Any]) -> list[dict[str, Any]]:
    pairs = reference_data.get("candidate_pairs", [])
    merges = []
    keeps = []

    for item in pairs:
        pair_id = item["pair_id"]
        decision = item["reference_decision"]
        if decision not in ("merge", "keep_separate"):
            continue

        s_hash = selection_hash_for_pair(pair_id)
        record = {
            "pair_id": pair_id,
            "word": item["word"],
            "pos": item["pos"],
            "reference_decision": decision,
            "review_notes": item.get("review_notes", ""),
            "selection_hash": s_hash,
            "is_sentinel": pair_id in SENTINELS,
            "first": item["first"],
            "second": item["second"],
            "partition_id": item.get("partition_id", ""),
        }
        if decision == "merge":
            merges.append(record)
        elif decision == "keep_separate":
            keeps.append(record)

    selected_merges = [m for m in merges if m["is_sentinel"]]
    remaining_merges = [m for m in merges if not m["is_sentinel"]]
    remaining_merges.sort(key=lambda x: x["selection_hash"])
    selected_merges.extend(remaining_merges[: (8 - len(selected_merges))])

    selected_keeps = [k for k in keeps if k["is_sentinel"]]
    remaining_keeps = [k for k in keeps if not k["is_sentinel"]]
    remaining_keeps.sort(key=lambda x: x["selection_hash"])
    selected_keeps.extend(remaining_keeps[: (8 - len(selected_keeps))])

    if len(selected_merges) != 8 or len(selected_keeps) != 8:
        raise ValueError(
            f"Unable to select required sample size: got {len(selected_merges)} merges, {len(selected_keeps)} keeps"
        )

    # Sort deterministically by pair_id
    sample = selected_merges + selected_keeps
    sample.sort(key=lambda x: x["pair_id"])
    return sample


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


def build_prompt_for_config(pair_record: Mapping[str, Any], policy: str) -> str:
    payload = {
        "task": "Return exactly one JSON object matching the required schema.",
        "learner_consolidation_policy": policy,
        "word": pair_record["word"],
        "part_of_speech": pair_record["pos"],
        "material_partition": list(pair_record["first"].get("material_partition", [])),
        "sense_a": build_sense_view(pair_record["first"]),
        "sense_b": build_sense_view(pair_record["second"]),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def is_full_contract_valid(decision: str | None, reason: str | None) -> bool:
    if not decision or not reason:
        return False
    allowed = VALID_DECISION_REASONS.get(decision)
    if not allowed:
        return False
    return reason in allowed


def evaluate_results(scored_pairs: list[dict[str, Any]], results: list[dict[str, Any]]) -> dict[str, Any]:
    total_pairs = len(scored_pairs)
    exact_accuracy_count = 0
    merge_tp = 0
    merge_fn = 0
    predicted_merge_count = 0
    keep_separate_correct = 0
    keep_separate_total = sum(1 for p in scored_pairs if p["reference_decision"] == "keep_separate")
    merge_total = sum(1 for p in scored_pairs if p["reference_decision"] == "merge")
    false_merges = 0
    false_splits = 0
    ref_merge_pred_uncertain = 0
    ref_keep_pred_uncertain = 0
    contract_invalid_count = 0
    malformed_count = 0
    reason_agreements = 0

    confusion_matrix: dict[str, dict[str, int]] = {
        "merge": {"merge": 0, "keep_separate": 0, "uncertain": 0, "invalid/malformed": 0},
        "keep_separate": {"merge": 0, "keep_separate": 0, "uncertain": 0, "invalid/malformed": 0},
    }

    results_by_pair = {r["pair_id"]: r for r in results}

    for pair in scored_pairs:
        pair_id = pair["pair_id"]
        ref_dec = pair["reference_decision"]
        res = results_by_pair.get(pair_id, {})
        status = res.get("status")
        pred_dec = res.get("decision")
        pred_reason = res.get("reason")
        is_valid = res.get("full_contract_valid", False)

        if status != "provider_success" or not is_valid:
            if status != "provider_success":
                malformed_count += 1
            else:
                contract_invalid_count += 1
            confusion_matrix[ref_dec]["invalid/malformed"] += 1
            if ref_dec == "merge":
                merge_fn += 1
            continue

        if pred_dec in ("merge", "keep_separate", "uncertain"):
            confusion_matrix[ref_dec][pred_dec] += 1

        if pred_dec == ref_dec:
            exact_accuracy_count += 1

        if pred_dec == "merge":
            predicted_merge_count += 1
            if ref_dec == "merge":
                merge_tp += 1
            elif ref_dec == "keep_separate":
                false_merges += 1
        elif pred_dec == "keep_separate":
            if ref_dec == "keep_separate":
                keep_separate_correct += 1
            elif ref_dec == "merge":
                false_splits += 1
                merge_fn += 1
        elif pred_dec == "uncertain":
            if ref_dec == "merge":
                ref_merge_pred_uncertain += 1
                merge_fn += 1
            elif ref_dec == "keep_separate":
                ref_keep_pred_uncertain += 1

    exact_accuracy = exact_accuracy_count / total_pairs if total_pairs > 0 else 0.0
    merge_recall = merge_tp / merge_total if merge_total > 0 else 0.0
    merge_precision = merge_tp / predicted_merge_count if predicted_merge_count > 0 else 0.0
    keep_separate_recall = keep_separate_correct / keep_separate_total if keep_separate_total > 0 else 0.0
    false_merge_rate = false_merges / keep_separate_total if keep_separate_total > 0 else 0.0

    return {
        "total_scored_pairs": total_pairs,
        "exact_decision_accuracy": exact_accuracy,
        "merge_true_positives": merge_tp,
        "merge_false_negatives": merge_fn,
        "merge_recall": merge_recall,
        "predicted_merge_count": predicted_merge_count,
        "merge_precision": merge_precision,
        "keep_separate_correct": keep_separate_correct,
        "keep_separate_recall": keep_separate_recall,
        "false_merge_count": false_merges,
        "false_merge_rate": false_merge_rate,
        "false_split_count": false_splits,
        "ref_merge_pred_uncertain_count": ref_merge_pred_uncertain,
        "ref_keep_pred_uncertain_count": ref_keep_pred_uncertain,
        "contract_invalid_count": contract_invalid_count,
        "malformed_parse_error_count": malformed_count,
        "confusion_matrix": confusion_matrix,
    }


def check_calibration_gate(metrics: Mapping[str, Any]) -> dict[str, Any]:
    cond_false_merges = metrics["false_merge_count"] == 0
    cond_invalid = metrics["contract_invalid_count"] == 0
    cond_recall = metrics["merge_recall"] >= 0.75
    cond_malformed = metrics["malformed_parse_error_count"] == 0
    cond_no_collapse = metrics["predicted_merge_count"] > 0 and metrics["keep_separate_correct"] > 0

    all_pass = cond_false_merges and cond_invalid and cond_recall and cond_malformed and cond_no_collapse

    return {
        "gate_pass": all_pass,
        "zero_false_merges": cond_false_merges,
        "zero_contract_invalid": cond_invalid,
        "merge_recall_gte_75": cond_recall,
        "zero_malformed": cond_malformed,
        "no_semantic_collapse": cond_no_collapse,
    }


def invoke_qwen_chat(
    prompt: str,
    schema: Mapping[str, Any],
    endpoint: str = OLLAMA_URL,
    model: str = QWEN_MODEL,
    options: Mapping[str, Any] = QWEN_SEMANTIC_OPTIONS,
) -> dict[str, Any]:
    url = f"{endpoint}/api/chat"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "format": schema,
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
                decision = parsed.get("decision")
                reason = parsed.get("reason")
                return {
                    "status": "provider_success",
                    "raw_body": body,
                    "content": content,
                    "parsed": parsed,
                    "decision": decision,
                    "reason": reason,
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
        except (requests.RequestException, SynthesisFailure, ValueError) as err:
            if attempt == 1 and isinstance(err, requests.RequestException):
                time.sleep(1)
                continue
            return {
                "status": "failure",
                "error": str(err),
                "attempt": attempt,
                "elapsed_sec": round(time.time() - start_time, 3),
            }

    return {"status": "failure", "error": "Exhausted attempts", "attempt": 2}


def run_benchmark(
    reference_path: Path,
    output_dir: Path,
    endpoint: str = OLLAMA_URL,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)

    ref_data = json.loads(reference_path.read_text())
    scored_sample = select_calibration_sample(ref_data)

    # Save frozen selection.json BEFORE any inference!
    selection_file = output_dir / "selection.json"
    selection_file.write_text(json.dumps({"sample": scored_sample}, indent=2, sort_keys=True))
    selection_sha256 = compute_file_sha256(selection_file)

    requests_file = output_dir / "requests.jsonl"
    responses_file = output_dir / "responses.jsonl"
    results_file = output_dir / "results.json"
    csv_file = output_dir / "results.csv"
    summary_file = output_dir / "summary.json"

    all_results = []
    csv_rows = []
    
    total_calls_made = 0

    with requests_file.open("w") as req_out, responses_file.open("w") as resp_out:
        for config_key in ("A", "B", "C", "D"):
            cfg = CONFIGURATIONS[config_key]
            policy = cfg["policy"]
            schema = cfg["schema"]

            for pair in scored_sample:
                pair_id = pair["pair_id"]
                prompt = build_prompt_for_config(pair, policy)

                req_record = {
                    "config": config_key,
                    "pair_id": pair_id,
                    "prompt": prompt,
                    "schema": schema,
                    "model": QWEN_MODEL,
                    "options": QWEN_SEMANTIC_OPTIONS,
                    "prompt_sha256": compute_sha256(prompt),
                    "schema_sha256": compute_sha256(schema),
                }
                req_out.write(json.dumps(req_record) + "\n")
                req_out.flush()

                res = invoke_qwen_chat(
                    prompt=prompt,
                    schema=schema,
                    endpoint=endpoint,
                    model=QWEN_MODEL,
                    options=QWEN_SEMANTIC_OPTIONS,
                )
                total_calls_made += res.get("attempt", 1)

                resp_record = {
                    "config": config_key,
                    "pair_id": pair_id,
                    "response": res,
                }
                resp_out.write(json.dumps(resp_record) + "\n")
                resp_out.flush()

                decision = res.get("decision")
                reason = res.get("reason")
                full_valid = is_full_contract_valid(decision, reason)

                result_record = {
                    "config": config_key,
                    "pair_id": pair_id,
                    "word": pair["word"],
                    "pos": pair["pos"],
                    "reference_decision": pair["reference_decision"],
                    "status": res.get("status"),
                    "decision": decision,
                    "reason": reason,
                    "full_contract_valid": full_valid,
                    "eval_count": res.get("eval_count"),
                    "done_reason": res.get("done_reason"),
                    "attempt": res.get("attempt", 1),
                    "elapsed_sec": res.get("elapsed_sec", 0.0),
                }
                all_results.append(result_record)

                csv_rows.append({
                    "config": config_key,
                    "pair_id": pair_id,
                    "word": pair["word"],
                    "pos": pair["pos"],
                    "reference_decision": pair["reference_decision"],
                    "predicted_decision": decision or "",
                    "predicted_reason": reason or "",
                    "full_contract_valid": full_valid,
                    "status": res.get("status", ""),
                })

    # Write CSV
    with csv_file.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "config",
                "pair_id",
                "word",
                "pos",
                "reference_decision",
                "predicted_decision",
                "predicted_reason",
                "full_contract_valid",
                "status",
            ],
        )
        writer.writeheader()
        writer.writerows(csv_rows)

    results_file.write_text(json.dumps(all_results, indent=2, sort_keys=True))

    # Calculate metrics for A, B, C, D
    metrics_by_config = {}
    gates_by_config = {}

    for config_key in ("A", "B", "C", "D"):
        config_res = [r for r in all_results if r["config"] == config_key]
        m = evaluate_results(scored_sample, config_res)
        metrics_by_config[config_key] = m
        gates_by_config[config_key] = check_calibration_gate(m)

    summary_payload = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model": QWEN_MODEL,
        "model_digest": QWEN_EXPECTED_DIGEST,
        "ollama_url": endpoint,
        "semantic_options": QWEN_SEMANTIC_OPTIONS,
        "reference_source": str(reference_path),
        "selection_sha256": selection_sha256,
        "total_calls_made": total_calls_made,
        "metrics": metrics_by_config,
        "calibration_gates": gates_by_config,
    }

    summary_file.write_text(json.dumps(summary_payload, indent=2, sort_keys=True))

    return {
        "selection_file": str(selection_file),
        "selection_sha256": selection_sha256,
        "results_file": str(results_file),
        "results_sha256": compute_file_sha256(results_file),
        "summary_file": str(summary_file),
        "summary_sha256": compute_file_sha256(summary_file),
        "total_calls_made": total_calls_made,
        "summary": summary_payload,
    }


if __name__ == "__main__":
    ref_file = Path("/home/chuck/.local/share/vocab-app/benchmarks/m004.6.6/20260910T234324Z/reference_adjudicated_v3.json")
    out_dir = Path(f"/home/chuck/.local/share/vocab-app/benchmarks/m004.6.13.2/{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}")
    print(f"Running benchmark against {ref_file} -> {out_dir}")
    res = run_benchmark(ref_file, out_dir)
    print("Benchmark complete!")
    print(json.dumps(res, indent=2))
