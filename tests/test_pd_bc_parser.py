from reports.pd_bc.analyzer import _fallback_headline
from reports.pd_bc.parser import (
    FUNNEL_ROWS,
    _parse_piv_detail,
    _period_map_from_table,
    _summarize_devices,
)


def test_other_segment_uses_corrected_name():
    assert FUNNEL_ROWS["B Other [2~6]"] == "Other"


def test_old_other_segment_name_remains_backward_compatible():
    assert FUNNEL_ROWS["B Order [2~6]"] == "Other"


def test_three_periods_are_mapped_by_chronological_order():
    rows = [
        [
            "",
            "3 weeks ago",
            "3 weeks ago",
            "2 weeks ago",
            "2 weeks ago",
            "Last Week",
            "Last Week",
        ]
    ]
    assert _period_map_from_table(rows) == {
        "3 weeks ago": "older",
        "2 weeks ago": "previous",
        "Last Week": "current",
    }


def test_piv_detail_parses_daily_rows_and_jcom():
    rows = [
        [
            "",
            "",
            "Visits",
            "PIV [Carrier]",
            "PIV (dcm carrier)",
            "PIV (jcom carrier)-",
            "PIV [eStore]",
        ],
        [
            "2 weeks ago",
            "",
            "100",
            "20",
            "20",
            "0",
            "30",
        ],
        [
            "Last Week",
            "",
            "120",
            "25",
            "20",
            "5",
            "35",
        ],
        [
            "Last Week",
            "2026-09-27",
            "20",
            "5",
            "3",
            "2",
            "6",
        ],
    ]
    result = _parse_piv_detail(
        rows,
        {
            "2 weeks ago": "previous",
            "Last Week": "current",
        },
    )
    assert result["summary"]["current"]["carriers"]["jcom"] == 5
    assert result["daily"]["current"][0]["date"] == "2026-09-27"
    assert result["daily"]["current"][0]["carriers"]["jcom"] == 2


def test_device_ranking_is_dynamic_and_can_prioritize_pc():
    devices = {
        "Galaxy S": {
            "current": {
                "visits": 100,
                "carrier_piv": 10,
                "estore_piv": 10,
                "piv_total": 20,
                "order": 0,
            }
        },
        "PC": {
            "current": {
                "visits": 100,
                "carrier_piv": 30,
                "estore_piv": 20,
                "piv_total": 50,
                "order": 0,
            }
        },
        "Google Pixel": {
            "current": {
                "visits": 100,
                "carrier_piv": 20,
                "estore_piv": 10,
                "piv_total": 30,
                "order": 0,
            }
        },
    }
    _summary, ranking = _summarize_devices(devices)
    assert [row["name"] for row in ranking[:3]] == [
        "PC",
        "Google Pixel",
        "Galaxy",
    ]


def test_fallback_headline_can_use_three_week_level():
    product = {
        "main": {
            "Total": {
                "older": {"pd_visit": 100},
                "previous": {"pd_visit": 140},
                "current": {"pd_visit": 105},
            }
        }
    }
    assert _fallback_headline(product) == "PD Visitは前週比減も先々週水準"
