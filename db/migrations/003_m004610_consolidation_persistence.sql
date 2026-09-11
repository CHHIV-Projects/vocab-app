CREATE TABLE IF NOT EXISTS lexical_consolidation_jobs (
    id BIGSERIAL PRIMARY KEY,
    consolidation_identity TEXT NOT NULL UNIQUE,
    normalized_lemma TEXT NOT NULL,
    evidence_set_hash TEXT NOT NULL,
    lexical_dataset_identity JSONB NOT NULL DEFAULT '{}'::jsonb,
    partition_identity TEXT NOT NULL,
    partition_manifest JSONB NOT NULL,
    pair_judgment_contract_version TEXT NOT NULL,
    semantic_model_identity JSONB NOT NULL,
    semantic_options_identity JSONB NOT NULL,
    topology_contract_version TEXT NOT NULL,
    container_contract_version TEXT NOT NULL,
    expected_pair_count INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'created',
    topology_identity TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    CONSTRAINT lexical_consolidation_jobs_lemma_not_blank CHECK (btrim(normalized_lemma) <> ''),
    CONSTRAINT lexical_consolidation_jobs_expected_pair_count_nonnegative CHECK (expected_pair_count >= 0),
    CONSTRAINT lexical_consolidation_jobs_status CHECK (status IN (
        'created', 'running', 'failed_retryable', 'failed_terminal', 'topology_validated'
    )),
    CONSTRAINT lexical_consolidation_jobs_topology_state CHECK (
        (status = 'topology_validated' AND topology_identity IS NOT NULL AND completed_at IS NOT NULL)
        OR
        (status <> 'topology_validated' AND topology_identity IS NULL AND completed_at IS NULL)
    )
);

CREATE INDEX IF NOT EXISTS lexical_consolidation_jobs_resume_index
    ON lexical_consolidation_jobs (status, created_at)
    WHERE status <> 'topology_validated';

CREATE TABLE IF NOT EXISTS lexical_pair_judgments (
    id BIGSERIAL PRIMARY KEY,
    consolidation_job_id BIGINT NOT NULL REFERENCES lexical_consolidation_jobs(id) ON DELETE RESTRICT,
    partition_identity TEXT NOT NULL,
    logical_pair_id TEXT NOT NULL,
    source_sense_id_a TEXT NOT NULL,
    source_sense_id_b TEXT NOT NULL,
    pair_judgment_identity TEXT NOT NULL,
    pair_judgment_contract_version TEXT NOT NULL,
    semantic_model_identity JSONB NOT NULL,
    semantic_options_identity JSONB NOT NULL,
    evidence_set_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    decision TEXT,
    reason TEXT,
    validated_result_identity TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    lease_owner TEXT,
    lease_acquired_at TIMESTAMPTZ,
    lease_expires_at TIMESTAMPTZ,
    last_error_classification TEXT,
    last_error_summary TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    CONSTRAINT lexical_pair_judgments_source_ids_ordered CHECK (
        btrim(source_sense_id_a) <> '' AND btrim(source_sense_id_b) <> ''
        AND source_sense_id_a < source_sense_id_b
    ),
    CONSTRAINT lexical_pair_judgments_status CHECK (status IN (
        'pending', 'running', 'succeeded_validated', 'failed_retryable', 'failed_terminal'
    )),
    CONSTRAINT lexical_pair_judgments_decision CHECK (
        decision IS NULL OR decision IN ('merge', 'keep_separate', 'uncertain')
    ),
    CONSTRAINT lexical_pair_judgments_reason CHECK (
        reason IS NULL OR reason IN (
            'paraphrase_or_duplicate', 'contextual_variant', 'specialized_subsense',
            'broader_or_narrower', 'related_but_distinct', 'materially_different',
            'insufficient_evidence'
        )
    ),
    CONSTRAINT lexical_pair_judgments_result_state CHECK (
        (status = 'succeeded_validated'
            AND decision IS NOT NULL
            AND reason IS NOT NULL
            AND validated_result_identity IS NOT NULL
            AND completed_at IS NOT NULL)
        OR
        (status <> 'succeeded_validated'
            AND decision IS NULL
            AND reason IS NULL
            AND validated_result_identity IS NULL
            AND completed_at IS NULL)
    ),
    CONSTRAINT lexical_pair_judgments_lease_state CHECK (
        (status = 'running' AND lease_owner IS NOT NULL AND lease_acquired_at IS NOT NULL AND lease_expires_at IS NOT NULL)
        OR
        (status <> 'running' AND lease_owner IS NULL AND lease_acquired_at IS NULL AND lease_expires_at IS NULL)
    ),
    CONSTRAINT lexical_pair_judgments_job_pair_unique UNIQUE (consolidation_job_id, logical_pair_id),
    CONSTRAINT lexical_pair_judgments_job_judgment_unique UNIQUE (consolidation_job_id, pair_judgment_identity)
);

CREATE INDEX IF NOT EXISTS lexical_pair_judgments_resume_index
    ON lexical_pair_judgments (consolidation_job_id, status, lease_expires_at);

CREATE TABLE IF NOT EXISTS lexical_consolidation_containers (
    id BIGSERIAL PRIMARY KEY,
    consolidation_job_id BIGINT NOT NULL REFERENCES lexical_consolidation_jobs(id) ON DELETE RESTRICT,
    partition_identity TEXT NOT NULL,
    topology_identity TEXT NOT NULL,
    container_identity TEXT NOT NULL,
    member_source_sense_ids JSONB NOT NULL,
    container_contract_version TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT lexical_consolidation_containers_members_array CHECK (jsonb_typeof(member_source_sense_ids) = 'array'),
    CONSTRAINT lexical_consolidation_containers_job_container_unique UNIQUE (consolidation_job_id, container_identity),
    CONSTRAINT lexical_consolidation_containers_job_topology_members_unique UNIQUE (
        consolidation_job_id, topology_identity, member_source_sense_ids
    )
);

CREATE INDEX IF NOT EXISTS lexical_consolidation_containers_job_topology_index
    ON lexical_consolidation_containers (consolidation_job_id, topology_identity);

INSERT INTO schema_migrations(version) VALUES ('003_m004610_consolidation_persistence')
ON CONFLICT (version) DO NOTHING;
