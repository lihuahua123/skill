# External Retry Advisor 改成 Intra-Attempt 三分支 Stuck Judge 的最简单方案

## 目标

把 `scripts/experiments/run_swebench_single_eval.sh` 里的：

- `EXTERNAL_RETRY_ADVISOR_ENABLED`
- `EXTERNAL_RETRY_ADVISOR_MAX_TOKENS`

这条现有线路，从“attempt 失败后给下一次 retry 生成建议”，改成：

- agent 在**同一 attempt / 同一会话**里运行一段时间没进展时
- 调用第三方 advisor 判断当前是否 stuck
- 如果不是 stuck，只输出 `No`
- 如果 stuck 但还适合留在当前会话里，输出 `Advice`
- 如果 stuck 且当前上下文已经太长，输出 `RestartSession`
- 然后主流程根据返回结果：
  - 忽略
  - 在当前会话中注入建议继续跑
  - 或保留工作区、重启一个新 session，继续同一 attempt

这里追求的是**最简单改法**，不是最通用、最干净的架构。

## 现状

入口脚本当前只是把参数透传给 runner：

- `skill/scripts/experiments/run_swebench_single_eval.sh`

当前传参：

- `--external-retry-advisor-enabled`
- `--external-retry-advisor-model`
- `--external-retry-advisor-max-tokens`

现在这条线实际接在：

- `skill/scripts/run_swebench_with_minisweagent.py`
- `skill/scripts/swebench_retry_advisor.py`

当前行为是：

1. 某个 attempt 跑完
2. verifier/eval 失败
3. `build_feedback_prompt(...)` 调 `request_retry_advice(...)`
4. advice 被拼进下一次 attempt 的 `feedback_prompt`

也就是说，**它是 inter-attempt retry advisor，不是 intra-attempt stuck judge**。

## 作用域边界

这次方案必须严格限制在 **SWE-bench 专用链路**：

- 入口必须是 `skill/scripts/run_swebench_with_minisweagent.py`
- 只影响它加载出来的 `DefaultAgent / ExperienceRetrievalAgent`
- 只对通过这个 runner 跑出来的 SWE-bench attempt 生效

明确不改这些链路：

- `skill/scripts/benchmark.py`
- `skill/scripts/run_skillsbench_with_early_stop.py`
- `skillsbench/libs/terminus_agent/...`
- 任何 Harbor 原生 benchmark runner
- 任何 SkillsBench task 链路

一句话说清楚：

- 这次不是做“通用 stuck advisor”
- 这次只做“`run_swebench_with_minisweagent.py` 专用 stuck advisor”

## 最简单方案

### 核心思路

不要新建一套 `EXTERNAL_STUCK_JUDGE_*` 配置。

直接复用现有：

- `EXTERNAL_RETRY_ADVISOR_ENABLED`
- `EXTERNAL_RETRY_ADVISOR_MODEL`
- `EXTERNAL_RETRY_ADVISOR_MAX_TOKENS`

但把它的语义改成：

- 开启一个“外部 stuck 裁判”
- 在主 agent 的单次会话内部，满足停滞触发条件时调用
- 结果不是给下一次 retry 用，而是给**当前 attempt 的控制流**用
- 第三方 agent 返回三分支决策：
  - `No`
  - `Advice`
  - `RestartSession`

### 为什么这是最简单的

因为现有线路已经有：

- 环境变量入口
- runner CLI 参数
- 单独的 advisor 模块
- 模型、token 限制、API key 加载

最省事的办法不是再造一套配置，而是：

1. 保留脚本参数名不变
2. 保留 advisor 模块文件，改它的 prompt 和返回格式
3. 把调用点从 `attempt 结束后` 挪到 `agent 会话循环内部`
4. 让返回值支持 `No / Advice / RestartSession`

### 为什么这样不会影响其他数据集

因为只要我们遵守下面两个约束，就不会波及其他链路：

1. 新逻辑只能由 `run_swebench_with_minisweagent.py` 通过 agent kwargs 显式打开
2. `DefaultAgent` 里的新增逻辑默认必须是关闭的

