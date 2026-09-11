"""PostgreSQL persistence for the isolated pairwise-consolidation domain."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from vocab_consolidation import (
    CONTAINER_CONTRACT,
    PAIR_JUDGMENT_CONTRACT,
    TOPOLOGY_CONTRACT,
    ConsolidationPartition,
    PairJudgment,
    assemble_complete_link,
    enumerate_pairs,
    pair_judgment_identity,
    pair_judgment_result_identity,
)
from vocab_lexical_engine import canonical_json, sha256_text


JOB_CONTRACT = "consolidation-job-v1"
PAIR_STATUSES = frozenset({"pending", "running", "succeeded_validated", "failed_retryable", "failed_terminal"})
PAIR_TRANSITIONS = {
    "pending": frozenset({"running", "failed_terminal"}),
    "running": frozenset({"succeeded_validated", "failed_retryable", "failed_terminal"}),
    "failed_retryable": frozenset({"running", "failed_terminal"}),
    "failed_terminal": frozenset(),
    "succeeded_validated": frozenset(),
}


def _identity(value: Mapping[str, Any]) -> str:
    return sha256_text(canonical_json(dict(value)))


def consolidation_identity(
    partition: ConsolidationPartition,
    *,
    lexical_dataset_identity: Mapping[str, Any],
    model_identity: Mapping[str, Any],
    semantic_options: Mapping[str, Any],
    contract_version: str = PAIR_JUDGMENT_CONTRACT,
) -> str:
    """Return the deterministic identity for one complete partition computation."""
    return _identity({
        "consolidation_job_contract": JOB_CONTRACT,
        "normalized_lemma": partition.normalized_lemma,
        "evidence_set_hash": partition.evidence_identity,
        "lexical_dataset_identity": dict(lexical_dataset_identity),
        "partition_identity": partition.partition_id,
        "pair_judgment_contract_version": contract_version,
        "semantic_model_identity": dict(model_identity),
        "semantic_options_identity": dict(semantic_options),
        "topology_contract_version": TOPOLOGY_CONTRACT,
        "container_contract_version": CONTAINER_CONTRACT,
    })


class ConsolidationPersistence:
    """Narrow, transaction-safe ledger for one-job-per-partition consolidation."""

    def __init__(self, connection: Any):
        self.connection = connection

    @staticmethod
    def _row(cursor: Any, row: Any) -> dict[str, Any] | None:
        if row is None:
            return None
        if isinstance(row, Mapping):
            return dict(row)
        return dict(zip((column.name for column in cursor.description), row))

    def _fetchone(self, cursor: Any) -> dict[str, Any] | None:
        return self._row(cursor, cursor.fetchone())

    def _fetchall(self, cursor: Any) -> list[dict[str, Any]]:
        return [self._row(cursor, row) for row in cursor.fetchall()]

    @staticmethod
    def _manifest(partition: ConsolidationPartition) -> dict[str, Any]:
        return {
            "pos": partition.pos,
            "material_partition": list(partition.material_partition),
            "source_sense_ids": [member["sense_id"] for member in partition.members],
        }

    def create_or_get_job(
        self,
        partition: ConsolidationPartition,
        *,
        lexical_dataset_identity: Mapping[str, Any],
        model_identity: Mapping[str, Any],
        semantic_options: Mapping[str, Any],
        contract_version: str = PAIR_JUDGMENT_CONTRACT,
    ) -> dict[str, Any]:
        identity = consolidation_identity(
            partition,
            lexical_dataset_identity=lexical_dataset_identity,
            model_identity=model_identity,
            semantic_options=semantic_options,
            contract_version=contract_version,
        )
        manifest = self._manifest(partition)
        with self.connection.transaction():
            with self.connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO lexical_consolidation_jobs
                    (consolidation_identity, normalized_lemma, evidence_set_hash, lexical_dataset_identity,
                     partition_identity, partition_manifest, pair_judgment_contract_version,
                     semantic_model_identity, semantic_options_identity, topology_contract_version,
                     container_contract_version, expected_pair_count)
                    VALUES (%s, %s, %s, %s::jsonb, %s, %s::jsonb, %s, %s::jsonb, %s::jsonb, %s, %s, %s)
                    ON CONFLICT (consolidation_identity) DO NOTHING""",
                    (identity, partition.normalized_lemma, partition.evidence_identity,
                     json.dumps(dict(lexical_dataset_identity)), partition.partition_id, json.dumps(manifest),
                     contract_version, json.dumps(dict(model_identity)), json.dumps(dict(semantic_options)),
                     TOPOLOGY_CONTRACT, CONTAINER_CONTRACT, partition.expected_pair_count),
                )
                cursor.execute("SELECT * FROM lexical_consolidation_jobs WHERE consolidation_identity=%s FOR UPDATE", (identity,))
                job = self._fetchone(cursor)
                if job is None or job["partition_identity"] != partition.partition_id or job["partition_manifest"] != manifest:
                    raise ValueError("Consolidation identity conflicts with an incompatible partition manifest")
        return job

    def initialize_pairs(self, job_id: int, partition: ConsolidationPartition) -> list[dict[str, Any]]:
        """Persist exactly the expected structural pairs, without mutating an existing ledger."""
        with self.connection.transaction():
            with self.connection.cursor() as cursor:
                cursor.execute("SELECT * FROM lexical_consolidation_jobs WHERE id=%s FOR UPDATE", (job_id,))
                job = self._fetchone(cursor)
                if job is None:
                    raise ValueError("Consolidation job does not exist")
                if job["partition_identity"] != partition.partition_id or job["partition_manifest"] != self._manifest(partition):
                    raise ValueError("Cannot initialize an incompatible partition on an existing job")
                for pair in enumerate_pairs(partition):
                    judgment_identity = pair_judgment_identity(
                        pair, evidence_identity=partition.evidence_identity, partition_identity=partition.partition_id,
                        contract_version=job["pair_judgment_contract_version"],
                        model_identity=job["semantic_model_identity"], semantic_options=job["semantic_options_identity"],
                    )
                    cursor.execute(
                        """INSERT INTO lexical_pair_judgments
                        (consolidation_job_id, partition_identity, logical_pair_id, source_sense_id_a, source_sense_id_b,
                         pair_judgment_identity, pair_judgment_contract_version, semantic_model_identity,
                         semantic_options_identity, evidence_set_hash)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s)
                        ON CONFLICT (consolidation_job_id, logical_pair_id) DO NOTHING""",
                        (job_id, partition.partition_id, pair.pair_id, pair.source_sense_id_a, pair.source_sense_id_b,
                         judgment_identity, job["pair_judgment_contract_version"],
                         json.dumps(job["semantic_model_identity"]), json.dumps(job["semantic_options_identity"]),
                         partition.evidence_identity),
                    )
                cursor.execute("SELECT * FROM lexical_pair_judgments WHERE consolidation_job_id=%s ORDER BY logical_pair_id", (job_id,))
                rows = self._fetchall(cursor)
                expected_ids = {pair.pair_id for pair in enumerate_pairs(partition)}
                if {row["logical_pair_id"] for row in rows} != expected_ids:
                    raise ValueError("Existing pair ledger does not match the immutable expected pair set")
        return rows

    def load_job(self, identity: str) -> dict[str, Any] | None:
        with self.connection.transaction():
            with self.connection.cursor() as cursor:
                cursor.execute("SELECT * FROM lexical_consolidation_jobs WHERE consolidation_identity=%s", (identity,))
                return self._fetchone(cursor)

    def load_pair_rows(self, job_id: int) -> list[dict[str, Any]]:
        with self.connection.transaction():
            with self.connection.cursor() as cursor:
                cursor.execute("SELECT * FROM lexical_pair_judgments WHERE consolidation_job_id=%s ORDER BY logical_pair_id", (job_id,))
                return self._fetchall(cursor)

    def claim_pair(self, job_id: int, logical_pair_id: str, lease_owner: str, lease_seconds: int = 300) -> dict[str, Any]:
        if not lease_owner or lease_seconds <= 0:
            raise ValueError("Lease owner and positive lease duration are required")
        with self.connection.transaction():
            with self.connection.cursor() as cursor:
                cursor.execute("SELECT * FROM lexical_pair_judgments WHERE consolidation_job_id=%s AND logical_pair_id=%s FOR UPDATE", (job_id, logical_pair_id))
                row = self._fetchone(cursor)
                if row is None:
                    raise ValueError("Pair judgment does not exist")
                if row["status"] not in {"pending", "failed_retryable"}:
                    raise ValueError(f"Illegal pair transition: {row['status']} -> running")
                cursor.execute(
                    """UPDATE lexical_pair_judgments
                    SET status='running', attempt_count=attempt_count+1, lease_owner=%s,
                        lease_acquired_at=now(), lease_expires_at=now() + %s * interval '1 second',
                        last_error_classification=NULL, last_error_summary=NULL, updated_at=now()
                    WHERE id=%s RETURNING *""",
                    (lease_owner, lease_seconds, row["id"]),
                )
                return self._fetchone(cursor)

    def store_validated_judgment(self, job_id: int, judgment: PairJudgment) -> dict[str, Any]:
        """Atomically store a validated, immutable semantic result."""
        result_identity = pair_judgment_result_identity(judgment)
        with self.connection.transaction():
            with self.connection.cursor() as cursor:
                cursor.execute("SELECT * FROM lexical_pair_judgments WHERE consolidation_job_id=%s AND logical_pair_id=%s FOR UPDATE", (job_id, judgment.pair.pair_id))
                row = self._fetchone(cursor)
                if row is None:
                    raise ValueError("Pair judgment does not exist")
                required = {
                    "partition_identity": judgment.partition_identity,
                    "pair_judgment_identity": judgment.judgment_identity,
                    "pair_judgment_contract_version": judgment.contract_version,
                    "evidence_set_hash": judgment.evidence_identity,
                }
                if any(row[key] != value for key, value in required.items()) or row["semantic_model_identity"] != dict(judgment.model_identity) or row["semantic_options_identity"] != dict(judgment.semantic_options):
                    raise ValueError("Validated judgment is incompatible with the durable pair identity")
                if row["status"] == "succeeded_validated":
                    if row["decision"] == judgment.decision and row["reason"] == judgment.reason and row["validated_result_identity"] == result_identity:
                        return row
                    raise ValueError("Successful validated judgment is immutable")
                if row["status"] not in PAIR_TRANSITIONS or "succeeded_validated" not in PAIR_TRANSITIONS[row["status"]]:
                    raise ValueError(f"Illegal pair transition: {row['status']} -> succeeded_validated")
                cursor.execute(
                    """UPDATE lexical_pair_judgments
                    SET status='succeeded_validated', decision=%s, reason=%s, validated_result_identity=%s,
                        lease_owner=NULL, lease_acquired_at=NULL, lease_expires_at=NULL, completed_at=now(), updated_at=now()
                    WHERE id=%s RETURNING *""",
                    (judgment.decision, judgment.reason, result_identity, row["id"]),
                )
                return self._fetchone(cursor)

    def record_pair_failure(self, job_id: int, logical_pair_id: str, status: str, classification: str, summary: str) -> dict[str, Any]:
        if status not in {"failed_retryable", "failed_terminal"} or not classification or not summary:
            raise ValueError("A failure status, classification, and summary are required")
        with self.connection.transaction():
            with self.connection.cursor() as cursor:
                cursor.execute("SELECT * FROM lexical_pair_judgments WHERE consolidation_job_id=%s AND logical_pair_id=%s FOR UPDATE", (job_id, logical_pair_id))
                row = self._fetchone(cursor)
                if row is None or status not in PAIR_TRANSITIONS.get(row["status"], frozenset()):
                    raise ValueError(f"Illegal pair transition to {status}")
                cursor.execute(
                    """UPDATE lexical_pair_judgments
                    SET status=%s, lease_owner=NULL, lease_acquired_at=NULL, lease_expires_at=NULL,
                        last_error_classification=%s, last_error_summary=%s, updated_at=now()
                    WHERE id=%s RETURNING *""",
                    (status, classification, summary, row["id"]),
                )
                return self._fetchone(cursor)

    def list_incomplete_jobs(self) -> list[dict[str, Any]]:
        with self.connection.transaction():
            with self.connection.cursor() as cursor:
                cursor.execute("SELECT * FROM lexical_consolidation_jobs WHERE status <> 'topology_validated' ORDER BY created_at, id")
                return self._fetchall(cursor)

    def list_resumable_pairs(self, job_id: int) -> list[dict[str, Any]]:
        with self.connection.transaction():
            with self.connection.cursor() as cursor:
                cursor.execute(
                    """SELECT * FROM lexical_pair_judgments
                    WHERE consolidation_job_id=%s
                      AND (status IN ('pending', 'failed_retryable')
                           OR (status='running' AND lease_expires_at < now()))
                    ORDER BY logical_pair_id""",
                    (job_id,),
                )
                return self._fetchall(cursor)

    def job_progress(self, job_id: int) -> dict[str, int]:
        """Derive progress from the pair ledger; job rows never own mutable counts."""
        with self.connection.transaction():
            with self.connection.cursor() as cursor:
                cursor.execute(
                    """SELECT
                        count(*) AS initialized_pair_count,
                        count(*) FILTER (WHERE status='succeeded_validated') AS completed_validated_pair_count,
                        count(*) FILTER (WHERE status IN ('failed_retryable', 'failed_terminal')) AS failed_pair_count
                    FROM lexical_pair_judgments WHERE consolidation_job_id=%s""",
                    (job_id,),
                )
                progress = self._fetchone(cursor)
                if progress is None:
                    raise ValueError("Could not derive consolidation progress")
                return {key: int(value) for key, value in progress.items()}

    def finalize_topology(self, job_id: int, partition: ConsolidationPartition) -> tuple[list[dict[str, Any]], str]:
        """Validate durable coverage and atomically publish the deterministic topology."""
        with self.connection.transaction():
            with self.connection.cursor() as cursor:
                cursor.execute("SELECT * FROM lexical_consolidation_jobs WHERE id=%s FOR UPDATE", (job_id,))
                job = self._fetchone(cursor)
                if job is None or job["partition_identity"] != partition.partition_id:
                    raise ValueError("Consolidation job is incompatible with this partition")
                if job["status"] == "topology_validated":
                    cursor.execute("SELECT * FROM lexical_consolidation_containers WHERE consolidation_job_id=%s ORDER BY container_identity", (job_id,))
                    return self._fetchall(cursor), job["topology_identity"]
                rows = self.load_pair_rows(job_id)
                judgments = []
                for row in rows:
                    if row["status"] != "succeeded_validated":
                        continue
                    pair = next((item for item in enumerate_pairs(partition) if item.pair_id == row["logical_pair_id"]), None)
                    if pair is None:
                        raise ValueError("Durable pair ledger contains a foreign logical pair")
                    judgments.append(PairJudgment(
                        pair, row["pair_judgment_identity"], row["evidence_set_hash"], row["partition_identity"],
                        row["pair_judgment_contract_version"], row["semantic_model_identity"], row["semantic_options_identity"],
                        row["decision"], row["reason"],
                    ))
                containers, topology = assemble_complete_link(
                    partition, judgments, model_identity=job["semantic_model_identity"],
                    semantic_options=job["semantic_options_identity"], contract_version=job["pair_judgment_contract_version"],
                )
                for container in containers:
                    cursor.execute(
                        """INSERT INTO lexical_consolidation_containers
                        (consolidation_job_id, partition_identity, topology_identity, container_identity,
                         member_source_sense_ids, container_contract_version)
                        VALUES (%s, %s, %s, %s, %s::jsonb, %s)""",
                        (job_id, partition.partition_id, topology, container.container_id,
                         json.dumps(list(container.source_sense_ids)), CONTAINER_CONTRACT),
                    )
                cursor.execute(
                    """UPDATE lexical_consolidation_jobs
                    SET status='topology_validated', topology_identity=%s, completed_at=now(), updated_at=now()
                    WHERE id=%s""",
                    (topology, job_id),
                )
                cursor.execute("SELECT * FROM lexical_consolidation_containers WHERE consolidation_job_id=%s ORDER BY container_identity", (job_id,))
                return self._fetchall(cursor), topology

    def load_validated_containers(self, job_id: int) -> list[dict[str, Any]]:
        with self.connection.transaction():
            with self.connection.cursor() as cursor:
                cursor.execute(
                    """SELECT c.* FROM lexical_consolidation_containers c
                    JOIN lexical_consolidation_jobs j ON j.id=c.consolidation_job_id
                    WHERE c.consolidation_job_id=%s AND j.status='topology_validated'
                    ORDER BY c.container_identity""",
                    (job_id,),
                )
                return self._fetchall(cursor)
