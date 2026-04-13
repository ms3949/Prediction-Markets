# 📊 Prediction Markets Research Assistant

A live AI-powered research platform that connects to Kalshi and Polymarket, deploys a 3-agent pipeline to classify and analyze cross-exchange markets, and recommends specific trades grounded in academic literature.

**Live App**: [prediction-markets-app.streamlit.app](https://prediction-markets-app.streamlit.app)

---

## What It Does

Prediction markets on Kalshi and Polymarket attract structurally different user bases — Kalshi serves US retail traders in a CFTC-regulated environment, while Polymarket draws a global crypto-native audience. These populations often disagree on the probability of the same event, creating persistent price spreads that represent genuine information asymmetry.

This app surfaces those spreads, classifies them by sector, evaluates their exploitability using fee structures and efficiency theory from Wolfers & Zitzewitz (2006), and recommends the single best trade available in the current session.

One button. Three agents. Under 60 seconds.

---

## Agent Pipeline

```
Kalshi V2 API          Polymarket Gamma API
     │                        │
     └──────────┬─────────────┘
                ▼
        ┌───────────────┐
        │  Agent 1      │  Collector
        │               │  Sort by volume, select top 20 each platform
        └──────┬────────┘
               │  titles + volume stats
               ▼
        ┌───────────────┐
        │  Agent 2      │  Classifier  ←── RAG: sector keywords
        │               │  GPT-4o-mini classifies each title into sector
        └──────┬────────┘  Token overlap matching finds cross-platform pairs
               │
        ┌──────┴──────────────────────────────────┐
        ▼       ▼        ▼        ▼        ▼       ▼
     Sports  Politics  Finance  Crypto  World   Other
        └──────┬──────────────────────────────────┘
               │  all sectors + matched pairs
               ▼
        ┌───────────────┐
        │  Agent 3      │  Strategist  ←── RAG: 5 docs (Wolfers & Zitzewitz
        │               │  Academic-grounded verdict per sector              + fees + liquidity)
        └──────┬────────┘
               │  best sector + verdict cards
               ▼
        [ User picks sector from dropdown ]
               │
               ▼
        ┌───────────────┐
        │  Agent 3b     │  Drilldown  ←── RAG: 3 docs
        │               │  score_spread() tool call per pair  ←── Tool calling
        └──────┬────────┘
               │
               ▼
        #1 trade recommendation + runner-up + matched pairs table
```

---

## RAG Knowledge Base

Built from `build_kb.py` — SQLite keyword search over 17 documents across 8 categories.

| Category | Documents | Source |
|---|---|---|
| `academic_theory` | 6 | Wolfers & Zitzewitz (2006) NBER WP 12083 |
| `platform_fees` | 3 | Kalshi official docs + Polymarket documentation |
| `spread_analysis` | 2 | Custom spread interpretation + exploitability framework |
| `liquidity` | 2 | Kalshi and Polymarket liquidity profiles |
| `category_sports` | 1 | Sports market behavior + arbitrage windows |
| `category_politics` | 1 | Political market efficiency + user base differences |
| `category_finance` | 1 | Economic data markets + pre-release spread behavior |
| `category_crypto` | 1 | Crypto dynamics + Polymarket-native liquidity |

Retrieval: `retrieve(query, top_n, category)` — keyword match with category boost, returns context string injected into each agent's prompt.

---

## Tool Calling

`score_spread()` is called by Agent 3b for each matched pair in the selected sector.

| Parameter | Type | Description |
|---|---|---|
| `spread_pct` | float | Absolute price difference between platform mid-prices |
| `kalshi_mid` | float | Kalshi YES contract mid-price |
| `polymarket_mid` | float | Polymarket YES contract mid-price |
| `category` | str | Sector: sports / politics / finance / crypto / world / other |

Returns: `exploitability_score` (1–20), `spread_size_score` (1–5), `liquidity_score` (1–5), `data_confidence` (1–5), `platform_advantage`, `fee_adjusted_exploitable` (bool), `verdict` (STRONG BUY / MONITOR / INVESTIGATE / AVOID).

---

## File Structure

```
prediction-markets/
├── app.py              # Single-page Streamlit UI
├── agents.py           # 3-agent pipeline + score_spread() tool
├── rag.py              # SQLite keyword search RAG
├── data_fetcher.py     # Kalshi V2 + Polymarket Gamma API fetchers
├── matcher.py          # Token-based cross-platform market matching
├── build_kb.py         # One-time script to build knowledge_base.db
├── knowledge_base.db   # SQLite RAG database (17 documents)
├── requirements.txt    # Python dependencies
└── .env.example        # API key template
```

---

## Recreating This Project

### 1. Prerequisites

- Python 3.11+
- OpenAI API key
- Kalshi API key (optional — public endpoints work without one)

### 2. Clone and set up environment

```bash
git clone https://github.com/ms3949/Prediction-Markets.git
cd Prediction-Markets

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

### 3. Configure API keys

Create a `.env` file in the project root:

```
OPENAI_API_KEY=sk-...
KALSHI_API_KEY=...
```

Polymarket requires no API key — their Gamma API is public.

### 4. Build the knowledge base

This is a one-time step that creates `knowledge_base.db`:

```bash
python build_kb.py
```

You should see:
```
✅ Built knowledge base: 17 documents
   academic_theory: 6 docs
   platform_fees: 3 docs
   spread_analysis: 2 docs
   ...
```

### 5. Run locally

```bash
streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501) in your browser.

