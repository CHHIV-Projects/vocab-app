import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from vocab_lexical_engine import build_sqlite, lookup, normalize_record
from vocab_workflow import (
    LexicalState,
    LexicalWorkflow,
    build_lexical_candidate,
    deduplicated_forms,
    meaning_source_rows,
    reconcile_saved_state,
    source_detail_rows,
    sort_pos_sections,
)


def records(dataset_version="wiktionary-20260901"):
    noun = normalize_record({
        "word": "fixture",
        "lang": "English",
        "lang_code": "en",
        "pos": "noun",
        "etymology_number": 1,
        "etymology_text": "From the source noun etymology.",
        "etymology_templates": [{"name": "inh", "expansion": "Inherited"}],
        "sounds": [
            {"ipa": "/ˈfɪkstʃɚ/", "tags": ["US"]},
            {"ipa": "/ˈfɪkstʃə/", "tags": ["Received-Pronunciation"]},
        ],
        "senses": [
            {
                "glosses": ["first gloss", "second component"],
                "tags": ["informal"],
                "synonyms": [{"word": "example-term"}],
                "examples": [{"text": "A source example."}],
            },
            {"glosses": ["second sense"]},
        ],
    }, dataset_version, "fixture.jsonl#line=1")
    verb = normalize_record({
        "word": "fixture",
        "lang": "English",
        "lang_code": "en",
        "pos": "verb",
        "etymology_number": 2,
        "etymology_text": "A separate verb etymology.",
        "senses": [{"glosses": ["verb sense"]}],
    }, dataset_version, "fixture.jsonl#line=2")
    adjective = normalize_record({
        "word": "fixture",
        "lang": "English",
        "lang_code": "en",
        "pos": "adjective",
        "senses": [{"glosses": ["adjective sense"]}],
    }, dataset_version, "fixture.jsonl#line=3")
    more_nouns = normalize_record({
        "word": "fixture",
        "lang": "English",
        "lang_code": "en",
        "pos": "noun",
        "etymology_number": 3,
        "senses": [{"glosses": [f"extra sense {index}"]} for index in range(1, 5)],
    }, dataset_version, "fixture.jsonl#line=4")
    return [noun, verb, adjective, more_nouns]


