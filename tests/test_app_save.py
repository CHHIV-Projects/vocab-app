import unittest
from contextlib import ExitStack
from importlib.util import find_spec
from pathlib import Path
from unittest.mock import Mock, patch

from vocab_workflow import LexicalState


@unittest.skipUnless(find_spec("streamlit"), "requires Streamlit runtime dependencies")
class LearnerRenderingTests(unittest.TestCase):
    def setUp(self):
        import streamlit as st
        from streamlit.testing.v1 import AppTest

        st.cache_resource.clear()
        self.addCleanup(st.cache_resource.clear)
        self.AppTest = AppTest
        self.persistence = Mock()
        self.persistence.load_history.return_value = []
        self.candidate = {
            "schema_version": "deterministic-lexical-candidate-v1",
            "normalized_lemma": "fixture",
            "wiktionary_versions": ["wiktionary-20260901"],
            "evidence_set_hash": "fixture-hash",
            "evidence_snapshot": {
                "wiktionary_versions": ["wiktionary-20260901"],
                "entries": [{
                    "part_of_speech": "noun",
                    "dataset_version": "wiktionary-20260901",
                    "source_locator": "fixture.jsonl#line=1",
                    "senses": [{
                        "sense_id": "S1",
                        "glosses": ["a source meaning"],
                        "tags": [],
                        "topics": [],
                        "examples": [],
                        "relations": [],
                    }, {
                        "sense_id": "S2",
                        "glosses": ["an additional source meaning"],
                        "tags": [],
                        "topics": [],
                        "examples": [],
                        "relations": [],
                    }],
                }],
            },
            "content": {
                "pos_sections": [{
                    "pos": "noun",
                    "core_meanings": [{
                        "definition": "a source meaning",
                        "source_sense_ids": ["S1"],
                        "labels": [],
                        "synonyms": [],
                        "example_ids": [],
                    }],
                    "additional_meanings": [{
                        "definition": "an additional source meaning",
                        "source_sense_ids": ["S2"],
                        "labels": [],
                        "synonyms": [],
                        "example_ids": [],
                    }],
                }],
            },
            "deterministic": {"us_pronunciations": [], "forms": [], "base_links": []},
            "etymology": [],
        }
        self.workflow = Mock()
        self.workflow.reconcile_authoritative_state.return_value = LexicalState(
            "fixture", candidate=self.candidate, origin="search"
        )
        self.saved_state = LexicalState(
            "fixture",
            candidate=self.candidate,
            saved_version={
                "version_number": 1,
                "active_version_id": 1,
                "lexical_entry_version_id": 1,
            },
            origin="saved",
        )
        self.workflow.search.return_value = self.saved_state
        self.stack = self.enterContext(ExitStack())
        for target, value in (
            ("vocab_persistence.PostgresPersistence.from_env", self.persistence),
            ("vocab_workflow.LexicalWorkflow", self.workflow),
            ("vocab_lexical_engine.active_dataset_status", {
                "dataset_version": "wiktionary-20260901",
                "dump_date": "2026-09-01",
            }),
        ):
            self.stack.enter_context(patch(target, return_value=value))
        self.tts = self.stack.enter_context(patch("gtts.gTTS"))

    def launch(self):
        return self.AppTest.from_file(
            str(Path(__file__).resolve().parents[1] / "app.py")
        ).run()

    def search(self, app):
        app.text_input[0].input("fixture")
        next(button for button in app.button if button.label == "Search").click().run()
        self.assertEqual(len(app.exception), 0)
        return app

    def button(self, app, label):
        return next(button for button in app.button if button.label == label)

    def test_source_derived_ui_shows_dataset_and_removes_ai_controls(self):
        app = self.search(self.launch())
        self.assertIn("**a source meaning**", [item.value for item in app.markdown])
        self.assertTrue(any("Installed: wiktionary-20260901" in item.value for item in app.caption))
        self.assertTrue(any(item.label == "Expand all meanings" for item in app.expander))
        labels = [item.label for item in app.button]
        self.assertNotIn("Retry", labels)
        self.assertIn("Save", labels)
        self.assertIn("Refresh from newer dataset", labels)
        self.assertTrue(self.button(app, "Refresh from newer dataset").disabled)
        self.assertFalse(any("GPT-OSS" in item.value for item in app.caption))
        self.assertFalse(any("Advanced Details" == item.label for item in app.expander))

    def test_short_synonym_lists_remain_visible_with_their_meaning(self):
        self.candidate["content"]["pos_sections"][0]["core_meanings"][0]["synonyms"] = [
            {"term": term} for term in ("term one", "term two", "term three")
        ]

        app = self.search(self.launch())

        self.assertTrue(any(
            item.value == "Synonyms: term one, term two, term three"
            for item in app.caption
        ))
        self.assertFalse(any(item.label == "3 synonyms" for item in app.expander))

    def test_long_synonym_lists_are_collapsed_per_meaning(self):
        terms = [f"term {index}" for index in range(12)]
        self.candidate["content"]["pos_sections"][0]["core_meanings"][0]["synonyms"] = [
            {"term": term} for term in terms
        ]

        app = self.search(self.launch())

        self.assertTrue(any(item.label == "12 synonyms" for item in app.expander))
        self.assertFalse(any(
            item.value.startswith("Synonyms: ") for item in app.caption
        ))

    def test_missing_us_ipa_keeps_requested_audio_fallback_available(self):
        self.tts.return_value.write_to_fp.side_effect = lambda target: target.write(b"audio")

        app = self.search(self.launch())
        self.assertFalse(any("U.S. IPA:" in item.value for item in app.caption))
        self.button(app, "Play pronunciation").click().run()

        self.tts.assert_called_once_with(text="fixture", lang="en")
        self.assertEqual(len(app.exception), 0)

    def test_us_ipa_is_shown_without_non_us_pronunciation(self):
        self.candidate["deterministic"]["us_pronunciations"] = [
            {"ipa": "/ˈfɪkstʃɚ/", "tags": ["US"]}
        ]

        app = self.search(self.launch())

        self.assertTrue(any(
            item.value == "U.S. IPA: /ˈfɪkstʃɚ/" for item in app.caption
        ))

    def test_save_failure_is_visible_and_leaves_entry_unsaved(self):
        app = self.search(self.launch())
        self.workflow.save.side_effect = ValueError("injected persistence failure")
        self.button(app, "Save").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.error), 1)
        self.assertIn("Save failed.", app.error[0].value)
        self.assertFalse(self.button(app, "Save").disabled)

    def test_successful_save_reconciles_to_immutable_accepted_version(self):
        app = self.search(self.launch())

        def accept(_state):
            self.workflow.reconcile_authoritative_state.return_value = self.saved_state
            return {"active_version_id": 1, "lexical_entry_version_id": 1}

        self.workflow.save.side_effect = accept
        self.button(app, "Save").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(self.button(app, "Save").disabled)
        self.assertEqual(self.workflow.save.call_count, 1)
        self.workflow.search.assert_called_once_with("fixture")
        self.assertIn("Saved accepted version", [item.value for item in app.success])


if __name__ == "__main__":
    unittest.main()
