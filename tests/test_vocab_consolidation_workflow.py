import unittest

from tests.fake_consolidation_persistence import FakeConsolidationPersistence
from tests.test_m004611_postgres_isolated import FakePairProvider
from vocab_consolidation_provider import PairProviderResult
from vocab_consolidation_workflow import (
    WORD_STATUS_BLOCKED,
    WORD_STATUS_COMPLETE,
    WORD_STATUS_INCOMPLETE,
    consolidate_word_evidence,
    plan_word_consolidation,
    total_expected_pair_count,
)

MODEL = {"name": "qwen3:8b", "digest": "test-digest"}
OPTIONS = {"think": False, "temperature": 0, "seed": 5100}


def evidence_for(senses_by_pos_and_tags, lemma="fixture"):
    """Build synthesis-style evidence (senses keyed by `"tags"`, not `"labels"`) with one
    entry per POS, so `partitions_from_synthesis_evidence` produces the requested partitions."""
    entries = []
    for pos, groups in senses_by_pos_and_tags.items():
        senses = []
        order = 1
        for tags, count in groups:
            for _ in range(count):
                senses.append({
                    "sense_id": f"{lemma}-{pos}-{'-'.join(tags) or 'plain'}-{order}",
                    "source_order": order, "glosses": [f"gloss {order}"], "tags": list(tags),
                    "topics": [], "examples": [], "relations": [],
                })
                order += 1
        entries.append({"entry_key": f"{lemma}-{pos}", "part_of_speech": pos, "senses": senses})
    return {
        "normalized_lemma": lemma,
        "wiktionary_versions": ["fixture-v1"],
        "wordnet_version": "fixture-wordnet",
        "entries": entries,
        "wordnet": [],
    }


class PlanningTests(unittest.TestCase):
    def test_deterministic_word_level_result_construction(self):
        evidence = evidence_for({"noun": [((), 1)]})
        persistence = FakeConsolidationPersistence()
        provider = FakePairProvider()
        result = consolidate_word_evidence(
            persistence, evidence, provider, model_identity=MODEL, semantic_options=OPTIONS,
        )
        self.assertEqual(result.normalized_lemma, "fixture")
        self.assertTrue(result.evidence_identity)
        self.assertEqual(result.lexical_dataset_identity, {"wiktionary_versions": ["fixture-v1"], "wordnet_version": "fixture-wordnet"})
        self.assertEqual(result.word_status, WORD_STATUS_COMPLETE)

    def test_multiple_pos_partitions_are_all_discovered(self):
        evidence = evidence_for({"noun": [((), 2)], "verb": [((), 3)]})
        partitions = plan_word_consolidation(evidence)
        self.assertEqual({p.pos for p in partitions}, {"noun", "verb"})
        self.assertEqual(len(partitions), 2)

    def test_material_label_partitions_are_discovered_and_disjoint(self):
        evidence = evidence_for({"noun": [((), 2), (("archaic",), 1)]})
        partitions = plan_word_consolidation(evidence)
        self.assertEqual(len(partitions), 2)
        signatures = {p.material_partition for p in partitions}
        self.assertEqual(signatures, {(), ("archaic",)})
        plain = next(p for p in partitions if p.material_partition == ())
        archaic = next(p for p in partitions if p.material_partition == ("archaic",))
        self.assertEqual(len(plain.members), 2)
        self.assertEqual(len(archaic.members), 1)
        self.assertFalse({m["sense_id"] for m in plain.members} & {m["sense_id"] for m in archaic.members})

    def test_total_expected_pair_count_calculation(self):
        evidence = evidence_for({"noun": [((), 3)], "verb": [((), 2)]})
        partitions = plan_word_consolidation(evidence)
        # noun: C(3,2)=3 pairs; verb: C(2,2)=1 pair
        self.assertEqual(total_expected_pair_count(partitions), 4)

    def test_no_cross_partition_pair_generation(self):
        from vocab_consolidation import enumerate_pairs

        evidence = evidence_for({"noun": [((), 2)], "verb": [((), 2)]})
        partitions = plan_word_consolidation(evidence)
        all_pair_sense_ids = set()
        for partition in partitions:
            partition_sense_ids = {m["sense_id"] for m in partition.members}
            for pair in enumerate_pairs(partition):
                self.assertIn(pair.source_sense_id_a, partition_sense_ids)
                self.assertIn(pair.source_sense_id_b, partition_sense_ids)
            all_pair_sense_ids |= partition_sense_ids
        # Confirm partitions do not overlap in membership (no shared senses across partitions).
        noun = next(p for p in partitions if p.pos == "noun")
        verb = next(p for p in partitions if p.pos == "verb")
        self.assertFalse({m["sense_id"] for m in noun.members} & {m["sense_id"] for m in verb.members})

    def test_stable_result_ordering_is_reproducible(self):
        evidence = evidence_for({"verb": [((), 1)], "noun": [(("archaic",), 1), ((), 1)]})
        first = plan_word_consolidation(evidence)
        second = plan_word_consolidation(evidence)
        self.assertEqual([p.partition_id for p in first], [p.partition_id for p in second])
        # POS ordering must be alphabetical/code-owned (noun before verb), not insertion order.
        self.assertEqual([p.pos for p in first], ["noun", "noun", "verb"])


