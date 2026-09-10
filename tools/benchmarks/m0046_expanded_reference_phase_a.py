"""Phase A reference construction for M004.6.6.

This module is benchmark-only. It surfaces candidate pairs for human
adjudication; it does not assign semantic labels or run an LLM.
"""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import sys
from collections import Counter, defaultdict
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
from m0046_semantic_pair_screening import compact_text, cosine, embed, representation, text_hash
from vocab_lexical_engine import evidence_set_hash, lookup
from vocab_synthesis import project_synthesis_evidence


ARTIFACT_BASE = Path.home() / ".local/share/vocab-app/benchmarks/m004.6.6"
MODEL = "nomic-embed-text:latest"
REPRESENTATION = {
    "version": "definition-focused-v1",
    "template": "{lemma} [{pos}]: {definitions joined by '; '}",
    "normalization": "Unicode NFC and deterministic whitespace collapse per definition",
}
THRESHOLD = 0.90
BANDS = (
    ("ge_0.94", 0.94, 1.01),
    ("0.90_0.94", 0.90, 0.94),
    ("0.86_0.90", 0.86, 0.90),
    ("0.80_0.86", 0.80, 0.86),
    ("lt_0.80", -1.0, 0.80),
)

# This is a diverse, deterministic inventory. Pair selection is performed
# after scoring and never uses a semantic label.
PARTITION_REQUESTS = [
    ("run", "verb"), ("set", "verb"), ("bank", "noun"), ("charge", "noun"),
    ("running", "adjective"), ("runner", "noun"), ("cleave", "verb"),
    ("quark", "noun"), ("light", "noun"), ("light", "adjective"),
    ("head", "noun"), ("field", "noun"), ("line", "noun"), ("point", "noun"),
    ("strike", "verb"), ("spring", "noun"), ("table", "noun"), ("fall", "verb"),
    ("break", "verb"), ("match", "noun"), ("scale", "noun"), ("seal", "noun"),
    ("bark", "noun"), ("right", "adjective"), ("fast", "adjective"),
]


def build_partitions(requests: list[tuple[str, str]]) -> list[dict[str, Any]]:
    partitions: list[dict[str, Any]] = []
    for word, wanted_pos in requests:
        evidence = project_synthesis_evidence(lookup(LEXICAL_DB, word))
        buckets: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
        for entry in evidence["entries"]:
            if entry["part_of_speech"] != wanted_pos:
                continue
            for sense in entry["senses"]:
                node = source_node(entry, sense)
                node["word"] = word
                buckets[material_partition(sense)].append(node)
        if not buckets:
            continue
        labels, nodes = max(buckets.items(), key=lambda item: (len(item[1]), tuple(item[0])))
        if len(nodes) < 2:
            continue
        nodes.sort(key=lambda node: node["source_sense_id"])
        partition_base = {
            "word": word,
            "pos": wanted_pos,
            "material_partition": list(labels),
            "source_nodes": nodes,
            "lexical_dataset_versions": evidence["wiktionary_versions"],
            "lexical_evidence_hash": evidence_set_hash(evidence),
        }
        partition = {
            **partition_base,
            "partition_id": f"{word}:{wanted_pos}:{canonical_hash(partition_base)[:12]}",
            "partition_hash": canonical_hash(partition_base),
        }
        partitions.append(partition)
    if not partitions:
        raise ValueError("No requested lexical partitions were available")
    return partitions


def pair_records(partitions: list[dict[str, Any]], identity: str) -> list[dict[str, Any]]:
    pairs = []
    for partition in partitions:
        for first, second in itertools.combinations(partition["source_nodes"], 2):
            pairs.append({
                "pair_id": f"{partition['partition_id']}:{canonical_hash([first['source_sense_id'], second['source_sense_id'], identity])[:16]}",
                "partition_id": partition["partition_id"],
                "word": partition["word"],
                "pos": partition["pos"],
                "material_partition": partition["material_partition"],
                "first": first,
                "second": second,
            })
    return pairs


def token_overlap(first: dict[str, Any], second: dict[str, Any]) -> float:
    def tokens(node: dict[str, Any]) -> set[str]:
        text = " ".join(node.get("definition", []))
        return {token.lower().strip(".,;:()[]{}\"'") for token in compact_text(text).split() if len(token) > 2}

    left, right = tokens(first), tokens(second)
    return len(left & right) / len(left | right) if left | right else 0.0


def band(score: float) -> str:
    for name, lower, upper in BANDS:
        if lower <= score < upper or (name == "ge_0.94" and score >= lower):
            return name
    raise AssertionError(score)


