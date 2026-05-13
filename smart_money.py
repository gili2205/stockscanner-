"""
Smart Money Tracker
===================
Fetches institutional & insider trading data from SEC EDGAR and pushes
to Firebase. Run every 4 hours via cron.

Data sources (all free, no API key):
  - Form 4 (SEC EDGAR)  : insider buy/sell transactions, filed within 2 days
  - 13F-HR (SEC EDGAR)  : quarterly hedge fund holdings (top 10 funds)

Firebase paths:
  /scanner/smart_money/insiders      : recent insider buys > $100K
  /scanner/smart_money/institutions  : top hedge fund holdings
  /scanner/smart_money/last_updated  : timestamp

Usage:
    python smart_money.py              # fetch everything
    python smart_money.py --insiders   # only insider data
    python smart_money.py --institutions # only 13F data
"""

import os, time, json, logging, argparse
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
MAX_INSIDER_FILINGS = 200     # max Form 4 filings to scan per run


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
    """Safely get text value from an XML element by tag name."""
    found = elem.find(f".//{tag}")
    if found is not None and found.text:
        return found.text.strip()
    # Try with <value> child
    found = elem.find(f".//{tag}/value")
    if found is not None and found.text:
        return found.text.strip()
    return None


# ── Form 4 — Insider Buying ───────────────────────────────────────────────────

def get_recent_form4_filings(days_back=14):
    """Get recent Form 4 filing accession numbers from EDGAR Atom feed.

    Uses the EDGAR browse-edgar Atom feed (action=getcurrent&type=4) which
    returns filings newest-first with correct dates — avoids the EFTS date-
    filter bug where q='' returns oldest filings regardless of startdt.
    Paginates via the 'dateb' param until we've covered the full date window.
    """
    start = (date.today() - timedelta(days=days_back)).isoformat()
    log.info(f"Fetching Form 4 filings since {start}...")

    ns = "http://www.w3.org/2005/Atom"
    filings = []
    dateb   = ""   # empty = today; set to oldest date seen each page

    for page in range(10):   # up to 10 pages × 200 = 2000 filings
        r = sec_get(
            "https://www.sec.gov/cgi-bin/browse-edgar",
            params={
                "action":      "getcurrent",
                "type":        "4",
                "dateb":       dateb,
                "owner":       "include",
                "count":       "200",
                "search_text": "",
                "output":      "atom",
            }
        )
        if not r:
            break

        try:
            root    = ET.fromstring(r.content)
            entries = root.findall(f"{{{ns}}}entry")
            if not entries:
                break

            reached_old = False
            for entry in entries:
                # Filing date is in <updated> tag (ISO format)
                updated = entry.find(f"{{{ns}}}updated")
                file_date = (updated.text or "")[:10] if updated is not None else ""

                if file_date and file_date < start:
                    reached_old = True
                    break

                # Accession number is in <id>: urn:tag:sec.gov,...=XXXXXXXXXX-YY-ZZZZZZ
                id_el = entry.find(f"{{{ns}}}id")
                if id_el is None or not id_el.text:
                    continue
                # Extract after last "="
                raw = id_el.text.strip()
                accession = raw.split("=")[-1] if "=" in raw else ""
                if not accession:
                    continue

                title_el = entry.find(f"{{{ns}}}title")
                entity   = title_el.text.strip() if title_el is not None and title_el.text else ""

                filings.append({
                    "accession": accession,
                    "entity":    entity,
                    "file_date": file_date,
                })
                dateb = file_date   # keep track of oldest date seen

            if reached_old or len(entries) < 200:
                break   # no need to fetch more pages

        except Exception as e:
            log.error(f"Failed to parse Form 4 Atom feed (page {page+1}): {e}")
            break

        if len(filings) >= MAX_INSIDER_FILINGS:
            break

    log.info(f"Found {len(filings)} Form 4 filings in date range")
    return filings[:MAX_INSIDER_FILINGS]


