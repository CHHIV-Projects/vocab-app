# Vocab App Milestone M004

# Self-Hosted PostgreSQL and Always-On Service Baseline

**Prompt file:** `milestones/004_self_hosted_postgresql_and_always_on_service_baseline_prompt.md`
**Required closeout:** `milestones/004_self_hosted_postgresql_and_always_on_service_baseline_closeout.md`
**Mode:** Bounded implementation
**Reasoning:** High
**Target repository:** `/home/chuck/projects/vocab-app`
**Target host:** `henderson-server1`

---

# 1. Objective

Convert the current Vocab application into a genuinely self-hosted, always-on service on `henderson-server1`.

M004 must establish the durable application architecture:

- Vocab application runs in a container;
- PostgreSQL runs on `henderson-server1` as Vocab's operational database;
- PostgreSQL may begin with an empty Vocab database; legacy Google Sheets data is not migrated in M004;
- normal application runtime no longer depends on Google Sheets;
- Streamlit remains the temporary UI layer;
- the application remains continuously available through a browser while the server is running;
- desktop and mobile browsers on the local network can reach the service;
- persistent PostgreSQL data survives container recreation/restart;
- secrets remain outside Git and outside the application image.

M004 is the self-hosted platform cutover.

It is not merely a container demonstration.

## Product Owner controlling clarification

This clarification supersedes conflicting earlier wording in this prompt while preserving the original prompt as milestone history.

- The local `main` branch must be at upstream parity before M004 implementation begins. Do not begin while local `main` is ahead of `origin/main`.
- M004 does not include Google Sheets migration, legacy header inspection, source-row fidelity verification, migration credentials, dry-run migration, duplicate-conflict resolution, or a Google migration reader.
- The new PostgreSQL database may start empty. Do not access the live Google Sheet merely for historical migration.
- Google Sheets must not participate in normal runtime, fallback, dual-write, or ongoing synchronization. The operational path is application -> PostgreSQL.
- Existing external definition, translation, pronunciation, and TTS services may remain. M004 self-hosting applies to the application runtime, canonical persistence, and always-on LAN service, not elimination of every external enrichment service.
- Use the official PostgreSQL `17` image, pinned to major version 17.
- Use external operator-owned runtime configuration at `/home/chuck/.config/vocab-app/runtime.env` when ordinary permissions allow. Keep real values outside Git, with restrictive permissions such as `600`, and never print passwords.
- Use application port `8501` if preflight confirms it is free. Confirm the current server LAN address; the expected address is `192.168.1.173`.
- Docker and Docker Compose operations are authorized for the Vocab project only. Do not modify unrelated stacks or Docker daemon configuration. Stop if Docker unexpectedly requires privileged access.
- If UFW blocks LAN access, stop and provide the exact minimal LAN-only command for the Product Owner; do not modify the firewall directly.
- The Product Owner will validate desktop access from a same-LAN Windows PC and mobile access from a phone on the same home Wi-Fi. The coder must provide the exact LAN URL and record the validation gate.
- M004 PASS accepts an empty/new PostgreSQL database and requires PostgreSQL-only persistence, persistent storage, always-on restart behavior, container/runtime validation, tests, and Repo Control evidence.

The controlling persistence architecture is:

```text
Vocab application -> PostgreSQL
```

The Google Sheets adapter may be removed or retained only for bounded code-history/testing reasons; it must not participate in normal runtime.

---

# 2. Long-Term Product Direction

The Product Owner's target architecture is a fully self-hosted Vocab application on `henderson-server1`.

The eventual user experience is:

    Desktop browser
          \
           \
            -> henderson-server1 -> Vocab application -> PostgreSQL
           /
          /
    Mobile browser

The service should be available whenever the server is running.

Google Sheets is not part of the permanent runtime architecture.

Streamlit is temporary but may remain in M004 because Streamlit itself is fully self-hostable.

The planned roadmap is now:

- **M003** — bounded refactor and characterization tests — complete;
- **M004** — PostgreSQL + containerized always-on self-hosted service with an empty/new operational database — this milestone;
- **M005** — multiple-choice practice;
- **M006** — replace Streamlit with the permanent self-hosted web UI;
- **M007+** — secure external access, deployment hardening, and later product enhancements.

Do not retain Google Sheets operationally merely because the old application used it.

Do not replace Streamlit in M004.

---

# 3. M003 Foundation

Treat accepted M003 as the controlling application baseline.

Relevant closeout:

`milestones/003_bounded_refactor_and_characterization_tests_closeout.md`

M003 established:

    app.py
        Streamlit UI/orchestration
    
    vocab_domain.py
        practice/scoring domain behavior
    
    vocab_persistence.py
        bounded persistence seam
        current Google Sheets implementation
    
    vocab_nlp.py
        bounded NLTK/synonym behavior
    
    tests/
        characterization suite

M004 should use the persistence seam created in M003 rather than bypassing or redesigning it.

The purpose of that seam is now realized:

    existing application/domain behavior
             |
             v
    persistence boundary
             |
             +--> PostgreSQL adapter — permanent runtime implementation

---

# 4. Service Availability Goal

The Vocab service is intended to be an always-on household service.

After M004 cutover:

- Docker should automatically restart the Vocab application and database after Docker/server restart;
- ordinary use should not require SSH commands or manually starting Streamlit;
- desktop browsers on the LAN should be able to open Vocab directly;
- mobile browsers on the same LAN/Wi-Fi should be able to open the same service;
- application data remains in PostgreSQL across container recreation.

Use an appropriate Docker restart policy such as:

`unless-stopped`

for both the Vocab application and its database.

Do not require the Product Owner to launch the application manually for normal use.

---

# 5. Network Scope

M004 provides local-network access.

The server currently has a stable LAN identity.

Confirm current reality before hard-coding an address, but the known server address is:

`192.168.1.173`

Prefer binding the application to the server's LAN address rather than indiscriminately publishing on every host interface if Docker/host topology permits it cleanly.

The intended access pattern is conceptually:

    Desktop:
    http://192.168.1.173:<vocab-port>
    
    Mobile on home Wi-Fi:
    http://192.168.1.173:<vocab-port>

Use application port `8501` if preflight confirms it is free, and document the result.

Do not configure:

- public Internet exposure;
- router port forwarding;
- DDNS;
- TLS;
- reverse proxy;
- Cloudflare Tunnel;
- public authentication;
- direct public Streamlit exposure.

Secure external/mobile-away-from-home access belongs to a later milestone.

Do not weaken the server firewall.

If a UFW rule is required for LAN access, STOP at the operator boundary and provide the exact minimal command for the Product Owner to execute rather than running privileged commands yourself.

---

# 6. Starting Git Gate

Before implementation:

    cd /home/chuck/projects/vocab-app
    
    pwd
    git branch --show-current
    git rev-parse HEAD
    git status --short
    git remote -v
    git rev-parse @{upstream} 2>/dev/null || true
    git rev-list --left-right --count HEAD...@{upstream} 2>/dev/null || true
    git log -6 --oneline --decorate

Confirm:

- branch is `main`;
- accepted M003 implementation/closeout is committed;
- upstream parity exists;
- M004 prompt is committed before implementation;
- working tree contains no unexplained source changes.

Capture the actual M003/M004 starting SHA.

Do not infer it from prior conversation. The Product Owner will restore upstream parity before implementation; a local-ahead state is a stop condition.

STOP if state is unexpected.

Do not reset, restore, clean, or overwrite unexplained work.

---

# 7. Repo Control Usage

Use Repo Control as the control plane throughout M004.

Repo Control repository:

`/home/chuck/projects/repo-control`

Do not modify Repo Control.

Do not access Photo Organizer.

At M004 start:

1. inspect deterministic Vocab Git state;
2. perform meaningful Context queries;
3. create or identify the clean M004 baseline Snapshot.

Useful concepts include:

- persistence;
- Google Sheets;
- `GoogleSheetsPersistence`;
- `get_persistence`;
- practice;
- score update;
- Streamlit;
- application entry point.

After implementation:

1. inspect deterministic Git state;
2. run useful Context discovery against the new PostgreSQL/container structure;
3. create post-change Snapshot evidence;
4. create a baseline-to-post Comparison where meaningful;
5. record artifact IDs in the closeout.

Source, tests, database inspection, and Docker evidence remain authoritative.

Do not treat partial structural coverage of untracked files as complete evidence.

The coding agent is not authorized to Stage or Commit M004.

---

# 8. Short Schema / Persistence Reconnaissance

Before designing PostgreSQL tables, inspect the actual canonical M003 persistence model and application behavior.

Identify exactly:

- fields represented by the current vocabulary record;
- fields written by the M003 save path;
- fields read by the application;
- score/Count field semantics;
- case-insensitive duplicate behavior;
- history and ordering semantics actually used by the application;
- empty/null/default behavior characterized by M003.

Do not invent a PostgreSQL schema from assumptions or add future-feature columns.

Document the source-to-database mapping in the closeout.

The operational database may start empty. Do not access the live Google Sheet for historical schema or data migration.

Keep this reconnaissance bounded.

---

# 9. PostgreSQL Architecture

Use a dedicated PostgreSQL service for Vocab.

Preferred architecture:

    compose.yaml
    
      vocab-app
          |
          | internal Docker network
          v
      vocab-db
          |
          v
      persistent PostgreSQL volume

Do not attach Vocab to an unrelated application's PostgreSQL database.

Do not inspect or modify Photo Organizer's database.

Do not reuse another project's database credentials.

Use the official PostgreSQL `17` container image, pinned to major version 17.

PostgreSQL should not need to publish its database port to the LAN.

Only the Vocab application needs to communicate with it through the Compose network.

---

# 10. PostgreSQL Persistence

Implement a PostgreSQL persistence adapter behind the M003 persistence boundary.

Normal application behavior after cutover must use PostgreSQL.

Preserve existing application semantics, including:

- vocabulary loading;
- practice loading;
- history behavior;
- duplicate detection;
- vocabulary creation;
- score lookup;
- score updates;
- Count behavior characterized in M003.

Do not redesign domain behavior while changing storage.

Avoid a large ORM/repository architecture unless the existing code clearly requires it.

Prefer the smallest maintainable PostgreSQL implementation.

A lightweight PostgreSQL driver such as `psycopg` is appropriate if consistent with the design.

If a materially larger persistence framework becomes necessary, STOP and report before introducing it.

---

# 11. PostgreSQL Schema

The schema must represent the current canonical vocabulary data faithfully.

Use appropriate PostgreSQL data types based on actual source fields.

Preserve the existing case-insensitive duplicate rule for vocabulary words.

Where practical, enforce that rule at the database level rather than relying solely on UI checks.

For example, a unique expression/index based on normalized/lowercase word identity may be appropriate if it matches current semantics.

Preserve ordering/history semantics where the existing product actually depends on them.

Do not add speculative future columns for multiple-choice or future UI work.

---

# 12. Schema Initialization / Evolution

Provide a repository-controlled and reproducible way to initialize the Vocab PostgreSQL schema.

Use the smallest maintainable method.

Acceptable directions include:

- versioned SQL migration files with a small runner;
- another lightweight existing repository-compatible mechanism.

Avoid relying solely on hand-entered SQL.

Avoid making database initialization dependent on an already-populated Docker volume.

Do not introduce a large migration framework unless justified.

The schema must be reproducible from source control.

---

# 13. Database Configuration

Supply PostgreSQL/application configuration through runtime environment variables or an equivalent external configuration mechanism.

Typical values may include:

- database host;
- database name;
- database user;
- database password;
- database port.

