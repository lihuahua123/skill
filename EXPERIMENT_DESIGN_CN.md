# PinchBench 多轮纠错实验设计

## 研究目标

本研究基于 PinchBench/OpenClaw，系统评估真实 agent 在“失败后多轮纠错”场景中的行为表现。研究重点不是提出新的 agent 方法，也不是单纯追求更高 success，而是在既有 validator-driven retry 框架之上，系统回答以下 token-efficiency 问题：

- 在尽量不损失 success 的前提下，多轮反馈究竟额外消耗了多少 token
- 哪些失败主要来自历史堆积或状态残留，从而造成可避免的 token 浪费
- 在固定成功率目标或固定预算目标下，哪类 stopping rule 最能节省 token
- 哪类 feedback / context 配置具有最佳 token-efficiency

## 论文定位

这项工作应明确定位为一篇 empirical study，而不是方法论文。

核心定位：

- 研究对象是真实 tool-using agent 在 validator-driven retry 下的成本与收益行为
- 核心贡献是 measurement、ablation 和 token-efficiency characterization
- 目标是找出更省 token 的重试配置，而不是提出新的训练方法或通用 agent 架构

非目标：

- 不主张“首次提出多轮反馈”
- 不主张“首次提出 fresh-session / rollback”
- 不主张“学习一个全新的 agent policy”
- 不把 cache-friendly formatting 包装成通用方法创新

更合适的 claim 是：

- 在真实 tool-using agent benchmark 上，系统刻画 validator-driven retries 的 success-cost frontier
- 区分哪些额外 token 是有效投入，哪些只是由历史污染或冗余反馈造成的浪费
- 给出在不同预算目标下更合理的 retry 配置与 stopping 经验规律

建议全文都坚持下面这个叙述顺序：

1. `token efficiency` 是主目标
2. `success` 是约束条件或比较基线
3. 重点不是“谁效果最好”，而是“谁在相近效果下最省 token”

## 现有项目基础

当前仓库已经具备可直接复用的多轮 baseline，并非纯单轮 benchmark。

- [`scripts/benchmark.py`](/root/skill/scripts/benchmark.py) 中已经有 `_build_iteration_feedback`，会把 validator 的 score、breakdown、notes 和 grading criteria 组织成下一轮输入。
- [`scripts/benchmark.py`](/root/skill/scripts/benchmark.py) 中已经实现了同一 workspace、同一 session 下的 in-place retry。
- [`scripts/benchmark.py`](/root/skill/scripts/benchmark.py) 已经把 `attempts`、`usage`、`usage_per_round`、`grading` 等信息写入结果 JSON。
- [`README.md`](/root/skill/README.md) 已经暴露 `--max-task-attempts` 参数。

这意味着新的 RQ1-RQ4 所需 baseline 数据路径已经基本存在，后续主要需要补的是：

- feedback policy 的可配置化
- context policy 的可配置化
- 更细的 instrumentation 和分析脚本

## 研究问题

建议最终聚焦在 4 个主 RQ 上。

### RQ1

多轮 validator feedback 的 token-efficiency 曲线与失效点是什么？

这一问题将“边际收益”和“token 开销”合并分析，关注 success 如何随轮次增长、token 如何累积，以及从第几轮开始额外 token 基本不再值得。

### RQ2

多轮反馈中的 token 浪费主要来自哪里？

具体区分三类可能来源：

- 对话历史污染
- 工作区状态污染
- feedback 信号不足或方向错误

### RQ3

在固定预算或固定成功率目标下，哪类 stopping rule 最省 token？

重点不再是提出新 policy，而是系统比较不同停止规则在 success 与 token/cost 上的经验 tradeoff。

### RQ4

哪类 feedback / context 配置最省 token？

该问题关注的不是“更多 feedback 是否更好”，而是：

- 哪些反馈字段真正带来额外 success
- 哪些上下文历史只是 token 噪音
- 哪些压缩或稳定化策略能在降本时保持相近 success

“任务复杂度如何影响迭代轮数”建议作为分层分析或 moderator，而不是单独作为主 RQ。更适合作为 RQ1 与 RQ3 的解释变量。

## Feedback Policy 设计

需要将当前写死的 retry prompt 抽象成可配置的 `feedback_policy`。

### `vague`

含义：

- 只告诉 agent 上一轮没有通过
- 要求其继续修改并重试

作用：

