import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_synthesis import FakeProvider, evidence
from tools.benchmarks.m002002_compatibility_trial import CONTRACT, MODELS, PINNED
from tools.benchmarks.m002002_consolidated_report import checked_sources, export
from tools.benchmarks.m002002_product_trial import evaluate, source_rows
from vocab_lexical_engine import evidence_set_hash


class ConsolidatedReportTests(unittest.TestCase):
    def test_exact_sources_reject_gloss_or_pos_changes(self):
        frozen = evidence()
        sources = source_rows(frozen, ["sense-1"])
        checked_sources(frozen, sources)
        sources[0]["glosses"] = ["changed"]
        with self.assertRaisesRegex(ValueError, "differs from frozen"):
            checked_sources(frozen, sources)

    def test_consolidation_preserves_exact_wording_and_blank_human_labels(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pilot, run, narrow = root / "pilot", root / "run", root / "narrow"
            for directory in (pilot, run, narrow):
                directory.mkdir()
            frozen = evidence()
            frozen["normalized_lemma"] = "lantern"
            original = evaluate(pilot / "01-lantern", frozen, FakeProvider("valid"))
            original["order"] = 1
            (pilot / "attempts.jsonl").write_text(json.dumps(original) + "\n")
            narrow_model = {"name": "gpt-oss:20b", "digest": "narrow-fixture"}
            (narrow / "manifest.json").write_text(json.dumps({"model": narrow_model}))
            for index in range(21):
                (narrow / f"repeat-{index // 7 + 1}-sense-{index % 7 + 1}.json").write_text(
                    json.dumps({
                        "lemma": "lantern", "repeat": index // 7 + 1, "status": "validated",
                        "source": source_rows(frozen, ["sense-1"])[0],
                        "evidence_set_hash": evidence_set_hash(frozen),
                        "wording": "EXACT_NARROW", "total_seconds": 0.01,
                    }))
            attempts = []
            for model in MODELS:
                directory = run / model.replace(":", "-")
                directory.mkdir()
                (directory / "model.json").write_text(json.dumps({"digest": PINNED[model]}))
                attempt_dir = directory / "r1-lantern"
                attempt = evaluate(attempt_dir, frozen, FakeProvider("valid"))
                attempt.update(model=model, model_digest=PINNED[model], repeat=1,
                               is_probe=True, comparison=CONTRACT)
                attempts.append(attempt)
                for index, path in enumerate(sorted(attempt_dir.glob("call-*.json")), 1):
                    call = json.loads(path.read_text())
                    request = {
                        "model": model, "messages": [{"role": "user", "content": call["prompt"]}],
                        "stream": False, "format": call["schema"], "think": False, "keep_alive": "5m",
                        "options": {"temperature": 0, "num_ctx": 16384, "num_predict": 3200},
                    }
                    (directory / f"request-{index:03d}.json").write_text(json.dumps(request))
            (run / "results.json").write_text(json.dumps({"attempts": attempts}))
            with patch("tools.benchmarks.m002002_consolidated_report.frozen_evidence",
                       return_value={"lantern": frozen}):
                report = export(run, pilot, narrow, root / "review")
                self.assertEqual(report["narrow_attempts"], 21)
                self.assertEqual(report["human_reviewed"], 0)
                self.assertEqual(report["rows"][0]["wording"], "EXACT_NARROW")
                self.assertEqual(report["rows"][0]["row_id"], "R0001")
                self.assertTrue(all(row["semantic_classification"] == "" and
                                    row["human_reviewer"] == "" and not row["human_reviewed"]
                                    for row in report["rows"]))
                self.assertTrue(any(row["stage"] == "final" for row in report["rows"]))
                with (root / "review_review.csv").open() as stream:
                    rows = list(csv.DictReader(stream))
                self.assertEqual(len(rows), len(report["rows"]))
                request = run / MODELS[0].replace(":", "-") / "request-001.json"
                value = json.loads(request.read_text())
                value["options"]["num_predict"] = 6400
                request.write_text(json.dumps(value))
                with self.assertRaisesRegex(ValueError, "changed more than the thinking option"):
                    export(run, pilot, narrow, root / "invalid")


if __name__ == "__main__":
    unittest.main()
