# Vocab App Milestone 002 Closeout

## 1. Executive conclusion

Observed fact: the canonical Vocab App on `main` is a single-file Streamlit application in `app.py` with direct Google Sheets persistence and multiple external services for dictionary, translation, audio, and NLP. The product is not currently separated into a clean layered architecture.

Observed fact: the data and behavior are tightly coupled in the same file. `app.py` contains UI rendering, session-state logic, dictionary lookup, audio/audio-generation logic, synonym logic, persistence, and quiz/flashcard behavior in a single place.

Observed fact: there is no obvious canonical Python test suite on the current `main` branch.

Interpretation: the most reasonable next step is not direct product implementation of multiple-choice, database migration, or Streamlit replacement. The safest next milestone is a narrow preparatory step that reduces risk by separating business logic from UI and persistence, while preserving current behavior. This fits a small bounded refactor or a robust containerized baseline before feature implementation.

Recommendation: the best M003 direction is a bounded refactor or current-app container baseline, depending on whether the Product Owner wants architectural risk reduction or deployment readiness first. Based on the current evidence, a small bounded refactor is the more defensible choice if the goal is to prepare for multiple choice and future database migration without prematurely rewriting the app.

## 2. Starting repository evidence

Observed facts:

- Repository path: `/home/chuck/projects/vocab-app`
- Branch: `main`
- HEAD: `9056811bdb6afc0ad698205180c5b7564f1d2ec0`
- Upstream: `origin/main`
- Ahead/behind: `0       0`
- Working tree: clean at the time of reconnaissance start (`git status --short` produced no output)
- Initial starting command evidence:

```bash
cd /home/chuck/projects/vocab-app
pwd
git branch --show-current
git rev-parse HEAD
git status --short
git remote -v
git rev-parse @{upstream} 2>/dev/null || true
git rev-list --left-right --count HEAD...@{upstream} 2>/dev/null || true
git log -5 --oneline --decorate
```

## 3. Canonical application inventory

Observed files in canonical `main`:

- `app.py`: active application entry point and primary logic container.
- `requirements.txt`: current dependency set.
- `.gitignore`: generated-state and secret exclusions.
- `.aiderignore`: credential and local-AI state exclusions.
- `architecture/vocab_repo_control_integration_roadmap_v1.md`: project roadmap.
- `docs/context/*.md`: controlling project workflow and role documents.
- `milestones/*.md`: milestone prompts and closeouts.

Application observations:

- `app.py` is the active execution path.
- There are no canonical test files in the repo tree at the time of reconnaissance.
- The app is a Streamlit-based vocabulary tracker, not a multi-module Python service.
- There are no obvious non-application operational files such as Dockerfiles or Compose files on canonical `main`.

Likely dead or historical files are preserved only in archive/test branches, not in canonical `main`.

## 4. Current runtime flow

Observed flow derived from `app.py`:

1. Application starts as a Streamlit app by module execution.
2. `st.set_page_config(...)` initializes UI metadata.
3. The file performs global initialization of session state such as `active_search`, `flashcards`, `current_card_idx`, and `logs`.
4. `get_sheet()` creates a Google Sheets client:
   - it tries `service_account.json` in the working directory;
   - otherwise it reads `st.secrets["gcp_service_account"]`.
5. `get_mw_data(query)` fetches Merriam-Webster data using `st.secrets["merriam_key"]`.
6. A synonym helper calls `wordnet` via NLTK and computes candidate synonyms.
7. The app renders three tabs: Dictionary, Translator, and Practice.
8. Dictionary interactions run search, fetch definition data, present synonyms, and allow word save.
9. The save path appends a row to the Google Sheet with fields including word, definition, part of speech, date, and score count.
10. Practice mode reads all records from the sheet, sorts them by a `Count` field, and presents flashcards.
11. Missed vs. got-it actions call `update_score(...)`, which searches the sheet and updates the score column.

Human-readable flow:

`browser/UI → Streamlit app → dictionary API + Google Sheets + NLP libraries → session state + sheet writes`