- 作为弱反馈 baseline

### `error-localized`

含义：

- 指出哪些评分项失败
- 给出 validator notes
- 但不直接告诉 agent 该怎么修

作用：

- 用于评估“指出错误位置”本身的价值

### `actionable-path`

含义：

- 不仅指出哪里错
- 还明确给出下一步修复建议或操作路径

作用：

- 用于评估更高质量反馈是否能够减少轮次并提高 success

## Cache-Friendly Feedback 设计

如果目标是尽可能提高 prompt cache 命中率，则反馈模板不应每轮重写整段内容，而应采用“稳定前缀 + 动态后缀”的结构。

### 稳定前缀

稳定前缀应包含：

- task ID
- 原始 grading criteria
- 通用 retry 规则
- 当前 feedback policy 的固定说明

这一部分在同一任务的所有尝试中都保持完全一致。

### 动态后缀

动态后缀只应包含：

- 最新 attempt 编号
- 最新 score
- 当前未解决的问题
- 简短的 notes 或 repair steps

这部分应尽量简短，并放在 prompt 尾部。

### 设计原则

- 不要在每轮重复完整历史
- 不要重复已通过的评分项
- 每轮保持字段和顺序稳定
- 将变化内容放在最后
- 优先使用结构化字段，而不是长篇自然语言总结

在这个框架下，后续可形成两种 feedback formatting 变体：

- `full-refresh`：每轮重写完整反馈
- `stable-prefix`：固定前缀 + 小型动态后缀

其中 `stable-prefix` 是更适合做 cache-friendly 实验的设计。

## Context Policy 设计

系统应支持多种 `context_policy`。

### `append`

含义：

- 保持同一 session
- 保持同一 workspace
- 将新的 feedback 追加到已有上下文中继续执行

作用：

- 当前实现的 baseline

### `fresh-session`

含义：

- 新开一个 session
- 保留 workspace 状态
- 注入精简后的 retry prompt 或 feedback summary

作用：

- 用于区分“对话历史污染”和“文件状态污染”

### `rollback`

含义：

- 将 workspace 回滚到失败前快照
- 使用新的 session
- 仅注入纠错提示

作用：

- 用于验证状态回滚是否能同时提高 success 并降低成本

关键约束：

- rollback 必须同时控制 session 历史和 workspace 状态；如果只重置 session，不恢复文件状态，就会把实验变量混淆掉

## 各研究问题对应的实验设计

### RQ1：多轮反馈的 token-efficiency 曲线与失效点是什么

目标：

- 系统刻画 success 随轮次增长、token 随轮次累积的联合动力学
- 判断 token 投入最划算的轮次集中在哪几轮
- 识别何时出现“额外 token 基本不再值得”的失效点

实验：

- 固定一种 feedback policy，初期可用当前默认策略或 `error-localized`
- 扫描 `max_task_attempts = 1, 2, 3, 4, 5, 6`
- 对每个模型、每个任务进行多次重复运行
- 设置较高上限时，记录每个成功样本的首次成功轮次
- 对未成功样本明确记录“在当前最大重试轮数内仍未成功”，以便与“已观察到首次成功轮次”的样本区分开来

指标：

- 累计 token by round
- `success@k`
- `delta success(k) = success@k - success@(k-1)`
- `delta tokens(k)`
- 每增加 1% success 所需 token / cost
- 首次成功轮次分布
- median attempts to success
- `P(success by round k)`
- 后期轮次 failure rate 是否上升

回答的问题：

- 多轮相对单轮究竟多花了多少 token，换来了多少 success
- 最划算的增益主要集中在哪几轮
- 后续轮次是在补救少量难例，还是已经基本只增加成本
- 是否存在“继续 retry 主要是在烧 token”的失效点

### RQ2：多轮反馈中的 token 浪费主要来自哪里

目标：

- 区分额外 token 开销究竟主要来自历史污染、状态污染，还是反馈不足
- 将“context pollution”从笼统现象变成可验证、可分解的浪费来源分析

实验：

- 固定一种 feedback policy
- 比较三种 `context_policy`：
  - `append`
  - `fresh-session`
  - `rollback`
- 严格控制 workspace 状态是否保留或恢复
- 必要时增加“精简 feedback summary”变体，以控制 prompt 长度因素

指标：