这样即使 `DefaultAgent` 被别的地方复用，只要没有传入新的 advisor 开关，就不会生效。

## 具体改法

## 1. 保留入口脚本，最多只改注释

文件：

- `skill/scripts/experiments/run_swebench_single_eval.sh`

建议：

- 不改变量名
- 不改透传参数
- 只把变量注释改清楚，说明它现在用于“intra-attempt stuck judge”

这样实验脚本、命令行、已有批处理都不用改。

## 1.5 只通过 SWE-bench runner 显式下发新开关

文件：

- `skill/scripts/run_swebench_with_minisweagent.py`

最关键的边界控制是：

- 不依赖全局环境变量自动生效
- 不依赖 `DefaultAgent` 自己去猜当前是不是 SWE-bench
- 只允许这个 runner 显式把 stuck-advisor 配置写进 `agent_config`

也就是说，新增字段应该只在这里注入，例如：

- `external_retry_advisor_enabled`
- `external_retry_advisor_model`
- `external_retry_advisor_max_tokens`
- `external_retry_advisor_mode=stuck_judge`

如果不是从这个 runner 传进去，`DefaultAgent` 就按旧逻辑运行。

## 2. 在 runner 里停用旧的 inter-attempt 调用

文件：

- `skill/scripts/run_swebench_with_minisweagent.py`

当前旧调用点：

- `build_feedback_prompt(...)` 里调用 `request_retry_advice(...)`

最简单做法：

- 先把这里的 `request_retry_advice(...)` 调用去掉
- `build_feedback_prompt(...)` 恢复成只使用 eval failure summary

原因：

- 你现在要的是“卡住时插话”
- 不是“attempt 失败后给下一轮 retry 总结”
- 两者同时开会混淆语义，也更难分析效果

### 这里要额外保证一件事

`request_retry_advice(...)` 的旧调用去掉后，不能在别的 runner 上偷偷保留同名行为。

最简单做法：

- 只在 `run_swebench_with_minisweagent.py` 里删掉这条 inter-attempt 调用
- 不去改 `benchmark.py` 或其他 runner 的 feedback 语义

## 3. 把调用点改到 agent 主循环里

文件：

- `EET/mini-swe-agent/src/minisweagent/agents/default.py`
- `EET/mini-swe-agent/src/minisweagent/agents/experience_retrieval.py`

这是最关键的改动点。

说明：

- `skill/scripts/run_swebench_with_minisweagent.py` 实际实例化的是 `DefaultAgent` 或 `ExperienceRetrievalAgent`
- `ExperienceRetrievalAgent` 继承自 `DefaultAgent`
- 所以 stop-check 和会话循环的真实入口在 `minisweagent/agents/default.py`

当前这里已经有停滞相关信号：

- `progress_score`
- `should_stop`
- `zero_progress_streak`
- `should_stop_yes_streak`

但这些信号本身并不可靠，尤其：

- `should_stop`
- `should_stop_yes_streak`

它们只能算弱信号，适合当“是否要请第三方看一眼”的触发器，不适合直接决定 stuck。

最简单方案不是大改 stop policy，而是：

1. 每轮照常解析 `stop_check`
2. 当满足“疑似停滞”条件时，不直接停
3. 调一次 external advisor
4. 如果 advisor 返回 `No`，主 agent 继续
5. 如果 advisor 返回 `Advice`，把建议拼成下一轮 prompt，主 agent 继续
6. 如果 advisor 返回 `RestartSession`，保留工作区，但重建 chat session，再继续当前 attempt

### 更具体的代码落点

只需要在 `DefaultAgent` 增加下面几类内容：

1. 新配置字段
2. 新的运行时状态字段
3. 一个 `maybe_invoke_external_advisor(...)`
4. 一个 `restart_session_from_summary(...)`
5. 一个日志累积容器

但这些逻辑都必须受新开关保护：

- `external_retry_advisor_enabled == true`
- 且 `external_retry_advisor_mode == "stuck_judge"`

否则 `step()` 保持原状。

### 最小代码改法

#### A. 在 `AgentConfig` 里新增字段

文件：

- `EET/mini-swe-agent/src/minisweagent/agents/default.py`

