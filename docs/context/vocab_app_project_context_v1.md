# Vocab App — Project Context v1

**Document:** `vocab_app_project_context_v1.md`  
**Project:** Vocab App  
**Status:** Active controlling project context  
**Version:** 1.0  
**Primary repository:** `/home/chuck/projects/vocab-app`  
**Primary branch:** `main`  
**Canonical GitHub repository:** `CHHIV-Projects/vocab-app`

---

# 1. Purpose

This document records the current authoritative context for the Vocab App project.

It exists so that future Architect and Coder chats do not need to reconstruct the project from conversational history.

This document describes:

- what the Vocab App is;
- the current repository and Git history situation;
- the current server location;
- the relationship between Vocab and Repo Control;
- the current Product Owner goals;
- the intended evolution of the application;
- the architectural questions still requiring reconnaissance;
- the boundaries that must remain protected.

This document describes current truth and accepted direction.

It is not itself an implementation prompt.

---

# 2. Product Overview

The Vocab App is a small vocabulary-learning application originally developed as a Windows-oriented personal application.

The current application historically uses:

- Python;
- Streamlit for the user interface/runtime;
- Google Sheets as the vocabulary/definition data source.

The Product Owner intends to evolve it into a more conventional self-hosted application running on `henderson-server1`.

The project is intentionally small enough to support rapid development while realistic enough to exercise:

- application refactoring;
- feature work;
- persistence migration;
- containerization;
- deployment;
- runtime verification;
- Repo Control integration.

---

# 3. Product Owner Goals

The Product Owner has three primary functional/architectural goals for the Vocab App.

## 3.1 Multiple-choice quiz behavior

Change the existing test/quiz function so that vocabulary testing uses multiple-choice questions.

The exact UX and scoring behavior will be defined in a later milestone.

This is intended to be the first visible product change exercised through the mature Repo Control workflow.

---

## 3.2 Move vocabulary data from Google Sheets to a server database

Current vocabulary words and definitions are stored in Google Sheets.

The target is to store them in a database hosted on `henderson-server1`.

The exact database technology, schema, migration method, and operational model are not yet locked.

Those decisions should come from reconnaissance and implementation evidence.

The future database must support:

- persistent vocabulary records;
- definitions;
- application reads/writes required by the product;
- reliable backups;
- deterministic testing;
- credentials outside Git;
- persistence independent of disposable application containers.

---

## 3.3 Remove Streamlit and self-host the application

The Product Owner ultimately wants the Vocab App to no longer depend on Streamlit as the application framework/runtime.

The target is a self-hosted application running on `henderson-server1`.

Desired access progression:

1. application runs on the server;
2. accessible from the local network;
3. later accessible externally through a controlled secure method.

The replacement web framework/runtime has not yet been selected.

Do not assume a specific framework before reconnaissance establishes the current application structure and migration needs.

---

# 4. Optional Refactor Direction

A bounded refactor may be inserted before the larger product changes if reconnaissance demonstrates that it materially reduces risk.

Potential problematic coupling to investigate includes:

- Streamlit UI code mixed with business logic;
- quiz logic mixed with data-access code;
- direct Google Sheets calls throughout the application;
- configuration mixed with application logic;
- synonym/quiz utilities embedded directly in UI code;
- insufficient boundaries for deterministic testing.

The project does not authorize refactoring merely for aesthetics or modernization.

Any refactor must have a clear purpose tied to approved near-term work.

---

# 5. Canonical Repository

The authoritative Vocab repository is:

`/home/chuck/projects/vocab-app`

The authoritative application branch is:

`main`

The canonical GitHub repository is:

`CHHIV-Projects/vocab-app`

Current canonical `main` was restored from the existing GitHub history rather than from the separate Repo Control testbed history.

At the time this project-control foundation was established:

`main` and `origin/main` were aligned at:

`f7693897223b3aaaf72e6bc08e6b41db779a803a`

This SHA should be treated as historical foundation context, not as a permanently fixed current HEAD.

Future work must always inspect the actual current repository state.

---

# 6. Repository Reconciliation History

Before this project-control foundation was established, a sanitized Vocab copy had been created under:

`/home/chuck/ai-agent-tests/vocab-app`

That copy was used as a disposable fixture while Repo Control itself was being developed.

It had a completely independent Git history from the real GitHub Vocab repository.

Its root commit was:

`ff00a5c919c6bacff97699343181e092529fc952`

The Repo Control testbed later reached:

`1281d7925b04b0d32bd6107b989af21221f1122c`

The histories were intentionally **not merged**.

Instead, the real GitHub Vocab history was restored as canonical `main`, while the experimental history was preserved locally for reference.

---

# 7. Preserved Historical Testbed Branches

The new canonical repository contains preserved local references to the earlier testbed history.

Relevant branches include:

- `archive/repo-control-testbed`
- `archive/sanitized-testbed-base`
- `archive/original-sanitized-main`
- `agent-test/devstral-existing-file-edit`
- `agent-test/devstral-first-edit`
- `agent-test/devstral-synonym-refactor`
- `agent-test/gpt-oss-synonym-refactor`
- `agent-test/repoctl-ui-demo`

These branches preserve useful historical evidence.

They are not canonical application history.

Do not merge them into `main` simply to recover their changes.

Their code may be inspected during reconnaissance.

Useful ideas should be deliberately evaluated and reimplemented or ported only when appropriate for current canonical code.

---

# 8. Historical Repo Control Testbed Work

The sanitized testbed was used extensively while developing Repo Control.

It exercised:

- deterministic repository status;
- Context;
- Snapshots;
- Comparisons;
- local AI review;
- guarded Stage;
- guarded Commit;
- Product Owner browser approval.

Historical testbed commits included:

- synonym normalization/refactor work;
- test additions;
- `vocab_utils.py`;
- `synonym_policy.py`;
- changes to `app.py`.

These changes should not be assumed to belong in current `main`.

They are valuable reference material for later reconnaissance.

---

# 9. Current Canonical Tree vs. Historical Testbed

A comparison between current GitHub `main` and the preserved testbed showed that the testbed contains a mixture of:

## Legacy/test-copy material

Examples included:

- `VocabLauncher.vbs`;
- `app - stable.py`;
- `app v-1.py`;
- `app v-2.py`;
- `find_path.py`;
- `start vocab app.bat`;
- `TEST_COPY_NOTICE.txt`.

These should not be reintroduced merely because they exist in the testbed.

## Potentially useful experimental work

Examples included:

- modifications to `app.py`;
- `vocab_utils.py`;
- `synonym_policy.py`;
- `test_vocab_utils.py`.

The value of these files/changes must be evaluated against current canonical `main`.

---

# 10. Current Repository Hygiene

The canonical repository intentionally excludes local runtime and credential artifacts.

Current local project hygiene includes:

- `.gitignore`;
- `.aiderignore`.

Local/generated artifacts should remain untracked, including:

- Aider chat/input history;
- Aider tag cache;
- `__pycache__/`;
- `.venv/`;
- Python bytecode;
- local `.env` files;
- real credential files.

---

# 11. Credential Boundaries

Historical versions of the Vocab App used credential-oriented files associated with Google Sheets and Streamlit.

Protected examples include:

- `service_account.json`;
- `.streamlit/`;
- `.env`;
- private keys;
- tokens;
- local authentication utilities.

The canonical repository must not contain real secrets.

The earlier sanitized testbed intentionally excluded credential material.

The same principle remains active for the real project.

---

# 12. `.aiderignore`

The repository retains `.aiderignore` as an AI-tool safety boundary.

It currently protects credential-oriented and non-source files such as:

- `service_account.json`;
- `.streamlit/`;
- `.env`;
- `get_secrets.py`;
- `test_connection.py`;
- pronunciation/runtime artifacts;
- caches;
- virtual environments.

AI coding tools should respect these exclusions.

If work appears to require an excluded credential file, stop and request explicit guidance rather than bypassing the exclusion.

---

# 13. Server Environment

Primary server:

`henderson-server1`

Operating system:

Ubuntu Server 24.04 LTS

The server is the intended long-term runtime host for the Vocab App.

The repository resides at:

`/home/chuck/projects/vocab-app`

The server already supports Docker and other application services.

Vocab development must remain isolated from unrelated workloads.

---

# 14. Shared-Host Context

`henderson-server1` is not dedicated exclusively to Vocab.

It also hosts other important workloads, including Repo Control and other applications/services.

Therefore Vocab work must not casually modify:

- unrelated containers;
- firewall configuration;
- unrelated ports;
- mounts;
- Docker networks;
- system services;
- NAS configuration;
- unrelated databases;
- Photo Organizer resources.

Any host-level change must be explicitly scoped.

---

# 15. Repo Control

Repo Control is a separate project located at:

`/home/chuck/projects/repo-control`

Repo Control is intended to become a generic development/control-plane tool.

Current capabilities developed before this Vocab arc include:

- deterministic Git status;
- working-tree classification;
- upstream information;
- Context;
- Snapshots;
- Comparisons;
- local AI/Product Owner review;
- guarded Stage preparation/review/approval;
- guarded Commit preparation/review/approval.

The Vocab App will now be used as a real application testbed for those capabilities and future Repo Control evolution.

---

# 16. Repo Control Authority Boundary

Repo Control and Vocab are separate codebases.

Vocab product work must not silently modify Repo Control.

If Vocab development exposes a Repo Control limitation:

1. preserve the evidence;
2. describe the limitation;
3. determine whether Vocab can continue safely;
4. return the issue to the Architect/Product Owner;
5. use a separate Repo Control milestone if a generalized control-plane change is approved.

This separation prevents Repo Control from becoming Vocab-specific.

---

# 17. Existing Repo Control Validation Against Vocab

Before the current canonical-repository transition, the historical Vocab testbed successfully exercised the browser-based guarded workflow.

The Product Owner performed:

1. Prepare Stage;
2. review immutable Stage Plan;
3. Approve Stage;
4. create matching Snapshot;
5. Prepare Commit;
6. review immutable Commit Plan;
7. Approve Commit.

The testbed finished with a successful local commit and clean working tree.

That work demonstrated that Repo Control can safely act as a thin browser adapter over its existing Stage/Commit authorities.

---

# 18. Why Vocab Is a Useful Integration Testbed

Vocab is intentionally small but realistic.

It has:

- UI behavior;
- external data dependency;
- business logic;
- tests;
- future database needs;
- future container runtime;
- future deployment;
- future remote access.

That makes it suitable for progressively exercising Repo Control against real application evolution without immediately exposing a larger production system.

---

# 19. Repo Control Integration Philosophy

The project uses this direction:

`real Vocab requirement → real development workflow → observed Repo Control capability or gap`

not:

`desired Repo Control feature → artificial Vocab change created to justify it`

The purpose is to discover reusable control-plane requirements from real work.

---

# 20. Current Testing State

The historical sanitized testbed contained 14 passing unit tests at the end of Repo Control M010 validation.

Those tests belong to the historical branch context.

Do not assume current canonical `main` has the same tests or behavior.

The upcoming reconnaissance must inspect the actual current test structure on `main`.

Future milestone validation must report actual commands and actual results from the current branch.

---

# 21. Current Application Architecture — Not Yet Fully Reconnoitered

The known high-level historical architecture is:

`Streamlit UI → application/quiz logic → Google Sheets`

However, the exact current canonical implementation has not yet been formally mapped under the new Vocab project workflow.

Do not treat that simplified model as sufficient implementation evidence.

The upcoming architecture reconnaissance must determine the real code-level structure.

---

# 22. Required Architecture Reconnaissance

The next major milestone should inspect at least:

## Application entry point

- current executable/start path;
- how Streamlit launches;
- module structure;
- runtime assumptions.

## Streamlit coupling

- which files import Streamlit;
- which business behaviors depend directly on Streamlit APIs;
- whether UI state and application logic are separable.

## Google Sheets coupling

- where Sheets authentication occurs;
- where reads occur;
- where writes occur;
- how record structure is represented;
- whether persistence logic is centralized.

## Quiz/test logic

