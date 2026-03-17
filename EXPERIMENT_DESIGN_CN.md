# PinchBench 多轮纠错实验设计

## 研究目标

本研究聚焦 PinchBench/OpenClaw 中 validator-driven retries 的 token-efficiency，核心问题只保留三类：

- 额外 retry budget 能带来多少真实收益
- 什么时候继续 retry 已经不划算
- 哪类 feedback / stopping 配置在相近 success 下最省 token

全文定位为 empirical study，而不是新 agent 方法。

## 研究问题

### RQ1

额外 validator-feedback 重试的边际收益是什么？

### RQ3

在固定预算或固定目标 success 下，哪类 stopping rule 最省 token？

### RQ4

哪类 feedback policy 与 feedback format 的 success-cost tradeoff 最好？

任务复杂度只作为分层变量，不单独作为主 RQ。

## 现有项目基础

仓库已经具备 append 风格的多轮 retry baseline。

- [`scripts/benchmark.py`](/root/skill/scripts/benchmark.py) 已经会根据 validator 输出构造 retry prompt。
- [`scripts/benchmark.py`](/root/skill/scripts/benchmark.py) 已经支持同一任务运行内的多次 validator-feedback 尝试。
- [`scripts/benchmark.py`](/root/skill/scripts/benchmark.py) 已经记录 attempts、usage、usage_per_round 和 grading 结果。
- [`README.md`](/root/skill/README.md) 已经暴露 `--max-task-attempts`。

## Feedback Policy 设计

### `vague`

- 只说明上一轮未通过
- 要求 agent 继续修改并重试

### `error-localized`

- 指出失败的评分项
- 给出 validator notes
- 不直接提供修复方案

### `actionable-path`

- 指出哪里失败
- 明确给出修复路径或下一步建议

## Cache-Friendly Feedback 设计

### `full-refresh`

- 每轮重写整段 retry feedback

### `stable-prefix`

- 固定前缀保留 task 元信息和通用 retry 规则
- 动态后缀只放最新未解决问题

## 各研究问题的实验设计

### RQ1：Retry Budget 的边际收益

目标：

- 衡量 success 随 retry budget 的增长曲线
- 识别边际收益开始明显衰减的轮次

实验：

- 固定 `feedback_policy = error-localized`
- 固定 `feedback_format = full-refresh`
- 扫描 `max_task_attempts = 1, 2, 3, 4, 5, 6`
- 对每个模型和任务做重复运行

指标：

- `success@k`
- `delta success(k)`
- 各轮累计 token / USD cost
- 首次成功轮次分布
- 每增加 1% success 所需 token

### RQ3：Stopping Rule 的 token-efficiency

目标：

- 比较简单、可解释的 stopping rules 在统一预算下的性价比

实验：

- 固定 `feedback_policy = error-localized`
- 固定 `feedback_format = full-refresh`
- 使用统一上限，如 `max_task_attempts = 5`
- 对比：
  - `max-attempts-only`
  - `score-stall`
  - `unresolved-stall`
  - `low-return`

指标：

- success vs cumulative tokens
- success vs cumulative USD cost
- success per 1K tokens
- success per dollar
- 达到目标 success 所需平均 token / cost
- stop-too-early / stop-too-late rate

### RQ4：Feedback Policy 与 Feedback Format

目标：

- 评估 feedback 质量和格式对收敛与 token 开销的影响

实验：

- 固定 `max_task_attempts`
- 比较：
  - `vague`
  - `error-localized`
  - `actionable-path`
- 交叉比较：
  - `full-refresh`
  - `stable-prefix`

指标：

- 最终 success rate
- 首次成功轮次
- 累计 token / cost
- 每轮 improvement rate
- feedback 长度与 cache 相关 proxy

## 最小实验矩阵

### E1：Attempt Budget 扫描

- 服务 RQ1
- 扫描 `max_task_attempts`

### E3：Stopping Rule 对比

- 服务 RQ3
- 扫描 `stop_rule`

### E4：Feedback / Format 对比

- 服务 RQ4
- 扫描 `feedback_policy` 与 `feedback_format`

## 需要的代码范围

### Benchmark Runner

文件：

- [`scripts/benchmark.py`](/root/skill/scripts/benchmark.py)

需要支持：

- 可配置 `feedback_policy`
- 可配置 `feedback_format`
- 可配置 `stop_rule`
- 结果 JSON 中记录 retry policy 元数据
- 记录每轮 retry prompt 统计

### Analysis Pipeline

需要支持：

- `success@k`
- marginal gain by attempt
- token-success / cost-success 曲线
- stopping-rule 对比
- feedback-policy 对比
- 从目标 success 反推预算

## 建议日志字段

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
- feedback 文本长度或 token 数
- transcript 长度及其增量

## 建议输出

### 表格

- 单轮 vs 多轮 success / token / cost
- stopping-rule 对比表
- feedback-policy 对比表
- 相近 success 下的最小 token 预算表

### 图表

- `success@k`
- marginal gain by attempt
- attempts-to-success 直方图或 CDF
- cumulative token vs success
- cumulative cost vs success
- stopping-rule 的 budget-success 曲线

## Threats to Validity

- LLM 输出有随机性，需要重复运行
- judge-based grading 可能带来偏差
- prompt cache 命中依赖 provider 实现
- 静态 complexity proxy 不一定完全反映真实任务难度

## 推荐实施顺序

1. 先复现 append baseline，并完成 attempt-budget 扫描。
2. 比较 stopping rules 的 token-efficiency。
3. 比较 feedback policy 和 cache-friendly formatting。
4. 汇总 budget-success frontier 结果。

## 一句话总结

论文贡献应表述为：在真实 tool-using agent benchmark 上，系统测量 retry 的收益边界、停止效率和反馈效率，而不是提出新的 agent 方法。
