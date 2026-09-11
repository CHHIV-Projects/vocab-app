"""Benchmark-only M004.6.7 failure characterization and candidate reduction."""

from __future__ import annotations

import argparse
import itertools
import json
import math
import re
import sqlite3
import statistics
import subprocess
import sys
import time
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from m0046_core_selection_benchmark import LEXICAL_DB, OLLAMA_URL, canonical_hash, git_head, installed_digest
from m0046_learner_consolidation_benchmark import material_partition, source_node
from m0046_semantic_pair_screening import cosine, representation, text_hash
from vocab_lexical_engine import canonical_json, lookup
from vocab_synthesis import MATERIAL_LABELS, project_synthesis_evidence, response_content, strict_json_object

ARTIFACT_BASE = Path.home() / ".local/share/vocab-app/benchmarks/m004.6.7"
DEFAULT_REFERENCE = Path.home() / ".local/share/vocab-app/benchmarks/m004.6.6/20260910T234324Z/reference_adjudicated_v3.json"
DEFAULT_PHASE_B_SUMMARY = DEFAULT_REFERENCE.parent / "phase_b_summary.json"
DEFAULT_PRIOR_QWEN_ATTEMPTS = Path.home() / ".local/share/vocab-app/benchmarks/m004.6.4/20260910T062518Z/attempts.json"
QWEN_MODEL = "qwen3:8b"
PROPOSAL_IDENTITY = "m004.6.7-qwen-candidate-proposal-v1"
STRUCTURAL_POLICY_IDENTITY = "m004.6.7-structural-candidate-policy-v1"
STRUCTURAL_CONTAINMENT_THRESHOLD = 0.62
DEFAULT_MAX_CANDIDATES_PER_ALIAS = 12

