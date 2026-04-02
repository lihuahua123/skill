---
name: skillsbench-retry-core-fixed
description: Offline-evolved skill generated from historical benchmark data.
category: workflow
skill_id: skillsbench-retry-core-fixed__8c8bc045
origin: fixed
parent_skill_ids:
  - suricata-rules-basics
  - pcap-analysis
  - pcap-analysis-n
source_task_id: suricata-custom-exfil
source_analysis_id: skillsbench::suricata-custom-exfil::skillsbench-openai-gpt-5-3-codex-2026-03-28-19-58-04
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

suricata-rules-basics, pcap-analysis, pcap-analysis-n

## Direction

Fix retry handling for suricata-custom-exfil. Add earlier stop conditions, output-contract checks, and failure-class detection.

## Rationale

Task kept retrying without reaching success; this maps to the OpenSpace fix pattern for an existing skill that is applied but not reliably effective.

## Source Evidence

- benchmark: `skillsbench`
- task: `suricata-custom-exfil`
- note: `benchmark=skillsbench; attempt_count=6; first_success_attempt=None; last_unresolved_criteria=1; parent_candidates=suricata-rules-basics,pcap-analysis,pcap-analysis-n`

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
