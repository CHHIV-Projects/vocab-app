"""A3-authorized equivalent-contract alternate-model lane; no production wiring."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any

import requests

from tools.benchmarks.m002002_product_trial import (
    ROOT, evaluate, public_payload, utc_now, write_json,
)
from vocab_lexical_engine import evidence_set_hash
from vocab_synthesis import OllamaProvider, SynthesisFailure

MODELS = ("qwen3.5:9b", "ministral-3:14b")
WORDS = ("lantern", "useful", "bread", "phone", "jelly", "staff", "bank", "draft")
DISK_CAP = 40_000_000_000
INFERENCE_CAP = 45 * 60


def frozen_evidence(pilot: Path) -> dict[str, Any]:
    manifest = json.loads((pilot / "manifest.json").read_text())
    for name, expected in manifest["source_sha256"].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Pilot source identity changed: {name}")
    records = {row["normalized_lemma"]: row for row in manifest["records"]}
    selected = {}
    for lemma in WORDS:
        evidence = json.loads((pilot / "evidence" / f"{lemma}.json").read_text())
        if evidence_set_hash(evidence) != records[lemma]["evidence_set_hash"]:
            raise ValueError(f"Frozen evidence changed: {lemma}")
        selected[lemma] = evidence
    return selected


def get_json(endpoint: str, route: str) -> dict[str, Any]:
    response = requests.get(endpoint + route, timeout=30)
    response.raise_for_status()
    return response.json()


class BoundedProvider(OllamaProvider):
    def __init__(self, endpoint: str, model: str, budget: list[float], directory: Path):
        super().__init__(endpoint=endpoint, model=model, timeout=180)
        self.budget = budget
        self.directory = directory
        self.calls = 0

    def generate(self, prompt: str, *, seed: int | None = None,
                 schema: dict[str, Any] | None = None) -> dict[str, Any]:
        if self.budget[0] + 180 > INFERENCE_CAP:
            raise SynthesisFailure("lane_budget_stop", "Insufficient remaining 45-minute call budget")
        state = get_json(self.endpoint, "/api/ps")
        self.calls += 1
        write_json(self.directory / f"runtime-before-call-{self.calls:03d}.json", state)
        if any(row["name"] != self.model for row in state["models"]):
            raise SynthesisFailure("shared_workload_stop", "Unrelated model loaded; no unload authorized")
        start = time.perf_counter()
        try:
            response = super().generate(prompt, seed=seed, schema=schema)
        except requests.HTTPError as error:
            http = error.response
            failure = {"status": http.status_code, "error": http.json().get("error")}
            write_json(self.directory / f"provider-error-{self.calls:03d}.json", failure)
            raise SynthesisFailure("provider_incompatible", str(failure)) from error
        except (requests.Timeout, requests.ConnectionError) as error:
            raise SynthesisFailure("provider_transport_stop", str(error)) from error
        finally:
            self.budget[0] += time.perf_counter() - start
        write_json(self.directory / f"provider-response-{self.calls:03d}.json", public_payload(response))
        state = get_json(self.endpoint, "/api/ps")
        write_json(self.directory / f"runtime-after-call-{self.calls:03d}.json", state)
        for row in state["models"]:
            if row["name"] != self.model:
                raise SynthesisFailure("shared_workload_stop", "Unrelated model appeared during inference")
            if row.get("context_length") != 16384 or row.get("size_vram", 0) < row["size"]:
                raise SynthesisFailure("runtime_fit_stop", "16K all-GPU allocation not established")
        return response


def pull(endpoint: str, model: str, directory: Path, reserved: int) -> int:
    family, tag = model.split(":")
    registry = f"https://registry.ollama.ai/v2/library/{family}"
    response = requests.get(registry + f"/manifests/{tag}", timeout=30)
    response.raise_for_status()
    manifest_digest = hashlib.sha256(response.content).hexdigest()
    manifest = response.json()
    write_json(directory / "registry-manifest.json", manifest)
    size = manifest["config"]["size"] + sum(layer["size"] for layer in manifest["layers"])
    # Reserve two complete bundle copies for staging, plus 1 GB benchmark output.
    if 2 * (reserved + size) + 1_000_000_000 > DISK_CAP:
        raise ValueError("Published bundles and staging exceed approved 40 GB reservation")
    licenses = [layer for layer in manifest["layers"] if layer["mediaType"].endswith(".license")]
    if not licenses:
        raise ValueError("Published license missing")
    for index, layer in enumerate(licenses):
        license_response = requests.get(registry + "/blobs/" + layer["digest"], timeout=30)
        license_response.raise_for_status()
        text = license_response.text
        if "Apache License" not in text or "Version 2.0" not in text:
            raise ValueError("Expected approved Apache-2.0 license")
        write_json(directory / f"license-{index}.json", {"text": text, "digest": layer["digest"]})
    response = requests.post(endpoint + "/api/pull", json={"model": model, "stream": False},
                             timeout=1800)
    response.raise_for_status()
    write_json(directory / "pull.json", response.json())
    models = get_json(endpoint, "/api/tags")["models"]
    installed = next(row for row in models if row["name"] == model)
    write_json(directory / "model.json", installed)
    if installed["digest"] != manifest_digest:
        raise ValueError("Tag moved between verified registry manifest and download")
    if installed["size"] > size:
        raise ValueError("Installed bundle exceeds verified download reservation")
    show = requests.post(endpoint + "/api/show", json={"model": model}, timeout=30)
    show.raise_for_status()
    write_json(directory / "show.json", show.json())
    return size


def run(pilot: Path, output: Path, endpoint: str) -> None:
    evidence = frozen_evidence(pilot)
    output.mkdir(parents=True, exist_ok=False)
    initial = get_json(endpoint, "/api/ps")
    write_json(output / "runtime-initial.json", initial)
    write_json(output / "installed-before.json", get_json(endpoint, "/api/tags"))
    if initial["models"]:
        raise ValueError("Service not idle; no shared model will be unloaded")
    write_json(output / "manifest.json", {
        "approval": "M002.002 A3", "created_at": utc_now(), "models": MODELS,
        "words": WORDS, "repeats": 3, "max_attempts_per_model": 24,
        "inference_cap_seconds": INFERENCE_CAP, "call_timeout_seconds": 180,
        "disk_cap_bytes": DISK_CAP, "pilot": str(pilot),
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "evidence": {lemma: evidence_set_hash(value) for lemma, value in evidence.items()},
        "contract": "unchanged production multi-sense; think=low; seed unset; 16K/3200",
    })
    budget = [0.0]
    reserved = 0
    results = []
    stops = {"provider_incompatible", "provider_transport_stop", "lane_budget_stop",
             "shared_workload_stop", "runtime_fit_stop"}
    for model in MODELS:
        directory = output / model.replace(":", "-")
        directory.mkdir()
        if get_json(endpoint, "/api/ps")["models"]:
            # Allow only natural keep-alive expiry; never unload a possibly shared job.
            deadline = time.monotonic() + 310
            while get_json(endpoint, "/api/ps")["models"] and time.monotonic() < deadline:
                time.sleep(10)
            if get_json(endpoint, "/api/ps")["models"]:
                raise ValueError("Service did not become idle; stop without unloading")
        reserved += pull(endpoint, model, directory, reserved)
        provider = BoundedProvider(endpoint, model, budget, directory)
        stop = False
        for repeat in range(1, 4):
            for lemma in WORDS:
                attempt = directory / f"r{repeat}-{lemma}"
                summary = evaluate(attempt, evidence[lemma], provider)
                summary.update(model=model, repeat=repeat,
                               model_digest=json.loads((directory / "model.json").read_text())["digest"])
                results.append(summary)
                write_json(attempt / "attempt.json", summary)
                print(json.dumps(summary), flush=True)
                if summary.get("error_code") in stops:
                    stop = True
                    break
            if stop:
                break
        write_json(directory / "disposition.json", {"candidate_stopped": stop,
                   "attempts": sum(row["model"] == model for row in results)})
    write_json(output / "results.json", {"attempts": results, "provider_seconds": budget[0],
                                       "finished_at": utc_now(), "bundle_bytes": reserved})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--endpoint", default="http://ollama:11434")
    args = parser.parse_args()
    if not args.output.resolve().is_relative_to(Path("/benchmark")):
        raise ValueError("Output must be inside the dedicated benchmark mount")
    run(args.pilot, args.output, args.endpoint.rstrip("/"))


if __name__ == "__main__":
    main()
