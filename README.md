# pe-tracker

Tells you when the Nifty 50 is cheap vs its own history, for SIP top-ups.

- **Daily job** (GitHub Actions, weekdays 18:00 IST): fetch PE, compare to the last 10 years, alert on Telegram.
- **Dashboard** (Next.js, static, Netlify): PE chart with buy/expensive bands, distance-from-median, distribution, data table.

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

You get a Telegram message when the zone changes, every day while in the BUY zone, and when a fetch fails (so stale data never looks like "no signal").

## Setup

1. Create a bot with @BotFather, send it a message, and find your chat id (`https://api.telegram.org/bot<TOKEN>/getUpdates`).
2. In the GitHub repo: Settings → Secrets and variables → Actions → add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.
3. Actions → "Daily PE check" → Run workflow with **backfill** ticked (loads ~12 years of history), and **always_notify** ticked to test Telegram.
4. Netlify: new site from this repo. `netlify.toml` already sets base `dashboard`, build `npm run build`, publish `out`. Each daily data commit triggers a rebuild.

## Local

```bash
pip install -r requirements.txt
python -m pytest -q
python -m tracker.run demo          # SYNTHETIC data to preview the UI (git-ignored)
cd dashboard && npm install && npm run dev
```

`python -m tracker.run backfill` and `daily` need network access to niftyindices.com / nseindia.com.

## Data sources (read this)

There is no official public PE API. This uses the niftyindices.com historical PE/PB/dividend-yield endpoint, with the NSE `allIndices` endpoint as a fallback for today's value. Both are unofficial and can change or block cloud IPs. Fetch parsing is covered by fixture tests, but the live endpoints have only been exercised on GitHub Actions, not in development.
