# RQ1 失败任务汇总报告

- 源文件: `/hy-tmp/skill/results/rq1/aggregated_results.json`
- 总任务数: **87**
- 成功任务数: **31**
- 失败任务数: **56**
- 状态分布: `success=31`, `error=53`, `failed=3`

## 失败分类统计

- 执行超时: **42**
- 模型调用限流: **7**
- 执行异常: **3**
- 验证失败-依赖缺失: **2**
- 验证失败-环境变量缺失: **1**
- 无尝试记录: **1**

## 分类说明

- `执行超时`: 最终 attempt 在 agent 执行阶段报 `TimeoutError`，trace 多数落在 `run_terminus_local_host.py` 的子进程启动或输出读取。
- `模型调用限流`: 最终 attempt 抛出 `RetryError`，底层是 `RateLimitError`。
- `验证失败-依赖缺失`: verifier 的 pytest 在测试收集阶段导入失败。
- `验证失败-环境变量缺失`: verifier 的 pytest 明确断言运行环境变量未设置。
- `无尝试记录`: 聚合结果里没有 attempt，因此没有可分析的 trace。

## 每个失败任务的具体原因

### mario-coin-counting

- 最终状态: `error`
- 分类: `执行异常`
- attempt 数: `4`
- 具体失败原因: 最终 attempt 抛出 `RetryError`。
- Trace 摘要: `RetryError` / RetryError[<Future at 0x7f1fe0aaf2f0 state=finished raised InternalServerError>]；见异常栈

### organize-messy-files

- 最终状态: `error`
- 分类: `执行异常`
- attempt 数: `2`
- 具体失败原因: 最终 attempt 抛出 `RetryError`。
- Trace 摘要: `RetryError` / RetryError[<Future at 0x7ff314633800 state=finished raised APIError>]；见异常栈

### pddl-tpp-planning

- 最终状态: `error`
- 分类: `执行异常`
- attempt 数: `1`
- 具体失败原因: 最终 attempt 抛出 `RetryError`。
- Trace 摘要: `RetryError` / RetryError[<Future at 0x7f87e1137050 state=finished raised APIError>]；见异常栈

### adaptive-cruise-control

- 最终状态: `error`
- 分类: `执行超时`
- attempt 数: `2`
- 具体失败原因: 最终 attempt 触发 `TimeoutError`；trace 显示启动子进程时超时（create_subprocess_exec）。
- Trace 摘要: `TimeoutError`；启动子进程时超时（create_subprocess_exec）
- 较早 attempt 暴露的问题: Failed tests: - tests/test_outputs.py::TestSimulationResults::test_simulation_results - tests/test_outputs.py::TestDistanceControl::test_distance_control - tests/test_outputs.py::TestSafety::test_safety -...

### crystallographic-wyckoff-position-analysis

- 最终状态: `error`
- 分类: `执行超时`
- attempt 数: `2`
- 具体失败原因: 最终 attempt 触发 `TimeoutError`；trace 显示启动子进程时超时（create_subprocess_exec）。
- Trace 摘要: `TimeoutError`；启动子进程时超时（create_subprocess_exec）
- 较早 attempt 暴露的问题: Failed tests: - tests/test_outputs.py::TestWyckoffAnalysis::test_Al2O3 - tests/test_outputs.py::TestWyckoffAnalysis::test_C_mp169 - tests/test_outputs.py::TestWyckoffAnalysis::test_C_mp683919 -...

### earthquake-phase-association

- 最终状态: `error`
- 分类: `执行超时`
- attempt 数: `1`
- 具体失败原因: 最终 attempt 触发 `TimeoutError`；trace 显示启动子进程时超时（create_subprocess_exec）。
- Trace 摘要: `TimeoutError`；启动子进程时超时（create_subprocess_exec）

### energy-ac-optimal-power-flow

- 最终状态: `error`
- 分类: `执行超时`
- attempt 数: `1`
- 具体失败原因: 最终 attempt 触发 `TimeoutError`；trace 显示启动子进程时超时（create_subprocess_exec）。
- Trace 摘要: `TimeoutError`；启动子进程时超时（create_subprocess_exec）

### energy-market-pricing

