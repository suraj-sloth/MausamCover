"""Quote + settlement engine. Pure Python, no I/O.

Layer 1 = parametric rain cover (off-chain, "traditional insurer" rail).
Layer 2 = basis-gap cover on a pooled mela sales index, priced by a simulated
          LMSR prediction market (terms/price/settlement anchored on-chain).

All numbers are illustrative and synthetic. This is a hackathon simulation,
not an insurance product.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from dataclasses import asdict, dataclass, field

# ---------------------------------------------------------------- defaults

DEFAULTS = {
    "rain_threshold_mm": 15.0,      # Layer 1 trigger: rain in the evening window
    "window": "16:00-22:00",        # local time (Asia/Kolkata)
    "covered_days": 7,              # festive week
    "layer1_payout_pct": 0.40,      # of typical daily sales, per trigger day
    "layer1_max_days": 3,           # weekly cap = payout x max_days
    "layer1_trigger_prob": 0.12,    # synthetic historical P(trigger day), Nov, Bengaluru
    "layer1_loading": 1.30,
    "layer2_drop_threshold": 0.30,  # pooled index must fall >= 30%
    "layer2_payout_pct": 0.75,      # of typical daily sales, once per week
    "market_loading": 1.25,
    "lmsr_liquidity_b": 200.0,
}

MELAS = {
    "commercial-street": {"name": "Commercial Street Diwali Mela", "lat": 12.9822, "lon": 77.6083},
    "malleshwaram": {"name": "Malleshwaram Festive Bazaar", "lat": 13.0035, "lon": 77.5709},
    "jayanagar": {"name": "Jayanagar 4th Block Mela", "lat": 12.9250, "lon": 77.5938},
}


def round_inr(x: float) -> int:
    return int(round(x / 10.0) * 10)


# ---------------------------------------------------------------- LMSR market


@dataclass
class LMSRMarket:
    """Binary LMSR market maker. q_yes / q_no = outstanding shares."""

    question: str
    b: float
    q_yes: float = 0.0
    q_no: float = 0.0
    trades: list[dict] = field(default_factory=list)

    def _cost(self, qy: float, qn: float) -> float:
        m = max(qy, qn) / self.b  # log-sum-exp for stability
        return self.b * (m + math.log(math.exp(qy / self.b - m) + math.exp(qn / self.b - m)))

    def price_yes(self) -> float:
        ey, en = math.exp(self.q_yes / self.b), math.exp(self.q_no / self.b)
        return ey / (ey + en)

    def buy(self, trader: str, side: str, shares: float) -> float:
        before = self._cost(self.q_yes, self.q_no)
        if side == "YES":
            self.q_yes += shares
        else:
            self.q_no += shares
        cost = self._cost(self.q_yes, self.q_no) - before
        self.trades.append({
            "trader": trader, "side": side, "shares": round(shares, 2),
            "cost": round(cost, 2), "price_yes_after": round(self.price_yes(), 4),
        })
        return cost


# Seeded, deterministic synthetic traders (no real stakes).
SEED_TRADERS = [
    ("weather-forecaster-1", "YES", 90),
    ("stall-owners-hedging", "YES", 120),
    ("liquidity-provider", "NO", 260),
    ("weather-forecaster-2", "NO", 80),
    ("local-trader", "YES", 40),
    ("liquidity-provider", "NO", 120),
]


def build_market(mela_key: str, b: float) -> LMSRMarket:
    mela = MELAS.get(mela_key, MELAS["commercial-street"])
    mkt = LMSRMarket(
        question=f"Will the pooled sales index of {mela['name']} stalls fall >=30% "
                 f"vs baseline on any covered evening?",
        b=b,
    )
    for trader, side, shares in SEED_TRADERS:
        mkt.buy(trader, side, shares)
    return mkt


# ---------------------------------------------------------------- quote


@dataclass
class Quote:
    mela_key: str
    mela_name: str
    lat: float
    lon: float
    daily_sales: int
    covered_days: int
    window: str
    # layer 1
    rain_threshold_mm: float
    layer1_payout_per_day: int
    layer1_cap: int
    layer1_premium: int
    # layer 2 (None if not offered)
    layer2_offered: bool
    layer2_payout: int | None = None
    layer2_premium: int | None = None
    market_prob_yes: float | None = None
    market_question: str | None = None

    @property
    def total_premium(self) -> int:
        return self.layer1_premium + (self.layer2_premium or 0)

    def terms(self) -> dict:
        """The fields committed on-chain. Changing any of them changes the hash."""
        d = asdict(self)
        d["total_premium"] = self.total_premium
        return d

    def terms_hash(self) -> str:
        blob = json.dumps(self.terms(), sort_keys=True, separators=(",", ":")).encode()
        return "0x" + hashlib.sha3_256(blob).hexdigest()


def make_quote(daily_sales: int, mela_key: str, layer2_enabled: bool, cfg: dict | None = None) -> Quote:
    c = {**DEFAULTS, **(cfg or {})}
    mela_key = mela_key if mela_key in MELAS else "commercial-street"
    mela = MELAS[mela_key]

    l1_payout = round_inr(daily_sales * c["layer1_payout_pct"])
    l1_cap = l1_payout * int(c["layer1_max_days"])
    expected_trigger_days = min(c["layer1_trigger_prob"] * c["covered_days"], c["layer1_max_days"])
    l1_premium = round_inr(expected_trigger_days * l1_payout * c["layer1_loading"])

    q = Quote(
        mela_key=mela_key, mela_name=mela["name"], lat=mela["lat"], lon=mela["lon"],
        daily_sales=int(daily_sales), covered_days=int(c["covered_days"]), window=c["window"],
        rain_threshold_mm=float(c["rain_threshold_mm"]),
        layer1_payout_per_day=l1_payout, layer1_cap=l1_cap, layer1_premium=l1_premium,
        layer2_offered=layer2_enabled,
    )
    if layer2_enabled:
        mkt = build_market(mela_key, float(c["lmsr_liquidity_b"]))
        p = mkt.price_yes()
        l2_payout = round_inr(daily_sales * c["layer2_payout_pct"])
        q.layer2_payout = l2_payout
        q.layer2_premium = round_inr(p * l2_payout * c["market_loading"])
        q.market_prob_yes = round(p, 4)
        q.market_question = mkt.question
    return q


# ---------------------------------------------------------------- scenarios

# Each scenario = one covered evening. Rain is total mm in the window; the
# pooled index is generated from 20 synthetic stalls around a target drop.
SCENARIOS = {
    "A": {"label": "Heavy rain evening", "rain_mm": 32.0, "rain_note": "steady rain 4-10 PM",
          "target_drop": 0.45},
    "B": {"label": "Evening burst (basis risk)", "rain_mm": 9.0,
          "rain_note": "short intense burst 6-8 PM, peak shopping hours", "target_drop": 0.38},
    "C": {"label": "Rain, crowds came anyway", "rain_mm": 18.0, "rain_note": "light rain spread over evening",
          "target_drop": 0.05},
}


def pooled_index(target_drop: float, n_stalls: int = 20, seed: int = 7) -> dict:
    rng = random.Random(seed + int(target_drop * 1000))
    stalls = []
    for i in range(n_stalls):
        baseline = rng.randint(4000, 15000)
        drop = max(-0.2, min(0.95, rng.gauss(target_drop, 0.08)))
        stalls.append({"stall": f"S{i + 1:02d}", "baseline": baseline, "actual": int(baseline * (1 - drop))})
    total_b = sum(s["baseline"] for s in stalls)
    total_a = sum(s["actual"] for s in stalls)
    return {"stalls": stalls, "index_drop": round(1 - total_a / total_b, 4), "synthetic": True}


@dataclass
class Settlement:
    scenario: str
    rain_mm: float
    index_drop: float
    layer1_fired: bool
    layer1_paid: int
    layer2_fired: bool
    layer2_paid: int
    explanation: str

    @property
    def total_paid(self) -> int:
        return self.layer1_paid + self.layer2_paid


def settle(q: Quote, scenario_key: str) -> Settlement:
    s = SCENARIOS[scenario_key]
    idx = pooled_index(s["target_drop"])
    rain = s["rain_mm"]
    l1 = rain >= q.rain_threshold_mm
    l2 = q.layer2_offered and idx["index_drop"] >= DEFAULTS["layer2_drop_threshold"]
    l1_paid = q.layer1_payout_per_day if l1 else 0
    l2_paid = (q.layer2_payout or 0) if l2 else 0

    parts = [
        f"Rain {rain:.0f} mm in {q.window} ({s['rain_note']}); trigger is {q.rain_threshold_mm:.0f} mm, "
        f"so rain cover {'PAYS' if l1 else 'does not pay'}.",
        f"Pooled mela sales fell {idx['index_drop'] * 100:.0f}% (threshold 30%).",
    ]
    if q.layer2_offered:
        parts.append(f"Basis-gap cover {'PAYS' if l2 else 'does not pay'}.")
    if not l1 and idx["index_drop"] >= DEFAULTS["layer2_drop_threshold"]:
        parts.append("This is basis risk: the rain gauge missed a real loss"
                     + (", and the basis-gap cover closed the gap." if l2 else "."))
    if l1 and idx["index_drop"] < DEFAULTS["layer2_drop_threshold"]:
        parts.append("Basis risk the other way: the trigger fired though sales held up.")
    return Settlement(scenario_key, rain, idx["index_drop"], l1, l1_paid, l2, l2_paid, " ".join(parts))
