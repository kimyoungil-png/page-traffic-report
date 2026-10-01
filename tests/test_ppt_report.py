from __future__ import annotations

import io

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.enum.text import MSO_AUTO_SIZE

from ppt_report import build_ppt_report


def _page(url: str, breadcrumb: str, report_path: str):
    channels = [
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
    rows = []
    for i, channel in enumerate(channels):
        is_total = channel == "Total"
        rows.append(
            {
                "channel": channel,
                "previous_entry": 1000 if is_total else 100 + i,
                "previous_cta": 10 if is_total else i,
                "previous_bounce": 20.0,
                "current_entry": 1200 if is_total else 120 + i,
                "ratio": "x1.20",
                "current_cta": 12 if is_total else i,
                "current_ctr": 1.0,
                "current_bounce": 18.0,
            }
        )

    return {
        "url": url,
        "meta_title": "Sample Samsung Page",
        "report_path": report_path,
        "breadcrumb": breadcrumb,
        "period_label": "2026/9/21~2026/9/27",
        "gsc_period_label": "2026/9/19~2026/9/25",
        "total_current_compact": "1.2K",
        "total_ratio_label": "x1.20",
        "headline_comment": "Entry Visitは前週比で増加",
        "share_line": "流入割合：Organic Search 96% > Direct 3% > Referral 1%",
        "secondary_line": "Entry→PF・PD・BC 12 Visit、CTR 1.0%",
        "table_rows": rows,
        "gsc_queries": [
            {"query": "sample query", "clicks": 9},
            {"query": "sample query 2", "clicks": 4},
        ],
        "screenshot_bytes": None,
    }


def test_build_multi_slide_report_preserves_template_relationships_and_no_autofit():
    pages = [
        _page(
            "https://www.samsung.com/jp/support/mobile-devices/example/",
            "support > example",
            "/support/mobile-devices/example",
        ),
        _page(
            "https://www.samsung.com/jp/explore/guide/example/",
            "guide > example",
            "/explore/guide/example",
        ),
    ]

    output = build_ppt_report(pages)
    prs = Presentation(io.BytesIO(output))
    assert len(prs.slides) == 2

    for slide in prs.slides:
        pictures = [shape for shape in slide.shapes if shape.shape_type == MSO_SHAPE_TYPE.PICTURE]
        assert pictures, "GSC header icon/picture relationship should survive slide duplication"

        for shape in slide.shapes:
            if getattr(shape, "has_text_frame", False):
                assert shape.text_frame.auto_size == MSO_AUTO_SIZE.NONE

        summary = next(shape for shape in slide.shapes if "流入割合：" in getattr(shape, "text", ""))
        assert "Entry→PF・PD・BC 12 Visit、CTR 1.0%" in summary.text

        footer = next(shape for shape in slide.shapes if "Data：" in getattr(shape, "text", ""))
        assert "Data：2026/9/21~2026/9/27" in footer.text

        gsc_period = next(
            shape for shape in slide.shapes
            if "GSC: 2026/9/19~2026/9/25" in getattr(shape, "text", "")
        )
        assert "GSC: 2026/9/19~2026/9/25" in gsc_period.text

        gsc_table = next(
            shape.table
            for shape in slide.shapes
            if shape.has_table and len(shape.table.rows) == 12 and len(shape.table.columns) == 3
        )
        assert gsc_table.cell(2, 1).text == "sample query"
        assert gsc_table.cell(2, 2).text == "9"
