# Vocab App Milestone 002

# Architecture and Integration Reconnaissance

**Prompt file:** `002_architecture_and_integration_reconnaissance_prompt.md`  
**Required closeout:** `002_architecture_and_integration_reconnaissance_closeout.md`  
**Mode:** Reconnaissance only  
**Reasoning:** High  
**Implementation authority:** None  
**Git mutation authority:** None except creation of the required closeout document  
**Runtime mutation authority:** None  
**Database mutation authority:** None  
**Repo Control mutation authority:** None

---

# 1. Objective

Perform a high-confidence architectural reconnaissance of the canonical Vocab App and produce the evidence-based implementation roadmap for the next development arc.

The Product Owner has three major intended changes:

1. change the vocabulary test/quiz function to multiple choice;
2. move vocabulary words and definitions from Google Sheets to a database hosted on `henderson-server1`;
3. remove Streamlit and operate the application as a self-hosted application on `henderson-server1`, initially locally/LAN and later through controlled secure external access.

A bounded refactor may precede those changes if reconnaissance demonstrates that it materially reduces implementation risk.

This milestone must determine:

- what the application actually does today;
- how the current code is structured;
- how tightly Streamlit, quiz behavior, Google Sheets, credentials, pronunciation, synonym handling, and persistence are coupled;
- what tests exist or are missing;
- whether useful work from the preserved Repo Control testbed should later be deliberately reimplemented or ported;
- what is required to containerize the current application without redesigning it;
- whether a bounded refactor should precede containerization or feature work;
- the safest milestone sequence for the three Product Owner goals;
- what real Repo Control integration opportunities are likely to arise.

M002 is reconnaissance only.

Do not implement the roadmap during this milestone.

---

# 2. Controlling Documents

Read and follow:

1. `docs/context/project_workflow_v1.md`
2. `docs/context/coding_agent_rules_v1.md`
3. `docs/context/vocab_app_project_context_v1.md`
4. `architecture/vocab_repo_control_integration_roadmap_v1.md`
5. `docs/context/new_chat_intro_coder_v1.md`
6. `milestones/001_repository_and_project_control_foundation_closeout.md`
7. this prompt

M001 established the canonical repository and project-control foundation.

Do not reopen M001 decisions unless deterministic evidence reveals a material contradiction.

---

# 3. Canonical Repository

Canonical Vocab repository:

`/home/chuck/projects/vocab-app`

Canonical branch:

`main`

Canonical remote:

`origin`

Canonical GitHub repository:

`CHHIV-Projects/vocab-app`

Historical Repo Control testbed branches remain reference evidence only.

Do not merge or mutate them.

---

# 4. Starting-State Gate

Before reconnaissance, capture:

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



Expected:

- branch `main`;
- tracking `origin/main`;
- M001 committed;
- no unexplained working-tree changes.

The M002 prompt itself may be the only expected uncommitted file if the Product Owner has not yet committed it.

If other unexplained modifications exist, stop and report before continuing.

Do not clean them.

---

# 5. Reconnaissance Authority

M002 authorizes read-only inspection of the canonical Vocab repository.

It also authorizes narrowly bounded read-only inspection of:

- preserved historical Vocab branches in the same repository;
- the frozen historical Vocab testbed at `/home/chuck/ai-agent-tests/vocab-app`, if necessary;
- Repo Control at `/home/chuck/projects/repo-control`, only where needed to understand existing integration capabilities or determine how Vocab can exercise them.

Do not modify any of those sources.

Prefer Git-object inspection of historical branches over checking them out or changing the working branch.

Examples:

```
git show <branch>:<path>
git diff <commit-or-branch>..<commit-or-branch> -- <path>
git ls-tree -r --name-only <branch>
git log <branch> --oneline
```

Do not switch canonical working state to a historical branch merely for inspection.

---

# 6. No Implementation

Do not during M002:

- refactor application code;
- add tests;
- modify dependencies;
- create Dockerfiles;
- create Compose files;
- create database schemas;
- migrate data;
- alter Streamlit behavior;
- alter Google Sheets behavior;
- port historical testbed utilities;
- modify Repo Control;
- start or stop application services;
- build images;
- change server configuration.

The only authored output is:

`milestones/002_architecture_and_integration_reconnaissance_closeout.md`

If a small implementation seems obvious, document it as a recommendation for the next milestone rather than performing it.

---

# 7. Canonical Application Inventory

Map the actual canonical application.

At minimum inspect:

- root files;
- Python modules;
- requirements;
- configuration-related files;
- ignored/runtime files where filenames can safely be inspected;
- current test files, if any;
- documentation relevant to operation;
- application startup assumptions.

Produce a concise file-purpose map.

Identify:

- active application files;
- likely historical/dead files if any;
- runtime-generated artifacts;
- configuration boundaries;
- credential boundaries.

Do not assume every file in GitHub `main` is still part of the active execution path.

---

# 8. Application Entry and Execution Flow

Determine the current application entry point.

Map the high-level runtime flow from application launch through normal user interaction.

At minimum determine:

- how the application is launched;
- what `app.py` does;
- how Streamlit participates;
- major initialization steps;
- session-state usage;
- external-service initialization;
- how the app obtains vocabulary data;
- how quiz/test behavior is invoked;
- how pronunciation/audio behavior is invoked, if present.

Provide a human-readable flow such as:

`browser/UI → application logic → vocabulary access → external service`

but derive the actual flow from code.

---

# 9. Streamlit Coupling Analysis

Identify all meaningful Streamlit coupling.

Determine:

- which modules import Streamlit;
- which business behaviors execute directly inside Streamlit code;
- use of `st.session_state`;
- UI rendering mixed with data access;
- UI rendering mixed with quiz logic;
- UI rendering mixed with synonym logic;
- UI rendering mixed with pronunciation logic;
- Streamlit-specific secrets/configuration dependencies;
- whether useful application logic already exists independently of Streamlit.

Classify important logic as:

- UI-specific;
- framework-independent;
- mixed/coupled.

The purpose is to understand what would need separation before eventual Streamlit replacement.

Do not replace Streamlit during M002.

---

# 10. Google Sheets Integration Analysis

Map the complete Google Sheets dependency.

Determine:

- libraries used;
- authentication mechanism;
- configuration/secrets expected;
- spreadsheet/document identity mechanism;
- worksheet/tab assumptions;
- read paths;
- write paths;
- row/column structure;
- transformations between sheet data and application data;
- error handling;
- retry behavior if any;
- caching if any;
- where Google-specific concepts leak into business/UI logic.

Do not expose credential values.

Do not open or reproduce real secret contents.

If actual credentials are required to establish a fact, state that the fact could not safely be verified from repository evidence.

---

# 11. Current Vocabulary Data Model

Infer the current logical vocabulary record from code.

Document the fields the application appears to understand, such as:

- word;
- definition;
- synonyms;
- status/progress;
- test-related fields;
- timestamps;
- pronunciation-related data;
- any other persisted fields.

Distinguish:

- actual persisted fields;
- computed/transient values;
- UI/session-only values.

Do not invent a future database schema yet.

The purpose is to establish the current logical model that a future database migration must preserve or intentionally change.

---

# 12. Google Sheets Read/Write Semantics

Determine whether the current application:

- reads all vocabulary records;
- filters records remotely or locally;
- adds words;
- modifies definitions;
- modifies progress/test state;
- deletes records;
- writes synonyms;
- writes other fields.

Map each observed mutation path.

This is important because the future database migration must preserve real application behavior, not merely copy words and definitions.

If some behavior cannot be established without live credentials, distinguish code-supported intent from runtime-verified behavior.

---

# 13. Quiz/Test Workflow Analysis

Map the existing test/quiz function in enough detail to design the later multiple-choice milestone.

Determine:

- how a test begins;
- how a vocabulary item is selected;
- what the user currently sees;
- what the user currently enters;
- how correctness is determined;
- whether matching is exact, normalized, synonym-aware, or otherwise processed;
- how feedback is shown;
- whether scoring/progress is recorded;
- how the next item is chosen;
- how session state affects the flow;
- whether the test mutates Google Sheets or other persistence;
- how the session ends or resets.

Provide a deterministic current-state flow.

Do not design the final multiple-choice UX beyond identifying implementation seams and decisions required.

---

