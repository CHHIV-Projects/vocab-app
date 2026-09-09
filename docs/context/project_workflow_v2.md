# Vocab App — Project Context v2

**Document:** `vocab_app_project_context_v2.md`
**Project:** Vocab App
**Status:** Active controlling project context
**Version:** 2.0
**Supersedes:** `vocab_app_project_context_v1.md`
**Primary repository:** `/home/chuck/projects/vocab-app`
**Primary branch:** `main`
**Canonical GitHub repository:** `CHHIV-Projects/vocab-app`

---

# 1. Purpose

This document records the current authoritative project context for the Vocab App.

It supersedes `vocab_app_project_context_v1.md`.

Version 1 was written near the beginning of the Vocab modernization effort, when the application was still primarily understood as a small Windows/Streamlit/Google Sheets program and many architectural decisions were intentionally unresolved.

The project has since changed substantially.

The Vocab App now has:

- a canonical Linux-hosted repository;
- a self-hosted Docker runtime;
- PostgreSQL persistence;
- a production-scale local Wiktionary lexical dataset;
- supplemental WordNet evidence;
- a deterministic lexical evidence engine;
- local GPT-OSS synthesis through Ollama;
- deterministic synthesis validation;
- accepted-entry versioning;
- a learner-facing lexical workflow;
- an increasingly important role as a test bed for reliable local AI.

This document records:

- the purpose and product direction of the Vocab App;
- what has actually been implemented;
- current runtime and data architecture at a contextual level;
- lessons learned during modernization;
- the role of local AI;
- current reliability concerns;
- the distinction between implemented architecture and architectural exploration;
- the current milestone state;
- Repo Control integration principles;
- future project direction.

This is a project-context document.

It is not an implementation prompt.

Detailed technical architecture should be maintained separately in a dedicated architecture document.

---

# 2. Product Vision

The Vocab App is a personal vocabulary-learning application intended to make it easy to:

1. look up an unfamiliar word;
2. understand its meanings accurately;
3. preserve useful linguistic detail without overwhelming the learner;
4. save a trusted version of the word;
5. return to saved vocabulary later;
6. practice and learn saved vocabulary.

The product should provide considerably richer information than a simple single-definition dictionary while remaining approachable for ordinary use.

The target learner experience includes:

- clear definitions;
- distinct meanings;
- parts of speech;
- uncommon and historical meanings when supported;
- pronunciation;
- forms;
- synonyms;
- etymology;
- source evidence;
- later practice/testing capabilities.

The application should favor:

**reliability, completeness, traceability, and ease of use over artificial conversational fluency.**

---

# 3. Broader Project Purpose

The Vocab App has acquired a second important purpose.

It is now a practical test bed for learning how to integrate local AI reliably into real software.

The Product Owner wants local AI to become useful across several projects, including:

- Vocab App;
- Repo Control;
- future Shopping App;
- Photo Organizer semantic search and related capabilities.

The Vocab App is particularly useful for this experimentation because:

- the source evidence can be deterministic;
- lexical correctness can often be inspected;
- failures are observable;
- tasks can be decomposed into small semantic decisions;
- results can be validated against source evidence;
- the application is small enough to iterate quickly.

The goal is not merely to prove that a language model can run locally.

The goal is to determine:

**how local AI can become a dependable application component.**

---

# 4. Current Local-AI Working Principle

Experience through M004.4 and M004.5 has established an important project principle:

**Running a capable language model locally is not itself an application architecture.**

Reliable local AI requires:

- deterministic source evidence;
- bounded tasks;
- explicit model authority;
- code-owned identities and topology;
- structured input/output contracts;
- deterministic validation;
- caching;
- reproducible model/runtime identity;
- measurable failure handling;
- the ability to abstain or fail rather than fabricate;
- willingness to use non-LLM models where they are better suited.

The emerging rule is:

**AI should make semantic judgments. Code should own everything that must be structurally correct.**

This principle is now central to the project.

---

# 5. Historical Application

The original Vocab App was a Windows-oriented personal application.

Its historical structure included:

- Python;
- Streamlit;
- Google Sheets;
- local helper logic;
- Windows-oriented launch/runtime files;
- pronunciation/audio support;
- a vocabulary practice function.

Early project goals included:

- multiple-choice vocabulary testing;
- replacing Google Sheets with a server database;
- self-hosting the application;
- eventually replacing Streamlit;
- using the application as a real Repo Control testbed.

The modernization effort ultimately expanded well beyond the original persistence and hosting goals.

---

# 6. Canonical Repository

The authoritative Vocab repository is:

`/home/chuck/projects/vocab-app`

The authoritative application branch is:

`main`

The canonical GitHub repository is:

`CHHIV-Projects/vocab-app`

Current work must always inspect the actual repository state before implementation.

Historical SHAs recorded in earlier documents are contextual only and must not be treated as current HEAD.

---

