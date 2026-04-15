有，而且已经有几条很接近的线了；但我没查到一篇完整覆盖你这个设计全部要点的论文。更准确地说，你的 EXPERIMENT_DESIGN.md 里至少有 4 个子问题，文献里分别有人做过，但“真实工具代理 + validator-driven iterative repair + feedback policy/context policy 对照 + success/cost/convergence 全套分析”这个组合，我目前没有找到现成一篇直接撞题的。

最接近的论文

- ChatRepair / Keep the Conversation Going（2023-04-01）
  最像你“validator-driven iterative repair”主线。它做的是 conversation-driven APR，把失败 patch 和测试反馈继续喂回去，形成多轮修复闭环。
  链接：https://www.catalyzex.com/paper/keep-the-conversation-going-fixing-162-out-of
- Studying and Understanding the Effectiveness and Failures of Conversational LLM-Based Repair（2025-03-19）
  这篇和你的 RQ1/RQ2/RQ4 尤其像，因为它专门分析 iterative component 到底有没有用。更重要的是，它的结论对你有直接启发：他们发现 ChatRepair 的迭代式改进未明显优于独立重复 prompting，甚至还更差一些。
  链接：https://qixin5.github.io/files/pdf/research/apr25studying.pdf
- ContrastRepair（期刊页显示 2025-10-03；对应 arXiv 2024）
  这篇像你“feedback_policy”那部分。核心思想是：反馈质量决定效果，它通过 failing/passing test pair 让反馈更可操作，显著优于已有 conversational APR。
  链接：https://research.monash.edu/en/publications/contrastrepair-enhancing-conversation-based-automated-program-rep/
- VRpilot（2024-05-24）
  这篇和你“actionable / error-localized feedback + 外部工具验证 + ablation”很像。它明确做了 reasoning 和 validation feedback 的消融，发现两者都重要。
  链接：https://arxiv.org/pdf/2405.15690
- Reflexion（2023-03-20）
  更偏一般 agent，不是 APR，但和你“多轮反馈促进收敛”高度相关。它研究 agent 如何从 trial-and-error 的反馈里持续改进。
  链接：https://www.scixplorer.org/abs/2023arXiv230311366S/abstract
- Self-Refine（2023-03-30）
  更偏通用 test-time self-correction，不是工具代理 benchmark，但和你“多轮 refinement / attempts-to-success 分布 / 增量收益”有方法论上的近似。
  链接：https://arxiv.gg/abs/2303.17651
- The Debugging Decay Index（2025-06-23 提交）
  这篇和你的 append / fresh-session / rollback extension 非常接近，核心就在说多轮 debug 会衰减，strategic fresh start 可能有帮助。
  链接：https://huggingface.co/papers/2506.18403
- On the Role of Feedback in Test-Time Scaling of Agentic AI Workflows（2025-07-08 版本页）
  这篇不是代码修复专门论文，但和你“反馈质量、反馈形式、成本-效果 tradeoff”很近。它系统研究 feedback 在有限 inference budget 下的作用。
  链接：http://arxiv.org/abs/2504.01931v4

跟你文档逐项对照

- RQ1/RQ2: 多轮反馈是否有效、成功发生在第几轮
已有相近工作：ChatRepair、Studying...、Reflexion、Self-Refine。
- RQ3: token/cost vs success
有部分论文会报成本或 API 次数，但像你这样把 success@k、marginal gain、tokens per extra 1% success 系统化展开的并不多。
- RQ4: feedback_policy 比较
ContrastRepair、VRpilot 很接近，但它们通常比较的是“某种更强反馈设计 vs baseline”，不一定像你这样显式拆成 vague / error-localized / actionable-path 三档。
- append / fresh-session / rollback
我查到非常接近的动机论文是 Debugging Decay Index，但我还没看到一篇在真实代码代理 benchmark上把这三种上下文策略做成完整对照实验的代表作。
- stable-prefix / cache-friendly formatting
这个更像你的实现与系统优化贡献，我没查到已有论文把“prompt cache reuse”本身作为主要实验变量来系统研究。

我的判断

- 如果你的论文主张是“多轮修复有用”，这个方向不新。
- 如果你的主张是“我们第一次在真实 tool-using agent benchmark 上，系统量化 validator-driven iterative repair 的收益边界、成本边界、收敛机制，并比较 feedback/context policy”，那它看起来还有明显空间。
- 如果你把 append vs fresh-session vs rollback 和 stable-prefix 做扎实，这部分更像可发表的新点。

最该引用的 5 篇

1. ChatRepair / Keep the Conversation Going

https://www.catalyzex.com/paper/keep-the-conversation-going-fixing-162-out-of
2. Studying and Understanding the Effectiveness and Failures of Conversational LLM-Based Repair
   https://qixin5.github.io/files/pdf/research/apr25studying.pdf
3. ContrastRepair

https://research.monash.edu/en/publications/contrastrepair-enhancing-conversation-based-automated-program-rep/
4. VRpilot
   https://arxiv.org/pdf/2405.15690
5. The Debugging Decay Index
   https://huggingface.co/papers/2506.18403

如果你要，我下一步可以直接帮你把这些论文整理成一个“related work 映射表”：按你文档里的 RQ1-RQ4 + extension 分栏，标出“谁做过、做到什么程度、你还能 claim 什么”。


你现在这份设计里，“多轮修复”本身不新，但现有文献大多落在 code repair / APR，而不是你这里想做的 real tool-using agent。真正和你更接近的，其实是两条相对新的 agent 线：

- ACE / Agentic Context Engineering（2025-10-06 预印本，ICLR 2026 页面）
  重点不是修代码，而是 agent 如何利用执行反馈持续改进上下文，并且明确提到降低 rollout cost / latency。

https://www.microsoft.com/en-us/research/publication/agentic-context-engineering-evolving-contexts-for-self-improving-language-models/
- Efficient Agents: Building Effective Agents While Reducing Cost（2025-07-24）
  这篇直接把 agent 的效率问题拿出来做，讨论 efficiency-effectiveness trade-off，还用了 cost-of-pass 这类指标。
  https://arxiv.org/abs/2508.02694
- Thinking vs. Doing / TTI（项目页 2025）
  它关注的是 agent test-time scaling，但核心是“更多 token 的思考”不一定最好，应该看交互式扩展。这个跟你做“多轮反馈是否值得”很相关。
  https://test-time-interaction.github.io/

所以你可以把 related work 改成这个判断：

APR literature 已经证明多轮反馈可能有用，但对象主要是 patch generation。
Agent literature 开始研究 feedback、memory、context evolution、interaction scaling，但很少系统测量 validator-driven retries 的 token/cost boundary。
你这篇真正的缺口不是“有没有多轮”，而是：

- 在真实 agent benchmark 上，多轮 validator feedback 到底带来多少增益
- 增益出现在哪几轮，何时平台化
- 哪种 feedback/context policy 最省 token
- append、fresh-session、rollback 谁更划算

这正好对应你说的“没人认真谈 token 消耗怎么省”。这点我同意，而且它很可能是你最有价值的贡献。

你可以把论文主张往这几个方向收：

1. 不是证明 retry 有用，而是量化 retry 的收益边界和成本边界。
2. 不是只看 success rate，而是看 success per 1K tokens、success per dollar、marginal gain per retry。
3. 不是把上下文越堆越长，而是研究如何用更短反馈维持甚至提升收敛。

如果你要回答“如何节省 token”，从研究设计上最值得做的不是泛泛优化，而是直接比较这几种策略：

- stable-prefix + dynamic-suffix
  固定前缀，变化信息只放末尾，最大化缓存复用。
- unresolved-only feedback
  只保留没过的 criteria，不重复已通过项。
- fresh-session with compact state handoff
  清空对话历史，只传 workspace 状态摘要和失败点，避免 transcript 膨胀。
- rollback
  不仅重开 session，还恢复工作区，测试“长上下文污染”是不是主要问题。
- adaptive stopping
  不是固定跑满 5 次，而是在 validator 改善停滞时提前停止。

## 2026-03-15 补充检索：基于一手论文页的重合排查

下面这部分是我重新查过的 primary sources，优先用了 arXiv / 官方论文页，而不是二手总结页。结论先写在前面：

- 你的设计已经和现有文献在若干子问题上明显重合，但我仍然没有查到一篇论文完整覆盖你现在这套组合：
  `real tool-using agent benchmark + validator-driven iterative repair + feedback policy ablation + context policy ablation + token/cost frontier`
