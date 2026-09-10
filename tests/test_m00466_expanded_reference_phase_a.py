import csv
import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location(
    "m00466_phase_a", ROOT / "tools/benchmarks/m0046_expanded_reference_phase_a.py"
)
assert SPEC and SPEC.loader
phase_a = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(phase_a)


class M00466PhaseATests(unittest.TestCase):
    def test_similarity_bands_cover_threshold_boundary(self):
        self.assertEqual(phase_a.band(0.95), "ge_0.94")
        self.assertEqual(phase_a.band(0.90), "0.90_0.94")
        self.assertEqual(phase_a.band(0.89), "0.86_0.90")
        self.assertEqual(phase_a.band(0.85), "0.80_0.86")
        self.assertEqual(phase_a.band(0.79), "lt_0.80")

    def test_pair_sampling_is_capped_and_deterministic(self):
        nodes = [
            {"source_sense_id": "A", "definition": ["same meaning"]},
            {"source_sense_id": "B", "definition": ["same meaning"]},
            {"source_sense_id": "C", "definition": ["different meaning"]},
        ]
        partition = {
            "partition_id": "p", "word": "x", "pos": "noun",
            "material_partition": [], "source_nodes": nodes,
        }
        pairs = phase_a.pair_records([partition], "identity")
        vectors = {"A": [1.0, 0.0], "B": [1.0, 0.0], "C": [0.0, 1.0]}
        first = phase_a.select_pairs(pairs, vectors, target=2)
        second = phase_a.select_pairs(pairs, vectors, target=2)
        self.assertEqual([item["pair_id"] for item in first], [item["pair_id"] for item in second])
        self.assertLessEqual(len(first), 2)

    def test_blinded_csv_fields_do_not_expose_screening_metadata(self):
        import tempfile

        pair = {
            "pair_id": "p", "review_order": 1, "word": "x", "pos": "noun",
            "material_partition": [], "first": {"source_sense_id": "A", "definition": ["a"], "labels": [], "examples": []},
            "second": {"source_sense_id": "B", "definition": ["b"], "labels": [], "examples": []},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "review.csv"
            phase_a.write_csv(path, [pair])
            with path.open(encoding="utf-8") as handle:
                fields = next(csv.reader(handle))
        self.assertNotIn("similarity", fields)
        self.assertNotIn("threshold", fields)
        self.assertNotIn("model", fields)
        self.assertIn("decision", fields)
        self.assertIn("review_notes", fields)

    def test_phase_a_artifact_carries_no_semantic_labels(self):
        payload = {
            "phase": "A",
            "review_status": "awaiting_product_owner_architect_adjudication",
            "candidate_pairs": [{"pair_id": "p", "reference_decision": None}],
        }
        self.assertIsNone(payload["candidate_pairs"][0]["reference_decision"])
        self.assertNotEqual(payload["review_status"], "adjudicated")


if __name__ == "__main__":
    unittest.main()