# 14. Multiple-Choice Readiness Analysis

Evaluate what would be required to change the current test behavior to multiple choice.

Identify:

- reusable existing logic;
- logic that should remain unchanged;
- likely source of distractors;
- current data limitations affecting distractor generation;
- whether synonyms complicate correct-answer determination;
- state-management implications;
- persistence implications;
- testing requirements;
- UI-specific coupling.

Recommend whether multiple choice can safely be implemented:

- directly on current architecture;
- after a small bounded refactor;
- only after a larger architecture change.

Explain why.

Do not implement it.

---

# 15. Synonym Behavior

Map current canonical synonym behavior.

Determine:

- where synonyms come from;
- how they are fetched or derived;
- how they are normalized;
- how they influence definitions or quiz behavior;
- whether ordering matters;
- whether duplicates are removed;
- whether source-word exclusion exists;
- external library/service dependencies.

Then compare this with the preserved Repo Control testbed work.

---

# 16. Historical Repo Control Testbed Evaluation

Inspect relevant historical testbed changes without modifying canonical `main`.

Known potentially useful historical files/changes include:

- `vocab_utils.py`;
- `synonym_policy.py`;
- `test_vocab_utils.py`;
- historical modifications to `app.py`.

Relevant preserved branch:

`archive/repo-control-testbed`

and/or:

`agent-test/repoctl-ui-demo`

Determine:

1. what problem each historical change attempted to solve;
2. whether the problem still exists on canonical `main`;
3. whether the implementation remains appropriate;
4. whether it should later be:
   - ignored;
   - reimplemented from concept;
   - selectively ported;
   - incorporated into a broader refactor;
5. whether the historical tests represent useful future regression coverage.

Do not cherry-pick.

Do not port code.

Do not treat historical code as automatically superior to canonical code.

---

# 17. Dependency Analysis

Inspect `requirements.txt` and relevant imports.

Classify dependencies by purpose:

- UI/framework;
- Google integration;
- vocabulary/NLP;
- pronunciation/audio;
- HTTP/network;
- testing;
- other.

Identify:

- unused-looking dependencies;
- implicit dependencies not declared;
- version pinning or lack thereof;
- dependencies likely to complicate Linux/container execution;
- dependencies tied specifically to Windows;
- dependencies tied specifically to Streamlit or Google Sheets.

Do not update dependencies.

---

# 18. Windows-to-Linux Portability Analysis

The original application was Windows-oriented.

The target host is Ubuntu Server on `henderson-server1`.

Identify current assumptions involving:

- Windows paths;
- batch files;
- VBS launchers;
- local browser behavior;
- audio playback;
- filesystem paths;
- environment variables;
- credential locations;
- desktop GUI assumptions;
- temporary files;
- shell commands;
- path separators;
- platform-specific libraries.

Classify each as:

- irrelevant to current canonical `main`;
- compatible with Linux;
- requires adaptation;
- unknown pending runtime validation.

Do not perform adaptation during M002.

---

# 19. Pronunciation / Audio Analysis

If pronunciation functionality exists, determine:

- how audio is obtained;
- whether audio is downloaded/generated;
- temporary filename/location;
- whether audio is persisted;
- how Streamlit renders/plays it;
- external network dependency;
- cleanup behavior;
- Linux/container implications;
- whether the feature is essential to the intended product.

Do not invoke paid/external services unnecessarily.

Do not generate runtime artifacts merely for reconnaissance.

---

# 20. Current Test Architecture

Determine the actual test situation on canonical `main`.

Identify:

- test files;
- test framework;
- current coverage areas;
- credential requirements;
- network requirements;
- Streamlit coupling;
- Google Sheets coupling;
- deterministic pure functions suitable for unit testing;
- important untested business behavior.

M001 found no obvious canonical tests.

Verify that more thoroughly.

Do not create tests during M002.

---

# 21. Future Test Strategy

Recommend the minimum useful test layers for the upcoming arc.

Consider:

- pure quiz/business-logic unit tests;
- synonym normalization tests;
- persistence-interface tests;
- Google Sheets adapter tests;
- database adapter tests;
- web/UI route tests after Streamlit replacement;
- container smoke/health tests;
- migration verification tests.

