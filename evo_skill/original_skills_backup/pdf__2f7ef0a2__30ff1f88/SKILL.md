---
name: skillsbench-retry-core-fixed
description: Offline-evolved skill generated from historical benchmark data.
category: workflow
skill_id: skillsbench-retry-core-fixed__645013e0
origin: fixed
parent_skill_ids:
  - pdf
  - xlsx
source_task_id: financial-modeling-qa
source_analysis_id: skillsbench::financial-modeling-qa::skillsbench-minimax-cn-minimax-m2-5
---

# skillsbench retry core fixed

## Why this exists

This skill was generated using an OpenSpace-style evolution flow:

1. historical execution records were analyzed
2. an evolution suggestion was created
3. the suggestion was materialized as a versioned skill

## Evolution Type

`fix`

## Parent Skills

pdf, xlsx

## Direction

Fix retry handling for financial-modeling-qa. Add earlier stop conditions, output-contract checks, and failure-class detection.

## Rationale

Task kept retrying without reaching success; this maps to the OpenSpace fix pattern for an existing skill that is applied but not reliably effective.

## Source Evidence

- benchmark: `skillsbench`
- task: `financial-modeling-qa`
- note: `benchmark=skillsbench; attempt_count=2; first_success_attempt=None; last_unresolved_criteria=1; parent_candidates=pdf,xlsx`

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
