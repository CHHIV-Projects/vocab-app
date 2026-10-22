import unittest
from copy import deepcopy

from vocab_workflow import (
    LexicalState,
    candidate_provenance,
    meaning_source_rows,
    reconcile_saved_state,
    source_detail_rows,
)


class FakePersistence:
    def __init__(self, saved):
        self.saved = saved

    def load_active_version(self, normalized_lemma):
        return self.saved


class LegacySavedSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.legacy_candidate = {
            "schema_version": "synthesis-v6-legacy",
            "normalized_lemma": "fixture",
            "evidence_set_hash": "legacy-evidence-hash",
            "model": "historical-model-identity",
            "content": {
                "pos_sections": [{
                    "pos": "noun",
                    "core_meanings": [{
                        "definition": "Historically accepted wording",
                        "source_sense_ids": ["S1"],
                        "labels": ["informal"],
                        "synonyms": [],
                        "example_ids": [],
                    }],
                    "additional_meanings": [],
                }],
            },
            "etymology": {
                "summary": "Historical accepted etymology wording",
                "evidence_ids": ["E1"],
            },
            "evidence_snapshot": {
                "wiktionary_versions": ["wiktionary-20260901"],
                "entries": [{
                    "part_of_speech": "noun",
                    "dataset_version": "wiktionary-20260901",
                    "source_locator": "legacy.jsonl#line=1",
                    "senses": [{
                        "sense_id": "S1",
                        "glosses": ["the exact source gloss"],
                        "tags": ["informal"],
                        "topics": [],
                        "examples": [],
                        "relations": [],
                    }],
                }],
            },
        }
        self.saved = {
            "normalized_lemma": "fixture",
            "lexical_entry_id": 1,
            "lexical_entry_version_id": 4,
            "active_version_id": 4,
            "candidate_identity": "legacy-candidate-identity",
            "evidence_set_hash": "legacy-evidence-hash",
            "candidate_snapshot": deepcopy(self.legacy_candidate),
            "evidence_snapshot": deepcopy(self.legacy_candidate["evidence_snapshot"]),
            "version_number": 3,
            "origin": "search",
        }

    def test_saved_legacy_snapshot_loads_without_reinterpretation(self):
        state = reconcile_saved_state(
            None, "Fixture", FakePersistence(self.saved)
        )
        self.assertEqual(state.origin, "saved")
        self.assertEqual(state.candidate, self.legacy_candidate)
        self.assertEqual(
            state.candidate["content"]["pos_sections"][0]["core_meanings"][0]["definition"],
            "Historically accepted wording",
        )
        self.assertEqual(
            state.candidate["etymology"]["summary"],
            "Historical accepted etymology wording",
        )
        self.assertEqual(self.saved["candidate_snapshot"], self.legacy_candidate)

    def test_provenance_is_learner_safe_and_does_not_surface_model_identity(self):
        details = candidate_provenance(LexicalState(
            "fixture",
            candidate=self.legacy_candidate,
            saved_version=self.saved,
            origin="saved",
        ))
        self.assertEqual(details["Viewing"], "Saved accepted version")
        self.assertEqual(details["Accepted version number"], 3)
        self.assertEqual(details["Source datasets"], "wiktionary-20260901")
        self.assertNotIn("model", " ".join(details).lower())
        self.assertNotIn("historical-model-identity", repr(details))

    def test_source_provenance_resolves_only_the_sense_linked_to_meaning(self):
        meaning = self.legacy_candidate["content"]["pos_sections"][0]["core_meanings"][0]
        rows = meaning_source_rows(self.legacy_candidate, meaning, "noun")
        self.assertEqual([row["sense_id"] for row in rows], ["S1"])
        self.assertEqual(rows[0]["glosses"], ["the exact source gloss"])
        self.assertEqual(rows[0]["source_locator"], "legacy.jsonl#line=1")
        self.assertEqual(source_detail_rows(self.legacy_candidate), rows)

    def test_invalid_or_cross_pos_source_links_raise(self):
        for meaning, pos in (
            ({"source_sense_ids": ["missing"]}, "noun"),
            ({"source_sense_ids": ["S1"]}, "verb"),
        ):
            with self.subTest(meaning=meaning, pos=pos):
                with self.assertRaisesRegex(ValueError, "Meaning provenance cannot resolve"):
                    meaning_source_rows(self.legacy_candidate, meaning, pos)


if __name__ == "__main__":
    unittest.main()
