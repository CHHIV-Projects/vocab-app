# Vocab App — Project Workflow

**Document role:** Vocab-specific operating notes for the Repo Control II workflow  
**Process baseline:** Repo Control II `docs/context/project_workflow.md`  
**Baseline SHA-256:** `2244501f6f6c2f5c8208d489665b058d378be3898bec351529aac485ae00122f`  
**Repository:** `/home/chuck/projects/vocab-app`

Repo Control II owns lifecycle, milestone state, Coder authority, Git boundaries, shared procedures, and review/acceptance flow. This document adapts that baseline only for Vocab repository identity, runtime, data safety, and the temporary milestone root. It is not an independent lifecycle authority.

## Roles and authority

- **Product Owner:** sets product intent and scope, approves/selects milestones, resolves consequential decisions, performs acceptance, and owns every Git mutation.
- **Architect:** translates product goals into bounded prompts, decisions, and review; interprets evidence and recommends next work.
- **Coder:** retrieves authoritative context, inspects/implements only authorized scope, records evidence, validates, submits closeout, and stops at review boundaries.
- **Repo Control II:** provides authoritative selection, lifecycle, authorization, standing references, approved dispatches, and durable events.

The active Repo Control prompt and approved binding decisions define scope. Prior prompts, closeouts, code, skills, or chat cannot independently authorize work.

## Lifecycle

The lifecycle states are `PLANNING`, `READY`, `IN_PROGRESS`, `WAITING`, `REVIEW`, and `CLOSED`. Repo Control transitions are authoritative. A prompt being present, tests passing, or a closeout file existing does not imply authorization or acceptance.

The Coder starts by retrieving current `coder-context`, confirms the repository and authorization (and uses `coder-status` when necessary), performs read-only Git preflight, classifies existing changes, and raises only material blockers or ambiguities. Routine handoffs may be “Prompt ready.”, “Correction ready.”, or “Instruction ready.”; the handoff itself is not authorization.

During authorized work, use the bounded Coder event commands for material questions/blockers, discovered bugs, and actual test evidence. In `WAITING`, stop implementation until Repo Control records a resolution and restores authorization. Do not manufacture events for routine decisions or simulated evidence.

When scope and evidence are complete, prepare the prompt-required closeout and submit it with `coder-closeout`. Verify the resulting phase with `coder-status`. `REVIEW` means stop for Architect/Product Owner review; it is not acceptance. Product Owner acceptance and closure are separate lifecycle decisions.

## Shared procedure

The accepted Repo Control II procedure is provided by these unchanged repository-local Skills:

- [Implementation and milestone work](../../.agents/skills/repo-control-implementation/SKILL.md)
- [Blocker and bug escalation](../../.agents/skills/repo-control-blocker-bug-escalation/SKILL.md)
- [Validation and closeout](../../.agents/skills/repo-control-validation-closeout/SKILL.md)

Load the relevant Skill after preflight and at the corresponding work boundary. Skills provide procedure only; they do not confer scope, lifecycle, Product Owner, or Git authority.

## Coder Git and data boundaries

The Coder must not stage, commit, push, tag, merge, rebase, reset, stash, clean, switch/create/delete branches, mutate remotes, or otherwise change Git state.

Do not mutate production PostgreSQL, learner records, mounted lexical datasets, runtime cache/diagnostics, external services, Docker networks/containers, host configuration, or another project's resources without explicit authorization. Never expose credentials. Treat the Compose file as configuration evidence, not proof of deployed-source parity.

## Vocab validation conventions

Use targeted existing checks. Tests use Python `unittest`; representative commands are:

```bash
python3 -m unittest tests.test_vocab_workflow
python3 -m unittest tests.test_vocab_consolidation
python3 -m unittest discover -s tests -p 'test_*.py'
python3 -m py_compile app.py vocab_workflow.py vocab_synthesis.py vocab_persistence.py
```

The first two examples are focused selectors; choose tests that actually cover the change. PostgreSQL tests may require explicit test database configuration. Do not run database, browser, model, or production runtime validation unless the active prompt authorizes it. Report exact commands, results, failures, and skipped validation.

Runtime-specific checks may involve `docker compose`, Streamlit health, PostgreSQL migration state, the read-only lexical mount, or Ollama. They require milestone-specific scope and safe test data; they are not automatic steps for documentation work.

## Temporary milestone-root override

Until the follow-on M001.002 cutover is complete, the active milestone root is the repository's root `milestones/`. Use the authoritative executable and explicit path/root for Coder lifecycle commands:

```bash
/home/chuck/projects/repo-control-ii/.venv/bin/repoctl coder-context \
  --repository /home/chuck/projects/vocab-app --milestone-root milestones
/home/chuck/projects/repo-control-ii/.venv/bin/repoctl coder-status \
  --repository /home/chuck/projects/vocab-app --milestone-root milestones
```

Do not move active M001.000/M001.001 lifecycle artifacts or change the external registry during an active milestone. The accepted bounded cutover must close M001.001 first and configure the external registry only in its separately authorized milestone.
