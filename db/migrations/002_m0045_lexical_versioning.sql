CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

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

CREATE TABLE IF NOT EXISTS lexical_entries (
    id BIGSERIAL PRIMARY KEY,
    normalized_lemma TEXT NOT NULL UNIQUE,
    display_word TEXT NOT NULL,
    active_version_id BIGINT,
    vocabulary_id BIGINT REFERENCES vocabulary(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT lexical_entries_lemma_not_blank CHECK (btrim(normalized_lemma) <> '')
);

CREATE TABLE IF NOT EXISTS lexical_entry_versions (
    id BIGSERIAL PRIMARY KEY,
    lexical_entry_id BIGINT NOT NULL REFERENCES lexical_entries(id) ON DELETE RESTRICT,
    version_number INTEGER NOT NULL,
    candidate_snapshot JSONB NOT NULL,
    evidence_snapshot JSONB NOT NULL,
    evidence_set_hash TEXT NOT NULL,
    dataset_identity JSONB NOT NULL DEFAULT '{}'::jsonb,
    wordnet_identity TEXT,
    model_identity JSONB NOT NULL DEFAULT '{}'::jsonb,
    prompt_identity JSONB NOT NULL DEFAULT '{}'::jsonb,
    policy_identity JSONB NOT NULL DEFAULT '{}'::jsonb,
    schema_identity JSONB NOT NULL DEFAULT '{}'::jsonb,
    packer_identity JSONB NOT NULL DEFAULT '{}'::jsonb,
    validator_identity JSONB NOT NULL DEFAULT '{}'::jsonb,
    inference_identity JSONB NOT NULL DEFAULT '{}'::jsonb,
    candidate_identity TEXT NOT NULL,
    origin TEXT NOT NULL,
    accepted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (lexical_entry_id, version_number),
    UNIQUE (lexical_entry_id, id)
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'lexical_entries_active_version_fk'
    ) THEN
        ALTER TABLE lexical_entries
            ADD CONSTRAINT lexical_entries_active_version_fk
            FOREIGN KEY (active_version_id) REFERENCES lexical_entry_versions(id)
            DEFERRABLE INITIALLY DEFERRED;
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS lexical_entry_one_active_version
    ON lexical_entries(active_version_id)
    WHERE active_version_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS lexical_flags (
    id BIGSERIAL PRIMARY KEY,
    candidate_identity TEXT NOT NULL UNIQUE,
    normalized_lemma TEXT NOT NULL,
    candidate_snapshot JSONB NOT NULL,
    evidence_set_hash TEXT NOT NULL,
    source_identity JSONB NOT NULL DEFAULT '{}'::jsonb,
    lexical_entry_id BIGINT REFERENCES lexical_entries(id) ON DELETE SET NULL,
    lexical_entry_version_id BIGINT REFERENCES lexical_entry_versions(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO schema_migrations(version) VALUES ('002_m0045_lexical_versioning')
ON CONFLICT (version) DO NOTHING;
