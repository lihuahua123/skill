基于 [results_visualization_skillbenhmark_full.ipynb](/data/lirui/skill_study/skill/analysis/rq1/results_visualization_skillbenhmark_full.ipynb) 第 6 个 cell 和 [aggregated_results.json](/data/lirui/skill_study/skill/analysis/rq1/aggregated_results.json) 里的 `attempts / verifier / execution.error / prompt_tokens_by_attempt / usage_per_round`，这 15 个最贵任务的共性很清楚：

它们贵，核心不是“模型写了很多字”，而是“长会话里反复带着大上下文运行”。Top 15 一共花了约 `106.38 CNY`，占总成本 `45.4%`。它们中位数有 `95` 轮对话，平均每个任务约 `4.0M` input tokens、`3.83M` cache-read tokens，但 output 平均只有 `40k`。也就是说，钱主要烧在反复读上下文、读历史、读文件、重跑长链路，不是烧在最终答案上。

我会分 4 类看：

1. 天生“重任务”，即使成功也贵
`pg-essay-to-audiobook`、`mars-clouds-clustering`、`court-form-filling`、`sec-financial-report`

共同点：
- 任务本身链路长，要读较多输入、处理较复杂产物、再过 verifier。
- 即使成功，也往往不是 1 次就过，或者单次 attempt 本身轮数就很多。
- 成本高的直接来源是 `prompt_tokens_by_attempt` 很大，不是 completion 大。

其中：
- `mars-clouds-clustering` 只跑 1 次就成功，但单次 prompt 就有 `4.36M` tokens，说明是典型“大上下文一次做完”型。
- `court-form-filling` 和 `sec-financial-report` 都是“接近正确，但还要根据 verifier 再修一次”，所以成功前多吃了一轮大上下文。
- `pg-essay-to-audiobook` 最明显，4 次 attempt 才成功，4 次 prompt 分别约 `1.71M / 0.49M / 1.44M / 1.28M`，是“成功了，但代价很高”的典型。

2. 长链路不收敛，最后超时
`adaptive-cruise-control`、`lab-unit-harmonization`、`fix-build-agentops`、`scheduling-email-assistant`、`lean4-proof`、`pedestrian-traffic-counting`、`shock-analysis-supply`、`setup-fuzzing-py`、`suricata-custom-exfil`

共同点：
- 前面已经花了很多轮和很多 prompt tokens。
- 但问题没有被快速收敛成一个小修复，最后直接 `TimeoutError`。
- 这类任务最贵，因为成本已经发生了，但结果没有交付。

代表例子：
- `adaptive-cruise-control` 最贵，2 次 attempt，`172` 轮，总成本 `13.79 CNY`。第 1 次 verifier 已经指出是仿真结果/安全/距离控制问题，第 2 次还是拖到超时。
- `fix-build-agentops`、`lean4-proof` 也类似，前置环境/工具链问题没有一次性打掉，后面继续在长上下文里消耗。
- `scheduling-email-assistant` 在已有分析笔记里表现出明显任务漂移，属于“越跑越偏”，这类最浪费 token。

3. 无效重试或重复犯同类错误
`fix-build-google-auto`、`pg-essay-to-audiobook`、`court-form-filling`、`sec-financial-report`

共同点：
- retry 不是没有价值，但很多成本来自“前一次已经暴露问题，后一次仍然没有把问题空间明显缩小”。
- 如果 retry 后 prompt 还是很大，说明 agent 没把问题压缩成“只修 verifier 指向的那个点”。

其中：
- `fix-build-google-auto` 最典型，`6` 次 attempt，始终没过，成本 `6.58 CNY`。这是“重复 retry，但没有实质收敛”。
- `pg-essay-to-audiobook` 虽然最后成功，但第 2、3 次 `score_delta` 其实是 `0.0`，仍继续花了两轮大成本，属于“救回来了，但重试效率低”。
- `court-form-filling` 则是“有用重试”的例子。第 1 次其实只是一个很具体的字段错误，但第 2 次仍然带了 `2.33M` prompt tokens，说明修复粒度还不够小。

4. 基础设施或执行层异常，把前面 token 全浪费了
`organize-messy-files`、部分 `setup-fuzzing-py`、部分 `suricata-custom-exfil`

