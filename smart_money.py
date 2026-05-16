"""
Smart Money Tracker
===================
Fetches institutional & insider trading data and pushes to Firebase.

Data sources (all free, no API key):
  - Form 4 (SEC EDGAR)     : insider buy/sell > $100K, filed within 2 days
  - 13F-HR (SEC EDGAR)     : quarterly hedge fund holdings (top 10 funds)
  - ARK Invest CSVs        : Cathie Wood's 6 ETFs, updated daily
  - Senate Stock Watcher   : congressional trades (GitHub raw data)
  - SC 13D/13G (SEC EDGAR) : activist investors crossing 5% ownership

Firebase paths:
  /scanner/smart_money/insiders      : recent insider buys > $100K
  /scanner/smart_money/institutions  : top hedge fund holdings (13F)
  /scanner/smart_money/ark_holdings  : ARK ETF holdings keyed by ticker
  /scanner/smart_money/congress      : recent Senate stock trades
  /scanner/smart_money/activist      : recent SC 13D/13G activist filings
  /scanner/smart_money/last_updated  : timestamp

Usage:
    python smart_money.py                # fetch everything
    python smart_money.py --insiders     # only Form 4 insider data
    python smart_money.py --institutions # only 13F hedge fund data
    python smart_money.py --ark          # only ARK holdings
    python smart_money.py --congress     # only Senate trades
    python smart_money.py --activist     # only 13D/13G filings
"""

import os, re, time, json, logging, argparse
import xml.etree.ElementTree as ET
from datetime import datetime, date, timedelta
from pathlib import Path

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

import requests
import firebase_admin
from firebase_admin import credentials, db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

FIREBASE_URL  = os.environ["FIREBASE_URL"]
FIREBASE_CRED = os.environ["FIREBASE_CRED"]

cred = credentials.Certificate(FIREBASE_CRED)
firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_URL})
sm_ref = db.reference("/scanner/smart_money")

HEADERS = {"User-Agent": "stockscanner analytics@stockscanner.com"}

# ── Top hedge funds to track (CIK: display name) ─────────────────────────────
HEDGE_FUNDS = {
    "1067983":  "Berkshire Hathaway (Buffett)",
    "1336528":  "Pershing Square (Ackman)",
    "1536411":  "Duquesne (Druckenmiller)",
    "1418814":  "Appaloosa (Tepper)",
    "1040273":  "Third Point (Loeb)",        # was 1040730 — digits were transposed
    "1167483":  "Tiger Global (Coleman)",
    "1061768":  "Baupost Group (Klarman)",
    "1103804":  "Viking Global (Halvorsen)",
    "1350694":  "Bridgewater Associates (Dalio)",  # replaced Point72 — files 13F-NT only
    "1037389":  "Renaissance Technologies",
}

MIN_INSIDER_VALUE = 100_000   # $100K minimum transaction value
MAX_INSIDER_FILINGS = 1000    # max Form 4 filings to scan per run


# ── Helpers ───────────────────────────────────────────────────────────────────

def sec_get(url, params=None, retries=3):
    """GET from SEC EDGAR with rate limiting and retries."""
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=20)
            if r.status_code == 200:
                return r
            if r.status_code == 429:
                log.warning("Rate limited — sleeping 10s")
                time.sleep(10)
        except Exception as e:
            log.warning(f"Request failed ({attempt+1}/{retries}): {e}")
        time.sleep(1)
    return None

def xml_val(elem, tag):
    """Safely get text value from an XML element by tag name.

    Form 4 XML stores numeric fields with a <value> child element:
        <transactionPricePerShare><value>25.50</value></transactionPricePerShare>
    The parent element's .text is whitespace-only in that case, so we must
    skip whitespace-only direct text and fall through to the <value> child.
    """
    found = elem.find(f".//{tag}")
    if found is not None and found.text and found.text.strip():
        return found.text.strip()
    # Try with <value> child (standard Form 4 XML schema pattern)
    found = elem.find(f".//{tag}/value")
    if found is not None and found.text and found.text.strip():
        return found.text.strip()
    return None


# ── Form 4 — Insider Buying ───────────────────────────────────────────────────

