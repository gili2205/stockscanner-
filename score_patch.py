content = open('/home/scanner/live_scanner.py').read()

old = '''def score_stock(ticker, df, live_price=None):
    if df is None or len(df) < 20: return None
    try:
        closes = df["Close"].dropna()
        prev   = float(closes.iloc[-1])
        price  = live_price if (live_price and live_price > 0) else prev
        chg    = round((price-prev)/prev*100, 2)

        h, l, pc = df["High"], df["Low"], closes.shift(1)
        tr  = pd.concat([h-l, (h-pc).abs(), (l-pc).abs()], axis=1).max(axis=1)
        atr = tr.ewm(span=14).mean()
        atr_c = round(float(atr.iloc[-5:].mean()/atr.iloc[-20:-10].mean()), 3) \\
                if atr.iloc[-20:-10].mean() > 0 else 1.0

        e10 = closes.ewm(span=10).mean().iloc[-1]
        e20 = closes.ewm(span=20).mean().iloc[-1]
        e50 = closes.ewm(span=50).mean().iloc[-1]
        ema = "full" if e10>e20>e50 and price>e10 else "partial" if e10>e20 else "weak"

        r = df.tail(15)
        hh_hl = round(float(((r["High"]>r["High"].shift(1)).sum()+(r["Low"]>r["Low"].shift(1)).sum())/((len(r)-1)*2)), 3)

        vol = df["Volume"]
        vr  = round(float(vol.iloc[-1]/vol.iloc[-20:].mean()), 2)
        vc  = round(float(vol.iloc[-8:].mean()/vol.iloc[-25:-8].mean()), 3) if len(vol) >= 25 else 1.0

        ath  = float(df["High"].max())
        h52  = float(df["High"].tail(252).max()) if len(df) >= 252 else ath
        dist = round((h52-price)/price*100, 2)
        level = "ATH" if price>=ath*0.98 else "52-week" if price>=h52*0.98 else "Prior resistance"

        s  = {"full": 25, "partial": 15, "weak": 7}.get(ema, 0)
        s += 20 if hh_hl>=0.85 else 13 if hh_hl>=0.70 else 7 if hh_hl>=0.55 else 0
        s += 15 if atr_c<=0.20 else 12 if atr_c<=0.25 else 9 if atr_c<=0.30 else 5 if atr_c<=0.40 else 0
        s += 15 if vc<=0.50 else 11 if vc<=0.70 else 6 if vc<=0.85 else 0
        s += 10 if level=="ATH" else 6 if level=="52-week" else 2
        s += 10 if dist<=1.0 else 8 if dist<=2.0 else 5 if dist<=3.0 else 2 if dist<=5.0 else 0
        score  = min(95, s)
        status = "READY" if score>=65 else "WATCH" if score>=50 else "BUILDING"
        pre    = atr_c<=0.30 and vc<=0.75 and dist<=3.0 and ema in ("full", "partial")

        return {
            "ticker": ticker, "price": round(price, 2), "change_pct": chg,
            "vol_ratio": vr, "score": score, "status": status,
            "ema_stack": ema, "atr": atr_c, "hh_hl": hh_hl,
            "vol_contraction": vc, "level": level, "dist_to_level": dist,
            "pre_breakout": pre, "bull_flag": atr_c<0.25 and vc<0.65,
            "rs_percentile": 70, "rank": 0, "name": ticker, "sector": "",
            "pe_ratio": None, "analyst_target": None, "rsi": None,
        }
    except: return None'''

