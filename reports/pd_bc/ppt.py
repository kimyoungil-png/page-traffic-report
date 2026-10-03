from __future__ import annotations

import io
import os
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_AUTO_SIZE
from pptx.util import Pt

from reports.pd_bc.parser import CHANNEL_ORDER


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TEMPLATE_PATH = ROOT / "templates" / "pd_bc_sample.pptx"
FONT_FACE = "Meiryo UI"

R_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

BLACK = RGBColor(0, 0, 0)
BLUE = RGBColor(30, 53, 227)
RATIO_BLUE = RGBColor(0, 49, 244)
RED = RGBColor(255, 0, 0)
GREY = RGBColor(128, 128, 128)
PALE = RGBColor(181, 181, 181)


def template_path() -> Path:
    return Path(
        os.getenv(
            "PD_BC_PPT_TEMPLATE_PATH",
            str(DEFAULT_TEMPLATE_PATH),
        )
    )


def _load_template() -> Presentation:
    path = template_path()
    if not path.exists():
        raise RuntimeError(
            "PD+BC PowerPointテンプレートが見つかりません: "
            f"{path}"
        )
    prs = Presentation(str(path))
    if len(prs.slides) < 2:
        raise RuntimeError(
            "PD+BCテンプレートにはSummary/Funnelの2枚が必要です。"
        )
    return prs


def _remap_relationship_ids(
    source_slide,
    new_slide,
    cloned_element,
) -> None:
    rid_map: dict[str, str] = {}
    for element in cloned_element.iter():
        for attr_name in (
            R_NS + "embed",
            R_NS + "link",
            R_NS + "id",
        ):
            old_rid = element.get(attr_name)
            if not old_rid or old_rid not in source_slide.part.rels:
                continue
            if old_rid not in rid_map:
                rel = source_slide.part.rels[old_rid]
                rid_map[old_rid] = new_slide.part.relate_to(
                    rel._target,
                    rel.reltype,
                )
            element.set(attr_name, rid_map[old_rid])


def _duplicate_slide(prs: Presentation, source_slide):
    new_slide = prs.slides.add_slide(source_slide.slide_layout)
    for shape in list(new_slide.shapes):
        element = shape.element
        element.getparent().remove(element)

    for shape in source_slide.shapes:
        cloned = deepcopy(shape.element)
        _remap_relationship_ids(
            source_slide,
            new_slide,
            cloned,
        )
        new_slide.shapes._spTree.insert_element_before(
            cloned,
            "p:extLst",
        )
    return new_slide


def _delete_slide(prs: Presentation, index: int) -> None:
    slide_id = prs.slides._sldIdLst[index]
    prs.part.drop_rel(slide_id.rId)
    del prs.slides._sldIdLst[index]


def _remove_shape(shape) -> None:
    element = shape.element
    element.getparent().remove(element)


def _set_font(
    run,
    size: float | None = None,
    color=None,
    bold: bool | None = None,
) -> None:
    run.font.name = FONT_FACE
    if size is not None:
        run.font.size = Pt(size)
    if color is not None:
        run.font.color.rgb = color
    if bold is not None:
        run.font.bold = bold


def _force_no_autofit(slide) -> None:
    for shape in slide.shapes:
        if hasattr(shape, "text_frame") and shape.has_text_frame:
            shape.text_frame.auto_size = MSO_AUTO_SIZE.NONE


def _find_text_shape(slide, predicate):
    for shape in slide.shapes:
        if not hasattr(shape, "text"):
            continue
        text = shape.text or ""
        if predicate(text, shape):
            return shape
    return None


def _find_table(slide, rows: int, cols: int):
    for shape in slide.shapes:
        if (
            shape.has_table
            and len(shape.table.rows) == rows
            and len(shape.table.columns) == cols
        ):
            return shape.table
    return None