# 7. Historical Repository Reconciliation

Before the current canonical repository was established, a sanitized Vocab copy existed at:

`/home/chuck/ai-agent-tests/vocab-app`

That copy was used extensively as a disposable Repo Control development/test fixture.

It had an independent Git history from the real Vocab repository.

Those histories were intentionally not merged.

The existing GitHub Vocab history was restored as canonical `main`, while testbed branches were preserved for historical/reference purposes.

Preserved historical branches may include:

- `archive/repo-control-testbed`;
- `archive/sanitized-testbed-base`;
- `archive/original-sanitized-main`;
- historical `agent-test/*` branches.

These are historical evidence, not canonical application history.

Useful ideas may be inspected and deliberately reimplemented when justified.

They must not be merged wholesale merely to recover old testbed changes.

---

# 8. Development Roles

The project generally uses three distinct roles.

## 8.1 Product Owner

The Product Owner:

- defines product direction;
- performs live acceptance testing;
- approves architectural decisions;
- determines milestone closure;
- controls Git publication decisions;
- decides when experimental work becomes accepted architecture.

## 8.2 Architect

ChatGPT generally acts as Architect.

The Architect:

- maintains project context;
- helps define architecture;
- decomposes work into milestones;
- reviews coder findings;
- identifies design risks;
- helps interpret failures;
- proposes controlled corrective work;
- protects milestone scope.

## 8.3 Coding Agent

The coding agent generally works through VS Code/Copilot/Codex-like tooling.

The coder:

- reads controlling context and milestone documents;
- performs reconnaissance;
- implements bounded changes;
- runs tests;
- produces evidence;
- updates milestone closeout documents.

The coding agent must follow `coding_agent_rules_v1.md`.

---

# 9. Git Authority Boundary

Going forward, coding agents must not perform:

- Stage;
- Commit;
- Push;
- Tag;
- Merge.

Those Git mutations belong to the Product Owner through Repo Control or explicit manual Git operations.

Coder prompts should explicitly preserve this boundary.

The coder may perform read-only Git inspection such as:

- `git status`;
- `git diff`;
- branch inspection;
- log inspection;
- upstream comparison.

---

# 10. Development Workflow

The preferred workflow is:

    Context / Architecture
            ↓
    Milestone reconnaissance
            ↓
    Architect/Product Owner review
            ↓
    bounded implementation
            ↓
    automated validation
            ↓
    deployed-runtime validation
            ↓
    Product Owner live acceptance
            ↓
    closeout review
            ↓
    Product Owner-controlled Git publication

Reconnaissance should generally be the highest-reasoning phase.

Implementation prompts should be narrower and should implement the smallest safe change supported by reconnaissance.

If implementation evidence contradicts the locked design or exposes a major architectural problem, the coding agent should stop and report rather than silently expanding scope.

---

# 11. Documentation Model

The project distinguishes:

## Context documents

Describe current accepted project truth.

## Architecture documents

Describe current technical architecture, locked design principles, and explicitly identified exploratory areas.

## Milestone prompts

Describe intended bounded work.

## Milestone closeouts

Describe what actually occurred.

## Git history

Preserves historical state and evolution.

Documents must not be silently rewritten to make historical development appear cleaner than it was.

---

# 12. Primary Runtime Environment

Primary host:

`henderson-server1`

Operating system:

Ubuntu Server 24.04 LTS

Repository:

`/home/chuck/projects/vocab-app`

The server currently provides:

- Docker CE;
- Docker Compose v2;
- PostgreSQL-capable container environment;
- NVIDIA container runtime;
- local Ollama/local-AI infrastructure;
- LAN access.

Relevant hardware includes:

- AMD Ryzen 9 7900X;
- 64 GB DDR5 RAM;
- NVIDIA GeForce RTX 5070 Ti with 16 GB VRAM;
- 2 TB NVMe storage.

The server hosts multiple projects and services.

Vocab changes must remain isolated from unrelated workloads.

---

# 13. Shared-Host Safety

Vocab work must not casually modify:

- unrelated Docker containers;
- unrelated Docker networks;
- firewall configuration;
- NAS mounts;
- Photo Organizer resources;
- Jellyfin resources;
- Repo Control runtime;
- unrelated databases;
- system-level services.

Any host-level change must be explicitly scoped and justified.

---

# 14. Current Runtime Topology

The Vocab application is now self-hosted through Docker Compose.

The current runtime includes:

    Browser
       |
       v
    Streamlit application container
       |
       +---- PostgreSQL
       |
       +---- lexical-data read-only mount
       |
       +---- WordNet read-only resources
       |
       +---- writable application runtime/cache path
       |
       +---- private Ollama service

Streamlit remains the current frontend/runtime, but it is no longer treated as a permanent architectural requirement.

It may be retained or replaced based on future UI/frontend reconnaissance.

---

# 15. Streamlit Status

The original context treated Streamlit removal as a locked future objective.

