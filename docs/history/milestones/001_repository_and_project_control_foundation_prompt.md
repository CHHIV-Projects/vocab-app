# Vocab App Milestone 001

# Repository and Project-Control Foundation Verification and Closeout

**Prompt file:** `001_repository_and_project_control_foundation_prompt.md`  
**Required closeout:** `001_repository_and_project_control_foundation_closeout.md`  
**Mode:** Verification / documentation closeout  
**Reasoning:** Medium  
**Implementation authority:** Documentation/foundation verification only  
**Git mutation authority:** None unless separately authorized by Product Owner

---

# 1. Objective

Verify and formally close the Vocab App repository and project-control foundation that was established before the new coder workflow begins.

This milestone does **not** redesign or implement the Vocab application.

The foundation work has already been performed manually with the Product Owner and Architect.

Your job is to:

1. verify the resulting repository structure and Git relationships;
2. verify the new controlling documents are internally consistent with the actual repository;
3. verify that the historical Repo Control testbed lineage remains preserved but separate from canonical Vocab `main`;
4. identify any material contradiction that must be corrected before technical development begins;
5. produce the authoritative M001 closeout.

The purpose is to establish a clean, evidence-backed starting boundary for Vocab M002.

---

# 2. Required Reading

Read these documents before performing verification:

1. `docs/context/project_workflow_v1.md`
2. `docs/context/coding_agent_rules_v1.md`
3. `docs/context/vocab_app_project_context_v1.md`
4. `architecture/vocab_repo_control_integration_roadmap_v1.md`
5. `docs/context/new_chat_intro_coder_v1.md`
6. this prompt

Treat the documents as proposed controlling project context subject to factual verification against the repository.

If a document conflicts with deterministic repository evidence, report the contradiction rather than silently correcting the evidence.

---

# 3. Known Foundation History

The following foundation decisions have already been made and should be verified rather than redesigned.

## 3.1 Canonical Vocab repository

Canonical working repository:

`/home/chuck/projects/vocab-app`

Canonical branch:

`main`

Canonical remote:

`origin`

Canonical GitHub repository:

`CHHIV-Projects/vocab-app`

The existing GitHub history was deliberately retained as the authoritative Vocab application lineage.

At the repository-reconciliation boundary, `main` and `origin/main` were aligned at:

`f7693897223b3aaaf72e6bc08e6b41db779a803a`

Do not assume that SHA remains current after foundation documentation is eventually committed.

Verify current state directly.

---

## 3.2 Historical testbed lineage

A separate sanitized Vocab repository had previously been used to develop and validate Repo Control.

That history had root:

`ff00a5c919c6bacff97699343181e092529fc952`

and later testbed HEAD:

`1281d7925b04b0d32bd6107b989af21221f1122c`

The independent histories were deliberately **not merged**.

Local archival/test branches were retained so the earlier experimental code can be inspected later.

Expected relevant references include:

- `archive/repo-control-testbed`
- `archive/sanitized-testbed-base`
- `archive/original-sanitized-main`
- historical `agent-test/*` branches

These branches are reference evidence only.

---

## 3.3 Local filesystem copy

The earlier testbed filesystem copy remains at:

`/home/chuck/ai-agent-tests/vocab-app`

It is frozen historical/reference material.

Do not modify or delete it.

---

# 4. Locked Decisions

Treat the following as locked for M001.

## 4.1 No unrelated-history merge

Do not merge the historical sanitized/testbed Git history into canonical `main`.

Do not rebase one history onto the other.

Do not rewrite history to make the two lineages appear related.

---

## 4.2 No automatic recovery of testbed code

Historical testbed changes are not automatically part of the real Vocab application.

Potentially useful historical work may later be evaluated during M002 reconnaissance.

Do not cherry-pick or port it during M001.

---

## 4.3 No application implementation

Do not modify:

- quiz behavior;
- Google Sheets behavior;
- Streamlit behavior;
- application architecture;
- dependencies;
- runtime;
- database behavior.

M001 is not a product implementation milestone.

---

## 4.4 No Repo Control implementation

Repo Control is a separate project at:

`/home/chuck/projects/repo-control`

M001 does not authorize Repo Control source changes.

Do not modify Repo Control.

---

## 4.5 No runtime/database mutation

Do not:

- build containers;
- start/stop/restart Vocab services;
- create databases;
- migrate data;
- alter server configuration;
- change firewall rules;
- modify unrelated host resources.

---

# 5. Starting-State Gate

