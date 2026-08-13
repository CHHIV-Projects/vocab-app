# Vocab App — Project Workflow v1

**Document:** `project_workflow_v1.md`  
**Project:** Vocab App  
**Status:** Active controlling workflow  
**Version:** 1.0  
**Primary repository:** `/home/chuck/projects/vocab-app`  
**Primary branch:** `main`

---

# 1. Purpose

This document defines the working methodology for development, testing, review, Git control, and deployment evolution of the Vocab App.

The Vocab App has two purposes:

1. It is a real application that will be improved and ultimately self-hosted on `henderson-server1`.
2. It is a controlled integration testbed for Repo Control, allowing Repo Control to be exercised against real application development and deployment work.

The workflow is intended to remain:

- milestone-driven;
- evidence-based;
- understandable to the Product Owner;
- safe for AI-assisted coding;
- resistant to unnecessary scope expansion;
- explicit about mutation authority;
- suitable for increasingly automated Repo Control integration.

The process should remain proportional to the size and risk of the Vocab App. Practices inherited from larger projects should be used where they add safety or clarity, not copied mechanically.

---

# 2. Core Roles

The project uses three primary roles.

## 2.1 Product Owner

The Product Owner defines product intent and provides final acceptance.

Responsibilities include:

- defining desired user behavior;
- deciding product priorities;
- approving material architectural decisions;
- answering business and UX questions;
- performing live browser/application validation when appropriate;
- approving significant Git or runtime mutations when required;
- accepting or rejecting milestone results;
- deciding whether a discovered issue belongs in the current milestone or future work.

The Product Owner is not expected to make low-level implementation decisions unless a decision affects product behavior, architecture, safety, or project scope.

---

## 2.2 Architect

ChatGPT normally serves as Architect.

Responsibilities include:

- maintaining the project roadmap;
- defining milestone boundaries;
- determining when reconnaissance is warranted;
- interpreting reconnaissance findings;
- deciding whether architectural refactoring is justified;
- composing coder prompts;
- resolving coder questions and escalation findings;
- reviewing implementation evidence and closeouts;
- guiding Product Owner validation;
- preserving separation between Vocab concerns and Repo Control concerns;
- identifying reusable lessons for Repo Control without making Vocab dependent on Repo Control-specific hacks.

The Architect should prefer the smallest milestone that produces a coherent, testable result.

The Architect should not prescribe implementation details that repository evidence has not yet established.

---

## 2.3 Coder

The coding agent performs repository reconnaissance and implementation under an approved milestone prompt.

Responsibilities include:

- reading the controlling documents;
- inspecting the repository as required by the milestone;
- reporting architectural conflicts or ambiguity before making unsafe assumptions;
- implementing the smallest safe change that satisfies the approved scope;
- preserving existing behavior unless the milestone explicitly changes it;
- adding or updating tests as appropriate;
- running required validation;
- reporting literal evidence;
- producing the milestone closeout.

The Coder does not independently redefine product scope or architecture.

---

# 3. Sources of Authority

When sources disagree, use the following hierarchy.

## 3.1 Current milestone prompt

The current approved milestone prompt controls the immediate work.

It may intentionally narrow the broader roadmap.

---

## 3.2 Explicit Product Owner decisions

Product Owner decisions made during the milestone override older assumptions when clearly applicable.

Material decisions should be captured in the milestone closeout and, when appropriate, incorporated into later controlling documents.

---

## 3.3 Current repository state and verified runtime evidence

Actual code, tests, Git state, database state, container/runtime state, and directly observed application behavior take precedence over assumptions about how the system works.

When documentation conflicts with verified implementation evidence, the discrepancy must be reported.

Do not silently choose whichever source is more convenient.

---

## 3.4 Project context and architecture documents

These describe accepted project direction and architectural boundaries.

They guide milestone design but do not authorize work outside the current milestone.

---

## 3.5 Roadmap

The roadmap describes intended sequencing and future direction.

It is not an implementation specification.

Future roadmap items must not be implemented merely because they appear nearby.

---

# 4. Canonical Repositories and Boundaries

## 4.1 Vocab App

Canonical working repository:

`/home/chuck/projects/vocab-app`

Canonical branch:

`main`

Canonical GitHub repository:

`CHHIV-Projects/vocab-app`

The current GitHub history remains the authoritative Vocab application lineage.

---

## 4.2 Historical Repo Control testbed lineage

Earlier sanitized Vocab test work was created under a separate Git history.

That history is preserved for reference, including:

`archive/repo-control-testbed`

and associated historical `agent-test/*` branches.

This historical lineage may be inspected during reconnaissance.

It must not be merged into canonical `main` merely to recover experimental work.