def get_recent_form4_filings(days_back=14):
    """Get recent Form 4 filings from EDGAR quarterly full-index.

    Uses https://www.sec.gov/Archives/edgar/full-index/{YEAR}/QTR{N}/form.idx
    — a fixed-width text file listing every SEC filing for the quarter, updated
    daily. Streamed line-by-line so we never load the full file into memory.
    Filters to Form 4 entries filed within the last `days_back` calendar days.
    The CIK column is the filer (reporting person) CIK, which matches the
    archive URL — no CIK mismatch issues.
    """
    start = (date.today() - timedelta(days=days_back)).isoformat()
    log.info(f"Fetching Form 4 filings since {start}...")

    today   = date.today()
    quarter = (today.month - 1) // 3 + 1
    idx_url = (f"https://www.sec.gov/Archives/edgar/full-index/"
               f"{today.year}/QTR{quarter}/form.idx")

    log.info(f"Streaming quarterly index: {idx_url}")
    try:
        r = requests.get(idx_url, headers=HEADERS, timeout=60, stream=True)
        if r.status_code != 200:
            log.error(f"Failed to fetch quarterly index: HTTP {r.status_code}")
            return []
    except Exception as e:
        log.error(f"Failed to fetch quarterly index: {e}")
        return []

    # form.idx fixed-width columns:
    #   0-11:  Form Type  (12 chars)
    #   12-73: Company Name (62 chars)
    #   74-85: CIK (12 chars)
    #   86-97: Date Filed YYYY-MM-DD (12 chars)
    #   98+:   Filename (e.g. edgar/data/CIK/ACCNO.txt)
    # form.idx is served without a text/* content-type so iter_lines returns bytes.
    # Decode explicitly to str before slicing.
    filings = []
    for raw in r.iter_lines():
        if isinstance(raw, bytes):
            raw = raw.decode("latin-1", errors="replace")
        if not raw or len(raw) < 98:
            continue
        form_type = raw[:12].strip()
        if form_type != "4":
            continue

        filed = raw[86:98].strip()
        if filed < start:
            continue   # too old (index is sorted by company name, not date)

        company         = raw[12:74].strip()
        cik             = raw[74:86].strip()
        filename        = raw[98:].strip()

        m = re.search(r'(\d{10}-\d{2}-\d{6})', filename)
        if not m:
            continue
        accession_clean = m.group(1).replace("-", "")

        filings.append({
            "company_cik":     cik,
            "accession_clean": accession_clean,
            "entity":          company,
            "file_date":       filed,
        })

        if len(filings) >= MAX_INSIDER_FILINGS:
            log.info(f"  Reached {MAX_INSIDER_FILINGS} cap — stopping early")
            break

    log.info(f"Found {len(filings)} Form 4 filings in date range")
    return filings[:MAX_INSIDER_FILINGS]


