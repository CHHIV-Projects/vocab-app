"""M004.6.10.1: isolated PostgreSQL tests proving the corrected pair-ordering CHECK constraint
uses `COLLATE "C"` (matching Python's canonical Unicode/code-point ordering) rather than the
database's locale-aware default collation.

Two independently configured disposable databases are used:

- `M0046101_TEST_DATABASE_URL`: a fresh, empty disposable database, to prove the full
  002 -> 003 -> 004 migration path.
- `M0046101_UPGRADE_TEST_DATABASE_URL`: a disposable database already at migration 003
  (M004.6.10), to prove the additive 003 -> 004 upgrade path in isolation from a fresh install.

If only the fresh-install variable is set, the upgrade-path test is skipped individually
rather than skipping the whole suite, so both paths can be validated independently.
"""

import os
import unittest
import uuid
from importlib.util import find_spec

PSYCOPG_AVAILABLE = find_spec("psycopg") is not None


def _connect(url):
    import psycopg

    return psycopg.connect(url)


@unittest.skipUnless(os.environ.get("M0046101_TEST_DATABASE_URL") and PSYCOPG_AVAILABLE, "set M0046101_TEST_DATABASE_URL and install psycopg for isolated PostgreSQL tests")
class FreshMigrationPathTests(unittest.TestCase):
    """Fresh, empty database: 002 -> 003 -> 004 must all apply cleanly."""

    @classmethod
    def setUpClass(cls):
        from vocab_migrations import apply_migrations

        cls.connection = _connect(os.environ["M0046101_TEST_DATABASE_URL"])
        cls.applied = apply_migrations(cls.connection)

    @classmethod
    def tearDownClass(cls):
        cls.connection.close()

    def test_all_three_migrations_apply_in_order_on_a_fresh_database(self):
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT version FROM schema_migrations ORDER BY version")
            versions = {row[0] if not isinstance(row, dict) else row["version"] for row in cursor.fetchall()}
        self.assertEqual(versions, {
            "002_m0045_lexical_versioning",
            "003_m004610_consolidation_persistence",
            "004_m004610_1_pair_ordering_collation_correction",
        })

    def test_corrected_constraint_is_present_and_uses_c_collation(self):
        with self.connection.cursor() as cursor:
            cursor.execute("""
                SELECT pg_get_constraintdef(oid) FROM pg_constraint
                WHERE conname = 'lexical_pair_judgments_source_ids_ordered'
            """)
            (definition,) = cursor.fetchone()
        self.assertIn('COLLATE "C"', definition)


@unittest.skipUnless(os.environ.get("M0046101_UPGRADE_TEST_DATABASE_URL") and PSYCOPG_AVAILABLE, "set M0046101_UPGRADE_TEST_DATABASE_URL (already at migration 003) and install psycopg")
class UpgradeMigrationPathTests(unittest.TestCase):
    """A database already at migration 003 (M004.6.10): only 004 should apply additively."""

    @classmethod
    def setUpClass(cls):
        from vocab_migrations import apply_migrations

        cls.connection = _connect(os.environ["M0046101_UPGRADE_TEST_DATABASE_URL"])
        with cls.connection.cursor() as cursor:
            cursor.execute("SELECT version FROM schema_migrations ORDER BY version")
            cls.versions_before = {row[0] if not isinstance(row, dict) else row["version"] for row in cursor.fetchall()}
        cls.applied = apply_migrations(cls.connection)

    @classmethod
    def tearDownClass(cls):
        cls.connection.close()

    def test_database_was_already_at_migration_003_before_this_test(self):
        self.assertEqual(self.versions_before, {"002_m0045_lexical_versioning", "003_m004610_consolidation_persistence"})

    def test_only_the_004_migration_applies_additively(self):
        self.assertEqual(self.applied, ["004_m004610_1_pair_ordering_collation_correction"])

    def test_corrected_constraint_is_present_after_upgrade(self):
        with self.connection.cursor() as cursor:
            cursor.execute("""
                SELECT pg_get_constraintdef(oid) FROM pg_constraint
                WHERE conname = 'lexical_pair_judgments_source_ids_ordered'
            """)
            (definition,) = cursor.fetchone()
        self.assertIn('COLLATE "C"', definition)

    def test_existing_003_tables_and_data_contract_are_unaffected(self):
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass('lexical_consolidation_jobs'), to_regclass('lexical_pair_judgments'), to_regclass('lexical_consolidation_containers')")
            row = cursor.fetchone()
        self.assertEqual(tuple(row), ("lexical_consolidation_jobs", "lexical_pair_judgments", "lexical_consolidation_containers"))


