"""Small framework-independent NLP helpers used by the dictionary flow."""


def _load_wordnet():
    from nltk.corpus import wordnet

    return wordnet


def _load_lemmatizer():
    from nltk.stem import WordNetLemmatizer

    return WordNetLemmatizer()


def get_nltk_root(word: str):
    value = word.lower().strip()

    for part_of_speech in ("n", "v", "a"):
        lemma = _load_lemmatizer().lemmatize(value, pos=part_of_speech)
        if lemma != value:
            return lemma

    return None


def get_synonyms_nltk(word: str) -> list[str]:
    synonyms = set()
    try:
        for synset in _load_wordnet().synsets(word):
            for lemma in synset.lemmas():
                clean_synonym = lemma.name().replace("_", " ")
                if clean_synonym.lower() != word.lower():
                    synonyms.add(clean_synonym)
    except Exception:
        pass

    return list(synonyms)[:5]