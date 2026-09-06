# Vocab App Milestone M003

# Bounded Refactor and Characterization Tests

**Prompt file:** `milestones/003_bounded_refactor_and_characterization_tests_prompt.md`
**Required closeout:** `milestones/003_bounded_refactor_and_characterization_tests_closeout.md`
**Mode:** Bounded implementation
**Reasoning:** High
**Target repository:** `/home/chuck/projects/vocab-app`

---

# 1. Objective

Refactor the current Vocab application just enough to establish safe, testable boundaries for the upcoming product changes while preserving current user-visible behavior.

M003 is not a feature milestone.

Do not implement the future multiple-choice quiz yet.

Do not migrate persistence to PostgreSQL yet.

Do not replace Streamlit yet.

The purpose of M003 is to reduce risk before those changes by separating:

1. framework-independent application/domain logic;
2. vocabulary persistence operations;
3. quiz/practice scoring behavior;
4. Streamlit presentation/orchestration.

Add characterization tests that preserve the important existing behavior.

The result should remain the current Vocab application, but with a cleaner internal structure that can support subsequent milestones safely.

---

# 2. Controlling Project Direction

The current Vocab roadmap is:

- **M003** — bounded refactor and characterization tests;
- **M004** — containerized current application baseline;
- **M005** — multiple-choice quiz;
- **M006** — PostgreSQL persistence migration;
- **M007** — Streamlit replacement;
- **M008+** — LAN/external deployment work.

Do not pull future milestone work into M003.

A small structural choice may anticipate PostgreSQL and multiple-choice where doing so avoids obvious rework, but M003 must not implement those future features.

---

# 3. Repository and Product Context

Canonical repository:

`/home/chuck/projects/vocab-app`

Current application characteristics established by M002:

- application is primarily in `app.py`;
- UI is Streamlit;
- persistence is Google Sheets through `gspread`;
- authentication/config uses `service_account.json` or Streamlit secrets;
- workbook is `VocabApp_DB`;
- current persistence operations include reading words and updating scores/counts;
- practice currently selects low-count words and shuffles them;
- current practice UX is flashcard-oriented;
- scoring updates existing persistence;
- synonym support uses NLTK WordNet;
- dictionary/translation/audio helpers exist;
- there was no meaningful automated test suite in the canonical repository before this refactor.

Historical sanitized/testbed branches may contain useful test concepts, but they are non-authoritative references.

Do not merge or cherry-pick historical testbed commits.

Reimplement only concepts that remain appropriate for the canonical code.

---

# 4. Product Behavior to Preserve

M003 should preserve the current product semantics unless characterization proves an existing behavior clearly differs from the M002 description.

Important existing behaviors include:

- vocabulary records are read from the current Google Sheets persistence path;
- existing words/data semantics remain unchanged;
- practice selection prioritizes the current low-count behavior;
- current practice ordering/shuffling behavior remains functionally equivalent;
- `Got it` and `Missed` continue to update the score/count according to current application behavior;
- existing synonym behavior remains available;
- existing translation/dictionary/audio behavior remains available;
- current Streamlit screens and normal application workflow remain usable.

Do not redesign the UI.

If existing source behavior differs from this summary, preserve the actual source behavior and document the discrepancy rather than silently changing it.

---

# 5. Starting-State Gate

Before changing code:

    cd /home/chuck/projects/vocab-app
    
    pwd
    git branch --show-current
    git rev-parse HEAD
    git status --short
    git remote -v
    git rev-parse @{upstream} 2>/dev/null || true
    git rev-list --left-right --count HEAD...@{upstream} 2>/dev/null || true
    git log -6 --oneline --decorate

Expected:

- canonical branch: `main`;
- upstream: canonical GitHub Vocab repository;
- M002.1 is already closed;
- working tree should be clean except for the committed M003 prompt once the Product Owner completes the prompt-lifecycle commit.

STOP if unexpected existing source changes make attribution unsafe.

Do not clean, reset, restore, or overwrite unexpected work.

---

# 6. Repo Control Usage — Required Real-World Validation

M003 is the first Vocab milestone after Repo Control M014.

Use Repo Control as the control plane from the beginning.

Repo Control repository:

`/home/chuck/projects/repo-control`

Do not modify Repo Control during M003.

Do not access Photo Organizer.

## Required initial Repo Control evidence

Against canonical Vocab:

1. inspect deterministic Git state;
2. perform meaningful Context discovery before broad source reading;
3. create or identify an appropriate baseline Snapshot for the current Vocab state.

Use the improved M012 Context capability.

Meaningful Context queries should include the concepts needed for this milestone, such as:

- Google Sheets persistence;
- practice selection;
- score update;
- synonyms;
- Streamlit session/application behavior;
- relevant exact symbols discovered from prior evidence.

