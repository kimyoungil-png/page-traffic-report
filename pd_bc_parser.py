from __future__ import annotations

import csv
import io
import re
from datetime import datetime
from typing import Any


CHANNEL_ORDER = [
    "App",
    "Organic Search",
    "Direct",
    "Referral",
    "Owned Social",
    "Social Network",
    "CRM",
    "Paid Search",
    "Display AD",
    "Total",
]

CHANNEL_MAP = {
    "[0] APP": "App",
    "[1] Organic": "Organic Search",
    "[2] Direct": "Direct",
    "[3] Referral": "Referral",
    "[4] Owned Social": "Owned Social",
    "[5] Social Network Referrals": "Social Network",
    "[6] CRM": "CRM",
    "[7] Paid Search": "Paid Search",
    "[8] Display AD": "Display AD",
    "[計] Total": "Total",
}

FUNNEL_SEGMENTS = {
    "A Organic Search [1]": "organic",
    "B Other [2~6]": "other",
    # Backward compatibility for the old label used in the sample CSV.
    "B Order [2~6]": "other",
    "C Paid [7~8]": "paid",
}


def _read_rows(content: bytes | str) -> list[list[str]]:
    if isinstance(content, bytes):
        text = content.decode("utf-8-sig", errors="replace")
    else:
        text = content.lstrip("\ufeff")
    return list(csv.reader(io.StringIO(text)))


def _int(value: str | int | float | None) -> int:
    if value is None:
        return 0
    text = str(value).strip().replace(",", "")
    if not text or text in {"-", "—"}:
        return 0
    try:
        return int(round(float(text)))
    except ValueError:
        return 0


def _pir(pd_visit: int, bc_visit: int, carrier_piv: int, estore_piv: int) -> float | None:
    denominator = pd_visit + bc_visit
    if denominator <= 0:
        return None
    return (carrier_piv + estore_piv) / denominator * 100


def _parse_period(text: str) -> tuple[str, str]:
    raw = (text or "").replace("# Date:", "").strip()
    if " - " not in raw:
        return "", ""
    left, right = [x.strip() for x in raw.split(" - ", 1)]
    for fmt in ("%b %d, %Y", "%Y/%m/%d", "%Y-%m-%d"):
        try:
            start = datetime.strptime(left, fmt).date()
            end = datetime.strptime(right, fmt).date()
            return start.isoformat(), end.isoformat()
        except ValueError:
            continue
    return "", ""


