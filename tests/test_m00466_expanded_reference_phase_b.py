import csv
import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location(
    "m00466_phase_b", ROOT / "tools/benchmarks/m0046_expanded_reference_phase_b.py"
)
assert SPEC and SPEC.loader
phase_b = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(phase_b)


class M00466PhaseBTests(unittest.TestCase):
    def test_adjudicated_labels_are_normalized_and_validated(self):
        candidates = [{
            "pair_id": "P1", "word": "x", "pos": "noun", "partition_id": "p",
            "first": {"source_sense_id": "A"}, "second": {"source_sense_id": "B"},
        }]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "labels.csv"
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["pair_id", "decision", "review_notes"])
                writer.writeheader()
                writer.writerow({"pair_id": "P1", "decision": "KEEP SEPARATE", "review_notes": "distinct"})
            result = phase_b.load_labels(path, candidates)
        self.assertEqual(result[0]["reference_decision"], "keep_separate")

    def test_reference_metrics_exclude_uncertain_pairs(self):
        references = [
            {"pair_id": "P1", "reference_decision": "merge"},
            {"pair_id": "P2", "reference_decision": "keep_separate"},
            {"pair_id": "P3", "reference_decision": "uncertain"},
        ]
        metrics = phase_b.score_reference({"S1"}, references, {"P1": "S1", "P2": "S2", "P3": "S3"})
        self.assertEqual(metrics["resolved_merge_count"], 1)
        self.assertEqual(metrics["uncertain_count"], 1)
        self.assertEqual(metrics["keep_separate_screened_count"], 1)

    def test_invalid_label_is_rejected(self):
        candidates = [{
            "pair_id": "P1", "word": "x", "pos": "noun", "partition_id": "p",
            "first": {"source_sense_id": "A"}, "second": {"source_sense_id": "B"},
        }]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "labels.csv"
            path.write_text("pair_id,decision\nP1,maybe\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                phase_b.load_labels(path, candidates)


if __name__ == "__main__":
    unittest.main()
