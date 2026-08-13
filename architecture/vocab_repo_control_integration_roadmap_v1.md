# Vocab App — Repo Control Integration Roadmap v1

**Document:** `vocab_repo_control_integration_roadmap_v1.md`  
**Project:** Vocab App  
**Status:** Active roadmap  
**Version:** 1.0  
**Canonical Vocab repository:** `/home/chuck/projects/vocab-app`  
**Canonical Vocab branch:** `main`  
**Repo Control repository:** `/home/chuck/projects/repo-control`

---

# 1. Purpose

This roadmap describes the intended evolution of the Vocab App and its use as a real integration testbed for Repo Control.

The roadmap has two parallel goals:

1. improve the Vocab App into a self-hosted application on `henderson-server1`;
2. use real Vocab development and deployment work to discover, validate, and refine generic Repo Control capabilities.

The roadmap is intentionally evidence-driven.

It does not authorize future work merely because a capability appears here.

Each step requires its own milestone scope.

---

# 2. Core Product Direction

The Product Owner intends to make three major Vocab changes:

1. change the quiz/test workflow to multiple choice;
2. move vocabulary words and definitions from Google Sheets to a database hosted on `henderson-server1`;
3. remove Streamlit and operate the application directly from `henderson-server1`, initially for LAN access and later through controlled secure external access.

A bounded refactor may be inserted before these changes if reconnaissance demonstrates material value.

---

# 3. Why Vocab Is the Repo Control Testbed

Vocab is intentionally being used as more than a synthetic test fixture.

It is a small real application with:

- user-facing behavior;
- data persistence;
- external service dependency;
- tests;
- evolving architecture;
- future database migration;
- future container runtime;
- future deployment;
- future remote access.

This makes it suitable for exposing real control-plane requirements while keeping experimentation bounded.

The guiding principle is:

> Real application needs should reveal Repo Control requirements.

Repo Control should not invent application work merely to justify new control-plane features.

---

# 4. Separation of Responsibilities

## Vocab

Responsible for:

- vocabulary behavior;
- quiz behavior;
- definitions;
- synonyms;
- persistence;
- application UI;
- application runtime;
- business rules.

## Repo Control

Responsible for generic development/control-plane concerns such as:

- repository identity;
- Git state;
- context;
- snapshots;
- comparisons;
- review evidence;
- guarded mutation;
- build identity;
- deployed version identity;
- health;
- controlled deployment workflow.

Repo Control should not need to understand Vocab-specific business rules.

---

# 5. Current Starting Point

Canonical Vocab development now occurs from:

`/home/chuck/projects/vocab-app`

Canonical GitHub repository:

`CHHIV-Projects/vocab-app`

Canonical branch:

`main`

Historical Repo Control testbed work remains preserved on separate archive/test branches.

The independent historical testbed lineage is reference material only.

It must not be merged into canonical `main` merely to recover experimental changes.

---

# 6. Current Repo Control Capability Baseline

Before this roadmap begins, Repo Control already supports the core local repository evidence and guarded Git lifecycle developed through earlier milestones.

Current conceptual capabilities include:

- deterministic Git state;
- working-tree classification;
- upstream visibility;
- Context;
- Snapshots;
- Comparisons;
- local AI/Product Owner review;
- guarded Stage preparation;
- immutable Stage Plan review;
- explicit Stage approval;
- guarded Commit preparation;
- immutable Commit Plan review;
- explicit Commit approval;
- execution evidence.

These form the starting control-plane baseline.

---

# 7. Development Philosophy

The Vocab and Repo Control projects should evolve incrementally.

Preferred pattern:

`application need`

→ `reconnaissance`

→ `bounded Vocab implementation`

→ `tests`

→ `Repo Control evidence`

→ `Product Owner validation`

→ `identify real control-plane gap if any`

→ `separate Repo Control milestone when justified`

This prevents Repo Control changes from being mixed casually into Vocab feature work.

---

# 8. Roadmap Overview