def _product_name(heading: str) -> str:
    text = heading.strip().lstrip("#").strip()
    text = re.sub(r"\s+PD(?:\+BC)?\s*Page.*$", "", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


def _find_index(block: list[list[str]], exact: str) -> int | None:
    for idx, row in enumerate(block):
        if row and row[0].strip() == exact:
            return idx
    return None


def _main_metrics(block: list[list[str]], stop_idx: int | None) -> dict[str, Any]:
    limit = stop_idx if stop_idx is not None else len(block)
    seg_idx = None
    for idx, row in enumerate(block[:limit]):
        if row and row[0].strip() == "Segments" and len(row) >= 13:
            seg_idx = idx
            break
    if seg_idx is None:
        raise ValueError("PD+BCのChannel別テーブルを取得できませんでした。")

    channels: dict[str, Any] = {}
    for row in block[seg_idx + 1 : limit]:
        if not row:
            continue
        label = row[0].strip()
        channel = CHANNEL_MAP.get(label)
        if not channel:
            continue
        if len(row) < 13:
            continue

        prev = {
            "pd_visit": _int(row[1]),
            "pd_to_bc": _int(row[2]),
            "bc_visit": _int(row[3]),
            "carrier_piv": _int(row[4]),
            "estore_piv": _int(row[5]),
            "order": _int(row[6]),
        }
        curr = {
            "pd_visit": _int(row[7]),
            "pd_to_bc": _int(row[8]),
            "bc_visit": _int(row[9]),
            "carrier_piv": _int(row[10]),
            "estore_piv": _int(row[11]),
            "order": _int(row[12]),
        }
        prev["pir"] = _pir(
            prev["pd_visit"], prev["bc_visit"], prev["carrier_piv"], prev["estore_piv"]
        )
        curr["pir"] = _pir(
            curr["pd_visit"], curr["bc_visit"], curr["carrier_piv"], curr["estore_piv"]
        )
        channels[channel] = {"previous": prev, "current": curr}

    if "Total" not in channels:
        raise ValueError("PD+BCのTotal行を取得できませんでした。")
    return channels


def _device_metrics(block: list[list[str]], start_idx: int | None, stop_idx: int | None) -> dict[str, Any]:
    if start_idx is None:
        return {}
    limit = stop_idx if stop_idx is not None else len(block)
    seg_idx = None
    for idx in range(start_idx, limit):
        row = block[idx]
        if row and row[0].strip() == "Segments" and len(row) >= 9:
            seg_idx = idx
            break
    if seg_idx is None:
        return {}

    result: dict[str, Any] = {}
    for row in block[seg_idx + 1 : limit]:
        if not row or len(row) < 9:
            continue
        label = row[0].strip()
        if not label.startswith(("[Device]", "[端末]")):
            continue
        if "Galaxy S" in label:
            key = "Galaxy S"
        elif "Galaxy Z" in label:
            key = "Galaxy Z"
        elif "Galaxy A" in label:
            key = "Galaxy A"
        elif "iPhone" in label:
            key = "iPhone"
        elif "Sony Xperia" in label:
            key = "Sony Xperia"
        elif "Google Pixel" in label:
            key = "Google Pixel"
        elif "PC User" in label:
            key = "PC User"
        else:
            key = re.sub(r"^\[[^\]]+\]\s*\d*\s*", "", label).strip()

        prev = {
            "visits": _int(row[1]),
            "carrier_piv": _int(row[2]),
            "estore_piv": _int(row[3]),
            "order": _int(row[4]),
        }
        curr = {
            "visits": _int(row[5]),
            "carrier_piv": _int(row[6]),
            "estore_piv": _int(row[7]),
            "order": _int(row[8]),
        }
        result[key] = {"previous": prev, "current": curr}
    return result


def _piv_detail(block: list[list[str]], start_idx: int | None, stop_idx: int | None) -> dict[str, Any]:
    if start_idx is None:
        return {}
    limit = stop_idx if stop_idx is not None else len(block)
    result: dict[str, Any] = {}
    for row in block[start_idx:limit]:
        if not row or len(row) < 9:
            continue
        label = row[0].strip()
        if label not in {"2 weeks ago", "Last Week"}:
            continue
        key = "previous" if label == "2 weeks ago" else "current"
        result[key] = {
            "total_piv": _int(row[1]),
            "carrier_piv": _int(row[2]),
            "docomo": _int(row[3]),
            "au": _int(row[4]),
            "softbank": _int(row[5]),
            "rakuten": _int(row[6]),
            "jcom": _int(row[7]),
            "estore_piv": _int(row[8]),
        }
    return result


def _funnel(block: list[list[str]], start_idx: int | None) -> dict[str, Any] | None:
    if start_idx is None:
        return None

    result: dict[str, Any] = {
        "current": {},
        "previous": {},
    }
    for row in block[start_idx:]:
        if not row or len(row) < 12:
            continue
        period = row[0].strip()
        segment = row[1].strip() if len(row) > 1 else ""
        segment_key = FUNNEL_SEGMENTS.get(segment)
        if period not in {"Last Week", "2 weeks ago"} or not segment_key:
            continue
        period_key = "current" if period == "Last Week" else "previous"
        values = [_int(value) for value in row[2:12]]
        if len(values) < 10:
            values.extend([0] * (10 - len(values)))
        result[period_key][segment_key] = values[:10]

    if not result["current"] and not result["previous"]:
        return None
    return result


def parse_pd_bc_csv(content: bytes | str) -> dict[str, Any]:
    rows = _read_rows(content)

    starts: list[int] = []
    for idx, row in enumerate(rows):
        if not row or not row[0].startswith("# "):
            continue
        if idx + 1 < len(rows) and rows[idx + 1] and rows[idx + 1][0].startswith("# Report suite:"):
            starts.append(idx)

    if not starts:
        raise ValueError("PD+BC PageのProduct blockを取得できませんでした。")

    products: list[dict[str, Any]] = []
    for pos, start in enumerate(starts):
        end = starts[pos + 1] if pos + 1 < len(starts) else len(rows)
        block = rows[start:end]

        heading = block[0][0]
        name = _product_name(heading)

        date_row = next(
            (row[0] for row in block if row and row[0].startswith("# Date:")),
            "",
        )
        period_start, period_end = _parse_period(date_row)

        raw_url = next(
            (
                row[0].lstrip("#").strip()
                for row in block
                if row and row[0].startswith("# http")
            ),
            "",
        )
        if not raw_url:
            raise ValueError(f"{name}: Product URLを取得できませんでした。")

        device_idx = _find_index(block, "# 主な端末別")
        piv_idx = _find_index(block, "# PIV詳細")
        funnel_idx = _find_index(block, "# BCからOrderまでの購入経路")

        channels = _main_metrics(block, device_idx)
        devices = _device_metrics(block, device_idx, piv_idx)
        piv = _piv_detail(block, piv_idx, funnel_idx)
        funnel = _funnel(block, funnel_idx)

        url = raw_url
        if not url.endswith("/"):
            url += "/"
        buy_url = url if url.rstrip("/").endswith("/buy") else url.rstrip("/") + "/buy/"

        products.append(
            {
                "name": name,
                "heading": heading.lstrip("#").strip(),
                "url": url,
                "buy_url": buy_url,
                "period_start": period_start,
                "period_end": period_end,
                "channels": channels,
                "devices": devices,
                "piv_detail": piv,
                "funnel": funnel,
            }
        )

    return {
        "products": products,
        "period_start": products[0].get("period_start", "") if products else "",
        "period_end": products[0].get("period_end", "") if products else "",
    }