def parse_form4_xml(company_cik, accession_clean, verbose=False):
    """
    Fetch and parse a Form 4 XML filing.
    Tries 'ownership.xml' directly first (standard filename for all electronic
    Form 4 filings under the EDGAR Ownership Schema) — avoids the extra
    directory-listing HTTP request that was slowing us down and failing for
    many filings. Falls back to directory listing only if needed.
    Returns list of purchase transaction dicts with value > MIN_INSIDER_VALUE.
    """
    base_url    = f"https://www.sec.gov/Archives/edgar/data/{company_cik}/{accession_clean}/"
    xml_content = None

    # Most Form 4 filings use 'ownership.xml' — try it directly first
    r = sec_get(f"{base_url}ownership.xml")
    if r and r.status_code == 200 and b"ownershipDocument" in r.content:
        xml_content = r.content
        if verbose:
            log.info(f"  [XML] {base_url}ownership.xml")
    else:
        # Fall back: fetch directory listing to find the actual XML filename
        r_dir = sec_get(base_url)
        if not r_dir:
            if verbose:
                log.info(f"  [MISS] Directory unreachable: {base_url}")
            return []
        xml_links = re.findall(r'href="([^"]*\.xml)"', r_dir.text, re.IGNORECASE)
        if not xml_links:
            if verbose:
                log.info(f"  [MISS] No XML in directory: {base_url}")
            return []
        xml_file = xml_links[0].split("/")[-1]
        r2 = sec_get(f"{base_url}{xml_file}")
        if not r2:
            return []
        xml_content = r2.content
        if verbose:
            log.info(f"  [XML] {base_url}{xml_file} (via directory fallback)")

    if not xml_content:
        return []

    try:
        root = ET.fromstring(xml_content)

        # Issuer info
        ticker  = xml_val(root, "issuerTradingSymbol") or ""
        company = xml_val(root, "issuerName") or ""

        # Reporting owner
        insider = xml_val(root, "rptOwnerName") or ""
        title   = xml_val(root, "officerTitle") or ""
        is_dir  = xml_val(root, "isDirector") == "1"
        is_10pct= xml_val(root, "isTenPercentOwner") == "1"

        if not title:
            if is_dir:    title = "Director"
            elif is_10pct: title = "10% Owner"
            else:         title = "Insider"

        all_txns = root.findall(".//nonDerivativeTransaction")
        if verbose:
            log.info(f"  [TXN] {ticker or '?'} — {len(all_txns)} nonDerivativeTransaction(s)")

        transactions = []
        for txn in all_txns:
            code = xml_val(txn, "transactionCode")
            adc  = xml_val(txn, "transactionAcquiredDisposedCode")

            # Only open-market purchases (code P)
            if code != "P":
                if verbose:
                    log.info(f"    skip code={code} adc={adc}")
                continue

            tx_date = xml_val(txn, "transactionDate")
            shares  = xml_val(txn, "transactionShares")
            price   = xml_val(txn, "transactionPricePerShare")
            owned   = xml_val(txn, "sharesOwnedFollowingTransaction")

            try:
                shares_f = float(shares) if shares else 0
                price_f  = float(price)  if price  else 0
                value    = round(shares_f * price_f)
            except Exception:
                if verbose:
                    log.info(f"    skip — bad numbers shares={shares} price={price}")
                continue

            if value < MIN_INSIDER_VALUE:
                if verbose:
                    log.info(f"    skip — value ${value:,} < ${MIN_INSIDER_VALUE:,}")
                continue
            if not ticker or not tx_date:
                if verbose:
                    log.info(f"    skip — missing ticker={ticker} date={tx_date}")
                continue

            transactions.append({
                "ticker":      ticker.upper().strip(),
                "company":     company,
                "insider":     insider,
                "title":       title,
                "date":        tx_date,
                "shares":      int(shares_f),
                "price":       round(price_f, 2),
                "value":       value,
                "owned_after": int(float(owned)) if owned else None,
                "accession":   accession_clean,
            })

        return transactions

    except Exception as e:
        log.warning(f"  XML parse error for {accession_clean}: {e}")
        return []


def fetch_insider_buys():
    """Fetch all recent insider buy transactions > $100K."""
    filings = get_recent_form4_filings(days_back=14)
    if not filings:
        log.warning("No Form 4 filings found")
        return []

    all_buys = []
    for i, filing in enumerate(filings):
        verbose = (i < 3)   # verbose for first 3 filings to debug
        txns = parse_form4_xml(filing["company_cik"], filing["accession_clean"], verbose=verbose)
        all_buys.extend(txns)
        if (i + 1) % 20 == 0:
            log.info(f"  Processed {i+1}/{len(filings)} filings, {len(all_buys)} buys found")
        time.sleep(0.12)  # ~8 req/sec — within SEC's 10 req/sec limit

    # Deduplicate (same insider + ticker + date)
    seen = set()
    unique = []
    for b in all_buys:
        key = f"{b['ticker']}-{b['insider']}-{b['date']}"
        if key not in seen:
            seen.add(key)
            unique.append(b)

    # Sort by value descending
    unique.sort(key=lambda x: x["value"], reverse=True)
    log.info(f"Total insider buys found: {len(unique)}")
    return unique[:300]   # keep top 300 by value


# ── 13F — Institutional Holdings ──────────────────────────────────────────────

