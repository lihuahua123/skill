---
name: skillsbench-find-topk-similiar-chemicals-derived
description: Offline-evolved skill generated from historical benchmark data.
category: workflow
skill_id: skillsbench-find-topk-similiar-chemicals-derived__e8d6d88d
origin: derived
parent_skill_ids:
  - pdf
source_task_id: find-topk-similiar-chemicals
source_analysis_id: skillsbench::find-topk-similiar-chemicals::skillsbench-openai-gpt-5-3-codex-2026-03-28-19-58-04
---

# skillsbench find topk similiar chemicals derived

## Why this exists

This skill was generated using an OpenSpace-style evolution flow:

1. historical execution records were analyzed
2. an evolution suggestion was created
3. the suggestion was materialized as a versioned skill

## Evolution Type

`derived`

## Parent Skills

pdf

## Direction

Capture the successful repair loop for find-topk-similiar-chemicals. Emphasize narrowing from full rework to verifier-visible repair.

## Rationale

Task succeeded only after retries, which matches the OpenSpace derived-skill pattern: preserve the parent workflow and add a more specific retry strategy.

## Source Evidence

- benchmark: `skillsbench`
- task: `find-topk-similiar-chemicals`
- note: `benchmark=skillsbench; attempt_count=2; first_success_attempt=2; last_unresolved_criteria=0; parent_candidates=pdf`

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