def select_pairs(pairs: list[dict[str, Any]], vectors: dict[str, list[float]], target: int = 200) -> list[dict[str, Any]]:
    scored = []
    for pair in pairs:
        score = cosine(vectors[pair["first"]["source_sense_id"]], vectors[pair["second"]["source_sense_id"]])
        overlap = token_overlap(pair["first"], pair["second"])
        scored.append({**pair, "similarity": score, "band": band(score), "definition_token_overlap": overlap})
    # Preserve every partition in the review set where possible, then fill
    # deterministic band quotas. Similarity is only a surfacing signal.
    selected: dict[str, dict[str, Any]] = {}
    covered_partitions: set[str] = set()
    for pair in sorted(scored, key=lambda item: (-item["similarity"], item["pair_id"])):
        if pair["partition_id"] not in covered_partitions:
            selected[pair["pair_id"]] = pair
            covered_partitions.add(pair["partition_id"])
            if len(selected) >= target:
                break
    quotas = {"ge_0.94": 45, "0.90_0.94": 45, "0.86_0.90": 45, "0.80_0.86": 35, "lt_0.80": 30}
    for current_band, quota in quotas.items():
        if len(selected) >= target:
            break
        candidates = [item for item in scored if item["band"] == current_band and item["pair_id"] not in selected]
        candidates.sort(key=lambda item: (-item["definition_token_overlap"], -item["similarity"], item["pair_id"]))
        for pair in candidates[:quota]:
            if len(selected) >= target:
                break
            selected[pair["pair_id"]] = pair
    if len(selected) < min(target, len(scored)):
        for pair in sorted(scored, key=lambda item: (-item["similarity"], item["pair_id"])):
            if len(selected) >= target:
                break
            selected.setdefault(pair["pair_id"], pair)
    result = list(selected.values())
    result.sort(key=lambda item: (item["word"], item["pos"], item["pair_id"]))
    by_partition: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for pair in result:
        by_partition[pair["partition_id"]].append(pair)
    plausible_ids: set[str] = set()
    for partition_pairs in by_partition.values():
        ranked = sorted(partition_pairs, key=lambda item: (-item["definition_token_overlap"], -item["similarity"], item["pair_id"]))
        for pair in ranked:
            if pair["similarity"] >= 0.86 or pair["definition_token_overlap"] >= 0.25:
                plausible_ids.add(pair["pair_id"])
            if len([item for item in ranked[:ranked.index(pair) + 1] if item["pair_id"] in plausible_ids]) >= 2:
                break
    # Keep the review set broad, while presenting a bounded pre-adjudication
    # surface of plausible merge candidates rather than calling every retained
    # pair a likely merge.
    plausible_ids = set(sorted(plausible_ids, key=lambda pair_id: next(
        (-item["similarity"], item["pair_id"]) for item in result if item["pair_id"] == pair_id
    ))[:50])
    for index, pair in enumerate(result, 1):
        pair["review_order"] = index
        pair["plausible_merge_candidate"] = pair["pair_id"] in plausible_ids
        pair["candidate_surface_reasons"] = [
            "partition_coverage" if pair["partition_id"] in {item["partition_id"] for item in result[:index - 1]} else "partition_representative",
            f"similarity_band:{pair['band']}",
        ]
        if pair["definition_token_overlap"] >= 0.25:
            pair["candidate_surface_reasons"].append("definition_vocabulary_overlap")
    return result


