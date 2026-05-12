给 rq1.sh 增加 benchmark=swebench 的方案
  当前关键链路是 scripts/experiments/rq1.sh:83 -> scripts/experiments/common.sh:233。rq1.sh
  只是参数编排，真正要扩的是 common.sh 的 run_benchmark() backend 分支；另外结果 JSON 必须
  继续满足 scripts/analyze_retries.py:91 现在依赖的 schema。

  建议最小可落地方案：

  1. 在 common.sh 新增第三个 backend：swebench。
     增加参数：
     --swebench-dataset, --swebench-split, --swebench-instance-id, --swebench-root,
     --swebench-max-workers, --swebench-cache-level, --namespace.
  2. 不要把 SWE-bench 硬塞进现有 scripts/benchmark.py。
     PinchBench 的 grader 和 SWE-bench 的 Docker harness 是两套机制；SWE-bench 应该走独立
     runner。
  3. 新增一个 runner，例如 scripts/run_swebench_with_retries.py。
     它负责：
      - 读 Verified parquet
      - 逐个 instance_id 取 problem_statement/repo/base_commit
      - 让 agent 生成第 1 次 patch
      - 写 predictions.attempt1.jsonl
      - 调用 python -m swebench.harness.run_evaluation
      - 从 report.json / results.json 取 resolved、耗时、日志
      - 若失败且 k>1，把失败摘要作为 feedback 再生成下一次 patch
      - 最后输出统一的 normalized result JSON
  4. 新增聚合器，例如 scripts/aggregate_swebench_results.py。
     输出格式对齐现在的 SkillsBench 聚合器，至少保留这些字段：
      - 顶层：model, benchmark, benchmark_version, run_id, suite, max_task_attempts,
        retry_policies, tasks, efficiency
      - 每个 task：task_id=instance_id, attempt_count, first_success_attempt,
        success_within_budget, attempts[]
      - 每个 attempt：grading.score 用 resolved ? 1.0 : 0.0，grading.max_score=1.0，
        execution.execution_time，execution.usage.*
        这样 scripts/analyze_retries.py:107 基本不用改。
  5. rq1.sh 的改动只做薄封装。
     当 --backend swebench 时：
      - 默认 --swebench-dataset /hy-tmp/skill/data/swebench_verified/test-00000-of-
        00001.parquet
      - 默认 --benchmark-version swebench_verified
      - 输出文件命名成 results/rq1/swebench__${model_slug}__${run_id}.json
      - 若用户没传 --swebench-instance-id，默认全量 500 条，或先给一个小子集脚本
  6. 需要额外注意两点。
      - 资源要求高：官方文档建议约 120GB 磁盘、16GB 内存、8+ CPU。
      - 反馈设计不能泄漏 patch/test_patch/FAIL_TO_PASS/PASS_TO_PASS，否则不是合法
        benchmark。

  如果你要，我下一步可以直接把这套最小实现落代码：先加 backend=swebench 的壳子、runner
  stub、聚合器 stub，再把 rq1.sh 接通。

