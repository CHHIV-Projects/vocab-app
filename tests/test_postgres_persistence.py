import os
import unittest
import uuid
from copy import deepcopy
from importlib.util import find_spec
from unittest.mock import Mock, patch

from vocab_persistence import PostgresPersistence


class PostgresPersistenceTests(unittest.TestCase):
    @unittest.skipUnless(find_spec("psycopg"), "psycopg is installed in the runtime image")
    def test_connection_factory_uses_external_database_configuration(self):
        connection = Mock()
        with patch("psycopg.connect", return_value=connection) as connect:
            with patch.dict(
                os.environ,
                {
                    "VOCAB_DB_HOST": "db",
                    "VOCAB_DB_PORT": "5432",
                    "VOCAB_DB_NAME": "vocab",
                    "VOCAB_DB_USER": "vocab",
                    "VOCAB_DB_PASSWORD": "test-only",
                },
            ):
                persistence = PostgresPersistence.from_env()

        self.assertIs(persistence.connection, connection)
        self.assertIs(connection.autocommit, True)
        self.assertEqual(connect.call_args.kwargs["host"], "db")
        self.assertEqual(connect.call_args.kwargs["dbname"], "vocab")

    def test_boundary_can_be_constructed_with_a_connection(self):
        connection = Mock()
        persistence = PostgresPersistence(connection)
        self.assertIs(persistence.connection, connection)


