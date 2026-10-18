# Vocab App M004 Closeout

## 1. Executive conclusion

Result: PASS

M004 establishes the PostgreSQL-backed, containerized, always-on LAN service baseline with an empty operational database. The application no longer uses Google Sheets for normal persistence. PostgreSQL 17, a dedicated named volume, Compose health checks, restart policies, external runtime configuration, and the existing Streamlit UI are operational.

The Product Owner confirmed access from both a desktop and mobile phone on the home network at `http://192.168.1.173:8501`. The coder-side LAN endpoint validation also succeeded at that URL.

No Google Sheets data was accessed or migrated, as explicitly superseded by the Product Owner clarification.

## 2. Starting Git state

- Branch: `main`
- HEAD: `8954a2a6cfc2f8da0f6364c760e5d0a78e9c4d49`
- Upstream: `origin/main`
- Ahead/behind: `0 0`
- Working tree: clean
- M003 complete suite: 13 tests passed

## 3. Starting Repo Control evidence

- Baseline Snapshot: `snap--c13dc6684f2baf01`
- Repo Control status: clean, main, upstream equal, no staged/unstaged/untracked files.
- Context discovery matched the M003 persistence, practice, scoring, and Streamlit structure before implementation.

## 4. M003 preflight

Command:

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
```

Result: `Ran 13 tests ... OK`.

## 5. Current persistence model

The M003 application record semantics used for the new schema are:

- `Word` -> `vocabulary.word`
- `Definition` -> `vocabulary.definition`
- `Part of Speech` -> `vocabulary.part_of_speech`
- source metadata -> `vocabulary.source`
- saved date -> `vocabulary.created_on`
- `Count` -> `vocabulary.count`

The application preserves insertion/history order through the database `id` ordering. Word identity is case-insensitive. The operational database starts empty; no legacy Sheet inspection or migration was performed.

## 6. Target architecture

```text
Desktop Windows browser / mobile browser
                |
                v
henderson-server1:192.168.1.173:8501
                |
                v
       vocab-app Streamlit container
                |
       internal Compose network
                v
       vocab-db PostgreSQL 17
                |
                v
       named volume: vocab_postgres_data
```

## 7. PostgreSQL schema

Repository-controlled schema: `db/init/001_create_vocabulary.sql`.

Table: `vocabulary`

- `id BIGSERIAL PRIMARY KEY`
- `word TEXT NOT NULL`
- `definition TEXT NOT NULL DEFAULT ''`
- `part_of_speech TEXT NOT NULL DEFAULT ''`
- `source TEXT NOT NULL DEFAULT ''`
- `created_on DATE NOT NULL`
- `count INTEGER NOT NULL DEFAULT 1`
- nonblank word check;
- positive count check;
- unique index on `lower(word)`.

No future multiple-choice or UI-specific fields were added.

## 8. Persistence implementation

`PostgresPersistence` in `vocab_persistence.py` implements the M003 boundary for:

- record loading;
- history loading;
- case-insensitive duplicate detection;
- vocabulary insertion;
- word lookup;
- score read;
- score update.

`app.py` constructs this adapter from external environment configuration. The old Google adapter remains only as bounded historical/test compatibility code and is not used by normal runtime.

## 9. Schema initialization

Compose mounts `db/init` read-only into PostgreSQL's initialization directory. The schema is reproducible from repository-controlled SQL and initializes a new empty database.

## 10. Runtime configuration

Operator-owned configuration was created outside Git at:

`/home/chuck/.config/vocab-app/runtime.env`

The file permissions are `600`. Its password was generated without printing it and was not included in logs, command output, source, image content, or this closeout.

`.env.example` contains variable names and a safe placeholder only.

## 11. Google runtime exclusion

No live Google Sheet was accessed. No Google migration credentials were inspected or supplied. No migration reader, dry-run migration, source comparison, dual-write, fallback, or synchronization was implemented.

Normal application persistence is PostgreSQL-only. `gspread` and `oauth2client` were removed from the normal dependency set.

## 12. PostgreSQL runtime cutover

The application image uses `PostgresPersistence.from_env()`. A direct in-container adapter smoke check returned `records 0` against the operational database. The application loaded a controlled PostgreSQL record through the normal Practice flow.

The database was empty again after cleanup.

## 13. Files changed

- `app.py`
- `vocab_persistence.py`
- `requirements.txt`
- `db/init/001_create_vocabulary.sql`
- `Dockerfile`
- `compose.yaml`
- `.dockerignore`
- `.env.example`
- `tests/test_postgres_persistence.py`
- `milestones/004_self_hosted_postgresql_and_always_on_service_baseline_closeout.md`

## 14. Dependency changes

Removed from normal runtime dependencies:

- `gspread`
- `oauth2client`

Added:

- `psycopg[binary]`

Existing dictionary, translation, NLTK, and gTTS services remain at their current external boundaries.

## 15. Dockerfile

- Base image: `python:3.12-slim`
- deterministic `/app` workdir;
- installs `requirements.txt` without cache;
- copies only required application modules;
- runs as non-root user `vocab` UID 10001;
- starts the existing `streamlit run app.py` entry point;
- listens on port 8501;
- contains no secrets or host virtual environment.

## 16. Compose

`compose.yaml` defines:

- `vocab-db` using official `postgres:17`;
- `vocab-app` built from repository source;
- `unless-stopped` restart policy for both services;
- PostgreSQL healthcheck via `pg_isready`;
- Streamlit healthcheck via `/_stcore/health`;
- internal database networking with no published PostgreSQL port;
- application binding at `192.168.1.173:8501`;
- dependency on healthy PostgreSQL;
- named volume `vocab_postgres_data`.

`docker compose config --quiet` passed.

## 17. Build-context hygiene

`.dockerignore` excludes Git metadata, virtual environments, Python caches, `.env` files, Streamlit secrets, service-account credentials, and local AI artifacts.

## 18. PostgreSQL persistence volume

Operational volume: `vocab_postgres_data`.

Validation performed:

- database container recreation preserved the controlled record and score;
- application/database restart preserved the controlled record and score;
- Compose stop/start preserved the controlled record and score;
- the controlled record was then deleted;
- final database row count: `0`.

Backup command for operators:

```bash
docker compose --env-file /home/chuck/.config/vocab-app/runtime.env exec -T vocab-db pg_dump -U vocab -d vocab > vocab-backup.sql
```

The backup file should be stored outside Git and protected as operational data.

## 19. Existing tests

The corrected M003 suite passed before M004 implementation with 13 tests.

The post-change suite passed with 15 tests and one expected skip because psycopg is installed in the runtime image rather than the current host test environment.

## 20. PostgreSQL tests

Added `tests/test_postgres_persistence.py` for adapter construction and external configuration. The built application image was also exercised directly with `PostgresPersistence.from_env()` and a live PostgreSQL connection.

## 21. Schema/persistence tests

Validated:

- schema initialization;
- empty database startup;
- record loading through the app;
- Practice candidate loading;
- score update through the existing Got it flow;
- score persistence across database recreation and Compose stop/start;
- final cleanup to zero rows.

## 22. Container build

Command:

```bash
docker compose --env-file /home/chuck/.config/vocab-app/runtime.env build
```

Result: application image built successfully from repository source. The PostgreSQL 17 image was pulled successfully.

## 23. Container startup/health

Command:

```bash
docker compose --env-file /home/chuck/.config/vocab-app/runtime.env up -d
docker compose --env-file /home/chuck/.config/vocab-app/runtime.env ps
```

Observed:

- `vocab-db`: healthy;
- `vocab-app`: healthy;
- Streamlit health endpoint: `ok`;
- PostgreSQL port is internal and not published.

## 24. Always-on behavior

Both services use `restart: unless-stopped`.

Validated:

- Compose start;
- application restart;
- PostgreSQL container recreation;
- application container recreation;
- Compose stop/start;
- data persistence across those operations.

A physical server reboot was not performed.

## 25. Desktop browser validation

Coder-side LAN validation succeeded at:

`http://192.168.1.173:8501`

