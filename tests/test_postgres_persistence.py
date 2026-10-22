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

    def test_explicit_refresh_save_preserves_immutable_history(self):
        from vocab_lexical_engine import evidence_set_hash
        from vocab_workflow import LexicalState, reconcile_saved_state

        evidence = {
            "normalized_lemma": self.word,
            "schema_version": "deterministic-lexical-evidence-v1",
            "wiktionary_versions": ["wiktionary-20260901"],
            "entries": [],
        }
        legacy_candidate = deepcopy(self.candidate)
        legacy_candidate["schema_version"] = "historical-ai-candidate-fixture"
        legacy_candidate["model"] = "historical-model-fixture"
        legacy_candidate["model_digest"] = "historical-digest-fixture"
        legacy_candidate["prompt_version"] = "historical-prompt-fixture"
        legacy_candidate["evidence_snapshot"] = evidence
        legacy_candidate["evidence_set_hash"] = evidence_set_hash(evidence)
        self.persistence.save_accepted_version(legacy_candidate, "historical")
        independent = PostgresPersistence.from_env()
        self.addCleanup(independent.connection.close)
        first = independent.load_active_version(self.word)
        refresh_candidate = deepcopy(self.candidate)
        refresh_candidate["content"]["pos_sections"][0]["core_meanings"][0]["definition"] = "new source-derived definition"
        refresh_candidate["schema_version"] = "deterministic-lexical-candidate-v1"
        refresh_candidate.pop("model", None)
        refresh_candidate.pop("model_digest", None)
        refresh_candidate.pop("prompt_version", None)
        changed_evidence = {
            **evidence,
            "wiktionary_versions": ["wiktionary-20261001"],
        }
        refresh_candidate["evidence_snapshot"] = changed_evidence
        refresh_candidate["evidence_set_hash"] = evidence_set_hash(changed_evidence)

        reopened = reconcile_saved_state(
            LexicalState(self.word, candidate=refresh_candidate, origin="search"),
            self.word,
            independent,
        )
        self.assertEqual(reopened.origin, "saved")
        self.assertEqual(reopened.candidate, first["candidate_snapshot"])
        self.assertEqual(
            reopened.candidate["content"]["pos_sections"][0]["core_meanings"][0]["definition"],
            "an isolated transaction test",
        )

        refresh_state = reconcile_saved_state(
            LexicalState(
                self.word,
                candidate=refresh_candidate,
                saved_version=first,
                origin="refresh",
            ),
            self.word,
            independent,
        )
        self.assertEqual(refresh_state.origin, "refresh")
        self.assertEqual(refresh_state.candidate, refresh_candidate)
        second_result = self.persistence.save_accepted_version(refresh_candidate, "refresh")
        second = independent.load_active_version(self.word)
        self.assertEqual(second["version_number"], 2)
        self.assertEqual(second["origin"], "refresh")
        self.assertEqual(second["active_version_id"], second_result["active_version_id"])
        self.assertNotEqual(second["candidate_identity"], first["candidate_identity"])
        with independent.connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, version_number, candidate_snapshot, evidence_snapshot, candidate_identity, origin, "
                "model_identity, prompt_identity "
                "FROM lexical_entry_versions WHERE lexical_entry_id=%s ORDER BY version_number",
                (first["lexical_entry_id"],),
            )
            history = cursor.fetchall()
            cursor.execute("SELECT definition FROM vocabulary WHERE word=%s", (self.word,))
            self.assertEqual(cursor.fetchone()["definition"], "new source-derived definition")
        self.assertEqual([row["version_number"] for row in history], [1, 2])
        self.assertEqual([row["origin"] for row in history], ["historical", "refresh"])
        for row, original in zip(history, (first, second)):
            self.assertEqual(row["id"], original["id"])
            self.assertEqual(row["candidate_snapshot"], original["candidate_snapshot"])
            self.assertEqual(row["evidence_snapshot"], original["evidence_snapshot"])
            self.assertEqual(row["candidate_identity"], original["candidate_identity"])
        self.assertEqual(
            history[0]["model_identity"],
            {"model": "historical-model-fixture", "digest": "historical-digest-fixture"},
        )
        self.assertEqual(
            history[0]["prompt_identity"],
            {"prompt": "historical-prompt-fixture"},
        )
        self.assertEqual(history[1]["model_identity"], {})
        self.assertEqual(history[1]["prompt_identity"], {})

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
