"""
agents.py - Clean 3-Agent Pipeline
Agent 1: Collector  — top 200 by volume from each platform (titles + counts only)
Agent 2: Classifier — sends titles to OpenAI, gets sector classification back
Agent 3: Strategist — analyzes each sector using academic paper, recommends best sector
Agent 3b: Drilldown — user picks sector, runs deep analysis on that sector
"""

import os
import json
from openai import OpenAI
from rag import retrieve

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL = "gpt-4o-mini"

def _llm(system: str, user: str, temperature: float = 0.3) -> str:
    resp = client.chat.completions.create(
        model=MODEL,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ]
    )
    return resp.choices[0].message.content.strip()

def _parse_json(raw: str):
    clean = raw.replace("```json", "").replace("```", "").strip()
    return json.loads(clean)


# ══════════════════════════════════════════════════════════════════════════════
# AGENT 1: COLLECTOR
# Fetches top 200 by volume from each platform
# Returns: titles, volume counts, basic stats — no dollar conversion
# ══════════════════════════════════════════════════════════════════════════════

def run_collector(kalshi_markets: list, poly_markets: list) -> dict:
    """
    Agent 1: Collects top markets by volume from each platform.
    Just counts and titles — no dollar math.
    """
    print("\n[Agent 1: Collector] Fetching top markets by volume...")

    # Sort by volume descending
    k_sorted = sorted(kalshi_markets, key=lambda m: float(m.get("volume") or 0), reverse=True)
    p_sorted = sorted(poly_markets,   key=lambda m: float(m.get("volume") or 0), reverse=True)

    # Total volume counts
    k_total = sum(float(m.get("volume") or 0) for m in kalshi_markets)
    p_total = sum(float(m.get("volume") or 0) for m in poly_markets)

    # Top 20 from each with just what we need
    top_k = [
        {
            "title":   m.get("title", ""),
            "volume":  float(m.get("volume") or 0),
            "mid":     m.get("mid_price"),
            "ticker":  m.get("ticker", ""),
        }
        for m in k_sorted[:20] if m.get("title")
    ]

    top_p = [
        {
            "title":   m.get("title", ""),
            "volume":  float(m.get("volume") or 0),
            "mid":     m.get("mid_price"),
            "ticker":  m.get("ticker", ""),
        }
        for m in p_sorted[:20] if m.get("title")
    ]

    result = {
        "kalshi_total_volume":     round(k_total),
        "polymarket_total_volume": round(p_total),
        "kalshi_market_count":     len(kalshi_markets),
        "polymarket_market_count": len(poly_markets),
        "volume_leader":           "polymarket" if p_total > k_total else "kalshi",
        "top_kalshi":              top_k,
        "top_polymarket":          top_p,
    }

    print(f"  ✅ Kalshi: {len(top_k)} top markets | Polymarket: {len(top_p)} top markets")
    print(f"  Kalshi volume: {k_total:,.0f} contracts | Polymarket volume: {p_total:,.0f} USDC")
    return result


# ══════════════════════════════════════════════════════════════════════════════
# AGENT 2: CLASSIFIER
# Sends all market titles to OpenAI → gets sector classification back
# Sectors: sports | politics | finance | crypto | world | other
# ══════════════════════════════════════════════════════════════════════════════

CLASSIFIER_SYSTEM = """
You are a prediction market classifier.

You will receive a list of market titles from Kalshi and Polymarket.
Classify EACH market into exactly one of these sectors:
- sports: any game, match, player, team, league (NBA, NFL, MLB, NHL, soccer, golf, tennis)
- politics: elections, candidates, approval ratings, government, policy, congress, president
- finance: Fed decisions, interest rates, CPI, GDP, inflation, recession, stocks, economic data
- crypto: Bitcoin, Ethereum, any cryptocurrency price, DeFi, blockchain events
- world: geopolitical events, wars, international news, climate, AI/technology milestones
- other: anything that doesn't fit above

Return ONLY valid JSON — no preamble, no markdown:
{
  "classified": [
    {"title": "exact title here", "platform": "kalshi", "sector": "sports", "volume": 0.0, "mid": 0.0},
    ...
  ]
}

Be decisive. Every market gets exactly one sector.
"""