The planned high-level sequence is:

## Phase 1

Project and repository foundation.

## Phase 2

Architecture and integration reconnaissance.

## Phase 3

Optional bounded refactor if justified.

## Phase 4

Containerized current-app runtime baseline.

## Phase 5

Multiple-choice quiz.

## Phase 6

Google Sheets → server database.

## Phase 7

Streamlit replacement / self-hosted web application.

## Phase 8

LAN operation and runtime hardening.

## Phase 9

Secure external access.

## Phase 10

Guarded Repo Control deployment integration.

Exact milestone numbering may change after reconnaissance.

---

# 9. Phase 1 — Project and Repository Foundation

Goal:

Establish the Vocab App as a normal independently managed project rather than a disposable Repo Control fixture.

Required outcomes include:

- canonical repository established at `/home/chuck/projects/vocab-app`;
- existing GitHub `main` retained as canonical history;
- historical Repo Control testbed lineage preserved separately;
- no unrelated-history merge;
- project workflow established;
- coding-agent rules established;
- project context established;
- integration roadmap established;
- coder-chat onboarding material established;
- repository hygiene established;
- secrets remain excluded.

This phase creates the durable foundation for all later work.

---

# 10. Phase 2 — Architecture and Integration Reconnaissance

This should be the first substantial technical milestone.

It should remain reconnaissance-only unless explicitly changed.

The reconnaissance should map the actual current canonical `main`.

Required areas include:

## Application structure

- entry point;
- module organization;
- current startup mechanism;
- runtime assumptions.

## Streamlit

- imports;
- UI/state coupling;
- business logic embedded in Streamlit callbacks or page code;
- framework-independent logic already available.

## Google Sheets

- authentication;
- reads;
- writes;
- data transformations;
- schema assumptions;
- error handling;
- coupling to application code.

## Quiz behavior

- current test flow;
- question generation;
- answer evaluation;
- scoring;
- definitions;
- synonym handling;
- state management.

## Tests

- current tests on canonical `main`;
- gaps;
- Streamlit dependencies;
- Google dependencies;
- opportunities for pure-function testing.

## Historical testbed value

Evaluate deliberately:

- `vocab_utils.py`;
- `synonym_policy.py`;
- `test_vocab_utils.py`;
- historical `app.py` changes.

Determine whether any of that experimental work is appropriate to port.

## Containerization

Determine:

- current Python/runtime requirements;
- exposed port;
- files required;
- environment variables;
- credentials;
- generated files;
- persistence needs;
- health-check strategy.

## Refactor value

Determine whether a bounded refactor materially reduces risk for the three planned Product Owner changes.

---

# 11. Phase 3 — Optional Bounded Refactor

This phase occurs only if Phase 2 recommends it and the Architect/Product Owner approve it.

The likely reason would be excessive coupling among:

- UI;
- quiz logic;
- persistence;
- Google Sheets;
- configuration;
- synonym/business logic.

A possible future architecture might resemble:

`UI adapter`

→ `application/quiz services`

→ `vocabulary repository interface`

with:

`Google Sheets implementation`

initially

and:

`database implementation`

later.

This is a hypothesis, not a locked design.

The refactor should be as small as possible while creating useful seams for later work.

---

# 12. Refactor Acceptance Standard

A refactor should be accepted only if it demonstrably improves near-term implementation.

It should produce concrete benefits such as:

- easier testing;
- cleaner multiple-choice implementation;
- centralized persistence;
- lower migration risk;
- simpler Streamlit replacement;
- reduced duplicate logic.

It should preserve user-visible behavior unless explicitly scoped otherwise.

---

# 13. Phase 4 — Containerized Current-App Baseline

The first deployment-oriented milestone should containerize the existing Vocab application without simultaneously redesigning it.

The purpose is to establish a known-good runtime baseline.

Preferred conceptual topology:

`/home/chuck/projects/vocab-app`

→ `container image`

→ `Vocab container`

→ `browser`

