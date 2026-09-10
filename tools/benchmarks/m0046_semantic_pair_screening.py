"""Benchmark-only high-recall semantic pair screening for M004.6.5."""

from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import math
import statistics
import sys
import time
import unicodedata
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from m0046_core_selection_benchmark import LEXICAL_DB, OLLAMA_URL, canonical_hash, git_head, utc_now
from m0046_learner_consolidation_benchmark import material_partition, source_node

ARTIFACT_BASE = Path.home() / ".local/share/vocab-app/benchmarks/m004.6.5"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def compact_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).split())


def representation(node: dict[str, Any]) -> str:
    definitions = node.get("definition", [])
    if isinstance(definitions, str):
        definitions = [definitions]
    return compact_text(f"{node.get('word', '')} [{node['pos']}]: {'; '.join(compact_text(item) for item in definitions)}")


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def cosine(first: list[float], second: list[float]) -> float:
    dot = sum(a * b for a, b in zip(first, second))
    norm_a = math.sqrt(sum(a * a for a in first))
    norm_b = math.sqrt(sum(b * b for b in second))
    if not norm_a or not norm_b:
        raise ValueError("Cannot compare zero vector")
    return dot / (norm_a * norm_b)


def pair_id(partition_id: str, first: str, second: str, screening_identity: str) -> str:
    return f"{partition_id}:{canonical_hash([first, second, screening_identity])[:16]}"


def embed(model: str, texts: list[str]) -> tuple[list[list[float]], dict[str, Any]]:
    request = urllib.request.Request(
        f"{OLLAMA_URL}/api/embed",
        data=json.dumps({"model": model, "input": texts, "truncate": False}).encode(),
        headers={"Content-Type": "application/json"},
    )
    started = time.monotonic()
    with urllib.request.urlopen(request, timeout=600) as response:
        result = json.load(response)
    result["wall_seconds"] = time.monotonic() - started
    return result["embeddings"], result


def reference_partitions(reference: list[dict[str, Any]]) -> list[dict[str, Any]]:
    partitions: dict[str, dict[str, Any]] = {}
    for item in reference:
        partition = item["partition"]
        partitions[partition["partition_id"]] = partition
    return list(partitions.values())


def large_partitions(words: list[str]) -> list[dict[str, Any]]:
    result = []
    requested = {tuple(item.split(":", 1)) for item in words}
    for word in words:
        word = word.split(":", 1)[0]
        evidence = __import__("vocab_lexical_engine").lookup(LEXICAL_DB, word)
        projected = __import__("vocab_synthesis").project_synthesis_evidence(evidence)
        buckets: dict[tuple[str, tuple[str, ...]], list[dict[str, Any]] ] = defaultdict(list)
        for entry in projected["entries"]:
            for sense in entry["senses"]:
                node = source_node(entry, sense)
                node["word"] = word
                buckets[(node["pos"], material_partition(sense))].append(node)
        for (pos, labels), nodes in sorted(buckets.items()):
            if (word, pos) not in requested:
                continue
            nodes = sorted(nodes, key=lambda node: node["source_sense_id"])
            result.append({"partition_id": f"{word}:{pos}:projection-v1", "word": word, "pos": pos,
                           "material_partition": list(labels), "source_nodes": nodes})
    return result


def all_pairs(partition: dict[str, Any], identity: str) -> list[dict[str, Any]]:
    nodes = partition["source_nodes"]
    return [{
        "pair_id": pair_id(partition["partition_id"], first["source_sense_id"], second["source_sense_id"], identity),
        "partition_id": partition["partition_id"], "word": partition["word"], "pos": partition["pos"],
        "first": first, "second": second,
    } for first, second in itertools.combinations(nodes, 2)]


