"""Flagsmith: segment-targeted Layer 2 rollout + live pricing config.

Flags to create in the Flagsmith environment:
  basis_gap_cover    boolean, OFF by default; enable for segment "pilot-mela"
                     (rule: trait mela == commercial-street)
  voice_intake       boolean, ON  (kill switch for Sarvam voice)
  voice_reply        boolean, OFF (Sarvam TTS reply)
  rain_threshold_mm  remote-config value, e.g. 15
  market_loading     remote-config value, e.g. 1.25
"""

from __future__ import annotations

import logging

from . import config

log = logging.getLogger("flags")
_client = None

FALLBACK = {"basis_gap_cover": True, "voice_intake": True, "voice_reply": False}


def _get():
    global _client
    if _client is None and config.FLAGSMITH_ENV_KEY:
        from flagsmith import Flagsmith

        _client = Flagsmith(environment_key=config.FLAGSMITH_ENV_KEY, request_timeout_seconds=5)
    return _client


def for_user(phone: str, mela: str) -> dict:
    """Returns {'enabled': {...}, 'cfg': {...}, 'source': 'flagsmith'|'fallback'}."""
    fs = _get()
    if fs is None:
        return {"enabled": dict(FALLBACK), "cfg": {}, "source": "fallback (no FLAGSMITH_ENV_KEY)"}
    try:
        f = fs.get_identity_flags(identifier=phone, traits={"mela": mela})
        enabled = {}
        for k, default in FALLBACK.items():
            try:
                enabled[k] = f.is_feature_enabled(k)
            except Exception:  # flag not created in Flagsmith yet
                enabled[k] = default
        cfg = {}
        for k in ("rain_threshold_mm", "market_loading"):
            try:
                v = f.get_feature_value(k)
                if v not in (None, ""):
                    cfg[k] = float(v)
            except Exception:
                pass
        return {"enabled": enabled, "cfg": cfg, "source": "flagsmith"}
    except Exception as e:
        log.warning("flagsmith failed: %s", e)
        return {"enabled": dict(FALLBACK), "cfg": {}, "source": f"fallback ({e.__class__.__name__})"}
