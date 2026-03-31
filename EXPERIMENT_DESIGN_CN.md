# PinchBench 多轮纠错实验设计

## 研究目标

本研究聚焦 PinchBench/OpenClaw 中 validator-driven retries 的 token-efficiency，核心问题只保留三类：

- 额外 retry budget 能带来多少真实收益
- 什么时候继续 retry 已经不划算
- 哪类 feedback / stopping 配置在相近 success 下最省 token

全文定位为 empirical study，而不是新 agent 方法。




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

### RQ1：总 token 开销中，有多少发生在单次 attempt 的内部探索阶段，又有多少来自外部
    反馈触发的额外 retry？
  - 第一部分：第一次 attempt 结束前烧了多少
  - 第二部分：后续 retries 又增加了多少
     哪些机制最容易导致 intra-attempt token 浪费？
     这里就是你 task_06_events 那种发现：
      - skill bootstrap overhead
      - tool failure / timeout
      - noisy search HTML
      - history growth
      - wrong skill choice 
Intra-attempt: 主要是 HTML 噪声和反复调用失败的 Tool。这一部分只要有主动出现的失败就会不断迭代
Inter-attempt: 主要是重复的 System Prompt 和不断堆叠的 History。这一部分没有主动出现的失败，而是外部感知，模拟人类反馈的，从而指导agent继续迭代

### RQ2：单轮的Feedback Policy 与 Feedback Format

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
这个目前是发现error-localized 好像更好？还是actionable-path 更好来着？
### RQ3：Retry Budget 的边际收益
task_10_workflow
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


## 最小实验矩阵


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

actionable-path-file 是为了模仿人类的，要说需要真实人来判断的话，可以使用
actionable-path 这种是交互式的，等你输出下一步应该做什么


把 intra-attempt 和 inter-attempt 明确拆开，单独建模
     task_06_events 这个 case 已经非常强地说明：大量浪费发生在第一次 attempt 内部，
     而不是 retry 本身。
     所以论文里不能只讲 retry efficiency，应该明确分成两层：
  - intra-attempt inefficiency：skill 读取、工具失败、搜索噪声、history growth
  - inter-attempt inefficiency：validator feedback 后整轮重试的额外成本
    一个比较稳的定义是：

  - intra-attempt feedback
    同一 attempt 内，由 agent 自己的执行环境产生的反馈
    例如：tool error、command output、parser error、runtime exception、甚至你在
    agent loop 里插入的 lightweight self-critique
  - inter-attempt feedback
    一个完整 attempt 结束后，由外部 evaluator / validator / grader 产生的反馈，并触
    发新 attempt


  加上日志，每轮的tool类型或者skill类型， 每次 retry feedback 本身的 token 长度，每个 skill 被读取后带来的 token 增量，每轮的cache 和非cache 的input tokens

   token efficiency = model policy × skill pool × tool reliability × retry policy

   skill benchmark 用来选择skill

   Stopping rule 最好做“离线反事实评估”
     现在如果每个 stopping rule 都重新跑一次，结果会混入新的随机探索路径。
     更稳的办法是：先收集完整轨迹，再离线模拟“如果在第 k 次停会怎样”。这样你比较的
     是 stopping 决策本身，而不是每次重跑生成了不同轨迹。
     这会让 RQ3 更硬。

  现在有个问题是，pinchbench是LLM评分的，有的时候并不是我的策略好，而单纯因为LLM输出了更高的分数而已。所以还是skillbench比较靠谱？

skillbench 是怎么停止的？
   - 第一次模型说“我做完了”，不会立刻停
  - agent 会回一条确认消息，让模型再确认一次
  - 只有第二次还坚持 task_complete，才真正结束 loop

  所以对 Terminus-2 来说，“没命令了”本身不是标准完成条件。更准确地说：
  - commands 为空，loop 也可能继续
  - 只要没有触发 task_complete 的双确认，agent 仍然会进入下一轮
  - 下一轮 prompt 会带上当前 terminal output，再问模型下一步
  这和 OpenClaw 的哲学差异很大：
  - OpenClaw：no tool call => stop
  - Terminus-2：explicit task_complete => stop，而且要双确认
  这会直接影响你的 token 研究：
  - OpenClaw 更容易因为“模型暂时不想调工具了”而提前结束
  - Terminus-2 更容易继续多转几轮，直到明确声明完成
  - 所以两者的“停止行为”不是同一类机制，token 曲线不能直接类比


  现有 agent token-efficiency 分析把成本错误地归因给 retry；实际上，大量浪费发生在第一
  次 attempt 内部。只有把 intra-attempt 与 inter-attempt 分开，feedback、budget、
  stopping 的比较才是有效的。 真的吗

  其实本意是想着尽可能少token来完成一件事，那我们是不是改变skill描述会比较好？