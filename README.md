# snowflow-sam-bot

> ⛔ **MOVED 2026-08-21: this bot now lives in `edagher92-coder/snowflow-ask-sam` under
> `sam-bot/` — make changes there.**
>
> Ask Sam is now the single self-contained home for every Sam surface. This repo is kept
> for history only; anything committed here will not be deployed and will drift from the
> live bot.

---

## History — what this repo was

The Snow Flow "Sam" multi-channel social bot: one Flask webhook (`app.py`) answering
Messenger, Instagram DM and WhatsApp Cloud API messages from a single reply brain
(`sam_replies.json`), with an optional Claude answer step for off-keyword questions.

- `app.py` — webhook verify + receive, hostility kill switch, postback/keyword routing,
  optional LLM answer, Graph API send, `/` health endpoint. Loop-proof: echoes, delivery
  and read receipts, and text-less attachments are ignored.
- `sam_replies.json` — persona, business hours, contact, verified facts, voice notes,
  greeting/away/fallback/hostility copy, postback map and keyword rules.
- `requirements.txt` — `flask`, `gunicorn`; everything else is Python stdlib.
- `tests/test_app.py` — pytest suite pinning the hostility kill switch.
- `skill_router/` — a vendored copy of the router; the canonical package lives in
  `edagher92-coder/Claude-code-` under `src/skill_router/`.

All of the above except the vendored `skill_router/` and the Claude Code configuration
(`.claude/`, `.claude-plugin/`) was migrated to `snowflow-ask-sam/sam-bot/` on
2026-08-21. See that directory's `README.md` for how to run it, the environment variables
it needs, and how it relates to the rest of Ask Sam.