def _set_shape_text(
    shape,
    text: str,
    *,
    size: float | None = None,
    color=None,
    bold: bool | None = None,
) -> None:
    tf = shape.text_frame
    tf.word_wrap = True
    tf.auto_size = MSO_AUTO_SIZE.NONE

    if tf.paragraphs and tf.paragraphs[0].runs:
        run = tf.paragraphs[0].runs[0]
        run.text = str(text or "")
        for extra in tf.paragraphs[0].runs[1:]:
            extra.text = ""
        _set_font(run, size=size, color=color, bold=bold)
        for paragraph in tf.paragraphs[1:]:
            for extra in paragraph.runs:
                extra.text = ""
        return

    tf.clear()
    run = tf.paragraphs[0].add_run()
    run.text = str(text or "")
    _set_font(run, size=size, color=color, bold=bold)


def _set_cell(
    cell,
    text: str,
    *,
    color=None,
    bold: bool | None = None,
) -> None:
    tf = cell.text_frame
    paragraph = tf.paragraphs[0]
    if paragraph.runs:
        run = paragraph.runs[0]
        run.text = str(text or "")
        for extra in paragraph.runs[1:]:
            extra.text = ""
    else:
        run = paragraph.add_run()
        run.text = str(text or "")
        _set_font(run, size=7.5)

    _set_font(run, color=color, bold=bold)

    for extra_p in tf.paragraphs[1:]:
        for extra_run in extra_p.runs:
            extra_run.text = ""


def _num(value: int | float | None) -> str:
    return f"{int(round(float(value or 0))):,}"


def _compact(value: int | float | None) -> str:
    number = float(value or 0)
    if abs(number) >= 10_000:
        return f"{number / 1000:.0f}K"
    if abs(number) >= 950:
        return f"{number / 1000:.1f}K"
    return f"{int(round(number)):,}"


def _pct(value: float | None, digits: int = 1) -> str:
    if value is None:
        return "—"
    return f"{float(value):.{digits}f}%"


def _ratio(current: int | float, previous: int | float) -> str:
    curr = float(current or 0)
    prev = float(previous or 0)
    if prev == 0:
        return "NEW" if curr > 0 else "—"
    return f"x{curr / prev:.2f}"


def _ratio_color(label: str):
    if label in {"", "—", "NEW"}:
        return GREY
    try:
        value = float(label.lstrip("x"))
    except ValueError:
        return RATIO_BLUE
    return RED if value < 1 else RATIO_BLUE


def _period(
    product: dict[str, Any],
    *,
    spaced: bool = False,
    short_year: bool = False,
    omit_end_year: bool = False,
) -> str:
    from datetime import date

    start_text = product.get("period_start") or ""
    end_text = product.get("period_end") or ""
    if not start_text or not end_text:
        return ""

    start = date.fromisoformat(start_text)
    end = date.fromisoformat(end_text)
    sep = " ~ " if spaced else "~"

    if short_year:
        return (
            f"{start.year % 100}/{start.month}/{start.day}"
            f"{sep}"
            f"{end.year % 100}/{end.month}/{end.day}"
        )

    if omit_end_year:
        return (
            f"{start.year}/{start.month}/{start.day}"
            f"{sep}"
            f"{end.month}/{end.day}"
        )

    return (
        f"{start.year}/{start.month}/{start.day}"
        f"{sep}"
        f"{end.year}/{end.month}/{end.day}"
    )


def _overall_pir(
    product: dict[str, Any],
    period: str,
) -> float | None:
    total = product["channels"]["Total"][period]
    denominator = total["pd_visit"] + total["bc_visit"]
    if denominator <= 0:
        return None

    piv = (
        product.get("piv_detail", {})
        .get(period, {})
        .get("total_piv")
    )
    if piv is None:
        piv = total["carrier_piv"] + total["estore_piv"]
    return float(piv or 0) / denominator * 100


def _channel_share_line(product: dict[str, Any]) -> str:
    total = product["channels"]["Total"]["current"]["bc_visit"]
    rows = []
    for channel in CHANNEL_ORDER:
        if channel == "Total":
            continue
        value = (
            product["channels"]
            .get(channel, {})
            .get("current", {})
            .get("bc_visit", 0)
        )
        share = value / total * 100 if total else 0
        rows.append((channel, value, share))

    rows.sort(key=lambda item: item[1], reverse=True)
    display = {
        "Organic Search": "Organic",
    }
    return "流入割合：" + " > ".join(
        f"{display.get(channel, channel)} {share:.0f}%"
        for channel, _value, share in rows[:3]
    )


