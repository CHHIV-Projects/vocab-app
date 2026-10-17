# Vocab App — Project Architecture

**Document role:** Current technical architecture reconstructed from committed source and runtime manifests  
**Last inspected:** 2026-10-17  
**Repository:** `/home/chuck/projects/vocab-app`

## 1. Runtime topology

```text
Learner browser
    |
    v
Streamlit application (Docker service: vocab-app)
    |-- PostgreSQL (Docker service: vocab-db; persistent named volume)
    |-- versioned lexical SQLite projection (host mount, read-only)
    |-- NLTK/WordNet resources (host mount, read-only)
    |-- application runtime root (host mount, writable cache/diagnostics)
    `-- Ollama endpoint on the private local-ai Docker network

Optional app capabilities:
    `-- translation provider and gTTS network calls
```

`compose.yaml` defines PostgreSQL 17, the application health checks, mounted data paths, and LAN port binding. `Dockerfile` builds a Python 3.12 image and runs `streamlit run app.py` as the non-root `vocab` user. These files describe intended deployment configuration, not proof that the live deployment currently runs the same source revision.

Streamlit is the implemented UI boundary, not a locked permanent frontend. A future replacement requires a separately scoped architecture decision.

## 2. Application components and data flow

| Component | Responsibility |
|---|---|
| `app.py` | Streamlit page, session state, user actions, presentation, audio and translation controls; creates cached PostgreSQL and lexical workflow resources. |
| `vocab_workflow.py` | Framework-independent learner lifecycle: lookup/synthesis, authoritative saved-state reconciliation, Save, Retry from exact stored evidence, Refresh on changed evidence, Flag, deterministic synonym enrichment, evidence-bound etymology validation, and display projections. |
| `vocab_lexical_engine.py` | Canonical Wiktextract normalization, stable source/sense identities, SQLite projection schema and deterministic lexical lookup; reads the active version pointer from the configured lexical root. |
| `vocab_synthesis.py` | Frozen evidence projection and packing; Ollama provider; structured synthesis contract; deterministic fact/coverage/identity validation; validated-result caching and bounded failure diagnostics. |
| `vocab_persistence.py` | PostgreSQL operational persistence and accepted-version/flag workflow. It also retains a Google Sheets adapter for legacy compatibility; current Compose wiring constructs `PostgresPersistence`. |
| `vocab_migrations.py` | Ordered SQL migration runner protected by a PostgreSQL advisory transaction lock and `schema_migrations`. |
| `vocab_domain.py`, `vocab_nlp.py`, `vocab_dictionary.py` | Practice selection/scoring and existing synonym/WordNet helper behavior. WordNet helper output is separate supplemental evidence. |
| `vocab_translation.py` | Optional translation-provider boundary. Historical M004.1 validation reported a reverse-direction provider failure. |
| `vocab_consolidation*.py` | Experimental pairwise semantic-consolidation domain, Qwen provider, resumable orchestration, topology, and persistence; not wired into the learner-facing `app.py` workflow. |

The learner lexical path is:

```text
exact word lookup
  -> active local SQLite Wiktionary/Wiktextract projection
  -> optional separate WordNet evidence
  -> deterministic source-complete evidence projection and identity
  -> bounded Ollama GPT-OSS:20b structured synthesis
  -> deterministic schema, evidence-reference, and coverage validation
  -> candidate shown to learner
  -> explicit Save
  -> PostgreSQL accepted version + snapshots + active-version pointer
```

Search for an already-saved word first reconciles against PostgreSQL. Retry uses the saved evidence snapshot after verifying its hash; it does not silently switch to current lexical data. Refresh is enabled only when the full current evidence identity differs. Save validates the candidate, writes versioned data transactionally, and verifies the durable active pointer/projection before presenting success.

## 3. Lexical evidence and authority

The primary source is English Wiktionary extracted with Wiktextract. Controlled dataset builds normalize source records into canonical JSONL and an SQLite projection. The versioned dataset is selected by an `active` pointer under `VOCAB_LEXICAL_ROOT`; deployment mounts the data read-only. `vocab_lexical_engine.py` stores entries, senses, forms, sounds, relations, and an FTS5 table. Exact normalized-lemma indexing has a known performance limitation recorded in project context; don't mutate the production projection in place.

Normalized records retain dataset/importer/schema versions, source locators and hashes, and stable source-derived IDs. WordNet/NLTK evidence is supplementary, carries a resource identity where available, and is not collapsed into Wiktionary sense authority. Missing evidence stays missing.

