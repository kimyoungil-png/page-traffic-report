from __future__ import annotations

from typing import Any

from adobe_parser import CHANNEL_ORDER


def safe_ratio(current: float, previous: float) -> float | None:
    if previous == 0:
        return None
    return current / previous


def format_ratio(current: float, previous: float) -> str:
    if previous == 0:
        return "NEW" if current > 0 else "—"
    return f"x{current / previous:.2f}"


def format_compact(value: int | float) -> str:
    value = float(value or 0)
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if abs(value) >= 1_000:
        return f"{value / 1_000:.1f}K"
    return f"{int(round(value)):,}"


def format_pct(value: float | None, digits: int = 0) -> str:
    if value is None:
        return "—"
    return f"{value:.{digits}f}%"


def channel_share_line(page: dict[str, Any], top_n: int = 3) -> str:
    current = page["current"]["entry"]
    total = float(current.get("Total", 0) or 0)
    if total <= 0:
        return "流入割合：—"
    rows = []
    for channel in CHANNEL_ORDER:
        if channel == "Total":
            continue
        value = float(current.get(channel, 0) or 0)
        rows.append((channel, value, value / total * 100))
    rows.sort(key=lambda x: x[1], reverse=True)
    rows = rows[:top_n]
    return "流入割合：" + " > ".join(
        f"{channel} {pct:.0f}%" for channel, _, pct in rows
    )


def cta_summary_line(page: dict[str, Any]) -> str:
    entry_total = float(page["current"]["entry"].get("Total", 0) or 0)
    cta_total = page["current"].get("cta", {}).get("Total")
    if cta_total is None:
        return ""
    cta_total = float(cta_total or 0)
    ctr = (cta_total / entry_total * 100) if entry_total > 0 else None
    return f"Entry→PF・PD・BC {int(cta_total):,} Visit、CTR {format_pct(ctr, 1)}"


def fallback_headline(page: dict[str, Any]) -> str:
    current = page["current"]["entry"]
    previous = page["previous"]["entry"]
    total_now = float(current.get("Total", 0) or 0)
    total_prev = float(previous.get("Total", 0) or 0)
    total_ratio = safe_ratio(total_now, total_prev)

    channels = []
    for channel in CHANNEL_ORDER:
        if channel == "Total":
            continue
        now = float(current.get(channel, 0) or 0)
        prev = float(previous.get(channel, 0) or 0)
        share = now / total_now * 100 if total_now else 0
        channels.append((channel, now, prev, share, safe_ratio(now, prev)))
    channels.sort(key=lambda x: x[1], reverse=True)
    dominant = channels[0] if channels else ("流入", 0, 0, 0, None)

    if total_prev == 0 and total_now > 0:
        return f"新規流入が発生し、{dominant[0]}が中心"
    if total_ratio is not None and total_ratio >= 1.2:
        return f"Entry Visitは前週比で増加、{dominant[0]}が流入を牽引"
    if total_ratio is not None and total_ratio <= 0.8:
        return f"Entry Visitは前週比で減少、{dominant[0]}が主要流入を占める"
    if dominant[3] >= 70:
        return f"前週比で大きな変動はなく、{dominant[0]}中心の流入構成を維持"
    return "Entry Visitは前週並みで推移"


def _total_metrics(page: dict[str, Any], period: str) -> dict[str, Any]:
    entry = float(page[period]["entry"].get("Total", 0) or 0)
    cta_raw = page[period].get("cta", {}).get("Total")
    cta = float(cta_raw) if cta_raw is not None else None
    ctr = (cta / entry * 100) if cta is not None and entry > 0 else None
    bounce = page[period].get("bounce", {}).get("Total")
    return {"entry": int(entry), "cta": int(cta) if cta is not None else None, "ctr_pct": ctr, "bounce_pct": bounce}


def build_analysis_payload(page: dict[str, Any], gsc_queries: list[dict[str, Any]]) -> dict[str, Any]:
    current = page["current"]["entry"]
    previous = page["previous"]["entry"]
    total_now = float(current.get("Total", 0) or 0)
    channels = []
    for channel in CHANNEL_ORDER:
        if channel == "Total":
            continue
        now = float(current.get(channel, 0) or 0)
        prev = float(previous.get(channel, 0) or 0)
        curr_cta_raw = page["current"].get("cta", {}).get(channel)
        prev_cta_raw = page["previous"].get("cta", {}).get(channel)
        channels.append(
            {
                "channel": channel,
                "current_entry": int(now),
                "previous_entry": int(prev),
                "share_pct": round(now / total_now * 100, 1) if total_now else 0,
                "entry_ratio": round(now / prev, 3) if prev else None,
                "current_cta": int(curr_cta_raw) if curr_cta_raw is not None else None,
                "previous_cta": int(prev_cta_raw) if prev_cta_raw is not None else None,
                "current_bounce_pct": page["current"].get("bounce", {}).get(channel),
                "previous_bounce_pct": page["previous"].get("bounce", {}).get(channel),
            }
        )
    return {
        "current_total": _total_metrics(page, "current"),
        "previous_total": _total_metrics(page, "previous"),
        "total_entry_ratio": safe_ratio(total_now, float(previous.get("Total", 0) or 0)),
        "channels": channels,
        "gsc_queries": gsc_queries[:10],
    }


def build_table_rows(page: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for channel in CHANNEL_ORDER:
        prev_entry = int(page["previous"]["entry"].get(channel, 0) or 0)
        curr_entry = int(page["current"]["entry"].get(channel, 0) or 0)
        prev_cta_raw = page["previous"].get("cta", {}).get(channel)
        curr_cta_raw = page["current"].get("cta", {}).get(channel)
        prev_cta = int(prev_cta_raw) if prev_cta_raw is not None else None
        curr_cta = int(curr_cta_raw) if curr_cta_raw is not None else None
        curr_ctr = (curr_cta / curr_entry * 100) if curr_cta is not None and curr_entry > 0 else None
        rows.append(
            {
                "channel": channel,
                "previous_entry": prev_entry,
                "previous_cta": prev_cta,
                "previous_bounce": page["previous"].get("bounce", {}).get(channel),
                "current_entry": curr_entry,
                "ratio": format_ratio(curr_entry, prev_entry),
                "current_cta": curr_cta,
                "current_ctr": curr_ctr,
                "current_bounce": page["current"].get("bounce", {}).get(channel),
            }
        )
    return rows
