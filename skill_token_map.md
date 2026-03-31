# Skill Token Map

## Purpose

This document provides a two-dimensional labeling schema for analyzing token usage when an agent selects and uses a skill.

The schema is designed for first-attempt analysis across tasks such as:

- `task_06_events`
- `task_20_eli5_pdf_summary`
- `task_14_humanizer`
- similar search, extraction, writing, transformation, and workflow tasks

The goal is not to force every round into one exclusive label. The goal is to make token waste analysis:

- more complete
- more consistent across tasks
- more explicit about causal mechanisms

## Why A Two-Dimensional Schema

A one-layer label set is usually not enough.

Reason:

- a step can belong to one workflow stage but waste tokens for another reason
- the same round can be both necessary in intent and wasteful in execution
- many token costs are chain effects from earlier mistakes

Example:

- reading a PDF is an `input acquisition` step
- but if it reads raw binary into context, the waste mechanism is `context contamination`

So each step should be labeled with:

1. `primary label`: where in the skill lifecycle this happened
2. `secondary label`: why this step consumed tokens inefficiently

## Label Structure

Each analyzed step gets:

- `primary label` = lifecycle stage
- `secondary label` = waste or efficiency mechanism
- `status` = whether the step was necessary, overpriced, or clearly wasteful

Recommended format:

`[primary / secondary / status]`

Example:

- `[acquisition / context_contamination / wasteful]`
- `[bootstrap / overlong_instruction_load / overpriced]`
- `[generation / none / necessary]`

## Dimension 1: Primary Labels

Primary labels describe the workflow stage.

### `selection`

Definition:

- the model decides whether to use a skill, and which skill to use

Typical actions:

- choosing between direct execution and a skill
- choosing between multiple candidate skills
- deciding whether to switch skills

### `bootstrap`

Definition:

- the model loads the skill instructions or supporting usage information

Typical actions:

- reading `SKILL.md`
- reading help text, README, examples, CLI usage
- inspecting skill install or invocation docs

### `acquisition`

Definition:

- the model obtains the raw task input or source material needed for work

Typical actions:

- reading files
- fetching PDFs
- pulling HTML
- opening logs
- reading source documents
- querying initial source pages

### `exploration`

Definition:

- the model probes paths, tools, URLs, extraction methods, or search routes to get actionable signal

Typical actions:

- search engine queries
- alternate tool attempts
- retries after failures
- URL guessing
- process polling
- command variations

### `generation`

Definition:

- the model creates the user-facing artifact or substantive task output

Typical actions:

- writing `events.md`
- drafting a summary
- generating rewritten text
- creating a report

### `verification`

Definition:

- the model checks whether the generated artifact or extracted facts satisfy the task

Typical actions:

- reading output back
- word count checks
- grep checks
- validating presence of fields
- spot-checking factual coverage

### `repair`

Definition:

- the model edits or regenerates content to fix a detected issue

Typical actions:

- correcting formatting
- restoring deleted text
- removing corrupted characters
- fixing wrong facts

## Dimension 2: Secondary Labels

Secondary labels describe why a step was efficient or inefficient.

### `none`

Definition:

- no clear inefficiency mechanism; the step is straightforwardly productive

Use when:

- the step is clearly required
- the payload is compact
- there is no obvious sign of waste

### `misselection`

Definition:

- the wrong skill or wrong non-skill path was chosen

Use when:

- a different skill would likely have reached productive work faster
- the selected path predictably causes avoidable overhead

### `overlong_instruction_load`

Definition:

- reading skill instructions or docs injected substantially more context than the task justified

Use when:

- the task is simple
- multiple long skill docs are loaded before useful action
- only a small fraction of the instructions are later used

### `context_contamination`

Definition:

- a large, noisy, malformed, or low-value payload is inserted into model-visible context and inflates later rounds

Use when:

- raw binary is read
- huge HTML blobs are loaded
- noisy tool output is pasted back
- later rounds become expensive because of that history

### `format_mismatch`

Definition:

- the model used the wrong reading or extraction strategy for the source format

Use when:

- binary files are treated as plain text
- JS-heavy pages are handled with brittle static extraction
- structured data is consumed through a lossy path

### `tool_failure`

Definition:

- the tool path itself fails or is unavailable