## 4. Synthesis and local-model boundary

`OllamaProvider` in `vocab_synthesis.py` calls the configured `VOCAB_OLLAMA_URL` (Compose currently supplies `http://ollama:11434`) using a structured schema and bounded decoding options. The baseline synthesis model is GPT-OSS:20b. Code creates the required evidence aliases and validates the model's grouping, coverage, evidence references, and deterministic projections before a result is accepted or cached. The model does not own source facts, stable IDs, POS topology, persistence, or acceptance.

`SynthesisRuntime` stores synthesis cache and failure diagnostics beneath `VOCAB_RUNTIME_ROOT` (Compose currently supplies `/vocab-runtime`). This is a writable runtime mount, not the source lexical dataset. Cache identity includes evidence and synthesis configuration; failed or invalid output is not a valid learner candidate.

Etymology summaries are a separate bounded generation over supplied source etymology evidence; the application validates evidence IDs before attaching the summary. Synonyms are selected deterministically from source relation evidence.

## 5. PostgreSQL persistence and migrations

The app constructs `PostgresPersistence.from_env()` using `VOCAB_DB_HOST`, `VOCAB_DB_PORT`, `VOCAB_DB_NAME`, `VOCAB_DB_USER`, and `VOCAB_DB_PASSWORD`. Do not expose credential values.

The schema retains a lightweight `vocabulary` row for existing practice/count behavior and adds:

- `lexical_entries`: normalized lemma and active accepted-version pointer;
- `lexical_entry_versions`: immutable version number, candidate and evidence JSONB snapshots, hashes, source/model/prompt/policy/schema/validator identities, origin, and acceptance time;
- `lexical_flags`: flagged candidate snapshot and identity;
- `lexical_consolidation_jobs`, `lexical_pair_judgments`, and `lexical_consolidation_containers`: separate experimental pairwise research persistence.

The SQL source is `db/init/001_create_vocabulary.sql` plus ordered files in `db/migrations/`. Do not infer runtime data contents from migrations; inspect the target database only under explicit authorization.

## 6. Optional external services

- **Ollama:** Private internal service boundary for local synthesis. No direct public model-service exposure is intended by Compose.
- **Translation:** Optional provider in `vocab_translation.py`; M004.1's reverse-language validation remains partial.
- **Audio:** gTTS in `app.py` makes an external network request. It is not a source of lexical truth.
- **NLTK resources:** The app checks WordNet resources at startup and may invoke NLTK downloads if missing. Compose mounts configured NLTK data read-only; runtime behavior must be verified before altering host resources.

External provider success is not equivalent to lexical validation; failures must remain visible rather than produce success-shaped fallbacks.

## 7. Accepted-entry and learner authority

The candidate is not durable accepted vocabulary until the learner explicitly saves it and PostgreSQL confirms the persisted version. Previous accepted versions and their source snapshots remain auditable. The active pointer, not Streamlit session state, determines whether a word is saved. `vocab_workflow.py` reconciles that state before deriving available actions.

The existing practice projection and counts are intentionally retained. Rich lexical entries do not automatically rewrite the legacy practice representation except through the explicit persistence projection on Save.

## 8. Experimental and rejected paths

Automatic Qwen3:8B pairwise sense consolidation is **NO-GO for product v1** under the final M004.6.13.3 exit gate. Current production `vocab_consolidation.py` uses the V1 pair-judgment contract; the previously described V2 changes are not present in this committed baseline. Pairwise tables/modules are not evidence that automatic merging is enabled or accepted. Preserve source senses; don't activate, tune, or restore consolidation without a new approved decision and evidence.

Embeddings, semantic candidate reduction, model/runtime changes, frontend replacement, and automatic dataset refresh are not current architecture decisions.

## 9. Testing and operational boundaries

Tests live under `tests/` and use Python `unittest`, including offline domain/provider/workflow tests and isolated PostgreSQL tests. Benchmark tooling under `tools/benchmarks/` is historical research, not a production request path. Use targeted tests appropriate to a change; do not connect to production services merely to validate documentation.

Production PostgreSQL, learner data, the read-only lexical dataset and WordNet mounts, runtime cache/diagnostics, shared Docker networks, and other host services are separately controlled boundaries. Do not delete, mutate, rebuild, chmod, or activate these resources without explicit authorization.
