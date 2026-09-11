import hashlib
import json
import os
import unittest
from importlib.util import find_spec


@unittest.skipUnless(os.environ.get("M0045_TEST_DATABASE_URL") and find_spec("psycopg"), "set M0045_TEST_DATABASE_URL and install psycopg for isolated PostgreSQL tests")
class IsolatedPostgresM0045Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        from psycopg.rows import dict_row
        from vocab_migrations import apply_migrations
        cls.connection = psycopg.connect(os.environ["M0045_TEST_DATABASE_URL"], row_factory=dict_row)
        apply_migrations(cls.connection)

    @classmethod
    def tearDownClass(cls):
        cls.connection.close()

    def test_ledger_schema_and_idempotency(self):
        from vocab_migrations import apply_migrations
        self.assertEqual(apply_migrations(self.connection), [])
        with self.connection.cursor() as cursor:
            cursor.execute("select version from schema_migrations")
            self.assertEqual(
                {row["version"] for row in cursor.fetchall()},
                {"002_m0045_lexical_versioning", "003_m004610_consolidation_persistence"},
            )
        self.connection.commit()

    def test_save_projection_versioning_and_flag_idempotency(self):
        from vocab_persistence import PostgresPersistence
        persistence = PostgresPersistence(self.connection)
        candidate = {"normalized_lemma": "isolated", "evidence_set_hash": "hash-1", "content": {"pos_sections": [{"pos": "noun", "core_meanings": [{"definition": "a test word", "source_sense_ids": [], "labels": [], "synonyms": [], "example_ids": []}], "additional_meanings": []}]}, "evidence_snapshot": {"schema_version": "synthesis-evidence-v1"}}
        first = persistence.save_accepted_version(candidate, "test")
        second = persistence.save_accepted_version(candidate, "test")
        self.assertFalse(first["idempotent"])
        self.assertTrue(second["idempotent"])
        self.assertTrue(persistence.flag_candidate(candidate, "test"))
        self.assertFalse(persistence.flag_candidate(candidate, "test"))
        with self.connection.cursor() as cursor:
            cursor.execute("select count(*), min(count), max(count) from vocabulary where lower(word)='isolated'")
            row = cursor.fetchone()
            self.assertEqual((row["count"], row["min"], row["max"]), (1, 1, 1))

    def test_save_returns_durable_accepted_version_after_new_connection(self):
        import psycopg
        from psycopg.rows import dict_row
        from vocab_persistence import PostgresPersistence

        candidate = {
            "normalized_lemma": "durable",
            "evidence_set_hash": "hash-verify-1",
            "candidate_identity": None,
            "content": {
                "pos_sections": [{
                    "pos": "noun",
                    "core_meanings": [{
                        "definition": "a durable verification word",
                        "source_sense_ids": [],
                        "labels": [],
                        "synonyms": [],
                        "example_ids": [],
                    }],
                    "additional_meanings": [],
                }]
            },
            "evidence_snapshot": {"schema_version": "synthesis-evidence-v1"},
        }
        candidate["candidate_identity"] = hashlib.sha256(json.dumps(candidate, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

        persistence = PostgresPersistence(self.connection)
        saved = persistence.save_accepted_version(candidate, "test")

        self.assertEqual(saved["version_number"], 1)
        self.assertEqual(saved["lexical_entry_version_id"], saved["active_version_id"])
        self.assertEqual(saved["candidate_identity"], candidate["candidate_identity"])
        self.assertEqual(saved["evidence_set_hash"], candidate["evidence_set_hash"])

        self.connection.close()
        reopened = psycopg.connect(os.environ["M0045_TEST_DATABASE_URL"], row_factory=dict_row)
        try:
            reloaded = PostgresPersistence(reopened).load_active_version(candidate["normalized_lemma"])
            self.assertIsNotNone(reloaded)
            self.assertEqual(reloaded["version_number"], 1)
            self.assertEqual(reloaded["candidate_identity"], candidate["candidate_identity"])
            self.assertEqual(reloaded["evidence_set_hash"], candidate["evidence_set_hash"])
            self.assertIn("candidate_snapshot", reloaded)
            self.assertIn("evidence_snapshot", reloaded)
            self.assertEqual(reloaded["normalized_lemma"], candidate["normalized_lemma"])
            with reopened.cursor() as cursor:
                cursor.execute("select count(*) from vocabulary where lower(word)=lower(%s)", (candidate["normalized_lemma"],))
                self.assertEqual(cursor.fetchone()["count"], 1)
        finally:
            reopened.close()
            self.connection = psycopg.connect(os.environ["M0045_TEST_DATABASE_URL"], row_factory=dict_row)


if __name__ == "__main__":
    unittest.main()