Do not treat Context as authoritative over source.

Use the hierarchy:

    source/tests
    -> deterministic Repo Control facts
    -> Snapshot/Comparison evidence
    -> advisory AI

If Context is insufficient for a question, record the limitation and inspect source directly.

Do not force artificial Repo Control usage where direct source/test evidence is clearer.

---

# 7. Bounded Reconnaissance Before Editing

This is an implementation milestone, so reconnaissance should be short and targeted.

Confirm the current responsibility map around:

- application entry/UI orchestration;
- Google Sheets connection and persistence;
- vocabulary record representation;
- practice candidate selection;
- scoring/update behavior;
- synonym lookup;
- dictionary/translation/audio helpers where they interact with application state.

Identify the smallest safe extraction boundaries.

Do not perform another full architectural survey.

M002 already established the broad architecture.

---

# 8. Refactor Target

The preferred structural direction is:

    Streamlit UI / orchestration
            |
            v
    framework-independent application/domain functions
            |
            v
    persistence interface / implementation
            |
            v
    current Google Sheets backend

The exact file/module names may follow existing repository conventions.

Do not create unnecessary abstraction layers.

The architecture only needs enough separation to support:

- characterization testing now;
- multiple-choice logic in M005;
- PostgreSQL substitution in M006;
- Streamlit replacement in M007.

---

# 9. Persistence Boundary

Separate Google Sheets-specific access from application/domain logic.

The application logic should not need to know about raw `gspread` calls.

Create the smallest useful persistence boundary for the operations the application currently requires.

Likely responsibilities include:

- load/read vocabulary records;
- persist/update practice score/count state;
- any other existing write required by current product behavior.

Do not design a generalized ORM.

Do not add PostgreSQL.

Do not change the current Google Sheets storage schema.

Do not migrate user data.

The existing Google Sheets implementation should remain the active production implementation after M003.

---

# 10. Domain / Application Logic Boundary

Extract framework-independent logic where it currently lives inside Streamlit orchestration.

Prioritize logic needed by upcoming milestones.

At minimum investigate/extract:

- vocabulary/practice candidate selection;
- sorting/prioritization behavior;
- shuffling/randomization boundary;
- scoring result calculation;
- update values passed to persistence;
- other small pure transformations directly involved in practice behavior.

Prefer pure functions where practical.

Do not rewrite unrelated helper functions merely for stylistic consistency.

---

# 11. Practice Selection Behavior

Characterize the exact existing practice-selection semantics before altering them.

M002 observed behavior equivalent to:

- prioritize approximately the first ten lowest-count words;
- shuffle the selected candidates;
- present them through the current flashcard workflow.

Verify exact current source behavior.

Extract the deterministic portion separately from randomness where practical so it can be tested reliably.

For example, candidate selection and random ordering should not need to be inseparably coupled if separating them is simple.

Do not change the number of selected words or ranking behavior unless current source proves the M002 description inaccurate.

---

# 12. Scoring Behavior

Characterize and preserve the existing meaning of:

- `Got it`;
- `Missed`;
- score/count updates;
- persistence write values.

Move calculation/decision logic out of Streamlit event handling where practical.

The UI may still initiate the action, but the rule itself should be testable without Streamlit.

Do not redesign scoring in M003.

---

# 13. Streamlit Boundary

Streamlit remains the active UI framework.

The goal is not to eliminate Streamlit references from the repository.

The goal is to prevent core behavior from requiring a live Streamlit session in order to test it.

Keep Streamlit-specific concerns in the presentation/orchestration layer where practical:

- widgets;
- buttons;
- layout;
- session state;
- rerun/navigation behavior;
- rendering.

Do not perform a UI rewrite.

---

# 14. External Services

Dictionary, translation, text-to-speech, NLTK, and related external/helper behavior should not be broadly redesigned.

Where those services prevent deterministic tests, introduce the smallest practical seam or mock boundary.

Tests must not require unreliable live external network calls.

Do not replace current services in M003.

---

# 15. Characterization Test Suite

Create a native automated test foundation for the canonical Vocab repository.

Use a lightweight Python testing approach compatible with the project.

Prefer the simplest established option already supported by the environment; do not add a heavy framework unnecessarily.

Tests should characterize existing behavior rather than invent new behavior.

At minimum cover the important extracted logic.

---

# 16. Required Characterization Coverage

At minimum add tests for:

## Practice selection

- lower-count vocabulary is prioritized correctly;
- expected candidate-count limit is preserved;
- candidate selection behaves correctly with fewer records than the normal limit;
- deterministic selection can be tested independently from shuffle behavior.

## Scoring

- `Got it` behavior;
- `Missed` behavior;
- exact values sent to persistence;
- relevant edge behavior present in current implementation.

## Persistence boundary

Using a fake/mock persistence implementation:

- application/domain code can load vocabulary without importing/calling live Google Sheets;
- application/domain scoring can request persistence updates without requiring `gspread`;
- Google Sheets-specific behavior remains confined to its implementation boundary.

## Synonym behavior

Characterize the current meaningful synonym transformation/lookup behavior without requiring unrelated Streamlit execution.

Use mocks/controlled data where NLTK corpus availability would otherwise make the test unreliable.

## Importability

Core extracted modules should import and test without starting Streamlit UI or requiring Google service credentials.

---

# 17. Historical Testbed Reference

Historical sanitized/testbed code may contain useful concepts, particularly around synonym behavior and localized testing.

It is reference material only.

Do not:

- merge it;
- cherry-pick it;
- treat its behavior as canonical;
- copy secrets/configuration;
- reintroduce sanitized/testbed Git history.

When historical test concepts conflict with canonical source behavior, canonical source wins.

---

# 18. Secrets and Credentials

Do not inspect, print, commit, or copy credentials.

Sensitive/runtime material remains excluded, including:

- `service_account.json`;
- `.streamlit/`;
- `.env`;
- private keys or credential helpers.

Tests must not require actual Google credentials.

Use dependency injection, mocks, fakes, or equivalent bounded testing seams.

---

# 19. Dependency Changes

Keep dependency changes minimal.

If a test dependency must be added, justify it.

Do not add:

- PostgreSQL libraries merely for future use;
- Flask/FastAPI merely for future Streamlit replacement;
- container dependencies merely for M004;
- generalized DI frameworks.

M003 should remain a small Python refactor.

---

# 20. No Product Feature Change

Do not implement:

- multiple-choice questions;
- distractor generation;
- new quiz modes;
- PostgreSQL;
- SQLite;
- Docker/containerization;
- Streamlit replacement;
- authentication changes;
- remote/LAN deployment;
- new database schema;
- data migration;
- major UI changes.

If a requested extraction would require one of these, stop and report rather than expanding scope.

---

# 21. Source Compatibility

Preserve the current normal application launch method unless a minimal import-safe entry-point adjustment is necessary.

If `app.py` currently executes Streamlit behavior at import time and this blocks testing, make the smallest safe structural change required to isolate testable logic.

Do not turn the application into a new framework architecture.

---

# 22. Test Execution

Run focused tests during implementation.

Then run the complete Vocab test suite.

Record exact commands and literal results.

Also run an appropriate compile/import validation such as:

    python -m compileall .

or a narrower repository-appropriate equivalent that excludes generated/runtime directories where necessary.

Run:

    git diff --check

before closeout.

---

# 23. Manual Application Validation

After tests pass, validate the existing Vocab application manually using its current Streamlit workflow to the extent possible without unsafe credential exposure.

Confirm that normal existing behavior still works, including:

- application starts;
- vocabulary data can be loaded through the existing backend in the normal configured environment;
- current practice UI still renders;
- current flashcard flow remains available;
- existing `Got it` / `Missed` actions still use the expected persistence path;
- no obvious regression in synonyms or other existing helper behavior.

Do not modify production vocabulary data merely to prove the refactor unless a controlled existing test method already exists.

If live write validation would alter real data unnecessarily, stop at a safe read-only/manual boundary and document what was and was not validated.

---

# 24. Repo Control Post-Implementation Evidence

After implementation and tests, use Repo Control against canonical Vocab to create deterministic evidence of the changed working state.

Required:

1. Git state inspection;
2. meaningful Context queries against the refactored structure;
3. post-implementation Snapshot;
4. deterministic Comparison from the M003 baseline Snapshot to the post-implementation Snapshot where meaningful.

The Comparison should help answer:

- what structural files/modules were added;
- what responsibilities moved;
- whether changes remained within M003 scope.

Advisory AI analysis may be used after deterministic evidence if useful, but is not required for acceptance and must not override source/tests.

Record useful Repo Control artifact IDs in the closeout.

---

# 25. Git Mutation Boundary

The coding agent is not authorized to stage or commit M003 implementation.

Do not run:

- `git add`;
- `git commit`;
- `git reset`;
- `git restore`;
- `git checkout` for mutation;
- `git clean`;
- `git push`.

The Product Owner will review the implementation and closeout first.

After acceptance, guarded Stage/Commit should be performed through the newly hardened Repo Control Workflow so M003 serves as the first real-world M014 validation.

---

# 26. Expected File Scope

Do not lock exact implementation filenames before inspecting the current repository.

However, expected scope should remain small and likely include:

- `app.py`;
- one or a few new application/domain modules;
- one persistence module/interface;
- test files;
- dependency metadata only if actually required;
- M003 closeout.

A large tree-wide rewrite is a STOP condition.

---

# 27. Escalation / Stop Conditions

