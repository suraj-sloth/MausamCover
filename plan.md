# Plan: MausamCover — protect your peak festive week

**Event:** WeMakeDevs Festive Hacks × WeAreDevelopers India, BIEC Bengaluru, **25 Nov 2026**.
**Hard deadline:** repo + setup README + demo video submitted by **5:00 PM IST**. Judging 5:00–5:45.
**Rules that bind us:** all three sponsors (Flagsmith, NudgeBee, Sarvam AI) must be used to win; 2nd prize is *Best use of Flagsmith*; "something that runs, not slides."
**Time now:** 1:00 PM → ~3h15m build, then README + video.

## One-liner

A Diwali-mela stall owner makes a big share of their year's sales in one festive week. One unseasonal Bengaluru downpour can wipe that week out. MausamCover lets them ask in Kannada/Hindi, get a two-layer protection quote, and see exactly what would pay out and why. Everything is a **simulation**: no real money, insurer, or contract.

## Persona and problem (one person, one headache)

- **Who:** an owner of a festive pop-up stall (sweets, diyas, decor) at a Bengaluru Diwali/Christmas mela.
- **Headache:** November northeast-monsoon rain cancels evening footfall in peak week; there is no product that covers *lost festive sales*.
- **Core insight (basis risk):** rain at a weather grid point ≠ this mela's lost sales. A pure rain trigger can miss real losses (short evening burst under the daily threshold) or pay when sales were fine.

## Product: two layers

### Layer 1: Parametric rain cover (default, always on)
- Trigger: Open-Meteo daily precipitation at the mela's lat/lon ≥ threshold (e.g. 15 mm) between 4 PM and 10 PM on any covered day.
- Fixed premium, fixed payout per trigger day, cap for the week.
- Transparent: shows grid point, time window, threshold, data source.

### Layer 2: Basis-gap cover, priced by a prediction market (behind Flagsmith)
- **Market question:** "Will the pooled sales index of participating stalls at <mela> fall ≥30% vs their baseline during the covered week?"
- **Why pooled:** no single stall can move the outcome (avoids moral hazard / self-reported loss gaming), yet it tracks real festive loss far better than rainfall.
- **Pricing:** simulated LMSR market with seeded traders (forecasters, stall owners hedging, a liquidity provider). Market-implied probability *p* → Layer-2 premium = *p* × payout × loading.
- **Payout:** if the index resolves YES, Layer 2 pays, even when Layer 1 didn't fire. That closes the basis-risk gap.
- **Boundary:** no real stakes, deposits, positions, or returns. Seeded/simulated only, labelled on screen.

### Demo scenarios (seeded, deterministic)
| Scenario | Rain trigger | Pooled sales index | Layer 1 | Layer 2 |
|---|---|---|---|---|
| A. Heavy rain day | fires | −45% | pays | pays |
| B. **Evening burst** (the basis-risk story) | does not fire (9 mm total, but 6–8 PM) | −38% | ✗ | **pays** |
| C. Rain, but crowds came anyway | fires | −5% | pays | ✗ |

Scenario B is the headline moment of the demo.

## What the stall owner sees vs what runs underneath

**Front end = WhatsApp only.** The stall owner never sees a market, a wallet, or a chain.
1. Sends a WhatsApp voice note in Kannada/Hindi: "Diwali week, Commercial Street mela, ~₹8,000/day, what if it rains?"
2. Gets back a plain-language quote (text, voice reply if time): what's covered, premium, max payout, what decides a payout.
3. Taps a **UPI payment link (Razorpay test mode, no real money)**. Policy is active, and the chat shows a "Verify on-chain" link.
4. After the event: WhatsApp message "Rain trigger didn't fire, but mela sales fell 38%. Basis-gap cover pays ₹X (simulated)."

**Under the hood = two rails:**
- **Off-chain, traditional insurance rail (Layer 1):** parametric rain cover with fixed premium and payout, presented as an illustrative insurer offer. In a real version this is an authorised insurance partner.
- **On-chain testnet rail (Layer 2 + audit trail):** basis-gap cover priced by the simulated prediction market. Terms, observations, price and settlement are committed on a testnet.

**Channel stack:**
- WhatsApp via **Twilio WhatsApp sandbox** → webhook on our server (ngrok or deployed URL).
- Voice notes → **Sarvam STT** → **Sarvam chat** extracts fields + writes the reply → optional **Sarvam TTS** voice reply.
- Premium → **Razorpay Payment Link (test mode)** → payment webhook marks policy active → `commitPolicy` on-chain.
- Payouts are **simulated** messages only; no UPI transfers out.

