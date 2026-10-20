# Vocab App — Project Context

**Document role:** Current Vocab product context  
**Last reconciled:** 2026-10-19
**Repository:** `/home/chuck/projects/vocab-app`  
**Canonical branch:** `main`  
**Remote:** `CHHIV-Projects/vocab-app` (`origin`)  
**Current Repo Control milestone root:** `docs/milestones/`

## Purpose and product direction

Vocab App is a personal vocabulary-learning application. It helps a learner look up a word, understand its supported meanings, inspect useful linguistic evidence, save a trusted version, and return to saved vocabulary for later practice. Reliability, traceability, completeness, and understandable presentation take precedence over conversational fluency.

The product combines deterministic lexical evidence and application code with bounded local-model synthesis. Source data is authoritative; model output is a candidate that must pass deterministic structural and evidence validation before it can be saved.

## Current trustworthy baseline

The current repository is the canonical Linux-hosted checkout at `/home/chuck/projects/vocab-app`, branch `main`, with upstream `origin/main`. At the M001.001 start, HEAD was `e3f2bf4` (`M001.001_vocab_app_governing_structure_and_shared_skill_onboarding_prompt`), equal to the local `origin/main` tracking ref.

The committed application is Python 3.12, Streamlit, and PostgreSQL. Docker Compose defines the application and PostgreSQL 17 services. The application reads a versioned local Wiktionary/Wiktextract SQLite projection, optionally adds NLTK WordNet evidence, and uses an internal Ollama endpoint for GPT-OSS:20b lexical synthesis. Runtime configuration is not proof that a currently deployed image matches this source; check deployment identity before browser acceptance.

Repo Control is authoritative for the currently selected repository milestone, lifecycle, and authorization; consult current Coder context rather than inferring active work from this standing document. M001.000 through M001.003 are closed onboarding milestones. Shared procedure is materialized and hash-locked in the repository; Vocab-specific safety and product constraints remain in local overlays.

The local lexical data root is configured through `VOCAB_LEXICAL_ROOT` and mounted read-only in Compose. The writable synthesis cache and failure diagnostics use `VOCAB_RUNTIME_ROOT`. PostgreSQL connection values are supplied through environment variables. Never copy secret values into documentation, prompts, or logs.

The previous project context recorded `wiktionary-20260901` as the active dataset version. Treat this as last-recorded context only; verify the external `active` pointer and dataset manifest for runtime-specific work.

## Product status and historical arcs

| Arc | Current understanding |
|---|---|
| M001–M003: repository/control foundation, reconnaissance, bounded refactor | Historical work complete for its stated scope; the historical workflow is not authority for new milestones. |
| M004–M004.1: self-hosted runtime, persistence, and external services | M004 established the container/PostgreSQL baseline. M004.1 remains a partial historical closeout because reverse-direction translation was not validated successfully; whether translation remains required is a Product Owner decision. |
| M004.2–M004.3.1: lexical evidence and production dataset | Local Wiktionary/Wiktextract evidence, normalized stable identities, SQLite runtime projection, and supplemental WordNet were implemented and validated for the scoped milestones. |
| M004.4: lexical synthesis | Bounded GPT-OSS synthesis and deterministic validation were implemented; representative examples passed, not every possible inference. |
| M004.5: learner UI and accepted versions | Substantial implementation exists, including Save, Retry, Refresh, Flag, source details, and accepted-version persistence. The closeout remains PARTIAL: full desktop/mobile browser lifecycle acceptance and a Product Owner browser retest remain outstanding. |
| M004.6.0–M004.6.13.3: local-AI reliability and sense consolidation | Research and benchmarks are complete. The final M004.6.13.3 gate is **NO-GO** for automatic Qwen3:8B sense consolidation in product v1. Do not treat earlier experiment recommendations as authorization to continue this path. |

See the [M004.5 closeout](../history/milestones/004.5_learner_facing_lexical_ui_and_save_versioning_closeout.md) and [M004.6.13.3 closeout](../history/milestones/004.6.13.3_relation_only_semantic_contract_and_final_qwen_consolidation_exit_gate_closeout.md) for the accepted details and limitations.

## Current incomplete and deferred work

- Complete M004.5 desktop/mobile browser and lifecycle acceptance only under a bounded, Product Owner-approved milestone. Verify that deployed code matches the reviewed source before testing real Save/Retry/Refresh/Flag behavior.
- Reassess the M004.1 translation issue only if the Product Owner confirms translation remains in scope.
- The production lexical projection has known exact-lemma indexing/performance work; dataset/index changes require a controlled build and explicit activation, not in-place edits to mounted production data.
- Multiple-choice practice remains an evidenced product direction, but has no current implementation authorization.
- Automatic Qwen sense consolidation is rejected for v1 by the final exit gate. Any alternative requires a new explicit product/architecture decision and fresh acceptance evidence.
- The location or disposition of the uncommitted M004.6.13 V2 contract changes is unverified. Current committed source uses the V1 contract. Do not restore or adopt those changes based on historical closeout descriptions alone.

These items are not a new roadmap or permission to expand an active milestone. The Vocab-specific [canonical parking lot](canonical_parking_lot.md) records their evidence and conditions.

## Local-AI principles

- Wiktionary/Wiktextract evidence, not an LLM, is lexical authority.
- WordNet is supplemental and must not be assumed equivalent to Wiktionary sense structure.
- Use deterministic code for evidence identity, coverage, schema validation, persistence, versioning, and state transitions.
- Keep model tasks bounded; preserve explicit model, prompt, policy, schema, and evidence identity where applicable.
- Reject malformed or unsupported output rather than silently fabricating missing facts.
- Cache only validated results; retain failure diagnostics within the configured runtime boundary.
- Benchmarks measure agreement with project references, not linguistic ground truth.

## Evidence and provenance expectations

Lexical source records retain source locators, source hashes, dataset/importer/schema identities, stable sense/evidence IDs, and dataset version. Synthesis consumes a deterministic projection of this evidence; accepted versions retain candidate/evidence snapshots and identity fields. Refresh is an explicit comparison against current evidence. Dataset creation and activation are controlled, separate operations.

Do not rewrite historical milestone evidence to make current status appear cleaner. The original V2 context, architecture/workflow duplicates, and legacy coding rules are preserved under [docs/history/context](../history/context/README.md). The 58-file legacy milestone corpus is preserved under [docs/history/milestones](../history/milestones/README.md); active Repo Control lifecycle artifacts are under `docs/milestones/`.

## Product safety boundaries

Production PostgreSQL, learner records, mounted lexical datasets, shared-host containers/networks, private Ollama services, and external runtime configuration are not disposable test fixtures. Do not mutate them without explicit scope and authorization. Keep unrelated host services and other projects isolated.

## Near-term boundary

The current authorized work is selected and reported by Repo Control; this standing context does not grant or imply authorization. Any product milestone, including possible M004.5 browser acceptance, requires separate Product Owner scope and authorization.