- 最终状态: `error`
- 分类: `执行超时`
- attempt 数: `1`
- 具体失败原因: 最终 attempt 触发 `TimeoutError`；trace 显示执行命令后读取子进程输出时超时（communicate/read）。
- Trace 摘要: `TimeoutError`；执行命令后读取子进程输出时超时（communicate/read）

### exoplanet-detection-period

- 最终状态: `error`
- 分类: `执行超时`
- attempt 数: `1`
- 具体失败原因: 最终 attempt 触发 `TimeoutError`；trace 显示执行命令后读取子进程输出时超时（communicate/read）。
- Trace 摘要: `TimeoutError`；执行命令后读取子进程输出时超时（communicate/read）

### financial-modeling-qa

- 最终状态: `error`
- 分类: `执行超时`
- attempt 数: `2`
- 具体失败原因: 最终 attempt 触发 `TimeoutError`；trace 显示启动子进程时超时（create_subprocess_exec）。
- Trace 摘要: `TimeoutError`；启动子进程时超时（create_subprocess_exec）
- 较早 attempt 暴露的问题: Failed tests: - tests/test_outputs.py::TestOutputs::test_answer_value_correct Pytest failure details: [Failure block 1] =================================== FAILURES ===================================...

### find-topk-similiar-chemicals

- 最终状态: `error`
- 分类: `执行超时`
- attempt 数: `1`
- 具体失败原因: 最终 attempt 触发 `TimeoutError`；trace 显示执行命令后读取子进程输出时超时（communicate/read）。
- Trace 摘要: `TimeoutError`；执行命令后读取子进程输出时超时（communicate/read）

### fix-build-agentops

- 最终状态: `error`
- 分类: `执行超时`
- attempt 数: `2`
- 具体失败原因: 最终 attempt 触发 `TimeoutError`；trace 显示启动子进程时超时（create_subprocess_exec）。
- Trace 摘要: `TimeoutError`；启动子进程时超时（create_subprocess_exec）
- 较早 attempt 暴露的问题: Pytest failure details: [Failure block 1] _ ERROR collecting jobs/skillsbench-rq1-2026-04-09__10-55-36/fix-build-agentops__XuNsH6W/task_root/tests/test_outputs.py _ ImportError while importing test module '/hy-...

### fix-erlang-ssh-cve

- 最终状态: `error`
- 分类: `执行超时`
- attempt 数: `2`
- 具体失败原因: 最终 attempt 触发 `TimeoutError`；trace 显示启动子进程时超时（create_subprocess_exec）。
- Trace 摘要: `TimeoutError`；启动子进程时超时（create_subprocess_exec）
- 较早 attempt 暴露的问题: Pytest failure details: [Failure block 1] _ ERROR collecting jobs/skillsbench-rq1-2026-04-08__10-00-32/fix-erlang-ssh-cve__79MnQR5/task_root/tests/test_outputs.py _ ImportError while importing test module '/hy-...

### fix-visual-stability

- 最终状态: `error`
- 分类: `执行超时`
- attempt 数: `1`
- 具体失败原因: 最终 attempt 触发 `TimeoutError`；trace 显示执行命令后读取子进程输出时超时（communicate/read）。
- Trace 摘要: `TimeoutError`；执行命令后读取子进程输出时超时（communicate/read）

### flink-query

- 最终状态: `error`
- 分类: `执行超时`
- attempt 数: `1`
- 具体失败原因: 最终 attempt 触发 `TimeoutError`；trace 显示启动子进程时超时（create_subprocess_exec）。
- Trace 摘要: `TimeoutError`；启动子进程时超时（create_subprocess_exec）

### gh-repo-analytics

- 最终状态: `error`
- 分类: `执行超时`
- attempt 数: `2`
- 具体失败原因: 最终 attempt 触发 `TimeoutError`；trace 显示执行命令后读取子进程输出时超时（communicate/read）。
- Trace 摘要: `TimeoutError`；执行命令后读取子进程输出时超时（communicate/read）
- 较早 attempt 暴露的问题: Failed tests: - tests/test_outputs.py::TestPR::test_total - tests/test_outputs.py::TestPR::test_merged - tests/test_outputs.py::TestPR::test_closed - tests/test_outputs.py::TestPR::test_avg_merge_days -...

### glm-lake-mendota

- 最终状态: `error`
- 分类: `执行超时`
- attempt 数: `1`
- 具体失败原因: 最终 attempt 触发 `TimeoutError`；trace 显示启动子进程时超时（create_subprocess_exec）。
- Trace 摘要: `TimeoutError`；启动子进程时超时（create_subprocess_exec）