def policy_pairs(pairs: list[dict[str, Any]], vectors: dict[str, list[float]], policy: str, value: float) -> set[str]:
    by_partition: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for pair in pairs:
        by_partition[pair["partition_id"]].append(pair)
    retained: set[str] = set()
    if policy == "threshold":
        return {pair["pair_id"] for pair in pairs if cosine(vectors[pair["first"]["source_sense_id"]], vectors[pair["second"]["source_sense_id"]]) >= value}
    for partition_pairs in by_partition.values():
        peers: dict[str, list[tuple[float, str]]] = defaultdict(list)
        for pair in partition_pairs:
            score = cosine(vectors[pair["first"]["source_sense_id"]], vectors[pair["second"]["source_sense_id"]])
            first, second = pair["first"]["source_sense_id"], pair["second"]["source_sense_id"]
            peers[first].append((score, second))
            peers[second].append((score, first))
        selected: set[tuple[str, str]] = set()
        for source, candidates in peers.items():
            for _, target in sorted(candidates, key=lambda item: (-item[0], item[1]))[:int(value)]:
                selected.add(tuple(sorted((source, target))))
        for pair in partition_pairs:
            if tuple(sorted((pair["first"]["source_sense_id"], pair["second"]["source_sense_id"]))) in selected:
                retained.add(pair["pair_id"])
    return retained


def score_policy(retained: set[str], references: list[dict[str, Any]], ref_to_screen: dict[str, str]) -> dict[str, Any]:
    resolved = [item for item in references if item["reference_decision"] != "uncertain"]
    merges = [item for item in resolved if item["reference_decision"] == "merge"]
    separates = [item for item in resolved if item["reference_decision"] == "keep_separate"]
    lost = [item["pair_id"] for item in merges if ref_to_screen[item["pair_id"]] not in retained]
    removed_separates = sum(ref_to_screen[item["pair_id"]] not in retained for item in separates)
    return {"resolved_merge_count": len(merges), "resolved_keep_separate_count": len(separates),
            "merge_recall": (len(merges) - len(lost)) / len(merges) if merges else None,
            "keep_separate_removed": removed_separates, "keep_separate_reduction": removed_separates / len(separates) if separates else None,
            "retained_reference_pairs": sum(ref_to_screen[item["pair_id"]] in retained for item in references),
            "lost_merge_pair_ids": lost, "uncertain_pair_ids": [item["pair_id"] for item in references if item["reference_decision"] == "uncertain"]}


