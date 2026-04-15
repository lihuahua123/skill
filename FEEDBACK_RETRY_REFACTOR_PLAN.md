# Harbor Feedback Retry Refactor Plan

## Goal

Change Harbor so the existing `n_attempts` parameter means:

- retry budget inside a single trial
- same task
- same environment
- same agent conversation/session when the agent supports resume

Do not require any task-specific changes.

## Scope

The refactor will touch Harbor runtime behavior in four places:

1. `harbor/job.py`
2. `harbor/trial/trial.py`
3. agent adapters that can resume an existing conversation
4. verifier result extraction so retry feedback has enough signal

No task files under `skillsbench/tasks*` should need changes.

## Behavioral Change

Current behavior:

- `n_attempts` duplicates the same trial config multiple times
- each attempt is an independent trial
- each attempt starts a fresh agent run

Target behavior:

- one `TrialConfig` per task/agent pair
- `Trial.run()` executes up to `n_attempts` internal attempts
- attempt 1 uses the original task instruction
- later attempts use verifier-driven retry feedback
- agents that support resume keep the same session id
- agents that do not support resume fall back to re-running in the same environment

## Design

### 1. Reinterpret `n_attempts` in `Job`

Files:

- `lib/python3.12/site-packages/harbor/job.py`

Change:

- stop expanding `_trial_configs` by `range(self.config.n_attempts)`
- create exactly one `TrialConfig` per task/agent pair

Reason:

- retry orchestration belongs inside `Trial`, not `Job`

### 2. Add Internal Attempt Loop to `Trial`

Files:

- `lib/python3.12/site-packages/harbor/trial/trial.py`

Change:

- keep environment setup and agent setup once per trial
- add an internal loop from `1..self.config.n_attempts`
- on attempt 1 call normal `agent.run()`
- on later attempts call `agent.continue_run()` when supported
- run verifier after every attempt
- stop on pass or when max attempts reached

New internal responsibilities:

- keep per-attempt timing
- store per-attempt agent context
- store per-attempt verifier result
- generate retry prompt from verifier artifacts

### 3. Add Agent Resume Capability

Files:

- `lib/python3.12/site-packages/harbor/agents/base.py`
- `lib/python3.12/site-packages/harbor/agents/installed/base.py`
- `lib/python3.12/site-packages/harbor/agents/installed/codex.py`
- `lib/python3.12/site-packages/harbor/agents/installed/claude_code.py`

Change:

- add a capability method such as `supports_session_resume()`
- add `continue_run(...)`
- store the recovered `session_id` into `AgentContext.metadata`

Adapter behavior:

- `Codex.run()` keeps using `codex exec ... --json`
- `Codex.continue_run()` uses `codex exec resume <session_id> ... --json`
- `ClaudeCode.run()` keeps using `claude --print --output-format=stream-json`
- `ClaudeCode.continue_run()` uses `claude --print --resume <session_id>`

Fallback behavior:

- adapters without resume support return `False` from `supports_session_resume()`
- `Trial` then falls back to fresh `run()` in the same environment

### 4. Expand Verifier Feedback Extraction

Files:

- `lib/python3.12/site-packages/harbor/models/verifier/result.py`
- `lib/python3.12/site-packages/harbor/verifier/verifier.py`

Current issue:

- verifier result only stores `rewards`
- retry feedback would otherwise have almost no information

Change:

- keep `rewards`
- add paths or copied payload for:
  - `stdout_path`
  - `stderr_path` when present
  - `ctrf_path` when present
  - `reward_path`
- add normalized summary fields:
  - `notes`
  - `feedback_items`

Extraction priority:

1. parse `ctrf.json` failures
2. parse concise failure summary from verifier stdout
3. fall back to reward-only note when nothing else is available

## Data Model Changes

### Trial result

File:

- `lib/python3.12/site-packages/harbor/models/trial/result.py`

Add a per-attempt structure, for example:

- `attempt`
- `instruction_kind`
- `feedback_prompt`
- `agent_session_id`
- `agent_result`
- `verifier_result`
- `started_at`
- `finished_at`

At top level keep:

- final summary fields for backward compatibility where practical
- `first_success_attempt`
- `attempt_count`
- `stop_reason`

## Main Risks and Strategies

### Risk 1: Resume command exists but does not append to the same durable session

Impact:

- retry would look like same-session in code but actually create a forked or fresh conversation

Strategy:

- after each resumed attempt, re-parse session logs
- verify that the session id matches the previous attempt
- verify that the trajectory gained additional steps
- if either check fails, downgrade that attempt to a fallback path and mark it in metadata

### Risk 2: Agent output parsers assume exactly one session directory

Impact:

- resume may create multiple session files or directories

Strategy:

- relax adapter parsing to select the session directory matching the expected session id
- stop relying on "exactly one session directory"

### Risk 3: Verifier output is noisy or inconsistent across tasks

Impact:

- retry prompts become long, weak, or answer-leaky

Strategy:

- normalize feedback centrally in Harbor
- prefer failed test names and concise assertion summaries
- cap extracted text size
- avoid dumping full stdout into the prompt

### Risk 4: Existing analysis expects one result per trial, not per internal attempt

Impact:

- downstream scripts may break

Strategy:

- preserve top-level summary fields where possible
- add `attempts[]` without immediately removing existing top-level fields
- update only the scripts that directly depend on attempt-wise semantics

### Risk 5: Reusing `n_attempts` changes old Harbor semantics

Impact:

- old workflows that expected independent repeated trials will behave differently

Strategy:

- document the semantic change in this branch clearly
- keep the change local to this Harbor copy
- note that this branch is for feedback-retry experiments, not general-purpose upstream parity

## Validation Plan

1. Verify `Codex` first.
2. Verify `ClaudeCode` second.
3. Use a single deterministic task with failing verifier output.
4. Confirm:
   - one trial directory only
   - multiple internal attempts recorded
   - same session id reused across attempts
   - verifier feedback is present in retry prompt metadata
   - trial stops on pass or attempt budget exhaustion

## Non-Goals for First Pass

- supporting every installed agent immediately
- changing task-side verifier scripts
- introducing new CLI flags
- preserving old `n_attempts` semantics
- optimizing prompt format beyond a simple full-refresh retry prompt

## Immediate Execution Order

1. finish baseline repo push
2. update job config expansion logic
3. add per-attempt result model
4. refactor `Trial.run()` into internal retry loop
5. implement `Codex.continue_run()`
6. implement `ClaudeCode.continue_run()`
7. enrich verifier feedback extraction
8. run a focused validation on one task



最小验证已经跑通了，结果说明这次 retry/refactor 的核心编排逻辑是生效的。

这次验证用的是一个临时 smoke task 和一个临时 `retry-probe` 自定义 agent，因为 `claude-code` 在容器里安装时命中了地域限制页，没法用它做端到端验证。但 Harbor 本身的 orchestration 已经验证到了。

验证结果在 `/tmp/harbor-jobs/retry-smoke-20260415-5`：

- 只有一个 trial 目录：`/tmp/harbor-jobs/retry-smoke-20260415-5/harbor-retry-smoke__2BGjdbY`
- `attempt_count = 2`
- `stop_reason = "attempt_budget_exhausted"`
- 两次 attempt 的 `agent_session_id` 都是同一个：`retry-probe-session`
- 第二次 attempt 收到的 instruction 已经变成 verifier feedback，而不是原始 task instruction
- verifier 产物里确实有 `ctrf.json` 和 `reward.txt`

直接证据：

- trial 结果汇总在 [`result.json`](/tmp/harbor-jobs/retry-smoke-20260415-5/harbor-retry-smoke__2BGjdbY/result.json)
- 第二次 retry prompt 在 [`instruction-attempt-2.txt`](/tmp/harbor-jobs/retry-smoke-20260415-5/harbor-retry-smoke__2BGjdbY/agent/instruction-attempt-2.txt)
- attempt 痕迹在 [`attempt.txt`](/tmp/harbor-jobs/retry-smoke-20260415-5/harbor-retry-smoke__2BGjdbY/agent/attempt.txt)
- verifier 反馈产物在 [`ctrf.json`](/tmp/harbor-jobs/retry-smoke-20260415-5/harbor-retry-smoke__2BGjdbY/verifier/ctrf.json)

这次实跑还顺手发现并修掉了一个真实 bug：
- `Trial` 改成内部 attempt 循环后，`TrialConfig` 里原本没有 `n_attempts`
- 我已经补了 `n_attempts` 从 `JobConfig -> TrialConfig` 的传递

当前结论可以定成：

- `Job` 不再把 `n_attempts` 展开成多个 trial，成立
- `Trial.run()` 内部多 attempt，成立
- retry feedback 从 verifier 注入下一次 attempt，成立
- session resume 接口和 same session id 语义，至少在 Harbor orchestration 层成立

还没完成的只有一块：
- 用真实 `codex` 或 `claude-code` 做外部 agent 端到端验证还没过，因为容器内 agent 安装受外部环境限制

如果你要，我下一步建议直接做两件事里的一件：
1. 我继续想办法把 `claude-code`/`codex` 的真实端到端验证跑起来
2. 我先把这次改动涉及的 Harbor 源码再做一轮 review，找逻辑边界和潜在回归点