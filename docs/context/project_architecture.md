# Vocab App — Project Architecture

**Document role:** Current technical architecture reconstructed from committed source and runtime manifests  
**Last inspected:** 2026-10-22
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
    `-- optional translation/audio providers

Optional app capabilities:
    `-- translation provider and user-requested gTTS playback
```

`compose.yaml` defines PostgreSQL 17, the application health checks, mounted data paths, and LAN port binding. `Dockerfile` builds a Python 3.12 image and runs `streamlit run app.py` as the non-root `vocab` user. These files describe intended deployment configuration, not proof that the live deployment currently runs the same source revision.

Streamlit is the implemented UI boundary, not a locked permanent frontend. A future replacement requires a separately scoped architecture decision.

## 2. Application components and data flow

| Component | Responsibility |
|---|---|
| `app.py` | Streamlit page, session state, user actions, presentation, audio and translation controls; creates cached PostgreSQL and lexical workflow resources. |
| `vocab_workflow.py` | Framework-independent deterministic source lookup, source-sense/POS presentation, sense-bound synonyms, source-derived etymology, immutable saved-state reconciliation, Save, explicit newer-dataset Refresh, Flag, and provenance projections. |
| `vocab_lexical_engine.py` | Canonical Wiktextract normalization, stable source/sense identities, SQLite projection schema and deterministic lexical lookup; reads the active version pointer from the configured lexical root. |
| `vocab_synthesis.py` | Historical M004/M002 model-evaluation implementation retained for isolated benchmark/research compatibility; not copied into the production image or imported by the learner application. |
| `vocab_persistence.py` | PostgreSQL operational persistence and accepted-version/flag workflow. It also retains a Google Sheets adapter for legacy compatibility; current Compose wiring constructs `PostgresPersistence`. |
| `vocab_migrations.py` | Ordered SQL migration runner protected by a PostgreSQL advisory transaction lock and `schema_migrations`. |
| `vocab_domain.py` | Practice selection/scoring retained for compatible non-lexical behavior. |
| `vocab_nlp.py`, `vocab_dictionary.py` | Existing synonym and WordNet helpers; WordNet output is supplemental evidence and is not used to rank learner meanings. |
| `vocab_translation.py` | Optional translation-provider boundary. Historical M004.1 validation reported a reverse-direction provider failure. |
| `vocab_consolidation*.py` | Experimental pairwise semantic-consolidation domain, Qwen provider, resumable orchestration, topology, and persistence; not wired into the learner-facing `app.py` workflow. |

The learner lexical path is:

```text
exact word lookup
  -> active local SQLite Wiktionary/Wiktextract projection
  -> one learner meaning per canonical source sense
  -> deterministic source-order Core/Additional presentation, grouped by POS
  -> sense-bound source synonyms, source etymology, U.S. pronunciation
  -> source-derived candidate shown to learner
  -> explicit Save
  -> PostgreSQL accepted version + snapshots + active-version pointer
