"""Twilio WhatsApp sandbox + Razorpay Payment Links (TEST MODE)."""

from __future__ import annotations

import hashlib
import hmac
import logging

import httpx

from . import config

log = logging.getLogger("channels")


# ---------------------------------------------------------------- WhatsApp


def whatsapp_enabled() -> bool:
    return bool(config.TWILIO_ACCOUNT_SID and config.TWILIO_AUTH_TOKEN)


def _log_out(to: str, body: str, result: dict) -> dict:
    from . import db  # local import: db has no deps on channels
    db.log_event(None, "whatsapp.out", {"to": to, "body": body, **result})
    return result


def send_whatsapp(to: str, body: str, media_url: str | None = None) -> dict:
    """Send to the user's channel. 'telegram:<chat_id>' goes to Telegram, else WhatsApp."""
    if to.startswith("telegram:"):
        return _log_out(to, body, send_telegram(to.removeprefix("telegram:"), body, media_url))
    if not whatsapp_enabled():
        log.info("[whatsapp skipped] to=%s body=%s", to, body)
        return _log_out(to, body, {"status": "skipped"})
    data = {"From": config.TWILIO_WHATSAPP_FROM, "To": to, "Body": body[:1500]}
    if media_url:
        data["MediaUrl"] = media_url
    r = httpx.post(f"https://api.twilio.com/2010-04-01/Accounts/{config.TWILIO_ACCOUNT_SID}/Messages.json",
                   data=data, auth=config.TWILIO_AUTH, timeout=20)
    if r.status_code >= 300:
        log.warning("twilio send failed %s %s", r.status_code, r.text[:300])
        code = (r.json() if r.headers.get("content-type", "").startswith("application/json") else {}).get("code")
        return _log_out(to, body, {"status": "blocked" if code == 21654 else "error", "code": code or r.status_code})
    return _log_out(to, body, {"status": "ok", "sid": r.json().get("sid")})


# ---------------------------------------------------------------- inbound polling (no webhook needed)

API = "https://api.twilio.com"


def poll_inbound(seen: set[str]) -> list[dict]:
    """Inbound WhatsApp messages to our sender that we haven't processed yet, as
    Twilio-webhook-shaped dicts (From, Body, NumMedia, MediaUrl0, MediaContentType0)."""
    r = httpx.get(f"{API}/2010-04-01/Accounts/{config.TWILIO_ACCOUNT_SID}/Messages.json",
                  params={"To": config.TWILIO_WHATSAPP_FROM, "PageSize": 20}, auth=config.TWILIO_AUTH, timeout=15)
    r.raise_for_status()
    out = []
    for m in reversed(r.json().get("messages", [])):
        if m["direction"] != "inbound" or m["sid"] in seen:
            continue
        seen.add(m["sid"])
        form = {"From": m["from"], "Body": m.get("body") or "", "NumMedia": m.get("num_media") or "0", "sid": m["sid"]}
        if int(form["NumMedia"]) > 0:
            mr = httpx.get(f"{API}{m['subresource_uris']['media']}", auth=config.TWILIO_AUTH, timeout=15)
            media = mr.json().get("media_list", [])
            if media:
                form["MediaUrl0"] = API + media[0]["uri"].removesuffix(".json")
                form["MediaContentType0"] = media[0].get("content_type", "")
        out.append(form)
    return out


def existing_inbound_sids() -> set[str]:
    try:
        r = httpx.get(f"{API}/2010-04-01/Accounts/{config.TWILIO_ACCOUNT_SID}/Messages.json",
                      params={"To": config.TWILIO_WHATSAPP_FROM, "PageSize": 50}, auth=config.TWILIO_AUTH, timeout=15)
        return {m["sid"] for m in r.json().get("messages", [])}
    except Exception:
        return set()


def download_media(url: str) -> bytes:
    r = httpx.get(url, auth=config.TWILIO_AUTH,
                  follow_redirects=True, timeout=30)
    r.raise_for_status()
    return r.content


