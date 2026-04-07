 更准确地说，这是两层问题：

  1. 模型侧问题

  - MiniMax 在这种 verifier-feedback -> 重新作答 -> 严格 JSON 协议 的闭环里，明显比一些更稳的模型更容
    易：
      - 输出非法 JSON
      - 收到失败反馈后过度发散
      - 不做局部修补，改成大范围重写
  - 这部分本质上是模型能力/对齐问题，你只能绕，不能真正“修好模型”。

  2. 运行框架侧问题

  - 这部分是能改的，而且通常能明显降失败率。
  - 你现在的问题不是单纯“模型笨”，而是框架把它最不擅长的模式放大了。

  可改的方向，按收益排序：

  1. 收紧 retry 提示，强制局部修复

  - 不要给它一大段开放式 verifier 输出，然后让它“自己理解并重做”。
  - 改成更硬的 prompt，比如：
      - 只允许修改已有输出文件
      - 不允许重写整体方案
      - 先列出上轮失败项，再只修这些项
      - 如果输出格式不是合法 JSON，直接给固定 fallback
  - 这通常是最有效的。
  
  对 JSON 输出加“硬约束”

  - 你已经看到很多 Previous response had parsing errors
  - 这说明 agent 协议层和 MiniMax 不够稳
  - 可以在 agent 层做：
      - 更严格的 JSON schema 提示
      - 非法 JSON 时自动抽取/修复一次，而不是完全回退给模型
      - 降低回复自由度，减少长分析文本

  2. 限制二轮预算

  - 现在很多失败像是“第二轮想太多”。
  - 可以让 retry 回合比首轮更短，比如：
      - 首轮正常 20 分钟
      - 后续每轮 5-8 分钟
  - 这样至少不会让一个 task 在错误修复阶段无限烧时间。

  3. 降低最大内层重试次数

  - 如果 MiniMax 的第二轮开始就容易发散，6 轮往往没意义。
  - 对这个模型，2 或 3 轮可能更合理。
  - 否则只是把 token 和时间烧在低质量修复上。

  4. 把 verifier feedback 做结构化压缩

  - 不要原样塞完整 pytest traceback。
  - 先把失败信息提炼成：
      - failing file
      - failing assertions
      - expected vs actual
      - top 3 likely causes
  - MiniMax 对长而乱的反馈更容易失控。



  6. 对特定任务禁用 retry

  - 有些任务首轮错了，二轮基本只会更糟。
  - 这类任务可以直接 max_task_attempts=1 或按 reward/no-improvement 提前停。

  所以结论是：

  - 有一部分确实是 MiniMax 的问题。
  - 但“在你这套 verifier-feedback 多轮框架里表现这么差”这件事，是可以通过 runner/prompt/retry policy
    优化明显缓解的。
  - 你修不了模型本身，但你可以把它从最容易失控的工作模式里拉出来。

  如果你要最务实的建议，我会这么做：

  1. 把 MiniMax 的内层 retry 从 6 降到 2 或 3
  2. retry prompt 改成“仅根据失败项做最小修复”
  3. verifier feedback 先压缩再喂
  4. 给 retry 单独更短 timeout
  5. 对 JSON 解析失败做 agent 侧修复，而不是完全依赖模型重答

  如果你愿意，我可以直接去看 run_terminus_local_host.py 里 feedback 拼接和 stop-rule 这段，给你出一版
  最小改动方案。



    - 00, 01, 02, 04, 08, 09, 11, 12, 21
  纯 llm_judge：
  - task_03_blog.md
  - task_05_summary.md
  - task_06_events.md
  - task_07_email.md
  - task_14_humanizer.md
  - task_15_daily_summary.md
  - task_20_eli5_pdf_summary.md
混合 hybrid，也包含 LLM judge：
  - task_10_workflow.md
  - task_13_image_gen.md
  - task_16_email_triage.md
  - task_17_email_search.md
  - task_18_market_research.md
  - task_19_spreadsheet_summary.md
  - task_22_second_brain.md
合计 14 个任务带 LLM 判分。

如何查看skillsbenc的命令以及如何续跑
最近一次的 minimax job_name 是：

  skillsbench-rq1-2026-04-06__13-09-43

  你可以从 /hy-tmp/skillsbench/jobs 下面反查出来；我刚确认这个目录里的 result.json 确实
  对应 model_name: minimax-cn/MiniMax-M2.5。

  所以续跑命令可以写成：

  cd /hy-tmp/skill
  SKILLSBENCH_APPEND_OUTPUT=1 ./scripts/experiments/rq1.sh minimax-cn/MiniMax-M2.5 \
    --backend skillsbench \
    --job-name skillsbench-rq1-2026-04-06__13-09-43 \
    --max-parallel-tasks 8