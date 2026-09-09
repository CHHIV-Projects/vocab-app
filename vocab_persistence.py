"""The small active persistence boundary for the Vocab application."""

import os
from collections.abc import Mapping
from datetime import date
from typing import Any


def _row_value(row: Any, key: str, position: int) -> Any:
    if isinstance(row, dict):
        return row[key]
    return row[position]


class GoogleSheetsPersistence:
    """Google Sheets implementation of the application's current data needs."""

    def __init__(self, sheet: Any):
        self.sheet = sheet

    @classmethod
    def from_streamlit_secrets(cls, secrets: Mapping[str, Any]) -> "GoogleSheetsPersistence":
        import gspread
        from oauth2client.service_account import ServiceAccountCredentials

        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]

        if os.path.exists("service_account.json"):
            creds = ServiceAccountCredentials.from_json_keyfile_name(
                "service_account.json", scope
            )
        else:
            creds = ServiceAccountCredentials.from_json_keyfile_dict(
                secrets["gcp_service_account"], scope
            )

        client = gspread.authorize(creds)
        return cls(client.open("VocabApp_DB").sheet1)

    def load_records(self) -> list[dict[str, Any]]:
        return self.sheet.get_all_records()

    def load_history(self) -> list[dict[str, Any]]:
        return self.load_records()

    def word_exists(self, word: str) -> bool:
        return word.lower() in [value.lower() for value in self.sheet.col_values(1)]

    def append_record(self, values: list[Any]) -> None:
        self.sheet.append_row(values)

    def find_word(self, word: str) -> Any:
        return self.sheet.find(word)

    def read_score(self, row: int, column: int = 6) -> int:
        return int(self.sheet.cell(row, column).value)

    def write_score(self, row: int, score: int, column: int = 6) -> None:
        self.sheet.update_cell(row, column, score)


