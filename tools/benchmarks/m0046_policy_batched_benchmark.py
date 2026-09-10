"""Benchmark-only M004.6.4 policy, batch, anchor, and clustering experiment."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import requests

HERE = Path(__file__).parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
from m0046_core_selection_benchmark import MODEL_POLICIES, OLLAMA_URL, canonical_hash, git_head, installed_digest, utc_now
from m0046_learner_consolidation_benchmark import fixed_key_assembly, fixed_key_diagnostics, fixed_key_schema
from vocab_lexical_engine import canonical_json
from vocab_synthesis import response_content, strict_json_object

ARTIFACT_BASE = Path.home() / ".local/share/vocab-app/benchmarks/m004.6.4"
REASONS = ("paraphrase_or_duplicate", "contextual_variant", "specialized_subsense", "broader_or_narrower",
           "related_but_distinct", "materially_different", "insufficient_evidence")
INCONSISTENT = {("merge", "specialized_subsense"), ("merge", "broader_or_narrower"),
                ("merge", "related_but_distinct"), ("merge", "materially_different")}


def load_manifest(path: Path) -> dict[str, Any]:
    manifest = json.loads(path.read_text())
    required = {"benchmark_id", "benchmark_version", "reference_status", "source_partitions", "models", "seed_sequence",
                "batch_sizes", "maximum_total_calls", "policy", "pairs"}
    if missing := required - set(manifest):
        raise ValueError(f"Manifest missing fields: {sorted(missing)}")
    if set(manifest["models"]) != set(MODEL_POLICIES):
        raise ValueError("Both approved models are required")
    if not 50 <= len(manifest["pairs"]) <= 100:
        raise ValueError("Reference set must contain 50-100 pairs")
    return manifest


def decision_schema() -> dict[str, Any]:
    return {"type": "object", "additionalProperties": False, "properties": {
        "decision": {"type": "string", "enum": ["merge", "keep_separate", "uncertain"]},
        "reason": {"type": "string", "enum": list(REASONS)},
    }, "required": ["decision", "reason"]}


def batch_schema(pair_ids: list[str]) -> dict[str, Any]:
    return {"type": "object", "additionalProperties": False,
            "properties": {pair_id: decision_schema() for pair_id in pair_ids}, "required": pair_ids}


def decision_diagnostics(value: Any) -> dict[str, bool]:
    valid = isinstance(value, dict) and set(value) == {"decision", "reason"} and value.get("decision") in {"merge", "keep_separate", "uncertain"} and value.get("reason") in REASONS
    consistent = valid and (value["decision"], value["reason"]) not in INCONSISTENT
    return {"exact_keys": isinstance(value, dict) and set(value) == {"decision", "reason"}, "allowed_values": valid, "decision_reason_consistent": consistent}


def decision_schema_valid(diagnostics: dict[str, bool]) -> bool:
    return diagnostics["exact_keys"] and diagnostics["allowed_values"]


def batch_diagnostics(value: Any, pair_ids: list[str]) -> dict[str, bool]:
    return {"is_object": isinstance(value, dict), "complete_pair_coverage": isinstance(value, dict) and set(value) == set(pair_ids),
            "all_decisions_schema_valid": isinstance(value, dict) and all(decision_schema_valid(decision_diagnostics(value.get(pair_id))) for pair_id in pair_ids),
            "no_policy_inconsistency": isinstance(value, dict) and all(decision_diagnostics(value.get(pair_id))["decision_reason_consistent"] for pair_id in pair_ids)}


def source_partitions(manifest: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    partitions = json.loads(Path(manifest["source_partitions"]).read_text())
    return {(item["word"], item["pos"]): item for item in partitions}


def references(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    partitions = source_partitions(manifest)
    result = []
    for index, (word, pos, first, second, decision, reason) in enumerate(manifest["pairs"], start=1):
        partition = partitions[(word, pos)]
        nodes = partition["source_nodes"]
        pair = {"pair_id": f"P{index:03d}", "word": word, "pos": pos, "partition": partition,
                "first": nodes[first], "second": nodes[second], "reference_decision": decision, "reference_reason": reason,
                "reference_status": manifest["reference_status"]}
        pair["pair_hash"] = canonical_hash({"ids": [pair["first"]["source_sense_id"], pair["second"]["source_sense_id"]], "reference": [decision, reason]})
        result.append(pair)
    return result


def chunks(items: list[Any], size: int) -> list[list[Any]]:
    return [items[index:index + size] for index in range(0, len(items), size)]


def prompt_for(items: list[dict[str, Any]], policy: str) -> str:
    return canonical_json({"task": "Return exactly one JSON object matching the schema.", "learner_consolidation_policy": policy,
                           "pairs": [{"pair_id": item["pair_id"], "word": item["word"], "pos": item["pos"],
                                      "material_partition": item["partition"]["material_partition"],
                                      "sense_a": item["first"], "sense_b": item["second"]} for item in items]})


def invoke(run: str, benchmark_id: str, benchmark_version: int, experiment: str, model: str, seed: int, items: list[dict[str, Any]], policy: str) -> dict[str, Any]:
    schema = decision_schema() if len(items) == 1 else batch_schema([item["pair_id"] for item in items])
    prompt = prompt_for(items, policy)
    invocation = MODEL_POLICIES[model]
    options = {**invocation["options"], "seed": seed}
    if model == "qwen3:8b" and experiment in {"batch-10", "batch-20"}:
        options["num_predict"] = 1024
    record = {"attempt_id": f"{run}:{experiment}:{model}:{canonical_hash([item['pair_id'] for item in items])[:10]}:{seed}",
              "benchmark_id": benchmark_id, "benchmark_version": benchmark_version,
              "run_id": run, "timestamp": utc_now(), "git_head": git_head(), "experiment": experiment, "model": model,
              "model_digest": installed_digest(model), "ollama_version": requests.get(f"{OLLAMA_URL}/api/version", timeout=10).json()["version"],
              "invocation": {"think": invocation["think"], "options": options},
              "pair_ids": [item["pair_id"] for item in items], "pair_hashes": [item["pair_hash"] for item in items],
              "pair_context": [{"word": item["word"], "pos": item["pos"], "partition_id": item["partition"]["partition_id"],
                                "source_sense_ids": [item["first"]["source_sense_id"], item["second"]["source_sense_id"]]} for item in items],
              "prompt_hash": canonical_hash(prompt), "schema_hash": canonical_hash(schema), "seed": seed,
              "raw_provider_response": None, "raw_content": None, "parsed": None, "parse_error": None, "provider_status": None}
    try:
        response = requests.post(f"{OLLAMA_URL}/api/chat", json={"model": model, "messages": [{"role": "user", "content": prompt}],
                                 "stream": False, "format": schema, "think": invocation["think"], "keep_alive": "5m",
                                 "options": options}, timeout=240)
        response.raise_for_status()
        provider = response.json()
        record["raw_provider_response"], record["done_reason"] = provider, provider.get("done_reason")
        record["raw_content"] = response_content(provider)
        record["provider_status"] = "done_reason_length" if record["done_reason"] == "length" else ("empty_content" if not record["raw_content"] else "provider_success")
        try:
            record["parsed"] = strict_json_object(record["raw_content"])
        except Exception as error:
            record["parse_error"] = str(error)
            if record["provider_status"] == "provider_success":
                record["provider_status"] = "json_parse_failure"
    except requests.Timeout as error:
        record.update(provider_status="timeout", provider_error=str(error))
    except requests.RequestException as error:
        record.update(provider_status="transport_failure", provider_error=str(error))
    if len(items) == 1:
        record["diagnostics"] = decision_diagnostics(record["parsed"])
        record["results"] = {items[0]["pair_id"]: record["parsed"]} if decision_schema_valid(record["diagnostics"]) else {}
    else:
        record["diagnostics"] = batch_diagnostics(record["parsed"], record["pair_ids"])
        record["results"] = record["parsed"] if all(record["diagnostics"][field] for field in ("is_object", "complete_pair_coverage", "all_decisions_schema_valid")) else {}
    return record


def majority(records: list[dict[str, Any]], pair_id: str) -> dict[str, Any]:
    values = [record["results"][pair_id] for record in records if pair_id in record["results"]]
    decisions = Counter(value["decision"] for value in values)
    winner, count = decisions.most_common(1)[0] if decisions else ("uncertain", 0)
    return {"decisions": values, "majority_decision": winner if count >= 2 else "uncertain",
            "unanimous": len(decisions) == 1 and len(values) == 3, "disagreement": len(decisions) > 1}


def scores(decisions: dict[str, dict[str, Any]], reference: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [(item["reference_decision"], decisions[item["pair_id"]]["majority_decision"]) for item in reference]
    merge_tp = sum(expected == actual == "merge" for expected, actual in rows)
    merge_fp = sum(expected != "merge" and actual == "merge" for expected, actual in rows)
    merge_fn = sum(expected == "merge" and actual != "merge" for expected, actual in rows)
    separate = [(expected, actual) for expected, actual in rows if expected == "keep_separate"]
    return {"reference_agreement": sum(expected == actual for expected, actual in rows) / len(rows),
            "merge_precision": merge_tp / (merge_tp + merge_fp) if merge_tp + merge_fp else None,
            "merge_recall": merge_tp / (merge_tp + merge_fn) if merge_tp + merge_fn else None,
            "false_merges": merge_fp, "false_splits": merge_fn,
            "keep_separate_accuracy": sum(actual == "keep_separate" for _, actual in separate) / len(separate),
            "uncertain_rate": sum(actual == "uncertain" for _, actual in rows) / len(rows)}


def cluster(nodes: list[str], pair_decisions: list[dict[str, Any]], policy: str) -> dict[str, Any]:
    parent = {node: node for node in nodes}
    def find(node: str) -> str:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node
    def groups() -> dict[str, set[str]]:
        output: dict[str, set[str]] = defaultdict(set)
        for node in nodes:
            output[find(node)].add(node)
        return output
    decisions = {frozenset(item["source_sense_ids"]): item["majority_decision"] for item in pair_decisions}
    conflicts = []
    for edge, decision in sorted(decisions.items(), key=lambda item: sorted(item[0])):
        if decision != "merge":
            continue
        first, second = sorted(edge)
        left, right = find(first), find(second)
        if left == right:
            continue
        left_members, right_members = groups()[left], groups()[right]
        cross = [frozenset((a, b)) for a in left_members for b in right_members]
        if any(decisions.get(pair) == "keep_separate" for pair in cross):
            conflicts.append({"blocked_merge": sorted(edge), "reason": "explicit_keep_separate"})
            continue
        if policy == "complete-link" and not all(decisions.get(pair) == "merge" for pair in cross):
            conflicts.append({"blocked_merge": sorted(edge), "reason": "missing_complete_merge_evidence"})
            continue
        parent[right] = left
    container_groups = sorted([sorted(group) for group in groups().values()], key=lambda group: group[0])
    containers = [{"container_id": f"G{index:03d}", "source_sense_ids": group} for index, group in enumerate(container_groups, start=1)]
    membership = [sense for container in containers for sense in container["source_sense_ids"]]
    return {"policy": policy, "containers": containers, "conflicts": conflicts,
            "invariants": {"complete_coverage": set(membership) == set(nodes), "exactly_once": len(membership) == len(set(membership)) == len(nodes)}}


def anchor_proposals(reference: list[dict[str, Any]], decisions: dict[str, dict[str, Any]], model: str) -> list[dict[str, Any]]:
    edge_decisions = {
        frozenset((pair["first"]["source_sense_id"], pair["second"]["source_sense_id"])): decisions[f"anchor:{model}:{pair['pair_id']}"]["majority_decision"]
        for pair in reference
    }
    anchors = sorted({(pair["word"], pair["pos"], pair["first"]["source_sense_id"]) for pair in reference})
    proposals = []
    for index, (word, pos, anchor) in enumerate(anchors, start=1):
        direct_pairs = [pair for pair in reference if (pair["word"], pair["pos"], pair["first"]["source_sense_id"]) == (word, pos, anchor)]
        direct_merges = sorted(pair["second"]["source_sense_id"] for pair in direct_pairs if edge_decisions[frozenset((anchor, pair["second"]["source_sense_id"]))] == "merge")
        accepted, blocked = [anchor], []
        for candidate in direct_merges:
            cross = [frozenset((candidate, member)) for member in accepted]
            if any(edge_decisions.get(edge) == "keep_separate" for edge in cross):
                blocked.append({"source_sense_id": candidate, "reason": "explicit_keep_separate"})
            elif all(edge_decisions.get(edge) == "merge" for edge in cross):
                accepted.append(candidate)
            else:
                blocked.append({"source_sense_id": candidate, "reason": "missing_complete_merge_evidence"})
        proposals.append({
            "proposal_id": f"A{index:03d}",
            "word": word,
            "pos": pos,
            "anchor_source_sense_id": anchor,
            "direct_merge_source_sense_ids": [anchor, *direct_merges],
            "safety_accepted_source_sense_ids": accepted,
            "blocked_candidates": blocked,
            "accepted_as_global_container": False,
        })
    return proposals


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")


def enrich_attempt_identity(root: Path, manifest: dict[str, Any]) -> None:
    reference = {item["pair_id"]: item for item in json.loads((root / "reference_pairs.json").read_text())}
    attempts_path = root / "attempts.json"
    attempts = json.loads(attempts_path.read_text())
    for attempt in attempts:
        attempt.setdefault("benchmark_id", manifest["benchmark_id"])
        attempt.setdefault("benchmark_version", manifest["benchmark_version"])
        attempt.setdefault("pair_context", [{
            "word": reference[pair_id]["word"],
            "pos": reference[pair_id]["pos"],
            "partition_id": reference[pair_id]["partition"]["partition_id"],
            "source_sense_ids": [reference[pair_id]["first"]["source_sense_id"], reference[pair_id]["second"]["source_sense_id"]],
        } for pair_id in attempt["pair_ids"]])
    write_json(attempts_path, attempts)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=HERE / "manifests/m004.6.4_policy_batched_reference.json")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--derive-artifacts", type=Path)
    args = parser.parse_args()
    manifest = load_manifest(args.manifest)
    if args.derive_artifacts:
        enrich_attempt_identity(args.derive_artifacts, manifest)
        refs = json.loads((args.derive_artifacts / "reference_pairs.json").read_text())
        decisions = json.loads((args.derive_artifacts / "decisions.json").read_text())
        write_json(args.derive_artifacts / "anchor_proposals.json", {
            model: anchor_proposals(refs, decisions, model) for model in manifest["models"]
        })
        return 0
    refs = references(manifest)
    anchors = sorted({(item["word"], item["pos"], item["first"]["source_sense_id"]) for item in refs})
    projection = {"single_pair_requests": len(refs) * 6, "batch_requests": sum(len(chunks(refs, size)) * 6 for size in manifest["batch_sizes"]),
                  "anchor_requests": len(anchors) * 6}
    projection["total_requests"] = sum(projection.values())
    if projection["total_requests"] > manifest["maximum_total_calls"]:
        raise RuntimeError(f"Call gate exceeded: {projection['total_requests']}")
    if args.smoke:
        refs, anchors = refs[:5], [(refs[0]["word"], refs[0]["pos"], refs[0]["first"]["source_sense_id"])]
    run = utc_now().replace("-", "").replace(":", "")
    root = ARTIFACT_BASE / run
    root.mkdir(parents=True)
    write_json(root / "manifest.json", manifest)
    write_json(root / "reference_pairs.json", refs)
    write_json(root / "projection.json", projection)
    attempts = []
    plans = [("single-pair", [[item] for item in refs])]
    plans.extend((f"batch-{size}", chunks(refs, size)) for size in manifest["batch_sizes"])
    anchor_batches = [[item for item in refs if (item["word"], item["pos"], item["first"]["source_sense_id"]) == anchor] for anchor in anchors]
    plans.append(("anchor", anchor_batches))
    for experiment, batches in plans:
        for batch in batches:
            for model in manifest["models"]:
                for seed in manifest["seed_sequence"]:
                    attempts.append(invoke(run, manifest["benchmark_id"], manifest["benchmark_version"], experiment, model, seed, batch, manifest["policy"]))
                    write_json(root / "attempts.json", attempts)
    decisions = {}
    for experiment, _ in plans:
        for model in manifest["models"]:
            for pair in refs:
                records = [record for record in attempts if record["experiment"] == experiment and record["model"] == model and pair["pair_id"] in record["pair_ids"]]
                decisions[f"{experiment}:{model}:{pair['pair_id']}"] = majority(records, pair["pair_id"])
    summary = {experiment: {model: scores({pair["pair_id"]: decisions[f"{experiment}:{model}:{pair['pair_id']}"] for pair in refs}, refs)
                            for model in manifest["models"]} for experiment, _ in plans}
    clusters = []
    partitions = {item["partition"]["partition_id"]: item["partition"] for item in refs}
    for partition in partitions.values():
        partition_pairs = [item for item in refs if item["partition"]["partition_id"] == partition["partition_id"]]
        for model in manifest["models"]:
            model_decisions = [{
                "source_sense_ids": [item["first"]["source_sense_id"], item["second"]["source_sense_id"]],
                "majority_decision": decisions[f"single-pair:{model}:{item['pair_id']}"]["majority_decision"],
            } for item in partition_pairs]
            nodes = [node["source_sense_id"] for node in partition["source_nodes"]]
            for policy in ("union", "complete-link"):
                clusters.append({"partition_id": partition["partition_id"], "word": partition["word"], "pos": partition["pos"],
                                 "model": model, **cluster(nodes, model_decisions, policy)})
    write_json(root / "decisions.json", decisions)
    write_json(root / "summary.json", summary)
    write_json(root / "clusters.json", clusters)
    write_json(root / "anchor_proposals.json", {
        model: anchor_proposals(refs, decisions, model) for model in manifest["models"]
    })
    with (root / "review.csv").open("w", newline="", encoding="utf-8") as output:
        fields = ["pair_id", "word", "pos", "sense_a", "sense_b", "reference_decision", "reference_reason", "experiment", "anonymous_model", "majority_decision", "decisions", "review_notes"]
        writer = csv.DictWriter(output, fieldnames=fields); writer.writeheader()
        for pair in refs:
            for experiment, _ in plans:
                for model, label in (("gpt-oss:20b", "Model A"), ("qwen3:8b", "Model B")):
                    result = decisions[f"{experiment}:{model}:{pair['pair_id']}"]
                    writer.writerow({"pair_id": pair["pair_id"], "word": pair["word"], "pos": pair["pos"],
                                     "sense_a": canonical_json(pair["first"]), "sense_b": canonical_json(pair["second"]),
                                     "reference_decision": pair["reference_decision"], "reference_reason": pair["reference_reason"],
                                     "experiment": experiment, "anonymous_model": label,
                                     "majority_decision": result["majority_decision"], "decisions": canonical_json(result["decisions"]), "review_notes": ""})
    write_json(root / "review_mapping.json", {"Model A": "gpt-oss:20b", "Model B": "qwen3:8b"})
    print(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
