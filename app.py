#!/usr/bin/env python3
"""
Snow Flow "Sam" Messenger bot — webhook server.
Auto-replies to first messages, keywords, and ice-breaker / persistent-menu taps in Sam's voice.

Env vars (set on your host):
  PAGE_TOKEN    Page access token (pages_messaging). For prod use a long-lived/non-expiring one.
  VERIFY_TOKEN  Any secret string; must match what you enter in the App Dashboard webhook setup.
  APP_SECRET    App secret (optional but recommended — verifies request signatures).
  REPLIES_FILE  Path to replies JSON (default: sam_replies.json next to this file).

Routing order: postback payload  ->  keyword match  ->  first-message greeting  ->  fallback.
Outside business hours, the away message is sent instead of the greeting for a new thread.
"""
import os, json, time, hmac, hashlib, urllib.request, urllib.parse, datetime
from flask import Flask, request, abort

HERE = os.path.dirname(os.path.abspath(__file__))
REPLIES = json.load(open(os.environ.get("REPLIES_FILE", os.path.join(HERE, "sam_replies.json"))))
PAGE_TOKEN = os.environ.get("PAGE_TOKEN", "")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "snowflow_sam_verify")
APP_SECRET = os.environ.get("APP_SECRET", "")
GRAPH = "https://graph.facebook.com/v21.0"

app = Flask(__name__)
_seen = {}  # psid -> last greeted ts (so we only greet once per ~6h thread)


def within_hours():
    h = REPLIES.get("business_hours", {})
    now = datetime.datetime.utcnow() + datetime.timedelta(hours=h.get("tz_offset", 10))
    if now.weekday() not in h.get("days", [0, 1, 2, 3, 4]):
        return False
    return h.get("open_hour", 8) <= now.hour < h.get("close_hour", 18)


def reply_for_text(text):
    t = (text or "").lower()
    for rule in REPLIES.get("rules", []):
        if any(k in t for k in rule["keywords"]):
            return rule["reply"]
    return None


def resolve(key_or_text):
    """A postback value may be a rule id, a named message, or literal text."""
    if key_or_text in ("greeting_first_message", "away_message", "fallback"):
        return REPLIES[key_or_text]
    for rule in REPLIES.get("rules", []):
        if rule["id"] == key_or_text:
            return rule["reply"]
    return key_or_text


def send(psid, text):
    body = json.dumps({"recipient": {"id": psid}, "messaging_type": "RESPONSE",
                       "message": {"text": text}}).encode()
    url = f"{GRAPH}/me/messages?access_token={urllib.parse.quote(PAGE_TOKEN)}"
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req) as r:
            return r.status
    except urllib.error.HTTPError as e:
        print("SEND ERROR:", e.read().decode()[:300]); return e.code


def valid_signature(req):
    if not APP_SECRET:
        return True  # signature check disabled if no secret set
    sig = req.headers.get("X-Hub-Signature-256", "")
    if not sig.startswith("sha256="):
        return False
    mac = hmac.new(APP_SECRET.encode(), req.get_data(), hashlib.sha256).hexdigest()
    return hmac.compare_digest("sha256=" + mac, sig)


@app.get("/webhook")
def verify():
    if request.args.get("hub.mode") == "subscribe" and request.args.get("hub.verify_token") == VERIFY_TOKEN:
        return request.args.get("hub.challenge", ""), 200
    abort(403)


@app.post("/webhook")
def webhook():
    if not valid_signature(request):
        abort(403)
    data = request.get_json(force=True, silent=True) or {}
    for entry in data.get("entry", []):
        for ev in entry.get("messaging", []):
            psid = ev.get("sender", {}).get("id")
            if not psid:
                continue
            # 1) postback (ice-breaker / menu / get-started tap)
            if "postback" in ev:
                payload = ev["postback"].get("payload", "")
                send(psid, resolve(REPLIES.get("postbacks", {}).get(payload, payload) or "fallback"))
                continue
            msg = ev.get("message", {})
            if msg.get("is_echo"):
                continue
            text = msg.get("text", "")
            # 2) keyword match
            r = reply_for_text(text)
            if r:
                send(psid, r); continue
            # 3) first-message greeting (once per ~6h), hours-aware
            last = _seen.get(psid, 0)
            if time.time() - last > 6 * 3600:
                _seen[psid] = time.time()
                send(psid, REPLIES["greeting_first_message"] if within_hours() else REPLIES["away_message"])
                continue
            # 4) fallback
            send(psid, REPLIES["fallback"])
    return "ok", 200


@app.get("/")
def health():
    return {"bot": "Snow Flow Sam", "ok": True, "hours_now": within_hours()}, 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
