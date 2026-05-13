# NASDAQ Scanner — Product Requirements Document
**Version: v3.2.0 | Last updated: 2026-05-13**

---

## 1. Product Vision

A personal, automated stock scanner that identifies NASDAQ breakout setups before they happen — using a systematic, quantitative version of the Qullamaggie methodology. The system continuously improves its own scoring logic using historical performance data, reducing manual effort and increasing edge over time.

**Core philosophy:**
- Surface the right 5–15 stocks per day, not 500
- Every signal must be backtestable and measurable
- The system should get smarter over time, not just bigger
- Keep the human in the loop for all weight changes and approvals

---

## 2. Users

There is one primary user: the owner/trader (you). This is not a multi-user product.

**User profile:**
- Experienced discretionary trader familiar with the Qullamaggie methodology
- Comfortable with GCP, Firebase, Git, and running CLI commands
- Wants automation for scanning but maintains full control over any scoring changes
- Trades NASDAQ momentum breakouts — needs setups identified 1–5 days before the move

---

## 3. Features

---

### 3.1 Live Dashboard (`/`)

**What it does:**  
Shows the latest scanner output — all stocks currently in READY or WATCH status — updated automatically as new scan data arrives from Firebase.

**Requirements:**

- **FR-1.1** Display all stocks with status READY or WATCH from the latest scan
- **FR-1.2** Each stock card must show: ticker, company name, price, score, status, EMA stack, ATR, volume contraction, distance to level, 1M momentum, RS percentile, market cap, setup flags (pre-breakout, bull flag)
- **FR-1.3** READY cards must have a visible green border; WATCH cards a yellow/amber border
- **FR-1.4** Cards must sort: READY first, then WATCH; within each group by score descending
- **FR-1.5** Page must auto-refresh when Firebase data updates — no manual refresh required
- **FR-1.6** Show connection status (live / reconnecting) and time since last scan
- **FR-1.7** Show market regime indicator (Pre-Market / Market Open / After-Hours / Closed) based on current ET time
- **FR-1.8** Show scanner metrics: total stocks scanned, stocks in READY, stocks in WATCH
- **FR-1.9** Show current app version in the header

**Non-functional:**
- NFR-1.1 Page must load and show first data within 3 seconds on a standard connection
- NFR-1.2 Firebase listener must reconnect automatically if connection drops

---

### 3.2 Analytics Page (`/analytics`)

**What it does:**  
Shows all historical scanner picks with their actual forward returns (1W, 1M, 3M), allowing the user to evaluate which setups performed and which didn't.

**Requirements:**

- **FR-2.1** Display all historical picks from Firebase `/scanner/history` in a table
- **FR-2.2** Each row must show: date, ticker, score, status, EMA stack, ATR, vol contraction, distance to level, 1M momentum, RS percentile, and forward returns (1W, 2W, 1M, 2M, 3M)
- **FR-2.3** Forward returns must be color-coded: green for positive, red for negative, grey for not yet available (`—`)
- **FR-2.4** Sort by: date (default), ticker (A–Z), score, 1W return, 1M return, 3M return
- **FR-2.5** Filter by ticker symbol (real-time search)
- **FR-2.6** Performance summary bar: overall win rate, avg return for filtered/visible rows
- **FR-2.7** localStorage caching: on first load, cache all history; on subsequent loads, only fetch new dates not in cache
- **FR-2.8** Show loading progress when fetching data for the first time

**Non-functional:**
- NFR-2.1 After initial load, subsequent page opens must render within 1 second (from cache)
- NFR-2.2 Table must handle 5,000+ rows without performance degradation

---

### 3.3 Smart Money Page (`/smart-money`)

**What it does:**  
Shows recent insider buying (Form 4 SEC filings) and major hedge fund holdings (13F filings) to provide institutional conviction signals alongside the scanner's technical setups.

**Requirements:**

- **FR-3.1** Display insider buys from the last 14 days: insider name, company, ticker, $ amount, date filed, transaction type
- **FR-3.2** Only show open-market purchases (not option exercises, gifts, or disposals) above $100K
- **FR-3.3** Display hedge fund holdings for 10 pre-defined funds: Berkshire, Pershing Square, Duquesne, Appaloosa, Third Point, Tiger Global, Baupost, Viking Global, Point72, Renaissance
- **FR-3.4** For each fund: show top 20 positions, % of portfolio, $ value, shares held
- **FR-3.5** Data sourced from SEC EDGAR via `smart_money.py` on the VM
- **FR-3.6** Show last updated timestamp for smart money data

