"""Local WordNet adapter for transient word definitions."""

from typing import Any


def _load_wordnet():
    from nltk.corpus import wordnet

    return wordnet


def get_dictionary_data(query: str) -> dict[str, Any] | None:
    """Return the first WordNet sense in the application's result shape."""
    cleaned_query = query.strip()
    if not cleaned_query:
        return None

    synsets = _load_wordnet().synsets(cleaned_query)
    if not synsets:
        return None

    primary_sense = synsets[0]
    return {
        "word": cleaned_query,
        "pos": primary_sense.pos(),
        "definition": primary_sense.definition(),
        "root_ref": None,
    }
