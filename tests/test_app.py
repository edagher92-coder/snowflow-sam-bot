"""Hostility kill switch — one calm exit line, then hard silence.

Guards `decide()` in app.py: a hostile/abusive message from a sender gets exactly
one deterministic exit reply and permanently mutes that sender_id (in-process) for
every message kind (text or postback) that follows, regardless of content.
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_bot_state():
    """decide()'s mute/first-seen state is module-global — isolate each test."""
    app._muted.clear()
    app._seen.clear()
    yield
    app._muted.clear()
    app._seen.clear()


HOSTILE_PHRASES = [
    "Fuck off",
    "fuck you",
    "shut up",
    "f**k off",
    "get lost",
    "piss off",
    "screw you",
    "stfu",
]

NOT_HOSTILE_PHRASES = [
    "how much is an sfx-3",
    "this machine is fucking amazing",
    "you know what I hate, automatically receiving messages when I was just looking",
    "is this covered by warranty",
]


@pytest.mark.parametrize("text", HOSTILE_PHRASES)
def test_is_hostile_detects_abuse(text):
    assert app.is_hostile(text) is True


@pytest.mark.parametrize("text", NOT_HOSTILE_PHRASES)
def test_is_hostile_ignores_ordinary_messages(text):
    assert app.is_hostile(text) is False


def test_first_hostile_message_gets_one_exit_reply():
    reply = app.decide("text", "Fuck off", "PSID_HOSTILE")
    assert reply == app.REPLIES["hostility_exit"]
    assert "PSID_HOSTILE" in app._muted


def test_muted_sender_gets_total_silence_on_repeat_hostility():
    app.decide("text", "Fuck off", "PSID_HOSTILE")
    second = app.decide("text", "Fuck off", "PSID_HOSTILE")
    assert second is None


def test_muted_sender_gets_silence_even_on_ordinary_follow_up():
    app.decide("text", "Fuck off", "PSID_HOSTILE")
    follow_up = app.decide("text", "how much is an sfx-3", "PSID_HOSTILE")
    assert follow_up is None


def test_muted_sender_gets_silence_on_postback_too():
    app.decide("text", "Fuck off", "PSID_HOSTILE")
    postback = app.decide("postback", "PRICE", "PSID_HOSTILE")
    assert postback is None


def test_mute_does_not_bleed_across_senders():
    app.decide("text", "Fuck off", "PSID_HOSTILE")
    other = app.decide("text", "how much is an sfx-3", "PSID_OTHER")
    assert other is not None
    assert "PSID_OTHER" not in app._muted


def test_webhook_sends_exit_line_once_then_stays_silent_on_repeat_abuse():
    payload = {
        "object": "page",
        "entry": [
            {
                "messaging": [
                    {"sender": {"id": "PSID_WH"}, "message": {"text": "Fuck off"}},
                ]
            }
        ],
    }
    with app.app.test_client() as client, patch("app.send_meta") as mock_send:
        client.post("/webhook", json=payload)
        client.post("/webhook", json=payload)
        client.post("/webhook", json=payload)

    assert mock_send.call_count == 1
    sent_psid, sent_text = mock_send.call_args[0]
    assert sent_psid == "PSID_WH"
    assert sent_text == app.REPLIES["hostility_exit"]