That is no longer the correct framing.

Current position:

- Streamlit is the existing frontend;
- it has allowed rapid delivery;
- its rerun/session-state model has exposed lifecycle complexity;
- it may not be the best long-term solution;
- replacement is permitted but not yet selected.

The project should not perform a framework migration in the middle of unrelated correctness work.

A future frontend milestone should compare alternatives based on:

- state management;
- responsiveness;
- mobile behavior;
- maintainability;
- API separation;
- development complexity;
- migration cost.

Possible future approaches may include:

- continuing Streamlit;
- FastAPI plus lightweight frontend;
- FastAPI plus a richer JavaScript framework;
- another evidence-supported architecture.

No frontend replacement is currently locked.

---

# 16. PostgreSQL Migration

The original Google Sheets persistence direction has been superseded.

PostgreSQL is now the active server-side application persistence system.

The current application retains a lightweight legacy/practice-oriented `vocabulary` representation while M004.5 introduced richer lexical acceptance/versioning tables.

The accepted-entry model includes:

- logical lexical entries;
- immutable accepted versions;
- active-version pointers;
- candidate snapshots;
- evidence snapshots;
- evidence hashes;
- model/resource/policy identities;
- flags.

The existing practice row/count semantics are intentionally preserved.

Google Sheets is no longer the normal authoritative application persistence path.

---

# 17. Accepted-Version Philosophy

Saving a lexical entry is not merely bookmarking a current lookup.

Save represents acceptance of a specific validated lexical candidate.

A saved version preserves:

- exact displayed candidate;
- exact evidence snapshot;
- evidence identity;
- synthesis/model identity;
- accepted version number;
- acceptance time.

Previous accepted versions should remain auditable.

A later accepted version does not silently rewrite historical evidence.

---

# 18. Save / Retry / Refresh Semantics

Current intended lifecycle semantics are:

## Save

Accept the current valid candidate as a durable version.

## Retry

For a saved entry, generate a new synthesis attempt from the same exact saved evidence snapshot.

Retry does not silently use newly changed lexical evidence.

## Refresh

Available only when current canonical lexical evidence produces a different full evidence hash than the saved version.

Refresh explicitly allows generation from the newer evidence.

## Flag

Allows the learner to mark a valid but unsatisfactory candidate.

Flag is intentionally simple and does not require a written explanation.

Invalid/system-failure candidates are not valid Save/Retry/Refresh/Flag candidates.

---

# 19. Production Lexical Evidence

M004.3/M004.3.1 established the production lexical evidence foundation.

Primary lexical source:

English Wiktionary

Extraction:

Wiktextract

Supplemental lexical source:

WordNet

The active production lexical root is approximately:

`/home/chuck/.local/share/vocab-lexical`

The current active dataset is:

`wiktionary-20260901`

The production build contains approximately:

- 1.58 million entries;
- 1.89 million senses;
- multi-gigabyte canonical JSONL evidence;
- multi-gigabyte SQLite runtime projection.

Exact current statistics should be taken from the active dataset manifest rather than relying permanently on this contextual snapshot.

---

# 20. Lexical Evidence Authority

Wiktionary/Wiktextract is the primary rich lexical evidence source.

WordNet is parallel supplemental evidence.

WordNet relationships must not automatically be assumed equivalent to Wiktionary senses.

The source hierarchy is:

    source evidence
        ↓
    canonical normalized evidence
        ↓
    bounded AI synthesis
        ↓
    deterministic validation
        ↓
    learner-facing candidate

The language model is never lexical authority.

Missing source evidence must remain missing rather than being invented.

---

# 21. Stable Evidence Identity

The lexical system uses stable evidence identity so that the application can distinguish:

- the same source content;
- changed source content;
- different datasets;
- different synthesis attempts;
- different accepted versions.

Evidence hashing and explicit resource identities support:

- reproducibility;
- caching;
- Refresh detection;
- versioning;
- troubleshooting;
- auditability.

---

# 22. Current Lexical Retrieval

Current normal lexical lookup begins with exact lemma retrieval from the local SQLite lexical projection.

An important known performance issue remains:

`normalized_lemma` exact lookup is not yet optimally indexed in the production projection.

This can produce several seconds of lexical lookup latency.

This is a database/indexing issue.

It is separate from local-AI synthesis performance and separate from future embedding work.

The active checksummed dataset should not be modified casually in place.

A corrected index should be incorporated into a future controlled lexical dataset build.

---

# 23. Dataset Refresh Direction

The project already has the architectural foundation for versioned lexical datasets:

    versions/
        wiktionary-YYYYMMDD/
        ...
    
    active
        -> selected version

A Wiktionary update is expected to be a controlled dataset-build operation rather than an uncontrolled application-time mutation.

