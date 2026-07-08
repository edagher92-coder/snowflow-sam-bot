#requires -Version 5.1
<#
  claude-routing-classifier.ps1  --  UserPromptSubmit hook
  Model Routing Policy v5.0 (Automatic Tier Delegation).

  Classifies each user message into STAKES / EXTRACTION / HEAVY / TRIVIAL / NORMAL
  and injects a ROUTING HINT for where to send the substantive work:
    STAKES     -> Claude Opus (money/legal/irreversible/customer-facing)
    EXTRACTION -> Claude Sonnet (structured data out of text)
    HEAVY      -> Ollama Cloud Pro via tools/ollama_route.py (bulk non-stakes
                  coding/reasoning — saves Claude quota + mid-tier load)
    TRIVIAL    -> Claude Haiku (or the local Ollama free floor)
    NORMAL     -> the current main model (no delegation)

  Server URL is overridable via CLAUDE_ROUTER_OLLAMA_URL so a secondary PC can
  reach the MAIN server (elzydlab) over Tailscale.

  Guarantees:
   * Money / refund / price / invoice / legal / tax terms -> STAKES via a
     deterministic regex gate that runs BEFORE the model, so a flaky or offline
     model can never demote a money task, and money never becomes HEAVY.
   * Deterministic model call (temperature 0, fixed seed, greedy).
   * Single-word output enforced by prompt + priority-ordered parsing
     (STAKES wins ties -- the safe direction).
   * FAILS OPEN: any error / timeout / unclear verdict -> emit nothing, exit 0.
#>

$ErrorActionPreference = 'Stop'

# ---- config ----
# Base URL is overridable so a secondary PC points at the MAIN server over
# Tailscale: set CLAUDE_ROUTER_OLLAMA_URL=http://elzydlab.tail76b098.ts.net:11434
$OllamaBase = if ($env:CLAUDE_ROUTER_OLLAMA_URL) { $env:CLAUDE_ROUTER_OLLAMA_URL.TrimEnd('/') } else { 'http://localhost:11434' }
$OllamaUrl  = "$OllamaBase/api/generate"
$Model      = 'llama3.2:3b'
$TimeoutSec = 6

# STAKES -> opus (fable only if opus-class already failed), EXTRACTION -> sonnet,
# TRIVIAL -> haiku, NORMAL -> no delegation (answer on the current main model).
$ModelFor = @{ STAKES = 'opus'; EXTRACTION = 'sonnet'; TRIVIAL = 'haiku' }

# Records the last Ollama engine actually used, for claude_status_line.py to
# render a live "offline"/"cloud" badge. Best-effort: never breaks the hook.
function Write-EngineStatus([string]$model) {
    try {
        $engine = if ($OllamaBase -match 'ollama\.com') { 'cloud' } else { 'local' }
        $statusDir = Join-Path $env:USERPROFILE '.claude'
        if (-not (Test-Path $statusDir)) { New-Item -ItemType Directory -Path $statusDir -Force | Out-Null }
        @{
            ts     = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
            engine = $engine
            model  = $model
            role   = 'classify'
            source = 'hook'
        } | ConvertTo-Json | Set-Content -Path (Join-Path $statusDir '.routing-status.json') -Encoding utf8
    } catch { }
}

