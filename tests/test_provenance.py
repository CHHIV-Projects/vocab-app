import hashlib
import json
import unittest
from copy import deepcopy
from importlib.util import find_spec
from unittest.mock import patch

from tests.test_synthesis import evidence, valid_content
from tests.test_vocab_workflow import FakePersistence, FakeProvider
from vocab_lexical_engine import evidence_set_hash
from vocab_synthesis import build_envelope, validate_content
from vocab_workflow import (
    LexicalState, LexicalWorkflow, candidate_provenance, meaning_source_rows,
)


def candidate_fixture():
    snapshot = evidence()
    snapshot["schema_version"] = "synthesis-evidence-v1"
    snapshot["entries"][0].update({
        "dataset_version": "fixture-v1", "importer_version": "fixture-importer",
        "source_locator": "fixture.jsonl#line=1", "source_record_hash": "source-hash",
    })
    return build_envelope(valid_content(), snapshot, model="fake-model",
                          digest=None, seed=None, attempt_id="fixture")


class MeaningProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.candidate = candidate_fixture()
        self.section = self.candidate["content"]["pos_sections"][0]

    def test_each_meaning_resolves_only_its_references(self):
        core = meaning_source_rows(self.candidate, self.section["core_meanings"][0], "noun")
        additional = meaning_source_rows(self.candidate, self.section["additional_meanings"][0], "noun")
        self.assertEqual([row["sense_id"] for row in core], ["sense-1"])
        self.assertEqual(core[0]["glosses"], ["one"])
        self.assertEqual([row["sense_id"] for row in additional], ["sense-2"])
        self.assertEqual(additional[0]["labels"], ["informal"])
        self.assertEqual(core[0]["source_locator"], "fixture.jsonl#line=1")
        self.assertEqual(core[0]["importer_version"], "fixture-importer")

    def test_one_to_many_count_uses_unique_ids_not_prose_or_gloss_count(self):
        meaning = {"definition": "unrelated prose", "source_sense_ids": ["sense-2", "sense-1", "sense-2"]}
        self.candidate["evidence_snapshot"]["entries"][0]["senses"][0]["glosses"] = ["one", "another gloss"]
        original = deepcopy(self.candidate)
        rows = meaning_source_rows(self.candidate, meaning, "noun")
        self.assertEqual(len(rows), 2)
        self.assertEqual([row["sense_id"] for row in rows], ["sense-2", "sense-1"])
        self.assertEqual(self.candidate, original)

    def test_missing_optional_fields_are_absent_and_bad_references_surface(self):
        self.candidate["evidence_snapshot"]["entries"][0].pop("source_locator")
        rows = meaning_source_rows(self.candidate, self.section["core_meanings"][0], "noun")
        self.assertIsNone(rows[0]["source_locator"])
        self.assertEqual(meaning_source_rows(self.candidate, {}, "noun"), [])
        for ids, pos in ((["unknown"], "noun"), (["sense-1"], "verb")):
            with self.subTest(ids=ids, pos=pos):
                with self.assertRaisesRegex(ValueError, "Meaning provenance cannot resolve"):
                    meaning_source_rows(self.candidate, {"source_sense_ids": ids}, pos)
        self.candidate["evidence_snapshot"]["entries"].append(deepcopy(self.candidate["evidence_snapshot"]["entries"][0]))
        with self.assertRaises(ValueError):
            meaning_source_rows(self.candidate, {"source_sense_ids": ["sense-1"]}, "noun")

    def test_metadata_origin_identity_optional_absence_and_private_boundary(self):
        saved = {
            "id": 10, "version_number": 2, "origin": "retry",
            "candidate_identity": "base-must-not-label-pending",
        }
        self.candidate.update({
            "message": {"thinking": "PRIVATE_SENTINEL"},
            "stages": {"reasoning": "PRIVATE_SENTINEL"},
            "inference": {"scratchpad": "PRIVATE_SENTINEL"},
            "response_metadata": {"message_thinking": "PRIVATE_SENTINEL"},
        })
        for origin, expected in (
            ("search", "Unsaved Search candidate"), ("retry", "Unsaved Retry candidate"),
            ("refresh", "Unsaved Refresh candidate"), ("saved", "Saved accepted version"),
        ):
            with self.subTest(origin=origin):
                state = LexicalState("fixture", candidate=self.candidate, origin=origin, saved_version=saved)
                details = candidate_provenance(state)
                self.assertEqual(details["Viewing"], expected)
                self.assertEqual(details["Produced by"], "Retry" if origin == "saved" else origin.title())
                self.assertEqual(details["Model digest"], "Not recorded")
                self.assertNotIn("PRIVATE_SENTINEL", json.dumps(details))
                self.assertEqual(details["Candidate identity"], hashlib.sha256(
                    json.dumps(self.candidate, sort_keys=True, separators=(",", ":")).encode()).hexdigest())
                self.assertNotEqual(details["Candidate identity"], saved["candidate_identity"])
        self.candidate["model"] = {"thinking": "PRIVATE_SENTINEL"}
        self.assertEqual(candidate_provenance(LexicalState("fixture", candidate=self.candidate))["Synthesis model"], "Not recorded")

    def test_saved_retry_and_refresh_use_their_exact_snapshots(self):
        saved = {
            "normalized_lemma": "fixture", "id": 7, "lexical_entry_id": 2,
            "lexical_entry_version_id": 7, "active_version_id": 7,
            "version_number": 1, "origin": "search", "candidate_identity": "accepted",
            "candidate_snapshot": self.candidate,
            "evidence_snapshot": self.candidate["evidence_snapshot"],
            "evidence_set_hash": self.candidate["evidence_set_hash"],
        }
        workflow = LexicalWorkflow("unused", FakePersistence(saved), FakeProvider())
        current = deepcopy(saved["evidence_snapshot"])
        current["entries"][0]["senses"][0]["glosses"] = ["changed source"]
        current["entries"][0]["dataset_version"] = "fixture-v2"
        current["wiktionary_versions"] = ["fixture-v2"]
        with patch("vocab_workflow.lookup", return_value={"entries": [1]}), \
             patch("vocab_workflow.project_synthesis_evidence", return_value=current):
            accepted = workflow.search("fixture")
            self.assertEqual(meaning_source_rows(accepted.candidate, self.section["core_meanings"][0], "noun")[0]["glosses"], ["one"])
            with patch("vocab_workflow.synthesize_word", return_value={"result": deepcopy(self.candidate)}) as synth:
                retry = workflow.retry_saved(accepted)
            self.assertIs(synth.call_args.kwargs["evidence_snapshot"], saved["evidence_snapshot"])
            retry = workflow.reconcile_authoritative_state("fixture", retry)
            self.assertEqual(meaning_source_rows(retry.candidate, self.section["core_meanings"][0], "noun")[0]["glosses"], ["one"])
            changed_candidate = deepcopy(self.candidate)
            changed_candidate["evidence_snapshot"] = current
            changed_candidate["evidence_set_hash"] = evidence_set_hash(current)
            with patch("vocab_workflow.synthesize_word", return_value={"result": changed_candidate}) as synth:
                refresh = workflow.refresh(accepted)
            self.assertIs(synth.call_args.kwargs["evidence_snapshot"], current)
            refresh = workflow.reconcile_authoritative_state("fixture", refresh)
            self.assertEqual(meaning_source_rows(refresh.candidate, self.section["core_meanings"][0], "noun")[0]["glosses"], ["changed source"])
            self.assertEqual(candidate_provenance(refresh)["Source datasets"], "fixture-v2")
        self.assertEqual(saved["evidence_snapshot"]["entries"][0]["senses"][0]["glosses"], ["one"])


