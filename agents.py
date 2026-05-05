"""
agents.py - 4-Agent Pipeline + Drilldown
Agent 1: Collector  — top 200 by volume from each platform
Agent 2: Classifier — classifies each title into sector via OpenAI
Agent 3: Matcher    — OpenAI cross-references all titles, finds same-event pairs
Agent 4: Strategist — academic-grounded sector verdicts
Agent 4b: Drilldown — user picks sector, finds best specific trade
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
# Top 200 by volume from each platform — titles + volume only
# ══════════════════════════════════════════════════════════════════════════════

def run_collector(kalshi_markets: list, poly_markets: list) -> dict:
    """Agent 1: sort by volume, return top markets from each platform."""
    print("\n[Agent 1: Collector] Collecting top markets by volume...")

    k_sorted = sorted(kalshi_markets, key=lambda m: float(m.get("volume") or 0), reverse=True)
    p_sorted = sorted(poly_markets,   key=lambda m: float(m.get("volume") or 0), reverse=True)

    k_total = sum(float(m.get("volume") or 0) for m in kalshi_markets)
    p_total = sum(float(m.get("volume") or 0) for m in poly_markets)

    top_k = [
        {"id": f"K{i}", "title": m.get("title",""), "volume": float(m.get("volume") or 0),
         "mid": m.get("mid_price"), "ticker": m.get("ticker","")}
        for i, m in enumerate(k_sorted[:50]) if m.get("title")
    ]
    top_p = [
        {"id": f"P{i}", "title": m.get("title",""), "volume": float(m.get("volume") or 0),
         "mid": m.get("mid_price"), "ticker": m.get("ticker","")}
        for i, m in enumerate(p_sorted[:50]) if m.get("title")
    ]

    print(f"  ✅ Kalshi top {len(top_k)} | Polymarket top {len(top_p)}")
    print(f"  Volume — Kalshi: {k_total:,.0f} contracts | Polymarket: {p_total:,.0f} USDC")

    return {
        "kalshi_total_volume":     round(k_total),
        "polymarket_total_volume": round(p_total),
        "kalshi_market_count":     len(kalshi_markets),
        "polymarket_market_count": len(poly_markets),
        "volume_leader":           "polymarket" if p_total > k_total else "kalshi",
        "top_kalshi":              top_k,
        "top_polymarket":          top_p,
    }


# ══════════════════════════════════════════════════════════════════════════════
# AGENT 2: CLASSIFIER
# Classifies every market title into a sector via OpenAI
# ══════════════════════════════════════════════════════════════════════════════

CLASSIFIER_SYSTEM = """
You are a prediction market sector classifier.

Classify EACH market into exactly one sector:
- sports:   any game, match, player stat, team result (NBA, NFL, MLB, NHL, NCAA, soccer, golf, tennis, MMA)
- politics:  elections, candidates, approval ratings, government policy, congress, president, legislation
- finance:   Fed decisions, interest rates, CPI, GDP, inflation, recession, jobs data, stock indices
- crypto:    Bitcoin, Ethereum, any token price or event, DeFi, blockchain milestones
- world:     geopolitics, wars, international events, climate, science, AI milestones, tech events
- other:     anything that doesn't clearly fit above

Return ONLY valid JSON, no preamble:
{
  "classified": [
    {"id": "K0", "title": "...", "platform": "kalshi", "sector": "sports", "volume": 0.0, "mid": 0.0}
  ]
}

