"""
HTML dashboard generator.
Produces a self-contained, offline dark-mode dashboard with:
- Market regime banner
- Filterable, sortable stock cards
- TradingView chart links
- Factor breakdown per stock
"""

from datetime import datetime
from pathlib import Path


STATUS_COLORS = {
    "READY":    "#27ae60",
    "WATCH":    "#e67e22",
    "BUILDING": "#3498db",
    "WEAK":     "#7f8c8d",
}

LEVEL_COLORS = {
    "ATH":              "#27ae60",
    "multi-year":       "#2ecc71",
    "52-week":          "#f39c12",
    "prior resistance": "#e74c3c",
}

REGIME_COLORS = {
    "Favorable": "#27ae60",
    "Mixed":     "#f39c12",
    "Caution":   "#e67e22",
    "Risk Off":  "#e74c3c",
}


def render_dashboard(results: list[dict], output_path: Path, date_str: str):
    """Render the full HTML dashboard and write to output_path."""
    regime = _infer_regime(results)
    stats = _compute_stats(results)
    cards_html = "\n".join(_render_card(r) for r in results[:200])  # cap at 200

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NASDAQ Momentum Screener — {date_str}</title>
<style>
  :root {{
    --bg: #0f1117; --bg2: #1a1d26; --bg3: #22263a;
    --text: #e8eaf0; --muted: #8892a4; --border: #2a2f42;
    --green: #27ae60; --amber: #e67e22; --blue: #3498db; --red: #e74c3c;
    --card-w: 320px;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; font-size: 14px; }}
  .header {{ background: var(--bg2); border-bottom: 1px solid var(--border); padding: 16px 24px; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; }}
  .header h1 {{ font-size: 18px; font-weight: 600; letter-spacing: -0.3px; }}
  .header p {{ color: var(--muted); font-size: 12px; margin-top: 2px; }}
  .regime {{ padding: 6px 14px; border-radius: 20px; font-size: 12px; font-weight: 600; }}
  .metrics {{ display: flex; gap: 12px; padding: 16px 24px; flex-wrap: wrap; background: var(--bg2); border-bottom: 1px solid var(--border); }}
  .metric {{ background: var(--bg3); border-radius: 8px; padding: 10px 16px; min-width: 110px; }}
  .metric-label {{ font-size: 11px; color: var(--muted); margin-bottom: 4px; text-transform: uppercase; letter-spacing: 0.5px; }}
  .metric-val {{ font-size: 22px; font-weight: 700; }}
  .controls {{ display: flex; gap: 10px; padding: 14px 24px; background: var(--bg2); border-bottom: 1px solid var(--border); flex-wrap: wrap; align-items: center; }}
  .controls input, .controls select {{ background: var(--bg3); color: var(--text); border: 1px solid var(--border); border-radius: 6px; padding: 7px 12px; font-size: 13px; outline: none; }}
  .controls input:focus, .controls select:focus {{ border-color: var(--blue); }}
  .controls label {{ color: var(--muted); font-size: 12px; display: flex; align-items: center; gap: 6px; }}
  .grid {{ display: flex; flex-wrap: wrap; gap: 14px; padding: 20px 24px; }}
  .card {{ background: var(--bg2); border: 1px solid var(--border); border-radius: 12px; padding: 16px; width: var(--card-w); transition: border-color 0.15s; }}
  .card:hover {{ border-color: #3d4460; }}
  .card-top {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 10px; }}
  .ticker {{ font-size: 20px; font-weight: 700; }}
  .company {{ font-size: 12px; color: var(--muted); margin-top: 2px; }}
  .sector {{ font-size: 11px; color: #5a6480; margin-top: 1px; }}
  .score-badge {{ text-align: center; min-width: 52px; }}
  .score-num {{ font-size: 24px; font-weight: 700; }}
  .score-label {{ font-size: 10px; margin-top: 2px; font-weight: 600; letter-spacing: 0.5px; }}
  .signals {{ display: flex; gap: 5px; flex-wrap: wrap; margin-bottom: 10px; }}
  .sig {{ font-size: 10px; font-weight: 600; padding: 3px 8px; border-radius: 20px; }}
  .sig-green {{ background: #1a3d2b; color: var(--green); }}
  .sig-amber {{ background: #3d2e10; color: var(--amber); }}
  .sig-blue  {{ background: #1a2a3d; color: var(--blue); }}
  .sig-red   {{ background: #3d1a1a; color: var(--red); }}
  .factors {{ display: grid; grid-template-columns: 1fr 1fr; gap: 3px 16px; margin-bottom: 10px; font-size: 12px; }}
  .factor {{ display: flex; justify-content: space-between; padding: 2px 0; border-bottom: 1px solid var(--border); }}
  .f-name {{ color: var(--muted); }}
  .f-val {{ font-weight: 500; }}
  .f-green {{ color: var(--green); }}
  .f-amber {{ color: var(--amber); }}
  .f-red   {{ color: var(--red); }}
  .card-footer {{ display: flex; justify-content: space-between; align-items: center; padding-top: 10px; border-top: 1px solid var(--border); }}
  .price {{ font-size: 15px; font-weight: 600; }}
  .chg {{ font-size: 12px; margin-left: 6px; }}
  .chg-up {{ color: var(--green); }}
  .chg-dn {{ color: var(--red); }}
  .tv-link {{ color: var(--blue); font-size: 11px; text-decoration: none; }}
  .tv-link:hover {{ text-decoration: underline; }}
  .rank {{ font-size: 11px; color: var(--muted); }}
  .empty {{ text-align: center; padding: 60px; color: var(--muted); width: 100%; }}
  .footer {{ padding: 20px 24px; color: var(--muted); font-size: 11px; border-top: 1px solid var(--border); }}
  @media (max-width: 700px) {{ :root {{ --card-w: 100%; }} .grid {{ padding: 12px; gap: 10px; }} }}
</style>
</head>
<body>

<div class="header">
  <div>
    <h1>NASDAQ Momentum Screener</h1>
    <p>Breakout · Bull Flag · Relative Strength · Volume Surge — {date_str}</p>
  </div>
  <div class="regime" style="background:{REGIME_COLORS.get(regime,'#333')}22; color:{REGIME_COLORS.get(regime,'#aaa')}; border:1px solid {REGIME_COLORS.get(regime,'#333')}55;">
    Market: {regime}
  </div>
</div>

<div class="metrics">
  <div class="metric"><div class="metric-label">Scanned</div><div class="metric-val">{stats['total']:,}</div></div>
  <div class="metric"><div class="metric-label">Ready (85+)</div><div class="metric-val" style="color:var(--green)">{stats['ready']}</div></div>
  <div class="metric"><div class="metric-label">Watch (70-84)</div><div class="metric-val" style="color:var(--amber)">{stats['watch']}</div></div>
  <div class="metric"><div class="metric-label">Bull Flags</div><div class="metric-val" style="color:var(--blue)">{stats['flags']}</div></div>
  <div class="metric"><div class="metric-label">Vol Surges (3x+)</div><div class="metric-val">{stats['vol_surges']}</div></div>
</div>

<div class="controls">
  <input type="text" id="search" placeholder="Search ticker / name..." oninput="filter()" style="width:200px">
  <select id="setup-filter" onchange="filter()">
    <option value="">All setups</option>
    <option value="Tight Base">Tight base</option>
    <option value="Bull Flag">Bull flag</option>
    <option value="Weekly Base">Weekly base</option>
    <option value="Trendline">Trendline compression</option>
    <option value="Undercut Rally">Undercut &amp; rally</option>
    <option value="ATH Break">ATH breakout</option>
  </select>
  <select id="status-filter" onchange="filter()">
    <option value="">All status</option>
    <option value="READY">READY only</option>
    <option value="WATCH">WATCH only</option>
  </select>
  <select id="sort-sel" onchange="filter()">
    <option value="score">Sort: composite score</option>
    <option value="rs">Sort: RS percentile</option>
    <option value="vol">Sort: volume surge</option>
    <option value="atr">Sort: ATR compression</option>
    <option value="chg">Sort: % change</option>
  </select>
  <label><input type="checkbox" id="gate-filter" onchange="filter()"> Gate-passing only</label>
  <span id="count-label" style="color:var(--muted);font-size:12px;margin-left:auto"></span>
</div>

<div class="grid" id="grid">
{cards_html}
</div>

<div class="footer">
  Generated {datetime.now().strftime("%Y-%m-%d %H:%M")} · {stats['total']} stocks scanned ·
  Data: yfinance (Yahoo Finance) · No API keys required ·
  ⚠️ For informational purposes only. Not financial advice. Always use stop losses.
</div>

<script>
const allCards = Array.from(document.querySelectorAll('.card'));

function filter() {{
  const search = document.getElementById('search').value.toLowerCase();
  const setup = document.getElementById('setup-filter').value;
  const status = document.getElementById('status-filter').value;
  const sortBy = document.getElementById('sort-sel').value;
  const gateOnly = document.getElementById('gate-filter').checked;
  const grid = document.getElementById('grid');

  let visible = allCards.filter(c => {{
    if (search && !c.dataset.ticker.toLowerCase().includes(search) &&
        !c.dataset.name.toLowerCase().includes(search)) return false;
    if (setup && !c.dataset.setup.includes(setup)) return false;
    if (status && c.dataset.status !== status) return false;
    if (gateOnly && c.dataset.gate !== '1') return false;
    return true;
  }});

  const sortFn = {{
    score: (a,b) => +b.dataset.score - +a.dataset.score,
    rs: (a,b) => +b.dataset.rs - +a.dataset.rs,
    vol: (a,b) => +b.dataset.vol - +a.dataset.vol,
    atr: (a,b) => +a.dataset.atr - +b.dataset.atr,
    chg: (a,b) => +b.dataset.chg - +a.dataset.chg,
  }}[sortBy] || (() => 0);

  visible.sort(sortFn);

  allCards.forEach(c => c.style.display = 'none');
  visible.forEach(c => {{ c.style.display = ''; grid.appendChild(c); }});

  document.getElementById('count-label').textContent = visible.length + ' stocks';
}}

// Keyboard shortcut
document.addEventListener('keydown', e => {{
  if (e.key === '/') {{ e.preventDefault(); document.getElementById('search').focus(); }}
}});

filter();
</script>
</body>
</html>"""

    output_path.parent.mkdir(exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)


def _render_card(r: dict) -> str:
    score = r.get("composite_score", 0)
    status = r.get("status", "WEAK")
    color = STATUS_COLORS.get(status, "#888")
    ticker = r.get("ticker", "?")
    name = r.get("name", ticker)
    sector = r.get("sector", "")
    price = r.get("price", 0)
    chg = r.get("change_pct", 0)
    vol_ratio = r.get("vol_ratio", 1)
    rs = r.get("rs_percentile", 50)
    atr = r.get("atr_compression", 1)
    ema = r.get("ema_stack", "none")
    level = r.get("breakout_level", "?")
    bull_flag = r.get("bull_flag", False)
    hh_hl = r.get("hh_hl_pct", 0)
    setup = r.get("setup_type", "")
    macd = r.get("macd_curl", False)
    gate = "1" if r.get("passes_gate") else "0"
    rank = r.get("rank", "?")
    pattern_score = r.get("pattern_score", 0)
    flag_score = r.get("bull_flag_score", 0)
    catalyst = r.get("catalyst_freshness", 0)

    chg_cls = "chg-up" if chg >= 0 else "chg-dn"
    chg_str = f"+{chg:.2f}%" if chg >= 0 else f"{chg:.2f}%"
    level_color = LEVEL_COLORS.get(level, "#888")

    ema_color = {"full": "f-green", "partial": "f-green", "weak": "f-amber", "none": "f-red"}.get(ema, "f-red")
    rs_color = "f-green" if rs >= 80 else ("f-amber" if rs >= 60 else "f-red")
    atr_color = "f-green" if atr <= 0.35 else ("f-amber" if atr <= 0.50 else "f-red")
    hh_color = "f-green" if hh_hl >= 0.80 else ("f-amber" if hh_hl >= 0.60 else "f-red")
    vol_color = "f-green" if vol_ratio >= 2 else ("f-amber" if vol_ratio >= 1 else "f-red")

    signals = []
    signals.append(f'<span class="sig sig-{"green" if status=="READY" else "amber" if status=="WATCH" else "blue"}">{status}</span>')
    if bull_flag:
        signals.append('<span class="sig sig-green">Bull Flag</span>')
    if setup:
        signals.append(f'<span class="sig sig-blue">{setup}</span>')
    if catalyst >= 0.5:
        signals.append('<span class="sig sig-amber">Catalyst</span>')
    if vol_ratio >= 3:
        signals.append(f'<span class="sig sig-amber">{vol_ratio:.1f}x Vol</span>')
    if macd:
        signals.append('<span class="sig sig-blue">MACD curl</span>')
    signals_html = "\n".join(signals)

    return f"""<div class="card"
  data-ticker="{ticker}" data-name="{name}" data-score="{score}"
  data-status="{status}" data-setup="{setup} {'Bull Flag' if bull_flag else ''}"
  data-rs="{rs}" data-vol="{vol_ratio}" data-atr="{atr}"
  data-chg="{chg}" data-gate="{gate}">
  <div class="card-top">
    <div>
      <div class="ticker">{ticker}</div>
      <div class="company">{name[:28]}</div>
      <div class="sector">{sector}</div>
    </div>
    <div class="score-badge">
      <div class="score-num" style="color:{color}">{score}</div>
      <div class="score-label" style="color:{color}">{status}</div>
    </div>
  </div>
  <div class="signals">{signals_html}</div>
  <div class="factors">
    <div class="factor"><span class="f-name">RS pct</span><span class="f-val {rs_color}">{rs:.0f}th</span></div>
    <div class="factor"><span class="f-name">ATR comp</span><span class="f-val {atr_color}">{atr:.2f}</span></div>
    <div class="factor"><span class="f-name">EMA stack</span><span class="f-val {ema_color}">{ema}</span></div>
    <div class="factor"><span class="f-name">Level</span><span class="f-val" style="color:{level_color}">{level}</span></div>
    <div class="factor"><span class="f-name">HH/HL</span><span class="f-val {hh_color}">{hh_hl:.0%}</span></div>
    <div class="factor"><span class="f-name">Vol ratio</span><span class="f-val {vol_color}">{vol_ratio:.1f}x</span></div>
    <div class="factor"><span class="f-name">Q score</span><span class="f-val">{r.get('q_score_raw', '—')}</span></div>
    <div class="factor"><span class="f-name">Flag score</span><span class="f-val {'f-green' if flag_score >= 60 else ''}">{flag_score:.0f}</span></div>
    <div class="factor"><span class="f-name">Pattern</span><span class="f-val">{pattern_score:.0f}</span></div>
    <div class="factor"><span class="f-name">Catalyst</span><span class="f-val {'f-green' if catalyst >= 0.7 else ''}">{catalyst:.2f}</span></div>
  </div>
  <div class="card-footer">
    <div>
      <span class="price">${price:,.2f}</span>
      <span class="chg {chg_cls}">{chg_str}</span>
    </div>
    <span class="rank">#{rank}</span>
    <a class="tv-link" href="https://www.tradingview.com/chart/?symbol=NASDAQ:{ticker}" target="_blank">TradingView →</a>
  </div>
</div>"""


def _compute_stats(results: list[dict]) -> dict:
    return {
        "total": len(results),
        "ready": sum(1 for r in results if r.get("status") == "READY"),
        "watch": sum(1 for r in results if r.get("status") == "WATCH"),
        "flags": sum(1 for r in results if r.get("bull_flag")),
        "vol_surges": sum(1 for r in results if r.get("vol_ratio", 0) >= 3),
    }


def _infer_regime(results: list[dict]) -> str:
    if not results:
        return "Unknown"
    # Regime is attached to scan JSON; here we infer from RS distribution
    median_rs = sorted(r.get("rs_percentile", 50) for r in results)[len(results) // 2]
    if median_rs >= 60:
        return "Favorable"
    if median_rs >= 45:
        return "Mixed"
    return "Caution"