- 真正最容易“撞”的不是 `stable-prefix / cache-friendly formatting`，而是：
  1. 多轮 validator feedback 是否有效
  2. fresh start / restart 是否优于一直 append
  3. 成本和效果是否存在明显收益递减

### A. 高重合：建议一定引用，并在写作里主动区分

- **ChatRepair / Keep the Conversation Going: Fixing 162 out of 337 bugs for $0.42 each using ChatGPT**
  Xia and Zhang, arXiv:2304.00385, first submitted on **2023-04-01**
  链接: https://arxiv.org/abs/2304.00385
  重合点：
  - 直接做 conversation-driven APR
  - 用前一轮失败 patch 和 test failure 信息驱动下一轮修复
  - 明确报告 cost
  对你意味着：
  - 你的 `validator-driven iterative repair` 主线并不新
  - 但它是 patch-generation/APR，不是你要做的 real tool-using benchmark
  - 你需要把 claim 收到“系统量化收益边界、成本边界、上下文策略”而不是“提出多轮修复”

- **Studying and Understanding the Effectiveness and Failures of Conversational LLM-Based Repair**
  Chen et al., arXiv:2503.15050, first submitted on **2025-03-19**
  链接: https://arxiv.org/abs/2503.15050
  重合点：
  - 专门复盘 ChatRepair
  - 直接分析 iterative patch improvement 这个组件到底是否有效
  - 非常接近你的 RQ1 / RQ2，且也触到 RQ4 的“什么反馈/形式真的有用”
  对你意味着：
  - 如果你的论文主张只是“多轮反馈有效”，很容易被它顶住
  - 你更适合把重点放在 agent benchmark、context policy、token efficiency

- **RepairAgent: An Autonomous, LLM-Based Agent for Program Repair**
  Bouzenia et al., arXiv:2403.17134, first submitted on **2024-03-25**
  链接: https://arxiv.org/abs/2403.17134
  重合点：
  - 是 agent-based program repair，不再只是固定 prompt
  - 会动态调用工具、结合先前反馈继续修复
  - 明确报告平均 token cost
  对你意味着：
  - 这是“真实 agent + repair + tools + cost”方向里最该看的近邻之一
  - 但它没有像你这样显式拆 `feedback_policy` / `context_policy`，也不是围绕 retry frontier 做系统实验

- **VRpilot: A Case Study of LLM for Automated Vulnerability Repair**
  Nascimento et al., arXiv:2405.15690, first submitted on **2024-05-24**
  链接: https://arxiv.org/abs/2405.15690
  重合点：
  - reasoning + patch validation feedback
  - 利用 compiler / tests / sanitizer 等外部工具输出做迭代修复
  - 做了 feedback 相关消融
  对你意味着：
  - 和你的 `error-localized / actionable-path` 反馈设计很近
  - 但仍然偏 vulnerability repair，不是通用 tool-using agent benchmark

- **The Debugging Decay Index: Rethinking Debugging Strategies for Code LLMs**
  Adnan and Kuhn, arXiv:2506.18403, first submitted on **2025-06-23**
  链接: https://arxiv.org/abs/2506.18403
  重合点：
  - 明确说 iterative debugging 效果会快速衰减
  - 提出 `strategic fresh start`
  - 非常接近你 `append` vs `fresh-session` 的动机
  对你意味着：
  - 如果你后面做 fresh-session / rollback，对比实验一定要引用它
  - 但它不是在你的 benchmark 设定里比较完整 context policy family

### B. 中等重合：不会直接撞题，但很适合支撑方法动机

- **Reflexion: Language Agents with Verbal Reinforcement Learning**
  Shinn et al., arXiv:2303.11366, first submitted on **2023-03-20**
  链接: https://arxiv.org/abs/2303.11366
  相关性：
  - 语言反馈驱动 agent 在后续 trial 中改进
  - 支撑“外部反馈可以促进收敛”的一般性方法论
  不直接撞的地方：
  - 它不是专门做 code repair retry frontier，也没有你的 context-policy 对照

- **Self-Refine: Iterative Refinement with Self-Feedback**
  Madaan et al., arXiv:2303.17651, first submitted on **2023-03-30**
  链接: https://arxiv.org/abs/2303.17651
  相关性：
  - 典型的 test-time iterative refinement
  - 很适合支撑你“多轮 refinement / first-success distribution / marginal gains”的总体框架
  不直接撞的地方：
  - 它不是工具代理，也不研究 validator-driven workspace repair

- **On the Role of Feedback in Test-Time Scaling of Agentic AI Workflows**
  Chakraborty et al., arXiv:2504.01931, first submitted on **2025-04-02**, current arXiv version dated **2025-07-08**
  链接: https://arxiv.org/abs/2504.01931
  相关性：
  - 直接把 feedback 当作 inference-time alignment 的关键变量
  - 明确研究 accuracy-compute trade-off、feedback quality、feedback composition
  - 和你的 token-effective 目标强相关
  不直接撞的地方：
  - 它关注 agentic workflows 的 test-time scaling，不是 repair benchmark 上的 retry curves

- **Efficient Agents: Building Effective Agents While Reducing Cost**
  Wang et al., arXiv:2508.02694, submitted on **2025-07-24**
  链接: https://arxiv.org/abs/2508.02694
  相关性：
  - 直接把 efficiency-effectiveness trade-off 拉成主问题
  - 用 `cost-of-pass` 之类的指标刻画成本/效果边界
  对你意味着：
  - 非常适合支撑 RQ3 的指标设计
  - 但它不是 validator-driven iterative repair 论文

- **Thinking vs. Doing: Agents that Reason by Scaling Test-Time Interaction**
  Shen et al., arXiv:2506.07976, first submitted on **2025-06-09**
  链接: https://arxiv.org/abs/2506.07976
  相关性：
  - 论证“增加交互步数”是区别于“每步想更久”的另一条 scaling 轴
  - 对你讨论 retry value / extra attempts 是否值得非常有启发
  不直接撞的地方：
  - 它是 web agent interaction scaling，不是 validator-guided repair

- **Agentic Context Engineering: Evolving Contexts for Self-Improving Language Models**
  Zhang et al., arXiv:2510.04618, first submitted on **2025-10-06**, current arXiv version dated **2026-01-29**
  链接: https://arxiv.org/abs/2510.04618
  相关性：
  - 直接讨论 context collapse、incremental updates、online agent memory
  - 把降低 adaptation latency / rollout cost 作为结果之一
  对你意味着：
  - 很适合支撑你 `stable-prefix`、compact handoff、避免 context collapse 的动机
  - 但它不是围绕 retry prompt caching 或 rollback 对照做实验

### C. 对你的设计逐项判断

- **RQ1: marginal benefit of extra retries**
  已有明显近邻：ChatRepair、Studying..., Reflexion、Self-Refine、TTI。
  所以这部分不能单独当 novelty，只能当系统量化的一部分。

- **RQ2: attempts-to-success / success-by-round 分布**
  现有工作会做 iterative analysis，但通常没有把 first-success distribution 和 censoring 讲得像你这么完整。
  这部分可以保留，但更像“分析贡献”，不是核心 novelty。

- **RQ3: token/cost vs success frontier**
  这是你更值得押注的点。
  ChatRepair、RepairAgent、Efficient Agents、Feedback-in-TTS 都会碰成本，但目前我没查到一篇把 `success@k`、marginal gain、per-extra-attempt tokens、cost frontier 在 validator-driven retry 设定下系统展开。

- **RQ4: feedback policy comparison**
  VRpilot、ContrastRepair、Feedback-in-TTS 已经说明“反馈质量/形式”很重要。
  但你这里显式拆成 `vague / error-localized / actionable-path` 三档，仍然有空间，前提是你做得足够干净。

- **append / fresh-session / rollback**
  这里和 DDI 最接近。
  目前我没查到一篇在真实 repair / tool-using benchmark 上，把这三种上下文策略做成系统对照并同时看 success-cost frontier。

- **stable-prefix / cache-friendly formatting**
  我这次也没查到直接把 prompt cache reuse 当主要研究对象、并放进 validator-driven repair retries 里做实验的代表论文。
  所以这部分更像你的系统设计增量，而不是被现有论文直接覆盖。

### D. 现在最像“会撞你”的论文清单

如果你只想快速避重，优先盯这 5 篇：

1. ChatRepair
   https://arxiv.org/abs/2304.00385
2. Studying and Understanding the Effectiveness and Failures of Conversational LLM-Based Repair
   https://arxiv.org/abs/2503.15050