@unittest.skipUnless(os.environ.get("M0046101_TEST_DATABASE_URL") and PSYCOPG_AVAILABLE, "set M0046101_TEST_DATABASE_URL and install psycopg for isolated PostgreSQL tests")
class ConstraintBehaviorTests(unittest.TestCase):
    """Direct CHECK-constraint validation for ordinary and anomalous (list-like) source IDs."""

    @classmethod
    def setUpClass(cls):
        from vocab_migrations import apply_migrations

        cls.connection = _connect(os.environ["M0046101_TEST_DATABASE_URL"])
        apply_migrations(cls.connection)

    @classmethod
    def tearDownClass(cls):
        cls.connection.close()

    def setUp(self):
        self.connection.rollback()

    def _job_id(self, token):
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO lexical_consolidation_jobs (
                    consolidation_identity, normalized_lemma, evidence_set_hash, partition_identity,
                    partition_manifest, pair_judgment_contract_version, semantic_model_identity,
                    semantic_options_identity, topology_contract_version, container_contract_version,
                    expected_pair_count
                ) VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s::jsonb, %s::jsonb, %s, %s, %s)
                RETURNING id
                """,
                (token, "fixture", "evidence-hash", "partition-id", "{}", "pair-judgment-v1-exhaustive-qwen",
                 "{}", "{}", "complete-link-v1", "learner-containers-v1", 1),
            )
            row = cursor.fetchone()
            job_id = row["id"] if isinstance(row, dict) else row[0]
        return job_id

    def _insert_pair(self, job_id, sense_a, sense_b, token):
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO lexical_pair_judgments (
                    consolidation_job_id, partition_identity, logical_pair_id,
                    source_sense_id_a, source_sense_id_b, pair_judgment_identity,
                    pair_judgment_contract_version, semantic_model_identity, semantic_options_identity,
                    evidence_set_hash
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (job_id, "partition-id", f"pair-{token}", sense_a, sense_b, f"judgment-{token}",
                 "pair-judgment-v1-exhaustive-qwen", "{}", "{}", "evidence-hash"),
            )

    def test_canonical_ordinary_pair_inserts_successfully(self):
        token = uuid.uuid4().hex
        job_id = self._job_id(token)
        self._insert_pair(job_id, "sense-alpha", "sense-beta", token)
        self.connection.commit()
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM lexical_pair_judgments WHERE logical_pair_id = %s", (f"pair-{token}",))
            (count,) = cursor.fetchone()
        self.assertEqual(count, 1)

    def test_reversed_ordinary_pair_is_rejected(self):
        import psycopg

        token = uuid.uuid4().hex
        job_id = self._job_id(token)
        with self.assertRaises(psycopg.errors.CheckViolation):
            self._insert_pair(job_id, "sense-beta", "sense-alpha", token)
        self.connection.rollback()

    def test_canonical_anomalous_list_like_pair_inserts_successfully(self):
        # This is the real shape observed in the live corpus: a stringified Wikidata-QID list
        # embedded in the sense ID, which previously triggered the CHECK-constraint failure
        # under the database's default locale-aware collation.
        token = uuid.uuid4().hex
        job_id = self._job_id(token)
        sense_a = "WIK:wiktionary-20260901:m004.3-v1:en:c922e763649711dfbac25110:['en:Q15872']:7f9d65e53e813e2f33a83d8c:1:sense"
        sense_b = "WIK:wiktionary-20260901:m004.3-v1:en:c922e763649711dfbac25110:content:bd98ca3ff42c7ccd4f2becb2:1:sense"
        self.assertTrue(sense_a < sense_b)  # Python canonical ordering (the accepted authority)
        self._insert_pair(job_id, sense_a, sense_b, token)
        self.connection.commit()
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM lexical_pair_judgments WHERE logical_pair_id = %s", (f"pair-{token}",))
            (count,) = cursor.fetchone()
        self.assertEqual(count, 1)

    def test_reversed_anomalous_list_like_pair_is_rejected(self):
        import psycopg

        token = uuid.uuid4().hex
        job_id = self._job_id(token)
        sense_a = "WIK:wiktionary-20260901:m004.3-v1:en:c922e763649711dfbac25110:['en:Q15872']:7f9d65e53e813e2f33a83d8c:1:sense"
        sense_b = "WIK:wiktionary-20260901:m004.3-v1:en:c922e763649711dfbac25110:content:bd98ca3ff42c7ccd4f2becb2:1:sense"
        with self.assertRaises(psycopg.errors.CheckViolation):
            self._insert_pair(job_id, sense_b, sense_a, token)  # reversed
        self.connection.rollback()

    def test_default_collation_would_have_rejected_the_canonical_anomalous_pair(self):
        """Demonstrates the original defect directly, using the real corpus pair that first
        surfaced it (gecko, entry c922e763649711dfbac25110): under the database's default
        (non-"C") collation, the *canonical* Python-ordered pair fails its `<` comparison,
        which is exactly why the M004.6.10 CHECK constraint rejected a correctly-ordered
        insert during the M004.6.12 live smoke test. Under `COLLATE "C"` the same comparison
        agrees with Python, proving the correction depends on the explicit collation."""
        sense_a = "WIK:wiktionary-20260901:m004.3-v1:en:c922e763649711dfbac25110:['en:Q15872']:7f9d65e53e813e2f33a83d8c:1:sense"
        sense_b = "WIK:wiktionary-20260901:m004.3-v1:en:c922e763649711dfbac25110:content:bd98ca3ff42c7ccd4f2becb2:1:sense"
        self.assertTrue(sense_a < sense_b)  # Python canonical ordering (the accepted authority)
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT %s < %s", (sense_a, sense_b))  # canonical order, default collation
            (default_collation_says_canonical_is_ordered,) = cursor.fetchone()
            cursor.execute('SELECT (%s COLLATE "C") < (%s COLLATE "C")', (sense_a, sense_b))
            (c_collation_says_canonical_is_ordered,) = cursor.fetchone()
        self.assertFalse(default_collation_says_canonical_is_ordered)
        self.assertTrue(c_collation_says_canonical_is_ordered)


@unittest.skipUnless(os.environ.get("M0046101_TEST_DATABASE_URL") and PSYCOPG_AVAILABLE, "set M0046101_TEST_DATABASE_URL and install psycopg for isolated PostgreSQL tests")
class RealPreviouslyFailingEvidenceTests(unittest.TestCase):
    """Reproduce the exact M004.6.12 live-smoke failure (gecko/noun) against the corrected schema."""

    @classmethod
    def setUpClass(cls):
        from vocab_migrations import apply_migrations

        cls.connection = _connect(os.environ["M0046101_TEST_DATABASE_URL"])
        apply_migrations(cls.connection)

    @classmethod
    def tearDownClass(cls):
        cls.connection.close()

    def test_previously_failing_gecko_noun_partition_now_persists_pairs_successfully(self):
        from vocab_consolidation import build_partitions, enumerate_pairs
        from vocab_consolidation_persistence import ConsolidationPersistence

        evidence = {
            "normalized_lemma": "gecko",
            "wiktionary_versions": ["wiktionary-20260901"],
            "wordnet_version": "wordnet-test",
            "entries": [{
                "entry_key": "gecko-noun",
                "part_of_speech": "noun",
                "senses": [
                    {"sense_id": "WIK:wiktionary-20260901:m004.3-v1:en:9b3ba253d812eb9992873755:content:402dc7a01dbdca9889cab552:1:sense",
                     "source_order": 1, "glosses": ["a lizard"], "labels": [], "topics": [], "examples": [], "relations": []},
                    {"sense_id": "WIK:wiktionary-20260901:m004.3-v1:en:c922e763649711dfbac25110:content:bd98ca3ff42c7ccd4f2becb2:1:sense",
                     "source_order": 2, "glosses": ["a car model"], "labels": [], "topics": [], "examples": [], "relations": []},
                    {"sense_id": "WIK:wiktionary-20260901:m004.3-v1:en:c922e763649711dfbac25110:['en:Q15872']:7f9d65e53e813e2f33a83d8c:1:sense",
                     "source_order": 3, "glosses": ["a place name"], "labels": [], "topics": [], "examples": [], "relations": []},
                ],
            }],
            "wordnet": [],
        }
        partition = build_partitions(evidence)[0]
        self.assertEqual(partition.expected_pair_count, 3)
        persistence = ConsolidationPersistence(self.connection)
        job = persistence.create_or_get_job(
            partition, lexical_dataset_identity={"dataset": "test"},
            model_identity={"name": "qwen3:8b", "digest": "test"}, semantic_options={"seed": 5100},
        )
        rows = persistence.initialize_pairs(job["id"], partition)
        self.assertEqual(len(rows), 3)
        self.connection.commit()


if __name__ == "__main__":
    unittest.main()
