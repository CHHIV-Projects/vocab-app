# Vocab App — Project Workflow Overlay

**Document role:** Vocab-specific validation and runtime operating notes
**Generic process:** Repo Control II shared workflow core and accepted Skills
**Repository:** `/home/chuck/projects/vocab-app`
**Canonical milestone root:** `docs/milestones/`

## Managed-repository Coder context

From this checkout, use the canonical Repo Control II CLI:

```bash
/home/chuck/projects/repo-control-ii/.venv/bin/python -m repoctl.cli coder-context
```

The central resolver must identify the exact managed repository as `vocab-app`, with repository ID `vocab-app--0d81efec80ef` and milestone root `docs/milestones/`. Stop if the returned identity or path does not match this checkout; do not proceed under a synthetic `default` identity. Do not install a project-local Repo Control package or pass a manual `--milestone-root` override during normal use.

## Focused application validation

Use existing focused tests where they cover the change. Tests use Python `unittest`; representative selectors include:

```bash
python3 -m unittest tests.test_vocab_workflow
python3 -m unittest tests.test_vocab_consolidation
python3 -m unittest discover -s tests -p 'test_*.py'
python3 -m py_compile app.py vocab_workflow.py vocab_lexical_engine.py vocab_persistence.py
```

Choose only checks relevant to the authorized change. PostgreSQL tests may require explicit test-database configuration. Do not run database, browser, model, or production-runtime checks unless the active prompt authorizes them.

## Runtime and data safety

- The canonical private-LAN deployment identity and app-only operational procedure are documented in [lan_deployment_runbook.md](lan_deployment_runbook.md). Follow it for authorized Compose deployment/restart work.
- Database or persistence validation must use an explicitly scoped test database and safe disposable learner data, never production records.
- Runtime checks involving Docker Compose, Streamlit health, migrations, mounted lexical data, Ollama, translation, or other external services require milestone-specific scope.
- Treat Compose and runtime configuration as evidence of intended setup, not proof that deployed code matches reviewed source.
- Do not mutate production PostgreSQL, mounted lexical data, runtime caches/diagnostics, containers, networks, host configuration, or external services without explicit authorization.
- Keep lexical dataset creation, validation, and activation as separate controlled operations; do not alter the read-only production projection in place.
- Record exact commands, outcomes, failures, and untested behavior. A passing test does not establish runtime or deployment behavior it did not exercise.