## 5. Streamlit coupling

Observed coupling:

- `app.py` imports `streamlit` and `streamlit.components.v1` directly.
- Most business behaviors execute directly in the Streamlit page code.
- `st.session_state` is used for search state, flashcards, score state, logs, and UI navigation.
- UI rendering and data access are mixed throughout the file.
- Quiz/flashcard logic is not separated from the UI logic.
- Synonym behavior is computed in the same flow as dictionary results and UI button handling.
- Pronunciation/audio generation is triggered directly from the UI render path.
- Secrets are read directly from `st.secrets` without a boundary object or config adapter.
- A cache resource is used for the Google Sheets client, but the app does not isolate a clean persistence interface.

Classification:

- UI-specific: Streamlit rendering, page config, tabs, buttons, sidebar history, alerts, progress, forms.
- Framework-independent: some helper logic like `get_nltk_root`, `get_synonyms_nltk`, and `get_audio_bytes` are conceptually separable but still sit in the same module.
- Mixed/coupled: dictionary-fetch logic, persistence, quiz flow, scoring, and synonym processing are all embedded in UI code.

Implication: a future Streamlit replacement will require boundary extraction and not just framework swapping.

## 6. Google Sheets integration

Observed facts:

- `app.py` imports `gspread` and `oauth2client.service_account.ServiceAccountCredentials`.
- Authentication is via `service_account.json` if present; otherwise `st.secrets["gcp_service_account"]`.
- `get_sheet()` calls `client.open("VocabApp_DB").sheet1`.
- The app expects a sheet with data rows used for vocabulary and scoring.
- Read paths include:
  - `sheet.get_all_records()` for history and flashcards;
  - `sheet.col_values(1)` when checking duplicates;
  - `sheet.find(word)` during score updates.
- Write paths include:
  - `sheet.append_row([...])` when saving a word;
  - `sheet.update_cell(...)` when updating score counts.
- Data shape appears to include word, definition, part of speech, source, date, and score count.
- Error handling is mostly `try/except` with `print(...)` or UI error messages.
- There is no obvious retry or transactional structure.

Credential boundary:

- No credentials were opened or reproduced during reconnaissance.
- The app is designed to load secrets either from a local file or Streamlit secrets, which means the credential boundary is present in the runtime environment and not in the Git repo.

Interpretation: the actual persistence boundary is hard-bound to Google Sheets and therefore the future database migration must preserve the real add/read/update semantics, not only the visible vocabulary fields.

## 7. Current logical vocabulary model

Observed persisted fields from `app.py` and the sheet operations:

- `Word`
- `Definition`
- `Part of Speech` or equivalent position metadata
- source metadata (`Auto-Generated` in save flow)
- date/timestamp
- `Count` / score field used in practice sessions

Observed transient values:

- `active_search` in `st.session_state`
- `flashcards`
- `current_card_idx`
- `card_flipped`
- `balloons_shown`
- `logs`

Interpretation:

- The current logical model is a simple vocabulary record with a score counter, a date, and a dictionary definition.
- The per-user session state is not a durable database model but a UX mechanism.
- Any database migration should preserve the user-visible vocabulary semantics and scoring behavior rather than just moving the raw cells.

## 8. Current quiz/test workflow

Observed behavior from the Practice tab in `app.py`:

- User clicks `Start Session`.
- `sheet.get_all_records()` loads the saved words.
- Rows are sorted by the `Count` field and the first 10 are selected.
- The entries are shuffled.
- The user sees the word and can click `Flip Card` to reveal the definition.
- The user then indicates whether they got it correct or missed it.
- `update_score(word, success)` does a `sheet.find(word)` and updates the `Count` column.
- The session advances to the next card.
- Completion shows balloons and allows starting a new session.

Deterministic current-state behavior:

- It is not a multiple-choice quiz.
- The app uses a simple flashcard pattern rather than a question/answer engine with distractors.
- Correctness is a user-driven binary action tied to score updates.
- The same sheet row is mutated on success/failure.

## 9. Multiple-choice readiness

