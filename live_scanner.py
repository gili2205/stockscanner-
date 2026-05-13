"""
NASDAQ Pre-Breakout + Catalyst Scanner v2.0
Two parallel scoring tracks:
  - BREAKOUT: Technical coil near 52w high, EMA stack, volume dry-up
  - CATALYST: Earnings in <14 days, strong analyst consensus, high upside
Both require minimum liquidity ($15 price, $10M+ daily dollar volume).
"""

import os, time, logging, requests, pickle, json
from logger import log_scan_results
from datetime import datetime, date, timedelta
from pathlib import Path
import pytz

# Load .env automatically so the script works from any shell without
# needing to manually source it first.
def _load_dotenv():
    for candidate in [Path(__file__).parent / ".env", Path("/home/scanner/.env")]:
        if candidate.exists():
            for line in candidate.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
            return
_load_dotenv()
import pandas as pd
import numpy as np
import firebase_admin
from firebase_admin import credentials, db
import yfinance as yf

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler("/var/log/scanner.log"), logging.StreamHandler()])
log = logging.getLogger(__name__)

FIREBASE_URL  = os.environ["FIREBASE_URL"]
FIREBASE_CRED = os.environ["FIREBASE_CRED"]
ALPACA_KEY    = os.environ["ALPACA_KEY"]
ALPACA_SECRET = os.environ["ALPACA_SECRET"]
ET   = pytz.timezone("America/New_York")
HDRS = {"APCA-API-KEY-ID": ALPACA_KEY, "APCA-API-SECRET-KEY": ALPACA_SECRET}

CACHE_FILE      = "/home/scanner/history_cache.pkl"
FUND_CACHE_FILE = "/home/scanner/fundamentals_cache.json"

cred = credentials.Certificate(FIREBASE_CRED)
firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_URL})
ref = db.reference("/scanner")

_funds_cache, _funds_ts = {}, {}
_fund_file_cache = {}
FUNDS_TTL = 6 * 3600

# ── Quality minimums ──────────────────────────────────────────────────────────
MIN_PRICE      = 15.0
MIN_AVG_VOL    = 400_000
MIN_DOLLAR_VOL = 10_000_000

# ── Universe ──────────────────────────────────────────────────────────────────
def get_nasdaq_universe():
    tickers = _fetch_edgar()
    if tickers: return tickers
    log.info("Trying NASDAQ API...")
    tickers = _fetch_nasdaq_api()
    if tickers: return tickers
    log.info("Trying NASDAQ FTP...")
    tickers = _fetch_nasdaq_ftp()
    if tickers: return tickers
    log.warning("Using hardcoded fallback")
    return _hardcoded_fallback()

def _fetch_edgar():
    for attempt in range(3):
        try:
            r = requests.get("https://www.sec.gov/files/company_tickers_exchange.json",
                headers={"User-Agent": "nasdaq-scanner/2.0 scanner@example.com"}, timeout=30)
            if not r.content or len(r.content) < 10:
                time.sleep(2**attempt); continue
            data = r.json()
            fields, rows = data.get("fields",[]), data.get("data",[])
            if not fields or not rows:
                time.sleep(2**attempt); continue
            fi, ei = fields.index("ticker"), fields.index("exchange")
            tickers = sorted({
                str(row[fi]).upper().strip() for row in rows
                if str(row[ei]).upper() == "NASDAQ"
                and str(row[fi]).strip() and len(str(row[fi]).strip()) <= 6
                and not any(c in str(row[fi]).strip() for c in "-.'+ ")
            })
            if tickers:
                log.info(f"SEC EDGAR: {len(tickers)} tickers")
                return tickers
        except Exception as e:
            log.warning(f"EDGAR attempt {attempt+1}: {e}")
            time.sleep(2**attempt)
    log.error("SEC EDGAR failed"); return []

def _fetch_nasdaq_api():
    try:
        url = "https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=5000&exchange=nasdaq&download=true"
        r = requests.get(url, headers={"User-Agent":"Mozilla/5.0","Accept":"application/json"}, timeout=30)
        if r.ok and r.content:
            rows = r.json().get("data",{}).get("table",{}).get("rows",[])
            tickers = sorted({row.get("symbol","").strip().upper() for row in rows
                if row.get("symbol","").strip() and row.get("symbol","").strip().isalpha()
                and len(row.get("symbol","")) <= 5})
            if tickers:
                log.info(f"NASDAQ API: {len(tickers)} tickers"); return tickers
    except Exception as e: log.warning(f"NASDAQ API: {e}")
    return []