3. RepairAgent
   https://arxiv.org/abs/2403.17134
4. VRpilot
   https://arxiv.org/abs/2405.15690
5. The Debugging Decay Index
   https://arxiv.org/abs/2506.18403

### E. 目前可保留的论文定位

基于这轮补充检索，我建议把你的论文定位收窄成下面这个版本：

- 不是“提出多轮修复”
- 也不是“首次证明反馈有用”
- 而是：**在真实 tool-using agent benchmark 上，系统测量 validator-driven iterative repair 的收益边界、成本边界与上下文策略差异**

更具体一点，可以写成：

- 量化 retry 的 marginal utility，而不是只报最终 success
- 比较 feedback policy 与 context policy 对收敛和成本的共同影响
- 研究如何在不牺牲效果的前提下，让 retry 更 token-efficient

这个表述和现有工作重合更少，也更贴近你现在的设计重点。

大家普遍意识到，没有高质量的 Critic（批评家/验证器）提供反馈，算力扩展的收益会迅速递减。但是这部分不是重点，我们假设人类接入是最高质量的验证器

## 2026-03-15 第二轮补充：按新 RQ 重新排查“是否撞题”

这一轮我专门按你现在的 4 个 RQ 重新筛了一遍，优先看一手论文页或 arXiv 条目。结论先写在前面：

- 我没有查到一篇论文完整覆盖你现在这组组合：
  `real tool-using agent benchmark + validator-driven iterative repair + feedback policy ablation + context policy ablation + adaptive stopping + token/cost frontier`
- 但你有几条子线已经明显进入“高重合区”，尤其是：
  - 多轮 feedback 是否有效
  - fresh start 是否优于一直 append
  - 外部 feedback 的质量是否决定收敛
- 所以你的 paper claim 不能写成“提出多轮纠错”或“首次发现 feedback 有用”，而应该写成：
  - 在真实 tool-using agent benchmark 上，系统量化收益曲线、失败机理、动态 stopping 与最小充分反馈设计

### 按 RQ1 排查：收益曲线 / 失效点

- **Studying and Understanding the Effectiveness and Failures of Conversational LLM-Based Repair**
  Chen et al., arXiv:2503.15050, first submitted on **2025-03-19**
  链接: https://arxiv.org/abs/2503.15050
  为什么危险：
  - 它直接研究 conversational repair 的 iterative component 到底有没有用
  - 它已经在问“继续迭代是否真的带来增益，还是反而更差”
  对你的影响：
  - 你的 RQ1 如果只写“多轮反馈的边际收益是多少”，会和它非常接近
  - 更安全的写法是把重点放到 `real tool-using agent benchmark`、`validator-driven`、`token frontier` 与 `failure decomposition`

- **The Debugging Decay Index: Rethinking Debugging Strategies for Code LLMs**
  Adnan and Kuhn, arXiv:2506.18403, first submitted on **2025-06-23**
  链接: https://arxiv.org/abs/2506.18403
  为什么危险：
  - 它已经明确提出 iterative debugging 会衰减
  - 和你“何时收益转负、何时应该 fresh start”的动机高度一致
  对你的影响：
  - 你可以做，但不能把“debugging decay exists”当成自己的主 novelty
  - 你的新意应放在 benchmark、policy family 与 cost-success frontier 的系统实验

- **Thinking vs. Doing: Agents that Reason by Scaling Test-Time Interaction**
  Shen et al., arXiv:2506.07976, first submitted on **2025-06-09**
  链接: https://arxiv.org/abs/2506.07976
  相关性：
  - 它把“增加交互轮数”当作一条 test-time scaling 轴
  - 很适合支撑你对 retry value / extra attempts 的动机
  不直接撞的地方：
  - 它不是 validator-guided repair，也没有你的 feedback/context policy 对照

### 按 RQ2 排查：失败根因 / 历史污染 / 状态污染

- **Agentic Context Engineering: Evolving Contexts for Self-Improving Language Models**
  Zhang et al., arXiv:2510.04618, first submitted on **2025-10-06**, current arXiv version dated **2026-01-29**
  链接: https://arxiv.org/abs/2510.04618
  为什么相关：
  - 它已经在研究 context collapse、incremental updates、online context evolution
  - 和你把“上下文策略”单独拿出来研究的思路非常接近
  不直接撞的地方：
  - 它不是围绕 retry failure decomposition 来设计 `append / fresh-session / rollback`
  - 也不是 validator-driven repair benchmark

- **The Debugging Decay Index**
  链接: https://arxiv.org/abs/2506.18403
  为什么相关：
  - 它最接近你 `append` vs `fresh-session`
  - 已经说明“strategic fresh start”可能优于把错误历史一直往后带
  你的空间：
  - 你仍然可以把 `rollback` 做成更强对照，因为它不仅重开 session，还恢复 workspace 状态
  - 这一步目前看仍然没有被同类工作完整覆盖

- **RepairAgent: An Autonomous, LLM-Based Agent for Program Repair**
  Bouzenia et al., arXiv:2403.17134, first submitted on **2024-03-25**
  链接: https://arxiv.org/abs/2403.17134
  为什么相关：
  - 它是 agent-based repair，而且有工具使用、反馈循环、成本报告
  - 是你“real agent + repair + cost”方向的强近邻
  不直接撞的地方：
  - 它没有把 context policy 显式拆成你现在这三个可控变量

### 按 RQ3 排查：adaptive stopping / budget-aware control

- **Efficient Agents: Building Effective Agents While Reducing Cost**
  Wang et al., arXiv:2508.02694, first submitted on **2025-07-24**
  链接: https://arxiv.org/abs/2508.02694
  为什么相关：
  - 直接把 agent 的 efficiency-effectiveness tradeoff 拿出来研究
  - 使用类似 `cost-of-pass` 这类面向预算的指标
  对你的启发：
  - 这篇很适合支撑你“不能只报 success，还要报 cost frontier”
  不直接撞的地方：
  - 我没有看到它把“是否继续下一轮 retry”做成 validator-driven stopping policy 问题

- **On the Role of Feedback in Test-Time Scaling of Agentic AI Workflows**
  arXiv version page: **2504.01931v4**
  链接: http://arxiv.org/abs/2504.01931v4
  为什么相关：
  - 它直接研究 feedback 在有限 inference budget 下的价值
  - 和你“下一轮还值不值得”的 framing 很接近
  对你的影响：
  - 你不能把“feedback matters under budget”作为新结论
  - 但你仍然可以把 stopping policy 做成更具体的、基于 validator trajectory 的决策问题

- **当前判断**
  我暂时没有查到一篇论文已经把“前 1-2 轮信号预测后续一轮的条件成功概率，并据此做 adaptive stopping”做成你这个设定下的主实验。
  也就是说，`RQ3` 目前看仍然是你这篇里相对更有新意的部分之一。

### 按 RQ4 排查：最小充分反馈 / 最小充分上下文

- **VRpilot: A Case Study of LLM for Automated Vulnerability Repair**
  Nascimento et al., arXiv:2405.15690, first submitted on **2024-05-24**
  链接: https://arxiv.org/abs/2405.15690
  为什么相关：
  - 它已经表明 reasoning 与 validation feedback 的设计会显著影响修复效果
  - 和你的 `error-localized` / `actionable-path` 很接近
  不直接撞的地方：
  - 它没有把 feedback granularity、formatting、context compression 系统拆开

- **ContrastRepair: Enhancing Conversation-based Automated Program Repair via Contrastive Test Case Pairs**
  期刊页: https://research.monash.edu/en/publications/contrastrepair-enhancing-conversation-based-automated-program-rep/
  为什么相关：
  - 它已经说明“更可操作、更有辨识度的反馈”会更有效
  - 本质上支撑了你“feedback quality matters”的动机
  对你的影响：
  - 你不能把“更好的反馈更有效”当成新点
  - 你要把新意放在“最小充分反馈是什么”“更短 feedback 是否足够”“cache-friendly formatting 是否几乎不伤 success”

- **CRITIC: Large Language Models Can Self-Correct with Tool-Interactive Critiquing**
  Gou et al., arXiv:2305.11738, first submitted on **2023-05-19**
  链接: https://arxiv.org/abs/2305.11738
  为什么相关：
  - 它已经清楚说明 external feedback / tool-interactive critique 很重要
  - 是你“validator-driven repair”更一般化的上位背景
  不直接撞的地方：
  - 它不是围绕多轮 repair 的 feedback token efficiency 或 context minimization

