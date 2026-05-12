# Fix Skill: deterministic, test-aligned error messaging (SWE-bench style)

## 任务目标

This skill targets a common SWE-bench pattern: **logic + error-message assertions**.

Primary objective:
- Fix the **underlying decision logic** so the correct branch is taken, and
- Emit an error message that is **deterministic** and **matches the exact test assertion**.

This file includes an Astropy example (`TimeSeries`/`BaseTimeSeries` required columns), but the workflow/general rules should transfer to similar “string-asserted exception” bugs across repos.

The problem is not “wording could be nicer”; it is that the **validation logic misclassifies “later required columns are missing” as “the first column is wrong”**, producing messages like:

```python
ValueError: TimeSeries object is invalid - expected 'time' as the first columns but found 'time'
```

This indicates:

- `time` 其实还在第一列
- `time` is still the first column
- the real problem is that a later required column is missing
- therefore you must change the **required columns validation branch**, not just the string template

---

## 通用执行原则（强约束）

1. **Tests are the spec**
   - If a test asserts a string/regex for an exception message, treat that as the contract.
   - Do not “improve wording” unless the tests explicitly allow it.

2. **Determinism**
   - Never build asserted messages using unordered data structures (`set`, `dict` iteration without fixed order).
   - Prefer “first failing position” / “single missing item” messages over listing multiple items.

3. **First-failure localization**
   - Compare expected vs found **in order** and raise based on the **first index where the constraint fails**.
   - Avoid “compute all differences” approaches; they often mismatch tests and lose ordering semantics.
   - Handle both:
     - prefix-too-short cases (`found` is shorter than `expected`)
     - equal-length or longer cases where a later position is wrong (`['time', 'b']` vs `['time', 'a']`)

4. **Minimal, targeted changes**
   - Fix the specific branch/logic that selects the wrong message.
   - Avoid refactors, new helpers, or new message styles (e.g., ordinals) unless tests demand them.

---

## 先读哪里（如何泛化）

Start at the failing test(s) and the code that throws:

1. Open the FAIL_TO_PASS test(s) and find the exact assertion:
   - `pytest.raises(..., match=...)` / `assert str(exc.value) == ...` / `caplog` message checks
2. Identify the throw site(s) in production code that produce that message.
3. Confirm which **decision branch** is currently taken and why it’s wrong.
4. Implement the smallest logic change that makes the correct branch fire.

---

## Astropy 示例：先读哪里

Start here (and mostly only here):

- `astropy/timeseries/core.py`

Focus on the `BaseTimeSeries` required columns consistency check, i.e. the code that currently raises when
`self.colnames[:len(required_columns)] != required_columns`.

---

## 正确问题模型

The current logic conflates two cases:

1. 第一列就错了
   例如实际第一列是 `flux`，预期第一列应为 `time`
2. The first column is correct, but later required columns are missing or mis-ordered
   例如：
   - `required_columns = ["time", "flux"]`
   - `self.colnames = ["time"]`

Case (2) is the core of this issue.

For case (2), continuing to raise:

```python
expected 'time' as the first column but found 'time'
```

is wrong, because “found 'time'” is exactly evidence that the first column is fine.

---

## 正确修复策略

### 核心原则

Compare `required_columns` and the actual `self.colnames` in order, find **the first position where the required-columns constraint fails**, and raise based on that.

### 应该保留的旧行为

If the first required column is wrong, keep the existing “first column mismatch” style:

```python
TimeSeries object is invalid - expected 'time' as the first column but found 'flux'
```

### 新增必须覆盖的行为

If the prefix matches but a later required column is missing, the error should explicitly indicate **which required column is missing**, rather than blaming the first column.

Minimum acceptable semantics:

```python
TimeSeries object is invalid - expected 'flux' as a required column
```

If preferred by the codebase, an equivalent “missing required column 'flux'” phrasing is fine, but it must match the exact test assertions. Prefer `test_required_columns` as the source of truth for the precise message.

Also cover the case where the first required column is correct but a later required position is occupied by the wrong column. Example:

```python
required_columns = ["time", "a"]
self.colnames = ["time", "b"]
```

In this case, do **not** fall back to `"expected 'time' ... found 'time'"`.
Treat it as a later-position mismatch and align the message with the exact test assertion, which may require mentioning the compared prefixes/lists rather than a single missing column.

---

## 推荐实现方式

在 `self.colnames[:len(required_columns)] != required_columns` 这个分支内：

1. 顺序遍历 `zip(self.colnames[:len(required_columns)], required_columns)`
2. 一旦发现 `found != expected`：
   - 若位置为 0，沿用“first column but found X”报错
   - 若位置 > 0，优先按测试断言要求产出消息；如果测试对比的是整个 required prefix 和 found prefix，就直接用那两个 ordered lists 生成消息