def get_latest_13f(cik, fund_name):
    """Get the latest 13F filing for a hedge fund."""
    padded_cik = cik.zfill(10)
    r = sec_get(f"https://data.sec.gov/submissions/CIK{padded_cik}.json")
    if not r:
        return None

    try:
        data = r.json()
        filings = data.get("filings", {}).get("recent", {})
        forms   = filings.get("form", [])
        accessions = filings.get("accessionNumber", [])
        dates   = filings.get("filingDate", [])

        primary_docs = filings.get("primaryDocument", [])

        # Find most recent 13F-HR
        for i, form in enumerate(forms):
            if form in ("13F-HR", "13F-HR/A"):
                return {
                    "cik":             cik,
                    "fund":            fund_name,
                    "accession":       accessions[i],
                    "filed":           dates[i],
                    "primary_doc":     primary_docs[i] if i < len(primary_docs) else "",
                }
        log.warning(f"No 13F-HR found for {fund_name}")
        return None
    except Exception as e:
        log.error(f"Error fetching submissions for {fund_name}: {e}")
        return None


def cusip_to_ticker(cusips):
    """Map CUSIPs to tickers using OpenFIGI API (free, no key needed for small batches)."""
    mapping = {}
    batch_size = 10
    for i in range(0, len(cusips), batch_size):
        batch = cusips[i:i+batch_size]
        payload = [{"idType": "ID_CUSIP", "idValue": c} for c in batch]
        try:
            r = requests.post(
                "https://api.openfigi.com/v3/mapping",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=15
            )
            if r.status_code == 200:
                results = r.json()
                for j, result in enumerate(results):
                    data = result.get("data", [])
                    if data:
                        # Prefer US equity
                        for item in data:
                            if item.get("exchCode") in ("US", "UW", "UN", "UA"):
                                mapping[batch[j]] = item.get("ticker", "")
                                break
                        if batch[j] not in mapping and data:
                            mapping[batch[j]] = data[0].get("ticker", "")
        except Exception as e:
            log.warning(f"OpenFIGI batch {i//batch_size+1} failed: {e}")
        time.sleep(0.5)
    return mapping


def parse_13f_holdings(filing):
    """Parse 13F XML and return list of holdings."""
    import re as _re
    cik = filing["cik"]
    accession = filing["accession"]
    accession_clean = accession.replace("-", "")

    # The primaryDocument is the HTML cover page, NOT the infotable XML.
    # Fetch the directory listing to find the actual infotable XML file.
    base_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_clean}/"
    r_dir = sec_get(base_url)
    if not r_dir:
        log.warning(f"  Could not fetch filing directory for {filing['fund']}")
        return []

    # Find all XML links in the directory listing
    xml_links = _re.findall(r'href="([^"]*\.xml)"', r_dir.text, _re.IGNORECASE)

    # Prefer files with 'infotable' or 'informationtable' in the name
    info_file = None
    for link in xml_links:
        name = link.lower().split("/")[-1]
        if "infotable" in name or "informationtable" in name:
            info_file = link.split("/")[-1]
            break

    # Fallback: any XML that isn't the cover page primary doc
    if not info_file:
        primary_name = (filing.get("primary_doc") or "").split("/")[-1].lower()
        for link in xml_links:
            candidate = link.split("/")[-1]
            if candidate.lower() != primary_name:
                info_file = candidate
                break

    if not info_file:
        log.warning(f"  Could not find infotable XML for {filing['fund']}")
        return []

    xml_url = f"{base_url}{info_file}"
    r = sec_get(xml_url)
    if not r:
        return []

    try:
        # Parse XML as-is — use {*} namespace wildcard instead of stripping namespaces.
        # Stripping leaves unbound prefixes in attributes and causes parse errors.
        root = ET.fromstring(r.content)

        def _val(elem, tag):
            """Get text from a child element, namespace-agnostic.
            Uses {*} wildcard (Python 3.8+) to match any namespace."""
            found = elem.find(f".//{{{chr(42)}}}{tag}")   # {*}tag — any namespace
            if found is None:
                found = elem.find(f".//{tag}")             # fallback: no namespace
            if found is not None and found.text:
                return found.text.strip()
            return None

        holdings = []
        # Find infoTable elements regardless of namespace
        info_tables = (root.findall(f".//{{{chr(42)}}}infoTable") or
                       root.findall(".//infoTable"))
        for info in info_tables:
            name     = _val(info, "nameOfIssuer") or ""
            cusip    = _val(info, "cusip") or ""
            value    = _val(info, "value")   # in thousands
            shares   = _val(info, "sshPrnamt")
            put_call = _val(info, "putCall") or ""

            if put_call in ("Put", "Call"):  # skip options
                continue

            try:
                value_f  = float(value)  * 1000 if value  else 0
                shares_f = float(shares)         if shares else 0
            except Exception:
                continue

            if value_f < 1_000_000:  # skip positions < $1M
                continue

            holdings.append({
                "name":   name.title(),
                "cusip":  cusip,
                "ticker": "",  # filled in later
                "value":  int(value_f),
                "shares": int(shares_f),
            })

        # Aggregate duplicate CUSIPs (same stock filed under multiple accounts/classes)
        merged = {}
        for h in holdings:
            key = h["cusip"] or h["name"]
            if key in merged:
                merged[key]["value"]  += h["value"]
                merged[key]["shares"] += h["shares"]
            else:
                merged[key] = h.copy()
        holdings = list(merged.values())

        # Sort by value descending, take top 30 per fund
        holdings.sort(key=lambda x: x["value"], reverse=True)
        holdings = holdings[:30]

        # Map CUSIPs to tickers
        cusips = [h["cusip"] for h in holdings if h["cusip"]]
        if cusips:
            ticker_map = cusip_to_ticker(cusips)
            for h in holdings:
                h["ticker"] = ticker_map.get(h["cusip"], "")

        return holdings

    except Exception as e:
        log.error(f"Error parsing 13F for {filing['fund']}: {e}")
        return []


