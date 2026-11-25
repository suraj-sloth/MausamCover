"""MausamCover server: WhatsApp bot + payment hooks + operator console.

Run:  uv run uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import uuid

from fastapi import BackgroundTasks, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import chain, channels, config, db, engine, flags, sarvam

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("app")

app = FastAPI(title="MausamCover (simulation)")
config.MEDIA_DIR.mkdir(exist_ok=True)
app.mount("/media", StaticFiles(directory=config.MEDIA_DIR), name="media")
templates = Jinja2Templates(directory=str(config.ROOT / "app" / "templates"))
db.init()
chain.enabled()  # deploy local chain eagerly (avoids a first-request race)


def _inbound_poller():
    """Picks up real WhatsApp messages from Twilio's log (sandbox has no webhook)."""
    import threading
    import time as _t

    if not channels.whatsapp_enabled():
        return
    seen = channels.existing_inbound_sids()  # ignore history from before startup

    def loop():
        while True:
            try:
                for form in channels.poll_inbound(seen):
                    db.log_event(None, "whatsapp.in", {"from": form["From"], "body": form["Body"],
                                                       "media": int(form["NumMedia"])})
                    threading.Thread(target=handle_inbound, args=(form,), daemon=True).start()
            except Exception as e:
                log.warning("inbound poll failed: %s", e)
            _t.sleep(3)

    threading.Thread(target=loop, daemon=True).start()
    log.info("WhatsApp inbound poller started (%d old messages skipped)", len(seen))


_inbound_poller()


def _telegram_poller():
    import threading
    import time as _t

    if not channels.telegram_enabled():
        return

    def loop():
        offset = 0
        while True:
            try:
                offset, items = channels.telegram_updates(offset)
                for form, audio in items:
                    if form["Body"].strip() == "/start":
                        channels.send_whatsapp(form["From"], "Namaskara! I'm MausamCover (hackathon demo). Tell me "
                                               "which mela your stall is at and how much you sell on a festive "
                                               "evening. A voice note in Kannada or Hindi works too.")
                        continue
                    db.log_event(None, "whatsapp.in", {"from": form["From"], "body": form["Body"],
                                                       "media": 1 if audio else 0, "channel": "telegram"})
                    threading.Thread(target=handle_inbound, args=(form, audio), daemon=True).start()
            except Exception as e:
                log.warning("telegram poll failed: %s", e)
                _t.sleep(3)

    threading.Thread(target=loop, daemon=True).start()
    log.info("Telegram poller started")


_telegram_poller()

EMPTY_TWIML = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'


# ---------------------------------------------------------------- quoting


def quote_summary(q: engine.Quote) -> str:
    lines = [
        f"MausamCover quote: {q.mela_name}, {q.covered_days} festive evenings ({q.window}).",
        f"1) Rain cover: if rain >= {q.rain_threshold_mm:.0f} mm in the evening window "
        f"(Open-Meteo, {q.lat:.3f},{q.lon:.3f}), you get Rs {q.layer1_payout_per_day} per evening, "
        f"max Rs {q.layer1_cap}. Premium Rs {q.layer1_premium}.",
    ]
    if q.layer2_offered:
        lines.append(
            f"2) Basis-gap cover: if pooled sales of all mela stalls fall >= 30% on any covered evening, "
            f"even without heavy rain, you get Rs {q.layer2_payout}. Market-implied chance "
            f"{q.market_prob_yes * 100:.0f}%, premium Rs {q.layer2_premium}.")
    lines.append(f"Total premium Rs {q.total_premium}. HACKATHON SIMULATION: not real insurance, test payment only.")
    return "\n".join(lines)


