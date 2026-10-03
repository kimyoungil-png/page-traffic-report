from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime, timedelta
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


def _pir(piv_total: float, visits: float) -> float | None:
    return piv_total / visits * 100 if visits else None


def _parse_date_line(text: str) -> tuple[date, date] | None:
    m = re.search(r"# Date:\s*(.+?)\s+-\s+(.+)$", text.strip().strip('"'))
    if not m:
        return None
    start_text, end_text = m.group(1).strip(), m.group(2).strip()
    for fmt in ("%b %d, %Y", "%Y/%m/%d", "%Y-%m-%d"):
        try:
            return (
                datetime.strptime(start_text, fmt).date(),
                datetime.strptime(end_text, fmt).date(),
            )
        except ValueError:
            pass
    return None


def _clean_product_name(report_title: str) -> str:
    name = re.sub(
        r"\s+PD\+BC\s+Page\s*$",
        "",
        report_title.strip(),
        flags=re.I,
    )
    name = re.sub(r"\s+PD\s+Page\s*$", "", name, flags=re.I)
    name = re.sub(r"\s+PD\s*$", "", name, flags=re.I)
    return name.strip()


def _find_next_section(
    rows: list[list[str]],
    start: int,
    title: str,
) -> int | None:
    for i in range(start, len(rows)):
        if rows[i] and rows[i][0].strip() == f"# {title}":
            return i
    return None


def _next_product_start(
    rows: list[list[str]],
    start: int,
) -> int:
    for i in range(start, len(rows) - 3):
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


def _extract_table(
    rows: list[list[str]],
    start: int,
    end: int,
) -> list[list[str]]:
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


def _unique_period_labels(header_row: list[str]) -> list[str]:
    labels: list[str] = []
    for cell in header_row[1:]:
        label = (cell or "").strip()
        if label and label not in labels:
            labels.append(label)
    return labels


def _period_map_from_table(
    rows: list[list[str]],
) -> dict[str, str]:
    """
    Normalize whatever Adobe calls the 3 displayed periods into:
    older -> 先々週, previous -> 先週, current -> 今週.

    The export labels can be e.g.
    3 weeks ago / 2 weeks ago / Last Week
    or
    2 weeks ago / Last Week / This Week.
    We therefore use chronological column order, not the literal wording.
    """
    for row in rows:
        labels = _unique_period_labels(row)
        if 2 <= len(labels) <= 4 and any(
            "week" in label.lower()
            for label in labels
        ):
            if len(labels) >= 3:
                selected = labels[-3:]
                return {
                    selected[0]: "older",
                    selected[1]: "previous",
                    selected[2]: "current",
                }
            return {
                labels[0]: "previous",
                labels[1]: "current",
            }
    return {
        "2 weeks ago": "previous",
        "Last Week": "current",
    }


def _period_dates(
    start: date,
    end: date,
) -> dict[str, dict[str, str]]:
    return {
        "older": {
            "start": (start - timedelta(days=14)).isoformat(),
            "end": (end - timedelta(days=14)).isoformat(),
        },
        "previous": {
            "start": (start - timedelta(days=7)).isoformat(),
            "end": (end - timedelta(days=7)).isoformat(),
        },
        "current": {
            "start": start.isoformat(),
            "end": end.isoformat(),
        },
    }


def _period_keys(
    period_map: dict[str, str],
) -> list[str]:
    if "older" in period_map.values():
        return ["older", "previous", "current"]
    return ["previous", "current"]


