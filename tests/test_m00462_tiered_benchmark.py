import csv
import importlib.util
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).parents[1]
MODULE_PATH = ROOT / "tools/benchmarks/m0046_core_selection_benchmark.py"
SPEC = importlib.util.spec_from_file_location("m00462_benchmark", MODULE_PATH)
assert SPEC and SPEC.loader
benchmark = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(benchmark)


class M00462TieredBenchmarkTests(unittest.TestCase):
    def test_manifest_is_valid_and_rejects_invalid_attempt_count(self):
        manifest_path = ROOT / "tools/benchmarks/manifests/m004.6.2_tier1.json"
        manifest = benchmark.load_manifest(manifest_path)
        self.assertEqual(manifest["benchmark_id"], "m004.6.2-tier1")
        with TemporaryDirectory() as directory:
            invalid = dict(manifest)
            invalid["attempts_per_configuration"] = 4
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps(invalid))
            with self.assertRaises(ValueError):
                benchmark.load_manifest(path)

    def test_fixture_identity_and_pos_local_identity_are_stable(self):
        source = {
            "source_word": "bank", "normalized_lemma": "bank", "pos": "noun",
            "lexical_dataset_versions": ["v1"], "lexical_evidence_hash": "evidence",
            "fixture_construction_method": "benchmark-reconstructed",
            "fixture_construction_policy": "v1", "candidate_group_ids": ["G001"],
            "candidate_groups": [{"group_id": "G001", "definition": "financial institution"}],
            "categories": ["highly-polysemous"],
        }
        noun_hash = benchmark.canonical_hash(source)
        verb_hash = benchmark.canonical_hash({**source, "pos": "verb"})
        self.assertEqual(noun_hash, benchmark.canonical_hash(source))
        self.assertNotEqual(noun_hash, verb_hash)

    def test_diagnostics_and_code_owned_tiebreaking_are_strict(self):
        subset = benchmark.subset_diagnostics({"core_group_ids": ["G001", "G001"]}, ["G001", "G002"])
        self.assertFalse(subset["ids_are_unique"])
        self.assertFalse(benchmark.subset_diagnostics({"core_group_ids": ["G001"]}, ["G002"])["all_ids_in_allowed_set"])
        valid = {"core_count": 2, "scores": {"G002": 5, "G001": 5, "G003": 1}}
        self.assertTrue(benchmark.fixed_key_diagnostics(valid, ["G001", "G002", "G003"])["deterministic_assembly_success"])
        self.assertEqual(
            benchmark.fixed_key_assembly(valid, ["G001", "G002", "G003"])["selected_final_ids"],
            ["G001", "G002"],
        )
        for invalid in (
            {"core_count": 2, "scores": {"G001": 4}},
            {"core_count": 2, "scores": {"G001": 4, "G002": 3, "G003": 2, "G999": 1}},
            {"core_count": 2, "scores": {"G001": "4", "G002": 3, "G003": 2}},
            {"core_count": 0, "scores": {"G001": 4, "G002": 3, "G003": 2}},
        ):
            self.assertFalse(benchmark.fixed_key_assembly(invalid, ["G001", "G002", "G003"])["selected_final_ids"])

    def test_stability_calculation_and_anonymous_review_artifact(self):
        records = [
            {"model": "gpt-oss:20b", "contract_id": "subset-array-v1", "seed": 1, "fixture_id": "fixture",
             "attempt_id": "one", "assembly": {"state": "not_applicable", "selected_final_ids": ["G001", "G002"]},
             "diagnostics": {"parse_success": True}, "provider_status": "provider_success", "done_reason": "stop",
             "raw_provider_response": {"total_duration": 1}, "parsed": {"core_group_ids": ["G001"]}},
            {"model": "gpt-oss:20b", "contract_id": "subset-array-v1", "seed": 2, "fixture_id": "fixture",
             "attempt_id": "two", "assembly": {"state": "not_applicable", "selected_final_ids": ["G002", "G001"]},
             "diagnostics": {"parse_success": True}, "provider_status": "provider_success", "done_reason": "stop",
             "raw_provider_response": {"total_duration": 1}, "parsed": {"core_group_ids": ["G001"]}},
        ]
        result = benchmark.stability(records)
        self.assertEqual(result["distinct_final_sets"], 1)
        self.assertEqual(result["mean_pairwise_jaccard"], 1.0)
        fixture = {
            "fixture_id": "fixture", "source_word": "word", "pos": "noun", "categories": ["simple"],
            "fixture_construction_method": "benchmark-reconstructed",
            "candidate_groups": [{"group_id": "G001", "definition": "meaning"}],
        }
        with TemporaryDirectory() as directory:
            root = Path(directory)
            benchmark.review_artifacts(root, [fixture], records)
            with (root / "semantic_review.csv").open() as source:
                row = next(csv.DictReader(source))
            mapping = json.loads((root / "semantic_review_config_mapping.json").read_text())
        self.assertEqual(row["config_label"], "Config A")
        self.assertEqual(mapping["Config A"]["model"], "gpt-oss:20b")


if __name__ == "__main__":
    unittest.main()
