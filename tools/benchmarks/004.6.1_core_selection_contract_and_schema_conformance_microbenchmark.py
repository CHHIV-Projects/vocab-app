#!/usr/bin/env python3
"""Isolated M004.6.1 core-selection contract benchmark."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vocab_lexical_engine import canonical_json, lookup
from vocab_synthesis import core_selection_schema, project_synthesis_evidence, response_content, strict_json_object

ARTIFACT_BASE = Path.home() / ".local" / "share" / "vocab-app" / "benchmarks" / "m004.6.1"
LEXICAL_DB = Path.home() / ".local" / "share" / "vocab-lexical" / "versions" / "wiktionary-20260901" / "lexical.sqlite"
MODELS = ("gpt-oss:20b", "qwen3:8b")
MODEL_OPTIONS = {
    "gpt-oss:20b": {"think": "low", "options": {"temperature": 0, "num_predict": 3200, "num_ctx": 16384}},
    # Qwen consumes the output budget with reasoning in "low" mode; this is benchmark-local.
    "qwen3:8b": {"think": False, "options": {"temperature": 0, "num_predict": 256, "num_ctx": 16384}},
}


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def git_output(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def subset_diagnostics(parsed: Any, allowed_ids: list[str]) -> dict[str, bool]:
    diagnostics = {
        "parse_success": parsed is not None,
        "exact_top_level_keys": False,
        "core_group_ids_is_array": False,
        "all_ids_are_strings": False,
        "all_ids_in_allowed_set": False,
        "ids_are_unique": False,
        "count_within_limit": False,
    }
    if not isinstance(parsed, dict):
        return diagnostics
    diagnostics["exact_top_level_keys"] = set(parsed) == {"core_group_ids"}
    ids = parsed.get("core_group_ids")
    if not isinstance(ids, list):
        return diagnostics
    diagnostics["core_group_ids_is_array"] = True
    diagnostics["all_ids_are_strings"] = all(isinstance(value, str) for value in ids)
    diagnostics["all_ids_in_allowed_set"] = diagnostics["all_ids_are_strings"] and set(ids) <= set(allowed_ids)
    diagnostics["ids_are_unique"] = len(ids) == len(set(ids))
    diagnostics["count_within_limit"] = len(ids) <= 5
    return diagnostics


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
    diagnostics = {
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
        return diagnostics
    diagnostics["exact_top_level_keys"] = set(parsed) == {"core_count", "scores"}
    core_count = parsed.get("core_count")
    diagnostics["core_count_valid"] = isinstance(core_count, int) and not isinstance(core_count, bool) and 1 <= core_count <= min(5, len(group_ids))
    scores = parsed.get("scores")
    if not isinstance(scores, dict):
        return diagnostics
    diagnostics["scores_is_object"] = True
    diagnostics["all_expected_score_keys_present"] = set(group_ids) <= set(scores)
    diagnostics["no_unknown_score_keys"] = set(scores) <= set(group_ids)
    diagnostics["all_scores_are_valid_ints"] = all(
        isinstance(scores.get(group_id), int) and not isinstance(scores.get(group_id), bool) and 0 <= scores[group_id] <= 5
        for group_id in group_ids
    )
    diagnostics["deterministic_assembly_success"] = all(diagnostics[name] for name in (
        "exact_top_level_keys", "core_count_valid", "scores_is_object", "all_expected_score_keys_present",
        "no_unknown_score_keys", "all_scores_are_valid_ints",
    ))
    return diagnostics


def fixed_key_assembly(parsed: Any, group_ids: list[str]) -> dict[str, Any]:
    diagnostics = fixed_key_diagnostics(parsed, group_ids)
    if not diagnostics["deterministic_assembly_success"]:
        return {"state": "rejected", "selected_final_ids": [], "diagnostics": diagnostics}
    scores = parsed["scores"]
    selected = [
        group_id for group_id, _ in sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:parsed["core_count"]]
    ]
    return {"state": "assembled", "selected_final_ids": selected, "diagnostics": diagnostics}


def artifact_record(
    *, benchmark_run_id: str, model: str, model_digest: str, fixture_id: str, contract_id: str,
    schema: dict[str, Any], prompt: str, seed: int, warm_before: bool,
) -> dict[str, Any]:
    settings = MODEL_OPTIONS[model]
    record: dict[str, Any] = {
        "run_id": benchmark_run_id,
        "timestamp": now(),
        "git_head": git_output("rev-parse", "HEAD"),
        "model": model,
        "model_digest": model_digest,
        "ollama_version": requests.get("http://127.0.0.1:11434/api/version", timeout=10).json()["version"],
        "contract_id": contract_id,
        "fixture_id": fixture_id,
        "schema_hash": canonical_hash(schema),
        "prompt_hash": canonical_hash(prompt),
        "seed": seed,
        "options": settings["options"],
        "think": settings["think"],
        "cold_warm": "warm" if warm_before else "cold",
        "provider_status": None,
        "raw_provider_response": None,
        "raw_content": None,
        "parse_error": None,
        "parsed": None,
        "diagnostics": None,
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "format": schema,
        "think": settings["think"],
        "keep_alive": "5m",
        "options": {**settings["options"], "seed": seed},
    }
    try:
        response = requests.post("http://127.0.0.1:11434/api/chat", json=payload, timeout=240)
        response.raise_for_status()
        provider = response.json()
        record["raw_provider_response"] = provider
        record["done_reason"] = provider.get("done_reason")
        content = response_content(provider)
        record["raw_content"] = content
        if provider.get("done_reason") == "length":
            record["provider_status"] = "done_reason_length"
        elif not content:
            record["provider_status"] = "empty_content"
        else:
            record["provider_status"] = "provider_success"
        try:
            record["parsed"] = strict_json_object(content)
        except Exception as error:
            record["parse_error"] = str(error)
            if record["provider_status"] == "provider_success":
                record["provider_status"] = "json_parse_failure"
    except requests.Timeout as error:
        record["provider_status"] = "timeout"
        record["provider_error"] = str(error)
    except requests.RequestException as error:
        record["provider_status"] = "transport_failure"
        record["provider_error"] = str(error)
    return record


def fixtures() -> list[dict[str, Any]]:
    result = []
    for word in ("archipelago", "run", "set", "phone", "runner", "meander", "happiness", "utilitarian"):
        evidence = project_synthesis_evidence(lookup(LEXICAL_DB, word))
        entries = evidence.get("entries", [])
        if not entries:
            continue
        pos = entries[0]["part_of_speech"]
        definitions = []
        for entry in entries:
            if entry["part_of_speech"] == pos:
                definitions.extend(sense["glosses"][0] for sense in entry["senses"] if sense.get("glosses"))
        definitions = list(dict.fromkeys(definitions))[:6]
        ids = [f"G{index:03d}" for index in range(1, len(definitions) + 1)]
        result.append({
            "fixture_id": f"reconstructed_{word}_{pos}",
            "word": word,
            "pos": pos,
            "allowed_group_ids": ids,
            "groups": [{"group_id": group_id, "definition": definition} for group_id, definition in zip(ids, definitions)],
        })
    return result


def subset_prompt(fixture: dict[str, Any], case: str | None = None) -> str:
    payload: dict[str, Any] = {
        "task": "Return exactly one JSON object matching the supplied schema.",
        "pos": fixture["pos"],
        "instruction": "Select up to five core learner groups using only the supplied code-owned IDs. Do not include any other keys.",
        "groups": fixture["groups"],
    }
    if case:
        payload["conformance_probe"] = case
        payload["attempted_invalid_result"] = {
            "unknown_id": {"core_group_ids": ["G999"]},
            "too_many_items": {"core_group_ids": ["G001", "G002", "G003", "G004", "G005", "G006"]},
            "wrong_top_level_property": {"other_ids": ["G001"]},
            "wrong_value_type": {"core_group_ids": "G001"},
            "duplicate_valid_id": {"core_group_ids": ["G001", "G001"]},
        }[case]
    return canonical_json(payload)


def fixed_prompt(fixture: dict[str, Any]) -> str:
    return canonical_json({
        "task": "Return exactly one JSON object matching the supplied schema.",
        "pos": fixture["pos"],
        "instruction": "Score every code-owned group from 0 to 5 and choose a core_count from 1 through five. Do not omit a score and do not include other keys.",
        "groups": fixture["groups"],
    })


def write_records(path: Path, records: list[dict[str, Any]]) -> None:
    path.write_text(json.dumps(records, indent=2, sort_keys=True), encoding="utf-8")


def model_digest(model: str) -> str:
    models = requests.get("http://127.0.0.1:11434/api/tags", timeout=60).json()["models"]
    for installed in models:
        if installed.get("name") == model:
            return str(installed["digest"])
    raise RuntimeError(f"Installed Ollama model was not found: {model}")


def main() -> int:
    benchmark_run_id = run_id()
    root = ARTIFACT_BASE / benchmark_run_id
    root.mkdir(parents=True)
    all_fixtures = fixtures()
    (root / "fixtures.json").write_text(json.dumps(all_fixtures, indent=2, sort_keys=True), encoding="utf-8")
    manifest = {"run_id": benchmark_run_id, "created_at": now(), "git_head": git_output("rev-parse", "HEAD"),
                "fixture_provenance": "benchmark-derived reconstructed POS-local lexical fixtures, not retained production grouping artifacts",
                "models": {model: {"digest": model_digest(model), "settings": MODEL_OPTIONS[model]} for model in MODELS}}
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    conformance_fixture = {"fixture_id": "synthetic_schema_conformance", "pos": "noun",
                           "groups": [{"group_id": f"G{index:03d}", "definition": f"synthetic meaning {index}"} for index in range(1, 7)],
                           "allowed_group_ids": [f"G{index:03d}" for index in range(1, 7)]}
    cases = ("unknown_id", "too_many_items", "wrong_top_level_property", "wrong_value_type", "duplicate_valid_id")
    for model in MODELS:
        digest = manifest["models"][model]["digest"]
        phase_a, phase_b, phase_c = [], [], []
        warm = False
        for case in cases:
            schema = core_selection_schema(conformance_fixture["allowed_group_ids"])
            prompt = subset_prompt(conformance_fixture, case)
            for offset in range(5):
                record = artifact_record(benchmark_run_id=benchmark_run_id, model=model, model_digest=digest, fixture_id=f"phase_a_{case}",
                                         contract_id="subset-array-v1", schema=schema, prompt=prompt, seed=1000 + offset, warm_before=warm)
                record["allowed_group_ids"] = conformance_fixture["allowed_group_ids"]
                record["diagnostics"] = subset_diagnostics(record["parsed"], conformance_fixture["allowed_group_ids"])
                phase_a.append(record)
                warm = True
        for fixture in all_fixtures:
            schema, prompt = fixed_key_schema(fixture["allowed_group_ids"]), fixed_prompt(fixture)
            for offset in range(5):
                record = artifact_record(benchmark_run_id=benchmark_run_id, model=model, model_digest=digest, fixture_id=fixture["fixture_id"],
                                         contract_id="fixed-key-v1", schema=schema, prompt=prompt, seed=2000 + offset, warm_before=warm)
                record["allowed_group_ids"] = fixture["allowed_group_ids"]
                record["diagnostics"] = fixed_key_diagnostics(record["parsed"], fixture["allowed_group_ids"])
                record["assembly"] = fixed_key_assembly(record["parsed"], fixture["allowed_group_ids"])
                phase_b.append(record)
        for fixture in all_fixtures:
            for contract, schema, prompt in (
                ("subset-array-v1", core_selection_schema(fixture["allowed_group_ids"]), subset_prompt(fixture)),
                ("fixed-key-v1", fixed_key_schema(fixture["allowed_group_ids"]), fixed_prompt(fixture)),
            ):
                for offset in range(5):
                    record = artifact_record(benchmark_run_id=benchmark_run_id, model=model, model_digest=digest, fixture_id=fixture["fixture_id"],
                                             contract_id=contract, schema=schema, prompt=prompt, seed=3000 + offset, warm_before=warm)
                    record["allowed_group_ids"] = fixture["allowed_group_ids"]
                    record["diagnostics"] = (subset_diagnostics(record["parsed"], fixture["allowed_group_ids"])
                                             if contract == "subset-array-v1" else fixed_key_diagnostics(record["parsed"], fixture["allowed_group_ids"]))
                    if contract == "fixed-key-v1":
                        record["assembly"] = fixed_key_assembly(record["parsed"], fixture["allowed_group_ids"])
                    phase_c.append(record)
        output = root / model.replace(":", "_")
        output.mkdir()
        write_records(output / "phase_a.json", phase_a)
        write_records(output / "phase_b.json", phase_b)
        write_records(output / "phase_c.json", phase_c)
    print(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
