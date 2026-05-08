复用 EET/mini-swe-agent 接入 SWE-bench 的适配方案

目标
  不自己从零实现一个 SWE-bench agent，而是复用
  /data/lirui/skill_study/EET/mini-swe-agent 作为单次求解 backend。
  上层仍然保留现有实验入口、重试策略、反馈策略、停止规则、结果聚合和分析脚本。

总体思路
  采用“上层是你的框架，底层是 mini-swe-agent”的分层：

  1. 你的 rq1.sh / common.sh
     负责实验入口、参数编排、运行多轮重试、统一输出 JSON、跑 analyze_retries.py。
  2. 新增一个 swebench runner
     负责读 SWE-bench 数据、逐个 instance 调 mini-swe-agent、调用官方评测、收集日志。
  3. EET/mini-swe-agent
     只负责“给一个 instance 生成一个 patch”。
  4. 你的聚合器
     把 mini-swe-agent 的 trajectory 和 SWE-bench harness 的结果归一化到你现有 schema。

为什么这样做
  - 最大化复用现成 agent 代码
  - 避免自己重写 SWE-bench 单次求解逻辑
  - 保留你自己的 retry / feedback / stop-rule 实验贡献
  - 更容易向审稿人说明边界：
    底层 agent 使用公开实现， 上层重试与反馈框架是你的方法

推荐分工
  mini-swe-agent 负责：
  - 根据 problem_statement 在指定 repo/base_commit 上生成 patch
  - 保存 trajectory
  - 记录 model cost / api calls

  你的框架负责：
  - 选择要跑的 SWE-bench instances
  - 每个 instance 的 attempt loop
  - 失败后构造安全反馈
  - 是否继续下一轮
  - 调用官方 evaluation
  - 聚合为现有 result JSON

最小落地结构
  建议新增两个脚本：

  1. scripts/run_swebench_with_minisweagent.py
     作用：
     - 读取 SWE-bench parquet 或 HuggingFace split
     - 根据 --swebench-instance-id 过滤样本
     - 对每个 instance 跑最多 k 轮 attempt
     - 每轮：
       - 准备 mini-swe-agent 运行目录
       - 调 mini-swe-agent 生成 patch
       - 写 predictions.attempt{n}.json
       - 调 SWE-bench harness 跑评测
       - 读取 resolved / logs / timing
       - 如果失败，提取安全反馈，进入下一轮
     - 最终输出一个 normalized intermediate JSON

  2. scripts/aggregate_swebench_minisweagent_results.py
     作用：
     - 读取每个 instance 的 attempt 结果
     - 读取 mini-swe-agent 的 traj.json
     - 转成你的统一 schema
     - 输出到 results/rq1/swebench__{model_slug}__{run_id}.json

建议保留的 backend 形态
  在 common.sh 里新增：
  - backend=swebench

  但这个 backend 的实现不是自己写 agent，而是做 thin wrapper：
  - 参数解析
  - 调用 run_swebench_with_minisweagent.py
  - 调用 aggregate_swebench_minisweagent_results.py

参数映射建议
  你的上层参数：
  - --model
  - --runs
  - --max-task-attempts
  - --feedback-policy
  - --feedback-format
  - --feedback-answer-safety
  - --stop-rule
  - --stop-threshold
  - --swebench-instance-id
  - --benchmark-version
  - --run-id

  mini-swe-agent / runner 层内部参数：
  - --subset verified
  - --split test
  - --filter {instance_id regex}
  - --output {attempt output dir}
  - --workers 1
  - --config {plain or EET config}
  - --model {same model}

建议的适配关系
  - 一个 SWE-bench instance = 你框架里的一个 task
  - 一次 mini-swe-agent 运行 = 你框架里的一个 attempt
  - mini-swe-agent 产出的 patch = 该 attempt 的 candidate patch
  - harness resolved = attempt.grading.score > 0

最重要的实现选择
  不建议直接调用 mini-extra swebench 做多轮重试总控。
  原因：
  - mini-extra swebench 自己已经管理 batch run
  - 你还要叠加自己的 retry / feedback / aggregation
  - 两层总控会让结构变乱

  更好的方式是：
  - 直接 import mini-swe-agent 的 Python 接口
  - 或者写一个很薄的 subprocess wrapper，只调用单个 instance 的求解逻辑

推荐优先级
  1. 优先复用 Python 接口
     原因：更容易拿到 trajectory、submission、cost、api_calls
  2. 次选 subprocess 调用
     原因：实现简单，但结果抽取和失败恢复更脆

最小 Python 复用点
  可以直接参考：
  - /data/lirui/skill_study/EET/mini-swe-agent/src/minisweagent/run/extra/swebench.py
  - /data/lirui/skill_study/EET/mini-swe-agent/src/minisweagent/run/utils/save.py

  其中可复用的关键逻辑是：
  - 加载 instance
  - 构造 SWE-bench docker environment
  - 选择 DefaultAgent 或 ExperienceRetrievalAgent
  - 调 agent.run(task, issue_id=instance_id)
  - 保存 traj.json
  - 从 data["info"]["model_stats"] 中读取 cost / api_calls

推荐的两种 backend 变体
  为了后续论文对比更清楚，建议一开始就支持两种模式：

  1. plain-mini
     使用 mini-swe-agent 的普通配置
     不开 EET 的 experience retrieval 和 confidence early stop

  2. eet-mini
     使用 swebench_experience.yaml
     开启 experience retrieval / early stop

  这样你后面可以做：
  - 你的方法 vs plain-mini
  - 你的方法 vs eet-mini
  - plain-mini vs eet-mini

