import unittest

from vocab_consolidation import (
    PAIR_JUDGMENT_CONTRACT,
    CoverageError,
    PairJudgment,
    SensePair,
    assemble_complete_link,
    build_partitions,
    enumerate_pairs,
    pair_judgment_identity,
    pair_judgment_result_identity,
    topology_identity,
)
from vocab_lexical_engine import evidence_set_hash


def fixture_evidence(count=3):
    return {
        "normalized_lemma": "fixture",
        "wiktionary_versions": ["fixture-v1"],
        "wordnet_version": "wordnet-v1",
        "entries": [{
            "entry_key": "entry-1",
            "part_of_speech": "noun",
            "senses": [
                {"sense_id": f"sense-{index}", "source_order": index, "glosses": [str(index)], "labels": [], "topics": [], "examples": [], "relations": []}
                for index in range(1, count + 1)
            ],
        }],
        "wordnet": [],
    }


MODEL = {"name": "qwen3:8b", "digest": "digest"}
OPTIONS = {"think": False, "temperature": 0, "seed": 0}


def judgments_for(partition, decisions):
    result = []
    for pair, (decision, reason) in zip(enumerate_pairs(partition), decisions):
        identity = pair_judgment_identity(
            pair,
            evidence_identity=partition.evidence_identity,
            partition_identity=partition.partition_id,
            model_identity=MODEL,
            semantic_options=OPTIONS,
        )
        result.append(PairJudgment(pair, identity, partition.evidence_identity, partition.partition_id,
                                   PAIR_JUDGMENT_CONTRACT, MODEL, OPTIONS, decision, reason))
    return result