The Git repository remains host-side.

Repo Control continues to inspect the host Git repository.

---

# 14. Container Baseline Requirements

The baseline should prove:

- image builds reproducibly;
- container starts;
- application is reachable;
- current application behavior is preserved;
- credentials are injected externally;
- persistent data is not accidentally embedded into disposable image layers;
- app can stop/start cleanly;
- rebuild/replacement works predictably;
- relevant tests pass;
- unrelated server workloads remain untouched.

No automatic Repo Control deployment should be added yet.

---

# 15. Source Revision Identity

A key container baseline goal is to associate the built/runtime application with the source commit that produced it.

Conceptually:

`Git commit XYZ`

→ `image built from XYZ`

→ `container running XYZ`

The image/container should eventually expose the exact source SHA through deterministic metadata.

This creates the foundation for future Repo Control runtime intelligence.

---

# 16. Repo Control Opportunity — Runtime Read-Only Awareness

After the manual container baseline is stable, Vocab may expose a legitimate need for Repo Control to understand runtime state.

A future Repo Control milestone may add read-only facts such as:

- application/service identity;
- container name;
- image identity;
- source revision;
- health;
- runtime state.

Example:

`Repository HEAD: abc123`

`Running revision: abc123`

`Relationship: CURRENT`

or:

`Repository HEAD: def456`

`Running revision: abc123`

`Relationship: DEPLOYMENT BEHIND CODE`

This should be generic, not Vocab-specific.

---

# 17. Phase 5 — Multiple-Choice Quiz

This should be the first major visible Product Owner feature change after the baseline architecture is stable.

Why first:

- visible;
- bounded;
- low persistence risk;
- easy to test;
- easy for Product Owner to validate;
- ideal for demonstrating Repo Control against real feature work.

The exact multiple-choice behavior should be defined in its own milestone.

---

# 18. Multiple-Choice Development Demonstration

The ideal workflow will be:

Product Owner requirement

→ Context / relevant-code discovery

→ Coder implementation

→ tests

→ Snapshot

→ Comparison

→ optional AI review

→ Prepare Stage

→ review exact Stage Plan

→ Approve Stage

→ matching Snapshot

→ Prepare Commit

→ review exact Commit Plan

→ Approve Commit

→ build container

→ deploy manually/through approved runtime workflow

→ validate multiple-choice behavior

→ verify deployed SHA matches intended commit.

This becomes the first full code-to-running-application demonstration.

---

# 19. Multiple-Choice Acceptance Themes

Future detailed requirements may include:

- prompt word or definition;
- correct answer;
- distractors;
- number of choices;
- duplicate avoidance;
- scoring;
- feedback;
- next-question flow;
- session progress;
- deterministic testing of choice generation.

The exact contract remains for its own milestone.

---

# 20. Phase 6 — Google Sheets to Server Database

This is the first major persistence change.

Current conceptual state:

`Vocab App → Google Sheets`

Target:

`Vocab App → database on henderson-server1`

The database technology is not yet locked.

It should be selected after reconnaissance based on application needs and operational simplicity.

---

# 21. Database Selection Principles

The chosen database should be evaluated for:

- simplicity;
- reliability;
- backup/recovery;
- testability;
- migration support;
- compatibility with containerized deployment;
- operational burden;
- persistence requirements.

PostgreSQL may be a candidate because the server already supports it for other applications, but that fact alone is not sufficient reason to choose it.

---

# 22. Database Topology

A likely future container topology could be:

`Docker`

- `vocab-app`
- `vocab-db`

with persistent database storage outside the disposable application container.

The exact topology is not locked.

Persistent data must not disappear merely because the application container is rebuilt.

---

# 23. Google Sheets Migration Requirements

The migration milestone should explicitly map and verify:

- source columns;
- word identity;
- definitions;
- synonyms;
- optional fields;
- duplicates;
- blank/null semantics;
- ordering if meaningful;
- existing data quality;
- migration counts;
- validation counts;
- repeatability;
- recovery/rollback.

