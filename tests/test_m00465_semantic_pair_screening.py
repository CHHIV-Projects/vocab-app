import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("m00465_screening", ROOT / "tools/benchmarks/m0046_semantic_pair_screening.py")
assert SPEC and SPEC.loader
screening = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(screening)


class M00465ScreeningTests(unittest.TestCase):
    def test_cosine_is_normalized_and_rejects_zero_vectors(self):
        self.assertAlmostEqual(screening.cosine([1.0, 0.0], [2.0, 0.0]), 1.0)
        with self.assertRaises(ValueError):
            screening.cosine([0.0, 0.0], [1.0, 0.0])

    def test_definition_representation_is_deterministic(self):
        node = {"word": "x", "pos": "noun", "definition": [" first ", "second\nmeaning"]}
        self.assertEqual(screening.representation(node), "x [noun]: first; second meaning")
        self.assertEqual(screening.text_hash(screening.representation(node)), screening.text_hash(screening.representation(node)))

    def test_top_k_is_symmetric_and_deterministically_tie_broken(self):
        partition = {"partition_id": "p", "source_nodes": [
            {"source_sense_id": "A"}, {"source_sense_id": "B"}, {"source_sense_id": "C"},
        ]}
        pairs = [
            {"pair_id": "AB", "partition_id": "p", "first": partition["source_nodes"][0], "second": partition["source_nodes"][1]},
            {"pair_id": "AC", "partition_id": "p", "first": partition["source_nodes"][0], "second": partition["source_nodes"][2]},
            {"pair_id": "BC", "partition_id": "p", "first": partition["source_nodes"][1], "second": partition["source_nodes"][2]},
        ]
        vectors = {"A": [1, 0], "B": [1, 0], "C": [0, 1]}
        self.assertEqual(screening.policy_pairs(pairs, vectors, "top_k", 1), {"AB", "AC"})

    def test_screening_metrics_exclude_uncertain_pairs(self):
        references = [
            {"pair_id": "P1", "reference_decision": "merge"},
            {"pair_id": "P2", "reference_decision": "keep_separate"},
            {"pair_id": "P3", "reference_decision": "uncertain"},
        ]
        score = screening.score_policy({"S1"}, references, {"P1": "S1", "P2": "S2", "P3": "S3"})
        self.assertEqual(score["resolved_merge_count"], 1)
        self.assertEqual(score["resolved_keep_separate_count"], 1)
        self.assertEqual(score["uncertain_pair_ids"], ["P3"])

    def test_pair_identity_includes_screening_identity(self):
        self.assertNotEqual(screening.pair_id("p", "A", "B", "v1"), screening.pair_id("p", "A", "B", "v2"))


if __name__ == "__main__":
    unittest.main()
