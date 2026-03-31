# SkillsBench Integration Refactor Plan

## Goal

Add `skillsbench` support to the existing `/root/skill` RQ pipeline with the smallest possible code change, while preserving current `pinchbench` behavior and result compatibility.

The guiding rule is:

- Do not rewrite RQ1/RQ3/RQ4 analysis first.
- Do not break current `pinchbench` scripts, outputs, or upload flow.
- Add a thin benchmark adaptation layer so both benchmarks emit the same normalized result schema.

## Current State

The current codebase is effectively hard-wired to `pinchbench` in the execution layer:

- `scripts/run.sh` always runs `scripts/benchmark.py`
- `scripts/experiments/common.sh` always calls `run.sh`
- `scripts/benchmark.py` loads PinchBench markdown tasks and runs the OpenClaw flow
- `scripts/lib_tasks.py` only understands PinchBench task markdown

However, the RQ analysis layer is already fairly generic.

`scripts/analyze_retries.py` mainly depends on:

- top-level result metadata
- `tasks[]`
- `tasks[].task_id`
- `tasks[].attempts[]`
- `attempts[].grading.score`
- `attempts[].grading.max_score`
- `attempts[].execution.usage.total_tokens`
- `attempts[].execution.usage.cost_usd`
- `attempts[].execution.execution_time`

This is the key leverage point: if `skillsbench` can be normalized into the same schema, most of the analysis code does not need to change.

## Minimal-Change Strategy

Use a two-layer design:

1. Keep the existing normalized result schema as the stable contract.
2. Introduce benchmark-specific adapters underneath that contract.

That means:

- `pinchbench` remains the default and continues to work as-is
- `skillsbench` is added by mapping Harbor/SkillsBench outputs into the same JSON shape currently consumed by the RQ scripts

Do not make RQ scripts benchmark-aware until normalization is in place.

## Target Architecture

Introduce a new benchmark adapter layer:

- `scripts/lib_benchmarks.py`

Suggested interface:

```python
class BenchmarkAdapter:
    name: str

    def run(self, args) -> dict:
        ...

    def normalize_result(self, raw_result: dict, args) -> dict:
        ...
```

Concrete implementations:

- `PinchBenchAdapter`
- `SkillsBenchAdapter`

The benchmark runner entrypoint chooses an adapter by CLI flag:

- `--benchmark pinchbench`
- `--benchmark skillsbench`

Default stays:

- `pinchbench`

## Stable Result Schema

Keep the current output schema used by `scripts/benchmark.py` and `scripts/analyze_retries.py`.

The minimum fields that must remain valid are:

```json
{
  "benchmark": "pinchbench|skillsbench",
  "model": "...",
  "run_id": "...",
  "suite": "...",
  "runs_per_task": 1,
  "max_task_attempts": 3,
  "retry_policies": {},
  "tasks": [
    {
      "task_id": "...",
      "status": "...",
      "execution_time": 0.0,
      "grading": {
        "score": 1.0,
        "max_score": 1.0
      },
      "attempt_count": 1,
      "first_success_attempt": 1,
      "success_within_budget": true,
      "attempts": [
        {
          "attempt_number": 1,
          "grading": {
            "score": 1.0,
            "max_score": 1.0
          },
          "execution": {
            "execution_time": 0.0,
            "usage": {
              "input_tokens": 0,
              "output_tokens": 0,
              "total_tokens": 0,
              "cost_usd": 0.0
            }
          }
        }
      ]
    }
  ],
  "efficiency": {
    "success_rate": 0.0
  }
}
```

Anything extra can remain benchmark-specific, but this contract should be treated as required.

## SkillsBench Mapping Rules

Map SkillsBench/Harbor artifacts into the existing schema instead of changing the schema.

### Raw SkillsBench Sources

Expected sources from Harbor/SkillsBench:

- `result.json`
- `verifier/reward.txt`
- `verifier/ctrf.json`
- `agent/trajectory.json`
- or `agent/codex.txt`
- or `agent/claude-code.txt`
- optional `trial.log`

### Mapping

For each SkillsBench trial attempt:

- `task_id`
  - use task name / task directory name
- `attempts[i].grading.score`
  - parse `verifier/reward.txt`
- `attempts[i].grading.max_score`
  - always `1.0`
- `attempts[i].execution.execution_time`
  - derive from `result.json`
- `attempts[i].execution.usage.*`
  - derive from `result.json`
- `attempts[i].execution.transcript`
  - normalize from trajectory files if available
- `attempts[i].feedback`
  - optional summary built from `ctrf.json`
- `attempts[i].unresolved_criteria_count`
  - optional count of failed tests from `ctrf.json`

Then derive task-level fields:

- `attempt_count`
- `first_success_attempt`
- `success_within_budget`
- `grading.score`
  - use final attempt score or mean score, but be consistent

Recommended for minimal change:

- task-level `grading.score` = final attempt score
- success = any attempt with `score >= max_score`

## What Not To Change First

To minimize risk, do **not** start with these:

- `scripts/analyze_retries.py` core success/cost logic
- existing PinchBench grading logic in `scripts/lib_grading.py`
- existing PinchBench markdown task parser in `scripts/lib_tasks.py`
- upload code in `scripts/lib_upload.py`

These should remain untouched until normalization is working.

## Refactor Order

Follow this sequence strictly.

### Phase 1: Add a benchmark selector without changing behavior

Files:

- `scripts/run.sh`
- `scripts/benchmark.py`
- `scripts/experiments/common.sh`

Changes:

- Add a `--benchmark` option
- Default to `pinchbench`
- If omitted, behavior must remain identical to today

Why first:

- This creates the routing hook without changing benchmark logic
- It keeps all current RQ scripts working

### Phase 2: Extract PinchBench logic behind an adapter

Files:

- new: `scripts/lib_benchmarks.py`
- maybe small edits in `scripts/benchmark.py`

Changes:

- Move current PinchBench orchestration into `PinchBenchAdapter`
- Keep result JSON identical
- `scripts/benchmark.py` becomes a dispatcher instead of the only implementation

Why second:

- This is the smallest architectural change that buys extensibility
- It lets you verify no PinchBench regressions before adding SkillsBench

### Phase 3: Add SkillsBench raw result ingestion only

Files:

- new: `scripts/lib_skillsbench.py`
- new or merged into `scripts/lib_benchmarks.py`

Changes:

- Implement a `SkillsBenchAdapter`
- Start from existing Harbor result directories or result exports
- Do not implement all feedback/retry features yet
- Only normalize raw SkillsBench results into the shared result schema

Why third:

- This gets cross-benchmark support working as fast as possible
- It avoids premature feature parity work

### Phase 4: Keep RQ analysis schema-stable and only make cosmetic updates

Files:

- `scripts/analyze_retries.py`

Changes:

- Replace hardcoded `PinchBench` plot titles with neutral titles like `Benchmark Retry Success@k`
- Add optional display of `benchmark`
- Do not change the success/cost curve formulas

Why fourth:

- Once both benchmarks emit the same schema, this file should need very little work

### Phase 5: Add benchmark-specific capability flags only if necessary

Files:

- likely `scripts/lib_benchmarks.py`
- maybe `scripts/benchmark.py`

Changes:

- Explicitly mark which stop rules and feedback policies are supported by each benchmark
- Example:
  - `pinchbench`: full support
  - `skillsbench`: initially only `max-attempts-only`

Why fifth:

- RQ3/RQ4 have assumptions that may not fully transfer to SkillsBench
- Delay this until after baseline ingestion works

### Phase 6: Extend SkillsBench support for richer RQ3/RQ4 semantics

Only after Phases 1-5 are stable.

Possible additions:

- derive failed-test count from `ctrf.json` for `unresolved_criteria_count`
- derive structured feedback text from test failures
- support stop rules like:
  - `score-stall`
  - `unresolved-stall`
  - `low-return`

This phase is optional for the first working integration.

## Concrete File-Level Plan

### 1. `scripts/benchmark.py`

Refactor role:

- from monolithic PinchBench runner
- to benchmark dispatcher + shared result writer

Keep:

