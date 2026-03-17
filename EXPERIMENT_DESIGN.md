# Experimental Design for Multi-Turn PinchBench

## Research Goal

This study focuses on validator-driven retries in PinchBench/OpenClaw and asks three practical questions:

- how much additional success is gained from extra retry budget
- when retrying stops being token-efficient
- which feedback and stopping policies give the best success-cost tradeoff

The project is framed as an empirical token-efficiency study, not as a new agent method.

## Research Questions

### RQ1

What is the marginal benefit of additional validator-feedback retries?

### RQ3

Under fixed budget or fixed target success, which stopping rule is most token-efficient?

### RQ4

Which feedback policy and feedback format provide the best success-cost tradeoff?

Task complexity should be treated as a stratification variable rather than a standalone RQ.

## Existing Project Foundation

The repository already contains the core append-style retry baseline.

- [`scripts/benchmark.py`](/root/skill/scripts/benchmark.py) builds retry prompts from validator outputs.
- [`scripts/benchmark.py`](/root/skill/scripts/benchmark.py) supports repeated validator-feedback attempts in the same task run.
- [`scripts/benchmark.py`](/root/skill/scripts/benchmark.py) already records attempts, usage, usage-per-round, and grading outputs.
- [`README.md`](/root/skill/README.md) already exposes `--max-task-attempts`.

## Feedback Policy Design

The retry prompt should remain configurable through `feedback_policy`.

### `vague`

- only says the previous attempt did not pass
- asks the agent to continue and retry

### `error-localized`

- identifies failed grading items
- includes validator notes
- does not prescribe a repair plan

### `actionable-path`

- identifies failure points
- adds explicit repair guidance or next-step instructions

## Cache-Friendly Feedback Design

To maximize prompt-cache reuse, retry prompts should support a stable-prefix structure.

### `full-refresh`

- rewrites the whole retry feedback block each round

### `stable-prefix`

- keeps a fixed prefix with task metadata and retry rules
- appends a compact dynamic suffix containing only the latest unresolved issues

## Experimental Design by Research Question

### RQ1: Marginal Benefit of Retry Budget

Objective:

- measure how success grows with retry budget
- identify where marginal gains flatten

Experiment:

- fix `feedback_policy = error-localized`
- fix `feedback_format = full-refresh`
- sweep `max_task_attempts = 1, 2, 3, 4, 5, 6`
- run multiple repetitions per model and task

Metrics:

- `success@k`
- `delta success(k)`
- cumulative tokens and USD cost by attempt
- first-success attempt distribution
- tokens per additional 1% success

### RQ3: Stopping Rule Efficiency

Objective:

- compare simple, interpretable stopping rules under a common retry budget

Experiment:

- fix `feedback_policy = error-localized`
- fix `feedback_format = full-refresh`
- use a common maximum attempt budget such as `5`
- compare:
  - `max-attempts-only`
  - `score-stall`
  - `unresolved-stall`
  - `low-return`

Metrics:

- success vs cumulative tokens
- success vs cumulative USD cost
- success per 1K tokens
- success per dollar
- average token/cost to reach target success
- stop-too-early and stop-too-late rate

### RQ4: Feedback Policy and Format

Objective:

- measure how retry guidance quality changes convergence and token use

Experiment:

- fix `max_task_attempts`
- compare:
  - `vague`
  - `error-localized`
  - `actionable-path`
- cross with:
  - `full-refresh`
  - `stable-prefix`

Metrics:

- final success rate
- first-success attempt
- cumulative token/cost
- per-round improvement rate
- feedback length and cache-related proxy metrics

## Minimal Experiment Matrix

### E1: Attempt Budget Sweep

- supports RQ1
- varies `max_task_attempts`

### E3: Stop Rule Comparison

- supports RQ3
- varies `stop_rule`

### E4: Feedback / Format Comparison

- supports RQ4
- varies `feedback_policy` and `feedback_format`

## Required Code Scope

### Benchmark Runner

File:

- [`scripts/benchmark.py`](/root/skill/scripts/benchmark.py)

Needed support:

- configurable `feedback_policy`
- configurable `feedback_format`
- configurable `stop_rule`
- retry policy metadata in result JSON
- per-attempt retry prompt statistics

### Analysis Pipeline

Needed support:

- `success@k`
- marginal gain by attempt
- token-success and cost-success curves
- stopping-rule comparison
- feedback-policy comparison
- target-success budget backsolve

## Suggested Logging Fields

- `feedback_policy`
- `feedback_format`
- `stop_rule`
- `stop_rule_threshold`
- `stop_reason`
- `first_success_attempt`
- `success_within_budget`
- `cumulative_usage_by_attempt`
- `prompt_tokens_by_attempt`
- `completion_tokens_by_attempt`
- `unresolved_criteria_count`
- feedback text length or token count
- transcript length and per-attempt delta

## Recommended Outputs

### Tables

- single-turn vs multi-turn success / token / cost
- stopping-rule comparison
- feedback-policy comparison
- minimum token budget at matched success

### Figures

- `success@k`
- marginal gain by attempt
- attempts-to-success histogram or CDF
- cumulative token vs success
- cumulative cost vs success
- stopping-rule budget-success curve

## Threats to Validity

- stochastic LLM outputs require repeated runs
- judge-based grading may introduce bias or variance
- cache-hit behavior depends on provider implementation
- static complexity proxies may not perfectly reflect task difficulty

## Recommended Implementation Order

1. Reproduce the append baseline with attempt-budget sweeps.
2. Compare stopping rules for token efficiency.
3. Compare feedback policies and cache-friendly formatting.
4. Add final reporting for budget-success frontiers.

## One-Sentence Summary

The main contribution should be framed as a systematic analysis of retry benefit boundaries, stopping efficiency, and feedback efficiency in real tool-using agents.