Keep recommendations proportional to this small application.

Do not design an enterprise-scale test architecture unnecessarily.

---

# 22. Refactor Decision

This is one of the primary outputs of M002.

Classify the recommended next architectural step as exactly one of:

## A — No pre-feature refactor required

Current architecture is sufficiently safe for the next intended change.

## B — Small bounded refactor recommended

A limited separation would materially reduce risk for multiple choice, containerization, database migration, or Streamlit replacement.

## C — Larger architecture refactor required

Current coupling is sufficiently severe that proceeding directly would create material risk.

If B or C, define:

- exact problem;
- smallest useful boundary;
- files/functions likely affected;
- behavior that must remain unchanged;
- tests required before/with the refactor;
- what must explicitly remain out of scope.

Avoid generic recommendations such as "clean up the code."

---

# 23. Containerization Reconnaissance

Determine what is required to containerize the current application **as it exists**, without first replacing Streamlit or Google Sheets.

Inspect:

- Python runtime requirements;
- application startup command;
- expected listening port;
- network dependencies;
- credentials/configuration;
- generated files;
- writable filesystem requirements;
- audio/temp requirements;
- dependency installation;
- health-check possibilities;
- persistent state;
- external Google access;
- likely image contents.

Do not create container files.

---

# 24. Container Baseline Recommendation

Recommend the smallest safe container baseline.

The expected conceptual direction is:

`host Git repository`

→ `container image`

→ `Vocab runtime container`

with source editing remaining host-side.

Recommend:

- what should be in the image;
- what should remain external;
- how credentials should be injected conceptually;
- whether any volume is needed;
- what port would likely be exposed;
- how a health check could work;
- how the source commit SHA could be embedded or exposed.

Do not lock details unsupported by current evidence.

---

# 25. Database Migration Reconnaissance

Without choosing or creating a database, determine what the future persistence layer must support.

Identify:

- current logical records;
- read operations;
- write operations;
- uniqueness assumptions;
- ordering assumptions;
- data types;
- optional fields;
- external IDs;
- synchronization assumptions;
- migration verification needs.

Determine whether the current application has a separable persistence boundary or whether one should be introduced first.

---

# 26. Database Technology Recommendation

Based on the actual application needs, assess appropriate options for the server-hosted database.

At minimum consider:

- SQLite;
- PostgreSQL.

You may mention another technology only if the current requirements materially justify it.

Evaluate:

- simplicity;
- concurrency needs;
- container/runtime topology;
- backups;
- future external access;
- migration;
- operational burden;
- testability.

Make a recommendation, but do not implement or provision it.

The fact that `henderson-server1` already hosts PostgreSQL-capable workloads may be relevant operational context, but do not assume Vocab should share another application's database instance or credentials.

---

# 27. Streamlit Replacement Reconnaissance

Determine what functionality a future Streamlit replacement must provide.

Map current requirements such as:

- pages/views;
- forms;
- buttons;
- session state;
- quiz interaction;
- vocabulary management;
- audio;
- feedback;
- data mutations;
- navigation;
- user state.

Separate actual current requirements from speculative future features.

---

# 28. Replacement Framework Recommendation

Based on the small application's real needs, recommend a reasonable future replacement approach.

Consider simplicity and maintainability.

Possible categories may include:

- lightweight Python server-rendered web framework;
- Python API + modest frontend;
- another architecture only if justified.

Do not select a complex stack merely because it is modern.

Explain:

- why the recommendation fits this application;
- what existing Python logic could be retained;
- what Streamlit-specific code would be replaced;
- implications for containerization and external access.

This is a recommendation only.

---

# 29. Server Runtime Reconnaissance

Perform read-only inspection only where needed to understand deployment constraints on `henderson-server1`.

Do not broadly inventory the server.

Relevant facts may include:

- Docker availability;
- Compose availability;
- current host architecture;
- port conflicts for a proposed Vocab baseline;
- whether an obvious Vocab container/service already exists.

Do not inspect unrelated application internals.

Do not modify Docker or host state.

Do not stop/start anything.

---

# 30. External Access Boundary

External access is a later phase.

For M002, identify only the architectural implications that current application design creates for future secure external access.

Do not:

- open ports;
- change UFW;
- configure router forwarding;
- configure reverse proxies;
- configure tunnels;
- register domains;
- add authentication.

State what later decisions will be required.

---

# 31. Repo Control Integration Reconnaissance

Evaluate how the planned Vocab arc can exercise existing Repo Control capabilities.

Distinguish:

## Existing capabilities that should already apply

Examples may include:

- repository status;
- Context;
- Snapshots;
- Comparisons;
- Product Owner review;
- guarded Stage;
- guarded Commit.

## Future capabilities that real Vocab work may expose a need for

Examples may include:

- repository chooser/binding;
- build identity;
- image/source SHA relationship;
- running container identity;
- deployed revision;
- runtime health;
- deployment comparison;
- guarded deployment.

Do not assume these future capabilities must be built.

Identify the real workflow event that would justify each one.

---

# 32. Repo Control Test Plan for Vocab

Recommend how Repo Control should be exercised during the upcoming Vocab milestones.

At minimum address:

- when Context should be used;
- when Snapshot should be created;
- when Comparison should be reviewed;
- when Product Owner review is useful;
- Stage/Commit workflow;
- what evidence should be preserved;
- how the container baseline can later expose runtime/deployment gaps.

Keep Repo Control usage useful rather than ceremonial.

---

# 33. Human-Readable Workflow

Produce a proposed end-to-end development flow for a normal future Vocab change.

For example, conceptually:

`Product Owner requirement`

→ `Architect milestone`

→ `Coder reconnaissance/context`

→ `implementation`

→ `tests`

→ `Repo Control review evidence`

→ `Stage Plan`

→ `Product Owner approval`

→ `Snapshot`

→ `Commit Plan`

→ `Product Owner approval`

→ `commit`

→ later `build/deploy`

→ `runtime verification`.

Adjust this to the actual Repo Control capabilities and Vocab needs found during reconnaissance.

---

# 34. Scope-Creep Analysis

Explicitly identify tempting work that should **not** be pulled into the next milestone.

Examples may include:

- multiple choice during a refactor;
- database migration during containerization;
- Streamlit replacement during database migration;
- external access during local deployment;
- Repo Control deployment mutation before manual deployment is stable.

This section should help the Architect keep future implementation prompts bounded.

---

# 35. Recommended Milestone Roadmap

Produce a concrete recommended milestone sequence after M002.

Do not merely repeat the broad roadmap document.

Use the reconnaissance findings to determine the actual sequence.

For each recommended milestone provide:

- milestone purpose;
- implementation vs reconnaissance;
- major files/components;
- main acceptance evidence;
- whether Repo Control should be exercised;
- key stop condition.

The first recommended milestone after M002 should be especially precise.

---

# 36. M003 Decision

Conclude with a specific recommendation for M003.

Choose one primary direction:

- bounded refactor;
- containerized current-app baseline;
- multiple-choice implementation;
- another narrowly justified prerequisite.

Explain why this is the safest next step.

Do not implement M003.

---

# 37. Evidence Standards

For important findings, cite:

- file;
- function/class/symbol where applicable;
- line number or approximate line range where practical;
- Git branch/commit for historical evidence;
- exact command for deterministic repository/runtime facts.

Distinguish clearly:

- observed fact;
- inference;
- recommendation.

Do not present inferred architecture as observed fact.

---

# 38. No Secret Exposure

Do not reproduce:

- service-account JSON;
- API keys;
- tokens;
- passwords;
- private keys;
- Streamlit secret values;
- database credentials.

Filename/configuration-reference evidence is sufficient.

If credentials prevent runtime verification, state the limitation.

---

# 39. Required Closeout

Create exactly:

`milestones/002_architecture_and_integration_reconnaissance_closeout.md`

Do not create a milestone subdirectory.

All Vocab milestone prompts and closeouts reside directly under:

`/home/chuck/projects/vocab-app/milestones/`

The closeout must include the following sections.

## 1. Executive conclusion

Concise architecture conclusion and M003 recommendation.

## 2. Starting repository evidence

Branch, HEAD, upstream, ahead/behind, working-tree state.

## 3. Canonical application inventory

Active files and responsibilities.

## 4. Current runtime flow

