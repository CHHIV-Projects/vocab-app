"""The small active persistence boundary for the Vocab application."""

import os
from collections.abc import Mapping
from datetime import date
from typing import Any


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
        return cls(connection)

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