def fetch_institutional_holdings():
    """Fetch latest 13F holdings for all tracked hedge funds."""
    all_institutions = []

    for cik, fund_name in HEDGE_FUNDS.items():
        log.info(f"Fetching 13F for {fund_name}...")
        filing = get_latest_13f(cik, fund_name)
        if not filing:
            continue

        holdings = parse_13f_holdings(filing)
        if not holdings:
            log.warning(f"  No holdings found for {fund_name}")
            continue

        total_value = sum(h["value"] for h in holdings)
        log.info(f"  {fund_name}: {len(holdings)} holdings, ${total_value/1e9:.1f}B tracked")

        all_institutions.append({
            "fund":        fund_name,
            "cik":         cik,
            "filed":       filing["filed"],
            "total_value": total_value,
            "holdings":    holdings,
        })
        time.sleep(1)

    return all_institutions


# ── ARK Invest ETF Holdings ───────────────────────────────────────────────────

ARK_BASE = "https://assets.ark-funds.com/fund-documents/funds-etf-csv/"
# Each fund can have multiple candidate filenames — tried in order until one succeeds.
ARK_FUNDS = {
    "ARKK": ["ARK_INNOVATION_ETF_ARKK_HOLDINGS.csv"],
    "ARKG": ["ARK_GENOMIC_REVOLUTION_ETF_ARKG_HOLDINGS.csv"],
    "ARKW": ["ARK_NEXT_GENERATION_INTERNET_ETF_ARKW_HOLDINGS.csv"],
    "ARKQ": ["ARK_AUTONOMOUS_TECH._&_ROBOTICS_ETF_ARKQ_HOLDINGS.csv",
             "ARK_AUTONOMOUS_TECHNOLOGY_&_ROBOTICS_ETF_ARKQ_HOLDINGS.csv"],
    "ARKF": ["ARK_FINTECH_INNOVATION_ETF_ARKF_HOLDINGS.csv"],
    "ARKX": ["ARK_SPACE_EXPLORATION_&_INNOVATION_ETF_ARKX_HOLDINGS.csv"],
}
ARK_MIN_WEIGHT = 0.5   # ignore positions < 0.5% weight (noise)

def _firebase_key(ticker):
    """Sanitize a ticker for use as a Firebase Realtime DB key.
    Firebase forbids: . $ # [ ] / in key names."""
    return re.sub(r'[.$#\[\]/]', '_', ticker)

