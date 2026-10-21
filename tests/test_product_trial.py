import json
import tempfile
import unittest
import shutil
from pathlib import Path

from tests.test_synthesis import FakeProvider, evidence
from tools.benchmarks.m002002_product_trial import (
    RecordedProvider, evaluate, pilot_rows, prepare, public_payload, review_rows,
)
from unittest.mock import patch
from tools.benchmarks.m002002_product_trial_report import export


class ProductTrialTests(unittest.TestCase):
    def test_approved_pilot_split_and_interleaving(self):
        rows = pilot_rows()
        self.assertEqual(len(rows), 20)
        self.assertEqual([row["stratum"] for row in rows[:3]],
                         ["normal", "complexity", "challenge"])
        self.assertEqual(rows[2]["normalized_lemma"], "lantern")
        self.assertEqual(len({row["normalized_lemma"] for row in rows}), 20)

    def test_success_reuses_production_pipeline_and_keeps_semantics_unjudged(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "attempt"
            result = evaluate(path, evidence(), FakeProvider("valid"))
            self.assertEqual(result["status"], "validated")
            self.assertTrue(result["fresh_generation"])
            self.assertFalse(result["cache_hit"])
            self.assertEqual(result["semantic_classification"], "UNJUDGED")
            self.assertTrue(any(row["stage"] == "final_validation"
                                for row in result["function_timings"]))
            review = json.loads((path / "review.json").read_text())
            self.assertTrue(all(row["semantic_classification"] == "UNJUDGED" for row in review))
            self.assertEqual(review[0]["sources"][0]["source_sense_id"], "sense-1")
            self.assertEqual(review[0]["wording"], "supported")
            for file in path.glob("*.json"):
                payload = file.read_text()
                self.assertNotIn("ignored reasoning", payload)
                self.assertNotIn('"message_thinking"', payload)

    def test_failed_structured_output_retained_without_private_thinking(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "attempt"
            result = evaluate(path, evidence(), FakeProvider('{"sense_results":{}}'))
            self.assertEqual(result["status"], "rejected")
            call = json.loads((path / "call-001.json").read_text())
            self.assertEqual(call["response"]["message"]["content"], '{"sense_results":{}}')
            self.assertNotIn("thinking", call["response"]["message"])
            self.assertTrue((path / "failure.json").exists())
            self.assertFalse((path / "validated.json").exists())

    def test_grouping_failure_keeps_the_actual_group_output(self):
        class InvalidGrouping(FakeProvider):
            def generate(self, prompt, *, seed=None, schema=None):
                if "group_assignments" in schema["properties"]:
                    return {"message": {"content": '{"group_assignments":{},"group_definitions":{}}',
                                        "thinking": "PRIVATE_SENTINEL"}}
                return super().generate(prompt, seed=seed, schema=schema)

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "attempt"
            result = evaluate(path, evidence(), InvalidGrouping("valid"))
            self.assertEqual(result["error_code"], "grouping_validation_failed")
            call = json.loads((path / "call-002.json").read_text())
            self.assertEqual(call["stage"], "grouping")
            self.assertEqual(call["response"]["message"]["content"],
                             '{"group_assignments":{},"group_definitions":{}}')
            self.assertNotIn("PRIVATE_SENTINEL", (path / "call-002.json").read_text())

    def test_freezing_rejects_corpus_inventory_drift_without_inference(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch("tools.benchmarks.m002002_product_trial.synthesis.project_synthesis_evidence",
                       return_value=evidence()), \
                 patch("tools.benchmarks.m002002_product_trial.lookup", return_value={}):
                with self.assertRaisesRegex(ValueError, "Approved lexical inventory changed"):
                    prepare(Path(temporary), Path("unused"))

    def test_provider_transport_failure_is_recorded_and_does_not_return_success(self):
        class Broken:
            model = "fake"

            def generate(self, *args, **kwargs):
                raise ConnectionError("fixture connection failure")

        with tempfile.TemporaryDirectory() as temporary:
            provider = RecordedProvider(Broken(), Path(temporary))
            with self.assertRaises(ConnectionError):
                provider.generate("{}", schema={"properties": {"sense_results": {}}})
            self.assertEqual(provider.calls[0]["error"]["type"], "ConnectionError")
            self.assertTrue((Path(temporary) / "call-001.json").exists())

    def test_sanitization_and_malformed_review_boundary(self):
        self.assertEqual(public_payload({"thinking": "secret", "nested": [{"message_thinking": "secret", "content": "keep"}]}),
                         {"nested": [{"content": "keep"}]})
        rows = review_rows(None, evidence(), [
            {"stage": "scaffold", "response": {"message": {"content": "not json"}}, "prompt": "{}"}])
        self.assertEqual(rows, [])

    def test_report_preserves_unjudged_rows_and_stratum_denominators(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original = root / "fixture"
            result = evaluate(original, evidence(), FakeProvider("valid"))
            run = root / "run"
            run.mkdir()
            rows = []
            records = []
            for index, row in enumerate(pilot_rows(), 1):
                lemma = row["normalized_lemma"]
                shutil.copytree(original, run / f"{index:02d}-{lemma}")
                records.append(dict(row, evidence_set_hash=result["evidence_set_hash"]))
                rows.append(dict(result, lemma=lemma, stratum=row["stratum"], order=index,
                                 evidence_preparation_seconds=0.1))
            (run / "attempts.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
            (run / "manifest.json").write_text(json.dumps({
                "records": records, "corpus_sha256": "fixture", "identities": {}, "source_sha256": {}}))
            (run / "model.json").write_text('{"digest":"fixture-model"}')
            report = export(run, root / "report")
            self.assertEqual(report["word_attempts"], 20)
            self.assertEqual(report["strata"]["normal"]["attempts"], 10)
            self.assertEqual(report["strata"]["complexity"]["attempts"], 6)
            self.assertEqual(report["strata"]["challenge"]["attempts"], 4)
            self.assertEqual(report["human_reviewed_meanings"], 0)
            self.assertEqual(report["semantic_verdict"], "PENDING_HUMAN_REVIEW")
            self.assertTrue((root / "report_review.csv").exists())
            self.assertIn("UNJUDGED", (root / "report_review.md").read_text())


if __name__ == "__main__":
    unittest.main()