- 最终 success
- attempts to success
- 累计 token / cost
- 相对 `append` 节省的 token 比例
- transcript 长度增长
- 后期轮次退化
- 不同 policy 下的 failure mode 分布

回答的问题：

- 对话历史污染是否真实存在，并且会不会系统性浪费 token
- 工作区残留状态是否会导致无效重试
- rollback 是否能在保持 success 的同时减少累计 token
- 若 `append`、`fresh-session`、`rollback` 差异不大，是否说明主要浪费不在上下文管理

### RQ3：在固定预算或固定成功率目标下，哪类 stopping rule 最省 token

目标：

- 比较不同停止规则的 token-efficiency
- 判断“下一轮是否值得继续”在经验上是否可预测
- 在固定预算下提升 success，或在相近 success 下显著降本

实验：

- 比较一组简单、可解释的 stopping rules，而不是复杂策略学习：
  - 固定 `max_task_attempts = 3`
  - 固定 `max_task_attempts = 5`
  - 当 score 连续两轮不提升时停止
  - 当 unresolved criteria 数量不再下降时停止
  - 当单位 token 带来的 improvement 低于阈值时停止
- 可选地做一个轻量 oracle-style 分析：
  - 用前 1 至 2 轮的观测信号估计下一轮成功概率
  - 但这部分只作为分析工具，不作为本文主方法
- 可使用的观测信号包括：
  - validator score 与 score delta
  - unresolved criteria 数量
  - feedback 长度
  - 本轮 token 增量
  - 历史是否已出现 improvement

指标：

- success vs cumulative tokens
- success vs cumulative USD cost
- 每增加 1% success 所需 token / cost
- score per 1K tokens
- success per dollar
- 达到目标 success 所需的最少 token
- stop-too-early / stop-too-late rate
- 达到目标 success 所需的平均 token / cost

回答的问题：

- 简单 stopping rules 能否在相近 success 下显著少用 token
- 哪类任务适合继续迭代，哪类任务应尽早停止
- 为多大比例的任务，额外一轮其实只是纯成本

### RQ4：哪类 feedback / context 配置最省 token

目标：

- 评估哪些 feedback 信息真正必要
- 评估哪些上下文历史只是 token 噪音
- 研究不同 feedback/context 配置的 success-cost frontier

实验：

- 固定 `max_task_attempts`，例如 `5`
- 比较三种 `feedback_policy`：
  - `vague`
  - `error-localized`
  - `actionable-path`
- 在每种 policy 下再比较两种 formatting：
  - `full-refresh`
  - `stable-prefix`
- 如有余力，可进一步加入“仅保留未通过项”或“仅保留最新 failure summary”变体

指标：

- 最终 success rate
- 首次成功轮次
- 平均累计 token / cost
- 每轮 improvement rate
- feedback 文本长度 / token 数
- cache 命中相关 proxy
- success per 1K tokens
- success per dollar

回答的问题：

- 更具体的反馈是否真的更有效，还是主要只是更贵
- 哪些反馈字段是收敛所必需的
- cache-friendly 改写是否能在降低 token 的同时保持类似 success
- 哪一组 feedback/context 配置处在更优的 Pareto frontier

## 核心指标优先级

如果论文需要明确主指标与次指标，建议按下面顺序写：

主指标：

- success per 1K tokens
- success per dollar
- 达到目标 success 所需的平均 token
- 每增加 1% success 所需 token

次指标：

- 最终 success rate
- `success@k`
- 首次成功轮次
- 平均 attempt 数

解释性指标：

- transcript 长度增长
- feedback 文本长度 / token 数
- unresolved criteria 数量变化
- stop-too-early / stop-too-late rate

## 任务复杂度分析

任务复杂度建议作为分层分析变量，而不是独立主 RQ。

可用的复杂度 proxy 包括：

- `timeout_seconds`
- grading criteria 数量
- workspace fixture 文件数
- 是否使用 `llm_judge`
- task category
- 实证上的 `pass@1` 难度

这些大多可以直接从任务 frontmatter 和任务结构中提取，不一定需要人工标注。

## 最小可执行实验矩阵

为了避免实验设计过散，建议先跑下面这 4 组最小实验。每组实验只服务一个主 RQ，且尽量复用同一套日志。

### 实验 E1：Attempt Budget 扫描

对应 RQ：

- RQ1

固定条件：

- `feedback_policy = error-localized`
- `context_policy = append`
- `feedback_format = full-refresh`
- `stop_rule = fixed`