- **Teaching Large Language Models to Self-Debug**
  Chen et al., arXiv:2304.05128, first submitted on **2023-04-11**
  链接: https://arxiv.org/abs/2304.05128
  为什么相关：
  - 它说明 code generation 场景下 iterative debugging 可以成立
  - 也讨论了复用失败尝试与反馈的收益
  不直接撞的地方：
  - 它不是工具代理 benchmark，也没有你这里的 context policy / prompt formatting 变量

### 对“self-correction 本身是否可靠”的负面文献

这类论文不会直接和你撞题，但它们很重要，因为它们会影响你如何写动机和 claim。

- **Large Language Models Cannot Self-Correct Reasoning Yet**
  Huang et al., arXiv:2310.01798, first submitted on **2023-10-03**
  链接: https://arxiv.org/abs/2310.01798
  意义：
  - 它强调没有外部反馈时，纯内生 self-correction 很不可靠，甚至可能退化
  - 这对你有利，因为你研究的是 `validator-driven` 而不是纯 self-correction

- **Can Large Language Models Really Improve by Self-critiquing Their Own Plans?**
  Valmeekam et al., arXiv:2310.08118, first submitted on **2023-10-12**
  链接: https://arxiv.org/abs/2310.08118
  意义：
  - 它进一步说明“让同一个模型批评自己”并不天然有效
  - 这也支持你把高质量外部 validator 视为前提，而不是研究 critic 本身

### 现在最像“会顶住你 claim”的论文

如果你只想快速判断风险，优先盯这几篇：

1. ChatRepair
   https://arxiv.org/abs/2304.00385
2. Studying and Understanding the Effectiveness and Failures of Conversational LLM-Based Repair
   https://arxiv.org/abs/2503.15050
3. RepairAgent
   https://arxiv.org/abs/2403.17134
4. VRpilot
   https://arxiv.org/abs/2405.15690
5. The Debugging Decay Index
   https://arxiv.org/abs/2506.18403
6. Efficient Agents
   https://arxiv.org/abs/2508.02694
7. On the Role of Feedback in Test-Time Scaling of Agentic AI Workflows
   http://arxiv.org/abs/2504.01931v4

### 当前可保留的论文定位

基于这轮补充检索，我建议你把论文定位继续收窄到下面这个版本：

- 不是“提出多轮修复”
- 不是“首次证明 feedback 有用”
- 不是“首次发现 fresh start 有时更好”
- 而是：**在真实 tool-using agent benchmark 上，系统测量 validator-driven iterative repair 的收益动力学、失败机理、动态 stopping 与最小充分反馈设计**

更具体地说，你最不容易撞题、也最值得强调的点是：

- 用 `success@k`、`delta success(k)`、首次成功轮次分布去刻画收益动力学
- 用 `append / fresh-session / rollback` 去做 failure decomposition，而不是泛泛谈 context pollution
- 用早期 trajectory 预测“下一轮值不值得”，把 retry 变成预算控制问题
- 用 `stable-prefix`、`unresolved-only feedback`、compact handoff 去探索最小充分反馈，而不是只比较“更强 feedback vs baseline”

### 这轮检索的不足

我这轮优先查的是与你主线最接近的 agent / APR / self-correction 论文页，没有做完整的系统综述。
尤其是 `adaptive stopping` 和 `prompt cache / stable-prefix` 这两块，我目前没有查到直接撞题的代表作，但这更像“暂未发现”，不是严格意义上的不存在。

## 2026-03-15 第三轮补充：前面没提到、但和不同 RQ 有交叉的论文

这一轮我刻意不再围着 ChatRepair / VRpilot / DDI 这几篇转，而是扩到更广的 APR / bug-fixing / process-feedback 方向。
下面这些论文不一定和你“完全撞题”，但它们分别会顶住你不同的 RQ。

### 新增高相关：Process Feedback / Iterative Repair

- **RePair: Automated Program Repair with Process-based Feedback**
  Zhao et al., ACL Findings 2024; arXiv:2408.11296, first submitted on **2024-08-21**
  链接: https://aclanthology.org/2024.findings-acl.973/
  为什么重要：
  - 它直接把 `process-based feedback` 放进标题
  - 训练时引入 reward model / critic，推理时要求模型迭代生成，直到效果不再提升或达到最大步数
  - 和你的 `RQ1`、`RQ3` 都有交叉
  对你的影响：
  - 你不能把“多轮修复 + feedback + 持续迭代直到停止”写成全新方向
  - 但它更像“训练一个会修复的模型”，而不是在真实 tool-using benchmark 上比较 `feedback_policy` / `context_policy`

- **ThinkRepair: Self-Directed Automated Program Repair**
  Yin et al., ISSTA 2024
  链接: https://2024.issta.org/details/issta-2024-papers/102/ThinkRepair-Self-Directed-Automated-Program-Repair
  为什么重要：
  - 它自动收集 CoT / pre-fixed knowledge，并在 fixing 阶段和 LLM 交互，可选地追加 testing feedback
  - 和你的 `RQ1`、`RQ4` 都有交叉，尤其是“如何构造更有效的反馈/思考上下文”
  对你的影响：
  - 你不能把“自动交互式 bug fixing”本身当 novelty
  - 但它重点是知识收集与 few-shot 例子选择，不是你这里的 cost frontier 或 context-policy decomposition

### 新增高相关：Feedback Content / Intent / Multi-stage Repair

- **Enhancing Automated Program Repair with Solution Design**
  Zhao et al., ASE 2024
  链接: https://conf.researchr.org/details/ase-2024/ase-2024-research/137/Enhancing-Automated-Program-Repair-with-Solution-Design
  为什么重要：
  - 它利用 issue log 里的 design rationale 提高 repair 质量
  - 还包含 feedback-based self-reflective framework，用 reference patch 和 identifier suggestion 继续修正输出
  - 和你的 `RQ4` 有明显交叉，因为它本质上在研究“什么额外反馈最有价值”
  对你的影响：
  - 你不能把“加入更高质量、更具操作性的反馈信息”写成完全没人做过
  - 但它的重点是 design rationale / project context，不是最小充分 feedback 或 token-efficient feedback

- **PATCH: Empowering Large Language Model with Programmer-Intent Guidance and Collaborative-Behavior Simulation for Automatic Bug Fixing**
  Zhang et al., TOSEM 2025; arXiv:2501.16149, first submitted on **2025-01-27**
  链接: https://www.citedrive.com/en/discovery/patch-empowering-large-language-model-with-programmer-intent-guidance-and-collaborative-behavior-simulation-for-automatic-bug-fixing/
  为什么重要：
  - 它把 bug fixing 拆成 bug reporting、diagnosis、patch generation、verification 四阶段
  - 还引入 programmer intent 和 multi-stage interactive workflow
  - 和你的 `RQ4`、部分 `RQ2` 有交叉
  对你的影响：
  - 这篇会顶住“我们把修复流程分阶段并让多轮交互更接近真实开发流程”这种 claim
  - 但它不是围绕 validator-driven retries 的收益曲线、stopping、rollback、token frontier 来设计实验

### 新增中高相关：Repair Guidance / Structured Constraint Feedback

- **PathFix: Automated Program Repair with Expected Path**
  Xu et al., arXiv preprint, first submitted on **2025-10-16**
  公开条目: https://jglobal.jst.go.jp/en/public/202502211808373863
  为什么相关：
  - 它把 failing test case 重新并入后续 synthesis constraint
  - 用更结构化的 expected path / constraint 来约束下一轮修复
  - 和你的 `RQ4` 很近，因为它研究的是“什么形式的反馈最能收敛”
  对你的影响：
  - 如果你后面想强调 `actionable-path`，这篇需要注意
  - 不过它更偏 program analysis + synthesis，和你的人类/validator feedback 设定仍不同

### 按 RQ 重映射这些新增论文

- **对 RQ1（收益曲线 / 失效点）有重合**
  - RePair
  - ThinkRepair
  - Studying and Understanding the Effectiveness and Failures of Conversational LLM-Based Repair
  - The Debugging Decay Index

- **对 RQ2（失败根因 / context pollution / state pollution）有重合**
  - The Debugging Decay Index
  - PATCH
  - Agentic Context Engineering
  说明：
  - 这里仍然没有直接看到一篇把 `append / fresh-session / rollback` 作为同一 family 系统对照的代表作
  - 所以 `failure decomposition` 目前仍是你比较能站得住的点