```

Search for an already-saved word first reconciles against PostgreSQL. Its immutable snapshot is shown by default and is never relinked to the active dataset. Refresh is offered only when a later-dated installed dataset contains source senses for the word. Refresh builds a pending source-derived candidate; only explicit Save creates another immutable version and advances the active pointer.

Every Dictionary rerun uses the workflow's single reconciliation boundary. Accepted
versions remain PostgreSQL authority; a pending Refresh candidate survives only
while it is bound to the same normalized query and accepted base version. A changed
base or different query invalidates it. Same-query unsaved Search candidates remain
stable across ordinary reruns; explicit Search clears them.

Meaning provenance is a read-only display projection: each initial/additional meaning's
canonical `source_sense_ids` resolves only within that candidate's `evidence_snapshot`.
Source gloss components are formatted as one definition for their canonical sense;
distinct source senses are never semantically combined. Unresolved/cross-POS
references surface an error rather than borrowing unrelated evidence. Previously
accepted AI-era snapshots remain historical facts and are displayed as saved, not
rewritten as source-derived output.

The initial display contains up to five meanings total, with one from each
represented POS where possible, then remaining slots filled by deterministic source
order. This is a compact presentation policy, not a popularity claim. Labels remain
visible but do not influence ordering.

## 3. Lexical evidence and authority

The primary source is English Wiktionary extracted with Wiktextract. Controlled dataset builds normalize source records into canonical JSONL and an SQLite projection. The versioned dataset is selected by an `active` pointer under `VOCAB_LEXICAL_ROOT`; deployment mounts the data read-only. `vocab_lexical_engine.py` stores entries, senses, forms, sounds, relations, and an FTS5 table. Exact normalized-lemma indexing has a known performance limitation recorded in project context; don't mutate the production projection in place.

Normalized records retain dataset/importer/schema versions, source locators and hashes, and stable source-derived IDs. The general lexical lookup retains optional WordNet support for other callers, but the learner workflow explicitly disables it and does not use it to rank meanings.

## 4. Historical model research boundary

The learner application has no Ollama provider, generation request, model prompt,
model cache, or model runtime configuration. The production Docker image omits
`vocab_synthesis.py`, and Compose no longer joins the private local-AI network.
Historical benchmark scripts and their research module remain in the repository
for reproducibility, but they are outside the production image and learner runtime.

Synonyms remain linked to the exact canonical sense and source relation. Etymology
wording and templates are retained from source records, with entry identity and
boundaries preserved.

## 5. PostgreSQL persistence and migrations

The app constructs `PostgresPersistence.from_env()` using `VOCAB_DB_HOST`, `VOCAB_DB_PORT`, `VOCAB_DB_NAME`, `VOCAB_DB_USER`, and `VOCAB_DB_PASSWORD`. Do not expose credential values.

After migrations commit, the long-lived application connection uses autocommit so
ordinary reads do not leave an implicit transaction open. Accepted-version Save
retains an explicit transaction for the entry, version, active pointer, and practice
projection; these commit together before the verification read. A transaction
nested inside a pre-existing implicit read transaction would only release a
savepoint, not make the Save durable.

After a successful Save, the Streamlit page reruns to reload authoritative saved
state and regenerate action controls, rather than retaining pre-Save button states.

The schema retains a lightweight `vocabulary` row for existing practice/count behavior and adds:

- `lexical_entries`: normalized lemma and active accepted-version pointer;
- `lexical_entry_versions`: immutable version number, candidate and evidence JSONB snapshots, hashes, source/model/prompt/policy/schema/validator identities, origin, and acceptance time. Legacy model/prompt columns remain for historical compatibility; new deterministic candidates leave those identities empty;
- `lexical_flags`: flagged candidate snapshot and identity;
- `lexical_consolidation_jobs`, `lexical_pair_judgments`, and `lexical_consolidation_containers`: separate experimental pairwise research persistence.

The SQL source is `db/init/001_create_vocabulary.sql` plus ordered files in `db/migrations/`. Do not infer runtime data contents from migrations; inspect the target database only under explicit authorization.

## 6. Optional external services

- **Translation:** Optional provider in `vocab_translation.py`; M004.1's reverse-language validation remains partial.
- **Audio:** User-requested gTTS playback in `app.py` makes an external network request. It is not a source of lexical truth.
- **NLTK resources:** WordNet remains available for compatible helper behavior. The learner lookup explicitly disables WordNet and never uses it to rank meanings; Compose mounts configured resources read-only.

External translation/audio provider success is not equivalent to lexical evidence.
Provider failures remain visible rather than producing success-shaped fallbacks.

## 7. Accepted-entry and learner authority

The candidate is not durable accepted vocabulary until the learner explicitly saves it and PostgreSQL confirms the persisted version. Previous accepted versions and their source snapshots remain auditable. The active pointer, not Streamlit session state, determines whether a word is saved. `vocab_workflow.py` reconciles that state before deriving available actions.

The existing practice projection and counts are intentionally retained. Rich lexical entries do not automatically rewrite the legacy practice representation except through the explicit persistence projection on Save.

## 8. Experimental and rejected paths

Automatic Qwen3:8B pairwise sense consolidation is **NO-GO for product v1** under the final M004.6.13.3 exit gate. Current production `vocab_consolidation.py` uses the V1 pair-judgment contract; the previously described V2 changes are not present in this committed baseline. Pairwise tables/modules are not evidence that automatic merging is enabled or accepted. Preserve source senses; don't activate, tune, or restore consolidation without a new approved decision and evidence.

Embeddings, semantic candidate reduction, model/runtime changes, frontend replacement, and automatic dataset refresh are not current architecture decisions.

## 9. Testing and operational boundaries

Tests live under `tests/` and use Python `unittest`, including offline domain/provider/workflow tests and isolated PostgreSQL tests. Benchmark tooling under `tools/benchmarks/` is historical research, not a production request path. Use targeted tests appropriate to a change; do not connect to production services merely to validate documentation.

Production PostgreSQL, learner data, the read-only lexical dataset and WordNet mounts, shared Docker networks, and other host services are separately controlled boundaries. Do not delete, mutate, rebuild, chmod, or activate these resources without explicit authorization.
