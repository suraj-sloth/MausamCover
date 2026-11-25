"""Testnet audit trail. Every call degrades to a 'skipped' record if the chain
is not configured, so the demo never blocks on RPC problems."""

from __future__ import annotations

import json
import logging

from . import config

log = logging.getLogger("chain")
_w3 = None
_acct = None
_contract = None


LOCAL = config.CHAIN_RPC_URL == "local"


def _load_local():
    """In-process EVM (py-evm). Same contract and checks; no public explorer."""
    global _w3, _acct, _contract
    import solcx
    from web3 import EthereumTesterProvider, Web3

    solcx.install_solc("0.8.24")
    out = solcx.compile_source((config.ROOT / "contracts" / "MausamLedger.sol").read_text(),
                               output_values=["abi", "bin"], solc_version="0.8.24")
    art = next(v for k, v in out.items() if k.endswith(":MausamLedger"))
    _w3 = Web3(EthereumTesterProvider())
    _acct = _w3.eth.account.create()
    _w3.eth.send_transaction({"from": _w3.eth.accounts[0], "to": _acct.address, "value": _w3.to_wei(1, "ether")})
    C = _w3.eth.contract(abi=art["abi"], bytecode=art["bin"])
    tx = C.constructor().build_transaction({"from": _acct.address, "nonce": 0, "chainId": _w3.eth.chain_id})
    h = _w3.eth.send_raw_transaction(_acct.sign_transaction(tx).raw_transaction)
    _contract = _w3.eth.contract(address=_w3.eth.wait_for_transaction_receipt(h).contractAddress, abi=art["abi"])
    log.info("local chain: MausamLedger at %s", _contract.address)
    return _contract


def tx_details(tx_hash: str) -> dict | None:
    """Decoded receipt + events for the /tx page (works for local and testnet)."""
    c = _load()
    if c is None:
        return None
    rcpt = _w3.eth.get_transaction_receipt(tx_hash)
    evs = []
    for ev in c.events:
        try:
            for e in ev().process_receipt(rcpt, errors=__import__("web3").logs.DISCARD):
                evs.append({"event": e.event, "args": {k: (v.hex() if isinstance(v, bytes) else v)
                                                       for k, v in e.args.items()}})
        except Exception:
            pass
    return {"tx": tx_hash, "block": rcpt.blockNumber, "status": rcpt.status, "from": rcpt["from"],
            "contract": c.address, "events": evs, "local": LOCAL}


def _load():
    global _w3, _acct, _contract
    if _contract is not None:
        return _contract
    if LOCAL:
        return _load_local()
    if not (config.CHAIN_RPC_URL and config.CHAIN_PRIVATE_KEY and config.DEPLOYMENTS_FILE.exists()):
        return None
    from web3 import Web3

    dep = json.loads(config.DEPLOYMENTS_FILE.read_text())
    _w3 = Web3(Web3.HTTPProvider(config.CHAIN_RPC_URL, request_kwargs={"timeout": 20}))
    _acct = _w3.eth.account.from_key(config.CHAIN_PRIVATE_KEY)
    _contract = _w3.eth.contract(address=dep["address"], abi=dep["abi"])
    return _contract


def enabled() -> bool:
    return _load() is not None


def policy_id_bytes(policy_id: str) -> bytes:
    from web3 import Web3

    return Web3.keccak(text=policy_id)


def _send(fn_name: str, *args) -> dict:
    c = _load()
    if c is None:
        return {"status": "skipped", "reason": "chain not configured"}
    try:
        fn = getattr(c.functions, fn_name)(*args)
        tx = fn.build_transaction({
            "from": _acct.address,
            "nonce": _w3.eth.get_transaction_count(_acct.address, "pending"),
            "chainId": _w3.eth.chain_id,
        })
        signed = _acct.sign_transaction(tx)
        h = _w3.eth.send_raw_transaction(signed.raw_transaction)
        rcpt = _w3.eth.wait_for_transaction_receipt(h, timeout=60)
        tx_hash = "0x" + h.hex().removeprefix("0x")
        ok = rcpt.status == 1
        url = f"{config.PUBLIC_BASE_URL}/tx/{tx_hash}" if LOCAL else config.CHAIN_EXPLORER_TX + tx_hash
        return {"status": "ok" if ok else "reverted", "tx": tx_hash, "url": url}
    except Exception as e:  # demo must keep going
        log.exception("chain call %s failed", fn_name)
        return {"status": "error", "reason": str(e)[:200]}


def commit_policy(policy_id: str, terms_hash: str, threshold_mm: float, l1: int, l2: int) -> dict:
    return _send("commitPolicy", policy_id_bytes(policy_id), bytes.fromhex(terms_hash[2:])[:32],
                 int(threshold_mm * 10), int(l1), int(l2))


def record_price(policy_id: str, prob: float) -> dict:
    return _send("recordPrice", policy_id_bytes(policy_id), int(round(prob * 10000)))


def post_observation(policy_id: str, day: str, rain_mm: float, index_drop: float) -> dict:
    return _send("postObservation", policy_id_bytes(policy_id), day, int(rain_mm * 10),
                 max(0, int(round(index_drop * 10000))))


def settle(policy_id: str, l1_paid: int, l2_paid: int) -> dict:
    return _send("settle", policy_id_bytes(policy_id), int(l1_paid), int(l2_paid))