def write_csv(path: Path, pairs: list[dict[str, Any]]) -> None:
    def evidence_text(values: list[Any]) -> str:
        rendered = []
        for value in values:
            rendered.append(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True))
        return " | ".join(rendered)

    fields = [
        "pair_id", "review_order", "word", "pos", "material_labels",
        "source_sense_id_a", "definition_a", "labels_a", "examples_a",
        "source_sense_id_b", "definition_b", "labels_b", "examples_b",
        "decision", "review_notes",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for pair in pairs:
            first, second = pair["first"], pair["second"]
            writer.writerow({
                "pair_id": pair["pair_id"],
                "review_order": pair["review_order"],
                "word": pair["word"],
                "pos": pair["pos"],
                "material_labels": ";".join(pair["material_partition"]),
                "source_sense_id_a": first["source_sense_id"],
                "definition_a": evidence_text(first.get("definition", [])),
                "labels_a": ";".join(first.get("labels", [])),
                "examples_a": evidence_text(first.get("examples", [])),
                "source_sense_id_b": second["source_sense_id"],
                "definition_b": evidence_text(second.get("definition", [])),
                "labels_b": ";".join(second.get("labels", [])),
                "examples_b": evidence_text(second.get("examples", [])),
                "decision": "",
                "review_notes": "",
            })


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-pairs", type=int, default=200)
    args = parser.parse_args()
    started = utc_now()
    partitions = build_partitions(PARTITION_REQUESTS)
    model_meta = next(item for item in json.load(__import__("urllib.request").request.urlopen(f"{OLLAMA_URL}/api/tags"))["models"] if item["name"] == MODEL)
    embedding_identity = canonical_hash({"model": model_meta, "representation": REPRESENTATION})[:24]
    nodes = {node["source_sense_id"]: node for partition in partitions for node in partition["source_nodes"]}
    texts = {source_id: representation(node) for source_id, node in nodes.items()}
    vector_list, embed_meta = embed(MODEL, list(texts.values()))
    vectors = dict(zip(texts, vector_list))
    all_pairs = pair_records(partitions, embedding_identity)
    selected = select_pairs(all_pairs, vectors, args.target_pairs)
    run_id = started.replace("-", "").replace(":", "")
    root = ARTIFACT_BASE / run_id
    root.mkdir(parents=True)
    for pair in selected:
        pair["representation_hashes"] = [text_hash(texts[pair["first"]["source_sense_id"]]), text_hash(texts[pair["second"]["source_sense_id"]])]
    candidate_payload = {
        "benchmark_id": "m004.6.6-expanded-semantic-screening-reference-validation",
        "phase": "A",
        "reference_version": "reference-candidates-v1",
        "run_id": run_id,
        "created_at": started,
        "git_head": git_head(),
        "embedding_model": model_meta,
        "embedding_identity": embedding_identity,
        "representation": REPRESENTATION,
        "threshold_for_technical_screening_only": THRESHOLD,
        "source_partitions": partitions,
        "candidate_pairs": selected,
        "review_status": "awaiting_product_owner_architect_adjudication",
    }
    (root / "reference_candidates_v1.json").write_text(json.dumps(candidate_payload, indent=2, sort_keys=True), encoding="utf-8")
    (root / "source_sense_representations.json").write_text(
        json.dumps({key: {"text": value, "hash": text_hash(value)} for key, value in texts.items()}, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    technical = {
        "run_id": run_id,
        "embedding_model": model_meta,
        "embedding_identity": embedding_identity,
        "representation": REPRESENTATION,
        "threshold": THRESHOLD,
        "pair_scores": [{
            "pair_id": pair["pair_id"], "partition_id": pair["partition_id"], "word": pair["word"],
            "pos": pair["pos"], "similarity": pair["similarity"], "band": pair["band"],
            "definition_token_overlap": pair["definition_token_overlap"],
            "representation_hashes": pair["representation_hashes"],
            "technical_screening_outcome": "retained_at_0.90" if pair["similarity"] >= THRESHOLD else "screened_at_0.90",
        } for pair in selected],
        "embedding_response_metadata": {key: value for key, value in embed_meta.items() if key != "embeddings"},
    }
    (root / "screening_scores_technical.json").write_text(json.dumps(technical, indent=2, sort_keys=True), encoding="utf-8")
    write_csv(root / "reference_review_blinded.csv", selected)
    inventory = [{
        "word": partition["word"], "pos": partition["pos"], "material_partition": partition["material_partition"],
        "partition_id": partition["partition_id"], "source_sense_count": len(partition["source_nodes"]),
        "complete_eligible_pair_count": len(partition["source_nodes"]) * (len(partition["source_nodes"]) - 1) // 2,
        "review_pair_count": sum(item["partition_id"] == partition["partition_id"] for item in selected),
    } for partition in partitions]
    (root / "selected_partition_inventory.json").write_text(json.dumps(inventory, indent=2, sort_keys=True), encoding="utf-8")
    accounting = []
    for partition in partitions:
        partition_pairs = [pair for pair in all_pairs if pair["partition_id"] == partition["partition_id"]]
        scores = [cosine(vectors[pair["first"]["source_sense_id"]], vectors[pair["second"]["source_sense_id"]]) for pair in partition_pairs]
        accounting.append({
            "partition_id": partition["partition_id"], "word": partition["word"], "pos": partition["pos"],
            "source_sense_count": len(partition["source_nodes"]), "complete_eligible_pair_count": len(scores),
            "similarity_min": min(scores), "similarity_median": sorted(scores)[len(scores) // 2], "similarity_max": max(scores),
            "threshold_0_90_retained_pair_count": sum(score >= THRESHOLD for score in scores),
            "threshold_0_90_reduction_percentage": (1 - sum(score >= THRESHOLD for score in scores) / len(scores)) * 100,
            "semantic_correctness_claim": "none; unlabeled workload projection",
        })
    (root / "complete_partition_accounting.json").write_text(json.dumps(accounting, indent=2, sort_keys=True), encoding="utf-8")
    summary = {
        "benchmark_id": candidate_payload["benchmark_id"], "phase": "A", "run_id": run_id,
        "status": "PARTIAL — Phase A expanded reference constructed; Product Owner / Architect semantic adjudication pending.",
        "selected_partition_count": len(partitions), "source_sense_count": len(nodes),
        "complete_pair_count": len(all_pairs), "review_pair_count": len(selected),
        "review_band_counts": dict(Counter(pair["band"] for pair in selected)),
        "plausible_merge_surface_count": sum(pair["plausible_merge_candidate"] for pair in selected),
        "artifacts": {
            "candidate_reference": str(root / "reference_candidates_v1.json"),
            "blinded_review": str(root / "reference_review_blinded.csv"),
            "technical_scores": str(root / "screening_scores_technical.json"),
            "partition_inventory": str(root / "selected_partition_inventory.json"),
            "complete_partition_accounting": str(root / "complete_partition_accounting.json"),
        },
        "phase_b_not_run": True,
        "semantic_labels_assigned": False,
    }
    (root / "phase_a_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