# ---------------------------------------------------------------- Razorpay (test)


def razorpay_enabled() -> bool:
    return bool(config.RAZORPAY_KEY_ID and config.RAZORPAY_KEY_SECRET)


def create_payment_link(policy_id: str, amount_inr: int, phone: str, description: str) -> dict:
    """-> {'url': str, 'id': str, 'mode': 'razorpay-test'|'simulated'}"""
    if not razorpay_enabled():
        return {"url": f"{config.PUBLIC_BASE_URL}/pay/{policy_id}", "id": None, "mode": "simulated"}
    contact = phone.removeprefix("whatsapp:")
    r = httpx.post("https://api.razorpay.com/v1/payment_links", timeout=20,
                   auth=(config.RAZORPAY_KEY_ID, config.RAZORPAY_KEY_SECRET),
                   json={
                       "amount": int(amount_inr) * 100, "currency": "INR",
                       "description": description[:2000],
                       "reference_id": policy_id,
                       "customer": {"contact": contact},
                       "notify": {"sms": False, "email": False},
                       "notes": {"policy_id": policy_id, "mode": "TEST - hackathon simulation"},
                       "callback_url": f"{config.PUBLIC_BASE_URL}/paid/{policy_id}",
                       "callback_method": "get",
                   })
    if r.status_code >= 300:
        log.warning("razorpay failed %s %s", r.status_code, r.text[:300])
        return {"url": f"{config.PUBLIC_BASE_URL}/pay/{policy_id}", "id": None, "mode": "simulated"}
    j = r.json()
    return {"url": j["short_url"], "id": j["id"], "mode": "razorpay-test"}


def verify_razorpay_webhook(body: bytes, signature: str) -> bool:
    if not config.RAZORPAY_WEBHOOK_SECRET:
        return False
    expected = hmac.new(config.RAZORPAY_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")


# ---------------------------------------------------------------- Telegram (long polling)

TG = "https://api.telegram.org"


def telegram_enabled() -> bool:
    return bool(config.TELEGRAM_BOT_TOKEN)


def send_telegram(chat_id: str, body: str, media_url: str | None = None) -> dict:
    if media_url:
        r = httpx.post(f"{TG}/bot{config.TELEGRAM_BOT_TOKEN}/sendAudio", timeout=30,
                       data={"chat_id": chat_id, "audio": media_url})
    else:
        r = httpx.post(f"{TG}/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage", timeout=20,
                       data={"chat_id": chat_id, "text": body[:4000], "disable_web_page_preview": "true"})
    if not r.is_success:
        log.warning("telegram send failed %s %s", r.status_code, r.text[:200])
        return {"status": "error", "code": r.status_code}
    return {"status": "ok", "channel": "telegram"}


def telegram_updates(offset: int) -> tuple[int, list[tuple[dict, tuple[bytes, str] | None]]]:
    """Long-poll Telegram. Returns (next_offset, [(form, audio)])."""
    r = httpx.get(f"{TG}/bot{config.TELEGRAM_BOT_TOKEN}/getUpdates", timeout=40,
                  params={"offset": offset, "timeout": 25, "allowed_updates": '["message"]'})
    r.raise_for_status()
    out = []
    for u in r.json().get("result", []):
        offset = max(offset, u["update_id"] + 1)
        m = u.get("message") or {}
        if not m:
            continue
        form = {"From": f"telegram:{m['chat']['id']}", "Body": m.get("text") or m.get("caption") or ""}
        audio = None
        voice = m.get("voice") or m.get("audio")
        if voice:
            f = httpx.get(f"{TG}/bot{config.TELEGRAM_BOT_TOKEN}/getFile", params={"file_id": voice["file_id"]},
                          timeout=20).json()["result"]
            data = httpx.get(f"{TG}/file/bot{config.TELEGRAM_BOT_TOKEN}/{f['file_path']}", timeout=30).content
            audio = (data, voice.get("mime_type") or "audio/ogg")
        out.append((form, audio))
    return offset, out
