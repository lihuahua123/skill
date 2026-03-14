# Experimental Design for Multi-Turn PinchBench

## Research Goal

This study uses PinchBench/OpenClaw to evaluate real agent behavior under iterative repair after failure. The goal is not just to show that multi-turn feedback can help, but to quantify:

- the marginal benefit of additional retries
- the distribution of attempts required for success
- the tradeoff between token/cost and success
- how feedback policy and context policy affect convergence

## Existing Project Foundation

The repository already contains a usable multi-turn baseline.

- [`scripts/benchmark.py`](/root/skill/scripts/benchmark.py) defines `_build_iteration_feedback`, which builds retry prompts from validator score, breakdown, notes, and grading criteria.
- [`scripts/benchmark.py`](/root/skill/scripts/benchmark.py) implements in-place retry with the same workspace and same session.
- [`scripts/benchmark.py`](/root/skill/scripts/benchmark.py) already stores `attempts`, `usage`, `usage_per_round`, and grading outputs in the result JSON.
- [`README.md`](/root/skill/README.md) already exposes `--max-task-attempts`.

This means the baseline data path for RQ1, RQ2, and part of RQ3 already exists. The main missing pieces are policy variables, context variants, and finer-grained instrumentation.

## Research Questions

The study should focus on four main research questions.

### RQ1

What is the marginal benefit of multi-turn validator feedback?

### RQ2

How many iterations are typically required for success, and what is the distribution of attempts-to-success?

### RQ3

What is the tradeoff between token/cost and success?

### RQ4

How do feedback policy and context policy affect convergence?

Task complexity should be treated as a moderator or stratification variable rather than a standalone main RQ.

## Feedback Policy Design

The retry prompt should be abstracted into configurable `feedback_policy` variants.

### `vague`

Meaning:

- only tells the agent that the previous attempt did not pass
- asks the agent to continue working and retry

Purpose:

- weak-feedback baseline

### `error-localized`

Meaning:

- identifies which grading items failed
- includes validator notes
- does not explicitly tell the agent how to repair the issue

Purpose:

- measures the value of locating the error without prescribing a fix

### `actionable-path`

Meaning:

- identifies the failure
- provides explicit repair guidance or next-step instructions

Purpose:

- measures whether higher-quality feedback reduces attempts and improves success

## Cache-Friendly Feedback Design

To maximize prompt cache reuse, feedback templates should use a stable-prefix structure instead of rewriting the full feedback each round.

### Stable Prefix

The stable prefix should include:

- task ID
- original grading criteria
- common retry rules
- fixed description of the active feedback policy

This section should remain identical across attempts for the same task.

### Dynamic Suffix

The dynamic suffix should include:

- latest attempt number
- latest score
- unresolved issues only
- short validator notes or repair steps

This section should be appended at the end of the prompt and should remain compact.

### Design Rules

- do not repeat full history across attempts
- do not repeat already-passed items
- keep ordering fixed across rounds
- place changing content at the end
- prefer structured fields over long free-form summaries

This allows two formatting variants:

- `full-refresh`: rewrite a full feedback block every round
- `stable-prefix`: fixed prefix plus a small changing suffix

The latter is the preferred cache-friendly design.

## Context Policy Design

The system should support multiple `context_policy` variants.

### `append`

Meaning:

- keep the same session
- keep the same workspace
- append retry feedback into the existing context

Role:

- current baseline

### `fresh-session`

Meaning:

- start a new session
- keep the workspace state
- inject a compact retry prompt or feedback summary

Role:

- isolates conversational-history effects from workspace-state effects

### `rollback`

Meaning:

- restore the workspace to a snapshot before the failed attempt
- use a new session
- inject only the retry guidance

Role:

- tests whether context/state rollback can improve success while reducing cost

Important constraint:

- rollback must address both session history and workspace state; resetting only the session without restoring files will confound the experiment

## Experimental Design by Research Question

### RQ1: Marginal Benefit of Multi-Turn Feedback

Objective:

- measure how much each additional retry improves success

Experiment:

- fix one feedback strategy, initially the current default or `error-localized`
- sweep `max_task_attempts = 1, 2, 3, 4, 5, 6`
- run multiple repetitions per model and per task

Metrics:

- `success@k`
- `delta success(k) = success@k - success@(k-1)`
- additional tokens per extra attempt
- additional cost per extra attempt

Questions answered:

- how much better is multi-turn than single-turn
- where do gains concentrate
- where does the curve plateau

### RQ2: Attempts-to-Success Distribution

Objective:

- characterize when success tends to happen

Experiment:

- fix a feedback strategy
- run with a high enough upper bound such as `max_task_attempts = 6` or `8`
- record the first successful attempt for each successful run
- treat failed runs as censored cases if survival analysis is used

Metrics:

- first-success attempt distribution
- median attempts to success
- `P(success by round k)`
- per-model and per-task-category distributions

Questions answered:

- in which round does success usually occur
- whether later rounds rescue difficult cases or provide little value

### RQ3: Token Cost vs Success Tradeoff

Objective:

- quantify whether more retries are worth the cost

