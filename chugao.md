1. 背景

- agent 已经广泛使用在 research、coding、productivity、analysis、email、memory 等真实任务中
- 现实使用里，用户并不只关心“模型单轮能力强不强”，还关心“最终能不能把任务做成，以及总成本是否可接受”
- 一个常见观察是：一些更便宜的模型首轮更容易失败，但并不一定永远做不成；如果允许外部 feedback 和迭代修正，它们可能可以逼近更贵模型的最终成功率

2. 问题

- 目前对 agent 模型的比较，常常默认把“第一次 attempt 的结果”当成模型能力本身
- 但 agent 实际运行不是单轮问答，而是：
  1. 先尝试完成任务
  2. 失败后接收 validator / external feedback
  3. 继续修复并 retry
- 这带来两个研究空白：
  1. 便宜模型是否能通过 feedback-driven iteration 逼近贵模型的任务成功率
  2. 即使能逼近，这种“追赶”是否仍然 cost-competitive

3. 核心洞察

- 首轮能力差距不等于最终能力差距
- 便宜模型可能在 first attempt 上落后，但在 iterative feedback 下逐步修复错误，最终达到接近贵模型的 success
- 但这种追赶不是免费的：额外 token 可能来自 retry，也可能来自第一次 attempt 内部的低效探索、错误 skill 使用、context contamination、self-repair 等
- 因此，判断便宜模型是否“值得用”，不能只看单价，也不能只看单轮 success，而要看：
  - 最终能否追上
  - 追上的累计成本是多少
  - 这些额外成本具体来自哪里

4. Gap（论文立足点）

现有工作主要集中在：

- 单轮 prompt 优化
- 减少 turn 数
- agent 架构优化
- 更强模型带来更高首轮成功率

但缺少对以下问题的系统研究：

- 更便宜模型能否通过 feedback-driven iteration 在 agent 任务上逼近更贵模型
- 这种“能力追赶”对应的累计 token / dollar 成本是否仍有竞争力
- 如果成本变高，额外成本究竟来自 retry 本身，还是来自 first attempt 内部的 inefficiency

因此，这篇论文的立足点不是单独研究 retry，也不是单独研究 token waste，而是研究：

`feedback-driven iteration 是否能让便宜模型以接近的累计成本达到接近贵模型的 agent 能力`

其中，token cost map 作为成本解释框架，用来拆解额外成本来源。

5. 方法概述

5.1 模型比较框架

- 选择多个 production-relevant 模型，覆盖更贵模型与更便宜模型
- 在同一 benchmark、同一 agent framework、同一工具环境下运行
- 对每个任务记录：
  - first-attempt success
  - final success under retry
  - first-success attempt
  - cumulative token
  - cumulative dollar cost

5.2 迭代设置

- agent 维持相同执行框架
- 每个完整 attempt 结束后，接收 validator feedback
- 在固定 retry budget 或统一 stopping rule 下继续下一轮
- 比较不同模型在“从首轮到最终”的追赶轨迹

5.3 成本分解

- 将累计成本拆解为：
  - first-attempt cost
  - retry-induced cost
- 对 first attempt 内部的高成本轨迹，进一步用 token cost map 做机制归因：
  - selection
  - bootstrap
  - acquisition
  - exploration
  - generation
  - verification
  - repair
- 并区分：
  - necessary
  - overpriced
  - wasteful

5.4 比较目标

不是只问“谁更强”，而是同时回答：

- 贵模型是否主要赢在首轮
- 便宜模型是否能靠迭代追上
- 如果追上，总成本是否仍然接近
- 如果没有追上，是能力上限问题，还是成本结构问题

6. RQ（研究问题）

RQ1（Performance）
- `RQ1：便宜模型能否通过反馈迭代在任务成功率上逼近贵模型？`

这个问题关注：

- cheaper vs expensive models 在 first attempt 上的差距有多大
- iterative feedback 后，这个差距缩小多少
- 哪些任务上便宜模型能追上，哪些任务上仍然追不上

RQ2（Cost）
- `RQ2：当便宜模型通过迭代获得提升时，它的累计成本是否仍然与贵模型具有竞争力，这些额外成本主要来自哪里？`

这个问题关注：

- 便宜模型虽然需要更多 iteration，但累计 token cost 是否仍可接受
- 总成本中有多少来自 retry
- 有多少额外成本在 first attempt 内部就已经产生
- 这些额外成本具体属于哪些 token cost components



8. Experimental Setting

8.1 Task and Benchmark

- 使用 PinchBench / Skillsbench
- 覆盖真实 skill-using agent 任务


作用：

- 保证任务真实且具有代表性

8.2 Large Language Models

- 使用minimax 和 GPT 模型
- 覆盖更贵模型与更便宜模型
- 统一记录：
  - token usage
  - cumulative dollar cost
  - success metrics

作用：

- 让“能力追赶”和“成本竞争力”可以在现实条件下比较

8.3 Evaluation Metrics

性能指标：

