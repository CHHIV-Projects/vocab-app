import unittest
from unittest.mock import patch

from vocab_consolidation import build_partitions, enumerate_pairs
from vocab_consolidation_provider import (
    QWEN_EXPECTED_DIGEST,
    QWEN_MODEL,
    QWEN_SEMANTIC_OPTIONS,
    PairProviderResult,
    QwenPairProvider,
    build_pair_prompt,
    build_pair_request,
    confirm_installed_model_identity,
    installed_model_digest,
    pair_decision_schema,
)


def fixture_evidence(count=2):
    return {
        "normalized_lemma": "fixture",
        "wiktionary_versions": ["fixture-v1"],
        "wordnet_version": "wordnet-v1",
        "entries": [{
            "entry_key": "entry-1",
            "part_of_speech": "noun",
            "senses": [
                {"sense_id": f"sense-{index}", "source_order": index, "glosses": [f"gloss {index}"],
                 "labels": [], "topics": [], "examples": [], "relations": []}
                for index in range(1, count + 1)
            ],
        }],
        "wordnet": [],
    }


def _partition(count=2):
    return build_partitions(fixture_evidence(count))[0]


class FakeResponse:
    def __init__(self, status_code=200, json_body=None, text=""):
        self.status_code = status_code
        self._json_body = json_body if json_body is not None else {}
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f"status {self.status_code}")

    def json(self):
        return self._json_body


def _chat_response(decision="merge", reason="paraphrase_or_duplicate", done_reason="stop"):
    return FakeResponse(200, {
        "message": {"content": f'{{"decision": "{decision}", "reason": "{reason}"}}'},
        "done_reason": done_reason,
        "eval_count": 12,
    })


class PairDecisionSchemaTests(unittest.TestCase):
    def test_schema_matches_accepted_m004_6_4_decision_reason_contract(self):
        schema = pair_decision_schema()
        self.assertEqual(schema["properties"]["decision"]["enum"], ["merge", "keep_separate", "uncertain"])
        self.assertEqual(
            schema["properties"]["reason"]["enum"],
            [
                "paraphrase_or_duplicate", "contextual_variant", "specialized_subsense",
                "broader_or_narrower", "related_but_distinct", "materially_different", "insufficient_evidence",
            ],
        )
        self.assertEqual(schema["required"], ["decision", "reason"])
        self.assertFalse(schema["additionalProperties"])


class PairPromptTests(unittest.TestCase):
    def test_prompt_is_deterministic_and_uses_only_domain_evidence_fields(self):
        partition = _partition(2)
        pair = enumerate_pairs(partition)[0]
        first = build_pair_prompt(partition, pair)
        second = build_pair_prompt(partition, pair)
        self.assertEqual(first, second)
        self.assertIn("sense-1", first)
        self.assertIn("sense-2", first)
        self.assertIn("Prefer false splits.", first)

    def test_build_pair_request_uses_provided_model_and_options(self):
        partition = _partition(2)
        pair = enumerate_pairs(partition)[0]
        request = build_pair_request(partition, pair, model="qwen3:8b", semantic_options={"think": False, "seed": 5100})
        self.assertEqual(request.model, "qwen3:8b")
        self.assertEqual(request.semantic_options, {"think": False, "seed": 5100})
        self.assertEqual(request.schema, pair_decision_schema())