def _device_values(
    product: dict[str, Any],
    keys: list[str],
) -> tuple[int, int]:
    visits = 0
    piv = 0
    devices = product.get("devices", {})
    for key in keys:
        current = devices.get(key, {}).get("current", {})
        visits += int(current.get("visits", 0) or 0)
        piv += int(current.get("carrier_piv", 0) or 0)
        piv += int(current.get("estore_piv", 0) or 0)
    return visits, piv


def _device_summary(product: dict[str, Any]) -> str:
    groups = (
        ("Galaxy", ["Galaxy S", "Galaxy Z", "Galaxy A"]),
        ("iPhone", ["iPhone"]),
        ("Sony Xperia", ["Sony Xperia"]),
    )
    parts = []
    for label, keys in groups:
        visits, piv = _device_values(product, keys)
        pir = piv / visits * 100 if visits else None
        parts.append(
            f"{label} {_compact(piv)}件 "
            f"(PIR {_pct(pir, 1)})"
        )
    return "PIV端末別：" + "、".join(parts)


def _headline(product: dict[str, Any]) -> str:
    total = product["channels"]["Total"]
    delta = (
        total["current"]["pd_visit"]
        - total["previous"]["pd_visit"]
    )

    contributions = []
    for channel in CHANNEL_ORDER:
        if channel == "Total":
            continue
        row = product["channels"].get(channel)
        if not row:
            continue
        change = (
            row["current"]["pd_visit"]
            - row["previous"]["pd_visit"]
        )
        contributions.append((channel, change))

    if delta < 0 and contributions:
        channel, change = min(
            contributions,
            key=lambda item: item[1],
        )
        if change < 0:
            return f"{channel}からのPD流入が減少"

    if delta > 0 and contributions:
        channel, change = max(
            contributions,
            key=lambda item: item[1],
        )
        if change > 0:
            return f"{channel}からのPD流入が増加"

    return "PD流入は前週並み"


def _fill_summary_title(
    slide,
    product: dict[str, Any],
) -> None:
    shape = _find_text_shape(
        slide,
        lambda text, _shape: (
            "PD Visit" in text
            and "BC Visit" in text
        ),
    )
    if shape is None:
        return

    name = product["name"]
    total = product["channels"]["Total"]
    prev = total["previous"]
    curr = total["current"]

    prev_piv = (
        product.get("piv_detail", {})
        .get("previous", {})
        .get(
            "total_piv",
            prev["carrier_piv"] + prev["estore_piv"],
        )
    )
    curr_piv = (
        product.get("piv_detail", {})
        .get("current", {})
        .get(
            "total_piv",
            curr["carrier_piv"] + curr["estore_piv"],
        )
    )

    pd_ratio = _ratio(curr["pd_visit"], prev["pd_visit"])
    bc_ratio = _ratio(curr["bc_visit"], prev["bc_visit"])
    piv_ratio = _ratio(curr_piv, prev_piv)

    tf = shape.text_frame
    tf.clear()
    tf.word_wrap = True
    tf.auto_size = MSO_AUTO_SIZE.NONE

    p0 = tf.paragraphs[0]
    for text, color in (
        (f"{name} PD Visit {_compact(curr['pd_visit'])} (", BLACK),
        (pd_ratio, _ratio_color(pd_ratio)),
        (" vs 先週) ", BLACK),
        (f"→ {_headline(product)}", BLUE),
    ):
        run = p0.add_run()
        run.text = text
        _set_font(run, size=15.0, color=color, bold=True)

    p1 = tf.add_paragraph()
    for text, color in (
        (f"{name} BC Visit {_compact(curr['bc_visit'])} (", BLACK),
        (bc_ratio, _ratio_color(bc_ratio)),
        (" vs 先週) , PIV ", BLACK),
        (f"{_compact(curr_piv)}件 (", BLACK),
        (piv_ratio, _ratio_color(piv_ratio)),
        (" vs 先週)", BLACK),
    ):
        run = p1.add_run()
        run.text = text
        _set_font(run, size=15.0, color=color, bold=True)