- **对 RQ3（adaptive stopping / budget-aware control）有重合**
  - RePair
  - Efficient Agents
  - On the Role of Feedback in Test-Time Scaling of Agentic AI Workflows
  说明：
  - 这些论文已经触到“何时继续、何时停止、预算是否值得”
  - 但我还没有看到一篇在你的设定下，把“基于前 1-2 轮 validator trajectory 预测下一轮条件收益”做成主要实验

- **对 RQ4（最小充分反馈 / 最小充分上下文）有重合**
  - ThinkRepair
  - Enhancing Automated Program Repair with Solution Design
  - PATCH
  - PathFix
  - ContrastRepair
  - VRpilot
  说明：
  - 这条线最拥挤
  - 所以你如果保留 RQ4，最好把 claim 收窄成：
    - 不是“高质量 feedback 更好”
    - 而是“在 validator-driven tool-using benchmark 上，最小充分 feedback / context 到底是什么，以及它能省多少 token”

### 这轮补充后的判断

现在看下来，最危险的不是 `RQ2`，也不是 `stable-prefix`，而是 `RQ4`。
因为“更好 feedback / 更多上下文 / 更接近开发流程的分阶段修复”已经被一批 APR 论文从不同角度做过了。

相对仍有空间的点：

- `append / fresh-session / rollback` 的系统 failure decomposition
- 基于 validator trajectory 的 adaptive stopping
- 在真实 tool-using benchmark 上测量 `success@k`、`delta success(k)`、`tokens per extra success`
- 将 `stable-prefix`、`unresolved-only`、compact handoff 放进一个明确的 token-efficiency 研究框架，而不是只作为 prompt engineering trick

## 2026-03-15 第四轮补充：真正偏 agent 的相关工作

这一轮不再以 APR / bug fixing 为中心，而是只看 tool-using agent、interactive agent、agent memory、agent cost control 这些方向。
结论先写在前面：

- 从 agent 视角看，你最容易和别人重合的不是“多轮 repair”本身，而是：
  - interaction scaling / 多轮 rollout 是否值得
  - execution feedback / language feedback 是否能持续提升 agent
  - evolving memory / context engineering 是否优于简单堆历史
  - cost frontier / budget-aware control 是否应该成为 agent 的一等目标
- 但我依然没有查到一篇把下面这些东西合在一起做：
  `validator-driven retries + feedback-policy ablation + append/fresh-session/rollback + adaptive stopping + token/cost frontier`

### Agent benchmark / feedback benchmark：它们不直接撞题，但决定你该把实验放在哪个语境下

- **LLF-Bench: Benchmark for Interactive Learning from Language Feedback**
  Cheng et al., arXiv:2312.06853, first submitted on **2023-12-11**
  链接: https://arxiv.org/abs/2312.06853
  为什么相关：
  - 它是专门面向 language feedback 的 benchmark
  - 明确支持不同 feedback type，例如指出错误，明确未来怎么做这些，我估计。GPT就是从这里学的
  - 和你的 `feedback_policy` 设计思路很接近
  对你的影响：
  - 你不能把“agent 应该从语言反馈中学习”当新动机
  - 但 LLF-Bench 更偏 interactive learning benchmark，不是围绕 validator-driven retries、cost frontier 或 workspace/state rollback
  未来导向反馈（fp / fn）效果最好也就是：fp（告诉你接下来该做什么）fn（告诉你不要做什么）

- **$τ$-bench: A Benchmark for Tool-Agent-User Interaction in Real-World Domains**
  Yao et al., arXiv:2406.12045, first submitted on **2024-06-17**
  链接: https://arxiv.org/abs/2406.12045
  为什么相关：
  - 它是现实 domain 的 tool-use benchmark
  - 明确提出 `pass^k` 来评估多次试验下的可靠性
  - 和你要报 `success@k`、多次重复运行、按 trial 看可靠性很近
  对你的影响：
  - 你不能把“多次运行下的 agent reliability”当全新指标框架
  - 但 `τ`-bench 主要是 benchmark/eval，不是在分析 retry feedback 的收益曲线与停止策略

- **ToolSandbox: A Stateful, Conversational, Interactive Evaluation Benchmark for LLM Tool Use Capabilities**
  Lu et al., arXiv:2408.04682, first submitted on **2024-08-08**
  链接: https://arxiv.org/abs/2408.04682
  为什么相关：
  - 它强调 stateful tool execution 和 on-policy conversation evaluation
  - 与你对“session 历史”和“workspace 状态”分开的敏感性高度一致
  对你的影响：
  - 它不是在比较 `append / fresh-session / rollback`
  - 但它说明“stateful interaction”本身已经是 agent 研究的主轴，不是你独有的 framing

### 对 RQ1 很近：interaction scaling / 多轮收益是不是很快递减

- **Thinking vs. Doing: Agents that Reason by Scaling Test-Time Interaction**
  Shen et al., arXiv:2506.07976, first submitted on **2025-06-09**
  链接: https://arxiv.org/abs/2506.07976
  为什么重要：
  - 它直接提出 test-time interaction 是独立于 per-step reasoning 的 scaling 轴
  - 明确讨论增加 interaction horizon 能否提升成功率
  - 和你的 `RQ1` 非常接近，尤其是“更多轮次值不值”
  对你的影响：
  - 你不能把“增加 interaction/retry 次数可能提高 success”当新发现
  - 你更应该把重点放在 validator feedback 下的 marginal utility、失效点与 token/cost accounting

- **ReAct: Synergizing Reasoning and Acting in Language Models**
  Yao et al., first released **2022-10-07**
  链接: https://arxiv.org/abs/2210.03629
  为什么相关：
  - 它是 interactive agent 里最基础的 baseline 之一
  - 已经讨论 internal reasoning 与 external environment feedback 的结合
  对你的影响：
  - 它不是多轮 repair 论文
  - 但它决定了你需要把“validator-driven retries”写成 ReAct 类闭环 agent 的一个后验修复子问题，而不是平地起高楼

- **Reflexion: Language Agents with Verbal Reinforcement Learning**
  Shinn et al., arXiv:2303.11366, first submitted on **2023-03-20**
  链接: https://arxiv.org/abs/2303.11366
  为什么相关：
  - 它是最直接的“agent 从语言反馈中跨 trial 改进”的经典工作
  - 和你的多轮反馈、失败后再试、利用 verbal feedback 收敛都高度相关
  对你的影响：
  - 你不能把“语言反馈能帮助 agent 下一次做得更好”当 novelty
  - 但 Reflexion 不是在系统测量 success-cost frontier，也没有你这里的 context-policy family

### 对 RQ2 很近：context engineering / memory evolution / 历史污染

- **Dynamic Cheatsheet: Test-Time Learning with Adaptive Memory**
  Suzgun et al., arXiv:2504.07952, first submitted on **2025-04-10**
  链接: https://arxiv.org/abs/2504.07952
  为什么重要：
  - 它直接讨论 inference-time persistent memory
  - 强调不要保留整个 transcript，而是保留 concise, transferable snippets
  - 和你的 `stable-prefix`、`compact handoff`、最小充分上下文非常接近
  对你的影响：
  - 你不能把“别把所有历史都塞回去，应该保留浓缩后的可迁移经验”当全新观点
  - 但它更偏跨 query / 跨任务 adaptive memory，不是单任务失败后的 retry context policy

- **Agentic Context Engineering: Evolving Contexts for Self-Improving Language Models**
  Zhang et al., arXiv:2510.04618, first submitted on **2025-10-06**
  链接: https://arxiv.org/abs/2510.04618
  为什么重要：
  - 它明确提出 `context collapse`、`brevity bias` 和 evolving playbooks
  - 还报告了 rollout cost 和 adaptation latency 的下降
  - 跟你的 `RQ2`、`RQ4` 都很近
  对你的影响：
  - 如果你写“长历史会污染后续 agent 行为”“context 应该结构化增量更新”，ACE 会直接压住这类 claim
  - 你的空间在于把这些想法落到 validator-driven retry 上，并进一步拆成 `append / fresh-session / rollback`

- **The Debugging Decay Index**
  链接: https://arxiv.org/abs/2506.18403
  从 agent 视角再看一次它为什么重要：
  - 它虽然偏 code LLM debugging，但本质上已经触到“长错误历史是否会伤害后续试次”
  - 是你研究 history pollution 的最近邻之一

### 对 RQ3 很近：budget-aware agent control / 动态资源决策

