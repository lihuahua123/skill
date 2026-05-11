## Ⅰ. 核心近邻：多轮修复与反馈机制 (RQ1, RQ4)
这类论文是你的“主战场”，它们证明了多轮反馈有用，但大多聚焦于代码补丁（Patch）而非工具型 Agent。

1.  **ChatRepair / Keep the Conversation Going** (2023)
    *   **核心：** 首次系统提出 Conversation-driven APR，利用测试反馈进行多轮修复。
    *   **关联：** 你的 `validator-driven` 主线。它设定了 5-10 轮的固定预算。把失败 patch 和失败反馈作为上下文，继续生成下一版；历史
     太长后再 reset 到 initial prompt。
2.  **Studying and Understanding the Effectiveness and Failures of Conversational LLM-Based Repair** (2025-03)
    *   **核心：** 对 ChatRepair 的深度复盘，发现迭代不一定优于独立重复（Fresh Start）。
    *   **关联：** **RQ1/RQ2**。它挑战了“多轮一定好”的假设，是你必须正面回应的对比项。
3.  **ContrastRepair** (2024/2025)
    *   **核心：** 提出反馈质量决定效果，通过对比失败/通过的测试对来增强反馈的可操作性。
    *   **关联：** **RQ4**。支撑了“反馈内容策略（Policy）影响收敛”的观点。
4.  **VRpilot** (2024)
    *   **核心：** 针对漏洞修复，利用外部工具（Sanitizer/Compiler）提供 Actionable 反馈，并做了消融实验。
    *   **关联：** **RQ4**。证明了“推理+验证反馈”的协同作用。
5.  **RePair: Automated Program Repair with Process-based Feedback** (2024)
    *   **核心：** 推理时要求模型迭代，直到效果不再提升或达到最大步数。
    *   **关联：** **RQ1/RQ3**。涉及了动态停止的初步思想。
6.  **RepairAgent: An Autonomous, LLM-Based Agent for Program Repair** (2024)
    *   **核心：** 将程序修复建模为 agent 式工具使用流程，结合外部反馈持续修复并报告 token 成本。
    *   **关联：** **RQ1/RQ3**。是“真实 agent + repair + tools + cost”方向的强近邻。
7.  **ThinkRepair: Self-Directed Automated Program Repair** (2024/2025)
    *   **核心：** 强调自引导的修复流程，结合知识收集、推理和测试反馈改进后续修复。
    *   **关联：** **RQ1/RQ4**。涉及“如何构造更有效的思考上下文与反馈”。
8.  **Enhancing Automated Program Repair with Solution Design** (2024/2025)
    *   **核心：** 利用设计信息和额外上下文提升修复质量，并引入反馈式自修正框架。
    *   **关联：** **RQ4**。说明“更高质量、更具结构的信息”会影响收敛。
9.  **PATCH: Empowering Large Language Model with Programmer-Intent Guidance and Collaborative-Behavior Simulation for Automatic Bug Fixing** (2025)
    *   **核心：** 将 bug fixing 拆成多阶段交互流程，并引入 programmer intent 与协作行为模拟。
    *   **关联：** **RQ2/RQ4**。与分阶段修复、历史组织和反馈设计有明显交叉。
10. **PathFix: Automated Program Repair with Expected Path** (2025)
    *   **核心：** 通过更结构化的 expected path / constraint 反馈约束后续修复方向。
    *   **关联：** **RQ4**。接近你想研究的 `actionable-path` 风格反馈。

---

## Ⅱ. 上下文管理与历史污染 (RQ2)
这类论文探讨了为什么多轮对话会变差，以及如何优化上下文结构。

11. **The Debugging Decay Index (DDI)** (2025-06)
    *   **核心：** 发现多轮 Debug 存在衰减效应，提出 `Strategic Fresh Start`（策略性重开）。
    *   **关联：** **RQ2** 的核心近邻。直接支撑了你 `append` vs `fresh-session` 的对比实验。
12. **Agentic Context Engineering (ACE)** (2025/2026)
    *   **核心：** 研究 Context Collapse（上下文崩溃）和增量更新，目标是降低 Rollout 成本。
    *   **关联：** **RQ2/RQ4**。涉及了你提到的 `stable-prefix` 和上下文演化逻辑。
