# Case Study: `task_06_events`

## Task Overview

- Task ID: `task_06_events`
- Name: `Tech Conference Research`
- Category: `research`
- User instruction: `Find 5 upcoming tech conferences and create events.md with name, date, location, and website for each.`

This task is superficially simple: the agent only needs to collect five conference entries and write them into `events.md`. However, in the analyzed run (`results/rq1/0001_minimax-cn-MiniMax-M2-5.json`), the first attempt alone consumed `214,663` non-cache input tokens and involved `28` internal model requests before the first retry feedback was ever issued. This makes the sample a useful illustration of token waste *within* a single attempt.

## What Happened

The 28 internal rounds were not caused by the external validator. They were produced by the normal agent execution loop inside OpenClaw:

1. the LLM chose a tool call,
2. OpenClaw executed the tool,
3. the tool result was returned to the LLM,
4. the LLM decided the next action.

Only after the entire attempt ended did the benchmark grader determine whether the attempt passed. Therefore, this case mainly reflects `intra-attempt inefficiency`, not retry-level overhead.

## Condensed Timeline

### Phase 1: Tool bootstrap and immediate failure

- `Round 1`: The agent read `exa-web-search-free/SKILL.md`.
  Assessment: partially useful, but expensive for a simple research task.
- `Round 2`: The agent called `exa.web_search_exa(...)`.
  Result: `Unknown MCP server 'exa'`.
  Assessment: pure waste.
- `Round 3`: The agent read `multi-search-engine/SKILL.md`.
  Assessment: partially useful, but again expanded the context with a long skill document.

### Phase 2: Search attempts dominated by failures

- `Rounds 4-6`: The agent tried a DuckDuckGo `curl` search, then had to `poll` and `kill` the hanging process.
  Assessment: pure waste.
- `Round 7`: The agent tried Bing search.
  Result: it only extracted a Bing search URL instead of usable conference data.
  Assessment: waste.
- `Rounds 8-9`: The agent searched for CES through Google, then polled a hanging process.
  Assessment: waste.
- `Rounds 10-12`: The agent tried `espacel.com`, `conferenceindex.org`, and `eventbrite`.
  Results: page error, no output, or noisy links.
  Assessment: mostly waste.
- `Round 13`: The agent queried `techcrunch.com/events/`.
  Assessment: partially useful, but still high-noise HTML.

### Phase 3: More trial-and-error on official sites

- `Rounds 14-15`: The agent queried `ces.tech`, then polled another hanging process.
  Assessment: waste.
- `Round 16`: The agent queried `sxsw.com/conferences/`.
  Assessment: useful. This was one of the first clearly productive rounds.
- `Rounds 17-20`: The agent tried two different Google I/O related URLs and again had to kill or poll failed processes.
  Assessment: waste.
- `Rounds 21-23`: The agent made three more CES-related requests (`ces-event-info`, homepage regex extraction, `/about`).
  Assessment: partially useful. These rounds produced some signal, but at high token cost.
- `Round 24`: The agent queried `developer.apple.com/wwdc`.
  Assessment: partially useful.
- `Round 25`: The agent queried the AWS re:Invent official page and finally extracted a clean date/location signal.
  Assessment: useful.

### Phase 4: Writing the file

- `Round 26`: The agent wrote `events.md`.
  Assessment: useful.
- `Round 27`: The agent read `events.md` back for confirmation.
  Assessment: partially useful.

## Why Did Token Usage Explode?

The large input token count was not caused by a single long initial prompt. Instead, it came from the accumulation of many internal requests within one attempt.

Several factors contributed:

- The attempt contained `28` internal model requests.
- The agent read long skill files before acting.
- Multiple search commands failed, hung, or returned irrelevant HTML.
- Each subsequent request carried forward more conversation history, so later rounds became progressively more expensive.

In other words, the `214,663` input tokens for attempt 1 should be interpreted as:

`sum of all input tokens across the 28 internal requests in attempt 1`

rather than:

`the length of one initial prompt`

## Waste Pattern

This sample suggests that token waste arose from four recurring patterns:

1. `Tool bootstrap overhead`
   The agent loaded skill instructions at runtime instead of using a shorter, already-known tool policy.

2. `Environment misconfiguration discovery`
   The agent spent multiple rounds discovering that the `exa` MCP endpoint was unavailable.

3. `Search/tool instability`
   Several `curl`-based searches hung, returned noise, or pointed to irrelevant pages.

4. `History growth`
   Because the full interaction history stayed in context, each additional round became more expensive than the previous one.

## Takeaway for the Paper

This case shows that token inefficiency in agent workflows does not come only from retrying failed attempts. A substantial fraction of the waste may already happen *inside a single attempt*, before any external feedback loop starts. Therefore, a complete token-efficiency analysis should separate:

- `intra-attempt inefficiency`: waste caused by tool misfires, long search exploration, and context growth within one attempt;
- `inter-attempt inefficiency`: waste caused by retrying the entire task after external grading feedback.

The sample is useful because it demonstrates that even a simple research-and-write task can incur very high token cost if the agent enters a noisy tool exploration loop.


## 为什么搜索引擎这一步浪费了我那么多token