- **Efficient Agents: Building Effective Agents While Reducing Cost**
  Wang et al., arXiv:2508.02694, first submitted on **2025-07-24**
  链接: https://arxiv.org/abs/2508.02694
  为什么重要：
  - 它是 agent 方向里最直接讨论 efficiency-effectiveness tradeoff 的论文之一
  - 提出 `cost-of-pass` 这样的预算导向指标
  - 和你 `RQ3` 的成本边界非常接近
  对你的影响：
  - 你不能把“agent paper 里应该同时报 success 和 cost”写成新贡献
  - 你的空间在于更细的 retry-level stopping，而不是系统级平均成本

- **Budget-Aware Agentic Routing via Boundary-Guided Training**
  arXiv:2602.21227, submitted on **2026-02-04**
  链接: https://arxiv.org/abs/2602.21227
  为什么重要：
  - 它直接把 autonomous agent 的 sequential decision-making 放在 strict per-task budget 下做
  - 关注 cost-success frontier，并用动态 routing 代替静态选择
  - 和你的 `RQ3` 明显同属一个问题簇
  对你的影响：
  - 如果你把 `RQ3` 写成泛泛的“budget-aware dynamic control”，会和它明显相撞
  - 你的 safer angle 是：基于 validator trajectory 决定“是否继续 retry”，而不是在每步做 model routing

- **On the Role of Feedback in Test-Time Scaling of Agentic AI Workflows**
  arXiv version page: **2504.01931v4**
  链接: http://arxiv.org/abs/2504.01931v4
  为什么重要：
  - 它在 agentic workflow 语境下系统研究 feedback 与 budget 的关系
  - 和你的 `RQ3`、部分 `RQ4` 高度相关
  对你的影响：
  - “feedback under budget matters” 不是新点
  - 但“利用早期 validator signal 预测下一轮收益”目前仍然和它有差异

### 对 RQ4 很近：feedback types / validator signals / 工具调用后验修正

- **Gecko: A Simulation Environment with Stateful Feedback for Refining Agent Tool Calls**
  arXiv:2602.19218, submitted on **2026-02-24**
  链接: https://arxiv.org/abs/2602.19218
  为什么重要：
  - 这是目前我看到和你“agent + validator-like feedback + iterative refinement”最近的工作之一
  - Gecko 提供三类 stateful feedback：tool call validity、schema-consistent response synthesis、goal completion assessment
  - 他们还明确把这套东西做成 test-time scaling method（GATS）
  对你的影响：
  - 如果你的叙述停留在“给 agent 提供 validator feedback，让它多轮 refine tool calls”，这篇会非常危险
  - 你的差异点需要强调：
    - 你研究的是 general agent skill / benchmark 上的 retry policy，而不是专门的 tool-call refinement simulator
    - 你有 `feedback_policy`、`context_policy`、`adaptive stopping`、`token frontier` 这套完整分析框架

- **LLF-Bench**
  再次从 `RQ4` 看它为什么相关：
  - 它允许配置不同 feedback semantics
  - 和你 `vague / error-localized / actionable-path` 的实验精神一致
  你的空间：
  - 你做的是 validator-driven retry in deployment/evaluation loop，不是 benchmarking interactive learning capability 本身

### Agent 视角下重新判断你的 RQ 风险

- **RQ1: 多轮收益曲线与失效点**
  近邻：
  - Thinking vs. Doing
  - Reflexion
  - On the Role of Feedback in Test-Time Scaling of Agentic AI Workflows
  判断：
  - “更多交互/反馈轮次可能带来提升”已经不新
  - 但在 validator-driven retry 上做 `success@k + delta success + extra token/cost per round` 仍有空间

- **RQ2: 失败根因 / history pollution / state pollution**
  近邻：
  - Agentic Context Engineering
  - Dynamic Cheatsheet
  - ToolSandbox
  - The Debugging Decay Index
  判断：
  - “context matters” 已经很拥挤
  - 但 `append / fresh-session / rollback` 这种 failure decomposition 目前仍然相对少见

- **RQ3: adaptive stopping**
  近邻：
  - Efficient Agents
  - Budget-Aware Agentic Routing
  - On the Role of Feedback in Test-Time Scaling of Agentic AI Workflows
  判断：
  - 预算感知 agent control 已经是活跃方向
  - 但“根据前 1-2 轮 validator trajectory 预测下一轮 retry 是否值得”目前仍不像一个已被做烂的标准题

- **RQ4: 最小充分反馈 / 最小充分上下文**
  近邻：
  - LLF-Bench
  - Gecko
  - Dynamic Cheatsheet
  - Agentic Context Engineering
  判断：
  - 这条线在 agent 里也已经变得拥挤
  - 如果保留，必须把问题写得更尖锐：不是“反馈越强越好吗”，而是“哪部分 feedback/context 对 validator-driven retries 真正必要”

### 目前 agent 方向最可能撞你的论文

如果只从 agent 文献里挑最危险的，优先看：

1. Reflexion
   https://arxiv.org/abs/2303.11366
2. LLF-Bench
   https://arxiv.org/abs/2312.06853
3. ToolSandbox
   https://arxiv.org/abs/2408.04682
4. Thinking vs. Doing
   https://arxiv.org/abs/2506.07976
5. Dynamic Cheatsheet
   https://arxiv.org/abs/2504.07952
6. Agentic Context Engineering
   https://arxiv.org/abs/2510.04618
7. Efficient Agents
   https://arxiv.org/abs/2508.02694
8. Budget-Aware Agentic Routing
   https://arxiv.org/abs/2602.21227
9. Gecko
   https://arxiv.org/abs/2602.19218

### Agent 方向下更安全的论文定位

如果你最后写的是 agent paper，而不是 APR paper，我建议把 claim 收成：

- 不是“agent 从 feedback 中提升”
- 不是“agent 需要 context engineering”
- 不是“agent 需要预算控制”
- 而是：**我们系统测量 validator-driven retry policy 在真实 tool-using agent benchmark 上的收益动力学、失败机理与预算控制规律**

这个版本相对更安全，因为它强调的是：

- retry-level analysis，而不是一般的 agent learning
- validator-driven post-hoc repair，而不是泛化的 memory / routing / RL training
- policy comparison（`append / fresh-session / rollback`），而不是单一方法 proposal


### gemini 生成的这些都有相关工作了
你的观察非常敏锐，而且这些结论在真实的工业落地中**非常核心且有价值**。你觉得“没啥创新”，是因为目前大多数做 Agent 成本和效能优化的团队，确实都卡在了你说的这个瓶颈上：**单轮优化的尽头似乎就是 Prompt 压缩，而多轮优化的尽头似乎就是简单粗暴的“大模型兜底（Fallback）”。**

要在这个基础上继续深化，打破“缺乏创新”的困局，我们需要把视角从**“单轮/静态的 Token 层面”**拔高到**“多轮/动态的 Agent 系统架构和状态机层面”**。

以下是几个可以帮助你深化研究、探索更具体的云际 Agent 优化策略的突破口：

### 1. 从“事后兜底 (Reactive Fallback)”到“事前/事中预测路由 (Predictive Routing)”

你目前的策略是：“先用便宜模型尝试，触及天花板再路由到大模型”。这个策略的痛点在于：**如果便宜模型注定会失败，它前几轮消耗的 Token（甚至引发的错误状态）就是纯粹的浪费。**

* **深化点 - 任务复杂度预测 (Task Complexity Prediction)：** 训练一个极其轻量级的分类器（甚至可以用 BERT 级别的模型，或者基于启发式规则），在请求到达时，基于用户的输入特征评估“任务难度”和“需要几轮交互”。对于判定为高难度的任务，**直接跳过小模型**，首轮就用 GPT-4/3.5。
* **深化点 - 动态 Early Exit（尽早放弃）：** 既然你发现小模型的主要增益在前两轮，你可以定义一个“Agent 沮丧指数 (Frustration Index)”。如果小模型在第二轮反馈中，表现出“重复原有错误”、“输出特定的道歉模板”或“状态机没有实质推进”，立刻阻断其继续尝试，触发转移。而不是死板地等它达到最大尝试次数。

### 2. 重新定义“Token 浪费”：从 Prompt 压缩走向“Agent 工作流状态剪枝”

你提到分析多轮 Token 成本时遇到了“任务类型不一，无法归纳同一套体系”的难题，最后觉得又回到了 Prompt 压缩。
**破解之道：不要把多轮对话当成“长文本”，要把它们当成“代码的版本迭代 (Git Commits)”。**