Useful changes from that history should be deliberately evaluated and ported when justified.

---

## 4.3 Repo Control

Repo Control is a separate project and control plane.

Canonical repository:

`/home/chuck/projects/repo-control`

Vocab milestones may use Repo Control according to its approved capabilities.

A Vocab milestone must not modify Repo Control code merely because Repo Control lacks a desired capability.

If Vocab work exposes a legitimate Repo Control deficiency or missing capability:

1. preserve the Vocab evidence;
2. identify the gap;
3. stop or continue Vocab work according to milestone safety;
4. raise the issue to the Architect/Product Owner;
5. create a separate Repo Control milestone if a Repo Control change is approved.

This separation is intentional.

Vocab should expose real control-plane requirements rather than cause Repo Control to accumulate Vocab-specific behavior.

---

# 5. Milestone Model

Vocab development is milestone-driven.

Each milestone should have:

1. a defined objective;
2. explicit in-scope work;
3. explicit exclusions when useful;
4. required validation;
5. escalation conditions;
6. a closeout.

Milestones should be large enough to produce a meaningful result but small enough to review and validate confidently.

Unrelated improvements should not be added merely because the coder encounters them.

---

# 6. Milestone Numbering

Vocab uses its own milestone sequence independent of Repo Control.

Example:

- Vocab 001 — repository/project-control foundation
- Vocab 002 — architecture and integration reconnaissance
- Vocab 003 — subsequent approved work

Repo Control continues to use its own milestone numbering.

A Vocab milestone number and a Repo Control milestone number do not imply a relationship unless explicitly documented.

---

# 7. Reconnaissance vs. Implementation

## 7.1 Reconnaissance

Use a reconnaissance milestone when important implementation facts are not yet established.

Typical reasons include:

- unfamiliar architecture;
- uncertain dependency boundaries;
- unclear persistence behavior;
- framework coupling;
- database migration planning;
- containerization planning;
- security-sensitive changes;
- significant refactoring decisions;
- interaction between Vocab and Repo Control that has not yet been proven.

Reconnaissance should answer questions, identify boundaries, and recommend the smallest safe implementation path.

Unless explicitly authorized, reconnaissance is read-only.

---

## 7.2 Implementation

Once the architecture and scope are sufficiently understood, implementation prompts should be focused.

Implementation should:

- inspect only what is necessary;
- reuse existing behavior and abstractions where appropriate;
- avoid reopening settled architecture without evidence;
- make the smallest coherent change;
- test the changed behavior;
- stop if the locked assumptions prove materially false.

Implementation prompts should generally be shorter than reconnaissance prompts.

---

# 8. Refactoring Policy

Refactoring is not a default milestone goal.

A refactor is justified when repository evidence shows that it materially improves one or more of:

- safety;
- testability;
- separation of concerns;
- migration risk;
- maintainability needed for approved near-term work;
- replacement of a tightly coupled dependency.

Refactoring should not be performed merely for style, elegance, modernization, or theoretical cleanliness.

For the planned Vocab evolution, a bounded refactor may be appropriate if reconnaissance demonstrates harmful coupling among:

- Streamlit UI;
- quiz/test logic;
- Google Sheets access;
- vocabulary data access;
- configuration;
- business logic.

Any approved refactor must preserve behavior except where the milestone explicitly changes it.

---

# 9. Prompt Workflow

The normal milestone lifecycle is:

1. Architect defines the milestone.
2. Architect writes the coder prompt.
3. Product Owner saves the prompt in the repository.
4. Prompt is reviewed as needed.
5. Prompt is committed before implementation begins.
6. Coder reads the committed prompt and controlling documents.
7. Coder performs required preflight/reconnaissance.
8. Coder raises blocking questions before unsafe implementation.
9. Coder implements the approved scope.
10. Coder runs required validation.
11. Product Owner performs live validation when required.
12. Coder writes the closeout.
13. Architect reviews the closeout.
14. Product Owner stages and commits the accepted milestone.
15. Push occurs only when authorized.

The committed prompt establishes a traceable starting contract for the milestone.

---

# 10. Prompt and Closeout Naming

Use matching prompt and closeout names whenever practical.

Recommended pattern:

`<milestone>_<short_name>_prompt.md`

and:

`<milestone>_<short_name>_closeout.md`

Example:

`002_architecture_and_integration_reconnaissance_prompt.md`

`002_architecture_and_integration_reconnaissance_closeout.md`

Milestone files should live under the corresponding milestone directory.

---

# 11. Coder Preflight

Before modifying code, the Coder should establish the relevant starting state.

At minimum when Git mutation is involved:

- repository path;
- current branch;
- current HEAD;
- upstream/tracking state when relevant;
- working-tree state.

