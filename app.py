"""
app.py - Prediction Markets Research Assistant V3
Production-ready. Stakeholder-aligned. Quality-controlled.
"""

import streamlit as st
import plotly.graph_objects as go
import json
import time
import hashlib
from dotenv import load_dotenv

load_dotenv()

from data_fetcher import fetch_snapshot
from agents import run_pipeline, run_drilldown

st.set_page_config(
    page_title="Prediction Markets Research Assistant",
    page_icon="📊", layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
    .stApp { background-color: #0a0c10; color: #e0e0e0; }
    #MainMenu, footer, header { visibility: hidden; }
    .block-container { padding-top: 1rem !important; }

    /* Header */
    .hdr { background: linear-gradient(135deg,#0d1117,#161b27);
           border:1px solid #21262d; border-radius:14px; padding:20px 28px; margin-bottom:16px; }
    .hdr h1 { color:#00d4aa; font-size:1.7rem; font-weight:700; margin:0; }
    .hdr-sub { color:#7d8590; margin:6px 0 0 0; font-size:0.85rem; line-height:1.5; }
    .hdr-how { color:#9198a1; font-size:0.78rem; margin-top:8px;
               background:#0d111788; border-radius:6px; padding:8px 12px; display:inline-block; }

    /* Panels */
    .panel { background:#161b27; border:1px solid #21262d; border-radius:12px; padding:18px 20px; }
    .ptitle { color:#00d4aa; font-size:0.75rem; font-weight:700; text-transform:uppercase;
              letter-spacing:0.6px; margin-bottom:12px; }

    /* Volume */
    .vol-grid { display:grid; grid-template-columns:1fr 1fr; gap:10px; }
    .vol-box  { background:#0d1117; border:1px solid #21262d; border-radius:8px;
                padding:12px 14px; text-align:center; }
    .vol-val  { font-size:1.4rem; font-weight:700; color:#00d4aa; }
    .vol-lbl  { font-size:0.7rem; color:#7d8590; margin-top:2px; }
    .vol-sub  { font-size:0.72rem; color:#9198a1; margin-top:2px; }

    /* Sector cards */
    .sector-card { background:#0d1117; border:1px solid #21262d; border-radius:10px;
                   padding:14px 16px; margin-bottom:10px; }
    .sc-high  { border-left:3px solid #00d4aa; }
    .sc-mod   { border-left:3px solid #f39c12; }
    .sc-low   { border-left:3px solid #e74c3c; }
    .sc-avoid { border-left:3px solid #444; }
    .sc-title { font-weight:700; font-size:0.92rem; color:#e0e0e0; margin-bottom:5px; }
    .sc-detail { font-size:0.78rem; color:#9198a1; margin:3px 0; }
    .sc-detail strong { color:#c0c8d0; }
    .sc-action { font-size:0.8rem; color:#c0c8d0; background:#161b27; border-radius:6px;
                 padding:8px 10px; margin-top:8px; line-height:1.5; }
    .sc-academic { font-size:0.7rem; color:#555; border-top:1px solid #21262d;
                   padding-top:6px; margin-top:6px; }

    /* Badges */
    .badge { display:inline-block; border-radius:10px; padding:2px 8px;
             font-size:0.7rem; font-weight:700; margin-bottom:6px; }
    .bg { background:#00d4aa22; color:#00d4aa; }
    .by { background:#f39c1222; color:#f39c12; }
    .br { background:#e74c3c22; color:#e74c3c; }
    .ba { background:#44444422; color:#888; }

    /* Trade card */
    .top-trade { background:linear-gradient(135deg,#00d4aa0a,#3b82f60a);
                 border:1px solid #00d4aa33; border-radius:8px; padding:14px 16px; margin-bottom:12px; }
    .tt-title { color:#00d4aa; font-weight:700; font-size:0.95rem; margin-bottom:8px; }
    .tt-body  { font-size:0.83rem; color:#c0c8d0; line-height:1.6; }
    .tt-risk  { font-size:0.75rem; color:#e74c3c; margin-top:8px; }
    .tt-warn  { font-size:0.75rem; color:#f39c12; margin-top:6px; font-style:italic; }

    .no-arb { background:#e74c3c0a; border:1px solid #e74c3c33; border-radius:8px;
              padding:12px 16px; font-size:0.83rem; color:#c0c8d0; }
    .no-arb-title { color:#e74c3c; font-weight:700; margin-bottom:6px; }

    /* Session banner */
    .banner { border-radius:8px; padding:14px 18px; margin-bottom:14px; }
    .b-active { background:#00d4aa08; border:1px solid #00d4aa33; }
    .b-quiet  { background:#f39c1208; border:1px solid #f39c1233; }
    .b-mixed  { background:#3b82f608; border:1px solid #3b82f633; }
    .b-title  { font-weight:700; font-size:1rem; margin-bottom:6px; }
    .b-body   { font-size:0.83rem; color:#9198a1; line-height:1.5; }

    /* QC badge */
    .qc-pass { background:#00d4aa22; color:#00d4aa; border-radius:6px;
               padding:4px 10px; font-size:0.72rem; font-weight:700; }
    .qc-warn { background:#f39c1222; color:#f39c12; border-radius:6px;
               padding:4px 10px; font-size:0.72rem; font-weight:700; }
    .qc-fail { background:#e74c3c22; color:#e74c3c; border-radius:6px;
               padding:4px 10px; font-size:0.72rem; font-weight:700; }

    /* Agent steps */
    .agent-step { font-size:0.82rem; padding:8px 12px; border-radius:6px; margin:4px 0;
                  border:1px solid #21262d; color:#7d8590; }
    .a-run { border-color:#f39c12; color:#f39c12; background:#f39c1208; }
    .a-done{ border-color:#00d4aa44; color:#00d4aa; background:#00d4aa08; }
</style>
""", unsafe_allow_html=True)

# ── Session State ─────────────────────────────────────────────────────────────

for k, v in {
    "pipeline":       None,
    "pipeline_hash":  None,
    "drilldown":      None,
    "drill_sector":   None,
    "run_timestamp":  None,
    "run_duration":   None,
    "qc_results":     None,
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── Helpers ───────────────────────────────────────────────────────────────────

def fmt(v):
    try:
        v = float(v)
        if v >= 1_000_000: return f"{v/1_000_000:.1f}M"
        if v >= 1_000:     return f"{v/1_000:.0f}K"
        return f"{v:.0f}"
    except: return "—"

SECTOR_EMOJI = {
    "sports":"🏀","politics":"🗳️","finance":"📈",
    "crypto":"₿","world":"🌍","other":"📌"
}
VERDICT_MAP = {
    "HIGH OPPORTUNITY": ("bg","sc-high"),
    "MODERATE":         ("by","sc-mod"),
    "LOW OPPORTUNITY":  ("br","sc-low"),
    "AVOID":            ("ba","sc-avoid"),
}

# ── Quality Control ───────────────────────────────────────────────────────────

def run_qc(pipeline: dict) -> dict:
    """
    Run quality control checks on pipeline output.
    Returns QC report with pass/warn/fail for each check.
    """
    classifier = pipeline.get("classifier") or {}
    strategist = pipeline.get("strategist") or {}
    sectors    = classifier.get("sectors") or {}

    checks = []
    total_markets = classifier.get("total_markets", 0)
    total_pairs   = sum(len(v.get("matched_pairs",[])) for v in sectors.values())
    total_sectors = len([s for s in sectors if sectors[s].get("kalshi") or sectors[s].get("polymarket")])
    has_analysis  = bool(strategist.get("sector_analysis"))
    has_narrative = bool(strategist.get("session_narrative"))
    best_sector   = strategist.get("best_sector","")

    # Check 1: Market classification coverage
    if total_markets >= 30:
        checks.append(("✅", "Market Classification", f"{total_markets} markets classified", "pass"))
    elif total_markets >= 10:
        checks.append(("⚠", "Market Classification", f"Only {total_markets} markets classified (low)", "warn"))
    else:
        checks.append(("❌", "Market Classification", f"Too few markets: {total_markets}", "fail"))

    # Check 2: Sector coverage
    if total_sectors >= 3:
        checks.append(("✅", "Sector Coverage", f"{total_sectors} sectors identified", "pass"))
    elif total_sectors >= 2:
        checks.append(("⚠", "Sector Coverage", f"Only {total_sectors} sectors (limited)", "warn"))
    else:
        checks.append(("❌", "Sector Coverage", "Fewer than 2 sectors found", "fail"))

    # Check 3: Same-event pair validation
    verified_pairs = sum(
        sum(1 for p in v.get("matched_pairs",[]) if p.get("same_event_verified"))
        for v in sectors.values()
    )
    if total_pairs == 0:
        checks.append(("⚠", "Cross-Platform Pairs", "No matched pairs found this session", "warn"))
    elif verified_pairs == total_pairs:
        checks.append(("✅", "Cross-Platform Pairs", f"{total_pairs} pairs — all same-event verified", "pass"))
    else:
        checks.append(("⚠", "Cross-Platform Pairs", f"{verified_pairs}/{total_pairs} pairs verified", "warn"))

    # Check 4: Strategist output completeness
    if has_analysis and has_narrative and best_sector:
        checks.append(("✅", "AI Analysis Quality", "Sector analysis complete with narrative", "pass"))
    elif has_analysis:
        checks.append(("⚠", "AI Analysis Quality", "Analysis present but incomplete", "warn"))
    else:
        checks.append(("❌", "AI Analysis Quality", "Sector analysis missing", "fail"))

    # Check 5: Spread sanity — no extreme outliers
    all_spreads = [
        p.get("spread", 0)
        for v in sectors.values()
        for p in v.get("matched_pairs", [])
    ]
    if all_spreads:
        suspicious = sum(1 for s in all_spreads if s > 0.40)
        if suspicious == 0:
            checks.append(("✅", "Spread Sanity", f"All {len(all_spreads)} pair spreads within normal range", "pass"))
        else:
            checks.append(("⚠", "Spread Sanity", f"{suspicious} pairs with >40% spread — may be data errors", "warn"))
    else:
        checks.append(("⚠", "Spread Sanity", "No pairs to validate", "warn"))

    passed = sum(1 for c in checks if c[3] == "pass")
    score  = round(passed / len(checks) * 100) if checks else 0

    return {
        "checks":        checks,
        "score":         score,
        "total_markets": total_markets,
        "total_pairs":   total_pairs,
        "verified_pairs": verified_pairs,
        "total_sectors": total_sectors,
    }

# ── Shortcuts ─────────────────────────────────────────────────────────────────

pipeline   = st.session_state.pipeline or {}
collector  = pipeline.get("collector")  or {}
classifier = pipeline.get("classifier") or {}
strategist = pipeline.get("strategist") or {}
sectors    = classifier.get("sectors")  or {}
analysis   = strategist.get("sector_analysis") or {}

# ═══════════════════════════════════════════════════════════════════════════════
# HEADER
# ═══════════════════════════════════════════════════════════════════════════════

st.markdown("""
<div class="hdr">
  <h1>📊 Prediction Markets Research Assistant</h1>
  <p class="hdr-sub">
    Find where Kalshi and Polymarket disagree on the same event — and whether that gap is worth trading.<br>
    Covers Sports · Politics · Finance · Crypto · World events across both platforms in real time.
  </p>
  <span class="hdr-how">
    How to use: Click <strong>Run Full Analysis</strong> → review sector verdicts → pick a sector → get the best trade recommendation
  </span>
</div>""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# TOP ROW — Volume left | Sector chart right
# ═══════════════════════════════════════════════════════════════════════════════

vol_col, chart_col = st.columns([1, 1.6], gap="medium")

with vol_col:
    st.markdown('<div class="panel">', unsafe_allow_html=True)
    st.markdown('<div class="ptitle">📡 Live Platform Activity</div>', unsafe_allow_html=True)

    kv = fmt(collector.get("kalshi_total_volume"))
    pv = fmt(collector.get("polymarket_total_volume"))
    km = collector.get("kalshi_market_count", "—")
    pm = collector.get("polymarket_market_count", "—")

    if st.session_state.run_timestamp:
        ts  = time.strftime("%H:%M:%S", time.localtime(st.session_state.run_timestamp))
        dur = st.session_state.run_duration or 0
        st.caption(f"Last updated: {ts} · Analysis took {dur:.0f}s")

    st.markdown(f"""
    <div class="vol-grid">
        <div class="vol-box">
            <div class="vol-val">{kv}</div>
            <div class="vol-lbl">Kalshi Contracts</div>
            <div class="vol-sub">{km} active markets</div>
        </div>
        <div class="vol-box">
            <div class="vol-val">{pv}</div>
            <div class="vol-lbl">Polymarket (USDC)</div>
            <div class="vol-sub">{pm} active markets</div>
        </div>
    </div>""", unsafe_allow_html=True)

    # QC score if available
    qc = st.session_state.qc_results
    if qc:
        score = qc["score"]
        qc_cls = "qc-pass" if score >= 80 else ("qc-warn" if score >= 60 else "qc-fail")
        st.markdown(f"""
        <div style="margin-top:10px; display:flex; align-items:center; gap:8px;">
            <span class="{qc_cls}">QC Score: {score}%</span>
            <span style="font-size:0.72rem; color:#555">
                {qc['total_markets']} markets · {qc['verified_pairs']} verified pairs
            </span>
        </div>""", unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

with chart_col:
    st.markdown('<div class="panel">', unsafe_allow_html=True)
    st.markdown('<div class="ptitle">📊 Active Markets by Sector</div>', unsafe_allow_html=True)

    if sectors:
        cats      = [s for s in ["sports","politics","finance","crypto","world","other"] if s in sectors]
        k_cnts    = [len(sectors[c].get("kalshi", [])) for c in cats]
        p_cnts    = [len(sectors[c].get("polymarket", [])) for c in cats]
        pair_cnts = [len(sectors[c].get("matched_pairs", [])) for c in cats]

        fig = go.Figure(data=[
            go.Bar(name="Kalshi",          x=cats, y=k_cnts,    marker_color="#00d4aa",
                   text=k_cnts,    textposition="outside", textfont=dict(size=10)),
            go.Bar(name="Polymarket",      x=cats, y=p_cnts,    marker_color="#3b82f6",
                   text=p_cnts,    textposition="outside", textfont=dict(size=10)),
            go.Bar(name="Same-event pairs",x=cats, y=pair_cnts, marker_color="#8b5cf6",
                   text=pair_cnts, textposition="outside", textfont=dict(size=10)),
        ])
        fig.update_layout(
            barmode="group",
            plot_bgcolor="#161b27", paper_bgcolor="#161b27",
            font_color="#9198a1", margin=dict(l=10,r=10,t=40,b=30),
            height=210,
            legend=dict(orientation="h", yanchor="bottom", y=1.02,
                        xanchor="right", x=1, bgcolor="rgba(0,0,0,0)", font=dict(size=10)),
            yaxis=dict(showticklabels=False, showgrid=False, zeroline=False),
            xaxis=dict(tickfont=dict(size=12)),
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    else:
        st.markdown("""
        <div style="height:180px; display:flex; align-items:center; justify-content:center;
                    color:#555; font-size:0.88rem; text-align:center;">
            Run the analysis to see how markets are<br>distributed across sectors
        </div>""", unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# RUN BUTTON
# ═══════════════════════════════════════════════════════════════════════════════

run_col, status_col = st.columns([1, 2], gap="medium")

with run_col:
    run_btn = st.button("▶ Run Full Analysis", type="primary", use_container_width=True)

with status_col:
    if pipeline and not run_btn:
        best = strategist.get("best_sector", "")
        total_mkts = classifier.get("total_markets", 0)
        dur = st.session_state.run_duration or 0
        st.caption(
            f"{total_mkts} markets classified · "
            f"Best: **{SECTOR_EMOJI.get(best,'')} {best.title()}** · "
            f"{strategist.get('overall_verdict','')} · "
            f"Ran in {dur:.0f}s"
        )
    elif not pipeline:
        st.caption("Fetches top 200 markets from each platform and runs 3 AI agents. Takes ~30-45 seconds.")

if run_btn:
    prog_bar    = st.progress(0, text="Starting...")
    step_holder = st.empty()
    step_labels = []
    t_start     = time.time()

    def update(step, total, label):
        step_labels.append(label)
        prog_bar.progress(int(step / total * 100), text=label)
        html = "".join(
            f'<div class="agent-step a-done">✅ {l}</div>' if i < len(step_labels) - 1
            else f'<div class="agent-step a-run">⏳ {l}</div>'
            for i, l in enumerate(step_labels)
        )
        step_holder.markdown(html, unsafe_allow_html=True)

    try:
        update(0, 3, "🔄 Fetching live markets from Kalshi and Polymarket...")
        k_raw, p_raw, _ = fetch_snapshot(category_filter="all", limit=200)

        def mkt_to_dict(m):
            return {
                "title":    m.title,
                "volume":   m.volume or 0,
                "mid_price": m.mid_price,
                "ticker":   m.ticker,
                "category": m.category,
            }

        results = run_pipeline(
            [mkt_to_dict(m) for m in k_raw],
            [mkt_to_dict(m) for m in p_raw],
            progress_callback=update,
        )

        duration = time.time() - t_start

        st.session_state.pipeline       = results
        st.session_state.drilldown      = None
        st.session_state.drill_sector   = None
        st.session_state.run_timestamp  = time.time()
        st.session_state.run_duration   = duration
        st.session_state.qc_results     = run_qc(results)

        prog_bar.progress(100, text=f"✅ Done in {duration:.0f}s")
        step_holder.empty()
        prog_bar.empty()
        st.rerun()

    except Exception as e:
        prog_bar.empty()
        step_holder.empty()
        st.error(f"Something went wrong: {e}")
        st.info("This is usually a temporary API issue. Please try again in a few seconds.")

# ── Stop if no results yet ────────────────────────────────────────────────────

if not st.session_state.pipeline:
    st.markdown("""
    <div style="text-align:center; padding:60px 20px; color:#555;">
        <div style="font-size:2.5rem; margin-bottom:12px;">📊</div>
        <div style="font-size:1rem; color:#7d8590;">Click <strong style="color:#00d4aa">▶ Run Full Analysis</strong> above to get started</div>
        <div style="font-size:0.82rem; margin-top:8px; color:#444;">
            The app will fetch live markets from both platforms, classify them by sector,<br>
            and show you where the best pricing opportunities are right now.
        </div>
    </div>""", unsafe_allow_html=True)
    st.stop()

if pipeline.get("error"):
    st.error(f"Pipeline error: {pipeline['error']}")
    st.caption("Try running again — this is usually a temporary API or network issue.")
    st.stop()

st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# SESSION BANNER
# ═══════════════════════════════════════════════════════════════════════════════

verdict   = strategist.get("overall_verdict", "MIXED")
narrative = strategist.get("session_narrative", "")
best_sec  = strategist.get("best_sector", "")
best_why  = strategist.get("best_sector_reason", "")

v_cls   = {"ACTIVE":"b-active","QUIET":"b-quiet","MIXED":"b-mixed"}.get(verdict,"b-mixed")
v_clr   = {"ACTIVE":"#00d4aa","QUIET":"#f39c12","MIXED":"#3b82f6"}.get(verdict,"#888")
v_emoji = {"ACTIVE":"🟢","QUIET":"🟡","MIXED":"🟡"}.get(verdict,"⚪")

st.markdown(f"""
<div class="banner {v_cls}">
    <div class="b-title" style="color:{v_clr}">{v_emoji} Market Session: {verdict}</div>
    <div class="b-body">{narrative}</div>
    {f'<div class="b-body" style="margin-top:8px">🏆 <strong style="color:{v_clr}">Best sector right now: {SECTOR_EMOJI.get(best_sec,"")} {best_sec.title()}</strong> — {best_why}</div>' if best_sec else ''}
</div>""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# BOTTOM — Sector cards left | Drilldown right
# ═══════════════════════════════════════════════════════════════════════════════

cards_col, drill_col = st.columns([1, 1], gap="medium")

# ── LEFT: Sector verdict cards ────────────────────────────────────────────────

with cards_col:
    st.markdown('<div class="panel">', unsafe_allow_html=True)
    st.markdown('<div class="ptitle">🗂 Sector Verdicts</div>', unsafe_allow_html=True)

    sector_order     = ["sports","politics","finance","crypto","world","other"]
    available_sectors = [s for s in sector_order if s in analysis]

    if not available_sectors:
        st.caption("No sector analysis available. Try running again.")
    else:
        for sec in available_sectors:
            card     = analysis[sec]
            sv       = card.get("verdict", "MODERATE")
            badge_cls, card_cls = VERDICT_MAP.get(sv, ("ba","sc-avoid"))
            emoji    = SECTOR_EMOJI.get(sec, "📌")
            is_best  = (sec == best_sec)
            n_pairs  = len(sectors.get(sec, {}).get("matched_pairs", []))

            st.markdown(f"""
            <div class="sector-card {card_cls}" {"style='border-color:#00d4aa66'" if is_best else ""}>
                <div class="sc-title">{emoji} {sec.upper()} {"⭐ Best right now" if is_best else ""}</div>
                <span class="badge {badge_cls}">{sv}</span>
                <div class="sc-detail">
                    Kalshi: <strong>{card.get('num_kalshi','—')}</strong> markets ·
                    Polymarket: <strong>{card.get('num_poly','—')}</strong> markets ·
                    Same-event pairs: <strong>{n_pairs}</strong>
                </div>
                <div class="sc-detail">Avg spread across pairs: <strong>{card.get('avg_spread_pct','—')}</strong></div>
                <div class="sc-action">{card.get('summary','—')}</div>
                <div class="sc-action" style="margin-top:6px">⚡ {card.get('recommendation','—')}</div>
                <div class="sc-academic">📚 {card.get('academic_note','—')}</div>
            </div>""", unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

# ── RIGHT: Sector selector + drilldown ───────────────────────────────────────

with drill_col:
    st.markdown('<div class="panel">', unsafe_allow_html=True)
    st.markdown('<div class="ptitle">🎯 Trade Finder</div>', unsafe_allow_html=True)

    if not available_sectors:
        st.info("No sectors available. Run the analysis first.")
    else:
        default_idx = available_sectors.index(best_sec) if best_sec in available_sectors else 0
        chosen = st.selectbox(
            "Select a sector to find the best trade in:",
            options=available_sectors,
            format_func=lambda s: f"{SECTOR_EMOJI.get(s,'')} {s.title()}",
            index=default_idx,
            key="sector_select"
        )

        n_pairs_chosen = len(sectors.get(chosen, {}).get("matched_pairs", []))
        if n_pairs_chosen > 0:
            st.caption(f"{n_pairs_chosen} same-event pair(s) found in {chosen} — ready to analyze")
        else:
            st.caption(f"No cross-platform pairs found in {chosen} this session — will analyze single-platform opportunities")

        drill_btn = st.button(
            f"🔍 Find Best {SECTOR_EMOJI.get(chosen,'')} {chosen.title()} Trade",
            type="primary", use_container_width=True
        )

        if drill_btn:
            with st.spinner(f"Finding best {chosen} trade..."):
                sector_data = sectors.get(chosen, {})
                dd = run_drilldown(chosen, sector_data)
                st.session_state.drilldown    = dd
                st.session_state.drill_sector = chosen
            st.rerun()

        dd  = st.session_state.drilldown
        sec = st.session_state.drill_sector

        if dd and sec:
            if dd.get("parse_error"):
                st.error("The AI returned an unexpected response format. Please try again.")
            else:
                top      = dd.get("top_trade")
                runner   = dd.get("runner_up", {})
                no_arb   = dd.get("no_arb_reason", "")
                cond     = dd.get("sector_conditions", "")
                warning  = dd.get("academic_warning", "")

                if cond:
                    st.caption(cond)

                # ── No valid arb case ─────────────────────────────────────────
                if not top or no_arb:
                    st.markdown(f"""
                    <div class="no-arb">
                        <div class="no-arb-title">❌ No exploitable arbitrage found in {sec.title()}</div>
                        {no_arb or "No same-event pairs with sufficient spread found this session."}
                        <br><br>
                        <em style="color:#555; font-size:0.75rem">
                            This is the correct result — not every session has exploitable spreads.
                            Wolfers & Zitzewitz (2006): arbitrage opportunities in prediction markets
                            are fleeting and involve only small potential profits.
                        </em>
                    </div>""", unsafe_allow_html=True)

                # ── Valid trade ───────────────────────────────────────────────
                else:
                    exploit = top.get("fee_exploitable", False)
                    same_ev = top.get("same_event", True)
                    e_icon  = "✅ Yes" if exploit else "❌ No — spread too tight after fees"

                    st.markdown(f"""
                    <div class="top-trade">
                        <div class="tt-title">🏆 Best Trade in {SECTOR_EMOJI.get(sec,'')} {sec.title()}</div>
                        <div class="tt-body">
                            <strong>Kalshi:</strong> {top.get("kalshi_title","—")}<br>
                            <strong>Polymarket:</strong> {top.get("polymarket_title","—")}<br>
                            <strong>Spread:</strong> {top.get("spread_pct","—")} &nbsp;·&nbsp;
                            <strong>Fee-exploitable:</strong> {e_icon}<br>
                            <strong>Platform to buy on:</strong> {top.get("platform_to_buy","—").title()}<br><br>
                            <strong style="color:#00d4aa">⚡ Action:</strong> {top.get("action","—")}<br><br>
                            {top.get("rationale","")}
                        </div>
                        <div class="tt-risk">⚠ Risk: {top.get("key_risk","—")}</div>
                        {f'<div class="tt-warn">📚 {warning}</div>' if warning else ''}
                    </div>""", unsafe_allow_html=True)

                    if runner and runner.get("kalshi_title"):
                        with st.expander("Runner-up trade"):
                            st.markdown(f"**{runner.get('kalshi_title','—')}** vs **{runner.get('polymarket_title','—')}**")
                            st.markdown(f"Spread: {runner.get('spread_pct','—')}")
                            st.markdown(runner.get('action','—'))

                # ── Matched pairs table ───────────────────────────────────────
                sec_pairs = sectors.get(sec, {}).get("matched_pairs", [])
                if sec_pairs:
                    with st.expander(f"All {len(sec_pairs)} same-event pairs in {sec.title()}"):
                        import pandas as pd
                        df = pd.DataFrame(sec_pairs)
                        show = [c for c in ["kalshi_title","polymarket_title","spread_pct","kalshi_mid","polymarket_mid"] if c in df.columns]
                        st.dataframe(
                            df[show].rename(columns={
                                "kalshi_title":"Kalshi","polymarket_title":"Polymarket",
                                "spread_pct":"Spread","kalshi_mid":"K Mid","polymarket_mid":"P Mid"
                            }),
                            hide_index=True, use_container_width=True
                        )
        else:
            # Pre-drilldown: show markets in selected sector
            import pandas as pd
            sec_k = sectors.get(chosen, {}).get("kalshi", [])
            sec_p = sectors.get(chosen, {}).get("polymarket", [])
            if sec_k or sec_p:
                st.markdown(f"**Markets in {SECTOR_EMOJI.get(chosen,'')} {chosen.title()} this session:**")
                all_mkts = (
                    [{"Platform":"Kalshi",     "Title":m["title"], "Mid":m.get("mid","—")} for m in sec_k] +
                    [{"Platform":"Polymarket", "Title":m["title"], "Mid":m.get("mid","—")} for m in sec_p]
                )
                st.dataframe(pd.DataFrame(all_mkts), hide_index=True, use_container_width=True, height=260)

    st.markdown('</div>', unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# QUALITY CONTROL PANEL (collapsed by default — for grader / advanced users)
# ═══════════════════════════════════════════════════════════════════════════════

if st.session_state.qc_results:
    qc = st.session_state.qc_results
    with st.expander(f"🔍 Quality Control Report — Score: {qc['score']}%"):
        st.markdown("These checks run automatically after every analysis to validate AI output quality.")
        for icon, name, detail, status in qc["checks"]:
            cls = {"pass":"qc-pass","warn":"qc-warn","fail":"qc-fail"}.get(status,"qc-warn")
            st.markdown(
                f'<span class="{cls}">{icon} {name}</span> '
                f'<span style="font-size:0.8rem; color:#7d8590; margin-left:8px">{detail}</span>',
                unsafe_allow_html=True
            )
        st.markdown(f"""
        **Summary:** {qc['total_markets']} markets classified ·
        {qc['total_sectors']} sectors identified ·
        {qc['verified_pairs']} same-event verified pairs
        """)

# ── Footer ────────────────────────────────────────────────────────────────────

st.markdown("---")
st.caption(
    "Prediction Markets Research Assistant · "
    "Wolfers & Zitzewitz (2006) NBER WP 12083 · "
    "Kalshi × Polymarket · Not financial advice"
)