建议的配置命名
  - config backend variant:
    plain-mini -> src/minisweagent/config/extra/swebench.yaml
    eet-mini -> src/minisweagent/config/extra/swebench_experience.yaml

  上层参数可设计为：
  - --swebench-agent-backend plain-mini
  - --swebench-agent-backend eet-mini

安全反馈接入点
  这里建议直接按你现在 SkillsBench 的风格接，不要额外发明一层复杂协议。

  SkillsBench 现在的做法本质上是：
  - 每轮 attempt 结束后先跑 verifier
  - 从 verifier stdout / stderr 提取失败摘要
  - 生成一个 feedback prompt
  - 下一轮输入 = feedback prompt + 原始 instruction

  SWE-bench 这里也建议完全照这个模式：
  - 每轮 attempt 结束后先跑官方 evaluation
  - 从 evaluation 结果和测试日志里提取安全失败摘要
  - 生成一个 feedback.txt
  - 下一轮输入 = feedback.txt + 原始 problem_statement

  也就是说，上层 retry loop 只需要做两件事：
  - 把本轮失败结果压成一段短 feedback
  - 把这段 feedback 拼回下一轮输入

  不建议在这里再定义单独的 feedback state machine。

  反馈内容保持 no-answers 风格：
  - 可以反馈 patch apply 是否成功
  - 可以反馈失败测试名
  - 可以反馈异常类型
  - 可以反馈精简错误摘要
  - 可以反馈回归测试名
  - 不要反馈 gold patch
  - 不要反馈 test_patch
  - 不要反馈 FAIL_TO_PASS / PASS_TO_PASS

  可直接复用：
  - /data/lirui/skill_study/skill/SWE_BENCHMARK.md
    中定义的“安全反馈模板”

  上层参数也保持和现有 rq1 / SkillsBench 一致即可：
  - --feedback-policy error-localized
  - --feedback-format full-refresh
  - --feedback-answer-safety no-answers

  这些参数在 SWE-bench 里的含义可以简单对齐为：
  - error-localized：
    下一轮只看本轮失败测试和对应报错，不给泛泛建议
  - full-refresh：
    每一轮重新生成完整 feedback，而不是依赖前几轮历史拼接
  - no-answers：
    反馈里不泄漏参考 patch、隐藏测试意图或标准答案

  如果要和 SkillsBench 结果结构保持一致，建议每个 attempt 也记录：
  - feedback_prompt
  - feedback_prompt_stats.text_length_chars
  - verifier / eval notes

  这样后面聚合时就能继续产出：
  - feedback_length_chars_by_attempt
  - attempts[]
  - first_success_attempt
  - stop_reason

建议的 attempt 目录结构
  results/swebench_runs/{run_id}/{instance_id}/
  - attempt_1/
    - traj.json
    - prediction.json
    - eval_result.json
    - feedback.txt
  - attempt_2/
    - traj.json
    - prediction.json
    - eval_result.json
    - feedback.txt
  - task_summary.json

  这里的 feedback.txt 就对应 SkillsBench 里的 feedback_prompt 落盘版本。
  不需要再单独设计更复杂的中间状态文件。

结果归一化建议
  最终聚合到你现有 schema 时，建议字段这样映射：

  顶层：
  - model
  - benchmark = "swebench"
  - benchmark_version
  - run_id
  - suite
  - max_task_attempts
  - retry_policies
  - tasks
  - efficiency

  每个 task：
  - task_id = instance_id
  - attempt_count
  - first_success_attempt
  - success_within_budget
  - attempts

  每个 attempt：
  - grading.score = resolved ? 1.0 : 0.0
  - grading.max_score = 1.0
  - execution.execution_time = harness timing
  - execution.usage.cost = traj.info.model_stats.instance_cost
  - execution.usage.api_calls = traj.info.model_stats.api_calls
  - feedback_prompt = 下一轮使用的失败摘要
  - feedback_prompt_stats.text_length_chars = feedback 长度
  - artifact_paths.traj_json
  - artifact_paths.eval_json
  - artifact_paths.prediction_json

为什么这个方案适合你的项目
  - 你不用重写 agent scaffold
  - 你保留了自己最关心的上层实验逻辑
  - 你仍然能在一个统一入口里跑 SkillsBench / PinchBench / SWE-bench
  - 后续分析脚本几乎不用推翻重来

不建议做的事
  - 不要把整个实验控制权都交给 mini-extra swebench
  - 不要把 EET 的 batch runner 和你的 retry runner 叠两层
  - 不要一开始就把 EET 经验检索和你的方法混成一个单独方法，先把 plain-mini 和 eet-mini 分开

推荐的最小实现顺序
  1. 先做 backend=swebench 的壳子
  2. 先接 plain-mini 单轮运行
  3. 再接官方 evaluation
  4. 再把单轮结果聚合到现有 schema
  5. 再按 SkillsBench 的方式加多轮 retry + 安全反馈
  6. 最后再支持 eet-mini 变体

一句话版本
  最省代码、最符合你需求的方案不是“自己实现一个 SWE-bench agent”，而是：
  用你的框架做上层总控，用 EET/mini-swe-agent 做底层单次求解 backend，再把结果聚合回你的
  统一实验格式。
