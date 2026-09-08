import json
import tempfile
import unittest
from pathlib import Path

from vocab_lexical_engine import build_sqlite, normalize_jsonl, lookup
from vocab_synthesis import (
    SynthesisFailure,
    SynthesisRuntime,
    build_envelope,
    lexical_content_schema,
    pack_evidence,
    scaffold_schema,
    sense_aliases,
    deterministic_group_assignments,
    MATERIAL_LABELS,
    grouping_schema,
    validate_grouping,
    validate_scaffold,
    response_content,
    strict_json_object,
    synthesize_word,
    validate_content,
)


class FakeProvider:
    model = "fake-model"

    def __init__(self, response):
        self.response = response
        self.calls = 0

    def generate(self, prompt, *, seed=None, schema=None):
        self.calls += 1
        response = self.response
        if response == "valid":
            if "sense_results" in schema["properties"]:
                response = json.dumps({"sense_results": {alias: {"definition": "supported"} for alias in schema["properties"]["sense_results"]["properties"]}})
            else:
                if "group_assignments" in schema["properties"]:
                    aliases = list(schema["properties"]["group_assignments"]["properties"])
                    groups = [f"G{index:03d}" for index in range(1, len(aliases) + 1)]
                    response = json.dumps({"group_assignments": {alias: group for alias, group in zip(aliases, groups)}, "group_definitions": {group: "supported" for group in groups}})
                else:
                    groups = list(schema["properties"]["core_group_ids"]["items"]["enum"])
                    response = json.dumps({"core_group_ids": groups[:1]})
        return {"message": {"role": "assistant", "content": response, "thinking": "ignored reasoning"}, "model_digest": "fake-digest", "done": True, "done_reason": "stop"}


def evidence():
    return {
        "normalized_lemma": "fixture",
        "wiktionary_versions": ["fixture-v1"],
        "wordnet_version": "wordnet-v1",
        "entries": [{
            "entry_key": "entry-1",
            "part_of_speech": "noun",
            "senses": [
                {"sense_id": "sense-1", "source_order": 1, "glosses": ["one"], "tags": [], "topics": [], "examples": [], "relations": []},
                {"sense_id": "sense-2", "source_order": 2, "glosses": ["two"], "tags": ["informal"], "topics": [], "examples": [], "relations": []},
            ],
        }],
        "wordnet": [],
    }


def valid_content():
    return {
        "pos_sections": [{
            "pos": "noun",
            "core_meanings": [{"definition": "one", "source_sense_ids": ["sense-1"], "labels": [], "synonyms": [], "example_ids": []}],
            "additional_meanings": [{"definition": "two", "source_sense_ids": ["sense-2"], "labels": ["informal"], "synonyms": [], "example_ids": []}],
        }],
        "coverage": {"source_sense_ids": ["sense-1", "sense-2"]},
    }


