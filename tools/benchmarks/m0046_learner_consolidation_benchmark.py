"""Benchmark-only M004.6.3 bounded equivalence and code-owned consolidation."""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import requests

BENCHMARK_DIR = Path(__file__).parent
if str(BENCHMARK_DIR) not in sys.path:
    sys.path.insert(0, str(BENCHMARK_DIR))
from m0046_core_selection_benchmark import (
    ARTIFACT_BASE as TIER1_ARTIFACT_BASE,
    LEXICAL_DB,
    MODEL_POLICIES,
    OLLAMA_URL,
    canonical_hash,
    fixed_key_assembly,
    fixed_key_diagnostics,
    fixed_key_schema,
    git_head,
    installed_digest,
    utc_now,
)

ROOT = BENCHMARK_DIR.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from vocab_lexical_engine import canonical_json, evidence_set_hash, lookup
from vocab_synthesis import MATERIAL_LABELS, project_synthesis_evidence, response_content, strict_json_object

ARTIFACT_BASE = Path.home() / ".local/share/vocab-app/benchmarks/m004.6.3"


def load_manifest(path: Path) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "benchmark_id", "benchmark_version", "words", "selected_partitions", "pair_policy",
        "material_boundary_policy", "models", "equivalence_contract", "clustering_policy",
        "ranking_contract", "seed_sequence", "attempts_per_pair_model", "maximum_total_calls",
    }
    if missing := required - set(manifest):
        raise ValueError(f"Manifest missing fields: {sorted(missing)}")
    if manifest["attempts_per_pair_model"] != len(manifest["seed_sequence"]):
        raise ValueError("attempt count must match seed sequence")
    if set(manifest["models"]) != set(MODEL_POLICIES):
        raise ValueError("Manifest must retain both approved models")
    return manifest


def material_partition(sense: dict[str, Any]) -> tuple[str, ...]:
    return tuple(sorted(set(sense.get("tags", [])) & MATERIAL_LABELS))


def source_node(entry: dict[str, Any], sense: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_sense_id": sense["sense_id"],
        "definition": sense.get("glosses", []),
        "labels": sorted(sense.get("tags", [])),
        "examples": [example["text"] for example in sense.get("examples", [])],
        "relations": [{"type": relation["type"], "target": relation["target"]} for relation in sense.get("relations", [])],
        "pos": entry["part_of_speech"],
        "material_partition": material_partition(sense),
    }