Use when:

- missing MCP server
- missing dependency
- wrong command path
- install failure
- permission failure

### `search_noise`

Definition:

- the model consumes search-result pages or noisy web pages that provide low signal relative to their token cost

Use when:

- search engine result pages are parsed directly
- aggregator pages return lots of irrelevant content
- noisy pages provide little usable structured information

### `extraction_failure`

Definition:

- the model uses an extraction strategy that does not recover the needed fields cleanly

Use when:

- grep fails to isolate date/location
- HTML scraping yields fragments instead of answers
- content exists but the extraction method is low precision

### `redundant_retry`

Definition:

- the model retries paths that are repetitive and unlikely to add new signal

Use when:

- multiple near-identical searches are attempted
- repeated polling/kill cycles occur
- alternate URLs are tried without a meaningful strategy change

### `wrong_object`

Definition:

- the model does work on the wrong document, wrong page, wrong entity, or wrong target

Use when:

- it summarizes the wrong paper
- edits the wrong file
- uses the wrong site or conference record

### `wrong_content`

Definition:

- the step creates substantive task content that is incorrect or misaligned even if the action appears productive

Use when:

- the draft contains factual errors
- the rewrite violates constraints
- the generated file misses key required content

### `self_repair`

Definition:

- the model spends tokens fixing problems introduced by its own earlier output or actions

Use when:

- repeated edit loops fix formatting, Unicode, deletions, or self-created inaccuracies

### `cache_miss_amplification`

Definition:

- the local step may be reasonable, but token cost is amplified because unstable prior context prevents efficient cache reuse

Use when:

- cache reads stay flat while input tokens balloon
- later rounds are expensive mainly because the changing tail is large

This is usually a companion label for already contaminated histories.

## Dimension 3: Status Labels

Status labels describe whether the step was needed and whether its cost was justified.

### `necessary`

Definition:

- the step directly contributes to solving the task and is reasonably priced

### `overpriced`

Definition:

- the step is directionally reasonable, but the token cost is inflated relative to its value

Typical reasons:

- long context tail
- too much instruction loading
- too much raw payload

### `wasteful`

Definition:

- the step adds little or no task progress, or actively causes later waste

## Labeling Rules

These rules improve consistency.

### Rule 1: Label the local step, not the whole task

Do not say a whole task is `context_contamination`.

Instead:

- label the specific read step as contamination
- label later rounds as `cache_miss_amplification` or `overpriced`

### Rule 2: Primary label is about intent, secondary label is about mechanism

If a step reads a file, the primary label is still `acquisition` even if it is badly done.

The badness goes into the secondary label.

Correct:

- `[acquisition / format_mismatch / wasteful]`

Incorrect:

- using `format_mismatch` as the primary label

### Rule 3: Use `none` only when no stronger mechanism applies

If there is a recognizable failure mode, use it.

Do not overuse `none`.

### Rule 4: Prefer the earliest causal mechanism

If one step both fails and contaminates context:

- label that step with the most causally important mechanism
- then label later rounds with downstream mechanisms

Example:

- raw PDF read: `context_contamination`
- later extraction round in bloated context: `cache_miss_amplification`

### Rule 5: Separate wrong work from repair work

If the model creates incorrect content:

- generation step: `wrong_content`

If it later fixes that content:

- repair step: `self_repair`

### Rule 6: `overpriced` is not the same as `wasteful`

Use `overpriced` when:

- the step still had real value
- but the cost was too high

Use `wasteful` when:

- the step was low-yield or harmful

### Rule 7: Do not force exclusivity across the whole attempt

Different steps in one attempt can legitimately receive different labels.

The schema should capture sequence and causal structure, not collapse everything into one root cause.

## Optional Multi-Tag Rule

If one secondary label is not enough, allow:

- one primary label
- up to two secondary labels
- one status label

Recommended order for two secondary labels:

1. immediate mechanism
2. downstream amplification

Example:

- `[acquisition / format_mismatch + context_contamination / wasteful]`
- `[exploration / extraction_failure + redundant_retry / wasteful]`

Use this sparingly.

## Decision Procedure

For each token-heavy step:

1. What was the model trying to do?
   Choose the `primary label`.

2. Why was this step cheap, expensive, or unproductive?
   Choose the `secondary label`.

