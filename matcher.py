"""
matcher.py - Cross-exchange market matching
Matches markets across Kalshi and Polymarket using keyword token overlap.
"""

import re
from data_fetcher import Market, MatchedPair

# ── Stopwords ─────────────────────────────────────────────────────────────────

STOPWORDS = {
    "will", "the", "win", "beat", "vs", "versus", "at", "by", "to", "a",
    "an", "in", "of", "be", "do", "or", "and", "for", "on", "is", "are",
    "who", "what", "which", "than", "their", "this", "that", "from", "over",
    "cover", "against", "game", "match", "series", "tonight", "today",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december",
    "nba", "nfl", "ncaab", "mlb", "nhl",
    "q", "!", ".", ",", "-", "'", "\"", "(", ")", "/",
}

# ── Team & Entity Aliases ─────────────────────────────────────────────────────

ALIASES = {
    # NBA
    "lakers":        ["lakers", "los angeles lakers", "la lakers"],
    "celtics":       ["celtics", "boston celtics", "boston"],
    "warriors":      ["warriors", "golden state warriors", "golden state", "gsw"],
    "nuggets":       ["nuggets", "denver nuggets", "denver"],
    "bucks":         ["bucks", "milwaukee bucks", "milwaukee"],
    "heat":          ["heat", "miami heat", "miami"],
    "knicks":        ["knicks", "new york knicks", "new york", "nyk"],
    "suns":          ["suns", "phoenix suns", "phoenix"],
    "clippers":      ["clippers", "los angeles clippers", "la clippers"],
    "bulls":         ["bulls", "chicago bulls", "chicago"],
    "nets":          ["nets", "brooklyn nets", "brooklyn"],
    "76ers":         ["76ers", "sixers", "philadelphia 76ers", "philadelphia", "philly"],
    "hawks":         ["hawks", "atlanta hawks", "atlanta"],
    "hornets":       ["hornets", "charlotte hornets", "charlotte"],
    "pacers":        ["pacers", "indiana pacers", "indiana"],
    "cavaliers":     ["cavaliers", "cleveland cavaliers", "cleveland", "cavs"],
    "pistons":       ["pistons", "detroit pistons", "detroit"],
    "raptors":       ["raptors", "toronto raptors", "toronto"],
    "magic":         ["magic", "orlando magic", "orlando"],
    "wizards":       ["wizards", "washington wizards", "washington"],
    "thunder":       ["thunder", "oklahoma city thunder", "oklahoma city", "okc"],
    "blazers":       ["trail blazers", "blazers", "portland trail blazers", "portland"],
    "jazz":          ["jazz", "utah jazz", "utah"],
    "kings":         ["kings", "sacramento kings", "sacramento"],
    "spurs":         ["spurs", "san antonio spurs", "san antonio"],
    "mavericks":     ["mavericks", "dallas mavericks", "dallas", "mavs"],
    "grizzlies":     ["grizzlies", "memphis grizzlies", "memphis"],
    "pelicans":      ["pelicans", "new orleans pelicans", "new orleans"],
    "rockets":       ["rockets", "houston rockets", "houston"],
    "timberwolves":  ["timberwolves", "minnesota timberwolves", "minnesota", "wolves"],
    # NHL
    "panthers":      ["panthers", "florida panthers", "fla panthers"],
    "lightning":     ["lightning", "tampa bay lightning", "tb lightning", "tampa"],
    "rangers":       ["rangers", "new york rangers", "ny rangers"],
    "bruins":        ["bruins", "boston bruins"],
    "maple leafs":   ["maple leafs", "toronto maple leafs", "leafs"],
    "oilers":        ["oilers", "edmonton oilers", "edmonton"],
    "avalanche":     ["avalanche", "colorado avalanche", "colorado"],
    "golden knights":["golden knights", "vegas golden knights", "vegas"],
    "canucks":       ["canucks", "vancouver canucks", "vancouver"],
    # MLB
    "yankees":       ["yankees", "new york yankees", "ny yankees"],
    "dodgers":       ["dodgers", "los angeles dodgers", "la dodgers"],
    "braves":        ["braves", "atlanta braves"],
    "guardians":     ["guardians", "cleveland guardians", "cleveland"],
    "astros":        ["astros", "houston astros"],
    "mets":          ["mets", "new york mets"],
    "cubs":          ["cubs", "chicago cubs"],
    "cardinals":     ["cardinals", "st louis cardinals", "st. louis"],
    "phillies":      ["phillies", "philadelphia phillies"],
    "pirates":       ["pirates", "pittsburgh pirates", "pittsburgh"],
    "eagles":        ["eagles", "philadelphia eagles"],
    "cowboys":       ["cowboys", "dallas cowboys"],
    "patriots":      ["patriots", "new england patriots", "new england"],
    "packers":       ["packers", "green bay packers", "green bay"],
    "49ers":         ["49ers", "san francisco 49ers", "san francisco"],
    "ravens":        ["ravens", "baltimore ravens", "baltimore"],
    "bills":         ["bills", "buffalo bills", "buffalo"],
    "bengals":       ["bengals", "cincinnati bengals", "cincinnati"],
    "rams":          ["rams", "los angeles rams"],
    # Crypto / Finance
    "bitcoin":       ["bitcoin", "btc"],
    "ethereum":      ["ethereum", "eth"],
    "fed":           ["fed", "federal reserve", "fomc"],
    # Politics
    "trump":         ["trump", "donald trump"],
    "biden":         ["biden", "joe biden"],
    "harris":        ["harris", "kamala harris"],
}

