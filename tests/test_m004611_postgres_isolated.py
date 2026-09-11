import os
import unittest
import uuid
from importlib.util import find_spec

from vocab_consolidation_provider import PairProviderRequest, PairProviderResult


class FakePairProvider:
    """Deterministic offline stand-in for `QwenPairProvider`. Each entry in `script` is either
    a `(decision, reason)` tuple (a `provider_success`) or a `PairProviderResult` for
    finer-grained control (retryable/terminal failures). Falls back to `default` when the
    script is exhausted for a given pair."""

    def __init__(self, script=None, default=("merge", "paraphrase_or_duplicate")):
        self.script = dict(script or {})
        self.default = default
        self.calls = []

    def judge_pair(self, request: PairProviderRequest) -> PairProviderResult:
        self.calls.append(request.pair.pair_id)
        queue = self.script.get(request.pair.pair_id)
        if queue:
            item = queue.pop(0)
        else:
            item = self.default
        if isinstance(item, PairProviderResult):
            return item
        decision, reason = item
        return PairProviderResult("provider_success", decision=decision, reason=reason)


@unittest.skipUnless(os.environ.get("M004611_TEST_DATABASE_URL") and find_spec("psycopg"), "set M004611_TEST_DATABASE_URL and install psycopg for isolated PostgreSQL tests")
class IsolatedPostgresM004611Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        from vocab_migrations import apply_migrations

        cls.database_url = os.environ["M004611_TEST_DATABASE_URL"]
        cls.connection = psycopg.connect(cls.database_url)
        apply_migrations(cls.connection)

    @classmethod
    def tearDownClass(cls):
        cls.connection.close()

    def _partition(self, count=3):
        from vocab_consolidation import build_partitions

        token = uuid.uuid4().hex
        evidence = {
            "normalized_lemma": f"orch-{token}",
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

    def _persistence(self):
        from vocab_consolidation_persistence import ConsolidationPersistence

        return ConsolidationPersistence(self.connection)

    def test_one_sense_partition_finalizes_with_zero_provider_calls(self):
        from vocab_consolidation_orchestrator import run_partition_consolidation

        partition = self._partition(1)
        dataset, model, options = self._identities()
        provider = FakePairProvider()
        result = run_partition_consolidation(
            self._persistence(), partition, provider,
            lexical_dataset_identity=dataset, model_identity=model, semantic_options=options,
        )
        self.assertEqual(result.status, "topology_validated")
        self.assertEqual(result.provider_calls_made, 0)
        self.assertEqual(provider.calls, [])
        self.assertEqual(len(result.containers), 1)

    def test_multi_pair_partition_completes_and_finalizes_topology(self):
        from vocab_consolidation_orchestrator import run_partition_consolidation

        partition = self._partition(3)
        dataset, model, options = self._identities()
        provider = FakePairProvider(default=("keep_separate", "materially_different"))
        result = run_partition_consolidation(
            self._persistence(), partition, provider,
            lexical_dataset_identity=dataset, model_identity=model, semantic_options=options,
        )
        self.assertEqual(result.status, "topology_validated")
        self.assertEqual(result.provider_calls_made, 3)
        self.assertEqual(len(result.containers), 3)

    def test_completed_job_replay_makes_zero_additional_provider_calls(self):
        from vocab_consolidation_orchestrator import run_partition_consolidation

        partition = self._partition(2)
        dataset, model, options = self._identities()
        provider = FakePairProvider(default=("merge", "paraphrase_or_duplicate"))
        first = run_partition_consolidation(
            self._persistence(), partition, provider,
            lexical_dataset_identity=dataset, model_identity=model, semantic_options=options,
        )
        self.assertEqual(first.status, "topology_validated")
        self.assertEqual(first.provider_calls_made, 1)

        replay_provider = FakePairProvider()
        second = run_partition_consolidation(
            self._persistence(), partition, replay_provider,
            lexical_dataset_identity=dataset, model_identity=model, semantic_options=options,
        )
        self.assertEqual(second.status, "already_complete")
        self.assertEqual(second.provider_calls_made, 0)
        self.assertEqual(replay_provider.calls, [])
        self.assertEqual(second.topology_identity, first.topology_identity)

    def test_retryable_failure_then_success_resumes_and_completes(self):
        from vocab_consolidation import enumerate_pairs
        from vocab_consolidation_orchestrator import run_partition_consolidation

        partition = self._partition(2)
        pair_id = enumerate_pairs(partition)[0].pair_id
        dataset, model, options = self._identities()
        provider = FakePairProvider(script={
            pair_id: [PairProviderResult("retryable_failure", error_classification="timeout", error_summary="boom")],
        }, default=("merge", "paraphrase_or_duplicate"))

        first = run_partition_consolidation(
            self._persistence(), partition, provider,
            lexical_dataset_identity=dataset, model_identity=model, semantic_options=options,
        )
        self.assertEqual(first.status, "incomplete")
        self.assertEqual(first.progress["failed_pair_count"], 1)

        second = run_partition_consolidation(
            self._persistence(), partition, provider,
            lexical_dataset_identity=dataset, model_identity=model, semantic_options=options,
        )
        self.assertEqual(second.status, "topology_validated")

    def test_terminal_failure_blocks_topology_finalization(self):
        from vocab_consolidation import enumerate_pairs
        from vocab_consolidation_orchestrator import run_partition_consolidation

        partition = self._partition(2)
        pair_id = enumerate_pairs(partition)[0].pair_id
        dataset, model, options = self._identities()
        provider = FakePairProvider(script={
            pair_id: [PairProviderResult("terminal_failure", error_classification="model_unavailable", error_summary="gone")],
        })

        result = run_partition_consolidation(
            self._persistence(), partition, provider,
            lexical_dataset_identity=dataset, model_identity=model, semantic_options=options,
        )
        self.assertEqual(result.status, "blocked_terminal_failure")
        self.assertIsNone(result.topology_identity)

        # A subsequent run must not finalize while a terminal failure remains outstanding.
        again = run_partition_consolidation(
            self._persistence(), partition, FakePairProvider(),
            lexical_dataset_identity=dataset, model_identity=model, semantic_options=options,
        )
        self.assertEqual(again.status, "blocked_terminal_failure")

    def test_retry_exhaustion_escalates_to_terminal_after_max_attempts(self):
        from vocab_consolidation import enumerate_pairs
        from vocab_consolidation_orchestrator import run_partition_consolidation

        partition = self._partition(2)
        pair_id = enumerate_pairs(partition)[0].pair_id
        dataset, model, options = self._identities()
        retryable = PairProviderResult("retryable_failure", error_classification="timeout", error_summary="boom")
        provider = FakePairProvider(script={pair_id: [retryable, retryable, retryable]})

        result = None
        for _ in range(4):
            result = run_partition_consolidation(
                self._persistence(), partition, provider,
                lexical_dataset_identity=dataset, model_identity=model, semantic_options=options,
                max_attempts=2,
            )
            if result.status != "incomplete":
                break
        self.assertEqual(result.status, "blocked_terminal_failure")

    def test_uncertain_decision_completes_coverage_and_creates_separate_containers(self):
        from vocab_consolidation_orchestrator import run_partition_consolidation

        partition = self._partition(2)
        dataset, model, options = self._identities()
        provider = FakePairProvider(default=("uncertain", "insufficient_evidence"))
        result = run_partition_consolidation(
            self._persistence(), partition, provider,
            lexical_dataset_identity=dataset, model_identity=model, semantic_options=options,
        )
        self.assertEqual(result.status, "topology_validated")
        self.assertEqual(len(result.containers), 2)

    def test_duplicate_invocation_with_same_provider_is_safe(self):
        from vocab_consolidation_orchestrator import run_partition_consolidation

        partition = self._partition(3)
        dataset, model, options = self._identities()
        provider = FakePairProvider(default=("keep_separate", "related_but_distinct"))
        first = run_partition_consolidation(
            self._persistence(), partition, provider,
            lexical_dataset_identity=dataset, model_identity=model, semantic_options=options,
        )
        second = run_partition_consolidation(
            self._persistence(), partition, FakePairProvider(),
            lexical_dataset_identity=dataset, model_identity=model, semantic_options=options,
        )
        self.assertEqual(first.topology_identity, second.topology_identity)
        self.assertEqual(second.provider_calls_made, 0)

    def test_expired_lease_is_reclaimed_and_resumed(self):
        import time

        from vocab_consolidation import enumerate_pairs
        from vocab_consolidation_orchestrator import run_partition_consolidation

        partition = self._partition(2)
        pair_id = enumerate_pairs(partition)[0].pair_id
        dataset, model, options = self._identities()
        persistence = self._persistence()
        job = persistence.create_or_get_job(partition, lexical_dataset_identity=dataset, model_identity=model, semantic_options=options)
        persistence.initialize_pairs(job["id"], partition)
        # Simulate a crashed worker that claimed the pair but never completed it.
        claimed = persistence.claim_pair(job["id"], pair_id, "crashed-worker", lease_seconds=1)
        self.assertEqual(claimed["attempt_count"], 1)
        time.sleep(1.2)

        provider = FakePairProvider(default=("merge", "paraphrase_or_duplicate"))
        result = run_partition_consolidation(
            persistence, partition, provider,
            lexical_dataset_identity=dataset, model_identity=model, semantic_options=options,
        )
        self.assertEqual(result.status, "topology_validated")
        self.assertEqual(provider.calls, [pair_id])
        rows = persistence.load_pair_rows(job["id"])
        self.assertEqual(rows[0]["attempt_count"], 2)

    def test_max_pairs_bounds_provider_calls_within_one_invocation(self):
        from vocab_consolidation_orchestrator import run_partition_consolidation

        partition = self._partition(3)
        dataset, model, options = self._identities()
        provider = FakePairProvider(default=("keep_separate", "related_but_distinct"))
        result = run_partition_consolidation(
            self._persistence(), partition, provider,
            lexical_dataset_identity=dataset, model_identity=model, semantic_options=options,
            max_pairs=1,
        )
        self.assertEqual(result.provider_calls_made, 1)
        self.assertEqual(result.status, "incomplete")


if __name__ == "__main__":
    unittest.main()
