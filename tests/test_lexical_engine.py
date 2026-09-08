import json
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

from vocab_lexical_engine import (
    build_manifest,
    build_sqlite,
    evidence_bundle,
    evidence_set_hash,
    lookup,
    normalize_jsonl,
    resource_fingerprint,
    resolve_active_database,
    write_manifest,
    wordnet_version,
)


FIXTURE = Path(__file__).parent / "fixtures" / "run.jsonl"
RUNNING_FIXTURE = Path(__file__).parent / "fixtures" / "running.jsonl"


class LexicalEngineTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.normalized_path = self.root / "evidence.jsonl"
        self.database_path = self.root / "lexical.sqlite"
        self.records = normalize_jsonl(FIXTURE, self.normalized_path, "fixture-20260906")
        self.records.extend(
            normalize_jsonl(RUNNING_FIXTURE, self.root / "running.jsonl", "fixture-20260906")
        )
        build_sqlite(self.records, self.database_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_normalization_preserves_multiple_pos_and_senses(self):
        result = lookup(self.database_path, "run")
        self.assertGreaterEqual(len(result["entries"]), 3)
        self.assertTrue(any(entry["part_of_speech"] == "verb" for entry in result["entries"]))
        self.assertTrue(any(entry["senses"] for entry in result["entries"]))

    def test_running_is_exact_lookup_not_silent_lemma_fallback(self):
        result = lookup(self.database_path, "running")
        self.assertTrue(result["entries"])
        self.assertTrue(all(entry["word"] == "running" for entry in result["entries"]))

    def test_unknown_word_is_empty_but_has_parallel_wordnet_shape(self):
        result = lookup(self.database_path, "not-a-fixture-word")
        self.assertEqual(result["entries"], [])
        self.assertIn("wordnet", result)

    def test_manifest_and_hash_are_deterministic(self):
        manifest = build_manifest("fixture-20260906", "https://kaikki.org/dictionary/English/meaning/r/ru/run.jsonl", FIXTURE, self.records)
        self.assertEqual(manifest["record_count"], len(self.records))
        bundle = evidence_bundle(lookup(self.database_path, "run"))
        self.assertEqual(evidence_set_hash(bundle), evidence_set_hash(json.loads(json.dumps(bundle))))
        changed = dict(bundle)
        changed["schema_version"] = "changed"
        self.assertNotEqual(evidence_set_hash(bundle), evidence_set_hash(changed))

    def test_resource_fingerprint_depends_on_content_not_path(self):
        first = self.root / "wordnet-a"
        second = self.root / "wordnet-b"
        first.mkdir()
        second.mkdir()
        (first / "data.txt").write_text("same", encoding="utf-8")
        (second / "data.txt").write_text("same", encoding="utf-8")
        self.assertEqual(resource_fingerprint(first), resource_fingerprint(second))
        (second / "data.txt").write_text("changed", encoding="utf-8")
        self.assertNotEqual(resource_fingerprint(first), resource_fingerprint(second))

    def test_wordnet_version_works_with_operational_resource_pointer(self):
        try:
            version = wordnet_version()
        except ModuleNotFoundError:
            self.skipTest("NLTK is unavailable in the host test environment")
        self.assertIn("nltk-", version)
        self.assertIn("-wordnet-", version)

    def test_repeated_lookup_latency_is_measurable(self):
        samples = []
        for _ in range(50):
            started = time.perf_counter()
            lookup(self.database_path, "run")
            samples.append(time.perf_counter() - started)
        self.assertEqual(len(samples), 50)
        self.assertGreaterEqual(min(samples), 0)

    def test_sqlite_has_expected_projection_tables(self):
        connection = sqlite3.connect(self.database_path)
        names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view')")}
        connection.close()
        self.assertTrue({"entries", "senses", "forms", "sounds", "relations", "entries_fts"}.issubset(names))

    def test_sqlite_skips_identical_duplicate_records_but_rejects_conflicts(self):
        duplicate_records = self.records + [self.records[0]]
        duplicate_db = self.root / "duplicate.sqlite"
        build_sqlite(duplicate_records, duplicate_db)
        connection = sqlite3.connect(duplicate_db)
        count = connection.execute("SELECT count(*) FROM entries").fetchone()[0]
        connection.close()
        self.assertEqual(count, len({record["entry_key"] for record in self.records}))

        conflicting = dict(self.records[0])
        conflicting["source_record_hash"] = "conflicting-hash"
        with self.assertRaises(ValueError):
            build_sqlite(self.records + [conflicting], self.root / "conflict.sqlite")

    def test_duplicate_source_sense_ids_remain_distinct(self):
        record = {
            "word": "free",
            "lang": "English",
            "lang_code": "en",
            "pos": "adjective",
            "senses": [
                {"senseid": "en:shared", "glosses": ["first"]},
                {"senseid": "en:shared", "glosses": ["second"]},
            ],
        }
        from vocab_lexical_engine import normalize_record
        normalized = normalize_record(record, "fixture", "fixture#1")
        self.assertEqual(len({sense["sense_id"] for sense in normalized["senses"]}), 2)

    def test_relation_identity_includes_source_relation_content(self):
        record = {
            "word": "test",
            "lang": "English",
            "lang_code": "en",
            "pos": "noun",
            "senses": [{"glosses": ["one"], "synonyms": [{"word": "same", "tags": ["one"]}, {"word": "same", "tags": ["two"]}]}],
        }
        from vocab_lexical_engine import normalize_record
        normalized = normalize_record(record, "fixture", "fixture#1")
        ids = [relation["relation_id"] for relation in normalized["relations"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_manifest_writes_and_active_version_resolves(self):
        manifest = build_manifest("fixture-20260906", "https://example.invalid/run.jsonl", FIXTURE, self.records[:4])
        manifest_path = self.root / "versions" / "fixture-20260906" / "manifest.json"
        manifest_path.parent.mkdir(parents=True)
        write_manifest(manifest, manifest_path)
        active = self.root / "active"
        active.write_text("fixture-20260906\n", encoding="utf-8")
        expected = self.root / "versions" / "fixture-20260906" / "lexical.sqlite"
        expected.parent.mkdir(exist_ok=True)
        self.assertEqual(resolve_active_database(self.root), expected)


if __name__ == "__main__":
    unittest.main()