class FakePersistence:
    def __init__(self, saved=None):
        self.saved = saved

    def load_active_version(self, word):
        return self.saved

    def save_accepted_version(self, candidate, origin):
        return {
            "lexical_entry_version_id": 2,
            "active_version_id": 2,
            "candidate_snapshot": deepcopy(candidate),
            "origin": origin,
        }


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.database = self.root / "lexical.sqlite"
        build_sqlite(records(), self.database)

    def test_source_senses_become_distinct_source_derived_meanings(self):
        candidate = build_lexical_candidate(
            __import__("vocab_lexical_engine").lookup(
                self.database, "fixture", include_wordnet=False
            )
        )
        meanings = [
            meaning
            for section in candidate["content"]["pos_sections"]
            for meaning in section["core_meanings"] + section["additional_meanings"]
        ]
        self.assertEqual(len(meanings), 8)
        self.assertEqual(len({
            meaning["source_sense_ids"][0] for meaning in meanings
        }), 8)
        self.assertEqual(
            meanings[0]["definition"],
            "first gloss; second component",
        )
        self.assertEqual(len(meanings[0]["source_sense_ids"]), 1)
        self.assertEqual(
            set(candidate["content"]["coverage"]["source_sense_ids"]),
            {meaning["source_sense_ids"][0] for meaning in meanings},
        )

    def test_core_policy_caps_total_at_five_and_represents_each_pos_first(self):
        result = __import__("vocab_lexical_engine").lookup(
            self.database, "fixture", include_wordnet=False
        )
        candidate = build_lexical_candidate(result)
        sections = candidate["content"]["pos_sections"]
        core = [(section["pos"], meaning) for section in sections for meaning in section["core_meanings"]]
        self.assertEqual(len(core), 5)
        self.assertEqual({pos for pos, _ in core}, {"noun", "verb", "adjective"})
        self.assertEqual(len([
            meaning for section in sections for meaning in section["additional_meanings"]
        ]), 3)
        all_ids = [
            meaning["source_sense_ids"][0]
            for section in sections
            for meaning in section["core_meanings"] + section["additional_meanings"]
        ]
        self.assertEqual(len(all_ids), len(set(all_ids)))

    def test_synonyms_are_bound_to_the_exact_source_sense_with_inspectable_evidence(self):
        candidate = build_lexical_candidate(
            __import__("vocab_lexical_engine").lookup(
                self.database, "fixture", include_wordnet=False
            )
        )
        meaning = candidate["content"]["pos_sections"][0]["core_meanings"][0]
        self.assertEqual([item["term"] for item in meaning["synonyms"]], ["example-term"])
        source = meaning_source_rows(candidate, meaning, "noun")
        self.assertEqual(len(source), 1)
        relation = source[0]["relations"][0]
        self.assertEqual(relation["target"], "example-term")
        self.assertEqual(relation["source_locator"], "fixture.jsonl#line=1")
        self.assertEqual(meaning["synonyms"][0]["evidence_ids"], [relation["evidence_id"]])

    def test_etymology_and_us_pronunciation_are_source_derived(self):
        candidate = build_lexical_candidate(
            __import__("vocab_lexical_engine").lookup(
                self.database, "fixture", include_wordnet=False
            )
        )
        etymologies = candidate["etymology"]
        self.assertEqual([item["etymology_number"] for item in etymologies], [1, 2])
        self.assertEqual(etymologies[0]["text"], "From the source noun etymology.")
        self.assertEqual(
            candidate["deterministic"]["us_pronunciations"],
            [{
                "entry_key": etymologies[0]["entry_key"],
                "ipa": "/ˈfɪkstʃɚ/",
                "tags": ["US"],
            }],
        )

    def test_lookup_does_not_call_wordnet_or_any_provider(self):
        workflow = LexicalWorkflow(str(self.database), FakePersistence())
        with patch("vocab_lexical_engine.wordnet_evidence",
                   side_effect=AssertionError("WordNet must not run on lookup")) as wordnet:
            state = workflow.search("fixture")
        wordnet.assert_not_called()
        self.assertEqual(state.origin, "search")
        self.assertEqual(state.candidate["wiktionary_versions"], ["wiktionary-20260901"])

    def test_saved_snapshot_is_returned_without_relinking_and_refresh_is_explicit(self):
        old_candidate = build_lexical_candidate(
            __import__("vocab_lexical_engine").lookup(
                self.database, "fixture", include_wordnet=False
            )
        )
        saved = {
            "normalized_lemma": "fixture",
            "lexical_entry_id": 1,
            "lexical_entry_version_id": 1,
            "active_version_id": 1,
            "candidate_identity": "accepted-v1",
            "evidence_set_hash": old_candidate["evidence_set_hash"],
            "candidate_snapshot": deepcopy(old_candidate),
            "evidence_snapshot": deepcopy(old_candidate["evidence_snapshot"]),
            "version_number": 1,
        }
        workflow = LexicalWorkflow(str(self.database), FakePersistence(saved))
        state = workflow.reconcile_authoritative_state("fixture")
        self.assertEqual(state.origin, "saved")
        self.assertEqual(state.candidate, old_candidate)
        self.assertFalse(state.refresh_available)
        self.assertFalse(state.actions["save"])
        self.assertNotIn("retry", state.actions)

    def test_newer_dataset_refresh_creates_pending_candidate_without_mutating_saved(self):
        old_candidate = build_lexical_candidate(
            __import__("vocab_lexical_engine").lookup(
                self.database, "fixture", include_wordnet=False
            )
        )
        saved = {
            "normalized_lemma": "fixture",
            "lexical_entry_id": 1,
            "lexical_entry_version_id": 1,
            "active_version_id": 1,
            "candidate_identity": "accepted-v1",
            "evidence_set_hash": old_candidate["evidence_set_hash"],
            "candidate_snapshot": deepcopy(old_candidate),
            "evidence_snapshot": deepcopy(old_candidate["evidence_snapshot"]),
            "version_number": 1,
        }
        newer_dir = self.root / "versions" / "wiktionary-20261001"
        newer_dir.mkdir(parents=True)
        newer_db = newer_dir / "lexical.sqlite"
        build_sqlite(records("wiktionary-20261001"), newer_db)
        (self.root / "active").write_text("wiktionary-20261001\n", encoding="utf-8")
        (newer_dir / "manifest.json").write_text(json.dumps({
            "dataset_version": "wiktionary-20261001",
            "dump_date": "2026-10-01",
        }), encoding="utf-8")
        workflow = LexicalWorkflow(str(self.root), FakePersistence(saved))
        accepted = workflow.reconcile_authoritative_state("fixture")
        self.assertTrue(accepted.refresh_available)
        self.assertEqual(accepted.candidate, old_candidate)
        pending = workflow.refresh(accepted)
        self.assertEqual(pending.origin, "refresh")
        self.assertTrue(pending.actions["save"])
        self.assertFalse(pending.actions["refresh"])
        self.assertEqual(saved["candidate_snapshot"], old_candidate)
        reconciled = reconcile_saved_state(pending, "fixture", FakePersistence(saved))
        self.assertEqual(reconciled.origin, "refresh")
        self.assertEqual(reconciled.candidate["wiktionary_versions"], ["wiktionary-20261001"])
        self.assertEqual(saved["evidence_snapshot"]["wiktionary_versions"], ["wiktionary-20260901"])

    def test_dataset_refresh_requires_a_strictly_newer_date_version(self):
        from vocab_workflow import _newer_dataset_is_installed

        saved = {"wiktionary_versions": ["wiktionary-20260901"]}
        self.assertTrue(_newer_dataset_is_installed(saved, {"wiktionary_versions": ["wiktionary-20261001"]}))
        self.assertFalse(_newer_dataset_is_installed(saved, {"wiktionary_versions": ["wiktionary-20260901"]}))
        self.assertFalse(_newer_dataset_is_installed(saved, {"wiktionary_versions": ["wiktionary-20250801"]}))

    def test_source_detail_rows_and_form_deduplication_remain_stable(self):
        candidate = build_lexical_candidate(
            __import__("vocab_lexical_engine").lookup(
                self.database, "fixture", include_wordnet=False
            )
        )
        rows = source_detail_rows(candidate)
        self.assertEqual(rows[0]["examples"][0], "A source example.")
        self.assertEqual(
            deduplicated_forms({
                "deterministic": {
                    "forms": [
                        {"form": {"form": "Form"}},
                        {"form": {"form": "form"}},
                    ]
                }
            }),
            ["Form"],
        )
        self.assertEqual(
            [section["pos"] for section in sort_pos_sections([
                {"pos": "name"}, {"pos": "verb"}, {"pos": "noun"},
            ])],
            ["noun", "verb", "name"],
        )


if __name__ == "__main__":
    unittest.main()