13. **Dynamic Cheatsheet: Test-Time Learning with Adaptive Memory** (2025)
    *   **核心：** 提倡保留浓缩的（Concise）经验片段而非全量轨迹（Transcript）。
    *   **关联：** **RQ2**。支持了最小充分上下文和状态压缩的想法。
14. **ToolSandbox: A Stateful, Conversational, Interactive Evaluation Benchmark for LLM Tool Use Capabilities** (2024)
    *   **核心：** 强调 stateful、conversational 的工具使用评测，区分会话历史与环境状态。
    *   **关联：** **RQ2**。支撑你把 `session history` 和 `workspace state` 分开分析。

---

## Ⅲ. 成本边界与效率优化 (RQ3)
这类论文关注 Agent 跑起来“贵不贵”以及“值不值”。

15. **Efficient Agents: Building Effective Agents While Reducing Cost** (2025)
    *   **核心：** 提出 `cost-of-pass` 指标，讨论效率与效能的 Trade-off。
    *   **关联：** **RQ3**。为你量化“Success per Dollar”提供了方法论支持。
16. **On the Role of Feedback in Test-Time Scaling of Agentic AI Workflows** (2025)
    *   **核心：** 系统研究在有限推理预算（Inference Budget）下，反馈如何影响 Scaling Law。
    *   **关联：** **RQ3**。探讨了成本-效果的边界。
17. **Budget-Aware Agentic Routing via Boundary-Guided Training** (2026)
    *   **核心：** 在严格的任务预算下做动态路由。
    *   **关联：** **RQ3**。将 Agent 的每一步视为预算决策。
18. **SkillReducer: Optimizing LLM Agent Skills for Token Efficiency** (2026)
    *   **核心：** 压缩技能描述和主体，区分“核心规则”与“按需加载”内容。
    *   **关联：** **RQ3/RQ4**。对应你提到的针对特定任务减少 Token 消耗的策略。
19. **tau-bench: A Benchmark for Tool-Agent-User Interaction in Real-World Domains** (2024)
    *   **核心：** 面向真实领域的 tool-use benchmark，并引入 `pass^k` 评估多次试验下的可靠性。
    *   **关联：** **RQ3**。与你想报告的 `success@k` / 多次运行可靠性非常接近。

---

## Ⅳ. 方法论支撑：反馈与自演化 (General Agent)
作为背景技术和动机支撑的经典/前沿工作。

20. **Reflexion: Language Agents with Verbal Reinforcement Learning** (2023)
    *   **核心：** 经典的自我反思框架，通过语言反馈在多轮尝试中自我纠正。
21. **Self-Refine: Iterative Refinement with Self-Feedback** (2023)
    *   **核心：** 通用的多轮迭代改进框架。
22. **Thinking vs. Doing: Agents that Reason by Scaling Test-Time Interaction** (2025)
    *   **核心：** 提出交互轮次（Interaction）是 Test-time Scaling 的重要轴。
23. **Gecko: A Simulation Environment with Stateful Feedback** (2026)
    *   **核心：** 提供状态化反馈（Tool call validity 等）用于精炼 Agent 的工具调用。
24. **LLF-Bench** (2023)
    *   **核心：** 交互式语言反馈的基准测试，定义了 FP（前向正向）和 FN（前向负向）反馈类型。
25. **ReAct: Synergizing Reasoning and Acting in Language Models** (2022)
    *   **核心：** 将 reasoning 与 acting 放入闭环交互框架，是后续 tool-using agent 的基础范式之一。
    *   **关联：** 为你的 `validator-driven retry` 提供一般性的 agent 闭环背景。
26. **CRITIC: Large Language Models Can Self-Correct with Tool-Interactive Critiquing** (2023)
    *   **核心：** 用工具交互式 critique 帮助模型自纠错，强调外部反馈的重要性。
    *   **关联：** 支撑“validator / tool feedback 比纯内生自我修正更可靠”的动机。
27. **Teaching Large Language Models to Self-Debug** (2023)
    *   **核心：** 在代码生成场景中通过错误信息和执行反馈推动迭代式 self-debug。
    *   **关联：** 是 validator-driven debugging 的早期方法论近邻。