### 6. Use the app

1. Click **▶ Run Full Analysis** — fetches live markets and runs all 3 agents (20–40 seconds)
2. Review the volume metrics (top left) and sector breakdown chart (top right)
3. Read the session verdict and sector verdict cards
4. Select a sector from the dropdown — it pre-selects the best sector automatically
5. Click **Analyze [Sector] Trades** to see the #1 trade recommendation

---

## Deploying to Streamlit Cloud

1. Push your code to GitHub (without `.env` — never commit API keys)
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Connect your GitHub repo
4. Set secrets under **Settings → Secrets**:

```toml
OPENAI_API_KEY = "sk-..."
KALSHI_API_KEY = "..."
```

5. Make sure `knowledge_base.db` is committed to the repo (it contains no secrets)
6. Deploy — Streamlit Cloud runs `streamlit run app.py` automatically

---

## Tech Stack

| Component | Technology |
|---|---|
| Frontend | Streamlit |
| AI Agents | OpenAI GPT-4o-mini |
| RAG Database | SQLite (knowledge_base.db) |
| RAG Search | SQL LIKE keyword search with relevance scoring |
| Market Data — Kalshi | REST API: `api.elections.kalshi.com/trade-api/v2` |
| Market Data — Polymarket | Gamma REST API: `gamma-api.polymarket.com` |
| Cross-platform matching | Token overlap with alias resolution (matcher.py) |
| Charts | Plotly |
| Deployment | Streamlit Community Cloud |

---

## API Notes

**Kalshi V2 field names** (updated from V1):
- Prices: `yes_bid_dollars` / `yes_ask_dollars` (string floats, already in dollars 0–1)
- Volume: `volume_fp` / `volume_24h_fp` (string floats, counts contracts — not dollars)

**Polymarket Gamma API**:
- Volume: `volume24hr` (USDC dollars — not directly comparable to Kalshi contracts)
- Prices: `outcomePrices` array (index 0 = YES token price)
- No authentication required

---

## Academic Foundation

Wolfers, J., & Zitzewitz, E. (2006). *Prediction Markets in Theory and Practice*. NBER Working Paper No. 12083.

Key findings applied in this app:
- Prediction markets exhibit weak-form efficiency — simple strategies based on public info yield no profit
- The law of one price roughly holds — cross-platform spreads are fleeting
- Favorite-longshot bias: contracts priced below 0.10 or above 0.90 are systematically mispriced
- Political markets: Polymarket (crypto-native) and Kalshi (US retail) users have structurally different information sets, driving persistent political spreads
- Sports markets respond fastest to new information — narrowest exploitable window

---

## Team

| Name | Role |
|---|---|
| Masaab Sohaib | Prompt Engineer · Agent Orchestration · Frontend · Deployment |
| Danny Atik | Backend · API Integration · System Architecture |