new = '''# Minimum quality thresholds — filters out micro-caps and penny stocks
MIN_PRICE     = 10.0    # Must be at least $10
MIN_AVG_VOL   = 300_000 # Must trade at least 300K shares/day avg
MIN_DOLLAR_VOL = 5_000_000  # Must have at least $5M avg daily dollar volume
MIN_HISTORY   = 30      # Need at least 30 days of data

def score_stock(ticker, df, live_price=None):
    if df is None or len(df) < MIN_HISTORY: return None
    try:
        closes = df["Close"].dropna()
        prev   = float(closes.iloc[-1])
        price  = live_price if (live_price and live_price > 0) else prev
        chg    = round((price-prev)/prev*100, 2)

        # ── Quality gates — skip junk stocks ──────────────────────────
        if price < MIN_PRICE:
            return None  # Penny stock filter

        vol = df["Volume"]
        avg_vol = float(vol.iloc[-20:].mean())
        avg_dollar_vol = avg_vol * price
        if avg_vol < MIN_AVG_VOL:
            return None  # Low volume filter
        if avg_dollar_vol < MIN_DOLLAR_VOL:
            return None  # Low liquidity filter

        # ── Technical indicators ──────────────────────────────────────
        h, l, pc = df["High"], df["Low"], closes.shift(1)
        tr  = pd.concat([h-l, (h-pc).abs(), (l-pc).abs()], axis=1).max(axis=1)
        atr = tr.ewm(span=14).mean()
        atr_c = round(float(atr.iloc[-5:].mean()/atr.iloc[-20:-10].mean()), 3) \
                if atr.iloc[-20:-10].mean() > 0 else 1.0

        e10 = closes.ewm(span=10).mean().iloc[-1]
        e20 = closes.ewm(span=20).mean().iloc[-1]
        e50 = closes.ewm(span=50).mean().iloc[-1]
        ema = "full" if e10>e20>e50 and price>e10 else "partial" if e10>e20 else "weak"

        # Higher highs / higher lows trend quality
        r = df.tail(15)
        hh_hl = round(float(((r["High"]>r["High"].shift(1)).sum()+(r["Low"]>r["Low"].shift(1)).sum())/((len(r)-1)*2)), 3)

        # Volume analysis
        vr  = round(float(vol.iloc[-1]/avg_vol), 2)
        vc  = round(float(vol.iloc[-8:].mean()/vol.iloc[-25:-8].mean()), 3) if len(vol) >= 25 else 1.0

        # Proximity to key levels
        ath  = float(df["High"].max())
        h52  = float(df["High"].tail(252).max()) if len(df) >= 252 else ath
        dist = round((h52-price)/price*100, 2)
        level = "ATH" if price>=ath*0.98 else "52-week" if price>=h52*0.98 else "Prior resistance"

        # 1-month momentum (RS proxy)
        mom1m = (price / float(closes.iloc[-21]) - 1) * 100 if len(closes) >= 21 else 0
        mom3m = (price / float(closes.iloc[-63]) - 1) * 100 if len(closes) >= 63 else mom1m

        # ── Scoring (100 points total) ────────────────────────────────

        # 1. EMA stack quality (25pts) — trend structure
        s  = {"full": 25, "partial": 14, "weak": 0}.get(ema, 0)

        # 2. Higher highs / higher lows (20pts) — trend momentum
        s += 20 if hh_hl>=0.85 else 12 if hh_hl>=0.70 else 5 if hh_hl>=0.60 else 0

        # 3. ATR coil / volatility compression (15pts) — base tightening
        s += 15 if atr_c<=0.20 else 12 if atr_c<=0.25 else 8 if atr_c<=0.30 else 3 if atr_c<=0.40 else 0

        # 4. Volume contraction (10pts) — institutional accumulation
        s += 10 if vc<=0.50 else 7 if vc<=0.70 else 3 if vc<=0.85 else 0

        # 5. Proximity to breakout level (15pts) — near trigger
        s += 15 if dist<=1.0 else 11 if dist<=2.0 else 7 if dist<=3.5 else 3 if dist<=6.0 else 0

        # 6. Momentum quality (10pts) — stock is actually going up
        s += 10 if mom1m>=15 else 7 if mom1m>=8 else 4 if mom1m>=3 else 0

        # 7. Liquidity bonus (5pts) — prefer more liquid stocks
        s += 5 if avg_dollar_vol>=50_000_000 else 3 if avg_dollar_vol>=20_000_000 else 1

        # ── Penalties ─────────────────────────────────────────────────
        # Penalize weak trend
        if ema == "weak":
            s = max(0, s - 10)
        # Penalize if stock is more than 10% below 52-week high (not near breakout)
        if dist > 10:
            s = max(0, s - 10)

        score  = min(95, s)
        # Raise the bar — READY requires score >= 70 now (was 65)
        status = "READY" if score>=70 else "WATCH" if score>=52 else "BUILDING"
        pre    = atr_c<=0.30 and vc<=0.75 and dist<=4.0 and ema in ("full", "partial") and mom1m>=0
        bull_flag = atr_c<0.25 and vc<0.65 and mom1m>=5

        return {
            "ticker": ticker, "price": round(price, 2), "change_pct": chg,
            "vol_ratio": vr, "score": score, "status": status,
            "ema_stack": ema, "atr": atr_c, "hh_hl": hh_hl,
            "vol_contraction": vc, "level": level, "dist_to_level": dist,
            "pre_breakout": pre, "bull_flag": bull_flag,
            "rs_percentile": 70, "rank": 0, "name": ticker, "sector": "",
            "pe_ratio": None, "analyst_target": None, "rsi": None,
            "momentum_1m": round(mom1m, 1), "momentum_3m": round(mom3m, 1),
            "avg_dollar_vol_m": round(avg_dollar_vol/1_000_000, 1),
        }
    except: return None'''

if old in content:
    content = content.replace(old, new)
    open('/home/scanner/live_scanner.py', 'w').write(content)
    print('SUCCESS - scoring logic updated')
else:
    print('ERROR - old pattern not found, manual update needed')
    # Show what the function looks like
    idx = content.find('def score_stock')
    print(content[idx:idx+200])