Experiment:

- reuse the `max_task_attempts = 1..k` sweep
- compare models under the same attempt budget
- generate cost-success and token-success curves

Metrics:

- success vs cumulative tokens
- success vs cumulative USD cost
- tokens per additional 1% success
- score per 1K tokens
- success per dollar

Questions answered:

- what retry budget is the most cost-effective
- whether stronger models benefit less from additional retries
- whether different models occupy different Pareto frontiers

### RQ4: Effect of Feedback Quality on Convergence

Objective:

- measure how feedback specificity changes convergence behavior

Experiment:

- fix `max_task_attempts`, e.g. `5`
- compare:
  - `vague`
  - `error-localized`
  - `actionable-path`
- keep all other settings identical
- optionally cross with feedback formatting:
  - `full-refresh`
  - `stable-prefix`

Metrics:

- final success rate
- first-success attempt
- average cumulative token/cost
- per-round improvement rate
- failure mode distribution

Questions answered:

- whether more specific feedback improves convergence
- whether better feedback is worth the extra prompt budget
- whether cache-friendly formatting preserves performance while lowering cost

## Extended Experiment: Append vs Rollback

This should be treated as a focused extension rather than mixed into the main four RQs.

Experiment:

- fix one feedback policy
- compare:
  - `append`
  - `fresh-session`
  - `rollback`
- control whether workspace state is preserved or restored

Metrics:

- final success
- attempts to success
- cumulative tokens and cost
- late-round degradation
- transcript growth

Questions answered:

- whether context pollution is a real effect
- whether rollback can improve the cost-performance boundary

## Task Complexity Analysis

Task complexity should be used as a stratification variable rather than a main standalone research question.

Possible complexity proxies:

- `timeout_seconds`
- number of grading criteria
- number of workspace fixture files
- whether the task uses `llm_judge`
- task category
- empirical `pass@1` difficulty

These can be extracted from task frontmatter and task structure without requiring manual labels.

## Code Changes Required

No code changes are made yet. The following summarizes the implementation scope.

### 1. Benchmark Runner

File:

- [`scripts/benchmark.py`](/root/skill/scripts/benchmark.py)

Changes needed:

- abstract `_build_iteration_feedback` into configurable `feedback_policy`
- add `context_policy`
- add CLI flags for retry strategy variants
- record policy metadata and stop reasons in result JSON
- support cache-friendly `stable-prefix` feedback formatting

### 2. Agent Execution Layer

File:

- [`scripts/lib_agent.py`](/root/skill/scripts/lib_agent.py)

Changes needed:

- support new-session retries with workspace reuse
- support workspace snapshot/restore for rollback experiments
- record clearer session/workspace lifecycle metadata

### 3. Analysis Pipeline

Files to add or update:

- a dedicated analysis script or notebook

Changes needed:

- compute `success@k`
- compute marginal gain by attempt
- compute attempts-to-success distribution
- compute token-success and cost-success curves
- compare feedback/context policy variants
- stratify results by task complexity proxies

### 4. Task Metadata

Optional changes:

- add explicit complexity tags in task frontmatter

Alternative:

- infer complexity only from existing metadata and empirical difficulty

## Suggested New Configuration Surface

Recommended future CLI options:

- `--feedback-policy`
- `--feedback-format`
- `--context-policy`
- `--max-task-attempts`
- `--stop-rule`
- `--snapshot-workspace`

## Suggested Additional Logging Fields

The current results already store attempts and usage, but more detail is needed for analysis.

Recommended fields:

- `feedback_policy`
- `feedback_format`
- `context_policy`
- `stop_reason`
- `first_success_attempt`
- `cumulative_usage_by_attempt`
- `unresolved_criteria_count`
- feedback text length or token count
- `workspace_restored`
- `session_reset`

## Recommended Outputs

### Tables

- single-turn vs multi-turn overall success, token, and cost
- feedback policy comparison
- append vs rollback comparison

### Figures

- `success@k` curve
- marginal gain by attempt
- attempts-to-success histogram or CDF
- cumulative token vs success
- cumulative cost vs success
- complexity-stratified success-cost curves
- append vs rollback comparison figure

## Threats to Validity

The experimental design should explicitly acknowledge the following limitations.

- LLM output stochasticity requires repeated runs
- judge-based grading may introduce bias or variance
- cache-hit behavior may depend on provider implementation and may not be fully observable
- rollback experiments become confounded if session state and workspace state are not both controlled
- static complexity proxies may not perfectly reflect true cognitive difficulty

## Recommended Implementation Order

The project should proceed in the following order.

1. Reproduce the current append baseline with attempt-budget sweeps.
2. Add configurable `feedback_policy`.
3. Add cache-friendly `stable-prefix` feedback formatting.
4. Run the main RQ1-RQ4 experiments.
5. Implement and evaluate `append` vs `rollback`.

## One-Sentence Summary

The main contribution of the study should be framed as a systematic analysis of the benefit boundary, cost boundary, and convergence mechanisms of validator-driven iterative repair in real tool-using agents, rather than simply showing that multi-turn retries can help.
