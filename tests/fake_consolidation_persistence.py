"""In-memory fake persistence double for offline M004.6.12 workflow tests.

Mirrors the public `ConsolidationPersistence` API and reuses the same production identity
functions, transition table, and complete-link assembly, but stores state in plain Python
dicts instead of PostgreSQL. This lets cache-reuse/resume/budget-distribution/aggregation
behavior be tested without a live database, while genuine persistence-integration behavior
is still separately proven against real PostgreSQL 17 in `tests/test_m004612_postgres_isolated.py`.
"""

from __future__ import annotations

import itertools
from typing import Any, Mapping

from vocab_consolidation import (
    CONTAINER_CONTRACT,
    PairJudgment,
    assemble_complete_link,
    enumerate_pairs,
    pair_judgment_identity,
    pair_judgment_result_identity,
)
from vocab_consolidation_persistence import JOB_CONTRACT, PAIR_TRANSITIONS, TOPOLOGY_CONTRACT, consolidation_identity


class FakeConsolidationPersistence:
    def __init__(self):
        self._jobs: dict[str, dict[str, Any]] = {}
        self._jobs_by_id: dict[int, dict[str, Any]] = {}
        self._pairs: dict[int, dict[str, dict[str, Any]]] = {}
        self._containers: dict[int, list[dict[str, Any]]] = {}
        self._ids = itertools.count(1)

    def _manifest(self, partition):
        return {
            "pos": partition.pos,
            "material_partition": list(partition.material_partition),
            "source_sense_ids": [member["sense_id"] for member in partition.members],
        }

    def create_or_get_job(self, partition, *, lexical_dataset_identity, model_identity, semantic_options, contract_version="pair-judgment-v1-exhaustive-qwen"):
        identity = consolidation_identity(
            partition, lexical_dataset_identity=lexical_dataset_identity, model_identity=model_identity,
            semantic_options=semantic_options, contract_version=contract_version,
        )
        manifest = self._manifest(partition)
        if identity not in self._jobs:
            job_id = next(self._ids)
            job = {
                "id": job_id, "consolidation_identity": identity, "partition_identity": partition.partition_id,
                "partition_manifest": manifest, "pair_judgment_contract_version": contract_version,
                "semantic_model_identity": dict(model_identity), "semantic_options_identity": dict(semantic_options),
                "topology_contract_version": TOPOLOGY_CONTRACT, "container_contract_version": CONTAINER_CONTRACT,
                "expected_pair_count": partition.expected_pair_count, "status": "pending", "topology_identity": None,
            }
            self._jobs[identity] = job
            self._jobs_by_id[job_id] = job
            self._pairs[job_id] = {}
            self._containers[job_id] = []
        job = self._jobs[identity]
        if job["partition_identity"] != partition.partition_id or job["partition_manifest"] != manifest:
            raise ValueError("Consolidation identity conflicts with an incompatible partition manifest")
        return job

    def initialize_pairs(self, job_id, partition):
        job = self._jobs_by_id[job_id]
        if job["partition_identity"] != partition.partition_id or job["partition_manifest"] != self._manifest(partition):
            raise ValueError("Cannot initialize an incompatible partition on an existing job")
        pairs = self._pairs[job_id]
        for pair in enumerate_pairs(partition):
            if pair.pair_id in pairs:
                continue
            judgment_identity = pair_judgment_identity(
                pair, evidence_identity=partition.evidence_identity, partition_identity=partition.partition_id,
                contract_version=job["pair_judgment_contract_version"], model_identity=job["semantic_model_identity"],
                semantic_options=job["semantic_options_identity"],
            )
            pairs[pair.pair_id] = {
                "logical_pair_id": pair.pair_id, "source_sense_id_a": pair.source_sense_id_a,
                "source_sense_id_b": pair.source_sense_id_b, "pair_judgment_identity": judgment_identity,
                "pair_judgment_contract_version": job["pair_judgment_contract_version"],
                "semantic_model_identity": job["semantic_model_identity"], "semantic_options_identity": job["semantic_options_identity"],
                "evidence_set_hash": partition.evidence_identity, "status": "pending", "attempt_count": 0,
                "lease_owner": None, "lease_expires_at": None, "decision": None, "reason": None,
                "validated_result_identity": None, "last_error_classification": None, "last_error_summary": None,
            }
        expected_ids = {pair.pair_id for pair in enumerate_pairs(partition)}
        if set(pairs) != expected_ids:
            raise ValueError("Existing pair ledger does not match the immutable expected pair set")
        return [dict(pairs[pair_id]) for pair_id in sorted(pairs)]

    def load_pair_rows(self, job_id):
        return [dict(row) for _, row in sorted(self._pairs[job_id].items())]

    def claim_pair(self, job_id, logical_pair_id, lease_owner, lease_seconds=300):
        row = self._pairs[job_id][logical_pair_id]
        if row["status"] not in {"pending", "failed_retryable"}:
            raise ValueError(f"Illegal pair transition: {row['status']} -> running")
        row["status"] = "running"
        row["attempt_count"] += 1
        row["lease_owner"] = lease_owner
        row["last_error_classification"] = None
        row["last_error_summary"] = None
        return dict(row)

    def store_validated_judgment(self, job_id, judgment: PairJudgment):
        row = self._pairs[job_id][judgment.pair.pair_id]
        result_identity = pair_judgment_result_identity(judgment)
        if row["status"] == "succeeded_validated":
            return dict(row)
        if row["status"] not in PAIR_TRANSITIONS or "succeeded_validated" not in PAIR_TRANSITIONS[row["status"]]:
            raise ValueError(f"Illegal pair transition: {row['status']} -> succeeded_validated")
        row.update(status="succeeded_validated", decision=judgment.decision, reason=judgment.reason,
                   validated_result_identity=result_identity, lease_owner=None)
        return dict(row)

    def record_pair_failure(self, job_id, logical_pair_id, status, classification, summary):
        row = self._pairs[job_id][logical_pair_id]
        if status not in PAIR_TRANSITIONS.get(row["status"], frozenset()):
            raise ValueError(f"Illegal pair transition to {status}")
        row.update(status=status, lease_owner=None, last_error_classification=classification, last_error_summary=summary)
        return dict(row)

    def list_resumable_pairs(self, job_id):
        return [dict(row) for _, row in sorted(self._pairs[job_id].items())
                if row["status"] in {"pending", "failed_retryable"}]

    def job_progress(self, job_id):
        rows = self._pairs[job_id].values()
        return {
            "initialized_pair_count": len(rows),
            "completed_validated_pair_count": sum(1 for row in rows if row["status"] == "succeeded_validated"),
            "failed_pair_count": sum(1 for row in rows if row["status"] in {"failed_retryable", "failed_terminal"}),
        }

    def finalize_topology(self, job_id, partition):
        job = self._jobs_by_id[job_id]
        if job["status"] == "topology_validated":
            return list(self._containers[job_id]), job["topology_identity"]
        judgments = []
        for pair in enumerate_pairs(partition):
            row = self._pairs[job_id][pair.pair_id]
            if row["status"] != "succeeded_validated":
                continue
            judgments.append(PairJudgment(
                pair, row["pair_judgment_identity"], row["evidence_set_hash"], partition.partition_id,
                row["pair_judgment_contract_version"], row["semantic_model_identity"], row["semantic_options_identity"],
                row["decision"], row["reason"],
            ))
        containers, topology = assemble_complete_link(
            partition, judgments, model_identity=job["semantic_model_identity"],
            semantic_options=job["semantic_options_identity"], contract_version=job["pair_judgment_contract_version"],
        )
        container_rows = [
            {"container_identity": container.container_id, "member_source_sense_ids": list(container.source_sense_ids),
             "topology_identity": topology, "container_contract_version": CONTAINER_CONTRACT}
            for container in containers
        ]
        self._containers[job_id] = container_rows
        job["status"] = "topology_validated"
        job["topology_identity"] = topology
        return list(container_rows), topology

    def load_validated_containers(self, job_id):
        job = self._jobs_by_id[job_id]
        if job["status"] != "topology_validated":
            return []
        return list(self._containers[job_id])
