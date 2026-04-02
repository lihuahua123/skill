---
name: skillsbench-pddl-tpp-planning-captured
description: Offline-evolved skill generated from historical benchmark data.
category: workflow
skill_id: skillsbench-pddl-tpp-planning-captured__c4e4722d
origin: captured
parent_skill_ids:
  []
source_task_id: pddl-tpp-planning
source_analysis_id: skillsbench::pddl-tpp-planning::skillsbench-minimax-cn-minimax-m2-5-recovered-full-87tasks
---

# skillsbench pddl tpp planning captured

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

Capture a reusable task-family playbook from pddl-tpp-planning, including verifier-first repair and artifact validation.

## Rationale

The task shows a reusable workflow pattern that should exist as a standalone skill rather than only as a retry tweak.

## Source Evidence

- benchmark: `skillsbench`
- task: `pddl-tpp-planning`
- note: `benchmark=skillsbench; attempt_count=0; first_success_attempt=None; parent_candidates=pddl-skills`

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
