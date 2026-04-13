"""
data_fetcher.py
Fetches live market data from Kalshi and Polymarket.
Supports: volume metrics, category filtering, market snapshots.
"""

import os
import requests
from dataclasses import dataclass, field

KALSHI_BASE = "https://api.elections.kalshi.com/trade-api/v2"
POLYMARKET_GAMMA = "https://gamma-api.polymarket.com"
POLYMARKET_CLOB  = "https://clob.polymarket.com"

KALSHI_API_KEY = os.getenv("KALSHI_API_KEY", "")

# ── Category Mappings ─────────────────────────────────────────────────────────

# Kalshi category slugs → our unified categories
KALSHI_CATEGORY_MAP = {
    "sports":    ["Sports", "Basketball", "Football", "Baseball", "Hockey", "Soccer", "Tennis", "Golf"],
    "politics":  ["Politics", "Elections", "Government", "Congress", "President"],
    "finance":   ["Economics", "Finance", "Financials", "Fed", "Macro", "Economy"],
    "crypto":    ["Crypto", "Cryptocurrency", "Bitcoin", "Ethereum"],
    "world":     ["Geopolitics", "International", "Climate", "Environment", "Science", "Technology"],
}

# Polymarket category keywords → our unified categories
POLY_CATEGORY_MAP = {
    "sports":   ["nba", "nfl", "mlb", "nhl", "ncaa", "soccer", "tennis", "golf", "sports", "basketball", "football"],
    "politics": ["election", "president", "congress", "senate", "political", "vote", "trump", "biden", "harris", "party"],
    "finance":  ["fed", "cpi", "gdp", "interest rate", "inflation", "recession", "payroll", "economic", "stock"],
    "crypto":   ["bitcoin", "btc", "ethereum", "eth", "crypto", "defi", "solana", "coinbase"],
    "world":    ["war", "conflict", "climate", "geopolitical", "international", "nuclear", "ai", "artificial intelligence", "technology"],
}


# ── Data Models ───────────────────────────────────────────────────────────────

@dataclass
class Market:
    platform:   str
    ticker:     str
    title:      str
    category:   str          # unified: sports | politics | finance | crypto | other
    mid_price:  float | None
    best_bid:   float | None
    best_ask:   float | None
    volume:     float | None
    volume_24h: float | None = None

@dataclass
class MatchedPair:
    kalshi:      Market
    polymarket:  Market
    spread:      float
    match_score: float

@dataclass
class PlatformVolume:
    kalshi_total_volume:     float = 0.0
    polymarket_total_volume: float = 0.0
    kalshi_market_count:     int   = 0
    polymarket_market_count: int   = 0
    kalshi_by_category:      dict  = field(default_factory=dict)
    polymarket_by_category:  dict  = field(default_factory=dict)


# ── Category Detection ────────────────────────────────────────────────────────

def detect_category_kalshi(raw_category: str, title: str) -> str:
    """Map Kalshi raw category to unified category."""
    raw = (raw_category or "").strip()
    for unified, variants in KALSHI_CATEGORY_MAP.items():
        if any(v.lower() in raw.lower() for v in variants):
            return unified
    # Fallback: keyword scan on title
    title_lower = title.lower()
    for unified, keywords in POLY_CATEGORY_MAP.items():
        if any(k in title_lower for k in keywords):
            return unified
    return "other"


def detect_category_poly(title: str, tags: list) -> str:
    """Map Polymarket title/tags to unified category."""
    text = (title + " " + " ".join(tags or [])).lower()
    for unified, keywords in POLY_CATEGORY_MAP.items():
        if any(k in text for k in keywords):
            return unified
    return "other"



def _parse_kalshi_market(m: dict, title: str, unified_cat: str) -> Market:
    """
    Parse a single Kalshi V2 market dict into a Market object.
    V2 API changes:
      - Prices: yes_bid_dollars / yes_ask_dollars (string floats, already in dollars 0-1)
      - Volume: volume_fp / volume_24h_fp (string floats)
    """
    # Prices — V2 uses _dollars suffix, already decimal (not cents)
    yes_bid_raw = m.get("yes_bid_dollars") or m.get("yes_bid")
    yes_ask_raw = m.get("yes_ask_dollars") or m.get("yes_ask")

    def to_price(val) -> float | None:
        if val is None:
            return None
        try:
            f = float(val)
            # If old API returned cents (>1.0), convert; V2 already decimal
            return f / 100 if f > 1.0 else f
        except (ValueError, TypeError):
            return None

    bid = to_price(yes_bid_raw)
    ask = to_price(yes_ask_raw)
    mid = None
    if bid is not None and ask is not None:
        mid = (bid + ask) / 2
    elif bid is not None:
        mid = bid
    elif ask is not None:
        mid = ask

    # Volume — V2 uses volume_fp / volume_24h_fp (string floats)
    def to_vol(val) -> float:
        if val is None:
            return 0.0
        try:
            return float(val)
        except (ValueError, TypeError):
            return 0.0

    volume     = to_vol(m.get("volume_fp") or m.get("volume"))
    volume_24h = to_vol(m.get("volume_24h_fp") or m.get("volume_24h"))

    return Market(
        platform   = "kalshi",
        ticker     = m.get("ticker", ""),
        title      = title,
        category   = unified_cat,
        mid_price  = mid,
        best_bid   = bid,
        best_ask   = ask,
        volume     = volume,
        volume_24h = volume_24h,
    )