Unexpected pre-existing changes must not be silently deleted, reset, staged, or absorbed into the milestone.

If the starting state conflicts with the milestone assumptions, stop and report.

---

# 12. Git Discipline

Git history is part of the project evidence.

## 12.1 General rules

Prefer:

- explicit branches;
- explicit HEADs;
- exact-file staging;
- review before commit;
- meaningful commit messages;
- clean milestone boundaries.

Avoid:

- destructive resets without explicit approval;
- force pushes without explicit approval;
- broad staging such as `git add .` when exact-file staging is practical;
- silently incorporating unrelated files;
- rewriting accepted history merely for cosmetic reasons.

---

## 12.2 Exact-file staging

At milestone closeout, stage only the files that belong to the accepted milestone.

The Product Owner should be able to inspect:

- staged file names;
- staged diff/stat;
- whitespace/error checks;
- resulting status.

Unknown local artifacts should remain separate until explicitly classified.

---

## 12.3 Push authority

A successful commit does not automatically authorize a push.

Push only when the Product Owner or current milestone explicitly authorizes it.

---

# 13. Repo Control in the Development Workflow

Repo Control is intended to become part of the normal Vocab development process.

As its approved capabilities allow, the workflow may include:

1. inspect repository state;
2. identify relevant context;
3. capture snapshot evidence;
4. compare meaningful states;
5. perform local AI review where useful;
6. prepare Stage;
7. review the immutable Stage plan;
8. explicitly approve Stage;
9. capture matching post-Stage evidence;
10. prepare Commit;
11. review the immutable Commit plan;
12. explicitly approve Commit;
13. verify resulting repository state.

Repo Control evidence supplements normal code/test evidence.

It does not replace tests or direct runtime validation.

---

# 14. Deterministic Evidence and AI Assessment

Repo Control may expose both deterministic evidence and AI-generated assessment.

These have different authority.

## Deterministic evidence

Examples:

- Git branch;
- HEAD;
- staged/unstaged state;
- file relationships;
- snapshots;
- comparisons;
- test results;
- container identity;
- deployed Git SHA;
- health checks.

These should be reproducible from defined inputs.

## AI assessment

Examples:

- code-quality observations;
- architectural concerns;
- suggested risk areas;
- interpretation of a comparison.

AI assessment is advisory.

It must not silently become mutation authority.

When deterministic evidence and AI interpretation disagree, preserve the deterministic evidence and investigate the disagreement.

---

# 15. Code State vs. Runtime State

Git state and deployed application state are distinct.

A commit does not mean the application has been deployed.

A deployment does not mean it is healthy.

A healthy runtime does not by itself prove which code is running unless runtime identity is established.

The project should increasingly preserve explicit lineage among:

`source change → commit → build → deployment → runtime verification`

Future Repo Control integration should be designed around that distinction.

---

# 16. Testing

Every implementation milestone should define appropriate validation.

Validation may include:

- unit tests;
- integration tests;
- direct service checks;
- database checks;
- container health checks;
- browser validation;
- Repo Control evidence;
- Product Owner acceptance.

Tests should target the changed behavior and relevant regressions.

Full regression testing should be used when the risk or scope warrants it.

Test commands and literal outcomes should be recorded in the closeout.

---

# 17. Product Owner Live Validation

Some behavior is best validated by the Product Owner.

Examples include:

- quiz behavior;
- multiple-choice UX;
- browser workflow;
- application accessibility;
- data correctness;
- deployment behavior visible to an end user.

When live validation is required:

1. coder reaches a stable validation point;
2. coder stops mutation;
3. Product Owner performs the agreed test;
4. unexpected behavior is preserved and investigated;
5. implementation resumes only after the issue is classified.

Do not conceal contradictory live evidence merely because automated tests pass.

---

# 18. Closeout Requirements

Each implementation milestone should produce one authoritative closeout.

The closeout should record, as applicable:

- objective;
- starting branch/HEAD;
- files changed;
- implementation summary;
- architectural decisions;
- tests run;
- literal test results;
- Product Owner validation;
- Repo Control evidence;
- known limitations;
- deferred work;
- final Git state;
- recommended next step.

Closeouts should distinguish:

- verified facts;
- architectural interpretation;
- future recommendations.

Do not reconstruct missing historical evidence and present it as observed fact.

If evidence was not retained, state that plainly.

---

# 19. Escalation Protocol

The Coder should stop and report when:

- repository state differs materially from the prompt;
- implementation requires architecture outside approved scope;
- a supposedly reusable abstraction does not exist;
- a destructive migration appears necessary;
- credentials or secrets would need to enter Git;
- a database/runtime mutation exceeds authorization;
- a Repo Control code change appears necessary during a Vocab milestone;
- test failures suggest broader regression;
- the requested change cannot be implemented safely within the locked scope.