Observed fact: current quiz logic is a flashcard flow and is not yet multiple choice.

Required changes to support multiple-choice:

- separate the quiz question-generation logic from the UI layer;
- generate answer distractors from a candidate set of possible words;
- determine correct-answer selection consistently with current synonym or definition logic;
- decide whether correctness uses exact word match, normalized match, or synonym-aware acceptability;
- update persistence to record score and maybe answer history in a way consistent with existing behavior;
- add deterministic tests around question generation and scoring.

Recommendation:

- Direct multiple-choice implementation on the current architecture is not advisable.
- A small bounded refactor is the more likely safe path, especially to isolate quiz logic from UI and persistence.
- If the goal is to preserve current behavior while adding multiple choice, the first milestone should separate source-of-truth vocabulary logic and create deterministic pure functions for question generation before changing the UI.

## 10. Synonym behavior

Observed fact from `app.py`:

- `get_synonyms_nltk(word)` uses NLTK WordNet synsets and returns up to five synonyms.
- The result is derived from lemma names and excludes the source word itself.
- These synonyms are shown in the dictionary UI as clickable suggestions.

Observed fact from historical testbed branch `archive/repo-control-testbed`:

- `vocab_utils.py` and `synonym_policy.py` show an earlier effort to normalize and prioritize synonym candidates based on deduplication, case normalization, and single-token preference.
- `test_vocab_utils.py` contains unit-style test logic for synonym normalization behavior.

Interpretation:

- The current canonical app has a basic synonym helper, but the historical branch had a more explicit normalization and prioritization design.
- The historical work appears relevant to future multiple-choice or synonym-aware answering, but it should be evaluated and selectively reimplemented rather than ported blindly.

## 11. Historical testbed evaluation

Observed historical branch evidence:

- `archive/repo-control-testbed` and `agent-test/repoctl-ui-demo` resolve to `1281d7925b04b0d32bd6107b989af21221f1122c`.
- `archive/original-sanitized-main` and `archive/sanitized-testbed-base` resolve to `ff00a5c919c6bacff97699343181e092529fc952`.
- Relevant historical files found in the preserved branch include:
  - `vocab_utils.py`
  - `synonym_policy.py`
  - `test_vocab_utils.py`
  - `app.py`

Observed historical changes:

- The historical branch shows more explicit synonym normalization and candidate ranking logic than canonical `main`.
- The branch also contains unit-style tests around synonym normalization, which are likely useful as future reference points.

Disposition recommendation:

- Ignore automatically: do not merge historical testbed code into canonical main.
- Reimplement conceptually when needed: the normalization and prioritization ideas are useful but the canonical application is still the authority.
- Treat `test_vocab_utils.py` as a useful model for future deterministic tests, not as an accepted live test suite for `main`.

## 12. Dependency analysis

Observed dependencies from `requirements.txt`:

- `streamlit`
- `gspread`
- `oauth2client`
- `requests`
- `deep-translator`
- `nltk`
- `gTTS`

Classification:

- UI/framework: `streamlit`
- Google integration: `gspread`, `oauth2client`
- Dictionary/NLP: `requests`, `nltk`, `wordnet` semantics via NLTK, `deep-translator`
- Pronunciation/audio: `gTTS`
- HTTP/network: `requests`

Observed portability risks:

- `nltk` requires data downloads at runtime.
- `gTTS` may generate audio output at runtime and may require an external network or environment for TTS generation.
- `deep-translator` is another external network dependency.
- The dependency set is not obviously version-pinned in a hardened production manner.
- There are no test dependencies visible on canonical `main`.

## 13. Windows-to-Linux portability

Observed facts:

- The repo contains preserved Windows-oriented historical files in the testbed branch, e.g. `VocabLauncher.vbs`, `start vocab app.bat`, `app - stable.py`, `app v-1.py`, `app v-2.py`.
- Canonical `main` does not include those files.
- The current app uses Python assumptions that are cross-platform, but also relies on Streamlit and the working directory for credential files.

Classification:

- Irrelevant to current canonical main: legacy Windows launcher scripts and archived test-copy files.
- Compatible with Linux: the Python/Streamlit app itself should be runnable on Linux if dependencies and secrets are in place.
- Requires adaptation: service-account and secret location assumptions, media output handling, and any local-file credential assumptions.
- Unknown pending runtime validation: actual Linux runtime behavior around audio generation and directory permissions.

## 14. Pronunciation / audio behavior

Observed facts:

- `get_audio_bytes(text, lang='en')` creates a `gTTS` object and writes audio to an in-memory buffer.
- The method returns bytes and the UI plays them with `st.audio(audio_bytes.getvalue(), format='audio/mpeg')`.
- There is no explicit file cleanup beyond the in-memory buffer.
- Audio generation is tied directly to the UI and dictionary/translation flows.
- The app uses `gTTS` for both dictionary lookups and translation output.

Implications:

- Audio generation is a real runtime dependency and not just a UI nicety.
- For containerization, the image must support audio generation and this may need a runtime dependency or filesystem assumptions.
- The feature is visible and user-facing, but it is not core persistence logic.

## 15. Current test architecture

Observed facts:

- No canonical Python test files were discovered in the repository root or the current tree.
- The preserved testbed branch includes `test_vocab_utils.py`, but it is historical reference material, not active canonical `main` coverage.
- M001 already documented no obvious safe credential-free baseline test on canonical `main`.

Interpretation:

- The application currently has no broad test architecture for quiz logic, persistence semantics, or Streamlit behavior.
- The most likely future tests should be small, deterministic, and business-logic-focused rather than UI-driven.

## 16. Future test strategy

Recommendation for the next phase:

- pure unit tests for synonym normalization and candidate ranking;
- pure tests for quiz question generation and answer validation once the logic is isolated;
- persistence adapter tests around reading/writing vocabulary records; 
- Google Sheets adapter tests only at the boundary, not the full UI;
- a minimal container smoke check after the current-app container baseline is attempted;
- migration validation tests once a database layer is introduced.

The architecture should remain proportional to the application: a small app does not require enterprise-level test infrastructure.

## 17. Refactor decision

Classification: B — Small bounded refactor recommended

Observed reason:

- The app is monolithic and highly coupled to UI, persistence, secret access, and business logic.
- This is exactly the kind of coupling that would complicate multiple choice, database migration, and Streamlit replacement.
- A small bounded refactor can separate the logic that is already framework-independent from the UI and the data layer without changing product behavior.

Minimal refactor boundary recommendation:

- Extract vocabulary lookup/normalization logic from `app.py`.
- Extract score and persistence operations behind a simple repository boundary.
- Isolate quiz generation and answer validation as pure functions.
- Leave the user-facing Streamlit widgets and session state in place for now.

Behavior that must remain unchanged:

- word lookup semantics;
- definition display;
- saved-word behavior;
- flashcard scoring logic;
- user-facing flow.

Tests required before the refactor:

- deterministically compare the existing behavior for synonym normalization and score updates; 
- confirm no export of credentials or service keys occurs in the refactor.

## 18. Containerization findings

Observed fact: canonical `main` has no Dockerfile, Compose file, or image definition.

What would be required to containerize the current app without redesigning it:

- Python runtime installation;
- dependency installation from `requirements.txt`;
- app startup via Streamlit command;
- secret injection through environment variables or mounted config;
- a port exposure for the Streamlit app;
- a writable filesystem for any generated audio or cache material;
- a way to provide `service_account.json` or equivalent Google credentials without committing them to Git.

Implication: the current app is containerizable as a baseline, but it is not a clean separation from secrets and persistent data.

## 19. Container baseline recommendation

Recommendation: a minimal container baseline should hold the current app, but keep external secrets and data sources outside the image.

Conceptual topology:

`host Git repo` → `container image` → `runtime container`

What belongs in the image:

- Python runtime
- application code
- Python dependencies from `requirements.txt`
- the Streamlit app entry command

What should remain external:

- Google service credentials
- Merriam-Webster key
- any environment-specific config
- persistent data volume if later needed

Likely port:

- Streamlit default port `8501` is the most plausible current baseline requirement, though the exact port should be validated in a future runtime milestone.

Health-check concept:

- a simple HTTP health endpoint or a lightweight process check referencing the Streamlit server startup process, but this is a recommendation only and not a current implementation.

## 20. Persistence/database requirements

Current persistence behavior that a future database must preserve:

- vocabulary records must be readable and writable;
- word definitions and parts of speech must be stored;
- score/count values must be updated during practice sessions;
- duplicate words should be prevented or handled in a consistent way;
- the app reads all records and sorts by score/count.

Migration constraints:

- the logical vocabulary model is still small but real;
- the future database should be able to support both record lookup and score updates;
- any migration should preserve current user-visible behavior and not break the app when users add words or track progress.

## 21. Database recommendation

Recommendation: SQLite is the simplest and safest first choice for the near-term server-hosted database transition if the product still remains small and single-app. PostgreSQL is also reasonable if the goal is to align with a Linux server environment and future operational maturity, but it is not automatically required for this app.

Reasoning:

- SQLite is simple to manage, easy to test, and very well-suited to this small app.
- PostgreSQL is a stronger long-term choice if the app grows or if multiple clients are used concurrently.
- The current application is not yet at the level where a distributed or high-concurrency database architecture is justified.

Interpretation: database decision should follow the app’s actual needs, not the architectural prestige of a larger stack.

## 22. Streamlit replacement requirements

The replacement must provide the capabilities the current app uses:

- dictionary/search forms;
- result rendering;
- navigation among tabs or screens;
- session state for active word and practice state;
- buttons for save, next, and flip actions;
- audio playback;
- vocabulary display and flashcard flow;
- score updates.

The replacement should not be built around the current Streamlit-specific assumptions. It should preserve the same user-facing semantics while allowing business logic to live outside the UI framework.

## 23. Replacement framework recommendation

Recommendation: a lightweight Python server-rendered web framework or a minimal Python API plus frontend is likely enough for this small app.

Why this fits:

- the app is small and functionally bounded;
- a complex frontend stack would add unnecessary risk;
- the main architectural problem is not the UI itself but the fact that logic and persistence are too tightly mixed into the Streamlit page code.

This still leaves the main logic in Python, which is consistent with the current application and reduces migration risk.

## 24. Server/runtime constraints

Observed read-only findings:

- The target host is `henderson-server1`, Ubuntu Server 24.04 LTS.
- The current repo contains no container definitions or host-level runtime assumptions beyond the Python app itself.
- No runtime or infrastructure changes were made during M002.

No broader host inventory was performed beyond what was necessary to establish the deployment context.

## 25. External-access implications

Observed fact: external access is a later phase and is explicitly beyond the current milestone.

Architectural implications:

- the app currently assumes local or secret-based access to its credentials and spreadsheet data;
- containerization should not assume external access is already solved;
- the future secure access model will require explicit decisions around single-user or multi-user access, authentication, reverse proxy, and network exposure.

No implementation was performed for external exposure.

## 26. Repo Control existing-capability map

Observed fact: Repo Control remains a separate repository at `/home/chuck/projects/repo-control` and was not modified during M002.

Capabilities that should already be useful to Vocab work:

- repository status and deterministic Git inspection;
- Context and Snapshot-style evidence capture;
- Comparison between revisions or snapshots;
- Product Owner review workflow;
- guarded Stage and Commit preparation processes.

These capabilities are directly relevant to Vocab milestone work and align with the intended project-control workflow.

## 27. Repo Control future-gap hypotheses

Potential future gaps that real Vocab work may expose:

- build identity for the app or image;
- mapping source SHA to built artifact;
- runtime health verification for a running container or app;
- deployed revision comparison for server-side deployments;
- guarded deployment for later runtime milestones.

These are not current proof of missing capability; they are reasonable hypotheses that would be justified by actual Vocab runtime and deployment milestones later.

## 28. Repo Control Vocab test plan