对，基本就是串行试的。不是“一次把很多引擎都跑了”，而是每一轮选一个路径，失败或信息
  不足，再进入下一轮换一个路径。

  从这条时间轴看，它大致是这么做的：

  1. 先读 exa-web-search-free
  2. 调 exa，直接失败
  3. 再读 multi-search-engine
  4. 用 DuckDuckGo 搜“upcoming tech conferences”
  5. 结果不好，再换 Bing
  6. 再换 Google / 具体 conference 搜索
  7. 再去聚合站，比如 conferenceindex、eventbrite
  8. 再去官方站，比如 sxsw.com、ces.tech、developer.apple.com/wwdc、aws.amazon.com/
     events/reinvent/
  9. 某些官方站抽不到，再换这个 conference 的别的 URL
  10. 最后拼出 events.md

  所以它不是“每个引擎都系统地测了一遍”，而是进入了这种模式：

  某条路没拿到可直接用的字段 -> 立即换另一条路

  为什么“每一个都不行”？
  不是说它们完全不行，而是“对它当时的抽取方法不行”。要分开看：

  1. 第一个 skill 真不行
  exa-web-search-free 这次是环境问题，不是搜索质量问题。
  它连不上 MCP server，直接报：
  Unknown MCP server 'exa'
  这一步是彻底失败。

  2. 搜索引擎结果页通常不是好数据源
  DuckDuckGo / Bing / Google 这类页的问题不是“搜不到”，而是：

  - 返回的是搜索结果页 HTML，不是结构化会议信息
  - HTML 噪声多
  - 可能有跳转、反爬、重定向、脚本
  - 它的 grep 很脆弱，容易只抓到 URL 或无关片段

  所以这里“不行”的意思通常是：
  没有抽到 name/date/location/website 这几个任务需要的字段
  而不是“网页上完全没有信息”。

  3. 聚合站信息多，但太脏
  像 conferenceindex、eventbrite 这种站，往往有很多活动，但问题是：

  - 真伪和时效性不稳定
  - 页面结构复杂
  - 不一定是“主会议信息页”
  - 抽出来的字段可能不完整
  - 对 benchmark 来说不够“可验证”

  所以不是它们完全没内容，而是：
  内容不够干净，不足以稳定支持最终答案

  4. 官方站也不一定“直接好抓”
  这点很关键。官方站也常常不容易抓，因为：

  - 日期可能在 JS 渲染内容里
  - 页面文案分散
  - URL 猜错就 404
  - grep 关键词太死，匹配不到
  - 页面里虽然有日期，但不是它正则想找的格式

  例如你 case 里：

  - sxsw.com 最后其实是抓到有用信息了
  - aws re:Invent 也抓到了比较干净的 date/location
  - ces.tech 则有明显“页面存在，但命中内容不稳定”的情况

  所以“为什么每一个都不行”，本质不是网站都没信息，而是：

  模型采用的是低鲁棒性的检索方式：curl + grep + 猜 URL

  这种方式只要：

  - 页面结构稍复杂
  - 字段不在静态 HTML 里
  - 关键词没对上
  - 返回内容太噪

  就会表现成“这条路不行”。

  更准确地说，这次失败链条里有三种“不行”：

  1. 工具级失败
     例：exa server 不存在
  2. 抽取级失败
     例：搜索页/官方页有内容，但 grep 没抽到可用字段
  3. 验证级失败
     例：模型主观上觉得“差不多找到了”，但 benchmark judge 认为“不足以证明日期已验证”

  所以你可以把它理解成：
  不是每个来源都没价值，而是每一步都只拿到“局部信号”，没能稳定转成任务所需的可验证字
  段。

  如果你要一个更直接的结论：

  它确实是在串行试多个路径；很多路径不是完全无效，而是对它当前的抓取方法和验证标准来
  说，产出不够稳定，所以它不断换路，最终把 token 堆高了。

## 解决方法
不要把“搜索引擎结果页”当成信息源
     Round 7 Bing、Round 8 Google、后面若干次搜索，本质上拿到的是 noisy HTML 或 URL，
     不是会议信息。
     搜索引擎结果页通常 token 性价比很差，因为内容杂、难抽取、易误导。
     更省 token 的做法是：
      - 先用一个极短搜索拿到候选域名
      - 之后只访问官方详情页
      - 不在搜索结果页里反复解析

之后retry也很费token：
append + full-refresh + max-attempts-only
append解决的是怎么跟之前的prompt交互，full-refresh解决的是每次retry都重新生成整个反馈prompt，max-attempts-only解决的是最多retry几次

input_tokens 字段不包含cache input
Tavily  需要API，每个月有1000条免费的机会，光是这个case就用了5个机会，但确实返回更短更规整更适合直接给模型消费的结果。
而multi-search-engine 容易让 agent 继续 curl Google/Bing/站点页面。一旦抓到 HTML，token 很快爆掉，但是multi-search-engine免费且不需要API配置什么的。
百度搜索也是需要API。

可优化的点：优化multi-search-engine，不过这只是工程上的实践
可优化的点：选什么skill得看你的skill 池子，如果你不引进那些很费token的skill，按理来说是不会很浪费token的，需要有一个skill的benchmark来评估每个skill的性价比
可优化的点：选错skill的话，会导致token浪费，比如/root/skill/results/rq1/0009_minimax-cn-MiniMax-M2-5.json 这个第一次选的skill直接curl，导致输入token猛增。不过这也说明minimax每次调用结果都不一样
了解到的点，一次attempt，openclaw是怎么判断要不要继续的（内部的多轮）：该次模型返回的结束原因是普通完成而不是继续 tool use，OpenClaw 就认为这回合结束。凡是有tool use 都会有下一步，直到不再调用tool use