- how a question is generated;
- how answers are evaluated;
- how definitions are displayed;
- how scoring/progress works;
- what would be required for multiple choice.

## Vocabulary/business logic

- synonym behavior;
- normalization;
- data transformations;
- reusable pure functions;
- duplication between UI and helpers.

## Tests

- existing test files;
- coverage;
- dependency on Streamlit;
- dependency on Google Sheets;
- missing seams needed for deterministic testing.

## Configuration/secrets

- current configuration paths;
- credential assumptions;
- environment dependencies;
- what must remain outside Git.

## Runtime

- Python version expectations;
- dependencies;
- network requirements;
- generated/runtime files;
- audio/pronunciation dependencies if any.

## Containerization

- minimum files required;
- whether Streamlit can be containerized as-is;
- required port;
- required environment;
- persistent state;
- credential injection method;
- health-check options.

## Refactor value

- whether current coupling materially blocks or complicates:
  - multiple choice;
  - database migration;
  - Streamlit replacement;
  - testing;
  - containerization.

---

# 23. Possible Future Architecture

No future architecture is locked yet.

A likely direction, subject to reconnaissance, may separate:

`UI`

from:

`application / quiz services`

from:

`vocabulary repository / persistence`

Conceptually:

`UI → application services → vocabulary repository`

with implementations such as:

`Google Sheets repository` today

and:

`database repository` later.

Likewise:

`Streamlit UI` today

could later be replaced by:

`self-hosted web UI`

while preserving application services.

This is only a design hypothesis until reconnaissance confirms the current code warrants it.

---

# 24. Containerization Direction

The Vocab runtime is expected to become containerized on `henderson-server1`.

The first container baseline should preserve existing behavior rather than combining containerization with major application redesign.

The canonical Git repository should remain host-side and visible to Repo Control.

Preferred conceptual model:

`host Git repo → image build → Vocab container`

The container runtime should eventually expose enough identity to determine which source commit it was built from.

---

# 25. Deployment Identity Goal

A future runtime should be able to answer:

- what application is running;
- what container/image is running;
- what Git commit was used to build it;
- whether it is healthy;
- whether deployed code matches repository HEAD.

This is a future Repo Control integration target.

It is not yet implemented.

---

# 26. Code State vs. Deployment State

The project explicitly distinguishes:

## Code state

Examples:

- modified;
- staged;
- committed;
- branch/HEAD.

## Build state

Examples:

- no image built;
- image built from commit X.

## Deployment state

Examples:

- not deployed;
- deployed commit X;
- deployed commit behind repository HEAD.

## Runtime state

Examples:

- stopped;
- starting;
- healthy;
- unhealthy.

These states must not be conflated.

---

# 27. Database Direction

The Product Owner intends to move vocabulary data away from Google Sheets.

The likely target is a database hosted on `henderson-server1`.

PostgreSQL is a possible candidate because the server already supports it for other workloads, but no database choice is yet locked for Vocab.

The database decision should consider:

- simplicity;
- backup/recovery;
- schema needs;
- container topology;
- testability;
- data migration;
- operational burden.

Do not select a database merely because another project uses it.

---

# 28. Google Sheets Migration Requirements

A future migration must preserve application data accurately.

The migration plan should determine:

- source rows/columns;
- vocabulary identifiers;
- definitions;
- synonyms or auxiliary fields;
- duplicate handling;
- null/empty behavior;
- ordering semantics if relevant;
- data validation;
- migration repeatability;
- rollback/recovery;
- post-migration verification.

Google Sheets should remain authoritative until the migration is explicitly accepted.

---

# 29. Streamlit Replacement Direction

The future project goal is not merely to run Streamlit on the server.

The long-term target is to remove Streamlit as the application's framework/runtime.

Before replacement, reconnaissance must determine:

- how deeply Streamlit is coupled to business logic;
- what UI behaviors need preservation;
- what framework-independent logic already exists;
- what replacement requirements actually exist.

Do not select a replacement framework prematurely.

---

# 30. Network Access Direction

The desired access sequence is:

## Initial

Local access on `henderson-server1`.

## Next

LAN access from the Product Owner's normal computers/devices.

## Later

Controlled secure external access.