- CLI parsing shape as much as possible
- current output JSON contract

Add:

- `--benchmark`
- adapter dispatch

Minimize:

- avoid moving every helper immediately
- only extract enough to isolate PinchBench and add SkillsBench

### 2. `scripts/run.sh`

Keep current behavior by default.

Only change:

- allow passing `--benchmark`
- update help text from “PinchBench” to generic benchmark runner

### 3. `scripts/experiments/common.sh`

Small change only:

- allow `BENCHMARK=${BENCHMARK:-pinchbench}`
- pass `--benchmark "${BENCHMARK}"` into `run.sh`

This preserves all current RQ shell scripts.

### 4. `scripts/analyze_retries.py`

Minimal edits:

- titles should not say `PinchBench`
- summary can include `benchmark`

Do not change:

- `_attempt_passed`
- `_compute_curve`
- token/cost formulas

### 5. New `scripts/lib_benchmarks.py`

Responsibilities:

- adapter selection
- common normalization helpers
- benchmark capability reporting

Suggested contents:

- `get_benchmark_adapter(name: str)`
- `PinchBenchAdapter`
- `SkillsBenchAdapter`
- shared helpers for normalized task/attempt entries

### 6. New `scripts/lib_skillsbench.py`

Responsibilities:

- parse Harbor jobs/trials
- load `reward.txt`, `ctrf.json`, trajectory files
- normalize them into your shared schema

Reason to keep separate:

- avoids polluting existing PinchBench files
- contains all SkillsBench-specific assumptions in one place

## Compatibility Rules

To avoid breaking the current project:

- default benchmark must remain `pinchbench`
- existing result JSON fields must remain present
- existing `results/rq1`, `results/rq3`, `results/rq4` layout should still work
- existing RQ scripts should still run unchanged when `BENCHMARK` is not set
- no existing PinchBench task markdown format should be modified
- no existing grading logic should be rewritten before adapter dispatch works

## Recommended First Functional Scope

For the first working version of SkillsBench support, implement only:

- benchmark selection
- SkillsBench normalized result ingestion
- RQ1-compatible output
- generic analysis compatibility

Delay full parity for RQ3/RQ4 until after this works.

Reason:

- RQ1 mostly needs attempt-wise success/cost curves
- RQ3 and RQ4 depend more on retry semantics and feedback modeling
- forcing parity too early will increase code churn

## Practical Milestone Plan

### Milestone A

Goal:

- current PinchBench still works with no behavior change

Deliverables:

- `--benchmark pinchbench` added
- defaults unchanged

Validation:

- existing `rq1.sh`, `rq3.sh`, `rq4.sh` still produce same style outputs

### Milestone B

Goal:

- SkillsBench can produce normalized result JSON

Deliverables:

- `SkillsBenchAdapter`
- one normalized output JSON for a small test set

Validation:

- `scripts/analyze_retries.py` runs on SkillsBench result JSON without code changes or with only cosmetic updates

### Milestone C

Goal:

- common RQ workflow supports both benchmarks

Deliverables:

- environment variable or CLI selection of benchmark in experiment scripts

Validation:

- same RQ shell scripts can be used with:
  - `BENCHMARK=pinchbench`
  - `BENCHMARK=skillsbench`

### Milestone D

Goal:

- richer SkillsBench retry/feedback semantics if needed

Deliverables:

- `ctrf.json` failure summary support
- optional stop-rule support

## Recommended Implementation Priority

If time is limited, implement in exactly this order:

1. Add `--benchmark` plumbing
2. Extract PinchBench into adapter with zero behavior change
3. Add SkillsBench normalization to existing result schema
4. Make analysis titles/schema benchmark-neutral
5. Add benchmark capability flags
6. Add advanced SkillsBench feedback/stop-rule support

## Final Recommendation

The least risky path is:

- keep analysis stable
- keep output schema stable
- add a benchmark adapter layer
- treat SkillsBench integration as a normalization problem, not an analysis rewrite

This approach minimizes code churn, preserves current PinchBench behavior, and leaves you with a scalable architecture for supporting multiple benchmarks later.
