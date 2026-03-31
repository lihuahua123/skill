# 试验记录

在skillsbench中



RQ1_MAX_ATTEMPTS=2 ./scripts/experiments/rq1.sh minimax-cn/MiniMax-M2.5     --backend skillsbench     --skillsbench-task-path tasks/offer-letter-generator     --feedback-policy error-localized     --feedback-format full-refresh     --feedback-strategy original
也就是简单讲verify的报错反馈给LLM


RQ1_MAX_ATTEMPTS=2 ./scripts/experiments/rq1.sh minimax-cn/MiniMax-M2.5     --backend skillsbench     --skillsbench-task-path tasks/offer-letter-generator     --feedback-policy error-localized     --feedback-format full-refresh     --feedback-strategy enhanced
这个是LLM自己总结出来的，能根据报错来指导下一步要怎么样。结果发现

 - total_tokens 增加了 152,079
  - 增幅约 43.0%
  - input_tokens 增加了 79,096
  - cache_read_tokens 增加了 74,432
  - output_tokens 反而减少了 1,449

  所以核心结论是：第二次enhanced 更耗 token，主要是多花在 input_tokens 和
  cache_read_tokens，不是输出变长。

2026/3/28
1. 最直接能做的：预测器
  你现在已有的可用特征基本包括：model、task_id/name、attempt、前几轮 score
  trajectory、execution_time、status、input/output/cache tokens、累计 cost，以及
  一些任务层面的 final score / attempt_count。基于这些可以做：

  - Pass@k 预测器
    目标：在第 i 次 attempt 后，预测这个 task 到预算用完前能不能过线。
    适合模型：Logistic Regression、XGBoost、LightGBM。
    价值：决定“还要不要继续 retry”。
  - Next-attempt gain 回归器
    目标：预测下一轮分数提升 delta_score。
    适合模型：Random Forest Regressor、XGBoost Regressor。
    价值：估计下一轮是否还有边际收益。
  - Final score 回归器
    目标：根据首轮或前两轮信息预测最终分数。
    价值：提前判断 near-miss plateau。
  - Cost-to-success 预测器
    目标：预测某任务如果最终能过，大概要花多少 token / 人民币。
    价值：做预算分配。

  2. 很适合做的：分类器
  你 notebook 里最有价值的一点，是已经发现了“不是 tool failure，而是 near-miss
  plateau”。这特别适合做分类。

  - 可恢复 / 不可恢复 二分类
    标签定义：首轮没过线的任务中，后续是否最终成功。
    价值：这是最实用的 retry classifier。
  - Validator-friendly / Capability-bound 分类
    这是你 markdown 里已经提出的机制假设，可以正式化。
    标签可以先人工标一版：
    validator-friendly：反馈后明显增长并最终通过
    capability-bound：高分停滞但不过线
    价值：把“哪些任务适合靠 feedback 修复”系统化。
  - Failure mode 多分类
    根据 judge notes 分成：accuracy、completeness、format/organization、style、
    multi-constraint integration。
    价值：后面能做针对性的 prompt / tool policy 优化。
  - Model-win region 分类
    目标：预测某任务更适合小模型还是大模型。
    标签：MiniMax sufficient / Needs GPT-class model。
    价值：直接服务 routing。

  3. 更有意思的：排序和优化算法
  如果你想更像“系统优化”而不是单纯做统计，这部分最值得做。

  - Retry stopping policy
    用预测器输出 P(success | current state) 和 expected delta_score /
    next_cost，然后设阈值：
    继续条件可以是
    E[gain]/E[cost] > tau 或 P(final success) > tau。
    这本质上是一个 early stopping policy。
  - Task routing policy
    给每个任务先决定：
    小模型一次试试 / 小模型+有限重试 / 直接上大模型。
    可建成一个 cost-sensitive classifier，优化目标是：
    max success - lambda * cost
  - Attempt budget allocation
    总预算固定时，不是每个任务都给同样 retry 次数，而是优先分给“最可能被救活”的
    任务。
    这可以建成：
      - 贪心排序：按 expected success gain per yuan
      - 0/1 knapsack：预算内最大化成功数
      - contextual bandit：在线分配重试资源
  - Dynamic model escalation
    例如：
    首轮用 MiniMax
    若出现 高分但卡住 + judge note 属于复杂整合类，升级到 GPT
    若只是格式/组织问题，则继续小模型
    这是很实际的 cascade policy。

  4. 如果只选 3 个最值得做的，我建议这三个
  按研究价值和落地性排序：

  1. Retry-or-stop 二分类/排序模型
     预测下一轮是否值得继续。这个最容易直接转成策略。
  2. Recoverability classifier
     判断失败任务是不是“可被 feedback 救回来”。这和你 notebook 的核心发现最一
     致。
  3. Cost-aware routing
     决定任务一开始该走小模型还是大模型。这个最接近真实系统优化。

  5. 用你现有 notebook 数据就能构造的特征
  建议先做这批，不需要额外采集：

  - 静态特征：model, task_id, task category/frontmatter name
  - 当前状态特征：attempt index, current score, best score so far
  - 轨迹特征：score gain from last attempt, slope over last 2 attempts, 是否已进
    入 plateau
  - 执行特征：execution_time, status
  - 成本特征：input/output/cache tokens, cumulative cost
  - 规则特征：first attempt success, 是否连续两轮增益<epsilon

  6. 你这份数据的一个关键限制
  仅根据当前 notebook，样本量看起来很小，任务大概只有 21 个共同任务，所以：

  - 不适合一开始上深度模型
  - 更适合树模型、逻辑回归、规则学习
  - 最好把“task-attempt”展开成样本行
  - 更适合做策略原型和机制验证，不适合宣称高泛化

  如果你要，我下一步可以直接按这个 notebook 的字段，给你整理一版：
  问题定义 + 标签构造 + 特征表 + baseline 模型 + 可写进论文的方法段
  甚至可以顺手把它补成一个新的 notebook。