Before doing anything else, run read-only preflight from:

`/home/chuck/projects/vocab-app`

Capture:

```bash
pwd
git branch --show-current
git rev-parse HEAD
git status --short
git remote -v
git branch -vv
git rev-parse origin/main
git rev-list --left-right --count HEAD...origin/main


Expected branch:

`main`

The working tree is expected to contain the newly created project-control/foundation files that have not yet been committed.

That expected documentation work is **not** itself a reason to stop.

However, stop and report if you find:

- application-code modifications not explained by the foundation work;
- staged files that were not explicitly expected;
- merge conflicts;
- an unexpected branch;
- an unexpected remote;
- canonical `main` based on the historical sanitized lineage;
- evidence that the unrelated histories were merged.

Do not clean or alter unexpected state.

---

# 6. Verify Canonical Main Ancestry

Establish deterministic evidence that canonical `main` belongs to the existing GitHub Vocab lineage.

Verify:

- `main` tracks `origin/main`;
- the historical GitHub lineage is reachable from canonical `main` as expected;
- `ff00a5c` is not an ancestor of canonical `main`;
- `1281d79` is not an ancestor of canonical `main`.

Use read-only Git commands.

Suggested evidence includes:

```
git merge-base --is-ancestor ff00a5c main
echo $?

git merge-base --is-ancestor 1281d79 main
echo $?