STOP and report if:

- preserving current behavior requires a materially larger redesign;
- current source semantics materially contradict M002 in a way that changes milestone scope;
- Google Sheets access cannot be isolated without broad application rewrite;
- Streamlit is so tightly coupled that characterization requires a framework replacement;
- credentials/secrets would need to be exposed;
- historical testbed behavior conflicts materially with canonical source and no safe interpretation exists;
- the working tree contains unexpected pre-existing source changes;
- Repo Control reports a target-state inconsistency with direct Git;
- the refactor begins pulling in M004/M005/M006/M007 work;
- tests expose a product defect whose fix would change current behavior rather than merely preserve it.

Do not silently fix unrelated product defects.

Document them for a later milestone.

---

# 28. Required Closeout

Create exactly:

`milestones/003_bounded_refactor_and_characterization_tests_closeout.md`

Include:

## 1. Executive conclusion

PASS / PARTIAL / STOP.

## 2. Starting Git state

Branch, HEAD, upstream, parity, status.

## 3. Starting Repo Control evidence

Git-state result, Context queries/results, baseline Snapshot ID.

## 4. Canonical behavior confirmed

What the existing application actually did before refactor.

## 5. Refactor architecture

Concise before/after responsibility map.

## 6. Persistence boundary

What was extracted and how Google Sheets remains active.

## 7. Domain/application logic

Exact behaviors moved out of Streamlit.

## 8. Practice selection characterization

Exact preserved semantics.

## 9. Scoring characterization

Exact preserved semantics.

## 10. Streamlit boundary

What remains UI-specific.

## 11. External-service seams

Mocks/fakes/isolation used.

## 12. Files changed

Exact list.

## 13. Tests added

Map each test to preserved behavior.

## 14. Focused test results

Exact commands/results.

## 15. Full suite results

Exact commands/results.

## 16. Compile/static validation

Exact commands/results.

## 17. Manual application validation

What was safely verified.

## 18. Post-implementation Repo Control evidence

Context result IDs, Snapshot ID, Comparison ID, relevant deterministic findings.

## 19. Scope assessment

Confirm no multiple-choice, PostgreSQL, container, or Streamlit-replacement work was introduced.

## 20. Secrets/hygiene

Confirm no credentials or excluded runtime artifacts were exposed or added.

## 21. Remaining limitations

Only genuine limitations.

## 22. Recommendation

State whether M003 is ready for Product Owner acceptance and guarded Stage/Commit through Repo Control.

## 23. Next milestone recommendation

Normally:

`Vocab M004 — containerized current application baseline`

Do not recommend another Repo Control milestone unless this real workflow exposes a genuine control-plane defect.

## 24. Final Git state

Capture:

    git branch --show-current
    git rev-parse HEAD
    git status --short
    git rev-parse @{upstream} 2>/dev/null || true
    git rev-list --left-right --count HEAD...@{upstream} 2>/dev/null || true

---

# 29. Acceptance Criteria

M003 is PASS only if:

- current Vocab behavior is preserved;
- important practice-selection behavior has deterministic characterization tests;
- scoring behavior has deterministic characterization tests;
- core behavior can be tested without starting Streamlit;
- application/domain code no longer directly depends on raw Google Sheets calls where the new boundary applies;
- Google Sheets remains the active persistence implementation;
- tests do not require real credentials;
- no future product feature is introduced;
- focused tests pass;
- full Vocab test suite passes;
- compile/import validation passes;
- `git diff --check` passes;
- existing Streamlit application remains operational;
- Repo Control produces usable post-change evidence;
- baseline/post-change Snapshot comparison is recorded where meaningful;
- canonical Vocab remains uncommitted for Product Owner review at closeout.

---

# 30. Post-M003 Workflow

If M003 is accepted:

1. Product Owner reviews exact changed files and closeout.
2. Use Repo Control Workflow for guarded Stage.
3. Create/use the required matching Snapshot directly from Workflow.
4. Prepare guarded Commit.
5. Approve guarded Commit.
6. Verify resulting Commit traceability and `Commit aligned` Snapshot classification.
7. Push canonical Vocab `main`.
8. Proceed to Vocab M004.

If Repo Control misrepresents actual Git state at any synchronization gate:

**STOP.**

Direct Git remains canonical truth.

Do not create another Repo Control milestone unless a genuine reproducible control-plane gap is exposed.

---

# 31. Working Principles

> Preserve behavior before changing behavior.

> Extract only the seams needed for the next product milestones.

> Google Sheets stays active in M003; PostgreSQL comes later.

> Streamlit stays active in M003; replacement comes later.

> Tests should characterize the canonical application, not the historical testbed.

> Repo Control should support the product workflow, not become the product work.

---

**End of `003_bounded_refactor_and_characterization_tests_prompt.md`**
