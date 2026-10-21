"""A2-authorized seven-sense, three-repeat current-model counterfactual only."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
from pathlib import Path
from time import perf_counter
from typing import Any

import requests

from tools.benchmarks.m002002_product_trial import (
    MODEL, digest, public_payload, source_rows, utc_now, write_json,
)
from vocab_lexical_engine import canonical_json, evidence_set_hash
from vocab_synthesis import OllamaProvider, SynthesisFailure, response_content, strict_json_object

SCHEMA = {"type": "object", "additionalProperties": False,
          "properties": {"definition": {"type": "string"}}, "required": ["definition"]}
SELECTION = [
    ("useful", "7c62411e22c5b39e476d1b0b"),
    ("quartz", "d71d7259df70b053f08f67dd"),
    ("phone", "87d29b1d9c9723d6468b4c54"),
    ("lantern", "ea61877afabe26b54ac088ba"),
    ("lantern", "3f6ca0c9e7d847597bbb4091"),
    ("lantern", "83105eb6ff2d293d412e3c04"),
    ("lantern", "76b511592e299c2fbe106ac9"),
]
CONTRACT = "m002002-one-fixed-source-v1"


def selected_sources(pilot: Path) -> list[dict[str, Any]]:
    manifest = json.loads((pilot / "manifest.json").read_text())
    expected = {row["normalized_lemma"]: row["evidence_set_hash"] for row in manifest["records"]}
    selected = []
    for lemma, suffix in SELECTION:
        evidence = json.loads((pilot / "evidence" / f"{lemma}.json").read_text())
        if evidence_set_hash(evidence) != expected[lemma]:
            raise ValueError(f"Frozen evidence changed: {lemma}")
        matches = [(entry, sense) for entry in evidence["entries"] for sense in entry["senses"]
                   if sense["sense_id"].endswith(f":{suffix}:1:sense")]
        if len(matches) != 1:
            raise ValueError(f"Fixed sense identity not unique: {lemma}/{suffix}")
        entry, sense = matches[0]
        selected.append({
            "lemma": lemma, "evidence_set_hash": expected[lemma],
            "source": source_rows(evidence, [sense["sense_id"]])[0],
            "sense_evidence": sense, "pos": entry["part_of_speech"],
        })
    return selected


def narrow_prompt(source: dict[str, Any]) -> str:
    return canonical_json({
        "task": "Return exactly one JSON object with exactly the key definition.",
        "authority": "Write one concise learner-friendly paraphrase of only the supplied "
                     "source sense. Preserve uncertainty. Do not invent facts. "
                     "Do not output IDs, POS, labels or other fields.",
        "lemma": source["lemma"], "source_pos": source["pos"],
        "source_sense": source["sense_evidence"],
    })


def validate_definition(raw: str) -> str:
    parsed = strict_json_object(raw)
    if set(parsed) != {"definition"} or not isinstance(parsed["definition"], str) or not parsed["definition"].strip():
        raise SynthesisFailure("narrow_structure_invalid", "Expected exactly one nonempty definition string")
    return parsed["definition"]


def attempt(source: dict[str, Any], repeat: int, provider: Any) -> dict[str, Any]:
    prompt = narrow_prompt(source)
    record = {
        "contract": CONTRACT, "comparison": "NON-EQUIVALENT: one source and definition-only schema; no grouping/core",
        "lemma": source["lemma"], "repeat": repeat, "source": source["source"],
        "evidence_set_hash": source["evidence_set_hash"], "prompt": prompt,
        "prompt_sha256": digest(prompt), "schema": SCHEMA, "seed": None,
        "started_at": utc_now(), "semantic_classification": "UNJUDGED",
        "human_reviewed": False, "human_reviewer": None,
    }
    start = perf_counter()
    try:
        response = provider.generate(prompt, seed=None, schema=SCHEMA)
        record["provider_seconds"] = perf_counter() - start
        record["response"] = public_payload(response)
        check_start = perf_counter()
        if response.get("done_reason") == "length":
            raise SynthesisFailure("output_truncated", "Narrow output ended at length limit")
        wording = validate_definition(response_content(response))
        record.update(status="validated", wording=wording, validation_seconds=perf_counter() - check_start)
    except (SynthesisFailure, requests.RequestException) as error:
        record.update(status="rejected", error_code=getattr(error, "code", type(error).__name__),
                      error=str(error))
    finally:
        record["total_seconds"] = perf_counter() - start
        record["ended_at"] = utc_now()
    return record


def export(records: list[dict[str, Any]], prefix: Path, run: Path) -> None:
    manifest = json.loads((run / "manifest.json").read_text())
    summary = {
        "run_path": str(run), "contract": CONTRACT, "comparison": "NON-EQUIVALENT",
        "model": manifest["model"], "inference_options": manifest["inference_options"],
        "schema": manifest["schema"], "code_sha256": manifest["code_sha256"],
        "manifest_sha256": hashlib.sha256((run / "manifest.json").read_bytes()).hexdigest(),
        "artifact_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                            for path in sorted(run.glob("*.json"))},
        "source_senses": len({row["source"]["source_sense_id"] for row in records}), "attempts": len(records),
        "validated": sum(row["status"] == "validated" for row in records),
        "human_reviewed": 0, "semantic_classification": "UNJUDGED",
        "latency_seconds": {
            "median": statistics.median(row["total_seconds"] for row in records),
            "min": min(row["total_seconds"] for row in records),
            "max": max(row["total_seconds"] for row in records),
            "sum": sum(row["total_seconds"] for row in records),
        },
        "wording_variants_by_source": {
            source_id: len({row.get("wording") for row in records
                            if row["source"]["source_sense_id"] == source_id and row["status"] == "validated"})
            for source_id in {row["source"]["source_sense_id"] for row in records}
        },
        "records": records,
    }
    write_json(Path(str(prefix) + "_attempts.json"), summary)
    with Path(str(prefix) + "_review.csv").open("x", newline="") as stream:
        fields = ["lemma", "repeat", "source_sense_id", "pos", "source_order", "exact_glosses",
                  "status", "wording", "seconds", "semantic_classification", "human_reviewer"]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in records:
            source = row["source"]
            writer.writerow({
                "lemma": row["lemma"], "repeat": row["repeat"],
                "source_sense_id": source["source_sense_id"], "pos": source["pos"],
                "source_order": source["source_order"], "exact_glosses": json.dumps(source["glosses"], ensure_ascii=False),
                "status": row["status"], "wording": row.get("wording", ""),
                "seconds": row["total_seconds"], "semantic_classification": "UNJUDGED", "human_reviewer": "",
            })


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report-prefix", type=Path, required=True)
    args = parser.parse_args()
    base = Path("/benchmark").resolve()
    for path in (args.output, args.pilot):
        if not path.resolve().is_relative_to(base) or path.resolve() == base:
            raise ValueError("Use only dedicated benchmark subdirectories")
    if not args.report_prefix.resolve().is_relative_to(base):
        raise ValueError("Reports must be written inside benchmark mount")
    sources = selected_sources(args.pilot)
    args.output.mkdir(exist_ok=False)
    tags = requests.get("http://ollama:11434/api/tags", timeout=15)
    tags.raise_for_status()
    models = [model for model in tags.json()["models"] if model["name"] == MODEL]
    baseline = json.loads((args.pilot / "model.json").read_text())
    if len(models) != 1 or models[0]["digest"] != baseline["digest"]:
        raise ValueError("Current GPT-OSS digest changed since pilot")
    write_json(args.output / "manifest.json", {
        "created_at": utc_now(), "contract": CONTRACT, "sources": sources, "schema": SCHEMA,
        "model": models[0], "repeats": 3, "seed": None,
        "code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "inference_options": {"temperature": 0, "think": "low", "num_ctx": 16384, "num_predict": 3200},
        "grouping": "omitted", "core_selection": "omitted",
    })
    provider = OllamaProvider()
    records = []
    for repeat in range(1, 4):
        for index, source in enumerate(sources, 1):
            record = attempt(source, repeat, provider)
            write_json(args.output / f"repeat-{repeat}-sense-{index}.json", record)
            records.append(record)
            print(canonical_json({key: record[key] for key in ("lemma", "repeat", "status", "total_seconds")}), flush=True)
    export(records, args.report_prefix, args.output)


if __name__ == "__main__":
    main()
