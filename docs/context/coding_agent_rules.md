# Vocab App — Repository Rules Overlay

<!-- repo-control-project-overlay:v1 -->

## Repository-specific rules

- Work only in the Vocab App repository at `/home/chuck/projects/vocab-app`.
- Never expose or copy credentials into prompts, documentation, logs, or evidence.
- Do not mutate production PostgreSQL, learner records, mounted lexical datasets, runtime caches or diagnostics, containers, networks, host configuration, or external services without explicit scope and authorization.
- Keep mounted lexical datasets read-only. Do not rebuild, activate, or replace a dataset without explicit authorization.
- Wiktionary/Wiktextract source evidence is lexical authority. Treat model output as a candidate and require deterministic validation before it can be saved.
- Automatic Qwen3:8B sense consolidation is NO-GO for product v1 unless a new approved decision explicitly changes that status.
- Application and runtime validation must use safe test data and preserve production isolation. Verify deployed-source identity before browser acceptance; configuration alone does not prove source parity.

For current product facts, architecture, local workflow, and deferred work, use [project_context.md](project_context.md), [project_architecture.md](project_architecture.md), [project_workflow.md](project_workflow.md), and [canonical_parking_lot.md](canonical_parking_lot.md).