Remote exposure must not be implemented casually.

External access should be addressed only after:

- the application runtime is stable;
- authentication/security needs are understood;
- network boundary is intentionally designed.

---

# 31. Product Behavior Priority

The Vocab App remains a real product.

Repo Control testing should not distort the application.

Product changes should make sense for the Vocab App independently of Repo Control.

Repo Control is expected to observe and safely manage the workflow around those changes.

---

# 32. Planned Evolution Sequence

Current high-level sequence:

1. repository and project-control foundation;
2. architecture/integration reconnaissance;
3. optional bounded refactor if justified;
4. containerized current-app baseline;
5. multiple-choice quiz;
6. Google Sheets → server database;
7. Streamlit replacement;
8. LAN-hosted application;
9. secure external access;
10. increasingly capable Repo Control runtime/deployment integration.

Exact milestone numbering may shift based on reconnaissance.

---

# 33. Vocab Milestone Numbering

Vocab uses an independent milestone sequence.

Current planned structure begins with:

## 001

Canonical repository reconciliation and project-control foundation.

## 002

Architecture and integration reconnaissance.

Later milestones will be numbered based on findings.

Repo Control milestones use their own numbering and should not be confused with Vocab milestone numbers.

---

# 34. Current Project-Control Documents

The controlling Vocab documents are intended to include:

- `docs/context/project_workflow_v1.md`
- `docs/context/coding_agent_rules_v1.md`
- `docs/context/vocab_app_project_context_v1.md`
- `architecture/vocab_repo_control_integration_roadmap_v1.md`
- `docs/context/new_chat_intro_coder_v1.md`

Milestone prompts and closeouts will live under `milestones/`.

---

# 35. Project Documentation Principle

Global context documents describe current accepted truth.

Milestone prompts describe intended bounded work.

Milestone closeouts describe what actually happened.

Git history preserves changes over time.

Do not silently rewrite context documents to make historical events appear cleaner than they were.

---

# 36. Current Unknowns

The following remain intentionally unresolved pending reconnaissance:

- exact current Streamlit structure;
- exact Google Sheets access layer;
- current test coverage on canonical `main`;
- whether historical testbed utilities should be ported;
- whether bounded refactor should precede feature work;
- exact container topology;
- exact database technology;
- exact self-hosted replacement framework;
- external-access architecture;
- exact future Repo Control deployment model.

These are not omissions.

They are decisions that should be evidence-driven.

---

# 37. Safety Boundaries

Until explicitly changed by a milestone:

- do not merge unrelated historical Git histories;
- do not reintroduce old Windows backup files automatically;
- do not commit secrets;
- do not modify Repo Control during a Vocab milestone;
- do not access or modify Photo Organizer;
- do not perform database mutation without authorization;
- do not alter unrelated Docker resources;
- do not expose Vocab publicly;
- do not delete the frozen historical source copy merely because canonical migration succeeded.

---

# 38. Frozen Historical Source Copy

The earlier testbed source remains at:

`/home/chuck/ai-agent-tests/vocab-app`

It should remain untouched during the initial reconciliation/foundation period.

Once the canonical repository, historical branches, project documentation, and integration roadmap are fully established, the Product Owner may later decide whether the frozen filesystem copy is still needed.

Do not delete it as part of routine cleanup.

---

# 39. Current Success Definition

The near-term project succeeds when:

- canonical Vocab development occurs from `/home/chuck/projects/vocab-app`;
- `main` tracks the existing GitHub application history;
- the historical Repo Control testbed remains preserved but separate;
- project-control documents are committed;
- a new coder chat can operate primarily from repository documentation;
- architecture reconnaissance produces a concrete implementation roadmap;
- real Vocab changes can exercise Repo Control without Vocab-specific control-plane hacks;
- the application progresses toward self-hosted operation on `henderson-server1`.

---

# 40. Current Working Principle

The current development philosophy is:

> **Evolve Vocab as a real application, use its real development needs to exercise Repo Control, and preserve enough deterministic evidence that code, decisions, and runtime state remain understandable later.**

---

**End of `vocab_app_project_context_v1.md`**
