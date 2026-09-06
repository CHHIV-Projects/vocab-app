"""Framework-independent vocabulary practice rules."""

import random
from typing import Any, Iterable


def coerce_count(value: Any) -> int:
    """Preserve the application's current count rule."""
    return value if isinstance(value, int) else 1


def select_practice_candidates(
    records: Iterable[dict[str, Any]], limit: int = 10
) -> list[dict[str, Any]]:
    """Select the lowest-count records before any random ordering."""
    normalized_records = []
    for record in records:
        normalized_record = dict(record)
        normalized_record["Count"] = coerce_count(normalized_record.get("Count"))
        normalized_records.append(normalized_record)

    sorted_records = sorted(normalized_records, key=lambda record: record["Count"])
    return sorted_records[:limit]


def shuffle_practice_candidates(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Shuffle a selected practice batch in place, matching the current flow."""
    random.shuffle(records)
    return records


def next_score(current_count: int, success: bool) -> int:
    """Return the score written for a successful or missed card."""
    return current_count + 1 if success else 1


def update_score(persistence: Any, word: str, success: bool) -> None:
    """Apply the current score rule through the persistence boundary."""
    cell = persistence.find_word(word)
    if cell:
        current_score = persistence.read_score(cell.row)
        persistence.write_score(cell.row, next_score(current_score, success))