Do not commit real secrets.

A committed `.env.example` or equivalent documentation containing variable names and safe placeholders is acceptable. The preferred operator-owned runtime file is `/home/chuck/.config/vocab-app/runtime.env` when ordinary permissions allow it.

The real server values must remain outside Git and should have restrictive permissions such as `600`. If creating the configuration location requires privilege, stop and provide the exact operator command.

Do not print real passwords into logs or closeout evidence.

---

# 14. PostgreSQL Persistence Volume

PostgreSQL data must survive:

- application container recreation;
- database container recreation;
- Compose restart;
- image rebuild.

Use a dedicated named Docker volume or an equally controlled server-owned persistence location.

Do not place active PostgreSQL data inside the Git repository.

Do not use an ephemeral anonymous volume for the operational database.

Document the volume name/location.

Do not delete or recreate the operational volume during routine validation.

## 15. Superseded legacy Google Sheets migration scope

The original sections 15 through 18 described a controlled Google Sheets migration. The Product Owner clarification supersedes those requirements for M004.

M004 must not:

- access the live Google Sheet for historical migration;
- inspect legacy headers or source rows;
- require Google migration credentials;
- implement dry-run or transactional Google-to-PostgreSQL migration;
- resolve legacy duplicate conflicts;
- perform source/target fidelity verification;
- retain a Google migration reader for this milestone.

The PostgreSQL database may start empty. Google Sheets is not part of normal runtime, fallback, dual-write, or synchronization. The existing GoogleSheetsPersistence implementation may be removed or retained only for bounded code-history/testing reasons, and must not participate in operational persistence.

M004 PASS does not require legacy migration or migration discrepancy reporting. The PostgreSQL database may begin empty.

---

# 19. Runtime Cutover

    Vocab application
          |
          v
      PostgreSQL

must be the normal runtime path.

The normal application container must not require:

- Google Sheets availability;
- Google service-account credentials;
- Streamlit Google secrets;
- a live Google network connection for persistence.

Do not implement dual-write.

Do not implement ongoing Google/PostgreSQL synchronization.

Do not keep Google Sheets as an automatic fallback.

A storage error should remain an explicit storage error rather than silently switching databases.

---

# 20. Google-Specific Runtime Dependencies

The final application runtime must not need Google libraries, Google configuration, or Google Sheets availability in order to serve normal Vocab functionality.

If `gspread` / `oauth2client` become unnecessary after the PostgreSQL cutover, remove them from the normal runtime dependency set where that is clean and safe. Do not retain a migration utility for this milestone.

---

# 21. Application Container

Create a conventional Docker application image.

Expected files are likely:

- `Dockerfile`
- `compose.yaml`
- `.dockerignore`
- external configuration example/documentation
- database schema/migration files
- PostgreSQL persistence code/tests.

Use an appropriate maintained Python image.

The application image should:

1. establish a deterministic working directory;
2. install repository-declared runtime dependencies;
3. copy required application source;
4. run Streamlit through the existing `app.py` entry point;
5. listen inside the container on the selected Streamlit port;
6. contain no secrets;
7. contain no host virtual environment;
8. contain no Git repository;
9. avoid unnecessary system packages.

Do not bind-mount application source for normal service operation.

The image itself should be the tested application artifact.

---

# 22. Build Context Hygiene

Create a `.dockerignore`.

Exclude at minimum where applicable:

- `.git/`;
- `.venv/`, `venv/`;
- Python caches;
- `.env*` except deliberately safe examples;
- `.streamlit/`;
- `service_account.json`;
- private keys;
- local AI/Aider artifacts;
- generated caches;
- runtime state;
- local database files;
- test/output artifacts not required by the application image.

Confirm secret-bearing files do not enter the Docker build context or final image.

---

# 23. Compose Service

Compose should manage the always-on service.