def loo_thresholds(reference: list[dict[str, Any]], vectors: dict[str, list[float]], pairs: list[dict[str, Any]], ref_to_screen: dict[str, str], thresholds: list[float]) -> list[dict[str, Any]]:
    result = []
    by_word = {item["word"] for item in reference}
    for held_out in sorted(by_word):
        train = [item for item in reference if item["word"] != held_out]
        test = [item for item in reference if item["word"] == held_out]
        train_pairs = [pair for pair in pairs if pair["pair_id"] in {ref_to_screen[item["pair_id"]] for item in train}]
        ref_map = {item["pair_id"]: ref_to_screen[item["pair_id"]] for item in train}
        candidates = []
        for threshold in thresholds:
            kept = policy_pairs(train_pairs, vectors, "threshold", threshold)
            candidates.append({"value": threshold, **score_policy(kept, train, ref_map)})
        selected = max((item for item in candidates if item["merge_recall"] == 1.0), key=lambda item: (item["keep_separate_reduction"], item["value"]), default=None)
        if selected is None:
            result.append({"held_out_word": held_out, "selected_threshold": None, "test_merge_recall": None, "test_lost_merge_pair_ids": []})
            continue
        test_pairs = [pair for pair in pairs if pair["pair_id"] in {ref_to_screen[item["pair_id"]] for item in test}]
        kept_test = policy_pairs(test_pairs, vectors, "threshold", selected["value"])
        test_map = {item["pair_id"]: ref_to_screen[item["pair_id"]] for item in test}
        test_score = score_policy(kept_test, test, test_map)
        result.append({"held_out_word": held_out, "selected_threshold": selected["value"],
                       "train_keep_separate_reduction": selected["keep_separate_reduction"],
                       "test_merge_recall": test_score["merge_recall"], "test_lost_merge_pair_ids": test_score["lost_merge_pair_ids"]})
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=HERE / "manifests/m004.6.5_semantic_pair_screening.json")
    parser.add_argument("--confirm-from-retained", type=Path)
    args = parser.parse_args()
    manifest = load_json(args.manifest)
    reference = load_json(Path(manifest["reference_artifact"]))
    ref_parts = reference_partitions(reference)
    large = large_partitions(manifest["large_partition_names"])
    partitions = ref_parts + [p for p in large if p["partition_id"] not in {x["partition_id"] for x in ref_parts}]
    model_meta = next(item for item in load_json_url(f"{OLLAMA_URL}/api/tags")["models"] if item["name"] == manifest["embedding_model"]["name"])
    identity = canonical_hash({"model": model_meta, "representation": manifest["representation"]})[:24]
    nodes = {node["source_sense_id"]: node | {"word": partition["word"]} for partition in partitions for node in partition["source_nodes"]}
    texts = {source_id: representation(node) for source_id, node in nodes.items()}
    vectors_list, embed_meta = embed(manifest["embedding_model"]["name"], list(texts.values()))
    vectors = dict(zip(texts, vectors_list))
    pairs = [pair for partition in partitions for pair in all_pairs(partition, identity)]
    ref_pair_lookup = {}
    for item in reference:
        first, second = item["first"]["source_sense_id"], item["second"]["source_sense_id"]
        matching = [pair for pair in pairs if {pair["first"]["source_sense_id"], pair["second"]["source_sense_id"]} == {first, second}]
        if len(matching) != 1:
            raise ValueError(f"Reference pair not found exactly once: {item['pair_id']}")
        ref_pair_lookup[item["pair_id"]] = matching[0]
    reference_scores = [{"pair_id": item["pair_id"], "reference_decision": item["reference_decision"],
                        "similarity": cosine(vectors[item["first"]["source_sense_id"]], vectors[item["second"]["source_sense_id"]]),
                        "representation_hashes": [text_hash(texts[item["first"]["source_sense_id"]]), text_hash(texts[item["second"]["source_sense_id"]])]} for item in reference]
    all_ref_pairs = list(ref_pair_lookup.values())
    ref_to_screen = {item["pair_id"]: ref_pair_lookup[item["pair_id"]]["pair_id"] for item in reference}
    thresholds = []
    for threshold in manifest["thresholds"]:
        kept = policy_pairs(all_ref_pairs, vectors, "threshold", threshold)
        thresholds.append({"policy": "threshold", "value": threshold, **score_policy(kept, reference, ref_to_screen)})
    topk = []
    for k in manifest["top_k_values"]:
        kept = policy_pairs(all_ref_pairs, vectors, "top_k", k)
        topk.append({"policy": "top_k", "value": k, **score_policy(kept, reference, ref_to_screen)})
    threshold_candidates = [row for row in thresholds if row["merge_recall"] == 1.0]
    topk_candidates = [row for row in topk if row["merge_recall"] == 1.0]
    chosen = max(threshold_candidates, key=lambda row: (row["keep_separate_reduction"], row["value"])) if threshold_candidates else None
    if chosen is None and topk_candidates:
        chosen = max(topk_candidates, key=lambda row: (row["keep_separate_reduction"], -row["value"]))
    run = utc_now().replace("-", "").replace(":", "")
    root = ARTIFACT_BASE / run
    root.mkdir(parents=True)
    output = {"benchmark_id": manifest["benchmark_id"], "benchmark_version": manifest["benchmark_version"], "run_id": run,
              "git_head": git_head(), "manifest": manifest, "embedding_model": model_meta, "embedding_identity": identity,
              "embedding_response_metadata": {key: value for key, value in embed_meta.items() if key != "embeddings"},
              "representation": manifest["representation"], "source_sense_count": len(nodes), "pair_count": len(pairs),
              "reference_similarity": reference_scores, "threshold_sweep": thresholds, "top_k_sweep": topk,
              "leave_one_word_out": loo_thresholds(reference, vectors, all_ref_pairs, ref_to_screen, manifest["thresholds"]),
              "selected_policy": chosen, "large_partition_projection": []}
    for partition in large:
        partition_pairs = all_pairs(partition, identity)
        if not partition_pairs:
            continue
        best_threshold = chosen if chosen and chosen["policy"] == "threshold" else None
        kept = policy_pairs(partition_pairs, vectors, "threshold", best_threshold["value"]) if best_threshold else policy_pairs(partition_pairs, vectors, "top_k", chosen["value"]) if chosen else set()
        output["large_partition_projection"].append({"word": partition["word"], "pos": partition["pos"], "source_senses": len(partition["source_nodes"]),
            "all_pairs": len(partition_pairs), "screened_pairs": len(kept), "reduction": 1 - len(kept) / len(partition_pairs), "chosen_policy": chosen})
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))
    (root / "screening_summary.json").write_text(json.dumps(output, indent=2, sort_keys=True))
    (root / "source_sense_representations.json").write_text(json.dumps({key: {"text": value, "hash": text_hash(value)} for key, value in texts.items()}, indent=2, sort_keys=True))
    with (root / "reference_review.csv").open("w", newline="", encoding="utf-8") as handle:
        fields = ["pair_id", "word", "pos", "reference_decision", "similarity", "threshold_retained", "top_k_retained", "review_notes"]
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader()
        threshold_kept = policy_pairs(all_ref_pairs, vectors, "threshold", chosen["value"]) if chosen and chosen["policy"] == "threshold" else set()
        top_k_kept = policy_pairs(all_ref_pairs, vectors, "top_k", 3)
        for row in reference_scores:
            writer.writerow({**{key: row.get(key, "") for key in ("pair_id", "reference_decision", "similarity")}, "word": next(x["word"] for x in reference if x["pair_id"] == row["pair_id"]), "pos": next(x["pos"] for x in reference if x["pair_id"] == row["pair_id"]), "threshold_retained": ref_to_screen[row["pair_id"]] in threshold_kept, "top_k_retained": ref_to_screen[row["pair_id"]] in top_k_kept, "review_notes": ""})
    if args.confirm_from_retained:
        derive_confirmation(root, args.confirm_from_retained)
    print(root)
    return 0


