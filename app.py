import json
import yfinance as yf
from flask import Flask, jsonify, request

app = Flask(__name__)

VERSION = "v2.1.0"

FIREBASE_CONFIG = {
    "apiKey": "AIzaSyAi_mL9BbKwwknyOm38B9lL68wI7wwLcaw",
    "authDomain": "stockscanner-f9f81.firebaseapp.com",
    "databaseURL": "https://stockscanner-f9f81-default-rtdb.firebaseio.com",
    "projectId": "stockscanner-f9f81",
    "storageBucket": "stockscanner-f9f81.firebasestorage.app",
    "messagingSenderId": "1066582982090",
    "appId": "1:1066582982090:web:359e1c670b8c3ca8222333"
}

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>NASDAQ Top 10 Scanner {ver}</title>
<style>
:root{{--bg:#0f1117;--bg2:#1a1d26;--bg3:#22263a;--text:#e8eaf0;--muted:#8892a4;--border:#2a2f42;--green:#27ae60;--amber:#e67e22;--blue:#3498db;--red:#e74c3c;--purple:#9b59b6;}}
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;font-size:14px;}}
.header{{background:var(--bg2);border-bottom:1px solid var(--border);padding:14px 24px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px;position:sticky;top:0;z-index:10;}}
.header h1{{font-size:17px;font-weight:600;}}
.header p{{color:var(--muted);font-size:11px;margin-top:2px;}}
.hright{{display:flex;align-items:center;gap:10px;}}
.ver{{font-size:10px;color:var(--muted);background:var(--bg3);border:1px solid var(--border);padding:3px 8px;border-radius:20px;font-family:monospace;}}
.dot{{width:8px;height:8px;border-radius:50%;display:inline-block;margin-right:6px;}}
.dot.g{{background:var(--green);animation:pulse 1.5s infinite;}}
.dot.a{{background:var(--amber);animation:pulse 1.5s infinite;}}
.dot.r{{background:var(--red);}}
.dot.x{{background:var(--muted);}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.3}}}}
.regime{{padding:5px 14px;border-radius:20px;font-size:11px;font-weight:600;}}
.regime.open{{background:#1a3d2b;color:var(--green);border:1px solid #27ae6055;}}
.regime.pre{{background:#1a2a3d;color:var(--blue);border:1px solid #3498db55;}}
.regime.after{{background:#2d1a3d;color:var(--purple);border:1px solid #9b59b655;}}
.regime.closed{{background:var(--bg3);color:var(--muted);border:1px solid var(--border);}}
.sbar{{padding:0 24px;font-size:12px;display:flex;align-items:center;gap:10px;border-bottom:1px solid var(--border);min-height:34px;position:relative;overflow:hidden;}}
.sbar.ok{{background:#1a3d2b33;color:var(--green);}}
.sbar.warn{{background:#3d2e1033;color:var(--amber);}}
.sbar.err{{background:#3d1a1a;color:var(--red);}}
.sbar.conn{{background:var(--bg2);color:var(--muted);}}
.sbar.dl{{background:#1a2a3d55;color:var(--blue);}}
.sbar-progress{{position:absolute;left:0;top:0;height:100%;background:currentColor;opacity:.07;transition:width 2s ease;pointer-events:none;}}
.sbar-dot{{width:7px;height:7px;border-radius:50%;background:currentColor;flex-shrink:0;animation:pulse 1.4s infinite;}}
.sbar-right{{margin-left:auto;font-size:11px;opacity:.65;display:flex;gap:16px;}}
.metrics{{display:flex;gap:10px;padding:12px 24px;flex-wrap:wrap;background:var(--bg2);border-bottom:1px solid var(--border);}}
.metric{{background:var(--bg3);border-radius:8px;padding:8px 14px;min-width:110px;}}
.mlabel{{font-size:10px;color:var(--muted);margin-bottom:3px;text-transform:uppercase;letter-spacing:.5px;}}
.mval{{font-size:19px;font-weight:700;}}
.msub{{font-size:10px;color:var(--muted);margin-top:1px;}}

/* ── Filter panel ── */
.filterpanel{{background:var(--bg2);border-bottom:2px solid var(--border);padding:14px 24px;}}
.filterrow{{display:flex;gap:20px;flex-wrap:wrap;align-items:flex-start;margin-bottom:10px;}}
.filterrow:last-child{{margin-bottom:0;}}
.fgroup{{display:flex;flex-direction:column;gap:6px;}}
.fgrouplabel{{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.8px;font-weight:600;}}
.fchips{{display:flex;gap:5px;flex-wrap:wrap;}}
.fchip{{display:flex;align-items:center;gap:5px;padding:5px 10px;border-radius:20px;border:1px solid var(--border);background:var(--bg3);color:var(--muted);cursor:pointer;font-size:11px;font-weight:500;transition:all .15s;user-select:none;white-space:nowrap;}}
.fchip:hover{{border-color:var(--blue);color:var(--text);transform:translateY(-1px);}}
.fchip.on{{color:#fff;transform:translateY(-1px);box-shadow:0 2px 8px rgba(0,0,0,.3);}}
.fchip.on.green{{background:var(--green);border-color:var(--green);}}
.fchip.on.blue{{background:var(--blue);border-color:var(--blue);}}
.fchip.on.amber{{background:var(--amber);border-color:var(--amber);}}
.fchip.on.purple{{background:var(--purple);border-color:var(--purple);}}
.fchip.on.red{{background:var(--red);border-color:var(--red);}}
.fchip .fcheck{{width:12px;height:12px;border-radius:3px;border:1.5px solid currentColor;display:flex;align-items:center;justify-content:center;font-size:9px;flex-shrink:0;}}
.fchip.on .fcheck::after{{content:'✓';}}
.filteractions{{display:flex;align-items:center;gap:10px;margin-top:6px;}}
.resetbtn{{background:transparent;color:var(--muted);border:1px solid var(--border);border-radius:6px;padding:5px 12px;font-size:11px;cursor:pointer;}}
.resetbtn:hover{{color:var(--red);border-color:var(--red);}}
.activedesc{{font-size:11px;color:var(--blue);flex:1;font-style:italic;}}
.cnt{{font-size:11px;color:var(--muted);margin-left:auto;}}

/* ── Sort bar ── */
.sortrow{{display:flex;align-items:center;gap:10px;padding:8px 24px;background:var(--bg);border-bottom:1px solid var(--border);}}
.sortrow select{{background:var(--bg3);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:5px 8px;font-size:11px;outline:none;cursor:pointer;}}

.alertbox{{background:#1a3d2b;border:1px solid var(--green);border-radius:8px;padding:10px 16px;margin:8px 24px;font-size:12px;color:var(--green);display:none;}}
.grid{{display:flex;flex-wrap:wrap;gap:18px;padding:20px 24px;}}
.card{{background:var(--bg2);border:1px solid var(--border);border-radius:14px;width:480px;border-left:3px solid var(--border);position:relative;overflow:hidden;transition:box-shadow .2s;}}
.card:hover{{box-shadow:0 4px 20px rgba(0,0,0,.3);}}
.card-body{{padding:18px;}}
.card.pre{{border-left-color:var(--green);}}
.card.watch{{border-left-color:var(--amber);}}
.rank{{position:absolute;top:14px;right:14px;width:30px;height:30px;border-radius:50%;background:var(--bg3);display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;color:var(--muted);}}
.rank.top{{background:#1a3d2b;color:var(--green);}}
.ctop{{margin-bottom:8px;padding-right:40px;}}
.ticker{{font-size:20px;font-weight:700;}}
.co{{font-size:11px;color:var(--muted);margin-top:1px;}}
.srow{{display:flex;align-items:center;gap:10px;margin:8px 0;}}
.snum{{font-size:26px;font-weight:700;}}
.smeta{{flex:1;}}
.slbl{{font-size:11px;font-weight:600;letter-spacing:.5px;}}
.sbar2{{height:5px;background:var(--bg3);border-radius:3px;overflow:hidden;margin-top:4px;}}
.sfill{{height:100%;border-radius:3px;}}
.funds{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-bottom:12px;}}
.fbox{{background:var(--bg3);border-radius:7px;padding:10px 8px;text-align:center;}}
.flbl{{font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:3px;}}
.fval{{font-size:14px;font-weight:700;}}
.fsub{{font-size:9px;color:var(--muted);margin-top:1px;}}
.rsiwrap{{margin-bottom:10px;}}
.rsitop{{display:flex;justify-content:space-between;font-size:10px;color:var(--muted);margin-bottom:3px;}}
.rsitrack{{height:8px;background:var(--bg3);border-radius:4px;overflow:hidden;}}
.rsifill{{height:100%;border-radius:4px;transition:width .5s;}}
.rsizones{{display:flex;justify-content:space-between;font-size:9px;color:var(--muted);margin-top:2px;}}
.prox{{margin-bottom:8px;}}
.ptop{{display:flex;justify-content:space-between;font-size:10px;color:var(--muted);margin-bottom:3px;}}
.ptrack{{background:var(--bg3);border-radius:3px;height:5px;}}
.pfill{{height:5px;border-radius:3px;}}
.sigs{{display:flex;gap:4px;flex-wrap:wrap;margin-bottom:8px;}}
.sig{{font-size:10px;font-weight:600;padding:2px 7px;border-radius:20px;}}
.sg{{background:#1a3d2b;color:var(--green);}}
.sa{{background:#3d2e10;color:var(--amber);}}
.sb{{background:#1a2a3d;color:var(--blue);}}
.sp{{background:#2d1a3d;color:var(--purple);}}
.sr{{background:#3d1a1a;color:var(--red);}}
.stitle{{font-size:9px;text-transform:uppercase;letter-spacing:.8px;color:var(--muted);margin-bottom:4px;margin-top:8px;}}
.factors{{display:grid;grid-template-columns:1fr 1fr;gap:2px 14px;font-size:11px;margin-bottom:8px;}}
.factor{{display:flex;justify-content:space-between;padding:2px 0;border-bottom:1px solid var(--border);}}
.fn{{color:var(--muted);}}
.fv{{font-weight:500;}}
.fg{{color:var(--green);}}
.fa{{color:var(--amber);}}
.fr{{color:var(--red);}}
.trade{{background:var(--bg3);border-radius:10px;padding:14px;margin-bottom:12px;border:1px solid #27ae6033;}}
.ttitle{{font-size:10px;text-transform:uppercase;letter-spacing:.8px;color:var(--green);margin-bottom:6px;font-weight:600;}}
.trow{{display:flex;justify-content:space-between;font-size:12px;padding:3px 0;}}
.tl{{color:var(--muted);}}
.tv{{font-weight:600;}}
.rrbadge{{display:inline-block;padding:2px 8px;border-radius:20px;font-size:11px;font-weight:700;background:#1a3d2b;color:var(--green);}}
.cfoot{{display:flex;justify-content:space-between;align-items:center;padding:12px 18px;border-top:1px solid var(--border);}}
.price{{font-size:14px;font-weight:600;}}
.chg{{font-size:11px;margin-left:5px;}}
.cup{{color:var(--green);}}
.cdn{{color:var(--red);}}
.tvlink{{color:var(--blue);font-size:11px;text-decoration:none;}}
.tvlink:hover{{text-decoration:underline;}}
.lookup-panel{{background:var(--bg2);border-bottom:2px solid var(--blue);padding:14px 24px;display:flex;align-items:center;gap:12px;}}
.lookup-icon{{font-size:18px;opacity:.6;}}
.lookup-panel input{{background:var(--bg3);color:var(--text);border:1px solid var(--border);border-radius:8px;padding:10px 16px;font-size:15px;font-weight:700;letter-spacing:2px;outline:none;width:160px;transition:border-color .2s,box-shadow .2s;text-transform:uppercase;}}
.lookup-panel input::placeholder{{font-weight:400;letter-spacing:0;font-size:13px;}}
.lookup-panel input:focus{{border-color:var(--blue);box-shadow:0 0 0 3px #3498db22;}}
.lookup-btn{{background:var(--blue);color:#fff;border:none;border-radius:8px;padding:10px 22px;font-size:13px;font-weight:600;cursor:pointer;transition:background .15s;}}
.lookup-btn:hover{{background:#2980b9;}}
.lookup-divider{{width:1px;height:28px;background:var(--border);flex-shrink:0;}}
.lookup-hint{{font-size:12px;color:var(--muted);}}
.lookup-hint strong{{color:var(--text);}}
.lookup-result{{padding:16px 24px 0;}}
.chart-btn{{background:var(--blue);color:#fff;border:none;border-radius:7px;padding:6px 14px;font-size:11px;font-weight:600;cursor:pointer;transition:background .15s;}}
.chart-btn:hover{{background:#2980b9;}}
.chart-btn.open{{background:var(--bg3);color:var(--blue);border:1px solid var(--blue);}}
.chart-panel{{height:320px;background:#000;position:relative;border-top:1px solid var(--border);display:none;}}
.chart-panel iframe{{width:100%;height:100%;border:none;display:block;}}
.chart-close{{position:absolute;top:8px;right:8px;background:#1a1d26dd;border:1px solid var(--border);color:var(--muted);border-radius:5px;padding:3px 8px;font-size:11px;cursor:pointer;z-index:10;}}
.chart-close:hover{{color:var(--text);}}
.empty{{text-align:center;padding:60px;color:var(--muted);width:100%;font-size:15px;line-height:2;}}
.pgfoot{{padding:14px 24px;color:var(--muted);font-size:11px;border-top:1px solid var(--border);text-align:center;margin-top:8px;}}
@media(max-width:750px){{.card{{width:100%;}}.grid{{padding:10px;gap:10px;}}.filterrow{{gap:12px;}}.filterpanel{{padding:10px 14px;}}}}
</style>
</head>
<body>
<div class="header">
  <div>
    <h1><span class="dot x" id="dot"></span>NASDAQ Pre-Breakout Scanner</h1>
    <p>Scans 2,000+ stocks &middot; Multi-filter &middot; P/E &middot; RSI &middot; Analyst Target &middot; Updates every 60s</p>
  </div>
  <div class="hright">
    <span class="ver" id="verspan">{ver}</span>
    <span class="regime closed" id="regime">&#9679; Connecting...</span>
  </div>
</div>

<div class="sbar conn" id="sbar">
  <div class="sbar-progress" id="sbar-progress" style="width:0%"></div>
  <span class="sbar-dot"></span>
  <span id="smsg">Connecting to Firebase...</span>
  <span class="sbar-right"><span id="sbar-age"></span>&nbsp;<span id="sbar-dur"></span></span>
</div>

<div class="metrics">
  <div class="metric"><div class="mlabel">Total scanned</div><div class="mval" id="m-total">&#8212;</div><div class="msub">full universe</div></div>
  <div class="metric"><div class="mlabel">Pre-breakout</div><div class="mval" style="color:var(--green)" id="m-pre">&#8212;</div><div class="msub">coiled &amp; near trigger</div></div>
  <div class="metric"><div class="mlabel">Ready (72+)</div><div class="mval" style="color:var(--green)" id="m-ready">&#8212;</div><div class="msub">breakout imminent</div></div>
  <div class="metric"><div class="mlabel">Watch (55-71)</div><div class="mval" style="color:var(--amber)" id="m-watch">&#8212;</div><div class="msub">almost ready</div></div>
  <div class="metric"><div class="mlabel">Bull flags</div><div class="mval" style="color:var(--blue)" id="m-flags">&#8212;</div><div class="msub">pole+flag detected</div></div>
  <div class="metric"><div class="mlabel">Last scan</div><div class="mval" style="font-size:13px" id="m-time">&#8212;</div><div class="msub" id="m-sess">&#8212;</div></div>
</div>

<!-- __ Ticker lookup __ -->
<div class="lookup-panel">
  <div class="lookup-icon">&#128269;</div>
  <input type="text" id="lookup-input" placeholder="e.g. NVDA" maxlength="6"
    onkeydown="if(event.key==='Enter')lookupTicker()"
    oninput="this.value=this.value.toUpperCase()">
  <button class="lookup-btn" onclick="lookupTicker()">Analyze</button>
  <div class="lookup-divider"></div>
  <span class="lookup-hint">&#9889; Full analysis on <strong>any stock</strong> &mdash; even outside top 200</span>
</div>
<div id="lookup-wrap" style="display:none"><div class="lookup-result" id="lookup-result"></div></div>

<!-- __ Multi-select filter panel __ -->
<div class="filterpanel">

  <div class="filterrow">
    <!-- Size -->
    <div class="fgroup">
      <div class="fgrouplabel">&#127970; Size</div>
      <div class="fchips">
        <div class="fchip green" data-group="size" data-val="mega" onclick="toggleChip(this)"><span class="fcheck"></span>&#129432; Mega $300+</div>
        <div class="fchip green" data-group="size" data-val="large" onclick="toggleChip(this)"><span class="fcheck"></span>&#128024; Large $80+</div>
        <div class="fchip green" data-group="size" data-val="mid" onclick="toggleChip(this)"><span class="fcheck"></span>&#128002; Mid $20+</div>
        <div class="fchip green" data-group="size" data-val="small" onclick="toggleChip(this)"><span class="fcheck"></span>&#128041; Small &lt;$20</div>
      </div>
    </div>

    <!-- Risk -->
    <div class="fgroup">
      <div class="fgrouplabel">&#9889; Risk Level</div>
      <div class="fchips">
        <div class="fchip blue" data-group="risk" data-val="low" onclick="toggleChip(this)"><span class="fcheck"></span>&#128994; Low ATR</div>
        <div class="fchip blue" data-group="risk" data-val="med" onclick="toggleChip(this)"><span class="fcheck"></span>&#128993; Medium ATR</div>
        <div class="fchip blue" data-group="risk" data-val="high" onclick="toggleChip(this)"><span class="fcheck"></span>&#128308; High ATR</div>
      </div>
    </div>

    <!-- Setup -->
    <div class="fgroup">
      <div class="fgrouplabel">&#128202; Setup Type</div>
      <div class="fchips">
        <div class="fchip amber" data-group="setup" data-val="breakout" onclick="toggleChip(this)"><span class="fcheck"></span>&#128293; Breakout</div>
        <div class="fchip amber" data-group="setup" data-val="catalyst" onclick="toggleChip(this)"><span class="fcheck"></span>&#128197; Catalyst</div>
        <div class="fchip amber" data-group="setup" data-val="bullflag" onclick="toggleChip(this)"><span class="fcheck"></span>&#127987; Bull Flag</div>
        <div class="fchip amber" data-group="setup" data-val="prebreak" onclick="toggleChip(this)"><span class="fcheck"></span>&#9889; Pre-breakout</div>
        <div class="fchip amber" data-group="setup" data-val="earnings" onclick="toggleChip(this)"><span class="fcheck"></span>&#128226; Earnings soon</div>
      </div>
    </div>
  </div>

  <div class="filterrow">
    <!-- Momentum -->
    <div class="fgroup">
      <div class="fgrouplabel">&#128640; Momentum (1 month)</div>
      <div class="fchips">
        <div class="fchip purple" data-group="momentum" data-val="hot" onclick="toggleChip(this)"><span class="fcheck"></span>&#128293; Hot +30%</div>
        <div class="fchip purple" data-group="momentum" data-val="strong" onclick="toggleChip(this)"><span class="fcheck"></span>&#128200; Strong +15%</div>
        <div class="fchip purple" data-group="momentum" data-val="pos" onclick="toggleChip(this)"><span class="fcheck"></span>&#9989; Positive +0%</div>
        <div class="fchip red" data-group="momentum" data-val="neg" onclick="toggleChip(this)"><span class="fcheck"></span>&#128308; Pullback &lt;0%</div>
      </div>
    </div>

    <!-- Quick presets -->
    <div class="fgroup">
      <div class="fgrouplabel">&#9889; Quick Presets</div>
      <div class="fchips">
        <div class="fchip blue" onclick="applyPreset('safe')"><span class="fcheck"></span>&#128739; Safe plays</div>
        <div class="fchip green" onclick="applyPreset('bigtech')"><span class="fcheck"></span>&#128640; Big Tech momentum</div>
        <div class="fchip amber" onclick="applyPreset('earnings')"><span class="fcheck"></span>&#128197; Earnings week</div>
        <div class="fchip purple" onclick="applyPreset('explosive')"><span class="fcheck"></span>&#128293; Explosive small caps</div>
        <div class="fchip" onclick="resetAll()">&#10005; Show all</div>
      </div>
    </div>
  </div>

  <div class="filteractions">
    <span class="activedesc" id="activedesc">Showing all stocks &mdash; select filters above to narrow down</span>
    <span class="cnt" id="cnt"></span>
  </div>
</div>

<div class="sortrow">
  <select id="ssort" onchange="render()">
    <option value="score">Sort: score</option>
    <option value="dist">Sort: nearest trigger</option>
    <option value="atr">Sort: tightest coil</option>
    <option value="vol">Sort: driest volume</option>
    <option value="upside">Sort: analyst upside</option>
    <option value="momentum">Sort: momentum</option>
    <option value="rsi">Sort: RSI</option>
  </select>
</div>

<div class="alertbox" id="alertbox"></div>
<div class="grid" id="grid"><div class="empty">&#9203; Connecting to live scanner...</div></div>
<div class="pgfoot">NASDAQ Pre-Breakout Scanner {ver} &middot; Alpaca + Firebase + GCP VM &middot; &#9888; Not financial advice. Always use stop losses.</div>

<script src="https://www.gstatic.com/firebasejs/9.23.0/firebase-app-compat.js"></script>
<script src="https://www.gstatic.com/firebasejs/9.23.0/firebase-database-compat.js"></script>
<script>
var VER = "{ver}";
var CFG = {cfg};
var connected = false, lastDataTime = null, watchdogTimer = null;
var stockData = {{}}, allStockData = {{}}, prevData = {{}}, seen = {{}};

// ── Filter state — which chips are ON per group ───────────────────────────────
// Empty set = no filter for that group (show all)
var activeFilters = {{ size:[], risk:[], setup:[], momentum:[] }};

function toggleChip(el) {{
  var group = el.dataset.group;
  var val   = el.dataset.val;
  var color = el.classList[1]; // green, blue, amber, purple, red
  el.classList.toggle("on");
  if (el.classList.contains("on")) {{
    if (!activeFilters[group]) activeFilters[group] = [];
    if (!activeFilters[group].includes(val)) activeFilters[group].push(val);
  }} else {{
    activeFilters[group] = activeFilters[group].filter(function(v){{return v!==val;}});
  }}
  render();
}}

function setChip(group, val, on) {{
  var el = document.querySelector('.fchip[data-group="'+group+'"][data-val="'+val+'"]');
  if (!el) return;
  var color = el.classList[1];
  if (on) {{
    el.classList.add("on");
    if (!activeFilters[group]) activeFilters[group] = [];
    if (!activeFilters[group].includes(val)) activeFilters[group].push(val);
  }} else {{
    el.classList.remove("on");
    activeFilters[group] = (activeFilters[group]||[]).filter(function(v){{return v!==val;}});
  }}
}}

function resetAll() {{
  document.querySelectorAll(".fchip[data-group]").forEach(function(c){{c.classList.remove("on");}});
  activeFilters = {{ size:[], risk:[], setup:[], momentum:[] }};
  render();
}}

// ── Quick presets ─────────────────────────────────────────────────────────────
var PRESETS = {{
  safe:      {{ size:["mega","large"], risk:["low","med"], setup:["breakout","prebreak"], momentum:[] }},
  bigtech:   {{ size:["mega","large"], risk:[],            setup:[],                      momentum:["strong","hot"] }},
  earnings:  {{ size:[],              risk:[],            setup:["earnings","catalyst"],  momentum:[] }},
  explosive: {{ size:["small","mid"], risk:["high"],      setup:["bullflag","breakout"],  momentum:["strong","hot"] }},
}};

function applyPreset(name) {{
  resetAll();
  var p = PRESETS[name];
  if (!p) return;
  Object.keys(p).forEach(function(group) {{
    p[group].forEach(function(val) {{ setChip(group, val, true); }});
  }});
  render();
}}

// ── Filter logic ──────────────────────────────────────────────────────────────
function capBucket(price)  {{ return price>=300?"mega":price>=80?"large":price>=20?"mid":"small"; }}
function riskBucket(atr)   {{ return atr<=0.25?"low":atr<=0.5?"med":"high"; }}
function momBucket(mom)    {{ return mom>=30?"hot":mom>=15?"strong":mom>=0?"pos":"neg"; }}

function passesFilters(s) {{
  var price = s.price||0;
  var atr   = s.atr||1;
  var mom   = s.momentum_1m||s.change_pct||0;
  var track = (s.track||"BREAKOUT").toUpperCase();

  // Size — if any size chips selected, stock must match one of them
  if (activeFilters.size.length > 0 && !activeFilters.size.includes(capBucket(price))) return false;

  // Risk — if any risk chips selected, stock must match one of them
  if (activeFilters.risk.length > 0 && !activeFilters.risk.includes(riskBucket(atr))) return false;

  // Momentum — use threshold logic (not exact bucket)
  // hot=30+, strong=15+, pos=0+, neg=<0 — pick the highest selected threshold
  if (activeFilters.momentum.length > 0) {{
    var momOk = false;
    if (activeFilters.momentum.includes("hot")    && mom >= 30)  momOk = true;
    if (activeFilters.momentum.includes("strong")  && mom >= 15)  momOk = true;
    if (activeFilters.momentum.includes("pos")     && mom >= 0)   momOk = true;
    if (activeFilters.momentum.includes("neg")     && mom < 0)    momOk = true;
    if (!momOk) return false;
  }}

  // Setup — if any setup chips selected, stock must match AT LEAST ONE
  if (activeFilters.setup.length > 0) {{
    var setupOk = false;
    if (activeFilters.setup.includes("breakout") && track==="BREAKOUT")  setupOk = true;
    if (activeFilters.setup.includes("catalyst") && track==="CATALYST")  setupOk = true;
    if (activeFilters.setup.includes("bullflag") && s.bull_flag)         setupOk = true;
    if (activeFilters.setup.includes("prebreak") && s.pre_breakout)      setupOk = true;
    if (activeFilters.setup.includes("earnings") && s.earnings_soon)     setupOk = true;
    if (!setupOk) return false;
  }}

  return true;
}}

function getActiveDesc() {{
  var parts = [];
  if (activeFilters.size.length)     parts.push(activeFilters.size.join(" or ").replace(/mega/g,"Mega").replace(/large/g,"Large").replace(/mid/g,"Mid").replace(/small/g,"Small")+" cap");
  if (activeFilters.risk.length)     parts.push(activeFilters.risk.join("/")+"-risk");
  if (activeFilters.setup.length)    parts.push(activeFilters.setup.map(function(v){{return {{breakout:"Breakout",catalyst:"Catalyst",bullflag:"Bull Flag",prebreak:"Pre-breakout",earnings:"Earnings"}}[v]||v;}}).join(" or "));
  if (activeFilters.momentum.length) parts.push({{hot:"Hot +30%",strong:"Strong +15%",pos:"Positive",neg:"Pullback"}}[activeFilters.momentum[0]]||activeFilters.momentum[0]);
  if (!parts.length) return "Showing all stocks \u2014 select filters above to narrow down";
  return "Filters: " + parts.join(" \u00b7 ");
}}

// ── Status helpers ────────────────────────────────────────────────────────────
function setStatus(type, msg, progress, age, dur) {{
  var b=document.getElementById("sbar"); b.className="sbar "+type;
  document.getElementById("smsg").textContent=msg;
  var pg=document.getElementById("sbar-progress"); if(pg)pg.style.width=(progress||0)+"%";
  var ael=document.getElementById("sbar-age"); if(ael)ael.textContent=age||"";
  var del2=document.getElementById("sbar-dur"); if(del2)del2.textContent=dur||"";
}}

function startWatchdog() {{
  clearInterval(watchdogTimer);
  watchdogTimer = setInterval(function() {{
    if (!lastDataTime) return;
    var age = (Date.now()-lastDataTime)/1000;
    var _n2=new Date(),_h2=(_n2.getUTCHours()-4+24)%24,_d2=_n2.getUTCDay();
    var mktOpen2=_d2>=1&&_d2<=5&&_h2>=9&&_h2<16;
    var errT=mktOpen2?600:86400,warnT=mktOpen2?180:3600;
    if (age>errT) {{ setStatus("err","No data for "+Math.round(age/60)+" min \u2014 check GCP VM"); document.getElementById("dot").className="dot r"; }}
    else if (age>120) {{ setStatus("warn","Last update "+Math.round(age/60)+" min ago",0,"",""); document.getElementById("dot").className="dot a"; }}
  }}, 15000);
}}

try {{ firebase.initializeApp(CFG); }} catch(e) {{ setStatus("err","Firebase init: "+e.message,0,"",""); }}
var fdb = firebase.database();

fdb.ref(".info/connected").on("value", function(snap) {{
  connected = snap.val();
  if (connected) {{ setStatus("ok","Connected \u2014 waiting for scanner data..."); document.getElementById("dot").className="dot g"; }}
  else {{ setStatus("err","Lost Firebase connection",0,"",""); document.getElementById("dot").className="dot r"; }}
}});

fdb.ref("/scanner").on("value", function(snap) {{
  var d = snap.val();
  lastDataTime = Date.now();
  if (!d) {{ setStatus("warn","No scanner data yet",0,"",""); return; }}

  // Keep app version in header; show scanner version in status bar only

  var _n=new Date(),_h=(_n.getUTCHours()-4+24)%24,_d=_n.getUTCDay();
  var mktOpen=_d>=1&&_d<=5&&_h>=9&&_h<16;
  var warnThresh=mktOpen?180:3600;
  var dlPct=d.download_progress?d.download_progress.pct||0:0;
  var age = d.last_updated_ts ? Math.round((Date.now()/1000-d.last_updated_ts)) : (d.last_updated ? Math.round((Date.now()-new Date(d.last_updated))/1000) : 0);
  var scanTime = d.last_scan_time ? " \u00b7 "+d.last_scan_time : "";
  var duration = d.scan_duration_sec ? " ("+d.scan_duration_sec+"s)" : "";
  var scanned  = d.stocks_scanned||0;

  if (scanned===0) setStatus("dl","Downloading market data\u2026");
  else if (age>warnThresh) setStatus("warn","Data is "+Math.round(age/60)+" min old"+scanTime,100,"","");
  else setStatus("ok","LIVE \u00b7 "+scanned.toLocaleString()+" stocks \u00b7 Updated "+age+"s ago"+scanTime+duration);

  document.getElementById("m-total").textContent = scanned.toLocaleString();
  document.getElementById("m-pre").textContent    = d.pre_breakout_count||0;
  document.getElementById("m-ready").textContent  = d.ready_count||0;
  document.getElementById("m-watch").textContent  = d.watch_count||0;
  document.getElementById("m-flags").textContent  = d.bull_flag_count||0;
  if (d.last_updated) {{
    var t = new Date(d.last_updated);
    document.getElementById("m-time").textContent = t.toLocaleTimeString([],{{hour:"2-digit",minute:"2-digit"}});
  }}
  if (d.session) document.getElementById("m-sess").textContent = d.session;

  var r=document.getElementById("regime"), dot=document.getElementById("dot"), sess=d.session||"";
  if      (sess.indexOf("Market Open")>=0)  {{ r.textContent="\u25cf Market Open";  r.className="regime open";   if(scanned>0) dot.className="dot g"; }}
  else if (sess.indexOf("Pre-Market")>=0)   {{ r.textContent="\u25d0 Pre-Market";   r.className="regime pre";    dot.className="dot a"; }}
  else if (sess.indexOf("After-Hours")>=0)  {{ r.textContent="\u25d1 After-Hours";  r.className="regime after";  dot.className="dot a"; }}
  else                                       {{ r.textContent="\u25cb Market Closed"; r.className="regime closed"; dot.className="dot x"; }}

  if (d.all_stocks&&Object.keys(d.all_stocks).length>0) allStockData=d.all_stocks;
  else if (d.stocks&&Object.keys(d.stocks).length>0) allStockData=d.stocks;

  if (d.stocks) {{
    var nr = [];
    Object.keys(d.stocks).forEach(function(t) {{
      var s = d.stocks[t];
      if (s.status==="READY" && (!prevData[t]||prevData[t].status!=="READY") && !seen[t+"-r"]) {{ nr.push(t); seen[t+"-r"]=true; }}
      if (s.status!=="READY") delete seen[t+"-r"];
    }});
    if (nr.length) {{
      var ab=document.getElementById("alertbox");
      ab.textContent="NEW READY: "+nr.join(", ")+" \u2014 check TradingView!";
      ab.style.display="block";
      setTimeout(function(){{ab.style.display="none";}},30000);
    }}
    prevData = JSON.parse(JSON.stringify(d.stocks));
    stockData = d.stocks;
  }}
  render();
}}, function(err) {{ setStatus("err","Firebase error: "+err.message,0,"",""); }});

startWatchdog();

// ── Render ────────────────────────────────────────────────────────────────────
function render() {{
  var sortBy   = document.getElementById("ssort").value;
  var grid     = document.getElementById("grid");
  var universe = Object.values(allStockData);
  if (!universe.length) universe = Object.values(stockData);
  if (!universe.length) return;

  // Apply combined filters — get best 10 from matching stocks
  var filtered = universe.filter(passesFilters);

  var fns = {{
    score:    function(a,b){{ return (b.score||0)-(a.score||0); }},
    dist:     function(a,b){{ return (a.dist_to_level||99)-(b.dist_to_level||99); }},
    atr:      function(a,b){{ return (a.atr||1)-(b.atr||1); }},
    vol:      function(a,b){{ return (a.vol_contraction||1)-(b.vol_contraction||1); }},
    momentum: function(a,b){{ return (b.momentum_1m||b.change_pct||0)-(a.momentum_1m||a.change_pct||0); }},
    upside:   function(a,b){{ var ua=(a.analyst_target&&a.price)?(a.analyst_target-a.price)/a.price:0; var ub=(b.analyst_target&&b.price)?(b.analyst_target-b.price)/b.price:0; return ub-ua; }},
    rsi:      function(a,b){{ return (a.rsi||50)-(b.rsi||50); }}
  }};

  filtered.sort(fns[sortBy]||fns.score);
  var top10 = filtered.slice(0,10);

  document.getElementById("activedesc").textContent = getActiveDesc();
  document.getElementById("cnt").textContent = filtered.length+" stocks match \u00b7 showing top 10";

  if (!top10.length) {{
    grid.innerHTML = '<div class="empty">No stocks match this combination.<br><span style="font-size:12px;color:var(--muted)">Try removing some filters or click <strong style="color:var(--blue)">Show all</strong> to reset.</span></div>';
  }} else {{
    grid.innerHTML = top10.map(function(s,i){{return makeCard(s,i+1);}}).join("");
  }}
}}

// ── Card helpers ──────────────────────────────────────────────────────────────
function sc(s)   {{ return s==="READY"?"#27ae60":s==="WATCH"?"#e67e22":"#3498db"; }}
function lc(l)   {{ return l==="ATH"?"#27ae60":(l&&l.indexOf("52")>=0)?"#3498db":"#e67e22"; }}
function ec(e)   {{ return e==="full"?"fg":e==="partial"?"fa":"fr"; }}
function rsiC(v) {{ if(!v||isNaN(v)) return "#8892a4"; return v>=70?"#e74c3c":v>=60?"#e67e22":v<=30?"#9b59b6":"#27ae60"; }}
function rsiL(v) {{ if(!v||isNaN(v)) return "N/A"; return v>=70?"Overbought":v>=60?"Hot":v<=30?"Oversold":"Healthy"; }}
function peC(v)  {{ if(!v||isNaN(v)||v<=0) return "#8892a4"; return v<20?"#27ae60":v<40?"#e67e22":"#e74c3c"; }}

function makeCard(s, rank) {{
  var color  = sc(s.status);
  var dist   = s.dist_to_level||0;
  var prox   = Math.min(100,Math.max(0,100-(dist/5)*100));
  var pc     = prox>80?"#27ae60":prox>60?"#e67e22":"#3498db";
  var chgCls = (s.change_pct||0)>=0?"cup":"cdn";
  var chgStr = ((s.change_pct||0)>=0?"+":"")+(s.change_pct||0).toFixed(2)+"%";
  var isTop  = rank<=3;
  var pe=s.pe_ratio, rsi=s.rsi, target=s.analyst_target, price=s.price||0;
  var upside = (target&&price)?((target-price)/price*100).toFixed(1):null;
  var rsiW   = rsi?Math.min(100,rsi):0;
  var rc     = rsiC(rsi);
  var mom    = s.momentum_1m||0;
  var track  = s.track||"BREAKOUT";

  var base=price>=300?0.018:price>=80?0.024:price>=20?0.032:0.045;
  var dailyAtrPct=Math.min(0.12,Math.max(0.01,base*(s.atr||1)));
  var entryNum=price*1.0025;
  // ATR-based stop as starting point
  var atrStop=Math.min(0.12,Math.max(0.02,dailyAtrPct*1.5));
  // Risk category based on ATR stop (before applying minimums)
  var riskCat,riskColor,riskBg;
  if(atrStop<=0.05){{riskCat='Low';riskColor='#27ae60';riskBg='#1a3d2b';}}
  else if(atrStop<=0.08){{riskCat='Medium';riskColor='#e67e22';riskBg='#3d2e10';}}
  else{{riskCat='High';riskColor='#e74c3c';riskBg='#3d1a1a';}}
  // Apply setup-aware minimum stop — breakout needs room to breathe
  var minStop=riskCat==='Low'?0.05:riskCat==='Medium'?0.07:0.08;
  var stopDist=Math.max(atrStop,minStop);
  var stopNum=entryNum*(1-stopDist),stpPct=(stopDist*100).toFixed(1);
  var rp=0;
  if((s.ema_stack||'')==='full')rp++;
  if((s.hh_hl||0)>=0.8)rp++;
  if((s.vol_contraction||1)<=0.7)rp++;
  if((s.level||'').indexOf('ATH')>=0||(s.level||'').indexOf('multi')>=0)rp++;
  var rewardCat,rewardColor,rewardBg;
  if(rp>=3){{rewardCat='High';rewardColor='#27ae60';rewardBg='#1a3d2b';}}
  else if(rp>=2){{rewardCat='Medium';rewardColor='#e67e22';rewardBg='#3d2e10';}}
  else{{rewardCat='Low';rewardColor='#e74c3c';rewardBg='#3d1a1a';}}
  var rr=riskCat+'/'+rewardCat,setupCat,setupColor,setupBg,setupIcon;
  if(rr==='Low/High'){{setupCat='Best setup';setupColor='#27ae60';setupBg='#1a3d2b';setupIcon='&#11088;';}}
  else if(rr==='Low/Medium'){{setupCat='Good setup';setupColor='#27ae60';setupBg='#1a3d2b';setupIcon='&#9989;';}}
  else if(rr==='Medium/High'){{setupCat='High upside';setupColor='#e67e22';setupBg='#3d2e10';setupIcon='&#127919;';}}
  else if(rr==='Medium/Medium'){{setupCat='Balanced';setupColor='#e67e22';setupBg='#3d2e10';setupIcon='&#128202;';}}
  else if(rr==='High/High'){{setupCat='Aggressive';setupColor='#e67e22';setupBg='#3d2e10';setupIcon='&#127922;';}}
  else if(rr==='Low/Low'){{setupCat='Weak upside';setupColor='#8892a4';setupBg='#22263a';setupIcon='&#128201;';}}
  else{{setupCat='Skip';setupColor='#e74c3c';setupBg='#3d1a1a';setupIcon='&#9888;';}}

  var sigs = '<span class="sig sg">'+s.status+'</span>';
  sigs += track==="CATALYST"?'<span class="sig sp">&#128197; Catalyst</span>':'<span class="sig sb">&#128293; Breakout</span>';
  if(s.earnings_soon)              sigs+='<span class="sig sa">&#128226; Earnings '+(s.days_to_earnings||0)+'d</span>';
  if(s.pre_breakout)               sigs+='<span class="sig sp">&#9889; Pre-breakout</span>';
  if(s.bull_flag)                  sigs+='<span class="sig sg">&#127987; Bull Flag</span>';
  if((s.vol_contraction||1)<=0.7)  sigs+='<span class="sig sb">Vol dry '+Math.round((s.vol_contraction||1)*100)+'%</span>';
  if(dist<=1.5)                    sigs+='<span class="sig sg">'+dist.toFixed(1)+'% to trigger</span>';
  if(mom>=30)                      sigs+='<span class="sig sg">&#128640; +'+mom.toFixed(0)+'% month</span>';
  else if(mom>=15)                 sigs+='<span class="sig sg">&#128200; +'+mom.toFixed(0)+'% month</span>';
  if(rsi&&rsi<=40)                 sigs+='<span class="sig sg">RSI room up</span>';
  if(rsi&&rsi>=70)                 sigs+='<span class="sig sr">RSI overbought</span>';
  if(upside&&parseFloat(upside)>=20) sigs+='<span class="sig sg">+'+upside+'% analyst upside</span>';

  var rsiHTML="";
  if(rsi!=null){{rsiHTML='<div class="rsiwrap"><div class="rsitop"><span>RSI Momentum</span><span style="color:'+rc+';font-weight:600">'+rsi.toFixed(0)+' \u2014 '+rsiL(rsi)+'</span></div><div class="rsitrack"><div class="rsifill" style="width:'+rsiW+'%;background:'+rc+'"></div></div><div class="rsizones"><span style="color:#9b59b6">Oversold 30</span><span>50</span><span style="color:#e67e22">Overbought 70</span></div></div>';}}
  var targetHTML="";

  var h = '';
  h += '<div class="card '+(s.pre_breakout?"pre":s.status==="WATCH"?"watch":"\")+'">';
  h += '<div class="card-body">';
  h += '<div class="rank '+(isTop?"top":"\")+'">' +rank+'</div>';
  h += '<div class="ctop"><div class="ticker">'+s.ticker+'</div>';
  h += '<div class="co">'+(s.name&&s.name!==s.ticker?s.name+' &middot; ':'')+(s.sector||'NASDAQ')+'</div></div>';
  h += '<div class="srow"><div class="snum" style="color:'+color+'">'+(s.score||'&mdash;')+'</div>';
  h += '<div class="smeta"><div class="slbl" style="color:'+color+'">'+s.status+'</div>';
  h += '<div class="sbar2"><div class="sfill" style="width:'+Math.min(100,s.score||0)+'%;background:'+color+'"></div></div></div></div>';
  h += '<div class="funds">';
  h += '<div class="fbox"><div class="flbl">P/E Ratio</div><div class="fval" style="color:'+peC(pe)+'">'+(pe&&pe>0?pe.toFixed(1):'&mdash;')+'</div><div class="fsub">'+(pe&&pe>0?(pe<20?'Cheap':pe<40?'Fair':'Pricey'):'N/A')+'</div></div>';
  h += '<div class="fbox"><div class="flbl">RSI (14)</div><div class="fval" style="color:'+rc+'">'+(rsi!=null?rsi.toFixed(0):'&mdash;')+'</div><div class="fsub">'+rsiL(rsi)+'</div></div>';
  h += '<div class="fbox"><div class="flbl">1Y Target</div><div class="fval" style="color:'+(upside&&parseFloat(upside)>0?'#27ae60':'#8892a4')+'\">'+(target?'$'+target.toFixed(0):'&mdash;')+'</div>';
  h += '<div class="fsub" style="color:'+(upside&&parseFloat(upside)>0?'#27ae60':'#8892a4')+'\">'+(upside?(parseFloat(upside)>=0?'+':'')+upside+'%':'N/A')+'</div></div>';
  h += '</div>';
  h += rsiHTML;
  h += '<div class="prox"><div class="ptop"><span>Distance to breakout trigger</span><span style="color:'+pc+';font-weight:600">'+dist.toFixed(1)+'% away</span></div>';
  h += '<div class="ptrack"><div class="pfill" style="width:'+prox+'%;background:'+pc+'"></div></div></div>';
  h += '<div class="sigs">'+sigs+'</div>';
  h += '<div class="stitle">Technical Factors</div>';
  h += '<div class="factors">';
  h += '<div class="factor"><span class="fn">ATR coil</span><span class="fv '+((s.atr||1)<=0.25?'fg':(s.atr||1)<=0.35?'fa':'fr')+'\">'+(s.atr||0).toFixed(2)+'</span></div>';
  h += '<div class="factor"><span class="fn">Vol contraction</span><span class="fv '+((s.vol_contraction||1)<=0.7?'fg':(s.vol_contraction||1)<=0.9?'fa':'fr')+'\">'+Math.round((s.vol_contraction||1)*100)+'%</span></div>';
  h += '<div class="factor"><span class="fn">RS percentile</span><span class="fv '+((s.rs_percentile||0)>=80?'fg':'')+'\">'+( s.rs_percentile!=null?s.rs_percentile.toFixed(0):'&mdash;')+'th</span></div>';
  h += '<div class="factor"><span class="fn">EMA stack</span><span class="fv '+ec(s.ema_stack)+'\">'+(s.ema_stack||'&mdash;')+'</span></div>';
  h += '<div class="factor"><span class="fn">HH/HL</span><span class="fv '+((s.hh_hl||0)>=0.8?'fg':'fa')+'\">'+Math.round((s.hh_hl||0)*100)+'%</span></div>';
  h += '<div class="factor"><span class="fn">Level</span><span class="fv" style="color:'+lc(s.level)+'\">'+(s.level||'&mdash;')+'</span></div>';
  h += '</div>';
  h += '<div class="trade"><div class="ttitle">Risk / Reward</div>';
  h += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:10px">';
  h += '<div style="background:'+riskBg+';border-radius:8px;padding:12px;text-align:center">';
  h += '<div style="font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">Risk</div>';
  h += '<div style="font-size:20px;font-weight:700;color:'+riskColor+'">'+riskCat+'</div>';
  h += '<div style="font-size:10px;color:'+riskColor+';margin-top:4px">stop '+stpPct+'%</div></div>';
  h += '<div style="background:'+rewardBg+';border-radius:8px;padding:12px;text-align:center">';
  h += '<div style="font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">Reward</div>';
  h += '<div style="font-size:20px;font-weight:700;color:'+rewardColor+'">'+rewardCat+'</div>';
  h += '<div style="font-size:10px;color:'+rewardColor+';margin-top:4px">'+rp+'/4 signals</div></div></div>';
  h += '<div style="background:'+setupBg+';border:1px solid '+setupColor+'44;border-radius:10px;padding:12px 16px;display:flex;justify-content:space-between;align-items:center">';
  h += '<div style="font-size:15px;font-weight:700;color:'+setupColor+'">'+setupIcon+' '+setupCat+'</div>';
  h += '<div style="font-size:11px;color:var(--muted)">Entry $'+entryNum.toFixed(2)+'&nbsp; Stop $'+stopNum.toFixed(2)+'</div></div>';
  h += '</div>';
  h += '</div>';
  h += '<div class="cfoot">';
  h += '<div><span class="price">$'+price.toFixed(2)+'</span><span class="chg '+chgCls+'">'+chgStr+'</span></div>';
  h += '<button class="chart-btn" id="cbtn-'+s.ticker+'" onclick="doChart(this)" data-ticker="'+s.ticker+'">&#128202; Chart</button>';
  h += '</div>';
  h += '<div class="chart-panel" id="cpanel-'+s.ticker+'">';
  h += '<button class="chart-close" data-ticker="'+s.ticker+'" onclick="doClose(this)">&times; Close</button>';
  h += '<iframe id="cframe-'+s.ticker+'" src="" scrolling="no" allowtransparency="true"></iframe>';
  h += '</div>';
  h += '</div>';
  return h;
}}

function doChart(btn) {{
  var t=btn.getAttribute('data-ticker');
  toggleChart(btn,'cpanel-'+t,'cframe-'+t);
}}
function doClose(btn) {{
  var t=btn.getAttribute('data-ticker');
  closeChart(t);
}}
function toggleChart(btn,panelId,frameId) {{
  var panel=document.getElementById(panelId),frame=document.getElementById(frameId);
  var open=panel.style.display==='block';
  if(open){{ panel.style.display='none'; frame.src=''; btn.className='chart-btn'; btn.innerHTML='&#128202; Chart'; }}
  else {{
    panel.style.display='block';
    frame.src='https://s.tradingview.com/widgetembed/?symbol=NASDAQ%3A'+frameId.replace('cframe-','')+'&interval=D&theme=dark&style=1&hide_side_toolbar=0&allow_symbol_change=0&save_image=0&toolbarbg=1a1d26&show_popup_button=0';
    btn.className='chart-btn open'; btn.innerHTML='&times; Close';
  }}
}}
function closeChart(t) {{
  var p=document.getElementById('cpanel-'+t),f=document.getElementById('cframe-'+t),b=document.getElementById('cbtn-'+t);
  if(p)p.style.display='none'; if(f)f.src=''; if(b){{b.className='chart-btn';b.innerHTML='&#128202; Chart';}}
}}
async function lookupTicker() {{
  var ticker=document.getElementById('lookup-input').value.trim().toUpperCase();
  if(!ticker)return;
  var wrap=document.getElementById('lookup-wrap'),result=document.getElementById('lookup-result');
  wrap.style.display='block';
  result.innerHTML='<div style="color:var(--muted);padding:12px 0">&#9203; Fetching '+ticker+'...</div>';
  if(allStockData&&allStockData[ticker]){{result.innerHTML='<div style="color:var(--green);font-size:12px;margin-bottom:8px">&#10003; Found in scanner</div>'+makeCard(allStockData[ticker],'&mdash;');return;}}
  if(stockData&&stockData[ticker]){{result.innerHTML='<div style="color:var(--green);font-size:12px;margin-bottom:8px">&#10003; Found in top 10</div>'+makeCard(stockData[ticker],'&mdash;');return;}}
  try {{
    var resp=await fetch('/lookup?t='+ticker);
    if(!resp.ok)throw new Error('HTTP '+resp.status);
    var data=await resp.json();
    if(data.error)throw new Error(data.error);
    var cl=data.closes,hi=data.highs,lo=data.lows,vo=data.vols;
    var n=cl.length,price=data.price,chg=data.change_pct;
    var trs=[];for(var i=1;i<n;i++)trs.push(Math.max(hi[i]-lo[i],Math.abs(hi[i]-cl[i-1]),Math.abs(lo[i]-cl[i-1])));
    var atr=trs.slice(-14).reduce(function(a,b){{return a+b;}},0)/14;
    function ema(a,p){{var k=2/(p+1),e=a[0];for(var i=1;i<a.length;i++)e=(a[i]||e)*k+e*(1-k);return e;}}
    var e10=ema(cl,10),e20=ema(cl,20),e50=ema(cl.slice(-60),50);
    var es=(e10>e20&&e20>e50&&price>e10)?'full':(price>e20?'partial':'none');
    var hh=0;for(var i=n-20;i<n-1;i++)if(hi[i+1]>hi[i]&&lo[i+1]>lo[i])hh++;
    var vr=vo.slice(-5).reduce(function(a,b){{return a+b;}},0)/5;
    var vb=vo.slice(-20,-5).reduce(function(a,b){{return a+b;}},0)/15;
    var vh=hi.filter(function(v){{return v>0;}}),h52=vh.length?Math.max.apply(null,vh):price;
    var dist=h52>0?((h52-price)/price*100):0,mom=n>=21?((price-cl[n-21])/cl[n-21]*100):0;
    var s={{ticker:ticker,name:data.name||ticker,sector:'',price:price,change_pct:chg,
      score:null,status:'LOOKUP',ema_stack:es,atr:price>0?atr/price:0.03,
      hh_hl:hh/19,vol_contraction:vb>0?vr/vb:1,vol_ratio:vb>0?vr/vb:1,
      level:dist<1?'ATH':dist<5?'52-week':'prior resistance',dist_to_level:dist,
      pre_breakout:(atr/price<=0.03&&vb>0&&vr/vb<=0.7&&dist<=5&&es!=='none'),
      bull_flag:(atr/price<=0.025&&vb>0&&vr/vb<=0.65&&mom>=8&&es!=='none'),
      earnings_soon:false,rs_percentile:null,rsi:null,momentum_1m:mom,
      pe_ratio:data.pe_ratio||null,rsi:data.rsi||null,analyst_target:data.analyst_target||null,
      analyst_upside:data.analyst_upside!=null?String(data.analyst_upside):null,track:'BREAKOUT'}};
    result.innerHTML='<div style="color:var(--amber);font-size:12px;margin-bottom:8px">&#9889; Live lookup &mdash; Yahoo Finance 60d</div>'+makeCard(s,'&mdash;');
  }} catch(e) {{
    result.innerHTML='<div style="color:var(--red);padding:12px 0">Could not fetch <strong>'+ticker+'</strong>: '+e.message+'</div>';
  }}
}}
</script>
</body>
</html>"""

@app.route('/lookup')
def lookup():
    ticker = request.args.get('t','').upper().strip()
    if not ticker or len(ticker) > 6:
        return jsonify({'error': 'Invalid ticker'}), 400
    try:
        tk = yf.Ticker(ticker)
        hist = tk.history(period='60d', interval='1d')
        if hist.empty:
            return jsonify({'error': 'No data found for '+ticker}), 404
        info = tk.info or {}
        fi   = tk.fast_info
        closes = [round(x,2) for x in hist['Close'].tolist()]
        highs  = [round(x,2) for x in hist['High'].tolist()]
        lows   = [round(x,2) for x in hist['Low'].tolist()]
        vols   = hist['Volume'].tolist()
        price  = getattr(fi, 'last_price', None) or closes[-1]
        chg    = round((price - closes[-2]) / closes[-2] * 100, 2) if len(closes) > 1 else 0
        # Fundamentals
        pe          = info.get('trailingPE') or info.get('forwardPE')
        target      = info.get('targetMeanPrice')
        name        = info.get('shortName') or info.get('longName') or ticker
        sector      = info.get('sector','')
        upside      = round((target - price) / price * 100, 1) if target and price else None
        # RSI (14) calculated from closes
        rsi = None
        if len(closes) >= 15:
            deltas = [closes[i]-closes[i-1] for i in range(1,len(closes))]
            gains  = [max(d,0) for d in deltas[-14:]]
            losses = [abs(min(d,0)) for d in deltas[-14:]]
            avg_g  = sum(gains)/14
            avg_l  = sum(losses)/14
            if avg_l > 0:
                rs  = avg_g / avg_l
                rsi = round(100 - 100/(1+rs), 1)
        return jsonify({
            'ticker':     ticker,
            'name':       name,
            'sector':     sector,
            'price':      round(price, 2),
            'change_pct': chg,
            'pe_ratio':   round(pe, 1) if pe else None,
            'rsi':        rsi,
            'analyst_target': round(target, 2) if target else None,
            'analyst_upside': round(upside, 1) if upside is not None else None,
            'closes':     closes,
            'highs':      highs,
            'lows':       lows,
            'vols':       vols,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/')
def index():
    html = HTML.format(
        ver=VERSION,
        cfg=json.dumps(FIREBASE_CONFIG)
    )
    return html

if __name__ == '__main__':
    app.run(debug=True)
