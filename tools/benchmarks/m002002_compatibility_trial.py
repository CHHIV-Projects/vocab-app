"""A4 staged NON-EQUIVALENT lane: only think=low changes to boolean false."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any
from unittest.mock import patch

import requests

from tools.benchmarks.m002002_alternate_trial import (
    BoundedProvider, DISK_CAP, INFERENCE_CAP, MODELS, WORDS, frozen_evidence, get_json,
)
from tools.benchmarks.m002002_product_trial import evaluate, utc_now, write_json
from vocab_lexical_engine import evidence_set_hash

PINNED = {
    "qwen3.5:9b": "56671c2ab9385f9cfcb404638e32cd62d88e3501d44822208363c010179a3c90",
    "ministral-3:14b": "4760c35aeb9d9e9c6174c2492562c0b999e80a222804fd96b1915ab72bbcdcf7",
}
CONTRACT = "NON-EQUIVALENT A4: only provider think=low -> boolean false"
STOPS = {"provider_incompatible", "provider_transport_stop", "lane_budget_stop",
         "shared_workload_stop", "runtime_fit_stop"}


class CompatibilityProvider(BoundedProvider):
    def generate(self, prompt: str, *, seed: int | None = None,
                 schema: dict[str, Any] | None = None) -> dict[str, Any]:
        original_post = requests.post

        def adapted_post(url: str, **kwargs: Any) -> Any:
            if url != self.endpoint + "/api/chat" or kwargs["json"]["think"] != "low":
                raise ValueError("Unexpected provider contract; only think=low may change")
            body = dict(kwargs["json"], think=False)
            write_json(self.directory / f"request-{self.calls:03d}.json", body)
            return original_post(url, **dict(kwargs, json=body))

        with patch("vocab_synthesis.requests.post", adapted_post):
            return super().generate(prompt, seed=seed, schema=schema)


def schedule() -> list[tuple[int, str]]:
    return [(repeat, lemma) for repeat in range(1, 4) for lemma in WORDS]


def run(pilot: Path, output: Path, endpoint: str) -> None:
    evidence = frozen_evidence(pilot)
    output.mkdir(parents=True, exist_ok=False)
    state = get_json(endpoint, "/api/ps")
    installed = get_json(endpoint, "/api/tags")
    write_json(output / "runtime-initial.json", state)
    write_json(output / "installed-before.json", installed)
    if state["models"]:
        raise ValueError("Shared service not idle; no model will be unloaded")
    models = {row["name"]: row for row in installed["models"]}
    if any(models.get(model, {}).get("digest") != PINNED[model] for model in MODELS):
        raise ValueError("Installed A3 model identity changed; no download authorized")
    write_json(output / "manifest.json", {
        "approval": "M002.002 A4", "contract": CONTRACT, "created_at": utc_now(),
        "models": PINNED, "schedule": schedule(), "probe_gate": "first lantern must validate",
        "inference_cap_seconds": INFERENCE_CAP, "call_timeout_seconds": 180,
        "disk_cap_bytes": DISK_CAP, "no_download": True,
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "evidence": {lemma: evidence_set_hash(value) for lemma, value in evidence.items()},
        "inference_options": {"think": False, "temperature": 0, "num_ctx": 16384,
                              "num_predict": 3200, "seed": None},
    })
    budget = [0.0]
    results = []
    for model in MODELS:
        directory = output / model.replace(":", "-")
        directory.mkdir()
        write_json(directory / "model.json", models[model])
        deadline = time.monotonic() + 310
        while get_json(endpoint, "/api/ps")["models"] and time.monotonic() < deadline:
            time.sleep(10)
        if get_json(endpoint, "/api/ps")["models"]:
            raise ValueError("Shared service not idle after natural expiry; stop without unload")
        provider = CompatibilityProvider(endpoint, model, budget, directory)
        stop_reason = None
        for order, (repeat, lemma) in enumerate(schedule()):
            attempt = directory / f"r{repeat}-{lemma}"
            summary = evaluate(attempt, evidence[lemma], provider)
            summary.update(model=model, model_digest=PINNED[model], repeat=repeat,
                           comparison=CONTRACT, is_probe=order == 0)
            write_json(attempt / "attempt.json", summary)
            results.append(summary)
            write_json(output / f"progress-{len(results):02d}.json", {
                "attempts": results, "provider_seconds": budget[0]})
            print(json.dumps({key: summary[key] for key in
                              ("model", "lemma", "repeat", "status", "synthesis_elapsed_seconds")}),
                  flush=True)
            if (order == 0 and summary["status"] != "validated"
                    or summary.get("error_code") in STOPS):
                stop_reason = summary.get("error_code", "invalid_probe")
                break
        write_json(directory / "disposition.json", {
            "stop_reason": stop_reason,
            "attempts": sum(row["model"] == model for row in results),
            "probe_validated": next(row["status"] == "validated"
                                    for row in results if row["model"] == model),
        })
        if stop_reason in {"shared_workload_stop", "lane_budget_stop", "provider_transport_stop"}:
            break
    write_json(output / "results.json", {
        "contract": CONTRACT, "attempts": results, "provider_seconds": budget[0],
        "finished_at": utc_now()})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--endpoint", default="http://ollama:11434")
    args = parser.parse_args()
    if not args.output.resolve().is_relative_to(Path("/benchmark")):
        raise ValueError("Use the dedicated benchmark mount")
    run(args.pilot, args.output, args.endpoint.rstrip("/"))
