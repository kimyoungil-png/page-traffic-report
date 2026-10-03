from __future__ import annotations

import io
import os
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_AUTO_SIZE, PP_ALIGN
from pptx.util import Pt

R_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TEMPLATE_PATH = ROOT / "templates" / "pd_bc_sample.pptx"
FONT_FACE = "Meiryo UI"

BLUE = RGBColor(30, 53, 227)
RATIO_BLUE = RGBColor(0, 49, 244)
RED = RGBColor(255, 0, 0)
BLACK = RGBColor(0, 0, 0)
GREY = RGBColor(128, 128, 128)
PALE = RGBColor(181, 181, 181)
WHITE = RGBColor(255, 255, 255)

CHANNEL_ROWS = [
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

FUNNEL_SEGMENTS = ["Organic Search", "Other", "Paid"]
FUNNEL_KEYS = [
    "bc_visit",
    "cart_add_event",
    "add_on_visit",
    "cart_page_visit",
    "checkout_login",
    "contact_info",
    "delivery",
    "payment",
    "payment_service",
    "order_confirmation",
    "order",
]


def _load_template() -> Presentation:
    path = Path(os.getenv("PD_BC_PPT_TEMPLATE_PATH", str(DEFAULT_TEMPLATE_PATH)))
    if not path.exists():
        raise RuntimeError(f"PD+BCãƒ†ãƒ³ãƒ—ãƒ¬ãƒ¼ãƒˆãŒè¦‹ã¤ã‹ã‚Šã¾ã›ã‚“: {path}")
    return Presentation(str(path))


def _remap_relationship_ids(source_slide, new_slide, cloned_element) -> None:
    rid_map: dict[str, str] = {}
    for element in cloned_element.iter():
        for attr_name in (R_NS + "embed", R_NS + "link", R_NS + "id"):
            old_rid = element.get(attr_name)
            if not old_rid or old_rid not in source_slide.part.rels:
                continue
            if old_rid not in rid_map:
                rel = source_slide.part.rels[old_rid]
                rid_map[old_rid] = new_slide.part.relate_to(rel._target, rel.reltype)
            element.set(attr_name, rid_map[old_rid])


def _duplicate_template_slide(presentation: Presentation, source_slide):
    new_slide = presentation.slides.add_slide(source_slide.slide_layout)
    for shape in list(new_slide.shapes):
        element = shape.element
        element.getparent().remove(element)
    for shape in source_slide.shapes:
        cloned = deepcopy(shape.element)
        _remap_relationship_ids(source_slide, new_slide, cloned)
        new_slide.shapes._spTree.insert_element_before(cloned, "p:extLst")
    return new_slide


def _remove_slide(presentation: Presentation, index: int) -> None:
    slide_id_list = presentation.slides._sldIdLst
    slides = list(slide_id_list)
    slide_id_list.remove(slides[index])


def _remove_shape(shape) -> None:
    shape.element.getparent().remove(shape.element)


def _clear_text_frame(shape):
    tf = shape.text_frame
    tf.clear()
    tf.word_wrap = True
    tf.auto_size = MSO_AUTO_SIZE.NONE
    return tf


def _set_font(run, size: float, color=BLACK, bold: bool = False, italic: bool = False):
    font = run.font
    font.name = FONT_FACE
    font.size = Pt(size)
    font.bold = bold
    font.italic = italic
    font.color.rgb = color


def _set_simple_text(shape, text: str, size: float, color=BLACK, bold: bool = False, italic: bool = False, align=None):
    tf = _clear_text_frame(shape)
    p = tf.paragraphs[0]
    if align is not None:
        p.alignment = align
    run = p.add_run()
    run.text = str(text or "")
    _set_font(run, size, color, bold, italic)


def _set_cell_text(cell, text: str, size: float = 8.0, color=BLACK, bold: bool = False, align=PP_ALIGN.CENTER):
    cell.text = ""
    tf = cell.text_frame
    tf.auto_size = MSO_AUTO_SIZE.NONE
    tf.margin_left = 0
    tf.margin_right = 0
    tf.margin_top = 0
    tf.margin_bottom = 0
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = str(text or "")
    _set_font(run, size, color, bold)


def _find_table(slide, rows: int, cols: int):
    for shape in slide.shapes:
        if shape.has_table and len(shape.table.rows) == rows and len(shape.table.columns) == cols:
            return shape.table
    return None


def _find_text_shape(slide, predicate):
    for shape in slide.shapes:
        if not hasattr(shape, "text"):
            continue
        text = shape.text or ""
        if predicate(text, shape):
            return shape
    return None


def _ratio(current: float, previous: float) -> str:
    if previous == 0:
        return "NEW" if current > 0 else "â€”"
    return f"x{current / previous:.2f}"


def _ratio_color(label: str):
    if not label or label in {"â€”", "NEW"}:
        return GREY
    try:
        value = float(str(label).replace("x", ""))
    except Exception:
        return RATIO_BLUE
    return RED if value < 1 else RATIO_BLUE


def _fmt_num(value) -> str:
    if value is None or value == "":
        return "â€”"
    try:
        return f"{int(round(float(value))):,}"
    except Exception:
        return str(value)


def _fmt_compact(value) -> str:
    v = float(value or 0)
    if abs(v) >= 1_000_000:
        return f"{v / 1_000_000:.1f}M"
    if abs(v) >= 1_000:
        return f"{v / 1_000:.1f}K"
    return f"{int(round(v)):,}"


def _fmt_pct(value, digits: int = 1) -> str:
    if value is None:
        return "â€”"
    return f"{float(value):.{digits}f}%"


def _bc_display_name(product: dict[str, Any]) -> str:
    name = product.get("product_name", "")
    if name.startswith("Fold") or name.startswith("Flip"):
        return "Z " + name
    return name


def _share_line(product: dict[str, Any]) -> str:
    total = float(product["main"].get("Total", {}).get("current", {}).get("bc_visit", 0) or 0)
    rows = []
    for ch in CHANNEL_ROWS:
        if ch == "Total":
            continue
        value = float(product["main"].get(ch, {}).get("current", {}).get("bc_visit", 0) or 0)
        rows.append((ch, value, value / total * 100 if total else 0))
    rows.sort(key=lambda item: item[1], reverse=True)
    return "æµå…¥å‰²åˆï¼š" + " > ".join(f"{ch} {pct:.0f}%" for ch, _, pct in rows[:3])


def _device_line(product: dict[str, Any]) -> str:
    parts = []
    for label in ("Galaxy", "iPhone", "Sony Xperia"):
        row = product.get("device_summary", {}).get(label, {})
        piv = row.get("piv_total", 0) or 0
        pir = row.get("pir")
        parts.append(f"{label} {_fmt_compact(piv)}ä»¶ (PIR {_fmt_pct(pir, 1)})")
    return "PIVç«¯æœ«åˆ¥ï¼š" + "ã€".join(parts)


def _headline(product: dict[str, Any]) -> str:
    total = product["main"].get("Total", {})
    curr_total = total.get("current", {}).get("bc_visit", 0) or 0
    prev_total = total.get("previous", {}).get("bc_visit", 0) or 0
    deltas = []
    for ch in CHANNEL_ROWS:
        if ch == "Total":
            continue
        current = product["main"].get(ch, {}).get("current", {}).get("bc_visit", 0) or 0
        previous = product["main"].get(ch, {}).get("previous", {}).get("bc_visit", 0) or 0
        deltas.append((ch, current - previous, current, previous))
    if curr_total < prev_total:
        ch, *_ = min(deltas, key=lambda x: x[1])
        return f"{ch}ã‹ã‚‰ã®æµå…¥ãŒæ¸›å°‘"
    if curr_total > prev_total:
        ch, *_ = max(deltas, key=lambda x: x[1])
        return f"{ch}ã‹ã‚‰ã®æµå…¥ãŒå¢—åŠ "
    return "æµå…¥æ§‹æˆã¯å‰Íé€²ä¸¦ã¿ã§æŽ¨ç§»"


def _funnel_cvr_line(product: dict[str, Any], segment: str, label: str) -> str:
    prev = product.get("funnel", {}).get("previous", {}).get(segment, {})
    curr = product.get("funnel", {}).get("current", {}).get(segment, {})
    prev_cvr = (prev.get("order", 0) / prev.get("bc_visit", 0) * 100) if prev.get("bc_visit") else None
    curr_cvr = (curr.get("order", 0) / curr.get("bc_visit", 0) * 100) if curr.get("bc_visit") else None
    return f"{label} ã®ãƒœãƒƒãƒˆã‚£ãƒ»è¥¿ã®å…¨æ•°ã‹é‡ã›ã†ä‰±ã®ãƒœãƒƒãƒˆã‚£ãƒ»è¥¿ã®å…¨æ•°ãŽ å…ˆé€± {_fmt_pct(prev_cvr, 2)} â†’ ä»Šé€± {_fmt_pct(curr_cvr, 2)}"


def _fill_summary_title(slide, product: dict[str, Any]) -> None:
    shape = _find_text_shape(slide, lambda text, _s: "PD Visit" in text and "BC Visit" in text)
    if shape is None:
        return
    total = product["main"].get("Total", {})
    prev = total.get("previous", {})
    curr = total.get("current", {})
    name = product.get("product_name", "")
    pd_ratio = _ratio(curr.get("pd_visit", 0), prev.get("pd_visit", 0))
    bc_ratio = _ratio(curr.get("bc_visit", 0), prev.get("bc_visit", 0))
    piv_ratio = _ratio(curr.get("piv_total", 0), prev.get("piv_total", 0))

    tf = _clear_text_frame(shape)
    p0 = tf.paragraphs[0]
    p0.space_after = Pt(0)
    runs = [
        (f"{name} PD Visit {_fmt_compact(curr.get('pd_visit', 0))} (", BLACK, 18.0),
        (pd_ratio, _ratio_color(pd_ratio), 16.0),
        (" vs å…ˆé€±) ", BLACK, 16.0),
        (f"â†’ k_headline(product)}", BLUE, 14.0),
    ]
    for txt, color, size in runs:
        r = p0.add_run()
        r.text = txt
        _set_font(r, size, color, True)

    p1 = tf.add_paragraph()
    p1.space_before = Pt(0)
    p1.space_after = Pt(0)
    runs2 = [
        (f"{name} BC Visit {_fmt_compact(curr.get('bc_visit', 0))} (", BLACK, 18.0),
        (bc_ratio, _ratio_color(bc_ratio), 16.0),
        (" vs å…ˆé€±) , BLACK, 16.0),
        (", PIV ", BLACK, 16.0),
        (f"{_fmt_compact(curr.get('piv_total', 0))}ä»¶", BLACK, 18.0),
        (" (", BLACK, 16.0),
        (piv_ratio, _ratio_color(piv_ratio), 16.0),
        (" vs å…ˆé€±)", BLACK, 16.0),
    ]
    for txt, color, size in runs2:
        r = p1.add_run()
        r.text = txt
        _set_font(r, size, color, True)


def _fill_summary_text(slide, product: dict[str, Any]) -> None:
    shape = _find_text_shape(slide, lambda text, _s: "æµå…¥å‰²åˆèˆ¥¸Ñ•áÐ¤(€€€¥˜Í¡…Á”¥Ì9½¹”è(€€€€€€€É•ÑÕÉ¸(€€€Ñ½Ñ…°€ôÁÉ½‘ÕÑl‰µ…¥¸‰t¹•Ð ‰Q½Ñ…°ˆ°íô¤(€€€ÁÉ•Ù}Á¥È€ôÑ½Ñ…°¹•Ð ‰ÁÉ•Ù¥½ÕÌˆ°íô¤¹•Ð ‰Á¥Èˆ¤(€€€ÕÉÉ}Á¥È€ôÑ½Ñ…°¹•Ð ‰ÕÉÉ•¹Ðˆ°íô¤¹•Ð ‰Á¥Èˆ¤(€€€±¥¹•Ì€ôl(€€€€€€€}Í¡…É•}±¥¹”¡ÁÉ½‘ÕÐ¤°(€€€€€€€˜‰A%K¾òk–#¦Äí}™µÑ}ÁÐ¡ÁÉ•Ù}Á¥È°€Ä¥ôƒŠH€Äƒ’î+¦Äí}™µÑ}ÁÐ¡ÕÉÉ}Á¥È°€Ä¥ôˆ°(€€€€€€€}‘•Ù¥•}±¥¹”¡ÁÉ½‘ÕÐ¤°(€€€t(€€€Ñ˜€ô}±•…É}Ñ•áÑ}™É…µ”¡Í¡…Á”¤(€€€™½È¤°±¥¹”¥¸•¹Õµ•É…Ñ”¡±¥¹•Ì¤è(€€€€€€€À€ôÑ˜¹Á…É…É…Á¡ÍlÁt¥˜¤€ôô€À•±Í”Ñ˜¹…‘‘}Á…É…É…Á  ¤(€€€€€€€È€ôÀ¹…‘‘}ÉÕ¸ ¤(€€€€€€€È¹Ñ•áÐ€ô±¥¹”(€€€€€€€}Í•Ñ}™½¹Ð¡È°€ÄÄ¸À°	1,°…±Í”¤(()‘•˜}™¥±±}ÍÕµµ…Éå}Ñ…‰±”¡Í±¥‘”°ÁÉ½‘ÕÐè‘¥ÑmÍÑÈ°¹åt¤€´ø9½¹”è(€€€Ñ…‰±”€ô}™¥¹‘}Ñ…‰±”¡Í±¥‘”°€ÄÈ°€ÄÜ¤(€€€¥˜Ñ…‰±”¥Ì9½¹”è(€€€€€€€É•ÑÕÉ¸(€€€Ñ…‰±”¹•±° À°€À¤¹Ñ•áÐ€ôÁÉ½‘ÕÐ¹•Ð ‰ÁÉ½‘ÕÑ}¹…µ”ˆ°€ˆˆ¤€¬€‰q¹A­	ˆ(€€€Ñ…‰±”¹•±° À°€à¤¹Ñ•áÐ€ô˜‰1…ÍÐ]••¬€¡íÁÉ½‘ÕÐ¹•Ð Í¡½ÉÑ}Á•É¥½‘}±…‰•°œ°€œœ¥ô¤ˆ(€€€™½ÈÉ¤° ¥¸•¹Õµ•É…Ñ”¡!991}I=]L°ÍÑ…ÉÐôÈ¤è(€€€€€€€É½Ü€ôÁÉ½‘ÕÑl‰µ…¥¸‰t¹•Ð¡ °íô¤(€€€€€€€ÁÉ•Ø€ôÉ½Ü¹•Ð ‰ÁÉ•Ù¥½ÕÌˆ°íô¤(€€€€€€€ÕÉÈ€ôÉ½Ü¹•Ð ‰ÕÉÉ•¹Ðˆ°íô¤(€€€€€€€Ù…±Õ•Ì€ôl(€€€€€€€€€€€ °(€€€€€€€€€€€}™µÑ}¹Õ´¡ÁÉ•Ø¹•Ð ‰Á‘}Ù¥Í¥Ðˆ¤¤°(€€€€€€€€€€€}™µÑ}¹Õ´¡ÁÉ•Ø¹•Ð ‰Á‘}Ñ½}‰Œˆ¤¤°(€€€€€€€€€€€}™µÑ}¹Õ´¡ÁÉ•Ø¹•Ð ‰‰}Ù¥Í¥Ðˆ¤¤°(€€€€€€€€€€€}™µÑ}¹Õ´¡ÁÉ•Ø¹•Ð ‰…ÉÉ¥•É}Á¥Øˆ¤¤°(€€€€€€€€€€€}™µÑ}¹Õ´¡ÁÉ•Ø¹•Ð ‰•ÍÑ½É•}Á¥Øˆ¤¤°(€€€€€€€€€€€}™µÑ}ÁÐ¡ÁÉ•Ø¹•Ð ‰Á¥Èˆ¤°€Ä¤°(€€€€€€€€€€€}™µÑ}¹Õ´¡ÁÉ•Ø¹•Ð ‰½É‘•Èˆ¤¤°(€€€€€€€€€€€}™µÑ}¹Õ´¡ÕÉÈ¹•Ð ‰Á‘}Ù¥Í¥Ðˆ¤¤°(€€€€€€€€€€€}É…Ñ¥¼¡ÕÉÈ¹•Ð ‰Á‘}Ù¥Í¥Ðˆ°€À¤°ÁÉ•Ø¹•Ð ‰Á‘}Ù¥Í¥Ðˆ°€À¤¤°(€€€€€€€€€€€}™µÑ}¹Õ´¡ÕÉÈ¹•Ð ‰Á‘}Ñ½}‰Œˆ¤¤°(€€€€€€€€€€€}™µÑ}¹Õ´¡ÕÉÈ¹•Ð ‰‰}Ù¥Í¥Ðˆ¤¤°(€€€€€€€€€€€}É…Ñ¥¼¡ÕÉÈ¹•Ð ‰‰}Ù¥Í¥Ðˆ°€À¤°ÁÉ•Ø¹•Ð ‰‰}Ù¥Í¥Ðˆ°€À¤¤°(€€€€€€€€€€€}™µÑ}¹Õ´¡ÕÉÈ¹•Ð ‰…ÉÉ¥•É}Á¥Øˆ¤¤°(€€€€€€€€€€€}™µÑ}¹Õ´¡ÕÉÈ¹•Ð ‰•ÍÑ½É•}Á¥Øˆ¤¤°(€€€€€€€€€€€}™µÑ}ÁÐ¡ÕÉÈ¹•Ð ‰Á¥Èˆ¤°€Ä¤°(€€€€€€€€€€€}™µÑ}¹Õ´¡ÕÉÈ¹•Ð ‰½É‘•Èˆ¤¤°(€€€€€€€t(€€€€€€€™½È¤°Ù…±Õ”¥¸•¹Õµ•É…Ñ”¡Ù…±Õ•Ì¤è(€€€€€€€€€€€½±½È€ô	1,(€€€€€€€€€€€‰½±€ô €ôô€‰Q½Ñ…°ˆ(€€€€€€€€€€€Í¥é”€ô€Ü¸À¥˜¤€ôô€À•±Í”€Ü¸Ô(€€€€€€€€€€€¥˜¤¥¸€ Ä°€È°€Ì°€Ð°€Ô°€Ø°€Ü¤è(€€€€€€€€€€€€€€€½±½È€ôId(€€€€€€€€€€€¥˜¤¥¸€ ä°€ÄÈ¤è(€€€€€€€€€€€€€€€½±½È€ô}É…Ñ¥½}½±½È¡ÍÑÈ¡Ù…±Õ”¤¤(€€€€€€€€€€€}Í•Ñ}•±±}Ñ•áÐ¡Ñ…‰±”¹•±°¡É¤°¤¤°Ù…±Õ”°Í¥é”õÍ¥é”°½±½Èõ½±½È°‰½±õ‰½±¤(()‘•˜}™¥±±}…ÉÉ¥•É}‰½à¡Í¡…Á”°‘•Ñ…¥°è‘¥ÑmÍÑÈ°¥¹Ñt¤€´ø9½¹”è(€€€Ñ•áÐ€ô€ (€€€€€€€˜‰‘½½µ¼í‘•Ñ…¥°¹•Ð ‘½½µ¼œ°€À¤è±õq¸ˆ(€€€€€€€˜‰…Ôí‘•Ñ…¥°¹•Ð …Ôœ°€À¤è±õq¸ˆ(€€€€€€€˜‰M½™Ñ	…¹¬í‘•Ñ…¥°¹•Ð Í½™Ñ‰…¹¬œ°€À¤è±õq¸ˆ(€€€€€€€˜‰I…­ÕÑ•¸í‘•Ñ…¥°¹•Ð É…­ÕÑ•¸œ°€À¤è±ôˆ(€€€€¤(€€€}Í•Ñ}Í¥µÁ±•}Ñ•áÐ¡Í¡…Á”°Ñ•áÐ°€à¸À°	1,°QÉÕ”°…±¥¸õAA}1%8¹9QH¤(()‘•˜}™¥±±}ÍÕµµ…Éå}…±±½ÕÑÌ¡Í±¥‘”°ÁÉ½‘ÕÐè‘¥ÑmÍÑÈ°¹åt¤€´ø9½¹”è(€€€‘•Ñ…¥±Ì€ôÁÉ½‘ÕÐ¹•Ð ‰Á¥Ù}‘•Ñ…¥°ˆ°íô¤(€€€‰½á•Ì€ômÍ¡…Á”™½ÈÍ¡…Á”¥¸Í±¥‘”¹Í¡…Á•Ì¥˜¡…Í…ÑÑÈ¡Í¡…Á”°€‰Ñ•áÐˆ¤…¹€‰‘½½µ¼ˆ¥¸€¡Í¡…Á”¹Ñ•áÐ½È€ˆˆ¥t(€€€‰½á•Ì¹Í½ÉÐ¡­•äõ±…µ‰‘„Í¡…Á”èÍ¡…Á”¹±•™Ð¤(€€€¥˜±•¸¡‰½á•Ì¤€øô€Äè(€€€€€€€}™¥±±}…ÉÉ¥•É}‰½à¡‰½á•ÍlÁt°‘•Ñ…¥±Ì¹•Ð ˆÈÝ••­Ì…¼ˆ¤½Èíô¤(€€€¥˜±•¸¡‰½á•Ì¤€øô€Èè(€€€€€€€}™¥±±}…ÉÉ¥•É}‰½à¡‰½á•ÍlÅt°‘•Ñ…¥±Ì¹•Ð ‰1…ÍÐ]••¬ˆ¤½Èíô¤(()‘•˜}™¥±±}ÍÉ••¹Í¡½Ð¡Í±¥‘”°ÁÉ½‘ÕÐè‘¥ÑmÍÑÈ°¹åt¤€´ø9½¹”è(€€€Ñ…É•Ð€ô9½¹”(€€€™½ÈÍ¡…Á”¥¸Í±¥‘”¹Í¡…Á•Ìè(€€€€€€€¥˜Í¡…Á”¹Í¡…Á•}ÑåÁ”€ôô€ÄÌ…¹Í¡…Á”¹±•™Ð€ð€ÌÀÀÀÀÀÀ…¹Í¡…Á”¹Ñ½À€ø€ÄàÀÀÀÀÀè(€€€€€€€€€€€Ñ…É•Ð€ôÍ¡…Á”(€€€€€€€€€€€‰É•…¬(€€€¥˜Ñ…É•Ð¥Ì9½¹”è(€€€€€€€É•ÑÕÉ¸(€€€±•™Ð°Ñ½À°Ý¥‘Ñ °¡•¥¡Ð€ôÑ…É•Ð¹±•™Ð°Ñ…É•Ð¹Ñ½À°Ñ…É•Ð¹Ý¥‘Ñ °Ñ…É•Ð¹¡•¥¡Ð(€€€}É•µ½Ù•}Í¡…Á”¡Ñ…É•Ð¤(€€€ÍÉ••¹Í¡½Ð€ôÁÉ½‘ÕÐ¹•Ð ‰ÍÉ••¹Í¡½Ñ}‰åÑ•Ìˆ¤(€€€¥˜¹½ÐÍÉ••¹Í¡½Ðè(€€€€€€€É•ÑÕÉ¸(€€€Ý¥Ñ Ñ•µÁ™¥±”¹9…µ•‘Q•µÁ½É…Éå¥±”¡ÍÕ™™¥àôˆ¹Á¹œˆ°‘•±•Ñ”õ…±Í”¤…Ì˜è(€€€€€€€˜¹ÝÉ¥Ñ”¡ÍÉ••¹Í¡½Ð¤(€€€€€€€¥µ…•}Á…Ñ €ô˜¹¹…µ”(€€€ÑÉäè(€€€€€€€Í±¥‘”¹Í¡…Á•Ì¹…‘‘}Á¥ÑÕÉ”¡¥µ…•}Á…Ñ °±•™Ð°Ñ½À°Ý¥‘Ñ õÝ¥‘Ñ °¡•¥¡Ðõ¡•¥¡Ð¤(€€€™¥¹…±±äè(€€€€€€€ÑÉäè(€€€€€€€€€€€½Ì¹É•µ½Ù”¡¥µ…•}Á…Ñ ¤(€€€€€€€•á•ÁÐ¥±•9½Ñ½Õ¹‘ÉÉ½Èè(€€€€€€€€€€€Á…ÍÌ(()‘•˜}™¥±±}ÍÕµµ…Éå}Í±¥‘”¡Í±¥‘”°ÁÉ½‘ÕÐè‘¥ÑmÍÑÈ°¹åt¤€´ø9½¹”è(€€€‰É•…‘ÉÕµˆ€ô}™¥¹‘}Ñ•áÑ}Í¡…Á”¡Í±¥‘”°±…µ‰‘„Ñ•áÐ°}Ìè€‰A­	A…”ˆ¥¸Ñ•áÐ…¹€‰Y¥Í¥Ðˆ¹½Ð¥¸Ñ•áÐ¤(€€€¥˜‰É•…‘ÉÕµˆ¥Ì¹½Ð9½¹”è(€€€€€€€}Í•Ñ}Í¥µÁ±•}Ñ•áÐ¡‰É•…‘ÉÕµˆ°˜‰íÁÉ½‘ÕÐ¹•Ð ÁÉ½‘ÕÑ}¹…µ”œ°€œœ¥ôA­	A…”ˆ°€ÄÀ¸À°A1°QÉÕ”¤(€€€}™¥±±}ÍÕµµ…Éå}Ñ¥Ñ±”¡Í±¥‘”°ÁÉ½‘ÕÐ¤(€€€}™¥±±}ÍÕµµ…Éå}Ñ•áÐ¡Í±¥‘”°ÁÉ½‘ÕÐ¤(€€€}™¥±±}ÍÕµµ…Éå}Ñ…‰±”¡Í±¥‘”°ÁÉ½‘ÕÐ¤(€€€}™¥±±}ÍÕµµ…Éå}…±±½ÕÑÌ¡Í±¥‘”°ÁÉ½‘ÕÐ¤(€€€}™¥±±}ÍÉ••¹Í¡½Ð¡Í±¥‘”°ÁÉ½‘ÕÐ¤(€€€™½½Ñ•È€ô}™¥¹‘}Ñ•áÑ}Í¡…Á”¡Í±¥‘”°±…µ‰‘„Ñ•áÐ°}Ìè€‰…Ñ‡¾òhˆ¥¸Ñ•áÐ…¹€‰Í…µÍÕ¹œˆ¥¸Ñ•áÐ¤(€€€¥˜™½½Ñ•È¥Ì¹½Ð9½¹”è(€€€€€€€‰Õå}ÕÉ°€ôÁÉ½‘ÕÐ¹•Ð ‰ÕÉ°ˆ°€ˆˆ¤¹ÉÍÑÉ¥À ˆ¼ˆ¤€¬€ˆ½‰Õä¼ˆ(€€€€€€€}Í•Ñ}Í¥µÁ±•}Ñ•áÐ¡™½½Ñ•È°˜‰…Ñ‡¾òiíÁÉ½‘ÕÐ¹•Ð Á•É¥½‘}±…‰•°œ°€œœ¥õq¹íÁÉ½‘ÕÐ¹•Ð ÕÉ°œ°€œœ¥õã€m‰Õå}ÕÉ±ôˆ°€Ø¸Ð°Idœ¤(()‘•˜}™Õ¹¹•±}É…Ñ”¡É½Üè‘¥ÑmÍÑÈ°¥¹Ñt°­•äèÍÑÈ¤€´ø™±½…Ðð9½¹”è(€€€‰Œ€ôÉ½Ü¹•Ð ‰‰}Ù¥Í¥Ðˆ°€À¤½È€À(€€€É•ÑÕÉ¸É½Ü¹•Ð¡­•ä°€À¤€¼‰Œ€¨€ÄÀÀ¥˜‰Œ•±Í”9½¹”(()‘•˜}™¥±±}™Õ¹¹•±}Ñ…‰±”¡Í±¥‘”°ÁÉ½‘ÕÐè‘¥ÑmÍÑÈ°¹åt¤€´ø9½¹”è(€€€Ñ…‰±”€ô}™¥¹‘}Ñ…‰±”¡Í±¥‘”°€Ää°€ÄÄ¤(€€€¥˜Ñ…‰±”¥Ì9½¹”è(€€€€€€€É•ÑÕÉ¸(€€€ÕÉÉ•¹Ð€ôÁÉ½‘ÕÐ¹•Ð ‰™Õ¹¹•°ˆ°íô¤¹•Ð ‰ÕÉÉ•¹Ðˆ°íô¤(€€€ÁÉ•Ù¥½ÕÌ€ôÁÉ½‘ÕÐ¹•Ð ‰™Õ¹¹•°ˆ°íô¤¹•Ð ‰ÁÉ•Ù¥½ÕÌˆ°íô¤(€€€É½Ý}ÍÑ…ÉÑÌ€ôì‰=É…¹¥ŒM•…É ˆè€È°€‰=Ñ¡•Èˆè€à°€‰A…¥ˆè€ÄÑô(€€€­•åÍ}™½É}½±Ì€ôl(€€€€€€€€‰‰}Ù¥Í¥Ðˆ°(€€€€€€€€‰…ÉÑ}…‘‘}•Ù•¹Ðˆ°(€€€€€€€€‰…‘‘}½¹}Ù¥Í¥Ðˆ°(€€€€€€€€‰…ÉÑ}Á…•}Ù¥Í¥Ðˆ°(€€€€€€€€‰¡•­½ÕÑ}±½¥¸ˆ°(€€€€€€€€‰½¹Ñ…Ñ}¥¹™¼ˆ°(€€€€€€€€‰‘•±¥Ù•Éäˆ°(€€€€€€€€‰Á…åµ•¹Ðˆ°(€€€€€€€€‰Á…åµ•¹Ñ}Í•ÉÙ¥”ˆ°(€€€€€€€€‰½É‘•É}½¹™¥Éµ…Ñ¥½¸ˆ°(€€€€€€€€‰½É‘•Èˆ°(€€€t(€€€™½ÈÍ•µ•¹Ð°ÍÑ…ÉÑ}É½Ü¥¸É½Ý}ÍÑ…ÉÑÌ¹¥Ñ•µÌ ¤è(€€€€€€€ÕÉÈ€ôÕÉÉ•¹Ð¹•Ð¡Í•µ•¹Ð°íô¤(€€€€€€€ÁÉ•Ø€ôÁÉ•Ù¥½ÕÌ¹•Ð¡Í•µ•¹Ð°íô¤(€€€€€€€™½È¤°­•ä¥¸•¹Õµ•É…Ñ”¡­•åÍ}™½É}½±Ì¤è(€€€€€€€€€€€¥˜­•ä€ôô€‰Á…åµ•¹Ñ}Í•ÉÙ¥”ˆè(€€€€€€€€€€€€€€€½¹Ñ¥¹Õ”(€€€€€€€€€€€Ù…±Õ”€ôÕÉÈ¹•Ð¡­•ä°€À¤(€€€€€€€€€€€ÁÉ•Ù}Ù…±Õ”€ôÁÉ•Ø¹•Ð¡­•ä°€À¤(€€€€€€€€€€€}Í•Ñ}•±±}Ñ•áÐ¡Ñ…‰±”¹•±°¡ÍÑ…ÉÑ}É½Ü°¤¤°}™µÑ}¹Õ´¡Ù…±Õ”¤¥˜Ù…±Õ”•±Í”€ˆˆ°Í¥é”ôÄÌ¸À°½±½ÈõIQ%=}	1U¥˜Í•µ•¹Ð€ôô€‰A…¥ˆ•±Í”€¡Id¥˜Í•µ•¹Ð€ôô€‰=Ñ¡•Èˆ•±Í”I	½±½È ÄÈÀ°€ÄÐÔ°€ÄÜØ¤¤°‰½±õQÉÕ”¤(€€€€€€€€€€€ÁÉ•Ù}Ñ•áÐ€ô˜ˆ£–#¦Ç¾òií}™µÑ}¹Õ´¡ÁÉ•Ù}Ù…±Õ”¥ô¤ˆ¥˜ÁÉ•Ù}Ù…±Õ”…¹­•ä¥¸ì‰‰}Ù¥Í¥Ðˆ°€‰…ÉÑ}…‘‘}•Ù•¹Ðˆ°€‰…ÉÑ}Á…•}Ù¥Í¥Ðˆ°€‰½É‘•È‰ô•±Í”€ˆˆ(€€€€€€€€€€€}Í•Ñ}•±±}Ñ•áÐ¡Ñ…‰±”¹•±°¡ÍÑ…ÉÑ}É½Ü€¬€Ä°¤¤°ÁÉ•Ù}Ñ•áÐ°Í¥é”ôØ¸À°½±½ÈõId°‰½±õQÉÕ”¤(€€€€€€€€€€€ÕÉÉ}É…Ñ”€ô}™Õ¹¹•±}É…Ñ”¡ÕÉÈ°­•ä¤(€€€€€€€€€€€ÁÉ•Ù}É…Ñ”€ô}™Õ¹¹•±}É…Ñ”¡ÁÉ•Ø°­•ä¤(€€€€€€€€€€€É…Ñ•}Ñ•áÐ€ô€‹žžï–.Wž:ˆ¥˜¤€ôô€À•±Í”}™µÑ}ÁÐ¡ÕÉÉ}É…Ñ”°€Ä¤(€€€€€€€€€€€ÁÉ•Ù}É…Ñ•}Ñ•áÐ€ô€‹–#¦Äˆ¥˜¤€ôô€À•±Í”}™µÑ}ÁÐ¡ÁÉ•Ù}É…Ñ”°€Ä¤(€€€€€€€€€€€}Í•Ñ}•±±}Ñ•áÐ¡Ñ…‰±”¹•±°¡ÍÑ…ÉÑ}É½Ü€¬€Ì°¤¤°É…Ñ•}Ñ•áÐ°Í¥é”ôØ¸Ô°½±½ÈõIQ%=}	1U¥˜Í•µ•¹Ð€ôô€‰A…¥ˆ•±Í”Id°‰½±õQÉÕ”¤(€€€€€€€€€€€}Í•Ñ}•±±}Ñ•áÐ¡Ñ…‰±”¹•±°¡ÍÑ…ÉÑ}É½Ü€¬€Ð°¤¤°ÁÉ•Ù}É…Ñ•}Ñ•áÐ°Í¥é”ôØ¸Ô°½±½ÈõIQ%=}	1U¥˜Í•µ•¹Ð€ôô€‰A…¥ˆ•±Í”Id°‰½±õQÉÕ”¤(()‘•˜}™¥±±}™Õ¹¹•±}Í±¥‘”¡Í±¥‘”°ÁÉ½‘ÕÐè‘¥ÑmÍÑÈ°¹åt¤€´ø9½¹”è(€€€ÁÉ½‘ÕÑ}¹…µ”€ô}‰}‘¥ÍÁ±…å}¹…µ”¡ÁÉ½‘ÕÐ¤(€€€‰É•…‘ÉÕµˆ€ô}™¥¹‘}Ñ•áÑ}Í¡…Á”¡Í±¥‘”°±…µ‰‘„Ñ•áÐ°}Ìè€‰	A…”ƒžÖ3¢Þ¼ˆ¥¸Ñ•áÐ¤(€€€¥˜‰É•…‘ÉÕµˆ¥Ì¹½Ð9½¹”è(€€€€€€€}Í•Ñ}Í¥µÁ±•}Ñ•áÐ¡‰É•…‘ÉÕµˆ°˜‰íÁÉ½‘ÕÑ}¹…µ•ô	A…”ƒžÖ3¢Þ¼ˆ°€ÄÀ¸À°A1°QÉÕ”¤(€€€Ñ¥Ñ±”€ô}™¥¹‘}Ñ•áÑ}Í¡…Á”¡Í±¥‘”°±…µ‰‘„Ñ•áÐ°}Ìè€‹¢Îó–—žÖ3¢Þ¼ˆ¥¸Ñ•áÐ¤(€€€¥˜Ñ¥Ñ±”¥Ì¹½Ð9½¹”è(€€€€€€€}Í•Ñ}Í¥µÁ±•}Ñ•áÐ¡Ñ¥Ñ±”°˜‰íÁÉ½‘ÕÑ}¹…µ•ô	Ž/Ž
%=É‘•ËŽûŽŸŽ»¢Îó–—žÖ3¢Þ¼ˆ°€Äà¸À°	1,°QÉÕ”¤(€€€‰Õ±±•ÑÌ€ô}™¥¹‘}Ñ•áÑ}Í¡…Á”¡Í±¥‘”°±…µ‰‘„Ñ•áÐ°}Ìè€‰YHˆ¥¸Ñ•áÐ¤(€€€¥˜‰Õ±±•ÑÌ¥Ì¹½Ð9½¹”è(€€€€€€€Ñ˜€ô}±•…É}Ñ•áÑ}™É…µ”¡‰Õ±±•ÑÌ¤(€€€€€€€™½È¤°±¥¹”¥¸•¹Õµ•É…Ñ”¡l(€€€€€€€€€€€}™Õ¹¹•±}ÙÉ}±¥¹”¡ÁÉ½‘ÕÐ°€‰=É…¹¥ŒM•…É ˆ°€‰=É…¹¥Œˆ¤°(€€€€€€€€€€€}™Õ¹¹•±}ÙÉ}±¥¹”¡ÁÉ½‘ÕÐ°€‰A…¥ˆ°€‰A…¥ˆ¤°(€€€€€€€t¤è(€€€€€€€€€€€À€ôÑ˜¹Á…É…É…Á¡ÍlÁt¥˜¤€ôô€À•±Í”Ñ˜¹…‘‘}Á…É…É…Á  ¤(€€€€€€€€€€€È€ôÀ¹…‘‘}ÉÕ¸ ¤(€€€€€€€€€€€È¹Ñ•áÐ€ô±¥¹”(€€€€€€€€€€€}Í•Ñ}™½¹Ð¡È°€ÄÄ¸À°	1,¤(€€€™½½Ñ•È€ô}™¥¹‘}Ñ•áÑ}Í¡…Á”¡Í±¥‘”°±…µ‰‘„Ñ•áÐ°}Ìè€‰…Ñ‡¾òhˆ¥¸Ñ•áÐ¤(€€€¥˜™½½Ñ•È¥Ì¹½Ð9½¹”è(€€€€€€€}Í•Ñ}Í¥µÁ±•}Ñ•áÐ¡™½½Ñ•È°˜‰…Ñ‡¾òiíÁÉ½‘ÕÐ¹•Ð ‘…Ñ•}ÍÑ…ÉÐœ°œœ¥lÀèÑuô½í¥¹Ð¡ÁÉ½‘ÕÐ¹•Ð ‘…Ñ•}ÍÑ…ÉÐœ°œÄäÜÀ´Ä´Äœ¤¹ÍÁ±¥Ð œ´œ¥lÅt¥ô½í¥¹Ð¡ÁÉ½‘ÕÐ¹•Ð ‘…Ñ•}ÍÑ…ÉÐœ°œÄäÜÀ´Ä´Äœ¤¹ÍÁ±¥Ð œ´œ¥lÉt¥ôøí¥¹Ð¡ÁÉ½‘ÕÐ¹•Ð ‘…Ñ•}•¹œ°œÄäÜÀ´Ä´Äœ¤¹ÍÁ±¥Ð œ´œ¥lÅt¥ô½í¥¹Ð¡ÁÉ½‘ÕÐ¹•Ð ‘…Ñ•}•¹œ°œÄäÜÀ´Ä´Äœ¤¹ÍÁ±¥Ð œ´œ¥lÉt¥ôˆ°€Ø¸Ð°Id¤(€€€}™¥±±}™Õ¹¹•±}Ñ…‰±”¡Í±¥‘”°ÁÉ½‘ÕÐ¤(()‘•˜}¡…Í}™Õ¹¹•°¡ÁÉ½‘ÕÐè‘¥ÑmÍÑÈ°¹åt¤€´ø‰½½°è(€€€É•ÑÕÉ¸‰½½°¡ÁÉ½‘ÕÐ¹•Ð ‰™Õ¹¹•°ˆ°íô¤¹•Ð ‰ÕÉÉ•¹Ðˆ¤¤(()‘•˜‰Õ¥±‘}Á‘}‰}É•Á½ÉÐ¡ÁÉ½‘ÕÑÌè±¥ÍÑm‘¥ÑmÍÑÈ°¹åut¤€´ø‰åÑ•Ìè(€€€¥˜¹½ÐÁÉ½‘ÕÑÌè(€€€€€€€É…¥Í”IÕ¹Ñ¥µ•ÉÉ½È¡ˆ‰A­	Ž³ŽwŽóŽ#Ž¯–ë–*oŽgŽ
/ŽŽóŽ
ÿŽ3ŽŽ
+ŽûŽoŽ
OŽˆ¤(€€€ÁÉ•Í•¹Ñ…Ñ¥½¸€ô}±½…‘}Ñ•µÁ±…Ñ” ¤(€€€ÍÕµµ…Éå}Ñ•µÁ±…Ñ”€ôÁÉ•Í•¹Ñ…Ñ¥½¸¹Í±¥‘•ÍlÁt(€€€™Õ¹¹•±}Ñ•µÁ±…Ñ”€ôÁÉ•Í•¹Ñ…Ñ¥½¸¹Í±¥‘•ÍlÅt((€€€½ÕÑÁÕÑ}Í±¥‘•Ì€ômt(€€€™½È¥‘à°ÁÉ½‘ÕÐ¥¸•¹Õµ•É…Ñ”¡ÁÉ½‘ÕÑÌ¤è(€€€€€€€¥˜¥‘à€ôô€Àè(€€€€€€€€€€€ÍÕµµ…Éå}Í±¥‘”€ôÁÉ•Í•¹Ñ…Ñ¥½¸¹Í±¥‘•ÍlÁt(€€€€€€€•±Í”è(€€€€€€€€€€€ÍÕµµ…Éå}Í±¥‘”€ô}‘ÕÁ±¥…Ñ•}Ñ•µÁ±…Ñ•}Í±¥‘”¡ÁÉ•Í•¹Ñ…Ñ¥½¸°ÍÕµµ…Éå}Ñ•µÁ±…Ñ”¤(€€€€€€€½ÕÑÁÕÑ}Í±¥‘•Ì¹…ÁÁ•¹¡ÍÕµµ…Éå}Í±¥‘”¤(€€€€€€€}™¥±±}ÍÕµµ…Éå}Í±¥‘”¡ÍÕµµ…Éå}Í±¥‘”°ÁÉ½‘ÕÐ¤(€€€€€€€¥˜}¡…Í}™Õ¹¹•°¡ÁÉ½‘ÕÐ¤è(€€€€€€€€€€€¥˜¥‘à€ôô€Àè(€€€€€€€€€€€€€€€™Õ¹¹•±}Í±¥‘”€ôÁÉ•Í•¹Ñ…Ñ¥½¸¹Í±¥‘•ÍlÅt(€€€€€€€€€€€•±Í”è(€€€€€€€€€€€€€€€™Õ¹¹•±}Í±¥‘”€ô}‘ÕÁ±¥…Ñ•}Ñ•µÁ±…Ñ•}Í±¥‘”¡ÁÉ•Í•¹Ñ…Ñ¥½¸°™Õ¹¹•±}Ñ•µÁ±…Ñ”¤(€€€€€€€€€€€½ÕÑÁÕÑ}Í±¥‘•Ì¹…ÁÁ•¹¡™Õ¹¹•±}Í±¥‘”¤(€€€€€€€€€€€}™¥±±}™Õ¹¹•±}Í±¥‘”¡™Õ¹¹•±}Í±¥‘”°ÁÉ½‘ÕÐ¤((€€€€Œ%˜Ñ¡”™¥ÉÍÐÁÉ½‘ÕÐ‘¥¹½Ð¡…Ù”„™Õ¹¹•°°É•µ½Ù”½É¥¥¹…°Í±¥‘”€È¸(€€€¥˜¹½Ð}¡…Í}™Õ¹¹•°¡ÁÉ½‘ÕÑÍlÁt¤…¹±•¸¡ÁÉ•Í•¹Ñ…Ñ¥½¸¹Í±¥‘•Ì¤€ø€Äè(€€€€€€€}É•µ½Ù•}Í±¥‘”¡ÁÉ•Í•¹Ñ…Ñ¥½¸°€Ä¤((€€€½ÕÑÁÕÐ€ô¥¼¹	åÑ•Í%< ¤(€€€ÁÉ•Í•¹Ñ…Ñ¥½¸¹Í…Ù”¡½ÕÑÁÕÐ¤(€€€½ÕÑÁÕÐ¹Í••¬ À¤(€€€É•ÑÕÉ¸½ÕÑÁÕÐ¹É•… ¤(