A future update workflow should support approximately:

    obtain official dump
        ↓
    verify source
        ↓
    run pinned Wiktextract
        ↓
    normalize evidence
        ↓
    build runtime projection
        ↓
    build future semantic projections if applicable
        ↓
    validate
        ↓
    review
        ↓
    activate explicitly

Dataset construction and dataset activation should remain separate operations.

A scheduled fully automatic refresh is not currently required.

---

# 24. M004.2 — Lexical Architecture

M004.2 established the lexical architecture direction:

- Wiktionary/Wiktextract as primary evidence;
- WordNet as supplemental evidence;
- canonical normalized evidence;
- local runtime lexical projection;
- PostgreSQL for user/application state;
- local AI used only for bounded synthesis;
- deterministic validation;
- accepted-entry versioning;
- source attribution and licensing awareness.

This milestone marked the transition from the original simple dictionary design to the current evidence-driven lexical system.

---

# 25. M004.3 — Deterministic Lexical Engine

M004.3 implemented the deterministic lexical evidence engine.

It established:

- canonical evidence structures;
- stable IDs;
- deterministic serialization;
- evidence hashes;
- exact lemma lookup;
- separate WordNet evidence;
- deterministic tests and fixtures.

The purpose was to ensure that the model receives a controlled evidence package rather than querying lexical sources directly.

---

# 26. M004.3.1 — Production Dataset

M004.3.1 produced the first production-scale Wiktionary lexical dataset.

The dataset is immutable/versioned.

The application uses the `active` pointer to select the production dataset.

Production lexical evidence is intentionally external to the application image.

The lexical artifact is mounted read-only into the runtime.

---

# 27. M004.4 — Bounded GPT-OSS Lexical Synthesis

M004.4 established bounded local-AI lexical synthesis.

Current baseline model/runtime:

- GPT-OSS:20b;
- Ollama;
- private container/network path;
- deterministic evidence packages;
- structured output;
- deterministic validation;
- cached validated results.

The synthesis pipeline evolved through multiple reliability corrections.

A key breakthrough was replacing free-form model responsibility with code-owned aliases and closed structural contracts.

The M004.4 pipeline ultimately demonstrated successful synthesis for complex words including highly polysemous examples such as:

- `run`;
- `set`;
- `runner`;
- `running`;
- `archipelago`;
- `happiness`.

This demonstrated that meaningful local lexical synthesis is possible.

It did not demonstrate that every future fresh inference will succeed.

---

# 28. M004.4 Reliability Lesson

The most important M004.4 lesson was:

**Prompt instructions alone are insufficient for structural reliability.**

Reliability improved materially when the system changed from:

    "please include every sense"

to structures where:

- code created every required sense alias;
- the schema required every alias;
- the model could not silently omit required topology;
- code reconstructed canonical identities afterward.

This pattern should guide future local-AI work.

---

# 29. M004.5 — Learner UI + Save/Versioning

M004.5 introduced the learner-facing lexical lifecycle.

Implemented or substantially implemented functionality includes:

- learner-facing lexical display;
- POS-separated meanings;
- Core and Additional Meanings;
- forms/base links;
- source labels;
- U.S. pronunciation where available;
- gTTS audio;
- Source Details;
- Advanced Details;
- deterministic Wiktionary synonym enrichment;
- bounded source-based learner etymology;
- PostgreSQL accepted-entry versioning;
- Save;
- Retry;
- Refresh;
- Flag;
- framework-independent workflow/controller boundary.

M004.5 is intentionally treated as a PARTIAL checkpoint, not a full final acceptance.

---

# 30. M004.5 Runtime Incidents and Lessons

M004.5 exposed several important classes of real deployment problems.

## 30.1 Lexical mount permissions

The application container initially lacked permission to traverse/read the host lexical tree.

This was corrected with narrow POSIX ACLs rather than broad permission changes.

## 30.2 Immutable SQLite access

Read-only lexical SQLite required an immutable/open-read-only approach that avoids attempted journal/sidecar writes.

## 30.3 Runtime-path leakage

An old host path leaked into the container runtime configuration.

The runtime cache was moved to an explicit writable container path.

## 30.4 WordNet availability

WordNet was restored to the container using a controlled read-only resource mount.

## 30.5 Save row-shape bug

Persistence code incorrectly assumed tuple-style psycopg results while the live connection returned dictionary rows.

The failed transaction rolled back correctly.

## 30.6 False Saved state

The UI could appear to show a saved entry while PostgreSQL had no corresponding accepted version.

The correction required stronger database-authoritative state reconciliation.

## 30.7 Deployment staleness

The Product Owner continued seeing old behavior because the running Streamlit container contained older source than the repository.

Repository tests passed against current source while browser testing exercised a stale Docker image.

This became a major workflow lesson.

---

# 31. Code State vs. Deployment State

The project must explicitly distinguish:

## Code state

Examples:

- modified;
- staged;
- committed;
- branch/HEAD.

## Build state

Examples:

- current source not built;
- image built from source X.

## Deployment state

