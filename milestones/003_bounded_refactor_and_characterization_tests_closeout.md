# Vocab App Milestone M003 Closeout

## 1. Executive conclusion

Result: PASS

The bounded refactor and characterization test foundation are implemented and validated without changing the intended product behavior. Practice selection, score calculation, Google Sheets access, save-word persistence operations, synonym behavior, and the configured Streamlit startup path now have small testable or inspectable boundaries. A disposable environment containing only the dependencies declared by `requirements.txt` launched the application successfully and rendered the normal UI. The practice action reached the expected missing-credentials boundary without any live data write.

No multiple-choice quiz, PostgreSQL migration, containerization, Streamlit replacement, schema change, or data migration was introduced.

## 2. Starting Git state

Observed before implementation:

- Repository: `/home/chuck/projects/vocab-app`
- Branch: `main`
- HEAD: `d9990d82810c1e56e90556d272c95b30127f1f61`
- Upstream: `origin/main`
- Ahead/behind: `0 0`
- Working tree: clean
- Starting commit: `d9990d8 bounded_refactor_and_characterization_tests_prompt`

## 3. Starting Repo Control evidence

Repo Control baseline evidence was captured before editing:

- deterministic status: clean, `main`, HEAD `d9990d82810c1e56e90556d272c95b30127f1f61`, upstream equal;
- baseline Snapshot: `snap--50399f343c56c971`;
- Context `google sheets`: matched, one file, two symbols;
- Context `practice`: matched, one file;
- Context `update_score`: matched, one file, two symbols, one relationship;
- Context `synonym`: matched, one file, three symbols, three relationships;
- Context `streamlit`: matched, two files;
- Context `get_sheet`: matched, one file, five symbols, four relationships;
- Context `get_synonyms_nltk`: matched, one file, three symbols, three relationships.

Repo Control evidence was used for navigation and state confirmation only. Source behavior remained authoritative.

## 4. Canonical behavior confirmed

The existing application behavior confirmed from `app.py` was:

- practice rows are copied, non-`int` `Count` values become `1`, records are stably sorted ascending by `Count`, the first 10 are selected, and only then are they shuffled;
- success writes the current count plus 1;
- missed writes count `1`;
- score lookup uses the word and writes Google Sheets column 6;
- save-word duplicate detection uses first-column values case-insensitively;
- new vocabulary records use the existing append-row values and schema;
- synonym lookup removes the queried word case-insensitively, deduplicates through a set, returns at most five values, and returns an empty list when lookup raises;
- the Streamlit-facing score wrapper continues to catch errors and print the existing error message rather than propagating them to the user.

## 5. Refactor architecture

Before:

```text
app.py
  Streamlit initialization and session state
  Google Sheets credentials and raw sheet calls
  practice selection and shuffle
  score calculation and writes
  NLTK synonym behavior
  dictionary, translator, audio, and UI rendering
```

After:

```text
app.py
  Streamlit launch, session state, rendering, orchestration, existing UI catches

vocab_domain.py
  count coercion, deterministic practice selection, shuffle boundary, scoring rules

vocab_nlp.py
  NLTK root and synonym helpers with lazy external loading

vocab_persistence.py
  purpose-built Google Sheets persistence adapter

tests/
  standard-library characterization tests using controlled data and fakes
```

The extraction is intentionally small. `app.py` remains the application entry point.

## 6. Persistence boundary

`GoogleSheetsPersistence` now owns the active Google Sheets operations required by the current application:

- connect using the existing `service_account.json` or Streamlit secrets path;
- load records and history;
- detect duplicate words from the first sheet column;
- append vocabulary records;
- find a word row;
- read score column 6;
- write score column 6.

The adapter raises infrastructure errors normally. The existing Streamlit-facing handlers retain their current catches and visible behavior. Google Sheets remains the active implementation and the sheet schema is unchanged.

The adapter imports `gspread` and `oauth2client` lazily only when a live connection is requested, allowing core tests to run without credentials or those runtime packages.