新增：

- `external_retry_advisor_enabled: bool | str = False`
- `external_retry_advisor_model: str = ""`
- `external_retry_advisor_max_tokens: int | str = 180`
- `external_retry_advisor_mode: str = ""`

默认都关掉。

#### B. 在 `__init__` 里解析这些字段

新增内部状态：

- `self._external_retry_advisor_enabled`
- `self._external_retry_advisor_model`
- `self._external_retry_advisor_max_tokens`
- `self._external_retry_advisor_mode`
- `self.external_advisor_events`
- `self.last_external_advisor_episode`
- `self.external_advisor_invocation_count`

#### C. 在 `run()` 里记录 episode

现在 `DefaultAgent.run()` 没有显式 episode 计数器。

最简单方案是新增：

- `self._episode_index = 0`

每次成功走完一轮 `step()` 或处理一次异常后递增。

这样 external advisor 的日志就能知道它是在第几轮触发的。

#### D. 在 `step()` 里拦截 stop-check 终止点

当前逻辑是：

- `_record_stop_check_snapshot(...)`
- 返回 `stop_reason`
- 直接 `raise StopCheckTerminated(...)`

要改成：

1. 先拿到 stop-check snapshot
2. 计算混合触发信号
3. 如果没触发 advisor，就沿用旧逻辑
4. 如果触发 advisor：
   - 调 third-party advisor
   - 记录触发原因和结果
   - `No` -> 继续执行 `get_observation(response)`
   - `Advice` -> 执行完本轮 observation 后，往 `self.messages` 加 advice
   - `RestartSession` -> 执行完本轮 observation 后，重建 `self.messages`

注意：

- 这里不要在 `step()` 里直接 `raise StopCheckTerminated`
- 除非你额外保留一个 hard-stop 分支，但当前方案不需要

#### E. `RestartSession` 只重建消息，不重建环境

这一点必须明确：

- 不新建 `env`
- 不新建 attempt
- 不动 `workspace`
- 只重建 `self.messages`

这样才能确保它只是 SWE-bench 当前 attempt 内部的 session reset。

### 建议的最小触发条件

最简单可落地的是**混合触发**，不再单靠 `zero_progress_streak`：

- `zero_progress_streak >= N`
- 或 `重复命令率` 很高
- 或 `错误签名` 连续几轮不变
- 或 `总 token` 超过阈值且最近无新编辑

满足任一，就调一次第三方 agent。

### 这些触发信号怎么定义

#### 1. `zero_progress_streak`

前提：

- `STOP_CHECK_EARLY_STOP_ENABLED` 必须为 `true`

直接复用现有：

- `paper_turn_stopcheck_zero_progress_streak`

也就是连续若干轮 `progress_score == 0`。

#### 2. `重复命令率`

对最近 `K` 轮命令做轻量归一化，只看命令名，不看参数。

例如：

- `pytest tests/a.py -q`
- `pytest tests/b.py -q`

都记成：

- `pytest`

然后计算最近 `K` 轮里，重复命令名的占比。

最简单规则：

- 最近 4 到 6 轮里，超过 70% 的命令名和前几轮重复
- 且没有新的关键命令类型出现

就认为 `重复命令率` 高。

#### 3. `错误签名连续不变`

对每轮 terminal output 提取一个轻量 `error_signature`，例如：

- 首个 failed test id
- exception type
- traceback 最后 1 到 3 行
- 第一条 assertion mismatch

如果最近连续几轮 `error_signature` 相同，就认为卡在同一个错误上。

#### 4. `总 token 超阈值且最近无新编辑`

从当前 `Chat` 拿累计 token：

- `total_input_tokens`
- `total_output_tokens`
- `total_cache_tokens`

再结合“最近几轮是否有新编辑”。

最简单的“无新编辑”定义：

- 最近若干轮没有新增 patch
- 或工作区文件修改集合没有明显变化

如果 token 很高，但没有新编辑，就更像是上下文膨胀导致的 stuck，适合 `RestartSession`。

### “最近无新编辑” 在 SWE-bench 链路里怎么拿

最简单版不要去做复杂 git diff 分析。