@unittest.skipUnless(
    os.environ.get("M002_TEST_POSTGRES") == "1" and find_spec("psycopg"),
    "requires explicitly isolated M002 PostgreSQL configuration",
)
class IsolatedConnectionLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.persistence = PostgresPersistence.from_env()
        self.addCleanup(self.persistence.connection.close)
        self.word = f"m002-transaction-{uuid.uuid4().hex}"
        self.addCleanup(self.remove_test_word)
        self.candidate = {
            "normalized_lemma": self.word,
            "evidence_set_hash": "test-evidence",
            "evidence_snapshot": {"schema_version": "synthesis-evidence-v1"},
            "content": {"pos_sections": [{
                "pos": "noun",
                "core_meanings": [{"definition": "an isolated transaction test"}],
                "additional_meanings": [],
            }]},
        }

    def remove_test_word(self):
        connection = self.persistence.connection
        connection.rollback()
        with connection.transaction():
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE lexical_entries SET active_version_id=NULL WHERE normalized_lemma=%s",
                    (self.word,),
                )
                cursor.execute(
                    "DELETE FROM lexical_entry_versions WHERE lexical_entry_id IN "
                    "(SELECT id FROM lexical_entries WHERE normalized_lemma=%s)",
                    (self.word,),
                )
                cursor.execute("DELETE FROM lexical_entries WHERE normalized_lemma=%s", (self.word,))
                cursor.execute("DELETE FROM vocabulary WHERE word=%s", (self.word,))

    def test_ordinary_reads_leave_connection_idle(self):
        from psycopg.pq import TransactionStatus

        self.assertIs(self.persistence.connection.autocommit, True)
        self.persistence.load_history()
        self.assertEqual(self.persistence.connection.info.transaction_status, TransactionStatus.IDLE)
        self.assertIsNone(self.persistence.load_active_version(self.word))
        self.assertEqual(self.persistence.connection.info.transaction_status, TransactionStatus.IDLE)

    def test_save_after_reads_is_visible_to_independent_connection(self):
        from psycopg.pq import TransactionStatus

        self.persistence.load_history()
        self.assertIsNone(self.persistence.load_active_version(self.word))
        saved = self.persistence.save_accepted_version(self.candidate, "test")
        self.assertEqual(self.persistence.connection.info.transaction_status, TransactionStatus.IDLE)
        independent = PostgresPersistence.from_env()
        self.addCleanup(independent.connection.close)
        reloaded = independent.load_active_version(self.word)
        self.assertIsNotNone(reloaded)
        self.assertEqual(reloaded["active_version_id"], saved["active_version_id"])
        self.assertEqual(reloaded["candidate_identity"], saved["candidate_identity"])
        self.assertEqual(reloaded["evidence_set_hash"], self.candidate["evidence_set_hash"])
        self.assertEqual(reloaded["candidate_snapshot"], self.candidate)
        self.assertEqual(reloaded["evidence_snapshot"], self.candidate["evidence_snapshot"])
        self.assertTrue(independent.word_exists(self.word))
        duplicate = self.persistence.save_accepted_version(self.candidate, "test")
        self.assertTrue(duplicate["idempotent"])
        self.assertEqual(duplicate["active_version_id"], saved["active_version_id"])

    def test_failed_save_rolls_back_entry_and_practice_projection(self):
        from psycopg.pq import TransactionStatus
        from vocab_persistence import _row_value

        self.persistence.load_history()
        ids_read = 0

        def fail_after_version_insert(row, key, position):
            nonlocal ids_read
            ids_read += 1
            if ids_read == 3:
                raise RuntimeError("injected failure after version insert")
            return _row_value(row, key, position)

        with patch("vocab_persistence._row_value", side_effect=fail_after_version_insert):
            with self.assertRaisesRegex(RuntimeError, "injected failure after version insert"):
                self.persistence.save_accepted_version(self.candidate, "test")
        self.assertEqual(self.persistence.connection.info.transaction_status, TransactionStatus.IDLE)
        independent = PostgresPersistence.from_env()
        self.addCleanup(independent.connection.close)
        with independent.connection.cursor() as cursor:
            cursor.execute("SELECT count(*) AS n FROM lexical_entries WHERE normalized_lemma=%s", (self.word,))
            self.assertEqual(cursor.fetchone()["n"], 0)
        self.assertFalse(independent.word_exists(self.word))

    def test_pending_retry_and_refresh_save_preserve_immutable_history(self):
        from vocab_lexical_engine import evidence_set_hash
        from vocab_workflow import LexicalWorkflow

        evidence = {
            "normalized_lemma": self.word, "schema_version": "synthesis-evidence-v1",
            "entries": [], "wordnet_version": "test-only",
        }
        self.candidate["evidence_snapshot"] = evidence
        self.candidate["evidence_set_hash"] = evidence_set_hash(evidence)
        self.persistence.save_accepted_version(self.candidate, "search")
        independent = PostgresPersistence.from_env()
        self.addCleanup(independent.connection.close)
        first = independent.load_active_version(self.word)
        workflow = LexicalWorkflow("unused", self.persistence, Mock())
        with patch("vocab_workflow.lookup", return_value={"entries": [1]}), \
             patch("vocab_workflow.project_synthesis_evidence", return_value=evidence):
            accepted = workflow.search(self.word)
            retry_candidate = deepcopy(self.candidate)
            retry_candidate["content"]["pos_sections"][0]["core_meanings"][0]["definition"] = "retry definition"
            with patch("vocab_workflow.synthesize_word", return_value={"result": retry_candidate}) as synth:
                pending = workflow.retry_saved(accepted)
            self.assertEqual(synth.call_args.kwargs["evidence_snapshot"], first["evidence_snapshot"])
            pending = workflow.reconcile_authoritative_state(self.word, pending)
            self.assertEqual(pending.origin, "retry")
            second_result = workflow.save(pending)
        second = independent.load_active_version(self.word)
        self.assertEqual(second["version_number"], 2)
        self.assertEqual(second["active_version_id"], second_result["active_version_id"])
        self.assertNotEqual(second["candidate_identity"], first["candidate_identity"])
        changed_evidence = dict(evidence, wordnet_version="test-only-changed")
        refresh_candidate = deepcopy(retry_candidate)
        refresh_candidate["evidence_snapshot"] = changed_evidence
        refresh_candidate["evidence_set_hash"] = evidence_set_hash(changed_evidence)
        with patch("vocab_workflow.lookup", return_value={"entries": [1]}), \
             patch("vocab_workflow.project_synthesis_evidence", return_value=changed_evidence):
            accepted = workflow.search(self.word)
            self.assertTrue(accepted.actions["refresh"])
            with patch("vocab_workflow.synthesize_word", return_value={"result": refresh_candidate}):
                pending = workflow.refresh(accepted)
            pending = workflow.reconcile_authoritative_state(self.word, pending)
            self.assertEqual(pending.origin, "refresh")
            third_result = workflow.save(pending)
        third = independent.load_active_version(self.word)
        self.assertEqual(third["version_number"], 3)
        self.assertEqual(third["active_version_id"], third_result["active_version_id"])
        self.assertEqual(third["candidate_snapshot"], refresh_candidate)
        self.assertEqual(third["evidence_snapshot"], changed_evidence)
        with independent.connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, version_number, candidate_snapshot, evidence_snapshot, candidate_identity, origin "
                "FROM lexical_entry_versions WHERE lexical_entry_id=%s ORDER BY version_number",
                (first["lexical_entry_id"],),
            )
            history = cursor.fetchall()
            cursor.execute("SELECT definition FROM vocabulary WHERE word=%s", (self.word,))
            self.assertEqual(cursor.fetchone()["definition"], "retry definition")
        self.assertEqual([row["version_number"] for row in history], [1, 2, 3])
        self.assertEqual([row["origin"] for row in history], ["search", "retry", "refresh"])
        for row, original in zip(history[:2], (first, second)):
            self.assertEqual(row["id"], original["id"])
            self.assertEqual(row["candidate_snapshot"], original["candidate_snapshot"])
            self.assertEqual(row["evidence_snapshot"], original["evidence_snapshot"])
            self.assertEqual(row["candidate_identity"], original["candidate_identity"])

    def test_flag_is_idempotent_without_changing_accepted_version(self):
        self.addCleanup(self.remove_test_flags)
        self.persistence.save_accepted_version(self.candidate, "test")
        original = self.persistence.load_active_version(self.word)
        self.assertTrue(self.persistence.flag_candidate(self.candidate, "saved"))
        self.assertFalse(self.persistence.flag_candidate(self.candidate, "saved"))
        independent = PostgresPersistence.from_env()
        self.addCleanup(independent.connection.close)
        self.assertEqual(independent.load_active_version(self.word), original)
        with independent.connection.cursor() as cursor:
            cursor.execute("SELECT count(*) AS n FROM lexical_flags WHERE normalized_lemma=%s", (self.word,))
            self.assertEqual(cursor.fetchone()["n"], 1)

    def remove_test_flags(self):
        self.persistence.connection.rollback()
        with self.persistence.connection.cursor() as cursor:
            cursor.execute("DELETE FROM lexical_flags WHERE normalized_lemma=%s", (self.word,))


if __name__ == "__main__":
    unittest.main()