Google Sheets remains authoritative until migration acceptance.

---

# 24. Migration Safety

The database migration should have a controlled transition.

Preferred pattern:

1. inspect source data;
2. define destination schema;
3. create deterministic migration path;
4. migrate to controlled destination;
5. validate counts and representative records;
6. test application against destination;
7. Product Owner validates behavior;
8. only then retire normal Google Sheets dependency.

Do not destroy the source data during migration.

---

# 25. Repo Control Opportunity — Persistence/Deployment Evidence

The database migration may expose new generic Repo Control needs.

Possible examples:

- deployment plan includes schema migration;
- runtime health depends on database availability;
- migration state is part of release verification;
- application revision and database schema must remain compatible.

These should be evaluated as generic control-plane requirements.

Repo Control should not understand vocabulary rows themselves.

---

# 26. Phase 7 — Streamlit Replacement

The long-term Product Owner target is to remove Streamlit as the application's UI/runtime framework.

This phase should occur only after application/business logic and persistence are sufficiently separable.

The replacement framework should not be selected solely from preference.

Reconnaissance should identify actual requirements such as:

- forms;
- session state;
- quiz interaction;
- navigation;
- server-side data access;
- static assets;
- authentication needs;
- deployment simplicity.

---

# 27. Streamlit Replacement Goal

Target conceptual architecture:

`browser`

→ `self-hosted Vocab web service`

→ `application/quiz services`

→ `server database`

The application should run on `henderson-server1` without requiring Streamlit.

The exact web technology remains open until scoped.

---

# 28. Streamlit Transition Safety

Avoid combining all of the following into one uncontrolled rewrite:

- persistence migration;
- quiz redesign;
- framework replacement;
- external exposure.

Each transition should have its own acceptance boundary.

Behavior that already works should remain testable during framework replacement.

---

# 29. Phase 8 — LAN Operation and Runtime Hardening

After self-hosted runtime is stable, establish normal local-network use.

Potential concerns include:

- stable port/service identity;
- restart behavior;
- health checks;
- logs;
- service supervision;
- container restart policy;
- persistent storage;
- local DNS/name if desired;
- browser compatibility.

The goal is a dependable local application before public exposure.

---

# 30. Phase 9 — Secure External Access

External access is intentionally late in the roadmap.

Do not expose the application publicly merely because it runs successfully on the LAN.

Before external access, determine:

- authentication requirements;
- HTTPS/TLS;
- reverse proxy or secure tunnel strategy;
- rate/security concerns;
- firewall boundary;
- public hostname;
- update/patch expectations;
- logging;
- recovery.

The exact solution should be designed separately.

---

# 31. External Access Principle

Preferred security posture:

> expose the minimum required surface through a deliberate supported mechanism.

Do not open broad server ports or expose internal database services publicly.

The database should normally remain private to the server/runtime environment.

---

# 32. Phase 10 — Guarded Repo Control Deployment Integration

Only after manual build/deploy behavior is stable should Repo Control begin controlling deployment mutation.

A future workflow may resemble:

`Prepare Deployment`

→ `immutable Deployment Plan`

→ `human review`

→ `explicit approval`

→ `build/deploy exact revision`

→ `health verification`

→ `execution evidence`.

This intentionally mirrors the Stage/Commit philosophy already established.

---

# 33. Deployment Plan Evidence

A future generic Deployment Plan might include:

- repository;
- branch;
- exact source commit;
- image target;
- container/service;
- current deployed revision;
- proposed revision;
- affected services;
- required migration;
- expected health check;
- rollback/recovery information.

This is future design direction, not current implementation authority.

---

# 34. Deployment Mutation Safety

Future Repo Control deployment mutation must remain fail-closed.

It should not:

- deploy “latest” implicitly;
- substitute a different commit;
- rebuild after approval without rebinding evidence;
- restart unrelated services;
- silently repair failures;
- hide partial deployment states.