def parse_form4_xml(accession):
    """
    Fetch and parse a Form 4 XML filing.
    Returns list of transaction dicts (only purchases with value > MIN_INSIDER_VALUE).
    """
    import re as _re

    # Normalise accession number — EFTS search returns CIK without zero-padding
    # (e.g. "1536411-26-000001") but the archive URL requires 18-digit form
    # ("000153641126000001"). Zero-pad the first segment to 10 digits.
    parts = accession.split("-")
    cik = str(int(parts[0]))                          # CIK without leading zeros (for URL path)
    accession_clean = parts[0].zfill(10) + "".join(parts[1:])  # always 18 digits

    # Fetch the filing directory listing to find the Form 4 XML.
    base_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_clean}/"
    r_dir = sec_get(base_url)
    if not r_dir:
        log.warning(f"  Could not fetch Form 4 directory: {base_url}")
        return []

    xml_links = _re.findall(r'href="([^"]*\.xml)"', r_dir.text, _re.IGNORECASE)
    if not xml_links:
        return []

    # Form 4 filings typically have one primary XML — take the first one
    xml_file = xml_links[0].split("/")[-1]
    xml_url = f"{base_url}{xml_file}"

    r = sec_get(xml_url)
    if not r:
        return []

    try:
        root = ET.fromstring(r.content)

        # Issuer info
        ticker  = xml_val(root, "issuerTradingSymbol") or ""
        company = xml_val(root, "issuerName") or ""

        # Reporting owner
        insider = xml_val(root, "rptOwnerName") or ""
        title   = xml_val(root, "officerTitle") or ""
        is_dir  = xml_val(root, "isDirector") == "1"
        is_off  = xml_val(root, "isOfficer")  == "1"
        is_10pct= xml_val(root, "isTenPercentOwner") == "1"

        if not title:
            if is_dir:   title = "Director"
            elif is_10pct: title = "10% Owner"
            else:        title = "Insider"

        transactions = []

        # Non-derivative transactions (actual stock purchases)
        for txn in root.findall(".//nonDerivativeTransaction"):
            code  = xml_val(txn, "transactionCode")
            adc   = xml_val(txn, "transactionAcquiredDisposedCode")

            # Only purchases: code P or code M with Acquired
            if code not in ("P",) and not (code == "M" and adc == "A"):
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
                continue

            if value < MIN_INSIDER_VALUE:
                continue
            if not ticker or not tx_date:
                continue

            transactions.append({
                "ticker":     ticker.upper().strip(),
                "company":    company,
                "insider":    insider,
                "title":      title,
                "date":       tx_date,
                "shares":     int(shares_f),
                "price":      round(price_f, 2),
                "value":      value,
                "owned_after": int(float(owned)) if owned else None,
                "accession":  accession,
            })

        return transactions

    except Exception as e:
        log.warning(f"  XML parse error for {accession}: {e}")
        return []


def fetch_insider_buys():
    """Fetch all recent insider buy transactions > $100K."""
    filings = get_recent_form4_filings(days_back=14)
    if not filings:
        log.warning("No Form 4 filings found")
        return []

    all_buys = []
    for i, filing in enumerate(filings):
        txns = parse_form4_xml(filing["accession"])
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


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--insiders",      action="store_true")
    parser.add_argument("--institutions",  action="store_true")
    args = parser.parse_args()

    # Default: run both
    run_insiders     = args.insiders     or not (args.insiders or args.institutions)
    run_institutions = args.institutions or not (args.insiders or args.institutions)

    payload = {}

    if run_insiders:
        log.info("=== FETCHING INSIDER BUYS ===")
        buys = fetch_insider_buys()
        payload["insiders"]     = buys
        payload["insiders_count"] = len(buys)
        log.info(f"Insider buys: {len(buys)} transactions")

    if run_institutions:
        log.info("=== FETCHING INSTITUTIONAL HOLDINGS ===")
        institutions = fetch_institutional_holdings()
        payload["institutions"]       = institutions
        payload["institutions_count"] = len(institutions)
        log.info(f"Institutions: {len(institutions)} funds")

    payload["last_updated"] = datetime.now().isoformat()

    # Push to Firebase
    log.info("Pushing to Firebase...")
    sm_ref.update(payload)
    log.info("Done ✓")
