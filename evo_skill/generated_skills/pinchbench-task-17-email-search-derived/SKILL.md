---
name: pinchbench-task-17-email-search-derived
description: Offline-evolved skill generated from historical benchmark data.
category: workflow
skill_id: pinchbench-task-17-email-search-derived__43798bd9
origin: derived
parent_skill_ids:
  - pinchbench-retry-core
source_task_id: task_17_email_search
source_analysis_id: pinchbench::task_17_email_search::pinchbench-autodl-gpt-5-3-codex
---

# pinchbench task 17 email search derived

## Why this exists

This skill was generated using an OpenSpace-style evolution flow:

1. historical execution records were analyzed
2. an evolution suggestion was created
3. the suggestion was materialized as a versioned skill

## Evolution Type

`derived`

## Parent Skills

pinchbench-retry-core

## Direction

Capture the successful repair loop for task_17_email_search. Emphasize narrowing from full rework to verifier-visible repair.

## Rationale

Task succeeded only after retries, which matches the OpenSpace derived-skill pattern: preserve the parent workflow and add a more specific retry strategy.

## Source Evidence

- benchmark: `pinchbench`
- task: `task_17_email_search`
- note: `benchmark=pinchbench; attempt_count=2; first_success_attempt=2; last_unresolved_criteria=0`

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
