# pe-tracker

Tells you when Indian equity indices are cheap vs their own history, and how they compare, for SIP top-ups.

- **Daily job** (GitHub Actions, weekdays 18:00 IST): fetch PE/PB/yield for every index, compare to the last 10 years, send one Telegram digest.
- **Dashboard** (Next.js, static, Netlify): per-index PE chart with buy/expensive bands, distance-from-median, distribution, data table; plus a **Compare** page (ranking, relative valuation, correlation, plain-language read-out).

## Indices

Defined in `tracker/indices.py`: Nifty 50, Nifty Next 50, Nifty 100, Nifty 500, Nifty Midcap 150, Nifty Smallcap 250, Nifty Bank, Nifty IT. Add one there and it flows through fetch, signal, compare, alerts and the UI.
Sensex is not included: BSE has no stable PE-history endpoint, and it overlaps Nifty 50 heavily.

## Compare and inference

All rule-based statistics on valuation history, not price forecasts (`tracker/compare.py`):

- **Valuation score** (0-100, lower is cheaper): mean of PE percentile, PB percentile and inverted dividend-yield percentile.
- **Relative valuation:** PE premium/discount of Midcap, Smallcap, Nifty 500, Bank and IT over Nifty 50, and where that gap sits in its own 10-year history.
- **Correlation** of daily PE changes (3y), which shows which indices actually diversify valuation risk.
- **Insights:** cheapest/richest, who is in the BUY zone, unusually high/low relative gaps.

Index PE methods differ slightly, so cross-index comparisons are approximate.

## The rule

Percentile of today's PE within the last 10 years of daily PE:

| Percentile | Zone | Meaning |
|---|---|---|
| ≤ 25 | BUY | Cheap vs history. Add beyond your regular SIP. |
| 25 to 75 | NEUTRAL | Keep the regular SIP. |
| ≥ 75 | EXPENSIVE | Keep the SIP, skip extra lump sums. |

Thresholds live in `tracker/signal.py` (and are mirrored in `dashboard/lib/stats.ts`, keep them in sync).
Signal only, not financial advice. Valuation can stay cheap or rich for years.

## Alerts

One digest message (not one per index) when: any index changes zone, a core index (Nifty 50, Nifty 500) is in its BUY zone (daily reminder), any fetch fails (so stale data never looks like "no signal"), or every Monday as a weekly summary. Otherwise it stays quiet.

## Setup

1. Create a bot with @BotFather, send it a message, and find your chat id (`https://api.telegram.org/bot<TOKEN>/getUpdates`).
2. In the GitHub repo: Settings → Secrets and variables → Actions → add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.
3. Actions → "Daily PE check" → Run workflow with **backfill** ticked (loads ~12 years of history), and **always_notify** ticked to test Telegram.
4. Netlify: new site from this repo. `netlify.toml` already sets base `dashboard`, build `npm run build`, publish `out`. Each daily data commit triggers a rebuild.

## Local

```bash
pip install -r requirements.txt
python -m pytest -q
python -m tracker.run demo          # SYNTHETIC data in data/demo/ to preview the UI (git-ignored)
python -m tracker.run backfill --only nifty50,midcap150   # backfill selected indices
python -m tracker.run probe        # test one live fetch from each source and print what came back
cd dashboard && npm install && npm run dev
```

`python -m tracker.run backfill` and `daily` need network access to niftyindices.com.

## Data sources (read this)

There is no official public PE API. This uses the niftyindices.com historical PE/PB/dividend-yield endpoint (`/BackPage/getpepbHistoricaldataDBtoString`), which is what stored history comes from. It is unofficial and can change or block cloud IPs. The NSE `allIndices` endpoint is only used by `python -m tracker.run probe` as a live check, never for stored history, because during market hours it reports the previous day's PE under today's date.

**Outliers:** when an index's earnings briefly collapse, the published PE spikes (Smallcap 250 once printed 44,711). Days with PE above 3x the window median are excluded from percentiles, bands, charts and comparisons, and indices with 3%+ such days (Midcap 150, Smallcap 250) get a warning mark: lean on PB and dividend yield for those. Raw data is kept as published.