def build_reference_corpus(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    selected = {(item["word"], item["pos"], tuple(item["material_labels"])): item for item in manifest["selected_partitions"]}
    partitions = []
    for word in manifest["words"]:
        evidence = project_synthesis_evidence(lookup(LEXICAL_DB, word))
        buckets: dict[tuple[str, tuple[str, ...]], list[dict[str, Any]]] = defaultdict(list)
        for entry in evidence["entries"]:
            for sense in entry["senses"]:
                node = source_node(entry, sense)
                buckets[(node["pos"], node["material_partition"])].append(node)
        for (pos, labels), nodes in sorted(buckets.items()):
            selection = selected.get((word, pos, labels))
            if selection is None:
                continue
            nodes = sorted(nodes, key=lambda node: node["source_sense_id"])
            partition = {
                "word": word, "normalized_lemma": evidence["normalized_lemma"], "pos": pos,
                "material_partition": list(labels), "selection_rationale": selection["rationale"],
                "lexical_dataset_versions": evidence["wiktionary_versions"],
                "lexical_evidence_hash": evidence_set_hash(evidence),
                "wordnet_evidence": evidence.get("wordnet", []),
                "source_nodes": nodes,
            }
            partition["partition_id"] = f"{word}:{pos}:{canonical_hash(partition)[:12]}"
            partition["partition_hash"] = canonical_hash(partition)
            partitions.append(partition)
    if len(partitions) != len(selected):
        raise ValueError("A selected complete partition was not found in the lexical corpus")
    return partitions


def pair_records(partition: dict[str, Any]) -> list[dict[str, Any]]:
    records = []
    for first, second in itertools.combinations(partition["source_nodes"], 2):
        pair = {
            "partition_id": partition["partition_id"],
            "source_sense_ids": [first["source_sense_id"], second["source_sense_id"]],
            "first": first,
            "second": second,
        }
        pair["pair_id"] = f"{partition['partition_id']}:{canonical_hash(pair['source_sense_ids'])[:12]}"
        records.append(pair)
    return records


def call_projection(partitions: list[dict[str, Any]], manifest: dict[str, Any]) -> dict[str, int]:
    pairs = sum(len(pair_records(partition)) for partition in partitions)
    multiplier = len(manifest["models"]) * manifest["attempts_per_pair_model"]
    equivalence = pairs * multiplier
    ranking = len(partitions) * multiplier
    return {"source_senses": sum(len(partition["source_nodes"]) for partition in partitions), "pairs": pairs,
            "equivalence_calls": equivalence, "ranking_calls": ranking, "total_calls": equivalence + ranking}


def equivalence_schema() -> dict[str, Any]:
    return {"type": "object", "additionalProperties": False, "properties": {
        "relationship": {"type": "string", "enum": ["same", "distinct", "uncertain"]},
    }, "required": ["relationship"]}


def equivalence_prompt(partition: dict[str, Any], pair: dict[str, Any]) -> str:
    return canonical_json({
        "task": "Return exactly one JSON object matching the schema.",
        "rule": "Return same only if the senses express substantially the same learner meaning and differences are primarily context/application. Return distinct when a learner needs a genuinely different meaning. Return uncertain when evidence is insufficient. Never merge across POS or material-label boundaries.",
        "word": partition["normalized_lemma"], "pos": partition["pos"], "material_partition": partition["material_partition"],
        "sense_a": pair["first"], "sense_b": pair["second"],
    })


def relationship_diagnostics(parsed: Any) -> dict[str, bool]:
    return {
        "parse_success": isinstance(parsed, dict),
        "exact_top_level_keys": isinstance(parsed, dict) and set(parsed) == {"relationship"},
        "relationship_is_allowed": isinstance(parsed, dict) and parsed.get("relationship") in {"same", "distinct", "uncertain"},
    }


def invoke(*, run_id: str, phase: str, model: str, seed: int, schema: dict[str, Any], prompt: str,
           partition: dict[str, Any], identity: str) -> dict[str, Any]:
    policy = MODEL_POLICIES[model]
    record: dict[str, Any] = {
        "attempt_id": f"{run_id}:{phase}:{model}:{identity}:{seed}", "run_id": run_id, "phase": phase,
        "timestamp": utc_now(), "git_head": git_head(), "model": model, "model_digest": installed_digest(model),
        "ollama_version": requests.get(f"{OLLAMA_URL}/api/version", timeout=10).json()["version"],
        "invocation": {"think": policy["think"], "options": {**policy["options"], "seed": seed}},
        "partition_id": partition["partition_id"], "partition_hash": partition["partition_hash"],
        "word": partition["word"], "pos": partition["pos"], "material_partition": partition["material_partition"],
        "lexical_dataset_versions": partition["lexical_dataset_versions"], "lexical_evidence_hash": partition["lexical_evidence_hash"],
        "identity": identity, "prompt_hash": canonical_hash(prompt), "schema_hash": canonical_hash(schema), "seed": seed,
        "provider_status": None, "done_reason": None, "raw_provider_response": None, "raw_content": None,
        "parsed": None, "parse_error": None,
    }
    try:
        response = requests.post(f"{OLLAMA_URL}/api/chat", json={
            "model": model, "messages": [{"role": "user", "content": prompt}], "stream": False,
            "format": schema, "think": policy["think"], "keep_alive": "5m",
            "options": {**policy["options"], "seed": seed},
        }, timeout=240)
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
    record["diagnostics"] = relationship_diagnostics(record["parsed"]) if phase == "equivalence" else fixed_key_diagnostics(record["parsed"], identity.split(","))
    return record


def majority_relationship(records: list[dict[str, Any]]) -> dict[str, Any]:
    values = [record["parsed"]["relationship"] for record in records if all(record["diagnostics"].values())]
    counts = Counter(values)
    winner, count = counts.most_common(1)[0] if counts else ("uncertain", 0)
    return {"judgments": values, "counts": dict(counts), "unanimous": len(counts) == 1 and len(values) == 3,
            "majority_relationship": winner if count >= 2 else "uncertain", "disagreement": len(counts) > 1}


def components(nodes: list[str], same_edges: list[tuple[str, str]], distinct_edges: set[frozenset[str]]) -> tuple[list[list[str]], list[dict[str, Any]]]:
    parent = {node: node for node in nodes}
    def find(node: str) -> str:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node
    def members(root: str) -> set[str]:
        return {node for node in nodes if find(node) == root}
    conflicts = []
    for first, second in sorted(same_edges):
        first_root, second_root = find(first), find(second)
        if first_root == second_root:
            continue
        left, right = members(first_root), members(second_root)
        conflicting = sorted([sorted(edge) for edge in distinct_edges if (set(edge) & left) and (set(edge) & right)])
        if conflicting:
            conflicts.append({"blocked_same_edge": [first, second], "distinct_evidence": conflicting})
            continue
        parent[second_root] = first_root
    grouped: dict[str, list[str]] = defaultdict(list)
    for node in nodes:
        grouped[find(node)].append(node)
    return sorted([sorted(group) for group in grouped.values()], key=lambda group: group[0]), conflicts


def containers_for_model(partition: dict[str, Any], pair_evidence: list[dict[str, Any]], model: str) -> dict[str, Any]:
    evidence = {
        item["pair_id"]: item
        for item in pair_evidence
        if item["model"] == model and item["partition_id"] == partition["partition_id"]
    }
    same_edges, distinct_edges = [], set()
    for item in evidence.values():
        first, second = item["source_sense_ids"]
        if item["majority_relationship"] == "same":
            same_edges.append((first, second))
        elif item["majority_relationship"] == "distinct":
            distinct_edges.add(frozenset((first, second)))
    groups, conflicts = components([node["source_sense_id"] for node in partition["source_nodes"]], same_edges, distinct_edges)
    result = []
    for index, group in enumerate(groups, start=1):
        members = [node for node in partition["source_nodes"] if node["source_sense_id"] in group]
        result.append({"container_id": f"G{index:03d}", "source_sense_ids": group,
                       "evidence_definitions": [node["definition"] for node in members], "labels": sorted({label for node in members for label in node["labels"]})})
    validation = validate_containers(partition, result)
    return {"model": model, "partition_id": partition["partition_id"], "clustering_policy": "conservative-majority-union-find-v1",
            "containers": result, "conflicts": conflicts, "validation": validation,
            "container_hash": canonical_hash(result)}


def validate_containers(partition: dict[str, Any], containers: list[dict[str, Any]]) -> dict[str, bool]:
    expected = [node["source_sense_id"] for node in partition["source_nodes"]]
    actual = [sense_id for container in containers for sense_id in container["source_sense_ids"]]
    return {"complete_coverage": set(actual) == set(expected), "exactly_once": len(actual) == len(set(actual)) == len(expected),
            "code_generated_ids": [container["container_id"] for container in containers] == [f"G{index:03d}" for index in range(1, len(containers) + 1)],
            "pos_and_material_local": True}


def ranking_prompt(partition: dict[str, Any], containers: list[dict[str, Any]]) -> str:
    return canonical_json({
        "task": "Return exactly one JSON object matching the schema.",
        "instruction": "Score every code-owned learner-meaning container from 0 to 5 for learner relevance. Set core_count from 1 through five. Do not omit or add keys.",
        "word": partition["normalized_lemma"], "pos": partition["pos"], "containers": containers,
    })


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")


def performance(records: list[dict[str, Any]]) -> dict[str, Any]:
    output = {}
    for model in MODEL_POLICIES:
        rows = [record for record in records if record["model"] == model]
        values = [(record["raw_provider_response"] or {}) for record in rows]
        totals = [value.get("total_duration", 0) / 1_000_000_000 for value in values]
        output[model] = {
            "calls": len(rows),
            "provider_failures": sum(record["provider_status"] != "provider_success" for record in rows),
            "p50_total_seconds": statistics.median(totals) if totals else None,
            "p95_total_seconds": sorted(totals)[round((len(totals) - 1) * .95)] if totals else None,
            "p50_generated_tokens": statistics.median([value.get("eval_count", 0) for value in values]) if values else None,
            "max_load_seconds": max([value.get("load_duration", 0) / 1_000_000_000 for value in values], default=0),
        }
    return output


def summary(partitions: list[dict[str, Any]], evidence: list[dict[str, Any]], containers: list[dict[str, Any]],
            equivalence: list[dict[str, Any]], rankings: list[dict[str, Any]]) -> dict[str, Any]:
    pair_outcomes = {model: Counter(item["majority_relationship"] for item in evidence if item["model"] == model) for model in MODEL_POLICIES}
    by_pair: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in evidence:
        by_pair[item["pair_id"]].append(item)
    model_disagreements = sum(
        len(items) == 2 and items[0]["majority_relationship"] != items[1]["majority_relationship"]
        for items in by_pair.values()
    )
    ratios = {
        model: [
            len(item["containers"]) / len(next(partition for partition in partitions if partition["partition_id"] == item["partition_id"])["source_nodes"])
            for item in containers if item["model"] == model
        ]
        for model in MODEL_POLICIES
    }
    return {
        "equivalence": {"pair_evidence_count": len(evidence), "by_model_relationship": {model: dict(counts) for model, counts in pair_outcomes.items()},
                        "model_disagreement_pairs": model_disagreements, "performance": performance(equivalence)},
        "containers": {"by_model_count": {model: sum(len(item["containers"]) for item in containers if item["model"] == model) for model in MODEL_POLICIES},
                       "consolidation_ratio": {model: {"mean": statistics.mean(values), "median": statistics.median(values)} for model, values in ratios.items()},
                       "conflict_count": sum(len(item["conflicts"]) for item in containers)},
        "ranking": {"performance": performance(rankings)},
    }


def review_artifacts(root: Path, partitions: list[dict[str, Any]], evidence: list[dict[str, Any]],
                     containers: list[dict[str, Any]]) -> None:
    partition_by_id = {partition["partition_id"]: partition for partition in partitions}
    container_by_key = {(item["partition_id"], item["model"]): item for item in containers}
    with (root / "equivalence_review.csv").open("w", newline="", encoding="utf-8") as output:
        fields = ["partition_id", "word", "pos", "material_partition", "pair_id", "source_sense_ids", "sense_a_definitions",
                  "sense_b_definitions", "anonymous_model", "judgments", "majority_relationship", "unanimous", "disagreement"]
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        for item in evidence:
            partition = partition_by_id[item["partition_id"]]
            nodes = {node["source_sense_id"]: node for node in partition["source_nodes"]}
            first, second = item["source_sense_ids"]
            writer.writerow({"partition_id": item["partition_id"], "word": partition["word"], "pos": partition["pos"],
                             "material_partition": "|".join(partition["material_partition"]), "pair_id": item["pair_id"],
                             "source_sense_ids": canonical_json(item["source_sense_ids"]),
                             "sense_a_definitions": canonical_json(nodes[first]["definition"]),
                             "sense_b_definitions": canonical_json(nodes[second]["definition"]),
                             "anonymous_model": "Model A" if item["model"] == "gpt-oss:20b" else "Model B",
                             "judgments": canonical_json(item["judgments"]), "majority_relationship": item["majority_relationship"],
                             "unanimous": item["unanimous"], "disagreement": item["disagreement"]})
    with (root / "container_review.csv").open("w", newline="", encoding="utf-8") as output:
        fields = ["partition_id", "word", "pos", "material_partition", "anonymous_model", "source_nodes_json",
                  "containers_json", "conflicts_json", "coverage_score", "merge_precision_score",
                  "consolidation_efficiency_score", "learner_coherence_score", "overall", "review_notes"]
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        for partition in partitions:
            for model in MODEL_POLICIES:
                item = container_by_key[(partition["partition_id"], model)]
                writer.writerow({"partition_id": partition["partition_id"], "word": partition["word"], "pos": partition["pos"],
                                 "material_partition": "|".join(partition["material_partition"]),
                                 "anonymous_model": "Model A" if model == "gpt-oss:20b" else "Model B",
                                 "source_nodes_json": canonical_json(partition["source_nodes"]),
                                 "containers_json": canonical_json(item["containers"]), "conflicts_json": canonical_json(item["conflicts"]),
                                 "coverage_score": "", "merge_precision_score": "", "consolidation_efficiency_score": "",
                                 "learner_coherence_score": "", "overall": "", "review_notes": ""})
    write_json(root / "review_model_mapping.json", {"Model A": "gpt-oss:20b", "Model B": "qwen3:8b"})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=BENCHMARK_DIR / "manifests/m004.6.3_reference_subproblem.json")
    parser.add_argument("--corpus-only", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    manifest = load_manifest(args.manifest)
    partitions = build_reference_corpus(manifest)
    projection = call_projection(partitions, manifest)
    if projection["total_calls"] > manifest["maximum_total_calls"]:
        raise RuntimeError(f"Call gate exceeded: {projection['total_calls']}")
    if args.corpus_only:
        print(json.dumps({"partitions": partitions, "projection": projection}, indent=2))
        return 0
    run = utc_now().replace("-", "").replace(":", "").replace("Z", "Z")
    root = ARTIFACT_BASE / run
    root.mkdir(parents=True)
    write_json(root / "manifest.json", manifest)
    write_json(root / "partitions.json", partitions)
    write_json(root / "projection.json", projection)
    if args.smoke:
        partitions = partitions[:1]
    equivalence, evidence, containers, rankings = [], [], [], []
    pairs = [pair for partition in partitions for pair in pair_records(partition)]
    if args.smoke:
        pairs = pairs[:1]
    for pair in pairs:
        partition = next(item for item in partitions if item["partition_id"] == pair["partition_id"])
        schema, prompt = equivalence_schema(), equivalence_prompt(partition, pair)
        for model in manifest["models"]:
            records = [invoke(run_id=run, phase="equivalence", model=model, seed=seed, schema=schema, prompt=prompt,
                              partition=partition, identity=pair["pair_id"]) for seed in manifest["seed_sequence"]]
            equivalence.extend(records)
            decision = majority_relationship(records)
            evidence.append({"pair_id": pair["pair_id"], "partition_id": pair["partition_id"], "source_sense_ids": pair["source_sense_ids"],
                             "model": model, **decision})
            write_json(root / "equivalence_attempts.json", equivalence)
            write_json(root / "pair_evidence.json", evidence)
    for partition in partitions:
        for model in manifest["models"]:
            container = containers_for_model(partition, evidence, model)
            containers.append(container)
            ids = [item["container_id"] for item in container["containers"]]
            schema, prompt = fixed_key_schema(ids), ranking_prompt(partition, container["containers"])
            for seed in manifest["seed_sequence"]:
                record = invoke(run_id=run, phase="ranking", model=model, seed=seed, schema=schema, prompt=prompt,
                                partition=partition, identity=",".join(ids))
                record["container_hash"] = container["container_hash"]
                record["assembly"] = fixed_key_assembly(record["parsed"], ids)
                rankings.append(record)
                write_json(root / "ranking_attempts.json", rankings)
    write_json(root / "equivalence_attempts.json", equivalence)
    write_json(root / "pair_evidence.json", evidence)
    write_json(root / "containers.json", containers)
    write_json(root / "ranking_attempts.json", rankings)
    write_json(root / "summary.json", summary(partitions, evidence, containers, equivalence, rankings))
    review_artifacts(root, partitions, evidence, containers)
    print(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