# ── Kalshi Fetcher ────────────────────────────────────────────────────────────

def fetch_kalshi_markets(limit: int = 200, category_filter: str = None) -> list[Market]:
    """
    Fetch active markets from Kalshi using the EVENTS endpoint.
    Events give clean human-readable titles + YES binary markets per event.
    Falls back to /markets endpoint if events endpoint fails.
    """
    markets = []
    headers = {}
    if KALSHI_API_KEY:
        headers["Authorization"] = f"Bearer {KALSHI_API_KEY}"

    # ── Try events endpoint first (cleaner titles) ────────────────────────────
    try:
        params = {"limit": limit, "status": "open"}
        resp = requests.get(
            f"{KALSHI_BASE}/events",
            headers=headers, params=params, timeout=10
        )
        resp.raise_for_status()
        data = resp.json()

        for event in data.get("events", []):
            event_title = event.get("title", "")
            raw_cat     = event.get("category", "")
            unified_cat = detect_category_kalshi(raw_cat, event_title)

            if category_filter and category_filter != "all" and unified_cat != category_filter:
                continue

            # Each event has one or more markets (YES/NO binary contracts)
            for m in event.get("markets", []):
                # Use event title + market subtitle for clean full title
                subtitle = m.get("subtitle", "") or m.get("title", "")
                if subtitle and subtitle.lower() not in event_title.lower():
                    title = f"{event_title} — {subtitle}"
                else:
                    title = event_title

                markets.append(_parse_kalshi_market(m, title, unified_cat))

        if markets:
            print(f"[Kalshi] Fetched {len(markets)} markets via events endpoint")
            # Debug: show volume fields from first raw event
            if data.get("events") and data["events"][0].get("markets"):
                market = data["events"][0]["markets"][0]
                print(f"  Yes Price: ${market.get('yes_bid_dollars')} | Volume: {market.get('volume_fp')}")
            return markets

    except Exception as e:
        print(f"[Kalshi] Events endpoint failed: {e}, trying markets endpoint...")

    # ── Fallback: /markets endpoint ───────────────────────────────────────────
    try:
        params = {
            "limit":  limit,
            "status": "open",
        }
        resp = requests.get(
            f"{KALSHI_BASE}/markets",
            headers=headers, params=params, timeout=15
        )
        resp.raise_for_status()
        data = resp.json()

        # Sort by volume_fp descending to get highest-volume markets first
        all_markets = data.get("markets", [])
        if all_markets:
            market = all_markets[0]
            print(f"  Yes Price: ${market.get('yes_bid_dollars')} | Volume: {market.get('volume_fp')}")
        all_markets.sort(
            key=lambda x: float(x.get("volume_fp") or x.get("volume") or 0),
            reverse=True
        )

        for m in all_markets:
            # Clean title: prefer title, then subtitle, strip "yes/no" prefixes
            title = m.get("title", "") or m.get("subtitle", "") or ""
            title = title.strip()

            # Strip leading "yes " / "no " tokens that appear in some Kalshi responses
            if title.lower().startswith("yes "):
                title = title[4:]
            elif title.lower().startswith("no "):
                title = title[3:]

            raw_cat     = m.get("category", "")
            unified_cat = detect_category_kalshi(raw_cat, title)

            if category_filter and category_filter != "all" and unified_cat != category_filter:
                continue

            markets.append(_parse_kalshi_market(m, title, unified_cat))

        print(f"[Kalshi] Fetched {len(markets)} markets via markets endpoint")

    except Exception as e:
        print(f"[Kalshi] Error: {e}")

    return markets


# ── Polymarket Fetcher ────────────────────────────────────────────────────────