先利用现有 attempt 工作区和命令输出，做一个保守定义：

- 最近 `K` 轮命令里没有出现明显编辑命令
  - `apply_patch`
  - `python`/`python3` 写文件
  - `cat > file`
  - `sed -i`
  - `perl -pi`
- 或最近 `K` 轮之后，工作区文件 mtime 集合没有变化

第一阶段建议只做“命令级是否编辑”的检测，够便宜也够稳。

### 触发原因必须写入日志

每次触发 external advisor 时，必须把触发原因记录下来。

最简单做法是在 `DefaultAgent` 内部维护一份 sidecar 日志，同时在 attempt metadata 里落一份摘要。

sidecar 日志建议由 `run_swebench_with_minisweagent.py` 在 `save_traj(...)` 旁边一起抄到 attempt 目录。

结构化记录例如：

```json
{
  "episode": 17,
  "triggered": true,
  "trigger_reasons": [
    "zero_progress_streak",
    "repeated_error_signature"
  ],
  "zero_progress_streak": 3,
  "should_stop_yes_streak": 1,
  "repeated_command_ratio": 0.83,
  "error_signature": "tests/test_api.py::test_x AssertionError",
  "total_input_tokens": 52341,
  "total_output_tokens": 6188,
  "total_cache_tokens": 110223,
  "recent_edit_detected": false
}
```

至少要记：

- `episode`
- `trigger_reasons`
- 触发时的各个原始信号值
- 最终 advisor 返回的是 `No` / `Advice` / `RestartSession`

### sidecar 日志具体放哪

最简单方案：

- `attempt_dir / "external_advisor_events.json"`

内容是一个 list，每次触发 append 一项。

然后 `run_swebench_with_minisweagent.py` 再把摘要放到：

- `traj_metadata["external_advisor"]`
- `attempt summary["external_advisor"]`

注意：

- 这里触发 advisor 后，**不要立刻终止**
- 按你现在需求，最简单版本里甚至**不需要 hard stop**
- stuck 时要么注入建议继续跑，要么重启 session 后继续跑

## 4. 复用 `swebench_retry_advisor.py`，把它改成三分支 stuck judge

文件：

- `skill/scripts/swebench_retry_advisor.py`

最简单做法不是新建文件，而是直接把这个模块扩展成 stuck-judge 模式。

建议新增一个函数，例如：

```python
request_stuck_advice(...)
```

输入包含：

- task / instance 基本信息
- 最近若干轮 agent response 摘要
- 最近若干轮 terminal output 摘要
- 最近的 `stop_check` 历史
- 当前 streak 计数
- 当前上下文 token 规模

### 最近若干轮 agent response 摘要怎么得到

不建议为摘要再额外调用一个模型。

最简单方案是**规则压缩**，直接从每轮 agent 的原始 JSON response 里抽字段。

每轮保留：

- `analysis` 前 1 到 2 句
- `plan` 前 1 到 2 句
- `commands` 的命令名列表
- `stop_check`

然后只取最近 `K` 轮，例如最近 4 到 6 轮。

示例结构：

```json
[
  {
    "episode": 12,
    "analysis": "Need to inspect failing parser branch.",
    "plan": "Read parser and run targeted test.",
    "commands": ["sed", "pytest"],
    "stop_check": {
      "progress_score": 1,
      "should_stop": "No"
    }
  }
]
```

也就是说，`agent response 摘要` 的获取方式是：

- 不额外做 LLM summarize
- 只做字段提取、截断、最近窗口裁剪

### 在 mini-swe-agent 里这些原始数据从哪来

直接从 `self.messages` 里取最近若干条 assistant message。

因为 `DefaultAgent.query()` 已经把模型回复塞进了：

- `self.messages.append({"role": "assistant", ...})`

所以规则是：

- 遍历最近若干条 assistant message
- 从 `content` 里提取：
  - `STOP_CHECK`
  - bash code block
  - code block 前面的自然语言 thought

不需要额外依赖外部日志文件。

### 最近若干轮 terminal output 摘要怎么得到

也不建议额外走模型摘要。

最简单方案是**规则抽取**：

