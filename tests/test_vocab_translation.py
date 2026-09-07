import unittest
from unittest.mock import patch

from vocab_translation import translate_text


class TranslationBoundaryTests(unittest.TestCase):
    def test_uses_explicit_source_and_target_languages(self):
        with patch("vocab_translation._load_translator") as load_translator:
            translator = load_translator.return_value
            translator.return_value.translate.return_value = "hot"
            result = translate_text("caliente", source="es", target="en")

        translator.assert_called_once_with(source="es", target="en")
        self.assertEqual(result, "hot")

    def test_rejects_unchanged_output_for_explicit_different_languages(self):
        with patch("vocab_translation._load_translator") as load_translator:
            load_translator.return_value.return_value.translate.return_value = "caliente"
            with self.assertRaises(ValueError):
                translate_text("caliente", source="es", target="en")

    def test_rejects_unchanged_output_from_auto_detection(self):
        with patch("vocab_translation._load_translator") as load_translator:
            load_translator.return_value.return_value.translate.return_value = "caliente"
            with self.assertRaises(ValueError):
                translate_text("caliente", source="auto", target="en")


if __name__ == "__main__":
    unittest.main()