"""Isolated M002.002 pilot; production synthesis contracts remain unchanged."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import time
from collections import Counter
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

import requests

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import vocab_synthesis as synthesis
from vocab_lexical_engine import canonical_json, evidence_set_hash, lookup, resolve_active_database

CORPUS = ROOT / "docs/milestones/M002.002_learner_product_trial_local_ai_utility_evaluation_corpus.csv"
CORPUS_HASH = "fcab3f780b4f0cb5f0e9c33ade3039ac544390323a24282bae5593edabc3620a"
MODEL = "gpt-oss:20b"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def public_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: public_payload(item) for key, item in value.items()
                if key not in {"thinking", "message_thinking", "message_thinking_truncated"}}
    if isinstance(value, list):
        return [public_payload(item) for item in value]
    return value


def write_json(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(public_payload(value), stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write("\n")


def pilot_rows() -> list[dict[str, str]]:
    if hashlib.sha256(CORPUS.read_bytes()).hexdigest() != CORPUS_HASH:
        raise ValueError("Approved corpus identity changed")
    with CORPUS.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 60 or len({row["normalized_lemma"] for row in rows}) != 60:
        raise ValueError("Expected 60 unique approved corpus words")
    queues = {name: [row for row in rows if row["stratum"] == name and row["pilot"] == "yes"]
              for name in ("normal", "complexity", "challenge")}
    if {name: len(queue) for name, queue in queues.items()} != {"normal": 10, "complexity": 6, "challenge": 4}:
        raise ValueError("Approved 20-word pilot split changed")
    ordered = []
    while any(queues.values()):
        for queue in queues.values():
            if queue:
                ordered.append(queue.pop(0))
    return ordered


def prepare(run: Path, database: Path) -> dict[str, Any]:
    frozen = run / "evidence"
    frozen.mkdir()
    records = []
    for row in pilot_rows():
        start = time.perf_counter()
        evidence = synthesis.project_synthesis_evidence(lookup(database, row["normalized_lemma"]))
        counts: Counter[str] = Counter()
        for entry in evidence["entries"]:
            counts[entry["part_of_speech"]] += len(entry["senses"])
        expected = {pair.split("=")[0]: int(pair.split("=")[1])
                    for pair in row["source_senses_by_pos"].split(";")}
        if dict(counts) != expected:
            raise ValueError(f"Approved lexical inventory changed: {row['normalized_lemma']}")
        identity = evidence_set_hash(evidence)
        write_json(frozen / f"{row['normalized_lemma']}.json", evidence)
        records.append(dict(row, evidence_set_hash=identity,
                            evidence_preparation_seconds=time.perf_counter() - start))
    manifest = {
        "created_at": utc_now(), "corpus_sha256": CORPUS_HASH,
        "source_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                          for name in ("vocab_synthesis.py", "vocab_lexical_engine.py",
                                       "tools/benchmarks/m002002_product_trial.py")},
        "model": MODEL, "seed": None, "pilot_only": True,
        "identities": {
            name: getattr(synthesis, name) for name in
            ("PROMPT_VERSION", "POLICY_VERSION", "SYNTHESIS_SCHEMA_VERSION",
             "PACKER_VERSION", "VALIDATOR_VERSION", "DEFAULT_CONTEXT_TOKENS",
             "DEFAULT_TARGET_INPUT_TOKENS", "DEFAULT_OUTPUT_TOKENS")
        },
        "records": records,
    }
    write_json(run / "manifest.json", manifest)
    return manifest


class RecordedProvider:
    def __init__(self, provider: Any, directory: Path):
        self.provider = provider
        self.model = provider.model
        self.directory = directory
        self.calls: list[dict[str, Any]] = []

    def generate(self, prompt: str, *, seed: int | None = None,
                 schema: dict[str, Any] | None = None) -> dict[str, Any]:
        properties = (schema or {}).get("properties", {})
        stage = next((name for key, name in (
            ("sense_results", "scaffold"), ("group_assignments", "grouping"),
            ("core_group_ids", "core_selection")) if key in properties), None)
        if stage is None:
            raise ValueError("Unexpected inference contract")
        record: dict[str, Any] = {
            "stage": stage, "started_at": utc_now(), "prompt": prompt,
            "schema": schema, "seed": seed, "prompt_sha256": digest(prompt),
        }
        start = time.perf_counter()
        try:
            response = self.provider.generate(prompt, seed=seed, schema=schema)
            record["response"] = public_payload(response)
            return public_payload(response)
        except Exception as error:
            record["error"] = {"type": type(error).__name__, "message": str(error)}
            raise
        finally:
            record["elapsed_seconds"] = time.perf_counter() - start
            record["ended_at"] = utc_now()
            self.calls.append(record)
            write_json(self.directory / f"call-{len(self.calls):03d}.json", record)


class TrialRuntime:
    def __init__(self, directory: Path):
        self.directory = directory

    def read_cache(self, identity: dict[str, Any]) -> None:
        raise AssertionError("Pilot must bypass cache")

    def write_cache(self, identity: dict[str, Any], value: dict[str, Any]) -> None:
        write_json(self.directory / "validated.json", {"identity": identity, "candidate": value})

    def record_failure(self, value: dict[str, Any]) -> Path:
        path = self.directory / "failure.json"
        write_json(path, value)
        return path


def source_rows(evidence: dict[str, Any], source_ids: list[str]) -> list[dict[str, Any]]:
    senses = {sense["sense_id"]: dict(sense, pos=entry["part_of_speech"])
              for entry in evidence["entries"] for sense in entry["senses"]}
    return [{"source_sense_id": identity, "pos": senses[identity]["pos"],
             "source_order": senses[identity]["source_order"],
             "glosses": senses[identity]["glosses"]} for identity in source_ids]


def review_rows(candidate: dict[str, Any] | None, evidence: dict[str, Any],
                calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for index, call in enumerate(calls, 1):
        if call["stage"] != "scaffold" or "response" not in call:
            continue
        content = call["response"].get("message", {}).get("content", "")
        try:
            parsed = synthesis.strict_json_object(content)
        except synthesis.SynthesisFailure:
            continue
        prompt = json.loads(call["prompt"])
        results = parsed.get("sense_results", {})
        for source in prompt["source_senses"]:
            alias = source["alias"]
            result = results.get(alias) if isinstance(results, dict) else None
            if isinstance(result, dict) and isinstance(result.get("definition"), str):
                rows.append({"stage": "scaffold", "call": index, "alias": alias,
                             "pos": source["pos"], "wording": result["definition"],
                             "sources": source_rows(evidence, [source["sense"]["sense_id"]])})
    if candidate:
        for section in candidate["content"]["pos_sections"]:
            for bucket in ("core_meanings", "additional_meanings"):
                for order, meaning in enumerate(section[bucket], 1):
                    rows.append({"stage": "final", "pos": section["pos"], "bucket": bucket,
                                 "order": order, "wording": meaning["definition"],
                                 "sources": source_rows(evidence, meaning["source_sense_ids"])})
    for row in rows:
        row.update(semantic_classification="UNJUDGED", human_reviewer=None,
                   semantic_flags=[], human_reviewed=False)
    return rows


def evaluate(directory: Path, evidence: dict[str, Any], provider: Any) -> dict[str, Any]:
    directory.mkdir()
    recorded = RecordedProvider(provider, directory)
    events: list[dict[str, Any]] = []
    assembled = False

    def instrument(name: str):
        original = getattr(synthesis, name)

        def measured(*args, **kwargs):
            nonlocal assembled
            if name == "grouped_content":
                assembled = True
            stage = "final_validation" if name == "validate_content" and assembled else name
            start = time.perf_counter()
            event: dict[str, Any] = {"stage": stage}
            try:
                result = original(*args, **kwargs)
                if name.startswith("validate_"):
                    event["errors"] = result
                return result
            finally:
                event["elapsed_seconds"] = time.perf_counter() - start
                events.append(event)
        return measured

    summary: dict[str, Any] = {
        "lemma": evidence["normalized_lemma"], "evidence_set_hash": evidence_set_hash(evidence),
        "started_at": utc_now(), "fresh_generation": True, "cache_hit": False,
        "semantic_classification": "UNJUDGED", "human_reviewed": False,
    }
    candidate = None
    start = time.perf_counter()
    try:
        with ExitStack() as stack:
            for name in ("pack_evidence", "validate_scaffold", "validate_grouping",
                         "scaffold_to_content", "grouped_content", "validate_content", "build_envelope"):
                stack.enter_context(patch.object(synthesis, name, instrument(name)))
            result = synthesis.synthesize_word("unused", evidence["normalized_lemma"], recorded,
                                               TrialRuntime(directory), retry=True,
                                               evidence_snapshot=evidence)
        candidate = result["result"]
        summary.update(status="validated", attempt_id=candidate["attempt_id"],
                       package_count=result["package_count"])
    except synthesis.SynthesisFailure as error:
        summary.update(status="rejected", error_code=error.code,
                       error=str(error), details=public_payload(error.details))
    finally:
        summary["synthesis_elapsed_seconds"] = time.perf_counter() - start
        summary["ended_at"] = utc_now()
        summary["function_timings"] = events
        summary["provider_calls"] = [
            {key: call[key] for key in ("stage", "elapsed_seconds", "started_at", "ended_at")}
            for call in recorded.calls]
        summary["provider_elapsed_seconds"] = sum(call["elapsed_seconds"] for call in recorded.calls)
        write_json(directory / "summary.json", summary)
    write_json(directory / "review.json", review_rows(candidate, evidence, recorded.calls))
    return summary


def run_pilot(run: Path, manifest: dict[str, Any], endpoint: str) -> None:
    tags = requests.get(endpoint.rstrip("/") + "/api/tags", timeout=15)
    tags.raise_for_status()
    installed = [model for model in tags.json()["models"] if model["name"] == MODEL]
    if len(installed) != 1 or not installed[0].get("digest"):
        raise ValueError("Current production model identity unavailable")
    write_json(run / "model.json", installed[0])
    provider = synthesis.OllamaProvider(endpoint=endpoint)
    for index, record in enumerate(manifest["records"], 1):
        lemma = record["normalized_lemma"]
        evidence = json.loads((run / "evidence" / f"{lemma}.json").read_text())
        if evidence_set_hash(evidence) != record["evidence_set_hash"]:
            raise ValueError(f"Frozen evidence identity changed: {lemma}")
        state = requests.get(endpoint.rstrip("/") + "/api/ps", timeout=15)
        state.raise_for_status()
        write_json(run / f"runtime-before-{index:02d}.json", state.json())
        summary = evaluate(run / f"{index:02d}-{lemma}", evidence, provider)
        summary.update(stratum=record["stratum"], order=index,
                       model_digest=installed[0]["digest"],
                       evidence_preparation_seconds=record["evidence_preparation_seconds"])
        with (run / "attempts.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(canonical_json(summary) + "\n")
        print(canonical_json({key: summary[key] for key in
                              ("lemma", "stratum", "status", "synthesis_elapsed_seconds")}), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--lexical-root", type=Path, default=Path("/lexical-data"))
    parser.add_argument("--endpoint", default="http://ollama:11434")
    parser.add_argument("--execute-approved-pilot", action="store_true")
    args = parser.parse_args()
    allowed = (Path("/benchmark"), Path.home() / ".local/share/vocab-app/benchmarks/m002.002")
    output = args.output.resolve()
    if not any(output.is_relative_to(base.resolve()) and output != base.resolve() for base in allowed):
        raise ValueError("Output must be a new run directory inside the dedicated M002.002 benchmark mount")
    output.mkdir(parents=True, exist_ok=False)
    manifest = prepare(output, resolve_active_database(args.lexical_root))
    if args.execute_approved_pilot:
        run_pilot(output, manifest, args.endpoint)
    else:
        print("Evidence prepared only; no inference executed", flush=True)


if __name__ == "__main__":
    main()
