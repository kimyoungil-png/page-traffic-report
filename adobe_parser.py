from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime, timedelta
from typing import Any

from url_utils import is_probable_page_url, normalize_adobe_url


CHANNEL_ORDER = [
    "Organic Search",
    "Direct",
    "Referral",
    "Owned Social",
    "Social Referrals",
    "CRM",
    "Paid Search",
    "Display AD",
    "Total",
]


def _normalize_channel(value: str) -> str:
    text = re.sub(r"^\[[^\]]+\]\s*", "", (value or "").strip())
    mapping = {
        "Organic": "Organic Search",
        "Organic Search": "Organic Search",
        "Direct": "Direct",
        "Referral": "Referral",
        "Owned Social": "Owned Social",
        "Social Network Referrals": "Social Referrals",
        "Social Referrals": "Social Referrals",
        "CRM": "CRM",
        "Paid Search": "Paid Search",
        "Display AD": "Display AD",
        "Total": "Total",
    }
    return mapping.get(text, text)


def _number(value: str) -> float | None:
    text = (value or "").strip().replace(",", "")
    if not text or text in {"-", "—"}:
        return None
    if text.endswith("%"):
        text = text[:-1].strip()
    try:
        return float(text)
    except ValueError:
        return None


def _int_number(value: str) -> int:
    num = _number(value)
    return int(round(num or 0))


def _read_rows(content: bytes | str) -> list[list[str]]:
    if isinstance(content, bytes):
        text = content.decode("utf-8-sig", errors="replace")
    else:
        text = content.lstrip("\ufeff")
    return list(csv.reader(io.StringIO(text)))


def _parse_report_end(rows: list[list[str]]) -> date:
    for row in rows[:10]:
        if not row:
            continue
        text = row[0]
        match = re.search(r"# Date:\s*.+?\s+-\s+(.+)$", text)
        if not match:
            continue
        end_text = match.group(1).strip().strip('"')
        for fmt in ("%b %d, %Y", "%Y/%m/%d", "%Y-%m-%d"):
            try:
                return datetime.strptime(end_text, fmt).date()
            except ValueError:
                pass
    return date.today()


def _week_ranges(report_end: date) -> dict[str, date]:
    current_week_monday = report_end - timedelta(days=report_end.weekday())
    last_week_end = current_week_monday - timedelta(days=1)
    last_week_start = last_week_end - timedelta(days=6)
    previous_end = last_week_start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=6)
    return {
        "last_week_start": last_week_start,
        "last_week_end": last_week_end,
        "previous_start": previous_start,
        "previous_end": previous_end,
    }


def _extract_sections(rows: list[list[str]]) -> dict[str, list[list[str]]]:
    headings: list[tuple[int, str]] = []
    for idx, row in enumerate(rows):
        if len(row) != 1:
            continue
        value = row[0].strip()
        if not value.startswith("# "):
            continue
        name = value[2:].strip()
        if name in {"Freeform"} or name.startswith("Report suite:") or name.startswith("Date:"):
            continue
        headings.append((idx, name))

    sections: dict[str, list[list[str]]] = {}
    for pos, (idx, name) in enumerate(headings):
        end = headings[pos + 1][0] if pos + 1 < len(headings) else len(rows)
        sections[name] = rows[idx + 1 : end]
    return sections


def _parse_matrix(section_rows: list[list[str]]) -> dict[str, Any]:
    channel_row_idx = None
    for idx, row in enumerate(section_rows):
        if len(row) >= 20 and row and not row[0].strip() and any("[1]" in cell for cell in row):
            channel_row_idx = idx
            break
    if channel_row_idx is None:
        return {"rows": {}, "metric_labels": []}

    channel_row = section_rows[channel_row_idx]
    channels = [_normalize_channel(x) for x in channel_row[2:11]]
    current_channels = [_normalize_channel(x) for x in channel_row[11:20]]
    if current_channels and channels != current_channels:
        channels = current_channels

    metric_labels: list[str] = []
    for row in section_rows[:channel_row_idx]:
        metric_labels.extend(cell.strip() for cell in row if cell.strip())

    data: dict[str, Any] = {}
    for row in section_rows[channel_row_idx + 1 :]:
        if not row or len(row) < 20:
            continue
        key = row[0].strip()
        if (
            not key
            or key.startswith("Entry URL without Parameter")
            or not is_probable_page_url(key)
        ):
            continue
        previous = {ch: _int_number(row[2 + i]) for i, ch in enumerate(channels)}
        current = {ch: _int_number(row[11 + i]) for i, ch in enumerate(channels)}
        data[key] = {
            "change": _int_number(row[1]),
            "previous": previous,
            "current": current,
            "raw_previous": row[2:11],
            "raw_current": row[11:20],
        }
    return {"rows": data, "metric_labels": metric_labels}


