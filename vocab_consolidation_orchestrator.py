"""Bounded, resumable orchestration connecting the M004.6.9 domain and M004.6.10 persistence
foundations to a pair-judgment provider (fake, for offline tests, or the real `QwenPairProvider`).

This module owns no semantic judgment, coverage, or clustering logic of its own; it only
sequences the already-accepted domain/persistence primitives and classifies provider outcomes
into the existing durable pair-ledger states.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from vocab_consolidation import (
    PAIR_JUDGMENT_CONTRACT,
    ConsolidationPartition,
    PairJudgment,
    build_partitions,
    enumerate_pairs,
    pair_judgment_identity,
)
from vocab_consolidation_persistence import ConsolidationPersistence
from vocab_consolidation_provider import PairProvider, PairProviderRequest, build_pair_request

# Bounded retry policy: a pair may be attempted at most this many times before a retryable
# failure is escalated to a terminal, topology-blocking failure. Matches the M004.6.11 prompt's
# suggested default bound (Section 20).
MAX_PAIR_ATTEMPTS = 3

DEFAULT_LEASE_OWNER = "m004611-orchestrator"

STATUS_ALREADY_COMPLETE = "already_complete"
STATUS_TOPOLOGY_VALIDATED = "topology_validated"
STATUS_INCOMPLETE = "incomplete"
STATUS_BLOCKED_TERMINAL_FAILURE = "blocked_terminal_failure"


def lexical_dataset_identity_from_evidence(evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Deterministic, code-owned dataset identity derived from already-projected evidence."""
    return {
        "wiktionary_versions": list(evidence.get("wiktionary_versions", [])),
        "wordnet_version": evidence.get("wordnet_version"),
    }


def partitions_from_synthesis_evidence(evidence: Mapping[str, Any]) -> tuple[ConsolidationPartition, ...]:
    """Adapt real `vocab_synthesis.project_synthesis_evidence()` output for `build_partitions()`.

    Real evidence senses expose material/register information under the key `"tags"`
    (see `vocab_synthesis._source_evidence`), while `vocab_consolidation._material_signature`
    reads `"labels"`. The M004.6.9 domain tests never exercised this boundary because their
    hand-built fixtures used `"labels"` directly, so `build_partitions()` has never previously
    been called against real evidence. Rather than editing the already-accepted M004.6.9
    `vocab_consolidation.py` or the already-accepted, learner-facing `vocab_synthesis.py`, this
    adapter narrowly bridges the two evidence shapes at the M004.6.11 integration boundary by
    adding a `"labels"` alias (mirroring `"tags"`) to each sense before partitioning. No source
    evidence field is removed, and `"tags"` is preserved unchanged.
    """
    adapted_entries = []
    for entry in evidence.get("entries", []):
        adapted_senses = []
        for sense in entry.get("senses", []):
            sense = dict(sense)
            sense.setdefault("labels", list(sense.get("tags", [])))
            adapted_senses.append(sense)
        adapted_entries.append({**entry, "senses": adapted_senses})
    adapted_evidence = {**evidence, "entries": adapted_entries}
    return build_partitions(adapted_evidence)


@dataclass(frozen=True)
class OrchestrationResult:
    job_id: int
    consolidation_identity: str
    partition_id: str
    expected_pair_count: int
    provider_calls_made: int
    status: str
    progress: Mapping[str, int]
    topology_identity: str | None = None
    containers: tuple[dict[str, Any], ...] = ()


def _pairs_by_id(partition: ConsolidationPartition) -> dict[str, Any]:
    return {pair.pair_id: pair for pair in enumerate_pairs(partition)}


def _reclaim_if_lease_expired(
    persistence: ConsolidationPersistence, job_id: int, pair, row: dict[str, Any]
) -> dict[str, Any]:
    """Demote an expired `running` lease to `failed_retryable` using existing transition rules
    before attempting to claim it again. This does not increment `attempt_count`; the original
    attempt was already counted when the expired lease was first acquired."""
    if row["status"] != "running":
        return row
    return persistence.record_pair_failure(
        job_id, pair.pair_id, "failed_retryable", "lease_expired",
        "Previous attempt lease expired before completion",
    )


