# MausamCover: protect your peak festive week

> **Hackathon simulation.** Not insurance, not a licensed product, no real money,
> stakes, or payouts. Payments use Razorpay **test mode**; the chain is a **testnet**.

A Diwali-mela stall owner earns a big share of their year in one festive week, and one
unseasonal Bengaluru downpour can wipe it out. MausamCover lets them ask on **WhatsApp**
(voice note in Kannada/Hindi/English), get a two-layer quote, pay a **test UPI** premium,
and later see exactly why a payout did or didn't happen, **verifiable on-chain**.

## How it works

| Layer | What it covers | Rail |
|---|---|---|
| 1. Rain cover | Rain ≥ threshold in the 4–10 PM window at the mela's grid point (Open-Meteo) | Off-chain, "traditional insurer" style fixed premium |
| 2. Basis-gap cover | Pooled sales of *all* mela stalls fall ≥30%, even if the rain gauge didn't trigger | Priced by a simulated LMSR prediction market |

**Basis risk** = the gap between what the weather gauge says and what the shop lost. A short 6–8 PM burst
(9 mm) misses a 15 mm rain trigger, but footfall still crashes. Layer 2 closes that gap; pooling many stalls
means no single owner can game the index.

**On-chain transparency (testnet):** `MausamLedger` records the policy's terms hash at payment, the market
price, observations, and the settlement. `settle()` *rejects* any payout that doesn't match the committed terms.

### Sponsor tools

- **Sarvam AI:** WhatsApp voice note → speech-to-text, chat model extracts fields and explains the quote in
  the user's language, optional text-to-speech reply.
- **Flagsmith:** `basis_gap_cover` rolled out to a *pilot-mela segment*; `rain_threshold_mm` / `market_loading`
  as remote config (change live, quote changes, no redeploy); `voice_intake` / `voice_reply` kill switches.
- **NudgeBee:** the weather-oracle worker runs on Kubernetes. When it breaks, settlements are **held**;
  NudgeBee investigates the crash-looping pod and runs an approval-gated runbook; then an operator approves
  the held settlement.

## Run it

```sh
uv sync
cp .env.example .env          # fill what you have; missing keys fall back gracefully
uv run uvicorn app.main:app --reload --port 8080
open http://localhost:8080    # operator console
```

### Testnet contract
```sh
# put a throwaway key with faucet funds in CHAIN_PRIVATE_KEY, then:
uv run python scripts/deploy_contract.py     # writes deployments.json
```

### WhatsApp (Twilio sandbox)
```sh
ngrok http 8080               # set PUBLIC_BASE_URL to the https URL
```
Twilio Console → Messaging → Try it out → WhatsApp: join the sandbox from your phone, set
*When a message comes in* to `POST https://<ngrok>/whatsapp`.

### Oracle worker on Kubernetes (for NudgeBee)
```sh
kind create cluster --name mausamcover
docker build -t mausamcover/oracle:dev worker/
kind load docker-image mausamcover/oracle:dev --name mausamcover
kubectl apply -f k8s/oracle.yaml
# connect the cluster to NudgeBee (agent install per NudgeBee docs)
./scripts/incident.sh break   # demo incident
./scripts/incident.sh fix     # what the approved runbook does
```

### Flagsmith setup
Create in your environment: `basis_gap_cover` (off; on for segment `pilot-mela` where trait
`mela = commercial-street`), `voice_intake` (on), `voice_reply` (off), `rain_threshold_mm` (value `15`),
`market_loading` (value `1.25`).

## What runs in this demo build (honest status)

- **Channels:** Telegram bot (`TELEGRAM_BOT_TOKEN`) gives full two-way voice/text. WhatsApp via Twilio sandbox:
  inbound messages are picked up by polling Twilio's message log (no webhook needed); replies are blocked on a
  Twilio *trial* account (error 21654, template required), so they show in the console chat panel with a QR for
  the payment link. Upgrading Twilio enables WhatsApp replies with no code change.
- **Chain:** `CHAIN_RPC_URL=local` runs `MausamLedger` on an in-process EVM (py-evm) with a `/tx/<hash>` page that
  decodes events. With a funded Base Sepolia key it uses the public testnet (`scripts/deploy_contract.py`).
- **Kubernetes:** k3d (`k3d cluster create mausamcover`) with the oracle worker (`k8s/oracle.yaml`, Recreate
  strategy so a bad config takes the feed down) and the NudgeBee agent (helm, per NudgeBee dashboard).
- Server listens on **8080** (`uv run uvicorn app.main:app --host 0.0.0.0 --port 8080`).
- `uv run python scripts/check_integrations.py` checks every key without printing secrets.

## Demo script

1. Send a WhatsApp voice note: "Diwali week, Commercial Street mela, I sell about ₹8,000 a day, what if it rains?"
2. Get the quote; flip `basis_gap_cover` in Flagsmith and ask again: Layer 2 appears.
3. Tap the test UPI link → "Policy active" + on-chain link.
4. Console → Scenario **B (evening burst)** → rain cover doesn't pay, basis-gap cover does; WhatsApp gets the
   explanation + on-chain settlement link.
5. `./scripts/incident.sh break` → new policy's settlement is **held** → NudgeBee investigates → approve runbook
   → oracle healthy → **Approve settlement** in console.

## Layout
```
app/engine.py      quote, LMSR market, scenarios, settlement (pure Python)
app/main.py        FastAPI: WhatsApp + payment webhooks, oracle, ops, console
app/{sarvam,flags,channels,chain,db}.py   integrations
contracts/MausamLedger.sol   testnet audit-trail contract
worker/            oracle worker image;  k8s/  manifests;  scripts/  deploy + incident
```

## Limits (honest)

- The chain proves what was committed and when, **not** that the rain reading or sales index is true.
  Next steps: multiple weather sources, verified POS data.
- Sales data and market traders are synthetic. A real product needs an authorised insurer and review under
  IRDAI, SEBI, consumer-protection, data, and payments rules.