def _fetch_nasdaq_ftp():
    try:
        r = requests.get("https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt", timeout=30)
        if r.ok:
            lines = r.text.strip().split("\n")
            tickers = [parts[0].strip().upper() for line in lines[1:]
                for parts in [line.split("|")]
                if len(parts)>=2 and parts[0].strip() and len(parts[0].strip())<=5
                and parts[0].strip().isalpha() and parts[-1].strip()!="Y"]
            if tickers:
                log.info(f"NASDAQ FTP: {len(tickers)} tickers"); return sorted(set(tickers))
    except Exception as e: log.warning(f"NASDAQ FTP: {e}")
    return []

def _hardcoded_fallback():
    return ["AAPL","MSFT","NVDA","AMZN","META","GOOGL","GOOG","TSLA","AVGO","COST",
        "ASML","NFLX","AMD","QCOM","AMAT","LRCX","KLAC","SNPS","CDNS","MRVL",
        "ADBE","CRM","ORCL","PANW","CRWD","FTNT","ZS","OKTA","NET","DDOG",
        "SNOW","MDB","PLTR","NOW","WDAY","ARM","SMCI","ON","MPWR","TXN",
        "HIMS","SOUN","ASTS","CELH","DUOL","CAVA","RDDT","APP","AXON","UBER",
        "DASH","ABNB","BKNG","HOOD","SOFI","COIN","MARA","MRNA","REGN","VRTX",
        "ISRG","DXCM","IONQ","RKLB","DOCS","MU","SNDK","INTC","AVGO"]

# ── History cache ──────────────────────────────────────────────────────────────
def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE,"rb") as f: cache = pickle.load(f)
        if cache.get("date") == date.today():
            log.info(f"Loaded today cache: {len(cache.get('data',{}))} stocks")
            return cache.get("data",{})
    return None

def save_cache(data):
    with open(CACHE_FILE,"wb") as f: pickle.dump({"date":date.today(),"data":data},f)
    log.info(f"Cache saved: {len(data)} stocks")

def download_history(universe):
    log.info(f"=== DAILY HISTORY DOWNLOAD: {len(universe)} stocks ===")
    history = {}
    chunks = [universe[i:i+20] for i in range(0,len(universe),20)]
    total  = len(chunks)
    for i, chunk in enumerate(chunks):
        try:
            d = yf.download(chunk, period="60d", interval="1d", progress=False, auto_adjust=True)
            for t in chunk:
                try:
                    if isinstance(d.columns, pd.MultiIndex):
                        if t not in d["Close"].columns: continue
                        df = pd.DataFrame({"Open":d["Open"][t],"High":d["High"][t],
                            "Low":d["Low"][t],"Close":d["Close"][t],"Volume":d["Volume"][t]}).dropna()
                    else:
                        df = d[["Open","High","Low","Close","Volume"]].dropna()
                    if len(df) >= 20: history[t] = df
                except: pass
            if (i+1)%10==0 or (i+1)==total:
                pct = round((i+1)/total*100)
                log.info(f"  Progress: {i+1}/{total} ({pct}%) | {len(history)} stocks")
            try:
                ref.child('download_progress').set({'loaded':len(history),'total':len(universe),
                    'pct':round(len(history)/len(universe)*100) if len(universe)>0 else 0})
            except: pass
            time.sleep(0.5)
        except Exception as e:
            log.warning(f"  Chunk {i+1} failed: {e}"); time.sleep(2)
    log.info(f"=== DOWNLOAD COMPLETE: {len(history)} stocks ===")
    save_cache(history); return history

# ── Fundamentals (fetched live for top candidates) ────────────────────────────
def load_fund_file_cache():
    """Load overnight fundamentals cache if available."""
    global _fund_file_cache
    try:
        if Path(FUND_CACHE_FILE).exists():
            with open(FUND_CACHE_FILE) as f: data = json.load(f)
            if data.get("_date") == str(date.today()):
                _fund_file_cache = data
                log.info(f"Loaded fundamentals file cache: {len(data)-1} stocks")
    except Exception as e:
        log.warning(f"Could not load fundamentals file cache: {e}")