### grid-dispatch-operator

- 最终状态: `error`
- 分类: `执行超时`
- attempt 数: `1`
- 具体失败原因: 最终 attempt 触发 `TimeoutError`；trace 显示执行命令后读取子进程输出时超时（communicate/read）。
- Trace 摘要: `TimeoutError`；执行命令后读取子进程输出时超时（communicate/read）

### jax-computing-basics

- 最终状态: `error`
- 分类: `执行超时`
- attempt 数: `1`
- 具体失败原因: 最终 attempt 触发 `TimeoutError`；trace 显示启动子进程时超时（create_subprocess_exec）。
- Trace 摘要: `TimeoutError`；启动子进程时超时（create_subprocess_exec）

### jpg-ocr-stat

- 最终状态: `error`
- 分类: `执行超时`
- attempt 数: `1`
- 具体失败原因: 最终 attempt 触发 `TimeoutError`；trace 显示启动子进程时超时（create_subprocess_exec）。
- Trace 摘要: `TimeoutError`；启动子进程时超时（create_subprocess_exec）

### lab-unit-harmonization

- 最终状态: `error`
- 分类: `执行超时`
- attempt 数: `2`
- 具体失败原因: 最终 attempt 触发 `TimeoutError`；trace 显示启动子进程时超时（create_subprocess_exec）。
- Trace 摘要: `TimeoutError`；启动子进程时超时（create_subprocess_exec）
- 较早 attempt 暴露的问题: Failed tests: - tests/test_outputs.py::TestHarmonizedOutput::test_format_two_decimals - tests/test_outputs.py::TestHarmonizedOutput::test_conversion_feature_in_range Pytest failure details: [Failure block 1]...

### lake-warming-attribution

- 最终状态: `error`
- 分类: `执行超时`
- attempt 数: `2`
- 具体失败原因: 最终 attempt 触发 `TimeoutError`；trace 显示启动子进程时超时（create_subprocess_exec）。
- Trace 摘要: `TimeoutError`；启动子进程时超时（create_subprocess_exec）
- 较早 attempt 暴露的问题: Failed tests: - tests/test_outputs.py::TestLakeWarmingAttribution::test_trend_result Pytest failure details: [Failure block 1] =================================== FAILURES ===================================...

### lean4-proof

- 最终状态: `error`
- 分类: `执行超时`
- attempt 数: `2`
- 具体失败原因: 最终 attempt 触发 `TimeoutError`；trace 显示启动子进程时超时（create_subprocess_exec）。
- Trace 摘要: `TimeoutError`；启动子进程时超时（create_subprocess_exec）
- 较早 attempt 暴露的问题: Failed tests: - tests/test_outputs.py::test_solution_lean_typechecks - tests/test_outputs.py::test_solution_prefix_exact - tests/test_outputs.py::test_no_changes_outside_solution -...

### manufacturing-codebook-normalization

- 最终状态: `error`
- 分类: `执行超时`
- attempt 数: `1`
- 具体失败原因: 最终 attempt 触发 `TimeoutError`；trace 显示执行命令后读取子进程输出时超时（communicate/read）。
- Trace 摘要: `TimeoutError`；执行命令后读取子进程输出时超时（communicate/read）

### manufacturing-equipment-maintenance

- 最终状态: `error`
- 分类: `执行超时`
- attempt 数: `1`
- 具体失败原因: 最终 attempt 触发 `TimeoutError`；trace 显示启动子进程时超时（create_subprocess_exec）。
- Trace 摘要: `TimeoutError`；启动子进程时超时（create_subprocess_exec）

### manufacturing-fjsp-optimization

- 最终状态: `error`
- 分类: `执行超时`
- attempt 数: `1`
- 具体失败原因: 最终 attempt 触发 `TimeoutError`；trace 显示启动子进程时超时（create_subprocess_exec）。
- Trace 摘要: `TimeoutError`；启动子进程时超时（create_subprocess_exec）

### mhc-layer-impl