Every market gets exactly one sector. Be decisive.
"""

def run_classifier(collector_output: dict) -> dict:
    """Agent 2: classify all market titles into sectors via OpenAI."""
    print("\n[Agent 2: Classifier] Classifying markets into sectors...")

    top_k = collector_output.get("top_kalshi", [])
    top_p = collector_output.get("top_polymarket", [])

    markets = (
        [{"id": m["id"], "title": m["title"], "platform": "kalshi",     "volume": m["volume"], "mid": m.get("mid")} for m in top_k] +
        [{"id": m["id"], "title": m["title"], "platform": "polymarket", "volume": m["volume"], "mid": m.get("mid")} for m in top_p]
    )

    raw = _llm(CLASSIFIER_SYSTEM,
               f"Classify these {len(markets)} prediction market titles:\n{json.dumps(markets, indent=2)}",
               temperature=0.1)

    try:
        result     = _parse_json(raw)
        classified = result.get("classified", [])

        # Group by sector for downstream use
        by_sector = {}
        for m in classified:
            sec = m.get("sector", "other")
            by_sector.setdefault(sec, {"kalshi": [], "polymarket": []})
            if m.get("platform") == "kalshi":
                by_sector[sec]["kalshi"].append(m)
            else:
                by_sector[sec]["polymarket"].append(m)

        print(f"  ✅ {len(classified)} markets → {len(by_sector)} sectors")
        for s, d in by_sector.items():
            print(f"     {s}: K={len(d['kalshi'])} P={len(d['polymarket'])}")

        return {
            "classified":     classified,
            "by_sector":      by_sector,
            "total_markets":  len(classified),
        }

    except Exception as e:
        print(f"  ⚠ Classifier parse error: {e}")
        return {"classified": [], "by_sector": {}, "total_markets": 0, "parse_error": str(e)}


# ══════════════════════════════════════════════════════════════════════════════
# AGENT 3: MATCHER  ← NEW AGENT
# OpenAI cross-references ALL titles across both platforms.
# Uses full language understanding to match:
#   - Team abbreviations:  "LAD" = "LA Dodgers" = "Los Angeles Dodgers"
#   - City shorthands:     "LA" = "Los Angeles", "KC" = "Kansas City"
#   - Question vs statement: "Will Lakers win?" = "Lakers win tonight"
#   - Alternate phrasings: "Trump approval > 50%" = "Trump job approval above fifty percent"
# ══════════════════════════════════════════════════════════════════════════════

MATCHER_SYSTEM = """
You are a prediction market cross-platform matching specialist.

You will receive two lists of market titles — one from Kalshi, one from Polymarket.
Your job: find every pair of markets that refer to THE SAME underlying real-world event.

MATCHING RULES (strict):
1. Same underlying event: same teams/players/entities, same game/date/timeframe, same outcome question
2. Use your knowledge of sports teams, political figures, and financial events to resolve:
   - Abbreviations: "LAD" = "LA Dodgers", "KC" = "Kansas City Chiefs", "NYY" = "New York Yankees"
   - City names: "LA" = "Los Angeles", "SF" = "San Francisco", "NO" = "New Orleans"  
   - Common shorthands: "Philly" = "Philadelphia", "Vegas" = "Las Vegas"
   - Question forms: "Will X win?" = "X wins" = "X to win"
