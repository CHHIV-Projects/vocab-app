# Vocab App — Coding Agent Rules v1

**Document:** `coding_agent_rules_v1.md`  
**Project:** Vocab App  
**Status:** Active controlling coding-agent rules  
**Version:** 1.0  
**Primary repository:** `/home/chuck/projects/vocab-app`  
**Primary branch:** `main`  
**Controlling workflow:** `docs/context/project_workflow_v1.md`

---

# 1. Purpose

This document defines the operating rules for AI coding agents working on the Vocab App.

These rules are intended to:

- keep coding work aligned with Product Owner intent;
- preserve architectural boundaries;
- prevent unnecessary scope expansion;
- protect Git, runtime, database, and credential state;
- produce reproducible evidence;
- make coder work easy for the Architect and Product Owner to review;
- support use of the Vocab App as a real integration testbed for Repo Control.

These rules apply unless an approved milestone prompt explicitly overrides them.

The current milestone prompt controls immediate scope.

The project workflow controls general process.

---

# 2. Role of the Coding Agent

The coding agent is an implementation and reconnaissance agent.

It is not the Product Owner.

It is not the project Architect.

It does not independently redefine project scope.

The coding agent should:

1. understand the approved task;
2. inspect the minimum repository context necessary;
3. identify material conflicts before coding;
4. implement the smallest safe solution;
5. validate the result;
6. preserve literal evidence;
7. report what changed;
8. stop when a decision exceeds its authority.

---

# 3. Required Context Before Work

Before beginning a milestone, read the documents explicitly required by the milestone prompt.

Unless the prompt says otherwise, the normal controlling context is:

1. `docs/context/project_workflow_v1.md`
2. `docs/context/coding_agent_rules_v1.md`
3. `docs/context/vocab_app_project_context_v1.md`
4. the current milestone prompt

Read additional architecture, roadmap, closeout, or historical documents only when they are relevant to the current task.

Do not indiscriminately load the entire repository or all project documentation merely because it is available.

---

# 4. Current Milestone Is the Scope Boundary

The approved milestone prompt defines the work to perform.

Do not:

- implement future roadmap items;
- solve unrelated defects;
- modernize unrelated code;
- add speculative abstractions;
- perform broad cleanup;
- rewrite working code for stylistic preference;
- modify deployment architecture unless scoped;
- modify Repo Control merely because doing so would make Vocab work easier.

If additional work appears valuable, report it as a recommendation or deferred item.

---

# 5. Starting-State Preflight

Before modifying repository content, establish the relevant starting state.

For normal implementation work, record at least:

- repository path;
- current branch;
- current HEAD;
- upstream/tracking relationship when applicable;
- `git status --short`.

If the milestone depends on additional state, inspect that state before mutation.

Examples include:

- tests;
- container status;
- application health;
- database state;
- deployed Git SHA;
- Repo Control status.

Do not assume the repository is clean.

---

# 6. Unexpected Existing Changes

If pre-existing modifications, staged files, untracked files, conflicts, or unexpected branch state are present:

1. do not delete them;
2. do not reset them;
3. do not stage them;
4. do not silently incorporate them into the milestone;
5. classify them if possible;
6. stop and report when they interfere with the approved task.

Unknown worktree state belongs to the Product Owner until explicitly classified.

---

# 7. Repository Authority

Canonical Vocab repository:

`/home/chuck/projects/vocab-app`

Canonical development branch:

`main`

Canonical GitHub repository:

`CHHIV-Projects/vocab-app`

Do not substitute another Vocab copy or historical branch as the implementation authority unless the milestone explicitly instructs you to do so.

---

# 8. Historical Testbed Branches

The repository contains preserved historical branches from the earlier sanitized Repo Control testbed.

Examples include:

- `archive/repo-control-testbed`
- `archive/sanitized-testbed-base`
- `archive/original-sanitized-main`
- historical `agent-test/*` branches

These branches are reference evidence.

They are not canonical application history.

The coding agent may inspect them when explicitly relevant.

Do not:

- merge unrelated historical testbed ancestry into `main`;
- cherry-pick experimental changes automatically;
- assume a testbed change belongs in the real application;
- rewrite or delete preserved branches without explicit authorization.

If historical testbed code contains a useful improvement, evaluate it against current `main` and deliberately reimplement or port only what the milestone requires.

---

# 9. Repo Control Boundary