def fetch_ark_holdings():
    """
    Fetch daily holdings CSVs for all 6 ARK ETFs.
    Returns dict keyed by ticker: {ticker, funds, total_weight, total_value, date}
    Aggregates across funds — a ticker in ARKK + ARKW gets combined weight.
    """
    import csv, io
    holdings = {}

    for symbol, candidates in ARK_FUNDS.items():
        r = None
        for filename in candidates:
            r = requests.get(ARK_BASE + filename, timeout=15,
                             headers={"User-Agent": "stockscanner/1.0"})
            if r.status_code == 200:
                break
            log.warning(f"  ARK {symbol}: HTTP {r.status_code} for {filename}")
            r = None
        if not r:
            continue
        try:

            reader = csv.DictReader(io.StringIO(r.text))
            fund_count = 0
            for row in reader:
                ticker = (row.get("ticker") or "").strip().upper()
                if not ticker or ticker in ("--", "NAN", ""):
                    continue

                weight_str = (row.get("weight (%)") or "0").strip().rstrip("%")
                value_str  = (row.get("market value ($)") or "0").strip().replace("$","").replace(",","")
                date_str   = (row.get("date") or "").strip()

                try:
                    weight = float(weight_str)
                    value  = float(value_str)
                except ValueError:
                    continue
                if weight < ARK_MIN_WEIGHT:
                    continue

                # Sanitize key: Firebase rejects . $ # [ ] / in key names
                key = _firebase_key(ticker)
                if key not in holdings:
                    holdings[key] = {
                        "ticker":       ticker,   # original (may contain dots)
                        "funds":        [],
                        "total_weight": 0.0,
                        "total_value":  0,
                        "date":         date_str,
                    }
                if symbol not in holdings[key]["funds"]:
                    holdings[key]["funds"].append(symbol)
                holdings[key]["total_weight"] = round(
                    holdings[key]["total_weight"] + weight, 2)
                holdings[key]["total_value"] += int(value)
                fund_count += 1

            log.info(f"  ARK {symbol}: {fund_count} qualifying positions")
        except Exception as e:
            log.warning(f"  ARK {symbol} error: {e}")
        time.sleep(0.5)

    log.info(f"ARK holdings: {len(holdings)} unique tickers across all funds")
    return holdings


# ── Senate Stock Trades ───────────────────────────────────────────────────────

SENATE_JSON_URL = (
    "https://raw.githubusercontent.com/timothycarambat/"
    "senate-stock-watcher-data/master/aggregate/all_transactions.json"
)

def _extract_ticker_from_senate(description, ticker_field):
    """Extract ticker from senate disclosure fields.
    Senate data sometimes puts ticker in ticker_field, sometimes in description."""
    t = (ticker_field or "").strip()
    if t and t not in ("--", "N/A", ""):
        return t.upper()
    # Pattern: "COMPANY NAME (TICK) - Stock"
    m = re.search(r'\(([A-Z]{1,5})\)', description or "")
    if m:
        return m.group(1)
    # Pattern: "TICK - Company Name"
    m = re.match(r'^([A-Z]{1,5})\s*[-–]\s*', (description or "").strip())
    if m:
        return m.group(1)
    return None

def fetch_senate_trades(days_back=365):
    """
    Fetch recent Senate stock trades from the senate-stock-watcher GitHub dataset.
    Returns list of buy/sell trades sorted newest-first, capped at 300.
    """
    log.info(f"Fetching Senate stock trades (last {days_back} days)...")
    try:
        r = requests.get(SENATE_JSON_URL, timeout=30)
        if r.status_code != 200:
            log.warning(f"  Senate data HTTP {r.status_code}")
            return []
        data = r.json()
    except Exception as e:
        log.warning(f"  Senate data error: {e}")
        return []

    cutoff = (date.today() - timedelta(days=days_back))
    trades  = []

    for txn in data:
        # Date is "MM/DD/YYYY"
        try:
            tx_date = datetime.strptime(txn.get("transaction_date", ""), "%m/%d/%Y").date()
        except ValueError:
            continue
        if tx_date < cutoff:
            continue

        asset_type = (txn.get("asset_type") or "").strip()
        if "Stock" not in asset_type:
            continue

        tx_type = (txn.get("type") or "").strip()
        if not any(x in tx_type for x in ("Purchase", "Sale")):
            continue

        ticker = _extract_ticker_from_senate(
            txn.get("asset_description"), txn.get("ticker")
        )
        if not ticker:
            continue

        trades.append({
            "senator":  txn.get("senator", "Unknown"),
            "ticker":   ticker,
            "company":  txn.get("asset_description", ""),
            "type":     "buy" if "Purchase" in tx_type else "sell",
            "amount":   txn.get("amount", ""),
            "date":     tx_date.isoformat(),
            "owner":    txn.get("owner", ""),
            "chamber":  "Senate",
        })

    trades.sort(key=lambda x: x["date"], reverse=True)
    log.info(f"Senate trades: {len(trades)} in last {days_back} days")
    return trades[:300]