2026/3/29
检查gpt3.5 失败原因
• 我看了这份汇总结果 skillsbench__openai-gpt-5-3-codex__2026-03-28__19-58-04.json 以及对应 job 的 trial.log /
  result.json，这批失败任务大致分成几类。

  主要失败原因

  - 超时，任务没做完。这是最大类，至少 10 个任务直接以 TimeoutError 结束：energy-market-pricing、fix-build-
    google-auto、latex-formula-extraction、manufacturing-codebook-normalization、mars-clouds-clustering、quantum-
    numerical-simulation、react-performance-debugging、shock-analysis-demand，以及后续重试也超时的 earthquake-
    phase-association、pedestrian-traffic-counting。可见在这批较重任务上，agent 经常没在预算内收敛。例子见
    parallel-tfidf-search trial.log 这种同类轨迹格式，超时类任务的 result.json 里都有 TimeoutError。
  - 先犯基础错误，重试也没修到位。earthquake-phase-association 第一次连 /root/results.csv 都没生成，第二次虽然产
    出了文件，但 F1 仍是 nan，第三次反而超时；pedestrian-traffic-counting 第一次结果值就错了，第二次超时。说明
    agent 能响应 verifier，但修复路径不稳定，容易从“缺文件”跳到“有文件但算法仍错”，最后耗尽预算。
  - 环境/前提理解错误。fix-build-agentops 六次都卡在 REPO_ID environment variable is not set，说明它一直没满足任
    务要求的运行前提；lean4-proof 六次都还是 lake: command not found，同时 verifier 还提示 baseline/solution.lean
    not found，说明它没有处理工具链缺失或基线文件要求。这两类都不是细节 bug，而是任务前置条件没有被正确建立。对应
    轨迹见 fix-build-agentops trial.log 和 lean4-proof result.json。
  - 输出形态不对，导致 verifier 根本跑不起来或收不到目标产物。python-scala-translation 和 setup-fuzzing-py 六次都
    是 collected 0 items / no tests ran，这通常不是“差一点做对”，而是输出文件名、目录、测试入口或任务约定没对上。
    也就是 agent 一直在提交 verifier 不认可的产物。
  - 核心算法/数值逻辑没修准。reserves-at-risk-calc 多次都算错，且后几次甚至把风险值改成 0；sec-financial-report
    反复出现数量级错误和标识列表错误；software-dependency-audit 虽然生成了 CSV，但内容和 ground truth 对不上；
    suricata-custom-exfil 则在“匹配不到应报文”和“规则过宽/关键词位置不合规”之间来回摆动。这类任务说明 agent 能产
    出结果，但没有把 verifier 的精确约束吃透。
  - 基础设施/上下文窗口问题。parallel-tfidf-search 不是任务本身逻辑失败，而是模型请求直接报 400: Your input
    exceeds the context window of this model，随后 tenacity 重试后仍失败。这属于运行时请求构造或上下文管理问题，
    不是 solver 代码本身能力不足。对应见 parallel-tfidf-search result.json。

  更抽象的共性

  - 这次失败更像是 执行策略问题，不是单一领域弱项。很多任务并非完全不会做，而是卡在“先满足输出契约/环境前提/最小
    可验证产物”这一步。
  - retry 机制帮助有限。像 python-scala-translation trial.log 和 fix-build-agentops trial.log 这种，6 次 attempt
    基本都在重复同一种失败，说明 agent 没有真正利用 verifier feedback 改变策略。
  - 超时任务占比很高，说明对重任务缺少更强的“先做最小闭环、快速验证、再扩展”的控制，否则很容易把 budget 消耗在探
    索上。

  如果你要，我下一步可以把这 16 个失败任务按 超时 / 环境前提 / 输出契约 / 算法错误 / 平台错误 做成一张更细的表，
  每个任务给一行证据和建议修复方向。


 - skill benchmark 里，MiniMax 看起来“便宜且两轮更有效”
  - skillsbench 里，MiniMax “两轮效果更好一些，但总成本也更高”

  重试是有用的，能提升准确率，但是代价也是很高的

2026/3/31

首先总结出单次attempt的token浪费的共性，发现是工具使用不当，导致结果一直污染上下文
  最推荐的策略
  1. 不要让脏内容直接入上下文
  2. 入上下文前先压缩 这个感觉又回到LLM进行上下文压缩了
  3. 原文外存，摘要入模
  4. 每轮做上下文预算
  5. 超过预算时优先丢弃低信号历史