## 7. Domain/application logic

`vocab_domain.py` contains:

- exact current non-`int` count coercion;
- stable ascending candidate selection;
- the limit of 10 candidates;
- a separate random shuffle operation;
- success and missed score calculation;
- score row lookup/read/write orchestration through a persistence object.

The Streamlit wrapper still catches score-update errors, preserving the current user-visible behavior.

## 8. Practice selection characterization

The extracted behavior preserves:

- `int` counts unchanged;
- `None`, numeric strings, empty strings, floats, and other non-`int` values converted to `1`;
- stable ascending sorting by normalized `Count`;
- first 10 selection;
- natural handling of fewer than 10 records;
- shuffle only after deterministic selection.

## 9. Scoring characterization

The extracted scoring behavior preserves:

- success: current count plus 1;
- missed: count becomes 1;
- lookup by word;
- read of the current score from the matched row;
- write to column 6;
- missing row produces no write;
- infrastructure errors propagate through the domain/persistence operation and are caught by the existing Streamlit-facing wrapper.

## 10. Streamlit boundary

Streamlit remains the launch framework and UI. Session state, widgets, tabs, reruns, progress, alerts, audio rendering, and UI error handling remain in `app.py`. No UI redesign or framework replacement was attempted.

## 11. External-service seams

- Google Sheets access is behind `GoogleSheetsPersistence`.
- NLTK loading is lazy in `vocab_nlp.py`.
- Synonym tests patch the controlled loader and use fake synsets/lemmas.
- No network calls, credentials, NLTK downloads, or Google Sheets writes are required by the test suite.
- Dictionary, translation, and audio services were not broadly redesigned.

## 12. Files changed

- `app.py`
- `vocab_domain.py`
- `vocab_nlp.py`
- `vocab_persistence.py`
- `tests/test_vocab_domain.py`
- `tests/test_vocab_nlp.py`
- `tests/test_vocab_persistence.py`
- `milestones/003_bounded_refactor_and_characterization_tests_closeout.md`

No dependency metadata was changed.

## 13. Tests added

- `test_vocab_domain.py`: count coercion, stable selection, ten-record limit, short input, separate shuffle, success scoring, missed scoring, and persistence score write requests.
- `test_vocab_persistence.py`: record/history loading, duplicate detection, append behavior, score lookup, and score-column writes using a fake sheet.
- `test_vocab_nlp.py`: normalized synonym membership, duplicate elimination, five-result maximum, queried-word exclusion, and exception fallback using controlled fake synsets.

## 14. Focused test results

Command:

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
```

Result: `Ran 12 tests ... OK`

## 15. Full suite results

The same command is the complete Vocab test suite because the repository had no earlier test suite. Result: 12 tests passed.

## 16. Compile/static validation

Command:

```bash
python -m py_compile app.py vocab_domain.py vocab_nlp.py vocab_persistence.py
```

Result: passed.

Command:

```bash
git diff --check
```

Result: passed.

## 17. Manual application validation

Runtime validation was performed in a disposable environment outside the repository:

```bash
rm -rf /tmp/vocab-app-m003-runtime
python3 -m venv /tmp/vocab-app-m003-runtime
. /tmp/vocab-app-m003-runtime/bin/activate
python -m pip install --upgrade pip
python -m pip install -r /home/chuck/projects/vocab-app/requirements.txt
python -m streamlit run app.py --server.headless true --server.address 127.0.0.1 --server.port 8766
```

The declared packages installed successfully, including:

- `streamlit 1.63.0`
- `gspread 6.2.1`
- `oauth2client 4.1.3`
- `requests 2.34.2`
- `deep-translator 1.11.4`
- `nltk 3.10.3`
- `gTTS 2.5.4`

Observed runtime evidence:

- Streamlit started on `http://127.0.0.1:8766`.
- The browser page title was `Vocab Tracker`.
- The normal `Vocab Builder` UI rendered.
- Dictionary, Translator, and Practice tabs rendered.
- The Practice tab rendered `Flashcard Session` and `Start Session`.
- Pressing `Start Session` reached the expected configuration boundary and displayed:

  `Could not fetch cards: No secrets found. Valid paths for a secrets.toml file or secret directories are: /home/chuck/.streamlit/secrets.toml, /home/chuck/projects/vocab-app/.streamlit/secrets.toml`

