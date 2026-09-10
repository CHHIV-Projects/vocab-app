import importlib.util
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).parents[1]
MODULE_PATH = ROOT / "tools/benchmarks/m0046_learner_consolidation_benchmark.py"
SPEC = importlib.util.spec_from_file_location("m00463_benchmark", MODULE_PATH)
assert SPEC and SPEC.loader
benchmark = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(benchmark)


class M00463LearnerConsolidationTests(unittest.TestCase):
    def test_manifest_and_pair_generation_are_deterministic(self):
        manifest = benchmark.load_manifest(ROOT / "tools/benchmarks/manifests/m004.6.3_reference_subproblem.json")
        self.assertEqual(manifest["attempts_per_pair_model"], 3)
        partition = {
            "partition_id": "word:noun:hash",
            "source_nodes": [{"source_sense_id": "S003"}, {"source_sense_id": "S001"}, {"source_sense_id": "S002"}],
        }
        pairs = benchmark.pair_records(partition)
        self.assertEqual(len(pairs), 3)
        self.assertEqual([pair["source_sense_ids"] for pair in pairs], [["S003", "S001"], ["S003", "S002"], ["S001", "S002"]])

    def test_equivalence_contract_and_model_disagreement_are_explicit(self):
        self.assertEqual(benchmark.equivalence_schema()["properties"]["relationship"]["enum"], ["same", "distinct", "uncertain"])
        self.assertTrue(benchmark.relationship_diagnostics({"relationship": "same"})["relationship_is_allowed"])
        self.assertFalse(benchmark.relationship_diagnostics({"relationship": "merge"})["relationship_is_allowed"])
        records = [
            {"parsed": {"relationship": "same"}, "diagnostics": {"parse_success": True, "exact_top_level_keys": True, "relationship_is_allowed": True}},
            {"parsed": {"relationship": "distinct"}, "diagnostics": {"parse_success": True, "exact_top_level_keys": True, "relationship_is_allowed": True}},
            {"parsed": {"relationship": "uncertain"}, "diagnostics": {"parse_success": True, "exact_top_level_keys": True, "relationship_is_allowed": True}},
        ]
        result = benchmark.majority_relationship(records)
        self.assertEqual(result["majority_relationship"], "uncertain")
        self.assertTrue(result["disagreement"])

    def test_conflicting_evidence_blocks_unsafe_transitive_merge(self):
        groups, conflicts = benchmark.components(
            ["S001", "S002", "S003"],
            [("S001", "S002"), ("S002", "S003")],
            {frozenset(("S001", "S003"))},
        )
        self.assertEqual(groups, [["S001", "S002"], ["S003"]])
        self.assertEqual(conflicts[0]["blocked_same_edge"], ["S002", "S003"])

    def test_containers_preserve_every_sense_exactly_once(self):
        partition = {
            "partition_id": "fixture", "source_nodes": [
                {"source_sense_id": "S001", "definition": ["one"], "labels": []},
                {"source_sense_id": "S002", "definition": ["two"], "labels": []},
            ],
        }
        evidence = [
            {"pair_id": "pair", "partition_id": "fixture", "model": "model", "source_sense_ids": ["S001", "S002"], "majority_relationship": "same"},
        ]
        result = benchmark.containers_for_model(partition, evidence, "model")
        self.assertEqual(result["containers"][0]["container_id"], "G001")
        self.assertEqual(result["containers"][0]["source_sense_ids"], ["S001", "S002"])
        self.assertTrue(all(result["validation"].values()))

    def test_containers_ignore_other_partition_pair_evidence(self):
        partition = {
            "partition_id": "target", "source_nodes": [
                {"source_sense_id": "S001", "definition": ["one"], "labels": []},
                {"source_sense_id": "S002", "definition": ["two"], "labels": []},
            ],
        }
        result = benchmark.containers_for_model(partition, [
            {"pair_id": "other", "partition_id": "other", "model": "model", "source_sense_ids": ["X001", "X002"], "majority_relationship": "same"},
            {"pair_id": "target", "partition_id": "target", "model": "model", "source_sense_ids": ["S001", "S002"], "majority_relationship": "same"},
        ], "model")
        self.assertEqual(result["containers"][0]["source_sense_ids"], ["S001", "S002"])

    def test_fixed_key_ranking_yields_exhaustive_core_additional_partition(self):
        ids = ["G001", "G002", "G003"]
        parsed = {"core_count": 2, "scores": {"G001": 4, "G002": 5, "G003": 1}}
        assembly = benchmark.fixed_key_assembly(parsed, ids)
        self.assertEqual(assembly["selected_final_ids"], ["G002", "G001"])
        additional = sorted(set(ids) - set(assembly["selected_final_ids"]))
        self.assertEqual(sorted(assembly["selected_final_ids"] + additional), ids)

    def test_container_artifact_serialization_preserves_provenance(self):
        artifact = {
            "partition_id": "word:noun:hash", "clustering_policy": "conservative-majority-union-find-v1",
            "containers": [{"container_id": "G001", "source_sense_ids": ["S001", "S002"]}],
            "conflicts": [], "container_hash": "hash",
        }
        with TemporaryDirectory() as directory:
            path = Path(directory) / "containers.json"
            benchmark.write_json(path, [artifact])
            restored = json.loads(path.read_text())
        self.assertEqual(restored, [artifact])


if __name__ == "__main__":
    unittest.main()