def create_policy(phone: str, language: str, daily_sales: int, mela: str) -> tuple[str, engine.Quote, dict, dict]:
    fl = flags.for_user(phone, mela)
    q = engine.make_quote(daily_sales, mela, fl["enabled"]["basis_gap_cover"], fl["cfg"])
    pid = "MC-" + uuid.uuid4().hex[:8].upper()
    pay = channels.create_payment_link(pid, q.total_premium, phone, f"MausamCover TEST premium {pid}")
    db.save_policy(pid, phone, language, q.terms(), q.terms_hash(), "quoted", pay["url"])
    db.log_event(pid, "quoted", {"flags": fl, "terms_hash": q.terms_hash(), "payment": pay})
    return pid, q, pay, fl


def activate(pid: str, how: str):
    p = db.get_policy(pid)
    if not p or p["status"] != "quoted":
        return
    db.set_status(pid, "active")
    q = p["quote"]
    db.log_event(pid, "paid", {"how": how, "amount": q["total_premium"], "test_mode": True})
    c = chain.commit_policy(pid, p["terms_hash"], q["rain_threshold_mm"], q["layer1_payout_per_day"],
                            q["layer2_payout"] or 0)
    db.log_event(pid, "chain.commitPolicy", c)
    if q["layer2_offered"]:
        db.log_event(pid, "chain.recordPrice", chain.record_price(pid, q["market_prob_yes"]))
    verify = f"\nTerms locked on-chain: {c['url']}" if c.get("url") else ""
    channels.send_whatsapp(p["phone"], f"Policy {pid} is active (TEST payment, simulation).{verify}")


# ---------------------------------------------------------------- WhatsApp


@app.post("/whatsapp")
async def whatsapp_webhook(request: Request, bg: BackgroundTasks):
    form = dict(await request.form())
    bg.add_task(handle_inbound, form)  # Twilio times out at 15s; reply async
    return Response(EMPTY_TWIML, media_type="application/xml")


def handle_inbound(form: dict, audio: tuple[bytes, str] | None = None):
    phone = form.get("From", "whatsapp:demo")
    text = (form.get("Body") or "").strip()
    language = "en-IN"
    try:
        fl = flags.for_user(phone, "commercial-street")
        has_twilio_audio = int(form.get("NumMedia", 0) or 0) > 0 and "audio" in form.get("MediaContentType0", "")
        if audio or has_twilio_audio:
            if not fl["enabled"]["voice_intake"]:
                channels.send_whatsapp(phone, "Voice notes are paused right now, please type your message.")
                return
            if sarvam.enabled():
                data, ctype = audio or (channels.download_media(form["MediaUrl0"]), form["MediaContentType0"])
                stt = sarvam.transcribe(data, ctype)
                text, language = stt["text"], stt["language"]
                db.log_event(None, "sarvam.stt", {"phone": phone, **stt})
                channels.send_whatsapp(phone, f"(heard: {text})")

        fields = sarvam.extract(text) if sarvam.enabled() else {}
        if not fields.get("daily_sales_inr"):  # fallback: first number in the text
            import re
            m = re.search(r"(\d[\d,]{2,})", text)
            fields["daily_sales_inr"] = int(m.group(1).replace(",", "")) if m else None
        if not fields.get("daily_sales_inr"):
            channels.send_whatsapp(phone, "Namaskara! Which mela is your stall at, and how much do you usually "
                                          "sell on a festive evening (in rupees)? You can send a voice note.")
            return

        pid, q, pay, fl = create_policy(phone, language, int(fields["daily_sales_inr"]),
                                        fields.get("mela") or "commercial-street")
        summary = quote_summary(q)
        msg = summary
        if sarvam.enabled() and language != "en-IN":
            try:
                msg = sarvam.explain(summary, language) + "\n\n---\n" + summary
            except Exception as e:
                log.warning("explain failed: %s", e)
        channels.send_whatsapp(phone, f"{msg}\n\nPay (TEST, no real money): {pay['url']}")

        if fl["enabled"]["voice_reply"] and sarvam.enabled():
            try:
                wav = sarvam.tts(msg.split("\n---\n")[0], language)
                (config.MEDIA_DIR / f"{pid}.wav").write_bytes(wav)
                channels.send_whatsapp(phone, "", f"{config.PUBLIC_BASE_URL}/media/{pid}.wav")
            except Exception as e:
                log.warning("tts failed: %s", e)
    except Exception as e:
        log.exception("inbound failed")
        db.log_event(None, "error", {"phone": phone, "error": str(e)[:300]})
        channels.send_whatsapp(phone, "Sorry, something went wrong. Please try again.")