- first-attempt success rate
- final success rate under retry
- success@k
- first-success attempt
- gap closure ratio

成本指标：

- cumulative input tokens
- cumulative output tokens
- cumulative dollar cost
- token per successful task
- additional token to achieve one more success

成本分解指标：

- first-attempt token share
- retry token share
- intra-attempt waste share
- inter-attempt waste share
- token cost components from the token cost map

8.4 Agent Design

- 保持 OpenClaw 原始 agent 执行框架
- 每个 attempt 结束后接收 validator feedback
- 在统一 retry budget / stopping rule 下运行
- 保持相同工具环境，避免把差异误归因到外部系统

作用：

- 明确核心变量是模型能力与迭代行为，而不是 agent 框架变化

9. Study Results（按 RQ 展开）

9.1 RQ1：Performance

9.1.1 First-Attempt Gap

在讲：

- 更便宜模型与更贵模型在 first attempt 上的 success gap
- 贵模型是否主要赢在“一次做对”

9.1.2 侧重“宏观定量” (Quantitative & The "What")
  核心任务是“报数据”，证明 Gap Closure 这个现象在统计层面是真实、显著且有差异的。
  在这里，你不需要深入探讨背后的机理，而是把重点放在总体趋势和各个数据集上的具体指标变化。

  总体大盘： 引入 Feedback 后，便宜模型和贵模型的整体 Success Rate Gap 从 X% 缩小到了 Y%。

  跨任务的统计对比： 在具体的 Benchmark 细分领域（如 Coding 任务 vs. Email 任务），Gap 分别收敛了多少？（例如：Coding 任务的 Gap 收敛了 40%，而 Analysis 任务只收敛了 10%）。

  收敛的效率： 便宜模型需要多少次 Retry 才能达到最大程度的 Gap 缩小（边际收益递减的拐点在哪里）？

9.1.3 侧重“微观定性与机理” (Qualitative & The "Why")
  核心任务是“做归因”，解释为什么在 9.1.2 中会出现“有的任务收敛快，有的任务不收敛”的数据差异。
  这部分是凸显你对大模型底层机制理解的 Insight 所在，你需要将“任务类型”下钻到具体的“能力维度”和“错误类型”。

  可恢复错误 (Recoverable Errors) vs. 致命缺陷 (Fatal Flaws)： 便宜模型能靠迭代追上的，往往是因为初始错误是“浅层的”（比如 API 参数传错、JSON 格式不合法），这类错误通过环境的 Validator feedback 极其容易纠正。

  硬性能力天花板 (Hard Capability Ceiling)： 便宜模型死活追不上的，往往是因为任务触及了模型的“硬伤”。比如长上下文污染（随着 Retry 次数增加，历史记录把注意力机制冲垮了）、长逻辑链规划能力缺失、或者是极其复杂的推理。在这些瓶颈前，给再多 Retry 也是徒劳。

  总结规律： 提炼出一个具有指导意义的结论。例如：“Feedback-driven iteration 对于具有明确环境报错机制（如 Code execution）的任务非常有效；但对于依赖开放式探索、弱反馈的任务（如长线 Research）帮助极小”。

Takeaway

- 便宜模型的首轮弱势不一定等于最终弱势
- iterative feedback 在部分任务上确实能显著缩小 cheaper vs expensive 的 performance gap

9.2 RQ2：Cost

9.2.1 Cumulative Cost of Catch-Up

在讲：

- 为了追上贵模型，便宜模型总共多花了多少 token / dollar
- 在什么条件下这种追赶仍然是 cost-competitive 的

9.2.2 First-Attempt vs Retry Cost

在讲：

- 总成本中有多少来自后续 retry
- 有多少其实在 first attempt 内部已经烧掉
- 说明高成本不应被简单归因为“retry 太多”

9.2.3 Token Cost Map of Extra Spending

在讲：

- 额外成本具体落在哪些 components
- 例如：
  - skill bootstrap overhead
  - context contamination
  - search noise
  - extraction failure
  - self-repair
  - wrong-content generation

9.2.4 Cost-Competitive vs Cost-Inefficient Catch-Up

在讲：

- 哪些情况下便宜模型虽然多迭代，但总成本仍然接近贵模型
- 哪些情况下便宜模型虽然尝试追赶，但额外成本已经吞掉价格优势

Takeaway

- 判断便宜模型是否值得用，不能只看单价，也不能只看单轮 success
- 关键是看 feedback-driven catch-up 后的累计成本与成本结构

10. Narrative Summary

这篇论文要建立的 narrative 是：

1. 更贵模型通常在 first attempt 上更强
2. 但更便宜模型并不一定无法达到接近的最终能力
3. feedback-driven iteration 可以帮助它们在部分任务上逼近贵模型
4. 真正的问题不是“是否多 retry”，而是“这种追赶最终值不值”
5. 回答这个问题需要同时分析：
   - performance gap closure
   - cumulative cost competitiveness
   - token cost map of extra spending