3. Did the step materially help?
   Choose the `status`.

4. Did a prior mistake inflate this step's cost?
   If yes, consider `cache_miss_amplification` or `overpriced`.

## Examples

### Example 1: Raw PDF read

Step:

- model reads `GPT4.pdf` as if it were plain text

Label:

- `[acquisition / format_mismatch + context_contamination / wasteful]`

Why:

- it is an acquisition step
- the format handling is wrong
- the payload likely pollutes later context

### Example 2: Recovery extraction after contaminated context

Step:

- model tries a better extraction route after the raw read already bloated history

Label:

- `[exploration / cache_miss_amplification / overpriced]`

Why:

- the local step may be reasonable
- but it is now operating under inflated context cost

### Example 3: Reading a long skill file for a simple task

Step:

- model reads a long `SKILL.md` before a simple operation

Label:

- `[bootstrap / overlong_instruction_load / overpriced]`

### Example 4: Failed tool endpoint

Step:

- model calls an unavailable search MCP

Label:

- `[exploration / tool_failure / wasteful]`

### Example 5: Parsing search results instead of final sources

Step:

- model repeatedly reads search result pages full of HTML noise

Label:

- `[exploration / search_noise / wasteful]`

### Example 6: Drafting the wrong answer

Step:

- model writes a polished but factually wrong summary

Label:

- `[generation / wrong_content / wasteful]`

### Example 7: Fixing self-created formatting corruption

Step:

- model runs repeated edits to fix Unicode and accidental deletion

Label:

- `[repair / self_repair / wasteful]`

## Task Mapping Sketches

### `task_06_events`

Likely sequence:

- read search skill doc: `[bootstrap / overlong_instruction_load / overpriced]`
- try unavailable search endpoint: `[exploration / tool_failure / wasteful]`
- parse noisy search pages: `[exploration / search_noise / wasteful]`
- probe official pages with weak extraction: `[exploration / extraction_failure / overpriced]`
- write final file: `[generation / none / necessary]`

Dominant waste pattern:

- exploration-heavy search loop

### `task_20_eli5_pdf_summary`

Likely sequence:

- raw PDF read: `[acquisition / format_mismatch + context_contamination / wasteful]`
- recovery probing in bloated history: `[exploration / cache_miss_amplification / overpriced]`
- successful extraction: `[exploration / none / necessary]`
- wrong summary draft: `[generation / wrong_content / wasteful]`
- repeated cleanup edits: `[repair / self_repair / wasteful]`

Dominant waste pattern:

- early contamination followed by expensive recovery and repair

### `task_14_humanizer`

Likely sequence:

- misuse install command: `[exploration / tool_failure / wasteful]`
- load skill docs: `[bootstrap / overlong_instruction_load / overpriced]`
- install and read real skill: `[bootstrap / none / necessary]`
- use skill CLI to rewrite: `[generation / none / necessary]`
- repeated invocation confusion if present: `[exploration / redundant_retry / wasteful]`

Dominant waste pattern:

- skill invocation confusion before productive use

## Minimal Annotation Template

Use this table for task analysis:

| Round / phase | Step description | Primary | Secondary | Status | Why |
|---|---|---|---|---|---|
| round X | read long skill doc | `bootstrap` | `overlong_instruction_load` | `overpriced` | too much instruction load for task size |
| round Y | raw PDF read | `acquisition` | `format_mismatch + context_contamination` | `wasteful` | wrong ingestion method polluted context |
| round Z | retry extraction | `exploration` | `cache_miss_amplification` | `overpriced` | locally useful but inflated by prior context |
| round K | repeated cleanup edits | `repair` | `self_repair` | `wasteful` | fixing model-created issues |

## What This Schema Still Does Not Solve

This schema is more complete than a flat label set, but it is still not perfectly exhaustive.

Remaining limits:

- some rounds genuinely have multiple plausible causal labels
- exact token attribution within a round is still approximate
- the same action can be productive in one environment and wasteful in another
- human annotators may still disagree on borderline cases

That is normal. The goal is consistency and explanatory power, not perfect metaphysical completeness.

## One-Sentence Summary

The right way to analyze skill token efficiency is not "what step happened," but "what stage was this, why did it become expensive, and did it actually move the task forward."
