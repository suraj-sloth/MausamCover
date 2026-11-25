"""Check each integration's credentials without printing secrets.

    uv run python scripts/check_integrations.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from app import config  # noqa: E402


def show(name, ok, msg=""):
    print(f"{'OK  ' if ok else 'FAIL'}  {name:<18} {msg}")


def check(name, fn):
    try:
        ok, msg = fn()
    except Exception as e:
        ok, msg = False, f"{e.__class__.__name__}: {str(e)[:120]}"
    show(name, ok, msg)


def sarvam():
    if not config.SARVAM_API_KEY:
        return False, "SARVAM_API_KEY empty"
    r = httpx.post("https://api.sarvam.ai/v1/chat/completions", timeout=30,
                   headers={"api-subscription-key": config.SARVAM_API_KEY},
                   json={"model": config.SARVAM_CHAT_MODEL, "max_tokens": 5,
                         "messages": [{"role": "user", "content": "Say ok"}]})
    return r.status_code == 200, f"chat {config.SARVAM_CHAT_MODEL}: HTTP {r.status_code} {'' if r.is_success else r.text[:150]}"


def twilio():
    sid = config.TWILIO_ACCOUNT_SID
    if not sid:
        return False, "TWILIO_ACCOUNT_SID empty"
    if not sid.startswith("AC"):
        return False, f"TWILIO_ACCOUNT_SID starts with '{sid[:2]}': needs the Account SID (AC...) from the Console home page"
    user = config.TWILIO_API_KEY_SID or sid
    pw = config.TWILIO_API_KEY_SECRET or config.TWILIO_AUTH_TOKEN
    r = httpx.get(f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json?PageSize=1", auth=(user, pw), timeout=20)
    return r.status_code == 200, f"HTTP {r.status_code}, sender {config.TWILIO_WHATSAPP_FROM}"


def razorpay():
    if not config.RAZORPAY_KEY_ID:
        return False, "RAZORPAY_KEY_ID empty"
    r = httpx.get("https://api.razorpay.com/v1/payment_links?count=1", timeout=20,
                  auth=(config.RAZORPAY_KEY_ID, config.RAZORPAY_KEY_SECRET))
    return r.status_code == 200, f"test mode, HTTP {r.status_code} {'' if r.is_success else r.text[:120]}"


def flagsmith():
    k = config.FLAGSMITH_ENV_KEY
    if not k:
        return False, "FLAGSMITH_ENV_KEY empty"
    r = httpx.get("https://edge.api.flagsmith.com/api/v1/flags/", headers={"X-Environment-Key": k}, timeout=20)
    if r.status_code != 200:
        hint = " (this looks like an Organisation/Admin API key, not an environment SDK key)" if "." in k and not k.startswith("ser.") else ""
        return False, f"HTTP {r.status_code}{hint}"
    names = sorted(f["feature"]["name"] for f in r.json())
    want = {"basis_gap_cover", "voice_intake", "voice_reply", "rain_threshold_mm", "market_loading"}
    missing = sorted(want - set(names))
    return True, f"flags: {names}" + (f"  MISSING: {missing}" if missing else "")


def chain():
    if not (config.CHAIN_RPC_URL and config.CHAIN_PRIVATE_KEY):
        return False, "CHAIN_RPC_URL / CHAIN_PRIVATE_KEY empty"
    if config.CHAIN_RPC_URL == "local":
        from app import chain as ch
        return ch.enabled(), "LOCAL in-process EVM (fallback: no public explorer)"
    from web3 import Web3

    w3 = Web3(Web3.HTTPProvider(config.CHAIN_RPC_URL, request_kwargs={"timeout": 20}))
    acct = w3.eth.account.from_key(config.CHAIN_PRIVATE_KEY)
    bal = w3.from_wei(w3.eth.get_balance(acct.address), "ether")
    dep = "deployed" if config.DEPLOYMENTS_FILE.exists() else "not deployed yet"
    return bal > 0, f"chain_id={w3.eth.chain_id} address={acct.address} ETH(gas)={bal} contract {dep}"


for n, f in [("Sarvam", sarvam), ("Twilio", twilio), ("Razorpay (test)", razorpay),
             ("Flagsmith", flagsmith), ("Chain (testnet)", chain)]:
    check(n, f)
print(f"\nPUBLIC_BASE_URL = {config.PUBLIC_BASE_URL}")
