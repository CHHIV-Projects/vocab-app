import os
import unittest
import uuid
from importlib.util import find_spec


@unittest.skipUnless(os.environ.get("M004610_TEST_DATABASE_URL") and find_spec("psycopg"), "set M004610_TEST_DATABASE_URL and install psycopg for isolated PostgreSQL tests")
class IsolatedPostgresM004610Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        from vocab_migrations import apply_migrations

        cls.database_url = os.environ["M004610_TEST_DATABASE_URL"]
        cls.connection = psycopg.connect(cls.database_url)
        apply_migrations(cls.connection)

    @classmethod
    def tearDownClass(cls):
        cls.connection.close()

    def _partition(self, count=3):
        from vocab_consolidation import build_partitions

        token = uuid.uuid4().hex
        evidence = {
            "normalized_lemma": f"persist-{token}",
            "wiktionary_versions": ["test-v1"],
            "wordnet_version": "test-wordnet",
            "entries": [{"entry_key": "entry", "part_of_speech": "noun", "senses": [
                {"sense_id": f"{token}-sense-{index}", "source_order": index, "glosses": [str(index)],
                 "labels": [], "topics": [], "examples": [], "relations": []}
                for index in range(1, count + 1)
            ]}],
            "wordnet": [],
        }
        return build_partitions(evidence)[0]

    @staticmethod
    def _identities():
        return {"dataset": "test-v1"}, {"name": "qwen3:8b", "digest": "test"}, {"think": False, "temperature": 0, "seed": 0}

    def _job(self, partition):
        from vocab_consolidation_persistence import ConsolidationPersistence

        dataset, model, options = self._identities()
        persistence = ConsolidationPersistence(self.connection)
        first = persistence.create_or_get_job(partition, lexical_dataset_identity=dataset, model_identity=model, semantic_options=options)
        second = persistence.create_or_get_job(partition, lexical_dataset_identity=dataset, model_identity=model, semantic_options=options)
        self.assertEqual(first["id"], second["id"])
        return persistence, first, model, options

    def test_migration_and_idempotent_partition_job_and_pairs(self):
        from vocab_migrations import apply_migrations

        self.assertEqual(apply_migrations(self.connection), [])
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT version FROM schema_migrations")
            self.assertIn("003_m004610_consolidation_persistence", {row[0] for row in cursor.fetchall()})
            cursor.execute("SELECT to_regclass('lexical_entries'), to_regclass('lexical_entry_versions'), to_regclass('lexical_flags')")
            self.assertEqual(tuple(cursor.fetchone()), ("lexical_entries", "lexical_entry_versions", "lexical_flags"))
        partition = self._partition()
        persistence, job, _, _ = self._job(partition)
        first = persistence.initialize_pairs(job["id"], partition)
        second = persistence.initialize_pairs(job["id"], partition)
        self.assertEqual(len(first), partition.expected_pair_count)
        self.assertEqual([row["logical_pair_id"] for row in first], [row["logical_pair_id"] for row in second])
        self.assertEqual(persistence.job_progress(job["id"]), {
            "initialized_pair_count": partition.expected_pair_count,
            "completed_validated_pair_count": 0,
            "failed_pair_count": 0,
        })

    def test_pair_transitions_success_immutability_and_resume_queries(self):
        from vocab_consolidation import PAIR_JUDGMENT_CONTRACT, PairJudgment, enumerate_pairs, pair_judgment_identity

        partition = self._partition(2)
        persistence, job, model, options = self._job(partition)
        pair_row = persistence.initialize_pairs(job["id"], partition)[0]
        self.assertEqual(len(persistence.list_resumable_pairs(job["id"])), 1)
        claimed = persistence.claim_pair(job["id"], pair_row["logical_pair_id"], "test-worker")
        self.assertEqual(claimed["status"], "running")
        pair = enumerate_pairs(partition)[0]
        judgment = PairJudgment(
            pair, pair_judgment_identity(pair, evidence_identity=partition.evidence_identity,
            partition_identity=partition.partition_id, model_identity=model, semantic_options=options),
            partition.evidence_identity, partition.partition_id, PAIR_JUDGMENT_CONTRACT, model, options,
            "merge", "paraphrase_or_duplicate",
        )
        persisted = persistence.store_validated_judgment(job["id"], judgment)
        self.assertEqual(persisted["status"], "succeeded_validated")
        self.assertEqual(persistence.job_progress(job["id"])["completed_validated_pair_count"], 1)
        self.assertEqual(persistence.store_validated_judgment(job["id"], judgment)["id"], persisted["id"])
        conflicting = PairJudgment(
            pair, judgment.judgment_identity, partition.evidence_identity, partition.partition_id,
            PAIR_JUDGMENT_CONTRACT, model, options, "uncertain", "insufficient_evidence",
        )
        with self.assertRaises(ValueError):
            persistence.store_validated_judgment(job["id"], conflicting)
        with self.assertRaises(ValueError):
            persistence.claim_pair(job["id"], pair.pair_id, "test-worker")

    def test_finalization_is_atomic_and_survives_restart(self):
        from vocab_consolidation import PAIR_JUDGMENT_CONTRACT, PairJudgment, enumerate_pairs, pair_judgment_identity

        partition = self._partition(3)
        persistence, job, model, options = self._job(partition)
        rows = persistence.initialize_pairs(job["id"], partition)
        with self.assertRaises(ValueError):
            persistence.finalize_topology(job["id"], partition)
        self.assertEqual(persistence.load_job(job["consolidation_identity"])["status"], "created")
        decisions = {
            pair.pair_id: decision
            for pair, decision in zip(enumerate_pairs(partition), ("merge", "keep_separate", "merge"))
        }
        for row in rows:
            pair = next(pair for pair in enumerate_pairs(partition) if pair.pair_id == row["logical_pair_id"])
            decision = decisions[pair.pair_id]
            persistence.claim_pair(job["id"], row["logical_pair_id"], "test-worker")
            persistence.store_validated_judgment(job["id"], PairJudgment(
                pair, pair_judgment_identity(pair, evidence_identity=partition.evidence_identity,
                partition_identity=partition.partition_id, model_identity=model, semantic_options=options),
                partition.evidence_identity, partition.partition_id, PAIR_JUDGMENT_CONTRACT, model, options,
                decision, "paraphrase_or_duplicate" if decision == "merge" else "materially_different",
            ))
        containers, topology = persistence.finalize_topology(job["id"], partition)
        self.assertEqual(sorted(row["member_source_sense_ids"] for row in containers), sorted([
            [partition.members[0]["sense_id"], partition.members[1]["sense_id"]], [partition.members[2]["sense_id"]]
        ]))
        self.assertTrue(topology)
        self.connection.close()
        import psycopg
        self.__class__.connection = psycopg.connect(self.database_url)
        reloaded = __import__("vocab_consolidation_persistence").ConsolidationPersistence(self.connection)
        self.assertEqual(reloaded.load_job(job["consolidation_identity"])["status"], "topology_validated")
        self.assertEqual(len(reloaded.load_validated_containers(job["id"])), 2)

    def test_one_sense_and_uncertain_partitions_finalize_without_provider_work(self):
        from vocab_consolidation import PAIR_JUDGMENT_CONTRACT, PairJudgment, enumerate_pairs, pair_judgment_identity

        one_sense = self._partition(1)
        persistence, job, _, _ = self._job(one_sense)
        self.assertEqual(persistence.initialize_pairs(job["id"], one_sense), [])
        containers, _ = persistence.finalize_topology(job["id"], one_sense)
        self.assertEqual(containers[0]["member_source_sense_ids"], [one_sense.members[0]["sense_id"]])

        partition = self._partition(2)
        persistence, job, model, options = self._job(partition)
        row = persistence.initialize_pairs(job["id"], partition)[0]
        persistence.claim_pair(job["id"], row["logical_pair_id"], "test-worker")
        pair = enumerate_pairs(partition)[0]
        persistence.store_validated_judgment(job["id"], PairJudgment(
            pair, pair_judgment_identity(pair, evidence_identity=partition.evidence_identity,
            partition_identity=partition.partition_id, model_identity=model, semantic_options=options),
            partition.evidence_identity, partition.partition_id, PAIR_JUDGMENT_CONTRACT, model, options,
            "uncertain", "insufficient_evidence",
        ))
        containers, _ = persistence.finalize_topology(job["id"], partition)
        self.assertEqual(len(containers), 2)

    def test_failure_and_incompatible_judgment_block_finalization(self):
        from vocab_consolidation import PAIR_JUDGMENT_CONTRACT, PairJudgment, enumerate_pairs, pair_judgment_identity

        partition = self._partition(2)
        persistence, job, model, options = self._job(partition)
        row = persistence.initialize_pairs(job["id"], partition)[0]
        persistence.claim_pair(job["id"], row["logical_pair_id"], "test-worker")
        persistence.record_pair_failure(job["id"], row["logical_pair_id"], "failed_retryable", "transport", "test failure")
        self.assertEqual(persistence.list_resumable_pairs(job["id"])[0]["status"], "failed_retryable")
        with self.assertRaises(ValueError):
            persistence.finalize_topology(job["id"], partition)
        self.assertEqual(persistence.load_validated_containers(job["id"]), [])
        self.assertEqual(persistence.load_job(job["consolidation_identity"])["status"], "created")

        persistence.claim_pair(job["id"], row["logical_pair_id"], "test-worker")
        pair = enumerate_pairs(partition)[0]
        incompatible = PairJudgment(
            pair, pair_judgment_identity(pair, evidence_identity=partition.evidence_identity,
            partition_identity=partition.partition_id, model_identity={"name": "other", "digest": "other"},
            semantic_options=options),
            partition.evidence_identity, partition.partition_id, PAIR_JUDGMENT_CONTRACT,
            {"name": "other", "digest": "other"}, options, "merge", "paraphrase_or_duplicate",
        )
        with self.assertRaises(ValueError):
            persistence.store_validated_judgment(job["id"], incompatible)


if __name__ == "__main__":
    unittest.main()