@unittest.skipUnless(find_spec("streamlit"), "requires Streamlit runtime dependencies")
class ProvenanceRenderingTests(unittest.TestCase):
    def test_actual_ui_core_additional_counts_origin_and_no_private_reasoning(self):
        import streamlit as st
        from streamlit.testing.v1 import AppTest
        from pathlib import Path
        from unittest.mock import Mock

        st.cache_resource.clear()
        self.addCleanup(st.cache_resource.clear)
        candidate = candidate_fixture()
        candidate["content"]["pos_sections"][0]["core_meanings"][0]["definition"] = "A trundle wheel unrelated to the recorded gloss."
        self.assertEqual(validate_content(candidate["content"], candidate["evidence_snapshot"]), [])
        candidate["message"] = {"thinking": "PRIVATE_SENTINEL"}
        candidate["stages"] = {"reasoning": "PRIVATE_SENTINEL"}
        saved = {"id": 7, "version_number": 2, "origin": "retry"}
        workflow = Mock()
        state = LexicalState("fixture", candidate=candidate, saved_version=saved, origin="saved")
        workflow.reconcile_authoritative_state.return_value = state
        persistence = Mock()
        persistence.load_history.return_value = []
        with patch("vocab_persistence.PostgresPersistence.from_env", return_value=persistence), \
             patch("vocab_workflow.LexicalWorkflow", return_value=workflow), \
             patch("vocab_lexical_engine.resolve_active_database", return_value=Path("unused")), \
             patch("nltk.data.find"), patch("gtts.gTTS"):
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run()
            app.text_input[0].input("fixture")
            next(button for button in app.button if button.label == "Search").click().run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(len(app.error), 0)
            cues = [item for item in app.expander if item.label == "1 linked source meaning"]
            self.assertEqual(len(cues), 2)
            self.assertFalse(any(item.proto.expanded for item in cues))
            self.assertEqual([item.value for item in cues[0].get("markdown")][:2], ["Wiktionary source meaning 1", "one"])
            self.assertEqual([item.value for item in cues[1].get("markdown")][:2], ["Wiktionary source meaning 1", "two"])
            boundary_copy = "These are the source references recorded for this generated meaning. Checks verify reference identity, source POS and coverage, not that the generated wording accurately represents those sources."
            self.assertTrue(all(boundary_copy in [item.value for item in cue.get("caption")] for cue in cues))
            self.assertIn("**A trundle wheel unrelated to the recorded gloss.**", [item.value for item in app.markdown])
            self.assertTrue(any("Accepted version: 2" in caption.value and "Retry" in caption.value for caption in app.caption))
            visible = [item.value for kind in ("json", "markdown", "caption", "text") for item in app.get(kind)]
            self.assertNotIn("PRIVATE_SENTINEL", str(visible))
            self.assertFalse(any("supporting" in str(value).lower() or "Based on 1 source" in str(value) for value in visible))
            core = candidate["content"]["pos_sections"][0]["core_meanings"][0]
            additional = candidate["content"]["pos_sections"][0]["additional_meanings"][0]
            core["source_sense_ids"] = ["sense-1", "sense-2"]
            core["labels"] = ["informal"]
            candidate["content"]["pos_sections"][0]["additional_meanings"] = []
            self.assertEqual(validate_content(candidate["content"], candidate["evidence_snapshot"]), [])
            app.run()
            plural = next(item for item in app.expander if item.label == "2 linked source meanings")
            self.assertEqual([item.value for item in plural.get("markdown")],
                             ["Wiktionary source meaning 1", "one", "Wiktionary source meaning 2", "two"])
            self.assertIn(boundary_copy, [item.value for item in plural.get("caption")])
            core["source_sense_ids"] = ["sense-1"]
            core["labels"] = []
            candidate["content"]["pos_sections"][0]["additional_meanings"] = [additional]
            for origin in ("search", "retry", "refresh"):
                state.origin = origin
                app.run()
                self.assertIn(f"Unsaved {origin.title()} candidate", [message.value for message in app.info])
                self.assertFalse(next(button for button in app.button if button.label == "Save").disabled)
            candidate["content"]["pos_sections"][0]["core_meanings"][0].pop("source_sense_ids")
            candidate["evidence_snapshot"]["entries"][0].pop("source_locator")
            app.run()
            self.assertTrue(any("Source mapping not recorded" in caption.value for caption in app.caption))
            self.assertTrue(any("Source locator: Not recorded" == caption.value for caption in app.caption))


if __name__ == "__main__":
    unittest.main()
