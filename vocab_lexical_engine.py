"""Deterministic Wiktextract normalization, indexing, and lexical lookup."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "lexical-evidence-v1"
IMPORTER_VERSION = "m004.3-v1"


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def wordnet_version() -> str:
    import nltk
    from nltk.corpus import wordnet

    return f"nltk-{nltk.__version__}-wordnet-{resource_fingerprint(wordnet.root)[:16]}"


def resource_fingerprint(root: Any) -> str:
    """Hash resource names and contents, never the filesystem location."""
    digest = hashlib.sha256()
    if hasattr(root, "zipfile") and hasattr(root, "entry"):
        prefix = root.entry.rstrip("/") + "/"
        for name in sorted(item for item in root.zipfile.namelist() if item.startswith(prefix) and not item.endswith("/")):
            relative = name[len(prefix):].encode("utf-8")
            digest.update(len(relative).to_bytes(8, "big"))
            digest.update(relative)
            digest.update(root.zipfile.read(name))
        return digest.hexdigest()

    root_path = Path(root)
    for path in sorted(item for item in root_path.rglob("*") if item.is_file()):
        relative = path.relative_to(root_path).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
    return digest.hexdigest()


def _source_record_hash(record: dict[str, Any]) -> str:
    return sha256_text(canonical_json(record))


def _entry_key(record: dict[str, Any], record_hash: str) -> str:
    identity = {
        "word": record.get("word", ""),
        "lang_code": record.get("lang_code", ""),
        "pos": record.get("pos", ""),
        "etymology_number": record.get("etymology_number"),
        "record_hash": record_hash,
    }
    return sha256_text(canonical_json(identity))[:24]


def normalize_record(
    record: dict[str, Any], dataset_version: str, source_locator: str
) -> dict[str, Any] | None:
    if record.get("lang_code") not in {"en", "mul"}:
        return None
    word = record.get("word")
    if not word:
        return None
    source_hash = _source_record_hash(record)
    entry_key = _entry_key(record, source_hash)
    base = {
        "source_type": "wiktionary-wiktextract",
        "dataset_version": dataset_version,
        "importer_version": IMPORTER_VERSION,
        "schema_version": SCHEMA_VERSION,
        "source_locator": source_locator,
        "source_record_hash": source_hash,
        "entry_key": entry_key,
        "word": word,
        "normalized_lemma": word.casefold(),
        "language": record.get("lang", ""),
        "language_code": record.get("lang_code", ""),
        "part_of_speech": record.get("pos", ""),
        "source_record": record,
        "senses": [],
        "forms": record.get("forms", []),
        "sounds": record.get("sounds", []),
        "etymology": {
            "text": record.get("etymology_text"),
            "templates": record.get("etymology_templates", []),
        },
        "relations": [],
    }
    sense_occurrences: dict[str, int] = {}
    for index, sense in enumerate(record.get("senses", []), start=1):
        sense_source_id = sense.get("senseid")
        sense_content_hash = sha256_text(canonical_json(sense))[:24]
        sense_identity = sense_source_id or "content"
        occurrence_key = f"{sense_identity}:{sense_content_hash}"
        occurrence = sense_occurrences.get(occurrence_key, 0) + 1
        sense_occurrences[occurrence_key] = occurrence
        sense_key = f"{sense_identity}:{sense_content_hash}:{occurrence}"
        sense_id = f"WIK:{dataset_version}:{IMPORTER_VERSION}:{base['language_code']}:{entry_key}:{sense_key}:sense"
        base["senses"].append({
            "sense_id": sense_id,
            "sense_key": sense_key,
            "source_order": index,
            "glosses": sense.get("glosses", []),
            "raw_glosses": sense.get("raw_glosses", []),
            "tags": sense.get("tags", []),
            "topics": sense.get("topics", []),
            "examples": sense.get("examples", []),
            "source": sense,
        })
        for relation_type in ("synonyms", "antonyms", "related", "derived", "hypernyms", "hyponyms"):
            for relation in sense.get(relation_type, []):
                target = relation.get("word") if isinstance(relation, dict) else relation
                if target:
                    relation_hash = sha256_text(canonical_json(relation))[:24]
                    base["relations"].append({
                        "relation_id": f"WIK:{dataset_version}:{IMPORTER_VERSION}:{base['language_code']}:{entry_key}:{sense_key}:{relation_type}:{relation_hash}",
                        "type": relation_type,
                        "target": target,
                        "sense_id": sense_id,
                        "source": relation,
                    })
    return base


def normalize_jsonl(
    input_path: str | Path,
    output_path: str | Path,
    dataset_version: str,
) -> list[dict[str, Any]]:
    normalized = []
    with open(input_path, encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if line.strip():
                record = json.loads(line)
                item = normalize_record(record, dataset_version, f"{input_path}#line={line_number}")
                if item:
                    normalized.append(item)
    with open(output_path, "w", encoding="utf-8") as target:
        for item in normalized:
            target.write(canonical_json(item) + "\n")
    return normalized


def iter_normalized_jsonl(
    input_path: str | Path, dataset_version: str
) -> Iterable[dict[str, Any]]:
    """Stream normalized records without retaining the production dataset in RAM."""
    with open(input_path, encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if line.strip():
                record = json.loads(line)
                item = normalize_record(
                    record, dataset_version, f"{input_path}#line={line_number}"
                )
                if item:
                    yield item


def normalize_jsonl_streaming(
    input_path: str | Path, output_path: str | Path, dataset_version: str
) -> tuple[int, str]:
    """Write canonical JSONL incrementally and return count plus SHA-256."""
    digest = hashlib.sha256()
    count = 0
    with open(output_path, "w", encoding="utf-8") as target:
        for item in iter_normalized_jsonl(input_path, dataset_version):
            encoded = (canonical_json(item) + "\n").encode("utf-8")
            target.write(encoded.decode("utf-8"))
            digest.update(encoded)
            count += 1
    return count, digest.hexdigest()


def build_manifest(dataset_version: str, source_url: str, input_path: str | Path, normalized: list[dict[str, Any]]) -> dict[str, Any]:
    raw = Path(input_path).read_bytes()
    normalized_jsonl = "".join(canonical_json(item) + "\n" for item in normalized)
    return {
        "schema_version": SCHEMA_VERSION,
        "source_type": "wiktionary-wiktextract",
        "dataset_version": dataset_version,
        "source_url": source_url,
        "source_snapshot": "2026-09-06 enwiktionary dump 2026-09-02",
        "captured_language_codes": ["en", "mul"],
        "importer_version": IMPORTER_VERSION,
        "input_sha256": hashlib.sha256(raw).hexdigest(),
        "normalized_jsonl_sha256": sha256_text(normalized_jsonl),
        "attribution": "Wiktionary/Wikimedia, CC BY-SA 4.0/GFDL as applicable; Wiktextract MIT",
        "record_count": len(normalized),
    }


def write_manifest(manifest: dict[str, Any], manifest_path: str | Path) -> None:
    Path(manifest_path).write_text(canonical_json(manifest) + "\n", encoding="utf-8")


def resolve_active_database(lexical_data_root: str | Path) -> Path:
    """Resolve one configured active version without hard-coding a host path."""
    root = Path(lexical_data_root)
    active = root / "active"
    if active.is_symlink():
        return active.resolve() / "lexical.sqlite"
    version = active.read_text(encoding="utf-8").strip()
    if not version or Path(version).name != version:
        raise ValueError("Invalid active lexical version")
    return root / "versions" / version / "lexical.sqlite"


def build_sqlite(records: Iterable[dict[str, Any]], database_path: str | Path) -> None:
    connection = sqlite3.connect(database_path)
    connection.executescript("""
        PRAGMA journal_mode = WAL;
        CREATE TABLE entries (
            entry_key TEXT PRIMARY KEY, normalized_lemma TEXT NOT NULL, word TEXT NOT NULL,
            language_code TEXT NOT NULL, language TEXT NOT NULL, part_of_speech TEXT NOT NULL,
            dataset_version TEXT NOT NULL, importer_version TEXT NOT NULL,
            source_locator TEXT NOT NULL, source_record_hash TEXT NOT NULL, source_record_json TEXT NOT NULL
        );
        CREATE TABLE senses (
            sense_id TEXT PRIMARY KEY, entry_key TEXT NOT NULL, source_order INTEGER NOT NULL,
            glosses_json TEXT NOT NULL, tags_json TEXT NOT NULL, examples_json TEXT NOT NULL,
            FOREIGN KEY(entry_key) REFERENCES entries(entry_key)
        );
        CREATE TABLE forms (entry_key TEXT NOT NULL, form_json TEXT NOT NULL);
        CREATE TABLE sounds (entry_key TEXT NOT NULL, sound_json TEXT NOT NULL);
        CREATE TABLE relations (relation_id TEXT PRIMARY KEY, entry_key TEXT NOT NULL, relation_json TEXT NOT NULL);
        CREATE VIRTUAL TABLE entries_fts USING fts5(normalized_lemma, word, content='entries', content_rowid='rowid');
    """)
    indexed_entry_hashes: dict[str, str] = {}
    for record in records:
        prior_hash = indexed_entry_hashes.get(record["entry_key"])
        if prior_hash == record["source_record_hash"]:
            continue
        if prior_hash is not None:
            connection.close()
            raise ValueError(f"Conflicting lexical identity: {record['entry_key']}")
        indexed_entry_hashes[record["entry_key"]] = record["source_record_hash"]
        connection.execute("INSERT INTO entries VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (
            record["entry_key"], record["normalized_lemma"], record["word"], record["language_code"],
            record["language"], record["part_of_speech"], record["dataset_version"], record["importer_version"],
            record["source_locator"], record["source_record_hash"], canonical_json(record["source_record"]),
        ))
        for sense in record["senses"]:
            connection.execute("INSERT INTO senses VALUES (?, ?, ?, ?, ?, ?)", (
                sense["sense_id"], record["entry_key"], sense["source_order"], canonical_json(sense["glosses"]),
                canonical_json(sense["tags"]), canonical_json(sense["examples"]),
            ))
        for form in record["forms"]:
            connection.execute("INSERT INTO forms VALUES (?, ?)", (record["entry_key"], canonical_json(form)))
        for sound in record["sounds"]:
            connection.execute("INSERT INTO sounds VALUES (?, ?)", (record["entry_key"], canonical_json(sound)))
        relation_hashes: dict[str, str] = {}
        for relation in record["relations"]:
            relation_json = canonical_json(relation)
            prior_relation = relation_hashes.get(relation["relation_id"])
            if prior_relation == relation_json:
                continue
            if prior_relation is not None:
                connection.close()
                raise ValueError(f"Conflicting lexical relation: {relation['relation_id']}")
            relation_hashes[relation["relation_id"]] = relation_json
            connection.execute("INSERT INTO relations VALUES (?, ?, ?)", (relation["relation_id"], record["entry_key"], relation_json))
    connection.execute("INSERT INTO entries_fts(entries_fts) VALUES ('rebuild')")
    connection.commit()
    connection.close()


def lookup(database_path: str | Path, word: str) -> dict[str, Any]:
    connection = sqlite3.connect(f"file:{Path(database_path).resolve()}?immutable=1", uri=True)
    rows = connection.execute("SELECT * FROM entries WHERE normalized_lemma = ? ORDER BY entry_key", (word.casefold(),)).fetchall()
    entries = []
    for row in rows:
        entry = dict(zip(("entry_key", "normalized_lemma", "word", "language_code", "language", "part_of_speech", "dataset_version", "importer_version", "source_locator", "source_record_hash", "source_record_json"), row))
        senses = connection.execute("SELECT sense_id, source_order, glosses_json, tags_json, examples_json FROM senses WHERE entry_key = ? ORDER BY source_order", (entry["entry_key"],)).fetchall()
        entry["senses"] = [{"sense_id": s[0], "source_order": s[1], "glosses": json.loads(s[2]), "tags": json.loads(s[3]), "examples": json.loads(s[4])} for s in senses]
        entries.append(entry)
    connection.close()
    return {"word": word, "entries": entries, "wordnet": wordnet_evidence(word)}


def wordnet_evidence(word: str) -> list[dict[str, Any]]:
    try:
        from nltk.corpus import wordnet
        synsets = wordnet.synsets(word)
    except (LookupError, ModuleNotFoundError):
        return []
    return [{"synset_id": synset.name(), "pos": synset.pos(), "gloss": synset.definition(), "lemmas": sorted(lemma.name() for lemma in synset.lemmas())} for synset in synsets]


def evidence_bundle(result: dict[str, Any]) -> dict[str, Any]:
    return {"schema_version": "evidence-bundle-v1", "lexical": result.get("entries", []), "wordnet": result.get("wordnet", [])}


def evidence_set_hash(bundle: dict[str, Any]) -> str:
    return sha256_text(canonical_json(bundle))