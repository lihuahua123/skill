# Evo Skill

`evo_skill` is a minimal OpenSpace-style skill evolution layer for `/root/skill`.

It keeps the same logical stages as OpenSpace:

1. execution history -> analysis
2. analysis -> evolution suggestion
3. suggestion -> skill evolution
4. evolved skill -> lineage store

This implementation is intentionally offline-first. It reads historical benchmark
results from `results/rq1/*.json`, produces candidate evolution records, and
generates versioned `SKILL.md` drafts without changing the benchmark runners.

## Layout

- `types.py`
  Shared dataclasses aligned to the OpenSpace concepts.
- `analyzer.py`
  Converts historical benchmark results into `ExecutionAnalysis`-style records
  and produces `EvolutionSuggestion`s.
- `evolver.py`
  Materializes evolved skills and lineage metadata.
- `cli.py`
  Command-line entrypoint.
- `store/`
  JSONL outputs for analyses and lineage.
- `generated_skills/`
  Generated skills created by the evolver.

## Default output locations

- Candidate analyses:
  `evo_skill/store/execution_analyses.jsonl`
- Lineage records:
  `evo_skill/store/skill_lineage.jsonl`
- Generated skills:
  `evo_skill/generated_skills/<skill-name>/SKILL.md`

## Usage

Analyze historical RQ1 results and write evolution candidates:

```bash
python3 -m evo_skill.cli analyze \
  --results-dir /root/skill/results/rq1
```

Generate evolved skill drafts from those candidates:

```bash
python3 -m evo_skill.cli evolve
```

Run both steps:

```bash
python3 -m evo_skill.cli run \
  --results-dir /root/skill/results/rq1
```

## Notes

- Generated skills stay inside this repo by default so they can be reviewed
  before exporting to an external skill runtime such as `~/.openclaw/skills`.
- The first version is heuristic-driven and deterministic. It does not require
  an online LLM call to produce candidate skills.
