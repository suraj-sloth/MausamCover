# Decision notes: MausamCover

This file records the rationale, assumptions, and unresolved questions behind the proposal in `plan.md`. It is a concise decision record, not private raw chain-of-thought.

## Current working decisions

### Start with a weather-sensitive shop

The supplied point-of-sale insight suggests that business sales history can help explain exposure better than weather alone. A shop-first demo makes that insight concrete: compare the business's typical sales with a selected weather window, while being explicit that this is not proof of a loss. Farmers remain a possible later persona, but including both from the start would broaden the workflow, datasets, and language needs too much for a short hackathon build.

### Keep a simple insurance-like offer in front

The user should see a clear fixed premium, a defined trigger, and a payout cap. A prediction-market order book would add friction for the intended user. The market component therefore belongs in an optional, clearly labeled risk-pricing illustration and operations dashboard, rather than becoming the farmer/shopkeeper's primary interface.

### Use a simulated market and settlement

This makes the concept explainable in a prototype without taking deposits, implying guaranteed insurer capacity, or presenting speculative activity as a real financial product. The original suggestion that sandbox funds mean “zero legal risk” is not adopted: a hackathon sandbox can reduce operational exposure, but it does not establish legal status. Any real deployment needs qualified review and appropriate partners.

### Make basis risk a visible product feature

The weather observation and the till are different measurements. The demo should show at least one mismatch example and state what data is used to settle. A POS signal may help tailor an illustration, but it should not silently change a contractual trigger or be represented as independently verified evidence.

### Give each sponsor a distinct, credible job

- **Sarvam AI:** speech, transcription, and/or multilingual explanation for a user who may prefer voice.
- **Flagsmith:** an actual controlled rollout of the market-informed quote or an alternate intake path; this should be easy for a judge to toggle.
- **NudgeBee:** operations investigation and approval-gated response when a weather feed or settlement workflow fails. This fits its published SRE/ops focus better than forcing it into quote pricing.

The sponsor/API integrations are not yet proven. These assignments are hypotheses until credentials and a minimal successful call are verified.

## Assumptions to validate

1. The event the user means is the WeMakeDevs Festive Hacks brief. Its published page says all three sponsor tools are required for the winning project; verify against the team's accepted event instructions and current schedule.
2. The judging team will value a coherent use of each sponsor tool more than superficial integration count.
3. A shopkeeper or small merchant is a better first demo persona than a combined farmer/MSME product.
4. The team can access Sarvam APIs, a NudgeBee workspace/API, and a Flagsmith environment in time.
5. A public weather data source with adequate local history and resolution can be used for a demonstration; no source or trigger has yet been selected.
6. A user can provide a minimal sales baseline manually, avoiding the need for POS provider integrations during the hackathon.

## Open questions that can change the plan

- Which business type and location will make the clearest, most relatable demo?
- Is “insurance” the desired long-term product, or is the primary goal short-term cashflow hedging? The distinction changes the partner, regulatory, and settlement design.
- Should the second layer be shown as an insurer quote comparison, liquidity-pool dashboard, or market-implied probability? Keep only one if time is tight.
- What exact NudgeBee API/workflow is available to the team, and can it be triggered from the demo app?
- Which Sarvam language and modality can be demonstrated reliably with the available credentials and venue/network conditions?
- What location/weather data source has acceptable history and a clear station-to-business mapping?
- What minimum point-of-sale data is useful without collecting customer-level records?
- What does the official judging rubric reward, and what does “use” mean for each sponsor API?

## Risks and mitigations

| Risk | Why it matters | Planning response |
|---|---|---|
| Basis risk | A weather threshold may not match a specific business's loss. | Explain trigger/source and show a mismatch example. Avoid claims that the trigger guarantees recovery of lost sales. |
| Regulatory/product claims | Insurance, derivatives, payments, and consumer financial claims are sensitive and context-dependent. | Keep demo simulated; use no real stakes or payments; avoid claiming authorization or guaranteed cover. Get specialist review before any pilot. |
| Sponsor integration failure | Credentials or endpoints may be unavailable or different from assumptions. | Verify each sponsor call early and preserve a labeled fallback path. |
| NudgeBee feels bolted on | Its published focus is SRE/operations, not insurance underwriting. | Use it for a concrete feed/settlement exception with a human approval step. |
| Weather data resolution/history | A coarse or incomplete source can make a local trigger misleading. | Pick geography and trigger only after inspecting sample data; define missing-data behavior. |
| Voice failure in a live demo | Network, noise, latency, or accents can break speech interaction. | Keep typed input and transcript visible; prepare deterministic demo data. |
| Over-scoped market model | A real market needs liquidity, settlement, and governance far beyond a short MVP. | Limit it to a simulated indicative signal; do not accept real funds or imply real yields. |

## Validation outcome

No API calls, credentials, user interviews, weather dataset inspection, or legal review have been completed in this planning pass. The next gate is to validate event requirements and sponsor access, then choose one user/location/trigger before writing application code.
