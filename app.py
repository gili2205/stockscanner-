import os
import json
import requests
import yfinance as yf
from flask import Flask, jsonify, request

app = Flask(__name__)

VERSION = "v3.2.0"

FIREBASE_CONFIGS = {
    "production": {
        "apiKey": "AIzaSyAi_mL9BbKwwknyOm38B9lL68wI7wwLcaw",
        "authDomain": "stockscanner-f9f81.firebaseapp.com",
        "databaseURL": "https://stockscanner-f9f81-default-rtdb.firebaseio.com",
        "projectId": "stockscanner-f9f81",
        "storageBucket": "stockscanner-f9f81.firebasestorage.app",
        "messagingSenderId": "1066582982090",
        "appId": "1:1066582982090:web:359e1c670b8c3ca8222333"
    },
    "staging": {
        "apiKey": "AIzaSyA-zd6GX6QB_-q0x2HvVUSdYVsjtNqcuTk",
        "authDomain": "stockscanner-staging.firebaseapp.com",
        "databaseURL": "https://stockscanner-staging-default-rtdb.firebaseio.com",
        "projectId": "stockscanner-staging",
        "storageBucket": "stockscanner-staging.firebasestorage.app",
        "messagingSenderId": "342956679780",
        "appId": "1:342956679780:web:573fc062c897cbb3e8b571"
    }
}