- 最终状态: `error`
- 分类: `执行超时`
- attempt 数: `2`
- 具体失败原因: 最终 attempt 触发 `TimeoutError`；trace 显示执行命令后读取子进程输出时超时（communicate/read）。
- Trace 摘要: `TimeoutError`；执行命令后读取子进程输出时超时（communicate/read）
- 较早 attempt 暴露的问题: ImportError while loading conftest '/hy-tmp/skillsbench/jobs/skillsbench-rq1-2026-04-09__16-25-22/mhc-layer-impl__RpLOBpR/task_root/tests/conftest.py'. tests/conftest.py:10: in <module> import torch E...

### parallel-tfidf-search

- 最终状态: `error`
- 分类: `执行超时`
- attempt 数: `1`
- 具体失败原因: 最终 attempt 触发 `TimeoutError`；trace 显示执行命令后读取子进程输出时超时（communicate/read）。
- Trace 摘要: `TimeoutError`；执行命令后读取子进程输出时超时（communicate/read）

### pedestrian-traffic-counting

- 最终状态: `error`
- 分类: `执行超时`
- attempt 数: `1`
- 具体失败原因: 最终 attempt 触发 `TimeoutError`；trace 显示启动子进程时超时（create_subprocess_exec）。
- Trace 摘要: `TimeoutError`；启动子进程时超时（create_subprocess_exec）

### pg-essay-to-audiobook

- 最终状态: `error`
- 分类: `执行超时`
- attempt 数: `2`
- 具体失败原因: 最终 attempt 触发 `TimeoutError`；trace 显示执行命令后读取子进程输出时超时（communicate/read）。
- Trace 摘要: `TimeoutError`；执行命令后读取子进程输出时超时（communicate/read）
- 较早 attempt 暴露的问题: Failed tests: - tests/test_outputs.py::test_audio_wer Pytest failure details: [Failure block 1] =================================== FAILURES =================================== ________________________________...

### python-scala-translation

- 最终状态: `error`
- 分类: `执行超时`
- attempt 数: `1`
- 具体失败原因: 最终 attempt 触发 `TimeoutError`；trace 显示启动子进程时超时（create_subprocess_exec）。
- Trace 摘要: `TimeoutError`；启动子进程时超时（create_subprocess_exec）

### quantum-numerical-simulation

- 最终状态: `error`
- 分类: `执行超时`
- attempt 数: `1`
- 具体失败原因: 最终 attempt 触发 `TimeoutError`；trace 显示执行命令后读取子进程输出时超时（communicate/read）。
- Trace 摘要: `TimeoutError`；执行命令后读取子进程输出时超时（communicate/read）

### react-performance-debugging

- 最终状态: `error`
- 分类: `执行超时`
- attempt 数: `1`
- 具体失败原因: 最终 attempt 触发 `TimeoutError`；trace 显示执行命令后读取子进程输出时超时（communicate/read）。
- Trace 摘要: `TimeoutError`；执行命令后读取子进程输出时超时（communicate/read）

### reserves-at-risk-calc

- 最终状态: `error`
- 分类: `执行超时`
- attempt 数: `1`
- 具体失败原因: 最终 attempt 触发 `TimeoutError`；trace 显示执行命令后读取子进程输出时超时（communicate/read）。
- Trace 摘要: `TimeoutError`；执行命令后读取子进程输出时超时（communicate/read）

### sales-pivot-analysis

- 最终状态: `error`
- 分类: `执行超时`
- attempt 数: `2`
- 具体失败原因: 最终 attempt 触发 `TimeoutError`；trace 显示启动子进程时超时（create_subprocess_exec）。
- Trace 摘要: `TimeoutError`；启动子进程时超时（create_subprocess_exec）
- 较早 attempt 暴露的问题: Failed tests: - tests/test_outputs.py::TestPivotTableConfiguration::test_pivot_row_is_state - tests/test_outputs.py::TestPivotTableConfiguration::test_pivot_uses_correct_aggregation -...

### scheduling-email-assistant

- 最终状态: `error`
- 分类: `执行超时`
- attempt 数: `1`
- 具体失败原因: 最终 attempt 触发 `TimeoutError`；trace 显示启动子进程时超时（create_subprocess_exec）。
- Trace 摘要: `TimeoutError`；启动子进程时超时（create_subprocess_exec）

### seismic-phase-picking

- 最终状态: `error`
- 分类: `执行超时`
- attempt 数: `1`
- 具体失败原因: 最终 attempt 触发 `TimeoutError`；trace 显示启动子进程时超时（create_subprocess_exec）。
- Trace 摘要: `TimeoutError`；启动子进程时超时（create_subprocess_exec）

