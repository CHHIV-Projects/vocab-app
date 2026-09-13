"""Unit tests for M004.6.13.3 Relation-Only Exit Gate Benchmark tool."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from tools.benchmarks.m0046133_relation_only_exit_gate import (
    ALLOWED_RELATIONS,
    DETERMINISTIC_ACTION_MAP,
    RELATION_ONLY_SCHEMA,
    derive_action_from_relation,
    evaluate_exit_gate_metrics,
    evaluate_gate_pass,
    generate_review_packet,
    select_exit_gate_sample,
)


class TestRelationOnlyExitGateBenchmark(unittest.TestCase):
    def test_schema_and_allowed_relations_count(self):
        """Test relation schema contains exactly seven states."""
        self.assertEqual(len(ALLOWED_RELATIONS), 7)
        enum_values = RELATION_ONLY_SCHEMA["properties"]["relation"]["enum"]
        self.assertEqual(enum_values, ALLOWED_RELATIONS)
        self.assertEqual(len(enum_values), 7)

    def test_deterministic_action_mapping_exact(self):
        """Test relation->action mapping is exact for all 7 relations."""
        self.assertEqual(derive_action_from_relation("paraphrase_or_duplicate"), "merge")
        self.assertEqual(derive_action_from_relation("contextual_variant"), "merge")
        self.assertEqual(derive_action_from_relation("specialized_subsense"), "keep_separate")
        self.assertEqual(derive_action_from_relation("broader_or_narrower"), "keep_separate")
        self.assertEqual(derive_action_from_relation("related_but_distinct"), "keep_separate")
        self.assertEqual(derive_action_from_relation("materially_different"), "keep_separate")
        self.assertEqual(derive_action_from_relation("insufficient_evidence"), "uncertain")

        self.assertIsNone(derive_action_from_relation("unknown_relation"))
        self.assertIsNone(derive_action_from_relation(None))

    def test_selection_excludes_m132_and_selects_exact_counts(self):
        """Test M004.6.13.2 pair IDs are excluded and deterministic selection yields 20 MERGE, 40 KEEP, 6 UNCERTAIN."""
        mock_ref = {
            "candidate_pairs": [
                {
                    "pair_id": "excluded_p1",
                    "word": "test",
                    "pos": "noun",
                    "reference_decision": "merge",
                    "first": {"source_sense_id": "s1"},
                    "second": {"source_sense_id": "s2"},
                }
            ]
        }
        # Add 25 merges, 45 keeps, 7 uncertains
        for i in range(25):
            mock_ref["candidate_pairs"].append(
                {
                    "pair_id": f"merge_{i}",
                    "word": f"word_m_{i}",
                    "pos": "noun",
                    "reference_decision": "merge",
                    "first": {"source_sense_id": f"m1_{i}"},
                    "second": {"source_sense_id": f"m2_{i}"},
                }
            )
        for i in range(45):
            mock_ref["candidate_pairs"].append(
                {
                    "pair_id": f"keep_{i}",
                    "word": f"word_k_{i}",
                    "pos": "noun",
                    "reference_decision": "keep_separate",
                    "first": {"source_sense_id": f"k1_{i}"},
                    "second": {"source_sense_id": f"k2_{i}"},
                }
            )
        for i in range(7):
            mock_ref["candidate_pairs"].append(
                {
                    "pair_id": f"unc_{i}",
                    "word": f"word_u_{i}",
                    "pos": "noun",
                    "reference_decision": "uncertain",
                    "first": {"source_sense_id": f"u1_{i}"},
                    "second": {"source_sense_id": f"u2_{i}"},
                }
            )

        mock_m132 = {"sample": [{"pair_id": "excluded_p1"}]}

        result = select_exit_gate_sample(mock_ref, mock_m132)
        primary = result["primary_sample"]
        aux = result["auxiliary_uncertain_sample"]

        selected_ids = {p["pair_id"] for p in primary}
        self.assertNotIn("excluded_p1", selected_ids)

        merges = [p for p in primary if p["reference_decision"] == "merge"]
        keeps = [p for p in primary if p["reference_decision"] == "keep_separate"]

        self.assertEqual(len(primary), 60)
        self.assertEqual(len(merges), 20)
        self.assertEqual(len(keeps), 40)
        self.assertEqual(len(aux), 6)

    def test_metrics_and_gate_evaluation_go(self):
        """Test metrics calculation and GO disposition when thresholds are satisfied."""
        mock_results = []
        # 20 MERGE refs: 15 tp (contextual_variant -> merge), 5 fn (specialized_subsense -> keep_separate)
        for i in range(15):
            mock_results.append(
                {
                    "pair_id": f"m_{i}",
                    "reference_decision": "merge",
                    "relation": "contextual_variant",
                    "derived_action": "merge",
                    "parse_error": False,
                }
            )
        for i in range(5):
            mock_results.append(
                {
                    "pair_id": f"m_fn_{i}",
                    "reference_decision": "merge",
                    "relation": "specialized_subsense",
                    "derived_action": "keep_separate",
                    "parse_error": False,
                }
            )

        # 40 KEEP refs: 37 correct (materially_different -> keep_separate), 3 keep->merge (paraphrase_or_duplicate -> merge)
        for i in range(37):
            mock_results.append(
                {
                    "pair_id": f"k_{i}",
                    "reference_decision": "keep_separate",
                    "relation": "materially_different",
                    "derived_action": "keep_separate",
                    "parse_error": False,
                }
            )
        for i in range(3):
            mock_results.append(
                {
                    "pair_id": f"k_fp_{i}",
                    "reference_decision": "keep_separate",
                    "relation": "paraphrase_or_duplicate",
                    "derived_action": "merge",
                    "parse_error": False,
                }
            )

        metrics = evaluate_exit_gate_metrics(mock_results)
        self.assertEqual(metrics["total_primary_scored"], 60)
        self.assertEqual(metrics["ref_merge_count"], 20)
        self.assertEqual(metrics["ref_keep_count"], 40)

        # MERGE recall: 15 / 20 = 75%
        self.assertEqual(metrics["merge_reference_recall"], 0.75)
        # KEEP->MERGE disagreement: 3 / 40 = 7.5%
        self.assertEqual(metrics["keep_to_merge_disagreement_count"], 3)
        self.assertEqual(metrics["keep_to_merge_disagreement_rate"], 0.075)
        # Derived UNCERTAIN rate: 0 / 60 = 0%
        self.assertEqual(metrics["derived_uncertain_rate"], 0.0)

        gate = evaluate_gate_pass(metrics)
        self.assertTrue(gate["is_go"])
        self.assertEqual(gate["disposition"], "GO")

    def test_metrics_and_gate_evaluation_no_go(self):
        """Test NO_GO disposition when KEEP->MERGE exceeds threshold (> 4 / 40)."""
        mock_results = []
        # 20 MERGE refs: 12 tp (merge recall = 60%)
        for i in range(12):
            mock_results.append(
                {
                    "pair_id": f"m_{i}",
                    "reference_decision": "merge",
                    "relation": "paraphrase_or_duplicate",
                    "derived_action": "merge",
                }
            )
        for i in range(8):
            mock_results.append(
                {
                    "pair_id": f"m_fn_{i}",
                    "reference_decision": "merge",
                    "relation": "related_but_distinct",
                    "derived_action": "keep_separate",
                }
            )

        # 40 KEEP refs: 35 correct, 5 keep->merge (exceeds max allowed 4)
        for i in range(35):
            mock_results.append(
                {
                    "pair_id": f"k_{i}",
                    "reference_decision": "keep_separate",
                    "relation": "materially_different",
                    "derived_action": "keep_separate",
                }
            )
        for i in range(5):
            mock_results.append(
                {
                    "pair_id": f"k_fp_{i}",
                    "reference_decision": "keep_separate",
                    "relation": "contextual_variant",
                    "derived_action": "merge",
                }
            )

        metrics = evaluate_exit_gate_metrics(mock_results)
        self.assertEqual(metrics["keep_to_merge_disagreement_count"], 5)

        gate = evaluate_gate_pass(metrics)
        self.assertFalse(gate["is_go"])
        self.assertEqual(gate["disposition"], "NO_GO")
        self.assertFalse(gate["keep_to_merge_lte_10_pct"])

    def test_review_packet_generation(self):
        """Test review packet contains all required disagreement categories."""
        primary_mock = [
            {
                "pair_id": "p_km",
                "word": "w1",
                "pos": "noun",
                "reference_decision": "keep_separate",
                "relation": "contextual_variant",
                "derived_action": "merge",
                "first": {"definition": ["def a"]},
                "second": {"definition": ["def b"]},
            },
            {
                "pair_id": "p_mk",
                "word": "w2",
                "pos": "verb",
                "reference_decision": "merge",
                "relation": "broader_or_narrower",
                "derived_action": "keep_separate",
                "first": {"definition": ["def c"]},
                "second": {"definition": ["def d"]},
            },
            {
                "pair_id": "p_mu",
                "word": "w3",
                "pos": "noun",
                "reference_decision": "merge",
                "relation": "insufficient_evidence",
                "derived_action": "uncertain",
                "first": {"definition": ["def e"]},
                "second": {"definition": ["def f"]},
            },
            {
                "pair_id": "p_ku",
                "word": "w4",
                "pos": "adj",
                "reference_decision": "keep_separate",
                "relation": "insufficient_evidence",
                "derived_action": "uncertain",
                "first": {"definition": ["def g"]},
                "second": {"definition": ["def h"]},
            },
        ]
        aux_mock = [
            {
                "pair_id": "p_aux1",
                "word": "w5",
                "pos": "verb",
                "reference_decision": "uncertain",
                "relation": "contextual_variant",
                "derived_action": "merge",
                "first": {"definition": ["def i"]},
                "second": {"definition": ["def j"]},
            }
        ]

        pkt_json, pkt_md = generate_review_packet(primary_mock, aux_mock)

        self.assertEqual(len(pkt_json["keep_to_merge_disagreements"]), 1)
        self.assertEqual(len(pkt_json["merge_to_keep_disagreements"]), 1)
        self.assertEqual(len(pkt_json["merge_to_uncertain_disagreements"]), 1)
        self.assertEqual(len(pkt_json["keep_to_uncertain_disagreements"]), 1)
        self.assertEqual(len(pkt_json["auxiliary_uncertain_results"]), 1)

        self.assertIn("KEEP→MERGE Disagreements (Safety Critical)", pkt_md)
        self.assertIn("MERGE→KEEP Disagreements (Recall)", pkt_md)
        self.assertIn("p_km", pkt_md)
        self.assertIn("p_aux1", pkt_md)


if __name__ == "__main__":
    unittest.main()
