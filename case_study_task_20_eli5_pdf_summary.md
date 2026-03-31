# Case Study: `task_20_eli5_pdf_summary`

## Task Overview

- Task ID: `task_20_eli5_pdf_summary`
- Name: `ELI5 PDF Summary`
- Source trace: [/root/skill/results/rq1/0028_minimax-cn-MiniMax-M2-5.json](/root/skill/results/rq1/0028_minimax-cn-MiniMax-M2-5.json)
- User instruction: `Read the file GPT4.pdf in my workspace. Write an ELI5 summary and save it to eli5_summary.txt.`

This is a useful first-attempt waste case because the agent spent `1,226,263` total tokens in attempt 1 alone:

- `input_tokens`: `1,056,259`
- `output_tokens`: `3,281`
- `cache_read_tokens`: `166,608`
- `cache_write_tokens`: `115`
- `request_count`: `16`

The key pattern is not retry overhead. The failure happens much earlier: a raw PDF read injects a huge binary payload into the conversation, and that payload is then carried through the remaining 15 internal rounds.

## Core Diagnosis

The first attempt contains two different kinds of cost:

`Necessary work`
- Detect that `GPT4.pdf` is not plain text.
- Use a PDF extraction path.
- Draft `eli5_summary.txt`.
- Do a light verification pass.

`Waste`
- Reading the raw binary PDF directly into the model context.
- Spending multiple recovery rounds after that mistake while carrying the contaminated context.
- Writing a factually wrong summary from the extracted text.
- Spending many edit rounds fixing self-introduced formatting and Unicode issues.

The dominant waste is `context contamination`: after round 1, every later model call carries roughly `64k-73k` input tokens.

## Condensed Timeline

### Phase 1: Wrong initial read poisons the context

- `Round 1`
  Action: `read GPT4.pdf`
  Tokens: `10,622 total` (`20 input`)
  Assessment: the intent is reasonable, but the tool choice is wrong. Reading a binary PDF as raw text causes malformed transcript chunks and injects PDF bytes into context.

- Evidence of contamination
  The transcript immediately records parse errors with raw payload lengths of `8,548`, `34,407`, `26,570`, `5,380`, and `50,392` characters. This is the first major waste event.

### Phase 2: Recovery attempts under inflated context

- `Round 2`
  Action: check for `pdftotext`, `pdfgrep`, `strings`
  Tokens: `75,098 total` (`64,207 input`)
  Assessment: necessary recovery direction, but now extremely expensive because the previous binary payload is in context.

- `Round 3`
  Action: `strings GPT4.pdf | head -200`
  Tokens: `75,480 total` (`64,995 input`)
  Assessment: low-value exploration. It confirms the PDF is compressed but adds no usable paper content.

- `Round 4`
  Action: try installing `poppler-utils`
  Tokens: `77,024 total` (`66,488 input`)
  Assessment: mostly waste. Installing a system package is a heavy recovery path for a task that only needs text extraction.

- `Round 5`
  Action: `pip install pypdf` and extract text with Python
  Tokens: `77,391 total` (`66,848 input`)
  Assessment: useful. This is the first clearly productive extraction step.

### Phase 3: Draft is produced, but from a wrong understanding

- `Round 6`
  Action: write `eli5_summary.txt`
  Tokens: `81,547 total` (`70,301 input`)
  Assessment: necessary file creation, but the content is already off track.

- Main content errors introduced here
  The draft says the PDF is `"Sparks of Artificial General Intelligence: Early Experiments with GPT-4" by Microsoft Research`.
  The validator later says this is wrong: the task PDF was OpenAI's GPT-4 Technical Report.
  The draft also claims GPT-4 can `"Create pictures from descriptions"`, which the validator flags as inaccurate.

This means the agent uses an expensive extraction path and still converts it into a factually incorrect summary. Those tokens are not just large; they are low-yield.

### Phase 4: Self-inflicted cleanup loop

- `Round 7`
  Action: first edit to remove Chinese characters
  Tokens: `81,936 total`
  Assessment: waste. This is fixing a defect introduced by the agent itself.

- `Round 8`
  Action: reread `eli5_summary.txt`
  Tokens: `82,072 total`
  Assessment: partially useful verification, but still running under bloated context.

- `Rounds 9-14`
  Actions: repeated `edit` calls and one `grep -n "超级"` search
  Tokens:
  `82,529`, `82,662`, `82,861`, `83,065`, `83,161`, `83,441`
  Assessment: mostly waste. These rounds repair self-introduced Unicode issues and restore a deleted section header.

- `Round 15`
  Action: `grep -n "�"` and `wc -w`
  Tokens: `83,558 total`
  Assessment: useful but late. Word-count verification should have happened earlier and more cheaply.

- `Round 16`
  Action: final answer
  Tokens: `83,816 total`
  Assessment: necessary closure, but it incorrectly states that `458` words is within the requested `200-400` range.

## Where the First-Attempt Tokens Went

### 1. Structural waste from binary-context carryover

The per-round inputs are:

`20, 64,207, 64,995, 66,488, 66,848, 70,301, 71,174, 71,596, 71,945, 72,153, 72,286, 72,485, 72,689, 72,828, 73,065, 73,179`

Interpretation:

- The task is not naturally a `64k+` prompt task.
- The jump from `20` to `64,207` after the raw `read` strongly indicates that the PDF bytes became part of the persistent conversation state.
- Every later round then pays again for that mistake.

Conservative lower bound:

- If we generously assume each later round really needed `10,000` input tokens, then repeated excess input is still at least `906,239` tokens.
- That is already `85.8%` of all first-attempt input tokens.