## USP: on-chain transparency

**Claim:** every policy's terms, the data used to settle it, the market's price, and the payout decision are publicly auditable and tamper-evident. Nobody, including us, can change a trigger or rewrite a settlement after the fact.

**Honest limit (say it before judges do):** the chain proves *what was committed and when*, not that the rain reading or sales index is true. Next steps for that: multiple weather sources and verified POS data.

**Design (testnet only, no value-bearing tokens):**
- One small contract, `MausamLedger`, on a testnet (Base Sepolia or Polygon Amoy, whichever faucet works first):
  - `commitPolicy(policyId, termsHash, threshold, window, payout, gridPoint)` at quote time, which locks the terms.
  - `postObservation(policyId, day, rainMm, poolIndex)` signed by the app's oracle key.
  - `recordPrice(policyId, impliedProbBps)` stores the market-implied probability used for the Layer-2 premium.
  - `settle(policyId, layer1Paid, layer2Paid)` checks against committed terms, emits event.
- **Off-chain:** LMSR trading and seeded traders stay in the app (no wallets, no tokens).
- **No user wallets:** a server-side signer pays gas. The UI has a "Verify on-chain" button that opens the transaction in the block explorer.
- **Ties into NudgeBee:** the worker that breaks in the demo is the **oracle poster**. If it is down, nothing is posted on-chain, settlement is held, NudgeBee investigates, a human approves the runbook, and the worker recovers and posts.

## Sponsor roles

### Sarvam AI: multilingual intake + explanation
- Speech-to-text for the stall owner's spoken request (Kannada or Hindi + English).
- Chat model to extract `{business type, mela, covered dates, typical daily sales}` and to explain the quote in plain language.
- Text-to-speech to read the quote and the payout explanation back.
- Fallbacks: visible transcript, typed input, and a pre-recorded audio clip for venue Wi-Fi failure.

### Flagsmith: rollout + live config (aim for the Best-use prize)
- `basis_gap_cover` flag, **segment-targeted** to a "pilot mela" segment (identity trait `mela=commercial-street`). Other users see Layer 1 only.
- **Remote config** values: `rain_threshold_mm`, `market_loading`, `lmsr_liquidity_b`. Changing them live changes the quote without a redeploy. Labelled "demo pricing config," not underwriting.
- `voice_intake` flag as a kill switch, which is also our live-demo fallback.
- Server-side SDK with the environment key; no management token in the client.

### NudgeBee: operations on real infrastructure
- Run the **weather-ingest worker** (polls Open-Meteo, writes observations) as a pod in a small Kubernetes cluster connected to NudgeBee.
- Demo incident: break the worker (bad config / crash loop). Observations go stale → app moves settlement to **"held: observation missing, human review."**
- NudgeBee investigates the pod failure and proposes an **approval-gated runbook** (fix config / restart). A human approves → worker recovers → settlement proceeds.
- This is NudgeBee's real job (SRE), applied to the thing our payouts depend on.

## Architecture (keep it small)

- **WhatsApp bot server:** Twilio webhook → Sarvam → quote engine → Razorpay link → on-chain commit.
- **Operator web app** (Next.js or similar, for judges and the demo, not the stall owner): market view, scenario simulator, settlement ledger with explorer links, Flagsmith-driven views, ops/approval panel.
- **Worker:** weather-ingest container, deployed to the NudgeBee-connected cluster.
- **Stack:** Python 3.12 via `uv`. FastAPI + uvicorn server (Twilio/Razorpay webhooks, quote API, operator pages via Jinja2 + htmx); `httpx` for Sarvam/Twilio/Razorpay/Open-Meteo REST; official `flagsmith` SDK; `web3.py` + `py-solc-x` (compile + deploy the Solidity contract from Python, no Foundry needed); stdlib `sqlite3`. Oracle worker = small Python script in a `python:3.12-slim` image on a **kind** cluster watched by NudgeBee. ngrok for webhooks.
- **Every integration degrades gracefully:** if a key is missing, that step is logged as "skipped (not configured)" and the demo continues.
- **Data:** SQLite/JSON seed: 20 stalls, baselines, pooled index per scenario, seeded market trades. Synthetic and labelled.
- **External:** Open-Meteo (no key), Sarvam API, Flagsmith SDK, NudgeBee, Twilio WhatsApp sandbox, Razorpay (test mode), testnet RPC.

