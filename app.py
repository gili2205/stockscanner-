import json
import yfinance as yf
from flask import Flask, jsonify, request

app = Flask(__name__)

VERSION = "v2.4.0"

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
:root{{--bg:#0f1117;--bg2:#1a1d26;--bg3:#22263a;--text:#e8eaf0;--muted:#8892a4;--border:#2a2f42;--green:#27ae60;--amber:#e67e22;--blue:#3498db;--red:#e74c3c;}}
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;font-size:14px;}}
.header{{background:var(--bg2);border-bottom:1px solid var(--border);padding:12px 24px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px;position:sticky;top:0;z-index:100;}}
.header h1{{font-size:16px;font-weight:600;}}.header p{{color:var(--muted);font-size:11px;margin-top:1px;}}
.hright{{display:flex;align-items:center;gap:10px;}}
.ver{{font-size:10px;color:var(--muted);background:var(--bg3);border:1px solid var(--border);padding:3px 8px;border-radius:20px;font-family:monospace;}}
.dot{{width:8px;height:8px;border-radius:50%;display:inline-block;margin-right:4px;}}
.dot.g{{background:var(--green);animation:pulse 1.5s infinite;}}.dot.a{{background:var(--amber);animation:pulse 1.5s infinite;}}.dot.r{{background:var(--red);}}.dot.x{{background:var(--muted);}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.3}}}}
.regime{{padding:4px 12px;border-radius:20px;font-size:11px;font-weight:600;border:1px solid;}}
.regime.open{{background:#1a3d2b;color:var(--green);border-color:#27ae6055;}}.regime.pre{{background:#1a2a3d;color:var(--blue);border-color:#3498db55;}}.regime.after{{background:#2d1a3d;color:#9b59b6;border-color:#9b59b655;}}.regime.closed{{background:var(--bg3);color:var(--muted);border-color:var(--border);}}
.sbar{{padding:0 24px;font-size:12px;display:flex;align-items:center;gap:10px;border-bottom:1px solid var(--border);min-height:32px;position:relative;overflow:hidden;}}
.sbar.ok{{background:#1a3d2b33;color:var(--green);}}.sbar.warn{{background:#3d2e1033;color:var(--amber);}}.sbar.err{{background:#3d1a1a;color:var(--red);}}.sbar.conn{{background:var(--bg2);color:var(--muted);}}.sbar.dl{{background:#1a2a3d55;color:var(--blue);}}
.sbar-dot{{width:7px;height:7px;border-radius:50%;background:currentColor;flex-shrink:0;animation:pulse 1.4s infinite;}}
.sbar-right{{margin-left:auto;font-size:11px;opacity:.65;display:flex;gap:16px;}}
.metrics{{display:flex;gap:10px;padding:12px 24px;flex-wrap:wrap;background:var(--bg2);border-bottom:1px solid var(--border);}}
.metric{{background:var(--bg3);border-radius:8px;padding:8px 14px;min-width:110px;}}
.mlabel{{font-size:10px;color:var(--muted);margin-bottom:3px;text-transform:uppercase;letter-spacing:.5px;}}.mval{{font-size:19px;font-weight:700;}}.msub{{font-size:10px;color:var(--muted);margin-top:1px;}}
.lookup-panel{{background:var(--bg2);border-bottom:2px solid var(--blue);padding:12px 24px;display:flex;align-items:center;gap:12px;}}
.lookup-panel input{{background:var(--bg3);color:var(--text);border:1px solid var(--border);border-radius:8px;padding:9px 14px;font-size:14px;font-weight:600;letter-spacing:1px;outline:none;width:150px;transition:border-color .2s;text-transform:uppercase;}}
.lookup-panel input:focus{{border-color:var(--blue);}}.lookup-btn{{background:var(--blue);color:#fff;border:none;border-radius:8px;padding:9px 18px;font-size:13px;font-weight:600;cursor:pointer;}}.lookup-btn:hover{{background:#2980b9;}}
.lookup-hint{{font-size:12px;color:var(--muted);}}.lookup-hint strong{{color:var(--text);}}
.lookup-result{{padding:14px 24px 0;}}
.filterpanel{{background:var(--bg2);border-bottom:2px solid var(--border);padding:12px 24px;}}
.filterrow{{display:flex;gap:16px;flex-wrap:wrap;align-items:flex-start;margin-bottom:8px;}}.filterrow:last-child{{margin-bottom:0;}}
.fgroup{{display:flex;flex-direction:column;gap:5px;}}.fgrouplabel{{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.8px;font-weight:600;}}
.fchips{{display:flex;gap:4px;flex-wrap:wrap;}}
.fchip{{display:flex;align-items:center;gap:4px;padding:4px 10px;border-radius:20px;border:1px solid var(--border);background:var(--bg3);color:var(--muted);cursor:pointer;font-size:11px;font-weight:500;transition:all .15s;user-select:none;white-space:nowrap;}}
.fchip:hover{{border-color:var(--blue);color:var(--text);}}.fchip.on{{color:#fff;box-shadow:0 2px 6px rgba(0,0,0,.3);}}.fchip.on.green{{background:var(--green);border-color:var(--green);}}.fchip.on.blue{{background:var(--blue);border-color:var(--blue);}}.fchip.on.amber{{background:var(--amber);border-color:var(--amber);}}.fchip.on.purple{{background:#9b59b6;border-color:#9b59b6;}}.fchip.on.red{{background:var(--red);border-color:var(--red);}}
.fchip .fcheck{{width:11px;height:11px;border-radius:2px;border:1.5px solid currentColor;display:flex;align-items:center;justify-content:center;font-size:8px;flex-shrink:0;}}.fchip.on .fcheck::after{{content:'✓';}}
.filteractions{{display:flex;align-items:center;gap:10px;margin-top:6px;}}
.resetbtn{{background:transparent;color:var(--muted);border:1px solid var(--border);border-radius:6px;padding:4px 10px;font-size:11px;cursor:pointer;}}.resetbtn:hover{{color:var(--red);border-color:var(--red);}}
.activedesc{{font-size:11px;color:var(--blue);flex:1;font-style:italic;}}.cnt{{font-size:11px;color:var(--muted);margin-left:auto;}}
.sortrow{{display:flex;align-items:center;gap:10px;padding:8px 24px;background:var(--bg);border-bottom:1px solid var(--border);}}
.sortrow select{{background:var(--bg3);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:4px 8px;font-size:11px;outline:none;cursor:pointer;}}
.alertbox{{background:#1a3d2b;border:1px solid var(--green);border-radius:8px;padding:10px 16px;margin:8px 24px;font-size:12px;color:var(--green);display:none;}}
.grid{{display:flex;flex-direction:column;gap:10px;padding:20px 24px;}}
.card{{background:var(--bg2);border:1px solid var(--border);border-left:3px solid var(--border);border-radius:12px;overflow:hidden;transition:box-shadow .15s;box-shadow:0 2px 8px rgba(0,0,0,.25);}}
.card:hover{{box-shadow:0 4px 16px rgba(0,0,0,.4);}}.card.pre{{border-left-color:var(--green);}}.card.watch{{border-left-color:var(--amber);}}
.card-fold{{display:flex;align-items:center;gap:12px;padding:14px 18px;cursor:pointer;user-select:none;}}.card-fold:hover{{background:#ffffff05;}}
.fold-rank{{width:26px;height:26px;border-radius:50%;background:var(--bg3);display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;color:var(--muted);flex-shrink:0;}}.fold-rank.top{{background:#1a3d2b;color:var(--green);}}
.fold-info{{flex:1;min-width:0;}}.fold-ticker{{font-size:17px;font-weight:700;letter-spacing:-.2px;}}.fold-sub{{font-size:11px;color:var(--muted);margin-top:2px;}}
.fold-metrics{{display:flex;gap:20px;flex-shrink:0;}}
.fold-metric{{text-align:center;min-width:48px;}}.fold-mlbl{{font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:2px;}}.fold-mval{{font-size:14px;font-weight:600;}}.fold-msub{{font-size:10px;margin-top:1px;}}
.fold-score{{text-align:right;flex-shrink:0;margin-left:14px;}}.fold-snum{{font-size:26px;font-weight:700;line-height:1;cursor:pointer;}}.fold-snum:hover{{opacity:.8;}}.fold-slbl{{font-size:10px;font-weight:600;letter-spacing:.5px;margin-top:2px;}}
.score-track{{height:3px;background:var(--bg3);}}.score-fill{{height:100%;transition:width .3s;}}
.card-body{{border-top:1px solid var(--border);padding:16px 18px;display:none;}}.card-body.open{{display:block;}}
.sec-lbl{{font-size:9px;font-weight:600;text-transform:uppercase;letter-spacing:.8px;color:var(--muted);margin-bottom:8px;margin-top:14px;}}.sec-lbl:first-child{{margin-top:0;}}
.factors{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;}}
.fbox{{background:var(--bg3);border-radius:8px;padding:10px 12px;}}.flbl{{font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px;}}.fval{{font-size:15px;font-weight:600;}}.fsub{{font-size:10px;color:var(--muted);margin-top:2px;}}
.fg{{color:var(--green);}}.fa{{color:var(--amber);}}.fr{{color:var(--red);}}
.rr-grid{{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:10px;}}
.rr-box{{border-radius:8px;padding:12px;text-align:center;}}.rr-lbl{{font-size:9px;text-transform:uppercase;letter-spacing:.5px;margin-bottom:5px;opacity:.8;}}.rr-val{{font-size:20px;font-weight:700;}}.rr-sub{{font-size:10px;margin-top:4px;}}
.sig-pills{{display:flex;flex-wrap:wrap;gap:4px;margin-top:6px;justify-content:center;}}
.setup-row{{border-radius:10px;padding:11px 14px;display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;}}
.setup-name{{font-size:14px;font-weight:700;}}.tf-badge{{font-size:11px;font-weight:600;}}
.action-grid{{display:grid;grid-template-columns:1fr 1fr;gap:8px;}}
.action-box{{background:var(--bg3);border-radius:8px;padding:10px 14px;}}.action-lbl{{font-size:9px;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);margin-bottom:4px;}}.action-val{{font-size:18px;font-weight:700;}}.action-sub{{font-size:10px;margin-top:2px;}}
.sigs{{display:flex;gap:4px;flex-wrap:wrap;margin-bottom:8px;}}
.sig{{font-size:10px;font-weight:600;padding:3px 8px;border-radius:20px;}}.sg{{background:#1a3d2b;color:var(--green);}}.sa{{background:#3d2e10;color:var(--amber);}}.sb{{background:#1a2a3d;color:var(--blue);}}.sp{{background:#2d1a3d;color:#9b59b6;}}.sr{{background:#3d1a1a;color:var(--red);}}
.chart-btn{{background:transparent;color:var(--blue);border:1px solid var(--border);border-radius:7px;padding:7px 14px;font-size:11px;font-weight:600;cursor:pointer;margin-top:12px;display:inline-flex;align-items:center;gap:6px;transition:background .15s;}}.chart-btn:hover{{background:var(--bg3);}}.chart-btn.open{{background:var(--bg3);border-color:var(--blue);}}
.chart-panel{{height:320px;background:#000;border-top:1px solid var(--border);display:none;position:relative;}}.chart-panel iframe{{width:100%;height:100%;border:none;display:block;}}
.chart-close{{position:absolute;top:8px;right:8px;background:#1a1d26dd;border:1px solid var(--border);color:var(--muted);border-radius:5px;padding:3px 8px;font-size:10px;cursor:pointer;z-index:10;}}
.breakdown-popup{{position:fixed;z-index:1000;background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:16px;min-width:280px;box-shadow:0 8px 32px rgba(0,0,0,.6);display:none;}}
.bp-title{{font-size:13px;font-weight:700;margin-bottom:12px;}}.bp-row{{display:flex;justify-content:space-between;align-items:center;padding:7px 0;border-bottom:1px solid var(--border);}}.bp-label{{font-size:12px;color:var(--muted);}}.bp-bar{{flex:1;margin:0 10px;height:6px;background:var(--bg3);border-radius:3px;overflow:hidden;}}.bp-fill{{height:100%;border-radius:3px;}}.bp-val{{font-size:12px;font-weight:700;min-width:40px;text-align:right;}}
.cup{{color:var(--green);}}.cdn{{color:var(--red);}}
.empty{{text-align:center;padding:60px;color:var(--muted);font-size:14px;line-height:2;}}
.pgfoot{{padding:14px 24px;color:var(--muted);font-size:11px;border-top:1px solid var(--border);text-align:center;margin-top:8px;}}
@media(max-width:700px){{.grid{{padding:10px;gap:8px;}}.fold-metrics{{display:none;}}.filterpanel{{padding:10px 14px;}}}}
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
    if (Object.keys(d.stocks).length>0) stockData = d.stocks;
  }}
  if (Object.keys(allStockData).length>0 || Object.keys(stockData).length>0) render();
}}, function(err) {{ setStatus("err","Firebase error: "+err.message,0,"",""); }});

startWatchdog();

// ── Render ────────────────────────────────────────────────────────────────────
function render() {{
  var sortBy   = document.getElementById("ssort").value;
  var grid     = document.getElementById("grid");
  var universe = Object.values(allStockData);
  if (!universe.length) universe = Object.values(stockData);
  // Filter out stocks with significantly negative analyst upside
  universe = universe.filter(function(s) {{
    var up = s.analyst_upside!=null?parseFloat(s.analyst_upside):null;
    return up===null || up>-10;
  }});
  if (!universe.length) return;

  // Apply combined filters — get best 10 from matching stocks
  var filtered = universe.filter(passesFilters);

  filtered.forEach(function(s) {{
    var tr=Math.min(16,Math.round((s.rs_percentile||0)/100*16));
    var tv=(s.vol_contraction||1)<=0.5?12:(s.vol_contraction||1)<=0.7?8:(s.vol_contraction||1)<=0.9?4:0;
    var ta=(s.atr||1)<=0.2?8:(s.atr||1)<=0.3?5:(s.atr||1)<=0.4?2:0;
    var tl=(s.level||'').indexOf('ATH')>=0?4:(s.level||'').indexOf('multi')>=0?3:1;
    var e=s.days_to_earnings;
    var ce=e!=null&&e>=0&&e<=7?15:e!=null&&e>=0&&e<=14?10:e!=null&&e>=0&&e<=30?5:0;
    var cv=(s.vol_ratio||1)>=3?10:(s.vol_ratio||1)>=2?6:(s.vol_ratio||1)>=1.5?3:0;
    var cm=(s.momentum_1m||0)>=30?5:(s.momentum_1m||0)>=15?3:(s.momentum_1m||0)>=5?1:0;
    var up=s.analyst_upside!=null?parseFloat(s.analyst_upside):0;
    var bp=s.analyst_buy_pct||0,na=s.num_analysts||0;
    var au=up>=40?12:up>=25?9:up>=10?5:up>0?2:up<-10?-5:0;
    var ab=bp>=80?10:bp>=65?7:bp>=50?4:bp>0?1:0;
    var ac=na>=10?8:na>=5?5:na>=2?2:0;
    s._unified=Math.min(100,Math.round(tr+tv+ta+tl+Math.min(30,ce+cv+cm)+Math.min(30,Math.max(0,au+ab+ac))));
  }});
  var fns = {{
    score:    function(a,b){{ return (b._unified||0)-(a._unified||0); }},
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

var cardBreakdowns = {{}};
var cardBreakdowns = {{}};
function makeCard(s, rank) {{
  if (!s||!s.ticker) return '';
  var price  = s.price||0;
  var chg    = s.change_pct||0;
  var chgCls = chg>=0?'cup':'cdn';
  var chgStr = (chg>=0?'+':'')+chg.toFixed(2)+'%';
  var pe     = s.pe_ratio, rsi=s.rsi, target=s.analyst_target;
  var upside = s.analyst_upside;
  var upsidePct = upside!=null?parseFloat(upside):null;
  var rc    = rsiC(rsi);
  var color = sc(s.status||'BUILDING');
  var isTop = rank<=3;
  var dist  = s.dist_to_level||0;
  var pc    = dist<=1?'#27ae60':dist<=3?'#e67e22':'#e74c3c';
  var buyPct = s.analyst_buy_pct||0;
  var numAna = s.num_analysts||0;
  var earn   = s.days_to_earnings;

  // Unified score
  var t_rs  = Math.min(16,Math.round((s.rs_percentile||0)/100*16));
  var t_vol = (s.vol_contraction||1)<=0.5?12:(s.vol_contraction||1)<=0.7?8:(s.vol_contraction||1)<=0.9?4:0;
  var t_atr = (s.atr||1)<=0.2?8:(s.atr||1)<=0.3?5:(s.atr||1)<=0.4?2:0;
  var t_lvl = (s.level||'').indexOf('ATH')>=0?4:(s.level||'').indexOf('multi')>=0?3:(s.level||'').indexOf('52')>=0?1:0;
  var techScore = t_rs+t_vol+t_atr+t_lvl;
  var c_earn = earn!=null&&earn>=0&&earn<=7?15:earn!=null&&earn>=0&&earn<=14?10:earn!=null&&earn>=0&&earn<=30?5:0;
  var c_vol  = (s.vol_ratio||1)>=3?10:(s.vol_ratio||1)>=2?6:(s.vol_ratio||1)>=1.5?3:0;
  var c_mom  = (s.momentum_1m||0)>=30?5:(s.momentum_1m||0)>=15?3:(s.momentum_1m||0)>=5?1:0;
  var catalystScore = Math.min(30,c_earn+c_vol+c_mom);
  var a_upside = upsidePct!=null?(upsidePct>=40?12:upsidePct>=25?9:upsidePct>=10?5:upsidePct>0?2:upsidePct<-10?-5:0):0;
  var a_buy    = buyPct>=80?10:buyPct>=65?7:buyPct>=50?4:buyPct>0?1:0;
  var a_cov    = numAna>=10?8:numAna>=5?5:numAna>=2?2:0;
  var analystScore = Math.min(30,Math.max(0,a_upside+a_buy+a_cov));
  var unifiedScore = Math.min(100,Math.round(techScore+catalystScore+analystScore));

  // Stop/entry
  var base=price>=300?0.018:price>=80?0.024:price>=20?0.032:0.045;
  var dailyAtrPct=Math.min(0.12,Math.max(0.01,base*(s.atr||1)));
  var entryNum=price*1.0025;
  var atrStop=Math.min(0.12,Math.max(0.02,dailyAtrPct*1.5));
  var minStop=atrStop<=0.05?0.05:atrStop<=0.08?0.07:0.08;
  var stopDist=Math.max(atrStop,minStop);
  var stopNum=entryNum*(1-stopDist),stpPct=(stopDist*100).toFixed(1);

  // Risk/Reward signals
  var sig_rs  = (s.rs_percentile||0)>=80;
  var sig_vol = (s.vol_contraction||1)<=0.7;
  var sig_lvl = (s.level||'').indexOf('ATH')>=0||(s.level||'').indexOf('multi')>=0;
  var sig_ema = (s.ema_stack||'')==='full';
  var rp = (sig_rs?1:0)+(sig_vol?1:0)+(sig_lvl?1:0)+(sig_ema?1:0);
  var riskCat=stopDist<=0.05?'Low':stopDist<=0.08?'Medium':'High';
  var riskColor=riskCat==='Low'?'#27ae60':riskCat==='Medium'?'#e67e22':'#e74c3c';
  var riskBg=riskCat==='Low'?'#1a3d2b':riskCat==='Medium'?'#3d2e10':'#3d1a1a';
  var rewardCat=rp>=3?'High':rp>=2?'Medium':'Low';
  var rewardColor=rp>=3?'#27ae60':rp>=2?'#e67e22':'#e74c3c';
  var rewardBg=rp>=3?'#1a3d2b':rp>=2?'#3d2e10':'#3d1a1a';

  // Timeframe
  var tf = s.timeframe||'mid';
  var tfLabel = tf==='short'?'Short (1-2w)':tf==='long'?'Long (3-12m)':'Mid (1-3m)';
  var tfColor = tf==='short'?'#e74c3c':tf==='long'?'#3498db':'#e67e22';
  var tfIcon  = tf==='short'?'&#9889;':tf==='long'?'&#128336;':'&#128197;';

  // Setup label
  var rr=riskCat+'/'+rewardCat,setupCat,setupColor,setupBg,setupIcon;
  if     (rr==='Low/High')     {{ setupCat='Best setup';  setupColor='#27ae60';setupBg='#1a3d2b';setupIcon='&#11088;'; }}
  else if(rr==='Low/Medium')   {{ setupCat='Good setup';  setupColor='#27ae60';setupBg='#1a3d2b';setupIcon='&#9989;'; }}
  else if(rr==='Medium/High')  {{ setupCat='High upside'; setupColor='#e67e22';setupBg='#3d2e10';setupIcon='&#127919;'; }}
  else if(rr==='Medium/Medium'){{ setupCat='Balanced';    setupColor='#e67e22';setupBg='#3d2e10';setupIcon='&#128202;'; }}
  else if(rr==='High/High')    {{ setupCat='Aggressive';  setupColor='#e67e22';setupBg='#3d2e10';setupIcon='&#127922;'; }}
  else if(rr==='Low/Low')      {{ setupCat='Weak upside'; setupColor='#8892a4';setupBg='#22263a';setupIcon='&#128201;'; }}
  else                         {{ setupCat='Skip';        setupColor='#e74c3c';setupBg='#3d1a1a';setupIcon='&#9888;'; }}

  // Signal chips
  var sigs='';
  if(s.pre_breakout)  sigs+='<span class="sig sp">&#9889; Pre-breakout</span>';
  if(s.bull_flag)     sigs+='<span class="sig sg">&#127987; Bull Flag</span>';
  if((s.vol_contraction||1)<=0.7) sigs+='<span class="sig sb">Vol dry '+Math.round((s.vol_contraction||1)*100)+'%</span>';
  if(earn!=null&&earn>=0&&earn<=14) sigs+='<span class="sig sa">&#128197; Earnings '+earn+'d</span>';
  if((s.momentum_1m||0)>=15) sigs+='<span class="sig sg">&#128640; +'+Math.round(s.momentum_1m)+'% month</span>';
  if(rsi!=null&&rsi>=70) sigs+='<span class="sig sr">RSI overbought</span>';
  if(upsidePct!=null&&upsidePct<-5) sigs+='<span class="sig sr">&#9888; Analyst bearish</span>';

  // Store breakdown data
  var scoreId='sc-'+s.ticker;
  cardBreakdowns[scoreId]={{tech:techScore,cat:catalystScore,ana:analystScore,
    entry:entryNum.toFixed(2),stop:stopNum.toFixed(2),
    tfLabel:tfIcon+' '+tfLabel,tfColor:tfColor}};

  var h = '';
  h += '<div class="card '+(s.pre_breakout?'pre':s.status==='WATCH'?'watch':'')+'">';
  h += '<div class="card-fold" data-card="card-'+s.ticker+'" onclick="toggleCard(this.dataset.card)">';
  h += '<div class="fold-rank '+(isTop?'top':'')+'">'+rank+'</div>';
  h += '<div class="fold-info">';
  h += '<div class="fold-ticker">'+s.ticker;
  if(s.name&&s.name!==s.ticker) h += '<span style="font-size:12px;font-weight:400;color:var(--muted)"> &middot; '+s.name.substring(0,20)+'</span>';
  h += '</div>';
  h += '<div style="font-size:12px;color:var(--muted);margin-top:3px">$'+price.toFixed(2)+'<span class="chg '+chgCls+'"> '+chgStr+'</span>';
  if(s.sector) h += '<span style="color:var(--muted)"> &middot; '+s.sector+'</span>';
  h += '</div></div>';
  h += '<div class="fold-metrics">';
  var tgtCol=upsidePct!=null&&upsidePct>5?'var(--green)':upsidePct!=null&&upsidePct<-5?'var(--red)':'var(--muted)';
  h += '<div class="fold-metric"><div class="fold-mlbl">P/E</div><div class="fold-mval" style="color:'+peC(pe)+'">'+(pe&&pe>0?pe.toFixed(1):'&mdash;')+'</div></div>';
  h += '<div class="fold-metric"><div class="fold-mlbl">RSI</div><div class="fold-mval" style="color:'+rc+'">'+(rsi!=null?rsi.toFixed(0):'&mdash;')+'</div></div>';
  h += '<div class="fold-metric"><div class="fold-mlbl">1Y Target</div><div class="fold-mval" style="color:'+tgtCol+'">'+(target?'$'+target.toFixed(0):'&mdash;')+'</div>'+(upsidePct!=null?'<div class="fold-msub" style="color:'+tgtCol+'">'+(upsidePct>=0?'+':'')+upsidePct.toFixed(1)+'%</div>':'')+'</div>';
  h += '</div>';
  h += '<div style="text-align:right;flex-shrink:0;margin-left:14px">';
  h += '<div id="'+scoreId+'" style="font-size:26px;font-weight:700;color:'+color+';cursor:pointer;line-height:1" onclick="event.stopPropagation();showBreakdown(this)">'+unifiedScore+'</div>';
  h += '<div style="font-size:10px;font-weight:600;letter-spacing:.5px;color:'+color+';margin-top:3px">'+s.status+'</div>';
  h += '</div></div>';
  h += '<div class="score-track"><div class="score-fill" style="width:'+Math.min(100,unifiedScore)+'%;background:'+color+'"></div></div>';
  h += '<div class="card-body" id="card-'+s.ticker+'">';
  h += '<div class="funds" style="margin-top:14px">';
  h += '<div class="fbox"><div class="flbl">P/E Ratio</div><div class="fval" style="color:'+peC(pe)+'">'+(pe&&pe>0?pe.toFixed(1):'&mdash;')+'</div><div class="fsub">'+(pe&&pe>0?(pe<20?'Cheap':pe<40?'Fair':'Pricey'):'N/A')+'</div></div>';
  h += '<div class="fbox"><div class="flbl">RSI (14)</div><div class="fval" style="color:'+rc+'">'+(rsi!=null?rsi.toFixed(0):'&mdash;')+'</div><div class="fsub">'+rsiL(rsi)+'</div></div>';
  h += '<div class="fbox"><div class="flbl">1Y Target</div><div class="fval" style="color:'+(upsidePct!=null&&upsidePct>0?'#27ae60':'#8892a4')+'">'+(target?'$'+target.toFixed(0):'&mdash;')+'</div><div class="fsub" style="color:'+(upsidePct!=null&&upsidePct>0?'#27ae60':upsidePct!=null&&upsidePct<0?'#e74c3c':'#8892a4')+'">'+(upsidePct!=null?(upsidePct>=0?'+':'')+upsidePct+'%':'N/A')+'</div></div>';
  h += '</div>';
  if(buyPct>0||numAna>0) {{
    h += '<div style="font-size:11px;color:var(--muted);padding:6px 0;display:flex;gap:14px;flex-wrap:wrap">';
    if(numAna>0) h += '<span>&#128101; '+numAna+' analysts</span>';
    if(buyPct>0) h += '<span style="color:'+(buyPct>=70?'#27ae60':buyPct>=50?'#e67e22':'#e74c3c')+'">&#128200; '+buyPct+'% Buy</span>';
    if(s.recommendation) h += '<span style="text-transform:capitalize">Consensus: '+s.recommendation+'</span>';
    h += '</div>';
  }}
  if(sigs) h += '<div class="sigs">'+sigs+'</div>';
  h += '<div class="sec-lbl">Technical Factors</div>';
  h += '<div class="factors">';
  h += '<div class="factor"><span class="fn">ATR coil</span><span class="fv '+((s.atr||1)<=0.25?'fg':(s.atr||1)<=0.35?'fa':'fr')+'">'+(s.atr||0).toFixed(2)+'</span></div>';
  h += '<div class="factor"><span class="fn">Vol contraction</span><span class="fv '+((s.vol_contraction||1)<=0.7?'fg':(s.vol_contraction||1)<=0.9?'fa':'fr')+'">'+Math.round((s.vol_contraction||1)*100)+'%</span></div>';
  h += '<div class="factor"><span class="fn">RS percentile</span><span class="fv '+((s.rs_percentile||0)>=80?'fg':'')+'">'+( s.rs_percentile!=null?s.rs_percentile.toFixed(0):'&mdash;')+'th</span></div>';
  h += '<div class="factor"><span class="fn">EMA stack</span><span class="fv '+ec(s.ema_stack)+'">'+(s.ema_stack||'&mdash;')+'</span></div>';
  h += '<div class="factor"><span class="fn">Level</span><span class="fv" style="color:'+lc(s.level)+'">'+(s.level||'&mdash;')+'</span></div>';
  h += '<div class="factor"><span class="fn">Distance</span><span class="fv" style="color:'+pc+'">'+dist.toFixed(1)+'%</span></div>';
  h += '</div>';
  h += '<div class="trade"><div class="ttitle">Risk / Reward</div>';
  h += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:10px">';
  h += '<div style="background:'+riskBg+';border-radius:8px;padding:10px;text-align:center">';
  h += '<div style="font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">Risk</div>';
  h += '<div style="font-size:18px;font-weight:700;color:'+riskColor+'">'+riskCat+'</div>';
  h += '<div style="font-size:10px;color:'+riskColor+';margin-top:3px">stop '+stpPct+'%</div></div>';
  h += '<div style="background:'+rewardBg+';border-radius:8px;padding:10px;text-align:center">';
  h += '<div style="font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">Reward</div>';
  h += '<div style="font-size:18px;font-weight:700;color:'+rewardColor+'">'+rewardCat+'</div>';
  h += '<div style="display:flex;flex-wrap:wrap;gap:3px;margin-top:5px;justify-content:center">';
  h += '<span style="font-size:9px;padding:2px 5px;border-radius:8px;background:'+(sig_rs?'#1a3d2b':'#22263a')+';color:'+(sig_rs?'#27ae60':'#4a5568')+'">RS&gt;80</span>';
  h += '<span style="font-size:9px;padding:2px 5px;border-radius:8px;background:'+(sig_vol?'#1a3d2b':'#22263a')+';color:'+(sig_vol?'#27ae60':'#4a5568')+'">Vol dry</span>';
  h += '<span style="font-size:9px;padding:2px 5px;border-radius:8px;background:'+(sig_lvl?'#1a3d2b':'#22263a')+';color:'+(sig_lvl?'#27ae60':'#4a5568')+'">ATH</span>';
  h += '<span style="font-size:9px;padding:2px 5px;border-radius:8px;background:'+(sig_ema?'#1a3d2b':'#22263a')+';color:'+(sig_ema?'#27ae60':'#4a5568')+'">EMA</span>';
  h += '</div></div></div>';
  h += '<div style="background:'+setupBg+';border:1px solid '+setupColor+'44;border-radius:10px;padding:12px 14px">';
  h += '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">';
  h += '<div style="font-size:14px;font-weight:700;color:'+setupColor+'">'+setupIcon+' '+setupCat+'</div>';
  h += '<div style="font-size:11px;color:'+tfColor+';font-weight:600">'+tfIcon+' '+tfLabel+'</div>';
  h += '</div>';
  h += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">';
  h += '<div style="background:var(--bg2);border-radius:7px;padding:8px 12px">';
  h += '<div style="font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:3px">Buy above</div>';
  h += '<div style="font-size:16px;font-weight:700;color:#27ae60">$'+entryNum.toFixed(2)+'</div></div>';
  h += '<div style="background:var(--bg2);border-radius:7px;padding:8px 12px">';
  h += '<div style="font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:3px">Stop loss</div>';
  h += '<div style="font-size:16px;font-weight:700;color:#e74c3c">$'+stopNum.toFixed(2)+'</div>';
  h += '<div style="font-size:10px;color:#e74c3c;margin-top:1px">-'+stpPct+'%</div></div>';
  h += '</div></div>';
  h += '</div>';
  h += '<div class="cfoot">';
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

<div class="breakdown-popup" id="breakdown-popup">
  <div class="bp-close" onclick="document.getElementById('breakdown-popup').classList.remove('show')">&#10005;</div>
  <div class="bp-title">Score Breakdown</div>
  <div class="bp-row">
    <span class="bp-label">&#128202; Technical</span>
    <div class="bp-bar"><div class="bp-fill" id="bp-tech-bar" style="background:#3498db"></div></div>
    <span class="bp-val" id="bp-tech"></span>
  </div>
  <div class="bp-row">
    <span class="bp-label">&#9889; Catalyst</span>
    <div class="bp-bar"><div class="bp-fill" id="bp-cat-bar" style="background:#e67e22"></div></div>
    <span class="bp-val" id="bp-cat"></span>
  </div>
  <div class="bp-row">
    <span class="bp-label">&#128101; Analyst</span>
    <div class="bp-bar"><div class="bp-fill" id="bp-ana-bar" style="background:#27ae60"></div></div>
    <span class="bp-val" id="bp-ana"></span>
  </div>
  <div style="margin-top:12px;padding-top:10px;border-top:1px solid var(--border)">
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
      <div style="background:var(--bg3);border-radius:7px;padding:8px 10px">
        <div style="font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:3px">Buy above</div>
        <div style="font-size:15px;font-weight:700;color:#27ae60" id="bp-entry"></div>
      </div>
      <div style="background:var(--bg3);border-radius:7px;padding:8px 10px">
        <div style="font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:3px">Stop loss</div>
        <div style="font-size:15px;font-weight:700;color:#e74c3c" id="bp-stop"></div>
      </div>
    </div>
    <div style="margin-top:8px;font-size:12px;font-weight:600" id="bp-tf"></div>
  </div>
</div>
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