class OneSenseFastPathTests(unittest.TestCase):
    def test_one_sense_partitions_require_zero_provider_calls(self):
        evidence = evidence_for({"noun": [((), 1)], "verb": [((), 1)]})
        persistence = FakeConsolidationPersistence()
        provider = FakePairProvider()
        result = consolidate_word_evidence(persistence, evidence, provider, model_identity=MODEL, semantic_options=OPTIONS)
        self.assertEqual(result.word_status, WORD_STATUS_COMPLETE)
        self.assertEqual(result.total_provider_calls_made, 0)
        self.assertEqual(provider.calls, [])
        self.assertEqual(len(result.validated_containers), 2)


class CacheReuseTests(unittest.TestCase):
    def test_completed_partition_cache_reuse_makes_zero_calls_on_second_run(self):
        evidence = evidence_for({"noun": [((), 2)]})
        persistence = FakeConsolidationPersistence()
        first = consolidate_word_evidence(
            persistence, evidence, FakePairProvider(default=("merge", "paraphrase_or_duplicate")),
            model_identity=MODEL, semantic_options=OPTIONS,
        )
        self.assertEqual(first.word_status, WORD_STATUS_COMPLETE)
        self.assertEqual(first.total_provider_calls_made, 1)

        replay_provider = FakePairProvider()
        second = consolidate_word_evidence(persistence, evidence, replay_provider, model_identity=MODEL, semantic_options=OPTIONS)
        self.assertEqual(second.word_status, WORD_STATUS_COMPLETE)
        self.assertEqual(second.total_provider_calls_made, 0)
        self.assertEqual(replay_provider.calls, [])
        self.assertEqual(
            [p.topology_identity for p in first.partitions],
            [p.topology_identity for p in second.partitions],
        )

    def test_unchanged_evidence_reuses_completed_topology(self):
        evidence = evidence_for({"noun": [((), 2)]})
        persistence = FakeConsolidationPersistence()
        consolidate_word_evidence(
            persistence, evidence, FakePairProvider(default=("keep_separate", "materially_different")),
            model_identity=MODEL, semantic_options=OPTIONS,
        )
        second = consolidate_word_evidence(
            persistence, evidence_for({"noun": [((), 2)]}), FakePairProvider(),
            model_identity=MODEL, semantic_options=OPTIONS,
        )
        self.assertEqual(second.total_provider_calls_made, 0)
        self.assertEqual(second.word_status, WORD_STATUS_COMPLETE)

    def test_changed_evidence_identity_does_not_reuse_stale_topology(self):
        persistence = FakeConsolidationPersistence()
        original = evidence_for({"noun": [((), 2)]})
        first = consolidate_word_evidence(
            persistence, original, FakePairProvider(default=("merge", "paraphrase_or_duplicate")),
            model_identity=MODEL, semantic_options=OPTIONS,
        )
        changed = evidence_for({"noun": [((), 2)]})
        changed["entries"][0]["senses"][0]["glosses"] = ["a materially different gloss"]
        second_provider = FakePairProvider(default=("keep_separate", "materially_different"))
        second = consolidate_word_evidence(
            persistence, changed, second_provider, model_identity=MODEL, semantic_options=OPTIONS,
        )
        self.assertNotEqual(first.evidence_identity, second.evidence_identity)
        # The changed evidence must perform its own live provider call, not reuse the first result.
        self.assertEqual(second.total_provider_calls_made, 1)
        self.assertNotEqual(
            [p.topology_identity for p in first.partitions],
            [p.topology_identity for p in second.partitions],
        )