# ---------------------------------------------------------------- payments


@app.get("/pay/{pid}", response_class=HTMLResponse)
def simulated_pay_page(pid: str, request: Request):
    p = db.get_policy(pid)
    if not p:
        raise HTTPException(404)
    return templates.TemplateResponse(request, "pay.html", {"p": p})


@app.post("/pay/{pid}")
def simulated_pay(pid: str):
    activate(pid, "simulated UPI (no Razorpay keys)")
    return RedirectResponse(f"/pay/{pid}", status_code=303)


@app.get("/paid/{pid}", response_class=HTMLResponse)
def razorpay_callback(pid: str, request: Request):
    qp = request.query_params
    payload = "|".join([qp.get("razorpay_payment_link_id", ""), qp.get("razorpay_payment_link_reference_id", ""),
                        qp.get("razorpay_payment_link_status", ""), qp.get("razorpay_payment_id", "")])
    sig = hmac.new(config.RAZORPAY_KEY_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if config.RAZORPAY_KEY_SECRET and hmac.compare_digest(sig, qp.get("razorpay_signature", "")) \
            and qp.get("razorpay_payment_link_status") == "paid":
        activate(pid, "razorpay test (callback)")
    return templates.TemplateResponse(request, "pay.html", {"p": db.get_policy(pid)})


@app.post("/razorpay/webhook")
async def razorpay_webhook(request: Request):
    body = await request.body()
    if not channels.verify_razorpay_webhook(body, request.headers.get("X-Razorpay-Signature", "")):
        raise HTTPException(400, "bad signature")
    j = await request.json()
    if j.get("event") == "payment_link.paid":
        ref = j["payload"]["payment_link"]["entity"].get("reference_id")
        if ref:
            activate(ref, "razorpay test (webhook)")
    return {"ok": True}


# ---------------------------------------------------------------- oracle + settlement


@app.post("/api/oracle/heartbeat")
async def oracle_heartbeat(request: Request):
    if request.headers.get("X-Oracle-Token") != config.ORACLE_TOKEN:
        raise HTTPException(401)
    obs = await request.json()
    db.oracle_seen(obs)
    return {"ok": True}


def run_settlement(pid: str, scenario: str):
    p = db.get_policy(pid)
    q = engine.Quote(**{k: v for k, v in p["quote"].items() if k != "total_premium"})
    s = engine.settle(q, scenario)
    db.log_event(pid, "chain.postObservation",
                 chain.post_observation(pid, f"scenario-{scenario}", s.rain_mm, s.index_drop))
    c = chain.settle(pid, s.layer1_paid, s.layer2_paid)
    db.log_event(pid, "chain.settle", c)
    db.log_event(pid, "settled", {"scenario": scenario, "layer1_paid": s.layer1_paid,
                                  "layer2_paid": s.layer2_paid, "explanation": s.explanation})
    db.set_status(pid, "settled")
    link = f"\nVerify on-chain: {c['url']}" if c.get("url") else ""
    channels.send_whatsapp(p["phone"], f"{s.explanation}\nSimulated payout: Rs {s.total_paid} "
                                       f"(no real money moves).{link}")


@app.post("/ops/scenario/{pid}/{scenario}")
def ops_scenario(pid: str, scenario: str):
    p = db.get_policy(pid)
    if not p or p["status"] != "active" or scenario not in engine.SCENARIOS:
        raise HTTPException(400, "policy must be active; scenario A/B/C")
    if not db.oracle_status()["healthy"]:
        db.set_status(pid, "held")
        db.log_event(pid, "held", {"scenario": scenario, "reason": "oracle observation missing/stale",
                                   "needs": "human approval after oracle recovers"})
        channels.send_whatsapp(p["phone"], f"Policy {pid}: weather data feed is delayed, so your settlement is "
                                           "on hold for human review. We'll update you shortly.")
    else:
        run_settlement(pid, scenario)
    return RedirectResponse("/", status_code=303)


@app.post("/ops/approve/{pid}")
def ops_approve(pid: str, approver: str = Form("operator")):
    p = db.get_policy(pid)
    held = [e for e in db.events(pid) if e["kind"] == "held"]
    if not p or p["status"] != "held" or not held:
        raise HTTPException(400, "not held")
    if not db.oracle_status()["healthy"]:
        raise HTTPException(409, "oracle still unhealthy: resolve the incident first")
    db.log_event(pid, "approved", {"by": approver})
    run_settlement(pid, held[0]["detail"]["scenario"])
    return RedirectResponse("/", status_code=303)


@app.post("/ops/intake")
async def ops_intake(request: Request, bg: BackgroundTasks):
    """Console-started conversation: voice/text in, replies go out on real WhatsApp."""
    form = await request.form()
    phone = (form.get("phone") or "").strip().replace(" ", "")
    if phone and not phone.startswith("whatsapp:"):
        phone = "whatsapp:" + (phone if phone.startswith("+") else "+91" + phone)
    audio = None
    f = form.get("audio")
    if f is not None and hasattr(f, "read"):
        data = await f.read()
        if data:
            audio = (data, f.content_type or "audio/webm")
    bg.add_task(handle_inbound, {"From": phone or "whatsapp:demo", "Body": form.get("text") or ""}, audio)
    return {"ok": True}


@app.post("/ops/demo-policy")
def ops_demo_policy(daily_sales: int = Form(8000), mela: str = Form("commercial-street"),
                    phone: str = Form("whatsapp:demo")):
    create_policy(phone, "en-IN", daily_sales, mela)
    return RedirectResponse("/", status_code=303)


@app.post("/ops/activate/{pid}")
def ops_activate(pid: str):
    activate(pid, "operator (simulated payment)")
    return RedirectResponse("/", status_code=303)


# ---------------------------------------------------------------- operator console


def console_ctx() -> dict:
    preview = engine.make_quote(8000, "commercial-street", True, flags.for_user("console", "commercial-street")["cfg"])
    mkt = engine.build_market("commercial-street", engine.DEFAULTS["lmsr_liquidity_b"])
    return {
        "policies": db.list_policies(), "events": db.events(), "oracle": db.oracle_status(),
        "market": mkt, "preview": preview, "scenarios": engine.SCENARIOS,
        "integrations": {
            "Sarvam": sarvam.enabled(), "WhatsApp (Twilio)": channels.whatsapp_enabled(),
            "Razorpay (test)": channels.razorpay_enabled(), "Flagsmith": bool(config.FLAGSMITH_ENV_KEY),
            "Chain (testnet)": chain.enabled(),
        },
        "flags_console": flags.for_user("console", "commercial-street"),
    }


@app.get("/", response_class=HTMLResponse)
def console(request: Request):
    return templates.TemplateResponse(request, "console.html", console_ctx())


@app.get("/partials/live", response_class=HTMLResponse)
def console_live(request: Request):
    return templates.TemplateResponse(request, "_live.html", console_ctx())


@app.get("/tx/{tx_hash}", response_class=HTMLResponse)
def tx_page(tx_hash: str, request: Request):
    try:
        d = chain.tx_details(tx_hash)
    except Exception as e:
        raise HTTPException(404, f"tx not found: {e}")
    if not d:
        raise HTTPException(404)
    return templates.TemplateResponse(request, "tx.html", {"d": d})


@app.get("/healthz")
def healthz():
    return {"ok": True}