Mutation should remain bound to exact reviewed identity.

---

# 35. Runtime Verification

Deployment execution should not end at “container started.”

It should verify:

- intended service is running;
- expected source revision is deployed;
- health check passes;
- required dependencies are available;
- application responds as expected.

When verification fails after mutation, preserve the fact that mutation occurred.

---

# 36. Code-to-Runtime Lineage

The long-term integration goal is an auditable lineage:

`Product Owner requirement`

→ `code change`

→ `tests`

→ `review evidence`

→ `commit`

→ `image`

→ `deployment`

→ `health`

→ `running source revision`.

Repo Control should make those relationships understandable without conflating them.

---

# 37. What Repo Control Should Eventually Answer

For a bound application repository, Repo Control should eventually be able to answer questions such as:

- What repository am I viewing?
- What branch/HEAD is current?
- What changed?
- What was reviewed?
- What was committed?
- What application/runtime is associated with this repository?
- Is it running?
- What exact source revision is deployed?
- Does deployed code match repository HEAD?
- Is the application healthy?
- Is there a reviewed deployment plan?
- What happened during the last deployment?

These are generic application-control-plane concepts.

---

# 38. What Repo Control Should Not Need to Know

Repo Control should not need to know:

- how vocabulary questions are scored;
- how distractors are chosen;
- what a synonym means;
- which database row represents a word;
- how definitions are displayed;
- Vocab-specific business state.

Those remain application concerns.

---

# 39. Real-Gap Rule

A new Repo Control capability should normally be introduced only after an actual Vocab workflow exposes the need.

Examples:

## Valid

“We committed code but cannot deterministically tell what revision the running container contains.”

This may justify runtime revision intelligence.

## Valid

“We have a stable manual deployment but need explicit Prepare → Review → Approve deployment control.”

This may justify guarded deployment.

## Invalid

“A deployment dashboard sounds useful, so build one now.”

That alone is not sufficient.

---

# 40. Vocab vs. Repo Control Milestones

Vocab and Repo Control retain independent milestone histories.

A Vocab milestone may discover a Repo Control need.

If so:

- record the finding in Vocab;
- create a separate Repo Control milestone;
- implement the generalized control-plane feature there;
- return to the Vocab validation when appropriate.

Do not hide Repo Control changes inside a Vocab feature commit.

---

# 41. Expected Vocab Milestone Sequence

Current conceptual sequence:

## 001

Repository reconciliation and project-control foundation.

## 002

Architecture and integration reconnaissance.

## 003

Either:

- bounded architecture refactor;

or, if no refactor is warranted:

- container runtime baseline.

## Next

Container baseline if not already completed.

## Following

Multiple-choice quiz.

## Following

Google Sheets → server database.

## Following

Streamlit replacement.

## Following

LAN hardening and secure external access.

Exact numbering should be selected after each prior milestone closes.

---

# 42. Expected Repo Control Evolution

Repo Control milestones should be created only as real gaps emerge.

Likely future themes may include:

- repository chooser/binding refinements;
- read-only application/runtime association;
- deployed-revision identity;
- container health/state;
- build evidence;
- deployment planning;
- guarded deployment execution;
- post-deployment verification;
- application release history.

These are anticipated themes, not commitments.

---

# 43. Product Owner Validation Role

Each meaningful product phase should end with Product Owner validation.

Examples:

## Container baseline

Open the existing Vocab application from the intended browser path.

## Multiple choice

Take a real quiz and confirm the desired behavior.

## Database migration

Verify real vocabulary/definitions and application behavior.

## Framework replacement

Use the self-hosted application through normal workflows.

## LAN/external access

Verify the intended access path.

Repo Control evidence should support, not replace, this validation.

---

# 44. Testing Evolution

Testing should become stronger as architecture improves.

Desired progression:

- pure business-logic unit tests;
- persistence adapter tests;
- controlled database integration tests;
- web route/API tests;
- container health/smoke tests;
- deployment verification;
- Product Owner browser tests.

