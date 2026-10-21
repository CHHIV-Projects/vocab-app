import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from tools.benchmarks.m002002_compatibility_trial import (
    CompatibilityProvider, MODELS, PINNED, WORDS, run, schedule,
)
from tests.test_synthesis import evidence


class CompatibilityTrialTests(unittest.TestCase):
    def test_only_thinking_option_changes_at_transport(self):
        response = Mock()
        response.json.return_value = {"message": {"content": "exact", "thinking": "PRIVATE"}}
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            provider = CompatibilityProvider("http://fixture", MODELS[0], [0], directory)
            with patch("tools.benchmarks.m002002_alternate_trial.get_json", side_effect=[
                {"models": []}, {"models": [
                    {"name": MODELS[0], "size": 100, "size_vram": 100, "context_length": 16384}
                ]},
            ]), patch("vocab_synthesis.requests.post", return_value=response) as post:
                provider.generate("exact prompt", seed=42, schema={"type": "object"})
            body = post.call_args.kwargs["json"]
            self.assertEqual(body, {
                "model": MODELS[0], "messages": [{"role": "user", "content": "exact prompt"}],
                "stream": False, "format": {"type": "object"}, "think": False,
                "keep_alive": "5m",
                "options": {"temperature": 0, "num_predict": 3200, "num_ctx": 16384, "seed": 42},
            })
            self.assertEqual(post.call_args.kwargs["timeout"], 180)
            self.assertEqual(json.loads((directory / "request-001.json").read_text()), body)
            self.assertNotIn("PRIVATE", (directory / "provider-response-001.json").read_text())

    def test_schedule_counts_probe_once(self):
        rows = schedule()
        self.assertEqual(rows[0], (1, "lantern"))
        self.assertEqual(len(rows), 24)
        self.assertEqual(len(set(rows)), 24)
        self.assertEqual(sum(lemma == "lantern" for _, lemma in rows), 3)

    def run_fixture(self, first_validates):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "run"
            installed = {"models": [{"name": model, "digest": PINNED[model]} for model in MODELS]}

            def get_state(endpoint, route):
                return installed if route == "/api/tags" else {"models": []}

            calls = []

            def evaluate(directory, frozen, provider):
                directory.mkdir()
                calls.append((provider.model, directory.name))
                valid = first_validates
                return {"status": "validated" if valid else "rejected",
                        "error_code": None if valid else "output_truncated",
                        "lemma": "fixture", "synthesis_elapsed_seconds": 0.01}

            with patch("tools.benchmarks.m002002_compatibility_trial.frozen_evidence",
                       return_value={lemma: evidence() for lemma in WORDS}), \
                 patch("tools.benchmarks.m002002_compatibility_trial.get_json", side_effect=get_state), \
                 patch("tools.benchmarks.m002002_compatibility_trial.evaluate", side_effect=evaluate), \
                 patch("builtins.print"):
                run(Path("unused"), output, "http://fixture")
            return calls, json.loads((output / "results.json").read_text())

    def test_rejected_probe_stops_each_candidate_after_one_attempt(self):
        calls, report = self.run_fixture(False)
        self.assertEqual(calls, [(model, "r1-lantern") for model in MODELS])
        self.assertEqual(len(report["attempts"]), 2)

    def test_valid_probe_enables_only_remaining_approved_schedule(self):
        calls, report = self.run_fixture(True)
        self.assertEqual(len(calls), 48)
        for model in MODELS:
            names = [name for candidate, name in calls if candidate == model]
            self.assertEqual(names, [f"r{repeat}-{lemma}" for repeat, lemma in schedule()])
        self.assertTrue(all(row["comparison"].startswith("NON-EQUIVALENT")
                            for row in report["attempts"]))


if __name__ == "__main__":
    unittest.main()