3. DO NOT match:
   - Player props vs team results (single player stat ≠ team game outcome)
   - Single game vs season futures (tonight's game ≠ championship winner)
   - Different sports, different leagues, different time windows
   - Markets that share only a city name but different events

For each valid pair, compute the spread:
  spread = abs(kalshi_mid - polymarket_mid)

Return ONLY valid JSON:
{
  "matched_pairs": [
    {
      "kalshi_id": "K0",
      "polymarket_id": "P3",
      "kalshi_title": "...",
      "polymarket_title": "...",
      "kalshi_mid": 0.0,
      "polymarket_mid": 0.0,
      "spread": 0.0,
      "spread_pct": "X.X%",
      "sector": "sports",
      "match_reason": "Same NBA game: Lakers vs Celtics on same date",
      "confidence": "high|medium|low"
    }
  ],
  "unmatched_kalshi":    ["K1", "K2"],
  "unmatched_polymarket": ["P1", "P4"],
  "matcher_notes": "Brief note on what you found overall"
}

Only include pairs where you are at least medium confidence they are the same event.
Exclude low-confidence matches entirely — false positives are worse than missed matches.
"""

def run_matcher(collector_output: dict, classifier_output: dict) -> dict:
    """
    Agent 3: OpenAI cross-references ALL market titles across both platforms
    to find same-event pairs using full language understanding.
    """
    print("\n[Agent 3: Matcher] Cross-referencing all markets for same-event pairs...")

    top_k = collector_output.get("top_kalshi", [])
    top_p = collector_output.get("top_polymarket", [])

    # Build clean lists for the matcher — include mid prices for spread calculation
    kalshi_list = [
        {"id": m["id"], "title": m["title"], "mid": m.get("mid"), "volume": m["volume"]}
        for m in top_k if m.get("title")
    ]
    poly_list = [
        {"id": m["id"], "title": m["title"], "mid": m.get("mid"), "volume": m["volume"]}
        for m in top_p if m.get("title")
    ]

    # Send to OpenAI for intelligent cross-referencing
    user_msg = f"""
Cross-reference these markets across both platforms. Find every same-event pair.

KALSHI MARKETS ({len(kalshi_list)} total):
{json.dumps(kalshi_list, indent=2)}

POLYMARKET MARKETS ({len(poly_list)} total):
{json.dumps(poly_list, indent=2)}

Use your knowledge of team names, abbreviations, and market conventions to match them.
"""
    raw = _llm(MATCHER_SYSTEM, user_msg, temperature=0.1)

    try:
        result = _parse_json(raw)
        pairs  = result.get("matched_pairs", [])

        # Validate: remove pairs with missing mid prices or extreme spreads
        valid_pairs = []
        for p in pairs:
            k_mid = float(p.get("kalshi_mid") or 0)
            pm_mid = float(p.get("polymarket_mid") or 0)
            # Skip if either price is missing or invalid
            if k_mid <= 0.01 or k_mid >= 0.99 or pm_mid <= 0.01 or pm_mid >= 0.99:
                continue
            # Skip suspiciously large spreads (likely data error)
            spread = abs(k_mid - pm_mid)
            if spread > 0.45:
                continue
            # Recalculate spread in case LLM got it wrong
            p["spread"]     = round(spread, 3)
            p["spread_pct"] = f"{spread*100:.1f}%"
            p["same_event_verified"] = True
            valid_pairs.append(p)

        # Enrich with classifier sector if not already set
        classified_by_id = {
            m["id"]: m.get("sector", "other")
            for m in classifier_output.get("classified", [])
        }
        for p in valid_pairs:
            if not p.get("sector"):
                k_id = p.get("kalshi_id","")
                p["sector"] = classified_by_id.get(k_id, "other")

        # Group pairs by sector for strategist
        pairs_by_sector = {}
        for p in valid_pairs:
            sec = p.get("sector", "other")
            pairs_by_sector.setdefault(sec, []).append(p)

        # Merge with classifier's by_sector structure
        merged_sectors = {}
        classifier_sectors = classifier_output.get("by_sector", {})
        all_sectors = set(list(classifier_sectors.keys()) + list(pairs_by_sector.keys()))

        for sec in all_sectors:
            merged_sectors[sec] = {
                "kalshi":       classifier_sectors.get(sec, {}).get("kalshi", []),
                "polymarket":   classifier_sectors.get(sec, {}).get("polymarket", []),
                "matched_pairs": pairs_by_sector.get(sec, []),
            }

        print(f"  ✅ Found {len(valid_pairs)} verified same-event pairs across {len(pairs_by_sector)} sectors")
        for sec, ps in pairs_by_sector.items():
            for p in ps:
                print(f"     {sec}: {p['kalshi_title'][:40]} ↔ {p['polymarket_title'][:40]} spread={p['spread_pct']}")

        return {
            "matched_pairs":   valid_pairs,
            "pairs_by_sector": pairs_by_sector,
            "sectors":         merged_sectors,
            "total_pairs":     len(valid_pairs),
            "matcher_notes":   result.get("matcher_notes", ""),
            "unmatched_kalshi":    result.get("unmatched_kalshi", []),
            "unmatched_polymarket": result.get("unmatched_polymarket", []),
        }

    except Exception as e:
        print(f"  ⚠ Matcher parse error: {e}")
        # Fallback: return classifier sectors with empty pairs
        return {
            "matched_pairs":   [],
            "pairs_by_sector": {},
            "sectors":         classifier_output.get("by_sector", {}),
            "total_pairs":     0,
            "parse_error":     str(e),
        }


# ══════════════════════════════════════════════════════════════════════════════
# AGENT 5: CLOSEST MATCHER
# Runs if no exact matches are found. Finds closest non-identical contracts.
# ══════════════════════════════════════════════════════════════════════════════

CLOSEST_MATCHER_SYSTEM = """
You are a prediction market cross-platform correlation specialist.

You will receive two lists of UNMATCHED market titles — one from Kalshi, one from Polymarket.
Your job: find pairs of markets that are NOT the identical event, but are the CLOSEST related contracts across the two platforms (e.g., similar games in the same sport, related political events where correlation or arbitrage might work).

MATCHING RULES:
1. Do not match completely unrelated events (e.g., NBA game vs NFL game).
2. Look for high correlation: e.g. "Lakers to win" vs "Lakers to score over 100 pts", or "Trump to win PA" vs "Trump to win MI".
3. Calculate the spread: spread = abs(kalshi_mid - polymarket_mid)
4. Set same_event_verified to false.

Return ONLY valid JSON:
{
  "closest_pairs": [
    {
      "kalshi_id": "K0",
      "polymarket_id": "P3",
      "kalshi_title": "...",
      "polymarket_title": "...",
      "kalshi_mid": 0.0,
      "polymarket_mid": 0.0,
      "spread": 0.0,
      "spread_pct": "X.X%",
      "sector": "sports",
      "match_reason": "Highly correlated: both involve Lakers game outcome",
      "same_event_verified": false
    }
  ],
  "matcher_notes": "Brief note on what you found"
}
"""

def run_closest_matcher(matcher_output: dict, classifier_output: dict) -> dict:
    """Agent 5: Finds closest correlated pairs when exact matches fail."""
    print("\n[Agent 5: Closest Matcher] Finding closest non-exact matches...")

    un_k = matcher_output.get("unmatched_kalshi", [])
    un_p = matcher_output.get("unmatched_polymarket", [])
    
    if not un_k or not un_p:
        print("  ⚠ Not enough unmatched markets to compare.")
        return {"closest_pairs": []}

    k_markets = []
    p_markets = []
    
    for m in classifier_output.get("classified", []):
        if m.get("id") in un_k:
            k_markets.append(m)
        elif m.get("id") in un_p:
            p_markets.append(m)

    user_msg = f"""
Find the closest correlated pairs across these unmatched markets.

KALSHI UNMATCHED:
{json.dumps([{"id": m["id"], "title": m["title"], "mid": m.get("mid")} for m in k_markets], indent=2)}

POLYMARKET UNMATCHED:
{json.dumps([{"id": m["id"], "title": m["title"], "mid": m.get("mid")} for m in p_markets], indent=2)}
"""
    raw = _llm(CLOSEST_MATCHER_SYSTEM, user_msg, temperature=0.3)

    try:
        result = _parse_json(raw)
        pairs = result.get("closest_pairs", [])
        
        valid_pairs = []
        for p in pairs:
            k_mid = float(p.get("kalshi_mid") or 0)
            pm_mid = float(p.get("polymarket_mid") or 0)
            if k_mid <= 0.01 or k_mid >= 0.99 or pm_mid <= 0.01 or pm_mid >= 0.99:
                continue
            spread = abs(k_mid - pm_mid)
            p["spread"] = round(spread, 3)
            p["spread_pct"] = f"{spread*100:.1f}%"
            p["same_event_verified"] = False
            
            k_id = p.get("kalshi_id", "")
            sec = next((m.get("sector", "other") for m in k_markets if m["id"] == k_id), "other")
            p["sector"] = sec
            valid_pairs.append(p)
            
        print(f"  ✅ Found {len(valid_pairs)} closest non-exact pairs")
        return {"closest_pairs": valid_pairs, "matcher_notes": result.get("matcher_notes", "")}
        
    except Exception as e:
        print(f"  ⚠ Closest Matcher parse error: {e}")
        return {"closest_pairs": [], "parse_error": str(e)}

# ══════════════════════════════════════════════════════════════════════════════
# AGENT 4: STRATEGIST
# Academic-grounded sector verdicts using matched pairs from Agent 3
# ══════════════════════════════════════════════════════════════════════════════

STRATEGIST_SYSTEM = """
You are a prediction markets strategist with deep knowledge of academic research.

You receive sector data including same-event matched pairs found by the Matcher agent.
Using Wolfers & Zitzewitz (2006), analyze each sector and recommend where to bet.

Key principles:
- Weak-form efficiency: simple public-info strategies yield no profit
- Law of one price roughly holds — spreads are fleeting
- Favorite-longshot bias: avoid contracts < 0.10 or > 0.90
- Kalshi (US retail) vs Polymarket (crypto-native global) user bases create structural disagreements
- Sports markets: fastest information incorporation
- Political markets: most persistent spreads due to different user priors
- Need >8-12% spread to break even after fees

For each sector with markets, provide analysis.

Return ONLY valid JSON:
{
  "sector_analysis": {
    "sports": {
      "verdict": "HIGH OPPORTUNITY|MODERATE|LOW OPPORTUNITY|AVOID",
      "num_kalshi": 0,
      "num_poly": 0,
      "num_pairs": 0,
      "avg_spread_pct": "X.X%",
      "summary": "2-3 sentence assessment",
      "recommendation": "Specific actionable thought",
      "academic_note": "One sentence citing the paper",
      "key_risk": "Biggest risk"
    }
  },
  "best_sector": "sports|politics|finance|crypto|world|other",
  "best_sector_reason": "Why this sector is best right now",
  "overall_verdict": "ACTIVE|QUIET|MIXED",
  "session_narrative": "3-4 sentence summary grounded in Wolfers & Zitzewitz"
}

Only include sectors that have markets. Skip empty sectors.
"""

def run_strategist(matcher_output: dict) -> dict:
    """Agent 4: academic-grounded sector verdicts using verified pairs."""
    print("\n[Agent 4: Strategist] Analyzing sectors with academic grounding...")

    rag_context = retrieve(
        "prediction market efficiency spread exploitable fees favorite longshot liquidity",
        top_n=5
    )

    sectors = matcher_output.get("sectors", {})

    sector_summary = {}
    for sec, data in sectors.items():
        pairs    = data.get("matched_pairs", [])
        avg_sp   = sum(p.get("spread",0) for p in pairs) / len(pairs) if pairs else 0
        sector_summary[sec] = {
            "num_kalshi":    len(data.get("kalshi",[])),
            "num_poly":      len(data.get("polymarket",[])),
            "num_pairs":     len(pairs),
            "avg_spread":    f"{avg_sp*100:.1f}%",
            "sample_pairs":  [
                {"k": p["kalshi_title"], "p": p["polymarket_title"],
                 "spread": p["spread_pct"], "confidence": p.get("confidence","—")}
                for p in pairs[:3]
            ],
            "sample_k": [m["title"] for m in data.get("kalshi",[])[:3]],
            "sample_p": [m["title"] for m in data.get("polymarket",[])[:3]],
        }

    raw = _llm(STRATEGIST_SYSTEM, f"""
Academic context (Wolfers & Zitzewitz 2006):
{rag_context}

Sector data with verified matched pairs:
{json.dumps(sector_summary, indent=2)}

Analyze each sector. Where are the real opportunities?
""", temperature=0.4)

    try:
        result = _parse_json(raw)
        print(f"  ✅ Best sector: {result.get('best_sector','—')} | {result.get('overall_verdict','—')}")
        return result
    except Exception as e:
        print(f"  ⚠ Strategist parse error: {e}")
        return {
            "sector_analysis": {},
            "best_sector": "—",
            "overall_verdict": "UNKNOWN",
            "session_narrative": str(e),
            "parse_error": str(e),
        }


# ══════════════════════════════════════════════════════════════════════════════
# AGENT 4b: DRILLDOWN
# User picks sector → find best specific trade using verified pairs
# ══════════════════════════════════════════════════════════════════════════════

DRILLDOWN_SYSTEM = """
You are a strict prediction markets arbitrage analyst.

CORE RULE — SAME EVENT ONLY (OR CLOSEST MATCH):
Only recommend trades where BOTH sides refer to the IDENTICAL underlying event, UNLESS they are marked with "same_event_verified": false.
If they are NOT same-event verified, treat them as a correlation/closest-match trade, not a strict arbitrage. Explain the correlation and why it might be a good trade despite not being identical.
The matched_pairs you receive have already been processed by the Matcher.

ARBITRAGE VALIDITY:
- If same-event: Need >8-12% spread to break even after fees (Kalshi 7% on winnings, Polymarket 2% taker on notional)
- If correlated (not same-event): Explain the correlation risk clearly.
- Avoid contracts < 0.10 or > 0.90 (favorite-longshot bias per Wolfers & Zitzewitz 2006)
- High-confidence Matcher pairs are more reliable than medium-confidence ones

If no valid pairs exist with exploitable spread/correlation, return null for top_trade
and explain clearly in no_arb_reason. Never fabricate a trade.

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
    "action": "BUY YES on [platform] at [price]. SELL YES on [platform] at [price].",
    "rationale": "2-3 sentences. Confirm if same event or correlated. Explain why spread is real.",
    "key_risk": "Biggest execution or correlation risk",
    "matcher_confidence": "high|medium"
  },
  "runner_up": {
    "kalshi_title": "...",
    "polymarket_title": "...",
    "spread_pct": "...",
    "action": "..."
  },
  "no_arb_reason": "If no valid trade, explain here. Otherwise leave empty.",
  "sector_conditions": "1-2 sentences on overall sector state",
  "academic_warning": "Relevant Wolfers & Zitzewitz warning"
}
"""

def run_drilldown(sector: str, sector_data: dict) -> dict:
    """Agent 4b: deep dive into user-selected sector, find best trade."""
    print(f"\n[Agent 4b: Drilldown] Analyzing {sector} sector trades...")

    rag_context = retrieve(
        f"spread exploitable fees favorite longshot {sector} liquidity platform",
        top_n=3, category=sector
    )

    pairs  = sector_data.get("matched_pairs", [])
    k_mkts = sector_data.get("kalshi", [])
    p_mkts = sector_data.get("polymarket", [])

    raw = _llm(DRILLDOWN_SYSTEM, f"""
