-- M004.6.10.1: correct the source-sense-pair ordering CHECK constraint to use an explicit,
-- deterministic collation ("C") instead of the database's locale-aware default collation.
--
-- Root cause: Python's canonical pair ordering (SensePair.create's `sorted((first, second))`,
-- i.e. Unicode code-point ordering) does not always agree with PostgreSQL's default
-- locale-aware text `<` comparison (observed under `en_US.utf8`) for real Wiktionary source
-- sense IDs that contain punctuation such as `[`, `]`, `'` (e.g. list-like IDs produced by
-- upstream Wikidata/category linkage). This was never exercised before because no earlier
-- test or live word triggered that exact character combination.
--
-- Fix: replace the constraint with an explicitly `COLLATE "C"` comparison, which matches
-- Python's Unicode/code-point ordering exactly (verified against the full characterized
-- corpus of 285,919 same-entry sense pairs: 0 disagreements under "C", versus 67,349
-- disagreements under the database's default collation).
--
-- This migration is purely additive: it does not edit 003_m004610_consolidation_persistence.sql,
-- does not touch any other table/column, and does not change any identity algorithm. No
-- existing `lexical_pair_judgments` rows exist in any real deployment at the time of this
-- correction (verified during reconnaissance), so no data rewrite is required.

ALTER TABLE lexical_pair_judgments
    DROP CONSTRAINT lexical_pair_judgments_source_ids_ordered;

ALTER TABLE lexical_pair_judgments
    ADD CONSTRAINT lexical_pair_judgments_source_ids_ordered CHECK (
        btrim(source_sense_id_a) <> '' AND btrim(source_sense_id_b) <> ''
        AND (source_sense_id_a COLLATE "C") < (source_sense_id_b COLLATE "C")
    );

INSERT INTO schema_migrations(version) VALUES ('004_m004610_1_pair_ordering_collation_correction')
ON CONFLICT (version) DO NOTHING;
