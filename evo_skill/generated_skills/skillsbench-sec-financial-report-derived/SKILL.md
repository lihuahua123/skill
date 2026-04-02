---
name: skillsbench-sec-financial-report-derived
description: Offline-evolved skill generated from historical benchmark data.
category: workflow
skill_id: skillsbench-sec-financial-report-derived__73913dd7
origin: derived
parent_skill_ids:
  - 13f-analyzer
source_task_id: sec-financial-report
source_analysis_id: skillsbench::sec-financial-report::skillsbench-minimax-cn-minimax-m2-5-merged-with-token-patch
---

# skillsbench sec financial report derived

## Why this exists

This skill was generated using an OpenSpace-style evolution flow:

1. historical execution records were analyzed
2. an evolution suggestion was created
3. the suggestion was materialized as a versioned skill

## Evolution Type

`derived`

## Parent Skills

13f-analyzer

## Direction

Capture the successful repair loop for sec-financial-report. Emphasize narrowing from full rework to verifier-visible repair.

## Rationale

Task succeeded only after retries, which matches the OpenSpace derived-skill pattern: preserve the parent workflow and add a more specific retry strategy.

## Source Evidence

- benchmark: `skillsbench`
- task: `sec-financial-report`
- note: `benchmark=skillsbench; attempt_count=2; first_success_attempt=2; last_unresolved_criteria=0; parent_candidates=13f-analyzer`

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
