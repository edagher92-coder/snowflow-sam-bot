# claude-defaults/tools

Account-wide helper tools distributed by `bootstrap.sh` into `~/.claude/tools/`.

## `ollama_route.py` — the Ollama bridge (tier 0/1)
Lets a Claude Code session or subagent offload **heavy, non-stakes** work to a
local or **Ollama Cloud Pro** model, so the big cheap open models carry the
mid-tier grunt work instead of spending Claude quota. This is the arm the router
uses to reach the Ollama Cloud tier the policy reserves.

```bash
python ~/.claude/tools/ollama_route.py --model gpt-oss:120b-cloud "Summarise ..."
echo "refactor this module ..." | python ~/.claude/tools/ollama_route.py --route heavy-code
python ~/.claude/tools/ollama_route.py --list          # models the server can see
```

Routes: `heavy-code` → `kimi-k2.7-code:cloud`, `heavy-reason` → `gpt-oss:120b-cloud`,
`trivial` → `gemma4:e4b`, `classify` → `llama3.2:3b`. Stdlib only, no deps.

**NUMBERS RULE:** never send customer-facing price/quote/invoice/legal here — those
stay on Claude (Sonnet/Opus). This tool is for heavy NON-stakes work only.

## Main server + Tailscale (multi-PC)
Both the bridge and the classifier hook read **`CLAUDE_ROUTER_OLLAMA_URL`**
(default `http://localhost:11434`). Run Ollama on one **main server** (elzydlab)
and point every other PC at it over Tailscale — no per-PC Ollama install:

1. **Main server (elzydlab):** run Ollama listening on the Tailscale interface —
   set `OLLAMA_HOST=0.0.0.0` (env var / service config) and restart Ollama.
2. **Every PC (incl. the main one, for consistency):** set
   ```
   CLAUDE_ROUTER_OLLAMA_URL=http://elzydlab.tail76b098.ts.net:11434
   ```
   (or the Tailscale IP `http://100.122.28.89:11434`). The hook + bridge then use
   the shared hub. On the main server itself you can leave it as `localhost`.
3. Install the kit on each PC with `bash claude-defaults/bootstrap.sh --user`.

The cloud models still bill your **Ollama Pro** sub, not Claude — that's the point:
mid-tier load moves off the Claude weekly limit onto the flat-rate Ollama Cloud plan.
