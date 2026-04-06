#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

MODEL_ARGS=()
if [[ $# -gt 0 && "${1}" != -* ]]; then
  MODEL_ARGS=(--model "$1")
  shift
elif option_supplied --model "$@"; then
  :
elif [[ -n "${MODEL:-}" ]]; then
  MODEL_ARGS=(--model "${MODEL}")
else
  echo "Usage: $0 MODEL [extra benchmark args...]" >&2
  echo "Or pass --model MODEL_ID, or set MODEL in the environment." >&2
  exit 2
fi
EXTRA_ARGS=("$@")

SUITE_ARGS=()
if ! option_supplied --suite "${EXTRA_ARGS[@]}"; then
  SUITE_ARGS=(--suite "$(default_suite)")
fi

RUNS_ARGS=()
if ! option_supplied --runs "${EXTRA_ARGS[@]}"; then
  RUNS_ARGS=(--runs "$(default_runs)")
fi

RESULTS_DIR="${RQ1_RESULTS_DIR:-results/rq1}"
ANALYSIS_DIR="${RQ1_ANALYSIS_DIR:-analysis/rq1}"
MAX_ATTEMPTS_VALUE="${RQ1_MAX_ATTEMPTS:-6}"

run_benchmark "${RESULTS_DIR}" \
  "${MODEL_ARGS[@]}" \
  "${SUITE_ARGS[@]}" \
  "${RUNS_ARGS[@]}" \
  --max-task-attempts "${MAX_ATTEMPTS_VALUE}" \
  --feedback-policy "${RQ1_FEEDBACK_POLICY:-error-localized}" \
  --feedback-format "${RQ1_FEEDBACK_FORMAT:-full-refresh}" \
  --feedback-answer-safety "no-answers" \
  --stop-rule "max-attempts-only" \
  "${EXTRA_ARGS[@]}"

run_analysis "${RESULTS_DIR}" "${ANALYSIS_DIR}" "policy"
# --model minimax-cn/MiniMax-M2.5 --suite task_06_events
# --model autodl/Kimi-K2.5
# ./scripts/experiments/rq1.sh  --backend pinchbench  --model minimax-cn/MiniMax-M2.5 --suite task_17_email_search,task_16_market_research
  # cd /hy-tmp/skill
  # ./scripts/experiments/rq1.sh minimax-cn/MiniMax-M2.5 --backend skillsbench --skillsbench-task-path tasks/speaker-diarization-subtitles,tasks/video-tutorial-indexer,tasks/xlsx-recover-data --max-task-attempts 6
# task_06_events,task_07_email,task_08_memory,task_09_files,task_10_workflow,task_11_clawdhub,task_12_skill_search,task_13_image_gen, task_14_humanizer,task_15_daily_summary,task_16_email_triage, task_17_email_search,task_16_market_research,task_18_spreadsheet_summary, task_20_eli5_pdf_summary,task_21_openclaw_comprehension,task_22_second_brain

#  ./scripts/experiments/rq1.sh minimax-cn/MiniMax-M2.5 \
    # --backend skillsbench \
    # --job-name skillsbench-rq1-2026-03-21__20-12-29 \
    # --max-task-attempts 1
  # 如果你问的是“哪些 task 从结构上看，更像是首轮容易失败、第二轮 verifier 反馈有明显价
  # 值的”，我会优先看这些。这里是基于任务说明、difficulty、超时配置和 verifier 严格度的
  # 推断，不是实测成功率统计。

  # 最像“至少两次更合理”的一组：

  # - speaker-diarization-subtitles
  #   task.toml 是 hard，而且 verifier 不只是查文件存在，还算 DER/JER/WER 这类质量指标；
  #   首轮很容易出现格式对了但指标不过线。见 tests/test_outputs.py。
  # - video-tutorial-indexer
  #   task.toml 是 hard，要对 29 个章节做精确时间对齐；首轮经常会先过结构检查，再被时间
  #   偏差打回。见 instruction.md 和 tests/test_outputs.py。
  # - xlsx-recover-data
  #   虽然 task.toml 只标了 medium，但 verifier 会检查 15 个缺失值、跨 sheet 依赖、残
  #   留 ???、行和一致性。很典型的“首轮修掉大部分，第二轮补漏”。见 tests/
  #   test_outputs.py。
  # - weighted-gdp-calc
  #   也是 medium，但 verifier 很长，既查公式结果，也查格式、sheet、无宏、统计区间是否完
  #   整。Excel 类任务里它比 xlsx-recover-data 更容易因为细节返工。见 instruction.md 和
  #   tests/test_outputs.py。
  # - fix-visual-stability
  #   task.toml 是 hard，而且是前端修复类任务。这类任务首轮常见问题是“修了一处、又引入另
  #   一处”，很适合 verifier 驱动的 repair loop。
  # - simpo-code-reproduction
  #   task.toml 是 hard，要读 paper、补 loss 实现、跑单测、产出数值文件，还要求环境信
  #   息。首轮容易出现“实现接近正确但数值不匹配”或“环境没配全”。
  # - syzkaller-ppdev-syzlang
  #   instruction.md 要写 syzlang 描述并通过 make descriptions、make all，verifier会检查
  #   ioctl、resource、常量、编译。很像典型的编译报错后第二轮修签名/常量。
  # - invoice-fraud-detection
  #   task.toml 是 hard，PDF + Excel + CSV + fuzzy matching，多源对齐很容易首轮漏边角
  #   case。

  # 还有几类我也会放进“重试价值较高”但不一定最优先的备选：

  # - enterprise-information-search
  #   instruction.md 需要在异构数据里答多个问题，还要把 token 写进输出；首轮常见是答案对
  #   一部分、格式不全。
  # - virtualhome-agent-planning
  #   tests/test_outputs.py 会做 plan validity 检查。PDDL 任务常见首轮语法对但 plan 不可
  #   执行。
  # - financial-modeling-qa
  #   task.toml 是 hard，PDF + Excel +问答，首轮容易因为读取策略不稳或数值口径错。

  # 如果你想挑“最适合验证你刚加的 retry+feedback 机制”的任务，我建议先用这 4 个：

  # 1. xlsx-recover-data
  # 2. weighted-gdp-calc
  # 3. simpo-code-reproduction
  # 4. syzkaller-ppdev-syzlang

  # 理由是它们的 verifier 失败信息相对明确，第二轮 prompt 更容易真正利用这些反馈；而像
  # speaker-diarization-subtitles、video-tutorial-indexer 这类虽然更难，但失败信号更偏质
  # 量阈值，repair loop 价值有时不如“换更强方法”。

  # 如果你要，我可以继续直接帮你筛出一个更小的列表：

  # - “本机最值得跑的 5 个”
  # - “最可能 first fail / second pass 的 5 个”
  # - “最不适合无 Docker 本地跑的任务”
