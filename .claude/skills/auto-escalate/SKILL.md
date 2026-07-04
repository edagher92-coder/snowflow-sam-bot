---
name: auto-escalate
description: |
  [EFFICIENCY] Seamless model escalation — keep the main session on Sonnet,
  route hard sub-problems to an Opus subagent (Fable 5 on double-escalation),
  mechanical fan-out to Haiku, and drop back automatically when the subagent
  returns. Apply the rubric silently on every task; also
  use when the user says "escalate this", "use opus for this", "this is hard",
  "think harder", or "double escalate".
---

# Auto-escalation — the model ladder

The main session stays on **Sonnet** (the orchestrator). Difficulty is judged
per *sub-problem*, not per conversation. Escalation = spawning a subagent via
the **Agent tool with `model: "opus"` / `"fable"` / `"haiku"`** — the main
session never changes model, so drop-back is automatic the moment the
subagent returns. (Only the user can change the main model, via `/model`.)

## Rubric — when to ESCALATE a sub-problem to an `opus` subagent

Any ONE of these:
- **Root-cause debugging** where the cause isn't apparent after the first look.
- **Architecture / design** decisions spanning several systems or ~5+ files,
  or changing a public interface.
- **Safety- or compliance-critical output**: pricing-engine logic, EOFY/tax
  phrasing, legal copy, anything the no-fabrication tests guard.
- **High-stakes numbers**: board/financial analysis, pricing or budget
  decisions, cash-flow strategy.
- **Two failed attempts** at the same problem on the current model.
- **Security-sensitive review** of code or configuration.

## When to STAY on Sonnet (no subagent)

Content generation from existing templates/calendars, routine code edits,
quotes via the deterministic reply engine, ops/scheduling, doc updates,
anything a test suite can settle cheaply. **Never escalate what a test can
answer** — run the test.

## When to DE-ESCALATE to `haiku` subagents

Search/grep fan-out, file inventories, bulk mechanical transforms,
long-list summarisation. No reasoning → no expensive model.

## DOUBLE-ESCALATION to `fable` (Fable 5)

Only when an Opus attempt **fails verification, is self-contradictory, or
reports low confidence** — or the task is genuinely frontier (novel
algorithm, deep multi-constraint planning). **One Fable attempt max**, then
surface to the user instead of burning further.

## Mechanics (keep it efficient)

1. Scope the escalation to the *sub-problem*, never the whole task. Write a
   **self-contained prompt** — the subagent starts with zero context.
2. `Agent(prompt, model: "opus")` → integrate the result → continue on Sonnet.
3. **Verify cheaply before accepting** (run the tests, check the invariant);
   a failed verification is what justifies the Fable rung.
4. Budget: at most one Opus + one Fable attempt per sub-problem.
5. Be transparent: one line in the final reply — `escalated: opus (root-cause
   debugging)` — so the user sees when and why the ladder was used.

## Strengths cheat-sheet

| Model | Use for | Avoid for |
|---|---|---|
| Haiku | mechanical fan-out, search, bulk transforms | anything needing judgement |
| Sonnet | day-to-day work, content, routine code, orchestration | frontier reasoning |
| Opus | deep debugging, architecture, high-stakes analysis | mechanical volume (cost) |
| Fable 5 | the hardest problems, after Opus falls short | anything the rungs below handle |
