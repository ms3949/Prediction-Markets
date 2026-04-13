"""
app.py - Prediction Markets Research Assistant V2
One page. One button. Three agents. User picks sector for drilldown.
"""

import streamlit as st
import plotly.graph_objects as go
import json
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

    .hdr { background: linear-gradient(135deg,#0d1117,#161b27); border:1px solid #21262d;
           border-radius:14px; padding:18px 24px; margin-bottom:16px; }
    .hdr h1 { color:#00d4aa; font-size:1.7rem; font-weight:700; margin:0; }
    .hdr p  { color:#7d8590; margin:4px 0 0 0; font-size:0.83rem; }

    .panel { background:#161b27; border:1px solid #21262d; border-radius:12px; padding:18px 20px; }
    .ptitle { color:#00d4aa; font-size:0.75rem; font-weight:700; text-transform:uppercase;
              letter-spacing:0.6px; margin-bottom:12px; }

    .vol-grid { display:grid; grid-template-columns:1fr 1fr; gap:10px; }
    .vol-box  { background:#0d1117; border:1px solid #21262d; border-radius:8px;
                padding:12px 14px; text-align:center; }
    .vol-val  { font-size:1.4rem; font-weight:700; color:#00d4aa; }
    .vol-lbl  { font-size:0.7rem; color:#7d8590; margin-top:2px; }
    .vol-sub  { font-size:0.72rem; color:#9198a1; margin-top:2px; }

    .sector-card { background:#0d1117; border:1px solid #21262d; border-radius:10px;
                   padding:14px 16px; margin-bottom:10px; }
    .sc-high   { border-left:3px solid #00d4aa; }
    .sc-mod    { border-left:3px solid #f39c12; }
    .sc-low    { border-left:3px solid #e74c3c; }
    .sc-avoid  { border-left:3px solid #444; }
    .sc-title  { font-weight:700; font-size:0.92rem; color:#e0e0e0; margin-bottom:5px; }
    .sc-detail { font-size:0.78rem; color:#9198a1; margin:3px 0; }
    .sc-detail strong { color:#c0c8d0; }
    .sc-action { font-size:0.8rem; color:#c0c8d0; background:#161b27; border-radius:6px;
                 padding:8px 10px; margin-top:8px; line-height:1.5; }
    .sc-academic { font-size:0.7rem; color:#555; border-top:1px solid #21262d;
                   padding-top:6px; margin-top:6px; }

    .badge { display:inline-block; border-radius:10px; padding:2px 8px;
             font-size:0.7rem; font-weight:700; margin-bottom:6px; }
    .bg { background:#00d4aa22; color:#00d4aa; }
    .by { background:#f39c1222; color:#f39c12; }
    .br { background:#e74c3c22; color:#e74c3c; }
    .ba { background:#44444422; color:#888; }

    .top-trade { background:linear-gradient(135deg,#00d4aa0a,#3b82f60a);
                 border:1px solid #00d4aa33; border-radius:8px; padding:14px 16px; margin-bottom:12px; }
    .tt-title { color:#00d4aa; font-weight:700; font-size:0.95rem; margin-bottom:8px; }
    .tt-body  { font-size:0.83rem; color:#c0c8d0; line-height:1.6; }
    .tt-risk  { font-size:0.75rem; color:#e74c3c; margin-top:8px; }
    .tt-warn  { font-size:0.75rem; color:#f39c12; margin-top:6px; font-style:italic; }

    .banner { border-radius:8px; padding:14px 18px; margin-bottom:14px; }
    .b-active { background:#00d4aa08; border:1px solid #00d4aa33; }
    .b-quiet  { background:#f39c1208; border:1px solid #f39c1233; }
    .b-mixed  { background:#3b82f608; border:1px solid #3b82f633; }
    .b-title  { font-weight:700; font-size:1rem; margin-bottom:6px; }
    .b-body   { font-size:0.83rem; color:#9198a1; line-height:1.5; }

    .agent-step { font-size:0.82rem; padding:8px 12px; border-radius:6px; margin:4px 0;
                  border:1px solid #21262d; color:#7d8590; }
    .a-run { border-color:#f39c12; color:#f39c12; background:#f39c1208; }
    .a-done{ border-color:#00d4aa44; color:#00d4aa; background:#00d4aa08; }
</style>
""", unsafe_allow_html=True)

# ── Session State ─────────────────────────────────────────────────────────────

for k, v in {
    "pipeline":      None,
    "drilldown":     None,
    "drill_sector":  None,
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
  <p>Live cross-exchange intelligence · Kalshi × Polymarket · 3-Agent AI Pipeline · RAG: Wolfers & Zitzewitz (2006)</p>
</div>""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# TOP ROW — Volume left | Sector chart right
# ═══════════════════════════════════════════════════════════════════════════════

vol_col, chart_col = st.columns([1, 1.6], gap="medium")

with vol_col:
    st.markdown('<div class="panel">', unsafe_allow_html=True)
    st.markdown('<div class="ptitle">📡 Live Platform Volume</div>', unsafe_allow_html=True)

    kv = fmt(collector.get("kalshi_total_volume"))
    pv = fmt(collector.get("polymarket_total_volume"))
    km = collector.get("kalshi_market_count", "—")
    pm = collector.get("polymarket_market_count", "—")

    st.markdown(f"""
    <div class="vol-grid">
        <div class="vol-box">
            <div class="vol-val">{kv}</div>
            <div class="vol-lbl">Kalshi Contracts Traded</div>
            <div class="vol-sub">{km} markets</div>
        </div>
        <div class="vol-box">
            <div class="vol-val">{pv}</div>
            <div class="vol-lbl">Polymarket Dollar Volume</div>
            <div class="vol-sub">{pm} markets</div>
        </div>
    </div>""", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

with chart_col:
    st.markdown('<div class="panel">', unsafe_allow_html=True)
    st.markdown('<div class="ptitle">📊 Markets by Sector</div>', unsafe_allow_html=True)

    if sectors:
        cats    = [s for s in ["sports","politics","finance","crypto","world","other"] if s in sectors]
        k_cnts  = [len(sectors[c].get("kalshi", [])) for c in cats]
        p_cnts  = [len(sectors[c].get("polymarket", [])) for c in cats]
        pair_cnts = [len(sectors[c].get("matched_pairs", [])) for c in cats]

        fig = go.Figure(data=[
            go.Bar(name="Kalshi markets",     x=cats, y=k_cnts,    marker_color="#00d4aa",
                   text=k_cnts, textposition="outside", textfont=dict(size=10)),
            go.Bar(name="Polymarket markets", x=cats, y=p_cnts,    marker_color="#3b82f6",
                   text=p_cnts, textposition="outside", textfont=dict(size=10)),
            go.Bar(name="Matched pairs",      x=cats, y=pair_cnts, marker_color="#8b5cf6",
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
        st.caption("Number of markets classified per sector across both platforms")
    else:
        st.caption("Run analysis to see sector breakdown.")

    st.markdown('</div>', unsafe_allow_html=True)

st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# RUN BUTTON
# ═══════════════════════════════════════════════════════════════════════════════

run_col, status_col = st.columns([1, 2], gap="medium")

with run_col:
    run_btn = st.button("▶ Run Full Analysis", type="primary", use_container_width=True)

with status_col:
    if pipeline:
        best = strategist.get("best_sector", "")
        total_mkts = classifier.get("total_markets", 0)
        st.caption(f"Last run: {total_mkts} markets classified · Best sector: **{SECTOR_EMOJI.get(best,'')} {best.title()}** · {strategist.get('overall_verdict','')}")

if run_btn:
    prog_bar    = st.progress(0, text="Starting...")
    step_holder = st.empty()
    step_labels = []

    def update(step, total, label):
        step_labels.append(label)
        prog_bar.progress(int(step/total*100), text=label)
        html = "".join(
            f'<div class="agent-step a-done">✅ {l}</div>' if i < len(step_labels)-1
            else f'<div class="agent-step a-run">⏳ {l}</div>'
            for i, l in enumerate(step_labels)
        )
        step_holder.markdown(html, unsafe_allow_html=True)

    try:
        update(0, 3, "🔄 Fetching top 200 markets from Kalshi and Polymarket...")
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
        st.session_state.pipeline    = results
        st.session_state.drilldown   = None
        st.session_state.drill_sector = None

        prog_bar.progress(100, text="✅ Done")
        step_holder.empty()
        prog_bar.empty()
        st.rerun()

    except Exception as e:
        st.error(f"Error: {e}")

# ── Stop here if no pipeline yet ──────────────────────────────────────────────

if not st.session_state.pipeline:
    st.info("Click **▶ Run Full Analysis** to fetch live markets and generate sector verdicts.")
    st.stop()

if pipeline.get("error"):
    st.error(f"Pipeline error: {pipeline['error']}")
    st.stop()

st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# SESSION BANNER
# ═══════════════════════════════════════════════════════════════════════════════

verdict   = strategist.get("overall_verdict", "MIXED")
narrative = strategist.get("session_narrative", "")
best_sec  = strategist.get("best_sector", "")
best_why  = strategist.get("best_sector_reason", "")

v_cls = {"ACTIVE":"b-active","QUIET":"b-quiet","MIXED":"b-mixed"}.get(verdict,"b-mixed")
v_clr = {"ACTIVE":"#00d4aa","QUIET":"#f39c12","MIXED":"#3b82f6"}.get(verdict,"#888")
v_emoji = {"ACTIVE":"🟢","QUIET":"🟡","MIXED":"🟡"}.get(verdict,"⚪")

st.markdown(f"""
<div class="banner {v_cls}">
    <div class="b-title" style="color:{v_clr}">{v_emoji} Session: {verdict}</div>
    <div class="b-body">{narrative}</div>
    {f'<div class="b-body" style="margin-top:8px">🏆 <strong style="color:{v_clr}">Best sector: {SECTOR_EMOJI.get(best_sec,"")} {best_sec.title()}</strong> — {best_why}</div>' if best_sec else ''}
</div>""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# BOTTOM — Sector cards left | Drilldown right
# ═══════════════════════════════════════════════════════════════════════════════

cards_col, drill_col = st.columns([1, 1], gap="medium")

# ── LEFT: Sector verdict cards ────────────────────────────────────────────────

with cards_col:
    st.markdown('<div class="panel">', unsafe_allow_html=True)
    st.markdown('<div class="ptitle">🗂 Sector Analysis</div>', unsafe_allow_html=True)

    sector_order = ["sports","politics","finance","crypto","world","other"]
    available_sectors = [s for s in sector_order if s in analysis]

    for sec in available_sectors:
        card     = analysis[sec]
        sv       = card.get("verdict", "MODERATE")
        badge_cls, card_cls = VERDICT_MAP.get(sv, ("ba","sc-avoid"))
        emoji    = SECTOR_EMOJI.get(sec, "📌")
        is_best  = (sec == best_sec)

        st.markdown(f"""
        <div class="sector-card {card_cls}" {"style='border-color:#00d4aa66'" if is_best else ""}>
            <div class="sc-title">{emoji} {sec.upper()} {"⭐ Best" if is_best else ""}</div>
            <span class="badge {badge_cls}">{sv}</span>
            <div class="sc-detail">Markets: <strong>K={card.get('num_kalshi','—')} | P={card.get('num_poly','—')} | Pairs={card.get('num_pairs','—')}</strong></div>
            <div class="sc-detail">Avg Cross-Platform Spread: <strong>{card.get('avg_spread_pct','—')}</strong></div>
            <div class="sc-action">{card.get('summary','—')}</div>
            <div class="sc-action" style="margin-top:6px">⚡ {card.get('recommendation','—')}</div>
            <div class="sc-academic">📚 {card.get('academic_note','—')}</div>
        </div>""", unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

# ── RIGHT: Sector selector + drilldown ───────────────────────────────────────

with drill_col:
    st.markdown('<div class="panel">', unsafe_allow_html=True)
    st.markdown('<div class="ptitle">🎯 Sector Deep Dive</div>', unsafe_allow_html=True)

    if available_sectors:
        # Sector selector
        default_idx = available_sectors.index(best_sec) if best_sec in available_sectors else 0
        chosen = st.selectbox(
            "Which sector would you like to know more about?",
            options=available_sectors,
            format_func=lambda s: f"{SECTOR_EMOJI.get(s,'')} {s.title()}",
            index=default_idx,
            key="sector_select"
        )

        drill_btn = st.button(
            f"🔍 Analyze {SECTOR_EMOJI.get(chosen,'')} {chosen.title()} Trades",
            type="primary", use_container_width=True
        )

        if drill_btn:
            with st.spinner(f"Analyzing best {chosen} trades..."):
                sector_data = sectors.get(chosen, {})
                st.session_state.drilldown    = run_drilldown(chosen, sector_data)
                st.session_state.drill_sector = chosen
            st.rerun()

        # Show drilldown results
        dd  = st.session_state.drilldown
        sec = st.session_state.drill_sector

        if dd and not dd.get("parse_error"):
            st.markdown(f"#### {SECTOR_EMOJI.get(sec,'')} {(sec or '').title()} — Best Trade")

            cond = dd.get("sector_conditions", "")
            if cond:
                st.caption(cond)

            top = dd.get("top_trade", {})
            if top:
                exploit = top.get("fee_exploitable", False)
                e_icon  = "✅ Yes" if exploit else "❌ No (spread too tight)"

                st.markdown(f"""
                <div class="top-trade">
                    <div class="tt-title">🏆 #1 Recommended Trade</div>
                    <div class="tt-body">
                        <strong>Kalshi:</strong> {top.get("kalshi_title","—")}<br>
                        <strong>Polymarket:</strong> {top.get("polymarket_title","—")}<br>
                        <strong>Spread:</strong> {top.get("spread_pct","—")} &nbsp;·&nbsp;
                        <strong>Fee-exploitable:</strong> {e_icon}<br>
                        <strong>Platform to favor:</strong> {top.get("platform_to_buy","—").title()}<br><br>
                        <strong style="color:#00d4aa">⚡ Action:</strong> {top.get("action","—")}<br><br>
                        {top.get("rationale","")}
                    </div>
                    <div class="tt-risk">⚠ Risk: {top.get("key_risk","—")}</div>
                    <div class="tt-warn">📚 {dd.get("academic_warning","")}</div>
                </div>""", unsafe_allow_html=True)

            runner = dd.get("runner_up", {})
            if runner and runner.get("kalshi_title"):
                st.markdown("**Runner-up:**")
                st.markdown(f"""
                <div class="sector-card sc-mod" style="margin-top:0">
                    <div class="sc-detail"><strong>{runner.get("kalshi_title","—")}</strong></div>
                    <div class="sc-detail">Spread: {runner.get("spread_pct","—")}</div>
                    <div class="sc-detail" style="color:#c0c8d0">{runner.get("action","—")}</div>
                </div>""", unsafe_allow_html=True)

            # All pairs in this sector
            sec_pairs = sectors.get(sec, {}).get("matched_pairs", [])
            if sec_pairs:
                st.markdown("---")
                st.markdown(f"**All {sec} matched pairs ({len(sec_pairs)})**")
                import pandas as pd
                df = pd.DataFrame(sec_pairs)
                show = [c for c in ["kalshi_title","polymarket_title","spread_pct","kalshi_mid","polymarket_mid"] if c in df.columns]
                st.dataframe(
                    df[show].rename(columns={
                        "kalshi_title":"Kalshi","polymarket_title":"Polymarket",
                        "spread_pct":"Spread","kalshi_mid":"K Mid","polymarket_mid":"P Mid"
                    }),
                    hide_index=True, use_container_width=True, height=220
                )

        elif dd and dd.get("parse_error"):
            st.error(f"Parse error: {dd['parse_error']}")
        else:
            # Show top markets from this sector while waiting
            import pandas as pd
            sec_k = sectors.get(chosen, {}).get("kalshi", [])
            sec_p = sectors.get(chosen, {}).get("polymarket", [])
            if sec_k:
                st.caption(f"**Kalshi {chosen} markets:**")
                st.dataframe(
                    pd.DataFrame([{"Title": m["title"], "Volume": fmt(m.get("volume")), "Mid": m.get("mid")} for m in sec_k]),
                    hide_index=True, use_container_width=True, height=180
                )
            if sec_p:
                st.caption(f"**Polymarket {chosen} markets:**")
                st.dataframe(
                    pd.DataFrame([{"Title": m["title"], "Volume": fmt(m.get("volume")), "Mid": m.get("mid")} for m in sec_p]),
                    hide_index=True, use_container_width=True, height=180
                )
    else:
        st.info("No sectors found. Run analysis first.")

    st.markdown('</div>', unsafe_allow_html=True)

# ── Footer ────────────────────────────────────────────────────────────────────

st.markdown("---")
st.caption("Wolfers & Zitzewitz (2006) · NBER Working Paper 12083 · Prediction Markets in Theory and Practice")

with st.expander("🔧 Raw Pipeline JSON"):
    st.json(pipeline)