def get_fundamentals_fast(tickers):
    """
    Fetch fundamentals for a list of tickers.
    Uses file cache first, then live yfinance, then Alpaca for what's missing.
    """
    now = time.time()
    to_fetch = [t for t in tickers
        if t not in _funds_cache or now - _funds_ts.get(t,0) > FUNDS_TTL]

    # Try file cache first (overnight batch)
    still_needed = []
    for t in to_fetch:
        if t in _fund_file_cache and isinstance(_fund_file_cache[t], dict):
            _funds_cache[t] = _fund_file_cache[t]
            _funds_ts[t] = now
        else:
            still_needed.append(t)

    # Fetch live from yfinance for what's missing
    log.info(f"Fundamentals: {len(tickers)-len(still_needed)} cached, {len(still_needed)} to fetch")
    for t in still_needed:
        try:
            info = yf.Ticker(t).info
            pe      = info.get("trailingPE") or info.get("forwardPE")
            target  = info.get("targetMeanPrice")
            rec     = info.get("recommendationMean")
            rev_g   = info.get("revenueGrowth")
            eps_g   = info.get("earningsGrowth")
            short   = info.get("shortPercentOfFloat")
            buy_pct = max(0,min(100,round((3.0-rec)/2.0*100))) if rec else None

            # Earnings date
            earn_days = None
            try:
                cal = yf.Ticker(t).calendar
                if cal is not None and not cal.empty:
                    cols = list(cal.columns)
                    if cols:
                        ed = cols[0]
                        if hasattr(ed,'date'): ed = ed.date()
                        earn_days = (ed - date.today()).days
            except: pass

            mc     = info.get("marketCap")
            mc_str = None
            if mc:
                if   mc >= 1e12: mc_str = f"{mc/1e12:.1f}T"
                elif mc >= 1e9:  mc_str = f"{mc/1e9:.1f}B"
                else:            mc_str = f"{mc/1e6:.0f}M"

            _funds_cache[t] = {
                "pe_ratio":           round(float(pe),1) if pe and pe>0 else None,
                "analyst_target":     round(float(target),2) if target else None,
                "analyst_buy_pct":    buy_pct,
                "revenue_growth_yoy": round(float(rev_g)*100,1) if rev_g else None,
                "eps_growth_yoy":     round(float(eps_g)*100,1) if eps_g else None,
                "short_interest_pct": round(float(short)*100,1) if short else None,
                "days_to_earnings":   earn_days,
                "sector":             info.get("sector", ""),
                "market_cap_str":     mc_str,
            }
        except:
            _funds_cache[t] = {"pe_ratio":None,"analyst_target":None,"analyst_buy_pct":None,
                "revenue_growth_yoy":None,"eps_growth_yoy":None,"days_to_earnings":None,
                "sector":"","market_cap_str":None}
        _funds_ts[t] = now

    return {t: _funds_cache.get(t, {}) for t in tickers}

# ── Live prices (Alpaca) ──────────────────────────────────────────────────────
def alpaca_prices(tickers):
    prices = {}
    for chunk in [tickers[i:i+1000] for i in range(0,len(tickers),1000)]:
        syms = ",".join(chunk)
        for ep,key in [("quotes","quotes"),("trades","trades")]:
            try:
                r = requests.get(f"https://data.alpaca.markets/v2/stocks/{ep}/latest",
                    params={"symbols":syms,"feed":"iex"}, headers=HDRS, timeout=15)
                if r.status_code==200:
                    for sym,q in r.json().get(key,{}).items():
                        if sym not in prices:
                            if ep=="quotes":
                                a,b=q.get("ap",0),q.get("bp",0)
                                if a>0 and b>0: prices[sym]=round((a+b)/2,2)
                            else:
                                p=q.get("p",0)
                                if p>0: prices[sym]=round(p,2)
            except: pass
    log.info(f"Live prices: {len(prices)} stocks")
    return prices