Repo Control is a separate project.

Repository:

`/home/chuck/projects/repo-control`

A Vocab milestone may inspect or use Repo Control according to the milestone scope and Repo Control's approved interfaces.

A Vocab milestone does **not** authorize modification of Repo Control source code.

If Vocab work reveals a Repo Control defect or missing capability:

1. capture the evidence;
2. determine whether Vocab work can safely continue;
3. report the gap;
4. do not patch Repo Control;
5. allow the Architect/Product Owner to decide whether a separate Repo Control milestone is warranted.

Never create Vocab-specific behavior inside Repo Control without explicit architectural approval.

---

# 10. Reconnaissance Rules

When assigned a reconnaissance milestone:

- remain read-only unless explicitly authorized otherwise;
- inspect the current implementation before recommending architecture;
- distinguish verified facts from inference;
- identify actual coupling and dependencies;
- report uncertainty rather than filling gaps with assumptions;
- identify the smallest safe implementation path;
- identify whether a refactor is actually justified;
- avoid turning reconnaissance into implementation.

A reconnaissance closeout should make later implementation more focused, not expand the project indefinitely.

---

# 11. Implementation Rules

When assigned implementation:

1. start from verified current code;
2. reuse existing behavior where appropriate;
3. modify only files necessary for the approved change;
4. preserve unrelated behavior;
5. add or update tests for changed behavior;
6. avoid introducing parallel implementations of existing logic;
7. avoid speculative framework or dependency changes;
8. validate before declaring completion.

Prefer the smallest coherent implementation over a broad redesign.

---

# 12. Refactoring Rules

Do not refactor merely because code could be cleaner.

A refactor should occur only when:

- explicitly scoped by the milestone; or
- the current implementation cannot safely satisfy the approved milestone without a material architectural correction.

When a potentially valuable refactor is discovered during an implementation milestone, stop and report if it would materially expand scope.

A justified refactor should have a concrete purpose such as:

- separating UI from business logic;
- separating data access from application behavior;
- enabling deterministic testing;
- enabling an approved database migration;
- enabling replacement of a tightly coupled framework;
- eliminating duplicated authoritative logic.

Preserve externally observable behavior unless the milestone explicitly changes it.

---

# 13. Reasoning Level

Use reasoning effort proportional to the task.

## Low / routine

Appropriate for:

- exact text changes;
- known configuration edits;
- straightforward tests;
- commands with already-established behavior.

## Medium

Appropriate for:

- localized implementation;
- normal debugging;
- small refactors;
- adding tests around understood code.

## High

Appropriate for:

- reconnaissance;
- architecture decisions;
- database migration;
- framework replacement;
- deployment/control-plane interaction;
- concurrency or persistence risks;
- security-sensitive behavior;
- unexplained contradictions between evidence sources.

Do not spend high-reasoning effort rediscovering architecture that an accepted reconnaissance milestone already established unless new evidence contradicts it.

---

# 14. Deterministic Evidence First

Prefer direct evidence over assumptions.

Examples:

- inspect Git rather than infer Git state;
- run tests rather than assume compatibility;
- inspect actual imports/calls rather than infer coupling from filenames;
- inspect database schema rather than assume it;
- inspect container metadata rather than assume what commit is running;
- inspect Repo Control output rather than reproduce its logic manually.

When possible, use deterministic evidence to narrow the problem before applying AI interpretation.

---

# 15. AI Assessment Is Advisory

AI-generated assessment may identify:

- risks;
- architecture concerns;
- likely defects;
- test gaps;
- refactor opportunities.

It does not override deterministic evidence.

If AI interpretation conflicts with:

- Git;
- tests;
- database evidence;
- runtime evidence;
- Repo Control deterministic evidence;

preserve the deterministic facts and investigate the disagreement.

Do not mutate the repository solely because an AI assessment suggests doing so.

---

# 16. File-Reading Discipline

Read enough context to understand the task, but avoid uncontrolled repository-wide reading.

Preferred sequence:

1. current milestone prompt;
2. named controlling documents;
3. files explicitly named by the prompt;
4. direct dependencies/imports/callers;
5. relevant tests;
6. broader repository search only when necessary.

For implementation milestones following accepted reconnaissance, use the reconnaissance findings as the roadmap and verify only the specific assumptions needed for implementation.

---

# 17. Search Discipline

Repository search should be purposeful.