Human-readable execution/data flow.

## 5. Streamlit coupling

Observed coupling and replacement implications.

## 6. Google Sheets integration

Authentication boundary, reads, writes, data assumptions, coupling.

## 7. Current logical vocabulary model

Persisted vs computed/session state.

## 8. Current quiz/test workflow

Deterministic current behavior.

## 9. Multiple-choice readiness

Required changes and architectural dependency.

## 10. Synonym behavior

Canonical behavior and dependencies.

## 11. Historical testbed evaluation

Useful historical changes and disposition recommendation.

## 12. Dependency analysis

Current dependencies and portability concerns.

## 13. Windows-to-Linux portability

Observed issues and classifications.

## 14. Pronunciation/audio behavior

Current architecture and container implications.

## 15. Current test architecture

Existing tests, gaps, external dependencies.

## 16. Future test strategy

Minimum useful testing layers.

## 17. Refactor decision

A / B / C with exact rationale.

## 18. Containerization findings

Minimum current-app container requirements.

## 19. Container baseline recommendation

Proposed bounded topology and acceptance evidence.

## 20. Persistence/database requirements

Operations and migration constraints.

## 21. Database recommendation

Technology recommendation and rationale.

## 22. Streamlit replacement requirements

Actual UI/runtime requirements.

## 23. Replacement framework recommendation

Recommended direction and rationale.

## 24. Server/runtime constraints

Only relevant read-only findings.

## 25. External-access implications

Later decisions required; no implementation.

## 26. Repo Control existing-capability map

What can already be used.

## 27. Repo Control future-gap hypotheses

Potential gaps and the real event that would justify them.

## 28. Repo Control Vocab test plan

How upcoming work should exercise the control plane.

## 29. Proposed normal development workflow

Code-to-review-to-commit-to-runtime progression.

## 30. Scope-creep exclusions

Work explicitly deferred.

## 31. Recommended milestone roadmap

Evidence-based sequence after M002.

## 32. M003 recommendation

Exact next milestone and scope boundary.

## 33. Limitations / unresolved questions

Anything not safely established.

## 34. Final repository state

Capture:

```
git branch --show-current
git rev-parse HEAD
git status --short
git rev-list --left-right --count HEAD...origin/main
```

---

# 40. Closeout Quality

The closeout should be comprehensive enough to guide the next several milestones without forcing later coders to rediscover the same architecture.

However:

- do not dump large source files;
- do not reproduce credentials;
- do not copy every import or every function;
- do not inflate the closeout with generic software advice;
- do not recommend unnecessary enterprise architecture.

Prefer specific evidence and decisions.

The most important outputs are:

1. actual current architecture;
2. refactor decision;
3. container baseline requirements;
4. multiple-choice implementation readiness;
5. database migration boundary;
6. Streamlit replacement boundary;
7. useful historical testbed work;
8. realistic Repo Control integration opportunities;
9. exact M003 recommendation.

---

# 41. Stop Conditions

Stop and report before completing reconnaissance if:

- canonical repository identity contradicts M001;
- unexplained dirty application state exists;
- unrelated histories appear merged;
- credentials would need to be exposed;
- required inspection would mutate production/runtime state;
- Repo Control modification appears necessary merely to complete reconnaissance;
- the actual application is materially different from the controlling project context in a way that changes the intended roadmap.

Provide evidence and await guidance rather than repairing the issue.

---

# 42. Expected Outcome

A successful M002 should allow the Architect/Product Owner to answer, with evidence:

- What does the current Vocab App actually look like?
- Where is its business logic?
- How tightly is it coupled to Streamlit and Google Sheets?
- What useful work exists in the historical Repo Control testbed?
- Should we refactor before feature work?
- Can we containerize the current app safely?
- What does multiple choice really require?
- What must the future database preserve?
- What would replacing Streamlit entail?
- What should M003 be?
- How should the next real Vocab changes exercise Repo Control?

No application implementation is required to answer those questions.

---

# 43. Working Principle

> Understand the real application before changing it.

M002 exists to replace assumptions with evidence and establish the smallest safe sequence for the Vocab App's evolution.

---

**End of `002_architecture_and_integration_reconnaissance_prompt.md`**
