"""The small active persistence boundary for the Vocab application."""

import os
from collections.abc import Mapping
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