Avoid tests that require real external services unless that integration itself is under test.

---

# 45. Development Environment Principle

The canonical source repository remains on the host.

Containers are runtime/build artifacts.

The development model should not require editing source inside disposable containers.

Preferred flow:

`edit host repository`

→ `test`

→ `commit`

→ `build image`

→ `replace runtime`

→ `verify`.

This preserves Repo Control visibility into source state.

---

# 46. Persistent Data Principle

Application containers may be disposable.

Application data is not.

Persistent vocabulary data must survive:

- container rebuild;
- container replacement;
- application restart;
- deployment of a new code revision.

Persistence architecture should make that boundary obvious.

---

# 47. Secrets Principle

Secrets remain outside:

- Git;
- container images;
- Repo Control evidence;
- logs intended for milestone documentation.

Future deployment mechanisms should inject secrets through approved external configuration.

---

# 48. Shared-Server Protection

Vocab shares `henderson-server1` with other services.

Every runtime/deployment milestone must identify:

- expected ports;
- Compose/project identity if used;
- container names;
- volumes;
- networks;
- configuration paths;
- persistent data paths;
- potential shared-host impact.

Do not use broad cleanup commands affecting unrelated resources.

---

# 49. Photo Organizer Boundary

Photo Organizer remains entirely out of scope for this roadmap.

The Vocab project may borrow process lessons from it.

It must not use Photo Organizer's:

- containers;
- databases;
- networks;
- runtime services;
- source repository;
- storage;

as part of Vocab implementation.

---

# 50. Roadmap Decision Gates

The roadmap intentionally includes several decision gates.

## Gate A — After architecture reconnaissance

Decision:

- refactor first;
- or containerize directly.

## Gate B — After container baseline

Decision:

- whether runtime identity is sufficient manually;
- whether a Repo Control read-only runtime milestone is justified.

## Gate C — Before database migration

Decision:

- database technology;
- schema;
- migration strategy;
- persistence topology.

## Gate D — Before Streamlit replacement

Decision:

- replacement framework/runtime;
- required web architecture;
- authentication implications.

## Gate E — Before external access

Decision:

- secure exposure mechanism.

## Gate F — Before deployment automation

Decision:

- whether manual deployment is stable enough to automate.

---

# 51. Scope-Control Principle

This roadmap is intentionally broad.

Individual milestones should not be.

Each milestone should implement only the next approved coherent step.

Do not combine:

- containerization;
- database migration;
- Streamlit replacement;
- external access;
- generalized Repo Control deployment;

into one implementation milestone.

The roadmap exists specifically so those changes can be sequenced safely.

---

# 52. Success Criteria for the Full Arc

The Vocab/Repo Control integration arc will be successful when:

- Vocab remains a useful real application;
- multiple-choice testing works;
- vocabulary data is stored durably on the server;
- Google Sheets is no longer required for normal operation;
- Streamlit is removed;
- the application runs reliably on `henderson-server1`;
- LAN use is straightforward;
- external access is secure and intentional;
- application data is backed up/recoverable;
- source/runtime version identity is deterministic;
- Repo Control can explain repository and deployment relationships;
- guarded deployment is possible without Vocab-specific control-plane logic;
- Vocab development remains understandable through project documentation and Git history.

---

# 53. Near-Term Next Step

The immediate technical next milestone after the project-control foundation should be:

**Vocab 002 — Architecture and Integration Reconnaissance**

It should remain read-only.

Its purpose is to turn current code reality into the implementation roadmap for:

- optional refactor;
- container baseline;
- multiple choice;
- database migration;
- Streamlit replacement.

The resulting reconnaissance closeout should be reviewed by the Architect/Product Owner before implementation begins.

---

# 54. Working Principle

The roadmap should be interpreted through this rule:

> **Do the next real Vocab task safely, learn what Repo Control actually needs from that task, and generalize only from evidence.**

---

**End of `vocab_repo_control_integration_roadmap_v1.md`**