Use search to answer specific questions such as:

- where is Google Sheets accessed?
- where is quiz behavior implemented?
- which code imports Streamlit?
- what tests exercise synonym normalization?
- where is application configuration loaded?

Do not treat broad keyword search results as proof of architectural importance.

Distinguish:

- lexical matches;
- direct imports;
- calls;
- test references;
- actual runtime dependencies.

---

# 18. Testing Rules

Tests are part of implementation, not an optional cleanup step.

For each implementation milestone:

- run focused tests for changed behavior;
- run relevant regression tests;
- run the full suite when scope/risk warrants it;
- record exact commands;
- record literal results;
- do not report tests as passing unless they were actually run.

If tests fail:

1. determine whether failure is caused by current work;
2. preserve evidence;
3. fix only if within scope;
4. escalate if broader architecture or unrelated defects are involved.

Do not weaken tests merely to obtain a passing result.

---

# 19. Product Owner Validation

When the milestone requires live Product Owner validation:

1. bring the system to a stable testable state;
2. stop further mutation;
3. explain exactly what should be tested;
4. preserve the state while the Product Owner validates;
5. investigate contradictions before continuing.

Automated tests do not invalidate contradictory live behavior.

If the Product Owner observes a defect, treat the observation as evidence requiring classification.

---

# 20. Git Mutation Rules

Do not perform Git mutation unless authorized by the milestone or Product Owner.

Git mutation includes:

- stage;
- unstage;
- commit;
- amend;
- merge;
- rebase;
- reset;
- branch deletion;
- tag creation/deletion;
- push;
- force push.

Read-only Git inspection is normally allowed when relevant.

---

# 21. Staging Rules

When staging is authorized:

- use exact-file staging whenever practical;
- inspect staged file names;
- inspect staged diff/stat;
- run `git diff --cached --check`;
- ensure unrelated files are excluded.

Avoid:

`git add .`

or equivalent broad staging unless the milestone explicitly justifies it.

Do not stage:

- local virtual environments;
- credentials;
- caches;
- AI tool history;
- unrelated generated artifacts;
- files outside the accepted milestone.

---

# 22. Commit Rules

When commit authority is granted:

- commit only reviewed staged content;
- use a meaningful milestone-oriented commit message;
- record resulting commit SHA;
- verify post-commit repository state.

A successful commit does not automatically authorize push.

---

# 23. Push Rules

Push only with explicit authorization.

Before push, confirm:

- intended branch;
- intended remote;
- expected upstream;
- accepted commit.

Never force-push without explicit Product Owner approval and a documented reason.

---

# 24. Destructive Git Operations

The following require explicit approval:

- `git reset --hard`;
- destructive checkout/restore of unknown changes;
- forced branch movement;
- history rewriting;
- branch deletion when history is not clearly disposable;
- force push.

If destructive Git recovery appears necessary, stop and report first.

---

# 25. Whitespace and Generated Noise

Avoid changes that create large meaningless diffs.

Preserve existing line-ending conventions unless changing them is explicitly required.

Before closeout:

- inspect changed files;
- inspect diff statistics;
- use `git diff --check` or equivalent;
- identify accidental whitespace-only changes.

Do not reformat unrelated files merely because an editor or formatter can do so.

---

# 26. Secrets

Never commit or expose secrets.

Protected examples include:

- `service_account.json`;
- `.streamlit/` secret material;
- `.env` files containing real credentials;
- database passwords;
- API keys;
- private keys;
- authentication tokens.

Do not print secret values into:

- terminal evidence;
- tests;
- logs;
- closeouts;
- prompts;
- Repo Control artifacts.

Use safe placeholders when documentation requires examples.

---

# 27. `.aiderignore` and Tool Boundaries

The project may contain `.aiderignore` or similar AI-tool exclusions.

Respect those exclusions.

Do not bypass an exclusion merely because direct file access is technically possible.

If an excluded file appears necessary to complete a milestone, stop and request guidance.

Tool convenience does not override credential or project boundaries.

---

# 28. Database Mutation Rules

The planned project includes migration to a database hosted on `henderson-server1`.

Database inspection may be read-only when authorized.

Database mutation requires explicit milestone scope.

Potentially destructive operations require explicit Product Owner authorization, including:

- dropping tables;
- deleting production data;
- replacing persistent volumes;
- destructive migrations;
- bulk data replacement;
- resetting the database.