28. **Large Language Models Cannot Self-Correct Reasoning Yet** (2023)
    *   **核心：** 指出缺乏外部反馈时，模型的纯自我修正能力非常有限。
    *   **关联：** 反向支撑你把外部 validator 作为研究前提，而不是研究纯 self-correction。
29. **Can Large Language Models Really Improve by Self-critiquing Their Own Plans?** (2023)
    *   **核心：** 质疑同一模型自我批评是否稳定有效，强调反馈来源与质量的重要性。
    *   **关联：** 与 **RQ4** 中“什么反馈真正有用”直接相关。
30. **Voyager: An Open-Ended Embodied Agent with Large Language Models** (2023)
    *   **核心：** 通过技能库、环境反馈和持续积累经验推动 agent 自演化。
    *   **关联：** 提供“从失败和环境反馈中积累可复用知识”的背景。
31. **LeMa: Learning From Mistakes Makes LLM Better Reasoner** (2023/2024)
    *   **核心：** 强调从错误轨迹中提炼经验以提升后续推理表现。
    *   **关联：** 与“失败后再试是否能形成有效改进”有方法论联系。
32. **GITM: Ghost in the Minecraft** (2023)
    *   **核心：** 通过长期交互、外部环境和阶段化技能积累提升 embodied agent 能力。
    *   **关联：** 可作为 agent 从多轮环境反馈中演化的补充背景。
33. **Just Talk: An Agent That Meta-Learns and Evolves in the Wild** (2026)
    *   **核心：** 研究 agent 在开放环境中如何基于失败轨迹进行元学习与持续演化。
    *   **关联：** 支撑你把 failure trajectory 视为可复用学习信号。
34. **Co-Evolving Agents: Learning from Failures as Hard Negatives** (2025/2026)
    *   **核心：** 将失败样本视为 hard negatives，驱动 agent 行为改进。
    *   **关联：** 与你从失败轨迹中抽取有用反馈的思路一致。
35. **EvoSkills: Self-Evolving Agent Skills via Co-Evolutionary Verification** (2026)
    *   **核心：** 通过验证驱动的协同进化不断更新 agent 技能。
    *   **关联：** 与 validator-guided skill evolution 的思路相关。
36. **Reinforcement Learning for Self-Improving Agent with Skill Library (SAGE)** (2026)
    *   **核心：** 结合技能库与强化学习，实现 agent 的持续自改进。
    *   **关联：** 适合作为“失败修正进一步下沉到技能层/训练层”的延伸背景。

---

## Ⅴ. 动态停止与早期终止 (RQ3 Extension)
针对你提到的“预测下一轮是否值得”的专项研究。

37. **EET: Experience-Driven Early Termination for SE Agents** (2026)
    *   **核心：** 利用过往轨迹的相似度来判断当前 Agent 是否陷入死循环，从而早停。
38. **The Cognitive Companion** (2026)
    *   **核心：** 引入轻量级“伴侣模型”监控推理衰减（循环、卡死），降低 50% 以上的重复 Token 浪费。
39. **More with Less: An Empirical Study of Turn-Control Strategies** (2026)
    *   **核心：** 发现将轮次限制设定在分布的第 75 百分位是成本效益的最优平衡点。
40. MiCP 
    框架用的是共形预测来给每一轮分配预算，在每一轮动态决定是否要继续或者停止，但是需要并行多次来得到模型的答案的置信度

41. AgentCollab
    在每一轮让小模型自己总结一下刚刚这“一步”的行动有没有让整个任务朝着最终目标实质性地推进 并输出是或者否，从而判断是否要继续。

42. ATROPOS: IMPROVING COST-BENEFIT TRADE-OFF OF LLM-BASED AGENTS UNDER SELF-CONSISTENCY WITH EARLY TERMINATION AND MODEL HOTSWAP.ATROPOS 将推理路径转化为一种名为语义流图（SFG）的数据结构，利用图卷积网络（GCN）分析推理到一半的 SFG 结构，预测这次推理最终是会成功还是失败，失败的话，提前终止，之后转移到更强大的模型上。
我是大模型给出方向，之后让小模型继续