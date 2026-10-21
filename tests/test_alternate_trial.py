import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from tools.benchmarks.m002002_alternate_trial import (
    BoundedProvider, INFERENCE_CAP, MODELS, WORDS,
)
from tools.benchmarks.m002002_alternate_report import export
from vocab_synthesis import SynthesisFailure


class AlternateTrialTests(unittest.TestCase):
    def test_exact_approved_scope(self):
        self.assertEqual(MODELS, ("qwen3.5:9b", "ministral-3:14b"))
        self.assertEqual(WORDS, ("lantern", "useful", "bread", "phone", "jelly",
                                 "staff", "bank", "draft"))
        self.assertEqual(len(WORDS) * 3, 24)

    def test_unsupported_settings_stop_without_adaptation(self):
        response = Mock(status_code=400)
        response.json.return_value = {"error": "think low unsupported"}
        response.raise_for_status.side_effect = requests.HTTPError(response=response)
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            provider = BoundedProvider("http://fixture", MODELS[0], [0.0], directory)
            with patch("tools.benchmarks.m002002_alternate_trial.get_json",
                       return_value={"models": []}), \
                 patch("vocab_synthesis.requests.post", return_value=response) as post:
                with self.assertRaises(SynthesisFailure) as raised:
                    provider.generate("exact prompt", schema={"type": "object"})
                self.assertEqual(raised.exception.code, "provider_incompatible")
                self.assertEqual(post.call_count, 1)
                body = post.call_args.kwargs["json"]
                self.assertEqual(body["think"], "low")
                self.assertEqual(body["options"], {"temperature": 0, "num_predict": 3200,
                                                  "num_ctx": 16384})
                self.assertEqual(post.call_args.kwargs["timeout"], 180)
                self.assertEqual(json.loads((directory / "provider-error-001.json").read_text()),
                                 {"status": 400, "error": "think low unsupported"})

    def test_budget_and_shared_model_stop_before_request(self):
        with tempfile.TemporaryDirectory() as temporary:
            provider = BoundedProvider("http://fixture", MODELS[0], [INFERENCE_CAP - 179],
                                       Path(temporary))
            with patch("vocab_synthesis.requests.post") as post:
                with self.assertRaises(SynthesisFailure) as raised:
                    provider.generate("unused")
                self.assertEqual(raised.exception.code, "lane_budget_stop")
                post.assert_not_called()
            provider.budget[0] = 0
            with patch("tools.benchmarks.m002002_alternate_trial.get_json",
                       return_value={"models": [{"name": "unrelated"}]}), \
                 patch("vocab_synthesis.requests.post") as post:
                with self.assertRaises(SynthesisFailure) as raised:
                    provider.generate("unused")
                self.assertEqual(raised.exception.code, "shared_workload_stop")
                post.assert_not_called()

    def test_runtime_fit_stop_preserves_response_without_private_reasoning(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            provider = BoundedProvider("http://fixture", MODELS[0], [0], directory)
            with patch("tools.benchmarks.m002002_alternate_trial.get_json", side_effect=[
                {"models": []},
                {"models": [{"name": MODELS[0], "size": 100, "size_vram": 90,
                             "context_length": 16384}]},
            ]), patch("tools.benchmarks.m002002_alternate_trial.OllamaProvider.generate",
                      return_value={"message": {"content": "exact", "thinking": "PRIVATE"}}):
                with self.assertRaises(SynthesisFailure) as raised:
                    provider.generate("unused")
                self.assertEqual(raised.exception.code, "runtime_fit_stop")
                text = (directory / "provider-response-001.json").read_text()
                self.assertIn("exact", text)
                self.assertNotIn("PRIVATE", text)

    def test_report_does_not_turn_provider_stops_into_semantic_failures(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pilot, run = root / "pilot", root / "run"
            pilot.mkdir()
            run.mkdir()
            baseline = []
            for order, lemma in enumerate(WORDS, 1):
                row = {"lemma": lemma, "order": order, "status": "validated",
                       "evidence_set_hash": "fixture", "synthesis_elapsed_seconds": 1}
                baseline.append(row)
                directory = pilot / f"{order:02d}-{lemma}"
                directory.mkdir()
                (directory / "review.json").write_text("[]")
                (directory / "call-001.json").write_text(
                    '{"prompt":"fixture","schema":{},"seed":null}')
            (pilot / "attempts.jsonl").write_text(
                "".join(json.dumps(row) + "\n" for row in baseline))
            attempts = []
            for model in MODELS:
                directory = run / model.replace(":", "-")
                directory.mkdir()
                (directory / "model.json").write_text('{"digest":"fixture","size":1}')
                attempt = directory / "r1-lantern"
                attempt.mkdir()
                (attempt / "review.json").write_text("[]")
                (attempt / "call-001.json").write_text(
                    '{"prompt":"fixture","schema":{},"seed":null}')
                attempts.append({"model": model, "lemma": "lantern", "repeat": 1,
                                 "status": "rejected", "error_code": "provider_incompatible",
                                 "error": "unsupported", "synthesis_elapsed_seconds": 0.01,
                                 "evidence_set_hash": "fixture"})
            (run / "results.json").write_text(json.dumps({"attempts": attempts}))
            report = export(run, pilot, root / "report")
            self.assertEqual([row["attempts"] for row in report["comparisons"]], [8, 1, 1])
            self.assertEqual(report["comparisons"][1]["errors"], {"provider_incompatible": 1})
            self.assertIn("not a semantic failure", report["interpretation"])
            self.assertIn("UNJUDGED", (root / "report_review.csv").read_text())
            changed_call = run / MODELS[0].replace(":", "-") / "r1-lantern/call-001.json"
            changed_call.write_text('{"prompt":"changed","schema":{},"seed":null}')
            with self.assertRaisesRegex(ValueError, "Initial scaffold contract differs"):
                export(run, pilot, root / "invalid")


if __name__ == "__main__":
    unittest.main()
