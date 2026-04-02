---
name: skillsbench-crystallographic-wyckoff-position-analysis-derived
description: Offline-evolved skill generated from historical benchmark data.
category: workflow
skill_id: skillsbench-crystallographic-wyckoff-position-analysis-derived__6173c7ef
origin: derived
parent_skill_ids:
  - pymatgen
  - pdf
source_task_id: crystallographic-wyckoff-position-analysis
source_analysis_id: skillsbench::crystallographic-wyckoff-position-analysis::skillsbench-minimax-cn-minimax-m2-5-recovered-full-87tasks
---

# skillsbench crystallographic wyckoff position analysis derived

## Why this exists

This skill was generated using an OpenSpace-style evolution flow:

1. historical execution records were analyzed
2. an evolution suggestion was created
3. the suggestion was materialized as a versioned skill

## Evolution Type

`derived`

## Parent Skills

pymatgen, pdf

## Direction

Capture the successful repair loop for crystallographic-wyckoff-position-analysis. Emphasize narrowing from full rework to verifier-visible repair.

## Rationale

Task succeeded only after retries, which matches the OpenSpace derived-skill pattern: preserve the parent workflow and add a more specific retry strategy.

## Source Evidence

- benchmark: `skillsbench`
- task: `crystallographic-wyckoff-position-analysis`
- note: `benchmark=skillsbench; attempt_count=2; first_success_attempt=2; last_unresolved_criteria=0; parent_candidates=pymatgen,pdf`

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