def _fill_summary_bullets(
    slide,
    product: dict[str, Any],
) -> None:
    shape = _find_text_shape(
        slide,
        lambda text, _shape: "流入割合" in text,
    )
    if shape is None:
        return

    tf = shape.text_frame
    tf.word_wrap = True
    tf.auto_size = MSO_AUTO_SIZE.NONE

    lines = (
        _channel_share_line(product),
        (
            "PIR：先週 "
            f"{_pct(_overall_pir(product, 'previous'), 1)}"
            " → 今週 "
            f"{_pct(_overall_pir(product, 'current'), 1)}"
        ),
        _device_summary(product),
    )

    while len(tf.paragraphs) < len(lines):
        tf.add_paragraph()

    for index, line in enumerate(lines):
        paragraph = tf.paragraphs[index]
        if paragraph.runs:
            run = paragraph.runs[0]
            run.text = line
            for extra in paragraph.runs[1:]:
                extra.text = ""
        else:
            run = paragraph.add_run()
            run.text = line
        _set_font(run, size=11.0, color=BLACK, bold=False)

    for paragraph in tf.paragraphs[len(lines):]:
        for run in paragraph.runs:
            run.text = ""


def _fill_summary_table(
    slide,
    product: dict[str, Any],
) -> None:
    table = _find_table(slide, 12, 17)
    if table is None:
        raise RuntimeError(
            "PD+BC Summary table (12x17) が見つかりません。"
        )

    name = product["name"]
    _set_cell(table.cell(0, 0), f"{name}\nPD+BC")
    _set_cell(
        table.cell(0, 8),
        f"Last Week ({_period(product, spaced=True, short_year=True)})",
    )
    _set_cell(table.cell(1, 7), f"{name}\nOrder")
    _set_cell(table.cell(1, 16), f"{name} Order")

    for row_index, channel in enumerate(
        CHANNEL_ORDER,
        start=2,
    ):
        data = product["channels"].get(channel)
        if not data:
            continue

        prev = data["previous"]
        curr = data["current"]
        pd_ratio = _ratio(
            curr["pd_visit"],
            prev["pd_visit"],
        )
        bc_ratio = _ratio(
            curr["bc_visit"],
            prev["bc_visit"],
        )

        values = (
            channel,
            _num(prev["pd_visit"]),
            _num(prev["pd_to_bc"]),
            _num(prev["bc_visit"]),
            _num(prev["carrier_piv"]),
            _num(prev["estore_piv"]),
            _pct(prev["pir"], 1),
            _num(prev["order"]),
            _num(curr["pd_visit"]),
            pd_ratio,
            _num(curr["pd_to_bc"]),
            _num(curr["bc_visit"]),
            bc_ratio,
            _num(curr["carrier_piv"]),
            _num(curr["estore_piv"]),
            _pct(curr["pir"], 1),
            _num(curr["order"]),
        )

        for col_index, value in enumerate(values):
            color = None
            if col_index == 9:
                color = _ratio_color(pd_ratio)
            elif col_index == 12:
                color = _ratio_color(bc_ratio)

            _set_cell(
                table.cell(row_index, col_index),
                value,
                color=color,
                bold=(
                    True
                    if col_index in {9, 12}
                    else channel == "Total"
                ),
            )


def _fill_carrier_boxes(
    slide,
    product: dict[str, Any],
) -> None:
    boxes = [
        shape
        for shape in slide.shapes
        if hasattr(shape, "text")
        and (shape.text or "").strip().startswith("docomo")
    ]
    boxes.sort(key=lambda shape: shape.left)

    if not boxes:
        return

    periods = (
        ["previous", "current"]
        if len(boxes) >= 2
        else ["current"]
    )

    for shape, period in zip(boxes, periods):
        data = (
            product.get("piv_detail", {})
            .get(period, {})
        )
        _set_shape_text(
            shape,
            (
                f"docomo {_num(data.get('docomo'))}\n"
                f"au {_num(data.get('au'))}\n"
                f"SoftBank {_num(data.get('softbank'))}\n"
                f"Rakuten {_num(data.get('rakuten'))}"
            ),
        )