class QwenPairProviderTests(unittest.TestCase):
    def setUp(self):
        self.partition = _partition(2)
        self.pair = enumerate_pairs(self.partition)[0]
        self.request = build_pair_request(self.partition, self.pair, semantic_options=QWEN_SEMANTIC_OPTIONS)
        self.provider = QwenPairProvider(endpoint="http://fake-ollama:11434")

    def test_successful_merge_judgment(self):
        with patch("vocab_consolidation_provider.requests.post", return_value=_chat_response("merge", "paraphrase_or_duplicate")):
            result = self.provider.judge_pair(self.request)
        self.assertEqual(result.status, "provider_success")
        self.assertEqual((result.decision, result.reason), ("merge", "paraphrase_or_duplicate"))

    def test_successful_keep_separate_judgment(self):
        with patch("vocab_consolidation_provider.requests.post", return_value=_chat_response("keep_separate", "materially_different")):
            result = self.provider.judge_pair(self.request)
        self.assertEqual(result.status, "provider_success")
        self.assertEqual((result.decision, result.reason), ("keep_separate", "materially_different"))

    def test_successful_uncertain_judgment_is_not_a_failure(self):
        with patch("vocab_consolidation_provider.requests.post", return_value=_chat_response("uncertain", "insufficient_evidence")):
            result = self.provider.judge_pair(self.request)
        self.assertEqual(result.status, "provider_success")
        self.assertEqual((result.decision, result.reason), ("uncertain", "insufficient_evidence"))

    def test_malformed_json_is_retryable(self):
        response = FakeResponse(200, {"message": {"content": "not json"}, "done_reason": "stop"})
        with patch("vocab_consolidation_provider.requests.post", return_value=response):
            result = self.provider.judge_pair(self.request)
        self.assertEqual(result.status, "retryable_failure")
        self.assertEqual(result.error_classification, "malformed_json")

    def test_schema_invalid_decision_is_retryable(self):
        response = FakeResponse(200, {"message": {"content": '{"decision": "not_a_decision", "reason": "materially_different"}'}, "done_reason": "stop"})
        with patch("vocab_consolidation_provider.requests.post", return_value=response):
            result = self.provider.judge_pair(self.request)
        self.assertEqual(result.status, "retryable_failure")
        self.assertEqual(result.error_classification, "schema_invalid")

    def test_incompatible_decision_reason_is_retryable(self):
        response = FakeResponse(200, {"message": {"content": '{"decision": "merge", "reason": "materially_different"}'}, "done_reason": "stop"})
        with patch("vocab_consolidation_provider.requests.post", return_value=response):
            result = self.provider.judge_pair(self.request)
        self.assertEqual(result.status, "retryable_failure")
        self.assertEqual(result.error_classification, "schema_invalid")

    def test_truncated_output_is_retryable(self):
        response = FakeResponse(200, {"message": {"content": '{"decision": "merge"'}, "done_reason": "length"})
        with patch("vocab_consolidation_provider.requests.post", return_value=response):
            result = self.provider.judge_pair(self.request)
        self.assertEqual(result.status, "retryable_failure")
        self.assertEqual(result.error_classification, "truncated_length")

    def test_empty_content_is_retryable(self):
        response = FakeResponse(200, {"message": {"content": ""}, "done_reason": "stop"})
        with patch("vocab_consolidation_provider.requests.post", return_value=response):
            result = self.provider.judge_pair(self.request)
        self.assertEqual(result.status, "retryable_failure")
        self.assertEqual(result.error_classification, "empty_response")

    def test_timeout_is_retryable(self):
        import requests
        with patch("vocab_consolidation_provider.requests.post", side_effect=requests.Timeout("boom")):
            result = self.provider.judge_pair(self.request)
        self.assertEqual(result.status, "retryable_failure")
        self.assertEqual(result.error_classification, "timeout")

    def test_transport_error_is_retryable(self):
        import requests
        with patch("vocab_consolidation_provider.requests.post", side_effect=requests.ConnectionError("boom")):
            result = self.provider.judge_pair(self.request)
        self.assertEqual(result.status, "retryable_failure")
        self.assertEqual(result.error_classification, "transport_failure")

    def test_server_error_is_retryable(self):
        with patch("vocab_consolidation_provider.requests.post", return_value=FakeResponse(503, text="unavailable")):
            result = self.provider.judge_pair(self.request)
        self.assertEqual(result.status, "retryable_failure")
        self.assertEqual(result.error_classification, "provider_server_error")

    def test_model_not_found_is_terminal(self):
        with patch("vocab_consolidation_provider.requests.post", return_value=FakeResponse(404, text="not found")):
            result = self.provider.judge_pair(self.request)
        self.assertEqual(result.status, "terminal_failure")
        self.assertEqual(result.error_classification, "model_unavailable")

    def test_bad_request_is_terminal(self):
        with patch("vocab_consolidation_provider.requests.post", return_value=FakeResponse(400, text="bad request")):
            result = self.provider.judge_pair(self.request)
        self.assertEqual(result.status, "terminal_failure")
        self.assertEqual(result.error_classification, "provider_request_error")


class InstalledModelIdentityTests(unittest.TestCase):
    def test_confirm_installed_model_identity_matches(self):
        response = FakeResponse(200, {"models": [{"model": QWEN_MODEL, "digest": QWEN_EXPECTED_DIGEST}]})
        with patch("vocab_consolidation_provider.requests.get", return_value=response):
            digest = confirm_installed_model_identity("http://fake-ollama:11434", QWEN_MODEL, QWEN_EXPECTED_DIGEST)
        self.assertEqual(digest, QWEN_EXPECTED_DIGEST)

    def test_confirm_installed_model_identity_raises_on_digest_mismatch(self):
        response = FakeResponse(200, {"models": [{"model": QWEN_MODEL, "digest": "different-digest"}]})
        with patch("vocab_consolidation_provider.requests.get", return_value=response):
            with self.assertRaises(RuntimeError):
                confirm_installed_model_identity("http://fake-ollama:11434", QWEN_MODEL, QWEN_EXPECTED_DIGEST)

    def test_installed_model_digest_raises_when_model_missing(self):
        response = FakeResponse(200, {"models": []})
        with patch("vocab_consolidation_provider.requests.get", return_value=response):
            with self.assertRaises(RuntimeError):
                installed_model_digest("http://fake-ollama:11434", QWEN_MODEL)


if __name__ == "__main__":
    unittest.main()