def _matrix_equal(a: dict[str, Any], b: dict[str, Any], keys: list[str]) -> bool:
    if not a or not b:
        return False
    compared = 0
    for key in keys:
        if key not in a or key not in b:
            continue
        compared += 1
        if a[key].get("raw_previous") != b[key].get("raw_previous"):
            return False
        if a[key].get("raw_current") != b[key].get("raw_current"):
            return False
    return compared > 0


def _parse_rate_cell(raw: str) -> float | None:
    text = (raw or "").strip().replace(",", "")
    if not text:
        return None
    is_percent = text.endswith("%")
    if is_percent:
        text = text[:-1].strip()
    try:
        value = float(text)
    except ValueError:
        return None
    if is_percent:
        return value
    if 0 <= value <= 1 and "." in text:
        return value * 100
    if 0 <= value <= 100:
        return value
    return None


def parse_adobe_csv(content: bytes | str, top_n: int | None = None, as_of_date: date | None = None) -> dict[str, Any]:
    rows = _read_rows(content)
    sections = _extract_sections(rows)
    warnings: list[str] = []

    entry_name = next((name for name in sections if name.strip() == "Entry Visit"), None)
    if not entry_name:
        raise ValueError("Adobe CSV内に '# Entry Visit' セクションが見つかりません。")

    entry_matrix = _parse_matrix(sections[entry_name])
    entry_rows = entry_matrix["rows"]
    if not entry_rows:
        raise ValueError("Entry VisitのURLデータを取得できませんでした。")

    all_urls = list(entry_rows.keys())
    selected_urls = all_urls if top_n is None else all_urls[:top_n]

    cta_name = None
    for name, section_rows in sections.items():
        if name == entry_name:
            continue
        parsed = _parse_matrix(section_rows)
        labels = " ".join(parsed.get("metric_labels") or [])
        if "Bounce Rate" in labels:
            continue
        if "PF" in name or "PF" in labels or "[CTA]" in labels:
            cta_name = name
            break
    cta_matrix = _parse_matrix(sections[cta_name])["rows"] if cta_name else {}

    bounce_matrix: dict[str, Any] = {}
    bounce_name = None
    for name, section_rows in sections.items():
        parsed = _parse_matrix(section_rows)
        labels = " ".join(parsed.get("metric_labels") or [])
        if "Bounce Rate" in labels:
            bounce_name = name
            candidate = parsed["rows"]
            if cta_matrix and _matrix_equal(candidate, cta_matrix, selected_urls):
                warnings.append(
                    f"'{name}' はCTAセクションと値が同一のため、Bounce Rateとしては使用しません。"
                )
            else:
                bounce_matrix = candidate
            break

    report_end = _parse_report_end(rows)
    period_anchor = as_of_date or report_end
    periods = _week_ranges(period_anchor)

    pages: list[dict[str, Any]] = []
    for raw_url in selected_urls:
        entry = entry_rows[raw_url]
        cta = cta_matrix.get(raw_url, {})
        bounce = bounce_matrix.get(raw_url, {})

        page = {
            "raw_url": raw_url,
            "url": normalize_adobe_url(raw_url),
            "change": entry.get("change", 0),
            "previous": {
                "entry": entry.get("previous", {}),
                "cta": cta.get("previous", {}) if cta else {},
                "bounce": {},
            },
            "current": {
                "entry": entry.get("current", {}),
                "cta": cta.get("current", {}) if cta else {},
                "bounce": {},
            },
        }

        if bounce:
            for period_name, raw_key in (("previous", "raw_previous"), ("current", "raw_current")):
                raw_values = bounce.get(raw_key) or []
                rate_map = {}
                for idx, channel in enumerate(CHANNEL_ORDER):
                    if idx < len(raw_values):
                        rate = _parse_rate_cell(raw_values[idx])
                        if rate is not None:
                            rate_map[channel] = rate
                page[period_name]["bounce"] = rate_map
        pages.append(page)

    return {
        "pages": pages,
        "report_end": report_end.isoformat(),
        "period_anchor": period_anchor.isoformat(),
        "last_week_start": periods["last_week_start"].isoformat(),
        "last_week_end": periods["last_week_end"].isoformat(),
        "previous_start": periods["previous_start"].isoformat(),
        "previous_end": periods["previous_end"].isoformat(),
        "warnings": warnings,
        "source_sections": list(sections.keys()),
        "cta_section": cta_name,
        "bounce_section": bounce_name,
    }