Conceptually:

    services:
      vocab-app:
        restart: unless-stopped
        depends_on:
          vocab-db:
            condition: service_healthy
    
      vocab-db:
        restart: unless-stopped
        healthcheck: ...
        volumes:
          - vocab_postgres_data:...

Do not use privileged mode.

Do not mount the Docker socket.

Do not add GPU devices.

Do not add unrelated services.

---

# 24. Health / Readiness

Distinguish database health from application health.

PostgreSQL should have a bounded healthcheck.

The application should have a bounded Streamlit health check where practical, such as the supported Streamlit health endpoint.

Acceptance should make it possible to distinguish:

- PostgreSQL unavailable;
- application container unavailable;
- Streamlit unhealthy;
- application persistence error.

Do not mistake a database/configuration problem for Docker health if the infrastructure layers are otherwise healthy.

---

# 25. Always-On Restart Validation

Validate ordinary restart behavior without rebooting the physical server unnecessarily.

At minimum prove:

- Compose service starts cleanly;
- containers reach healthy/running state;
- restarting the application container brings it back automatically;
- database data remains present;
- Compose stop/start preserves data;
- restart policy is configured for server/Docker restart.

If `systemctl is-enabled docker` can be inspected read-only, record it.

Do not reboot `henderson-server1` solely for M004 unless the Product Owner explicitly chooses to do so.

---

# 26. LAN Browser Access

Once the service is healthy, validate access through the server LAN interface.

The desired endpoint is conceptually:

`http://192.168.1.173:<vocab-port>`

or the currently confirmed server LAN address.

Validate from another machine on the LAN where possible.

The service should not require an SSH tunnel for ordinary household use after M004.

An SSH tunnel may still be used for troubleshooting, but it is not the intended user experience.

---

# 27. Desktop Browser Validation

From a desktop browser on the LAN, verify:

- Vocab page loads;
- expected page/title renders;
- current major tabs render;
- Practice renders;
- existing flashcard path remains functional;
- vocabulary data is loaded from PostgreSQL;
- no Google credential/configuration error appears;
- no obvious M003 behavior regression is introduced.

Avoid unnecessary live mutation solely for validation.

A controlled test write may be used if it can be safely reversed or clearly identified.

---

# 28. Mobile Browser Validation

The Product Owner intends to use Vocab from a mobile browser as well as desktop.

Validate from a mobile browser on the same LAN/Wi-Fi where practical.

At minimum verify:

- service URL loads;
- main page renders;
- navigation/tabs are usable;
- Practice can be opened;
- no desktop-only networking dependency exists.

Do not redesign Streamlit for mobile in M004.

Minor responsive-layout limitations inherent to the existing Streamlit UI are not by themselves a reason to replace Streamlit during this milestone.

Document any material usability problem for M006.

---

# 29. Secure External Access Boundary

Do not expose the application directly to the Internet in M004.

The long-term goal may include accessing Vocab from a mobile device away from home.

That will require a deliberate secure-access design in a later milestone.

Do not implement router port forwarding or direct public Streamlit exposure as a shortcut.

M004 establishes the always-on self-hosted LAN service first.

---

# 30. NLTK / External Services

Preserve the M003 NLP seam.

Determine the container requirements for the actual NLTK resources used by current Vocab behavior.

Provision required resources predictably if necessary.

Do not redesign NLP.

Dictionary, translation, and text-to-speech may still use their current external APIs/services.

The phrase "fully self-hosted" in M004 specifically requires the application runtime and persistence to reside locally.

Do not attempt to replace all third-party dictionary/translation/TTS services in this milestone.

Document those remaining external functional dependencies clearly.

If the Product Owner later wants those replaced locally, treat that as separate product scope.

---

# 31. Existing Tests

Before M004 changes, run the existing M003 characterization suite.

Expected framework:

`unittest`

Record exact command and result.

After implementation, rerun the complete Vocab suite.

Add focused tests for PostgreSQL/persistence behavior.

Do not remove or weaken M003 characterization tests.

---