The escalation should include:

1. what was discovered;
2. why it matters;
3. evidence;
4. smallest safe options;
5. recommended path.

Do not silently choose a broader option.

---

# 20. Secrets and Configuration

Secrets must not be committed to Git.

Examples include:

- service-account credentials;
- database passwords;
- private keys;
- API secrets;
- production environment files.

Use approved external configuration mechanisms.

Repository configuration may include safe templates such as `.env.example`, but not real credentials.

AI coding tools must not be given unnecessary access to credential files.

---

# 21. Database Safety

The planned Vocab evolution includes migration from Google Sheets to a server-hosted database.

Database changes must distinguish:

- schema changes;
- data migration;
- application code changes;
- test fixtures;
- persistent runtime data.

Destructive database operations require explicit authorization.

Migration work should preserve recoverability and verify data correctness.

The database must not be treated as disposable merely because the application runtime is containerized.

---

# 22. Container and Runtime Safety

Containerization is an application-runtime concern, not a replacement for Git repository management.

The Vocab Git repository should remain host-visible and independently inspectable.

Runtime containers should be reproducible from committed source and versioned deployment definitions.

Persistent data and secrets should remain outside disposable application containers.

Docker mutation such as:

- build;
- create;
- restart;
- replace;
- remove;
- compose up/down;

must occur only when authorized by the milestone or Product Owner.

---

# 23. Deployment Philosophy

The project should first establish manual, deterministic deployment behavior before automating it through Repo Control.

Preferred progression:

1. understand application runtime;
2. establish reproducible container baseline;
3. establish deterministic health/runtime evidence;
4. associate runtime with exact source commit;
5. expose deployment state read-only in Repo Control;
6. design guarded deployment preparation;
7. require explicit approval;
8. execute narrowly;
9. verify runtime health and code identity.

Do not automate an unstable manual process.

---

# 24. Current Product Direction

The current intended Vocab evolution is:

## Phase A — Project foundation

Establish:

- canonical repository;
- project workflow;
- coding-agent rules;
- project context;
- integration roadmap;
- milestone structure.

## Phase B — Architecture reconnaissance

Understand:

- Streamlit coupling;
- Google Sheets coupling;
- quiz logic;
- data-access boundaries;
- configuration;
- tests;
- container/runtime needs;
- value of bounded refactoring.

## Phase C — Optional bounded refactor

Perform only if reconnaissance demonstrates material value.

## Phase D — Container runtime baseline

Run the existing application reproducibly on `henderson-server1`.

## Phase E — Multiple-choice testing

Change the vocabulary testing experience to multiple choice.

## Phase F — Server database

Move vocabulary words/definitions from Google Sheets to a database hosted on `henderson-server1`.

## Phase G — Streamlit replacement

Remove Streamlit as the application framework/runtime and operate the Vocab application directly from `henderson-server1`.

## Phase H — Access

Support:

1. local/LAN access;
2. later, controlled secure external access.

The exact implementation technology for later phases should be selected from reconnaissance and implementation evidence rather than assumed in advance.

---

# 25. Repo Control Integration Principle

The Vocab App is a testbed for discovering what Repo Control needs in real application development.

Therefore:

> Use real Vocab work to expose real Repo Control requirements.

Do not add Repo Control features solely because they sound useful.

When a real workflow exposes a gap:

1. capture the gap;
2. classify it;
3. decide whether the Vocab milestone can continue;
4. create a separate Repo Control milestone when warranted;
5. validate the generalized Repo Control solution against Vocab.

The goal is a reusable control plane, not a Vocab-specific automation layer.

---

# 26. Scope-Creep Control

During implementation, classify newly discovered work as one of:

- required for current milestone;
- defect caused by current milestone;
- blocker requiring escalation;
- valuable future work;
- unrelated work.

Only the first two should normally be implemented without a new Product Owner decision.

Future work should be recorded rather than opportunistically absorbed.

---

# 27. Workflow Evolution

This workflow is expected to evolve as Vocab becomes more sophisticated and Repo Control gains capabilities.

Changes should be deliberate.

When a material workflow change is accepted:

1. create a new workflow version;
2. preserve the previous version in Git history;
3. explain the material change;
4. update coder context references;
5. use the new version prospectively.

Do not silently rewrite project history.

---

# 28. Working Principle

The project should optimize for:

> **clear intent → bounded work → deterministic evidence → explicit review → controlled mutation → verified result**

The Vocab App should remain small enough to move quickly while disciplined enough to serve as a meaningful proving ground for Repo Control.

---

**End of `project_workflow_v1.md`**