扫描变量：

- `max_task_attempts = 1, 2, 3, 4, 5, 6`

核心输出：

- `success@k`
- `delta success(k)`
- `delta tokens(k)`
- 首次成功轮次分布
- 每增加 1% success 所需 token

用途：

- 先回答“多轮 retry 是否值得，以及从第几轮开始不值”
- 为后续 stopping rule 设计提供 baseline

### 实验 E2：Context Policy 对比

对应 RQ：

- RQ2

固定条件：

- `feedback_policy = error-localized`
- `feedback_format = full-refresh`
- `max_task_attempts = 5`
- `stop_rule = fixed`

扫描变量：

- `context_policy = append`
- `context_policy = fresh-session`
- `context_policy = rollback`

核心输出：

- 相对 `append` 的 token 节省比例
- matched-success token savings
- 不同 context policy 的 success-cost frontier

用途：

- 判断主要 token 浪费是否来自历史污染或状态污染
- 明确 `fresh-session` 和 `rollback` 是否值得额外工程成本

### 实验 E3：Stopping Rule 对比

对应 RQ：

- RQ3

固定条件：

- `feedback_policy = error-localized`
- `context_policy` 先固定为 E2 中更划算的一种
- `feedback_format = full-refresh`
- `max_task_attempts = 5` 或 `6`

扫描变量：

- `stop_rule = fixed-3`
- `stop_rule = fixed-5`
- `stop_rule = score-stall`
- `stop_rule = unresolved-stall`
- `stop_rule = low-return`

核心输出：

- 不同 stopping rule 的 success per 1K tokens
- 达到目标 success 所需的平均 token
- stop-too-early / stop-too-late rate

用途：

- 判断简单启发式 stopping rule 是否已经足够省 token
- 避免把论文做成复杂 policy learning

### 实验 E4：Feedback / Format 对比

对应 RQ：

- RQ4

固定条件：

- `context_policy` 先固定为 E2 中更划算的一种
- `stop_rule` 先固定为 E3 中更划算的一种
- `max_task_attempts = 5`

扫描变量：

- `feedback_policy = vague`
- `feedback_policy = error-localized`
- `feedback_policy = actionable-path`
- `feedback_format = full-refresh`
- `feedback_format = stable-prefix`

可选扩展：

- unresolved-only feedback
- latest-failure-summary only

核心输出：

- success per 1K tokens
- success per dollar
- feedback token 长度与最终 success 的关系
- token saved at matched success

用途：

- 找出最省 token 的 feedback / context 配置
- 支撑论文的 token-efficiency 主结论

## 实验与日志字段映射

下面这部分可以直接作为 instrumentation checklist。

### E1 必需日志字段

- `task_id`
- `model`
- `attempt_index`
- `max_task_attempts`
- `success`
- `first_success_attempt`
- `prompt_tokens_by_attempt`
- `completion_tokens_by_attempt`
- `cumulative_usage_by_attempt`
- `score_by_attempt`
- `unresolved_criteria_count`
- `stop_reason`
- `success_within_budget`

### E2 必需日志字段

- E1 的全部字段
- `context_policy`
- `session_reset`
- `workspace_restored`
- `workspace_changed_since_last_attempt`
- transcript 总长度与每轮新增长度
- retry prompt 的稳定前缀长度和动态后缀长度

### E3 必需日志字段

- E1 的全部字段
- `stop_rule`
- `stop_rule_threshold`
- 每轮是否触发停止规则
- 触发停止规则的依据
- score delta by attempt
- token delta by attempt

### E4 必需日志字段

- E1 的全部字段
- `feedback_policy`
- `feedback_format`
- feedback 文本长度或 token 数
- feedback 的结构化字段摘要
- prompt cache 命中相关 proxy
- retry prompt 的稳定前缀长度和动态后缀长度

### 所有实验共享的建议字段

- `run_id`
- `seed` 或 temperature 相关配置
- `task_category`
- `timeout_seconds`
- grading criteria 数量
- 是否使用 `llm_judge`

## 需要修改的代码范围

当前先不改代码，这里只总结后续实现范围。

### 1. Benchmark Runner

文件：

- [`scripts/benchmark.py`](/root/skill/scripts/benchmark.py)

需要修改：