def alpaca_rsi(tickers, period=14):
    rsi_map = {}
    end = datetime.now(pytz.UTC)
    start = end - pd.Timedelta(days=5)
    for chunk in [tickers[i:i+50] for i in range(0,len(tickers),50)]:
        try:
            r = requests.get("https://data.alpaca.markets/v2/stocks/bars",
                params={"symbols":",".join(chunk),"timeframe":"15Min",
                    "start":start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "end":end.strftime("%Y-%m-%dT%H:%M:%SZ"),"feed":"iex","limit":1000},
                headers=HDRS, timeout=20)
            if r.status_code!=200: continue
            for sym,bars in r.json().get("bars",{}).items():
                if not bars or len(bars)<period*2: continue
                closes=pd.Series([b["c"] for b in bars])
                d=closes.diff()
                g=d.where(d>0,0).ewm(span=period,adjust=False).mean()
                l=(-d.where(d<0,0)).ewm(span=period,adjust=False).mean()
                rs=g/l.replace(0,np.nan)
                rsi_map[sym]=round(float(100-(100/(1+rs.iloc[-1]))),1)
        except: pass
    return rsi_map

# ── SCORING — Dual Track v2.0 ─────────────────────────────────────────────────
#
# TRACK A — BREAKOUT SETUP
#   Best for: momentum traders, technical breakout plays
#   Needs: tight base (low ATR), volume dry-up, EMA stack, near 52w high
#   Ignores: fundamentals (but uses them as bonus)
#
# TRACK B — CATALYST PLAY
#   Best for: event-driven traders, earnings plays
#   Needs: earnings soon, strong analyst consensus, high price target upside
#   Ignores: proximity to 52w high (stock can be anywhere)
#   Key insight: NVDA before earnings = massive opportunity even if 15% from ATH