# Build reverse lookup: surface_form → canonical
_SURFACE_TO_CANONICAL = {}
for canonical, surfaces in ALIASES.items():
    for surface in surfaces:
        _SURFACE_TO_CANONICAL[surface.lower()] = canonical


# ── Tokenization ──────────────────────────────────────────────────────────────

def tokenize(text: str) -> set[str]:
    """
    Extract meaningful keyword tokens from a market title.
    Strips noise words, resolves aliases to canonical team/entity names.
    """
    text = text.lower()
    text = re.sub(r'[^\w\s]', ' ', text)
    words = text.split()

    tokens = set()
    i = 0
    while i < len(words):
        matched = False
        # Try longest phrase match first (3-gram → 2-gram → unigram)
        for n in [3, 2]:
            if i + n <= len(words):
                phrase = " ".join(words[i:i+n])
                if phrase in _SURFACE_TO_CANONICAL:
                    tokens.add(_SURFACE_TO_CANONICAL[phrase])
                    i += n
                    matched = True
                    break
        if not matched:
            word = words[i]
            if word in _SURFACE_TO_CANONICAL:
                tokens.add(_SURFACE_TO_CANONICAL[word])
            elif word not in STOPWORDS and len(word) > 1:
                tokens.add(word)
            i += 1

    return tokens


# ── Scoring ───────────────────────────────────────────────────────────────────

def token_overlap_score(a: str, b: str) -> float:
    """
    Score keyword overlap between two market titles.
    Uses average of Jaccard similarity and coverage ratio.
    Returns 0.0 - 1.0.
    """
    tokens_a = tokenize(a)
    tokens_b = tokenize(b)

    if not tokens_a or not tokens_b:
        return 0.0

    intersection = tokens_a & tokens_b
    if not intersection:
        return 0.0

    union = tokens_a | tokens_b
    jaccard = len(intersection) / len(union)
    coverage = len(intersection) / min(len(tokens_a), len(tokens_b))

    return round((jaccard + coverage) / 2, 4)


# ── Matching Engine ───────────────────────────────────────────────────────────

def match_markets(
    kalshi_markets: list[Market],
    polymarket_markets: list[Market],
    threshold: float = 0.12
) -> list[MatchedPair]:
    """
    Match Kalshi markets to Polymarket markets using keyword token overlap.
    Lower threshold than fuzzy matching since token overlap is more precise.
    """
    pairs = []
    used_poly = set()

    for km in kalshi_markets:
        if km.mid_price is None:
            continue

        best_score = 0.0
        best_poly = None

        for i, pm in enumerate(polymarket_markets):
            if i in used_poly:
                continue
            if pm.mid_price is None:
                continue

            score = token_overlap_score(km.title, pm.title)

            if score > best_score:
                best_score = score
                best_poly = (i, pm)

        if best_poly and best_score >= threshold:
            idx, pm = best_poly
            used_poly.add(idx)
            spread = abs(km.mid_price - pm.mid_price)
            pairs.append(MatchedPair(
                kalshi=km,
                polymarket=pm,
                spread=round(spread, 4),
                match_score=round(best_score, 3)
            ))

    pairs.sort(key=lambda x: x.spread, reverse=True)
    return pairs


def summarize_pairs(pairs: list[MatchedPair]) -> list[dict]:
    """Convert MatchedPair list to dicts for agent consumption."""
    return [
        {
            "kalshi_title": p.kalshi.title,
            "polymarket_title": p.polymarket.title,
            "kalshi_mid": round(p.kalshi.mid_price, 4) if p.kalshi.mid_price else None,
            "polymarket_mid": round(p.polymarket.mid_price, 4) if p.polymarket.mid_price else None,
            "spread": p.spread,
            "spread_pct": f"{p.spread * 100:.2f}%",
            "match_score": p.match_score,
            "kalshi_volume": p.kalshi.volume,
            "polymarket_volume": p.polymarket.volume,
            "shared_tokens": list(tokenize(p.kalshi.title) & tokenize(p.polymarket.title)),
        }
        for p in pairs
    ]


# ── Quick Test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== Tokenizer Test ===")
    tests = [
        "Will the Lakers beat the Celtics tonight?",
        "Los Angeles Lakers vs Boston Celtics",
        "Chiefs vs Eagles - Super Bowl",
        "Will Kansas City Chiefs win?",
        "Bitcoin above 100k by end of 2025?",
        "BTC to exceed 100000",
    ]
    for t in tests:
        print(f"  '{t}' → {tokenize(t)}")

    print("\n=== Live Match Test ===")
    from data_fetcher import fetch_market_snapshot
    k, p = fetch_market_snapshot()
    print(f"Fetched {len(k)} Kalshi, {len(p)} Polymarket markets")
    pairs = match_markets(k, p)
    print(f"Matched {len(pairs)} pairs\n")
    for pair in pairs[:10]:
        print(f"  K: {pair.kalshi.title[:65]}")
        print(f"  P: {pair.polymarket.title[:65]}")
        print(f"  Tokens: {list(tokenize(pair.kalshi.title) & tokenize(pair.polymarket.title))}")
        print(f"  Score: {pair.match_score} | Spread: {pair.spread*100:.2f}%")
        print()