# ── Activist Investors — SC 13D / SC 13G ─────────────────────────────────────

def fetch_activist_filings(days_back=30):
    """
    Fetch recent SC 13D and SC 13G filings from the EDGAR quarterly index.
    SC 13D = activist investor crossing 5% and intending to influence management.
    SC 13G = passive large holder crossing 5% with no activist intent.
    Returns list sorted by filed date desc.
    """
    start = (date.today() - timedelta(days=days_back)).isoformat()
    log.info(f"Fetching activist 13D/13G filings since {start}...")

    today   = date.today()
    quarter = (today.month - 1) // 3 + 1
    idx_url = (f"https://www.sec.gov/Archives/edgar/full-index/"
               f"{today.year}/QTR{quarter}/form.idx")

    try:
        r = requests.get(idx_url, headers=HEADERS, timeout=60, stream=True)
        if r.status_code != 200:
            log.error(f"  EDGAR index HTTP {r.status_code}")
            return []
    except Exception as e:
        log.error(f"  EDGAR index error: {e}")
        return []

    target_forms = {"SC 13D", "SC 13G", "SC 13D/A", "SC 13G/A"}
    filings = []

    for raw in r.iter_lines():
        if isinstance(raw, bytes):
            raw = raw.decode("latin-1", errors="replace")
        if not raw or "SC 13" not in raw[:20]:
            continue

        # Use regex instead of fixed column offsets — the form.idx column widths
        # vary between SEC versions; fixed positions give wrong CIK/date values.

        # Form type: at the start of the line
        ft_m = re.match(r'^(SC\s+13[DG](?:/A)?)\s+', raw)
        if not ft_m:
            continue
        form_type = re.sub(r'\s+', ' ', ft_m.group(1).strip())
        if form_type not in target_forms:
            continue

        # Date: always YYYY-MM-DD
        date_m = re.search(r'(\d{4}-\d{2}-\d{2})', raw)
        if not date_m:
            continue
        filed = date_m.group(1)
        if filed < start:
            continue

        # Filename: always contains 'edgar/data/' — CIK is embedded in path
        path_m = re.search(r'edgar/data/(\d+)/(\S+)', raw)
        if not path_m:
            continue
        cik      = path_m.group(1)
        fname    = path_m.group(2)

        # Accession number from filename
        acc_m = re.search(r'(\d{10}-\d{2}-\d{6})', fname)
        if not acc_m:
            continue

        # Filer name: between end of form-type match and the date/CIK area
        filer_raw = raw[ft_m.end():date_m.start()].strip()
        filer = re.split(r'\s{3,}', filer_raw)[0].strip()

        filings.append({
            "form_type": form_type,
            "filer":     filer,
            "cik":       cik,
            "accession": acc_m.group(1).replace("-", ""),
            "filed":     filed,
        })

    log.info(f"Found {len(filings)} 13D/13G filings — parsing top 50...")
    results = []
    for f in filings[:50]:
        parsed = _parse_13dg_filing(f)
        if parsed:
            results.append(parsed)
        time.sleep(0.15)

    results.sort(key=lambda x: x["filed"], reverse=True)
    log.info(f"Activist filings parsed: {len(results)}")
    return results