Recommended use of Repo Control during the Vocab arc:

- use Context at the start of each feature milestone;
- use Snapshot before major implementation choices;
- use Comparison when evaluating the current app against refactor or database migration work;
- preserve Product Owner review evidence at milestone boundaries;
- use Stage/Commit review when the repo changes; 
- preserve runtime or deployment evidence when containerization and server work are authorized.

The goal is to use Repo Control for evidence and control, not to force Vocab work into a repo-control-specific architecture.

## 29. Proposed normal development workflow

`Product Owner requirement` → `Architect milestone` → `Coder reconnaissance/context` → `bounded implementation` → `deterministic tests` → `Repo Control review evidence` → `Product Owner validation` → `Stage/Commit` → `runtime verification`.

This remains the default flow for the Vocab project because it preserves validation and review evidence without over-engineering the process.

## 30. Scope-creep exclusions

Work explicitly deferred from this reconnaissance and should not be pulled into an immediate implementation milestone:

- multiple-choice implementation during this milestone;
- database migration during this milestone;
- Streamlit replacement during this milestone;
- runtime setup or container build during this milestone;
- Repo Control source changes during this milestone;
- broad host inventory or unrelated server inspection.

## 31. Recommended milestone roadmap

Recommended sequence after M002:

1. M003 — bounded refactor or current-app container baseline
   - Purpose: separate business logic from Streamlit and data-access code while preserving current behavior.
   - Mode: implementation or precise baseline work.
   - Files: likely `app.py` plus helper modules.
   - Acceptance evidence: deterministic behavior preserved, no credential leak, earlier logic remains operational.
   - Repo Control: yes, via Context/Snapshot/Comparison and review evidence.
   - Stop condition: risk reduction achieved without changing product intent.

2. M004 — multiple-choice quiz implementation
   - Purpose: convert the current flashcard/test flow to multiple choice.
   - Files: current quiz logic and UI layer.
   - Acceptance evidence: deterministic multiple-choice behavior and scoring semantics.
   - Repo Control: yes.
   - Stop condition: user-facing behavior matches approved product decisions.

3. M005 — database migration from Google Sheets to server-hosted database
   - Purpose: preserve the logical vocabulary model while moving persistence.
   - Files: repository abstraction, persistence adapters, migration logic.
   - Acceptance evidence: writes and reads preserved, data integrity verified.
   - Repo Control: yes.
   - Stop condition: app still works with database-backed storage and no credential leakage.

4. M006 — Streamlit replacement / self-hosted runtime
   - Purpose: remove Streamlit as the runtime and replace it with a simpler Python web stack or equivalent.
   - Acceptance evidence: same user flows work in the new runtime.
   - Repo Control: yes.
   - Stop condition: deployment-ready server runtime with controlled access.

## 32. M003 recommendation

Recommended next milestone: bounded refactor

Reason:

- the application’s current architecture is monolithic and heavily coupled to UI and persistence;
- the prompt requires multiple choice, database migration, and Streamlit replacement later, and those all become more dangerous without a small separation step;
- a bounded refactor is significantly safer than implementing feature work directly on the current `app.py`-centric design.

## 33. Limitations / unresolved questions

Observed limitations:

- No live runtime validation was performed because the prompt forbids application startup or server mutation.
- No credential values were accessed or reproduced.
- No live Google Sheets data was inspected.
- No exact sheet schema beyond evidence from code was verified at runtime.
- The historical testbed content is useful but not authoritative for canonical `main`.

These limitations are acceptable for M002; they are documented and should guide later implementation milestones.

## 34. Final repository state

Observed final state after reconnaissance and closeout creation:

```bash
git branch --show-current
git rev-parse HEAD
git status --short
git rev-list --left-right --count HEAD...origin/main
```

Latest observed output:

```bash
main
9056811bdb6afc0ad698205180c5b7564f1d2ec0
?? milestones/002_architecture_and_integration_reconnaissance_closeout.md
0       0
```

This file is the only authored output created during M002, as required by the milestone prompt.
