import unittest
import os
from copy import deepcopy
from unittest.mock import patch

from vocab_lexical_engine import evidence_set_hash
from vocab_workflow import LexicalState, LexicalWorkflow, enrich_candidate, deduplicated_forms, reconcile_saved_state, source_detail_rows, sort_pos_sections
from vocab_synthesis import SynthesisRuntime


class FakePersistence:
    def __init__(self, saved):
        self.saved = saved

    def load_active_version(self, word):
        return self.saved


class FakeProvider:
    def generate(self, prompt, *, seed=None, schema=None):
        return {"message": {"content": '{"summary":"From supplied evidence","evidence_ids":["E1"]}', "thinking": "hidden"}, "done_reason": "stop"}


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.evidence = {
            "schema_version": "synthesis-evidence-v1",
            "normalized_lemma": "fixture",
            "wiktionary_versions": ["fixture"],
            "wordnet_version": "wordnet",
            "entries": [{
                "entry_key": "entry",
                "part_of_speech": "noun",
                "etymology": {"text": None, "templates": [], "evidence_id": "E0"},
                "senses": [{"sense_id": "S1", "tags": [], "relations": [{"type": "synonyms", "target": "rapid", "evidence_id": "R1"}], "examples": []}],
            }],
            "wordnet": [],
        }
        self.candidate = {
            "normalized_lemma": "fixture",
            "evidence_set_hash": evidence_set_hash(self.evidence),
            "evidence_snapshot": self.evidence,
            "content": {"pos_sections": [{"pos": "noun", "core_meanings": [{"definition": "fast", "source_sense_ids": ["S1"], "labels": [], "synonyms": [], "example_ids": []}], "additional_meanings": []}]},
        }

    def test_retry_uses_saved_snapshot_without_current_lookup(self):
        saved = {"evidence_snapshot": self.evidence, "evidence_set_hash": self.candidate["evidence_set_hash"], "candidate_snapshot": self.candidate, "id": 7}
        workflow = LexicalWorkflow("unused", FakePersistence(saved), FakeProvider())
        state = LexicalState("fixture", saved_version=saved, candidate=self.candidate, origin="saved")
        retry_candidate = dict(self.candidate)
        with patch("vocab_workflow.lookup", side_effect=AssertionError("current lookup used")), patch("vocab_workflow.synthesize_word", return_value={"result": retry_candidate}) as synthesize:
            retried = workflow.retry_saved(state)
        synthesize.assert_called_once()
        self.assertEqual(retried.origin, "retry")
        self.assertEqual(retried.candidate["evidence_set_hash"], state.saved_version["evidence_set_hash"])

    def test_synonym_enrichment_maps_source_relation_to_group(self):
        enriched = enrich_candidate(self.candidate, FakeProvider())
        synonyms = enriched["content"]["pos_sections"][0]["core_meanings"][0]["synonyms"]
        self.assertEqual(synonyms, [{"term": "rapid", "evidence_ids": ["R1"]}])

    def test_saved_hash_mismatch_is_rejected_before_retry(self):
        saved = {"evidence_snapshot": self.evidence, "evidence_set_hash": "wrong", "candidate_snapshot": self.candidate}
        workflow = LexicalWorkflow("unused", FakePersistence(saved), FakeProvider())
        with self.assertRaises(Exception) as caught:
            workflow.retry_saved(LexicalState("fixture", saved_version=saved, candidate=self.candidate, origin="saved"))
        self.assertEqual(getattr(caught.exception, "code", None), "saved_evidence_hash_mismatch")

    def test_runtime_root_uses_container_environment_path(self):
        with patch.dict(os.environ, {"VOCAB_RUNTIME_ROOT": "/vocab-runtime"}, clear=False):
            self.assertEqual(str(SynthesisRuntime().root), "/vocab-runtime")

    def test_source_detail_rows_normalize_structured_examples(self):
        candidate = {"evidence_snapshot": {"entries": [{"part_of_speech": "noun", "senses": [{"sense_id": "S1", "glosses": ["a turn"], "tags": ["informal"], "examples": [{"text": {"quote": "a turn"}}], "relations": []}]}]}}
        rows = source_detail_rows(candidate)
        self.assertEqual(rows[0]["examples"], [{"quote": "a turn"}])

    def test_form_deduplication_and_action_states(self):
        candidate = {"deterministic": {"forms": [{"form": {"form": "meandered"}}, {"form": {"form": "Meandered"}}, {"form": {"form": "meandering"}}]}}
        self.assertEqual(deduplicated_forms(candidate), ["meandered", "meandering"])
        self.assertTrue(LexicalState("word", candidate={"x": 1}).actions["save"])
        saved = LexicalState("word", candidate={"x": 1}, saved_version={"id": 1}, origin="saved")
        self.assertTrue(saved.actions["retry"])
        self.assertFalse(saved.actions["save"])

    def test_pos_sections_put_ordinary_lexical_pos_before_names(self):
        sections = sort_pos_sections([{"pos": "name"}, {"pos": "verb"}, {"pos": "noun"}])
        self.assertEqual([section["pos"] for section in sections], ["noun", "verb", "name"])

    def test_stale_saved_state_is_overridden_by_authoritative_database(self):
        stale = LexicalState("phone", candidate={"normalized_lemma": "phone"}, saved_version={"id": 99}, origin="saved")
        reconciled_missing = reconcile_saved_state(stale, "phone", FakePersistence(None))
        self.assertIsNotNone(reconciled_missing)
        self.assertEqual(reconciled_missing.origin, "search")
        self.assertIsNone(reconciled_missing.saved_version)

        saved = {"id": 99, "evidence_snapshot": self.evidence, "evidence_set_hash": self.candidate["evidence_set_hash"], "candidate_snapshot": self.candidate}
        reconciled_present = reconcile_saved_state(stale, "phone", FakePersistence(saved))
        self.assertEqual(reconciled_present.origin, "saved")
        self.assertEqual(reconciled_present.saved_version["id"], 99)

    def test_rerender_reconciles_saved_session_state_against_db_truth(self):
        stale = LexicalState(
            "phone",
            candidate={"normalized_lemma": "phone", "content": {"pos_sections": [{"pos": "noun", "core_meanings": [{"definition": "a number", "source_sense_ids": [], "labels": [], "synonyms": [], "example_ids": []}], "additional_meanings": []}]}, "evidence_set_hash": "hash-phone"},
            saved_version={"id": 99, "lexical_entry_version_id": 99, "active_version_id": 99, "candidate_identity": "phone-candidate"},
            origin="saved",
        )
        workflow = LexicalWorkflow("unused", FakePersistence(None), FakeProvider())
        with patch("vocab_workflow.synthesize_word", return_value={"result": self.candidate}) as synthesize:
            reconciled = workflow.reconcile_authoritative_state("phone", stale)
        self.assertEqual(reconciled.origin, "search")
        self.assertIsNone(reconciled.saved_version)
        self.assertTrue(reconciled.actions["save"])
        self.assertFalse(reconciled.actions["retry"])
        synthesize.assert_not_called()

    def saved_version(self):
        return {
            "normalized_lemma": "fixture", "lexical_entry_id": 2,
            "lexical_entry_version_id": 7, "active_version_id": 7,
            "candidate_identity": "accepted", "evidence_set_hash": self.candidate["evidence_set_hash"],
            "candidate_snapshot": deepcopy(self.candidate), "evidence_snapshot": deepcopy(self.evidence),
        }

    def test_pending_candidates_survive_only_matching_authoritative_base(self):
        saved = self.saved_version()
        for origin in ("retry", "refresh"):
            with self.subTest(origin=origin):
                pending = LexicalState(" Fixture ", candidate=deepcopy(self.candidate),
                                       saved_version=deepcopy(saved), origin=origin)
                pending.candidate["content"]["marker"] = "pending"
                preserved = reconcile_saved_state(pending, "FIXTURE", FakePersistence(saved))
                self.assertIs(preserved.candidate, pending.candidate)
                self.assertEqual(preserved.origin, origin)
                self.assertTrue(preserved.actions["save"])
                for key in ("lexical_entry_id", "lexical_entry_version_id", "active_version_id",
                            "candidate_identity", "evidence_set_hash"):
                    with self.subTest(changed=key):
                        changed = dict(saved, **{key: "changed"})
                        resolved = reconcile_saved_state(pending, "fixture", FakePersistence(changed))
                        self.assertEqual(resolved.origin, "saved")
                        self.assertIs(resolved.candidate, changed["candidate_snapshot"])
                        incomplete = deepcopy(pending)
                        incomplete.saved_version.pop(key)
                        self.assertEqual(reconcile_saved_state(incomplete, "fixture", FakePersistence(saved)).origin, "saved")
                self.assertIsNone(reconcile_saved_state(pending, "fixture", FakePersistence(None)))
                self.assertIsNone(reconcile_saved_state(pending, "other", FakePersistence(None)))

    def test_query_and_candidate_lemma_guards_for_all_transient_origins(self):
        for origin in ("search", "saved", "retry", "refresh"):
            for changed in ("query", "candidate"):
                with self.subTest(origin=origin, changed=changed):
                    state = LexicalState("fixture", candidate=deepcopy(self.candidate),
                                         saved_version=self.saved_version(), origin=origin)
                    if changed == "query":
                        state.query = "other"
                    else:
                        state.candidate["normalized_lemma"] = "other"
                    self.assertIsNone(reconcile_saved_state(state, "fixture", FakePersistence(None)))
                    saved = self.saved_version()
                    resolved = reconcile_saved_state(state, "fixture", FakePersistence(saved))
                    self.assertEqual(resolved.origin, "saved")
                    self.assertIs(resolved.candidate, saved["candidate_snapshot"])

    def test_pending_evidence_integrity_and_retry_snapshot_identity(self):
        saved = self.saved_version()
        for origin in ("retry", "refresh"):
            pending = LexicalState("fixture", candidate=deepcopy(self.candidate),
                                   saved_version=saved, origin=origin)
            pending.candidate["evidence_snapshot"]["wordnet_version"] = "changed"
            self.assertEqual(reconcile_saved_state(pending, "fixture", FakePersistence(saved)).origin, "saved")
            pending.candidate["evidence_set_hash"] = evidence_set_hash(pending.candidate["evidence_snapshot"])
            resolved = reconcile_saved_state(pending, "fixture", FakePersistence(saved))
            self.assertEqual(resolved.origin, "refresh" if origin == "refresh" else "saved")
            pending.failure = {"code": "invalid"}
            self.assertEqual(reconcile_saved_state(pending, "fixture", FakePersistence(saved)).origin, "saved")

    def test_workflow_resolves_refresh_and_reuses_unsaved_search_candidate(self):
        saved = self.saved_version()
        persistence = FakePersistence(saved)
        workflow = LexicalWorkflow("unused", persistence, FakeProvider())
        for changed in (False, True):
            current_evidence = deepcopy(self.evidence)
            if changed:
                current_evidence["wordnet_version"] = "changed"
            with patch("vocab_workflow.lookup", return_value={"entries": [1]}), \
                 patch("vocab_workflow.project_synthesis_evidence", return_value=current_evidence), \
                 patch("vocab_workflow.synthesize_word") as synth:
                resolved = workflow.reconcile_authoritative_state("fixture")
            self.assertEqual(resolved.actions["refresh"], changed)
            synth.assert_not_called()
        persistence.saved = None
        current = LexicalState("fixture", candidate=self.candidate)
        with patch("vocab_workflow.synthesize_word") as synth:
            resolved = workflow.reconcile_authoritative_state("fixture", current)
        self.assertIs(resolved.candidate, current.candidate)
        synth.assert_not_called()
        pending = LexicalState("fixture", candidate=self.candidate, saved_version=saved, origin="retry")
        with patch("vocab_workflow.synthesize_word", return_value={"result": deepcopy(self.candidate)}) as synth:
            resolved = workflow.reconcile_authoritative_state("fixture", pending)
        synth.assert_called_once()
        self.assertIsNone(resolved.saved_version)
        self.assertEqual(resolved.origin, "search")


if __name__ == "__main__":
    unittest.main()
