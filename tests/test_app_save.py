import unittest
from copy import deepcopy
from contextlib import ExitStack
from importlib.util import find_spec
from pathlib import Path
from unittest.mock import Mock, patch

from vocab_lexical_engine import evidence_set_hash
from vocab_synthesis import SynthesisFailure
from vocab_workflow import LexicalState, LexicalWorkflow


@unittest.skipUnless(find_spec("streamlit"), "requires Streamlit runtime dependencies")
class SaveRenderingTests(unittest.TestCase):
    def run_save(self, outcome):
        import streamlit as st
        from streamlit.testing.v1 import AppTest

        st.cache_resource.clear()
        self.addCleanup(st.cache_resource.clear)
        candidate = {
            "normalized_lemma": "lantern",
            "content": {"pos_sections": [{
                "pos": "noun",
                "core_meanings": [{"definition": "a portable light"}],
                "additional_meanings": [],
            }]},
        }
        saved = {"id": 7, "active_version_id": 7, "candidate_snapshot": candidate}
        persistence = Mock()
        persistence.load_history.return_value = []
        persistence.load_active_version.return_value = None
        workflow = Mock()
        workflow.search.side_effect = lambda word: LexicalState(
            word,
            candidate=candidate,
            saved_version=persistence.load_active_version.return_value,
            origin="saved" if persistence.load_active_version.return_value else "search",
        )
        workflow.reconcile_authoritative_state.side_effect = lambda word, current: workflow.search(word)

        def save(state):
            if outcome == "error":
                raise ValueError("injected persistence failure")
            if outcome == "missing_version":
                return {}
            persistence.load_active_version.return_value = saved
            return saved

        workflow.save.side_effect = save
        with (
            patch("vocab_persistence.PostgresPersistence.from_env", return_value=persistence),
            patch("vocab_workflow.LexicalWorkflow", return_value=workflow),
            patch("vocab_lexical_engine.resolve_active_database", return_value=Path("unused")),
            patch("nltk.data.find"),
            patch("gtts.gTTS"),
        ):
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"))
            app.run()
            app.text_input[0].input("lantern")
            next(button for button in app.button if button.label == "Search").click().run()
            next(button for button in app.button if button.label == "Save").click().run()
        workflow.save.assert_called_once()
        self.assertEqual(len(app.exception), 0)
        return app

    def test_save_rerenders_authoritative_saved_actions_without_second_click(self):
        app = self.run_save("success")
        self.assertTrue(next(button for button in app.button if button.label == "Save").disabled)
        self.assertFalse(next(button for button in app.button if button.label == "Retry").disabled)
        self.assertTrue(next(button for button in app.button if button.label == "Refresh").disabled)
        self.assertEqual([message.value for message in app.success], ["Saved accepted version"])
        self.assertEqual(len(app.error), 0)

    def test_save_failure_stays_unsaved_and_surfaces_error(self):
        for outcome in ("error", "missing_version"):
            with self.subTest(outcome=outcome):
                app = self.run_save(outcome)
                self.assertFalse(next(button for button in app.button if button.label == "Save").disabled)
                self.assertTrue(next(button for button in app.button if button.label == "Retry").disabled)
                self.assertEqual(len(app.success), 0)
                self.assertEqual(len(app.error), 1)
                self.assertIn("Save failed.", app.error[0].value)