def _fill_summary_meta(
    slide,
    product: dict[str, Any],
) -> None:
    label = _find_text_shape(
        slide,
        lambda text, _shape: (
            text.strip().endswith("PD+BC Page")
            and len(text.strip()) < 80
        ),
    )
    if label is not None:
        _set_shape_text(
            label,
            f"{product['name']} PD+BC Page",
            size=10.0,
            color=PALE,
            bold=True,
        )

    footer = _find_text_shape(
        slide,
        lambda text, _shape: "Data：" in text,
    )
    if footer is not None:
        _set_shape_text(
            footer,
            (
                f"Data：{_period(product)}\n"
                f"{product.get('url', '')}、"
                f"{product.get('buy_url', '')}"
            ),
            size=6.4,
            color=GREY,
        )


def _replace_screenshot(
    slide,
    screenshot_bytes: bytes | None,
) -> None:
    target = next(
        (
            shape
            for shape in slide.shapes
            if shape.shape_type == 13
        ),
        None,
    )
    if target is None or not screenshot_bytes:
        return

    left = target.left
    top = target.top
    width = target.width
    height = target.height
    _remove_shape(target)

    with tempfile.NamedTemporaryFile(
        suffix=".png",
        delete=False,
    ) as file:
        file.write(screenshot_bytes)
        path = file.name

    try:
        slide.shapes.add_picture(
            path,
            left,
            top,
            width=width,
            height=height,
        )
    finally:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


def _fill_summary_slide(
    slide,
    product: dict[str, Any],
) -> None:
    _fill_summary_title(slide, product)
    _fill_summary_bullets(slide, product)
    _fill_summary_table(slide, product)
    _fill_carrier_boxes(slide, product)
    _fill_summary_meta(slide, product)
    _replace_screenshot(
        slide,
        product.get("screenshot_bytes"),
    )
    _force_no_autofit(slide)


FUNNEL_TABLE_COLS = (0, 1, 2, 3, 4, 5, 6, 7, 9, 10)
PREVIOUS_ABSOLUTE_COLS = {0, 1, 3, 10}


def _funnel_rate(
    values: list[int],
    index: int,
) -> float | None:
    if not values:
        return None
    base = values[0]
    if base <= 0:
        return None
    return values[index] / base * 100


def _fill_funnel_group(
    table,
    *,
    current_row: int,
    previous_row: int,
    current_rate_row: int,
    previous_rate_row: int,
    current: list[int],
    previous: list[int],
) -> None:
    for value_index, table_col in enumerate(
        FUNNEL_TABLE_COLS
    ):
        _set_cell(
            table.cell(current_row, table_col),
            _num(current[value_index]),
            bold=True,
        )

        if table_col in PREVIOUS_ABSOLUTE_COLS:
            _set_cell(
                table.cell(previous_row, table_col),
                f"(先週：{_num(previous[value_index])})",
            )
        else:
            _set_cell(
                table.cell(previous_row, table_col),
                "",
            )

        if value_index == 0:
            continue

        _set_cell(
            table.cell(current_rate_row, table_col),
            _pct(
                _funnel_rate(current, value_index),
                1,
            ),
            bold=True,
        )
        _set_cell(
            table.cell(previous_rate_row, table_col),
            _pct(
                _funnel_rate(previous, value_index),
                1,
            ),
        )

    _set_cell(
        table.cell(current_rate_row, 0),
        "移動率",
        bold=True,
    )
    _set_cell(
        table.cell(previous_rate_row, 0),
        "先週",
    )

    # Payment Service is intentionally blank in the template.
    for row in (
        current_row,
        previous_row,
        current_rate_row,
        previous_rate_row,
    ):
        _set_cell(table.cell(row, 8), "")


def _segment_cvr(
    funnel: dict[str, Any],
    period: str,
    segment: str,
) -> float | None:
    values = funnel.get(period, {}).get(segment)
    if not values or not values[0]:
        return None
    return values[-1] / values[0] * 100