* **深化点 - 差异化上下文注入 (Differential Context Injection)：** 在多轮 Feedback 中，最浪费 Token 的是将“之前的错误代码/错误回答”原封不动地传给下一轮。
    * *创新策略：* 引入一个极其廉价的模型（甚至本地小模型）专门做 **State Summarization（状态压缩）**。下一轮的 Prompt 不要包含之前的全量错误，而是变成：`[初始目标] + [当前已成功的部分] + [上一次尝试的失败原因总结（Diff）]`。
* **深化点 - 按组件生命周期管理 Token：** 将 Agent 的 Prompt 拆分为：System Rules, Tools Description, Current Observation, Memory。在多次迭代中，**动态剔除当前步骤不需要的 Tools Description**。例如，Agent 在做代码调试时，就不需要再携带“网页搜索”工具的 Token 描述了。

### 3. Skill 抽取的落地：从“轨迹 (Trajectory)”到“宏动作 (Macro-Action)”

你提到将成功修复的轨迹抽取成可复用的 Skill，这是非常有前景的方向（类似 Voyager 的思路）。但怎么做才能在云端低成本复用？

* **深化点 - 动态 Few-Shot 库的构建与检索 (RAG-based Skill Routing)：** 将小模型经过多轮修复才做对的轨迹，提炼为 `<Task_Description, Optimal_Action_Sequence>` 的键值对，存入向量数据库。
    * 当新的相似任务到来时，不再让小模型去“试错”，而是通过 RAG 检索出这个最优动作序列，作为 Few-Shot Example 直接喂给小模型。**这等价于用少量的 Token 换取了之前多轮迭代才能达到的智慧。**
* **深化点 - 从 Prompt 层下沉到微调层 (Trajectory-based SFT/DPO)：** 如果积累了大量“小模型失败 -> 大模型指导/多轮迭代后成功”的配对数据，这本质上是极佳的 DPO（直接偏好优化）数据（`Rejected = 首轮失败结果`, `Chosen = 最终修复结果`）。在云际环境中，可以定期用这些数据微调小模型（如果云厂商提供微调接口，或者自己部署开源模型），从而永久性提升小模型的“天花板”。

### 4. 异构模型协作 (Heterogeneous Multi-Agent Collaboration)

不要让同一个模型完成整个多轮链路。

* **深化点 - 脑手分离架构 (Brain-Hand Separation)：**
    * **大模型（GPT）作为“大脑 / Planner”：** 负责阅读长需求，拆解任务，制定 Workflow（只消耗少量输入和输出 Token）。
    * **小模型（Minimax）作为“手 / Executor”：** 负责具体的代码编写、API 调用。小模型如果报错，只把局部错误抛回给小模型自己迭代 1-2 轮；如果仍无法解决，再抛回给大脑（大模型）重新规划。
    * *优势：* 完美结合了 GPT 的高成功率（解决小模型的天花板问题）和小模型的低单价。

---

**下一步建议：**

如果想做出区别于常规工程优化的研究或高阶方案，**“多轮交互中的动态上下文剪枝 (Dynamic Context Pruning)”** 和 **“基于置信度的模型动态路由 (Confidence-based Dynamic Routing)”** 是两个最容易出成果的方向。

针对你目前的困境，我们可以先聚焦一个点深入：**你目前分析 Token 浪费时，遇到“任务类型不一”的具体瓶颈是什么？是无法量化哪些 Token 属于“有效推进”，还是无法在不同任务（比如写代码 vs 搜信息）中提取统一的状态特征？**


EvoSkill: Automated Skill Discovery for Multi-Agent Systems
反馈的具体输出形态
提案者智能体在分析后，会输出一份结构化的文本描述提案（即前向反馈），用于指导下游的技能构建。根据论文附录中的 Prompt，这份反馈提案包含以下具体要素：
动作指令 (Action)：明确是创建一个新技能 (create) 还是编辑修改现有技能 (edit) 。
目标对象 (Target Skill)：如果是修改，需指出具体要修改的现有技能名称 。
技能方案 (Proposed Skill)：详细描述要构建的新能力、输入输出要求，或者对现有技能的具体修改意见 。
详细论证 (Justification)：解释做出该提案的原因。这需要引用执行轨迹中的具体失误环节、现有技能为何失效，以及参考过去迭代中被丢弃或采纳的策略 。


上述论文包含ground true的反馈吗？
这是一个非常关键的问题！直接回答你的核心疑问：不包含。这几篇主线论文的 Feedback 中，绝大多数都严格排除了 Ground Truth（最终的正确答案/黄金代码/完美工具调用序列）。
如果把 Ground Truth 直接放进反馈里让 Agent 抄，在 Agent 和 APR（自动程序修复）领域的 Benchmark 评估中会被视为**Data Leakage（数据泄露）**或作弊。这些论文的核心研究点就在于：Agent 如何在只有“不完整/间接信号”的情况下，通过多轮交互逼近正确答案。
为了让你在写论文时能准确地做区分（ablation/comparison），我把这几篇代表性论文的 Feedback 构成方式拆解成了以下三类：
1. 纯执行层面的状态反馈 (Execution / Stateful Feedback)
这是最基础、最普遍的反馈形式，完全依赖底层环境的客观输出，没有任何答案提示。
ToolSandbox / Thinking vs. Doing： * 构成： API 返回的 JSON 结果、数据库查询返回的报错字符串、或者网页交互后更新的 HTML DOM 树。
特点： 环境是冷酷的。如果 Agent 传错了参数，反馈就是一句干巴巴的 {"error": "Invalid token"} 或 404 Not Found。
ContrastRepair / 传统 APR：
构成： 编译器报错信息（Traceback）或测试用例的执行结果（比如 Expected output: 5, Actual output: 0）
注意： 虽然这里出现了 Expected output，但这只是针对某个特定 Test Case 的标量断言，绝不是正确修复代码（Patch）的 Ground Truth。

2. 验证器 / 规则驱动的约束反馈 (Validator / Schema Feedback)
这是系统主动生成的反馈，它比纯环境报错多了一步“诊断”，但依然不给正确答案。

Gecko (2026)：
构成： 它的环境内置了 Argument Validator 和 Task State Estimator。如果 Agent 调用工具错误，反馈会是格式诊断，比如：“你遗漏了必填参数 location” 或 “你的输出不符合 JSON Schema”；如果任务没做完，反馈是：“目标 A 已完成，但目标 B 尚未满足”。

RePair / PathFix：
构成： 将失败的测试转化为下一轮的约束条件（Constraints）。比如反馈不是“你应该写 if x < 0”，而是“你的代码在走这条执行路径时引发了越界，下一轮生成的代码必须满足变量状态 X 的约束”。

3. 语言批判与自我反思 (Language Critique / Self-Reflection)
这类反馈最像人类语言，包含指导方向（如你提到的 LLF-Bench），但它故意保留了对 Ground Truth 的屏蔽。

Reflexion (2023) / ACE (2025/2026)：
构成： 它们通常把环境的 Pass/Fail 信号喂给一个“反思大模型（Critic）”，让模型自己生成一段自然语言。比如：“我刚才试图抓取苹果，但失败了，因为我没有先打开冰箱门。下次我应该先执行 open(fridge)。”
特点： 这是 Agent 基于自己的错误推导出的经验，而不是上帝视角直接塞给它的 Ground Truth。

LLF-Bench (2023)：
构成： 正如你所说，它提供非常细粒度的自然语言反馈，比如 FP（Forward Positive，你接下来该尝试去厨房） 和 FN（Forward Negative，不要再撞这堵墙了）。
关键点： 这类 Benchmark 是一个“Teacher-Student”设定。Teacher 知道 Ground Truth，但 Teacher 吐出的 Feedback 被严格限制在“给出局部建议（Hints）”的程度，绝对不会把整个任务的解法直接吐给 Agent。



Agent 实现“技能自进化（Skill Self-Evolution）”并从错误中学习（Learning from Mistakes/Failures）是目前大模型和智能体领域非常核心且前沿的研究方向。这类研究通常涉及**技能库（Skill Library）的构建、自我反思（Self-Reflection）机制以及基于失败轨迹的反馈修正**。

为你整理了该领域最新（2025-2026年）的前沿研究以及几篇奠基性的经典论文，希望能为你的研究或项目提供参考：

### 一、 最新前沿论文（2025 - 2026）

