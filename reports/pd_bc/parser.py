from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime
from typing import Any

from url_utils import normalize_adobe_url


CHANNELS = [
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

FUNNEL_ROWS = {
    "A Organic Search [1]": "Organic Search",
    "B Other [2~6]": "Other",
    # Backward compatibility for the earlier sample export.
    "B Order [2~6]": "Other",
    "C Paid [7~8]": "Paid",
}

FUNNEL_KEYS = [
    "bc_visit",
    "cart_add_event",
    "add_on_visit",
    "cart_page_visit",
    "checkout_login",
    "contact_info",
    "delivery",
    "payment",
    "order_confirmation",
    "order",
]


def _read_rows(content: bytes | str) -> list[list[str]]:
    if isinstance(content, bytes):
        text = content.decode("utf-8-sig", errors="replace")
    else:
        text = content.lstrip("\ufeff")
    return list(csv.reader(io.StringIO(text)))


def _num(value: str | int | float | None) -> float:
    text = str(value or "").strip().replace(",", "")
    if not text or text in {"-", "—"}:
        return 0.0
    if text.endswith("%"):
        text = text[:-1]
    try:
        return float(text)
    except ValueError:
        return 0.0


def _int(value: str | int | float | None) -> int:
    return int(round(_num(value)))


def _parse_date_line(text: str) -> tuple[date, date] | None:
    m = re.search(r"# Date:\s*([^\-]+?)\s+-\s+(.+)$", text.strip().strip('"'))
    if not m:
        return None
    start_text, end_text = m.group(1).strip(), m.group(2).strip()
    for fmt in ("%b %d, %Y", "%Y/%m/%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(start_text, fmt).date(), datetime.strptime(end_text, fmt).date()
        except ValueError:
            pass
    return None


def _clean_product_name(report_title: str) -> str:
    name = re.sub(r"\s+PD\+BC\s+Page\s*$", "", report_title.strip(), flags=re.I)
    name = re.sub(r"\s+PD\s+Page\s*$", "", name, flags=re.I)
    name = re.sub(r"\s+PD\s*$", "", name, flags=re.I)
    return name.strip()


def _find_next_section(rows: list[list[str]], start: int, title: str) -> int | None:
    for i in range(start, len(rows)):
        if rows[i] and rows[i][0].strip() == f"# {title}":
            return i
    return None


def _next_product_start(rows: list[list[str]], start: int) -> int:
    for i in range(start, len(rows) - 3):
        # A product starts with separator + title + report suite + date.
        # The same separator also appears immediately after the date, so do
        # not treat every separator as a new product boundary.
        if (
            rows[i]
            and rows[i][0].startswith("#===")
            and rows[i + 1]
            and rows[i + 1][0].startswith("# ")
            and rows[i + 2]
            and rows[i + 2][0].startswith("# Report suite")
            and rows[i + 3]
            and rows[i + 3][0].startswith("# Date:")
        ):
            return i
    return len(rows)


def _extract_table(rows: list[list[str]], start: int, end: int) -> list[list[str]]:
    out: list[list[str]] = []
    for row in rows[start:end]:
        if not row:
            continue
        if row[0].startswith("#") or row[0].startswith("###"):
            continue
        if all(not (cell or "").strip() for cell in row):
            continue
        out.append(row)
    return out


def _parse_main_matrix(rows: list[list[str]]) -> dict[str, dict[str, Any]]:
    data: dict[str, dict[str, Any]] = {}
    for row in rows:
        label = (row[0] if row else "").strip()
        channel = CHANNEL_MAP.get(label)
        if not channel:
            continue
        cells = row[1:13]
        while len(cells) < 12:
            cells.append("0")
        prev_pd, prev_pd2bc, prev_bc, prev_carrier, prev_estore, prev_order = [_int(x) for x in cells[:6]]
        curr_pd, curr_pd2bc, curr_bc, curr_carrier, curr_estore, curr_order = [_int(x) for x in cells[6:12]]
        data[channel] = {
            "previous": {
                "pd_visit": prev_pd,
                "pd_to_bc": prev_pd2bc,
                "bc_visit": prev_bc,
                "carrier_piv": prev_carrier,
                "estore_piv": prev_estore,
                "piv_total": prev_carrier + prev_estore,
                "order": prev_order,
                "pir": _pir(prev_carrier + prev_estore, prev_pd + prev_bc),
            },
            "current": {
                "pd_visit": curr_pd,
                "pd_to_bc": curr_pd2bc,
                "bc_visit": curr_bc,
                "carrier_piv": curr_carrier,
                "estore_piv": curr_estore,
                "piv_total": curr_carrier + curr_estore,
                "order": curr_order,
                "pir": _pir(curr_carrier + curr_estore, curr_pd + curr_bc),
            },
        }
    return data


def _pir(piv_total: float, visits: float) -> float | None:
    return piv_total / visits * 100 if visits else None


def _parse_devices(rows: list[list[str]]) -> dict[str, dict[str, Any]]:
    devices = {}
    for row in rows:
        label = (row[0] if row else "").strip()
        if not label or label.startswith(",") or label in {"Segments"} or label.startswith("Date"):
            continue
        if label.startswith("[") or label.startswith("[Device"):
            cells = row[1:9]
            while len(cells) < 8:
                cells.append("0")
            devices[label] = {
                "previous": {
                    "visits": _int(cells[0]),
                    "carrier_piv": _int(cells[1]),
                    "estore_piv": _int(cells[2]),
                    "order": _int(cells[3]),
                },
                "current": {
                    "visits": _int(cells[4]),
                    "carrier_piv": _int(cells[5]),
                    "estore_piv": _int(cells[6]),
                    "order": _int(cells[7]),
                },
            }
    return devices


def _device_group(devices: dict[str, Any], period: str, includes: list[str]) -> dict[str, Any]:
    visits = carrier = estore = order = 0
    for label, data in devices.items():
        if any(token in label for token in includes):
            p = data[period]
            visits += int(p.get("visits", 0) or 0)
            carrier += int(p.get("carrier_piv", 0) or 0)
            estore += int(p.get("estore_piv", 0) or 0)
            order += int(p.get("order", 0) or 0)
    piv = carrier + estore
    return {"visits": visits, "carrier_piv": carrier, "estore_piv": estore, "piv_total": piv, "order": order, "pir": _pir(piv, visits)}


def _parse_piv_detail(rows: list[list[str]]) -> dict[str, dict[str, int]]:
    detail: dict[str, dict[str, int]] = {}
    keys = ["piv_total", "carrier", "docomo", "au", "softbank", "rakuten", "jcom", "estore"]
    for row in rows:
        label = (row[0] if row else "").strip()
        if label not in {"Date Ranges", "2 weeks ago", "Last Week"}:
            continue
        vals = row[1:9]
        while len(vals) < 8:
            vals.append("0")
        detail[label] = {k: _int(v) for k, v in zip(keys, vals)}
    return detail


def _parse_funnel(rows: list[list[str]]) -> dict[str, dict[str, dict[str, int]]]:
    data: dict[str, dict[str, dict[str, int]]] = {"current": {}, "previous": {}}
    for row in rows:
        if len(row) < 3:
            continue
        period_label = (row[0] or "").strip()
        segment_label = (row[1] or "").strip()
        segment = FUNNEL_ROWS.get(segment_label)
        if not segment:
            continue
        period = "current" if period_label == "Last Week" else "previous" if period_label == "2 weeks ago" else None
        if not period:
            continue
        vals = row[2:12]
        while len(vals) < len(FUNNEL_KEYS):
            vals.append("0")
        data[period][segment] = {k: _int(v) for k, v in zip(FUNNEL_KEYS, vals)}
    return data


def _summarize_devices(devices: dict[str, Any]) -> dict[str, Any]:
    current_galaxy = _device_group(devices, "current", ["Galaxy S", "Galaxy Z", "Galaxy A"])
    current_iphone = _device_group(devices, "current", ["iPhone"])
    current_sony = _device_group(devices, "current", ["Sony Xperia"])
    return {"Galaxy": current_galaxy, "iPhone": current_iphone, "Sony Xperia": current_sony}


def _period_label(start: date, end: date) -> str:
    return f"{start.year}/{start.month}/{start.day}~{end.year}/{end.month}/{end.day}"


def _short_period_label(start: date, end: date) -> str:
    return f"{str(start.year)[2:]}/{start.month}/{start.day} ~ {str(end.year)[2:]}/{end.month}/{end.day}"


def parse_pd_bc_csv(content: bytes | str) -> dict[str, Any]:
    rows = _read_rows(content)
    products: list[dict[str, Any]] = []
    i = 0
    while i < len(rows):
        row = rows[i]
        if not row or not row[0].startswith("#==="):
            i += 1
            continue
        if i + 3 >= len(rows):
            break
        title = rows[i + 1][0].lstrip("#").strip() if rows[i + 1] else ""
        parsed_dates = _parse_date_line(rows[i + 3][0] if rows[i + 3] else "")
        if not title or not parsed_dates:
            i += 1
            continue
        start_date, end_date = parsed_dates
        product_end = _next_product_start(rows, i + 4)

        url = ""
        url_idx = None
        for j in range(i + 4, product_end):
            cell = rows[j][0].strip() if rows[j] else ""
            if cell.startswith("# http") or cell.startswith("# www"):
                url = cell.lstrip("#").strip()
                url_idx = j
                break
        if not url or url_idx is None:
            i = product_end
            continue

        devices_idx = _find_next_section(rows, url_idx, "主な端末別")
        piv_idx = _find_next_section(rows, url_idx, "PIV詳細")
        funnel_idx = _find_next_section(rows, url_idx, "BCからOrderまでの購入経路")

        main_end = min(x for x in (devices_idx, piv_idx, funnel_idx, product_end) if x is not None)
        main_table = _extract_table(rows, url_idx + 1, main_end)

        devices_table = _extract_table(rows, devices_idx + 1, piv_idx or product_end) if devices_idx is not None and piv_idx is not None else []
        piv_table = _extract_table(rows, piv_idx + 1, funnel_idx or product_end) if piv_idx is not None else []
        funnel_table = _extract_table(rows, funnel_idx + 1, product_end) if funnel_idx is not None else []

        product = {
            "report_title": title,
            "product_name": _clean_product_name(title),
            "url": normalize_adobe_url(url),
            "raw_url": url,
            "date_start": start_date.isoformat(),
            "date_end": end_date.isoformat(),
            "period_label": _period_label(start_date, end_date),
            "short_period_label": _short_period_label(start_date, end_date),
            "main": _parse_main_matrix(main_table),
            "devices": _parse_devices(devices_table),
            "piv_detail": _parse_piv_detail(piv_table),
            "funnel": _parse_funnel(funnel_table),
        }
        product["device_summary"] = _summarize_devices(product["devices"])
        products.append(product)
        i = product_end
    if not products:
        raise ValueError("PD+BC Page用のデータを取得できませんでした。")
    return {"products": products}