# 32. PostgreSQL Tests

Add deterministic tests covering, as applicable:

- record loading;
- history semantics;
- duplicate detection;
- append/insert behavior;
- score lookup;
- score update;
- missing-row behavior;
- current Count semantics;
- transaction/error behavior;
- persistence interface compatibility.

Prefer native PostgreSQL integration tests against a disposable PostgreSQL container for database-specific behavior.

Do not point automated tests at the operational Vocab database.

---

# 33. PostgreSQL Initialization and Persistence Tests

Using controlled synthetic records and a disposable PostgreSQL service where practical, test:

- reproducible schema initialization;
- current vocabulary fields and Count semantics;
- case-insensitive duplicate enforcement;
- record loading and history behavior;
- append/insert behavior;
- score lookup and update;
- missing-row behavior;
- transaction/error behavior;
- persistence across application/database container recreation.

Do not point automated tests at an operational Vocab database or a live Google Sheet.

---

# 34. Container Validation

Perform a controlled clean build/start cycle.

Record:

    docker compose config
    docker compose build
    docker compose up -d
    docker compose ps
    docker compose logs --tail ...

or repository-appropriate equivalents.

Confirm:

- app image builds from source;
- database image/service starts;
- DB becomes healthy;
- app becomes healthy/running;
- application can connect to PostgreSQL;
- port is available on intended LAN binding;
- logs contain no secret content.

Do not rely on manually modified containers.

---

# 35. Source / Image Traceability

Where practical, use standard OCI metadata to record the source revision.

Because implementation remains uncommitted until Product Owner acceptance, distinguish clearly between:

- development validation image built from an uncommitted working tree;
- final image rebuilt after M004 is committed.

Do not label an uncommitted development image as though it corresponds exactly to a Git Commit SHA.

After Product Owner guarded Commit, the operational image should be rebuilt from the committed source and can then carry the exact source revision.

---

# 36. Operational Data Protection

The PostgreSQL volume is operational state.

Do not delete it during routine application rebuilds.

Document a simple bounded PostgreSQL backup command using `pg_dump` or equivalent so the Product Owner has a portable logical backup path.

Do not build a large automated backup platform in M004.

Do not modify the existing Synology/Active Backup configuration.

Document that container image/source and PostgreSQL data are separate recovery concerns.

---

# 37. Security Baseline

Confirm:

- database port is not publicly/LAN exposed unnecessarily;
- application is exposed only as required for LAN browser access;
- no Google credentials exist in normal runtime;
- database password remains outside Git;
- no secrets are inside Docker image layers;
- no privileged mode;
- no Docker socket;
- no GPU;
- no unrelated host mounts;
- persistent DB data is outside Git;
- `.dockerignore` protects sensitive paths.

If safely practical, run the application as a non-root container user.

Do not force this if it materially expands scope; document the result.

---

# 38. No Product Behavior Redesign

Do not change:

- practice selection semantics;
- scoring semantics;
- Count coercion;
- synonym semantics;
- duplicate semantics;
- current vocabulary fields;
- current Streamlit navigation;
- current flashcard behavior.

Containerization and persistence migration must not become product redesign.

If the current M003 application semantics expose a defect that conflicts with PostgreSQL constraints, STOP and report rather than silently correcting it.

---

# 39. Explicit Non-Goals

Do not implement:

- multiple-choice practice;
- distractor generation;
- permanent UI replacement;
- Flask/FastAPI web redesign;
- secure public Internet access;
- router changes;
- reverse proxy;
- TLS;
- public authentication;
- Google/PostgreSQL ongoing sync;
- dual-write;
- unrelated external-service replacement;
- Redis;
- GPU support;
- Kubernetes;
- CI/CD;
- Repo Control deployment mutation;
- Photo Organizer integration.

---

# 40. Expected File Scope

Expected changes may include:

- `vocab_persistence.py`;
- one or a few PostgreSQL/schema initialization modules;
- database/schema SQL or lightweight migration files;
- `app.py` only for bounded persistence wiring/configuration;
- `requirements.txt` only if a runtime dependency is justified;
- `Dockerfile`;
- `compose.yaml`;
- `.dockerignore`;
- `.env.example` or equivalent safe configuration example;
- tests;
- small operator documentation if needed;
- M004 closeout.

Do not perform a broad source-tree rewrite.

---

# 41. Git Mutation Boundary

The coding agent must not Stage or Commit M004.

Do not run:

- `git add`;
- `git commit`;
- `git reset`;
- `git restore`;
- `git clean`;
- `git push`.

The Product Owner will review the implementation and closeout.

After acceptance, use Repo Control Workflow for guarded Stage/Commit.

---

# 42. Stop / Escalation Conditions

STOP and report if:

- M003 tests fail before M004 changes;
- PostgreSQL integration requires a broad application redesign;
- container runtime requires privileged access or unrelated server changes;
- a host port/firewall change requires privileged action;
- another server stack would need modification;
- containerization requires changing product behavior;
- Repo Control and direct Git disagree at a synchronization gate;
- work begins expanding into multiple-choice, Streamlit replacement, or public Internet exposure.

Do not improvise around a material stop condition.

---

# 43. Required Closeout

Create exactly:

`milestones/004_self_hosted_postgresql_and_always_on_service_baseline_closeout.md`

Include:

## 1. Executive conclusion

PASS / PARTIAL / STOP.

## 2. Starting Git state

Branch, HEAD, upstream, parity, status.

## 3. Starting Repo Control evidence

Context IDs/findings and baseline Snapshot ID.

## 4. M003 preflight

Existing test results before M004 work.

## 5. Current Google persistence schema

Exact current M003 vocabulary fields and semantics used to design the empty PostgreSQL schema. Do not access Google Sheets for historical migration.

## 6. Target architecture

Application / PostgreSQL / Docker / LAN diagram.

## 7. PostgreSQL schema

Tables, fields, constraints, indexes, ordering semantics.

## 8. Persistence implementation

How PostgreSQL satisfies the M003 persistence boundary.

## 9. Schema initialization

Exact reproducible schema initialization mechanism.

## 10. Runtime configuration

Database/environment configuration and secret boundary.

## 11. Google runtime exclusion

Record that no legacy Google Sheets migration was performed or required, and that Google Sheets is absent from normal operational persistence.

## 12. PostgreSQL runtime cutover

Proof normal application persistence no longer requires Google Sheets.

## 13. Files changed

Exact list.

## 14. Dependency changes

Runtime dependencies and any justified removal of unnecessary Google persistence dependencies.

## 15. Dockerfile

Base image, user, workdir, source/dependency strategy, command.

## 16. Compose

App/DB services, health, network, volume, restart policy, LAN binding.

## 17. Build-context hygiene

Secret/runtime exclusions.

## 18. PostgreSQL persistence volume

Exact operational volume and persistence validation.

## 19. Existing tests

Pre/post commands and results.

## 20. PostgreSQL tests

Exact tests/results.

## 21. Schema/persistence tests

Exact tests/results.

## 22. Container build

Command, result, image identity.

## 24. Container startup/health

App and database evidence.

## 25. Always-on behavior

Restart policy and restart validation.

## 26. Desktop browser validation

Exact LAN endpoint and observed behavior.

## 27. Mobile browser validation

Observed LAN/mobile behavior or explicit Product Owner validation boundary.

## 28. Persistence application validation

Proof application reads from PostgreSQL.

## 29. Security validation

Secrets, ports, mounts, privilege, image inspection.

## 30. Backup/recovery baseline

Logical PostgreSQL backup command/documentation.

## 31. External functional dependencies

Dictionary/translation/TTS or other services still external after M004.

## 32. Repo Control post-change evidence

Context, Snapshot ID, Comparison ID, limitations.

## 33. Scope assessment

