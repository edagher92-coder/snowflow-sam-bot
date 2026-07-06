"""Drift guardrail for Sam's customer-facing facts.

Sam's "brain" here (`sam_replies.json`) is one of three copies of the same
business facts across the edagher92-coder account. The canonical values now
come from a single machine-readable manifest, `sam-facts.canonical.json`,
which is generated from Claude-code-/snowflow/reply_engine/pricing.py by
`tools/export_sam_facts.py` and synced into this repo by `tools/sync_sam_facts.sh`.
DO NOT hand-edit the vendored manifest — change pricing.py upstream and re-sync.

This test fails CI if this repo's brain contradicts the manifest — e.g. the
F2-E soft-serve that once shipped live at $21,995 ($2,000 below the verified
$23,995). Pure stdlib + pytest; no network, no cross-repo import.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPLIES = ROOT / "sam_replies.json"
MANIFEST = ROOT / "sam-facts.canonical.json"

# Machines THIS brain headlines and must therefore price correctly. Other
# manifest machines (e.g. hire-only SKUs) aren't quoted here, so we don't
# require their price to appear — but no brain may ever print a forbidden one.
REQUIRE_PRESENT = ("SFX3", "F2-E")


def _manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _load():
    return json.loads(REPLIES.read_text(encoding="utf-8"))


def _all_text(data):
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


def test_manifest_and_replies_are_valid():
    _manifest()
    _load()


def test_no_forbidden_prices_anywhere():
    text = _all_text(_load())
    for machine, spec in _manifest()["prices"].items():
        for wrong in spec["forbidden"]:
            assert wrong not in text, (
                f"Stale/incorrect price {wrong} for {machine} found in "
                f"sam_replies.json — canonical price is {spec['correct']}."
            )


def test_headline_machines_use_canonical_price():
    text = _all_text(_load())
    prices = _manifest()["prices"]
    for machine in REQUIRE_PRESENT:
        assert machine in prices, f"{machine} missing from the canonical manifest"
        correct = prices[machine]["correct"]
        assert correct in text, (
            f"Expected canonical price {correct} for {machine} in "
            f"sam_replies.json but it is absent — did a price change without "
            f"re-syncing from pricing.py?"
        )


def test_every_five_figure_price_is_canonical():
    """Closes the partial-drift blind spot: a novel wrong price (e.g. $22,995)
    alongside one correct occurrence used to pass. Every five-figure ($XX,XXX)
    price in the file must be one the manifest verifies — so any invented
    machine price fails, wherever it appears (facts, llm_voice, a rule reply)."""
    import re
    canonical_five_fig = {
        spec["correct"] for spec in _manifest()["prices"].values()
        if re.fullmatch(r"\$\d{2},\d{3}", spec["correct"])
    }
    found = set(re.findall(r"\$\d{2},\d{3}", _all_text(_load())))
    rogue = found - canonical_five_fig
    assert not rogue, (
        f"Non-canonical five-figure price(s) {sorted(rogue)} in sam_replies.json. "
        f"Only manifest-verified prices are allowed: {sorted(canonical_five_fig)}. "
        f"A machine price was changed/invented without re-syncing from pricing.py."
    )


def test_contact_details_are_canonical():
    data = _load()
    contact = data.get("contact", {})
    canon = _manifest()["contact"]
    assert contact.get("email") == canon["email_snowflow"], (
        f"contact.email drifted: {contact.get('email')!r} != "
        f"{canon['email_snowflow']!r}"
    )
    assert contact.get("phone") == canon["phone"], (
        f"contact.phone drifted: {contact.get('phone')!r} != {canon['phone']!r}"
    )
    # Brand rule: the Snow Flow email uses a capital S.
    assert canon["email_snowflow"].lower() not in _all_text(data), (
        "Found a lower-cased Snow Flow email — brand uses capital S "
        f"({canon['email_snowflow']})."
    )