def _fill_funnel_slide(
    slide,
    product: dict[str, Any],
) -> None:
    funnel = product.get("funnel")
    if not funnel:
        return

    name = product["name"]

    header = _find_text_shape(
        slide,
        lambda text, _shape: "BC Page 経路" in text,
    )
    if header is not None:
        _set_shape_text(
            header,
            f"{name} BC Page 経路",
            size=10.0,
            color=PALE,
            bold=True,
        )

    title = _find_text_shape(
        slide,
        lambda text, _shape: (
            "BCからOrderまでの購入経路" in text
        ),
    )
    if title is not None:
        _set_shape_text(
            title,
            f"{name} BCからOrderまでの購入経路",
            size=16.0,
            color=BLACK,
            bold=True,
        )

    bullets = _find_text_shape(
        slide,
        lambda text, _shape: (
            "Organic" in text
            and "Paid" in text
            and "CVR" in text
        ),
    )
    if bullets is not None:
        organic_prev = _segment_cvr(
            funnel,
            "previous",
            "organic",
        )
        organic_curr = _segment_cvr(
            funnel,
            "current",
            "organic",
        )
        paid_prev = _segment_cvr(
            funnel,
            "previous",
            "paid",
        )
        paid_curr = _segment_cvr(
            funnel,
            "current",
            "paid",
        )

        tf = bullets.text_frame
        tf.word_wrap = True
        tf.auto_size = MSO_AUTO_SIZE.NONE
        lines = (
            (
                "Organic のBC VisitからOrderまでのCVRは "
                f"先週 {_pct(organic_prev, 2)} → "
                f"今週 {_pct(organic_curr, 2)}"
            ),
            (
                "Paid のBC VisitからOrderまでのCVRは "
                f"先週 {_pct(paid_prev, 2)} → "
                f"今週 {_pct(paid_curr, 2)}"
            ),
        )
        while len(tf.paragraphs) < 2:
            tf.add_paragraph()
        for index, line in enumerate(lines):
            paragraph = tf.paragraphs[index]
            if paragraph.runs:
                run = paragraph.runs[0]
                run.text = line
                for extra in paragraph.runs[1:]:
                    extra.text = ""
            else:
                run = paragraph.add_run()
                run.text = line
            _set_font(
                run,
                size=11.0,
                color=BLACK,
                bold=False,
            )

    footer = _find_text_shape(
        slide,
        lambda text, _shape: "Data：" in text,
    )
    if footer is not None:
        _set_shape_text(
            footer,
            f"Data：{_period(product, spaced=True, omit_end_year=True)}",
            size=6.4,
            color=GREY,
        )

    table = _find_table(slide, 19, 11)
    if table is None:
        raise RuntimeError(
            "PD+BC Funnel table (19x11) が見つかりません。"
        )

    groups = (
        ("organic", 2, 3, 5, 6),
        ("other", 8, 9, 11, 12),
        ("paid", 14, 15, 17, 18),
    )
    for (
        segment,
        current_row,
        previous_row,
        current_rate_row,
        previous_rate_row,
    ) in groups:
        current = funnel.get("current", {}).get(segment)
        previous = funnel.get("previous", {}).get(segment)
        if not current or not previous:
            continue
        _fill_funnel_group(
            table,
            current_row=current_row,
            previous_row=previous_row,
            current_rate_row=current_rate_row,
            previous_rate_row=previous_rate_row,
            current=current,
            previous=previous,
        )

    _force_no_autofit(slide)


def build_pd_bc_ppt(
    products: list[dict[str, Any]],
) -> bytes:
    if not products:
        raise RuntimeError(
            "PowerPointに出力するPD+BC Productがありません。"
        )

    prs = _load_template()
    summary_source = prs.slides[0]
    funnel_source = prs.slides[1]

    output_slides: list[tuple[str, Any, dict[str, Any]]] = []

    for product in products:
        summary_slide = _duplicate_slide(
            prs,
            summary_source,
        )
        output_slides.append(
            ("summary", summary_slide, product)
        )

        if product.get("funnel"):
            funnel_slide = _duplicate_slide(
                prs,
                funnel_source,
            )
            output_slides.append(
                ("funnel", funnel_slide, product)
            )

    # Remove untouched source slides after all clones are created.
    _delete_slide(prs, 0)
    _delete_slide(prs, 0)

    for kind, slide, product in output_slides:
        if kind == "summary":
            _fill_summary_slide(slide, product)
        else:
            _fill_funnel_slide(slide, product)

    output = io.BytesIO()
    prs.save(output)
    output.seek(0)
    return output.read()
