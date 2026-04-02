---
name: skillsbench-dapt-intrusion-detection-captured
description: Offline-evolved skill generated from historical benchmark data.
category: workflow
skill_id: skillsbench-dapt-intrusion-detection-captured__832d3fd4
origin: captured
parent_skill_ids:
  []
source_task_id: dapt-intrusion-detection
source_analysis_id: skillsbench::dapt-intrusion-detection::skillsbench-openai-gpt-5-3-codex-2026-03-28-19-58-04
---

# skillsbench dapt intrusion detection captured

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

Capture a reusable task-family playbook from dapt-intrusion-detection, including verifier-first repair and artifact validation.

## Rationale

The task shows a reusable workflow pattern that should exist as a standalone skill rather than only as a retry tweak.

## Source Evidence

- benchmark: `skillsbench`
- task: `dapt-intrusion-detection`
- note: `benchmark=skillsbench; attempt_count=3; first_success_attempt=3; last_unresolved_criteria=0`

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
