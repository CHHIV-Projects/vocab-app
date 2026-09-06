import unittest

from vocab_persistence import GoogleSheetsPersistence


class FakeSheet:
    def __init__(self):
        self.records = [{"Word": "alpha", "Count": 2}]
        self.appended = []
        self.writes = []

    def get_all_records(self):
        return self.records

    def col_values(self, column):
        self.assert_column(column)
        return [record["Word"] for record in self.records]

    def append_row(self, values):
        self.appended.append(values)

    def find(self, word):
        return type("Cell", (), {"row": 2})() if word == "alpha" else None

    def cell(self, row, column):
        self.assert_column(column)
        return type("Cell", (), {"value": "2"})()

    def update_cell(self, row, column, score):
        self.assert_column(column)
        self.writes.append((row, column, score))

    @staticmethod
    def assert_column(column):
        if column not in (1, 6):
            raise AssertionError(f"unexpected column {column}")


class PersistenceBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.sheet = FakeSheet()
        self.persistence = GoogleSheetsPersistence(self.sheet)

    def test_load_records_and_history_use_sheet_reads(self):
        self.assertEqual(self.persistence.load_records(), self.sheet.records)
        self.assertEqual(self.persistence.load_history(), self.sheet.records)

    def test_duplicate_detection_and_append_are_confined_to_adapter(self):
        self.assertTrue(self.persistence.word_exists("ALPHA"))
        self.assertFalse(self.persistence.word_exists("beta"))
        self.persistence.append_record(["beta", "definition"])
        self.assertEqual(self.sheet.appended, [["beta", "definition"]])

    def test_score_lookup_and_write_preserve_sheet_columns(self):
        cell = self.persistence.find_word("alpha")
        current = self.persistence.read_score(cell.row)
        self.persistence.write_score(cell.row, current + 1)
        self.assertEqual(self.sheet.writes, [(2, 6, 3)])


if __name__ == "__main__":
    unittest.main()