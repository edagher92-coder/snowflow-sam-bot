---
name: skill-router
description: |
  [OPS] Rank this repo's Claude Code skills against a natural-language request
  using the auto-registering skill_router CLI (stdlib-only, zero config), and
  regenerate the skills INDEX.md from the live registry.
  Use when the user says "which skill should I use", "route this request",
  "list all skills", or "regenerate the skills index".
---

# Skill router

The router reads every `*/SKILL.md` under this repo's skills directory as its
routing table — no hand-maintained config. It scans `.claude/skills/` when it
exists, falling back to a top-level `skills/` directory. Drop a new `SKILL.md`
on disk and it registers automatically.

## Commands (run from the repo root)

| Task | Command |
|---|---|
| Route a request | `python -m skill_router "audit these drafts"` |
| Top-N as JSON | `python -m skill_router --json -n 3 "chase overdue invoices"` |
| List the registry | `python -m skill_router --registry` |
| Regenerate INDEX.md | `python -m skill_router --index` |
| Scan another directory | `python -m skill_router -d path/to/skills "query"` |

In repos where the package lives under `src/` (the Snow Flow monorepo), prefix
commands with `PYTHONPATH=src` unless the package is already pip-installed
(CI's `pip install -e .` covers this).

## Behaviour

1. Run the route command with the user's request as the query.
2. Report the top matches with their scores. If the best match is clearly
   right, invoke that skill (or point the user at it).
3. If nothing matches, say so and show the `--registry` output — never guess a
   skill that isn't registered.
4. After adding or renaming any skill, run `--index` so `INDEX.md` stays in
   sync with what is actually on disk.

## Model escalation (seamless — see /auto-escalate)

After routing, gauge the task against the /auto-escalate rubric: run hard
sub-problems through an `opus` subagent (Agent tool, `model: "opus"`), the
truly frontier ones through `fable` (one attempt max, only after Opus falls
short), and mechanical fan-out through `haiku`. The main session stays on
Sonnet and picks the result up automatically — drop-back needs no action.
