#!/usr/bin/env python3
"""Snow Flow "Sam" multi-channel bot - Messenger + Instagram DM + WhatsApp Cloud API.
One webhook, one reply brain (sam_replies.json), three channels, optional LLM upgrade.

Env:
  PAGE_TOKEN          (required) Page access token (non-expiring recommended)
  VERIFY_TOKEN        (default: snowflow_sam_verify) webhook verify token
  APP_SECRET          (optional) enables X-Hub-Signature-256 check; leave UNSET to skip
  WHATSAPP_TOKEN      (optional) only for WhatsApp Cloud API channel
  WHATSAPP_PHONE_ID   (optional) only for WhatsApp
  REPLIES_FILE        (optional) path to the reply-brain json
  ANTHROPIC_API_KEY   (optional) if set, Sam answers off-keyword questions intelligently
  ANTHROPIC_MODEL     (default: claude-3-5-haiku-latest)

LOOP-PROOF: only ever replies to a real inbound text message or a postback. Echoes,
delivery receipts and read receipts are ignored, so the bot can never answer itself.
Routing: postback -> keyword rule -> (LLM if key set) -> first-message greeting -> fallback."""
import os, json, time, hmac, hashlib, urllib.request, urllib.parse, urllib.error, datetime
from flask import Flask, request, abort

HERE = os.path.dirname(os.path.abspath(__file__))
REPLIES = json.load(open(os.environ.get("REPLIES_FILE", os.path.join(HERE, "sam_replies.json"))))
PAGE_TOKEN = os.environ.get("PAGE_TOKEN", "")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "snowflow_sam_verify")
APP_SECRET = os.environ.get("APP_SECRET", "")
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN", "")
WHATSAPP_PHONE_ID = os.environ.get("WHATSAPP_PHONE_ID", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-3-5-haiku-latest")
GRAPH = "https://graph.facebook.com/v21.0"
app = Flask(__name__)
_seen = {}

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

def resolve(key):
    if key in ("greeting_first_message", "away_message", "fallback"):
        return REPLIES[key]
    for rule in REPLIES.get("rules", []):
        if rule["id"] == key:
            return rule["reply"]
    return key

def _greeting_or_away():
    return REPLIES["greeting_first_message"] if within_hours() else REPLIES["away_message"]

def build_system_prompt():
    f = REPLIES.get("facts", "")
    voice = REPLIES.get("llm_voice", "")
    return ("You are Sam, the friendly, sharp human who answers Snow Flow Sydney customer "
            "messages on Facebook/Instagram/WhatsApp. Answer ONLY using the verified facts "
            "below. NEVER invent prices, specs, stock or policies; if a fact isn't given, ask "
            "a question or point them to the team (0450 878 787 / Sydney@snowflow.com.au). "
            "Keep it to 1-4 short sentences, mobile-friendly, at most one emoji, no emoji on "
            "prices. Ask at most ONE qualifying question. Sales = all NSW; service & repairs = "
            "Sydney & Greater Sydney only. Never collect ABN/credit/finance details in chat - "
            "route finance to email. Be warm and a little witty, never robotic.\n\n"
            "VERIFIED FACTS:\n" + f + ("\n\nVOICE:\n" + voice if voice else ""))

def llm_reply(text):
    if not ANTHROPIC_API_KEY:
        return None
    body = json.dumps({
        "model": ANTHROPIC_MODEL, "max_tokens": 320, "temperature": 0.4,
        "system": build_system_prompt(),
        "messages": [{"role": "user", "content": text or "Hello"}],
    }).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, method="POST",
        headers={"content-type": "application/json", "x-api-key": ANTHROPIC_API_KEY,
                 "anthropic-version": "2023-06-01"})
    try:
        with urllib.request.urlopen(req, timeout=6) as r:
            data = json.loads(r.read().decode())
        parts = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
        out = "".join(parts).strip()
        return out or None
    except Exception as e:
        print("LLM ERROR:", str(e)[:200])
        return None

def decide(kind, value, sender_id):
    if kind == "postback":
        return resolve(REPLIES.get("postbacks", {}).get(value, value) or "fallback")
    r = reply_for_text(value)
    if r:
        return r
    first = (time.time() - _seen.get(sender_id, 0)) > 6 * 3600
    _seen[sender_id] = time.time()
    if first and not ANTHROPIC_API_KEY:
        return _greeting_or_away()
    smart = llm_reply(value)
    if smart:
        return smart
    return _greeting_or_away() if first else REPLIES["fallback"]

def _post(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req) as r:
            return r.status
    except urllib.error.HTTPError as e:
        print("SEND ERROR:", e.read().decode()[:300])
        return e.code

def send_meta(psid, text):
    url = GRAPH + "/me/messages?access_token=" + urllib.parse.quote(PAGE_TOKEN)
    return _post(url, {"recipient": {"id": psid}, "messaging_type": "RESPONSE", "message": {"text": text}})

def send_whatsapp(to, text):
    url = GRAPH + "/" + WHATSAPP_PHONE_ID + "/messages?access_token=" + urllib.parse.quote(WHATSAPP_TOKEN)
    return _post(url, {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": text}})

def valid_signature(req):
    if not APP_SECRET:
        return True
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
    # WhatsApp Cloud API
    if data.get("object") == "whatsapp_business_account":
        for entry in data.get("entry", []):
            for ch in entry.get("changes", []):
                for msg in ch.get("value", {}).get("messages", []):
                    frm = msg.get("from")
                    if not frm:
                        continue
                    if msg.get("type") == "text" and msg.get("text", {}).get("body"):
                        send_whatsapp(frm, decide("text", msg["text"]["body"], frm))
                    elif msg.get("type") == "interactive":
                        inter = msg.get("interactive", {})
                        pid = inter.get("button_reply", {}).get("id") or inter.get("list_reply", {}).get("id")
                        if pid:
                            send_whatsapp(frm, decide("postback", pid, frm))
        return "ok", 200
    # Messenger + Instagram (page object)
    for entry in data.get("entry", []):
        for ev in entry.get("messaging", []):
            psid = ev.get("sender", {}).get("id")
            if not psid:
                continue
            if "postback" in ev and ev["postback"].get("payload"):
                send_meta(psid, decide("postback", ev["postback"]["payload"], psid))
                continue
            m = ev.get("message")
            if not m or m.get("is_echo"):
                continue
            text = m.get("text")
            if not text:           # sticker/image/attachment with no text -> ignore (loop-proof)
                continue
            send_meta(psid, decide("text", text, psid))
    return "ok", 200

@app.get("/")
def health():
    return {"bot": REPLIES.get("persona", "Bot") + " @ " + REPLIES.get("page_name", ""),
            "ok": True,
            "channels": {"messenger": bool(PAGE_TOKEN), "instagram": bool(PAGE_TOKEN),
                         "whatsapp": bool(WHATSAPP_TOKEN and WHATSAPP_PHONE_ID)},
            "smart_llm": bool(ANTHROPIC_API_KEY), "hours_now": within_hours(),
            "rules": len(REPLIES.get("rules", []))}, 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
