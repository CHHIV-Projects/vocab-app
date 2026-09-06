CREATE TABLE IF NOT EXISTS vocabulary (
    id BIGSERIAL PRIMARY KEY,
    word TEXT NOT NULL,
    definition TEXT NOT NULL DEFAULT '',
    part_of_speech TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    created_on DATE NOT NULL,
    count INTEGER NOT NULL DEFAULT 1,
    CONSTRAINT vocabulary_word_not_blank CHECK (btrim(word) <> ''),
    CONSTRAINT vocabulary_count_positive CHECK (count >= 1)
);

CREATE UNIQUE INDEX IF NOT EXISTS vocabulary_word_lower_unique
    ON vocabulary (lower(word));
