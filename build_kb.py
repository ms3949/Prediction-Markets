"""
build_kb.py
Builds the SQLite knowledge base for the Prediction Markets Research Assistant.
Sources:
  1. Wolfers & Zitzewitz (2006) NBER paper — academic theory & empirics
  2. Platform fee/liquidity facts
  3. Spread interpretation framework
  4. Category-level behavior (sports, politics, finance, crypto)
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "knowledge_base.db")

# ── Schema ────────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    title    TEXT NOT NULL,
    content  TEXT NOT NULL,
    category TEXT NOT NULL
);
"""

# ── Knowledge Records ─────────────────────────────────────────────────────────

DOCUMENTS = [

    # ── ACADEMIC THEORY (Wolfers & Zitzewitz 2006) ────────────────────────────

    {
        "title": "Prediction Markets as Information Aggregators",
        "category": "academic_theory",
        "content": (
            "Prediction markets aggregate dispersed private information into a single price signal. "
            "Under log utility, the prediction market price equals the mean belief among traders "
            "(Wolfers & Zitzewitz 2005). Markets designed around information aggregation yield prices "
            "interpretable as market-aggregated probabilities of future events. "
            "The Efficient Market Hypothesis underpins prediction market theory: in equilibrium, "
            "prices summarize all available private information (Grossman 1976)."
        ),
    },
    {
        "title": "Prediction Market Efficiency and Random Walk Prices",
        "category": "academic_theory",
        "content": (
            "Empirical evidence shows prediction market prices follow a random walk in most cases. "
            "Simple betting strategies based on publicly available information yield no profit. "
            "These markets meet the standard definition of weak-form efficiency. "
            "Prices respond rapidly to new information — in the 2004 US election, prices moved "
            "in lockstep with S&P 500 futures within minutes of leaked exit poll data (Snowberg, "
            "Wolfers & Zitzewitz 2006). Cross-exchange arbitrage opportunities are fleeting and "
            "involve only small potential profits — the law of one price roughly holds."
        ),
    },
    {
        "title": "Favorite-Longshot Bias in Prediction Markets",
        "category": "academic_theory",
        "content": (
            "A documented pathology: prediction markets tend to over-price low probability events. "
            "This 'favorite-longshot bias' means contracts priced below 0.10 are systematically "
            "overvalued relative to their true probability. Conversely, high-probability events "
            "(contracts priced above 0.80) tend to be underpriced. "
            "Implication for cross-exchange analysis: spreads on extreme-probability markets "
            "may reflect this bias rather than genuine information asymmetry. "
            "Analysts should apply caution when interpreting spreads on contracts priced < 0.10 or > 0.90."
        ),
    },
    {
        "title": "Manipulation Resistance in Prediction Markets",
        "category": "academic_theory",
        "content": (
            "Attempts to manipulate prediction market prices typically fail. "
            "Camerer (1998) attempted to manipulate pari-mutuel horse racing markets — no discernible effect. "
            "Rhode & Strumpf (2005) documented failed manipulation attempts on Iowa Electronic Markets. "
            "Hanson & Oprea (2005) showed manipulation attempts actually increase information market accuracy "
            "by raising rewards for informed trading. "
            "Implication: sudden large spread widening is more likely to reflect genuine information "
            "asymmetry than market manipulation, especially on liquid markets."
        ),
    },
    {
        "title": "Prediction Market Forecasting Accuracy vs Benchmarks",
        "category": "academic_theory",
        "content": (
            "Prediction markets consistently outperform expert opinion and surveys. "
            "Iowa Electronic Markets average absolute error: 1.6pp vs Gallup Poll's 1.9pp over 13 elections. "
            "Hollywood Stock Exchange outperformed expert opinions on box office and Oscar predictions. "
            "NFL prediction markets outperformed all but a handful of 2000 self-professed experts. "
            "HP internal prediction market outperformed internal sales forecast experts (Chen & Plott 2002). "
            "This outperformance is strongest over long horizons — polls show excess volatility vs markets."
        ),
    },
    {
        "title": "Contract Types and What Prices Reveal",
        "category": "academic_theory",
        "content": (
            "Binary option contracts (pay $1 if event occurs) reveal the market probability p(x). "
            "Index futures contracts reveal the mean expected value E[x]. "
            "Spread betting contracts reveal the median outcome. "
            "Kalshi and Polymarket primarily use binary YES/NO contracts — prices should be interpreted "
            "as market-aggregated probabilities, not certainties. "
            "A YES price of 0.62 means the market assigns 62% probability to that outcome. "
            "Cross-exchange spread = difference in these probability assessments between platforms."
        ),
    },

    # ── PLATFORM FEES ─────────────────────────────────────────────────────────

    {
        "title": "Kalshi Fee Structure",
        "category": "platform_fees",
        "content": (
            "Kalshi charges fees on net winnings (profit), not notional trade size. "
            "Fee tiers: Tier 1 (<$100K monthly volume): 7% on net winnings. "
            "Tier 2 ($100K-$1M monthly): 5% on net winnings. "
            "Tier 3 (>$1M monthly): 3% on net winnings. "
            "Fees only apply to winning trades — losing trades keep full stake. "
            "Minimum trade: $1. Max position: $25,000 retail. "
            "Effective break-even spread needed: ~4.7% at Tier 1, ~2.9% at Tier 3. "
            "Kalshi is CFTC-regulated as a Designated Contract Market (DCM)."
        ),
    },
    {
        "title": "Polymarket Fee Structure",
        "category": "platform_fees",
        "content": (
            "Polymarket charges a taker fee of 2% on notional trade value (not just profit). "
            "Maker fee: 0% — liquidity providers pay nothing. "
            "Gas fees: $0.01-$0.05 per transaction on Polygon blockchain. "
            "All positions denominated in USDC stablecoin. "
            "The taker fee on notional makes Polymarket more expensive for small spread trades. "
            "Example: Buy YES at 0.60 for $60 notional → fee = $1.20 → effective fee on profit = 3%. "
            "Break-even spread: approximately 2% on notional. "
            "Decentralized — unregulated in most jurisdictions, geo-blocked for US users officially."
        ),
    },
    {
        "title": "Cross-Exchange Arbitrage Fee Math",
        "category": "platform_fees",
        "content": (
            "To execute cross-exchange arbitrage, trader takes positions on BOTH platforms simultaneously. "
            "Combined fee drag: Kalshi fee on winnings + Polymarket taker fee on notional. "
            "Minimum spread required to break even: approximately 8-12% for most retail traders. "
            "Spreads < 5%: NOT exploitable after fees for retail. "
            "Spreads 5-10%: MARGINAL — requires Kalshi Tier 2+ and large position. "
            "Spreads > 10%: POTENTIALLY exploitable — warrants serious analysis. "
            "Spreads > 15%: STRONG signal — likely structural dislocation. "
            "Additional friction: Kalshi ACH withdrawal takes 3-5 business days. "
            "Polymarket USDC withdrawal is near-instant but requires fiat conversion steps."
        ),
    },

    # ── SPREAD INTERPRETATION ─────────────────────────────────────────────────

    {
        "title": "Spread Size Interpretation Framework",
        "category": "spread_analysis",
        "content": (
            "Spread = abs(Kalshi_mid - Polymarket_mid), expressed as percentage points. "
            "TIGHT (0-3%): Normal market condition for liquid events. Not exploitable after fees. Noise. "
            "MODERATE (3-7%): Mildly unusual. May indicate slower info incorporation on one platform. Monitor. "
            "SIGNIFICANT (7-12%): Structurally interesting. Likely stale prices, info asymmetry, or liquidity crunch. "
            "LARGE (12-20%): Strong inefficiency signal. Could indicate data error or market suspension — verify. "
            "EXTREME (>20%): Almost always a data problem or API error. Treat as suspect until verified. "
            "Spreads lasting >5 minutes are more significant than brief spikes (<60 seconds). "
            "Persistent spreads >10 minutes warrant serious attention."
        ),
    },
    {
        "title": "Exploitability Scoring Framework",
        "category": "spread_analysis",
        "content": (
            "Score each arbitrage opportunity on four dimensions (1-5 scale): "
            "1. Spread Size: <3%=1, 3-7%=2, 7-12%=3, 12-20%=4, >20%=5. "
            "2. Persistence: <1min=1, 1-5min=2, 5-15min=3, 15-60min=4, >1hr=5. "
            "3. Liquidity (order book depth): Very thin=1, Thin=2, Moderate=3, Good=4, Deep=5. "
            "4. Data Confidence: Suspect=1, Uncertain=2, Likely valid=3, Confident=4, Verified=5. "
            "Total Score Interpretation: 4-8=Not exploitable, 9-13=Monitor, 14-17=High conviction, 18-20=Act. "
            "Favorite-longshot bias: apply extra skepticism to markets priced below 0.10 or above 0.90."
        ),
    },

    # ── LIQUIDITY BY PLATFORM ─────────────────────────────────────────────────

    {
        "title": "Kalshi Liquidity Profile",
        "category": "liquidity",
        "content": (
            "Kalshi is a centralized CLOB (central limit order book) exchange, CFTC-regulated, US-based. "
            "Typical bid-ask spread: 2-5% on major sports markets, 5-15% on niche markets. "
            "Order book depth: generally shallow beyond best bid/ask (<$5,000 at second level). "
            "Fill certainty: high for <$500 orders, uncertain for >$5,000. "
            "Peak liquidity: 30 min before game tip-off or major political announcements. "
            "Kalshi's own market makers tighten spreads during high-activity periods. "
            "Sudden spread widening on Kalshi = early signal of incoming information. "
            "Low liquidity: overnight hours (12am-7am ET), far-from-resolution contracts (>30 days out)."
        ),
    },
    {
        "title": "Polymarket Liquidity Profile",
        "category": "liquidity",
        "content": (
            "Polymarket is decentralized, blockchain-based (Polygon network), global user base. "
            "Typical bid-ask spread: 1-4% on major markets — often tighter than Kalshi. "
            "Order book depth: highly variable — major political markets can be very deep (>$100,000). "
            "Fill certainty: dependent on on-chain confirmation (1-5 min delay). "
            "24/7 global access — less time-zone dependent than Kalshi. "
            "Liquidity can be added by ANY user as LP (liquidity provider). "
            "Large whale positions can significantly move prices on smaller markets. "
            "On-chain transparency: large orders are publicly visible before execution. "
            "Smart money from crypto-native traders often incorporates information faster than Kalshi."
        ),
    },

    # ── CATEGORY-LEVEL BEHAVIOR ───────────────────────────────────────────────

    {
        "title": "Sports Markets Behavior and Characteristics",
        "category": "category_sports",
        "content": (
            "Sports markets are typically the most liquid on both platforms. "
            "NBA, NFL, NCAAB are most active. NFL has highest liquidity of all sports. "
            "Kalshi typical depth: $500-$5,000 per side on major NBA games, up to $20,000 on NFL. "
            "Polymarket typical depth: $2,000-$20,000 NBA, $5,000-$50,000 NFL primetime. "
            "Spreads typically tight (1-4%) for major games under normal conditions. "
            "Spreads widen significantly on: injury news, weather delays, lineup changes. "
            "Best arbitrage window: 2-6 hours before game time (post-lineup, pre-sharp action). "
            "March Madness NCAAB games are 10x more liquid than regular season. "
            "Prediction markets outperform expert NFL picks (Servan-Schreiber et al. 2004). "
            "Sports markets show fastest price response to new information of any category."
        ),
    },
    {
        "title": "Politics Markets Behavior and Characteristics",
        "category": "category_politics",
        "content": (
            "Political markets are historically the most studied prediction markets (Iowa Electronic Markets). "
            "Average absolute forecasting error: 1.6pp vs Gallup Poll's 1.9pp over 13 US elections. "
            "Polymarket significantly deeper than Kalshi for presidential/congressional races. "
            "Kalshi more liquid for local/state-level events. "
            "Political spreads can persist for hours or days — less efficient than sports. "
            "Higher volatility, less predictable spreads — platforms have different user bases with different political priors. "
            "Partisan information asymmetry is real: crypto-native Polymarket users vs US retail Kalshi users. "
            "This user base difference is the primary driver of persistent political market spreads. "
            "Snowberg, Wolfers & Zitzewitz (2006): partisan impacts of elections visible in prediction market prices."
        ),
    },
    {
        "title": "Finance and Economic Markets Behavior",
        "category": "category_finance",
        "content": (
            "Economic prediction markets (Fed decisions, CPI, GDP) show rapid price convergence at data release. "
            "Gürkaynak & Wolfers (2005): economic derivatives market forecasts encompass survey-based forecasts. "
            "Behavioral anomalies in survey forecasts are NOT evident in market-based forecasts. "
            "Pre-release spreads can be significant as different platforms incorporate analyst views at different speeds. "
            "Post-release spreads collapse within minutes as both platforms update. "
            "Finance markets on Polymarket tend to attract more sophisticated traders — prices often lead Kalshi. "
            "Best opportunity window: 30-60 minutes before major economic data release (CPI, Fed, payrolls)."
        ),
    },
    {
        "title": "Crypto Markets Behavior and Characteristics",
        "category": "category_crypto",
        "content": (
            "Crypto prediction markets (Bitcoin price, ETH moves) are heavily traded on Polymarket by native users. "
            "Kalshi has growing crypto market coverage but typically lags Polymarket in liquidity here. "
            "Polymarket crypto markets often reflect on-chain sentiment before Kalshi prices update. "
            "This creates persistent directional spreads when crypto markets are trending. "
            "Spreads in crypto markets tend to be larger and more persistent than sports (3-8% typical). "
            "High volatility of underlying asset makes spread persistence harder to exploit. "
            "Best opportunity: during major crypto events (ETF approvals, halving, regulatory news). "
            "Favorite-longshot bias particularly pronounced in extreme crypto prediction contracts."
        ),
    },
]

# ── Build Database ────────────────────────────────────────────────────────────

def build():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.executescript(SCHEMA)

    # Clear existing
    cur.execute("DELETE FROM documents")

    for doc in DOCUMENTS:
        cur.execute(
            "INSERT INTO documents (title, content, category) VALUES (?, ?, ?)",
            (doc["title"], doc["content"], doc["category"])
        )

    conn.commit()
    n = cur.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    conn.close()
    print(f"✅ Built knowledge base: {n} documents in {DB_PATH}")

    # Show categories
    conn = sqlite3.connect(DB_PATH)
    cats = conn.execute("SELECT category, COUNT(*) FROM documents GROUP BY category").fetchall()
    conn.close()
    for cat, count in cats:
        print(f"   {cat}: {count} docs")

if __name__ == "__main__":
    build()
