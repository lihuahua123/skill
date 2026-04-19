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