### shock-analysis-demand

- 最终状态: `error`
- 分类: `执行超时`
- attempt 数: `1`
- 具体失败原因: 最终 attempt 触发 `TimeoutError`；trace 显示启动子进程时超时（create_subprocess_exec）。
- Trace 摘要: `TimeoutError`；启动子进程时超时（create_subprocess_exec）

### shock-analysis-supply

- 最终状态: `error`
- 分类: `执行超时`
- attempt 数: `1`
- 具体失败原因: 最终 attempt 触发 `TimeoutError`；trace 显示启动子进程时超时（create_subprocess_exec）。
- Trace 摘要: `TimeoutError`；启动子进程时超时（create_subprocess_exec）

### software-dependency-audit

- 最终状态: `error`
- 分类: `执行超时`
- attempt 数: `1`
- 具体失败原因: 最终 attempt 触发 `TimeoutError`；trace 显示执行命令后读取子进程输出时超时（communicate/read）。
- Trace 摘要: `TimeoutError`；执行命令后读取子进程输出时超时（communicate/read）

### taxonomy-tree-merge

- 最终状态: `error`
- 分类: `执行超时`
- attempt 数: `1`
- 具体失败原因: 最终 attempt 触发 `TimeoutError`；trace 显示执行命令后读取子进程输出时超时（communicate/read）。
- Trace 摘要: `TimeoutError`；执行命令后读取子进程输出时超时（communicate/read）

### threejs-to-obj

- 最终状态: `error`
- 分类: `执行超时`
- attempt 数: `2`
- 具体失败原因: 最终 attempt 触发 `TimeoutError`；trace 显示执行命令后读取子进程输出时超时（communicate/read）。
- Trace 摘要: `TimeoutError`；执行命令后读取子进程输出时超时（communicate/read）
- 较早 attempt 暴露的问题: Failed tests: - tests/test_outputs.py::TestObjExport::test_geometry_matches_ground_truth Pytest failure details: [Failure block 1] =================================== FAILURES ===================================...

### video-silence-remover

- 最终状态: `error`
- 分类: `执行超时`
- attempt 数: `2`
- 具体失败原因: 最终 attempt 触发 `TimeoutError`；trace 显示执行命令后读取子进程输出时超时（communicate/read）。
- Trace 摘要: `TimeoutError`；执行命令后读取子进程输出时超时（communicate/read）
- 较早 attempt 暴露的问题: Pytest failure details: [Failure block 1] _ ERROR collecting jobs/skillsbench-rq1-2026-04-09__20-35-18/video-silence-remover__sPUraiT/task_root/tests/test_outputs.py _ ImportError while importing test module '/hy-...

### weighted-gdp-calc

- 最终状态: `error`
- 分类: `执行超时`
- attempt 数: `2`
- 具体失败原因: 最终 attempt 触发 `TimeoutError`；trace 显示启动子进程时超时（create_subprocess_exec）。
- Trace 摘要: `TimeoutError`；启动子进程时超时（create_subprocess_exec）
- 较早 attempt 暴露的问题: Failed tests: - tests/test_outputs.py::TestStep1DataValues::test_exports_values - tests/test_outputs.py::TestStep1DataValues::test_imports_values - tests/test_outputs.py::TestStep1DataValues::test_gdp_values -...

### xlsx-recover-data

- 最终状态: `error`
- 分类: `执行超时`
- attempt 数: `1`
- 具体失败原因: 最终 attempt 触发 `TimeoutError`；trace 显示启动子进程时超时（create_subprocess_exec）。
- Trace 摘要: `TimeoutError`；启动子进程时超时（create_subprocess_exec）

### virtualhome-agent-planning

- 最终状态: `error`
- 分类: `无尝试记录`
- attempt 数: `0`
- 具体失败原因: 任务无 attempt 记录，无法从 `aggregated_results.json` 中定位具体 trace。

### fix-druid-loophole-cve

- 最终状态: `error`
- 分类: `模型调用限流`
- attempt 数: `1`
- 具体失败原因: 最终 attempt 抛出 `RetryError`，其底层异常为 `RateLimitError`，说明模型调用被限流且重试耗尽。
- Trace 摘要: `RetryError` / RetryError[<Future at 0x7f1bf15547d0 state=finished raised RateLimitError>]；见异常栈