## Timeline (1:00 → 5:00 PM)

| Time | Work | Done when |
|---|---|---|
| 1:15–1:45 | **De-risk:** Twilio sandbox echo bot reachable via ngrok; Razorpay test payment link created; Sarvam STT on a voice note; Flagsmith flag read; NudgeBee sees the cluster; Open-Meteo fetch; **testnet faucet + empty contract deployed**. Public repo. | All green, or fallback decided |
| 1:45–2:35 | Core engine: quote (Layer 1 + LMSR Layer 2), scenarios A/B/C, settlement. Seed data. Callable from a test script. | Scenarios A/B/C run end to end |
| 1:45–2:35 *(parallel)* | WhatsApp flow: voice note → Sarvam STT → chat extraction → quote reply → Razorpay link → payment webhook. | Real phone gets a quote and a test payment link |
| 2:35–3:15 | `MausamLedger` contract + server signer: commit on payment, post observations, record price, settle; explorer links in chat and in the operator app. | Scenario B leaves a verifiable trail |
| 3:15–3:40 | Operator app (market, ledger, scenario buttons); Flagsmith segment flag + `rain_threshold_mm` remote config. | Flag toggle changes the quote live |
| 3:40–4:00 | Oracle-poster worker on cluster; break-it script; settlement "held"; NudgeBee investigation + approval. | Incident → approve → recovery → posted on-chain |
| 4:00–4:15 | README (setup, env vars, seed, run, demo script); feature freeze. | A stranger could run it |
| 4:15–4:45 | Record 2–3 min demo video; submit. | Submitted with 15 min buffer |

**If parallel (team of 2–4):** A = quote engine + market + contract; B = WhatsApp + Sarvam + Razorpay; C = cluster + oracle worker + NudgeBee; D = operator app + Flagsmith + README + video script.

**Cut order if behind:** Sarvam TTS → remote-config extras → live Open-Meteo (use cached JSON) → on-chain `recordPrice` → Razorpay (fall back to a "Pay (test)" button) → *never cut* WhatsApp voice → quote, Scenario B, on-chain commit + settle, the Flagsmith toggle, or the NudgeBee approval.

**WhatsApp fallback:** if Twilio/ngrok fails on stage, play the pre-recorded phone screen capture from an earlier run.

**On-chain fallback:** if the testnet RPC is flaky during recording, show pre-recorded transaction links from an earlier successful run (labelled).

## Demo video script (2–3 min)

1. On a real phone, the stall owner sends a WhatsApp voice note in Kannada/Hindi: "Diwali week, Commercial Street mela, I usually sell ₹8,000 a day; what if it rains?" (Sarvam STT + chat)
2. WhatsApp reply: Layer 1 rain cover quote. Presenter flips the Flagsmith segment → next reply includes Layer 2 basis-gap cover with its market-implied price.
2b. Owner taps the UPI test-payment link (Razorpay test mode) → "Policy active" + "Verify on-chain" link.
3. Change `rain_threshold_mm` in Flagsmith → quote updates live.
4. From the operator app, run Scenario B: evening burst; rain trigger misses, pooled index −38%, Layer 2 pays. The owner's phone gets the WhatsApp payout message (simulated). Explain basis risk in one sentence.
5. Click "Verify on-chain": terms committed before the event, observations, price, and settlement all on the explorer.
6. Break the oracle worker → nothing posted, settlement held → NudgeBee investigates → human approves runbook → recovered and posted.
7. Closing card: simulated only; no real insurance, payments, or market.

## Boundaries (keep on screen)

- Simulation only: not an insurer, not a licensed product, no real premiums, payouts, stakes or UPI transfers. Razorpay runs in **test mode only**, never live keys. WhatsApp messages say "test/simulated" on the payment and payout steps.
- Any real version would need an authorised insurance partner and specialist review (IRDAI, SEBI/derivatives, consumer protection, data, payments).
- Sales data is synthetic; in reality, stall baselines would need verified POS data.

## Success criteria

- Demo video shows all three sponsors doing visible, real work.
- Scenario B makes basis risk, and how Layer 2 covers it, obvious in under 30 seconds.
- Flagsmith changes the product live (segment + remote config) with no redeploy.
- Public repo with a README someone else can follow.