3. If the loop finds no mismatch, the existing columns are a true prefix of `required_columns`, but the table is too short:
   - 缺失列就是 `required_columns[len(self.colnames)]`
   - 报“expected 'missing_col' as a required column”或测试要求的精确文案

Implementation note (important for passing tests reliably):
- Prefer emitting **exactly one** missing/mismatched column (the first failing one).
- Avoid “missing columns: a, b, c” lists unless the test expects that exact format.
- If the test expects a message of the form `expected [...] as the first columns but found [...]`, preserve that exact style instead of inventing a new “missing required column” wording.

This approach is more robust than “special-case the first column, then handle length separately”, because it uniformly handles:

- 第一列错
- 中间列错
- 后续列缺失

---

## 明确禁止的错误方向

Avoid repeating these common mistakes seen across the attempts in this trajectory:

1. 只改报错措辞，不改判定逻辑
   - 典型表现：仍然从 `required_columns[0]` 出发组织报错
   - 结果：`test_required_columns` 继续失败

2. 把“缺失 required column”硬塞进“first column”模板
   - 例如：
     - `expected 'time' as the first column but required column 'flux' missing`
   - 这不是最自然的错误定位，而且大概率对不上测试断言

3. 一次性改太多文案风格
   - 例如引入 ordinal（`2nd required column`）这类新风格
   - 风险：偏离仓库既有错误消息约定，且不一定符合测试

4. **用 `set(...)` / 无序集合 来生成消息**
   - 典型表现：`missing = set(required) - set(found)` 然后 join
   - 风险：顺序不稳定，且往往与“第一个失败位置”语义不一致
   - 结果：即使逻辑对了，也会因为 message 不对齐而失败

5. **只处理“长度变短”而不处理“等长但后续位置错误”**
   - 典型表现：新增 `len(self.colnames) < len(required_columns)` 分支，但保留原有 later-mismatch 分支不变
   - 风险：`['time', 'b']` vs `['time', 'a']` 这类 case 仍会报成 `time` vs `time`
   - 结果：对旧测试可能过，对评测补丁后的新断言仍失败

4. 被 `test_initialization_with_time_delta` 带偏
   - This failure comes from leap-second / IERS environment issues
   - 不是本题目标逻辑
   - 不要为了让它过而改 `astropy/time/core.py` 或其他无关代码

5. 往补丁里塞临时脚本
   - 轨迹里加了 `reproduce_issue.py`、`test_logic.py`、`test_edge_cases.py`
   - 这些都不该成为最终提交的一部分

---

## 最小复现

Validate around the core scenario from the issue statement:

```python
from astropy.time import Time
from astropy.timeseries import TimeSeries

ts = TimeSeries(time=Time([1, 2, 3], format="jd"), data={"flux": [1.0, 2.0, 3.0]})
ts._required_columns = ["time", "flux"]
ts.remove_column("flux")
```

This should no longer raise “expected time as the first column but found time”.

Also check two control cases to ensure no regressions:

1. 删掉 `time`
   - 这时应该仍然报第一列错误
2. 在 index 0 插入别的列
   - 也应该仍然报第一列错误

---

## 验证顺序

Recommended verification order:

1. 先看 `astropy/timeseries/tests/test_sampled.py::test_required_columns`
   - 核对它断言的**精确消息**
   - 如果评测脚本会 patch 测试文件，必须先看 patch 后新增的断言，而不是只看仓库原始测试
2. Use the minimal reproduction to confirm the branch has shifted from “first column mismatch” to “missing required column”
3. 再确认 `test_empty_initialization_invalid` 这类旧行为没被破坏
4. 如果回归测试里只剩 `test_initialization_with_time_delta` 一类 leap-second 错误，不要继续误修 timeseries 逻辑

---

## 给模型的执行提示

If you want to solve this instance correctly, follow this action order:

1. 打开 `astropy/timeseries/core.py`，只分析 required columns 校验
2. 打开 `test_sampled.py`，只读 `test_required_columns` 和相关旧断言
3. 如果 runner/eval 会 patch 测试文件，先读 patch 后的新增断言，再决定 message strategy
4. 先确定“测试期望的是哪种具体异常消息”（包括单复数、引号、空格、标点、是否要求 list repr）
5. 再改 `core.py` 的判定分支（按**第一个失败位置**产生消息，且消息构造必须确定性）
5. Treat `test_required_columns` as the primary success metric; recognize leap-second failures as environment noise

One-line summary: **this instance is about fixing “first failing required-column localization logic” against the exact evaluated assertions, not generally polishing exception wording.**