Examples:

- old image deployed;
- current image deployed;
- container recreated.

## Runtime state

Examples:

- healthy;
- unhealthy;
- responding;
- connected to expected DB/resources.

A successful repository test does not prove that the browser is running the same source.

Future browser acceptance should include deployment/source parity preflight.

---

# 32. Deployment Identity Requirement

A future mature runtime should make it easy to determine:

- repository commit/source identity;
- Docker image identity;
- container identity;
- application build time;
- deployed source parity;
- health state.

This remains an important Repo Control integration opportunity.

---

# 33. Current Local-AI Limitation

After the M004.5 deployment was synchronized correctly, a fresh lookup of:

`Utilitarian`

failed with:

`Model core selection was not a valid subset of POS groups`

This is significant because it represents a different failure class from runtime or deployment problems.

The deterministic validator correctly refused an internally invalid synthesis result.

That behavior is desirable.

However, the failure shows that the current model is still being given structural authority that may be better owned by code.

This failure is the immediate trigger for the next local-AI reliability arc.

---

# 34. M004.6 — Local AI Reliability & Architecture Exploration

The next major project arc should not merely fix `Utilitarian`.

The objective is broader:

**Determine how to integrate local AI into the Vocab App in a way that is demonstrably reliable, measurable, and transferable to other applications.**

M004.6 should investigate:

- current synthesis contracts;
- model-owned versus code-owned responsibilities;
- known and anticipated failure modes;
- alternative local models;
- smaller models;
- specialized models;
- embedding models;
- constrained decoding;
- runtime alternatives;
- task routing;
- deterministic preprocessing;
- deterministic postprocessing;
- selective escalation;
- reliability benchmarks;
- possible future fine-tuning.

No particular new model or architecture should be considered locked before measured evidence supports it.

---

# 35. Local-AI Architectural Exploration

Current exploratory direction suggests a future pattern such as:

    deterministic retrieval
            ↓
    deterministic evidence normalization
            ↓
    specialized local model(s)
            ↓
    bounded semantic judgment
            ↓
    deterministic assembly
            ↓
    deterministic validation
            ↓
    accept / fail

Potential specialized components may include:

- text embedding models;
- image/text embedding models in other projects;
- small classification/ranking LLMs;
- stronger reasoning models used only for ambiguity;
- deterministic Python orchestration;
- grammar/schema-constrained decoding.

These are exploratory directions, not yet accepted implementation architecture.

---

# 36. Embedding Exploration

Embeddings are an important candidate for M004.6.

An embedding model converts text into a numerical vector representing semantic relationships.

For the Vocab App, the most promising use is likely sense-level embeddings.

Conceptually:

    canonical Wiktionary sense
            ↓
    embedding model
            ↓
    stored sense vector

Sense vectors can then be compared to identify:

- clearly dissimilar senses;
- strongly similar senses;
- ambiguous pairs requiring additional judgment.

This could reduce the amount of semantic grouping work delegated directly to an LLM.

Embeddings should not replace:

- exact lemma retrieval;
- source evidence;
- POS;
- stable IDs;
- deterministic validation.

They would supplement those systems.

---

# 37. Embedding Build Direction

If adopted, lexical embeddings should generally be produced as part of a controlled dataset/index build rather than recomputed for every lookup.

Conceptually:

    Wiktionary dataset
        ↓
    canonical senses
        ↓
    embedding projection
        ↓
    stored versioned vectors

Normal lookup could then retrieve existing sense embeddings immediately.

A future lexical dataset manifest should identify:

- embedding model;
- model digest/version;
- embedding projection version;
- source dataset identity.

Changing embedding models may require rebuilding the embedding projection because vectors from unrelated embedding spaces should not be mixed casually.

---

# 38. Exact Retrieval vs. Semantic Retrieval

The project distinguishes three different operations.

## 38.1 Exact lexical retrieval

Example:

`run`

Find canonical entries where normalized lemma is exactly `run`.

This should use conventional indexed database lookup.

## 38.2 Semantic similarity

Example:

Determine whether:

`to move quickly on foot`

and:

`to travel rapidly using one's legs`

represent closely related meanings.

This is a potential embedding task.

## 38.3 Semantic search

Example future request:

`words related to wandering without direction`

This could use query embeddings and vector retrieval.

These are separate engineering problems and should not be conflated.

---

# 39. Alternative Model Exploration

GPT-OSS:20b remains the current baseline local language model.

It should not be assumed to be the final or universally best model.

M004.6 may evaluate:

- smaller general-purpose models;
- alternative reasoning models;
- code-specialized models for Repo Control;
- task-specific models;
- multimodal models where relevant;
- embedding models;
- multiple-model routing.

Potential advantages of smaller models include:

- lower VRAM use;
- faster loading;
- faster inference;
- ability to keep multiple specialized models available;
- potentially better behavior on narrow classification/structured tasks.

