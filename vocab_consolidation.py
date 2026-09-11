"""Provider-independent domain foundation for pairwise lexical consolidation."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from vocab_lexical_engine import canonical_json, evidence_set_hash, sha256_text
from vocab_synthesis import MATERIAL_LABELS


PAIR_JUDGMENT_CONTRACT = "pair-judgment-v1-exhaustive-qwen"
LOGICAL_PAIR_SCHEMA_VERSION = "sense-pair-v1"
TOPOLOGY_CONTRACT = "complete-link-v1"
CONTAINER_CONTRACT = "learner-containers-v1"
DECISIONS = frozenset({"merge", "keep_separate", "uncertain"})
REASONS = (
    "paraphrase_or_duplicate",
    "contextual_variant",
    "specialized_subsense",
    "broader_or_narrower",
    "related_but_distinct",
    "materially_different",
    "insufficient_evidence",
)
INCONSISTENT_DECISIONS = frozenset({
    ("merge", "specialized_subsense"),
    ("merge", "broader_or_narrower"),
    ("merge", "related_but_distinct"),
    ("merge", "materially_different"),
})


def _hash(value: Any) -> str:
    return sha256_text(canonical_json(value))


def _ordered_senses(evidence: Mapping[str, Any]) -> list[dict[str, Any]]:
    senses = [
        {**sense, "part_of_speech": entry["part_of_speech"]}
        for entry in evidence.get("entries", [])
        for sense in entry.get("senses", [])
    ]
    return sorted(senses, key=lambda sense: (sense.get("source_order", 0), sense["sense_id"]))


def _material_signature(sense: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(sorted(set(sense.get("labels", [])) & MATERIAL_LABELS))


@dataclass(frozen=True)
class ConsolidationPartition:
    normalized_lemma: str
    pos: str
    material_partition: tuple[str, ...]
    evidence_identity: str
    members: tuple[dict[str, Any], ...]
    partition_id: str

    @classmethod
    def create(
        cls,
        normalized_lemma: str,
        pos: str,
        material_partition: tuple[str, ...],
        evidence_identity: str,
        members: Iterable[Mapping[str, Any]],
    ) -> "ConsolidationPartition":
        ordered = tuple(dict(member) for member in members)
        if not ordered:
            raise ValueError("A consolidation partition must contain at least one source sense")
        member_ids = [member["sense_id"] for member in ordered]
        if len(member_ids) != len(set(member_ids)):
            raise ValueError("Partition source-sense IDs must be unique")
        partition_payload = {
            "contract": "partition-v1",
            "normalized_lemma": normalized_lemma,
            "pos": pos,
            "material_partition": list(material_partition),
            "evidence_identity": evidence_identity,
            "source_sense_ids": member_ids,
        }
        return cls(
            normalized_lemma,
            pos,
            material_partition,
            evidence_identity,
            ordered,
            _hash(partition_payload),
        )

    @property
    def aliases(self) -> dict[str, str]:
        return {f"S{index:03d}": member["sense_id"] for index, member in enumerate(self.members, 1)}

    @property
    def reverse_aliases(self) -> dict[str, str]:
        return {source_id: alias for alias, source_id in self.aliases.items()}

    @property
    def expected_pair_count(self) -> int:
        count = len(self.members)
        return count * (count - 1) // 2


def build_partitions(evidence: Mapping[str, Any]) -> tuple[ConsolidationPartition, ...]:
    """Build the existing material-label partitions without mutating evidence."""
    identity = evidence_set_hash(dict(evidence))
    groups: dict[tuple[str, tuple[str, ...]], list[dict[str, Any]]] = {}
    for sense in _ordered_senses(evidence):
        key = (sense["part_of_speech"], _material_signature(sense))
        groups.setdefault(key, []).append(sense)
    return tuple(
        ConsolidationPartition.create(
            evidence["normalized_lemma"],
            pos,
            material,
            identity,
            members,
        )
        for (pos, material), members in sorted(groups.items())
    )


@dataclass(frozen=True)
class SensePair:
    partition_id: str
    source_sense_id_a: str
    source_sense_id_b: str
    pair_id: str

    @classmethod
    def create(cls, partition: ConsolidationPartition, first: str, second: str) -> "SensePair":
        ordered = tuple(sorted((first, second)))
        if ordered[0] == ordered[1]:
            raise ValueError("A semantic pair cannot contain the same source sense twice")
        if set(ordered) - {member["sense_id"] for member in partition.members}:
            raise ValueError("Semantic pair contains a source sense outside its partition")
        pair_id = _hash({
            "logical_pair_schema_version": LOGICAL_PAIR_SCHEMA_VERSION,
            "partition_id": partition.partition_id,
            "source_sense_ids": list(ordered),
        })
        return cls(partition.partition_id, ordered[0], ordered[1], pair_id)

    @property
    def source_sense_ids(self) -> tuple[str, str]:
        return self.source_sense_id_a, self.source_sense_id_b


def enumerate_pairs(partition: ConsolidationPartition) -> tuple[SensePair, ...]:
    pairs = [
        SensePair.create(partition, first["sense_id"], second["sense_id"])
        for index, first in enumerate(partition.members)
        for second in partition.members[index + 1 :]
    ]
    return tuple(sorted(pairs, key=lambda pair: pair.source_sense_ids))


def pair_judgment_identity(
    pair: SensePair,
    *,
    evidence_identity: str,
    partition_identity: str,
    contract_version: str = PAIR_JUDGMENT_CONTRACT,
    model_identity: Mapping[str, Any],
    semantic_options: Mapping[str, Any],
) -> str:
    return _hash({
        "logical_pair_id": pair.pair_id,
        "evidence_identity": evidence_identity,
        "partition_identity": partition_identity,
        "pair_judgment_contract_version": contract_version,
        "semantic_model_identity": dict(model_identity),
        "semantic_options_identity": dict(semantic_options),
    })


def validate_decision_reason(decision: str, reason: str) -> None:
    if decision not in DECISIONS:
        raise ValueError(f"Invalid pair decision: {decision}")
    if reason not in REASONS:
        raise ValueError(f"Invalid pair reason: {reason}")
    if (decision, reason) in INCONSISTENT_DECISIONS:
        raise ValueError(f"Incompatible pair decision/reason: {decision}/{reason}")


@dataclass(frozen=True)
class PairJudgment:
    pair: SensePair
    judgment_identity: str
    evidence_identity: str
    partition_identity: str
    contract_version: str
    model_identity: Mapping[str, Any]
    semantic_options: Mapping[str, Any]
    decision: str
    reason: str
    status: str = "succeeded_validated"

    def __post_init__(self) -> None:
        validate_decision_reason(self.decision, self.reason)
        if self.status != "succeeded_validated":
            raise ValueError("Only succeeded_validated judgments can be represented by this domain object")


def pair_judgment_result_identity(judgment: PairJudgment) -> str:
    if judgment.status != "succeeded_validated":
        raise ValueError("Only succeeded_validated judgments have a result identity")
    return _hash({
        "pair_judgment_identity": judgment.judgment_identity,
        "decision": judgment.decision,
        "reason": judgment.reason,
    })


class CoverageError(ValueError):
    """Raised when pair judgments cannot authorize topology."""

    def __init__(self, diagnostics: dict[str, Any]):
        super().__init__("Pair judgment coverage is incomplete or incompatible")
        self.diagnostics = diagnostics


def validate_pair_coverage(
    partition: ConsolidationPartition,
    judgments: Iterable[PairJudgment],
    *,
    model_identity: Mapping[str, Any],
    semantic_options: Mapping[str, Any],
    contract_version: str = PAIR_JUDGMENT_CONTRACT,
) -> dict[str, PairJudgment]:
    judgments = tuple(judgments)
    expected = {pair.pair_id: pair for pair in enumerate_pairs(partition)}
    actual: dict[str, PairJudgment] = {}
    duplicate_ids: list[str] = []
    foreign_ids: list[str] = []
    incompatible_ids: list[str] = []
    for judgment in judgments:
        pair_id = judgment.pair.pair_id
        if pair_id in actual:
            duplicate_ids.append(pair_id)
        actual[pair_id] = judgment
        expected_pair = expected.get(pair_id)
        expected_identity = expected_pair and pair_id == judgment.pair.pair_id
        compatible = (
            expected_identity
            and judgment.pair.partition_id == partition.partition_id
            and judgment.evidence_identity == partition.evidence_identity
            and judgment.partition_identity == partition.partition_id
            and judgment.contract_version == contract_version
            and dict(judgment.model_identity) == dict(model_identity)
            and dict(judgment.semantic_options) == dict(semantic_options)
            and judgment.judgment_identity == pair_judgment_identity(
                judgment.pair,
                evidence_identity=partition.evidence_identity,
                partition_identity=partition.partition_id,
                contract_version=contract_version,
                model_identity=model_identity,
                semantic_options=semantic_options,
            )
        )
        if not expected_identity:
            foreign_ids.append(pair_id)
        elif not compatible:
            incompatible_ids.append(pair_id)
    missing_ids = sorted(set(expected) - set(actual))
    diagnostics = {
        "expected_pair_count": len(expected),
        "actual_judgment_count": len(judgments),
        "missing_pair_ids": missing_ids,
        "duplicate_pair_ids": sorted(set(duplicate_ids)),
        "foreign_pair_ids": sorted(set(foreign_ids)),
        "incompatible_pair_ids": sorted(set(incompatible_ids)),
    }
    if any(diagnostics[key] for key in ("missing_pair_ids", "duplicate_pair_ids", "foreign_pair_ids", "incompatible_pair_ids")):
        raise CoverageError(diagnostics)
    return actual


@dataclass(frozen=True)
class LearnerContainer:
    container_id: str
    partition_id: str
    source_sense_ids: tuple[str, ...]


def topology_identity(
    partition: ConsolidationPartition,
    judgments: Mapping[str, PairJudgment],
) -> str:
    return _hash({
        "partition_id": partition.partition_id,
        "pair_judgment_result_identities": sorted(
            pair_judgment_result_identity(judgment) for judgment in judgments.values()
        ),
        "topology_contract": TOPOLOGY_CONTRACT,
        "container_contract": CONTAINER_CONTRACT,
    })


def _container_id(partition_id: str, members: tuple[str, ...]) -> str:
    return _hash({
        "partition_id": partition_id,
        "member_source_sense_ids": list(members),
        "container_contract": CONTAINER_CONTRACT,
    })


def assemble_complete_link(
    partition: ConsolidationPartition,
    judgments: Iterable[PairJudgment],
    *,
    model_identity: Mapping[str, Any],
    semantic_options: Mapping[str, Any],
    contract_version: str = PAIR_JUDGMENT_CONTRACT,
) -> tuple[tuple[LearnerContainer, ...], str]:
    validated = validate_pair_coverage(
        partition,
        judgments,
        model_identity=model_identity,
        semantic_options=semantic_options,
        contract_version=contract_version,
    )
    by_ids = {frozenset(pair.source_sense_ids): judgment for pair, judgment in ((item.pair, item) for item in validated.values())}
    containers = [(member["sense_id"],) for member in partition.members]
    while True:
        containers = sorted(containers)
        merged = False
        for left_index, left in enumerate(containers):
            for right in containers[left_index + 1 :]:
                cross_pairs = (
                    (left_id, right_id)
                    for left_id in left
                    for right_id in right
                )
                if all(by_ids[frozenset(pair)].decision == "merge" for pair in cross_pairs):
                    combined = tuple(sorted(left + right))
                    containers.remove(left)
                    containers.remove(right)
                    containers.append(combined)
                    merged = True
                    break
            if merged:
                break
        if not merged:
            break
    result = tuple(
        LearnerContainer(_container_id(partition.partition_id, members), partition.partition_id, members)
        for members in sorted(containers)
    )
    covered = [source_id for container in result for source_id in container.source_sense_ids]
    expected = [member["sense_id"] for member in partition.members]
    if sorted(covered) != sorted(expected) or len(covered) != len(set(covered)):
        raise ValueError("Complete-link output failed exact source-sense coverage")
    return result, topology_identity(partition, validated)