function Write-Hint([string]$verdict) {
    if ($verdict -eq 'NORMAL') { return }   # no delegation overhead
    if ($verdict -eq 'HEAVY') {
        Write-Output ("ROUTING HINT (Model Routing Policy v5.0): HEAVY non-stakes work -> offload to " +
            "Ollama Cloud (Pro) to save Claude quota and mid-tier load. Run: python " +
            "`"$env:USERPROFILE\.claude\tools\ollama_route.py`" --route heavy-code (bulk coding/refactors) " +
            "or --route heavy-reason (long reasoning/summarising), then review the output. NEVER send " +
            "money / pricing / invoice / legal / customer-facing text there -- those stay on Claude.")
        return
    }
    $model = $ModelFor[$verdict]
    if (-not $model) { return }
    Write-Output ("ROUTING HINT (Model Routing Policy v5.0): this message classified $verdict -> " +
        "delegate the substantive answer to an Agent with model:`"$model`". Quality-first: if that " +
        "tier is unsure or wrong for any reason, escalate one tier up and re-run. Escalating to " +
        "Fable needs a one-time YES from Elie first (premium / credits). A manual /model choice by " +
        "Elie always overrides this hint.")
}

try {
    # --- read the hook payload (fail open if absent/garbled) ---
    $raw = [Console]::In.ReadToEnd()
    if ([string]::IsNullOrWhiteSpace($raw)) { exit 0 }
    $prompt = [string]($raw | ConvertFrom-Json).prompt
    if ([string]::IsNullOrWhiteSpace($prompt)) { exit 0 }

    # --- deterministic high-stakes gate (fires even if Ollama is down) ---
    # Over-escalation here is the safe direction: a money task must never demote.
    $stakesRegex = '(?i)(\$\s?\d|\brefund|\binvoice|\bprice|\bpricing|\bquote\b|\bcharge\b|\bpayment|' +
                   '\bdeposit|\bdiscount|\bAUD\b|\bGST\b|\bBAS\b|\bowe\b|\boverdue|\bdebtor|\bbilling|' +
                   '\bcontract\b|\blegal\b|\btax\b)'
    if ($prompt -match $stakesRegex) { Write-Hint 'STAKES'; exit 0 }

    # --- deterministic LLM classification ---
    $instructions = @'
You are a strict routing classifier. Read the USER MESSAGE and reply with EXACTLY ONE WORD from this set: STAKES EXTRACTION HEAVY TRIVIAL NORMAL. No explanation, no punctuation, no other text.

STAKES = money, prices, quotes, invoices, refunds, charges, payments, discounts; legal/tax/compliance; irreversible or customer-facing final content; complex architecture. If money or a customer-facing decision is involved, answer STAKES.
EXTRACTION = pull structured data (names, dates, amounts, addresses, line items) out of unstructured text; parsing, not deciding or acting.
HEAVY = large NON-stakes coding, refactors, long reasoning, or bulk summarising where a big open model suffices and there is no money/customer/legal element. Prefer this to spending premium Claude tiers on grunt work.
TRIVIAL = mechanical low-stakes work: reformatting, renaming, a one-line lookup, a quick fact with no money or customer impact.
NORMAL = everything else / general well-specified work. Use NORMAL only when none of the above clearly applies.

Examples:
refund the customer $50 => STAKES
what is our price for the SFX3 => STAKES
send this quote to the client => STAKES
pull the invoice number and due date from this email => EXTRACTION
extract all suburb names from this list => EXTRACTION
refactor this 600-line module for readability => HEAVY
summarise these 15 log files into one report => HEAVY
rename these variables to camelCase => TRIVIAL
what is the capital of France => TRIVIAL
plan next week's content => NORMAL
explain how this function works => NORMAL

USER MESSAGE:
'@
    $fullPrompt = $instructions + "`n" + $prompt + "`n=> "

    $body = @{
        model   = $Model
        prompt  = $fullPrompt
        stream  = $false
        options = @{ temperature = 0; seed = 42; top_k = 1; top_p = 1; num_predict = 5 }
    } | ConvertTo-Json -Depth 5

    $resp = Invoke-RestMethod -Uri $OllamaUrl -Method Post -Body $body -ContentType 'application/json' -TimeoutSec $TimeoutSec
    Write-EngineStatus $Model
    $text = ([string]$resp.response).ToUpperInvariant()

    # priority-ordered parse: STAKES wins ties (safe direction); unknown -> NORMAL
    $verdict = 'NORMAL'
    if     ($text -match 'STAKES')     { $verdict = 'STAKES' }
    elseif ($text -match 'EXTRACTION') { $verdict = 'EXTRACTION' }
    elseif ($text -match 'HEAVY')      { $verdict = 'HEAVY' }
    elseif ($text -match 'TRIVIAL')    { $verdict = 'TRIVIAL' }
    elseif ($text -match 'NORMAL')     { $verdict = 'NORMAL' }

    Write-Hint $verdict
    exit 0
}
catch {
    # Fail open: Ollama offline, timeout, bad JSON, anything -> no hint, never block.
    exit 0
}