- 优先提取 failed test names
- 提取 exception type
- 提取 traceback 最后几行
- 提取 `AssertionError` 所在行
- 提取命令退出码
- 提取高频错误模式
  - `ModuleNotFoundError`
  - `No such file`
  - `permission denied`
  - `command not found`

如果没有明显结构化错误，就保留每轮 terminal output 的最后 `N` 行，例如 20 行。

然后再做一个极轻量去重：

- 相邻两轮错误签名相同，就标记为 repeated
- 只把“新错误”和“持续错误”传给第三方 agent

示例结构：

```json
[
  {
    "episode": 12,
    "command_kinds": ["pytest"],
    "error_signature": "tests/test_api.py::test_x AssertionError",
    "tail": "E AssertionError: expected ... got ..."
  }
]
```

也就是说，`terminal output 摘要` 的获取方式是：

- 从每轮命令输出做规则提取
- 提取错误签名、失败测试、尾部关键行
- 不额外调用摘要模型

### 在 mini-swe-agent 里这些 terminal output 从哪来

直接从 `self.messages` 里取最近若干条 user observation message。

因为 `get_observation()` 里已经把 observation 通过：

- `self.add_message("user", observation)`

写回对话历史了。

所以不需要额外读 runner 日志，也不需要读 transcript 文件。

输出格式严格限制为三种之一：

```text
No
```

或者：

```text
Advice:
- You are likely stuck because ...
- Next inspect ...
- Avoid ...
```

或者：

```text
RestartSession:
- The current session is too bloated/noisy ...
- Rebuild context from current workspace state ...
```

### 为什么返回纯文本最简单

因为主循环现在就是 prompt string in / string out。

如果返回 JSON，还得加一个 judge parser。

最简单版可以约定：

- 返回值严格等于 `No`，表示不干预
- 以 `Advice:` 开头，表示注入当前会话
- 以 `RestartSession:` 开头，表示重建当前 attempt 的 chat session

这样主流程只要：

```python
if advice.strip() == "No":
    continue
elif advice.startswith("RestartSession:"):
    restart_chat_with_summary(...)
else:
    prompt = build_advice_injection_prompt(...)
```

## 5. `Advice` 注入到当前 prompt，不重开 chat

文件：

- `EET/mini-swe-agent/src/minisweagent/agents/default.py`

当前 `DefaultAgent` 通过 `self.messages` 保留历史消息。

所以最简单的继续当前会话方式是：

- 不新建 agent
- 不 break
- 不生成新的 attempt
- 直接往 `self.messages` 里加一条新的 `user` message，内容类似：

```text
External stuck review:
<advisor output>

Continue in the current environment and current session.
Do not restart from scratch.
Inspect existing edits first and choose the most targeted next step.

Current terminal state:
...
```

这样 advice 会作为同一会话里的下一条 user message 进入上下文。

## 6. `RestartSession` 的最简单处理方式

文件：

- `EET/mini-swe-agent/src/minisweagent/agents/default.py`

`RestartSession` 的目标不是新开 attempt，而是：

- 保留当前工作区修改
- 丢弃当前过长的 `self.messages` 历史
- 在同一 attempt 内重建最小消息历史
- 用精简摘要重新启动会话

### 为什么需要这个分支

有两类 stuck：

- 方向性 stuck
  - 适合 `Advice`
- 上下文性 stuck
  - 历史过长
  - 重复探索太多
  - prompt 已经被噪声淹没
  - 适合 `RestartSession`

### 最简单的重启方式

当 advisor 返回 `RestartSession:` 时：

1. 提取当前 attempt 的必要状态
2. 清空并重建 `self.messages`
3. 重新加入 system message
4. 构造一个新的首轮 user prompt
4. 继续主循环

新的首轮 prompt 只保留：

- 原始任务说明
- 当前 terminal state
- 当前工作区已经有改动这一事实
- 最近几轮失败/停滞的极简摘要
- advisor 给的 restart 建议

### 最小摘要内容

为了避免重启后完全失忆，建议最少带上：

- `original instruction`
- `latest terminal output`
- `recent stop_check history`
- `external advisor restart reason`
- `preserve existing workspace changes`

