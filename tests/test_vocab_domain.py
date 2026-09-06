import unittest
from unittest.mock import Mock, patch

from vocab_domain import (
    coerce_count,
    next_score,
    select_practice_candidates,
    shuffle_practice_candidates,
    update_score,
)


class PracticeSelectionTests(unittest.TestCase):
    def test_count_coercion_preserves_current_non_int_rule(self):
        self.assertEqual(coerce_count(4), 4)
        self.assertEqual(coerce_count(None), 1)
        self.assertEqual(coerce_count("4"), 1)
        self.assertEqual(coerce_count(""), 1)
        self.assertEqual(coerce_count(4.0), 1)

    def test_selection_is_stable_sorted_and_limited(self):
        records = [
            {"Word": "third", "Count": 2},
            {"Word": "first", "Count": 1},
            {"Word": "second", "Count": 1},
        ]

        selected = select_practice_candidates(records, limit=2)

        self.assertEqual([record["Word"] for record in selected], ["first", "second"])

    def test_selection_handles_fewer_than_ten_records(self):
        records = [{"Word": "one", "Count": 3}]
        self.assertEqual(select_practice_candidates(records), records)

    def test_shuffle_is_separate_from_candidate_selection(self):
        records = [{"Word": "one", "Count": 1}, {"Word": "two", "Count": 2}]
        selected = select_practice_candidates(records)

        with patch("vocab_domain.random.shuffle") as shuffle:
            result = shuffle_practice_candidates(selected)

        shuffle.assert_called_once_with(selected)
        self.assertIs(result, selected)


class ScoringTests(unittest.TestCase):
    def test_success_increments_current_count(self):
        self.assertEqual(next_score(4, success=True), 5)

    def test_missed_card_resets_count_to_one(self):
        self.assertEqual(next_score(4, success=False), 1)

    def test_update_score_looks_up_row_and_writes_score_column(self):
        persistence = Mock()
        persistence.find_word.return_value = type("Cell", (), {"row": 7})()
        persistence.read_score.return_value = 4

        update_score(persistence, "word", success=True)

        persistence.find_word.assert_called_once_with("word")
        persistence.read_score.assert_called_once_with(7)
        persistence.write_score.assert_called_once_with(7, 5)


if __name__ == "__main__":
    unittest.main()