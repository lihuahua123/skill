---
name: pinchbench-retry-core-fixed
description: Offline-evolved skill generated from historical benchmark data.
category: workflow
skill_id: pinchbench-retry-core-fixed__c1d32db6
origin: fixed
parent_skill_ids:
  - pinchbench-retry-core
source_task_id: task_17_email_search
source_analysis_id: pinchbench::task_17_email_search::pinchbench-minimax-cn-minimax-m2-5
---

# pinchbench retry core fixed

## Why this exists

This skill was generated using an OpenSpace-style evolution flow:

1. historical execution records were analyzed
2. an evolution suggestion was created
3. the suggestion was materialized as a versioned skill

## Evolution Type

`fix`

## Parent Skills

pinchbench-retry-core

## Direction

Fix retry handling for task_17_email_search. Add earlier stop conditions, output-contract checks, and failure-class detection.

## Rationale

Task kept retrying without reaching success; this maps to the OpenSpace fix pattern for an existing skill that is applied but not reliably effective.

## Source Evidence

- benchmark: `pinchbench`
- task: `task_17_email_search`
- note: `benchmark=pinchbench; attempt_count=6; first_success_attempt=None; last_unresolved_criteria=5`

## Workflow

1. Read the verifier-visible failure before changing strategy.
2. Check output-contract and artifact existence before broad rewrites.
3. Preserve successful intermediate artifacts and only patch the narrow mismatch.
4. Stop repeated retries when the failure class is unchanged.
5. Escalate to a new task-family-specific method when the loop is not converging.

## Task-Family Guidance

- If the task touches structured artifacts such as PDFs, XLSX, or generated reports, validate the artifact first.
- If the task is planning-heavy or search-heavy, avoid repeating the same long-horizon strategy after two similar failures.
- If the verifier identifies one narrow mismatch, patch that mismatch instead of restarting the whole task.