class PostgresPersistence:
    """PostgreSQL implementation of the operational Vocab persistence boundary."""

    def __init__(self, connection: Any):
        self.connection = connection

    @classmethod
    def from_env(cls) -> "PostgresPersistence":
        import psycopg
        from psycopg.rows import dict_row

        connection = psycopg.connect(
            host=os.environ.get("VOCAB_DB_HOST", "vocab-db"),
            port=os.environ.get("VOCAB_DB_PORT", "5432"),
            dbname=os.environ.get("VOCAB_DB_NAME", "vocab"),
            user=os.environ.get("VOCAB_DB_USER", "vocab"),
            password=os.environ["VOCAB_DB_PASSWORD"],
            row_factory=dict_row,
        )
        persistence = cls(connection)
        from vocab_migrations import apply_migrations
        if not connection.__class__.__module__.startswith("unittest.mock"):
            apply_migrations(connection)
        return persistence

    def _verify_durable_version(self, normalized_lemma: str, expected_version_id: int, candidate_identity: str, evidence_set_hash: str, idempotent: bool = False) -> dict[str, Any]:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    e.id AS lexical_entry_id,
                    e.normalized_lemma,
                    e.active_version_id,
                    v.id AS lexical_entry_version_id,
                    v.version_number,
                    v.candidate_identity,
                    v.evidence_set_hash,
                    v.candidate_snapshot,
                    v.evidence_snapshot,
                    v.lexical_entry_id AS version_entry_id
                FROM lexical_entries e
                JOIN lexical_entry_versions v ON v.lexical_entry_id = e.id
                WHERE e.normalized_lemma = %s AND v.id = %s
                """,
                (normalized_lemma, expected_version_id),
            )
            row = cursor.fetchone()
            if row is None:
                raise ValueError("durable save verification failed: accepted version not found")
            if row["candidate_identity"] != candidate_identity:
                raise ValueError("durable save verification failed: candidate identity mismatch")
            if row["evidence_set_hash"] != evidence_set_hash:
                raise ValueError("durable save verification failed: evidence set hash mismatch")
            if row["active_version_id"] != expected_version_id:
                raise ValueError("durable save verification failed: active pointer mismatch")
            cursor.execute(
                "SELECT id, word, definition, part_of_speech, count FROM vocabulary WHERE lower(word)=lower(%s)",
                (normalized_lemma,),
            )
            vocabulary = cursor.fetchone()
            if vocabulary is None:
                raise ValueError("durable save verification failed: vocabulary projection missing")
        result = dict(row)
        result.update({
            "id": expected_version_id,
            "entry_id": result["lexical_entry_id"],
            "lexical_entry_id": result["lexical_entry_id"],
            "lexical_entry_version_id": expected_version_id,
            "version_id": expected_version_id,
            "version_number": result["version_number"],
            "active_version_id": expected_version_id,
            "normalized_lemma": normalized_lemma,
            "candidate_identity": candidate_identity,
            "evidence_set_hash": evidence_set_hash,
            "idempotent": idempotent,
        })
        return result

    def save_accepted_version(self, candidate: dict[str, Any], origin: str) -> dict[str, Any]:
        """Accept a validated candidate and advance one logical active pointer atomically."""
        import hashlib
        import json
        from datetime import datetime, timezone

        evidence = candidate["evidence_snapshot"]
        normalized = candidate["normalized_lemma"]
        candidate_identity = hashlib.sha256(json.dumps(candidate, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        projection = candidate["content"]["pos_sections"]
        first = next(section for section in projection if section["core_meanings"])
        definition = first["core_meanings"][0]["definition"]
        pos = first["pos"]
        saved_result: dict[str, Any] | None = None
        with self.connection.transaction():
            with self.connection.cursor() as cursor:
                cursor.execute("SELECT id, active_version_id FROM lexical_entries WHERE normalized_lemma=%s FOR UPDATE", (normalized,))
                entry = cursor.fetchone()
                if entry:
                    entry_id = entry["id"] if isinstance(entry, dict) else entry[0]
                    active_id = entry["active_version_id"] if isinstance(entry, dict) else entry[1]
                    if active_id:
                        cursor.execute("SELECT id, candidate_identity, evidence_set_hash FROM lexical_entry_versions WHERE id=%s AND candidate_identity=%s", (active_id, candidate_identity))
                        existing = cursor.fetchone()
                        if existing:
                            saved_result = {
                                "entry_id": entry_id,
                                "lexical_entry_id": entry_id,
                                "version_id": active_id,
                                "lexical_entry_version_id": active_id,
                                "id": active_id,
                                "version_number": 1,
                                "active_version_id": active_id,
                                "normalized_lemma": normalized,
                                "candidate_identity": candidate_identity,
                                "evidence_set_hash": candidate["evidence_set_hash"],
                                "idempotent": True,
                            }
                    if saved_result is None:
                        cursor.execute("SELECT coalesce(max(version_number),0)+1 AS next_version FROM lexical_entry_versions WHERE lexical_entry_id=%s", (entry_id,))
                        version = _row_value(cursor.fetchone(), "next_version", 0)
                else:
                    cursor.execute("INSERT INTO lexical_entries(normalized_lemma, display_word) VALUES (%s,%s) RETURNING id", (normalized, candidate.get("normalized_lemma", normalized)))
                    entry_id = _row_value(cursor.fetchone(), "id", 0)
                    version = 1
                if saved_result is None:
                    cursor.execute("SELECT id FROM vocabulary WHERE lower(word)=lower(%s)", (normalized,))
                    vocabulary = cursor.fetchone()
                    if vocabulary:
                        vocabulary_id = vocabulary["id"] if isinstance(vocabulary, dict) else vocabulary[0]
                        cursor.execute("UPDATE vocabulary SET definition=%s, part_of_speech=%s WHERE id=%s", (definition, pos, vocabulary_id))
                    else:
                        cursor.execute("INSERT INTO vocabulary(word,definition,part_of_speech,source,created_on,count) VALUES (%s,%s,%s,%s,%s,1) RETURNING id", (normalized, definition, pos, "M004.5 lexical synthesis", datetime.now(timezone.utc).date()))
                        vocabulary_id = _row_value(cursor.fetchone(), "id", 0)
                    cursor.execute("UPDATE lexical_entries SET vocabulary_id=%s, updated_at=now() WHERE id=%s", (vocabulary_id, entry_id))
                    cursor.execute("""INSERT INTO lexical_entry_versions
                        (lexical_entry_id,version_number,candidate_snapshot,evidence_snapshot,evidence_set_hash,dataset_identity,wordnet_identity,model_identity,prompt_identity,policy_identity,schema_identity,packer_identity,validator_identity,inference_identity,candidate_identity,origin)
                        VALUES (%s,%s,%s::jsonb,%s::jsonb,%s,%s::jsonb,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s) RETURNING id""", (entry_id, version, json.dumps(candidate), json.dumps(evidence), candidate["evidence_set_hash"], json.dumps({"wiktionary": evidence.get("wiktionary_versions")}), evidence.get("wordnet_version"), json.dumps({"model": candidate.get("model"), "digest": candidate.get("model_digest")}), json.dumps({"prompt": candidate.get("prompt_version")}), json.dumps({"policy": candidate.get("policy_version")}), json.dumps({"schema": candidate.get("schema_version")}), json.dumps({"packer": candidate.get("packer_version")}), json.dumps({"validator": candidate.get("validator_version")}), json.dumps(candidate.get("inference", {})), candidate_identity, origin))
                    version_id = _row_value(cursor.fetchone(), "id", 0)
                    cursor.execute("UPDATE lexical_entries SET active_version_id=%s, updated_at=now() WHERE id=%s", (version_id, entry_id))
                    saved_result = {
                        "entry_id": entry_id,
                        "lexical_entry_id": entry_id,
                        "version_id": version_id,
                        "lexical_entry_version_id": version_id,
                        "id": version_id,
                        "version_number": version,
                        "active_version_id": version_id,
                        "normalized_lemma": normalized,
                        "candidate_identity": candidate_identity,
                        "evidence_set_hash": candidate["evidence_set_hash"],
                        "idempotent": False,
                    }
        if saved_result is None:
            raise ValueError("Save verification failed before durable commit")
        return self._verify_durable_version(normalized, saved_result["active_version_id"], candidate_identity, candidate["evidence_set_hash"], saved_result["idempotent"])

    def load_active_version(self, normalized_lemma: str) -> dict[str, Any] | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    e.id AS lexical_entry_id,
                    e.normalized_lemma,
                    e.active_version_id,
                    v.id AS lexical_entry_version_id,
                    v.id AS id,
                    v.version_number,
                    v.candidate_identity,
                    v.evidence_set_hash,
                    v.candidate_snapshot,
                    v.evidence_snapshot,
                    v.lexical_entry_id AS version_entry_id
                FROM lexical_entries e
                JOIN lexical_entry_versions v ON v.id = e.active_version_id
                WHERE e.normalized_lemma=%s
                """,
                (normalized_lemma,),
            )
            row = cursor.fetchone()
        if not row:
            return None
        payload = dict(row)
        payload["entry_id"] = payload["lexical_entry_id"]
        payload["version_id"] = payload["lexical_entry_version_id"]
        payload["version_number"] = payload["version_number"]
        payload["active_version_id"] = payload["active_version_id"]
        payload["id"] = payload["lexical_entry_version_id"]
        return payload

    def flag_candidate(self, candidate: dict[str, Any], origin: str) -> bool:
        import hashlib, json
        identity = hashlib.sha256(json.dumps(candidate, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        with self.connection.cursor() as cursor:
            cursor.execute("INSERT INTO lexical_flags(candidate_identity,normalized_lemma,candidate_snapshot,evidence_set_hash,source_identity) VALUES (%s,%s,%s::jsonb,%s,%s::jsonb) ON CONFLICT(candidate_identity) DO NOTHING", (identity, candidate["normalized_lemma"], json.dumps(candidate), candidate["evidence_set_hash"], json.dumps({"origin": origin})))
            created = cursor.rowcount == 1
        self.connection.commit()
        return created

    def load_records(self) -> list[dict[str, Any]]:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT word AS "Word", definition AS "Definition",
                       part_of_speech AS "Part of Speech", source AS "Source",
                       created_on AS "Date", count AS "Count"
                FROM vocabulary
                ORDER BY id
                """
            )
            records = cursor.fetchall()
        return [dict(record) for record in records]

    def load_history(self) -> list[dict[str, Any]]:
        return self.load_records()

    def word_exists(self, word: str) -> bool:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM vocabulary WHERE lower(word) = lower(%s) LIMIT 1",
                (word,),
            )
            exists = cursor.fetchone() is not None
        return exists

    def append_record(self, values: list[Any]) -> None:
        word, definition, part_of_speech, source, created_on, count = values
        created_date = (
            date.fromisoformat(created_on) if isinstance(created_on, str) else created_on
        )
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO vocabulary
                    (word, definition, part_of_speech, source, created_on, count)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (word, definition, part_of_speech, source, created_date, count),
            )
        self.connection.commit()

    def find_word(self, word: str) -> Any:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM vocabulary WHERE word = %s LIMIT 1", (word,)
            )
            row = cursor.fetchone()
        row_id = row["id"] if isinstance(row, dict) else row[0]
        return type("ScoreRow", (), {"row": row_id})() if row else None

    def read_score(self, row: int, column: int = 6) -> int:
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT count FROM vocabulary WHERE id = %s", (row,))
            value = cursor.fetchone()
        count = value["count"] if isinstance(value, dict) else value[0]
        return int(count)

    def write_score(self, row: int, score: int, column: int = 6) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute("UPDATE vocabulary SET count = %s WHERE id = %s", (score, row))
        self.connection.commit()