class ConsolidationTests(unittest.TestCase):
    def test_partition_aliases_and_one_sense_fast_path(self):
        partition = build_partitions(fixture_evidence(1))[0]
        self.assertEqual(partition.aliases, {"S001": "sense-1"})
        self.assertEqual(partition.reverse_aliases, {"sense-1": "S001"})
        self.assertEqual(enumerate_pairs(partition), ())
        containers, topology = assemble_complete_link(partition, [], model_identity=MODEL, semantic_options=OPTIONS)
        self.assertEqual([container.source_sense_ids for container in containers], [("sense-1",)])
        self.assertTrue(topology)

    def test_pair_counts_and_order_are_exhaustive(self):
        for count, expected in ((1, 0), (2, 1), (3, 3), (5, 10)):
            pairs = enumerate_pairs(build_partitions(fixture_evidence(count))[0])
            self.assertEqual(len(pairs), expected)
            self.assertEqual(len({pair.pair_id for pair in pairs}), expected)
            self.assertEqual([pair.source_sense_ids for pair in pairs], sorted(pair.source_sense_ids for pair in pairs))
            if count == 2:
                reversed_pair = SensePair.create(build_partitions(fixture_evidence(2))[0], "sense-2", "sense-1")
                self.assertEqual(reversed_pair.pair_id, pairs[0].pair_id)

    def test_judgment_identity_changes_only_for_semantic_inputs(self):
        pair = enumerate_pairs(build_partitions(fixture_evidence(2))[0])[0]
        alternate_contract = "pair-judgment-v2"
        self.assertEqual(
            SensePair.create(build_partitions(fixture_evidence(2))[0], "sense-2", "sense-1").pair_id,
            pair.pair_id,
        )
        base = pair_judgment_identity(pair, evidence_identity="e", partition_identity="p", model_identity=MODEL, semantic_options=OPTIONS)
        self.assertNotEqual(
            base,
            pair_judgment_identity(
                pair,
                evidence_identity="e",
                partition_identity="p",
                contract_version=alternate_contract,
                model_identity=MODEL,
                semantic_options=OPTIONS,
            ),
        )
        self.assertNotEqual(base, pair_judgment_identity(pair, evidence_identity="changed", partition_identity="p", model_identity=MODEL, semantic_options=OPTIONS))
        self.assertNotEqual(base, pair_judgment_identity(pair, evidence_identity="e", partition_identity="p", model_identity={"name": "qwen3:8b", "digest": "other"}, semantic_options=OPTIONS))
        self.assertNotEqual(base, pair_judgment_identity(pair, evidence_identity="e", partition_identity="p", model_identity=MODEL, semantic_options={"think": True}))

    def test_result_identity_and_topology_identity_include_validated_outputs(self):
        partition = build_partitions(fixture_evidence(2))[0]
        first = judgments_for(partition, [("merge", "paraphrase_or_duplicate")])[0]
        second = judgments_for(partition, [("uncertain", "insufficient_evidence")])[0]
        self.assertNotEqual(pair_judgment_result_identity(first), pair_judgment_result_identity(second))
        first_topology = topology_identity(partition, {first.pair.pair_id: first})
        second_topology = topology_identity(partition, {second.pair.pair_id: second})
        self.assertNotEqual(first_topology, second_topology)
        three_partition = build_partitions(fixture_evidence(3))[0]
        three_judgments = judgments_for(
            three_partition,
            [("merge", "paraphrase_or_duplicate")] * 3,
        )
        reordered = {judgment.pair.pair_id: judgment for judgment in reversed(three_judgments)}
        self.assertEqual(
            topology_identity(three_partition, {judgment.pair.pair_id: judgment for judgment in three_judgments}),
            topology_identity(three_partition, reordered),
        )

    def test_complete_link_protects_non_transitive_merge(self):
        partition = build_partitions(fixture_evidence(3))[0]
        decisions = [
            ("merge", "paraphrase_or_duplicate"),
            ("keep_separate", "materially_different"),
            ("merge", "paraphrase_or_duplicate"),
        ]
        containers, _ = assemble_complete_link(partition, judgments_for(partition, decisions), model_identity=MODEL, semantic_options=OPTIONS)
        self.assertEqual([container.source_sense_ids for container in containers], [("sense-1", "sense-2"), ("sense-3",)])

    def test_uncertain_blocks_merge_and_is_coverage_complete(self):
        partition = build_partitions(fixture_evidence(2))[0]
        containers, _ = assemble_complete_link(
            partition,
            judgments_for(partition, [("uncertain", "insufficient_evidence")]),
            model_identity=MODEL,
            semantic_options=OPTIONS,
        )
        self.assertEqual(len(containers), 2)

    def test_missing_duplicate_foreign_and_incompatible_pairs_reject_coverage(self):
        partition = build_partitions(fixture_evidence(3))[0]
        judgments = judgments_for(partition, [("merge", "paraphrase_or_duplicate")] * 3)
        with self.assertRaises(CoverageError) as missing:
            assemble_complete_link(partition, judgments[:-1], model_identity=MODEL, semantic_options=OPTIONS)
        self.assertTrue(missing.exception.diagnostics["missing_pair_ids"])
        with self.assertRaises(CoverageError) as duplicate:
            assemble_complete_link(partition, judgments + [judgments[0]], model_identity=MODEL, semantic_options=OPTIONS)
        self.assertTrue(duplicate.exception.diagnostics["duplicate_pair_ids"])
        foreign = judgments_for(build_partitions(fixture_evidence(2))[0], [("merge", "paraphrase_or_duplicate")])[0]
        with self.assertRaises(CoverageError) as foreign_error:
            assemble_complete_link(partition, judgments[:-1] + [foreign], model_identity=MODEL, semantic_options=OPTIONS)
        self.assertTrue(foreign_error.exception.diagnostics["foreign_pair_ids"])
        incompatible = judgments[0]
        incompatible = PairJudgment(incompatible.pair, incompatible.judgment_identity, incompatible.evidence_identity,
                                    incompatible.partition_identity, incompatible.contract_version,
                                    {"name": "qwen3:8b", "digest": "other"}, OPTIONS, incompatible.decision, incompatible.reason)
        with self.assertRaises(CoverageError):
            assemble_complete_link(partition, [incompatible] + judgments[1:], model_identity=MODEL, semantic_options=OPTIONS)

    def test_material_labels_create_separate_partitions(self):
        evidence = fixture_evidence(2)
        evidence["entries"][0]["senses"][1]["labels"] = ["figurative"]
        partitions = build_partitions(evidence)
        self.assertEqual(len(partitions), 2)
        self.assertEqual({partition.material_partition for partition in partitions}, {(), ("figurative",)})


if __name__ == "__main__":
    unittest.main()
