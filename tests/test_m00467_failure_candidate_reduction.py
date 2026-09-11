import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location(
    "m00467", ROOT / "tools/benchmarks/m0046_failure_candidate_reduction.py"
)
assert SPEC and SPEC.loader
m00467 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m00467)

REFERENCE = Path("/home/chuck/.local/share/vocab-app/benchmarks/m004.6.6/20260910T234324Z/reference_adjudicated_v3.json")


class M00467FailureCandidateReductionTests(unittest.TestCase):
    def test_immutable_reference_ingestion_counts_and_does_not_mutate(self):
        before = (REFERENCE.stat().st_mtime_ns, REFERENCE.stat().st_size)
        identity = m00467.validate_reference(REFERENCE)
        after = (REFERENCE.stat().st_mtime_ns, REFERENCE.stat().st_size)
        self.assertEqual(identity["total_pairs"], 200)
        self.assertEqual(identity["counts"], {"merge": 30, "keep_separate": 164, "uncertain": 6})
        self.assertEqual(before, after)
        self.assertTrue(identity["mtime_ns_unchanged_by_load"])

    def test_structural_signal_extracts_shared_parent_without_merge_authority(self):
        first = {"source_sense_id": "WIK:v:i:en:entry:['en:topmost']:aaa:1:sense", "definition": ["The topmost part."], "relations": []}
        second = {"source_sense_id": "WIK:v:i:en:entry:['en:topmost']:bbb:1:sense", "definition": ["The topmost part.", "The end of a table."], "relations": []}
        signals = m00467.structural_signals(first, second)
        self.assertEqual(signals["decision"], "retain_for_semantic_review")
        self.assertIn("shared_parent_definition_prefix", signals["reason_codes"])
        self.assertIn("same_source_hierarchy_identity", signals["reason_codes"])
        self.assertNotIn("merge", signals["decision"])

    def test_candidate_pair_identity_is_deterministic_and_undirected(self):
        left = m00467.candidate_pair_id("p", "B", "A", "policy")
        right = m00467.candidate_pair_id("p", "A", "B", "policy")
        changed = m00467.candidate_pair_id("p", "A", "B", "policy2")
        self.assertEqual(left, right)
        self.assertNotEqual(left, changed)

    def test_fixed_key_candidate_proposal_schema_requires_exact_aliases(self):
        schema = m00467.proposal_schema(["S001", "S002", "S003"], max_candidates_per_alias=2)
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["required"], ["S001", "S002", "S003"])
        self.assertNotIn("S001", schema["properties"]["S001"]["items"]["enum"])

    def test_alias_validation_rejects_unknown_self_and_duplicate_candidates(self):
        aliases = ["S001", "S002", "S003"]
        valid = {"S001": ["S002"], "S002": ["S001"], "S003": []}
        self.assertTrue(m00467.proposal_diagnostics(valid, aliases)["deterministic_pair_normalization_success"])
        unknown = {"S001": ["S004"], "S002": [], "S003": []}
        self.assertFalse(m00467.proposal_diagnostics(unknown, aliases)["all_candidates_known_aliases"])
        self_ref = {"S001": ["S001"], "S002": [], "S003": []}
        self.assertFalse(m00467.proposal_diagnostics(self_ref, aliases)["no_self_references"])
        duplicate = {"S001": ["S002", "S002"], "S002": [], "S003": []}
        self.assertFalse(m00467.proposal_diagnostics(duplicate, aliases)["no_duplicate_candidates"])

    def test_undirected_candidate_normalization_deduplicates_reciprocal_pairs(self):
        parsed = {"S001": ["S002"], "S002": ["S001"], "S003": []}
        aliases = ["S001", "S002", "S003"]
        diagnostics = m00467.proposal_diagnostics(parsed, aliases)
        pairs = m00467.normalized_candidate_pairs(parsed, {"S001": "A", "S002": "B", "S003": "C"}, diagnostics)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]["source_sense_ids"], ["A", "B"])

    def test_recall_and_reduction_metrics_exclude_uncertain(self):
        references = [
            {"pair_id": "P1", "reference_decision": "merge", "first": {"source_sense_id": "A"}, "second": {"source_sense_id": "B"}},
            {"pair_id": "P2", "reference_decision": "keep_separate", "first": {"source_sense_id": "A"}, "second": {"source_sense_id": "C"}},
            {"pair_id": "P3", "reference_decision": "uncertain", "first": {"source_sense_id": "B"}, "second": {"source_sense_id": "C"}},
        ]
        metrics = m00467.score_retention({("A", "B")}, references)
        self.assertEqual(metrics["merge_candidate_recall"], 1.0)
        self.assertEqual(metrics["keep_separate_reduction"], 1.0)
        self.assertEqual(metrics["uncertain_count"], 1)

    def test_exhaustive_pair_and_lazy_precompute_cost_calculations(self):
        economics = m00467.exhaustive_economics([], {"p50_seconds": 0.5, "p95_seconds": 1.0})
        five = next(row for row in economics["representative_partitions"] if row["key"] == "5_senses")
        self.assertEqual(five["complete_pairs"], 10)
        self.assertEqual(five["first_build_runtime_seconds_p50"], 5.0)
        distribution = {"total_all_pairs": 100, "buckets": {"1": {"all_pairs": 0}, "2": {"all_pairs": 10}, "3": {"all_pairs": 10}, "4-5": {"all_pairs": 10}, "6-10": {"all_pairs": 10}, "11-20": {"all_pairs": 10}, "21-40": {"all_pairs": 20}, ">40": {"all_pairs": 30}}}
        projection = m00467.lazy_precompute_projection(distribution, {"p50_seconds": 0.5, "p95_seconds": 1.0})
        self.assertEqual(projection["background_precompute"]["projected_total_runtime_seconds_p50"], 50.0)
        self.assertEqual(projection["background_precompute"]["large_pair_calls_21_plus"], 50)

    def test_partition_size_bucket_boundaries(self):
        expected = {1: "1", 2: "2", 3: "3", 4: "4-5", 5: "4-5", 6: "6-10", 10: "6-10", 11: "11-20", 20: "11-20", 21: "21-40", 40: "21-40", 41: ">40"}
        for size, bucket in expected.items():
            self.assertEqual(m00467.bucket_for_size(size), bucket)


if __name__ == "__main__":
    unittest.main()
