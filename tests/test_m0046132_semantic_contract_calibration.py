"""Unit tests for the M004.6.13.2 benchmark harness."""

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.benchmarks.m0046132_semantic_contract_calibration import (
    CONFIGURATIONS,
    POLICY_V1,
    POLICY_V2,
    QWEN_MODEL,
    QWEN_SEMANTIC_OPTIONS,
    SCHEMA_V1,
    SCHEMA_V2,
    SENTINELS,
    build_prompt_for_config,
    check_calibration_gate,
    compute_sha256,
    evaluate_results,
    is_full_contract_valid,
    select_calibration_sample,
    selection_hash_for_pair,
)


def _mock_reference_data():
    pairs = [
        # Sentinels
        {
            "pair_id": "charge:noun:8b49b912413a:c1f8d19006ac7ddf",
            "word": "charge",
            "pos": "noun",
            "reference_decision": "merge",
            "first": {"definition": ["An accusation."], "source_sense_id": "s1"},
            "second": {"definition": ["An accusation."], "source_sense_id": "s2"},
        },
        {
            "pair_id": "cleave:verb:06bbcdfef61b:b90d5075d1e6ab47",
            "word": "cleave",
            "pos": "verb",
            "reference_decision": "merge",
            "first": {"definition": ["Split crystal."], "source_sense_id": "s3"},
            "second": {"definition": ["Split crystal plane."], "source_sense_id": "s4"},
        },
        {
            "pair_id": "charge:noun:8b49b912413a:5a79e6778413c507",
            "word": "charge",
            "pos": "noun",
            "reference_decision": "keep_separate",
            "first": {"definition": ["Electric charge."], "source_sense_id": "s5"},
            "second": {"definition": ["CHARGE syndrome."], "source_sense_id": "s6"},
        },
    ]
    # Add dummy merge pairs to reach 8 merges
    for i in range(1, 15):
        pairs.append({
            "pair_id": f"merge_pair_{i:02d}",
            "word": "test",
            "pos": "noun",
            "reference_decision": "merge",
            "first": {"definition": [f"m1_{i}"], "source_sense_id": f"ms1_{i}"},
            "second": {"definition": [f"m2_{i}"], "source_sense_id": f"ms2_{i}"},
        })

    # Add dummy keep_separate pairs to reach 8 keeps
    for i in range(1, 15):
        pairs.append({
            "pair_id": f"keep_pair_{i:02d}",
            "word": "test",
            "pos": "noun",
            "reference_decision": "keep_separate",
            "first": {"definition": [f"k1_{i}"], "source_sense_id": f"ks1_{i}"},
            "second": {"definition": [f"k2_{i}"], "source_sense_id": f"ks2_{i}"},
        })

    return {"candidate_pairs": pairs}