**Non-functional:**
- NFR-3.1 Smart money data updated at least twice daily (via cron on VM)

---

### 3.4 Optimizer Page (`/optimizer`)

**What it does:**  
A two-section page where the user can review statistical factor analysis and AI-generated scoring weight suggestions, then approve or reject them. Approved changes are queued for application to the live scanner.

---

#### 3.4.1 Section 1 — Statistical Optimizer

**What it does:**  
Analyzes historical pick performance to identify which signals actually predict winning trades. Free, automated, no AI involved.

**Requirements:**

- **FR-4.1** Read latest `optimizer.py` report from Firebase `/scanner/optimization_reports`
- **FR-4.2** Show overall performance stats: total picks analyzed, date range, win rate, avg return, median return, best pick, worst pick
- **FR-4.3** Show score band breakdown: for each 10-point score range (0–9, 10–19, ... 90–99), show count, win rate, avg return, median return
- **FR-4.4** Show factor analysis table: for each signal, show N picks with signal, win rate with/without, WR lift (difference), avg return with/without, and an edge indicator (Strong / Mild / Weak / Hurts)
- **FR-4.5** Factor table sorted by WR lift descending (most predictive at top)
- **FR-4.6** Auto-generate weight change suggestions:
  - Factor with WR lift ≥ +10% → increase corresponding weight by 25% (Strong)
  - Factor with WR lift ≥ +5% → increase weight by 15% (Mild)
  - Factor with WR lift ≤ -10% → decrease weight by 30%
  - Factor with WR lift ≤ -5% → decrease weight by 20%
- **FR-4.7** Show approve and dismiss buttons for the auto-generated suggestions
- **FR-4.8** Approving saves suggested weights to Firebase `/scanner/approved_weights`
- **FR-4.9** If no optimizer data available yet, show empty state with the CLI command to run
- **FR-4.10** Show when the last optimizer run was

---

#### 3.4.2 Section 2 — AI Analysis

**What it does:**  
On-demand Claude AI analysis that reads backtest data, suggests specific weight changes with reasoning, shadow-backtests the proposal, and shows the projected win rate improvement.

**Requirements:**

- **FR-4.11** "Run AI Analysis" button visible at all times in the section header
- **FR-4.12** Button triggers Firebase flag (`/scanner/run_ai_requested = pending`) — never runs AI directly from the browser
- **FR-4.13** Button must show live status driven by Firebase listener:
  - `idle` → "🧠 Run AI Analysis" (enabled)
  - `pending` → "⏳ Queued..." (disabled)
  - `running` → "🔄 Running..." (disabled)
  - `done` → "✓ Done — Run Again" (enabled)
  - `error` → button re-enabled, error shown
- **FR-4.14** Show a progress banner while status is `pending` or `running` explaining the VM polling mechanism
- **FR-4.15** When a recommendation exists, show:
  - Claude's one-line summary
  - Status badge (Pending / Approved / Rejected / Applied)
  - Confidence level (High / Medium / Low)
  - Current vs projected stats: win rate, avg return, number of picks
  - Win rate improvement delta prominently displayed
  - Claude's full reasoning
  - Table of proposed weight changes: key, current value → proposed value, Claude's reason for each
- **FR-4.16** Approve and Reject buttons for each pending recommendation
- **FR-4.17** Approving sets `status = approved` in Firebase
- **FR-4.18** Once approved, show instructions to run `python ai_optimizer.py --apply` on the VM
- **FR-4.19** If multiple recommendations exist, show a history list (last 5) with timestamps, WR delta, and ability to switch between them
- **FR-4.20** AI Analysis must be triggered manually only — no automatic scheduling
- **FR-4.21** If no recommendations yet, show empty state with instructions

---

### 3.5 Scoring Weight Management

**What it does:**  
The underlying system that allows scoring weights to be changed, applied, and rolled back safely.

**Requirements:**

- **FR-5.1** Scoring weights defined in a single `DEFAULT_WEIGHTS` dict in `live_scanner.py`
- **FR-5.2** The same `DEFAULT_WEIGHTS` dict must exist in `ai_optimizer.py` (kept in sync) for shadow backtest accuracy
- **FR-5.3** `ai_optimizer.py --apply` must create a timestamped backup of `live_scanner.py` before patching
- **FR-5.4** Patch applies only to the specific weight values; all other code in `live_scanner.py` remains untouched
- **FR-5.5** Applied recommendations must be marked as `applied: true` + `applied_at` timestamp in Firebase
- **FR-5.6** Only one recommendation can be in `approved + not applied` state at a time

