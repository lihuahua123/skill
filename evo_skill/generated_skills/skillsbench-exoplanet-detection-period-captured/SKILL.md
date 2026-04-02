---
name: skillsbench-exoplanet-detection-period-captured
description: Offline-evolved skill generated from historical benchmark data.
category: workflow
skill_id: skillsbench-exoplanet-detection-period-captured__a2c2a7ba
origin: captured
parent_skill_ids:
  []
source_task_id: exoplanet-detection-period
source_analysis_id: skillsbench::exoplanet-detection-period::skillsbench-minimax-cn-minimax-m2-5-recovered-full-87tasks
---

# skillsbench exoplanet detection period captured

## Why this exists

This skill was generated using an OpenSpace-style evolution flow:

1. historical execution records were analyzed
2. an evolution suggestion was created
3. the suggestion was materialized as a versioned skill

## Evolution Type

`captured`

## Parent Skills

(none)

## Direction

Capture a reusable task-family playbook from exoplanet-detection-period, including verifier-first repair and artifact validation.

## Rationale

The task shows a reusable workflow pattern that should exist as a standalone skill rather than only as a retry tweak.

## Source Evidence

- benchmark: `skillsbench`
- task: `exoplanet-detection-period`
- note: `benchmark=skillsbench; attempt_count=2; first_success_attempt=2; last_unresolved_criteria=0; parent_candidates=light-curve-preprocessing,transit-least-squares`

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
