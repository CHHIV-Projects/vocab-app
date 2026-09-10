"""Phase B validation for the adjudicated M004.6.6 reference."""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from m0046_core_selection_benchmark import OLLAMA_URL, canonical_hash, git_head, utc_now
from m0046_semantic_pair_screening import (
    all_pairs,
    cosine,
    embed,
    policy_pairs,
    representation,
    text_hash,
)

MODEL = "nomic-embed-text:latest"
THRESHOLD = 0.90
THRESHOLDS = [0.86, 0.87, 0.88, 0.89, 0.90, 0.91, 0.92]
TOP_K = [2, 3, 5]


def load_labels(path: Path, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidate_by_id = {item["pair_id"]: item for item in candidates}
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    expected = {"MERGE", "KEEP SEPARATE", "UNCERTAIN"}
    if len(rows) != len(candidates) or len({row["pair_id"] for row in rows}) != len(rows):
        raise ValueError("Adjudicated CSV must contain each candidate pair exactly once")
    if set(row["pair_id"] for row in rows) != set(candidate_by_id):
        raise ValueError("Adjudicated CSV pair IDs do not match Phase A candidates")
    result = []
    for row in rows:
        decision = row["decision"].strip().upper()
        if decision not in expected:
            raise ValueError(f"Unsupported decision for {row['pair_id']}: {decision!r}")
        item = candidate_by_id[row["pair_id"]]
        result.append({
            "pair_id": row["pair_id"],
            "word": item["word"],
            "pos": item["pos"],
            "partition_id": item["partition_id"],
            "first": item["first"],
            "second": item["second"],
            "reference_decision": decision.lower().replace(" ", "_"),
            "review_notes": row.get("review_notes", ""),
        })
    return result


def score_reference(retained: set[str], references: list[dict[str, Any]], mapping: dict[str, str]) -> dict[str, Any]:
    resolved = [item for item in references if item["reference_decision"] != "uncertain"]
    merges = [item for item in resolved if item["reference_decision"] == "merge"]
    separates = [item for item in resolved if item["reference_decision"] == "keep_separate"]
    lost = [item["pair_id"] for item in merges if mapping[item["pair_id"]] not in retained]
    removed = sum(mapping[item["pair_id"]] not in retained for item in separates)
    return {
        "resolved_merge_count": len(merges),
        "resolved_keep_separate_count": len(separates),
        "uncertain_count": len(references) - len(resolved),
        "retained_resolved_merge_count": len(merges) - len(lost),
        "merge_recall": (len(merges) - len(lost)) / len(merges) if merges else None,
        "keep_separate_retained_count": len(separates) - removed,
        "keep_separate_screened_count": removed,
        "keep_separate_reduction": removed / len(separates) if separates else None,
        "lost_merge_pair_ids": lost,
        "uncertain_pair_ids": [item["pair_id"] for item in references if item["reference_decision"] == "uncertain"],
    }


def pair_scores(pairs: list[dict[str, Any]], vectors: dict[str, list[float]]) -> dict[str, float]:
    return {
        pair["pair_id"]: cosine(vectors[pair["first"]["source_sense_id"]], vectors[pair["second"]["source_sense_id"]])
        for pair in pairs
    }


def loo(reference: list[dict[str, Any]], ref_pairs: list[dict[str, Any]], vectors: dict[str, list[float]],
        mapping: dict[str, str]) -> list[dict[str, Any]]:
    by_id = {pair["pair_id"]: pair for pair in ref_pairs}
    result = []
    for held_out in sorted({item["word"] for item in reference}):
        train = [item for item in reference if item["word"] != held_out]
        test = [item for item in reference if item["word"] == held_out]
        train_pairs = [by_id[mapping[item["pair_id"]]] for item in train]
        train_map = {item["pair_id"]: mapping[item["pair_id"]] for item in train}
        candidates = []
        for threshold in THRESHOLDS:
            retained = policy_pairs(train_pairs, vectors, "threshold", threshold)
            candidates.append({"threshold": threshold, **score_reference(retained, train, train_map)})
        safe = [row for row in candidates if row["merge_recall"] == 1.0]
        chosen = max(safe, key=lambda row: (row["keep_separate_reduction"], row["threshold"])) if safe else None
        test_pairs = [by_id[mapping[item["pair_id"]]] for item in test]
        test_map = {item["pair_id"]: mapping[item["pair_id"]] for item in test}
        test_retained = policy_pairs(test_pairs, vectors, "threshold", chosen["threshold"]) if chosen else set()
        result.append({
            "held_out_word": held_out,
            "training_selected_threshold": chosen["threshold"] if chosen else None,
            "training_metrics": chosen,
            "held_out_metrics": score_reference(test_retained, test, test_map) if chosen else None,
        })
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase-a-root", type=Path, required=True)
    parser.add_argument("--adjudicated-csv", type=Path, required=True)
    args = parser.parse_args()

    phase_a = json.loads((args.phase_a_root / "reference_candidates_v1.json").read_text(encoding="utf-8"))
    partitions = phase_a["source_partitions"]
    model_meta = next(
        item for item in json.load(__import__("urllib.request").request.urlopen(f"{OLLAMA_URL}/api/tags"))["models"]
        if item["name"] == MODEL
    )
    representation_meta = phase_a["representation"]
    identity = canonical_hash({"model": model_meta, "representation": representation_meta})[:24]
    nodes = {
        node["source_sense_id"]: node
        for partition in partitions
        for node in partition["source_nodes"]
    }
    texts = {source_id: representation(node) for source_id, node in nodes.items()}
    vector_list, embed_meta = embed(MODEL, list(texts.values()))
    vectors = dict(zip(texts, vector_list))
    pairs = [pair for partition in partitions for pair in all_pairs(partition, identity)]
    references = load_labels(args.adjudicated_csv, phase_a["candidate_pairs"])
    by_pair_key: dict[frozenset[str], dict[str, Any]] = {
        frozenset((pair["first"]["source_sense_id"], pair["second"]["source_sense_id"])): pair
        for pair in pairs
    }
    reference_pairs = []
    mapping = {}
    for reference in references:
        key = frozenset((reference["first"]["source_sense_id"], reference["second"]["source_sense_id"]))
        pair = by_pair_key[key]
        reference_pairs.append(pair)
        mapping[reference["pair_id"]] = pair["pair_id"]
    scores = pair_scores(pairs, vectors)
    reference_scores = [{
        **reference,
        "screen_pair_id": mapping[reference["pair_id"]],
        "similarity": scores[mapping[reference["pair_id"]]],
        "representation_hashes": [
            text_hash(texts[reference["first"]["source_sense_id"]]),
            text_hash(texts[reference["second"]["source_sense_id"]]),
        ],
    } for reference in references]
    threshold_sweep = []
    for threshold in THRESHOLDS:
        retained = {pair_id for pair_id, score in scores.items() if score >= threshold}
        threshold_sweep.append({"policy": "threshold", "value": threshold,
                                **score_reference({mapping[item["pair_id"]] for item in references if mapping[item["pair_id"]] in retained},
                                                  references, mapping)})
    top_k_sweep = []
    for k in TOP_K:
        retained = policy_pairs(reference_pairs, vectors, "top_k", k)
        top_k_sweep.append({"policy": "top_k", "value": k, **score_reference(retained, references, mapping)})
    primary_retained = {pair_id for pair_id, score in scores.items() if score >= THRESHOLD}
    top_k_three = policy_pairs(reference_pairs, vectors, "top_k", 3)
    primary_reference_retained = {mapping[item["pair_id"]] for item in references if mapping[item["pair_id"]] in primary_retained}
    hybrid = None
    primary_metrics = score_reference(primary_reference_retained, references, mapping)
    top_k_three_metrics = score_reference(top_k_three, references, mapping)
    if primary_metrics["lost_merge_pair_ids"] and not top_k_three_metrics["lost_merge_pair_ids"]:
        hybrid_retained = primary_retained | top_k_three
        hybrid = {
            "policy": "threshold_0.90_union_top_k_3",
            **score_reference(hybrid_retained, references, mapping),
            "additional_retained_pairs_over_threshold": len(hybrid_retained - primary_retained),
            "tested_because": "threshold lost approved merges and top-K=3 recovered them",
        }
    resolved = [item for item in reference_scores if item["reference_decision"] != "uncertain"]
    merge_scores = [item["similarity"] for item in resolved if item["reference_decision"] == "merge"]
    negative_scores = sorted(
        (item for item in resolved if item["reference_decision"] == "keep_separate"),
        key=lambda item: item["similarity"], reverse=True,
    )
    low_positive = sorted(
        (item for item in resolved if item["reference_decision"] == "merge"),
        key=lambda item: item["similarity"],
    )
    projections = []
    for partition in partitions:
        partition_pairs = [pair for pair in pairs if pair["partition_id"] == partition["partition_id"]]
        kept = {pair["pair_id"] for pair in partition_pairs if scores[pair["pair_id"]] >= THRESHOLD}
        if partition["word"] in {"bank", "runner", "set", "run"}:
            projections.append({
                "word": partition["word"], "pos": partition["pos"],
                "source_senses": len(partition["source_nodes"]),
                "complete_pairs": len(partition_pairs), "retained_pairs": len(kept),
                "retained_percentage": len(kept) / len(partition_pairs) * 100,
                "reduction_percentage": (1 - len(kept) / len(partition_pairs)) * 100,
                "average_retained_peers_per_sense": 2 * len(kept) / len(partition["source_nodes"]),
                "maximum_retained_peers_per_sense": max(
                    (sum(pair["pair_id"] in kept for pair in partition_pairs
                         if node["source_sense_id"] in {pair["first"]["source_sense_id"], pair["second"]["source_sense_id"]})
                     for node in partition["source_nodes"]), default=0),
                "isolated_sense_count": sum(
                    not any(pair["pair_id"] in kept and node["source_sense_id"] in
                            {pair["first"]["source_sense_id"], pair["second"]["source_sense_id"]}
                            for pair in partition_pairs) for node in partition["source_nodes"]
                ),
            })
    retained_rate = sum(len({p["pair_id"] for p in [pair for pair in pairs if pair["partition_id"] == partition["partition_id"]]
                              if scores[p["pair_id"]] >= THRESHOLD}) for partition in partitions) / len(pairs)
    small_partition = [{
        "sense_count": count,
        "complete_pairs": count * (count - 1) // 2,
        "exhaustive_qwen_pair_calls": count * (count - 1) // 2,
        "screened_qwen_pair_calls_estimate": round(count * (count - 1) // 2 * retained_rate, 3),
        "embedding_plus_screening_note": "Embedding overhead is benchmark-local and separate from Qwen pair-call counts.",
    } for count in [2, 3, 5, 8, 10]]
    run_id = utc_now().replace("-", "").replace(":", "")
    root = args.phase_a_root.parent / run_id
    root.mkdir(parents=True)
    adjudicated = {
        "benchmark_id": phase_a["benchmark_id"], "phase": "B",
        "reference_version": "reference-adjudicated-v3",
        "source_candidate_reference": str(args.phase_a_root / "reference_candidates_v1.json"),
        "adjudication_source": str(args.adjudicated_csv),
        "created_at": utc_now(), "git_head": git_head(),
        "candidate_pairs": references, "immutable_input_hash": canonical_hash(references),
    }
    (root / "reference_adjudicated_v3.json").write_text(json.dumps(adjudicated, indent=2, sort_keys=True), encoding="utf-8")
    summary = {
        "benchmark_id": phase_a["benchmark_id"], "phase": "B", "run_id": run_id,
        "git_head": git_head(), "embedding_model": model_meta, "embedding_identity": identity,
        "representation": representation_meta, "threshold_primary": THRESHOLD,
        "source_sense_count": len(nodes), "complete_pair_count": len(pairs),
        "reference_counts": {
            "total": len(references), "merge": sum(x["reference_decision"] == "merge" for x in references),
            "keep_separate": sum(x["reference_decision"] == "keep_separate" for x in references),
            "uncertain": sum(x["reference_decision"] == "uncertain" for x in references),
        },
        "reference_similarity": reference_scores,
        "threshold_sweep": threshold_sweep, "top_k_sweep": top_k_sweep,
        "primary_policy_metrics": primary_metrics, "hybrid_gate": hybrid,
        "leave_one_word_out": loo(references, reference_pairs, vectors, mapping),
        "positive_safety_margin": {
            "minimum": min(merge_scores), "median": sorted(merge_scores)[len(merge_scores) // 2],
            "maximum": max(merge_scores), "distance_from_0_90": min(merge_scores) - THRESHOLD,
        },
        "high_similarity_keep_separate": negative_scores[:15],
        "low_similarity_merge": low_positive,
        "large_partition_projection": projections,
        "small_partition_cost_projection": small_partition,
        "phase_b_scope": "screening validation only; no LLM calls; no production recommendation authorized",
        "embedding_response_metadata": {key: value for key, value in embed_meta.items() if key != "embeddings"},
    }
    (root / "phase_b_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    (root / "reference_comparison.json").write_text(json.dumps(reference_scores, indent=2, sort_keys=True), encoding="utf-8")
    print(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