共同点：
- 任务本身已经跑了很多轮，prompt token 已经吃掉。
- 结果在执行层或 API 层挂掉，比如 `RetryError`、`APIError`、超时。
- 这种贵法的特点是：不是“不会做”，而是“做到一半死掉”，沉没成本特别高。

`organize-messy-files` 很典型：
- 第 1 次 attempt prompt 就约 `4.08M` tokens。
- 第 2 次直接 `RetryError[...APIError]`。
- 也就是大头成本已经烧掉，但没有换来有效输出。

如果再抽象一层，最核心的共同原因只有 3 个：

1. 上下文过大  
这些任务几乎全是 input/cache 驱动，说明 agent 在长会话里不断重放历史、文件内容、执行结果。

2. retry 没有“变窄”  
贵任务往往不是因为 retry 本身，而是 retry 后仍然像第一次那样大范围搜索、重读、重跑。

3. 失败发生得太晚  
很多任务不是早早失败，而是跑了 70 到 170 轮后才 timeout / error。也就是最大的问题不是单次错误，而是缺少及时止损。



核心判断是：

**首轮求解 skill 解决的是“怎么做这类任务”**，  
**retry policy skill 解决的是“第一次没过以后，下一步该不该继续、修哪里、修多大”**。

对你这批 SkillsBench 高价任务，贵的大头主要发生在第二种。

因为从 trace 看，很多任务不是第一次完全不会做，而是：

- 首轮已经产出了东西，甚至 verifier 已经给了很具体的失败信号
- 但后续 retry 没有缩小问题范围
- agent 继续大范围读代码、读文件、重跑命令、重建上下文
- 最后把 token 烧在“错误的修复策略”上

所以 skill 更该介入 retry policy。

**为什么不是优先首轮求解 skill**

首轮求解 skill 只有在任务结构高度稳定时才值钱，比如 `court-form-filling` 这种：
- 输入结构稳定
- 输出结构稳定
- 工具链稳定
- verifier 约束也稳定

这种任务你可以用 family skill 直接压缩首轮搜索。

但你 top 贵任务里大量不是这种：

- `fix-build-agentops`
- `fix-build-google-auto`
- `lean4-proof`
- `adaptive-cruise-control`
- `sec-financial-report`
- `suricata-custom-exfil`

这些任务的问题不是“缺少通用做法说明”，而是：
- 环境前提没满足
- verifier 指向的错误没被正确吸收
- 后续修复没有局部化
- 明明已经重复失败，还继续全量重试

这类任务就算首轮 skill 写得很好，也只能帮一点。真正决定成本的是第 2 次以后怎么做。

**retry policy skill 具体在管什么**

它不是教模型“如何解题”，而是给 retry 一个决策框架。至少包括 4 件事。

1. 失败分诊
先判断这次失败属于哪一类，再决定后续动作。

例如：
- 环境前提缺失：`REPO_ID` 没设、`lake` 不存在
- 输出契约错误：文件名、路径、schema、空字段不对
- 局部 verifier mismatch：只有一个字段/一个测试没过
- 算法/数值逻辑错误：结果接近但指标不达标
- 基础设施异常：timeout、API error、rate limit

这一步的作用是防止 agent 把所有失败都当成“继续试一遍”。

2. 修复范围裁剪
决定下次 retry 是：
- 只修一个点
- 只重跑一个子步骤
- 还是必须重新做整条链路

比如：
- `court-form-filling` 看到 `page1_court_info should be empty`，就应该只修这个字段，不该整份 PDF 重做。
- `fix-build-google-auto` 看到 `REPO_ID environment variable is not set`，就应该先解决环境前提，不该继续改业务输出。
- `sec-financial-report` 如果是路径错，就先修路径，不该重新做整张大表分析。

这一步直接决定 token 会不会爆。

3. 同类失败止损
如果连续两次还是同类失败，skill 要明确要求停。

比如：
- 连续两次还是环境错误
- 连续两次还是 verifier 不识别输出文件
- 连续两次还是 timeout，且没有更窄的执行计划

那就不应该第 3 次继续“全量探索”。  
你在 `experiment.md` 里总结的 `same-class-failure-stop` 本质上就是这个。

4. retry prompt 压缩
把上一次失败压缩成很短的 repair brief，而不是把完整历史再灌回去。

好的 retry skill 应该产出类似这样的内部结构：

- failure_type: `structured-output-mismatch`
- minimal_target: `page1_court_info`
- do_not_touch:
  - other PDF fields
  - output path