def run_classifier(collector_output: dict) -> dict:
    """
    Agent 2: Sends all market titles to OpenAI for sector classification.
    Simple, clean, one LLM call.
    """
    print("\n[Agent 2: Classifier] Classifying markets into sectors...")

    top_k = collector_output.get("top_kalshi", [])
    top_p = collector_output.get("top_polymarket", [])

    # Build flat list of markets to classify
    markets_to_classify = (
        [{"title": m["title"], "platform": "kalshi",     "volume": m["volume"], "mid": m.get("mid")} for m in top_k] +
        [{"title": m["title"], "platform": "polymarket", "volume": m["volume"], "mid": m.get("mid")} for m in top_p]
    )

    user_msg = f"""
Classify each of these {len(markets_to_classify)} prediction market titles into their sector.

Markets:
{json.dumps(markets_to_classify, indent=2)}
"""
    raw = _llm(CLASSIFIER_SYSTEM, user_msg, temperature=0.1)

    try:
        result = _parse_json(raw)
        classified = result.get("classified", [])

        # Group by sector
        sectors = {}
        for m in classified:
            sec = m.get("sector", "other")
            if sec not in sectors:
                sectors[sec] = {"kalshi": [], "polymarket": []}
            platform = m.get("platform", "other")
            if platform == "kalshi":
                sectors[sec]["kalshi"].append(m)
            else:
                sectors[sec]["polymarket"].append(m)

        # Find cross-platform matches (same event on both)
        for sec, data in sectors.items():
            k_titles = data["kalshi"]
            p_titles = data["polymarket"]
            matches = []
            for km in k_titles:
                for pm in p_titles:
                    # Simple keyword overlap check
                    k_words = set(km["title"].lower().split())
                    p_words = set(pm["title"].lower().split())
                    stopwords = {"will","the","a","an","in","of","to","be","vs","at","by","or","and","is","for","on"}
                    k_clean = k_words - stopwords
                    p_clean = p_words - stopwords
                    if len(k_clean) > 0 and len(p_clean) > 0:
                        overlap = len(k_clean & p_clean) / min(len(k_clean), len(p_clean))
                        if overlap >= 0.3:
                            k_mid = float(km.get("mid") or 0.5)
                            p_mid = float(pm.get("mid") or 0.5)
                            spread = abs(k_mid - p_mid)
                            matches.append({
                                "kalshi_title":     km["title"],
                                "polymarket_title": pm["title"],
                                "kalshi_mid":       round(k_mid, 3),
                                "polymarket_mid":   round(p_mid, 3),
                                "spread":           round(spread, 3),
                                "spread_pct":       f"{spread*100:.1f}%",
                                "kalshi_volume":    km.get("volume", 0),
                                "polymarket_volume": pm.get("volume", 0),
                            })
            data["matched_pairs"] = matches

        print(f"  ✅ Classified {len(classified)} markets into {len(sectors)} sectors")
        for sec, data in sectors.items():
            print(f"     {sec}: {len(data['kalshi'])} Kalshi | {len(data['polymarket'])} Poly | {len(data.get('matched_pairs',[]))} pairs")

        return {
            "sectors":        sectors,
            "total_markets":  len(classified),
            "all_classified": classified,
        }

    except Exception as e:
        print(f"  ⚠ Parse error: {e}")
        return {"sectors": {}, "total_markets": 0, "parse_error": str(e)}


# ══════════════════════════════════════════════════════════════════════════════
# AGENT 3: STRATEGIST
# Analyzes each sector using the academic paper
# Gives thoughts on which sectors make sense to bet in
# ══════════════════════════════════════════════════════════════════════════════