FLASK_ENV = os.environ.get("FLASK_ENV", "production")
FIREBASE_CONFIG = FIREBASE_CONFIGS.get(FLASK_ENV, FIREBASE_CONFIGS["production"])

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>NASDAQ Top 10 Scanner {ver}</title>
<style>
:root{{--bg:#0f1117;--bg2:#1a1d26;--bg3:#22263a;--text:#e8eaf0;--muted:#8892a4;--border:#2a2f42;--green:#27ae60;--amber:#e67e22;--blue:#3498db;--red:#e74c3c;}}
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;font-size:14px;}}
.header{{background:var(--bg2);border-bottom:1px solid var(--border);padding:12px 24px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px;position:sticky;top:0;z-index:100;min-height:56px;}}
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
.fchip:hover{{border-color:var(--blue);color:var(--text);}}.fchip.on{{color:#fff;box-shadow:0 2px 6px rgba(0,0,0,.3);}}.fchip.on.green{{background:var(--green);border-color:var(--green);}}.fchip.on.blue{{background:var(--blue);border-color:var(--blue);}}.fchip.on.amber{{background:var(--amber);border-color:var(--amber);}}.fchip.on.purple{{background:#9b59b6;border-color:#9b59b6;}}.fchip.on.red{{background:var(--red);border-color:var(--red);}}.fchip.on.teal{{background:#1abc9c;border-color:#1abc9c;}}
.fchip .fcheck{{width:11px;height:11px;border-radius:2px;border:1.5px solid currentColor;display:flex;align-items:center;justify-content:center;font-size:8px;flex-shrink:0;}}.fchip.on .fcheck::after{{content:'✓';}}
.filteractions{{display:flex;align-items:center;gap:10px;margin-top:6px;}}
.resetbtn{{background:transparent;color:var(--muted);border:1px solid var(--border);border-radius:6px;padding:4px 10px;font-size:11px;cursor:pointer;}}.resetbtn:hover{{color:var(--red);border-color:var(--red);}}
.activedesc{{font-size:11px;color:var(--blue);flex:1;font-style:italic;}}.cnt{{font-size:11px;color:var(--muted);margin-left:auto;}}
.sortrow{{display:flex;align-items:center;gap:10px;padding:8px 24px;background:var(--bg);border-bottom:1px solid var(--border);}}
.sortrow select{{background:var(--bg3);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:4px 8px;font-size:11px;outline:none;cursor:pointer;}}
.alertbox{{background:#1a3d2b;border:1px solid var(--green);border-radius:8px;padding:10px 16px;margin:8px 24px;font-size:12px;color:var(--green);display:none;}}
.grid{{display:flex;flex-direction:column;gap:16px;padding:20px 24px;}}
.card{{background:var(--bg2);border:1px solid var(--border);border-left:4px solid var(--border);border-radius:14px;overflow:hidden;transition:box-shadow .2s;box-shadow:0 4px 16px rgba(0,0,0,.35);}}
.card:hover{{box-shadow:0 8px 24px rgba(0,0,0,.5);}}
.card.pre{{border-left-color:var(--green);}}
.card.watch{{border-left-color:var(--amber);}}
.card-header{{display:block;padding:18px 20px;cursor:pointer;user-select:none;}}
.card-header:hover{{background:#ffffff05;}}

.card-rank{{width:32px;height:32px;border-radius:50%;background:var(--bg3);display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:700;color:var(--muted);flex-shrink:0;}}
.card-rank.top{{background:#1a3d2b;color:var(--green);}}
.card-score-block{{text-align:right;}}
.msl{{margin-left:6px;}}
.sec-title{{font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.8px;color:var(--muted);margin:14px 0 8px;}}
.card-fold{{display:flex;align-items:center;gap:12px;padding:14px 18px;cursor:pointer;user-select:none;}}.card-fold:hover{{background:#ffffff05;}}
.fold-rank{{width:26px;height:26px;border-radius:50%;background:var(--bg3);display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;color:var(--muted);flex-shrink:0;}}.fold-rank.top{{background:#1a3d2b;color:var(--green);}}
.fold-info{{flex:1;min-width:0;}}.fold-ticker{{font-size:17px;font-weight:700;letter-spacing:-.2px;}}.fold-sub{{font-size:11px;color:var(--muted);margin-top:2px;}}
.fold-metrics{{display:flex;gap:20px;flex-shrink:0;}}
.fold-metric{{text-align:center;min-width:48px;}}.fold-mlbl{{font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:2px;}}.fold-mval{{font-size:14px;font-weight:600;}}.fold-msub{{font-size:10px;margin-top:1px;}}
.fold-score{{text-align:right;flex-shrink:0;margin-left:14px;}}.fold-snum{{font-size:26px;font-weight:700;line-height:1;cursor:pointer;}}.fold-snum:hover{{opacity:.8;}}.fold-slbl{{font-size:10px;font-weight:600;letter-spacing:.5px;margin-top:2px;}}
.rank-badge{{width:32px;height:32px;border-radius:50%;background:var(--bg3);display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:700;color:var(--muted);}}
.rank-badge.top{{background:#1a3d2b;color:var(--green);}}
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
.nav-pills{{display:flex;gap:6px;align-items:center;}}
.nav-pill{{padding:5px 14px;border-radius:20px;font-size:12px;font-weight:600;text-decoration:none;border:1px solid var(--border);color:var(--muted);transition:all .15s;background:var(--bg3);}}
.nav-pill:hover{{color:var(--text);border-color:var(--blue);}}
.nav-pill.active{{background:var(--blue);color:#fff;border-color:var(--blue);}}
.mcap-badge{{font-size:11px;padding:2px 8px;border-radius:10px;background:var(--bg3);color:var(--muted);border:1px solid var(--border);vertical-align:middle;margin-left:6px;font-weight:400;}}
.perf-row{{display:flex;border-top:1px solid var(--border);margin-top:10px;padding-top:10px;}}
.perf-item{{flex:1;text-align:center;border-right:1px solid var(--border);}}
.perf-item:last-child{{border-right:none;}}
.perf-lbl{{font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:3px;}}
.perf-val{{font-size:13px;font-weight:600;}}
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
    <div class="nav-pills"><a class="nav-pill active" href="/">&#128202; Dashboard</a><a class="nav-pill" href="/analytics">&#128200; Analytics</a><a class="nav-pill" href="/smart-money">&#127974; Smart Money</a><a class="nav-pill" href="/optimizer">&#128202; Optimizer</a></div>
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
        <div class="fchip green" data-group="size" data-val="mega" onclick="toggleChip(this)"><span class="fcheck"></span>&#129432; Mega &gt;$200B</div>
        <div class="fchip green" data-group="size" data-val="large" onclick="toggleChip(this)"><span class="fcheck"></span>&#128024; Large $10B-$200B</div>
        <div class="fchip green" data-group="size" data-val="mid" onclick="toggleChip(this)"><span class="fcheck"></span>&#128002; Mid $2B-$10B</div>
        <div class="fchip green" data-group="size" data-val="small" onclick="toggleChip(this)"><span class="fcheck"></span>&#128041; Small &lt;$2B</div>
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
    <!-- Sector -->
    <div class="fgroup">
      <div class="fgrouplabel">&#127970; Sector</div>
      <div class="fchips">
        <div class="fchip teal" data-group="sector" data-val="Technology" onclick="toggleChip(this)"><span class="fcheck"></span>&#128187; Tech</div>
        <div class="fchip teal" data-group="sector" data-val="Healthcare" onclick="toggleChip(this)"><span class="fcheck"></span>&#127973; Health</div>
        <div class="fchip teal" data-group="sector" data-val="Financial Services" onclick="toggleChip(this)"><span class="fcheck"></span>&#127970; Finance</div>
        <div class="fchip teal" data-group="sector" data-val="Consumer Cyclical" onclick="toggleChip(this)"><span class="fcheck"></span>&#128717; Consumer</div>
        <div class="fchip teal" data-group="sector" data-val="Industrials" onclick="toggleChip(this)"><span class="fcheck"></span>&#9881; Industrial</div>
        <div class="fchip teal" data-group="sector" data-val="Communication Services" onclick="toggleChip(this)"><span class="fcheck"></span>&#128225; Telecom</div>
        <div class="fchip teal" data-group="sector" data-val="Energy" onclick="toggleChip(this)"><span class="fcheck"></span>&#9889; Energy</div>
        <div class="fchip teal" data-group="sector" data-val="Real Estate" onclick="toggleChip(this)"><span class="fcheck"></span>&#127968; Real Estate</div>
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

    <!-- Days on list -->
    <div class="fgroup">
      <div class="fgrouplabel">&#128197; On the list</div>
      <div class="fchips">
        <div class="fchip blue" data-group="streak" data-val="new" onclick="toggleChip(this)"><span class="fcheck"></span>New today</div>
        <div class="fchip" data-group="streak" data-val="fresh" onclick="toggleChip(this)"><span class="fcheck"></span>1-5 days</div>
        <div class="fchip amber" data-group="streak" data-val="building" onclick="toggleChip(this)"><span class="fcheck"></span>6-14 days</div>
        <div class="fchip green" data-group="streak" data-val="proven" onclick="toggleChip(this)"><span class="fcheck"></span>15+ days</div>
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
var stockData = {{}}, allStockData = {{}}, prevData = {{}}, seen = {{}}, firstSeenData = {{}};

// ── Filter state — which chips are ON per group ───────────────────────────────
// Empty set = no filter for that group (show all)
var activeFilters = {{ size:[], risk:[], setup:[], momentum:[], sector:[], streak:[] }};

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
  activeFilters = {{ size:[], risk:[], setup:[], momentum:[], sector:[], streak:[] }};
  render();
}}

// ── Quick presets ─────────────────────────────────────────────────────────────
var PRESETS = {{
  safe:      {{ size:["mega","large"], risk:["low","med"], setup:["breakout","prebreak"], momentum:[], sector:[], streak:[] }},
  bigtech:   {{ size:["mega","large"], risk:[],            setup:[],                      momentum:["strong","hot"], sector:[], streak:[] }},
  earnings:  {{ size:[],              risk:[],            setup:["earnings","catalyst"],  momentum:[], sector:[], streak:[] }},
  explosive: {{ size:["small","mid"], risk:["high"],      setup:["bullflag","breakout"],  momentum:["strong","hot"], sector:[], streak:[] }},
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
// Parse "4.6B" → 4.6e9, "1.2T" → 1.2e12, "500M" → 500e6
function parseMcap(str) {{
  if (!str) return 0;
  var s = String(str).trim();
  var n = parseFloat(s);
  if (isNaN(n)) return 0;
  if (s.indexOf("T")>=0) return n*1e12;
  if (s.indexOf("B")>=0) return n*1e9;
  if (s.indexOf("M")>=0) return n*1e6;
  return n;
}}
// Bucket by market cap (uses s.market_cap if present, otherwise falls back to price)
function capBucket(s) {{
  var mc = parseMcap(s.market_cap);
  if (mc >= 200e9) return "mega";
  if (mc >= 10e9)  return "large";
  if (mc >= 2e9)   return "mid";
  if (mc > 0)      return "small";
  // Fallback: price-based buckets when market_cap not yet populated
  var p = s.price || 0;
  return p>=300?"mega":p>=80?"large":p>=20?"mid":"small";
}}
function riskBucket(atr)   {{ return atr<=0.25?"low":atr<=0.5?"med":"high"; }}
function momBucket(mom)    {{ return mom>=30?"hot":mom>=15?"strong":mom>=0?"pos":"neg"; }}

function passesFilters(s) {{
  var atr   = s.atr||1;
  var mom   = s.momentum_1m||s.change_pct||0;
  var track = (s.track||"BREAKOUT").toUpperCase();
  var earn  = s.days_to_earnings;

  // Size — if any size chips selected, stock must match one of them (uses market cap)
  if (activeFilters.size.length > 0 && !activeFilters.size.includes(capBucket(s))) return false;

  // Risk — if any risk chips selected, stock must match one of them
  if (activeFilters.risk.length > 0 && !activeFilters.risk.includes(riskBucket(atr))) return false;

  // Sector — if any sector chips selected, stock must match one of them
  if (activeFilters.sector && activeFilters.sector.length > 0) {{
    var stockSector = s.sector || "";
    if (!activeFilters.sector.includes(stockSector)) return false;
  }}

  // Streak — filter by how many days the stock has been on the list
  if (activeFilters.streak && activeFilters.streak.length > 0) {{
    var fs = firstSeenData[s.ticker];
    var days = null;
    if (fs && fs.date) {{
      var d0 = new Date(fs.date+'T00:00:00'), d1 = new Date(); d1.setHours(0,0,0,0);
      days = Math.round((d1-d0)/86400000);
    }}
    var streakOk = false;
    if (activeFilters.streak.includes("new")      && days === 0)           streakOk = true;
    if (activeFilters.streak.includes("fresh")    && days !== null && days >= 1 && days <= 5)  streakOk = true;
    if (activeFilters.streak.includes("building") && days !== null && days >= 6 && days <= 14) streakOk = true;
    if (activeFilters.streak.includes("proven")   && days !== null && days >= 15)              streakOk = true;
    if (!streakOk) return false;
  }}

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
    if (activeFilters.setup.includes("earnings") && (s.earnings_soon || (earn!=null && earn>=0 && earn<=14))) setupOk = true;
    if (!setupOk) return false;
  }}

  return true;
}}

function getActiveDesc() {{
  var parts = [];
  if (activeFilters.size.length)     parts.push(activeFilters.size.join(" or ").replace(/mega/g,"Mega").replace(/large/g,"Large").replace(/mid/g,"Mid").replace(/small/g,"Small")+" cap");
  if (activeFilters.risk.length)     parts.push(activeFilters.risk.join("/")+"-risk");
  if (activeFilters.sector && activeFilters.sector.length) parts.push(activeFilters.sector.join(" or "));
  if (activeFilters.streak && activeFilters.streak.length) parts.push(activeFilters.streak.map(function(v){{return {{new:"New today",fresh:"1-5 days",building:"6-14 days",proven:"15+ days"}}[v]||v;}}).join(" or ")+" on list");
  if (activeFilters.setup.length)    parts.push(activeFilters.setup.map(function(v){{return {{breakout:"Breakout",catalyst:"Catalyst",bullflag:"Bull Flag",prebreak:"Pre-breakout",earnings:"Earnings soon"}}[v]||v;}}).join(" or "));
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
  if (d.first_seen) firstSeenData = d.first_seen;

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
  // Save which cards are open before rebuild
  var openCards = {{}};
  document.querySelectorAll('.card-body').forEach(function(b) {{
    if(b.style.display==='block') openCards[b.id]=true;
  }});
  grid.innerHTML = top10.map(function(s,i){{return makeCard(s,i+1);}}).join("");
  // Restore open cards
  Object.keys(openCards).forEach(function(id) {{
    var el=document.getElementById(id);
    if(el) el.style.display='block';
  }});
  setTimeout(prefetchAllFundamentals, 100);
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
  var upColor = upsidePct!=null&&upsidePct>5?'#27ae60':upsidePct!=null&&upsidePct<-5?'#e74c3c':'#8892a4';

  // Unified score
  var t_rs  = Math.min(16,Math.round((s.rs_percentile||0)/100*16));
  var t_vol = (s.vol_contraction||1)<=0.5?12:(s.vol_contraction||1)<=0.7?8:(s.vol_contraction||1)<=0.9?4:0;
  var t_atr = (s.atr||1)<=0.2?8:(s.atr||1)<=0.3?5:(s.atr||1)<=0.4?2:0;
  var t_lvl = (s.level||'').indexOf('ATH')>=0?4:(s.level||'').indexOf('multi')>=0?3:1;
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

  // Risk/Reward
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
  var tf=s.timeframe||'mid';
  var tfLabel=tf==='short'?'Short (1-2w)':tf==='long'?'Long (3-12m)':'Mid (1-3m)';
  var tfColor=tf==='short'?'#e74c3c':tf==='long'?'#3498db':'#e67e22';
  var tfIcon=tf==='short'?'&#9889;':tf==='long'?'&#128336;':'&#128197;';

  // Setup
  var rr=riskCat+'/'+rewardCat,setupCat,setupColor,setupBg,setupIcon;
  if     (rr==='Low/High')    {{ setupCat='Best setup';  setupColor='#27ae60';setupBg='#1a3d2b';setupIcon='&#11088;'; }}
  else if(rr==='Low/Medium')  {{ setupCat='Good setup';  setupColor='#27ae60';setupBg='#1a3d2b';setupIcon='&#9989;'; }}
  else if(rr==='Medium/High') {{ setupCat='High upside'; setupColor='#e67e22';setupBg='#3d2e10';setupIcon='&#127919;'; }}
  else if(rr==='Medium/Medium'){{ setupCat='Balanced';   setupColor='#e67e22';setupBg='#3d2e10';setupIcon='&#128202;'; }}
  else if(rr==='High/High')   {{ setupCat='Aggressive';  setupColor='#e67e22';setupBg='#3d2e10';setupIcon='&#127922;'; }}
  else if(rr==='Low/Low')     {{ setupCat='Weak upside'; setupColor='#8892a4';setupBg='#22263a';setupIcon='&#128201;'; }}
  else                        {{ setupCat='Skip';        setupColor='#e74c3c';setupBg='#3d1a1a';setupIcon='&#9888;'; }}

  // Signal chips
  var sigs='';
  if(s.pre_breakout)  sigs+='<span class="sig sp">&#9889; Pre-breakout</span>';
  if(s.bull_flag)     sigs+='<span class="sig sg">&#127987; Bull Flag</span>';
  if((s.vol_contraction||1)<=0.7) sigs+='<span class="sig sb">Vol dry '+Math.round((s.vol_contraction||1)*100)+'%</span>';
  if(earn!=null&&earn>=0&&earn<=14) sigs+='<span class="sig sa">&#128197; Earnings '+earn+'d</span>';
  if((s.momentum_1m||0)>=15) sigs+='<span class="sig sg">&#128640; +'+Math.round(s.momentum_1m)+'% month</span>';
  if(rsi!=null&&rsi>=70) sigs+='<span class="sig sr">RSI overbought</span>';
  if(upsidePct!=null&&upsidePct<-5) sigs+='<span class="sig sr">&#9888; Analyst bearish</span>';

  // Store breakdown
  var scoreId='sc-'+s.ticker;
  cardBreakdowns[scoreId]={{tech:techScore,cat:catalystScore,ana:analystScore,
    entry:entryNum.toFixed(2),stop:stopNum.toFixed(2),
    tfLabel:tfIcon+' '+tfLabel,tfColor:tfColor}};

  // Days on list
  var daysOnList = null;
  var fsEntry = firstSeenData[s.ticker];
  if (fsEntry && fsEntry.date) {{
    var fsDate = new Date(fsEntry.date + 'T00:00:00');
    var today2 = new Date(); today2.setHours(0,0,0,0);
    daysOnList = Math.round((today2 - fsDate) / 86400000);
  }}
  var daysLabel='', daysColor='var(--muted)';
  if (daysOnList === 0) {{ daysLabel='New today'; daysColor='var(--blue)'; }}
  else if (daysOnList === 1) {{ daysLabel='1 day on the list'; daysColor='var(--muted)'; }}
  else if (daysOnList !== null && daysOnList <= 3) {{ daysLabel=daysOnList+' days on the list'; daysColor='var(--muted)'; }}
  else if (daysOnList !== null && daysOnList <= 14) {{ daysLabel=daysOnList+' days on the list'; daysColor='var(--amber)'; }}
  else if (daysOnList !== null) {{ daysLabel=daysOnList+' days on the list'; daysColor='var(--green)'; }}

  var h='';
  h += '<div class="card '+(s.status==='READY'?'pre':s.status==='WATCH'?'watch':'')+'" id="card-'+s.ticker+'">';

  // ── Click-to-fold header ──────────────────────────────────────────────────
  var tgtCol2=upsidePct!=null&&upsidePct>5?'var(--green)':upsidePct!=null&&upsidePct<-5?'var(--red)':'var(--muted)';
  h += '<div class="card-header" data-ticker="'+s.ticker+'" onclick="event.stopPropagation();toggleCard(this.dataset.ticker)">';
  // Row 1: rank + ticker + sector | score
  h += '<div style="display:flex;justify-content:space-between;align-items:center">';
  h += '<div style="display:flex;align-items:center;gap:12px">';
  h += '<div class="card-rank '+(isTop?'top':'')+'">'+rank+'</div>';
  h += '<div>';
  h += '<div style="font-size:20px;font-weight:700">'+s.ticker+'<span class="mcap-badge" id="mcap-'+s.ticker+'">&#8212;</span><span style="font-size:12px;font-weight:400;color:var(--muted);margin-left:8px">'+(s.sector||'NASDAQ')+'</span></div>';
  h += '<div style="font-size:13px;color:var(--muted);margin-top:3px">$'+price.toFixed(2)+'<span class="chg '+chgCls+'" style="margin-left:6px">'+chgStr+'</span>'+(daysLabel?'<span style="margin-left:10px;font-size:11px;color:'+daysColor+'">'+daysLabel+'</span>':'')+'</div>';
  h += '</div></div>';
  h += '<div style="text-align:right">';
  h += '<div id="'+scoreId+'" style="font-size:32px;font-weight:700;color:'+color+';cursor:pointer;line-height:1" onclick="event.stopPropagation();showBreakdown(this)">'+unifiedScore+'</div>';
  h += '<div style="font-size:11px;font-weight:600;letter-spacing:.5px;color:'+color+';margin-top:3px">'+s.status+'</div>';
  h += '</div>';
  h += '</div>';
  // Performance row — directly under title, no 1D (already shown in price line)
  h += '<div class="perf-row" style="margin-top:10px">';
  h += '<div class="perf-item"><div class="perf-lbl">1W</div><div class="perf-val" id="p1w-'+s.ticker+'">&mdash;</div></div>';
  h += '<div class="perf-item"><div class="perf-lbl">1M</div><div class="perf-val" id="p1m-'+s.ticker+'">&mdash;</div></div>';
  h += '<div class="perf-item"><div class="perf-lbl">3M</div><div class="perf-val" id="p3m-'+s.ticker+'">&mdash;</div></div>';
  h += '<div class="perf-item"><div class="perf-lbl">6M</div><div class="perf-val" id="p6m-'+s.ticker+'">&mdash;</div></div>';
  h += '</div>';

  // Row 2: P/E | RSI | 1Y Target
  h += '<div id="fold-'+s.ticker+'" style="display:flex;margin-top:10px;border-top:1px solid var(--border);padding-top:10px">';
  h += '<div style="flex:1;text-align:center;border-right:1px solid var(--border);padding:0 8px">';
  h += '<div style="font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">P/E Ratio</div>';
  h += '<div class="fund-pe-val" style="font-size:18px;font-weight:700;color:'+peC(pe)+'">'+(pe&&pe>0?pe.toFixed(1):'&mdash;')+'</div>';
  h += '<div class="fund-pe-sub" style="font-size:10px;color:var(--muted);margin-top:2px">'+(pe&&pe>0?(pe<20?'Cheap':pe<40?'Fair':'Pricey'):'')+'</div>';
  h += '</div>';
  h += '<div style="flex:1;text-align:center;border-right:1px solid var(--border);padding:0 8px">';
  h += '<div style="font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">RSI (14)</div>';
  h += '<div class="fund-rsi-val" style="font-size:18px;font-weight:700;color:'+rc+'">'+(rsi!=null?rsi.toFixed(0):'&mdash;')+'</div>';
  h += '<div class="fund-rsi-sub" style="font-size:10px;color:var(--muted);margin-top:2px">'+rsiL(rsi)+'</div>';
  h += '</div>';
  h += '<div style="flex:1;text-align:center;padding:0 8px">';
  h += '<div style="font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">1Y Target</div>';
  h += '<div class="fund-tgt-val" style="font-size:18px;font-weight:700;color:'+tgtCol2+'">'+(target?'$'+target.toFixed(0):'&mdash;')+'</div>';
  h += '<div class="fund-tgt-sub" style="font-size:10px;color:'+tgtCol2+';margin-top:2px">'+(upsidePct!=null?(upsidePct>=0?'+':'')+upsidePct.toFixed(1)+'%':'')+'</div>';
  h += '</div>';
  h += '</div>';
  h += '</div>'; // end card-header
  // Score bar removed — left border color already conveys status

  // ── Expandable body ───────────────────────────────────────────────────────
  h += '<div class="card-body" id="body-'+s.ticker+'" style="display:none">';

  // Fundamentals shown in header — not repeated here

  // Analyst row
  if(buyPct>0||numAna>0) {{
    h += '<div style="font-size:11px;color:var(--muted);padding:6px 0;display:flex;gap:16px;flex-wrap:wrap">';
    if(numAna>0) h += '<span>&#128101; '+numAna+' analysts</span>';
    if(buyPct>0) h += '<span style="color:'+(buyPct>=70?'#27ae60':buyPct>=50?'#e67e22':'#e74c3c')+'">&#128200; '+buyPct+'% Buy rating</span>';
    if(s.recommendation) h += '<span style="text-transform:capitalize">Consensus: <strong>'+s.recommendation+'</strong></span>';
    h += '</div>';
  }}

  // Signal chips
  if(sigs) h += '<div class="sigs" style="margin:8px 0">'+sigs+'</div>';

  // Technical factors
  h += '<div class="sec-title">Technical Factors</div>';
  h += '<div class="factors">';
  h += '<div class="fbox"><div class="flbl">ATR coil</div><div class="fval '+((s.atr||1)<=0.25?'fg':(s.atr||1)<=0.35?'fa':'fr')+'">'+(s.atr||0).toFixed(2)+'</div><div class="fsub">'+((s.atr||1)<=0.25?'Very tight':(s.atr||1)<=0.35?'Tight':'Wide')+'</div></div>';
  h += '<div class="fbox"><div class="flbl">RS percentile</div><div class="fval '+((s.rs_percentile||0)>=80?'fg':'')+'">'+(s.rs_percentile!=null?s.rs_percentile.toFixed(0)+'th':'&mdash;')+'</div><div class="fsub">'+((s.rs_percentile||0)>=90?'Elite':(s.rs_percentile||0)>=80?'Strong':(s.rs_percentile||0)>=60?'Good':'Weak')+'</div></div>';
  h += '<div class="fbox"><div class="flbl">Vol contraction</div><div class="fval '+((s.vol_contraction||1)<=0.7?'fg':(s.vol_contraction||1)<=0.9?'fa':'fr')+'">'+Math.round((s.vol_contraction||1)*100)+'%</div><div class="fsub">'+((s.vol_contraction||1)<=0.5?'Very dry':(s.vol_contraction||1)<=0.7?'Dry':(s.vol_contraction||1)<=0.9?'Light':'Heavy')+'</div></div>';
  h += '<div class="fbox"><div class="flbl">EMA stack</div><div class="fval '+('full'===(s.ema_stack||'')?'fg':'partial'===(s.ema_stack||'')?'fa':'fr')+'">'+(s.ema_stack||'&mdash;')+'</div><div class="fsub">'+('full'===(s.ema_stack||'')?'Strong trend':'partial'===(s.ema_stack||'')?'Partial':'Weak')+'</div></div>';
  h += '<div class="fbox"><div class="flbl">Level</div><div class="fval" style="color:'+(lc(s.level))+'">'+(s.level||'&mdash;')+'</div><div class="fsub">'+((s.level||'').indexOf('ATH')>=0?'No resistance':(s.level||'').indexOf('multi')>=0?'Multi-year':'Prior level')+'</div></div>';
  h += '<div class="fbox"><div class="flbl">Distance</div><div class="fval" style="color:'+pc+'">'+Math.abs(dist).toFixed(1)+'%</div><div class="fsub">'+(dist<=0?'Broke out':dist<=1?'Very close':'Away')+'</div></div>';
  h += '</div>';

  // Risk/Reward
  h += '<div class="sec-title">Risk / Reward</div>';
  h += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px">';
  h += '<div style="background:'+riskBg+';border-radius:10px;padding:14px;text-align:center">';
  h += '<div style="font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px">Risk</div>';
  h += '<div style="font-size:22px;font-weight:700;color:'+riskColor+'">'+riskCat+'</div>';
  h += '<div style="font-size:11px;color:'+riskColor+';margin-top:5px">Stop '+stpPct+'%</div>';
  h += '</div>';
  h += '<div style="background:'+rewardBg+';border-radius:10px;padding:14px;text-align:center">';
  h += '<div style="font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px">Reward</div>';
  h += '<div style="font-size:22px;font-weight:700;color:'+rewardColor+'">'+rewardCat+'</div>';
  h += '<div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:6px;justify-content:center">';
  h += '<span style="font-size:9px;padding:2px 7px;border-radius:20px;background:'+(sig_rs?'#1a3d2b':'#22263a')+';color:'+(sig_rs?'#27ae60':'#4a5568')+'">RS&gt;80</span>';
  h += '<span style="font-size:9px;padding:2px 7px;border-radius:20px;background:'+(sig_vol?'#1a3d2b':'#22263a')+';color:'+(sig_vol?'#27ae60':'#4a5568')+'">Vol dry</span>';
  h += '<span style="font-size:9px;padding:2px 7px;border-radius:20px;background:'+(sig_lvl?'#1a3d2b':'#22263a')+';color:'+(sig_lvl?'#27ae60':'#4a5568')+'">ATH</span>';
  h += '<span style="font-size:9px;padding:2px 7px;border-radius:20px;background:'+(sig_ema?'#1a3d2b':'#22263a')+';color:'+(sig_ema?'#27ae60':'#4a5568')+'">EMA</span>';
  h += '</div></div></div>';

  // Setup + Action
  h += '<div style="background:'+setupBg+';border:1px solid '+setupColor+'44;border-radius:12px;padding:14px">';
  h += '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">';
  h += '<div style="font-size:15px;font-weight:700;color:'+setupColor+'">'+setupIcon+' '+setupCat+'</div>';
  h += '<div style="font-size:12px;font-weight:600;color:'+tfColor+'">'+tfIcon+' '+tfLabel+'</div>';
  h += '</div>';
  h += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">';
  h += '<div style="background:var(--bg2);border-radius:8px;padding:10px 14px">';
  h += '<div style="font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">Buy above</div>';
  h += '<div style="font-size:20px;font-weight:700;color:#27ae60">$'+entryNum.toFixed(2)+'</div>';
  h += '</div>';
  h += '<div style="background:var(--bg2);border-radius:8px;padding:10px 14px">';
  h += '<div style="font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">Stop loss</div>';
  h += '<div style="font-size:20px;font-weight:700;color:#e74c3c">$'+stopNum.toFixed(2)+'</div>';
  h += '<div style="font-size:10px;color:#e74c3c;margin-top:2px">-'+stpPct+'%</div>';
  h += '</div></div></div>';

  // Footer
  h += '<div style="padding-top:12px;display:flex;justify-content:flex-end">';
  h += '<button class="chart-btn" id="cbtn-'+s.ticker+'" onclick="doChart(this)" data-ticker="'+s.ticker+'">&#128202; Chart</button>';
  h += '</div>';
  h += '</div>'; // card-body

  // Chart panel
  h += '<div class="chart-panel" id="cpanel-'+s.ticker+'">';
  h += '<button class="chart-close" data-ticker="'+s.ticker+'" onclick="doClose(this)">&times; Close</button>';
  h += '<iframe id="cframe-'+s.ticker+'" src="" scrolling="no" allowtransparency="true"></iframe>';
  h += '</div>';
  h += '</div>'; // card
  return h;
}}


function toggleCard(ticker) {{
  var body = document.getElementById('body-'+ticker);
  if (!body) return;
  var isOpen = body.style.display === 'block';
  body.style.display = isOpen ? 'none' : 'block';
  if (!isOpen) fetchFundamentals(ticker);
}}

function showBreakdown(el) {{
  var d = cardBreakdowns[el.id];
  if(!d) return;
  var p = document.getElementById('breakdown-popup');
  if(!p) return;
  document.getElementById('bp-tech').textContent = d.tech+'/40';
  document.getElementById('bp-cat').textContent  = d.cat+'/30';
  document.getElementById('bp-ana').textContent  = d.ana+'/30';
  document.getElementById('bp-tech-bar').style.width = Math.round(d.tech/40*100)+'%';
  document.getElementById('bp-cat-bar').style.width  = Math.round(d.cat/30*100)+'%';
  document.getElementById('bp-ana-bar').style.width  = Math.round(d.ana/30*100)+'%';
  document.getElementById('bp-entry').textContent = '$'+d.entry;
  document.getElementById('bp-stop').textContent  = '$'+d.stop;
  document.getElementById('bp-tf').innerHTML = '<span style="color:'+d.tfColor+'">'+d.tfLabel+'</span>';
  var rect = el.getBoundingClientRect();
  p.style.top  = (rect.bottom + window.scrollY + 8) + 'px';
  p.style.left = Math.min(rect.left, window.innerWidth - 310) + 'px';
  p.style.display = p.style.display === 'block' ? 'none' : 'block';
}}
document.addEventListener('click', function(e) {{
  var p = document.getElementById('breakdown-popup');
  if(p && !p.contains(e.target)) p.style.display = 'none';
}});

// _fundData stores fetched data persistently across re-renders
// _fundCache tracks which tickers are currently being fetched
var _fundData  = {{}};
var _fundCache = {{}};

function applyFundamentals(ticker) {{
  var d = _fundData[ticker];
  if (!d) return;
  var card = document.getElementById('card-'+ticker);
  if (!card) return;
  if(d.pe_ratio) {{
    var pe=d.pe_ratio;
    var peEl=card.querySelector('.fund-pe-val'), peSub=card.querySelector('.fund-pe-sub');
    if(peEl){{peEl.textContent=pe.toFixed(1);peEl.style.color=pe<20?'var(--green)':pe<40?'var(--amber)':'var(--red)';}}
    if(peSub) peSub.textContent=pe<20?'Cheap':pe<40?'Fair':'Pricey';
  }}
  if(d.rsi!=null) {{
    var rsi=d.rsi;
    var rsiEl=card.querySelector('.fund-rsi-val'), rsiSub=card.querySelector('.fund-rsi-sub');
    if(rsiEl){{rsiEl.textContent=rsi.toFixed(0);rsiEl.style.color=rsi>=70?'var(--red)':rsi<=30?'var(--blue)':'var(--green)';}}
    if(rsiSub) rsiSub.textContent=rsi>=70?'Overbought':rsi<=30?'Oversold':'Healthy';
  }}
  if(d.pe_ratio||d.rsi!=null) {{
    var upEl=card.querySelector('.fund-tgt-val'), subEl=card.querySelector('.fund-tgt-sub');
    var tgt=d.analyst_target, up=d.analyst_upside!=null?parseFloat(d.analyst_upside):null;
    var col=up!=null&&up>5?'var(--green)':up!=null&&up<-5?'var(--red)':'var(--muted)';
    if(upEl&&tgt){{upEl.textContent='$'+tgt.toFixed(0);upEl.style.color=col;}}
    if(subEl){{subEl.textContent=up!=null?(up>=0?'+':'')+up.toFixed(1)+'%':'';subEl.style.color=col;}}
  }}
}}

async function fetchFundamentals(ticker) {{
  // If already have data, just apply it to current DOM
  if(_fundData[ticker]) {{ applyFundamentals(ticker); return; }}
  // If currently fetching, skip
  if(_fundCache[ticker]) return;
  _fundCache[ticker] = true;
  try {{
    var resp = await fetch('/lookup?t='+ticker);
    if(!resp.ok) {{ _fundCache[ticker]=false; return; }}
    var d = await resp.json();
    if(d.error) {{ _fundCache[ticker]=false; return; }}
    _fundData[ticker] = d; // persist data
    applyFundamentals(ticker);
  }} catch(e) {{ _fundCache[ticker]=false; }}
}}

function prefetchAllFundamentals() {{
  // First apply cached data immediately (no delay)
  var headers = document.querySelectorAll('.card-header');
  var needFetch = [];
  headers.forEach(function(hdr) {{
    var ticker = hdr.getAttribute('data-ticker');
    if(!ticker) return;
    if(_fundData[ticker]) {{
      applyFundamentals(ticker); // instant - from cache
    }} else {{
      needFetch.push(ticker);
    }}
  }});
  // Then fetch missing ones with small stagger
  needFetch.forEach(function(ticker, i) {{
    setTimeout(function() {{ fetchFundamentals(ticker); }}, i * 150);
    setTimeout(function() {{ fetchPerf(ticker); }}, i * 150 + 75);
  }});
  // Apply cached perf data immediately
  headers.forEach(function(hdr) {{
    var ticker = hdr.getAttribute('data-ticker');
    if(ticker && _perfData[ticker]) applyPerf(ticker);
  }});
}}

// ── Performance (market cap + 1W/1M/3M/6M) ───────────────────────────────────
var _perfData  = {{}};
var _perfCache = {{}};

function applyPerf(ticker) {{
  var d = _perfData[ticker];
  if (!d) return;
  var mcap = document.getElementById('mcap-'+ticker);
  if (mcap && d.market_cap) mcap.textContent = d.market_cap;
  function setPct(id, val) {{
    var el = document.getElementById(id);
    if (!el) return;
    if (val == null) {{ el.textContent = '—'; el.className = 'perf-val'; return; }}
    el.textContent = (val >= 0 ? '+' : '') + val.toFixed(1) + '%';
    el.className = 'perf-val ' + (val >= 0 ? 'fg' : 'fr');
  }}
  setPct('p1w-'+ticker, d.change_1w);
  setPct('p1m-'+ticker, d.change_1m);
  setPct('p3m-'+ticker, d.change_3m);
  setPct('p6m-'+ticker, d.change_6m);
}}

async function fetchPerf(ticker) {{
  if (_perfData[ticker]) {{ applyPerf(ticker); return; }}
  if (_perfCache[ticker]) return;
  _perfCache[ticker] = true;
  try {{
    var resp = await fetch('/api/perf/' + ticker);
    if (!resp.ok) {{ _perfCache[ticker] = false; return; }}
    var d = await resp.json();
    if (d.error) {{ _perfCache[ticker] = false; return; }}
    _perfData[ticker] = d;
    applyPerf(ticker);
  }} catch(e) {{ _perfCache[ticker] = false; }}
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
  var baseData = (allStockData&&allStockData[ticker]) ? allStockData[ticker]
               : (stockData&&stockData[ticker])       ? stockData[ticker]
               : null;
  var foundLabel = (allStockData&&allStockData[ticker]) ? '&#10003; Found in scanner'
                 : (stockData&&stockData[ticker])       ? '&#10003; Found in top 10'
                 : null;
  if(baseData) {{
    // Always fetch fresh market data so RSI / PE / analyst fields are populated
    var enriched = Object.assign({{}}, baseData);
    try {{
      var resp2 = await fetch('/lookup?t='+ticker);
      if(resp2.ok) {{
        var d2 = await resp2.json();
        if(!d2.error) {{
          // Lookup wins on market data; scanner wins on score/status/signals
          enriched.price          = d2.price          || enriched.price;
          enriched.change_pct     = d2.change_pct     != null ? d2.change_pct : enriched.change_pct;
          enriched.rsi            = d2.rsi            != null ? d2.rsi : enriched.rsi;
          enriched.pe_ratio       = d2.pe_ratio       != null ? d2.pe_ratio : enriched.pe_ratio;
          enriched.analyst_target = d2.analyst_target != null ? d2.analyst_target : enriched.analyst_target;
          enriched.analyst_upside = d2.analyst_upside != null ? String(d2.analyst_upside) : enriched.analyst_upside;
          enriched.name           = d2.name           || enriched.name;
          enriched.sector         = d2.sector         || enriched.sector;
        }}
      }}
    }} catch(e) {{/* use scanner data only */}}
    result.innerHTML='<div style="color:var(--green);font-size:12px;margin-bottom:8px">'+foundLabel+'</div>'+makeCard(enriched,'&mdash;');
    return;
  }}
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
            if avg_l == 0 and avg_g > 0:
                rsi = 100.0
            elif avg_l > 0:
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



@app.route('/api/perf/<ticker>')
def api_perf(ticker):
    """Return market cap + 1W/1M/3M/6M performance for a ticker."""
    ticker = ticker.upper().strip()
    if not ticker or len(ticker) > 6:
        return jsonify({'error': 'Invalid ticker'}), 400
    try:
        tk   = yf.Ticker(ticker)
        hist = tk.history(period='1y', interval='1d')
        if hist.empty:
            return jsonify({'error': 'No data'}), 404
        closes = hist['Close'].tolist()
        price  = closes[-1]

        def pct(n):
            # closes[-n] = price n days ago; need at least n+1 points (current + n back)
            if len(closes) >= n and n > 0:
                base = closes[-n]
                if base and base > 0:
                    return round((price - base) / base * 100, 1)
            return None

        mc     = getattr(tk.fast_info, 'market_cap', None)
        mc_str = None
        if mc:
            if   mc >= 1e12: mc_str = f"{mc/1e12:.1f}T"
            elif mc >= 1e9:  mc_str = f"{mc/1e9:.1f}B"
            else:             mc_str = f"{mc/1e6:.0f}M"

        return jsonify({
            'market_cap': mc_str,
            'change_1w':  pct(5),
            'change_1m':  pct(21),
            'change_3m':  pct(63),
            'change_6m':  pct(126),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/analytics')
def analytics():
    cfg_tag = '<script id="fb-cfg" type="application/json">' + json.dumps(FIREBASE_CONFIG) + '</script>'
    return ANALYTICS_HTML.replace('<!--FB_CONFIG-->', cfg_tag).replace('<!--VERSION-->', VERSION)


ANALYTICS_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Scanner Analytics</title>
<style>
:root{--bg:#0f1117;--bg2:#1a1d26;--bg3:#22263a;--text:#e8eaf0;--muted:#8892a4;--border:#2a2f42;--green:#27ae60;--amber:#e67e22;--blue:#3498db;--red:#e74c3c;}
*{box-sizing:border-box;margin:0;padding:0;}
body{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;font-size:14px;}
.header{background:var(--bg2);border-bottom:1px solid var(--border);padding:12px 24px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px;position:sticky;top:0;z-index:100;min-height:56px;}
.header h1{font-size:16px;font-weight:600;}
.header p{font-size:11px;color:var(--muted);margin-top:1px;}
.hright{display:flex;align-items:center;gap:10px;}
.ver{font-size:10px;color:var(--muted);background:var(--bg3);border:1px solid var(--border);padding:3px 8px;border-radius:20px;font-family:monospace;}
.nav-pills{display:flex;gap:6px;align-items:center;}
.nav-pill{padding:5px 14px;border-radius:20px;font-size:12px;font-weight:600;text-decoration:none;border:1px solid var(--border);color:var(--muted);transition:all .15s;background:var(--bg3);}
.nav-pill:hover{color:var(--text);border-color:var(--blue);}
.nav-pill.active{background:var(--blue);color:#fff;border-color:var(--blue);}
.ver{font-size:10px;color:var(--muted);background:var(--bg3);border:1px solid var(--border);padding:3px 8px;border-radius:20px;font-family:monospace;}
.regime{padding:4px 12px;border-radius:20px;font-size:11px;font-weight:600;border:1px solid;}
.regime.open{background:#1a3d2b;color:#27ae60;border-color:#27ae6055;}
.regime.pre{background:#1a2a3d;color:#3498db;border-color:#3498db55;}
.regime.after{background:#2d1a3d;color:#9b59b6;border-color:#9b59b655;}
.regime.closed{background:var(--bg3);color:var(--muted);border-color:var(--border);}
.page{padding:24px;}
.loading{text-align:center;padding:80px;color:var(--muted);font-size:16px;}
.error{color:var(--red);padding:20px;text-align:center;}

/* Controls */
.controls{display:flex;gap:12px;margin-bottom:24px;flex-wrap:wrap;align-items:center;}
.ctrl-group{display:flex;align-items:center;gap:8px;}
.ctrl-group label{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;}
select,input[type=number]{background:var(--bg3);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:6px 10px;font-size:12px;outline:none;}
.btn{background:var(--blue);color:#fff;border:none;border-radius:7px;padding:7px 16px;font-size:12px;font-weight:600;cursor:pointer;}
.btn:hover{background:#2980b9;}
.btn.sec{background:var(--bg3);color:var(--text);border:1px solid var(--border);}

/* KPI cards */
.kpi-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:14px;margin-bottom:28px;}
.kpi{background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:16px 18px;}
.kpi-label{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px;}
.kpi-val{font-size:28px;font-weight:700;line-height:1;}
.kpi-sub{font-size:11px;color:var(--muted);margin-top:4px;}
.kpi.green{border-left:3px solid var(--green);}
.kpi.red{border-left:3px solid var(--red);}
.kpi.blue{border-left:3px solid var(--blue);}
.kpi.amber{border-left:3px solid var(--amber);}

/* Timeframe table */
.section{background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:20px;margin-bottom:20px;}
.section h2{font-size:14px;font-weight:700;margin-bottom:16px;display:flex;align-items:center;gap:8px;}
.tf-table{width:100%;border-collapse:collapse;}
.tf-table th{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;padding:8px 12px;text-align:center;border-bottom:1px solid var(--border);}
.tf-table th:first-child{text-align:left;}
.tf-table td{padding:10px 12px;text-align:center;border-bottom:1px solid var(--border)44;font-size:13px;}
.tf-table td:first-child{text-align:left;font-weight:600;color:var(--muted);}
.tf-table tr:last-child td{border-bottom:none;}
.tf-table .pos{color:var(--green);font-weight:600;}
.tf-table .neg{color:var(--red);font-weight:600;}
.tf-table .na{color:var(--muted);}

/* Signal analysis */
.signal-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px;}
.signal-card{background:var(--bg3);border-radius:10px;padding:14px;}
.signal-name{font-size:12px;font-weight:600;margin-bottom:10px;}
.signal-bar-row{display:flex;align-items:center;gap:8px;margin-bottom:6px;}
.signal-bar-label{font-size:11px;color:var(--muted);width:80px;flex-shrink:0;}
.signal-bar-track{flex:1;height:8px;background:var(--bg2);border-radius:4px;overflow:hidden;}
.signal-bar-fill{height:100%;border-radius:4px;}
.signal-bar-val{font-size:11px;font-weight:600;width:40px;text-align:right;flex-shrink:0;}
.signal-diff{font-size:11px;color:var(--muted);margin-top:4px;}

/* Sort buttons */
.sort-btn{background:var(--bg3);color:var(--muted);border:1px solid var(--border);border-radius:20px;padding:5px 12px;font-size:11px;font-weight:600;cursor:pointer;transition:all .15s;white-space:nowrap;}
.sort-btn:hover{border-color:var(--blue);color:var(--text);}
.sort-btn.active{background:var(--blue);color:#fff;border-color:var(--blue);}

/* Picks table */
.picks-table{width:100%;border-collapse:collapse;font-size:12px;}
.picks-table th{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;padding:8px 10px;text-align:left;border-bottom:1px solid var(--border);cursor:pointer;white-space:nowrap;}
.picks-table th:hover{color:var(--text);}
.picks-table td{padding:8px 10px;border-bottom:1px solid var(--border)22;}
.picks-table tr:hover td{background:#ffffff05;}
.ret-pos{color:var(--green);font-weight:600;}
.ret-neg{color:var(--red);font-weight:600;}
.ret-na{color:var(--muted);}
.badge{font-size:9px;padding:2px 7px;border-radius:20px;font-weight:600;}
.badge.READY{background:#1a3d2b;color:var(--green);}
.badge.WATCH{background:#3d2e10;color:var(--amber);}
.badge.BUILDING{background:var(--bg3);color:var(--muted);}
.sparkline{display:inline-block;vertical-align:middle;}
.pg{display:flex;gap:8px;align-items:center;margin-top:12px;font-size:12px;color:var(--muted);}
.pg button{background:var(--bg3);border:1px solid var(--border);color:var(--text);border-radius:5px;padding:3px 10px;cursor:pointer;font-size:11px;}
.pg button:disabled{opacity:.4;cursor:default;}
</style>
<!--FB_CONFIG-->
<script src="https://www.gstatic.com/firebasejs/9.23.0/firebase-app-compat.js"></script>
<script src="https://www.gstatic.com/firebasejs/9.23.0/firebase-database-compat.js"></script>
<script>
var CFG = JSON.parse(document.getElementById('fb-cfg').textContent);
try { firebase.initializeApp(CFG); } catch(e) {}
var fdb = firebase.database();
</script>
</head>
<body>
<div class="header">
  <div>
    <h1>📊 Scanner Analytics</h1>
    <p>Historical performance of scanner picks — does the logic actually find winners?</p>
  </div>
  <div class="hright">
    <div class="nav-pills"><a class="nav-pill" href="/">&#128202; Dashboard</a><a class="nav-pill active" href="/analytics">&#128200; Analytics</a><a class="nav-pill" href="/smart-money">&#127974; Smart Money</a><a class="nav-pill" href="/optimizer">&#128202; Optimizer</a></div>
    <span class="ver"><!--VERSION--></span>
    <span class="regime closed" id="regime-badge">&#9675; Checking...</span>
  </div>
</div>
<script>
(function(){
  var n=new Date(),h=(n.getUTCHours()-4+24)%24,m=n.getUTCMinutes(),d=n.getUTCDay(),t=h*60+m;
  var el=document.getElementById('regime-badge');
  if(d===0||d===6){el.textContent='○ Market Closed';el.className='regime closed';}
  else if(t>=570&&t<960){el.textContent='● Market Open';el.className='regime open';}
  else if(t>=240&&t<570){el.textContent='◐ Pre-Market';el.className='regime pre';}
  else if(t>=960&&t<1200){el.textContent='◑ After-Hours';el.className='regime after';}
  else{el.textContent='○ Market Closed';el.className='regime closed';}
})();
</script>

<div class="page">
  <div id="loading" class="loading">⏳ Loading historical data...</div>
  <div id="content" style="display:none">

    <!-- Controls -->
    <div class="controls">
      <div class="ctrl-group">
        <label>Window</label>
        <select id="tf-select" onchange="render()">
          <option value="1w">1 Week</option>
          <option value="2w">2 Weeks</option>
          <option value="1m" selected>1 Month</option>
          <option value="2m">2 Months</option>
          <option value="3m">3 Months</option>
          <option value="6m">6 Months</option>
          <option value="1y">1 Year</option>
        </select>
      </div>
      <div class="ctrl-group">
        <label>Status</label>
        <select id="status-filter" onchange="render()">
          <option value="all">All</option>
          <option value="READY">Ready only</option>
          <option value="WATCH">Watch only</option>
        </select>
      </div>
      <div class="ctrl-group">
        <label>Min score</label>
        <input type="number" id="min-score" value="0" min="0" max="100" style="width:70px" onchange="render()">
      </div>
      <div class="ctrl-group">
        <label>Setup</label>
        <select id="setup-filter" onchange="render()">
          <option value="all">All setups</option>
          <option value="pre_breakout">Pre-breakout</option>
          <option value="bull_flag">Bull flag</option>
        </select>
      </div>
      <button class="btn" onclick="loadData()">🔄 Refresh</button>
      <span id="data-info" style="font-size:11px;color:var(--muted)"></span>
    </div>

    <!-- KPI row -->
    <div class="kpi-grid" id="kpi-grid"></div>

    <!-- Timeframe performance table -->
    <div class="section">
      <h2>📅 Performance by Timeframe</h2>
      <table class="tf-table" id="tf-table">
        <thead>
          <tr>
            <th>Metric</th>
            <th>1W</th><th>2W</th><th>1M</th><th>2M</th><th>3M</th><th>6M</th><th>1Y</th>
          </tr>
        </thead>
        <tbody id="tf-body"></tbody>
      </table>
    </div>

    <!-- Signal analysis -->
    <div class="section">
      <h2>🔬 What signals predict success?
        <span style="font-size:11px;color:var(--muted);font-weight:400">
          (win = positive return in selected window)
        </span>
      </h2>
      <div class="signal-grid" id="signal-grid"></div>
    </div>

    <!-- Per-pick detail table -->
    <div class="section">
      <h2>📋 First Flagged Stocks
        <span id="picks-count" style="font-size:11px;color:var(--muted);font-weight:400"></span>
      </h2>
      <p style="font-size:11px;color:var(--muted);margin-bottom:14px;">
        Each stock shown once — from the <strong style="color:var(--text)">first time the scanner flagged it</strong>.
        Returns measured from that entry date.
      </p>
      <!-- Table sort + search -->
      <div style="display:flex;gap:8px;align-items:center;margin-bottom:14px;flex-wrap:wrap;">
        <span style="font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;flex-shrink:0;">Sort:</span>
        <button class="sort-btn active" id="sort-btn-date"  onclick="setSort('scan_date')">📅 Date</button>
        <button class="sort-btn"        id="sort-btn-abc"   onclick="setSort('ticker_asc')">🔤 A–Z</button>
        <button class="sort-btn"        id="sort-btn-score" onclick="setSort('score')">⭐ Score</button>
        <button class="sort-btn"        id="sort-btn-ret1w" onclick="setSort('ret_1w')">1W Return</button>
        <button class="sort-btn"        id="sort-btn-ret1m" onclick="setSort('ret_1m')">1M Return</button>
        <button class="sort-btn"        id="sort-btn-ret3m" onclick="setSort('ret_3m')">3M Return</button>
        <div style="margin-left:auto;">
          <input type="text" id="ticker-search" placeholder="🔍 Search ticker…" style="background:var(--bg3);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:5px 10px;font-size:12px;outline:none;width:150px;text-transform:uppercase" oninput="this.value=this.value.toUpperCase();page=0;render()">
        </div>
      </div>
      <table class="picks-table">
        <thead>
          <tr>
            <th onclick="sortBy('scan_date')">First Flagged ↕</th>
            <th onclick="sortBy('ticker')">Ticker ↕</th>
            <th onclick="sortBy('price_at_scan')">Entry $</th>
            <th onclick="sortBy('score')">Score ↕</th>
            <th>Status</th>
            <th>Setup</th>
            <th onclick="sortBy('rs_percentile')">RS %ile</th>
            <th onclick="sortBy('vol_contraction')">Vol dry</th>
            <th onclick="sortBy('atr')">ATR</th>
            <th>Level</th>
            <th onclick="sortBy('days_on_list')">Days on list ↕</th>
            <th onclick="sortBy('ret_1w')">1W</th>
            <th onclick="sortBy('ret_1m')">1M</th>
            <th onclick="sortBy('ret_3m')">3M</th>
          </tr>
        </thead>
        <tbody id="picks-body"></tbody>
      </table>
      <div class="pg">
        <button id="pg-prev" onclick="prevPage()" disabled>← Prev</button>
        <span id="pg-info"></span>
        <button id="pg-next" onclick="nextPage()">Next →</button>
      </div>
    </div>

  </div><!-- /content -->
</div>

<script>
var allPicks = [];
var filtered = [];
var sortCol  = 'scan_date';
var sortAsc  = false;
var page     = 0;
var pageSize = 50;

var CACHE_KEY     = 'scanner_analytics_v1';
var CACHE_TS_KEY  = 'scanner_analytics_ts_v1';
var CACHE_DAYS_KEY= 'scanner_analytics_days_v1';

function getCached() {
  try {
    var raw = localStorage.getItem(CACHE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch(e) { return null; }
}

function setCached(picks, knownDays) {
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify(picks));
    localStorage.setItem(CACHE_TS_KEY, Date.now().toString());
    localStorage.setItem(CACHE_DAYS_KEY, JSON.stringify(knownDays));
  } catch(e) {}
}

function getCachedDays() {
  try {
    var raw = localStorage.getItem(CACHE_DAYS_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch(e) { return []; }
}

function buildPicks(rawPicks) {
  var daysCount = {};
  rawPicks.forEach(function(p) {
    daysCount[p.ticker] = (daysCount[p.ticker] || 0) + 1;
  });
  var firstMap = {};
  rawPicks.forEach(function(p) {
    if (!firstMap[p.ticker] || p.scan_date < firstMap[p.ticker].scan_date) {
      firstMap[p.ticker] = p;
    }
  });
  return Object.values(firstMap).map(function(p) {
    return Object.assign({}, p, {days_on_list: daysCount[p.ticker] || 1});
  });
}

function processAndRender(rawPicks, nDays) {
  allPicks = buildPicks(rawPicks);
  document.getElementById('data-info').textContent =
    allPicks.length + ' unique stocks · first flagged across ' + nDays + ' scan days';
  render();
  document.getElementById('loading').style.display = 'none';
  document.getElementById('content').style.display = 'block';
}

function loadData() {
  document.getElementById('loading').style.display = 'block';
  document.getElementById('loading').innerHTML = '⏳ Loading historical data...';
  document.getElementById('content').style.display = 'none';

  // Step 1: get list of available dates (shallow fetch — very fast)
  fdb.ref('scanner/history').once('value', function(snap) {
    var data = snap.val();
    if (!data) {
      document.getElementById('loading').innerHTML =
        '<div class="error">No historical data yet. Run the backtest on the VM.</div>';
      return;
    }

    var allDates   = Object.keys(data).sort();
    var cachedDays = getCachedDays();
    var cachedPicks= getCached() || [];
    var newDates   = allDates.filter(function(d) { return cachedDays.indexOf(d) === -1; });

    if (newDates.length === 0) {
      // Everything is cached — instant load
      document.getElementById('data-info').textContent =
        'Loaded from cache · ' + cachedPicks.length + ' unique stocks · ' + allDates.length + ' scan days';
      allPicks = cachedPicks;
      render();
      document.getElementById('loading').style.display = 'none';
      document.getElementById('content').style.display = 'block';
      return;
    }

    // Step 2: fetch only missing dates
    document.getElementById('loading').innerHTML =
      '⏳ Fetching ' + newDates.length + ' new scan day' + (newDates.length > 1 ? 's' : '') + '…';

    // Build raw picks from cached + new data
    var rawPicks = [];

    // Restore cached raw picks (we keep them as allPicks so rebuild from stored picks)
    // Expand stored first-seen picks back to rawPicks format
    cachedPicks.forEach(function(p) {
      for (var i = 0; i < (p.days_on_list || 1); i++) {
        rawPicks.push(p);
      }
    });

    var pending = newDates.length;
    if (pending === 0) {
      processAndRender(rawPicks, allDates.length);
      setCached(buildPicks(rawPicks), allDates);
      return;
    }

    newDates.forEach(function(date) {
      var dayData = data[date];
      if (dayData && typeof dayData === 'object') {
        Object.keys(dayData).forEach(function(ticker) {
          var r = dayData[ticker];
          if (r && r.price_at_scan) {
            rawPicks.push(Object.assign({}, r, {scan_date: date}));
          }
        });
      }
      pending--;
      if (pending === 0) {
        processAndRender(rawPicks, allDates.length);
        setCached(buildPicks(rawPicks), allDates);
      }
    });

  }, function(err) {
    document.getElementById('loading').innerHTML =
      '<div class="error">Firebase error: ' + err.message + '</div>';
  });
}

function getFiltered() {
  var status   = document.getElementById('status-filter').value;
  var minScore = parseInt(document.getElementById('min-score').value) || 0;
  var setup    = document.getElementById('setup-filter').value;
  var search   = (document.getElementById('ticker-search').value || '').trim().toUpperCase();

  return allPicks.filter(function(p) {
    if (status !== 'all' && p.status !== status) return false;
    if (p.score < minScore) return false;
    if (setup === 'pre_breakout' && !p.pre_breakout) return false;
    if (setup === 'bull_flag'    && !p.bull_flag)    return false;
    if (search && p.ticker.indexOf(search) === -1)   return false;
    return true;
  });
}

function setSort(col) {
  sortCol = col;
  sortAsc = (col === 'ticker_asc');  // A-Z is ascending, everything else descending
  // Update button styles
  var btns = ['date','abc','score','ret1w','ret1m','ret3m'];
  var map  = {scan_date:'date', ticker_asc:'abc', score:'score', ret_1w:'ret1w', ret_1m:'ret1m', ret_3m:'ret3m'};
  btns.forEach(function(b) { document.getElementById('sort-btn-'+b).classList.remove('active'); });
  var active = map[col];
  if (active) document.getElementById('sort-btn-'+active).classList.add('active');
  page = 0;
  render();
}

function render() {
  var tf = document.getElementById('tf-select').value;
  filtered = getFiltered();
  filtered.sort(function(a,b) {
    // A-Z sort
    if (sortCol === 'ticker_asc') {
      return a.ticker < b.ticker ? -1 : a.ticker > b.ticker ? 1 : 0;
    }
    // Return sorts
    if (sortCol.startsWith('ret_')) {
      var key = sortCol.replace('ret_','');
      var va = a.returns && a.returns[key] != null ? a.returns[key] : -Infinity;
      var vb = b.returns && b.returns[key] != null ? b.returns[key] : -Infinity;
      return vb - va;  // highest first
    }
    // Standard sorts (highest first)
    var va = a[sortCol] != null ? a[sortCol] : -Infinity;
    var vb = b[sortCol] != null ? b[sortCol] : -Infinity;
    if (sortCol === 'scan_date') return va < vb ? 1 : va > vb ? -1 : 0;  // newest first
    return vb - va;
  });

  renderKPIs(tf);
  renderTFTable();
  renderSignals(tf);
  renderPicks(tf);
}

function renderKPIs(tf) {
  var picks = filtered.filter(function(p) {
    return p.returns && p.returns[tf] != null;
  });
  if (!picks.length) {
    document.getElementById('kpi-grid').innerHTML =
      '<div style="color:var(--muted);grid-column:1/-1">No data with returns for this window yet.</div>';
    return;
  }
  var rets = picks.map(function(p) { return p.returns[tf]; });
  var wins = rets.filter(function(r) { return r > 0; });
  var loss = rets.filter(function(r) { return r < 0; });
  var winRate = Math.round(wins.length / rets.length * 100);
  var lossRate= Math.round(loss.length / rets.length * 100);
  var avgRet  = round1(rets.reduce(function(a,b){return a+b;},0)/rets.length);
  var avgWin  = wins.length ? round1(wins.reduce(function(a,b){return a+b;},0)/wins.length) : 0;
  var avgLoss = loss.length ? round1(loss.reduce(function(a,b){return a+b;},0)/loss.length) : 0;
  var best    = Math.max.apply(null, rets);
  var worst   = Math.min.apply(null, rets);
  var bestTkr = picks[rets.indexOf(best)].ticker;
  var worstTkr= picks[rets.indexOf(worst)].ticker;

  document.getElementById('kpi-grid').innerHTML = [
    kpi('Win rate', winRate+'%', picks.length+' picks · '+tf+' window', 'green'),
    kpi('Avg return', fmtRet(avgRet), 'all picks', avgRet>=0?'green':'red'),
    kpi('Avg win',  fmtRet(avgWin),  wins.length+' winners', 'green'),
    kpi('Avg loss', fmtRet(avgLoss), loss.length+' losers', 'red'),
    kpi('Best pick', fmtRet(best), bestTkr, 'green'),
    kpi('Worst pick', fmtRet(worst), worstTkr, 'red'),
    kpi('Picks analyzed', picks.length, 'with '+tf+' returns available', 'blue'),
    kpi('Expectancy', fmtRet(winRate/100*avgWin + lossRate/100*avgLoss), 'per trade', avgRet>=0?'green':'red'),
  ].join('');
}

function kpi(label, val, sub, cls) {
  var color = cls==='green'?'var(--green)':cls==='red'?'var(--red)':cls==='amber'?'var(--amber)':'var(--blue)';
  return '<div class="kpi '+cls+'"><div class="kpi-label">'+label+'</div>'
    +'<div class="kpi-val" style="color:'+color+'">'+val+'</div>'
    +'<div class="kpi-sub">'+sub+'</div></div>';
}

function renderTFTable() {
  var windows = ['1w','2w','1m','2m','3m','6m','1y'];
  var rows = {
    'Win rate':  function(w) { return winRateForWindow(w); },
    'Avg return':function(w) { return avgRetForWindow(w); },
    'Avg win':   function(w) { return avgWinForWindow(w); },
    'Avg loss':  function(w) { return avgLossForWindow(w); },
    'Picks w/data': function(w) { return picsWithWindow(w); },
  };
  var html = '';
  for (var label in rows) {
    html += '<tr><td>'+label+'</td>';
    for (var i=0; i<windows.length; i++) {
      var val = rows[label](windows[i]);
      var cls = (label==='Win rate'||label==='Avg win') ? (parseFloat(val)>=50||parseFloat(val)>=0?'pos':'neg')
              : label==='Avg loss' ? 'neg'
              : label==='Avg return' ? (parseFloat(val)>=0?'pos':'neg') : 'na';
      html += '<td class="'+cls+'">'+val+'</td>';
    }
    html += '</tr>';
  }
  document.getElementById('tf-body').innerHTML = html;
}

function picksForWindow(w) {
  return filtered.filter(function(p){return p.returns&&p.returns[w]!=null;});
}
function picsWithWindow(w)  { return picksForWindow(w).length||'—'; }
function winRateForWindow(w) {
  var ps=picksForWindow(w); if(!ps.length)return'—';
  return Math.round(ps.filter(function(p){return p.returns[w]>0;}).length/ps.length*100)+'%';
}
function avgRetForWindow(w) {
  var ps=picksForWindow(w); if(!ps.length)return'—';
  return fmtRet(round1(ps.reduce(function(a,p){return a+p.returns[w];},0)/ps.length));
}
function avgWinForWindow(w) {
  var ps=picksForWindow(w).filter(function(p){return p.returns[w]>0;}); if(!ps.length)return'—';
  return fmtRet(round1(ps.reduce(function(a,p){return a+p.returns[w];},0)/ps.length));
}
function avgLossForWindow(w) {
  var ps=picksForWindow(w).filter(function(p){return p.returns[w]<0;}); if(!ps.length)return'—';
  return fmtRet(round1(ps.reduce(function(a,p){return a+p.returns[w];},0)/ps.length));
}

function renderSignals(tf) {
  var ps = filtered.filter(function(p){return p.returns&&p.returns[tf]!=null;});
  if (!ps.length) { document.getElementById('signal-grid').innerHTML='<div style="color:var(--muted)">Not enough data yet</div>'; return; }

  var signals = [
    {name:'RS percentile > 80', with_fn: function(p){return (p.rs_percentile||0)>=80;}},
    {name:'Vol contraction ≤ 70%', with_fn: function(p){return (p.vol_contraction||1)<=0.7;}},
    {name:'Level = ATH/multi-year', with_fn: function(p){return (p.level||'').indexOf('ATH')>=0||(p.level||'').indexOf('multi')>=0;}},
    {name:'EMA stack = full', with_fn: function(p){return p.ema_stack==='full';}},
    {name:'Pre-breakout', with_fn: function(p){return !!p.pre_breakout;}},
    {name:'Bull flag', with_fn: function(p){return !!p.bull_flag;}},
    {name:'Score ≥ 50', with_fn: function(p){return (p.score||0)>=50;}},
    {name:'Analyst upside > 10%', with_fn: function(p){return (p.analyst_upside||0)>10;}},
    {name:'Analyst buy ≥ 70%', with_fn: function(p){return (p.analyst_buy_pct||0)>=70;}},
    {name:'Earnings in ≤ 14d', with_fn: function(p){return p.days_to_earnings!=null&&p.days_to_earnings>=0&&p.days_to_earnings<=14;}},
  ];

  var html = '';
  for (var i=0; i<signals.length; i++) {
    var sig = signals[i];
    var with_sig = ps.filter(sig.with_fn);
    var without  = ps.filter(function(p){return !sig.with_fn(p);});
    if (with_sig.length < 3) continue;

    var wr_with = with_sig.length ? Math.round(with_sig.filter(function(p){return p.returns[tf]>0;}).length/with_sig.length*100) : 0;
    var wr_wout = without.length  ? Math.round(without.filter(function(p){return p.returns[tf]>0;}).length/without.length*100)  : 0;
    var diff = wr_with - wr_wout;
    var diffStr = (diff>=0?'+':'')+diff+'%';
    var diffCol = diff>=5?'var(--green)':diff<=-5?'var(--red)':'var(--muted)';

    html += '<div class="signal-card">';
    html += '<div class="signal-name">'+sig.name+' <span style="color:var(--muted);font-weight:400;font-size:10px">('+with_sig.length+' picks)</span></div>';
    html += signalBar('With signal', wr_with, 'var(--green)');
    html += signalBar('Without', wr_wout, 'var(--muted)');
    html += '<div class="signal-diff">Difference: <strong style="color:'+diffCol+'">'+diffStr+'</strong> win rate</div>';
    html += '</div>';
  }
  document.getElementById('signal-grid').innerHTML = html || '<div style="color:var(--muted)">Not enough picks yet</div>';
}

function signalBar(label, pct, color) {
  return '<div class="signal-bar-row">'
    +'<div class="signal-bar-label">'+label+'</div>'
    +'<div class="signal-bar-track"><div class="signal-bar-fill" style="width:'+pct+'%;background:'+color+'"></div></div>'
    +'<div class="signal-bar-val" style="color:'+color+'">'+pct+'%</div>'
    +'</div>';
}

function renderPicks(tf) {
  var start = page * pageSize;
  var rows  = filtered.slice(start, start + pageSize);

  var html = '';
  for (var i=0; i<rows.length; i++) {
    var p = rows[i];
    var ret1w = p.returns&&p.returns['1w']!=null ? p.returns['1w'] : null;
    var ret1m = p.returns&&p.returns['1m']!=null ? p.returns['1m'] : null;
    var ret3m = p.returns&&p.returns['3m']!=null ? p.returns['3m'] : null;
    var setup = p.pre_breakout?'Pre-brkout':p.bull_flag?'Bull flag':'Breakout';
    var dol   = p.days_on_list || 1;
    var dolColor = dol >= 5 ? 'var(--green)' : dol >= 3 ? 'var(--amber)' : 'var(--muted)';
    html += '<tr>'
      +'<td>'+p.scan_date+'</td>'
      +'<td><strong>'+p.ticker+'</strong></td>'
      +'<td>$'+(p.price_at_scan?p.price_at_scan.toFixed(2):'—')+'</td>'
      +'<td>'+p.score+'</td>'
      +'<td><span class="badge '+(p.status||'')+'">'+p.status+'</span></td>'
      +'<td>'+setup+'</td>'
      +'<td>'+(p.rs_percentile!=null?p.rs_percentile+'th':'—')+'</td>'
      +'<td>'+(p.vol_contraction!=null?Math.round(p.vol_contraction*100)+'%':'—')+'</td>'
      +'<td>'+(p.atr!=null?p.atr.toFixed(2):'—')+'</td>'
      +'<td>'+(p.level||'—')+'</td>'
      +'<td style="color:'+dolColor+';font-weight:600">'+dol+'d</td>'
      +'<td class="'+(ret1w==null?'ret-na':ret1w>=0?'ret-pos':'ret-neg')+'">'+(ret1w==null?'—':fmtRet(ret1w))+'</td>'
      +'<td class="'+(ret1m==null?'ret-na':ret1m>=0?'ret-pos':'ret-neg')+'">'+(ret1m==null?'—':fmtRet(ret1m))+'</td>'
      +'<td class="'+(ret3m==null?'ret-na':ret3m>=0?'ret-pos':'ret-neg')+'">'+(ret3m==null?'—':fmtRet(ret3m))+'</td>'
      +'</tr>';
  }
  document.getElementById('picks-body').innerHTML = html;
  document.getElementById('picks-count').textContent = '— '+filtered.length+' picks';
  document.getElementById('pg-info').textContent = 'Page '+(page+1)+' of '+Math.ceil(filtered.length/pageSize);
  document.getElementById('pg-prev').disabled = page === 0;
  document.getElementById('pg-next').disabled = (page+1)*pageSize >= filtered.length;
}

function sortBy(col) { if(sortCol===col){sortAsc=!sortAsc;}else{sortCol=col;sortAsc=false;} render(); }
function prevPage() { if(page>0){page--;renderPicks(document.getElementById('tf-select').value);} }
function nextPage() { if((page+1)*pageSize<filtered.length){page++;renderPicks(document.getElementById('tf-select').value);} }
function fmtRet(v) { return (v>=0?'+':'')+v.toFixed(1)+'%'; }
function round1(v) { return Math.round(v*10)/10; }

loadData();
</script>
</body>
</html>"""


@app.route('/')
def index():
    html = HTML.format(
        ver=VERSION,
        cfg=json.dumps(FIREBASE_CONFIG)
    )
    return html

@app.route('/smart-money')
def smart_money():
    cfg_tag = '<script id="fb-cfg" type="application/json">' + json.dumps(FIREBASE_CONFIG) + '</script>'
    return SMART_MONEY_HTML.replace('<!--FB_CONFIG-->', cfg_tag).replace('<!--VERSION-->', VERSION)


SMART_MONEY_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Smart Money Tracker</title>
<style>
:root{--bg:#0f1117;--bg2:#1a1d26;--bg3:#22263a;--text:#e8eaf0;--muted:#8892a4;--border:#2a2f42;--green:#27ae60;--amber:#e67e22;--blue:#3498db;--red:#e74c3c;--purple:#9b59b6;}
*{box-sizing:border-box;margin:0;padding:0;}
body{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;font-size:14px;}
.header{background:var(--bg2);border-bottom:1px solid var(--border);padding:12px 24px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px;position:sticky;top:0;z-index:100;min-height:56px;}
.header h1{font-size:16px;font-weight:600;}
.header p{font-size:11px;color:var(--muted);margin-top:1px;}
.hright{display:flex;align-items:center;gap:10px;}
.ver{font-size:10px;color:var(--muted);background:var(--bg3);border:1px solid var(--border);padding:3px 8px;border-radius:20px;font-family:monospace;}
.nav-pills{display:flex;gap:6px;align-items:center;}
.nav-pill{padding:5px 14px;border-radius:20px;font-size:12px;font-weight:600;text-decoration:none;border:1px solid var(--border);color:var(--muted);transition:all .15s;background:var(--bg3);}
.nav-pill:hover{color:var(--text);border-color:var(--blue);}
.nav-pill.active{background:var(--blue);color:#fff;border-color:var(--blue);}
.ver{font-size:10px;color:var(--muted);background:var(--bg3);border:1px solid var(--border);padding:3px 8px;border-radius:20px;font-family:monospace;}
.regime{padding:4px 12px;border-radius:20px;font-size:11px;font-weight:600;border:1px solid;}
.regime.open{background:#1a3d2b;color:#27ae60;border-color:#27ae6055;}
.regime.pre{background:#1a2a3d;color:#3498db;border-color:#3498db55;}
.regime.after{background:#2d1a3d;color:#9b59b6;border-color:#9b59b655;}
.regime.closed{background:var(--bg3);color:var(--muted);border-color:var(--border);}
.page{padding:24px;}
.loading{text-align:center;padding:60px;color:var(--muted);font-size:15px;}
.error{color:var(--red);padding:20px;text-align:center;}
.section{background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:20px;margin-bottom:24px;}
.section h2{font-size:15px;font-weight:700;margin-bottom:4px;display:flex;align-items:center;gap:8px;}
.section .sub{font-size:11px;color:var(--muted);margin-bottom:16px;}
.meta{font-size:11px;color:var(--muted);margin-bottom:16px;}
/* Table */
.sm-table{width:100%;border-collapse:collapse;font-size:12px;}
.sm-table th{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;padding:8px 10px;text-align:left;border-bottom:1px solid var(--border);white-space:nowrap;}
.sm-table td{padding:9px 10px;border-bottom:1px solid var(--border)22;vertical-align:middle;}
.sm-table tr:hover td{background:#ffffff05;}
.sm-table tr:last-child td{border-bottom:none;}
.ticker-badge{font-size:13px;font-weight:700;color:var(--text);}
.scanner-match{display:inline-block;font-size:9px;background:#1a3d2b;color:var(--green);border:1px solid var(--green)44;border-radius:20px;padding:2px 7px;margin-left:6px;font-weight:600;}
.value-big{font-size:13px;font-weight:700;color:var(--green);}
.value-neg{color:var(--red);}
.role-badge{font-size:9px;padding:2px 7px;border-radius:20px;font-weight:600;background:var(--bg3);color:var(--muted);}
.role-badge.ceo{background:#1a2a3d;color:var(--blue);}
.role-badge.dir{background:#2d1a3d;color:var(--purple);}
.role-badge.own{background:#3d2e10;color:var(--amber);}
/* Fund cards */
.fund-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:16px;}
.fund-card{background:var(--bg3);border-radius:10px;padding:16px;}
.fund-name{font-size:13px;font-weight:700;margin-bottom:2px;}
.fund-meta{font-size:10px;color:var(--muted);margin-bottom:12px;}
.holding-row{display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--border)33;}
.holding-row:last-child{border-bottom:none;}
.h-ticker{font-size:13px;font-weight:700;width:60px;flex-shrink:0;}
.h-name{font-size:11px;color:var(--muted);flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.h-value{font-size:11px;font-weight:600;text-align:right;flex-shrink:0;}
.h-bar{height:4px;background:var(--blue);border-radius:2px;margin-top:3px;}
/* Search */
.search-box{background:var(--bg3);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:6px 12px;font-size:12px;outline:none;width:180px;text-transform:uppercase;}
.search-box:focus{border-color:var(--blue);}
.toolbar{display:flex;align-items:center;gap:10px;margin-bottom:14px;flex-wrap:wrap;}
.updated{font-size:11px;color:var(--muted);}
</style>
<!--FB_CONFIG-->
<script src="https://www.gstatic.com/firebasejs/9.23.0/firebase-app-compat.js"></script>
<script src="https://www.gstatic.com/firebasejs/9.23.0/firebase-database-compat.js"></script>
<script>
var CFG = JSON.parse(document.getElementById('fb-cfg').textContent);
try { firebase.initializeApp(CFG); } catch(e) {}
var fdb = firebase.database();
</script>
</head>
<body>
<div class="header">
  <div>
    <h1>🏦 Smart Money Tracker</h1>
    <p>Insider transactions &amp; hedge fund holdings — see what big players are buying</p>
  </div>
  <div class="hright">
    <div class="nav-pills"><a class="nav-pill" href="/">&#128202; Dashboard</a><a class="nav-pill" href="/analytics">&#128200; Analytics</a><a class="nav-pill active" href="/smart-money">&#127974; Smart Money</a><a class="nav-pill" href="/optimizer">&#128202; Optimizer</a></div>
    <span class="ver"><!--VERSION--></span>
    <span class="regime closed" id="regime-badge">&#9675; Checking...</span>
  </div>
</div>
<script>
(function(){
  var n=new Date(),h=(n.getUTCHours()-4+24)%24,m=n.getUTCMinutes(),d=n.getUTCDay(),t=h*60+m;
  var el=document.getElementById('regime-badge');
  if(d===0||d===6){el.textContent='○ Market Closed';el.className='regime closed';}
  else if(t>=570&&t<960){el.textContent='● Market Open';el.className='regime open';}
  else if(t>=240&&t<570){el.textContent='◐ Pre-Market';el.className='regime pre';}
  else if(t>=960&&t<1200){el.textContent='◑ After-Hours';el.className='regime after';}
  else{el.textContent='○ Market Closed';el.className='regime closed';}
})();
</script>

<div class="page">
  <div id="loading" class="loading">⏳ Loading smart money data...</div>
  <div id="content" style="display:none">

    <!-- Insider Buying -->
    <div class="section">
      <h2>👤 Insider Buying
        <span id="insider-count" style="font-size:11px;color:var(--muted);font-weight:400"></span>
      </h2>
      <p class="sub">Form 4 filings — purchases &gt; $100K by executives, directors &amp; 10% owners. Updated daily.</p>
      <div class="toolbar">
        <input type="text" class="search-box" id="insider-search" placeholder="🔍 Search ticker…"
          oninput="this.value=this.value.toUpperCase();renderInsiders()">
        <span class="updated" id="last-updated"></span>
      </div>
      <table class="sm-table">
        <thead>
          <tr>
            <th>Date</th>
            <th>Ticker</th>
            <th>Company</th>
            <th>Insider</th>
            <th>Role</th>
            <th>Shares</th>
            <th>Price</th>
            <th>Value</th>
            <th>Owns after</th>
          </tr>
        </thead>
        <tbody id="insider-body"></tbody>
      </table>
    </div>

    <!-- Institutional Holdings -->
    <div class="section">
      <h2>🏛️ Hedge Fund Holdings
        <span style="font-size:11px;color:var(--muted);font-weight:400"> — latest 13F filings</span>
      </h2>
      <p class="sub">Top 10 positions per fund. Quarterly data — filed 45 days after quarter end.</p>
      <div id="fund-grid" class="fund-grid"></div>
    </div>

  </div>
</div>

<script>
var insiderData      = [];
var institutionData  = [];
var scannerTickers   = new Set();

function fmtVal(v) {
  if (!v) return '—';
  if (v >= 1e9) return '$' + (v/1e9).toFixed(1) + 'B';
  if (v >= 1e6) return '$' + (v/1e6).toFixed(1) + 'M';
  if (v >= 1e3) return '$' + (v/1e3).toFixed(0) + 'K';
  return '$' + v;
}

function fmtShares(v) {
  if (!v) return '—';
  if (v >= 1e6) return (v/1e6).toFixed(2) + 'M';
  if (v >= 1e3) return (v/1e3).toFixed(1) + 'K';
  return v.toLocaleString();
}

function roleClass(title) {
  var t = (title||'').toLowerCase();
  if (t.includes('ceo') || t.includes('chief executive')) return 'ceo';
  if (t.includes('director')) return 'dir';
  if (t.includes('owner') || t.includes('10%')) return 'own';
  return '';
}

function renderInsiders() {
  var search = (document.getElementById('insider-search').value || '').trim();
  var rows = insiderData.filter(function(r) {
    if (search && r.ticker.indexOf(search) === -1 && (r.company||'').toUpperCase().indexOf(search) === -1) return false;
    return true;
  });

  document.getElementById('insider-count').textContent = '— ' + rows.length + ' transactions';

  var html = '';
  rows.forEach(function(r) {
    var match = scannerTickers.has(r.ticker);
    var rc = roleClass(r.title);
    html += '<tr>'
      + '<td>' + (r.date||'—') + '</td>'
      + '<td><span class="ticker-badge">' + r.ticker + '</span>'
      + (match ? '<span class="scanner-match">📡 In scanner</span>' : '') + '</td>'
      + '<td style="color:var(--muted);max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + (r.company||'—') + '</td>'
      + '<td style="max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + (r.insider||'—') + '</td>'
      + '<td><span class="role-badge ' + rc + '">' + (r.title||'Insider') + '</span></td>'
      + '<td>' + fmtShares(r.shares) + '</td>'
      + '<td>' + (r.price ? '$' + r.price.toFixed(2) : '—') + '</td>'
      + '<td class="value-big">' + fmtVal(r.value) + '</td>'
      + '<td style="color:var(--muted)">' + fmtShares(r.owned_after) + '</td>'
      + '</tr>';
  });
  document.getElementById('insider-body').innerHTML = html ||
    '<tr><td colspan="9" style="color:var(--muted);text-align:center;padding:30px">No insider buys found matching your search.</td></tr>';
}

function renderInstitutions() {
  var html = '';
  institutionData.forEach(function(fund) {
    var maxVal = fund.holdings && fund.holdings.length ? fund.holdings[0].value : 1;
    html += '<div class="fund-card">';
    html += '<div class="fund-name">' + fund.fund + '</div>';
    html += '<div class="fund-meta">Filed: ' + (fund.filed||'—') + ' · Portfolio tracked: ' + fmtVal(fund.total_value) + '</div>';
    (fund.holdings||[]).forEach(function(h) {
      var match = h.ticker && scannerTickers.has(h.ticker);
      var barW  = Math.round(h.value / maxVal * 100);
      html += '<div class="holding-row">';
      html += '<div><div class="h-ticker">' + (h.ticker || '—') + (match ? ' 📡' : '') + '</div>'
            + '<div class="h-bar" style="width:' + barW + '%"></div></div>';
      html += '<div class="h-name">' + h.name + '</div>';
      html += '<div class="h-value">' + fmtVal(h.value) + '</div>';
      html += '</div>';
    });
    html += '</div>';
  });
  document.getElementById('fund-grid').innerHTML = html ||
    '<div style="color:var(--muted);padding:20px">No institutional data yet. Run smart_money.py on the VM.</div>';
}

function loadData() {
  // Load current scanner tickers for cross-referencing
  fdb.ref('scanner/all_stocks').once('value', function(snap) {
    var stocks = snap.val() || {};
    scannerTickers = new Set(Object.keys(stocks));
  });

  fdb.ref('scanner/smart_money').once('value', function(snap) {
    var data = snap.val();
    if (!data) {
      document.getElementById('loading').innerHTML =
        '<div class="error">No smart money data yet.<br><br>'
        + '<code style="font-size:12px;color:var(--muted)">python smart_money.py</code><br>'
        + '<span style="font-size:12px;color:var(--muted)">Run on the VM to populate data.</span></div>';
      return;
    }

    insiderData     = data.insiders     || [];
    institutionData = data.institutions || [];

    var updated = data.last_updated ? new Date(data.last_updated).toLocaleString() : '—';
    document.getElementById('last-updated').textContent = 'Last updated: ' + updated;

    renderInsiders();
    renderInstitutions();

    document.getElementById('loading').style.display = 'none';
    document.getElementById('content').style.display = 'block';
  }, function(err) {
    document.getElementById('loading').innerHTML =
      '<div class="error">Firebase error: ' + err.message + '</div>';
  });
}

loadData();
</script>
</body>
</html>"""


@app.route('/api/analytics')
def api_analytics():
    """Return flat list of all historical picks with returns via Firebase REST."""
    try:
        db_url = FIREBASE_CONFIG.get('databaseURL','')
        resp = requests.get(
            f"{db_url}/scanner/history.json",
            timeout=30
        )
        if not resp.ok:
            return jsonify({'error': f'Firebase error {resp.status_code}'}), 500
        history = resp.json() or {}
        picks = []
        for day_str, day_data in history.items():
            if not isinstance(day_data, dict):
                continue
            for ticker, pick in day_data.items():
                if isinstance(pick, dict):
                    pick['scan_date'] = day_str
                    picks.append(pick)
        return jsonify(picks)
    except Exception as e:
        return jsonify({'error': str(e)}), 500



@app.route('/ai')
@app.route('/optimizer')
def ai_page():
    cfg_tag = f'<script>var FIREBASE_CONFIG={json.dumps(FIREBASE_CONFIG)};</script>'
    return AI_HTML.replace('<!--FB_CONFIG-->', cfg_tag).replace('<!--VERSION-->', VERSION)

@app.route('/api/recommendations/<rec_id>/approve', methods=['POST'])
def approve_recommendation(rec_id):
    try:
        db_url = FIREBASE_CONFIG.get('databaseURL', '')
        # Read the recommendation
        resp = requests.get(f"{db_url}/scanner/ai_recommendations/{rec_id}.json", timeout=10)
        if not resp.ok or not resp.json():
            return jsonify({'error': 'Recommendation not found'}), 404
        rec = resp.json()
        proposed = rec.get('proposed_weights', {})
        # Mark as approved + store approved weights
        requests.patch(
            f"{db_url}/scanner/ai_recommendations/{rec_id}.json",
            json={'status': 'approved', 'approved_at': __import__('datetime').datetime.now().isoformat()},
            timeout=10
        )
        requests.put(
            f"{db_url}/scanner/approved_weights.json",
            json={**proposed, '_approved_from': rec_id, '_approved_at': __import__('datetime').datetime.now().isoformat()},
            timeout=10
        )
        return jsonify({'ok': True, 'message': 'Approved. Run python ai_optimizer.py --apply on the VM to update live_scanner.py.'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/recommendations/<rec_id>/reject', methods=['POST'])
def reject_recommendation(rec_id):
    try:
        db_url = FIREBASE_CONFIG.get('databaseURL', '')
        requests.patch(
            f"{db_url}/scanner/ai_recommendations/{rec_id}.json",
            json={'status': 'rejected', 'rejected_at': __import__('datetime').datetime.now().isoformat()},
            timeout=10
        )
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/optimizer-suggestions/approve', methods=['POST'])
def approve_optimizer_suggestion():
    """Approve a statistically-derived optimizer suggestion."""
    try:
        import datetime
        data     = request.get_json()
        weights  = data.get('weights', {})
        label    = data.get('label', 'Optimizer suggestion')
        db_url   = FIREBASE_CONFIG.get('databaseURL', '')
        ts       = datetime.datetime.now().isoformat()
        rec_id   = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        # Save suggestion record
        requests.put(
            f"{db_url}/scanner/optimizer_suggestions/{rec_id}.json",
            json={'label': label, 'weights': weights, 'approved_at': ts, 'status': 'approved'},
            timeout=10
        )
        # Write to approved_weights (same path as AI suggestions)
        requests.put(
            f"{db_url}/scanner/approved_weights.json",
            json={**weights, '_approved_from': f'optimizer_{rec_id}', '_approved_at': ts},
            timeout=10
        )
        return jsonify({'ok': True, 'message': 'Approved. Run python ai_optimizer.py --apply on the VM to update live_scanner.py.'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/run-ai-analysis', methods=['POST'])
def run_ai_analysis():
    """Set Firebase flag to trigger AI optimizer on the VM."""
    try:
        import datetime as dt
        db_url = FIREBASE_CONFIG.get('databaseURL', '')
        requests.put(
            f"{db_url}/scanner/run_ai_requested.json",
            json={'status': 'pending', 'requested_at': dt.datetime.now().isoformat()},
            timeout=10
        )
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


AI_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Optimizer <!--VERSION--></title>
<style>
:root{--bg:#0f1117;--bg2:#1a1d26;--bg3:#22263a;--text:#e8eaf0;--muted:#8892a4;--border:#2a2f42;--green:#27ae60;--amber:#e67e22;--blue:#3498db;--red:#e74c3c;--purple:#9b59b6;}
*{box-sizing:border-box;margin:0;padding:0;}
body{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;font-size:14px;}
.header{background:var(--bg2);border-bottom:1px solid var(--border);padding:12px 24px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px;position:sticky;top:0;z-index:100;min-height:56px;}
.header h1{font-size:16px;font-weight:600;}.header p{font-size:11px;color:var(--muted);margin-top:1px;}
.hright{display:flex;align-items:center;gap:10px;}
.ver{font-size:10px;color:var(--muted);background:var(--bg3);border:1px solid var(--border);padding:3px 8px;border-radius:20px;font-family:monospace;}
.nav-pills{display:flex;gap:6px;align-items:center;}
.nav-pill{padding:5px 14px;border-radius:20px;font-size:12px;font-weight:600;text-decoration:none;border:1px solid var(--border);color:var(--muted);transition:all .15s;background:var(--bg3);}
.nav-pill:hover{color:var(--text);border-color:var(--blue);}
.nav-pill.active{background:var(--purple);color:#fff;border-color:var(--purple);}
.regime{padding:4px 12px;border-radius:20px;font-size:11px;font-weight:600;border:1px solid;}
.regime.open{background:#1a3d2b;color:var(--green);border-color:#27ae6055;}
.regime.pre{background:#1a2a3d;color:var(--blue);border-color:#3498db55;}
.regime.after{background:#2d1a3d;color:#9b59b6;border-color:#9b59b655;}
.regime.closed{background:var(--bg3);color:var(--muted);border-color:var(--border);}
.page{max-width:1200px;margin:0 auto;padding:24px;display:flex;flex-direction:column;gap:32px;}
.section{background:var(--bg2);border:1px solid var(--border);border-radius:16px;overflow:hidden;}
.section-head{padding:18px 24px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;gap:12px;}
.section-title{font-size:15px;font-weight:700;}
.section-sub{font-size:11px;color:var(--muted);margin-top:2px;}
.section-body{padding:24px;}
.badge{display:inline-block;padding:3px 10px;border-radius:20px;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;}
.badge-stat{background:#1a2a3d;color:var(--blue);border:1px solid #3498db44;}
.badge-ai{background:#2d1a3d;color:var(--purple);border:1px solid #9b59b644;}
.badge-approved{background:#1a3d2b;color:var(--green);border:1px solid #27ae6044;}
.badge-rejected{background:#3d1a1a;color:var(--red);border:1px solid #e74c3c44;}
.badge-pending{background:#1a2a3d;color:var(--blue);border:1px solid #3498db44;}
.badge-applied{background:#1a3d2b;color:var(--green);border:1px solid #27ae6044;}

/* Empty state */
.empty-state{text-align:center;padding:40px 24px;color:var(--muted);}
.empty-state h3{color:var(--text);font-size:15px;margin-bottom:8px;}
.cmd-block{background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:14px 18px;display:inline-block;margin-top:14px;text-align:left;font-size:12px;font-family:monospace;color:var(--green);line-height:1.8;}

/* Stats bar */
.stats-row{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:20px;}
.stat-box{background:var(--bg3);border-radius:10px;padding:14px 18px;flex:1;min-width:120px;text-align:center;}
.stat-box-lbl{font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px;}
.stat-box-val{font-size:22px;font-weight:700;}
.stat-box-sub{font-size:10px;color:var(--muted);margin-top:3px;}

/* Comparison stats */
.cmp-grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:20px;}
.cmp-card{border-radius:10px;padding:16px;text-align:center;border:1px solid var(--border);}
.cmp-card.cur{background:var(--bg3);}
.cmp-card.proj{background:#0f1f14;border-color:#27ae6044;}
.cmp-card.delta{background:#1a1033;border-color:#9b59b644;}
.cmp-lbl{font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px;}
.cmp-val{font-size:28px;font-weight:700;line-height:1;}
.cmp-sub{font-size:10px;color:var(--muted);margin-top:6px;}

/* Factor table */
.factor-table{width:100%;border-collapse:collapse;font-size:12px;}
.factor-table th{font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;padding:8px 10px;text-align:left;border-bottom:1px solid var(--border);white-space:nowrap;}
.factor-table td{padding:10px;border-bottom:1px solid var(--border);vertical-align:middle;}
.factor-table tr:last-child td{border-bottom:none;}
.factor-table tr:hover td{background:#ffffff04;}
.lift-bar{height:6px;border-radius:3px;margin-top:4px;}
.edge-pill{padding:2px 8px;border-radius:20px;font-size:10px;font-weight:700;white-space:nowrap;}
.edge-strong{background:#1a3d2b;color:var(--green);}
.edge-mild{background:#3d2e10;color:var(--amber);}
.edge-weak{background:var(--bg3);color:var(--muted);}
.edge-hurts{background:#3d1a1a;color:var(--red);}

/* Suggestions */
.suggestions{display:flex;flex-direction:column;gap:8px;margin-top:20px;}
.suggestion-item{background:var(--bg3);border-radius:10px;padding:14px 16px;border:1px solid var(--border);display:flex;align-items:center;gap:12px;flex-wrap:wrap;}
.sug-factor{flex:1;min-width:180px;}
.sug-factor-name{font-size:13px;font-weight:600;}
.sug-factor-reason{font-size:11px;color:var(--muted);margin-top:3px;}
.sug-change{display:flex;align-items:center;gap:8px;flex-shrink:0;}
.val-chip{padding:4px 10px;border-radius:6px;font-size:13px;font-weight:700;font-family:monospace;}
.val-cur{background:var(--bg);color:var(--muted);}
.val-up{background:#1a3d2b;color:var(--green);}
.val-down{background:#3d1a1a;color:var(--red);}
.val-arrow{color:var(--muted);font-size:12px;}

/* Changes table (AI section) */
.changes-table{width:100%;border-collapse:collapse;}
.changes-table th{font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;padding:8px 12px;text-align:left;border-bottom:1px solid var(--border);}
.changes-table td{padding:12px;border-bottom:1px solid var(--border);font-size:13px;vertical-align:top;}
.changes-table tr:last-child td{border-bottom:none;}
.changes-table tr:hover td{background:#ffffff04;}
.reason-text{font-size:11px;color:var(--muted);margin-top:4px;line-height:1.5;}

/* Reasoning */
.reasoning{font-size:13px;line-height:1.8;color:var(--text);margin-bottom:20px;padding:16px;background:var(--bg3);border-radius:10px;}

/* Action bar */
.action-bar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:16px 20px;background:var(--bg);border-top:1px solid var(--border);}
.btn{padding:9px 22px;border-radius:8px;font-size:13px;font-weight:600;cursor:pointer;border:none;transition:all .15s;}
.btn-approve{background:var(--green);color:#fff;}.btn-approve:hover{background:#219a52;}
.btn-reject{background:transparent;color:var(--red);border:1px solid var(--red);}.btn-reject:hover{background:#3d1a1a;}
.btn-disabled{background:var(--bg3);color:var(--muted);cursor:not-allowed;}
.action-note{font-size:11px;color:var(--muted);flex:1;}
code{background:var(--bg);padding:2px 6px;border-radius:4px;font-family:monospace;font-size:11px;}

/* History selector */
.hist-list{display:flex;flex-direction:column;gap:6px;margin-bottom:20px;}
.hist-item{background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:10px 14px;display:flex;align-items:center;gap:12px;cursor:pointer;transition:border-color .15s;}
.hist-item:hover{border-color:var(--blue);}
.hist-item.active{border-color:var(--purple);}
.hist-ts{font-size:11px;color:var(--muted);flex-shrink:0;width:150px;}
.hist-sum{flex:1;font-size:12px;}
.hist-delta{font-size:13px;font-weight:700;flex-shrink:0;}

.fg{color:var(--green);}.fr{color:var(--red);}.fa{color:var(--amber);}
.pgfoot{padding:14px 24px;color:var(--muted);font-size:11px;border-top:1px solid var(--border);text-align:center;}
</style>
</head>
<body>
<!--FB_CONFIG-->
<div class="header">
  <div>
    <h1>&#128202; Optimizer</h1>
    <p>Statistical factor analysis + Claude AI &middot; shadow-backtested on 180 days &middot; approve to apply</p>
  </div>
  <div class="hright">
    <div class="nav-pills">
      <a class="nav-pill" href="/">&#128202; Dashboard</a>
      <a class="nav-pill" href="/analytics">&#128200; Analytics</a>
      <a class="nav-pill" href="/smart-money">&#127974; Smart Money</a>
      <a class="nav-pill active" href="/optimizer">&#128202; Optimizer</a>
    </div>
    <span class="ver"><!--VERSION--></span>
    <span class="regime closed" id="regime-badge">&#9675; Checking...</span>
  </div>
</div>
<script>
(function(){
  var n=new Date(),h=(n.getUTCHours()-4+24)%24,m=n.getUTCMinutes(),d=n.getUTCDay(),t=h*60+m;
  var el=document.getElementById('regime-badge');
  if(d===0||d===6){el.textContent='○ Market Closed';el.className='regime closed';}
  else if(t>=570&&t<960){el.textContent='● Market Open';el.className='regime open';}
  else if(t>=240&&t<570){el.textContent='◐ Pre-Market';el.className='regime pre';}
  else if(t>=960&&t<1200){el.textContent='◑ After-Hours';el.className='regime after';}
  else{el.textContent='○ Market Closed';el.className='regime closed';}
})();
</script>

<div class="page" id="page">
  <div style="text-align:center;padding:60px;color:var(--muted)">&#9203; Loading...</div>
</div>
<div class="pgfoot">Optimizer <!--VERSION--> &middot; Statistical analysis + Claude claude-opus-4-5 &middot; &#9888; Always review before approving.</div>

<script src="https://www.gstatic.com/firebasejs/9.23.0/firebase-app-compat.js"></script>
<script src="https://www.gstatic.com/firebasejs/9.23.0/firebase-database-compat.js"></script>
<script>
firebase.initializeApp(FIREBASE_CONFIG);
var fdb = firebase.database();

// Current default weights (mirrors live_scanner.py + ai_optimizer.py)
var DEFAULT_WEIGHTS = {
  breakout_momentum_max:  28,
  breakout_ema_full:      22,
  breakout_ema_partial:   12,
  breakout_hh_hl_strong:   6,
  breakout_hh_hl_ok:       3,
  breakout_atr_max:       12,
  breakout_vol_max:        8,
  breakout_dist_max:      18,
  breakout_liquidity_max:  7,
  penalty_weak_ema:       18,
  penalty_far_dist:       12,
  penalty_neg_mom:        12,
  penalty_high_vol_atr:    8,
  threshold_ready:        72,
  threshold_watch:        55
};

// Factor name → weight key mapping
var FACTOR_WEIGHT_MAP = {
  'EMA stack = FULL':       'breakout_ema_full',
  'EMA stack = PARTIAL':    'breakout_ema_partial',
  'EMA stack = WEAK':       'penalty_weak_ema',
  'Vol dry ≤ 50%':     'breakout_vol_max',
  'Vol dry ≤ 70%':     'breakout_vol_max',
  'ATR ≤ 0.25':        'breakout_atr_max',
  'ATR ≤ 0.35':        'breakout_atr_max',
  'HH/HL ≥ 0.85':      'breakout_hh_hl_strong',
  'HH/HL ≥ 0.70':      'breakout_hh_hl_ok',
  'Momentum 1M ≥ +15%':'breakout_momentum_max',
  'Momentum 1M ≥ +8%': 'breakout_momentum_max',
  'Dist ≤ 1%':         'breakout_dist_max',
  'Dist ≤ 3%':         'breakout_dist_max',
  'Status = READY':         'threshold_ready',
  'Status = WATCH':         'threshold_watch'
};

var optReports = {}, aiRecs = {}, currentAiId = null, aiFlag = null;

// Load all data sources in parallel
var loaded = {opt: false, ai: false, flag: false};
function checkReady() {
  if (loaded.opt && loaded.ai && loaded.flag) renderPage();
}

fdb.ref('/scanner/optimization_reports').on('value', function(snap) {
  optReports = snap.val() || {};
  loaded.opt = true;
  checkReady();
});

fdb.ref('/scanner/ai_recommendations').on('value', function(snap) {
  aiRecs = snap.val() || {};
  var ids = Object.keys(aiRecs).sort().reverse();
  if (!currentAiId || !aiRecs[currentAiId]) currentAiId = ids[0] || null;
  loaded.ai = true;
  checkReady();
});

fdb.ref('/scanner/run_ai_requested').on('value', function(snap) {
  aiFlag = snap.val();
  loaded.flag = true;
  // Re-render just the button area if already loaded
  if (loaded.opt && loaded.ai) renderPage();
});

// ── Helpers ───────────────────────────────────────────────────────────────────
function fmt(v, sign) {
  if (v == null) return '—';
  return (sign && v >= 0 ? '+' : '') + parseFloat(v).toFixed(1) + '%';
}
function fmtAvg(v) {
  if (v == null) return '—';
  return (parseFloat(v) >= 0 ? '+' : '') + parseFloat(v).toFixed(2) + '%';
}
function dc(v) { return parseFloat(v) > 0 ? 'fg' : parseFloat(v) < 0 ? 'fr' : ''; }

function edgePill(lift) {
  lift = parseFloat(lift) || 0;
  if (lift >= 10) return '<span class="edge-pill edge-strong">&#11088; Strong</span>';
  if (lift >= 5)  return '<span class="edge-pill edge-mild">&#128993; Mild</span>';
  if (lift >= 0)  return '<span class="edge-pill edge-weak">&#9898; Weak</span>';
  return '<span class="edge-pill edge-hurts">&#128308; Hurts</span>';
}

function statusBadge(status, applied) {
  if (applied) return '<span class="badge badge-applied">&#9679; Applied</span>';
  var map = {pending:'badge-pending &#9711; Pending', approved:'badge-approved &#10003; Approved', rejected:'badge-rejected &#10005; Rejected'};
  var v = map[status] || 'badge-pending &#9711; Pending';
  var cls = v.split(' ')[0], txt = v.split(' ').slice(1).join(' ');
  return '<span class="badge '+cls+'">'+txt+'</span>';
}

// ── Derive optimizer suggestions from factor analysis ─────────────────────────
function deriveOptSuggestions(factors) {
  var seen = {}, suggestions = [];
  factors.forEach(function(f) {
    var lift = parseFloat(f.wr_lift) || 0;
    var wKey = FACTOR_WEIGHT_MAP[f.factor];
    if (!wKey || seen[wKey]) return;
    seen[wKey] = true;
    var cur = DEFAULT_WEIGHTS[wKey];
    if (cur == null) return;
    var proposed = cur;
    var reason = '';
    if (lift >= 10) {
      proposed = Math.round(cur * 1.25);
      reason = 'Strong predictor (+' + lift.toFixed(1) + '% WR lift) — increase weight by 25%';
    } else if (lift >= 5) {
      proposed = Math.round(cur * 1.15);
      reason = 'Mild predictor (+' + lift.toFixed(1) + '% WR lift) — increase weight by 15%';
    } else if (lift <= -10) {
      proposed = Math.round(cur * 0.70);
      reason = 'Hurts performance (' + lift.toFixed(1) + '% WR drag) — decrease weight by 30%';
    } else if (lift <= -5) {
      proposed = Math.round(cur * 0.80);
      reason = 'Drags performance (' + lift.toFixed(1) + '% WR drag) — decrease weight by 20%';
    } else { return; }
    if (proposed === cur) return;
    suggestions.push({weight_key: wKey, factor: f.factor, current_value: cur, proposed_value: proposed, reason: reason, wr_lift: lift});
  });
  return suggestions;
}

// ── RENDER ────────────────────────────────────────────────────────────────────
function renderPage() {
  var page = document.getElementById('page');
  var h = '';

  // ══ SECTION 1: STATISTICAL OPTIMIZER ══════════════════════════════════════
  h += '<div class="section">';
  h += '<div class="section-head">';
  h += '<div><div class="section-title">&#128202; Statistical Optimizer <span class="badge badge-stat">Factor Analysis</span></div>';
  h += '<div class="section-sub">Analyzes which signals actually predict winning trades — no AI involved</div></div>';
  var optIds = Object.keys(optReports).sort().reverse();
  if (optIds.length) {
    var latest = optReports[optIds[0]];
    h += '<div style="font-size:11px;color:var(--muted)">Last run: '+optIds[0].replace(/_/g,' ')+'</div>';
  }
  h += '</div>';
  h += '<div class="section-body">';

  if (!optIds.length) {
    h += '<div class="empty-state"><h3>No optimizer data yet</h3>';
    h += '<p>Run the optimizer on the VM to generate factor analysis:</p>';
    h += '<div class="cmd-block">cd /home/scanner<br>/home/scanner/venv/bin/python optimizer.py --all-windows</div></div>';
  } else {
    var rep = optReports[optIds[0]];
    var win = rep.windows && rep.windows[0] ? rep.windows[0] : '1m';
    var rData = (rep.reports || {})[win] || {};
    var stats = rData.stats || {};
    var factors = rData.factors || [];
    var bands = rData.bands || [];

    // Overall stats
    h += '<div class="stats-row">';
    h += '<div class="stat-box"><div class="stat-box-lbl">Picks analyzed</div><div class="stat-box-val">'+(stats.total_picks||'—')+'</div><div class="stat-box-sub">'+(stats.date_range||'')+'</div></div>';
    h += '<div class="stat-box"><div class="stat-box-lbl">Win Rate</div><div class="stat-box-val '+(parseFloat(stats.win_rate)>=55?'fg':parseFloat(stats.win_rate)>=45?'fa':'fr')+'">'+fmt(stats.win_rate,false)+'</div><div class="stat-box-sub">'+win+' window</div></div>';
    h += '<div class="stat-box"><div class="stat-box-lbl">Avg Return</div><div class="stat-box-val '+dc(stats.avg_return)+'">'+fmtAvg(stats.avg_return)+'</div><div class="stat-box-sub">per pick</div></div>';
    h += '<div class="stat-box"><div class="stat-box-lbl">Best Pick</div><div class="stat-box-val fg">'+fmt(stats.best,true)+'</div></div>';
    h += '<div class="stat-box"><div class="stat-box-lbl">Worst Pick</div><div class="stat-box-val fr">'+fmt(stats.worst,true)+'</div></div>';
    h += '</div>';

    // Factor table
    if (factors.length) {
      h += '<div style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);margin-bottom:10px;">Factor Analysis — sorted by win-rate lift</div>';
      h += '<div style="overflow-x:auto"><table class="factor-table">';
      h += '<thead><tr><th>Factor</th><th>N picks</th><th>WR with</th><th>WR without</th><th>WR Lift</th><th>Avg with</th><th>Edge</th></tr></thead><tbody>';
      factors.forEach(function(f) {
        var lift = parseFloat(f.wr_diff || f.wr_lift) || 0;
        var barColor = lift >= 5 ? 'var(--green)' : lift >= 0 ? 'var(--amber)' : 'var(--red)';
        var barW = Math.min(100, Math.abs(lift) * 4);
        h += '<tr>';
        h += '<td><strong>'+f.factor+'</strong>';
        h += '<div class="lift-bar" style="width:'+barW+'%;background:'+barColor+'"></div></td>';
        h += '<td>'+(f.n_with||f.n||'—')+'</td>';
        h += '<td class="'+(parseFloat(f.wr_with)>=55?'fg':parseFloat(f.wr_with)>=45?'fa':'fr')+'">'+fmt(f.wr_with,false)+'</td>';
        h += '<td>'+fmt(f.wr_without||f.wr_wout,false)+'</td>';
        h += '<td class="'+(lift>0?'fg':lift<0?'fr':'')+'"><strong>'+fmt(lift,true)+'</strong></td>';
        h += '<td class="'+(parseFloat(f.avg_ret_with||f.avg_with)>0?'fg':parseFloat(f.avg_ret_with||f.avg_with)<0?'fr':'')+'">'+fmtAvg(f.avg_ret_with||f.avg_with)+'</td>';
        h += '<td>'+edgePill(lift)+'</td>';
        h += '</tr>';
      });
      h += '</tbody></table></div>';
    }

    // Auto-generated suggestions
    var sugs = deriveOptSuggestions(factors);
    if (sugs.length) {
      h += '<div style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);margin:20px 0 10px;">Auto-generated Suggestions ('+sugs.length+')</div>';
      h += '<div class="suggestions" id="opt-sugs">';
      sugs.forEach(function(s) {
        var up = s.proposed_value > s.current_value;
        h += '<div class="suggestion-item">';
        h += '<div class="sug-factor"><div class="sug-factor-name">'+s.weight_key+'</div>';
        h += '<div class="sug-factor-reason">'+s.reason+'</div></div>';
        h += '<div class="sug-change">';
        h += '<span class="val-chip val-cur">'+s.current_value+'</span>';
        h += '<span class="val-arrow">'+(up?'&#8593;':'&#8595;')+'</span>';
        h += '<span class="val-chip '+(up?'val-up':'val-down')+'">'+s.proposed_value+'</span>';
        h += '</div></div>';
      });
      h += '</div>';
    } else {
      h += '<div style="margin-top:20px;padding:14px;background:var(--bg3);border-radius:10px;font-size:12px;color:var(--muted)">&#9432; No significant suggestions — no factor has &gt;5% or &lt;-5% win-rate lift yet. Run more backtest history for stronger signals.</div>';
    }

    // Approve/reject for optimizer suggestions
    if (sugs.length) {
      h += '<div class="action-bar" id="opt-action-bar">';
      h += '<button class="btn btn-approve" onclick="approveOptSugs()">&#10003; Approve Suggestions</button>';
      h += '<button class="btn btn-reject" onclick="rejectOptSugs()">&#10005; Dismiss</button>';
      h += '<span class="action-note">Approving queues these changes. Then run <code>python ai_optimizer.py --apply</code> on the VM to patch live_scanner.py.</span>';
      h += '</div>';
    }
  }
  h += '</div></div>'; // section-body + section

  // ══ SECTION 2: AI ANALYSIS ════════════════════════════════════════════════
  h += '<div class="section">';
  h += '<div class="section-head">';
  h += '<div><div class="section-title">&#129504; AI Analysis <span class="badge badge-ai">Claude claude-opus-4-5</span></div>';
  h += '<div class="section-sub">Claude analyzes backtest data and suggests weight changes — shadow-backtested on 180 days</div></div>';
  // Run button with live status
  var aiStatus = aiFlag ? (aiFlag.status || 'idle') : 'idle';
  var btnLabel, btnDisabled, btnCls;
  if      (aiStatus === 'pending')  { btnLabel='&#9203; Queued...';  btnDisabled=true;  btnCls='btn-disabled'; }
  else if (aiStatus === 'running')  { btnLabel='&#128260; Running...'; btnDisabled=true;  btnCls='btn-disabled'; }
  else if (aiStatus === 'done')     { btnLabel='&#10003; Done &mdash; Run Again'; btnDisabled=false; btnCls='btn-approve'; }
  else                              { btnLabel='&#129504; Run AI Analysis'; btnDisabled=false; btnCls='btn-approve'; }
  h += '<button class="btn '+btnCls+'" '+(btnDisabled?'disabled':'')+' onclick="triggerAiRun()" id="run-ai-btn">'+btnLabel+'</button>';
  h += '</div>';
  h += '<div class="section-body">';
  if (aiStatus === 'pending' || aiStatus === 'running') {
    h += '<div style="background:var(--bg3);border-radius:10px;padding:16px 20px;margin-bottom:20px;display:flex;align-items:center;gap:12px;font-size:13px;">';
    h += '<span style="font-size:20px">'+( aiStatus==='running'?'&#128260;':'&#9203;')+'</span>';
    h += '<div><strong>'+(aiStatus==='running'?'AI analysis running...':'Waiting for VM to pick up request...')+'</strong>';
    h += '<div style="font-size:11px;color:var(--muted);margin-top:3px;">The VM checks every 5 minutes. Results will appear automatically when done.</div></div>';
    h += '</div>';
  }
  var aiIds = Object.keys(aiRecs).sort().reverse();
  if (!aiIds.length) {
    h += '<div class="empty-state"><h3>No AI recommendations yet</h3>';
    h += '<p>Click <strong style="color:var(--purple)">Run AI Analysis</strong> above to generate your first recommendation.</p>';
    h += '<p style="margin-top:8px;font-size:11px;color:var(--muted)">Make sure ANTHROPIC_API_KEY is set in /home/scanner/.env on the VM.</p></div>';
  } else {
    // History list if multiple
    if (aiIds.length > 1) {
      h += '<div class="hist-list">';
      aiIds.slice(0,5).forEach(function(id) {
        var r = aiRecs[id];
        var d = r.win_rate_delta || 0;
        h += '<div class="hist-item'+(id===currentAiId?' active':'')+'" data-id="'+id+'" onclick="selectAiRec(this.dataset.id)">';
        h += '<span class="hist-ts">'+id.replace('_',' ').replace(/_/g,':')+'</span>';
        h += '<span class="hist-sum">'+(r.window||'')+'w &middot; '+(r.claude_summary||'').substring(0,70)+'…</span>';
        h += '<span class="hist-delta '+dc(d)+'">'+fmt(d,true)+' WR</span>';
        h += '</div>';
      });
      h += '</div>';
    }

    var rec = aiRecs[currentAiId];
    if (rec) {
      var cur  = (rec.current_stats  || {}).all || {};
      var proj = (rec.projected_stats|| {}).all || {};
      var wrD  = rec.win_rate_delta  || 0;
      var avgD = rec.avg_return_delta || 0;
      var st   = rec.status || 'pending';

      // Summary pill + status
      h += '<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:16px;">';
      h += '<div style="background:var(--purple);color:#fff;padding:6px 14px;border-radius:20px;font-size:12px;font-weight:600;">&#129504; '+(rec.claude_summary||'')+'</div>';
      h += statusBadge(st, rec.applied);
      if (rec.claude_confidence) h += '<span class="badge '+(rec.claude_confidence==='HIGH'?'badge-approved':rec.claude_confidence==='LOW'?'badge-rejected':'badge-pending')+'">'+rec.claude_confidence+' confidence</span>';
      h += '</div>';

      // Stats comparison
      h += '<div class="cmp-grid">';
      h += '<div class="cmp-card cur"><div class="cmp-lbl">&#128202; Current</div><div class="cmp-val" style="color:var(--blue)">'+fmt(cur.win_rate,false)+'</div><div class="cmp-sub">Win Rate &middot; '+fmtAvg(cur.avg_return)+' avg &middot; '+(cur.n||'—')+' picks</div></div>';
      h += '<div class="cmp-card proj"><div class="cmp-lbl">&#128200; Projected</div><div class="cmp-val" style="color:var(--green)">'+fmt(proj.win_rate,false)+'</div><div class="cmp-sub">Win Rate &middot; '+fmtAvg(proj.avg_return)+' avg &middot; '+(proj.n||'—')+' picks</div></div>';
      h += '<div class="cmp-card delta"><div class="cmp-lbl">&#9654; Improvement</div><div class="cmp-val '+dc(wrD)+'" style="font-size:32px">'+fmt(wrD,true)+'</div><div class="cmp-sub">Win Rate &middot; '+fmtAvg(avgD)+' avg ret</div></div>';
      h += '</div>';

      // Reasoning
      if (rec.claude_reasoning) {
        h += '<div class="reasoning">'+rec.claude_reasoning.replace(/\\n/g,'<br>')+'</div>';
      }

      // Changes table
      var changes = rec.changes || [];
      if (changes.length) {
        h += '<div style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);margin-bottom:10px;">Proposed Weight Changes ('+changes.length+')</div>';
        h += '<table class="changes-table"><thead><tr><th>Weight Key</th><th>Current</th><th></th><th>Proposed</th><th>Reason</th></tr></thead><tbody>';
        changes.forEach(function(ch) {
          var up = ch.proposed_value > ch.current_value;
          var same = ch.proposed_value === ch.current_value;
          var cls = same ? 'val-cur' : up ? 'val-up' : 'val-down';
          h += '<tr>';
          h += '<td><strong>'+ch.weight_key+'</strong></td>';
          h += '<td><span class="val-chip val-cur">'+ch.current_value+'</span></td>';
          h += '<td style="text-align:center;color:var(--muted)">'+(same?'=':up?'&#8593;':'&#8595;')+'</td>';
          h += '<td><span class="val-chip '+cls+'">'+ch.proposed_value+'</span></td>';
          h += '<td><div class="reason-text">'+ch.reason+'</div></td>';
          h += '</tr>';
        });
        h += '</tbody></table>';
      }

      // Action bar
      h += '<div class="action-bar" id="ai-action-bar">';
      if (st === 'pending') {
        h += '<button class="btn btn-approve" onclick="approveAiRec()">&#10003; Approve</button>';
        h += '<button class="btn btn-reject" onclick="rejectAiRec()">&#10005; Reject</button>';
        h += '<span class="action-note">Approving queues changes. Then run <code>python ai_optimizer.py --apply</code> on the VM.</span>';
      } else if (st === 'approved' && !rec.applied) {
        h += '<button class="btn btn-disabled" disabled>&#10003; Approved</button>';
        h += '<span class="action-note">&#9654; Run <code>python ai_optimizer.py --apply</code> on the VM, then restart the scanner.</span>';
      } else if (rec.applied) {
        h += '<button class="btn btn-disabled" disabled>&#9679; Applied</button>';
        if (rec.applied_at) h += '<span class="action-note">Applied '+rec.applied_at+'</span>';
      } else {
        h += '<button class="btn btn-disabled" disabled>&#10005; Rejected</button>';
        h += '<span class="action-note">Generate a new recommendation on the VM.</span>';
      }
      h += '</div>';
    }
  }

  h += '</div></div>'; // section-body + section
  page.innerHTML = h;
}

function selectAiRec(id) { currentAiId = id; renderPage(); }

// ── Trigger AI run ────────────────────────────────────────────────────────────
async function triggerAiRun() {
  var btn = document.getElementById('run-ai-btn');
  if (btn) { btn.disabled = true; btn.textContent = '⏳ Queuing...'; }
  try {
    var resp = await fetch('/api/run-ai-analysis', {method: 'POST'});
    var data = await resp.json();
    if (!data.ok) { alert('Error: ' + (data.error || 'Unknown')); renderPage(); }
    // Firebase listener will update aiFlag and re-render automatically
  } catch(e) { alert('Network error: ' + e.message); renderPage(); }
}

// ── Optimizer approve/reject ──────────────────────────────────────────────────
async function approveOptSugs() {
  var sugs = deriveOptSuggestions(getLatestFactors());
  if (!sugs.length) return;
  var weights = Object.assign({}, DEFAULT_WEIGHTS);
  sugs.forEach(function(s) { weights[s.weight_key] = s.proposed_value; });
  document.getElementById('opt-action-bar').innerHTML = '<span style="color:var(--muted)">Approving...</span>';
  try {
    var resp = await fetch('/api/optimizer-suggestions/approve', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({weights: weights, label: 'Statistical optimizer suggestions'})
    });
    var data = await resp.json();
    if (data.ok) {
      document.getElementById('opt-action-bar').innerHTML =
        '<span class="badge badge-approved">&#10003; Approved</span>' +
        '<span class="action-note" style="margin-left:10px">Run <code>python ai_optimizer.py --apply</code> on the VM to apply.</span>';
    } else { alert('Error: '+(data.error||'Unknown')); }
  } catch(e) { alert('Network error: '+e.message); }
}

function rejectOptSugs() {
  document.getElementById('opt-action-bar').innerHTML =
    '<span class="badge badge-rejected">&#10005; Dismissed</span>';
}

// ── AI approve/reject ─────────────────────────────────────────────────────────
async function approveAiRec() {
  document.getElementById('ai-action-bar').innerHTML = '<span style="color:var(--muted)">Approving...</span>';
  try {
    var resp = await fetch('/api/recommendations/'+currentAiId+'/approve', {method:'POST'});
    var data = await resp.json();
    if (data.ok) { aiRecs[currentAiId].status = 'approved'; renderPage(); }
    else { alert('Error: '+(data.error||'Unknown')); renderPage(); }
  } catch(e) { alert('Network error: '+e.message); renderPage(); }
}

async function rejectAiRec() {
  if (!confirm('Reject this recommendation?')) return;
  try {
    await fetch('/api/recommendations/'+currentAiId+'/reject', {method:'POST'});
    aiRecs[currentAiId].status = 'rejected';
    renderPage();
  } catch(e) { alert('Network error: '+e.message); }
}

function getLatestFactors() {
  var ids = Object.keys(optReports).sort().reverse();
  if (!ids.length) return [];
  var rep = optReports[ids[0]];
  var win = rep.windows && rep.windows[0] ? rep.windows[0] : '1m';
  return ((rep.reports || {})[win] || {}).factors || [];
}
</script>
</body>
</html>"""



if __name__ == '__main__':
    app.run(debug=True)