Model choice should be empirical.

---

# 40. Runtime Exploration

Ollama remains the current local-model runtime.

It has been useful because it provides:

- simple model management;
- local API access;
- container integration;
- structured-output support.

However, M004.6 may compare alternative runtimes if they offer stronger guarantees or performance.

Areas of interest include:

- grammar-constrained decoding;
- dynamic JSON schemas;
- model residency/load behavior;
- GPU utilization;
- deterministic inference behavior;
- observability;
- reproducibility.

No runtime migration is currently locked.

---

# 41. Deterministic Orchestration vs. Agent/Crew Architecture

The project should not assume that multiple autonomous AI agents improve reliability.

A multi-agent system can multiply:

- stochastic decisions;
- prompts;
- latency;
- GPU usage;
- debugging complexity.

The preferred initial direction is:

**Python/code is the orchestrator. Specialized AI models are bounded workers.**

Conceptually:

    Python controller
        |
        +-- lexical database
        +-- embedding model
        +-- small LLM
        +-- reasoning LLM if needed
        +-- deterministic validator

This may resemble a "crew" conceptually, but authority remains deterministic.

A future multi-model/agent strategy should be adopted only when benchmarks demonstrate a clear benefit.

---

# 42. Conservative AI Escalation

A promising future pattern is:

    easy/deterministic case
        -> code handles it
    
    high-confidence embedding result
        -> code handles/ranks it
    
    bounded semantic ambiguity
        -> small local model
    
    difficult semantic ambiguity
        -> stronger local model
    
    invalid/uncertain result
        -> fail or preserve separation

The project should favor conservative results over hidden repair.

For lexical grouping, disagreement or uncertainty may appropriately mean:

`keep meanings separate`

rather than forcing a merge.

---

# 43. Fine-Tuning Direction

Fine-tuning is not an immediate objective.

The project should first build:

- task definitions;
- reliability benchmarks;
- failure corpora;
- known-good expected outputs;
- model comparisons.

Once sufficient examples exist, a small fine-tuned local model may become worth evaluating.

The project should not fine-tune simply because the capability exists.

---

# 44. Reliability Measurement

Future local-AI acceptance should be based on measured evidence rather than a small collection of successful examples.

M004.6 should eventually establish a representative lexical benchmark containing categories such as:

- simple words;
- many-sense words;
- multiple parts of speech;
- inflected forms;
- technical/philosophical terms;
- archaic senses;
- figurative uses;
- register-heavy terms;
- rich etymologies;
- homonyms.

Testing should record stage-level outcomes such as:

- success/failure;
- failure category;
- latency;
- evidence identity;
- model identity;
- seed/settings;
- token usage;
- structured-output validity;
- deterministic-validator outcome.

The project should determine reliability targets only after establishing a measured baseline.

---

# 45. Structural Correctness Standard

The following should remain hard requirements regardless of model choice:

- no invalid result is accepted;
- no source evidence is silently dropped when completeness is required;
- no unknown identity enters an accepted candidate;
- no cross-POS structural corruption;
- no unsupported lexical fact becomes authoritative;
- invalid synthesis is not cached as valid;
- accepted versions preserve exact evidence;
- system failure remains failure rather than hidden repair.

The goal is not to guarantee that a local LLM never makes a mistake.

The goal is to build a system where model mistakes cannot silently become trusted application state.

---

# 46. User-Facing Failure Philosophy

Technical diagnostics should be rich for development.

Learner-facing errors should remain simple.

For example:

`Lexical synthesis failed validation.`

Developer diagnostics may separately retain:

- failure code;
- failed stage;
- source/evidence hash;
- model digest;
- inference configuration;
- raw bounded model output where appropriate;
- validator reason;
- runtime timing.

This supports troubleshooting without exposing internal implementation complexity to normal users.

---

# 47. Product UI Direction

The learner UI should generally present:

- word;
- pronunciation/audio;
- part of speech;
- approximately 3–5 core learner meanings per POS where appropriate;
- Additional Meanings containing remaining distinct meanings;
- synonyms tied to specific meanings when source-supported;
- forms;
- etymology;
- source details;
- advanced diagnostic/evidence information only on demand.

The application should preserve uncommon, archaic, technical, and historical meanings when source evidence supports them.

Those meanings need not dominate the default view.

---

# 48. Source Details Direction

Source Details should be human-readable evidence disclosure.

It should not resemble raw Python/JSON structures.

The current M004.5 UI has exposed cases where source examples or evidence structures were rendered too literally.

This remains a UI-hardening item.

Source transparency remains required, but presentation should be intentionally learner-readable.

---

# 49. Mobile Direction

The Product Owner wants the Vocab App to be usable from normal desktop and mobile devices.

Desktop and mobile may eventually use different layouts.

They should preserve the same core product semantics.

Mobile support should be considered during future frontend architecture work rather than treated as an afterthought.

---

# 50. Practice / Quiz Functionality