STOPWORDS = {
    "the", "and", "that", "with", "from", "into", "onto", "over", "under", "when", "where", "which",
    "this", "these", "those", "used", "using", "being", "been", "such", "having", "have", "has", "had",
    "especially", "particularly", "usually", "often", "some", "any", "one", "two", "many", "very", "more",
    "part", "thing", "person", "place", "state", "quality", "action", "process", "manner", "kind", "type",
    "something", "someone", "relating", "pertaining", "characterized", "consisting", "made", "make",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")


def compact(value: str) -> str:
    return " ".join(value.split())


def normalize_text(value: str) -> str:
    return compact(value).casefold()


def node_definitions(node: dict[str, Any]) -> list[str]:
    value = node.get("definition", [])
    if isinstance(value, str):
        value = [value]
    return [normalize_text(str(item)) for item in value if compact(str(item))]


def display_definitions(node: dict[str, Any]) -> list[str]:
    value = node.get("definition", [])
    if isinstance(value, str):
        value = [value]
    return [compact(str(item)) for item in value if compact(str(item))]


def token_set(texts: list[str]) -> set[str]:
    tokens: set[str] = set()
    for text in texts:
        for token in re.findall(r"[a-z][a-z'-]{2,}", text.casefold()):
            token = token.strip("'-")
            if len(token) >= 3 and token not in STOPWORDS:
                tokens.add(token)
    return tokens


def source_entry_key(source_sense_id: str) -> str | None:
    parts = source_sense_id.split(":")
    return parts[4] if len(parts) >= 8 and parts[0] == "WIK" else None


def source_hierarchy_identity(source_sense_id: str) -> str | None:
    parts = source_sense_id.split(":")
    if len(parts) < 9 or parts[0] != "WIK":
        return None
    identity = ":".join(parts[5:-3])
    if not identity or identity == "content":
        return None
    return identity


def relation_keys(node: dict[str, Any]) -> set[tuple[str, str]]:
    result = set()
    for relation in node.get("relations", []) or []:
        relation_type = str(relation.get("type", "")).casefold()
        target = normalize_text(str(relation.get("target", "")))
        if relation_type and target:
            result.add((relation_type, target))
    for relation_type in ("alt_of", "form_of"):
        for relation in node.get(relation_type, []) or []:
            target = relation.get("word") if isinstance(relation, dict) else relation
            target_text = normalize_text(str(target or ""))
            if target_text:
                result.add((relation_type, target_text))
    return result


def structural_signals(first: dict[str, Any], second: dict[str, Any], *, containment_threshold: float = STRUCTURAL_CONTAINMENT_THRESHOLD) -> dict[str, Any]:
    first_defs = node_definitions(first)
    second_defs = node_definitions(second)
    common_prefix = 0
    for left, right in zip(first_defs, second_defs):
        if left != right:
            break
        common_prefix += 1
    first_prefixes_second = bool(first_defs) and len(first_defs) < len(second_defs) and second_defs[:len(first_defs)] == first_defs
    second_prefixes_first = bool(second_defs) and len(second_defs) < len(first_defs) and first_defs[:len(second_defs)] == second_defs
    exact_overlap = sorted(set(first_defs) & set(second_defs))
    first_tokens = token_set(first_defs)
    second_tokens = token_set(second_defs)
    shared_tokens = sorted(first_tokens & second_tokens)
    token_containment = (len(shared_tokens) / min(len(first_tokens), len(second_tokens))) if first_tokens and second_tokens else 0.0
    hierarchy_first = source_hierarchy_identity(first["source_sense_id"])
    hierarchy_second = source_hierarchy_identity(second["source_sense_id"])
    same_hierarchy_identity = bool(hierarchy_first and hierarchy_first == hierarchy_second)
    shared_relations = sorted(relation_keys(first) & relation_keys(second))
    safe_shared_relations = [item for item in shared_relations if item[0] in {"synonyms", "alt_of", "form_of"}]
    reasons: list[str] = []
    if exact_overlap:
        reasons.append("exact_definition_overlap")
    if common_prefix and (len(first_defs) > common_prefix or len(second_defs) > common_prefix):
        reasons.append("shared_parent_definition_prefix")
    if first_prefixes_second or second_prefixes_first:
        reasons.append("definition_chain_prefix")
    if same_hierarchy_identity:
        reasons.append("same_source_hierarchy_identity")
    if token_containment >= containment_threshold and min(len(first_tokens), len(second_tokens)) >= 6:
        reasons.append("high_definition_token_containment")
    if safe_shared_relations:
        reasons.append("explicit_safe_source_relation_overlap")
    retain = bool(reasons)
    return {
        "policy_identity": STRUCTURAL_POLICY_IDENTITY,
        "decision": "retain_for_semantic_review" if retain else "no_structural_candidate_signal",
        "reason_codes": reasons,
        "common_definition_prefix_count": common_prefix,
        "exact_definition_overlap": exact_overlap,
        "first_chain_prefixes_second": first_prefixes_second,
        "second_chain_prefixes_first": second_prefixes_first,
        "same_source_entry_key": source_entry_key(first["source_sense_id"]) == source_entry_key(second["source_sense_id"]),
        "same_source_hierarchy_identity": same_hierarchy_identity,
        "source_hierarchy_identities": [hierarchy_first, hierarchy_second],
        "token_containment": round(token_containment, 4),
        "shared_token_count": len(shared_tokens),
        "shared_tokens_sample": shared_tokens[:24],
        "shared_relation_count": len(shared_relations),
        "safe_shared_relations": safe_shared_relations[:12],
    }


def reference_pair_key(pair: dict[str, Any]) -> tuple[str, str]:
    ids = sorted((pair["first"]["source_sense_id"], pair["second"]["source_sense_id"]))
    return (ids[0], ids[1])


def candidate_pair_id(partition_id: str, first_id: str, second_id: str, identity: str) -> str:
    left, right = sorted((first_id, second_id))
    return f"{partition_id}:{canonical_hash([left, right, identity])[:16]}"


def score_retention(retained_keys: set[tuple[str, str]], references: list[dict[str, Any]]) -> dict[str, Any]:
    resolved = [item for item in references if item["reference_decision"] != "uncertain"]
    merges = [item for item in resolved if item["reference_decision"] == "merge"]
    keeps = [item for item in resolved if item["reference_decision"] == "keep_separate"]
    lost = [item["pair_id"] for item in merges if reference_pair_key(item) not in retained_keys]
    screened_keep = sum(reference_pair_key(item) not in retained_keys for item in keeps)
    retained_keep = len(keeps) - screened_keep
    return {
        "resolved_merge_count": len(merges),
        "resolved_keep_separate_count": len(keeps),
        "uncertain_count": len(references) - len(resolved),
        "retained_resolved_merge_count": len(merges) - len(lost),
        "merge_candidate_recall": (len(merges) - len(lost)) / len(merges) if merges else None,
        "lost_merge_pair_ids": lost,
        "keep_separate_retained_count": retained_keep,
        "keep_separate_screened_count": screened_keep,
        "keep_separate_reduction": screened_keep / len(keeps) if keeps else None,
        "uncertain_retained_count": sum(reference_pair_key(item) in retained_keys for item in references if item["reference_decision"] == "uncertain"),
    }


def validate_reference(path: Path) -> dict[str, Any]:
    before_mtime = path.stat().st_mtime_ns
    before_size = path.stat().st_size
    data = load_json(path)
    after_mtime = path.stat().st_mtime_ns
    pairs = data.get("candidate_pairs", [])
    counts = Counter(item.get("reference_decision") for item in pairs)
    if len(pairs) != 200 or counts != {"merge": 30, "keep_separate": 164, "uncertain": 6}:
        raise ValueError(f"M004.6.6 reference counts are not the immutable expected counts: {dict(counts)}, total={len(pairs)}")
    return {
        "path": str(path),
        "reference_version": data.get("reference_version"),
        "benchmark_id": data.get("benchmark_id"),
        "created_at": data.get("created_at"),
        "git_head": data.get("git_head"),
        "source_candidate_reference": data.get("source_candidate_reference"),
        "immutable_input_hash": data.get("immutable_input_hash"),
        "artifact_hash": canonical_hash(data),
        "counts": dict(counts),
        "total_pairs": len(pairs),
        "mtime_ns_unchanged_by_load": before_mtime == after_mtime,
        "size_bytes_unchanged_by_load": before_size == path.stat().st_size,
    }


def load_reference_and_partitions(reference_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    reference = load_json(reference_path)
    pairs = reference["candidate_pairs"]
    source_reference = Path(reference["source_candidate_reference"])
    source = load_json(source_reference)
    return reference, pairs, source["source_partitions"]


def score_structural_policy(references: list[dict[str, Any]], partitions: list[dict[str, Any]]) -> dict[str, Any]:
    retained: set[tuple[str, str]] = set()
    all_candidate_pairs = 0
    retained_candidate_pairs = 0
    partition_rows = []
    for partition in partitions:
        partition_retained = 0
        pairs = 0
        for first, second in itertools.combinations(partition["source_nodes"], 2):
            pairs += 1
            signals = structural_signals(first, second)
            if signals["decision"] == "retain_for_semantic_review":
                retained.add(tuple(sorted((first["source_sense_id"], second["source_sense_id"]))))
                partition_retained += 1
        all_candidate_pairs += pairs
        retained_candidate_pairs += partition_retained
        partition_rows.append({
            "partition_id": partition["partition_id"], "word": partition["word"], "pos": partition["pos"],
            "source_senses": len(partition["source_nodes"]), "complete_pairs": pairs,
            "structural_candidate_pairs": partition_retained,
            "structural_reduction": 1 - partition_retained / pairs if pairs else None,
        })
    return {
        "policy_identity": STRUCTURAL_POLICY_IDENTITY,
        "policy": {
            "candidate_only_outputs": ["retain_for_semantic_review", "no_structural_candidate_signal"],
            "merge_authority": False,
            "rules": [
                "exact normalized definition overlap",
                "shared deterministic parent-definition prefix",
                "one normalized definition chain prefixes the other",
                "same non-content source hierarchy identity encoded in source_sense_id",
                f"definition-token containment >= {STRUCTURAL_CONTAINMENT_THRESHOLD} with at least six non-stopword tokens in the shorter definition",
                "explicit safe synonym/alt-of/form-of relation overlap",
            ],
        },
        "complete_pairs_evaluated": all_candidate_pairs,
        "structural_candidate_pairs": retained_candidate_pairs,
        "structural_pair_reduction": 1 - retained_candidate_pairs / all_candidate_pairs if all_candidate_pairs else None,
        "reference_metrics": score_retention(retained, references),
        "partition_results": partition_rows,
    }


def failure_characterization(references: list[dict[str, Any]], phase_b_summary: dict[str, Any]) -> dict[str, Any]:
    similarities = {item["pair_id"]: item["similarity"] for item in phase_b_summary["reference_similarity"]}
    lost_ids = set(phase_b_summary["primary_policy_metrics"]["lost_merge_pair_ids"])
    rows = []
    for pair in sorted((item for item in references if item["reference_decision"] == "merge"), key=lambda item: similarities[item["pair_id"]]):
        signals = structural_signals(pair["first"], pair["second"])
        causes = []
        if signals["same_source_hierarchy_identity"] or signals["common_definition_prefix_count"]:
            causes.extend(["B_inherited_wiktionary_definition_hierarchy", "E_insufficient_representation_context"])
        if len(set(token_set(node_definitions(pair["first"]))) ^ set(token_set(node_definitions(pair["second"])))) >= 6:
            causes.append("A_different_surface_vocabulary")
        if any(code in signals["reason_codes"] for code in ("shared_parent_definition_prefix", "definition_chain_prefix", "high_definition_token_containment")):
            causes.append("C_contextual_specialization")
        if pair["first"].get("labels") != pair["second"].get("labels"):
            causes.append("D_grammatical_or_label_variation")
        if similarities[pair["pair_id"]] < 0.90:
            causes.append("F_embedding_model_semantic_limitation")
        if not causes:
            causes.append("near_paraphrase_or_lexically_similar_merge")
        rows.append({
            "pair_id": pair["pair_id"], "word": pair["word"], "pos": pair["pos"],
            "similarity": similarities[pair["pair_id"]], "threshold_0_90_retained": similarities[pair["pair_id"]] >= 0.90,
            "m004_6_6_false_negative": pair["pair_id"] in lost_ids,
            "first_source_sense_id": pair["first"]["source_sense_id"], "second_source_sense_id": pair["second"]["source_sense_id"],
            "first_definitions": display_definitions(pair["first"]), "second_definitions": display_definitions(pair["second"]),
            "first_labels": pair["first"].get("labels", []), "second_labels": pair["second"].get("labels", []),
            "first_examples": pair["first"].get("examples", [])[:2], "second_examples": pair["second"].get("examples", [])[:2],
            "first_relations": pair["first"].get("relations", [])[:12], "second_relations": pair["second"].get("relations", [])[:12],
            "review_notes": pair.get("review_notes", ""),
            "structural_signals": signals,
            "primary_failure_causes": sorted(set(causes)),
            "near_paraphrase_vs_conceptual_equivalence": "near_paraphrase" if similarities[pair["pair_id"]] >= 0.93 else "conceptually_equivalent_but_lexically_or_contextually_dissimilar",
        })
    below_091 = [row for row in rows if row["similarity"] < 0.91]
    return {
        "threshold": 0.90,
        "approved_merge_count": len(rows),
        "false_negative_pair_ids": sorted(lost_ids),
        "approved_merges_below_0_91": below_091,
        "approved_merges": rows,
        "summary": {
            "false_negative_count": len(lost_ids),
            "below_0_91_count": len(below_091),
            "dominant_patterns": [
                "definition chains and source_sense_id hierarchy often expose parent/subsense relationships lost by flat embedding text",
                "contextual specializations can be approved learner-meaning merges even when surface vocabulary shifts",
                "embedding similarity alone cannot distinguish low-similarity true merges from high-similarity true keep-separate cases",
            ],
        },
    }


def qwen_latency_baseline(path: Path) -> dict[str, Any]:
    rows = load_json(path) if path.exists() else []
    seconds = []
    for row in rows:
        if row.get("model") == QWEN_MODEL and row.get("experiment") == "single-pair" and row.get("provider_status") == "provider_success":
            total = (row.get("raw_provider_response") or {}).get("total_duration")
            if isinstance(total, (int, float)) and total > 0:
                seconds.append(total / 1_000_000_000)
    if not seconds:
        return {"source": str(path), "model": QWEN_MODEL, "successful_single_pair_calls": 0, "p50_seconds": None, "p95_seconds": None}
    ordered = sorted(seconds)
    return {
        "source": str(path), "model": QWEN_MODEL, "successful_single_pair_calls": len(seconds),
        "p50_seconds": statistics.median(ordered),
        "p95_seconds": ordered[round((len(ordered) - 1) * 0.95)],
        "mean_seconds": statistics.mean(ordered),
        "max_seconds": max(ordered),
    }


def partition_lookup(partitions: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    result = {}
    for partition in partitions:
        result[(partition["word"], partition["pos"])] = partition
    return result


def build_word_partitions(word: str) -> list[dict[str, Any]]:
    evidence = project_synthesis_evidence(lookup(LEXICAL_DB, word))
    buckets: dict[tuple[str, tuple[str, ...]], list[dict[str, Any]]] = defaultdict(list)
    for entry in evidence["entries"]:
        for sense in entry["senses"]:
            node = source_node(entry, sense)
            node["word"] = word
            buckets[(node["pos"], material_partition(sense))].append(node)
    result = []
    for (pos, labels), nodes in sorted(buckets.items()):
        nodes = sorted(nodes, key=lambda node: node["source_sense_id"])
        partition = {
            "word": word, "pos": pos, "material_partition": list(labels),
            "lexical_dataset_versions": evidence["wiktionary_versions"],
            "lexical_evidence_hash": canonical_hash({"word": word, "pos": pos, "labels": list(labels), "nodes": nodes}),
            "source_nodes": nodes,
        }
        partition["partition_id"] = f"{word}:{pos}:{canonical_hash(partition)[:12]}"
        partition["partition_hash"] = canonical_hash(partition)
        result.append(partition)
    return result


def representative_partition_counts(source_partitions: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_word_pos = partition_lookup(source_partitions)
    reps: dict[str, dict[str, Any]] = {}
    for senses in [2, 3, 5, 10]:
        reps[f"{senses}_senses"] = {"label": f"{senses} senses", "source_senses": senses, "complete_pairs": senses * (senses - 1) // 2}
    for word, pos in [("bank", "noun"), ("runner", "noun"), ("set", "verb"), ("run", "verb")]:
        partition = by_word_pos.get((word, pos))
        if partition:
            senses = len(partition["source_nodes"])
            reps[f"{word}_{pos}"] = {"label": f"{word} {pos}", "source_senses": senses, "complete_pairs": senses * (senses - 1) // 2, "partition_id": partition["partition_id"]}
    return reps


def exhaustive_economics(source_partitions: list[dict[str, Any]], latency: dict[str, Any]) -> dict[str, Any]:
    p50 = latency.get("p50_seconds") or 0.0
    p95 = latency.get("p95_seconds") or p50
    rows = []
    for key, item in representative_partition_counts(source_partitions).items():
        calls = item["complete_pairs"]
        rows.append({
            "key": key, **item,
            "projected_qwen_calls_production_baseline": calls,
            "first_build_runtime_seconds_p50": calls * p50,
            "first_build_runtime_seconds_p95": calls * p95,
            "cached_subsequent_lookup_qwen_calls": 0,
            "cached_subsequent_lookup_runtime_seconds": 0,
            "cost_note": "local inference wall time only; no external per-token API cost in this self-hosted benchmark",
        })
    return {
        "assumptions": {
            "semantic_model": QWEN_MODEL,
            "judgments_per_pair": 1,
            "retry_policy": "retry only on transport/schema failure",
            "cache_identity": "lexical evidence + semantic contract + model identity; production cache not implemented here",
            "benchmark_multipliers_removed": ["two models", "three seeds", "repeated comparison experiments"],
        },
        "latency_baseline": latency,
        "representative_partitions": rows,
    }


def bucket_for_size(size: int) -> str:
    if size <= 1:
        return "1"
    if size == 2:
        return "2"
    if size == 3:
        return "3"
    if 4 <= size <= 5:
        return "4-5"
    if 6 <= size <= 10:
        return "6-10"
    if 11 <= size <= 20:
        return "11-20"
    if 21 <= size <= 40:
        return "21-40"
    return ">40"


def partition_size_distribution(database_path: Path = LEXICAL_DB) -> dict[str, Any]:
    started = time.monotonic()
    counts: dict[tuple[str, str, tuple[str, ...]], int] = defaultdict(int)
    connection = sqlite3.connect(f"file:{database_path.resolve()}?immutable=1", uri=True)
    try:
        dataset_versions = sorted({row[0] for row in connection.execute("SELECT DISTINCT dataset_version FROM entries")})
        importer_versions = sorted({row[0] for row in connection.execute("SELECT DISTINCT importer_version FROM entries")})
        for lemma, pos, tags_json in connection.execute(
            "SELECT e.normalized_lemma, e.part_of_speech, s.tags_json FROM senses s JOIN entries e ON s.entry_key = e.entry_key WHERE e.language_code = 'en'"
        ):
            labels = tuple(sorted(set(json.loads(tags_json or "[]")) & MATERIAL_LABELS))
            counts[(lemma, pos, labels)] += 1
    finally:
        connection.close()
    bucket_order = ["1", "2", "3", "4-5", "6-10", "11-20", "21-40", ">40"]
    buckets = {bucket: {"partition_count": 0, "sense_count": 0, "all_pairs": 0} for bucket in bucket_order}
    for size in counts.values():
        bucket = bucket_for_size(size)
        buckets[bucket]["partition_count"] += 1
        buckets[bucket]["sense_count"] += size
        buckets[bucket]["all_pairs"] += size * (size - 1) // 2
    total_partitions = sum(row["partition_count"] for row in buckets.values())
    total_senses = sum(row["sense_count"] for row in buckets.values())
    total_pairs = sum(row["all_pairs"] for row in buckets.values())
    for row in buckets.values():
        row["partition_percentage"] = row["partition_count"] / total_partitions if total_partitions else 0
        row["sense_percentage"] = row["sense_count"] / total_senses if total_senses else 0
        row["all_pairs_percentage"] = row["all_pairs"] / total_pairs if total_pairs else 0
    return {
        "database_path": str(database_path), "dataset_versions": dataset_versions, "importer_versions": importer_versions,
        "material_labels": sorted(MATERIAL_LABELS), "elapsed_seconds": time.monotonic() - started,
        "total_partitions": total_partitions, "total_senses": total_senses, "total_all_pairs": total_pairs,
        "buckets": buckets,
        "method": "read-only immutable SQLite scan grouped by normalized lemma, POS, and material-label signature",
    }


def lazy_precompute_projection(distribution: dict[str, Any], latency: dict[str, Any]) -> dict[str, Any]:
    p50 = latency.get("p50_seconds") or 0.0
    p95 = latency.get("p95_seconds") or p50
    total_pairs = distribution.get("total_all_pairs", 0)
    large_pairs = sum(distribution["buckets"][bucket]["all_pairs"] for bucket in ["21-40", ">40"])
    small_medium_pairs = total_pairs - large_pairs
    return {
        "lazy_per_word": {
            "description": "Compute and cache only when a word/POS/material partition is requested.",
            "ordinary_cached_lookup_qwen_calls": 0,
            "first_lookup_latency_depends_on_partition_size": True,
            "interactive_warning": "large partitions may be unsuitable for synchronous UI even when acceptable as background lexical preparation",
        },
        "background_precompute": {
            "description": "Process all eligible partitions before demand.",
            "projected_total_pair_calls": total_pairs,
            "projected_total_runtime_seconds_p50": total_pairs * p50,
            "projected_total_runtime_seconds_p95": total_pairs * p95,
            "small_medium_pair_calls": small_medium_pairs,
            "large_pair_calls_21_plus": large_pairs,
        },
    }


def alias_records(partition: dict[str, Any]) -> tuple[list[str], dict[str, str], list[dict[str, Any]]]:
    nodes = sorted(partition["source_nodes"], key=lambda node: node["source_sense_id"])
    aliases = [f"S{index:03d}" for index in range(1, len(nodes) + 1)]
    alias_to_id = {alias: node["source_sense_id"] for alias, node in zip(aliases, nodes)}
    records = []
    for alias, node in zip(aliases, nodes):
        records.append({
            "alias": alias,
            "source_sense_id": node["source_sense_id"],
            "definitions": display_definitions(node),
            "labels": sorted(node.get("labels", [])),
            "examples": node.get("examples", [])[:1],
            "relations": node.get("relations", [])[:8],
        })
    return aliases, alias_to_id, records


def proposal_schema(aliases: list[str], max_candidates_per_alias: int = DEFAULT_MAX_CANDIDATES_PER_ALIAS) -> dict[str, Any]:
    properties = {}
    for alias in aliases:
        allowed = [item for item in aliases if item != alias]
        properties[alias] = {
            "type": "array",
            "items": {"type": "string", "enum": allowed},
            "uniqueItems": True,
            "maxItems": min(max_candidates_per_alias, len(allowed)),
        }
    return {"type": "object", "additionalProperties": False, "properties": properties, "required": aliases}


def proposal_prompt(partition: dict[str, Any], *, max_candidates_per_alias: int = DEFAULT_MAX_CANDIDATES_PER_ALIAS) -> str:
    aliases, _, records = alias_records(partition)
    return canonical_json({
        "task": "Return exactly one JSON object matching the schema. For every supplied alias, list other aliases in this same partition that should receive later pairwise semantic review.",
        "authority_boundary": [
            "You are not merging senses.", "You are not assigning groups or containers.",
            "Python owns aliases, pair normalization, final semantic judgment, topology, and validation.",
        ],
        "candidate_policy": [
            "Optimize recall: a missed plausible pair can cause a false split; a false positive only costs one later pair judgment.",
            "Include near-paraphrases, duplicate definitions, contextual variants, broader/narrower source subsenses, and pairs with shared parent meaning.",
            "Exclude only aliases that are clearly unrelated learner meanings.",
            f"List at most {max_candidates_per_alias} candidates per alias. Do not list self aliases.",
        ],
        "word": partition["word"], "pos": partition["pos"], "material_partition": partition.get("material_partition", []),
        "aliases": aliases, "senses": records,
    })


def prompt_size_estimate(partition: dict[str, Any], *, max_candidates_per_alias: int = DEFAULT_MAX_CANDIDATES_PER_ALIAS) -> dict[str, Any]:
    prompt = proposal_prompt(partition, max_candidates_per_alias=max_candidates_per_alias)
    schema = proposal_schema(alias_records(partition)[0], max_candidates_per_alias=max_candidates_per_alias)
    chars = len(prompt) + len(canonical_json(schema))
    return {"prompt_chars": len(prompt), "schema_chars": len(canonical_json(schema)), "combined_chars": chars, "rough_tokens_at_4_chars": math.ceil(chars / 4)}


def proposal_diagnostics(parsed: Any, aliases: list[str], max_candidates_per_alias: int = DEFAULT_MAX_CANDIDATES_PER_ALIAS) -> dict[str, bool]:
    alias_set = set(aliases)
    diagnostics = {
        "parse_success": isinstance(parsed, dict),
        "exact_alias_coverage": False,
        "all_values_are_arrays": False,
        "all_candidates_are_strings": False,
        "all_candidates_known_aliases": False,
        "no_self_references": False,
        "no_duplicate_candidates": False,
        "candidate_count_within_limit": False,
        "deterministic_pair_normalization_success": False,
        "candidate_only_no_merge_authority": True,
    }
    if not isinstance(parsed, dict):
        return diagnostics
    diagnostics["exact_alias_coverage"] = set(parsed) == alias_set and len(parsed) == len(aliases)
    diagnostics["all_values_are_arrays"] = all(isinstance(parsed.get(alias), list) for alias in aliases)
    if not diagnostics["all_values_are_arrays"]:
        return diagnostics
    diagnostics["all_candidates_are_strings"] = all(isinstance(candidate, str) for alias in aliases for candidate in parsed[alias])
    diagnostics["all_candidates_known_aliases"] = diagnostics["all_candidates_are_strings"] and all(candidate in alias_set for alias in aliases for candidate in parsed[alias])
    diagnostics["no_self_references"] = all(alias not in parsed[alias] for alias in aliases)
    diagnostics["no_duplicate_candidates"] = all(len(parsed[alias]) == len(set(parsed[alias])) for alias in aliases)
    diagnostics["candidate_count_within_limit"] = all(len(parsed[alias]) <= min(max_candidates_per_alias, len(aliases) - 1) for alias in aliases)
    diagnostics["deterministic_pair_normalization_success"] = all(diagnostics[name] for name in (
        "exact_alias_coverage", "all_values_are_arrays", "all_candidates_are_strings", "all_candidates_known_aliases",
        "no_self_references", "no_duplicate_candidates", "candidate_count_within_limit",
    ))
    return diagnostics


def normalized_candidate_pairs(parsed: Any, alias_to_id: dict[str, str], diagnostics: dict[str, bool]) -> list[dict[str, Any]]:
    if not diagnostics.get("deterministic_pair_normalization_success"):
        return []
    alias_pairs = set()
    for alias, candidates in parsed.items():
        for candidate in candidates:
            alias_pairs.add(tuple(sorted((alias, candidate))))
    rows = []
    for first_alias, second_alias in sorted(alias_pairs):
        first_id, second_id = alias_to_id[first_alias], alias_to_id[second_alias]
        rows.append({
            "aliases": [first_alias, second_alias],
            "source_sense_ids": sorted([first_id, second_id]),
            "pair_key": tuple(sorted([first_id, second_id])),
        })
    return rows


def invoke_proposal(run: str, partition: dict[str, Any], seed: int, *, max_candidates_per_alias: int = DEFAULT_MAX_CANDIDATES_PER_ALIAS) -> dict[str, Any]:
    aliases, alias_to_id, _ = alias_records(partition)
    schema = proposal_schema(aliases, max_candidates_per_alias=max_candidates_per_alias)
    prompt = proposal_prompt(partition, max_candidates_per_alias=max_candidates_per_alias)
    options = {"temperature": 0, "num_predict": 8192, "num_ctx": 32768, "seed": seed}
    record: dict[str, Any] = {
        "attempt_id": f"{run}:{PROPOSAL_IDENTITY}:{partition['partition_id']}:{seed}",
        "run_id": run, "timestamp": utc_now(), "git_head": git_head(),
        "model": QWEN_MODEL, "model_digest": installed_digest(QWEN_MODEL),
        "ollama_version": requests.get(f"{OLLAMA_URL}/api/version", timeout=10).json().get("version"),
        "proposal_identity": PROPOSAL_IDENTITY, "seed": seed,
        "invocation": {"think": False, "options": options},
        "partition_id": partition["partition_id"], "word": partition["word"], "pos": partition["pos"],
        "source_sense_count": len(aliases), "alias_to_source_sense_id": alias_to_id,
        "prompt_hash": canonical_hash(prompt), "schema_hash": canonical_hash(schema),
        "prompt_size": prompt_size_estimate(partition, max_candidates_per_alias=max_candidates_per_alias),
        "provider_status": None, "done_reason": None, "raw_provider_response": None, "raw_content": None,
        "parsed": None, "parse_error": None, "diagnostics": None, "candidate_pairs": [], "wall_seconds": None,
    }
    started = time.monotonic()
    try:
        response = requests.post(f"{OLLAMA_URL}/api/chat", json={
            "model": QWEN_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "format": schema,
            "think": False,
            "keep_alive": "5m",
            "options": options,
        }, timeout=360)
        response.raise_for_status()
        provider = response.json()
        record["raw_provider_response"] = provider
        record["done_reason"] = provider.get("done_reason")
        content = response_content(provider)
        record["raw_content"] = content
        record["provider_status"] = "done_reason_length" if provider.get("done_reason") == "length" else ("empty_content" if not content else "provider_success")
        try:
            record["parsed"] = strict_json_object(content)
        except Exception as error:
            record["parse_error"] = str(error)
            if record["provider_status"] == "provider_success":
                record["provider_status"] = "json_parse_failure"
    except requests.Timeout as error:
        record.update(provider_status="timeout", provider_error=str(error))
    except requests.RequestException as error:
        record.update(provider_status="transport_failure", provider_error=str(error))
    record["wall_seconds"] = time.monotonic() - started
    diagnostics = proposal_diagnostics(record["parsed"], aliases, max_candidates_per_alias=max_candidates_per_alias)
    record["diagnostics"] = diagnostics
    record["candidate_pairs"] = normalized_candidate_pairs(record["parsed"], alias_to_id, diagnostics)
    for pair in record["candidate_pairs"]:
        pair["candidate_pair_id"] = candidate_pair_id(partition["partition_id"], pair["source_sense_ids"][0], pair["source_sense_ids"][1], PROPOSAL_IDENTITY)
        pair["pair_key"] = list(pair["pair_key"])
    return record


def select_proposal_partitions(source_partitions: list[dict[str, Any]], references: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {partition["partition_id"]: partition for partition in source_partitions}
    selected_ids = sorted({item["partition_id"] for item in references})
    selected = [by_id[partition_id] for partition_id in selected_ids if partition_id in by_id]
    if not any(item["word"] == "running" and item["pos"] in {"adj", "adjective"} for item in selected):
        for partition in build_word_partitions("running"):
            if partition["pos"] in {"adj", "adjective"} and not partition.get("material_partition"):
                selected.append(partition)
                break
    return sorted(selected, key=lambda item: (item["word"], item["pos"], item["partition_id"]))


def proposal_plan(partitions: list[dict[str, Any]], seeds: list[int], *, max_candidates_per_alias: int, max_calls: int, max_projected_tokens: int) -> dict[str, Any]:
    rows = []
    skipped = []
    for partition in partitions:
        size = prompt_size_estimate(partition, max_candidates_per_alias=max_candidates_per_alias)
        row = {"partition_id": partition["partition_id"], "word": partition["word"], "pos": partition["pos"],
               "source_senses": len(partition["source_nodes"]), **size}
        if size["rough_tokens_at_4_chars"] > max_projected_tokens:
            skipped.append({**row, "skip_reason": "projected_prompt_exceeds_context_budget"})
        else:
            rows.append(row)
    projected_calls = len(rows) * len(seeds)
    return {
        "model": QWEN_MODEL, "think": False, "temperature": 0, "seeds": seeds,
        "max_candidates_per_alias": max_candidates_per_alias,
        "planned_partitions": rows, "skipped_partitions": skipped,
        "projected_new_qwen_calls": projected_calls, "maximum_authorized_calls": max_calls,
        "comfortably_under_500": projected_calls < min(max_calls, 500) * 0.5,
        "within_budget": projected_calls <= max_calls and projected_calls < 500,
    }


def evaluate_proposal_attempts(attempts: list[dict[str, Any]], references: list[dict[str, Any]]) -> dict[str, Any]:
    by_seed: dict[int, set[tuple[str, str]]] = defaultdict(set)
    by_partition_seed: dict[tuple[str, int], int] = defaultdict(int)
    all_keys: set[tuple[str, str]] = set()
    for attempt in attempts:
        seed = attempt["seed"]
        for pair in attempt.get("candidate_pairs", []):
            key = tuple(sorted(pair["source_sense_ids"]))
            by_seed[seed].add(key)
            all_keys.add(key)
            by_partition_seed[(attempt["partition_id"], seed)] += 1
    seed_metrics = {str(seed): {"candidate_pair_count": len(keys), **score_retention(keys, references)} for seed, keys in sorted(by_seed.items())}
    intersection = set.intersection(*by_seed.values()) if by_seed else set()
    union_metrics = score_retention(all_keys, references)
    return {
        "attempt_count": len(attempts),
        "successful_schema_attempt_count": sum(bool((attempt.get("diagnostics") or {}).get("deterministic_pair_normalization_success")) for attempt in attempts),
        "provider_status_counts": dict(Counter(attempt.get("provider_status") for attempt in attempts)),
        "latency_seconds": {
            "p50_wall": statistics.median([attempt["wall_seconds"] for attempt in attempts]) if attempts else None,
            "p95_wall": sorted([attempt["wall_seconds"] for attempt in attempts])[round((len(attempts) - 1) * .95)] if attempts else None,
            "total_wall_sum": sum(attempt["wall_seconds"] for attempt in attempts),
        },
        "by_seed": seed_metrics,
        "union": {"candidate_pair_count": len(all_keys), **union_metrics},
        "intersection": {"candidate_pair_count": len(intersection), **score_retention(intersection, references)},
        "seed_symmetric_differences": {
            f"{left}_vs_{right}": len(by_seed[left] ^ by_seed[right])
            for left, right in itertools.combinations(sorted(by_seed), 2)
        },
        "partition_seed_candidate_counts": {f"{partition_id}|{seed}": count for (partition_id, seed), count in sorted(by_partition_seed.items())},
    }


def strategy_comparison(*, references: list[dict[str, Any]], phase_b_summary: dict[str, Any], structural: dict[str, Any], proposal: dict[str, Any] | None, economics: dict[str, Any]) -> list[dict[str, Any]]:
    resolved_pairs = len([item for item in references if item["reference_decision"] != "uncertain"])
    exhaustive_calls = resolved_pairs
    p50 = economics["latency_baseline"].get("p50_seconds") or 0.0
    topk3 = next(item for item in phase_b_summary["top_k_sweep"] if item["value"] == 3)
    rows = [
        {"strategy": "exhaustive_qwen_baseline", "merge_candidate_recall": 1.0, "keep_separate_reduction": 0.0,
         "reference_candidate_pairs_retained": resolved_pairs, "upstream_screening_or_proposal_calls": 0,
         "downstream_projected_pairwise_qwen_calls_on_reference": exhaustive_calls, "estimated_reference_runtime_seconds": exhaustive_calls * p50,
         "architecture_complexity": "lowest; pairwise semantic authority only"},
        {"strategy": "m004.6.6_embedding_threshold_0.90_failed", "merge_candidate_recall": phase_b_summary["primary_policy_metrics"]["merge_recall"],
         "keep_separate_reduction": phase_b_summary["primary_policy_metrics"]["keep_separate_reduction"],
         "reference_candidate_pairs_retained": phase_b_summary["primary_policy_metrics"]["retained_resolved_merge_count"] + phase_b_summary["primary_policy_metrics"]["keep_separate_retained_count"],
         "upstream_screening_or_proposal_calls": "1 embedding batch", "downstream_projected_pairwise_qwen_calls_on_reference": phase_b_summary["primary_policy_metrics"]["retained_resolved_merge_count"] + phase_b_summary["primary_policy_metrics"]["keep_separate_retained_count"],
         "estimated_reference_runtime_seconds": (phase_b_summary["primary_policy_metrics"]["retained_resolved_merge_count"] + phase_b_summary["primary_policy_metrics"]["keep_separate_retained_count"]) * p50,
         "architecture_complexity": "medium; failed recall gate"},
        {"strategy": "m004.6.6_embedding_top_k_3_safe_comparator", "merge_candidate_recall": topk3["merge_recall"],
         "keep_separate_reduction": topk3["keep_separate_reduction"],
         "reference_candidate_pairs_retained": topk3["retained_resolved_merge_count"] + topk3["keep_separate_retained_count"],
         "upstream_screening_or_proposal_calls": "1 embedding batch", "downstream_projected_pairwise_qwen_calls_on_reference": topk3["retained_resolved_merge_count"] + topk3["keep_separate_retained_count"],
         "estimated_reference_runtime_seconds": (topk3["retained_resolved_merge_count"] + topk3["keep_separate_retained_count"]) * p50,
         "architecture_complexity": "medium; safe on reference but weak reduction"},
        {"strategy": "deterministic_structural_candidate_policy", "merge_candidate_recall": structural["reference_metrics"]["merge_candidate_recall"],
         "keep_separate_reduction": structural["reference_metrics"]["keep_separate_reduction"],
         "reference_candidate_pairs_retained": structural["reference_metrics"]["retained_resolved_merge_count"] + structural["reference_metrics"]["keep_separate_retained_count"],
         "upstream_screening_or_proposal_calls": 0, "downstream_projected_pairwise_qwen_calls_on_reference": structural["reference_metrics"]["retained_resolved_merge_count"] + structural["reference_metrics"]["keep_separate_retained_count"],
         "estimated_reference_runtime_seconds": (structural["reference_metrics"]["retained_resolved_merge_count"] + structural["reference_metrics"]["keep_separate_retained_count"]) * p50,
         "architecture_complexity": "low-medium; deterministic but incomplete semantic recall"},
    ]
    if proposal:
        union = proposal["union"]
        rows.append({"strategy": "bounded_qwen_candidate_proposal_union", "merge_candidate_recall": union["merge_candidate_recall"],
                     "keep_separate_reduction": union["keep_separate_reduction"],
                     "reference_candidate_pairs_retained": union["retained_resolved_merge_count"] + union["keep_separate_retained_count"],
                     "upstream_screening_or_proposal_calls": proposal["attempt_count"],
                     "downstream_projected_pairwise_qwen_calls_on_reference": union["retained_resolved_merge_count"] + union["keep_separate_retained_count"],
                     "estimated_reference_runtime_seconds": proposal["latency_seconds"]["total_wall_sum"] + (union["retained_resolved_merge_count"] + union["keep_separate_retained_count"]) * p50,
                     "architecture_complexity": "highest; learned proposal stage plus pairwise judgment cache"})
    return rows


def preflight(reference_identity: dict[str, Any]) -> dict[str, Any]:
    status = subprocess.run(["git", "status", "--short"], cwd=ROOT, text=True, capture_output=True, check=True).stdout
    branch = subprocess.run(["git", "branch", "--show-current"], cwd=ROOT, text=True, capture_output=True, check=True).stdout.strip()
    upstream = subprocess.run(["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], cwd=ROOT, text=True, capture_output=True)
    with urllib.request.urlopen(f"{OLLAMA_URL}/api/version", timeout=10) as response:
        ollama_version = json.load(response).get("version")
    with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=10) as response:
        models = json.load(response).get("models", [])
    model_meta = {item["name"]: item for item in models if item.get("name") in {QWEN_MODEL, "gpt-oss:20b", "nomic-embed-text:latest"}}
    connection = sqlite3.connect(f"file:{LEXICAL_DB.resolve()}?immutable=1", uri=True)
    try:
        lexical_identity = {
            "path": str(LEXICAL_DB), "size_bytes": LEXICAL_DB.stat().st_size,
            "dataset_versions": sorted({row[0] for row in connection.execute("SELECT DISTINCT dataset_version FROM entries")}),
            "importer_versions": sorted({row[0] for row in connection.execute("SELECT DISTINCT importer_version FROM entries")}),
            "entry_count": connection.execute("SELECT COUNT(*) FROM entries").fetchone()[0],
            "sense_count": connection.execute("SELECT COUNT(*) FROM senses").fetchone()[0],
        }
    finally:
        connection.close()
    return {
        "repository": str(ROOT), "branch": branch, "head": git_head(),
        "upstream": upstream.stdout.strip() if upstream.returncode == 0 else None,
        "git_status_short_literal": status,
        "ollama_version": ollama_version, "models": model_meta,
        "lexical_dataset_identity": lexical_identity,
        "benchmark_artifact_roots": {
            "m004.6.6": str(DEFAULT_REFERENCE.parent),
            "m004.6.7": str(ARTIFACT_BASE),
        },
        "reference_identity": reference_identity,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--phase-b-summary", type=Path, default=DEFAULT_PHASE_B_SUMMARY)
    parser.add_argument("--prior-qwen-attempts", type=Path, default=DEFAULT_PRIOR_QWEN_ATTEMPTS)
    parser.add_argument("--manifest", type=Path, default=HERE / "manifests/m004.6.7_candidate_reduction.json")
    parser.add_argument("--offline-only", action="store_true")
    parser.add_argument("--skip-live", action="store_true")
    args = parser.parse_args()

    manifest = load_json(args.manifest)
    run = run_id()
    root = ARTIFACT_BASE / run
    root.mkdir(parents=True, exist_ok=False)

    reference_identity = validate_reference(args.reference)
    reference, references, source_partitions = load_reference_and_partitions(args.reference)
    phase_b_summary = load_json(args.phase_b_summary)
    write_json(root / "manifest.json", manifest)
    write_json(root / "reference_identity.json", reference_identity)
    write_json(root / "preflight.json", preflight(reference_identity))

    characterization = failure_characterization(references, phase_b_summary)
    structural = score_structural_policy(references, source_partitions)
    latency = qwen_latency_baseline(args.prior_qwen_attempts)
    economics = exhaustive_economics(source_partitions, latency)
    distribution = partition_size_distribution(LEXICAL_DB)
    lazy_precompute = lazy_precompute_projection(distribution, latency)

    write_json(root / "failure_characterization.json", characterization)
    write_json(root / "deterministic_structural_policy.json", structural)
    write_json(root / "exhaustive_qwen_economics.json", economics)
    write_json(root / "partition_size_distribution.json", distribution)
    write_json(root / "lazy_precompute_projection.json", lazy_precompute)

    proposal_partitions = select_proposal_partitions(source_partitions, references)
    seeds = manifest["candidate_proposal"]["seeds"]
    max_candidates = manifest["candidate_proposal"].get("max_candidates_per_alias", DEFAULT_MAX_CANDIDATES_PER_ALIAS)
    plan = proposal_plan(
        proposal_partitions,
        seeds,
        max_candidates_per_alias=max_candidates,
        max_calls=manifest["candidate_proposal"]["maximum_total_calls"],
        max_projected_tokens=manifest["candidate_proposal"].get("max_projected_context_tokens", 32000),
    )
    write_json(root / "candidate_proposal_plan.json", plan)
    if not plan["within_budget"]:
        write_json(root / "summary.json", {"status": "STOP", "stop_condition": "projected live Qwen calls exceed authorized budget", "plan": plan})
        print(root)
        return 2
    if args.offline_only or args.skip_live:
        write_json(root / "summary.json", {"status": "OFFLINE_ONLY", "plan": plan, "offline_artifacts_complete": True})
        print(root)
        return 0

    attempts = []
    for partition_row in plan["planned_partitions"]:
        partition = next(item for item in proposal_partitions if item["partition_id"] == partition_row["partition_id"])
        for seed in seeds:
            attempts.append(invoke_proposal(run, partition, seed, max_candidates_per_alias=max_candidates))
            write_json(root / "candidate_proposal_raw_responses.json", attempts)
    proposal_metrics = evaluate_proposal_attempts(attempts, references)
    comparison = strategy_comparison(references=references, phase_b_summary=phase_b_summary, structural=structural, proposal=proposal_metrics, economics=economics)
    write_json(root / "candidate_proposal_raw_responses.json", attempts)
    write_json(root / "candidate_proposal_metrics.json", proposal_metrics)
    write_json(root / "strategy_comparison.json", comparison)

    structural_missed = set(structural["reference_metrics"]["lost_merge_pair_ids"])
    proposal_missed = set(proposal_metrics["union"]["lost_merge_pair_ids"])
    proposal_union_keys = {
        tuple(sorted(pair["source_sense_ids"]))
        for attempt in attempts for pair in attempt.get("candidate_pairs", [])
    }
    human_rows = []
    for pair in references:
        if pair["pair_id"] in characterization["false_negative_pair_ids"] or pair["pair_id"] in structural_missed or pair["pair_id"] in proposal_missed:
            human_rows.append({
                "pair_id": pair["pair_id"], "word": pair["word"], "pos": pair["pos"],
                "reference_decision": pair["reference_decision"], "review_notes": pair.get("review_notes", ""),
                "first_definitions": display_definitions(pair["first"]), "second_definitions": display_definitions(pair["second"]),
                "structural_evidence": structural_signals(pair["first"], pair["second"]),
                "qwen_candidate_proposal_retained_by_union": reference_pair_key(pair) in proposal_union_keys,
                "human_review_note": "Review false negative or reference-sensitive candidate-reduction behavior; do not relabel reference here.",
            })
    high_cost_false_positive_keys = sorted(proposal_union_keys - {reference_pair_key(pair) for pair in references})[:50]
    write_json(root / "human_review_cases.json", {"cases": human_rows, "sample_unreferenced_qwen_candidate_pairs": high_cost_false_positive_keys})

    summary = {
        "status": "PASS",
        "run_id": run,
        "artifact_root": str(root),
        "reference_counts": reference_identity["counts"],
        "offline_phase_completed_before_live_qwen": True,
        "candidate_proposal_plan": plan,
        "structural_metrics": structural["reference_metrics"],
        "candidate_proposal_metrics": proposal_metrics,
        "strategy_comparison": comparison,
        "recommendation": "Candidate reduction remains unsafe on this reference; prefer exhaustive single-pair Qwen as the correctness baseline and solve large-partition latency with caching/asynchronous preparation rather than unsafe screening.",
        "git_status_short_literal_at_start": preflight(reference_identity)["git_status_short_literal"],
    }
    write_json(root / "summary.json", summary)
    print(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