Prefer migrations that are:

- deterministic;
- testable;
- recoverable;
- auditable.

Do not treat persistent application data as disposable test state.

---

# 29. Container Mutation Rules

Container/runtime inspection may be read-only when relevant.

The following are mutations and require authorization:

- image build;
- container creation;
- container replacement;
- restart;
- stop/start;
- Compose `up`/`down`;
- volume creation/removal;
- network mutation;
- image deletion.

Do not modify unrelated containers or server services.

Vocab work must remain bounded to approved Vocab runtime resources.

---

# 30. Host-System Boundary

`henderson-server1` hosts other important applications and services.

Do not treat the server as a disposable development machine.

Do not:

- broadly change firewall rules;
- alter unrelated mounts;
- stop unrelated containers;
- modify unrelated system services;
- install broad system dependencies without authorization;
- change NAS configuration;
- modify Photo Organizer resources.

Host-level changes require explicit scope.

---

# 31. Photo Organizer Is Out of Scope

Photo Organizer is a separate project.

Do not inspect, modify, restart, migrate, or use Photo Organizer code, containers, databases, storage, or configuration during Vocab work unless explicitly authorized in a future milestone.

Existing Photo Organizer methodology may inform process documentation, but its runtime resources are not part of the Vocab testbed.

---

# 32. Code State vs. Deployment State

Never assume:

`committed = deployed`

or:

`deployed = healthy`

or:

`healthy = running current HEAD`

These are distinct facts.

When deployment work begins, preserve explicit evidence for:

- repository commit;
- image build identity;
- deployed container/service identity;
- runtime health;
- deployed source revision.

If the running application cannot identify its source revision, report that limitation.

---

# 33. Deployment Automation Rule

Do not automate a deployment workflow that has not first been proven manually and deterministically.

Preferred progression:

1. manual controlled procedure;
2. deterministic evidence;
3. reproducibility;
4. read-only Repo Control awareness;
5. guarded preparation;
6. explicit approval;
7. controlled execution;
8. verification.

Do not jump directly from “container runs” to “Repo Control automatically deploys.”

---

# 34. Application-Specific Logic Must Stay in Vocab

Repo Control must not need to understand Vocab business logic such as:

- what constitutes a vocabulary question;
- how distractor answers are selected;
- how definitions are scored;
- how vocabulary records are interpreted.

Those belong in Vocab.

Repo Control should reason about generic control-plane facts such as:

- repository identity;
- Git state;
- evidence;
- tests;
- build identity;
- deployment identity;
- health;
- approved mutation.

If a proposed Repo Control integration requires Vocab-specific business rules, stop and escalate the architectural boundary.

---

# 35. Error Handling

Do not conceal or auto-heal unexpected failures merely to keep a workflow moving.

For meaningful failures:

- preserve reason/evidence;
- leave state understandable;
- avoid destructive retries;
- report whether mutation already occurred;
- distinguish complete failure from “mutation succeeded but verification/audit failed.”

This distinction is particularly important for Git, database, and deployment operations.

---

# 36. Closeout Rules

Every completed implementation milestone should produce one authoritative closeout.

The closeout should contain only evidence that can be supported.

Record, as applicable:

- starting branch/HEAD;
- starting state;
- files changed;
- implementation summary;
- tests and literal results;
- runtime validation;
- Product Owner validation;
- Repo Control evidence;
- final Git state;
- limitations;
- deferred work;
- recommended next step.

Do not claim historical evidence was captured if it was not.

If exact starting evidence was not retained, state that explicitly.

---

# 37. Closeout Is Not a New Implementation Phase

Once implementation is accepted, closeout work should normally be documentation-only.

Do not use closeout preparation as an opportunity to:

- refactor;
- add features;
- clean unrelated code;
- change runtime behavior.

If closeout review exposes a real implementation defect, classify it explicitly and obtain approval before changing code.

---

# 38. Escalation Conditions

Stop and report rather than guessing when any of the following occurs:

- milestone assumptions materially conflict with current code;
- repository state is unexpected;
- required behavior needs a broader architecture change;
- a new dependency materially changes the design;
- a refactor becomes necessary but was not scoped;
- credentials would need to be exposed;
- database mutation exceeds authorization;
- container/host mutation exceeds authorization;
- Repo Control source modification appears necessary;
- tests reveal broader regression;
- current behavior cannot be preserved safely;
- unrelated work blocks progress;
- a destructive operation appears necessary.