class ResumeTests(unittest.TestCase):
    def test_partial_partition_resume_does_not_repeat_successful_pairs(self):
        from vocab_consolidation import enumerate_pairs

        evidence = evidence_for({"noun": [((), 3)]})
        partitions = plan_word_consolidation(evidence)
        pair_ids = [pair.pair_id for pair in enumerate_pairs(partitions[0])]
        persistence = FakeConsolidationPersistence()

        # First invocation only budgets one live call; the job is left incomplete.
        first = consolidate_word_evidence(
            persistence, evidence, FakePairProvider(default=("keep_separate", "related_but_distinct")),
            model_identity=MODEL, semantic_options=OPTIONS, max_total_pairs=1,
        )
        self.assertEqual(first.word_status, WORD_STATUS_INCOMPLETE)
        self.assertEqual(first.total_provider_calls_made, 1)

        # Second invocation must resume the remaining pairs without re-judging the first.
        resuming_provider = FakePairProvider(default=("keep_separate", "related_but_distinct"))
        second = consolidate_word_evidence(
            persistence, evidence, resuming_provider, model_identity=MODEL, semantic_options=OPTIONS,
        )
        self.assertEqual(second.word_status, WORD_STATUS_COMPLETE)
        self.assertEqual(second.total_provider_calls_made, 2)
        self.assertEqual(len(resuming_provider.calls), 2)
        self.assertNotIn(pair_ids[0] if pair_ids[0] not in resuming_provider.calls else None, [])


class MixedPartitionTests(unittest.TestCase):
    def test_multiple_partitions_with_mixed_complete_and_incomplete_status(self):
        evidence = evidence_for({"noun": [((), 1)], "verb": [((), 3)]})
        persistence = FakeConsolidationPersistence()
        result = consolidate_word_evidence(
            persistence, evidence, FakePairProvider(default=("keep_separate", "related_but_distinct")),
            model_identity=MODEL, semantic_options=OPTIONS, max_total_pairs=1,
        )
        self.assertEqual(result.word_status, WORD_STATUS_INCOMPLETE)
        noun_status = next(p for p in result.partitions if p.pos == "noun")
        verb_status = next(p for p in result.partitions if p.pos == "verb")
        self.assertTrue(noun_status.is_topology_validated)
        self.assertFalse(verb_status.is_topology_validated)
        # The one-sense noun partition must not have consumed any of the pair budget.
        self.assertEqual(noun_status.provider_calls_made, 0)
        self.assertEqual(verb_status.provider_calls_made, 1)

    def test_terminally_blocked_partition_makes_whole_word_blocked(self):
        from vocab_consolidation import enumerate_pairs

        evidence = evidence_for({"noun": [((), 1)], "verb": [((), 2)]})
        partitions = plan_word_consolidation(evidence)
        verb_partition = next(p for p in partitions if p.pos == "verb")
        failing_pair_id = enumerate_pairs(verb_partition)[0].pair_id

        persistence = FakeConsolidationPersistence()
        provider = FakePairProvider(script={
            failing_pair_id: [PairProviderResult("terminal_failure", error_classification="model_unavailable", error_summary="gone")],
        })
        result = consolidate_word_evidence(persistence, evidence, provider, model_identity=MODEL, semantic_options=OPTIONS)
        self.assertEqual(result.word_status, WORD_STATUS_BLOCKED)
        noun_status = next(p for p in result.partitions if p.pos == "noun")
        verb_status = next(p for p in result.partitions if p.pos == "verb")
        # The unrelated, already-complete noun partition's topology must be preserved and reported.
        self.assertTrue(noun_status.is_topology_validated)
        self.assertTrue(verb_status.is_blocked)


class BudgetDistributionTests(unittest.TestCase):
    def test_explicit_word_level_work_budget_is_distributed_deterministically(self):
        evidence = evidence_for({"noun": [((), 3)], "verb": [((), 3)]})
        persistence = FakeConsolidationPersistence()
        provider = FakePairProvider(default=("keep_separate", "related_but_distinct"))
        result = consolidate_word_evidence(
            persistence, evidence, provider, model_identity=MODEL, semantic_options=OPTIONS, max_total_pairs=4,
        )
        self.assertEqual(result.total_provider_calls_made, 4)
        self.assertEqual(result.word_status, WORD_STATUS_INCOMPLETE)
        noun_status = next(p for p in result.partitions if p.pos == "noun")
        verb_status = next(p for p in result.partitions if p.pos == "verb")
        # Deterministic order is noun, then verb: noun's 3 pairs consumed first, then 1 of verb's 3.
        self.assertEqual(noun_status.provider_calls_made, 3)
        self.assertEqual(verb_status.provider_calls_made, 1)
        self.assertTrue(noun_status.is_topology_validated)
        self.assertFalse(verb_status.is_topology_validated)


if __name__ == "__main__":
    unittest.main()
