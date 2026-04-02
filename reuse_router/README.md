# Reuse Router Prototype

This directory contains a lightweight prototype for task-aware routing, direct action reuse, macro-action reuse, and reuse-failure detection.

The prototype is intentionally simple but now covers the full control loop:

- `catalog.json` stores reusable task families, task membership, and distilled action skeletons.
- `route_request.py` scores a new request against the catalog and returns one of three modes:
  - `template_reuse`
  - `macro_reuse`
  - `full_model`
- `executor.py` executes a compiled reuse program directly without calling an LLM.
- `failure_rules.json` stores abort conditions for reuse.
- `failure_detector.py` evaluates runtime signals and returns either:
  - `continue_reuse`
  - `abort_and_fallback`

## Why this exists

The benchmark analysis suggests that direct trajectory reuse is only safe for a subset of tasks:

- some tasks have stable input/output structure and stable tool sequences;
- some tasks only support partial reuse of macro-actions;
- some tasks are exploration-heavy and should go directly to a stronger model.

This prototype turns that idea into an executable decision layer with runtime safeguards.

## Directory layout

- `catalog.json`
  Reuse families, task membership, keywords, score biases, and distilled action skeletons.
- `route_request.py`
  Static routing step for deciding whether a new request should use template reuse, macro reuse, or a full model.
- `executor.py`
  Direct executor for compiled cached-action programs. This is the LLM-free reuse path.
- `failure_rules.json`
  Rule table for retrieval miss and execution miss detection.
- `failure_detector.py`
  Runtime decision step for aborting bad reuse early.

## Usage

Route a natural-language request:

```bash
python3 reuse_router/route_request.py \
  --request "Fill a new California small claims PDF form from the case description and save the filled PDF."
```

Route a known benchmark task:

```bash
python3 reuse_router/route_request.py \
  --task-id task_19_spreadsheet_summary
```

Route with both task id and free-form request:

```bash
python3 reuse_router/route_request.py \
  --task-id court-form-filling \
  --request "Use the case facts to fill the court PDF and leave court-only fields empty."
```

Evaluate reuse failure from runtime signals:

```bash
python3 reuse_router/failure_detector.py \
  --runtime-json '{
    "family_score": 9,
    "family_score_gap": 3,
    "missing_slots_count": 0,
    "output_contract_passed": false,
    "missing_intermediate_artifacts_count": 1,
    "validator_error_expected": true,
    "trajectory_deviation_score": 0.52,
    "token_ratio_to_template_mean": 2.1,
    "time_ratio_to_template_mean": 1.3,
    "repair_progress_stalled": true
  }' \
  --pretty
```

Execute a direct reuse program without any model call:

```bash
python3 reuse_router/executor.py \
  --program-file reuse_router/examples/direct_reuse_program.json \
  --pretty
```

Run the task 21 direct-reuse prototype on any workspace by overriding slots:

```bash
python3 reuse_router/executor.py \
  --program-file reuse_router/programs/task_21_openclaw_comprehension_program.json \
  --slots-json '{
    "input_pdf": "/tmp/pinchbench/0008/agent_workspace/openclaw_report.pdf",
    "output_file": "/tmp/pinchbench/0008/agent_workspace/answer.txt"
  }' \
  --pretty
```

## Output

`route_request.py` returns JSON with:

- the chosen execution mode;
- the matched task family;
- the reusable template name when one is available;
- the feature-based score and feature breakdown;
- fallback guidance for runtime execution.

`failure_detector.py` returns JSON with:

- the runtime decision;
- triggered failure rules;
- a short natural-language summary of why reuse should continue or stop.

## Intended runtime policy

1. `template_reuse`
   Execute the compiled cached action program directly, with slot filling and checkpoint validation. No LLM participates in the reuse path.
2. `macro_reuse`
   Execute the cached macro-actions directly. If execution reaches a step that is not covered by the cached program, stop reuse and escalate to the full model.
3. `full_model`
   Skip reuse and start from a stronger model or full exploration policy.