Academic context:
{rag_context}

Sector: {sector.upper()}

Same-event matched pairs from Matcher agent ({len(pairs)} total):
{json.dumps(pairs, indent=2)}

Kalshi-only markets (no Polymarket pair found):
{json.dumps([m.get("title","") for m in k_mkts[:10]], indent=2)}

Polymarket-only markets (no Kalshi pair found):
{json.dumps([m.get("title","") for m in p_mkts[:10]], indent=2)}

Find the best trade in {sector}. Only recommend from matched_pairs — those are verified same-event.
""", temperature=0.3)

    try:
        return _parse_json(raw)
    except Exception as e:
        return {"parse_error": str(e), "raw": raw}


# ══════════════════════════════════════════════════════════════════════════════
# MAIN ORCHESTRATOR
# Agent 1 → Agent 2 → Agent 3 → Agent 4
# ══════════════════════════════════════════════════════════════════════════════

def run_pipeline(kalshi_markets: list, poly_markets: list, progress_callback=None) -> dict:
    """
    Runs the full 4-agent pipeline sequentially.
    Agent 1 → Collector
    Agent 2 → Classifier
    Agent 3 → Matcher (OpenAI cross-referencing)
    Agent 4 → Strategist
    """
    results = {
        "collector":  None,
        "classifier": None,
        "matcher":    None,
        "closest_matcher": None,
        "strategist": None,
        "error":      None,
    }
    total = 5

    try:
        if progress_callback:
            progress_callback(1, total, "🔍 Agent 1: Collecting top markets by volume...")
        results["collector"] = run_collector(kalshi_markets, poly_markets)

        if progress_callback:
            progress_callback(2, total, "📋 Agent 2: Classifying markets into sectors...")
        results["classifier"] = run_classifier(results["collector"])

        if progress_callback:
            progress_callback(3, total, "🔗 Agent 3: Cross-referencing platforms for same-event pairs...")
        results["matcher"] = run_matcher(results["collector"], results["classifier"])

        if results["matcher"].get("total_pairs", 0) == 0:
            if progress_callback:
                progress_callback(4, total, "🔍 Agent 5: No exact matches. Finding closest pairs...")
            
            closest_res = run_closest_matcher(results["matcher"], results["classifier"])
            closest_pairs = closest_res.get("closest_pairs", [])
            results["closest_matcher"] = closest_res
            
            for p in closest_pairs:
                sec = p.get("sector", "other")
                if sec not in results["matcher"]["sectors"]:
                    results["matcher"]["sectors"][sec] = {"kalshi": [], "polymarket": [], "matched_pairs": []}
                results["matcher"]["sectors"][sec].setdefault("matched_pairs", []).append(p)
                results["matcher"].setdefault("pairs_by_sector", {}).setdefault(sec, []).append(p)
                results["matcher"].setdefault("matched_pairs", []).append(p)
            
            results["matcher"]["total_pairs"] += len(closest_pairs)
        else:
            if progress_callback:
                progress_callback(4, total, "⏭️ Agent 5: Exact matches found, skipping closest matches...")

        if progress_callback:
            progress_callback(5, total, "⚖️ Agent 4: Generating academic-grounded verdicts...")
        results["strategist"] = run_strategist(results["matcher"])

    except Exception as e:
        results["error"] = str(e)
        print(f"[Pipeline Error] {e}")

    return results