def score_stock(ticker, df, live_price=None, fund=None):
    if df is None or len(df) < 30: return None
    if fund is None: fund = {}

    try:
        closes = df["Close"].dropna()
        if len(closes) < 20: return None
        prev  = float(closes.iloc[-1])
        price = live_price if (live_price and live_price > 0) else prev
        chg   = round((price-prev)/prev*100, 2)

        # ── Hard quality gates ────────────────────────────────────────
        if price < MIN_PRICE: return None

        vol     = df["Volume"]
        avg_vol = float(vol.iloc[-20:].mean()) if len(vol)>=20 else 0
        if avg_vol < MIN_AVG_VOL: return None
        avg_dollar_vol = avg_vol * price
        if avg_dollar_vol < MIN_DOLLAR_VOL: return None

        # ── Base calculations ─────────────────────────────────────────
        h, l, pc = df["High"], df["Low"], closes.shift(1)
        tr  = pd.concat([h-l,(h-pc).abs(),(l-pc).abs()],axis=1).max(axis=1)
        atr = tr.ewm(span=14).mean()
        atr_ref = float(atr.iloc[-20:-10].mean()) if len(atr)>=20 else float(atr.mean())
        atr_c = round(float(atr.iloc[-5:].mean())/atr_ref,3) if atr_ref>0 else 1.0

        e10 = closes.ewm(span=10).mean().iloc[-1]
        e20 = closes.ewm(span=20).mean().iloc[-1]
        e50 = closes.ewm(span=50).mean().iloc[-1]
        ema = "full" if e10>e20>e50 and price>e10 else "partial" if e10>e20 else "weak"

        r = df.tail(15)
        hh_hl = round(float(
            ((r["High"]>r["High"].shift(1)).sum()+(r["Low"]>r["Low"].shift(1)).sum())/((len(r)-1)*2)
        ),3) if len(r)>1 else 0.5

        vol_ref = float(vol.iloc[-25:-8].mean()) if len(vol)>=25 else avg_vol
        vc = round(float(vol.iloc[-8:].mean())/vol_ref,3) if vol_ref>0 else 1.0
        vr = round(float(vol.iloc[-1])/avg_vol,2) if avg_vol>0 else 1.0

        ath = float(df["High"].max())
        h52 = float(df["High"].tail(252).max()) if len(df)>=252 else ath
        dist = round((h52-price)/price*100, 2)
        level = "ATH" if price>=ath*0.98 else "52-week" if price>=h52*0.98 else "Prior resistance"

        mom1m = round((price/float(closes.iloc[-21])-1)*100,1) if len(closes)>=21 else 0
        mom3m = round((price/float(closes.iloc[-63])-1)*100,1) if len(closes)>=63 else mom1m

        # Fundamentals
        target       = fund.get("analyst_target")
        buy_pct      = fund.get("analyst_buy_pct")
        rev_growth   = fund.get("revenue_growth_yoy")
        eps_growth   = fund.get("eps_growth_yoy")
        days_earn    = fund.get("days_to_earnings")
        short_pct    = fund.get("short_interest_pct")

        upside = round((target-price)/price*100,1) if target and price else None

        # ════════════════════════════════════════════════════════════════
        # TRACK A: BREAKOUT SETUP SCORE (0-95)
        # ════════════════════════════════════════════════════════════════
        # Skip falling knives
        if mom3m < -30: breakout_score = 0
        else:
            ba = 0

            # 1. Momentum (28 pts) — stock must be in uptrend
            if   mom1m>=25: ba+=28
            elif mom1m>=15: ba+=22
            elif mom1m>=8:  ba+=15
            elif mom1m>=3:  ba+=9
            elif mom1m>=0:  ba+=4
            else:           ba+=0

            # 2. Trend structure (22 pts)
            if   ema=="full":    ba+=22
            elif ema=="partial": ba+=12
            if   hh_hl>=0.85:   ba+=6
            elif hh_hl>=0.70:   ba+=3

            # 3. Base tightness (20 pts) — coiling before explosion
            if   atr_c<=0.20: ba+=12
            elif atr_c<=0.25: ba+=9
            elif atr_c<=0.30: ba+=6
            elif atr_c<=0.40: ba+=2
            if   vc<=0.50:    ba+=8
            elif vc<=0.65:    ba+=5
            elif vc<=0.80:    ba+=2

            # 4. Breakout proximity (18 pts) — how close to the level?
            if   dist<=1.0: ba+=18
            elif dist<=2.0: ba+=14
            elif dist<=3.5: ba+=9
            elif dist<=6.0: ba+=4
            elif dist<=10:  ba+=1

            # 5. Liquidity (7 pts)
            if   avg_dollar_vol>=200_000_000: ba+=7
            elif avg_dollar_vol>=50_000_000:  ba+=5
            elif avg_dollar_vol>=20_000_000:  ba+=3
            else:                             ba+=1

            # Penalties
            if ema=="weak":   ba=max(0,ba-18)
            if dist>15:       ba=max(0,ba-12)
            if mom1m<-5:      ba=max(0,ba-12)
            # Only penalize high volatility if momentum is NOT strong
            # (NVDA/META rallying = high ATR is OK)
            if atr_c>0.7 and mom1m<10: ba=max(0,ba-8)

            breakout_score = min(95, ba)

        # ════════════════════════════════════════════════════════════════
        # TRACK B: CATALYST PLAY SCORE (0-95)
        # ════════════════════════════════════════════════════════════════
        # Needs either earnings coming OR very strong analyst consensus
        ca = 0

        # 1. Earnings catalyst (35 pts) — THE biggest driver
        if days_earn is not None and days_earn >= 0:
            if   days_earn<=1:  ca+=35  # Reporting tomorrow!
            elif days_earn<=3:  ca+=30  # This week
            elif days_earn<=7:  ca+=22  # Next week
            elif days_earn<=14: ca+=12  # Two weeks
            elif days_earn<=21: ca+=5   # Three weeks

        # 2. Analyst upside (25 pts) — how much room to target?
        if upside is not None:
            if   upside>=50: ca+=25
            elif upside>=30: ca+=20
            elif upside>=20: ca+=15
            elif upside>=10: ca+=8
            elif upside>=5:  ca+=3

        # 3. Analyst buy consensus (20 pts)
        if buy_pct is not None:
            if   buy_pct>=85: ca+=20
            elif buy_pct>=70: ca+=14
            elif buy_pct>=55: ca+=8
            elif buy_pct>=40: ca+=3

        # 4. Business quality (15 pts)
        if rev_growth is not None:
            if   rev_growth>=50: ca+=8
            elif rev_growth>=25: ca+=5
            elif rev_growth>=10: ca+=2
            elif rev_growth<0:   ca-=5

        if eps_growth is not None and eps_growth>=25:
            ca+=7

        # 5. Technical bonus (not required but helps)
        if ema=="full":   ca+=5
        if mom1m>=10:     ca+=3
        if dist<=8:       ca+=4   # Relatively close to level

        # Short squeeze potential bonus
        if short_pct and short_pct>=15: ca+=5

        # Penalties for catalyst track
        if mom3m<-30:     ca=max(0,ca-15)  # Very bad trend = skeptical
        if price<MIN_PRICE: ca=0

        catalyst_score = min(95, ca)

        # ── Pick best track ───────────────────────────────────────────
        if breakout_score >= catalyst_score:
            score = breakout_score
            track = "BREAKOUT"
        else:
            score = catalyst_score
            track = "CATALYST"

        # Must score at least 30 on chosen track
        if score < 30: return None

        status = "READY" if score>=72 else "WATCH" if score>=55 else "BUILDING"
        pre    = (atr_c<=0.32 and vc<=0.80 and dist<=5.0
                  and ema in ("full","partial") and mom1m>=0)
        bull_flag = (atr_c<0.28 and vc<0.70 and mom1m>=8 and ema in ("full","partial"))
        earnings_soon = days_earn is not None and 0<=days_earn<=7

        return {
            "ticker":           ticker,
            "price":            round(price,2),
            "change_pct":       chg,
            "vol_ratio":        vr,
            "score":            score,
            "track":            track,
            "status":           status,
            "ema_stack":        ema,
            "atr":              atr_c,
            "hh_hl":            hh_hl,
            "vol_contraction":  vc,
            "level":            level,
            "dist_to_level":    dist,
            "pre_breakout":     pre,
            "bull_flag":        bull_flag,
            "earnings_soon":    earnings_soon,
            "days_to_earnings": days_earn,
            "analyst_buy_pct":  buy_pct,
            "revenue_growth":   rev_growth,
            "analyst_upside":   upside,
            "breakout_score":   breakout_score,
            "catalyst_score":   catalyst_score,
            "rs_percentile":    70,
            "rank":             0,
            "name":             ticker,
            "sector":           fund.get("sector",""),
            "market_cap":       fund.get("market_cap_str",""),
            "pe_ratio":         fund.get("pe_ratio"),
            "analyst_target":   target,
            "rsi":              None,
            "momentum_1m":      mom1m,
            "momentum_3m":      mom3m,
        }
    except Exception as e:
        log.debug(f"score_stock {ticker}: {e}")
        return None

