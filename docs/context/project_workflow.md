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

## Coding-agent bootstrap registrations

Vocab's repository-local SessionStart registrations are:

- GitHub Copilot: `.github/hooks/repo_control_context.json`
- Codex: `.codex/hooks.json`

Both registrations invoke the centrally maintained adapters in `/home/chuck/projects/repo-control-ii` with the trusted Repo Control II virtualenv. The adapters resolve current authority through `coder-context` and bind each event to this repository's expected root, key, and ID; registrations do not cache milestone state. Inspect the proposed or installed registration shapes with the read-only `coder-bootstrap-preview` command:

```bash
/home/chuck/projects/repo-control-ii/.venv/bin/python -m repoctl.cli coder-bootstrap-preview \
  --repository-key vocab-app \
  --repository-id vocab-app--0d81efec80ef \
  --repository-root /home/chuck/projects/vocab-app
```

Preview output is not installation, trust, or proof of host delivery. Repository-local hook files do not themselves authorize host execution. Copilot hook activation and Codex project trust require Product Owner approval and the host's supported trust flow; never bypass trust or manually edit Codex global trust configuration. In a fresh authorized session, use only the ordinary handoff notice and let the hook resolve current context; do not copy milestone prompts, authority, or prior transcripts between sessions. Registrations are Vocab-specific and must fail closed rather than resolve another managed repository. See the [central multi-repository Coder bootstrap guide](../../../repo-control-ii/docs/guides/multi_repository_coder_bootstrap.md) for the shared design and limitations.

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
