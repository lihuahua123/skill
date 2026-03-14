# PinchBench 多轮纠错实验设计

## 研究目标

本研究基于 PinchBench/OpenClaw，系统评估真实 agent 在“失败后多轮纠错”场景中的行为表现。研究重点不只是证明多轮反馈可能带来提升，而是定量回答以下问题：

- 额外重试轮次的边际收益有多大
- 成功通常发生在第几轮，其分布如何
- token 成本 / 金钱成本 与成功率之间的 tradeoff 是什么
- 不同 feedback policy 与 context policy 如何影响收敛效率

## 现有项目基础

当前仓库已经具备可直接复用的多轮 baseline，并非纯单轮 benchmark。

- [`scripts/benchmark.py`](/root/skill/scripts/benchmark.py) 中已经有 `_build_iteration_feedback`，会把 validator 的 score、breakdown、notes 和 grading criteria 组织成下一轮输入。
- [`scripts/benchmark.py`](/root/skill/scripts/benchmark.py) 中已经实现了同一 workspace、同一 session 下的 in-place retry。
- [`scripts/benchmark.py`](/root/skill/scripts/benchmark.py) 已经把 `attempts`、`usage`、`usage_per_round`、`grading` 等信息写入结果 JSON。
- [`README.md`](/root/skill/README.md) 已经暴露 `--max-task-attempts` 参数。

这意味着 RQ1、RQ2、RQ3 的 baseline 数据路径已经基本存在，后续主要需要补的是：

- feedback policy 的可配置化
- context policy 的可配置化
- 更细的 instrumentation 和分析脚本

## 研究问题

建议最终聚焦在 4 个主 RQ 上。

### RQ1

多轮 validator feedback 的边际收益是多少？

### RQ2

成功通常需要多少轮迭代？成功轮次的分布是什么？

### RQ3

token / cost 与 success 之间的 tradeoff 是什么？

### RQ4

feedback policy 与 context policy 如何影响收敛？

“任务复杂度如何影响迭代轮数”建议作为分层分析或 moderator，而不是单独作为主 RQ。否则主线会变散。

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

### RQ1：多轮反馈的边际收益是多少

目标：

- 衡量每增加一轮重试究竟带来多少 success 增益

实验：

- 固定一种 feedback strategy，初期可用当前默认策略或 `error-localized`
- 扫描 `max_task_attempts = 1, 2, 3, 4, 5, 6`
- 对每个模型、每个任务进行多次重复运行

指标：

- `success@k`
- `delta success(k) = success@k - success@(k-1)`
- 每增加一轮带来的新增 token
- 每增加一轮带来的新增 cost

回答的问题：

- 多轮相对单轮提升多少
- 收益主要集中在哪几轮
- 从第几轮开始收益趋近于 0

### RQ2：成功通常需要多少轮 / 成功分布是什么

目标：

- 刻画成功通常发生在第几轮

实验：

- 固定一种 feedback strategy
- 设置较高上限，例如 `max_task_attempts = 6` 或 `8`
- 记录每个成功样本的首次成功轮次
- 如果要做更严谨分析，可将失败样本按 censored case 处理

指标：

- 首次成功轮次分布
- median attempts to success
- `P(success by round k)`
- 按模型或任务类别分层后的分布差异

回答的问题：

- 成功通常集中在哪一轮
- 后续轮次是在补救少量难例，还是基本无效

### RQ3：token cost vs success 的 tradeoff 是什么

目标：

- 量化额外 success 是否值得付出对应 token / cost

实验：

- 复用 `max_task_attempts = 1..k` 的扫描结果
- 比较不同模型在相同 attempt budget 下的表现
- 绘制 cost-success / token-success 曲线

指标：

- success vs cumulative tokens
- success vs cumulative USD cost
- 每增加 1% success 所需 token / cost
- score per 1K tokens
- success per dollar

回答的问题：

- 最划算的重试轮次上限是多少
- 强模型是否更不依赖多轮
- 不同模型是否处于不同的 Pareto frontier

### RQ4：feedback quality 如何影响收敛

目标：

- 评估不同反馈粒度对收敛行为的影响

实验：

- 固定 `max_task_attempts`，例如 `5`
- 比较三种 `feedback_policy`：
  - `vague`
  - `error-localized`
  - `actionable-path`
- 其他实验条件保持一致
- 可进一步加入 feedback formatting 维度：
  - `full-refresh`
  - `stable-prefix`

指标：

- 最终 success rate
- 首次成功轮次
- 平均累计 token / cost
- 每轮 improvement rate
- failure mode 分布

回答的问题：

- 更具体的反馈是否更有效
- 更高质量的反馈是否值得更高成本
- cache-friendly 改写是否能在降低 token 的同时保持类似 success

## 扩展实验：Append vs Rollback

这一部分建议作为独立扩展实验，而不是混入前四个 RQ。

实验：

- 固定一种 feedback policy
- 比较：
  - `append`
  - `fresh-session`
  - `rollback`
- 严格控制 workspace 状态是否保留或恢复

指标：

- 最终 success
- attempts to success
- 累计 token / cost
- 后期轮次退化
- transcript 长度增长

回答的问题：

- 上下文污染是否是真实存在的现象
- rollback 是否能改善成本-性能边界

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

## 需要修改的代码范围

当前先不改代码，这里只总结后续实现范围。

### 1. Benchmark Runner

文件：

- [`scripts/benchmark.py`](/root/skill/scripts/benchmark.py)

需要修改：

- 将 `_build_iteration_feedback` 抽象成可配置的 `feedback_policy`
- 增加 `context_policy`
- 增加相关 CLI 参数
- 在结果 JSON 中记录 policy 元数据和 stop reason
- 支持 cache-friendly 的 `stable-prefix` feedback formatting

### 2. Agent Execution Layer

文件：

- [`scripts/lib_agent.py`](/root/skill/scripts/lib_agent.py)

需要修改：

- 支持新 session 下的重试执行，同时复用 workspace
- 为 rollback 实验提供 workspace snapshot / restore
- 更明确地记录 session / workspace 生命周期信息

### 3. Analysis Pipeline

需要新增或补充：

- 独立分析脚本或 notebook

需要实现：

- `success@k`
- marginal gain by attempt
- attempts-to-success 分布
- token-success / cost-success 曲线
- feedback/context policy 对比
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
- `--snapshot-workspace`

## 建议补充的记录字段

当前结果已经包含 attempts 和 usage，但为了后续分析，建议增加：

- `feedback_policy`
- `feedback_format`
- `context_policy`
- `stop_reason`
- `first_success_attempt`
- `cumulative_usage_by_attempt`
- `unresolved_criteria_count`
- feedback 文本长度或 token 数
- `workspace_restored`
- `session_reset`

## 建议输出的结果形式

### 表格

- 单轮 vs 多轮的整体 success / token / cost 对比
- feedback policy 对比表
- append vs rollback 对比表

### 图表

- `success@k` 曲线
- marginal gain by attempt
- attempts-to-success 直方图或 CDF
- cumulative token vs success
- cumulative cost vs success
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

1. 先复现当前 append baseline，并做 attempt budget 扫描。
2. 增加可配置的 `feedback_policy`。
3. 增加 cache-friendly 的 `stable-prefix` feedback formatting。
4. 完成 RQ1-RQ4 的主实验。
5. 最后实现并评估 `append` vs `rollback`。

## 一句话总结

这项研究的主要贡献应表述为：在真实 tool-using agent benchmark 上，系统刻画 validator-driven iterative repair 的收益边界、成本边界以及收敛机制，而不是简单证明多轮重试可能带来提升。