def _parse_main_matrix(
    rows: list[list[str]],
    period_map: dict[str, str],
) -> dict[str, dict[str, Any]]:
    data: dict[str, dict[str, Any]] = {}
    keys = _period_keys(period_map)

    for row in rows:
        label = (row[0] if row else "").strip()
        channel = CHANNEL_MAP.get(label)
        if not channel:
            continue

        cells = row[1:]
        metric_count = 6
        groups = [
            cells[i : i + metric_count]
            for i in range(0, len(cells), metric_count)
        ]
        groups = [
            group
            for group in groups
            if len(group) >= metric_count
        ]
        if len(groups) < len(keys):
            continue
        groups = groups[-len(keys) :]

        record: dict[str, Any] = {}
        for period, group in zip(keys, groups):
            (
                pd_visit,
                pd_to_bc,
                bc_visit,
                carrier_piv,
                estore_piv,
                order,
            ) = [_int(value) for value in group[:6]]

            piv_total = carrier_piv + estore_piv
            record[period] = {
                "pd_visit": pd_visit,
                "pd_to_bc": pd_to_bc,
                "bc_visit": bc_visit,
                "carrier_piv": carrier_piv,
                "estore_piv": estore_piv,
                "piv_total": piv_total,
                "order": order,
                "pir": _pir(
                    piv_total,
                    pd_visit + bc_visit,
                ),
            }
        data[channel] = record

    return data


def _device_display_name(label: str) -> str:
    if "PC User" in label:
        return "PC"
    if "Galaxy S" in label:
        return "Galaxy S"
    if "Galaxy Z" in label:
        return "Galaxy Z"
    if "Galaxy A" in label:
        return "Galaxy A"
    if "Google Pixel" in label:
        return "Google Pixel"
    if "Sony Xperia" in label:
        return "Sony Xperia"
    if "iPhone" in label:
        return "iPhone"
    return re.sub(
        r"^\[[^\]]+\]\s*\d*\s*",
        "",
        label,
    ).strip()


def _parse_devices(
    rows: list[list[str]],
    period_map: dict[str, str],
) -> dict[str, dict[str, Any]]:
    devices: dict[str, dict[str, Any]] = {}
    keys = _period_keys(period_map)

    for row in rows:
        label = (row[0] if row else "").strip()
        if not label or not (
            label.startswith("[")
            or label.startswith("[Device")
        ):
            continue

        cells = row[1:]
        metric_count = 4
        groups = [
            cells[i : i + metric_count]
            for i in range(0, len(cells), metric_count)
        ]
        groups = [
            group
            for group in groups
            if len(group) >= metric_count
        ]
        if len(groups) < len(keys):
            continue
        groups = groups[-len(keys) :]

        display_name = _device_display_name(label)
        record: dict[str, Any] = {
            "raw_label": label,
        }

        for period, group in zip(keys, groups):
            visits, carrier_piv, estore_piv, order = [
                _int(value)
                for value in group[:4]
            ]
            piv_total = carrier_piv + estore_piv
            record[period] = {
                "visits": visits,
                "carrier_piv": carrier_piv,
                "estore_piv": estore_piv,
                "piv_total": piv_total,
                "order": order,
                "pir": _pir(piv_total, visits),
            }

        devices[display_name] = record

    return devices


def _sum_devices(
    devices: dict[str, Any],
    names: list[str],
    period: str,
) -> dict[str, Any]:
    total = {
        "visits": 0,
        "carrier_piv": 0,
        "estore_piv": 0,
        "piv_total": 0,
        "order": 0,
    }
    for name in names:
        row = devices.get(name, {}).get(period, {})
        for key in (
            "visits",
            "carrier_piv",
            "estore_piv",
            "piv_total",
            "order",
        ):
            total[key] += int(row.get(key, 0) or 0)

    total["pir"] = _pir(
        total["piv_total"],
        total["visits"],
    )
    return total