STRATEGIST_SYSTEM = """
You are a prediction markets strategist with deep knowledge of academic research.

You have classified market data grouped by sector. Using the academic context provided
(Wolfers & Zitzewitz 2006), analyze each sector and give your thoughts on where it
makes sense to bet right now.

Key academic principles to apply:
- Prediction markets are weak-form efficient — simple strategies based on public info yield no profit
- The law of one price roughly holds — cross-platform spreads are fleeting
- Favorite-longshot bias: avoid contracts priced below 0.10 or above 0.90
- Markets with more liquidity aggregate information better
- Political markets: Polymarket users vs Kalshi users have different information sets
- Sports markets: respond fastest to new information (injuries, lineups)

For each sector that has markets, give:
1. Your assessment of current conditions
2. Whether the spread between platforms suggests opportunity
3. A clear recommendation

Return ONLY valid JSON:
{
  "sector_analysis": {
    "sports": {
      "verdict": "HIGH OPPORTUNITY|MODERATE|LOW OPPORTUNITY|AVOID",
      "num_kalshi": 0,
      "num_poly": 0,
      "num_pairs": 0,
      "avg_spread_pct": "X.X%",
      "summary": "2-3 sentences on this sector right now",
      "recommendation": "Specific actionable thought",
      "academic_note": "One sentence citing the paper",
      "key_risk": "Biggest risk in this sector"
    }
  },
  "best_sector": "sports|politics|finance|crypto|world|other",
  "best_sector_reason": "Why this is the best opportunity right now in 1-2 sentences",
  "overall_verdict": "ACTIVE|QUIET|MIXED",
  "session_narrative": "3-4 sentence overall summary grounded in Wolfers & Zitzewitz"
}

Only include sectors that actually have markets. Skip empty sectors.
"""

def run_strategist(classifier_output: dict) -> dict:
    """
    Agent 3: Analyzes each sector using the academic paper.
    """
    print("\n[Agent 3: Strategist] Analyzing sectors with academic grounding...")

    rag_context = retrieve(
        "prediction market efficiency spread exploitable favorite longshot bias platform liquidity",
        top_n=5
    )

    sectors = classifier_output.get("sectors", {})

    # Build sector summary for the LLM
    sector_summary = {}
    for sec, data in sectors.items():
        pairs = data.get("matched_pairs", [])
        avg_spread = (
            sum(p.get("spread", 0) for p in pairs) / len(pairs)
            if pairs else 0
        )
        sector_summary[sec] = {
            "num_kalshi":    len(data.get("kalshi", [])),
            "num_poly":      len(data.get("polymarket", [])),
            "num_pairs":     len(pairs),
            "avg_spread":    f"{avg_spread*100:.1f}%",
            "sample_pairs":  pairs[:3],  # send top 3 pairs as examples
            "sample_kalshi": [m["title"] for m in data.get("kalshi", [])[:3]],
            "sample_poly":   [m["title"] for m in data.get("polymarket", [])[:3]],
        }

    user_msg = f"""
Academic context (Wolfers & Zitzewitz 2006):
{rag_context}

Current market data by sector:
{json.dumps(sector_summary, indent=2)}

Analyze each sector and give your strategic thoughts on where to bet.
"""
    raw = _llm(STRATEGIST_SYSTEM, user_msg, temperature=0.4)

    try:
        result = _parse_json(raw)
        best = result.get("best_sector", "—")
        print(f"  ✅ Best sector: {best} | Verdict: {result.get('overall_verdict','—')}")
        return result
    except Exception as e:
        print(f"  ⚠ Parse error: {e}")
        return {
            "sector_analysis": {},
            "best_sector": "—",
            "overall_verdict": "UNKNOWN",
            "session_narrative": raw,
            "parse_error": str(e),
        }


# ══════════════════════════════════════════════════════════════════════════════
# AGENT 3b: SECTOR DRILLDOWN
# User picks a sector → deep analysis of best specific trade in that sector
# ══════════════════════════════════════════════════════════════════════════════