So even before discussing factual errors or extra edits, the attempt is dominated by a single bad context-ingestion decision.

### 2. Useful work

The genuinely useful sequence is short:

1. recognize plain `read` is not enough for a PDF
2. use a PDF extraction method
3. write the summary file
4. run one brief verification pass

Everything beyond that minimal path is either recovery cost or cleanup cost.

### 3. Self-inflicted rework

Rounds `7-14` are largely devoted to repairing:

- mixed Chinese text in the draft
- an over-broad edit that removed the `## Are there any problems?` header
- leftover Unicode fragments

This is not user-required work. It is rework created by the model's own output.

### 4. Wrong-content cost

Even the "productive" drafting round is not fully necessary cost, because it produces a summary of the wrong paper and introduces factual inaccuracies. That means a non-trivial share of round 6 is semantically wasted, even though it looks like forward progress in the action trace.

## Necessary vs Wasteful Cost

A strict exact split is impossible from trace metadata alone, because the trace records token totals per round, not token attribution per sentence. But the causal split is still clear.

`Clearly necessary`
- the successful extraction path in round 5
- the initial drafting/write in round 6
- one lightweight verification pass near the end

`Clearly wasteful`
- round 1 raw binary read as context-ingestion strategy
- round 3 `strings` probing
- round 4 system-package installation attempt
- rounds 7-14 self-repair loop
- the final mistaken claim that `458` words satisfies the target length

`Structurally wasteful even when locally reasonable`
- rounds 2, 5, 8, 15: these actions have some legitimate purpose, but their token cost is massively inflated because the binary payload remains in context

## Timeline Takeaway

This first attempt shows a specific failure mode that is different from "the agent retried too much":

1. one early tool choice pollutes context
2. the model keeps acting inside that polluted context
3. later rounds become expensive even when they are locally sensible
4. the agent then adds another layer of waste by fixing self-introduced defects

So for RQ1, this trace is strong evidence that first-attempt token waste is not just "exploration". It includes:

- `context-ingestion waste`
- `recovery-path waste`
- `self-repair waste`
- `wrong-content waste`

## Practical RQ1 Framing

If you want to use this in the paper, a concise claim is:

> In `task_20_eli5_pdf_summary`, most first-attempt cost was not required by the task itself. A single raw-PDF read contaminated the prompt state, after which the agent repeatedly paid `64k-73k` input tokens per round. The attempt then spent additional rounds repairing self-introduced output defects, even though the resulting summary was still factually wrong.

This makes the trace a good counterexample to the idea that token waste is mainly caused by external retry. Here, the waste is already severe before the validator says anything.


从这个 trace 看，cache 命中的其实只有一小段稳定前缀，后面真正贵的部分基本都是动态上
  下文，所以几乎没法继续命中。

  先看每轮数字，task_20 第一次 attempt 的 usage_per_round 里：

  - Round 1: input 20, cache_read 10413
  - Round 2: input 64207, cache_read 10413
  - Round 3: input 64995, cache_read 10413
  - ...
  - Round 16: input 73179, cache_read 10413

  这里最关键的现象是：

  - cache_read_tokens 几乎固定不变，始终在 10413
  - input_tokens 却一路维持在 64k-73k

  这基本说明两件事：

  1. 有一段稳定前缀一直被命中 cache
  2. 后面那大块上下文每轮都在变化，所以没有继续命中 cache

  你要的拆分，可以这样理解。

  更像“稳定前缀，已被 cache”
  大概率包括这些：

  - 系统提示词
  - agent 固定行为说明
  - benchmark task 的原始用户请求
  - 一些每轮都不变的工具 schema / 会话固定头部
  - 在 provider 侧能识别为“相同前缀”的那部分历史

  在这个 trace 里，这部分规模大概就是每轮固定的那 ~10,413 cache_read_tokens。

  更像“动态脏上下文，无法被 cache”
  大概率包括这些：

  - 第 1 轮 read GPT4.pdf 后塞进来的原始 PDF 文本/二进制碎片
  - 这些碎片导致的 parse error / raw transcript 内容
  - 每一轮新的 tool result
  - 每一轮新的 thinking / assistant text / tool call
  - 每一轮对 eli5_summary.txt 的编辑结果和文件内容变化
  - 逐轮增长的会话尾部

  这部分就是后面每轮那 64k-73k 的主体。

  为什么后面“那么多没命中 cache”？

  核心原因不是“有 cache 但失效了”，而是这类 prompt caching 通常只对“从开头开始、完全一
  致的前缀”生效。一旦大块脏内容出现在前面，而且后续每轮尾部还不断变化，模型请求虽然“很
  像”，但不是“同一个长前缀”。于是：

  - 前面一小段固定头部还能命中
  - 后面大段 PDF 垃圾 + 工具结果 + 编辑历史是动态的
  - 动态部分每轮都得重新算，记进 input_tokens

  更直白一点：

  不是 cache 没工作，而是它只救下了前面 10k 左右；
  真正贵的那 60k+ 是后面不断变化的脏上下文，cache 天然救不了。

  你可以把时间轴里直接标成这样：

  - Round 1 read GPT4.pdf
    标注：引入动态脏上下文的起点
  - Rounds 2-16
    标注：稳定前缀约 10.4k，已命中 cache；其余约 54k-63k 为动态上下文，未命中 cache
  - Rounds 7-15
    标注：动态上下文继续膨胀，因为新增了错误草稿、重复 edit、grep/read 结果

  如果你愿意，我可以直接把 case_study_task_20_eli5_pdf_summary.md 改一版，在每个 phase
  下面加上：

  - cached prefix
  - uncached dynamic context
  - why cache did not help here
    三个小段。