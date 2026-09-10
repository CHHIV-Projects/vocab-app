import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("m00464_benchmark", ROOT / "tools/benchmarks/m0046_policy_batched_benchmark.py")
assert SPEC and SPEC.loader
benchmark = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(benchmark)
ADJ_SPEC = importlib.util.spec_from_file_location("m00464_adjudication", ROOT / "tools/benchmarks/m0046_reference_adjudication.py")
assert ADJ_SPEC and ADJ_SPEC.loader
adjudication = importlib.util.module_from_spec(ADJ_SPEC)
ADJ_SPEC.loader.exec_module(adjudication)


class M00464PolicyBatchedTests(unittest.TestCase):
    def test_refined_contract_rejects_invalid_or_inconsistent_pairs(self):
        self.assertTrue(all(benchmark.decision_diagnostics({"decision": "merge", "reason": "paraphrase_or_duplicate"}).values()))
        self.assertFalse(benchmark.decision_diagnostics({"decision": "merge", "reason": "materially_different"})["decision_reason_consistent"])
        self.assertFalse(benchmark.decision_diagnostics({"decision": "unknown", "reason": "materially_different"})["allowed_values"])

    def test_batch_contract_requires_exact_code_owned_pair_coverage(self):
        valid = {"P001": {"decision": "merge", "reason": "contextual_variant"}, "P002": {"decision": "keep_separate", "reason": "specialized_subsense"}}
        self.assertTrue(all(benchmark.batch_diagnostics(valid, ["P001", "P002"]).values()))
        self.assertFalse(benchmark.batch_diagnostics({"P001": valid["P001"]}, ["P001", "P002"])["complete_pair_coverage"])
        self.assertFalse(benchmark.batch_diagnostics({**valid, "P999": valid["P001"]}, ["P001", "P002"])["complete_pair_coverage"])

    def test_complete_link_blocks_missing_or_explicitly_separate_cross_evidence(self):
        evidence = [
            {"source_sense_ids": ["S001", "S002"], "majority_decision": "merge"},
            {"source_sense_ids": ["S002", "S003"], "majority_decision": "merge"},
            {"source_sense_ids": ["S001", "S003"], "majority_decision": "keep_separate"},
        ]
        result = benchmark.cluster(["S001", "S002", "S003"], evidence, "complete-link")
        self.assertEqual([item["source_sense_ids"] for item in result["containers"]], [["S001", "S002"], ["S003"]])
        self.assertEqual(result["conflicts"][0]["reason"], "explicit_keep_separate")
        self.assertTrue(all(result["invariants"].values()))

    def test_reference_scores_separate_false_merges_and_splits(self):
        reference = [{"pair_id": "P001", "reference_decision": "merge"}, {"pair_id": "P002", "reference_decision": "keep_separate"}]
        results = {"P001": {"majority_decision": "keep_separate"}, "P002": {"majority_decision": "merge"}}
        score = benchmark.scores(results, reference)
        self.assertEqual(score["false_merges"], 1)
        self.assertEqual(score["false_splits"], 1)
        self.assertEqual(score["merge_recall"], 0.0)

    def test_manifest_and_anchor_identity_are_valid(self):
        manifest = benchmark.load_manifest(ROOT / "tools/benchmarks/manifests/m004.6.4_policy_batched_reference.json")
        refs = benchmark.references(manifest)
        self.assertEqual(len(refs), len(manifest["pairs"]))
        self.assertTrue(refs[0]["pair_id"].startswith("P"))
        self.assertEqual(benchmark.chunks(refs, 20)[0][0]["pair_id"], "P001")

    def test_anchor_proposals_require_complete_merge_evidence(self):
        reference = [
            {"pair_id": "P001", "word": "word", "pos": "noun", "first": {"source_sense_id": "S001"}, "second": {"source_sense_id": "S002"}},
            {"pair_id": "P002", "word": "word", "pos": "noun", "first": {"source_sense_id": "S001"}, "second": {"source_sense_id": "S003"}},
        ]
        decisions = {
            "anchor:model:P001": {"majority_decision": "merge"},
            "anchor:model:P002": {"majority_decision": "merge"},
        }
        proposal = benchmark.anchor_proposals(reference, decisions, "model")[0]
        self.assertEqual(proposal["safety_accepted_source_sense_ids"], ["S001", "S002"])
        self.assertEqual(proposal["blocked_candidates"], [{"source_sense_id": "S003", "reason": "missing_complete_merge_evidence"}])

    def test_adjudication_versions_only_named_policy_sensitive_pairs(self):
        reference = [
            {"pair_id": "P010", "word": "charge", "pos": "noun", "reference_decision": "keep_separate", "reference_reason": "specialized_subsense"},
            {"pair_id": "P001", "word": "charge", "pos": "noun", "reference_decision": "merge", "reference_reason": "paraphrase_or_duplicate"},
        ]
        corrected, changes = adjudication.adjudicate(reference)
        self.assertEqual(corrected[0]["reference_decision"], "uncertain")
        self.assertEqual(corrected[1]["reference_decision"], "merge")
        self.assertEqual([row["pair_id"] for row in changes], ["P010"])


if __name__ == "__main__":
    unittest.main()
