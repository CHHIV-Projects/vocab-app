"""Small GoogleTranslator boundary for explicit source/target selection."""

SUPPORTED_LANGUAGES = {
    "Auto": "auto",
    "English": "en",
    "French": "fr",
    "Spanish": "es",
    "German": "de",
    "Italian": "it",
}


def _load_translator():
    from deep_translator import GoogleTranslator

    return GoogleTranslator


def translate_text(text: str, source: str, target: str) -> str:
    """Translate text and reject unchanged output when languages differ."""
    result = _load_translator()(source=source, target=target).translate(text)
    if source != target and source != "auto" and result.strip() == text.strip():
        raise ValueError("Translation provider returned the source text unchanged")
    if source == "auto" and result.strip() == text.strip() and target != "auto":
        raise ValueError("Automatic language detection returned the source text unchanged")
    return result