SWE-bench 多轮重试的安全反馈模板
  目标：
  当某一轮 patch 在 SWE-bench 验证失败后，可以把执行结果反馈给下一轮 agent，帮助它继续修
  复；但反馈不能泄漏 gold patch、隐藏测试意图或官方答案信息。

  设计原则：
  1. 只反馈公开可观察的执行现象，不反馈参考答案。
  2. 只反馈本轮候选 patch 造成的结果，不反馈数据集中隐藏字段的原文。
  3. 允许给出失败测试名、异常类型、精简报错摘要；不允许给出官方修复 patch、test_patch、
     FAIL_TO_PASS、PASS_TO_PASS 的原始内容。
  4. 如果失败日志很长，只保留少量高价值摘要，避免把测试断言细节原样大段塞回 prompt。

  允许反馈给下一轮的信息：
  - patch 是否成功应用
  - 环境构建或依赖安装是否成功
  - 测试命令是否成功执行
  - 失败测试数量、通过测试数量、是否超时
  - 失败测试名称
  - 异常类型，如 AssertionError、TypeError、ImportError
  - 精简后的 traceback / stderr 摘要
  - 回归测试名称，也就是“原本通过、现在失败”的测试
  - 本轮 agent 自己的修改摘要，前提是该摘要只描述自己改了什么，不暗示 gold solution

  明确禁止反馈的信息：
  - gold patch 或其任何改写、摘要、diff 提示
  - test_patch 原文或其任何改写、摘要
  - FAIL_TO_PASS、PASS_TO_PASS 的原始列表或接近原文的转述
  - 从官方 PR、隐藏测试、参考补丁中提炼出的修复建议
  - 过细的断言差异，如果该差异几乎等价于告诉模型“应该改哪一行、改成什么”

  推荐做法：
  - 保留失败测试名
  - 保留异常类型
  - 每个失败测试最多保留 1 到 3 行报错摘要
  - 优先保留第一段 stack trace 末尾和异常消息
  - 去掉超长日志、环境噪音、完整断言大文本

  适用于本框架的下一轮安全反馈模板：

  <swebench_retry_feedback>
  Previous attempt result: FAILED

  Attempt number: {attempt_index}
  Instance id: {instance_id}
  Repository: {repo}
  Base commit: {base_commit}

  Patch application:
  - applied: {yes_or_no}
  - apply_summary: {short_apply_summary}

  Environment setup:
  - setup_status: {success_or_failed}
  - setup_summary: {short_setup_summary}

  Test execution:
  - status: {completed_or_failed_or_timeout}
  - passed_count: {passed_count}
  - failed_count: {failed_count}
  - timeout: {yes_or_no}

  Regressions:
  - {regression_test_name_1}
  - {regression_test_name_2}

  Failed tests:
  1. {test_name_1}
     - error_type: {error_type}
     - summary: {one_to_three_lines}
  2. {test_name_2}
     - error_type: {error_type}
     - summary: {one_to_three_lines}

  Execution notes:
  - {optional_short_note_1}
  - {optional_short_note_2}

  Instructions for the next attempt:
  - Use only the issue statement, repository state, and the failure symptoms above.
  - Do not assume any hidden reference patch or hidden test intent.
  - Fix the observed failures while avoiding unrelated changes.
  - If the previous patch introduced regressions, prioritize removing those regressions.
  </swebench_retry_feedback>

  更保守的极简模板：

  <swebench_retry_feedback>
  Previous attempt result: FAILED
  Attempt number: {attempt_index}
  Instance id: {instance_id}

  Patch application: {yes_or_no}
  Test execution status: {completed_or_failed_or_timeout}
  Passed: {passed_count}
  Failed: {failed_count}

  Failed tests:
  - {test_name}: {error_type}: {short_summary}
  - {test_name}: {error_type}: {short_summary}

  Regressions:
  - {test_name}

  Please continue from the current repository state and fix the observed failures without
  making unrelated changes.
  </swebench_retry_feedback>

  对 runner 的实现建议：
  1. 先从 harness 结果中提取结构化字段，再统一裁剪日志。
  2. 默认限制：
     - 最多反馈 5 个失败测试
     - 每个失败测试最多 3 行摘要
     - 总反馈字符数上限 4000 到 8000
  3. 聚合结果里单独保留 full logs 到本地文件，但不要把 full logs 直接注入下一轮 prompt。
  4. 如果 patch 连 apply 都失败，下一轮只反馈 apply error，不要附带任何官方测试信息。


# swebench 一些知识
agent 看不到 在 attempt 结束后额外跑的那一整套官方判分流程

astropy/timeseries/tests/test_sampled.py 是仓库里的一个普通测试文件，而“评测器在 attempt 结束后跑的官方判分流程”是外层的裁判逻辑。前者是被执行的测试内容，后者是决定你算不算过题的规则和流程。测试文件定义“代码应该怎么表现”，评测器定义“哪些测试算关键、怎么记分、最终是否通过”


## SWE-bench 风格的“修 bug”题是长什么样的？
输入主要是两部分：一个仓库：这里是 astropy.一段 issue / PR 描述：告诉 agent 有个 bug，需要它自己去代码里定位、修改、验证