@unittest.skipUnless(find_spec("streamlit"), "requires Streamlit runtime dependencies")
class LifecycleRenderingTests(unittest.TestCase):
    def setUp(self):
        import streamlit as st
        from streamlit.testing.v1 import AppTest

        st.cache_resource.clear()
        self.addCleanup(st.cache_resource.clear)
        self.evidence = {"normalized_lemma": "fixture", "entries": [], "wordnet_version": "base"}
        self.candidate = {
            "normalized_lemma": "fixture", "evidence_snapshot": self.evidence,
            "evidence_set_hash": evidence_set_hash(self.evidence),
            "content": {"pos_sections": [{
                "pos": "noun", "core_meanings": [{"definition": "accepted definition"}],
                "additional_meanings": [],
            }]},
        }
        self.saved = {
            "normalized_lemma": "fixture", "lexical_entry_id": 2,
            "lexical_entry_version_id": 7, "active_version_id": 7, "id": 7,
            "candidate_identity": "accepted", "evidence_snapshot": self.evidence,
            "evidence_set_hash": self.candidate["evidence_set_hash"],
            "candidate_snapshot": deepcopy(self.candidate),
        }
        self.persistence = Mock()
        self.persistence.load_history.return_value = []
        self.persistence.load_active_version.side_effect = lambda word: self.saved if word == "fixture" else None
        self.current_evidence = deepcopy(self.evidence)
        self.workflow = LexicalWorkflow("unused", self.persistence, Mock())
        stack = self.enterContext(ExitStack())
        for target, value in (
            ("vocab_persistence.PostgresPersistence.from_env", self.persistence),
            ("vocab_workflow.LexicalWorkflow", self.workflow),
            ("vocab_lexical_engine.resolve_active_database", Path("unused")),
            ("vocab_workflow.lookup", {"entries": [1]}),
        ):
            stack.enter_context(patch(target, return_value=value))
        stack.enter_context(patch("nltk.data.find"))
        stack.enter_context(patch("gtts.gTTS"))
        stack.enter_context(patch("vocab_workflow.project_synthesis_evidence", side_effect=lambda result: self.current_evidence))
        self.synthesize = stack.enter_context(patch("vocab_workflow.synthesize_word", side_effect=self.generate))
        self.app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run()
        self.app.text_input[0].input("fixture")
        self.click("Search")

    def generate(self, *args, **kwargs):
        candidate = deepcopy(self.candidate)
        evidence = kwargs.get("evidence_snapshot", self.evidence)
        candidate["evidence_snapshot"] = deepcopy(evidence)
        candidate["evidence_set_hash"] = evidence_set_hash(evidence)
        candidate["content"]["pos_sections"][0]["core_meanings"][0]["definition"] = "pending definition"
        return {"result": candidate}

    def button(self, label):
        return next(button for button in self.app.button if button.label == label)

    def click(self, label):
        self.button(label).click().run()
        self.assertEqual(len(self.app.exception), 0)

    def test_retry_pending_survives_reruns_failed_save_and_successful_save(self):
        self.assertTrue(self.button("Refresh").disabled)
        self.click("Retry")
        self.assertIs(self.synthesize.call_args.kwargs["evidence_snapshot"], self.evidence)
        self.assert_pending("retry")
        self.app.run()
        self.assert_pending("retry")
        self.synthesize.assert_called_once()
        self.click("Flag")
        self.persistence.flag_candidate.assert_called_once()
        self.assert_pending("retry")
        self.synthesize.assert_called_once()
        self.persistence.save_accepted_version.side_effect = ValueError("injected failure")
        self.click("Save")
        self.assert_pending("retry")
        self.assertIn("Save failed.", self.app.error[0].value)
        self.persistence.save_accepted_version.side_effect = self.accept
        self.click("Save")
        self.assertTrue(self.button("Save").disabled)
        self.assertFalse(self.button("Retry").disabled)
        self.assertEqual(self.app.session_state.lexical_state.saved_version["active_version_id"], 8)
        self.assertEqual([message.value for message in self.app.success], ["Saved accepted version"])
        self.assertEqual(len(self.app.error), 0)

    def assert_pending(self, origin):
        self.assertEqual(self.app.session_state.lexical_state.origin, origin)
        self.assertFalse(self.button("Save").disabled)
        self.assertTrue(self.button("Retry").disabled)
        self.assertTrue(self.button("Refresh").disabled)
        self.assertFalse(any(message.value == "Saved accepted version" for message in self.app.success))
        self.assertTrue(any("pending definition" in text.value for text in self.app.markdown))

    def accept(self, candidate, origin):
        self.saved = dict(self.saved, candidate_snapshot=deepcopy(candidate),
                          evidence_snapshot=deepcopy(candidate["evidence_snapshot"]),
                          evidence_set_hash=candidate["evidence_set_hash"], candidate_identity="new",
                          lexical_entry_version_id=8, active_version_id=8, id=8)
        return self.saved

    def test_refresh_availability_pending_rerun_and_save(self):
        self.assertTrue(self.button("Refresh").disabled)
        self.current_evidence["wordnet_version"] = "changed"
        self.app.run()
        self.assertFalse(self.button("Refresh").disabled)
        self.click("Refresh")
        self.assertIs(self.synthesize.call_args.kwargs["evidence_snapshot"], self.current_evidence)
        self.assert_pending("refresh")
        self.app.run()
        self.assert_pending("refresh")
        self.synthesize.assert_called_once()
        self.persistence.save_accepted_version.side_effect = self.accept
        self.click("Save")
        self.assertTrue(self.button("Save").disabled)
        self.assertTrue(self.button("Refresh").disabled)
        self.assertEqual(self.app.session_state.lexical_state.saved_version["active_version_id"], 8)

    def test_validation_failure_leaves_saved_controls_and_later_retry_available(self):
        for action in ("Retry", "Refresh"):
            with self.subTest(action=action):
                if action == "Refresh":
                    self.current_evidence["wordnet_version"] = "changed"
                    self.app.run()
                original = deepcopy(self.saved)
                self.synthesize.side_effect = SynthesisFailure(
                    "grouping_validation_failed", "Model grouping failed deterministic validation",
                    details={"errors": ["missing_used_group_definition"]},
                )
                self.click(action)
                self.assertEqual(self.saved, original)
                self.persistence.save_accepted_version.assert_not_called()
                self.assertEqual(self.app.session_state.lexical_state.origin, "saved")
                self.assertTrue(self.button("Save").disabled)
                self.assertFalse(self.button("Retry").disabled)
                self.assertIn(f"{action} failed.", self.app.error[0].value)
        self.synthesize.side_effect = self.generate
        self.click("Retry")
        self.assert_pending("retry")

    def test_changed_or_missing_base_and_different_query_invalidate_pending(self):
        self.click("Retry")
        self.saved = dict(self.saved, lexical_entry_version_id=8, active_version_id=8, candidate_identity="new")
        self.app.run()
        self.assertTrue(self.button("Save").disabled)
        self.assertEqual(self.app.session_state.lexical_state.origin, "saved")
        self.click("Retry")
        self.app.session_state.active_search = "other"
        other = deepcopy(self.candidate)
        other["normalized_lemma"] = "other"
        self.synthesize.side_effect = None
        self.synthesize.return_value = {"result": other}
        self.app.run()
        self.assertEqual(self.app.session_state.lexical_state.candidate["normalized_lemma"], "other")
        self.assertEqual(self.app.session_state.lexical_state.origin, "search")
        self.assertIsNone(self.app.session_state.lexical_state.saved_version)
        self.app.session_state.active_search = "fixture"
        self.synthesize.side_effect = self.generate
        self.app.run()
        self.click("Retry")
        self.assert_pending("retry")
        self.saved = None
        self.synthesize.side_effect = None
        self.synthesize.return_value = {"result": deepcopy(self.candidate)}
        self.app.run()
        self.assertEqual(self.app.session_state.lexical_state.origin, "search")
        self.assertIsNone(self.app.session_state.lexical_state.saved_version)


if __name__ == "__main__":
    unittest.main()
