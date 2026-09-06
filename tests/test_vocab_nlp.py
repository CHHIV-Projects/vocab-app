import unittest
from unittest.mock import patch

from vocab_nlp import get_synonyms_nltk


class FakeLemma:
    def __init__(self, name):
        self._name = name

    def name(self):
        return self._name


class FakeSynset:
    def __init__(self, *names):
        self._lemmas = [FakeLemma(name) for name in names]

    def lemmas(self):
        return self._lemmas


class SynonymTests(unittest.TestCase):
    def test_synonyms_are_normalized_unique_and_exclude_query(self):
        synsets = [
            FakeSynset("bright", "bright_light", "target"),
            FakeSynset("bright", "clear"),
        ]

        with patch("vocab_nlp._load_wordnet") as load_wordnet:
            load_wordnet.return_value.synsets.return_value = synsets
            result = get_synonyms_nltk("target")

        self.assertEqual(
            {value.lower() for value in result},
            {"bright", "bright light", "clear"},
        )

    def test_synonyms_are_limited_to_five_without_order_contract(self):
        allowed_synonyms = {"alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta"}
        synsets = [FakeSynset(*allowed_synonyms, "target")]

        with patch("vocab_nlp._load_wordnet") as load_wordnet:
            load_wordnet.return_value.synsets.return_value = synsets
            result = get_synonyms_nltk("target")

        self.assertEqual(len(result), 5)
        self.assertEqual(len(set(result)), 5)
        self.assertTrue(set(result).issubset(allowed_synonyms))
        self.assertNotIn("target", {value.lower() for value in result})

    def test_synonym_lookup_returns_empty_list_when_lookup_fails(self):
        with patch("vocab_nlp._load_wordnet") as load_wordnet:
            load_wordnet.return_value.synsets.side_effect = LookupError
            self.assertEqual(get_synonyms_nltk("target"), [])


if __name__ == "__main__":
    unittest.main()