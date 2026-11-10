"""Telegram notifications. Token/chat id come from environment variables only."""
from __future__ import annotations

import os

import requests

from .signal import Signal

API = "https://api.telegram.org/bot{token}/sendMessage"


def format_signal(sig: Signal, prev_zone: str | None = None) -> str:
    icon = {"BUY": "🟢", "NEUTRAL": "⚪", "EXPENSIVE": "🔴"}[sig.zone]
    lines = [
        f"{icon} Nifty 50 PE: {sig.pe:.2f}  ({sig.zone})",
        f"Cheaper than {100 - sig.percentile:.0f}% of the last {sig.lookback_years}y "
        f"(percentile {sig.percentile:.0f})",
        f"Median {sig.median:.2f} · Mean {sig.mean:.2f} · z-score {sig.z_score:+.2f}",
    ]
    if prev_zone and prev_zone != sig.zone:
        lines.insert(1, f"Zone changed: {prev_zone} → {sig.zone}")
    if sig.zone == "BUY":
        lines.append("Valuation is below its historical norm: good time to add beyond your regular SIP.")
    elif sig.zone == "EXPENSIVE":
        lines.append("Valuation is rich: keep the regular SIP, skip extra lump-sum buys.")
    lines.append("Signal only, not financial advice.")
    return "\n".join(lines)


def send_telegram(text: str, token: str | None = None, chat_id: str | None = None) -> None:
    token = token or os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set")
    resp = requests.post(
        API.format(token=token),
        json={"chat_id": chat_id, "text": text},
        timeout=30,
    )
    if resp.status_code != 200:
        # Do not include the URL (it contains the token) in the error.
        raise RuntimeError(f"Telegram send failed: HTTP {resp.status_code} {resp.text[:200]}")


ZONE_ICON = {"BUY": "🟢", "NEUTRAL": "⚪", "EXPENSIVE": "🔴"}


def should_send(
    table: list[dict],
    prev_state: dict,
    failures: dict[str, str],
    core_keys: set[str],
    always: bool = False,
    weekly: bool = False,
) -> list[str]:
    """Reasons to send a digest today. Empty list means stay quiet.

    Zone change in any index, a core index sitting in BUY (daily reminder), any fetch failure,
    the Monday weekly digest, or a forced send.
    """
    reasons = []
    for r in table:
        prev = prev_state.get(r["key"], {}).get("zone")
        if prev and prev != r["zone"]:
            reasons.append(f"{r['label']}: {prev} -> {r['zone']}")
        elif r["key"] in core_keys and r["zone"] == "BUY":
            reasons.append(f"{r['label']} in BUY zone")
    if failures:
        reasons.append("fetch failures")
    if weekly:
        reasons.append("weekly digest")
    if always:
        reasons.append("forced")
    return reasons


def format_digest(
    table: list[dict],
    prev_state: dict,
    insights: list[str],
    failures: dict[str, str],
    when: str,
    max_insights: int = 3,
) -> str:
    lines = [f"📊 Valuation check · {when}", ""]
    for r in table:
        prev = prev_state.get(r["key"], {}).get("zone")
        changed = f" (was {prev})" if prev and prev != r["zone"] else ""
        lines.append(
            f"{ZONE_ICON[r['zone']]} {r['label']}: PE {r['pe']:.1f} · p{r['pe_percentile']:.0f} · {r['zone']}{changed}"
        )
    if insights:
        lines += ["", *[f"• {t}" for t in insights[:max_insights]]]
    if failures:
        lines += ["", "⚠️ Could not fetch (showing last stored data): " + ", ".join(sorted(failures))]
    lines += ["", "p = percentile of PE in the last 10y. Signal only, not financial advice."]
    return "\n".join(lines)