这是最小能工作的版本，不需要做复杂 transcript summarization。

## 7. 加一个 cooldown，避免每轮都调 advisor

这是最小必要防护，不然会重复调用。

建议在 `DefaultAgent` 里加两个简单状态：

- `last_external_advisor_episode`
- `external_advisor_invocation_count`

最简单规则：

- 两次 advisor 调用之间至少间隔 3 到 5 个 episode

否则会出现：

- 触发一次
- 注入建议或刚重启完 session
- 下一轮仍然 `progress_score=0`
- 又立刻再次触发

## 建议的数据流

### 触发前

主 agent 正常运行：

- LLM 输出 `analysis/plan/commands/stop_check`
- 执行 commands
- 累积 `zero_progress_streak` / `should_stop_yes_streak`

### 触发后

满足阈值时：

1. 组装 stuck review prompt
2. 调 `request_stuck_advice(...)`
3. 如果返回 `No`
   - 不做任何事
   - 下一轮仍然用正常 terminal output prompt
4. 如果返回 `Advice`
   - 把建议作为外部评审注入下一轮 prompt
   - 主 agent 在同一会话中继续
5. 如果返回 `RestartSession`
   - 新建 chat session
   - 用精简摘要重启当前 attempt
   - 工作区不变

### 触发后的日志也要记录

除了触发前信号，触发后还要记录：

- advisor 输入摘要的长度
- advisor 返回类别
- advisor 原始返回文本
- 是否执行了 `RestartSession`

最简单结构例如：

```json
{
  "episode": 17,
  "trigger_reasons": ["high_repeated_command_ratio"],
  "advisor_result": "RestartSession",
  "advisor_text": "RestartSession:\n- The current session is too noisy ...",
  "agent_response_summary_count": 5,
  "terminal_output_summary_count": 5,
  "session_restarted": true
}
```

## 只改 SWE-bench 链路的实施步骤

### 第 1 步

只改：

- `skill/scripts/run_swebench_with_minisweagent.py`

让它通过 `apply_agent_runtime_settings(...)` 把 stuck-advisor 字段塞进 `agent_config`。

不要改其他 runner。

### 第 2 步

只改：

- `EET/mini-swe-agent/src/minisweagent/agents/default.py`

在 `step()` 和 `run()` 里加 stuck-advisor 控制流。

不要改其他 agent 框架。

### 第 3 步

不直接改：

- `ExperienceRetrievalAgent` 的主循环

因为它继承 `DefaultAgent`，只要 `DefaultAgent` 支持，`eet-mini` 后端会自然继承这个行为。

### 第 4 步

只改：

- `skill/scripts/swebench_retry_advisor.py`

把它从 retry advisor 扩成 stuck judge helper。

### 第 5 步

把新增 metadata 只写回当前 SWE-bench attempt 产物：

- `attempt_n/traj.json`
- `attempt_n/external_advisor_events.json`
- `task_summary.json`

不要写入任何全局 benchmark 聚合逻辑，除非后面明确需要。

## 最小需要改的文件

### 必改

- `skill/scripts/swebench_retry_advisor.py`
  - 增加 stuck-judge 调用函数
  - prompt 改成判断 stuck / 输出 `No` / `Advice` / `RestartSession`

- `EET/mini-swe-agent/src/minisweagent/agents/default.py`
  - 在主循环里加 trigger
  - 记录触发原因和触发时信号值
  - 调 advisor
  - 处理 `Advice` 注入当前 prompt
  - 处理 `RestartSession` 重建 `self.messages`
  - 加 cooldown
  - 不再在触发阈值时直接 break

- `skill/scripts/run_swebench_with_minisweagent.py`
  - 把 `DefaultAgent` 里新增的 advisor 日志和元数据写进 attempt 产物
  - 把 stuck-advisor kwargs 只注入当前 SWE-bench runner 的 `agent_config`

### 建议改

- `skill/scripts/run_swebench_with_minisweagent.py`
  - 去掉 `build_feedback_prompt(...)` 里的旧 advisor 调用
  - 避免同一个开关同时做“retry advisor”和“stuck judge”两种事