class SynthesisTests(unittest.TestCase):
    def test_strict_parser_rejects_surrounding_prose_and_fences(self):
        self.assertEqual(strict_json_object('{"ok": true}'), {"ok": True})
        for raw in ('prefix {"ok": true}', '```json\n{"ok": true}\n```', '{bad}'):
            with self.assertRaises(SynthesisFailure):
                strict_json_object(raw)

    def test_chat_parser_uses_final_content_not_thinking(self):
        response = {"message": {"content": '{"ok": true}', "thinking": '{"ok": false}'}}
        self.assertEqual(response_content(response), '{"ok": true}')

    def test_lexical_schema_is_expanded_and_closed(self):
        schema = lexical_content_schema()
        self.assertEqual(schema["type"], "object")
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["properties"]["pos_sections"]["items"]["required"], ["pos", "core_meanings", "additional_meanings"])
        self.assertEqual(schema["properties"]["coverage"]["required"], ["source_sense_ids"])

    def test_scaffold_requires_all_deterministic_aliases(self):
        package = {"senses": [{"sense_id": "sense-1", "part_of_speech": "noun"}, {"sense_id": "sense-2", "part_of_speech": "noun"}]}
        self.assertEqual(sense_aliases(package), {"S001": "sense-1", "S002": "sense-2"})
        schema = scaffold_schema(package)
        self.assertEqual(schema["properties"]["sense_results"]["required"], ["S001", "S002"])
        self.assertEqual(validate_scaffold({"sense_results": {"S001": {"definition": "one"}}}, package), ["scaffold_alias_coverage"])

    def test_scaffold_rejects_unknown_alias_and_empty_definition(self):
        package = {"senses": [{"sense_id": "sense-1", "part_of_speech": "noun"}]}
        self.assertTrue(validate_scaffold({"sense_results": {"S001": {"definition": ""}}}, package))
        self.assertEqual(validate_scaffold({"sense_results": {"S001": {"definition": "one"}, "S999": {"definition": "x"}}}, package), ["scaffold_alias_coverage"])

    def test_grouping_baseline_is_exhaustive_and_deterministic(self):
        package = {"senses": [{"sense_id": "sense-1"}, {"sense_id": "sense-2"}]}
        self.assertEqual(deterministic_group_assignments(package), {"S001": "G001", "S002": "G002"})

    def test_grouping_validation_rejects_omitted_duplicate_unknown_and_cross_pos(self):
        aliases = {"S001": "sense-1", "S002": "sense-2"}
        senses = [{"definition": "one", "labels": [], "source_sense_ids": ["sense-1"]}, {"definition": "two", "labels": [], "source_sense_ids": ["sense-2"]}]
        valid = {"group_assignments": {"S001": "G001", "S002": "G001"}, "group_definitions": {"G001": "one or two", "G002": ""}}
        self.assertEqual(validate_grouping(valid, aliases, senses), [])
        omitted = dict(valid)
        omitted["group_assignments"] = {"S001": "G001"}
        self.assertIn("group_alias_coverage", validate_grouping(omitted, aliases, senses))
        unknown = dict(valid)
        unknown["group_assignments"] = {"S001": "G999", "S002": "G001"}
        self.assertIn("unknown_group_id", validate_grouping(unknown, aliases, senses))

    def test_material_label_partitions_block_literal_figurative_and_formal_informal_merges(self):
        aliases = {"S001": "sense-1", "S002": "sense-2"}
        for first, second in (("", "figurative"), ("formal", "informal")):
            senses = [{"definition": "one", "labels": [first] if first else [], "source_sense_ids": ["sense-1"]}, {"definition": "two", "labels": [second], "source_sense_ids": ["sense-2"]}]
            value = {"group_assignments": {"S001": "G001", "S002": "G001"}, "group_definitions": {"G001": "combined", "G002": ""}}
            self.assertTrue(any(error.startswith("material_label_boundary:") for error in validate_grouping(value, aliases, senses)))

    def test_identical_material_signatures_remain_groupable_and_coverage_is_complete(self):
        aliases = {"S001": "sense-1", "S002": "sense-2"}
        senses = [{"definition": "one", "labels": ["figurative"], "source_sense_ids": ["sense-1"]}, {"definition": "two", "labels": ["figurative"], "source_sense_ids": ["sense-2"]}]
        value = {"group_assignments": {"S001": "G001", "S002": "G001"}, "group_definitions": {"G001": "combined", "G002": ""}}
        self.assertEqual(validate_grouping(value, aliases, senses), [])
        self.assertEqual(set(aliases.values()), {source_id for alias in value["group_assignments"] for source_id in [aliases[alias]]})
        self.assertTrue(MATERIAL_LABELS.issuperset({"figurative", "formal", "humorous", "informal", "literary"}))

    def test_packer_preserves_all_senses_and_source_order(self):
        packages = pack_evidence(evidence(), target_tokens=1)
        self.assertEqual([sense["sense_id"] for package in packages for sense in package["senses"]], ["sense-1", "sense-2"])

    def test_validator_accepts_complete_content(self):
        self.assertEqual(validate_content(valid_content(), evidence()), [])

    def test_validator_rejects_unknown_and_incomplete_content(self):
        content = valid_content()
        content["pos_sections"][0]["core_meanings"][0]["source_sense_ids"] = ["unknown"]
        self.assertIn("unknown_sense_id", validate_content(content, evidence()))
        self.assertIn("incomplete_or_duplicate_coverage", validate_content(content, evidence()))

    def test_validator_rejects_cross_pos_and_unsupported_label(self):
        content = valid_content()
        content["pos_sections"][0]["additional_meanings"][0]["labels"] = ["obsolete"]
        self.assertIn("unsupported_label", validate_content(content, evidence()))

    def test_cache_round_trip_and_failure_diagnostic(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = SynthesisRuntime(directory)
            identity = {"lemma": "fixture", "evidence_set_hash": "hash", "schema": "v1"}
            value = build_envelope(valid_content(), evidence(), model="fake", digest="digest", seed=1, attempt_id="attempt")
            runtime.write_cache(identity, value)
            self.assertEqual(runtime.read_cache(identity), value)
            path = runtime.record_failure({"code": "parse_invalid_json", "attempt_id": "attempt"})
            self.assertTrue(path.is_file())
            self.assertEqual(json.loads(path.read_text())["code"], "parse_invalid_json")

    def test_fake_provider_validates_then_hits_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = Path(__file__).parent / "fixtures" / "archipelago.jsonl"
            normalized = root / "evidence.jsonl"
            records = normalize_jsonl(fixture, normalized, "fixture-v1")
            database = root / "lexical.sqlite"
            build_sqlite(records[:1], database)
            lookup_result = lookup(database, "archipelago")
            projected_ids = [sense["sense_id"] for entry in lookup_result["entries"] for sense in entry["senses"]]
            content = {"pos_sections": [{"pos": lookup_result["entries"][0]["part_of_speech"], "core_meanings": [{"definition": "supported", "source_sense_ids": [projected_ids[0]], "labels": [], "synonyms": [], "example_ids": []}], "additional_meanings": [{"definition": "supported", "source_sense_ids": projected_ids[1:], "labels": [], "synonyms": [], "example_ids": []}]}], "coverage": {"source_sense_ids": projected_ids}}
            provider = FakeProvider("valid")
            runtime = SynthesisRuntime(root / "runtime")
            first = synthesize_word(database, "archipelago", provider, runtime)
            second = synthesize_word(database, "archipelago", provider, runtime)
            self.assertEqual(first["status"], "validated")
            self.assertEqual(second["status"], "cached")
            self.assertEqual(provider.calls, 4)

    def test_invalid_provider_result_is_not_cached(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = Path(__file__).parent / "fixtures" / "archipelago.jsonl"
            records = normalize_jsonl(fixture, root / "evidence.jsonl", "fixture-v1")
            database = root / "lexical.sqlite"
            build_sqlite(records, database)
            runtime = SynthesisRuntime(root / "runtime")
            with self.assertRaises(SynthesisFailure):
                synthesize_word(database, "archipelago", FakeProvider("not-json"), runtime)
            self.assertFalse(list((root / "runtime" / "synthesis-cache").glob("*.json")))

    def test_length_done_reason_is_hard_failure_and_not_cached(self):
        class TruncatedProvider(FakeProvider):
            def generate(self, prompt, *, seed=None, schema=None):
                return {"message": {"content": '{"partial":', "thinking": "reasoning"}, "done": True, "done_reason": "length", "eval_count": 2400}

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            records = normalize_jsonl(Path(__file__).parent / "fixtures" / "archipelago.jsonl", root / "evidence.jsonl", "fixture-v1")
            database = root / "lexical.sqlite"
            build_sqlite(records, database)
            with self.assertRaises(SynthesisFailure) as caught:
                synthesize_word(database, "archipelago", TruncatedProvider("unused"), SynthesisRuntime(root / "runtime"))
            self.assertEqual(caught.exception.code, "output_truncated")
            self.assertFalse(list((root / "runtime" / "synthesis-cache").glob("*.json")))


if __name__ == "__main__":
    unittest.main()