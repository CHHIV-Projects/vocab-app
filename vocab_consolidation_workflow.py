"""Word-level internal consolidation workflow (M004.6.12).

Composes the already-accepted M004.6.9 domain, M004.6.10 persistence, and M004.6.11
provider/orchestrator primitives into one deterministic, cache-aware, resumable
word-level consolidation result. This module owns no semantic judgment, identity,
coverage, or clustering logic of its own -- it only discovers partitions, plans work,
distributes a bounded pair-call budget across partitions in deterministic order, and
aggregates the resulting per-partition outcomes.

This is an internal foundation only. It does not produce learner-facing wording, does
not perform Core/Additional ranking, and is not wired into the Streamlit UI or the
existing `LexicalWorkflow.search()` path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from vocab_consolidation import PAIR_JUDGMENT_CONTRACT, ConsolidationPartition
from vocab_consolidation_orchestrator import (
    STATUS_ALREADY_COMPLETE,
    STATUS_BLOCKED_TERMINAL_FAILURE,
    STATUS_TOPOLOGY_VALIDATED,
    OrchestrationResult,
    lexical_dataset_identity_from_evidence,
    partitions_from_synthesis_evidence,
    run_partition_consolidation,
)
from vocab_consolidation_persistence import ConsolidationPersistence
from vocab_consolidation_provider import PairProvider

WORD_STATUS_COMPLETE = "complete"
WORD_STATUS_INCOMPLETE = "incomplete"
WORD_STATUS_BLOCKED = "blocked"

_COMPLETE_PARTITION_STATUSES = frozenset({STATUS_ALREADY_COMPLETE, STATUS_TOPOLOGY_VALIDATED})


@dataclass(frozen=True)
class PartitionConsolidationStatus:
    """Deterministic per-partition outcome, suitable for a downstream M004.6.13 consumer."""

    partition_id: str
    pos: str
    material_partition: tuple[str, ...]
    source_sense_ids: tuple[str, ...]
    expected_pair_count: int
    status: str
    provider_calls_made: int
    progress: Mapping[str, int]
    topology_identity: str | None
    containers: tuple[dict[str, Any], ...]

    @property
    def is_topology_validated(self) -> bool:
        return self.status in _COMPLETE_PARTITION_STATUSES

    @property
    def is_blocked(self) -> bool:
        return self.status == STATUS_BLOCKED_TERMINAL_FAILURE


@dataclass(frozen=True)
class WordConsolidationResult:
    """Deterministic, code-owned word-level consolidation result. Contains no learner wording."""

    normalized_lemma: str
    evidence_identity: str
    lexical_dataset_identity: Mapping[str, Any]
    partitions: tuple[PartitionConsolidationStatus, ...]
    total_expected_pair_count: int
    total_reused_pair_count: int
    total_provider_calls_made: int
    word_status: str

    @property
    def is_complete(self) -> bool:
        return self.word_status == WORD_STATUS_COMPLETE

    @property
    def is_blocked(self) -> bool:
        return self.word_status == WORD_STATUS_BLOCKED

    @property
    def validated_containers(self) -> tuple[dict[str, Any], ...]:
        """All validated containers across topology-validated partitions, in deterministic order."""
        containers: list[dict[str, Any]] = []
        for partition in self.partitions:
            if partition.is_topology_validated:
                containers.extend(partition.containers)
        return tuple(containers)


def _partition_sort_key(partition: ConsolidationPartition) -> tuple[str, tuple[str, ...], str]:
    """Deterministic, code-owned partition order: POS, then material signature, then partition_id.

    This intentionally does not reuse any learner-facing display ordering (e.g.
    `vocab_workflow.sort_pos_sections`'s `POS_PRESENTATION_ORDER`), which is a presentation
    concern. It relies only on `build_partitions()`'s own already-deterministic evidence/
    source ordering plus the partition's own stable identity.
    """
    return (partition.pos, partition.material_partition, partition.partition_id)


def plan_word_consolidation(evidence: Mapping[str, Any]) -> tuple[ConsolidationPartition, ...]:
    """Discover deterministic partitions for a word without performing any inference."""
    partitions = partitions_from_synthesis_evidence(evidence)
    return tuple(sorted(partitions, key=_partition_sort_key))


def total_expected_pair_count(partitions: tuple[ConsolidationPartition, ...]) -> int:
    return sum(partition.expected_pair_count for partition in partitions)


def _partition_status(partition: ConsolidationPartition, outcome: OrchestrationResult) -> PartitionConsolidationStatus:
    return PartitionConsolidationStatus(
        partition_id=partition.partition_id,
        pos=partition.pos,
        material_partition=partition.material_partition,
        source_sense_ids=tuple(member["sense_id"] for member in partition.members),
        expected_pair_count=partition.expected_pair_count,
        status=outcome.status,
        provider_calls_made=outcome.provider_calls_made,
        progress=outcome.progress,
        topology_identity=outcome.topology_identity,
        containers=outcome.containers,
    )


def _word_status(partitions: tuple[PartitionConsolidationStatus, ...]) -> str:
    if any(partition.is_blocked for partition in partitions):
        return WORD_STATUS_BLOCKED
    if all(partition.is_topology_validated for partition in partitions):
        return WORD_STATUS_COMPLETE
    return WORD_STATUS_INCOMPLETE


def consolidate_word_evidence(
    persistence: ConsolidationPersistence,
    evidence: Mapping[str, Any],
    provider: PairProvider,
    *,
    model_identity: Mapping[str, Any],
    semantic_options: Mapping[str, Any],
    contract_version: str = PAIR_JUDGMENT_CONTRACT,
    lease_owner: str = "m004612-word-workflow",
    max_total_pairs: int | None = None,
    max_attempts: int = 3,
) -> WordConsolidationResult:
    """Consolidate one word's canonical evidence into a deterministic, cache-aware result.

    `evidence` must already be the accepted projected synthesis evidence for exactly one
    canonical lexical lookup (i.e. the output of `vocab_synthesis.project_synthesis_evidence`).
    This function performs no independent lexical extraction.

    `max_total_pairs` bounds the number of *live provider calls* made across all partitions
    during this single invocation; it is distributed deterministically in partition order.
    Already-reused or already-resumed-from-persistence pairs never consume this budget.
    """
    from vocab_lexical_engine import evidence_set_hash

    partitions = plan_word_consolidation(evidence)
    dataset_identity = lexical_dataset_identity_from_evidence(evidence)
    evidence_identity = evidence_set_hash(dict(evidence))

    remaining_budget = max_total_pairs
    statuses: list[PartitionConsolidationStatus] = []
    total_reused = 0
    total_calls = 0

    for partition in partitions:
        partition_budget = remaining_budget
        outcome = run_partition_consolidation(
            persistence,
            partition,
            provider,
            lexical_dataset_identity=dataset_identity,
            model_identity=model_identity,
            semantic_options=semantic_options,
            contract_version=contract_version,
            lease_owner=lease_owner,
            max_pairs=partition_budget,
            max_attempts=max_attempts,
        )
        statuses.append(_partition_status(partition, outcome))
        total_calls += outcome.provider_calls_made
        # Pairs already `succeeded_validated` before/without this invocation's own provider
        # calls are "reused" work (persisted cache hits), not freshly computed work.
        total_reused += outcome.progress.get("completed_validated_pair_count", 0) - outcome.provider_calls_made
        if remaining_budget is not None:
            remaining_budget = max(0, remaining_budget - outcome.provider_calls_made)

    partitions_tuple = tuple(statuses)
    return WordConsolidationResult(
        normalized_lemma=evidence.get("normalized_lemma", ""),
        evidence_identity=evidence_identity,
        lexical_dataset_identity=dataset_identity,
        partitions=partitions_tuple,
        total_expected_pair_count=sum(status.expected_pair_count for status in partitions_tuple),
        total_reused_pair_count=total_reused,
        total_provider_calls_made=total_calls,
        word_status=_word_status(partitions_tuple),
    )