- `skill/scripts/experiments/run_swebench_single_eval.sh`
  - 只改注释，说明语义已变

## 不建议这次做的事

为了保持“最简单方案”，这次不建议做下面这些：

- 不新建一套 `EXTERNAL_STUCK_JUDGE_*` 环境变量
- 不引入独立 JSON parser 给 advisor
- 不让 advisor 直接决定终止 attempt
- 不把这个逻辑放到 `run_skillsbench_with_early_stop.py`
- 不做复杂的 transcript 压缩或结构化摘要服务

这里的摘要都用规则压缩，不额外引入新的摘要模型。

## 一个非常直接的实现约定

### advisor prompt 约定

system prompt：

- 你是一个 stuck judge
- 如果当前主 agent 还没有明显 stuck，只回答 `No`
- 如果已经 stuck 但适合继续当前会话，回答 `Advice:` 并给最多 3 条简短建议
- 如果已经 stuck 且当前上下文过长不适合继续当前会话，回答 `RestartSession:` 并给最多 3 条简短建议
- 不要输出代码
- 不要输出 patch
- 不要输出文件精确修改内容

### 主流程判定约定

- 返回值为空：当作 `No`
- 返回值精确等于 `No`：当作未 stuck
- 以 `Advice:` 开头：当作 stuck advice
- 以 `RestartSession:` 开头：当作 session restart 建议

这能把控制逻辑压到最简单。

## 推荐的最小 advisor 输入 payload

最简单可用的 payload 至少包含：

- `instance_id`
- `episode`
- `trigger_reasons`
- `zero_progress_streak`
- `should_stop_yes_streak`
- `repeated_command_ratio`
- `error_signature`
- `total_input_tokens`
- `total_output_tokens`
- `total_cache_tokens`
- `recent_edit_detected`
- `recent_agent_response_summaries`
- `recent_terminal_output_summaries`

这样第三方 agent 判断时，不会只看到模糊的 `stop_check`，而能看到更具体的 stuck 证据。

## 风险

### 1. 变量名会误导

`EXTERNAL_RETRY_ADVISOR_*` 名字和实际用途不一致了。

但这是“最简单方案”可接受的代价。后面如果稳定，再重命名。

### 2. advisor 可能重复给泛泛建议

所以必须加 cooldown。

### 3. `RestartSession` 需要最小状态摘要

如果摘要太弱，重启后会丢关键信息。

但最简单版只要保留任务说明、terminal state、最近停滞原因和“保留已有修改”提示，通常就够了。

### 4. 主 agent 可能无视 advice

这是可接受的。你的需求是“给建议并继续”，不是“强制遵从”。

### 5. 规则摘要可能丢细节

这是最简单方案的代价。

但对“是否 stuck”这个判断来说，通常不需要完整 transcript，规则提取的关键信号已经够用。

## 建议的最小版本验收标准

1. `EXTERNAL_RETRY_ADVISOR_ENABLED=false`
   - 行为与现在基本一致

2. `EXTERNAL_RETRY_ADVISOR_ENABLED=true`
   - agent 在连续低进展后触发一次 advisor
   - 如果 advisor 返回 `No`，主会话继续，无额外干预
   - 如果 advisor 返回 `Advice`，建议被注入同一会话，且不新开 attempt
   - 如果 advisor 返回 `RestartSession`，`self.messages` 被重建，但 attempt 和工作区保持不变

3. `task_summary.json` 或 attempt metadata 里能看到：
   - advisor 是否触发
   - 触发原因是什么
   - advisor 调用了几次
   - 最后一次返回是 `No` / `Advice` / `RestartSession`

## 一句话结论

最简单的改法是：

- **保留 `EXTERNAL_RETRY_ADVISOR_*` 入口不变**
- **停用它在 inter-attempt feedback 里的旧用途**
- **把它挪到 `minisweagent DefaultAgent.step()/run()` 这条会话循环里，作为 intra-attempt stuck sidecar**
- **返回 `No` 就忽略，返回 `Advice` 就往 `self.messages` 追加 advice，返回 `RestartSession` 就重建 `self.messages` 后继续当前 attempt**