The historical vocabulary practice function remains part of the product.

The early goal of a multiple-choice quiz has not been abandoned.

However, lexical evidence, persistence, and local-AI work took priority during M004.

Practice functionality should eventually consume accepted/saved lexical state rather than relying on obsolete Google Sheets assumptions.

Quiz redesign should occur as a separate bounded product milestone.

---

# 51. Repo Control Relationship

Repo Control remains a separate repository:

`/home/chuck/projects/repo-control`

Vocab is a real product used to expose genuine development-control requirements.

The relationship should remain:

    real Vocab need
        ↓
    real workflow evidence
        ↓
    Repo Control capability or gap

not:

    desired Repo Control feature
        ↓
    artificial Vocab work

Repo Control must not become Vocab-specific.

---

# 52. Repo Control Lessons From Vocab

Vocab has already exposed important generalized workflow needs, especially:

- separating code state from deployment state;
- proving deployed source identity;
- preserving immutable review evidence;
- preventing coding agents from self-publishing;
- controlled milestone closeout;
- using real runtime evidence during acceptance.

These lessons may inform future Repo Control milestones but should not be implemented inside the Vocab repository unless explicitly approved.

---

# 53. Relationship to Shopping App

The future Shopping App is expected to rely heavily on local AI.

Likely relevant lessons from Vocab include:

- deterministic sources remain authoritative;
- AI should not invent prices/specifications;
- embeddings may assist product similarity and normalization;
- small models may perform extraction/classification;
- stronger models may resolve ambiguity;
- code should calculate ranking, totals, tax/shipping logic, and confidence where deterministic inputs allow it;
- local-AI reliability should be measured before broad rollout.

Vocab therefore serves as a lower-risk proving ground for architecture that may later be reused in Shopping.

---

# 54. Relationship to Photo Organizer

Photo Organizer may eventually use semantic image search.

The likely architecture differs from lexical LLM synthesis.

A vision-language embedding model such as a CLIP/SigLIP-family approach may be more appropriate for large-scale image semantic retrieval.

Conceptually:

    photos
        ↓
    precomputed image embeddings
        ↓
    vector index
    
    user query
        ↓
    text embedding
        ↓
    nearest-neighbor retrieval

An LLM could later help interpret complex queries or summarize results.

The lesson is important:

**The correct local-AI tool depends on the task.**

The project should not default to an LLM when an embedding model, classifier, deterministic algorithm, or specialized model is more appropriate.

---

# 55. Current Milestone State

At the time this v2 context is composed:

## M001

Canonical repository/project-control foundation — complete.

## M002 / M002.1

Architecture reconnaissance and bounded refactor decision — complete.

## M003

Bounded application refactor — complete.

## M004

Self-hosted PostgreSQL/container baseline — complete.

## M004.1

External dictionary/service cleanup — partial/transition work completed.

## M004.2

Lexical evidence architecture — complete.

## M004.3

Deterministic lexical engine — complete.

## M004.3.1

Production Wiktionary lexical dataset — complete.

## M004.4

Bounded GPT-OSS lexical synthesis and deterministic validation — complete.

## M004.5

Learner-facing lexical UI + Save/versioning — substantial implementation complete but accepted as a PARTIAL checkpoint.

## M004.6

Local AI reliability and architecture exploration — next major arc.

Actual Git history and milestone closeouts remain authoritative for exact implementation details.

---

# 56. Proposed M004.6 Structure

The current planning direction is approximately:

## M004.6.0 — Local AI System Reconnaissance

No implementation.

Inventory:

- AI tasks;
- contracts;
- model authority;
- deterministic alternatives;
- embeddings;
- runtimes;
- failure modes.

## M004.6.1 — Model / Runtime Benchmarking

Establish GPT-OSS/Ollama baseline and evaluate credible alternatives.

## M004.6.2 — Deterministic Contract Hardening

Reduce model-owned structural topology.

## M004.6.3 — Specialized Model Routing

Evaluate embeddings, smaller models, escalation, and task decomposition.

## M004.6.4 — Reliability Benchmark

Run a representative controlled corpus with repeated fresh inference.

## M004.6.5 — Architecture Decision

Select model/runtime/routing strategy based on measured evidence.

## M004.6.6 — Production Hardening

Implement and validate the chosen architecture.

Exact subdivision may change after M004.6.0 reconnaissance.

---

# 57. Implemented vs. Locked vs. Exploratory

Future documentation must distinguish three states.

## 57.1 Implemented

Examples:

- PostgreSQL;
- Wiktionary/Wiktextract evidence;
- WordNet supplemental evidence;
- SQLite lexical projection;
- GPT-OSS:20b;
- Ollama;
- deterministic validation;
- accepted lexical versioning;
- current Streamlit UI.

## 57.2 Locked principles

Examples:

- source evidence remains authoritative;
- AI does not invent lexical truth;
- code owns identity;
- accepted versions are traceable;
- invalid synthesis fails;
- no hidden repair;
- model/runtime identity is recorded;
- Git publication is Product Owner-controlled.

## 57.3 Exploratory

Examples:

- embeddings;
- alternate LLMs;
- smaller LLMs;
- multimodel routing;
- llama.cpp/vLLM or other runtimes;
- constrained decoding alternatives;
- multiple-model verification;
- fine-tuning;
- frontend replacement.

Exploratory items must not be described as implemented architecture until accepted by evidence.

---

# 58. Credential and Secret Boundaries

Real secrets must remain outside Git.

Protected material includes:

- `.env`;
- API tokens;
- private keys;
- service credentials;
- authentication secrets;
- runtime-specific secret configuration.

AI coding tools must not bypass protected file exclusions without explicit authorization.

---

# 59. Runtime Data Boundaries

The repository should not contain large mutable runtime data.

Examples that belong outside the Git repository include:

- production Wiktionary artifacts;
- lexical SQLite projections;
- future embedding indexes;
- synthesis cache;
- PostgreSQL data volumes;
- NLTK/WordNet runtime data;
- large model files.

The repository should contain:

- build logic;
- schemas;
- migration logic;
- manifests/specifications;
- configuration templates;
- tests;
- application source.

---

# 60. Safety Boundaries

Until explicitly changed by a milestone:

- do not merge unrelated historical Git histories;
- do not commit secrets;
- do not modify Repo Control during a Vocab milestone;
- do not modify Photo Organizer during a Vocab milestone;
- do not modify Shopping App during a Vocab milestone;
- do not modify unrelated Docker resources;
- do not destroy PostgreSQL volumes;
- do not mutate checksummed lexical artifacts casually;
- do not expose the application publicly without an approved network/security design;
- do not let coding agents Stage/Commit/Push/Tag/Merge;
- do not weaken deterministic validation merely to make a failing model output pass.

---

# 61. Current Known Gaps

Known or partially unresolved areas include:

- full Save/Retry/Refresh/Flag lifecycle acceptance;
- additional live browser validation;
- Source Details presentation cleanup;
- mobile UX refinement;
- exact lexical lookup indexing/performance;
- robust local-AI fresh-inference reliability;
- final model selection;
- final local-AI runtime selection;
- embedding architecture;
- frontend framework decision;
- multiple-choice practice redesign;
- controlled remote-access architecture;
- formal runtime/deployment identity integration with Repo Control.

These are active roadmap items, not evidence that the completed foundation should be discarded.

---

# 62. Current Success Definition

The Vocab project succeeds when it becomes:

1. a useful vocabulary-learning application;
2. a reliable self-hosted service;
3. an evidence-backed lexical system;
4. a safe place to save/version learner vocabulary;
5. a practical demonstration of bounded local AI;
6. a measured test bed for determining when local AI works and when other techniques are preferable;
7. a source of reusable architecture lessons for Repo Control, Shopping, and Photo Organizer.

---

# 63. Core Product Principle

The learner should not need to understand the complexity of the underlying architecture.

The internal system may involve:

- source datasets;
- evidence IDs;
- hashes;
- local models;
- embeddings;
- validators;
- versioning;
- caches.

The normal user experience should remain:

    search a word
        ↓
    receive a trustworthy explanation
        ↓
    inspect additional detail if desired
        ↓
    save it
        ↓
    learn it later

---

# 64. Core Engineering Principle

The project’s current engineering philosophy is:

**Use deterministic software for identity, evidence, structure, persistence, validation, and control; use local AI only where semantic judgment adds value; measure its reliability; and never allow model convenience to silently weaken application correctness.**

---

# 65. Current Working Principle

The original v1 principle remains valid but has expanded.

Version 1 stated:

**Evolve Vocab as a real application, use its real development needs to exercise Repo Control, and preserve enough deterministic evidence that code, decisions, and runtime state remain understandable later.**

Version 2 extends that principle:

**Evolve Vocab as a real application and as a controlled local-AI test bed. Keep source evidence authoritative, make AI responsibility deliberately narrow, move structural correctness into deterministic code wherever practical, measure model reliability instead of assuming it, and carry successful patterns into other applications only after they are proven.**

---

# 66. Document Transition

Upon Product Owner approval:

- `vocab_app_project_context_v2.md` becomes the controlling Vocab project context;
- `vocab_app_project_context_v1.md` may be removed from the active documentation set;
- v1 remains preserved through Git history;
- future chats should read v2 rather than reconstructing the project from v1 plus milestone history.

The companion architecture document should be created from scratch as:

`vocab_app_architecture_v2.md`

That architecture document should explicitly separate:

1. CURRENT / IMPLEMENTED architecture;
2. LOCKED architectural principles;
3. EXPLORATORY / M004.6 architecture candidates.

---

**End of `vocab_app_project_context_v2.md`**