def fetch_polymarket_markets(limit: int = 200, category_filter: str = None) -> list[Market]:
    """Fetch active markets from Polymarket Gamma API (richer metadata)."""
    markets = []
    try:
        params = {
            "active":    "true",
            "closed":    "false",
            "limit":     limit,
            "order":     "volume24hr",
            "ascending": "false",
        }

        resp = requests.get(f"{POLYMARKET_GAMMA}/markets", params=params, timeout=15)
        resp.raise_for_status()
        raw = resp.json()
        items = raw if isinstance(raw, list) else raw.get("data", [])

        # Sort by 24h volume descending (API may not always honor order param)
        items.sort(key=lambda x: float(x.get("volume24hr") or x.get("volume") or 0), reverse=True)

        for m in items:
            title   = m.get("question", "") or m.get("title", "")
            tags    = [t.get("label", "") for t in m.get("tags", [])]
            unified_cat = detect_category_poly(title, tags)

            if category_filter and category_filter != "all" and unified_cat != category_filter:
                continue

            # Best YES token price
            outcomes     = m.get("outcomes", "[]")
            outcome_prices = m.get("outcomePrices", "[]")
            mid = None
            try:
                import json
                if isinstance(outcomes, str):
                    outcomes = json.loads(outcomes)
                if isinstance(outcome_prices, str):
                    outcome_prices = json.loads(outcome_prices)
                if outcomes and outcome_prices:
                    yes_idx = next((i for i, o in enumerate(outcomes) if str(o).upper() == "YES"), 0)
                    mid = float(outcome_prices[yes_idx])
            except Exception:
                pass

            volume     = float(m.get("volume", 0) or 0)
            volume_24h = float(m.get("volume24hr", 0) or 0)

            markets.append(Market(
                platform   = "polymarket",
                ticker     = m.get("conditionId", m.get("id", "")),
                title      = title,
                category   = unified_cat,
                mid_price  = mid,
                best_bid   = mid - 0.01 if mid else None,
                best_ask   = mid + 0.01 if mid else None,
                volume     = volume,
                volume_24h = volume_24h,
            ))

    except Exception as e:
        print(f"[Polymarket] Error: {e}")

    return markets


# ── Volume Aggregator ─────────────────────────────────────────────────────────

def fetch_platform_volume(
    kalshi_markets:  list[Market],
    poly_markets:    list[Market],
) -> PlatformVolume:
    """
    Aggregate volume metrics across both platforms and by category.
    Uses 24h volume where available, falls back to total volume.
    """
    def vol(m: Market) -> float:
        return (m.volume_24h or 0) if (m.volume_24h and m.volume_24h > 0) else (m.volume or 0)

    pv = PlatformVolume()

    pv.kalshi_total_volume     = sum(vol(m) for m in kalshi_markets)
    pv.polymarket_total_volume = sum(vol(m) for m in poly_markets)
    pv.kalshi_market_count     = len(kalshi_markets)
    pv.polymarket_market_count = len(poly_markets)

    for cat in ["sports", "politics", "finance", "crypto", "other"]:
        k_vol = sum(vol(m) for m in kalshi_markets if m.category == cat)
        p_vol = sum(vol(m) for m in poly_markets   if m.category == cat)
        k_cnt = sum(1 for m in kalshi_markets if m.category == cat)
        p_cnt = sum(1 for m in poly_markets   if m.category == cat)
        pv.kalshi_by_category[cat]     = {"volume": k_vol, "count": k_cnt}
        pv.polymarket_by_category[cat] = {"volume": p_vol, "count": p_cnt}

    return pv


# ── Full Snapshot ─────────────────────────────────────────────────────────────

def fetch_snapshot(category_filter: str = "all", limit: int = 200):
    """
    Fetch full snapshot: markets from both platforms + volume metrics.

    Returns
    -------
    tuple: (kalshi_markets, poly_markets, platform_volume)
    """
    kalshi = fetch_kalshi_markets(limit=limit, category_filter=category_filter)
    poly   = fetch_polymarket_markets(limit=limit, category_filter=category_filter)
    volume = fetch_platform_volume(kalshi, poly)
    return kalshi, poly, volume


# ── Quick Test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Fetching snapshot (all categories)...")
    k, p, vol = fetch_snapshot(category_filter="all", limit=50)
    print(f"Kalshi: {len(k)} markets | Polymarket: {len(p)} markets")
    print(f"Kalshi total volume: ${vol.kalshi_total_volume:,.0f}")
    print(f"Polymarket total volume: ${vol.polymarket_total_volume:,.0f}")
    print("\nBy category:")
    for cat in ["sports", "politics", "finance", "crypto", "other"]:
        kc = vol.kalshi_by_category.get(cat, {})
        pc = vol.polymarket_by_category.get(cat, {})
        print(f"  {cat}: K={kc.get('count',0)} mkts/${kc.get('volume',0):,.0f} | P={pc.get('count',0)} mkts/${pc.get('volume',0):,.0f}")