class BenchmarkHarnessTests(unittest.TestCase):
    def test_selection_hashing_is_stable(self):
        h1 = selection_hash_for_pair("charge:noun:1")
        h2 = selection_hash_for_pair("charge:noun:1")
        h3 = selection_hash_for_pair("charge:noun:2")
        self.assertEqual(h1, h2)
        self.assertNotEqual(h1, h3)

    def test_sample_selection_includes_sentinels_and_reaches_exact_counts(self):
        ref_data = _mock_reference_data()
        sample = select_calibration_sample(ref_data)
        self.assertEqual(len(sample), 16)
        merges = [p for p in sample if p["reference_decision"] == "merge"]
        keeps = [p for p in sample if p["reference_decision"] == "keep_separate"]
        self.assertEqual(len(merges), 8)
        self.assertEqual(len(keeps), 8)

        # Confirm sentinels are included
        sample_ids = {p["pair_id"] for p in sample}
        for sentinel_id in SENTINELS:
            self.assertIn(sentinel_id, sample_ids)

    def test_configurations_differ_only_in_prompt_and_schema(self):
        self.assertEqual(set(CONFIGURATIONS), {"A", "B", "C", "D"})
        self.assertEqual(CONFIGURATIONS["A"]["policy"], POLICY_V1)
        self.assertEqual(CONFIGURATIONS["A"]["schema"], SCHEMA_V1)
        self.assertEqual(CONFIGURATIONS["B"]["policy"], POLICY_V1)
        self.assertEqual(CONFIGURATIONS["B"]["schema"], SCHEMA_V2)
        self.assertEqual(CONFIGURATIONS["C"]["policy"], POLICY_V2)
        self.assertEqual(CONFIGURATIONS["C"]["schema"], SCHEMA_V1)
        self.assertEqual(CONFIGURATIONS["D"]["policy"], POLICY_V2)
        self.assertEqual(CONFIGURATIONS["D"]["schema"], SCHEMA_V2)

    def test_common_seven_combination_scoring(self):
        # Valid combinations
        self.assertTrue(is_full_contract_valid("merge", "paraphrase_or_duplicate"))
        self.assertTrue(is_full_contract_valid("merge", "contextual_variant"))
        self.assertTrue(is_full_contract_valid("keep_separate", "specialized_subsense"))
        self.assertTrue(is_full_contract_valid("keep_separate", "broader_or_narrower"))
        self.assertTrue(is_full_contract_valid("keep_separate", "related_but_distinct"))
        self.assertTrue(is_full_contract_valid("keep_separate", "materially_different"))
        self.assertTrue(is_full_contract_valid("uncertain", "insufficient_evidence"))

        # Invalid combinations
        self.assertFalse(is_full_contract_valid("merge", "specialized_subsense"))
        self.assertFalse(is_full_contract_valid("keep_separate", "paraphrase_or_duplicate"))
        self.assertFalse(is_full_contract_valid("uncertain", "materially_different"))
        self.assertFalse(is_full_contract_valid("invalid_dec", "paraphrase_or_duplicate"))
        self.assertFalse(is_full_contract_valid("merge", "invalid_reason"))

    def test_evaluate_results_metrics_and_false_merges(self):
        scored_pairs = [
            {"pair_id": "m1", "reference_decision": "merge"},
            {"pair_id": "m2", "reference_decision": "merge"},
            {"pair_id": "k1", "reference_decision": "keep_separate"},
            {"pair_id": "k2", "reference_decision": "keep_separate"},
        ]
        results = [
            {"pair_id": "m1", "status": "provider_success", "decision": "merge", "reason": "paraphrase_or_duplicate", "full_contract_valid": True},
            {"pair_id": "m2", "status": "provider_success", "decision": "keep_separate", "reason": "materially_different", "full_contract_valid": True}, # False split
            {"pair_id": "k1", "status": "provider_success", "decision": "keep_separate", "reason": "materially_different", "full_contract_valid": True},
            {"pair_id": "k2", "status": "provider_success", "decision": "merge", "reason": "contextual_variant", "full_contract_valid": True}, # False merge!
        ]

        metrics = evaluate_results(scored_pairs, results)
        self.assertEqual(metrics["total_scored_pairs"], 4)
        self.assertEqual(metrics["exact_decision_accuracy"], 0.5) # 2 correct out of 4
        self.assertEqual(metrics["merge_true_positives"], 1)
        self.assertEqual(metrics["merge_false_negatives"], 1)
        self.assertEqual(metrics["merge_recall"], 0.5) # 1 of 2 merges
        self.assertEqual(metrics["false_merge_count"], 1)
        self.assertEqual(metrics["false_split_count"], 1)

    def test_calibration_gate_pass_and_fail_conditions(self):
        passing_metrics = {
            "false_merge_count": 0,
            "contract_invalid_count": 0,
            "merge_recall": 0.875, # 7 of 8
            "malformed_parse_error_count": 0,
            "predicted_merge_count": 7,
            "keep_separate_correct": 8,
        }
        gate_pass = check_calibration_gate(passing_metrics)
        self.assertTrue(gate_pass["gate_pass"])

        failing_false_merge = dict(passing_metrics, false_merge_count=1)
        self.assertFalse(check_calibration_gate(failing_false_merge)["gate_pass"])

        failing_recall = dict(passing_metrics, merge_recall=0.5)
        self.assertFalse(check_calibration_gate(failing_recall)["gate_pass"])

        failing_invalid = dict(passing_metrics, contract_invalid_count=1)
        self.assertFalse(check_calibration_gate(failing_invalid)["gate_pass"])


if __name__ == "__main__":
    unittest.main()