# ── Fast rescore ──────────────────────────────────────────────────────────────
def fast_rescore(history, live_prices, fund_data):
    t0 = time.time()
    results = []
    for ticker, df in history.items():
        fund = fund_data.get(ticker, {})
        res = score_stock(ticker, df, live_prices.get(ticker), fund)
        if res: results.append(res)

    if not results:
        log.info(f"Rescore: 0 stocks in {round(time.time()-t0,1)}s")
        return []

    scores = [r["score"] for r in results]
    for r in results:
        r["rs_percentile"] = round(
            sum(1 for s in scores if s<r["score"])/len(scores)*100, 1)

    results.sort(key=lambda x: x["score"], reverse=True)
    for i,r in enumerate(results): r["rank"] = i+1

    ready   = sum(1 for r in results if r["status"]=="READY")
    breakouts = sum(1 for r in results if r["track"]=="BREAKOUT")
    catalysts = sum(1 for r in results if r["track"]=="CATALYST")
    log.info(f"Rescore: {len(results)} stocks | READY={ready} | Breakouts={breakouts} Catalysts={catalysts} | {round(time.time()-t0,1)}s")
    return results

# ── Push to Firebase ──────────────────────────────────────────────────────────
def push_results(results, sess, scan_time, elapsed):
    top10 = results[:10]
    top10_tickers = [r["ticker"] for r in top10]

    rsi_map = alpaca_rsi(top10_tickers)
    for r in top10:
        if r["ticker"] in rsi_map: r["rsi"] = rsi_map[r["ticker"]]

    # Fetch fundamentals for top 10 only
    fund_data = get_fundamentals_fast(top10_tickers)
    for r in top10:
        if r["ticker"] in fund_data:
            fd = fund_data[r["ticker"]]
            if not r.get("pe_ratio"):     r["pe_ratio"]     = fd.get("pe_ratio")
            if not r.get("analyst_target"): r["analyst_target"] = fd.get("analyst_target")

    now_et = datetime.now(ET)
    payload = {
        "stocks":             {r["ticker"]:r for r in top10},
        "stocks_scanned":     len(results),
        "ready_count":        sum(1 for r in results if r["status"]=="READY"),
        "watch_count":        sum(1 for r in results if r["status"]=="WATCH"),
        "pre_breakout_count": sum(1 for r in results if r["pre_breakout"]),
        "bull_flag_count":    sum(1 for r in results if r["bull_flag"]),
        "catalyst_count":     sum(1 for r in results if r["track"]=="CATALYST"),
        "earnings_soon_count":sum(1 for r in results if r.get("earnings_soon")),
        "market_open":        sess=="Market Open",
        "session":            sess,
        "last_updated":       now_et.isoformat(),
        "last_scan_time":     scan_time,
        "scan_duration_sec":  elapsed,
        "scanner_version":    "v2.0.2",
    }
    ref.update(payload)

    # Also push all scored stocks so dashboard filters work across full universe
    # Send as a dict keyed by ticker for fast lookup
    try:
        all_stocks = {r["ticker"]: r for r in results[:200]}  # top 200 by score
        ref.child("all_stocks").set(all_stocks)
    except Exception as e:
        log.debug(f"all_stocks push failed: {e}")

    log.info(f"Pushed: top10={top10_tickers} | READY={payload['ready_count']} | [{sess}] | {elapsed}s")