### latex-formula-extraction

- 最终状态: `error`
- 分类: `模型调用限流`
- attempt 数: `1`
- 具体失败原因: 最终 attempt 抛出 `RetryError`，其底层异常为 `RateLimitError`，说明模型调用被限流且重试耗尽。
- Trace 摘要: `RetryError` / RetryError[<Future at 0x7f2c03ec7d10 state=finished raised RateLimitError>]；见异常栈

### multilingual-video-dubbing

- 最终状态: `error`
- 分类: `模型调用限流`
- attempt 数: `1`
- 具体失败原因: 最终 attempt 抛出 `RetryError`，其底层异常为 `RateLimitError`，说明模型调用被限流且重试耗尽。
- Trace 摘要: `RetryError` / RetryError[<Future at 0x7f6973d4c8c0 state=finished raised RateLimitError>]；见异常栈

### setup-fuzzing-py

- 最终状态: `error`
- 分类: `模型调用限流`
- attempt 数: `1`
- 具体失败原因: 最终 attempt 抛出 `RetryError`，其底层异常为 `RateLimitError`，说明模型调用被限流且重试耗尽。
- Trace 摘要: `RetryError` / RetryError[<Future at 0x7f0dba09fd10 state=finished raised RateLimitError>]；见异常栈

### spring-boot-jakarta-migration

- 最终状态: `error`
- 分类: `模型调用限流`
- attempt 数: `1`
- 具体失败原因: 最终 attempt 抛出 `RetryError`，其底层异常为 `RateLimitError`，说明模型调用被限流且重试耗尽。
- Trace 摘要: `RetryError` / RetryError[<Future at 0x7f2266d27260 state=finished raised RateLimitError>]；见异常栈

### suricata-custom-exfil

- 最终状态: `error`
- 分类: `模型调用限流`
- attempt 数: `1`
- 具体失败原因: 最终 attempt 抛出 `RetryError`，其底层异常为 `RateLimitError`，说明模型调用被限流且重试耗尽。
- Trace 摘要: `RetryError` / RetryError[<Future at 0x7fb45bb53830 state=finished raised RateLimitError>]；见异常栈

### syzkaller-ppdev-syzlang

- 最终状态: `error`
- 分类: `模型调用限流`
- attempt 数: `1`
- 具体失败原因: 最终 attempt 抛出 `RetryError`，其底层异常为 `RateLimitError`，说明模型调用被限流且重试耗尽。
- Trace 摘要: `RetryError` / RetryError[<Future at 0x7fce2d150560 state=finished raised RateLimitError>]；见异常栈

### invoice-fraud-detection

- 最终状态: `failed`
- 分类: `验证失败-依赖缺失`
- attempt 数: `6`
- 具体失败原因: verifier 在测试收集阶段失败；trace 显示 `ModuleNotFoundError: No module named 'rapidfuzz'`。
- Trace/notes 摘要: Pytest failure details: [Failure block 1] _ ERROR collecting jobs/skillsbench-rq1-2026-04-09__10-55-36/invoice-fraud-detection__0MZl8wG/task_root/tests/test_outputs.py _ ImportError while importing test module '/hy-...

### pptx-reference-formatting

- 最终状态: `failed`
- 分类: `验证失败-依赖缺失`
- attempt 数: `6`
- 具体失败原因: verifier 在测试收集阶段失败；trace 显示 `ModuleNotFoundError: No module named 'rapidfuzz'`。
- Trace/notes 摘要: Pytest failure details: [Failure block 1] _ ERROR collecting jobs/skillsbench-rq1-2026-04-09__16-25-22/pptx-reference-formatting__9SMf6lf/task_root/tests/test_outputs.py _ ImportError while importing test module '/hy-...

### fix-build-google-auto

- 最终状态: `failed`
- 分类: `验证失败-环境变量缺失`
- attempt 数: `6`
- 具体失败原因: verifier 的 pytest 失败，trace 指向 `tests/test_outputs.py:53`，断言 `REPO_ID environment variable is not set`。
- Trace/notes 摘要: Failed tests: - tests/test_outputs.py::test_diff_exists Pytest failure details: [Failure block 1] =================================== FAILURES =================================== _______________________________...