- 将 `_build_iteration_feedback` 抽象成可配置的 `feedback_policy`
- 增加 `context_policy`
- 增加 `stop_rule`，支持固定轮次和简单启发式停止规则
- 增加相关 CLI 参数
- 在结果 JSON 中记录 policy 元数据和 stop reason
- 支持 cache-friendly 的 `stable-prefix` feedback formatting
- 记录每一轮 feedback prompt 的长度、token 数和结构化字段
- 记录每一轮是否命中停止规则，以及触发停止的依据

### 2. Agent Execution Layer

文件：

- [`scripts/lib_agent.py`](/root/skill/scripts/lib_agent.py)

需要修改：

- 支持新 session 下的重试执行，同时复用 workspace
- 为 rollback 实验提供 workspace snapshot / restore
- 更明确地记录 session / workspace 生命周期信息
- 记录每一轮执行前后的 workspace 是否变化、是否恢复，以便区分“状态污染”与“纯历史污染”

### 3. Analysis Pipeline

需要新增或补充：

- 独立分析脚本或 notebook

需要实现：

- `success@k`
- marginal gain by attempt
- attempts-to-success 分布
- token-success / cost-success 曲线
- matched-success token savings 分析
- token saved per avoided retry
- feedback/context policy 对比
- stopping rule 对比
- 按目标 success 反推最小 token 预算
- 按任务复杂度 proxy 分层分析

### 4. Task Metadata

可选修改：

- 在 task frontmatter 中增加 complexity tag

替代方案：

- 完全使用现有 metadata 和经验难度自动构造复杂度 proxy

## 建议新增的配置项

建议未来在 CLI 中增加：

- `--feedback-policy`
- `--feedback-format`
- `--context-policy`
- `--max-task-attempts`
- `--stop-rule`
- `--stop-threshold`
- `--snapshot-workspace`

## 建议补充的记录字段

当前结果已经包含 attempts 和 usage，但为了后续分析，建议增加：

- `feedback_policy`
- `feedback_format`
- `context_policy`
- `stop_rule`
- `stop_rule_threshold`
- `stop_reason`
- `first_success_attempt`
- `success_within_budget`
- `cumulative_usage_by_attempt`
- `prompt_tokens_by_attempt`
- `completion_tokens_by_attempt`
- `unresolved_criteria_count`
- feedback 文本长度或 token 数
- retry prompt 的稳定前缀长度和动态后缀长度
- transcript 总长度与每轮新增长度
- `workspace_restored`
- `session_reset`
- `workspace_changed_since_last_attempt`

## 建议输出的结果形式

### 表格

- 单轮 vs 多轮的整体 success / token / cost 对比
- 相近 success 下的 token 节省对比
- feedback policy 对比表
- append vs rollback 对比表
- stopping rule 对比表
- 不同目标 success 下的最小 token 预算表

### 图表

- `success@k` 曲线
- marginal gain by attempt
- attempts-to-success 直方图或 CDF
- cumulative token vs success
- cumulative cost vs success
- success-cost Pareto frontier
- token saved at matched success
- stop rule 的 budget-success 曲线
- complexity-stratified success-cost 曲线
- append vs rollback 对比图

## Threats to Validity

实验设计中需要明确说明以下局限性：

- LLM 输出存在随机性，因此需要重复运行
- judge-based grading 可能引入偏差和方差
- prompt cache 命中依赖底层 provider 实现，未必完全可观测
- 如果 rollback 只控制 session 不控制 workspace，会导致实验混淆
- 静态复杂度 proxy 不一定能完全反映真实认知复杂度

## 推荐实施顺序

建议按照以下顺序推进：

1. 先复现当前 `append` baseline，并完成 RQ1 所需的 attempt budget 扫描。
2. 增加可配置的 `feedback_policy` 与 `feedback_format`，支撑 RQ4。
3. 增加 `fresh-session` 与 `rollback`，完成 RQ2 的 failure decomposition。
4. 补充 stop reason、first success attempt、unresolved criteria 等 instrumentation。
5. 比较简单 stopping rules，在不引入复杂方法学习的前提下完成 RQ3。

## 一句话总结

这项研究的主要贡献应表述为：在真实 tool-using agent benchmark 上，系统测量 validator-driven iterative repair 的 token-efficiency、浪费来源与 success-cost frontier，并给出在尽量不损失 success 的前提下更省 token 的 retry 配置经验规律，而不是提出新的 agent 方法。