- verify_first:
  - inspect failing assertion
- stop_if:
  - same field still wrong after one patch

而不是再附上整段原始任务说明、整段长 verifier log、整段历史推理。

**为什么这对成本最敏感**

因为你这批贵任务有一个共同特征：  
高成本主要不是 output tokens，而是反复增长的 prompt/context。

也就是说，贵在：

- retry 时又把整个任务背景带一遍
- 又把大量文件内容读一遍
- 又把完整 verifier 输出塞一遍
- 又跑一遍大命令链路

所以真正能降成本的不是“让第一轮更聪明一点”，而是“让第二轮开始明显变窄”。

**拿几个任务具体看**

`court-form-filling`
- 首轮其实已经接近成功
- verifier 明确说某字段应为空
- 这类任务最适合 retry skill
- 正确策略：只看失败字段，只 patch 对应输出，不重做整份表

`fix-build-google-auto`
- 多轮失败都在环境前提
- 这不是 solve 能力问题，是 retry policy 没先做 prerequisite gate
- 正确策略：先检查 env contract，未满足就停，不进入大规模修复

`lean4-proof`
- 如果一直是 `lake: command not found` 或基线文件要求不满足
- 后续 retry 再怎么读 proof 内容都没意义
- 正确策略：环境/工具链失败直接分类，限制后续搜索

`sec-financial-report`
- 大表分析类任务很容易“因为一个路径或格式错误，反复重跑整条数据链”
- 正确策略：retry 时先只验证输入路径、schema、输出格式，再决定要不要重算

`suricata-custom-exfil`
- 这类约束型任务经常在相近错误间摆动
- 正确策略：记录上轮失败是哪种约束，下一轮只允许做一类定向修改；若失败类型不变则止损

**如果把它落实成 skill，我建议分两层**

第一层：一个很短的 `retry-core`
只做决策，不教解题。

内容只要这些：
- classify failure
- decide repair scope
- require minimal patch
- stop on repeated same-class failure
- avoid replaying full task context

第二层：family-specific retry playbook
按任务族补少量规则。

例如：
- `output-contract family`
- `environment-debug family`
- `data-analysis family`
- `simulation/control family`

这样比把所有经验堆进一个大 SKILL 更省 token，也更稳。

**一句话总结**

优先把 skill 投在 retry policy 层，是因为 SkillsBench 高价主要不是“第一轮不会做”，而是“失败后不会缩范围、不会止损、不会只修 verifier 指向的那个点”。

如果你要，我下一步可以直接把这个思路写成一版很具体的 retry-skill 结构草案，按：
- 触发条件
- 输入
- 决策步骤
- 输出模板
- stop rule  
给你列出来。




 我会建议的最小方案

  A. 一个任务族路由器
  输入：task 静态信息
  输出：

  - aggressive-stop-safe
  - conservative-stop
  - drift-only-stop

  这个完全可以手工规则。

  B. 做 case-based retrieval，不做参数学习
  你现在的数据量其实更适合“找相似例子”，不适合“拟合模型”。

  即：
  给一个新 task / attempt，先找历史上最像的几个任务：

  - verifier 形态像不像
  - 输出契约像不像
  - 是否 repo/debug
  - 是否 data-heavy
  - 是否 simulation-heavy
  - 历史上这类任务是不是天然长

  然后根据最近邻任务的行为，决定：

  - 该不该宽松
  - 该不该保守
  - 哪类 early-stop 信号可信

  这本质上不是训练，而是经验检索器。

  你说，intra-attempt早停，之后再用verify这类的进行重试，会有效果吗？不行，直接停止inter-attempt

  还有就是skillsbench 并没有调用skill！！！！

./scripts/experiments/rq1.sh anthropic/MiniMax-M2.5     --backend skillsbench     --skillsbench-task-path tasks/data-to-d3     --runs 1     --max-task-attempts 1     --max-parallel-tasks 1     --job-name data-to-d3-minimax-paper-dynamic-turn     --force-build     --ak paper_dynamic_turn_enabled=true     --ak paper_dynamic_turn_initial_turn_limit=14     --ak paper_dynamic_turn_extension_turn_limit=14     --ak paper_dynamic_turn_remind_every_turn=true 没有调用skill

查看是否用上skill
python3 /data/lirui/skill_study/skillsbench/detect_skill_usage.py /data/lirui/skill_study/skillsbench/jobs/newjobs