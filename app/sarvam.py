"""Sarvam AI: speech-to-text, chat (field extraction + explanation), text-to-speech.

Endpoint shapes follow Sarvam's REST API; VERIFY model names and response
fields against current docs during the de-risk slot (models are env-configurable).
"""

from __future__ import annotations

import base64
import json
import logging
import re
import shutil
import subprocess
import tempfile

import httpx

from . import config

log = logging.getLogger("sarvam")
BASE = "https://api.sarvam.ai"
LANG_NAMES = {"kn-IN": "Kannada", "hi-IN": "Hindi", "en-IN": "English", "ta-IN": "Tamil", "te-IN": "Telugu"}


def _headers():
    return {"api-subscription-key": config.SARVAM_API_KEY}


def _post(path: str, **kw) -> httpx.Response:
    """POST with one retry: the venue network resets connections now and then."""
    for attempt in range(3):
        try:
            r = httpx.post(f"{BASE}{path}", headers=_headers(), timeout=60, **kw)
            if r.status_code >= 500 and attempt < 2:
                continue
            if r.status_code >= 400:
                log.warning("sarvam %s -> %s %s", path, r.status_code, r.text[:300])
            r.raise_for_status()
            return r
        except httpx.TransportError:
            if attempt == 2:
                raise
            log.warning("sarvam %s transport error, retrying", path)
    raise RuntimeError("unreachable")


def enabled() -> bool:
    return bool(config.SARVAM_API_KEY)


def _to_wav(data: bytes, content_type: str) -> tuple[bytes, str, str]:
    """WhatsApp voice notes are OGG/Opus. Convert to 16k WAV if ffmpeg exists."""
    if "wav" in content_type or not shutil.which("ffmpeg"):
        ext = "ogg" if "ogg" in content_type else "wav"
        return data, f"audio.{ext}", content_type or "audio/ogg"
    with tempfile.NamedTemporaryFile(suffix=".ogg") as src, tempfile.NamedTemporaryFile(suffix=".wav") as dst:
        src.write(data)
        src.flush()
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src.name, "-ar", "16000", "-ac", "1", dst.name],
                       check=True)
        return open(dst.name, "rb").read(), "audio.wav", "audio/wav"


def transcribe(audio: bytes, content_type: str) -> dict:
    """-> {'text': str, 'language': 'kn-IN' | ...}"""
    data, name, ctype = _to_wav(audio, content_type)
    r = _post("/speech-to-text", files={"file": (name, data, ctype)},
              data={"model": config.SARVAM_STT_MODEL, "language_code": "unknown"})
    j = r.json()
    return {"text": j.get("transcript", ""), "language": j.get("language_code") or "en-IN"}


def chat(system: str, user: str, max_tokens: int = 1500) -> str:
    r = _post("/v1/chat/completions", json={
        "model": config.SARVAM_CHAT_MODEL,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0.2, "max_tokens": max_tokens,
    })
    text = r.json()["choices"][0]["message"]["content"] or ""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()  # strip reasoning, if any


EXTRACT_SYS = """Extract fields from a festive-season stall owner's message (any Indian language).
Return ONLY JSON: {"daily_sales_inr": int|null, "mela": "commercial-street"|"malleshwaram"|"jayanagar"|null,
"business": str|null, "wants_cover": bool}. Typical daily sales in rupees; "8 hazaar" = 8000."""


def extract(text: str) -> dict:
    try:
        raw = chat(EXTRACT_SYS, text)
        m = re.search(r"\{.*\}", raw, re.S)
        return json.loads(m.group(0)) if m else {}
    except Exception as e:
        log.warning("extract failed: %s", e)
        return {}


EXPLAIN_SYS = """You explain a SIMULATED weather-protection quote to a small festive stall owner on WhatsApp.
Reply in {lang}, warm and simple, max 120 words, no markdown tables. Keep every number exactly as given.
Say clearly it is a hackathon demo, not real insurance. End by saying they can tap the test payment link."""


def explain(quote_text: str, language: str) -> str:
    return chat(EXPLAIN_SYS.format(lang=LANG_NAMES.get(language, "English")), quote_text)


def tts(text: str, language: str) -> bytes:
    r = _post("/text-to-speech", json={
        "inputs": [text[:480]], "target_language_code": language if language in LANG_NAMES else "en-IN",
        "model": config.SARVAM_TTS_MODEL,
    })
    return base64.b64decode(r.json()["audios"][0])
