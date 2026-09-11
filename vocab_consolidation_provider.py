"""Bounded, single-pair Qwen (`qwen3:8b`) provider for isolated semantic pair judgment.

This module produces exactly one structured-JSON pair judgment per request. It reuses the
accepted M004.6.4 single-pair decision/reason prompt pattern and policy string, and the
existing Ollama response-parsing helpers in `vocab_synthesis.py`. It does not modify, call,
or depend on the learner-facing `gpt-oss:20b` synthesis/grouping path (`OllamaProvider`).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

import requests

from vocab_consolidation import ConsolidationPartition, SensePair, validate_decision_reason
from vocab_lexical_engine import canonical_json
from vocab_synthesis import SynthesisFailure, response_content, strict_json_object

# Accepted M004.6.4 single-pair benchmark identity (tools/benchmarks/m0046_policy_batched_benchmark.py
# and tools/benchmarks/manifests/m004.6.4_policy_batched_reference.json), reused verbatim.
PAIR_PROMPT_VERSION = "pair-prompt-v1-m004.6.4-policy"
QWEN_MODEL = "qwen3:8b"
QWEN_EXPECTED_DIGEST = "500a1f067a9f782620b40bee6f7b0c89e17ae61f686b92c24933e4ca4b2b8b41"
QWEN_SEMANTIC_OPTIONS: dict[str, Any] = {
    "think": False,
    "temperature": 0,
    "seed": 5100,
    "num_predict": 256,
    "num_ctx": 16384,
}
LEARNER_CONSOLIDATION_POLICY = (
    "Merge only near-paraphrase, duplicate, or contextual-application variants. "
    "Keep specialized, broader/narrower, related-but-distinct, materially different, "
    "and uncertain senses separate. Prefer false splits."
)

PROVIDER_SUCCESS = "provider_success"
RETRYABLE_FAILURE = "retryable_failure"
TERMINAL_FAILURE = "terminal_failure"


def pair_decision_schema() -> dict[str, Any]:
    """The exact accepted single-pair decision/reason schema (M004.6.4)."""
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "decision": {"type": "string", "enum": ["merge", "keep_separate", "uncertain"]},
            "reason": {
                "type": "string",
                "enum": [
                    "paraphrase_or_duplicate",
                    "contextual_variant",
                    "specialized_subsense",
                    "broader_or_narrower",
                    "related_but_distinct",
                    "materially_different",
                    "insufficient_evidence",
                ],
            },
        },
        "required": ["decision", "reason"],
    }


def _sense_view(member: Mapping[str, Any]) -> dict[str, Any]:
    """Project only fields already exposed by M004.6.9 domain evidence members."""
    return {
        "source_sense_id": member["sense_id"],
        "definitions": list(member.get("glosses", [])),
        "labels": sorted(member.get("labels", [])),
        "examples": [
            example.get("text") if isinstance(example, Mapping) else example
            for example in member.get("examples", [])
        ],
        "relations": [
            {"type": relation.get("type"), "target": relation.get("target")}
            for relation in member.get("relations", [])
            if isinstance(relation, Mapping)
        ],
    }


def build_pair_prompt(partition: ConsolidationPartition, pair: SensePair) -> str:
    """Deterministic single-pair judgment prompt, adapted from the accepted M004.6.4 template."""
    members = {member["sense_id"]: member for member in partition.members}
    payload = {
        "task": "Return exactly one JSON object matching the required schema.",
        "learner_consolidation_policy": LEARNER_CONSOLIDATION_POLICY,
        "word": partition.normalized_lemma,
        "part_of_speech": partition.pos,
        "material_partition": list(partition.material_partition),
        "sense_a": _sense_view(members[pair.source_sense_id_a]),
        "sense_b": _sense_view(members[pair.source_sense_id_b]),
    }
    return canonical_json(payload)


@dataclass(frozen=True)
class PairProviderRequest:
    pair: SensePair
    partition: ConsolidationPartition
    prompt: str
    schema: Mapping[str, Any]
    model: str
    semantic_options: Mapping[str, Any]


@dataclass(frozen=True)
class PairProviderResult:
    status: str
    decision: str | None = None
    reason: str | None = None
    error_classification: str | None = None
    error_summary: str | None = None
    diagnostics: Mapping[str, Any] = field(default_factory=dict)


def build_pair_request(
    partition: ConsolidationPartition,
    pair: SensePair,
    *,
    model: str = QWEN_MODEL,
    semantic_options: Mapping[str, Any] = QWEN_SEMANTIC_OPTIONS,
) -> PairProviderRequest:
    return PairProviderRequest(
        pair=pair,
        partition=partition,
        prompt=build_pair_prompt(partition, pair),
        schema=pair_decision_schema(),
        model=model,
        semantic_options=dict(semantic_options),
    )


class PairProvider(Protocol):
    def judge_pair(self, request: PairProviderRequest) -> PairProviderResult: ...


def installed_model_digest(endpoint: str, model: str) -> str:
    response = requests.get(endpoint.rstrip("/") + "/api/tags", timeout=30)
    response.raise_for_status()
    for item in response.json().get("models", []):
        if item.get("model") == model or item.get("name") == model:
            return str(item["digest"])
    raise RuntimeError(f"Required installed model is not available: {model}")


def confirm_installed_model_identity(endpoint: str, model: str, expected_digest: str) -> str:
    """Preflight identity confirmation. Callers must STOP rather than proceed on mismatch."""
    digest = installed_model_digest(endpoint, model)
    if digest != expected_digest:
        raise RuntimeError(
            f"Installed {model} digest {digest!r} does not match expected {expected_digest!r}; STOP required"
        )
    return digest


class QwenPairProvider:
    """Bounded, single-pair Ollama Qwen provider. One HTTP request judges exactly one pair."""

    def __init__(self, endpoint: str | None = None, model: str = QWEN_MODEL, timeout: float = 120):
        self.endpoint = (endpoint or os.environ.get("VOCAB_OLLAMA_URL", "http://ollama:11434")).rstrip("/")
        self.model = model
        self.timeout = timeout

    def judge_pair(self, request: PairProviderRequest) -> PairProviderResult:
        options = request.semantic_options
        try:
            response = requests.post(
                self.endpoint + "/api/chat",
                json={
                    "model": request.model,
                    "messages": [{"role": "user", "content": request.prompt}],
                    "stream": False,
                    "format": dict(request.schema),
                    "think": bool(options.get("think", False)),
                    "keep_alive": "5m",
                    "options": {
                        "temperature": options.get("temperature", 0),
                        "seed": options.get("seed"),
                        "num_predict": options.get("num_predict", 256),
                        "num_ctx": options.get("num_ctx", 16384),
                    },
                },
                timeout=self.timeout,
            )
        except requests.Timeout as error:
            return PairProviderResult(RETRYABLE_FAILURE, error_classification="timeout", error_summary=str(error))
        except requests.RequestException as error:
            return PairProviderResult(RETRYABLE_FAILURE, error_classification="transport_failure", error_summary=str(error))

        if response.status_code == 404:
            return PairProviderResult(TERMINAL_FAILURE, error_classification="model_unavailable", error_summary=response.text[:500])
        if 500 <= response.status_code < 600:
            return PairProviderResult(RETRYABLE_FAILURE, error_classification="provider_server_error", error_summary=response.text[:500])
        try:
            response.raise_for_status()
        except requests.HTTPError as error:
            return PairProviderResult(TERMINAL_FAILURE, error_classification="provider_request_error", error_summary=str(error))

        try:
            payload = response.json()
        except ValueError as error:
            return PairProviderResult(RETRYABLE_FAILURE, error_classification="malformed_response", error_summary=str(error))

        diagnostics = {"done_reason": payload.get("done_reason"), "eval_count": payload.get("eval_count")}
        if payload.get("done_reason") == "length":
            return PairProviderResult(
                RETRYABLE_FAILURE,
                error_classification="truncated_length",
                error_summary="Model output was truncated at the output budget",
                diagnostics=diagnostics,
            )

        try:
            content = response_content(payload)
        except SynthesisFailure as error:
            return PairProviderResult(RETRYABLE_FAILURE, error_classification="provider_response_shape", error_summary=str(error), diagnostics=diagnostics)

        if not content.strip():
            return PairProviderResult(RETRYABLE_FAILURE, error_classification="empty_response", error_summary="Model returned empty content", diagnostics=diagnostics)

        try:
            parsed = strict_json_object(content)
        except SynthesisFailure as error:
            return PairProviderResult(RETRYABLE_FAILURE, error_classification="malformed_json", error_summary=str(error), diagnostics=diagnostics)

        if set(parsed) != {"decision", "reason"}:
            return PairProviderResult(
                RETRYABLE_FAILURE,
                error_classification="schema_invalid",
                error_summary=f"Unexpected keys in decision object: {sorted(parsed)}",
                diagnostics=diagnostics,
            )

        decision, reason = parsed.get("decision"), parsed.get("reason")
        try:
            validate_decision_reason(decision, reason)
        except ValueError as error:
            return PairProviderResult(RETRYABLE_FAILURE, error_classification="schema_invalid", error_summary=str(error), diagnostics=diagnostics)

        return PairProviderResult(PROVIDER_SUCCESS, decision=decision, reason=reason, diagnostics=diagnostics)