def _parse_13dg_filing(filing):
    """Parse SC 13D/G to extract target company name, CUSIP, ticker, % owned."""
    base_url = (f"https://www.sec.gov/Archives/edgar/data/"
                f"{filing['cik']}/{filing['accession']}/")
    r_dir = sec_get(base_url)
    if not r_dir:
        return None

    # Find the main filing document (not an exhibit, not the index)
    doc_links = re.findall(r'href="([^"]*\.(htm[l]?|txt))"', r_dir.text, re.IGNORECASE)
    doc_file  = None
    for link, _ in doc_links:
        name = link.lower().split("/")[-1]
        if "index" not in name and not name.startswith("ex") and not name.startswith("exhibit"):
            doc_file = name
            break
    if not doc_file:
        return None

    r = sec_get(f"{base_url}{doc_file}")
    if not r:
        return None

    # Strip HTML and collapse whitespace for regex
    clean = re.sub(r'<[^>]+>', ' ', r.text[:60000])
    clean = re.sub(r'\s+', ' ', clean)

    # CUSIP (9 alphanumeric chars after "CUSIP")
    cusip_m = re.search(
        r'CUSIP\s*(?:No\.?|Number)?\s*[:\.]?\s*([0-9A-Z]{9})',
        clean, re.IGNORECASE
    )
    cusip = cusip_m.group(1) if cusip_m else None

    # Issuer name (Item 1 of the form)
    issuer_m = re.search(
        r'(?:Name of Issuer|1\s*[\.:]?\s*Name of Issuer)[:\s]+([A-Z][^<\n\r]{3,60}?)(?:\s{2,}|CUSIP|Item\s*2)',
        clean, re.IGNORECASE
    )
    company = issuer_m.group(1).strip() if issuer_m else ""

    # Percent of class owned (Item 11 or "Percent of Class")
    pct_m = re.search(
        r'(?:Percent of Class|11\s*[\.:])[:\s]*([\d.]+)\s*%',
        clean, re.IGNORECASE
    )
    pct_owned = round(float(pct_m.group(1)), 1) if pct_m else None

    if not company and not cusip:
        return None

    result = {
        "form_type":   filing["form_type"],
        "filer":       filing["filer"].title(),
        "company":     company.title() if company else "",
        "cusip":       cusip or "",
        "ticker":      "",
        "pct_owned":   pct_owned,
        "filed":       filing["filed"],
        "is_activist": "13D" in filing["form_type"],
    }

    if cusip:
        ticker_map      = cusip_to_ticker([cusip])
        result["ticker"] = ticker_map.get(cusip, "")

    return result


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--insiders",      action="store_true")
    parser.add_argument("--institutions",  action="store_true")
    parser.add_argument("--ark",           action="store_true")
    parser.add_argument("--congress",      action="store_true")
    parser.add_argument("--activist",      action="store_true")
    args = parser.parse_args()

    run_all          = not any([args.insiders, args.institutions,
                                args.ark, args.congress, args.activist])
    run_insiders     = args.insiders     or run_all
    run_institutions = args.institutions or run_all
    run_ark          = args.ark          or run_all
    run_congress     = args.congress     or run_all
    run_activist     = args.activist     or run_all

    payload = {}

    if run_insiders:
        log.info("=== FETCHING INSIDER BUYS ===")
        buys = fetch_insider_buys()
        payload["insiders"]       = buys
        payload["insiders_count"] = len(buys)
        log.info(f"Insider buys: {len(buys)} transactions")

    if run_institutions:
        log.info("=== FETCHING INSTITUTIONAL HOLDINGS (13F) ===")
        institutions = fetch_institutional_holdings()
        payload["institutions"]       = institutions
        payload["institutions_count"] = len(institutions)
        log.info(f"Institutions: {len(institutions)} funds")

    if run_ark:
        log.info("=== FETCHING ARK INVEST HOLDINGS ===")
        ark = fetch_ark_holdings()
        payload["ark_holdings"]       = ark
        payload["ark_holdings_count"] = len(ark)
        log.info(f"ARK holdings: {len(ark)} tickers")

    if run_congress:
        log.info("=== FETCHING SENATE TRADES ===")
        congress = fetch_senate_trades(days_back=365)
        payload["congress"]       = congress
        payload["congress_count"] = len(congress)
        log.info(f"Senate trades: {len(congress)}")

    if run_activist:
        log.info("=== FETCHING ACTIVIST 13D/13G FILINGS ===")
        activist = fetch_activist_filings(days_back=30)
        payload["activist"]       = activist
        payload["activist_count"] = len(activist)
        log.info(f"Activist filings: {len(activist)}")

    payload["last_updated"] = datetime.now().isoformat()

    # Push to Firebase
    log.info("Pushing to Firebase...")
    sm_ref.update(payload)
    log.info("Done ✓")