Confirm no M005/M006/public-access work entered M004.

## 34. Remaining limitations

Only genuine limitations.

## 35. Recommendation

State whether M004 is ready for Product Owner acceptance and guarded Stage/Commit.

## 36. Next milestone

Normally:

`Vocab M005 — Multiple-Choice Practice`

Do not recommend another infrastructure/Repo Control milestone unless a genuine blocker is discovered.

## 37. Final Git state

Capture:

    git branch --show-current
    git rev-parse HEAD
    git status --short
    git rev-parse @{upstream} 2>/dev/null || true
    git rev-list --left-right --count HEAD...@{upstream} 2>/dev/null || true

---

# 44. Acceptance Criteria

M004 is PASS only if:

- all accepted M003 tests still pass;
- PostgreSQL is the active Vocab persistence implementation;
- current vocabulary schema/behavior is faithfully represented;
- an empty/new PostgreSQL database is acceptable;
- Google Sheets is no longer required by ordinary runtime persistence;
- no dual-write/synchronization exists;
- database initialization is reproducible;
- PostgreSQL data persists across container recreation;
- Vocab application image builds from repository source;
- Compose validates;
- application and database containers start reliably;
- restart policy supports always-on operation;
- Streamlit health/runtime is stable;
- service is reachable from the intended LAN endpoint;
- desktop browser access works;
- mobile browser access works or reaches a clearly documented Product Owner validation gate;
- current Practice functionality remains available;
- application reads vocabulary from PostgreSQL;
- database port is not unnecessarily exposed;
- secrets remain outside Git and image;
- no Google credentials are needed by normal runtime;
- existing external definition, translation, pronunciation, and TTS services remain at their current boundary or continue to function;
- no privileged/GPU/Docker-socket configuration exists;
- PostgreSQL logical backup procedure is documented;
- Repo Control post-change evidence is captured;
- no M005/M006/public Internet/local-AI replacement work is introduced;
- implementation remains uncommitted for Product Owner review.

---

# 45. Post-M004 Product Owner Workflow

If implementation is accepted:

1. Review exact changed files and closeout.
2. Use Repo Control guarded Stage.
3. Create/use matching Snapshot from Workflow.
4. Prepare guarded Commit.
5. Approve Commit.
6. Confirm successful execution.
7. Confirm associated Snapshot is `Commit aligned`.
8. Push canonical `main`.
9. Rebuild Vocab image from committed source.
10. Record/verify the exact source Git SHA for the operational image.
11. Bring the committed Compose service up.
12. Confirm PostgreSQL volume remains intact.
13. Confirm desktop/mobile LAN access.
14. Proceed directly to M005.

---

# 46. Next Product Milestone

After M004:

`Vocab M005 — Multiple-Choice Practice`

M005 should develop against:

- the permanent PostgreSQL persistence architecture;
- the containerized always-on service;
- the existing M003 domain seam;
- the still-temporary Streamlit UI.

This develops the new quiz against the permanent PostgreSQL persistence architecture rather than Google Sheets.

---

# 47. Later UI / Access Direction

M006 should replace Streamlit with the permanent self-hosted web UI after the multiple-choice behavior is established.

A later milestone should address secure away-from-home access for desktop/mobile use.

Do not expose Streamlit directly to the public Internet merely to satisfy the long-term mobile goal.

---

# 48. Working Principles

> The operational application and its data belong on `henderson-server1`.

> Google Sheets is not part of the M004 operational persistence path.

> PostgreSQL becomes the canonical Vocab datastore in M004.

> The service should be on when the server is on.

> Desktop and mobile clients should need only a browser.

> Streamlit is temporary, but it is not an obstacle to self-hosting.

> Do not combine PostgreSQL cutover with permanent UI replacement.

> Initialize PostgreSQL reproducibly, validate deterministically, cut over once, and return to product work.

---

**End of `004_self_hosted_postgresql_and_always_on_service_baseline_prompt.md`**
