"""Drift guardrail for Sam's customer-facing facts.

Sam's "brain" (`sam_replies.json`) is one of three hand-maintained copies of
the same business facts across the edagher92-coder account:

  * Claude-code-/snowflow/reply_engine/pricing.py  (the programmatic source
    of truth) + Claude-code-/CLAUDE.md hard-rule #13 (the headline marketing
    prices) + web/knowledge.json (generated brain)
  * snowflow-sam-bot/sam_replies.json              (THIS repo — FB/IG/WhatsApp)
  * snowflow-ask-sam/knowledge/*.md                (staff Ask-Sam)

Because nothing regenerates this file from the source of truth, prices drift.
A real example: the F2-E soft-serve price sat at $21,995 here for a while —
$2,000 below the verified $23,995 — and was served live to customers.

This test pins the CANONICAL headline facts (sourced from
Claude-code-/CLAUDE.md hard-rule #13) so any future edit that reintroduces a
wrong number fails CI instead of reaching a customer. Update CANONICAL below
only when the verified source of truth changes — and update all three brains
together.

Pure stdlib + pytest; no network, no cross-repo import.
"""
import json
import re
from pathlib import Path

REPLIES = Path(__file__).resolve().parents[1] / "sam_replies.json"

# --- Canonical facts (source: edagher92-coder/Claude-code- CLAUDE.md #13 + contact) ---
# Machine -> verified inc-GST price string that MUST appear wherever the machine
# is priced, and wrong prices that must NEVER appear.
CANONICAL_PRICES = {
    "F2-E": {"correct": "$23,995", "forbidden": ["$21,995"]},
    "SFX3": {"correct": "$4,100", "forbidden": []},
}
CANONICAL_CONTACT = {
    "email": "Sydney@snowflow.com.au",   # capital S — the Snow Flow sales/service brand
    "phone": "0450 878 787",
}


def _load():
    return json.loads(REPLIES.read_text(encoding="utf-8"))


def _all_text(data):
    """Every customer-visible string in the file, concatenated."""
    chunks = []

    def walk(v):
        if isinstance(v, str):
            chunks.append(v)
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)

    walk(data)
    return "\n".join(chunks)


def test_replies_json_is_valid():
    _load()  # raises on malformed JSON


def test_no_forbidden_prices_anywhere():
    text = _all_text(_load())
    for machine, spec in CANONICAL_PRICES.items():
        for wrong in spec["forbidden"]:
            assert wrong not in text, (
                f"Stale/incorrect price {wrong} for {machine} found in "
                f"sam_replies.json — the verified price is {spec['correct']}. "
                f"Sam would quote the wrong number to a customer."
            )


def test_canonical_prices_present():
    text = _all_text(_load())
    for machine, spec in CANONICAL_PRICES.items():
        assert spec["correct"] in text, (
            f"Expected the verified price {spec['correct']} for {machine} to "
            f"appear in sam_replies.json but it does not — did a price change "
            f"here without updating the canonical facts (and the other brains)?"
        )


def test_contact_details_are_canonical():
    data = _load()
    contact = data.get("contact", {})
    assert contact.get("email") == CANONICAL_CONTACT["email"], (
        f"contact.email drifted: {contact.get('email')!r} != "
        f"{CANONICAL_CONTACT['email']!r}"
    )
    assert contact.get("phone") == CANONICAL_CONTACT["phone"], (
        f"contact.phone drifted: {contact.get('phone')!r} != "
        f"{CANONICAL_CONTACT['phone']!r}"
    )
    # The email must never appear lower-cased (brand rule: capital S).
    text = _all_text(data)
    assert "sydney@snowflow.com.au" not in text, (
        "Found lower-case 'sydney@snowflow.com.au' — the Snow Flow brand uses "
        "a capital S (Sydney@snowflow.com.au)."
    )


def test_price_list_in_llm_voice_matches_facts():
    """The llm_voice 'Use exact prices only: ...' list must not contradict the
    facts block — both are grounding for the LLM layer, so a mismatch there is
    exactly how Sam ends up quoting two different numbers."""
    data = _load()
    voice = data.get("llm_voice", "")
    facts = data.get("facts", "")
    for machine, spec in CANONICAL_PRICES.items():
        correct = spec["correct"]
        # If the machine's correct price appears in facts, it must not be
        # contradicted by a forbidden price living in the voice list.
        if correct in facts:
            for wrong in spec["forbidden"]:
                assert wrong not in voice, (
                    f"llm_voice price list still shows {wrong} for {machine} "
                    f"while facts uses {correct} — they must agree."
                )