4. `failure_detector.py`
   After the first checkpoints, inspect runtime signals and either continue reuse or abort to fallback.

## How strong-template routing works

The router uses two layers.

1. Task-family match
   If a known `task_id` is supplied and appears in a family, that family is prioritized.
2. Feature scoring
   The request text is scored using stable vs unstable task signals.

Current positive signals:

- stable output format
- stable tool sequence
- parameter substitution
- local validator repair

Current negative signals:

- open-ended search
- repo-specific debugging
- long-horizon reasoning

The result is:

- high-confidence stable family: `template_reuse`
- partially stable family: `macro_reuse`
- unstable or exploration-heavy family: `full_model`

## How direct reuse works

`template_reuse` is not prompt reuse.

The intended flow is:

1. compile a successful historical trajectory into a small action program;
2. bind the new request's slots into that program;
3. run the program with `executor.py`;
4. abort immediately if a checkpoint fails.

That means the reused portion is deterministic. If the router selects `template_reuse`, the system should not ask an LLM to "follow" the old trajectory. It should just execute the cached actions.

There is now a concrete benchmark-style example of this in:

- `programs/task_21_openclaw_comprehension_program.json`
- `programs/task21_cached_extract.py`

This pair encodes the first successful task-21 workflow as a direct cached-action program:

1. assert the PDF exists;
2. run the fixed PDF extractor script;
3. assert `answer.txt` exists;
4. assert the output contains the exact API phrase `typed WebSocket API`.

The compiled program format is deliberately small:

- `program_id`
- `mode`
- `slots`
- `compiled_steps`

Each step names an action primitive such as:

- `mkdir`
- `write_text`
- `append_text`
- `copy_file`
- `replace_text`
- `regex_replace`
- `assert_exists`
- `assert_contains`
- `run_command`

## How macro-action reuse works

Macro-action reuse does not replay the full old trajectory.

Instead, it reuses a compressed stage skeleton such as:

1. inspect inputs
2. identify required metrics or transformation target
3. run the stable middle-stage workflow
4. validate the local contract
5. patch only the narrow mismatch

For this mode, the reuse portion is still direct execution: run the cached macro-actions first. The LLM only appears after reuse has reached an uncovered step, at which point reuse stops and the request is handed to the full-model policy.

This is why it is safer than direct trajectory replay for mid-structure tasks like analysis, reporting, translation, and audits.

## How failure detection works

Failure detection splits misses into two types.

1. Retrieval miss
   The template should not have been selected in the first place.
2. Execution miss
   The template looked plausible, but runtime behavior shows it is drifting or failing.

The detector currently checks:

- missing required slots
- ambiguous family match
- output-contract failure
- missing intermediate artifacts
- unexpected validator-error class
- trajectory deviation
- token/time budget anomaly
- no progress across repeated repairs

When any high-risk rule triggers, the recommended action is `abort_and_fallback`.

## Suggested control loop

1. Run `route_request.py` on the new request.
2. If the mode is `template_reuse`, instantiate slots and execute the compiled action program directly with `executor.py`.
3. If the mode is `macro_reuse`, execute only the cached macro-actions directly. If the next step is uncovered, stop reuse and escalate.
4. At checkpoints, collect runtime signals and call `failure_detector.py`.
5. If the detector returns `abort_and_fallback`, stop reuse and switch to the stronger full-model policy.

## Representative runtime signals

The detector expects a runtime JSON object with fields like:

- `family_score`
- `family_score_gap`
- `missing_slots_count`
- `output_contract_passed`
- `missing_intermediate_artifacts_count`
- `validator_error_expected`
- `trajectory_deviation_score`
- `token_ratio_to_template_mean`
- `time_ratio_to_template_mean`
- `repair_progress_stalled`

These are deliberately generic so the detector can be attached to different runners later.

## Next step

If you want to connect this to actual benchmark runs, the next natural extensions are:

- compressed successful trajectories into executable programs;
- template slot extractors;
- runner hooks that emit runtime signals automatically;
- fallback triggers after the first deviating step.