# ── Session helper ────────────────────────────────────────────────────────────
def get_session():
    now_et = datetime.now(ET)
    h,m,wd = now_et.hour,now_et.minute,now_et.weekday()
    if   wd<5 and (9,30)<=(h,m)<(16,0): return "Market Open"
    elif wd<5 and (4,0)<=(h,m)<(9,30):  return "Pre-Market"
    elif wd<5 and (16,0)<=(h,m)<(20,0): return "After-Hours"
    else:                                return "Market Closed"

# ── Main loop ─────────────────────────────────────────────────────────────────
log.info("Scanner v2.0.2 starting — Dual Track: Breakout + Catalyst")
load_fund_file_cache()
universe = get_nasdaq_universe()

history = load_cache()
if not history:
    log.info("No cache — downloading history...")
    history = download_history(universe)

log.info(f"Ready: {len(history)} stocks. Starting 60s scan loop.")
last_download_date = date.today()

# Pre-load fundamentals for the full universe from file cache
full_fund_data = {}
for ticker in list(history.keys()):
    if ticker in _fund_file_cache and isinstance(_fund_file_cache[ticker], dict):
        full_fund_data[ticker] = _fund_file_cache[ticker]

log.info(f"Pre-loaded fundamentals for {len(full_fund_data)} stocks from file cache")

while True:
    try:
        t0     = time.time()
        now_et = datetime.now(ET)
        sess   = get_session()

        if date.today() != last_download_date:
            if now_et.hour==9 and now_et.minute>=25:
                log.info("=== New trading day — refreshing caches ===")
                history = download_history(universe)
                load_fund_file_cache()
                full_fund_data = {t:_fund_file_cache[t] for t in history
                    if t in _fund_file_cache and isinstance(_fund_file_cache[t],dict)}
                last_download_date = date.today()

        live    = alpaca_prices(list(history.keys()))
        results = fast_rescore(history, live, full_fund_data)

        elapsed   = round(time.time()-t0, 1)
        scan_time = now_et.strftime("%Y-%m-%d %H:%M:%S ET")

        if results:
            push_results(results, sess, scan_time, elapsed)
        log_scan_results(results, sess)
        log.info("Next scan in 60s...")
        time.sleep(60)

    except KeyboardInterrupt:
        log.info("Stopped."); break
    except Exception as e:
        log.error(f"Loop error: {e}")
        time.sleep(30)