---

### 3.6 Automated Processes

**Requirements:**

- **FR-6.1** `live_scanner.py` must run automatically every market day and push results to Firebase
- **FR-6.2** A watchdog cron must restart `live_scanner.py` within 5 minutes if it crashes
- **FR-6.3** `backtest.py --days 2` must run nightly (market days) to add the latest trading day to history
- **FR-6.4** `backtest.py --update-returns` must run nightly to fill in new return windows for existing picks
- **FR-6.5** `optimizer.py --all-windows` must run automatically every Sunday at 4am
- **FR-6.6** `ai_optimizer.py --check-and-run` must poll Firebase every 5 minutes and execute AI analysis when triggered
- **FR-6.7** All cron jobs must log output to `/tmp/` or `/var/log/` for debugging

---

### 3.7 Two-Environment Architecture

**Requirements:**

- **FR-7.1** Staging and production must be completely isolated: separate VMs, separate Firebase databases, separate Vercel deployments
- **FR-7.2** All code changes must be tested on staging before merging to production
- **FR-7.3** Git branch `fix/scanner-bugs` → staging; `main` → production
- **FR-7.4** Merging to `main` requires explicit user approval — never auto-merge
- **FR-7.5** Both environments must have identical cron schedules and scripts

---

## 4. Non-Functional Requirements

| ID | Category | Requirement |
|----|----------|-------------|
| NFR-4.1 | Availability | Live dashboard must be accessible 24/7 (Vercel SLA) |
| NFR-4.2 | Freshness | Scanner data must be no more than 5 minutes stale during market hours |
| NFR-4.3 | Cost | AI analysis cost must not exceed ~$0.10/run; optimizer.py is free |
| NFR-4.4 | Reliability | VM scripts must resume automatically after VM restart (systemd + watchdog) |
| NFR-4.5 | Safety | No scoring weight change may be applied without explicit user approval |
| NFR-4.6 | Recoverability | `live_scanner.py` must be backed up before any automated patching |
| NFR-4.7 | Transparency | All Claude reasoning must be shown in full before the user approves |
| NFR-4.8 | Portability | All environment-specific config must be in `.env` — no hardcoded credentials |
| NFR-4.9 | Auditability | Every AI recommendation must be stored in Firebase with full history (approved, rejected, applied) |

---

## 5. Out of Scope

The following are explicitly not part of this product:

- **Multi-user access** — single user only, no auth layer planned
- **Real-time trade execution** — the scanner identifies setups; execution is manual
- **Options / non-NASDAQ instruments** — NASDAQ equities only
- **Mobile app** — web-responsive UI only
- **Alerts/notifications** — no push notifications or email alerts (browser only)
- **Social features** — no sharing, no community

---

## 6. Roadmap (Future)

### Phase 4 — Signal Improvements
- Fix `smart_money.py` Form 4 insider buys (currently returning 0)
- Add earnings date filter: avoid picks within 5 days of earnings
- Add relative volume spike detection
- Add sector rotation signal (RS rank by sector, not just individual)

### Phase 5 — Optimizer Enhancements
- Auto-apply approved weight changes after X days of shadow-backtest validation (with hard limits on max change per run)
- Add 6M and 1Y return windows to optimizer analysis
- Show factor correlation matrix (which signals cluster together vs. are truly independent)
- Confidence interval on win rate delta (not just point estimate)

### Phase 6 — Dashboard UX
- Intraday price update on cards (current price vs scan price)
- Breakout alert: flag when a WATCH stock crosses above its level
- Sector grouping view in dashboard
- Watchlist: save tickers across sessions (currently localStorage only)

### Phase 7 — Pre-Market Intelligence
- Pre-market price + volume vs. previous close
- Overnight gap analysis (gap up with volume = setup catalyst)
- Earnings gap scanner (post-earnings breakout setups)

---

## 7. Constraints

| Constraint | Detail |
|------------|--------|
| Data source | Yahoo Finance (yfinance) — free, may rate-limit under heavy use |
| AI model | Claude claude-opus-4-5 — must have valid Anthropic API key with credits |
| VM | GCP Compute Engine — manual SSH required for operations |
| Deployment | Vercel — Flask must stay serverless-compatible (no persistent state) |
| Firebase | Realtime Database (not Firestore) — flat JSON structure required |
| Budget | Keep infrastructure costs minimal — no paid data feeds, no GPU, no dedicated servers |
