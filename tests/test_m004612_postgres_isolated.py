import os
import unittest
import uuid
from importlib.util import find_spec

from tests.test_m004611_postgres_isolated import FakePairProvider
from vocab_consolidation_provider import PairProviderResult

MODEL = {"name": "qwen3:8b", "digest": "test-digest"}
OPTIONS = {"think": False, "temperature": 0, "seed": 5100}


def _evidence(token, senses_by_pos_and_tags):
    entries = []
    for pos, groups in senses_by_pos_and_tags.items():
        senses = []
        order = 1
        for tags, count in groups:
            for _ in range(count):
                senses.append({
                    "sense_id": f"{token}-{pos}-{'-'.join(tags) or 'plain'}-{order}",
                    "source_order": order, "glosses": [f"gloss {order}"], "tags": list(tags),
                    "topics": [], "examples": [], "relations": [],
                })
                order += 1
        entries.append({"entry_key": f"{token}-{pos}", "part_of_speech": pos, "senses": senses})
    return {
        "normalized_lemma": token, "wiktionary_versions": ["test-v1"], "wordnet_version": "test-wordnet",
        "entries": entries, "wordnet": [],
    }


@unittest.skipUnless(os.environ.get("M004612_TEST_DATABASE_URL") and find_spec("psycopg"), "set M004612_TEST_DATABASE_URL and install psycopg for isolated PostgreSQL tests")
class IsolatedPostgresM004612Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        from vocab_migrations import apply_migrations

        cls.database_url = os.environ["M004612_TEST_DATABASE_URL"]
        cls.connection = psycopg.connect(cls.database_url)
        apply_migrations(cls.connection)

    @classmethod
    def tearDownClass(cls):
        cls.connection.close()

    def _persistence(self):
        from vocab_consolidation_persistence import ConsolidationPersistence

        return ConsolidationPersistence(self.connection)

    def test_fresh_migrations_support_word_level_workflow(self):
        from vocab_consolidation_workflow import consolidate_word_evidence

        token = uuid.uuid4().hex
        evidence = _evidence(token, {"noun": [((), 1)]})
        result = consolidate_word_evidence(
            self._persistence(), evidence, FakePairProvider(), model_identity=MODEL, semantic_options=OPTIONS,
        )
        self.assertEqual(result.word_status, "complete")

    def test_each_partition_gets_its_own_durable_job(self):
        from vocab_consolidation_workflow import consolidate_word_evidence

        token = uuid.uuid4().hex
        evidence = _evidence(token, {"noun": [((), 2)], "verb": [((), 2)]})
        result = consolidate_word_evidence(
            self._persistence(), evidence, FakePairProvider(default=("keep_separate", "materially_different")),
            model_identity=MODEL, semantic_options=OPTIONS,
        )
        self.assertEqual(len(result.partitions), 2)
        self.assertEqual(len({p.partition_id for p in result.partitions}), 2)
        self.assertEqual(result.total_provider_calls_made, 2)

    def test_first_run_makes_live_calls_second_run_makes_zero(self):
        from vocab_consolidation_workflow import consolidate_word_evidence

        token = uuid.uuid4().hex
        evidence = _evidence(token, {"noun": [((), 2)]})
        first = consolidate_word_evidence(
            self._persistence(), evidence, FakePairProvider(default=("merge", "paraphrase_or_duplicate")),
            model_identity=MODEL, semantic_options=OPTIONS,
        )
        self.assertEqual(first.total_provider_calls_made, 1)
        replay_provider = FakePairProvider()
        second = consolidate_word_evidence(
            self._persistence(), evidence, replay_provider, model_identity=MODEL, semantic_options=OPTIONS,
        )
        self.assertEqual(second.total_provider_calls_made, 0)
        self.assertEqual(replay_provider.calls, [])
        self.assertEqual(
            [p.topology_identity for p in first.partitions],
            [p.topology_identity for p in second.partitions],
        )

    def test_partial_run_can_be_resumed_across_invocations(self):
        from vocab_consolidation_workflow import consolidate_word_evidence

        token = uuid.uuid4().hex
        evidence = _evidence(token, {"noun": [((), 3)]})
        first = consolidate_word_evidence(
            self._persistence(), evidence, FakePairProvider(default=("keep_separate", "related_but_distinct")),
            model_identity=MODEL, semantic_options=OPTIONS, max_total_pairs=1,
        )
        self.assertEqual(first.word_status, "incomplete")
        second = consolidate_word_evidence(
            self._persistence(), evidence, FakePairProvider(default=("keep_separate", "related_but_distinct")),
            model_identity=MODEL, semantic_options=OPTIONS,
        )
        self.assertEqual(second.word_status, "complete")
        self.assertEqual(second.total_provider_calls_made, 2)

    def test_topology_survives_a_fresh_connection(self):
        import psycopg

        from vocab_consolidation_persistence import ConsolidationPersistence
        from vocab_consolidation_workflow import consolidate_word_evidence

        token = uuid.uuid4().hex
        evidence = _evidence(token, {"noun": [((), 2)]})
        first = consolidate_word_evidence(
            self._persistence(), evidence, FakePairProvider(default=("merge", "paraphrase_or_duplicate")),
            model_identity=MODEL, semantic_options=OPTIONS,
        )
        other_connection = psycopg.connect(self.database_url)
        try:
            second = consolidate_word_evidence(
                ConsolidationPersistence(other_connection), evidence, FakePairProvider(),
                model_identity=MODEL, semantic_options=OPTIONS,
            )
        finally:
            other_connection.close()
        self.assertEqual(second.total_provider_calls_made, 0)
        self.assertEqual(
            [p.topology_identity for p in first.partitions],
            [p.topology_identity for p in second.partitions],
        )

    def test_changed_evidence_creates_a_distinct_job_and_result(self):
        from vocab_consolidation_workflow import consolidate_word_evidence

        token = uuid.uuid4().hex
        original = _evidence(token, {"noun": [((), 2)]})
        first = consolidate_word_evidence(
            self._persistence(), original, FakePairProvider(default=("merge", "paraphrase_or_duplicate")),
            model_identity=MODEL, semantic_options=OPTIONS,
        )
        changed = _evidence(token, {"noun": [((), 2)]})
        changed["entries"][0]["senses"][0]["glosses"] = ["a materially different gloss"]
        second = consolidate_word_evidence(
            self._persistence(), changed, FakePairProvider(default=("keep_separate", "materially_different")),
            model_identity=MODEL, semantic_options=OPTIONS,
        )
        self.assertNotEqual(first.evidence_identity, second.evidence_identity)
        self.assertEqual(second.total_provider_calls_made, 1)
        self.assertNotEqual(
            [p.topology_identity for p in first.partitions],
            [p.topology_identity for p in second.partitions],
        )

    def test_old_topology_remains_intact_after_evidence_change(self):
        from vocab_consolidation_workflow import consolidate_word_evidence

        token = uuid.uuid4().hex
        original = _evidence(token, {"noun": [((), 2)]})
        first = consolidate_word_evidence(
            self._persistence(), original, FakePairProvider(default=("merge", "paraphrase_or_duplicate")),
            model_identity=MODEL, semantic_options=OPTIONS,
        )
        changed = _evidence(token, {"noun": [((), 2)]})
        changed["entries"][0]["senses"][0]["glosses"] = ["a materially different gloss"]
        consolidate_word_evidence(
            self._persistence(), changed, FakePairProvider(default=("keep_separate", "materially_different")),
            model_identity=MODEL, semantic_options=OPTIONS,
        )
        # Replaying the original, unchanged evidence must still find its original topology cached.
        replay = consolidate_word_evidence(
            self._persistence(), original, FakePairProvider(), model_identity=MODEL, semantic_options=OPTIONS,
        )
        self.assertEqual(replay.total_provider_calls_made, 0)
        self.assertEqual(
            [p.topology_identity for p in first.partitions],
            [p.topology_identity for p in replay.partitions],
        )

    def test_mixed_one_sense_and_multi_sense_partitions_aggregate_correctly(self):
        from vocab_consolidation_workflow import consolidate_word_evidence

        token = uuid.uuid4().hex
        evidence = _evidence(token, {"noun": [((), 1)], "verb": [((), 2)]})
        result = consolidate_word_evidence(
            self._persistence(), evidence, FakePairProvider(default=("merge", "paraphrase_or_duplicate")),
            model_identity=MODEL, semantic_options=OPTIONS,
        )
        self.assertEqual(result.word_status, "complete")
        noun_status = next(p for p in result.partitions if p.pos == "noun")
        verb_status = next(p for p in result.partitions if p.pos == "verb")
        self.assertEqual(noun_status.provider_calls_made, 0)
        self.assertEqual(verb_status.provider_calls_made, 1)
        self.assertEqual(len(result.validated_containers), 2)

    def test_terminal_partition_blocks_whole_word_completion(self):
        from vocab_consolidation import enumerate_pairs
        from vocab_consolidation_workflow import consolidate_word_evidence, plan_word_consolidation

        token = uuid.uuid4().hex
        evidence = _evidence(token, {"noun": [((), 1)], "verb": [((), 2)]})
        verb_partition = next(p for p in plan_word_consolidation(evidence) if p.pos == "verb")
        failing_pair_id = enumerate_pairs(verb_partition)[0].pair_id
        provider = FakePairProvider(script={
            failing_pair_id: [PairProviderResult("terminal_failure", error_classification="model_unavailable", error_summary="gone")],
        })
        result = consolidate_word_evidence(
            self._persistence(), evidence, provider, model_identity=MODEL, semantic_options=OPTIONS,
        )
        self.assertEqual(result.word_status, "blocked")
        noun_status = next(p for p in result.partitions if p.pos == "noun")
        verb_status = next(p for p in result.partitions if p.pos == "verb")
        self.assertTrue(noun_status.is_topology_validated)
        self.assertTrue(verb_status.is_blocked)


if __name__ == "__main__":
    unittest.main()
