---
name: auro-memory
description: "Auto-memory for Cowork and Chat. Save, restore, and recall working context across sessions using the Claude HQ Drive memory/ folder. Use when the user says 'save memory', 'remember this', 'auromemory', 'restore', 'where was I', 'what was I working on', or 'recall X'."
---

# /auro-memory — Auto-Memory for Cowork & Chat

Persistent working memory that survives across Cowork and Chat sessions. Backed by the
`Claude HQ/memory/` folder on Google Drive — the same store `skill-routing-protocol` reads —
so anything saved here is visible to every future Cowork or Chat session connected to that Drive.

This is the Cowork/Chat-native companion to the gstack context skills that run in Claude Code
(`/context-save`, `/context-restore`, `/learn`). Same idea: capture decisions and remaining work
so the next session resumes without a cold start. The difference is the store — Drive memory
notes here, local `~/.gstack/projects/<slug>/checkpoints/` in Claude Code.

## Modes

| The user says | Mode |
| --- | --- |
| "save memory", "remember this", "auromemory save", "checkpoint this" | **SAVE** |
| "restore", "where was I", "what was I working on", "resume" | **RESTORE** |
| "recall X", "what do we know about X", "did we decide X" | **RECALL** |
| "learn this: ...", "remember that ..." (a durable fact/preference) | **LEARN** |

## SAVE

Capture the current working context as a new memory note in the `memory/` folder.

1. Summarize from the conversation: **what's being worked on**, **decisions made** (with the why),
   **remaining work** (next steps in priority order), and **notes/gotchas**.
2. Write a NEW file `session-<YYYY-MM-DD>-<short-slug>.md` to the `memory/` folder using the
   memory node format below. Never overwrite an existing note — each save is a new file.
3. Confirm: title, file, and a one-line summary of what was captured.

## RESTORE

1. List the `memory/` folder, newest first.
2. Read the most recent `session-*` note (or the one matching a title fragment the user gave).
3. Present: what was being worked on, decisions, and the remaining-work list. Offer to start on
   the first remaining item.

## RECALL

Search the `memory/` notes (titles + bodies) for the user's term and summarize the matches.
Prefer notes with `type: decision` when the question is "what did we decide / why".

## LEARN

Append a durable learning as a new note with `type: learning` — a project quirk, a preference,
a command that works. One insight per note; keep it short. Don't log obvious or one-off facts.

## Memory note format (match the existing memory/ convention)

```
---
name: <kebab-title>
description: "<one line>"
metadata:
node_type: memory
 type: <session-context | decision | learning | reference>
 originSessionId: <session id or date>
---

<short, scannable body. Link related notes with [[wikilinks]].>
```

## Guardrails

- **Additive only.** Never overwrite or delete an existing memory note; every save is a new file.
- **No secrets.** Never write credentials, tokens, or keys into a memory note.
- **Keep it short.** Memory notes are read on every routing pass — scannable beats exhaustive.
- **Link, don't duplicate.** Reference related notes with `[[wikilinks]]` instead of restating them.
- This skill cannot run shell or Claude Code; in Cowork/Chat it operates purely on the Drive
  `memory/` folder via the connected Google Drive tools.
