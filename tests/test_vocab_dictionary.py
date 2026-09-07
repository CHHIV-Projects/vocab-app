import unittest
from unittest.mock import Mock, patch

from vocab_dictionary import get_dictionary_data


class DictionaryAdapterTests(unittest.TestCase):
    def test_maps_primary_wordnet_sense_to_application_shape(self):
        primary = Mock()
        primary.pos.return_value = "n"
        primary.definition.return_value = "a focused test definition"
        secondary = Mock()

        with patch("vocab_dictionary._load_wordnet") as load_wordnet:
            load_wordnet.return_value.synsets.return_value = [primary, secondary]
            result = get_dictionary_data("bright")

        load_wordnet.return_value.synsets.assert_called_once_with("bright")
        primary.pos.assert_called_once_with()
        primary.definition.assert_called_once_with()
        secondary.pos.assert_not_called()
        self.assertEqual(
            result,
            {
                "word": "bright",
                "pos": "n",
                "definition": "a focused test definition",
                "root_ref": None,
            },
        )

    def test_unknown_word_returns_none(self):
        with patch("vocab_dictionary._load_wordnet") as load_wordnet:
            load_wordnet.return_value.synsets.return_value = []
            self.assertIsNone(get_dictionary_data("not-a-real-word"))

    def test_empty_query_returns_none_without_lookup(self):
        with patch("vocab_dictionary._load_wordnet") as load_wordnet:
            self.assertIsNone(get_dictionary_data("  "))
            load_wordnet.return_value.synsets.assert_not_called()

    def test_definition_lookup_requires_no_network_or_api_key(self):
        primary = Mock()
        primary.pos.return_value = "v"
        primary.definition.return_value = "to test"

        with patch("vocab_dictionary._load_wordnet") as load_wordnet:
            load_wordnet.return_value.synsets.return_value = [primary]
            result = get_dictionary_data("test")

        self.assertEqual(result["pos"], "v")
        self.assertEqual(result["definition"], "to test")


if __name__ == "__main__":
    unittest.main()