This confirms the refactored modules loaded, Streamlit startup succeeded, UI wiring succeeded, and the practice path reached persistence construction. The missing secret configuration was an expected environment boundary, not a refactor failure.

No credentials were inspected, printed, copied, fabricated, or inserted. No live Google Sheets read/write, score update, or vocabulary save was attempted.

## 18. Post-implementation Repo Control evidence

Post-change Context results:

- `practice`: matched;
- `update_score`: matched;
- `get_persistence`: matched, one file, three symbols, one relationship;
- `select_practice_candidates`: matched;
- `get_synonyms_nltk`: matched.

Post-change Snapshot: `snap--d36cfbbc9e1cef28`

Baseline-to-post Comparison: `cmp--e4d8bdcf797fa152`

Comparison findings:

- `app.py` content changed;
- `get_persistence` was added;
- `get_sheet`, `get_nltk_root`, and `get_synonyms_nltk` moved out of `app.py`;
- the score call now routes through `get_persistence`;
- no requirements changes;
- no parse failures;
- no unrelated tracked files changed.

The after Snapshot reported partial worktree coverage because the new modules and tests were untracked at snapshot time. They are listed explicitly as untracked paths, but Repo Control did not render them as tracked-file content changes. Direct Git and source/tests remain authoritative for those files.

## 19. Scope assessment

Confirmed absent:

- multiple-choice questions;
- distractor generation;
- PostgreSQL or SQLite;
- Docker/containerization;
- Streamlit replacement;
- authentication changes;
- schema changes;
- data migration;
- broad external-service redesign.

## 20. Secrets/hygiene

- No credentials were inspected, printed, copied, or committed.
- No `service_account.json`, `.streamlit`, `.env`, private key, or generated runtime artifact was added.
- Tests use fakes, mocks, and controlled data.

## 21. Remaining limitations

- Repo Control structural Comparison does not include untracked file contents in its tracked-file structural records; direct Git/source evidence covers those new files.
- The app still performs Streamlit/NLTK initialization at import time; M003 extracted the required core seams without attempting a broad import-time rewrite.
- Live Google Sheets data loading and write behavior were not exercised because no safe configured credentials were available; the application reached and reported that expected boundary.

## 22. Recommendation

M003 is ready for Product Owner acceptance as `PASS`. The configured runtime validation satisfied the previously outstanding acceptance criterion through the safe missing-credentials boundary. The implementation remains uncommitted and unstaged. No guarded Stage or Commit was executed.

The remaining live Google Sheets limitation is environmental and does not block M003 acceptance: no credentials were available, and no real-data write was necessary or appropriate for this validation.

## 23. Next milestone recommendation

Recommended next milestone: `Vocab M004 — containerized current application baseline`, subject to Product Owner acceptance of this M003 result and completion or explicit acceptance of the manual-validation limitation.

## 24. Final Git state

Observed after implementation and closeout creation:

```bash
git branch --show-current
main

git rev-parse HEAD
d9990d82810c1e56e90556d272c95b30127f1f61

git status --short
 M app.py
?? milestones/003_bounded_refactor_and_characterization_tests_closeout.md
?? tests/test_vocab_domain.py
?? tests/test_vocab_nlp.py
?? tests/test_vocab_persistence.py
?? vocab_domain.py
?? vocab_nlp.py
?? vocab_persistence.py

git rev-parse @{upstream}
d9990d82810c1e56e90556d272c95b30127f1f61

git rev-list --left-right --count HEAD...@{upstream}
0 0
```

The canonical Vocab repository remains uncommitted for Product Owner review. No Stage, Commit, or Push operation was performed.
