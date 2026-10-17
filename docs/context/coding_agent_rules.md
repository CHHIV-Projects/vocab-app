# Vocab App — Coding Agent Bootstrap

**Document role:** Compact always-loaded Vocab identity and safety bootstrap  
**Process authority:** Repo Control II and [project_workflow.md](project_workflow.md)  
**Architecture/context:** [project_architecture.md](project_architecture.md), [project_context.md](project_context.md)

## Authority and start

1. Follow explicit Product Owner direction, the active approved prompt and lock-ins, Repo Control lifecycle/authorization, this bootstrap, current Vocab context/architecture/workflow, applicable Skills, then other project evidence in that order.
2. Confirm the selected repository is `/home/chuck/projects/vocab-app`.
3. Retrieve authoritative `repoctl coder-context`; verify active prompt, lifecycle, authorization, and lock-ins. Use `coder-status` when status needs rechecking.
4. Run read-only Git preflight and classify all existing modifications. Preserve work you did not make.
5. Raise only material blockers, conflicts, risks, or ambiguities. If none exist, proceed within the prompt.

## Absolute Git prohibition

The Coder must never stage, commit, push, tag, merge, rebase, reset, stash, clean, switch/create/delete branches, mutate remotes, or otherwise mutate Git state. Stop for Product Owner review after closeout submission.

## Scope and project safety

- Change only the active prompt's scope and defects directly caused by that work.
- Do not expose or copy credentials.
- Do not alter production PostgreSQL, learner records, mounted lexical data, runtime state, external services, shared-host configuration, containers/networks, or other projects without explicit authorization.
- Do not treat model output as lexical authority; use deterministic source evidence and validation.
- Do not activate automatic Qwen sense consolidation for product v1; M004.6.13.3 is NO-GO.
- Tests or a closeout do not confer lifecycle authorization or Product Owner acceptance.

## Shared procedure Skills

Load the applicable Repo Control procedure explicitly:

- [Implementation and milestone work](../../.agents/skills/repo-control-implementation/SKILL.md)
- [Blocker and bug escalation](../../.agents/skills/repo-control-blocker-bug-escalation/SKILL.md)
- [Validation and closeout](../../.agents/skills/repo-control-validation-closeout/SKILL.md)

Skills provide procedure only and cannot override Repo Control or authorize scope, lifecycle, Product Owner, or Git actions. If an applicable Skill is unavailable, follow Repo Control's canonical prompt and governing documents; stop if safe procedure remains unclear.

## Current repository-specific operational note

Until the M001.002 milestone-root cutover is accepted, Vocab Coder CLI calls must explicitly use the authoritative Repo Control II executable and `--milestone-root milestones`. Do not configure the central registry or move active lifecycle artifacts from this repository.