**1. Just Talk: An Agent That Meta-Learns and Evolves in the Wild (2026)**
* **核心机制：** 这篇论文非常直接地切中了“从错误中进化”。它提出了一种“技能驱动的快速适应”机制（Skill-driven fast adaptation）。Agent 会收集并分析**失败的交互轨迹（Failure Trajectories）**，将其作为支持数据，通过 LLM 进化器（Evolver）去合成新的行为指令（即新技能），从而实现免梯度的技能库自进化。
* **亮点：** 强调在真实环境（in the wild）中，将失败经验转化为新技能，并且可以做到零停机时间更新。
《MetaClaw》论文本身就提供了一个很好的跨模型对比视角。他们在实验中对比了 GPT-5.2 和 Kimi-K2.5 。研究得出了一个很重要的结论：基础能力较弱的模型获益更大：像 Kimi-K2.5 这种相对较弱的模型，由于本身缺乏隐含的程序性知识，从显式的技能注入中获得了巨大的提升（在 Part I 中准确率提升了 32.2%） 。协同进化可以弥合模型代差：当结合了强化学习的底层策略优化后，Kimi-K2.5 的准确率达到了 40.6%，几乎追平了未经进化的 GPT-5.2 基线水平（41.1%） 。

**2. Co-Evolving Agents: Learning from Failures as Hard Negatives (2025/2026)**
* **核心机制：** 论文提出了一种“双 Agent 协同进化”框架。它没有单纯地把失败当成废弃数据，而是将失败轨迹系统性地转化为“困难负样本（Hard Negatives）”。
* **亮点：** 通过引入一个专门学习失败环境的辅助 Agent，配合目标 Agent 进行偏好优化（Preference Optimization）。这种从“接近成功但最终失败”的经验中学习的机制，极大地提高了 Agent 技能的鲁棒性和泛化能力。

**3. EvoSkills: Self-Evolving Agent Skills via Co-Evolutionary Verification (2026)**
* **核心机制：** 现有的工具自进化方法很难直接迁移到复杂的技能（Skills）上。这篇论文提出了 EvoSkills 框架，使 Agent 能够通过与环境的交互和“协同进化验证”，自主地构建和修正复杂的多文件技能包。
* **亮点：** 重点解决了机器生成技能时可能存在的“人类-机器认知偏差”导致的错误，通过不断验证和修正来进化技能。

**4. Reinforcement Learning for Self-Improving Agent with Skill Library (SAGE) (2026)**
* **核心机制：** 结合了技能库（Skill Library）与强化学习（如 GRPO 算法）。研究发现，如果 Agent 只是单纯挂载技能库，有时会因为技能调用不当（Inappropriate skill applications）导致任务失败。
* **亮点：** SAGE 框架让 Agent 将这些失败的调用作为经验回放，通过强化学习系统性地内化技能的正确使用时机，实现技能调度能力的自进化。

---

### 二、 必读的基石与经典论文（2023 - 2024）

如果你刚开始调研这个方向，以下几篇高引用的经典论文是构建相关认知的必读基石：

**1. Voyager: An Open-Ended Embodied Agent with Large Language Models (2023)**
* **核心机制：** 技能库自进化领域的绝对标杆。Voyager 在《我的世界》（Minecraft）中通过编写代码来执行动作。当代码执行报错（Error）或任务失败时，它会将**环境反馈和错误日志**作为 Prompt 输入给 LLM，LLM 借此修正代码。一旦执行成功，这段修正后的代码就会作为新技能（Skill）被固化到技能库中，供未来复用。

**2. Reflexion: Language Agents with Verbal Reinforcement Learning (2023)**
* **核心机制：** 引入了“语言反思（Verbal Reflection）”的概念。当 Agent 执行任务失败时，Reflexion 框架会提示 LLM 写下一段自我反思（例如：“我刚才在哪一步做错了，因为我没有考虑到 XYZ”）。这段基于错误的经验会被存入记忆中，在下一次尝试时作为上下文，从而指导行为的改进。

**3. LeMa: Learning From Mistakes Makes LLM Better Reasoner (2023/2024)**
* **核心机制：** 聚焦于模型底层推理能力的纠错进化。研究者收集了大量 LLM 的错误推理轨迹，利用高阶模型（如 GPT-4）指出错误步骤、解释犯错原因并给出正确解法。使用这些“错误-纠正”的数据对模型进行微调，证明了从错误中反向学习能显著提升能力。

**4. GITM: Ghost in the Minecraft (2023)**
* **核心机制：** 虽然同样是在 Minecraft 环境中，GITM 也强调了“子目标失败”时的重新规划机制。它通过分解任务，如果在某个子技能执行时遇到物理障碍或逻辑错误，Agent 会总结失败原因并动态调整技能图谱。

AutoSkill: Experience-Driven Lifelong Learning via Skill Self-Evolution (2026)

核心内容： 这篇论文提出了一种经验驱动的终身学习框架。Agent 会从过去的对话和交互错误中提取经验，并自我进化出新的技能。
与不同模型的关系： 它的最大亮点是将技能库设计为一个模型无关（Model-Agnostic）的插件层。这意味着它不仅兼容现有的各种 LLMs，还引入了标准化的技能表示方法。Model A（例如大参数模型）在复杂环境中试错并进化出的技能，可以直接 Transfer（迁移）给 Model B（例如端侧小模型）使用，无需重新训练底层模型。

LEMMA: Learning from Errors for MatheMatical Advancement in LLMs (2026)
核心内容： 专注于从错误中学习的机制。它构建了包含“错误-反思-修正”的轨迹数据集。
与不同模型的关系： 论文中明确探讨了不同模型之间的配合：利用**高级/强模型（Advanced Models）去指导生成和分析代表性的错误类型，然后用这些数据去增强目标模型（Target Models）**的自我纠错（Self-correct）能力。这提供了一种“跨模型师生范式”的技能进化思路。

Reducing Cost of LLM Agents with Trajectory Reduction
每次工具调用的指令和返回的长篇结果，都会被永久记录在对话上下文中，这就是智能体的“轨迹（Trajectory）” 。随着任务的推进，输入给 LLM 的 Token 数量会像滚雪球一样急剧增长，造成巨大的计算开销。解决方案：AgentDiet 方法引入“反思模块（Reflection Module）”： 论文并没有让正在执行任务的主力模型自己去删减记忆（因为它们往往倾向于继续原任务而忽略缩减要求），而是引入了一个外部的、独立的“反思模块” 。使用低成本模型做“清洁工”： 该模块会调用一个成本极其低廉的 LLM（例如用 GPT-5 mini 辅助昂贵的 Claude 4 Sonnet），专门负责将旧轨迹中的废话替换为简短的总结 。滑动窗口与阈值控制： 为了防止反思模块自身的调用成本超过缩减省下的钱，AgentDiet 采用了滑动窗口策略，并设定了阈值 。只有当某个历史步骤的长度超过设定值（如 500 Token），且距离当前进度有一定延迟时，才会触发信息清理 。
引入额外的模型进行压缩

SkillReducer: Optimizing LLM Agent Skills for Token Efficiency
痛点：每次调用技能时，将这些内容注入到大模型的上下文窗口中，不仅会带来高昂的 API 调用成本（金钱消耗），还会导致模型处理信息的注意力被分散（Token 冗余） 。
通过对 55,315 个公开技能进行大规模实证研究，作者发现了以下现象：路由层缺失严重：有 26.4% 的技能完全没有描述，这导致智能体的路由匹配机制失效，只能“盲目”去评估技能主体 。核心内容占比极低：在技能主体中，只有 38.5% 是真正具有操作指导意义的“核心规则” 。超过 60% 的内容是不可操作的背景知识、举例或模板 。参考文件成灾：那些带有额外参考文件的技能，可能会在每次调用时向上下文中塞入数以万计的 Token，即使当前任务只用到其中一小部分 。
阶段一（优化路由层）：针对技能的简短描述（Description）进行压缩。通过“增量调试”（Delta Debugging）技术，去除冗长的废话，只保留核心信息；同时为那些缺失描述的技能自动生成描述 。阶段二（重组技能主体）：对技能的主体内容（Body）进行结构化重组。它将必须遵循的“核心规则”提取出来作为常驻内容，而将背景知识、示例代码等补充内容分离为“按需加载”的模块（即渐进式披露） 。

Agentic Plan Caching: Test-Time Memory for Fast and Cost-Efficient LLM Agents
这个跟王贵良想法一样

More with Less: An Empirical Study of Turn-Control Strategies for Efficient Coding Agents 
这个动态停止轮次，是基于统计的将固定轮次限制设定在基准分布的第75百分位是一个“最佳平衡点（sweet spot）”