def run_partition_consolidation(
    persistence: ConsolidationPersistence,
    partition: ConsolidationPartition,
    provider: PairProvider,
    *,
    lexical_dataset_identity: Mapping[str, Any],
    model_identity: Mapping[str, Any],
    semantic_options: Mapping[str, Any],
    contract_version: str = PAIR_JUDGMENT_CONTRACT,
    lease_owner: str = DEFAULT_LEASE_OWNER,
    max_pairs: int | None = None,
    max_attempts: int = MAX_PAIR_ATTEMPTS,
) -> OrchestrationResult:
    job = persistence.create_or_get_job(
        partition,
        lexical_dataset_identity=lexical_dataset_identity,
        model_identity=model_identity,
        semantic_options=semantic_options,
        contract_version=contract_version,
    )
    job_id = job["id"]

    if job["status"] == "topology_validated":
        containers = persistence.load_validated_containers(job_id)
        return OrchestrationResult(
            job_id, job["consolidation_identity"], partition.partition_id, partition.expected_pair_count,
            0, STATUS_ALREADY_COMPLETE, persistence.job_progress(job_id), job["topology_identity"], tuple(containers),
        )

    persistence.initialize_pairs(job_id, partition)

    if partition.expected_pair_count == 0:
        containers, topology = persistence.finalize_topology(job_id, partition)
        return OrchestrationResult(
            job_id, job["consolidation_identity"], partition.partition_id, 0,
            0, STATUS_TOPOLOGY_VALIDATED, persistence.job_progress(job_id), topology, tuple(containers),
        )

    pairs_by_id = _pairs_by_id(partition)
    resumable = persistence.list_resumable_pairs(job_id)
    if max_pairs is not None:
        resumable = resumable[:max_pairs]

    provider_calls_made = 0
    for row in resumable:
        pair = pairs_by_id.get(row["logical_pair_id"])
        if pair is None:
            raise ValueError("Durable pair ledger contains a foreign logical pair")

        row = _reclaim_if_lease_expired(persistence, job_id, pair, row)

        if row["status"] == "failed_retryable" and row["attempt_count"] >= max_attempts:
            persistence.record_pair_failure(
                job_id, pair.pair_id, "failed_terminal", "retry_exhausted",
                f"Retryable failure exhausted after {row['attempt_count']} attempts: {row.get('last_error_summary')}",
            )
            continue

        claimed = persistence.claim_pair(job_id, pair.pair_id, lease_owner)
        request: PairProviderRequest = build_pair_request(
            partition, pair, model=model_identity["name"], semantic_options=semantic_options
        )
        result = provider.judge_pair(request)
        provider_calls_made += 1

        if result.status == "provider_success":
            judgment = PairJudgment(
                pair,
                pair_judgment_identity(
                    pair,
                    evidence_identity=partition.evidence_identity,
                    partition_identity=partition.partition_id,
                    contract_version=contract_version,
                    model_identity=model_identity,
                    semantic_options=semantic_options,
                ),
                partition.evidence_identity,
                partition.partition_id,
                contract_version,
                model_identity,
                semantic_options,
                result.decision,
                result.reason,
            )
            persistence.store_validated_judgment(job_id, judgment)
        elif result.status == "terminal_failure":
            persistence.record_pair_failure(
                job_id, pair.pair_id, "failed_terminal",
                result.error_classification or "terminal_failure",
                result.error_summary or "Terminal provider failure",
            )
        else:
            if claimed["attempt_count"] >= max_attempts:
                persistence.record_pair_failure(
                    job_id, pair.pair_id, "failed_terminal", "retry_exhausted",
                    f"Retryable failure exhausted after {claimed['attempt_count']} attempts: {result.error_summary}",
                )
            else:
                persistence.record_pair_failure(
                    job_id, pair.pair_id, "failed_retryable",
                    result.error_classification or "retryable_failure",
                    result.error_summary or "Retryable provider failure",
                )

    progress = persistence.job_progress(job_id)

    if progress["failed_pair_count"] > 0:
        pair_rows = persistence.load_pair_rows(job_id)
        status = (
            STATUS_BLOCKED_TERMINAL_FAILURE
            if any(pair_row["status"] == "failed_terminal" for pair_row in pair_rows)
            else STATUS_INCOMPLETE
        )
        return OrchestrationResult(
            job_id, job["consolidation_identity"], partition.partition_id, partition.expected_pair_count,
            provider_calls_made, status, progress,
        )

    if progress["completed_validated_pair_count"] == partition.expected_pair_count:
        containers, topology = persistence.finalize_topology(job_id, partition)
        return OrchestrationResult(
            job_id, job["consolidation_identity"], partition.partition_id, partition.expected_pair_count,
            provider_calls_made, STATUS_TOPOLOGY_VALIDATED, persistence.job_progress(job_id), topology, tuple(containers),
        )

    return OrchestrationResult(
        job_id, job["consolidation_identity"], partition.partition_id, partition.expected_pair_count,
        provider_calls_made, STATUS_INCOMPLETE, progress,
    )
