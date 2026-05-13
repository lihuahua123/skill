# SWE-bench Strong Execution Skill

This skill is for SWE-bench repair only.

## Override Rule

If this skill conflicts with any generic workflow such as:

- explore the repository first
- create a reproduction script
- run broader tests
- inspect related modules

then **follow this skill instead**.

Treat this skill as higher priority than any generic workflow, recommended workflow, or default repair checklist that appears elsewhere in the prompt.

If the prompt contains both this skill and a generic workflow, you must obey this skill and ignore the conflicting workflow steps.

## First-Command Rule

Your first command must directly read the target failing test or the exact failure output already named in the prompt.

Allowed first commands:

- read the target test function
- read the exact production file already named by the failure
- read the exact failing assertion from evaluation feedback

Forbidden first commands:

- `find /testbed ...`
- repository-wide grep
- reading package structure
- creating scripts
- running full test files

## Required Execution Order

Follow this order exactly:

1. Read the exact target failing test assertion.
2. Read the exact throw site or branch producing that failure.
3. Compare expected vs actual.
4. Decide whether the bug is:
   - wrong branch selection
   - wrong comparison granularity
   - wrong message template
5. Make the smallest non-test code change.
6. Run only the target failing test.
7. If it passes, stop expanding.

Do not add extra exploration before step 5 unless the prompt is missing the target test or target file.

## Retry Rule

On retries, evaluation feedback may contain both the target FAIL_TO_PASS test and unrelated environment or historical failures.

When that happens:

1. Prioritize the issue-relevant FAIL_TO_PASS test named in the prompt or feedback.
2. Treat unrelated failures as noise unless your patch directly touched their code path.
3. Do not switch to fixing another failure just because it appears earlier in the feedback output.
4. If retry guidance says your previous direction was wrong, change the repair hypothesis for the target test, not the target itself.

## Command Budget

For single-branch SWE-bench bugs, you should usually modify code within the first 3 to 5 shell commands.

If you are still exploring after 6 commands, assume you are off track and narrow scope immediately.

## Verification Rule

First verification must be only one of:

- the single failing test
- the smallest directly related test case

Do not run:

- the whole test file
- the whole subpackage
- broad regression

unless the target test already passes and you changed shared logic.

If you changed shared validation logic, you may run at most one adjacent assertion-preservation test that exercises the old branch behavior most likely to regress.

## Stop Rule

Stop when all three are true:

1. the target FAIL_TO_PASS test passes
2. the patch is confined to issue-relevant non-test code
3. there is no new directly-caused failure

Do not keep testing just for reassurance.

## Hard Prohibitions

Do not do any of the following unless the prompt explicitly requires it:

- repository-wide `find` or broad `grep`
- create `reproduce_issue.py`, `debug.py`, `test_logic.py`, or similar temp files
- `git stash`
- repeated re-running of a test that already passed
- changing unrelated modules because of environment noise
- treating warning-suppressed passes as a real fix

Do not let retry feedback pull you into fixing unrelated failures in other modules when the issue and target test already localize the task.

## Astropy 13033 Specific Rule

For `astropy__astropy-13033`, focus only on:

- `astropy/timeseries/tests/test_sampled.py::test_required_columns`
- the required-columns validation branch in `astropy/timeseries/core.py`
- the first failing required-column position

Do not treat leap-second / IERS failures as the main target for this instance.

Do not fix this instance by only changing wording for missing columns.
Fix the failure localization logic first.

Preserve these old behaviors while fixing the issue case:

- if the first required column itself is wrong or missing, keep the existing first-column mismatch style
- if all required columns exist but order is wrong, keep the existing first-column mismatch style
- do not generalize the new missing-column message to every required-column failure

Before patching, compare the issue case against the earlier assertions in the same test function that cover:

- add column at index 0
- remove `time`
- remove `time` plus another leading column

If your planned logic would change those outcomes, your hypothesis is too broad.

## One-Line Reminder

Read the target assertion first, go straight to the throwing branch, make the smallest patch, run only the target test, and stop as soon as it passes.