def _summarize_devices(
    devices: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    groups: dict[str, list[str]] = {
        "Galaxy": [
            "Galaxy S",
            "Galaxy Z",
            "Galaxy A",
        ],
    }

    for name in devices:
        if name not in {
            "Galaxy S",
            "Galaxy Z",
            "Galaxy A",
        }:
            groups[name] = [name]

    summary: dict[str, Any] = {}
    for label, members in groups.items():
        summary[label] = {}
        for period in (
            "older",
            "previous",
            "current",
        ):
            summary[label][period] = _sum_devices(
                devices,
                members,
                period,
            )

    ranking = sorted(
        [
            {
                "name": label,
                **values["current"],
            }
            for label, values in summary.items()
        ],
        key=lambda row: (
            row.get("piv_total", 0),
            row.get("visits", 0),
        ),
        reverse=True,
    )
    return summary, ranking


def _carrier_key(header: str) -> str | None:
    text = (header or "").strip()
    lower = text.lower()

    if "dcm carrier" in lower or "docomo" in lower:
        return "docomo"
    if "au carrier" in lower:
        return "au"
    if "softbank carrier" in lower:
        return "softbank"
    if "rakuten carrier" in lower:
        return "rakuten"
    if "jcom carrier" in lower or "j:com" in lower:
        return "jcom"

    match = re.search(
        r"PIV\s*\((.+?)\s*carrier\)",
        text,
        flags=re.I,
    )
    if match:
        return re.sub(
            r"\s+",
            "_",
            match.group(1).strip().lower(),
        )
    return None


def _parse_iso_date(
    value: str,
) -> date | None:
    try:
        return date.fromisoformat(
            (value or "").strip()
        )
    except ValueError:
        return None


def _parse_piv_detail(
    rows: list[list[str]],
    period_map: dict[str, str],
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "summary": {},
        "daily": {
            "older": [],
            "previous": [],
            "current": [],
        },
        "carrier_order": [],
    }
    if not rows:
        return result

    header = next(
        (
            row
            for row in rows
            if any(
                "PIV [Carrier]" in (cell or "")
                for cell in row
            )
        ),
        None,
    )
    if not header:
        return result

    column_map: dict[str, int] = {}
    carrier_columns: list[tuple[int, str]] = []

    for index, cell in enumerate(header):
        name = (cell or "").strip()
        if name == "Visits":
            column_map["visits"] = index
        elif name == "PIV [Carrier]":
            column_map["carrier_piv"] = index
        elif name == "PIV [eStore]":
            column_map["estore_piv"] = index
        else:
            carrier = _carrier_key(name)
            if carrier:
                carrier_columns.append(
                    (index, carrier)
                )

    result["carrier_order"] = [
        carrier
        for _, carrier in carrier_columns
    ]

    for row in rows:
        label = (
            row[0]
            if row
            else ""
        ).strip()
        period = period_map.get(label)
        if not period:
            continue

        day = _parse_iso_date(
            row[1]
            if len(row) > 1
            else ""
        )

        record = {
            "visits": (
                _int(row[column_map["visits"]])
                if "visits" in column_map
                and len(row) > column_map["visits"]
                else 0
            ),
            "carrier_piv": (
                _int(row[column_map["carrier_piv"]])
                if "carrier_piv" in column_map
                and len(row) > column_map["carrier_piv"]
                else 0
            ),
            "estore_piv": (
                _int(row[column_map["estore_piv"]])
                if "estore_piv" in column_map
                and len(row) > column_map["estore_piv"]
                else 0
            ),
            "carriers": {
                carrier: (
                    _int(row[index])
                    if len(row) > index
                    else 0
                )
                for index, carrier
                in carrier_columns
            },
        }
        record["piv_total"] = (
            record["carrier_piv"]
            + record["estore_piv"]
        )

        if day:
            record["date"] = day.isoformat()
            result["daily"].setdefault(
                period,
                [],
            ).append(record)
        elif (
            len(row) < 2
            or not (row[1] or "").strip()
        ):
            result["summary"][period] = record

    return result


def _parse_funnel(
    rows: list[list[str]],
    period_map: dict[str, str],
) -> dict[str, dict[str, dict[str, int]]]:
    data: dict[str, dict[str, dict[str, int]]] = {
        "older": {},
        "previous": {},
        "current": {},
    }

    for row in rows:
        if len(row) < 3:
            continue

        period = period_map.get(
            (row[0] or "").strip()
        )
        segment = FUNNEL_ROWS.get(
            (row[1] or "").strip()
        )
        if not period or not segment:
            continue

        values = row[2:12]
        while len(values) < len(FUNNEL_KEYS):
            values.append("0")

        data[period][segment] = {
            key: _int(value)
            for key, value
            in zip(FUNNEL_KEYS, values)
        }

    return data


def _period_label(
    start: date,
    end: date,
) -> str:
    return (
        f"{start.year}/{start.month}/{start.day}"
        f"~{end.year}/{end.month}/{end.day}"
    )


def _short_period_label(
    start: date,
    end: date,
) -> str:
    return (
        f"{str(start.year)[2:]}/{start.month}/{start.day}"
        f" ~ "
        f"{str(end.year)[2:]}/{end.month}/{end.day}"
    )


def parse_pd_bc_csv(
    content: bytes | str,
) -> dict[str, Any]:
    rows = _read_rows(content)
    products: list[dict[str, Any]] = []
    i = 0

    while i < len(rows):
        row = rows[i]
        if (
            not row
            or not row[0].startswith("#===")
        ):
            i += 1
            continue

        if i + 3 >= len(rows):
            break

        title = (
            rows[i + 1][0]
            .lstrip("#")
            .strip()
            if rows[i + 1]
            else ""
        )
        parsed_dates = _parse_date_line(
            rows[i + 3][0]
            if rows[i + 3]
            else ""
        )
        if not title or not parsed_dates:
            i += 1
            continue

        start_date, end_date = parsed_dates
        product_end = _next_product_start(
            rows,
            i + 4,
        )

        url = ""
        url_idx = None
        for j in range(
            i + 4,
            product_end,
        ):
            cell = (
                rows[j][0].strip()
                if rows[j]
                else ""
            )
            if (
                cell.startswith("# http")
                or cell.startswith("# www")
            ):
                url = (
                    cell.lstrip("#").strip()
                )
                url_idx = j
                break

        if not url or url_idx is None:
            i = product_end
            continue

        devices_idx = _find_next_section(
            rows,
            url_idx,
            "主な端末別",
        )
        piv_idx = _find_next_section(
            rows,
            url_idx,
            "PIV詳細",
        )
        funnel_idx = _find_next_section(
            rows,
            url_idx,
            "BCからOrderまでの購入経路",
        )

        main_end = min(
            value
            for value in (
                devices_idx,
                piv_idx,
                funnel_idx,
                product_end,
            )
            if value is not None
        )

        main_table = _extract_table(
            rows,
            url_idx + 1,
            main_end,
        )
        period_map = _period_map_from_table(
            main_table
        )

        devices_table = (
            _extract_table(
                rows,
                devices_idx + 1,
                piv_idx or product_end,
            )
            if devices_idx is not None
            and piv_idx is not None
            else []
        )
        piv_table = (
            _extract_table(
                rows,
                piv_idx + 1,
                funnel_idx or product_end,
            )
            if piv_idx is not None
            else []
        )
        funnel_table = (
            _extract_table(
                rows,
                funnel_idx + 1,
                product_end,
            )
            if funnel_idx is not None
            else []
        )

        devices = _parse_devices(
            devices_table,
            period_map,
        )
        (
            device_summary,
            device_ranking,
        ) = _summarize_devices(devices)

        product = {
            "report_title": title,
            "product_name": _clean_product_name(
                title
            ),
            "url": normalize_adobe_url(url),
            "raw_url": url,
            "date_start": start_date.isoformat(),
            "date_end": end_date.isoformat(),
            "period_label": _period_label(
                start_date,
                end_date,
            ),
            "short_period_label": (
                _short_period_label(
                    start_date,
                    end_date,
                )
            ),
            "period_map": period_map,
            "period_dates": _period_dates(
                start_date,
                end_date,
            ),
            "main": _parse_main_matrix(
                main_table,
                period_map,
            ),
            "devices": devices,
            "device_summary": device_summary,
            "device_ranking": device_ranking,
            "piv_detail": _parse_piv_detail(
                piv_table,
                period_map,
            ),
            "funnel": _parse_funnel(
                funnel_table,
                period_map,
            ),
        }

        products.append(product)
        i = product_end

    if not products:
        raise ValueError(
            "PD+BC Page用のデータを取得できませんでした。"
        )

    return {
        "products": products,
    }
