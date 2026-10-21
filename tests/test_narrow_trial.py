import json
import tempfile
import unittest
from pathlib import Path

from tools.benchmarks.m002002_narrow_trial import (
    SCHEMA, attempt, export, narrow_prompt, validate_definition,
)
from vocab_synthesis import SynthesisFailure


class Provider:
    def __init__(self, content, reason="stop"):
        self.content = content
        self.reason = reason
        self.calls = []

    def generate(self, prompt, **kwargs):
        self.calls.append((prompt, kwargs))
        return {"message": {"content": self.content, "thinking": "PRIVATE_SENTINEL"},
                "done_reason": self.reason}


def source():
    return {
        "lemma": "fixture", "pos": "noun", "evidence_set_hash": "fixture-hash",
        "sense_evidence": {"sense_id": "fixed-id", "source_order": 5, "glosses": ["A cupola."]},
        "source": {"source_sense_id": "fixed-id", "source_order": 5,
                   "pos": "noun", "glosses": ["A cupola."]},
    }


class NarrowTrialTests(unittest.TestCase):
    def test_identity_pos_and_order_are_owned_by_code_not_model(self):
        provider = Provider('{"definition":"A trundle wheel."}')
        row = attempt(source(), 1, provider)
        self.assertEqual(row["status"], "validated")
        self.assertEqual(row["source"], source()["source"])
        self.assertEqual(row["semantic_classification"], "UNJUDGED")
        self.assertEqual(row["wording"], "A trundle wheel.")
        self.assertEqual(provider.calls[0][1]["schema"], SCHEMA)
        self.assertNotIn("PRIVATE_SENTINEL", json.dumps(row))
        self.assertEqual(set(SCHEMA["properties"]), {"definition"})
        self.assertEqual(json.loads(narrow_prompt(source()))["source_pos"], "noun")

    def test_rejects_empty_extra_id_wrong_type_and_non_json(self):
        for raw in ('{"definition":""}', '{"definition":"ok","source_id":"other"}',
                    '{"definition":3}', 'not json'):
            with self.subTest(raw=raw):
                with self.assertRaises(SynthesisFailure):
                    validate_definition(raw)

    def test_truncated_response_is_rejected(self):
        row = attempt(source(), 1, Provider('{"definition":"A cupola."}', "length"))
        self.assertEqual(row["status"], "rejected")
        self.assertEqual(row["error_code"], "output_truncated")

    def test_export_reports_variation_not_semantic_repeatability(self):
        records = [attempt(source(), repeat, Provider('{"definition":"A cupola."}'))
                   for repeat in range(1, 4)]
        with tempfile.TemporaryDirectory() as temporary:
            prefix = Path(temporary) / "report"
            (Path(temporary) / "manifest.json").write_text(json.dumps({
                "model": {"digest": "fixture"}, "inference_options": {},
                "schema": SCHEMA, "code_sha256": "fixture-code",
            }))
            export(records, prefix, Path(temporary))
            summary = json.loads(Path(str(prefix) + "_attempts.json").read_text())
            self.assertEqual(summary["validated"], 3)
            self.assertEqual(summary["human_reviewed"], 0)
            self.assertEqual(summary["wording_variants_by_source"]["fixed-id"], 1)
            self.assertEqual(summary["comparison"], "NON-EQUIVALENT")


if __name__ == "__main__":
    unittest.main()