DRILLDOWN_SYSTEM = """
You are a prediction markets trade analyst.

A user has selected a specific sector to investigate. You have all the markets
in that sector across Kalshi and Polymarket.

Your job: find the BEST specific trade in this sector and explain exactly what to do.

Use these principles from Wolfers & Zitzewitz (2006):
- Spreads > 8-12% are needed to break even after fees (Kalshi 7%, Polymarket 2% taker)
- Favorite-longshot bias: contracts < 0.10 or > 0.90 are systematically mispriced
- Look for persistent spreads — brief spikes are likely API latency, not real opportunity
- Platform user bases differ: crypto-native Polymarket traders vs US retail Kalshi users

Return ONLY valid JSON:
{
  "top_trade": {
    "kalshi_title": "...",
    "polymarket_title": "...",
    "kalshi_mid": 0.0,
    "polymarket_mid": 0.0,
    "spread_pct": "X.X%",
    "fee_exploitable": true,
    "platform_to_buy": "kalshi|polymarket",
    "action": "Exact instruction e.g. BUY YES on Kalshi at 0.54, SHORT YES on Polymarket at 0.63",
    "rationale": "2-3 sentences explaining why this trade makes sense right now",
    "key_risk": "Single biggest risk"
  },
  "runner_up": {
    "kalshi_title": "...",
    "spread_pct": "...",
    "action": "..."
  },
  "sector_conditions": "1-2 sentences on the overall state of this sector",
  "academic_warning": "Any relevant warning from Wolfers & Zitzewitz that applies here"
}

If there are no matched pairs, recommend the most interesting single-platform market instead.
"""

def run_drilldown(sector: str, sector_data: dict) -> dict:
    """Agent 3b: deep dive into user-selected sector."""
    print(f"\n[Agent 3b: Drilldown] Deep analysis of {sector} sector...")

    rag_context = retrieve(
        f"spread exploitable fees favorite longshot {sector} liquidity platform",
        top_n=3, category=sector
    )

    pairs   = sector_data.get("matched_pairs", [])
    k_mkts  = sector_data.get("kalshi", [])
    p_mkts  = sector_data.get("polymarket", [])

    user_msg = f"""
Academic context:
{rag_context}

Sector: {sector.upper()}

Matched cross-platform pairs ({len(pairs)} total):
{json.dumps(pairs, indent=2)}

Kalshi-only markets in this sector:
{json.dumps([m["title"] for m in k_mkts], indent=2)}

Polymarket-only markets in this sector:
{json.dumps([m["title"] for m in p_mkts], indent=2)}

Find the best specific trade in {sector} right now.
"""
    raw = _llm(DRILLDOWN_SYSTEM, user_msg, temperature=0.3)

    try:
        return _parse_json(raw)
    except Exception as e:
        return {"parse_error": str(e), "raw": raw}


# ══════════════════════════════════════════════════════════════════════════════
# MAIN ORCHESTRATOR
# ══════════════════════════════════════════════════════════════════════════════

def run_pipeline(kalshi_markets: list, poly_markets: list, progress_callback=None) -> dict:
    """Runs Agent 1 → Agent 2 → Agent 3 sequentially."""
    results = {"collector": None, "classifier": None, "strategist": None, "error": None}
    total = 3

    try:
        if progress_callback: progress_callback(1, total, "🔍 Agent 1: Collecting top markets by volume...")
        results["collector"] = run_collector(kalshi_markets, poly_markets)

        if progress_callback: progress_callback(2, total, "📊 Agent 2: Classifying markets into sectors...")
        results["classifier"] = run_classifier(results["collector"])

        if progress_callback: progress_callback(3, total, "⚖️ Agent 3: Analyzing sectors with academic paper...")
        results["strategist"] = run_strategist(results["classifier"])

    except Exception as e:
        results["error"] = str(e)
        print(f"[Pipeline Error] {e}")

    return results
