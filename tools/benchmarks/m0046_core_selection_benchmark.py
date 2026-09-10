"""Narrow, isolated Tier 1 core-selection benchmark utilities and runner."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vocab_lexical_engine import canonical_json, evidence_set_hash, lookup
from vocab_synthesis import core_selection_schema, project_synthesis_evidence, response_content, strict_json_object

OLLAMA_URL = "http://127.0.0.1:11434"
LEXICAL_DB = Path.home() / ".local/share/vocab-lexical/versions/wiktionary-20260901/lexical.sqlite"
ARTIFACT_BASE = Path.home() / ".local/share/vocab-app/benchmarks/m004.6.2"
MODEL_POLICIES = {
    "gpt-oss:20b": {"think": "low", "options": {"temperature": 0, "num_predict": 3200, "num_ctx": 16384}},
    "qwen3:8b": {"think": False, "options": {"temperature": 0, "num_predict": 256, "num_ctx": 16384}},
}
CONFIG_LABELS = {
    ("gpt-oss:20b", "subset-array-v1"): "Config A",
    ("gpt-oss:20b", "fixed-key-v1"): "Config B",
    ("qwen3:8b", "subset-array-v1"): "Config C",
    ("qwen3:8b", "fixed-key-v1"): "Config D",
}


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def git_head() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=True).stdout.strip()


def load_manifest(path: Path) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "benchmark_id", "benchmark_version", "tier", "intended_words", "fixture_generation",
        "models", "contracts", "seed_sequence", "attempts_per_configuration", "artifact_root",
    }
    missing = required - set(manifest)
    if missing:
        raise ValueError(f"Manifest missing fields: {sorted(missing)}")
    if manifest["attempts_per_configuration"] != len(manifest["seed_sequence"]):
        raise ValueError("attempts_per_configuration must equal the seed sequence length")
    if set(manifest["models"]) != set(MODEL_POLICIES):
        raise ValueError("Manifest model set must match the approved benchmark policies")
    if set(manifest["contracts"]) != {"subset-array-v1", "fixed-key-v1"}:
        raise ValueError("Manifest must use only the two approved contracts")
    return manifest


def subset_diagnostics(parsed: Any, allowed_ids: list[str]) -> dict[str, bool]:
    result = {
        "parse_success": parsed is not None,
        "exact_top_level_keys": False,
        "core_group_ids_is_array": False,
        "all_ids_are_strings": False,
        "all_ids_in_allowed_set": False,
        "ids_are_unique": False,
        "count_within_limit": False,
    }
    if not isinstance(parsed, dict):
        return result
    result["exact_top_level_keys"] = set(parsed) == {"core_group_ids"}
    ids = parsed.get("core_group_ids")
    if not isinstance(ids, list):
        return result
    result["core_group_ids_is_array"] = True
    result["all_ids_are_strings"] = all(isinstance(value, str) for value in ids)
    result["all_ids_in_allowed_set"] = result["all_ids_are_strings"] and set(ids) <= set(allowed_ids)
    result["ids_are_unique"] = len(ids) == len(set(ids))
    result["count_within_limit"] = len(ids) <= 5
    return result


def fixed_key_schema(group_ids: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "core_count": {"type": "integer", "minimum": 1, "maximum": min(5, len(group_ids))},
            "scores": {
                "type": "object",
                "additionalProperties": False,
                "properties": {group_id: {"type": "integer", "minimum": 0, "maximum": 5} for group_id in group_ids},
                "required": group_ids,
            },
        },
        "required": ["core_count", "scores"],
    }


def fixed_key_diagnostics(parsed: Any, group_ids: list[str]) -> dict[str, bool]:
    result = {
        "parse_success": parsed is not None,
        "exact_top_level_keys": False,
        "core_count_valid": False,
        "scores_is_object": False,
        "all_expected_score_keys_present": False,
        "no_unknown_score_keys": False,
        "all_scores_are_valid_ints": False,
        "deterministic_assembly_success": False,
    }
    if not isinstance(parsed, dict):
        return result
    result["exact_top_level_keys"] = set(parsed) == {"core_count", "scores"}
    core_count = parsed.get("core_count")
    result["core_count_valid"] = isinstance(core_count, int) and not isinstance(core_count, bool) and 1 <= core_count <= min(5, len(group_ids))
    scores = parsed.get("scores")
    if not isinstance(scores, dict):
        return result
    result["scores_is_object"] = True
    result["all_expected_score_keys_present"] = set(group_ids) <= set(scores)
    result["no_unknown_score_keys"] = set(scores) <= set(group_ids)
    result["all_scores_are_valid_ints"] = all(
        isinstance(scores.get(group_id), int) and not isinstance(scores.get(group_id), bool) and 0 <= scores[group_id] <= 5
        for group_id in group_ids
    )
    result["deterministic_assembly_success"] = all(result[name] for name in (
        "exact_top_level_keys", "core_count_valid", "scores_is_object", "all_expected_score_keys_present",
        "no_unknown_score_keys", "all_scores_are_valid_ints",
    ))
    return result


def fixed_key_assembly(parsed: Any, group_ids: list[str]) -> dict[str, Any]:
    diagnostics = fixed_key_diagnostics(parsed, group_ids)
    if not diagnostics["deterministic_assembly_success"]:
        return {"state": "rejected", "selected_final_ids": [], "diagnostics": diagnostics}
    selected = [
        group_id for group_id, _ in sorted(parsed["scores"].items(), key=lambda item: (-item[1], item[0]))[:parsed["core_count"]]
    ]
    return {"state": "assembled", "selected_final_ids": selected, "diagnostics": diagnostics}


def word_categories(word: str, pos_count: int) -> list[str]:
    categories = {
        "running": ["inflected"], "runner": ["inflected"], "run": ["highly-polysemous"],
        "set": ["highly-polysemous"], "bank": ["highly-polysemous", "semantic-boundary"],
        "charge": ["highly-polysemous"], "mouse": ["technical"], "quark": ["technical"],
        "justice": ["abstract"], "utilitarian": ["abstract"], "awful": ["register-sensitive"],
        "literally": ["register-sensitive"], "cleave": ["contronym", "semantic-boundary"],
        "wicked": ["register-sensitive"], "phone": ["simple"], "archipelago": ["simple"],
        "meander": ["simple"], "happiness": ["abstract"],
    }
    result = list(categories.get(word, ["simple"]))
    if pos_count > 1:
        result.append("multi-pos")
    return sorted(set(result))


def build_fixtures(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    policy = manifest["fixture_generation"]
    fixtures = []
    for word in manifest["intended_words"]:
        evidence = project_synthesis_evidence(lookup(LEXICAL_DB, word))
        by_pos: dict[str, list[str]] = {}
        for entry in evidence.get("entries", []):
            by_pos.setdefault(entry["part_of_speech"], [])
            by_pos[entry["part_of_speech"]].extend(
                sense["glosses"][0] for sense in entry["senses"] if sense.get("glosses")
            )
        populated = {pos: list(dict.fromkeys(glosses))[:policy["maximum_candidates"]] for pos, glosses in by_pos.items()}
        material = {pos: glosses for pos, glosses in populated.items() if len(glosses) >= policy["minimum_unique_glosses"]}
        for pos, glosses in sorted(material.items()):
            group_ids = [f"G{index:03d}" for index in range(1, len(glosses) + 1)]
            fixture = {
                "source_word": word,
                "normalized_lemma": evidence["normalized_lemma"],
                "pos": pos,
                "lexical_dataset_versions": evidence["wiktionary_versions"],
                "lexical_evidence_hash": evidence_set_hash(evidence),
                "fixture_construction_method": "benchmark-reconstructed",
                "fixture_construction_policy": policy["version"],
                "candidate_group_ids": group_ids,
                "candidate_groups": [{"group_id": group_id, "definition": gloss} for group_id, gloss in zip(group_ids, glosses)],
                "categories": word_categories(word, len(material)),
            }
            fixture["fixture_id"] = f"{word}:{pos}:{canonical_hash(fixture)[:12]}"
            fixture["fixture_hash"] = canonical_hash(fixture)
            fixtures.append(fixture)
    return fixtures


def subset_prompt(fixture: dict[str, Any]) -> str:
    return canonical_json({
        "task": "Return exactly one JSON object matching the supplied schema.",
        "pos": fixture["pos"],
        "instruction": "Select up to five core learner meanings from the supplied code-owned group IDs. Do not invent IDs or add keys.",
        "groups": fixture["candidate_groups"],
    })


def fixed_key_prompt(fixture: dict[str, Any]) -> str:
    return canonical_json({
        "task": "Return exactly one JSON object matching the supplied schema.",
        "pos": fixture["pos"],
        "instruction": "Score every supplied code-owned group from 0 to 5 and select core_count from 1 through five. Do not omit a score or add keys.",
        "groups": fixture["candidate_groups"],
    })


def installed_digest(model: str) -> str:
    response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=30).json()
    for item in response["models"]:
        if item["name"] == model:
            return str(item["digest"])
    raise RuntimeError(f"Required installed model is not available: {model}")


def invoke(
    *, benchmark_id: str, benchmark_version: int, run: str, fixture: dict[str, Any], model: str,
    contract: str, seed: int, warm: bool,
) -> dict[str, Any]:
    policy = MODEL_POLICIES[model]
    schema = core_selection_schema(fixture["candidate_group_ids"]) if contract == "subset-array-v1" else fixed_key_schema(fixture["candidate_group_ids"])
    prompt = subset_prompt(fixture) if contract == "subset-array-v1" else fixed_key_prompt(fixture)
    record: dict[str, Any] = {
        "attempt_id": f"{run}:{fixture['fixture_id']}:{model}:{contract}:{seed}",
        "benchmark_id": benchmark_id, "benchmark_version": benchmark_version, "benchmark_tier": 1,
        "run_id": run, "timestamp": utc_now(), "git_head": git_head(), "model": model,
        "model_digest": installed_digest(model),
        "ollama_version": requests.get(f"{OLLAMA_URL}/api/version", timeout=10).json()["version"],
        "invocation": {"think": policy["think"], "options": {**policy["options"], "seed": seed}},
        "contract_id": contract, "fixture_id": fixture["fixture_id"], "fixture_hash": fixture["fixture_hash"],
        "lexical_dataset_versions": fixture["lexical_dataset_versions"], "lexical_evidence_hash": fixture["lexical_evidence_hash"],
        "prompt_hash": canonical_hash(prompt), "schema_hash": canonical_hash(schema), "seed": seed,
        "cold_warm": "warm" if warm else "cold", "provider_status": None, "done_reason": None,
        "raw_provider_response": None, "raw_content": None, "parsed": None, "parse_error": None,
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
    record["diagnostics"] = (
        subset_diagnostics(record["parsed"], fixture["candidate_group_ids"])
        if contract == "subset-array-v1" else fixed_key_diagnostics(record["parsed"], fixture["candidate_group_ids"])
    )
    record["assembly"] = (
        {"state": "not_applicable", "selected_final_ids": record["parsed"].get("core_group_ids", []) if isinstance(record["parsed"], dict) else []}
        if contract == "subset-array-v1" else fixed_key_assembly(record["parsed"], fixture["candidate_group_ids"])
    )
    return record


def stability(records: list[dict[str, Any]]) -> dict[str, Any]:
    selected = [frozenset(record["assembly"]["selected_final_ids"]) for record in records if record["assembly"]["state"] != "rejected"]
    if not selected:
        return {"valid_attempts": 0, "distinct_final_sets": 0, "all_five_agree": False, "mean_pairwise_jaccard": None}
    similarities = []
    for index, first in enumerate(selected):
        for second in selected[index + 1:]:
            union = set(first) | set(second)
            similarities.append(len(set(first) & set(second)) / len(union) if union else 1.0)
    return {
        "valid_attempts": len(selected), "distinct_final_sets": len(set(selected)),
        "all_five_agree": len(selected) == 5 and len(set(selected)) == 1,
        "mean_pairwise_jaccard": sum(similarities) / len(similarities) if similarities else 1.0,
    }


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")


def review_artifacts(root: Path, fixtures: list[dict[str, Any]], records: list[dict[str, Any]]) -> None:
    fixture_by_id = {fixture["fixture_id"]: fixture for fixture in fixtures}
    fields = [
        "attempt_id", "fixture_id", "word", "pos", "categories", "provenance_type", "config_label", "seed",
        "candidate_groups_json", "selected_final_ids_json", "scores_json", "structural_valid", "provider_status",
        "done_reason", "total_latency_seconds", "coverage_score", "precision_score", "preservation_score", "overall", "review_notes",
    ]
    with (root / "semantic_review.csv").open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        for record in sorted(records, key=lambda item: (item["fixture_id"], CONFIG_LABELS[(item["model"], item["contract_id"])], item["seed"])):
            fixture = fixture_by_id[record["fixture_id"]]
            response = record["raw_provider_response"] or {}
            scores = record["parsed"].get("scores", {}) if isinstance(record["parsed"], dict) else {}
            writer.writerow({
                "attempt_id": record["attempt_id"], "fixture_id": record["fixture_id"], "word": fixture["source_word"],
                "pos": fixture["pos"], "categories": "|".join(fixture["categories"]), "provenance_type": fixture["fixture_construction_method"],
                "config_label": CONFIG_LABELS[(record["model"], record["contract_id"])], "seed": record["seed"],
                "candidate_groups_json": canonical_json(fixture["candidate_groups"]),
                "selected_final_ids_json": canonical_json(record["assembly"]["selected_final_ids"]),
                "scores_json": canonical_json(scores), "structural_valid": all(record["diagnostics"].values()),
                "provider_status": record["provider_status"], "done_reason": record["done_reason"],
                "total_latency_seconds": (response.get("total_duration") or 0) / 1_000_000_000,
                "coverage_score": "", "precision_score": "", "preservation_score": "", "overall": "", "review_notes": "",
            })
    write_json(root / "semantic_review_config_mapping.json", {
        label: {"model": model, "contract": contract} for (model, contract), label in CONFIG_LABELS.items()
    })


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {"by_model_contract": {}, "stability": {}}
    for model in MODEL_POLICIES:
        for contract in ("subset-array-v1", "fixed-key-v1"):
            subset = [record for record in records if record["model"] == model and record["contract_id"] == contract]
            durations = [(record["raw_provider_response"] or {}).get("total_duration", 0) / 1_000_000_000 for record in subset]
            prompt_durations = [(record["raw_provider_response"] or {}).get("prompt_eval_duration", 0) / 1_000_000_000 for record in subset]
            eval_durations = [(record["raw_provider_response"] or {}).get("eval_duration", 0) / 1_000_000_000 for record in subset]
            load_durations = [(record["raw_provider_response"] or {}).get("load_duration", 0) / 1_000_000_000 for record in subset]
            result["by_model_contract"][f"{model}:{contract}"] = {
                "attempts": len(subset), "structurally_valid": sum(all(record["diagnostics"].values()) for record in subset),
                "provider_failures": sum(record["provider_status"] != "provider_success" for record in subset),
                "p50_total_seconds": statistics.median(durations) if durations else None,
                "p95_total_seconds": sorted(durations)[round((len(durations) - 1) * 0.95)] if durations else None,
                "min_total_seconds": min(durations) if durations else None,
                "max_total_seconds": max(durations) if durations else None,
                "p50_prompt_eval_seconds": statistics.median(prompt_durations) if prompt_durations else None,
                "p50_eval_seconds": statistics.median(eval_durations) if eval_durations else None,
                "generated_tokens_p50": statistics.median([(record["raw_provider_response"] or {}).get("eval_count", 0) for record in subset]) if subset else None,
                "max_load_seconds": max(load_durations) if load_durations else None,
                "load_over_one_second": sum(duration > 1 for duration in load_durations),
            }
            for fixture_id in sorted({record["fixture_id"] for record in subset}):
                result["stability"][f"{fixture_id}:{model}:{contract}"] = stability([record for record in subset if record["fixture_id"] == fixture_id])
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=Path(__file__).parent / "manifests/m004.6.2_tier1.json")
    parser.add_argument("--fixtures-only", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    arguments = parser.parse_args()
    manifest = load_manifest(arguments.manifest)
    fixtures = build_fixtures(manifest)
    if len(fixtures) > 40:
        raise RuntimeError(f"Fixture gate exceeded: {len(fixtures)} POS-local fixtures")
    if arguments.fixtures_only:
        print(json.dumps({"fixture_count": len(fixtures), "fixtures": fixtures}, indent=2))
        return 0
    run = run_id()
    root = ARTIFACT_BASE / run
    root.mkdir(parents=True)
    write_json(root / "manifest.json", manifest)
    write_json(root / "fixtures.json", fixtures)
    combinations = [(model, contract) for model in manifest["models"] for contract in manifest["contracts"]]
    if arguments.smoke:
        combinations = combinations
        fixtures = fixtures[:1]
        seeds = manifest["seed_sequence"][:1]
    else:
        seeds = manifest["seed_sequence"]
    records = []
    warm_by_model = {model: False for model in manifest["models"]}
    for fixture in fixtures:
        for model, contract in combinations:
            for seed in seeds:
                record = invoke(benchmark_id=manifest["benchmark_id"], benchmark_version=manifest["benchmark_version"],
                                run=run, fixture=fixture, model=model, contract=contract, seed=seed, warm=warm_by_model[model])
                records.append(record)
                warm_by_model[model] = True
    write_json(root / "attempts.json", records)
    write_json(root / "summary.json", summarize(records))
    review_artifacts(root, fixtures, records)
    print(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