---

# 39. Escalation Format

When escalating, report concisely:

## Finding

What was discovered.

## Evidence

Files, commands, tests, or runtime facts supporting it.

## Why It Matters

Impact on safety, architecture, scope, or acceptance.

## Options

Smallest viable paths.

## Recommendation

Preferred path and why.

Then stop at the relevant mutation boundary.

---

# 40. Do Not Manufacture Questions

Do not ask the Product Owner questions that repository inspection can answer safely.

First inspect the relevant evidence.

Ask when the decision genuinely requires:

- product intent;
- architectural preference;
- mutation authorization;
- security judgment;
- acceptance criteria;
- scope expansion.

The goal is to reduce unnecessary back-and-forth without making unauthorized assumptions.

---

# 41. Do Not Manufacture Work

Finding an improvement does not create authorization to implement it.

Classify discovered work as:

- required now;
- current-milestone defect;
- blocker;
- future improvement;
- unrelated.

Implement only what the milestone permits.

---

# 42. Minimal Safe Change Principle

Default to:

> the smallest coherent change that satisfies the approved requirement and can be verified confidently.

This does not mean choosing a shortcut that creates known architectural debt.

It means avoiding unnecessary expansion while still solving the actual problem correctly.

---

# 43. Preserve Useful Existing Behavior

Do not remove existing functionality simply because the future roadmap will eventually replace it.

Examples:

- Google Sheets remains until an approved database migration replaces it.
- Streamlit remains until an approved framework/runtime replacement occurs.
- existing quiz behavior remains until an approved quiz milestone changes it.

Transitions should be deliberate and testable.

---

# 44. Current Planned Product Changes

The current Product Owner direction includes three major Vocab changes:

1. change the test/quiz function to multiple choice;
2. move vocabulary words and definitions from Google Sheets to a database hosted on `henderson-server1`;
3. remove Streamlit and run the application directly from `henderson-server1`, first locally/LAN and later through controlled secure external access.

These are roadmap direction.

They are not authorization to implement all three at once.

Each must be scoped through approved milestones.

---

# 45. Optional Refactor Decision

A refactor may precede these changes if reconnaissance demonstrates material value.

The coding agent should specifically look for harmful coupling among:

- Streamlit presentation;
- quiz logic;
- vocabulary/business logic;
- Google Sheets data access;
- configuration;
- persistent state.

If separation would materially reduce risk across multiple approved future changes, recommend the smallest useful refactor.

Do not implement it during reconnaissance.

---

# 46. Repo Control Testbed Principle

Vocab is intended to expose Repo Control to increasingly realistic development workflows.

Use this sequence:

`real application need → real workflow → observed Repo Control capability/gap → architectural review → generalized Repo Control change if warranted`

Do not reverse it into:

`desired Repo Control feature → manufacture Vocab work to justify it`

The application remains a real product, not merely synthetic test data.

---

# 47. Evidence Quality

Prefer evidence that is:

- direct;
- reproducible;
- attributable to a specific state;
- understandable later;
- tied to a branch/HEAD/runtime identity where relevant.

Avoid vague claims such as:

- “looks good”;
- “should work”;
- “probably clean”;
- “seems deployed”;
- “tests were fine.”

Use literal evidence.

---

# 48. Completion Standard

Do not declare a milestone complete merely because code was written.

Completion requires the acceptance evidence defined by the milestone.

Depending on scope, this may include:

- tests passing;
- browser behavior validated;
- database migration verified;
- container healthy;
- Repo Control evidence reconciled;
- Product Owner acceptance;
- closeout completed.

If an acceptance requirement is incomplete, say so.

---

# 49. Working Rule

When uncertain, use this sequence:

1. **Inspect**
2. **Understand**
3. **Constrain**
4. **Implement**
5. **Test**
6. **Compare evidence**
7. **Escalate contradictions**
8. **Document**
9. **Mutate Git/runtime only with authority**
10. **Verify final state**

---

# 50. Core Principle

The coding agent should optimize for:

> **correct, bounded, reviewable work with evidence strong enough that another person can understand exactly what changed and why.**

Speed is valuable.

Uncontrolled scope, hidden assumptions, unverifiable mutation, and accidental architectural drift are not.

---

**End of `coding_agent_rules_v1.md`**
