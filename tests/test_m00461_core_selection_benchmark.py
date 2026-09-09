import importlib.util
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


MODULE_PATH = Path(__file__).parents[1] / "tools" / "benchmarks" / "004.6.1_core_selection_contract_and_schema_conformance_microbenchmark.py"
SPEC = importlib.util.spec_from_file_location("m00461_benchmark", MODULE_PATH)
assert SPEC and SPEC.loader
benchmark = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(benchmark)


class M00461BenchmarkTests(unittest.TestCase):
    def test_subset_diagnostics_are_allowed_set_specific_and_detect_duplicates_and_limits(self):
        self.assertTrue(benchmark.subset_diagnostics({"core_group_ids": ["G001"]}, ["G001"])["all_ids_in_allowed_set"])
        self.assertFalse(benchmark.subset_diagnostics({"core_group_ids": ["G001"]}, ["G002"])["all_ids_in_allowed_set"])
        diagnostics = benchmark.subset_diagnostics({"core_group_ids": ["G001", "G001", "G002", "G003", "G004", "G005"]}, ["G001", "G002", "G003", "G004", "G005"])
        self.assertFalse(diagnostics["ids_are_unique"])
        self.assertFalse(diagnostics["count_within_limit"])

    def test_fixed_key_diagnostics_reject_missing_unknown_and_invalid_values(self):
        group_ids = ["G001", "G002"]
        valid = {"core_count": 2, "scores": {"G001": 5, "G002": 1}}
        self.assertTrue(benchmark.fixed_key_diagnostics(valid, group_ids)["deterministic_assembly_success"])
        for invalid in (
            {"core_count": 2, "scores": {"G001": 5}},
            {"core_count": 2, "scores": {"G001": 5, "G002": 1, "G999": 2}},
            {"core_count": 2, "scores": {"G001": "5", "G002": 1}},
            {"core_count": 0, "scores": {"G001": 5, "G002": 1}},
            {"core_count": 3, "scores": {"G001": 5, "G002": 1}},
        ):
            self.assertFalse(benchmark.fixed_key_diagnostics(invalid, group_ids)["deterministic_assembly_success"])

    def test_fixed_key_assembly_is_code_owned_and_stably_tiebreaks(self):
        result = benchmark.fixed_key_assembly({"core_count": 2, "scores": {"G002": 4, "G001": 4, "G003": 1}}, ["G001", "G002", "G003"])
        self.assertEqual(result["state"], "assembled")
        self.assertEqual(result["selected_final_ids"], ["G001", "G002"])
        rejected = benchmark.fixed_key_assembly({"core_count": 1, "scores": {"G001": 3}}, ["G001", "G002"])
        self.assertEqual(rejected["state"], "rejected")
        self.assertEqual(rejected["selected_final_ids"], [])

    def test_artifact_serialization_retains_identity_fields(self):
        record = {
            "run_id": "run", "timestamp": "time", "git_head": "head", "model": "model", "model_digest": "digest",
            "ollama_version": "version", "contract_id": "contract", "fixture_id": "fixture", "schema_hash": "schema",
            "prompt_hash": "prompt", "seed": 1, "options": {"temperature": 0}, "cold_warm": "cold",
        }
        with TemporaryDirectory() as directory:
            path = Path(directory) / "artifact.json"
            benchmark.write_records(path, [record])
            restored = json.loads(path.read_text())
        self.assertEqual(restored, [record])


if __name__ == "__main__":
    unittest.main()