git log --oneline --decorate -10 main
```

Interpret return codes correctly.

A nonzero result for the historical testbed commits is expected.

Do not mutate history.

---

# 7. Verify Historical Preservation

Verify the preserved references exist and point where expected.

At minimum inspect:

```
git show-ref --heads
```

Confirm, where present:

- `archive/sanitized-testbed-base` → `ff00a5c...`
- `archive/original-sanitized-main` → `ff00a5c...`
- `archive/repo-control-testbed` → `1281d79...`
- `agent-test/repoctl-ui-demo` → `1281d79...`

Also record the other preserved `agent-test/*` references.

Do not create, rename, delete, or push branches during M001.

If the exact expected references differ, report the actual evidence.

---

# 8. Verify Repository Hygiene

Inspect:

- `.gitignore`
- `.aiderignore`

Confirm that local/generated state and credential-oriented material are appropriately excluded.

At minimum evaluate protection for:

- `__pycache__/`
- Python bytecode
- `.venv/`
- Aider history/cache
- `.env`
- `.streamlit/`
- `service_account.json`
- private key material

Do not inspect secret contents.

Verify whether any obvious sensitive files are currently present in the working tree.

Use filename/path inspection only where appropriate.

Do not open credentials merely to prove that they are credentials.

---

# 9. Verify Foundation Document Set

Confirm the following files exist:

- `docs/context/project_workflow_v1.md`
- `docs/context/coding_agent_rules_v1.md`
- `docs/context/vocab_app_project_context_v1.md`
- `architecture/vocab_repo_control_integration_roadmap_v1.md`
- `docs/context/new_chat_intro_coder_v1.md`
- this M001 prompt

Review them for material contradictions.

Focus on:

- canonical repository path;
- canonical branch;
- GitHub authority;
- historical branch treatment;
- Repo Control separation;
- Photo Organizer exclusion;
- Product Owner / Architect / Coder roles;
- Git mutation authority;
- runtime/database mutation authority;
- the three Product Owner Vocab goals;
- M002 reconnaissance direction.

Do not spend M001 rewriting wording for style.

Only material factual or safety contradictions matter.

---

# 10. Verify Project Directories

Confirm the intended project organization exists.

At minimum:

```
architecture/docs/docs/context/milestones/
```

Confirm the M001 directory contains this prompt.

Do not reorganize the project during verification.

---

# 11. Verify Current Application Baseline Without Changing It

Perform only enough read-only inspection to establish what canonical `main` currently contains.

At minimum record:

- root-level application/source files;
- `requirements.txt`;
- whether `app.py` exists;
- whether test files are currently present on canonical `main`.

Do not perform the full architecture reconnaissance intended for M002.

Do not begin mapping all Streamlit or Google Sheets relationships.

The purpose here is simply to preserve the starting application baseline.

---

# 12. Optional Baseline Test

If the current canonical application has an obvious safe unit-test command that:

- requires no credentials;
- requires no external service;
- performs no mutation;

you may run it and record the result.

If no such test is clearly available, state:

`No safe credential-free baseline test was established during M001.`

Do not broaden M001 merely to construct a test harness.

M002 will inspect testing properly.

---

# 13. Repo Control Boundary Verification

Confirm read-only that:

`/home/chuck/projects/repo-control`

exists as a separate repository.

Do not perform Repo Control implementation reconnaissance.

Do not modify it.

Record only enough evidence to establish that Vocab and Repo Control remain separate repositories.

---

# 14. Foundation Consistency Decision

At the end of verification, classify the foundation as one of:

## PASS

The repository and control documents form a coherent safe starting boundary for M002.

## PASS WITH DOCUMENTATION CORRECTION REQUIRED

The architecture is sound, but one or more factual/safety statements in the foundation documents require bounded correction before commit.

## STOP

A material repository/history/safety contradiction exists that must be resolved before M002.

Do not invent additional classifications.

---

# 15. Documentation Correction Authority

M001 is primarily verification.

If you identify a small factual documentation correction that is:

- directly proven by deterministic evidence;
- clearly required to make the foundation truthful;
- not an architectural change;
- not a product change;

do **not** silently edit it.

Report the proposed correction first.

The Product Owner/Architect will decide whether to authorize the documentation-only fix.

This preserves the distinction between verification and implementation.

---

# 16. No Git Mutation

Do not run:

- `git add`
- `git commit`
- `git push`
- `git merge`
- `git rebase`
- `git reset`
- `git restore`
- `git stash`
- branch creation/deletion/rename
- tag mutation

during M001 verification unless the Product Owner explicitly authorizes a later closeout step.

The Product Owner will handle the accepted foundation commit after closeout review.

---

# 17. Required Closeout

Create exactly one closeout:

`milestones/001_repository_and_project_control_foundation/001_repository_and_project_control_foundation_closeout.md`

The closeout must include:

## 1. Milestone result

PASS / PASS WITH DOCUMENTATION CORRECTION REQUIRED / STOP.

## 2. Starting repository evidence

- repository path;
- branch;
- HEAD;
- upstream;
- ahead/behind;
- working-tree state.

## 3. Canonical lineage verification

Explain the relationship between:

- `main`;
- `origin/main`;
- `ff00a5c`;
- `1281d79`.

## 4. Historical branch preservation

List the relevant archive/test references and SHAs.

## 5. Repository hygiene

Summarize `.gitignore`, `.aiderignore`, and sensitive-path findings.

Do not reproduce secrets.

## 6. Foundation documents

Confirm existence and identify any material contradiction.

## 7. Application baseline

Record the minimal current canonical source/test structure observed.

## 8. Test evidence

Record any safe baseline test actually run, or state that none was established.

## 9. Repo Control boundary

Confirm Vocab and Repo Control remain separate repositories.

## 10. Deviations or unresolved issues

State explicitly.

## 11. Final repository state

Capture:

```
git branch --show-current
git rev-parse HEAD
git status --short
git rev-list --left-right --count HEAD...origin/main
```

## 12. Recommendation

State whether the project is ready for:

**Vocab M002 — Architecture and Integration Reconnaissance**

---

# 18. Closeout Quality Rules

The closeout must distinguish:

- observed fact;
- interpretation;
- recommendation.

Do not reconstruct evidence that was not observed.

Do not claim the repository was clean if foundation files are intentionally untracked.

Do not claim a test passed unless it was actually run.

Do not claim a historical branch is preserved remotely unless that was actually verified.

Local preservation and remote preservation are different facts.

---

# 19. Stop Conditions

Stop immediately and report before creating a PASS closeout if:

- canonical `main` contains the sanitized/testbed ancestry;
- unrelated histories appear merged;
- `origin` does not represent the expected GitHub repository;
- unexplained application code is modified;
- sensitive credentials appear tracked;
- foundation documents materially misrepresent repository authority;
- Repo Control and Vocab have become coupled in a way contrary to the locked boundary;
- verification would require destructive or unauthorized mutation.

---

# 20. Expected Outcome

If the known foundation work is correct, M001 should be short.

The expected result is:

- canonical GitHub Vocab lineage verified;
- historical Repo Control testbed lineage preserved separately;
- project-control documents verified;
- repository hygiene verified;
- no application/runtime/database implementation performed;
- authoritative M001 closeout created;
- project ready for M002 reconnaissance.

Do not expand the milestone beyond that purpose.

---

# 21. Working Principle

> Verify the foundation we deliberately created; do not redesign it.

The value of M001 is a trustworthy boundary from which the new Vocab coder workflow can begin.

---

**End of `001_repository_and_project_control_foundation_prompt.md`**