Observed:

- Vocab Tracker page rendered;
- Dictionary, Translator, and Practice tabs rendered;
- Practice loaded the controlled PostgreSQL record;
- Flashcard definition rendered;
- Got it completed the existing flow and updated PostgreSQL count.

Product Owner Windows desktop validation completed successfully at the same LAN URL.

## 26. Mobile browser validation

Product Owner phone validation on the same home Wi-Fi completed successfully. The validated URL was:

`http://192.168.1.173:8501`

## 27. Persistence application validation

The application read the controlled record from PostgreSQL and rendered it through Practice. The Got it action changed its count from 1 to 2. That value survived PostgreSQL container recreation, application restart, and Compose stop/start.

The disposable record was deleted afterward, leaving the database empty.

## 28. Security validation

- runtime password remains in `/home/chuck/.config/vocab-app/runtime.env` with mode `600`;
- no credentials are in Git or the application image;
- PostgreSQL is not LAN-published;
- only application port 8501 is published;
- no privileged mode;
- no Docker socket;
- no GPU;
- no unrelated host mounts;
- application runs as non-root;
- UFW was not changed.

## 29. Backup/recovery baseline

The bounded `pg_dump` command is documented in section 18. Docker image/source recovery and PostgreSQL logical data recovery remain separate concerns.

## 30. External functional dependencies

Dictionary API, translation, NLTK WordNet resources, and gTTS remain at their existing external/service boundaries. M004 does not attempt local AI definition replacement or local pronunciation/TTS replacement.

## 31. Repo Control post-change evidence

- M004 baseline Snapshot: `snap--c13dc6684f2baf01`
- M004 post-change Snapshot: `snap--8057d3f558d5e1c2`
- baseline-to-post Comparison: `cmp--f15a73c43058e7de`

The comparison includes the PostgreSQL/container source changes. Untracked-file structural coverage remains limited by Repo Control and direct Git/source evidence is authoritative.

## 32. Scope assessment

Not implemented:

- multiple-choice practice;
- permanent Streamlit replacement;
- local-AI definition replacement;
- local pronunciation/TTS replacement;
- public Internet access;
- authentication redesign;
- reverse proxy/TLS;
- Google migration or synchronization;
- unrelated stack changes;
- Repo Control mutation;
- Photo Organizer integration.

## 33. Remaining limitations

- No physical server reboot was performed.
- The operational database intentionally contains no migrated legacy vocabulary data and is currently empty.

## 34. Recommendation

M004 is accepted as `PASS`. The Product Owner confirmed the exact LAN URL from both the same-LAN desktop and mobile phone on the home Wi-Fi. The implementation remains uncommitted and unstaged pending the guarded Repo Control workflow.

The implementation remains uncommitted and unstaged. No guarded Stage, Commit, or Push was performed.

## 35. Next milestone

After Product Owner acceptance: `Vocab M005 — Multiple-Choice Practice`.

## 36. Final Git state

Captured after implementation:

```text
git branch --show-current
main

git rev-parse HEAD
8954a2a6cfc2f8da0f6364c760e5d0a78e9c4d49

git rev-parse @{upstream}
8954a2a6cfc2f8da0f6364c760e5d0a78e9c4d49
git rev-list --left-right --count HEAD...@{upstream}
0 0
```

The implementation remains uncommitted for Product Owner review.
