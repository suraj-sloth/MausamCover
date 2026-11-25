"""Compile + deploy MausamLedger to the testnet in .env. Writes deployments.json.

    uv run python scripts/deploy_contract.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import solcx  # noqa: E402
from web3 import Web3  # noqa: E402

from app import config  # noqa: E402

SOLC = "0.8.24"

if not (config.CHAIN_RPC_URL and config.CHAIN_PRIVATE_KEY):
    raise SystemExit("Set CHAIN_RPC_URL and CHAIN_PRIVATE_KEY in .env first.")

solcx.install_solc(SOLC)
src = (config.ROOT / "contracts" / "MausamLedger.sol").read_text()
out = solcx.compile_source(src, output_values=["abi", "bin"], solc_version=SOLC)
_, art = next((k, v) for k, v in out.items() if k.endswith(":MausamLedger"))

w3 = Web3(Web3.HTTPProvider(config.CHAIN_RPC_URL))
acct = w3.eth.account.from_key(config.CHAIN_PRIVATE_KEY)
bal = w3.eth.get_balance(acct.address)
print(f"chain {w3.eth.chain_id}  deployer {acct.address}  balance {w3.from_wei(bal, 'ether')} ETH")
if bal == 0:
    raise SystemExit("Deployer has 0 balance: get testnet funds from a faucet.")

C = w3.eth.contract(abi=art["abi"], bytecode=art["bin"])
tx = C.constructor().build_transaction({
    "from": acct.address, "nonce": w3.eth.get_transaction_count(acct.address), "chainId": w3.eth.chain_id,
})
h = w3.eth.send_raw_transaction(acct.sign_transaction(tx).raw_transaction)
rcpt = w3.eth.wait_for_transaction_receipt(h, timeout=120)
config.DEPLOYMENTS_FILE.write_text(json.dumps(
    {"address": rcpt.contractAddress, "chain_id": w3.eth.chain_id, "abi": art["abi"]}, indent=2))
print("deployed", rcpt.contractAddress, config.CHAIN_EXPLORER_TX + "0x" + h.hex().removeprefix("0x"))