def load_json_url(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.load(response)


def derive_confirmation(root: Path, m0046_artifact: Path) -> None:
    summary = load_json(root / "screening_summary.json")
    references = load_json(Path(summary["manifest"]["reference_artifact"]))
    decisions = load_json(m0046_artifact / "decisions.json")
    chosen = summary["selected_policy"]
    similarities = {row["pair_id"]: row for row in summary["reference_similarity"]}
    retained = {pair["pair_id"] for pair in references
                if similarities[pair["pair_id"]]["similarity"] >= chosen["value"]}
    rows = []
    for pair in references:
        key = f"single-pair:qwen3:8b:{pair['pair_id']}"
        if pair["pair_id"] not in retained:
            rows.append({"pair_id": pair["pair_id"], "screening_decision": "screened_out_not_semantically_compared",
                         "qwen_majority_decision": None, "qwen_seed_evidence": None,
                         "reference_decision": pair["reference_decision"]})
        else:
            result = decisions[key]
            rows.append({"pair_id": pair["pair_id"], "screening_decision": "retained_for_semantic_review",
                         "qwen_majority_decision": result["majority_decision"], "qwen_seed_evidence": result["decisions"],
                         "reference_decision": pair["reference_decision"]})
    resolved = [row for row in rows if row["reference_decision"] != "uncertain"]
    judged = [row for row in resolved if row["qwen_majority_decision"] is not None]
    false_merges = [row["pair_id"] for row in judged if row["qwen_majority_decision"] == "merge" and row["reference_decision"] != "merge"]
    false_splits = [row["pair_id"] for row in resolved if row["reference_decision"] == "merge" and row["qwen_majority_decision"] != "merge"]
    confirmation = {
        "source": "retained M004.6.4 Qwen single-pair decisions; no new model calls",
        "screening_policy": chosen,
        "projected_qwen_calls": len(retained) * 3,
        "exhaustive_reference_qwen_calls": len(references) * 3,
        "qwen_calls_avoided": (len(references) - len(retained)) * 3,
        "resolved_pairs": len(resolved), "retained_resolved_pairs_judged": len(judged),
        "screened_out_not_semantically_compared": len(resolved) - len(judged),
        "false_merge_pair_ids": false_merges, "false_split_pair_ids": false_splits,
        "rows": rows,
    }
    (root / "qwen_confirmation_from_retained_artifacts.json").write_text(json.dumps(confirmation, indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
