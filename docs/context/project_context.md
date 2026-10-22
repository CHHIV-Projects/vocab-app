# Vocab App — Project Context

**Document role:** Current Vocab product context  
**Last reconciled:** 2026-10-22
**Repository:** `/home/chuck/projects/vocab-app`  
**Canonical branch:** `main`  
**Remote:** `CHHIV-Projects/vocab-app` (`origin`)  
**Current Repo Control milestone root:** `docs/milestones/`

## Purpose and product direction

Vocab App is a personal vocabulary-learning application. It helps a learner look up a word, understand its supported meanings, inspect useful linguistic evidence, save a trusted version, and return to saved vocabulary for later practice. Reliability, traceability, completeness, and understandable presentation take precedence over conversational fluency.

The active product uses deterministic lexical evidence and application code. Generative AI is no longer part of the learner lookup path. Wiktionary/Wiktextract source senses are preserved as learner meanings; source order and POS drive compact presentation, while synonyms and etymology remain source-linked.

## Current trustworthy baseline

The current repository is the canonical Linux-hosted checkout at `/home/chuck/projects/vocab-app`, branch `main`, with upstream `origin/main`. At the M001.001 start, HEAD was `e3f2bf4` (`M001.001_vocab_app_governing_structure_and_shared_skill_onboarding_prompt`), equal to the local `origin/main` tracking ref.

The committed application is Python 3.12, Streamlit, and PostgreSQL. Docker Compose defines the application and PostgreSQL 17 services. The application reads a versioned local Wiktionary/Wiktextract SQLite projection; learner lookup does not require WordNet or a generative model. Historical benchmark/research modules remain outside the production image. Runtime configuration is not proof that a currently deployed image matches this source; check deployment identity before browser acceptance.

Repo Control is authoritative for the currently selected repository milestone, lifecycle, and authorization; consult current Coder context rather than inferring active work from this standing document. M001.000 through M001.003 are closed onboarding milestones. Shared procedure is materialized and hash-locked in the repository; Vocab-specific safety and product constraints remain in local overlays.

The local lexical data root is configured through `VOCAB_LEXICAL_ROOT` and mounted read-only in Compose. PostgreSQL connection values are supplied through environment variables. Never copy secret values into documentation, prompts, or logs.

The previous project context recorded `wiktionary-20260901` as the active dataset version. Treat this as last-recorded context only; verify the external `active` pointer and dataset manifest for runtime-specific work.

## Product status and historical arcs

| Arc | Current understanding |
|---|---|
| M001–M003: repository/control foundation, reconnaissance, bounded refactor | Historical work complete for its stated scope; the historical workflow is not authority for new milestones. |
| M004–M004.1: self-hosted runtime, persistence, and external services | M004 established the container/PostgreSQL baseline. M004.1 remains a partial historical closeout because reverse-direction translation was not validated successfully; whether translation remains required is a Product Owner decision. |
| M004.2–M004.3.1: lexical evidence and production dataset | Local Wiktionary/Wiktextract evidence, normalized stable identities, SQLite runtime projection, and supplemental WordNet were implemented and validated for the scoped milestones. |
| M004.4: lexical synthesis | Historical bounded GPT-OSS synthesis and deterministic validation; retained only for research history, not the active product path. |
| M004.5: learner UI and accepted versions | Historical closeout remains PARTIAL as a historical record. M002.000 subsequently completed and Product Owner accepted the isolated desktop/physical-mobile lifecycle baseline, including durable versions and guarded pending Retry/Refresh candidates. |
| M004.6.0–M004.6.13.3: local-AI reliability and sense consolidation | Research and benchmarks are complete. The final M004.6.13.3 gate is **NO-GO** for automatic Qwen3:8B sense consolidation in product v1. Do not treat earlier experiment recommendations as authorization to continue this path. |
| M002.003: deterministic lexical product rebaseline | Active milestone: remove generative AI from the learner path; retain source senses, deterministic presentation, per-sense synonyms, source etymology, U.S. pronunciation and immutable versions. |

See the [M004.5 closeout](../history/milestones/004.5_learner_facing_lexical_ui_and_save_versioning_closeout.md) and [M004.6.13.3 closeout](../history/milestones/004.6.13.3_relation_only_semantic_contract_and_final_qwen_consolidation_exit_gate_closeout.md) for the accepted details and limitations.

## Current incomplete and deferred work

- M004.5 lifecycle acceptance was completed by accepted [M002.000](../milestones/M002.000_learner_lifecycle_baseline_acceptance_closeout.md). Future UI changes still require source-parity and safe-target checks; this acceptance does not authorize production rollout.
- Reassess the M004.1 translation issue only if the Product Owner confirms translation remains in scope.
- The production lexical projection has known exact-lemma indexing/performance work; dataset/index changes require a controlled build and explicit activation, not in-place edits to mounted production data.
- Multiple-choice practice remains an evidenced product direction, but has no current implementation authorization.
- Automatic Qwen sense consolidation is rejected for v1 by the final exit gate. Any alternative requires a new explicit product/architecture decision and fresh acceptance evidence.
- The location or disposition of the uncommitted M004.6.13 V2 contract changes is unverified. Current committed source uses the V1 contract. Do not restore or adopt those changes based on historical closeout descriptions alone.

These items are not a new roadmap or permission to expand an active milestone. The Vocab-specific [canonical parking lot](canonical_parking_lot.md) records their evidence and conditions.

## Deterministic lexical principles

- Wiktionary/Wiktextract evidence, not an LLM, is lexical authority.
- One canonical source sense becomes one learner meaning by default; preserve distinct senses even when glosses look similar.
- Group meanings by POS and source order. Show up to five meanings total initially, include one per represented POS where possible, and do not describe this as popularity ranking.
- Keep synonyms attached to the exact source sense and preserve source etymology boundaries.
- Keep saved accepted versions immutable. A later-dated dataset may offer explicit Refresh; Refresh creates a candidate and never overwrites until saved.
- Benchmarks measure agreement with project references, not linguistic ground truth.

## Evidence and provenance expectations

Lexical source records retain source locators, source hashes, dataset/importer/schema identities, stable sense/evidence IDs, and dataset version. Accepted versions retain candidate/evidence snapshots and identity fields. Dataset creation and activation are controlled, separate operations; the application reports the active dataset identity but does not download or activate updates.

Meaning inspectability exposes linked source meanings from the exact candidate
snapshot. Meaning definitions are formatted from source gloss components; no model
paraphrase or cross-sense semantic consolidation occurs in the active lookup path.

Do not rewrite historical milestone evidence to make current status appear cleaner. The original V2 context, architecture/workflow duplicates, and legacy coding rules are preserved under [docs/history/context](../history/context/README.md). The 58-file legacy milestone corpus is preserved under [docs/history/milestones](../history/milestones/README.md); active Repo Control lifecycle artifacts are under `docs/milestones/`.

## Product safety boundaries

Production PostgreSQL, learner records, mounted lexical datasets, shared-host containers/networks, and external runtime configuration are not disposable test fixtures. Do not mutate them without explicit scope and authorization. Keep unrelated host services and other projects isolated.d.

## Near-term boundary

The current authorized work is selected and reported by Repo Control; this standing context does not grant or imply authorization. Any product milestone requires separate Product Owner scope and authorization.
