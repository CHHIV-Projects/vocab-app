# Vocab App — Canonical Parking Lot

**Document role:** Forward-looking record of evidence-backed deferred or conditional Vocab work  
**Project:** Vocab App  
**Current milestone and authorization:** Selected and reported by Repo Control; this planning document does not establish active scope or authorization.

This is a planning aid, not an active prompt, bug tracker, architecture decision, or commitment. Product Owner approval and a separate milestone are required before implementation. Remove items when completed, rejected, superseded, or otherwise resolved; preserve history in milestone closeouts.

VCAP-001 (M004.5 browser lifecycle acceptance) was completed and retired by accepted
[M002.000](../milestones/M002.000_learner_lifecycle_baseline_acceptance_closeout.md);
the historical M004.5 closeout is preserved unchanged.

## VCAP-002 — Reverse-direction translation validation

- **Status:** Conditional on the Product Owner retaining translation as a product requirement.
- **Evidence:** [M004.1 closeout](../history/milestones/004.1_external_service_runtime_configuration_and_functional_validation_closeout.md) reports partial status because the required reverse-language provider check failed.
- **Next action:** Confirm product requirement first; if retained, separately diagnose and validate both directions without changing success reporting to hide provider failures.

## VCAP-003 — Exact lexical lookup indexing/performance

- **Status:** Deferred maintenance.
- **Evidence:** Project context records non-optimal exact `normalized_lemma` indexing in the production lexical projection.
- **Next action:** Measure a controlled candidate dataset build; validate index and lookup correctness before explicit dataset activation. Do not mutate the read-only production projection in place.

## VCAP-004 — Multiple-choice practice redesign

- **Status:** Deferred product work; not authorized.
- **Evidence:** The product context retains multiple-choice practice as a direction; existing practice row/count behavior is intentionally preserved.
- **Next action:** Product Owner defines desired learner behavior and scope before a future prompt.

## VCAP-005 — Alternatives to automatic Qwen sense consolidation

- **Status:** Explicitly NO-GO for automatic Qwen3:8B consolidation in product v1; no reconsideration authorized.
- **Evidence:** [M004.6.13.3 closeout](../history/milestones/004.6.13.3_relation_only_semantic_contract_and_final_qwen_consolidation_exit_gate_closeout.md) records `NO_GO` after failing its KEEP→MERGE disagreement gate.
- **Next action:** Preserve source senses. Any different architecture or renewed research requires an explicit new Product Owner/Architect decision and new acceptance criteria; do not resume prompt tuning implicitly.

## VCAP-006 — Provenance of uncommitted M004.6.13 V2 changes

- **Status:** Unresolved historical provenance; not a recovery task by default.
- **Evidence:** Historical closeouts describe V2 work as uncommitted/preserved, but current committed source uses V1 and the current checkout has no such changes or Git stash.
- **Next action:** Preserve the closeout record. Investigate external copies only if a future authorized task has a concrete need; do not restore or adopt unverified changes.
