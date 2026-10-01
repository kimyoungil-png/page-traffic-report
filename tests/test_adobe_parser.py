from datetime import date
from pathlib import Path

from adobe_parser import _parse_matrix, parse_adobe_csv
from url_utils import breadcrumb_label, normalize_adobe_url


def test_normalize_adobe_url():
    assert normalize_adobe_url('www.samsung.com/jp/explore/hint/test') == 'https://www.samsung.com/jp/explore/hint/test/'


def test_breadcrumb_rules():
    assert breadcrumb_label('https://www.samsung.com/jp/support/mobile-devices/galaxy-device-lock-screen-features/') == 'support > galaxy-device-lock-screen-features'
    assert breadcrumb_label('https://www.samsung.com/jp/explore/hint/galaxy-zoom-moon-shot/') == 'hint > galaxy-zoom-moon-shot'
    assert breadcrumb_label('https://www.samsung.com/jp/explore/special/android-data-transfer/') == 'special > android-data-transfer'
    assert breadcrumb_label('https://www.samsung.com/jp/explore/foo/bar/') == 'foo > bar'


def test_corrected_csv_sections():
    path = Path('/mnt/data/今週-explore-上位Page - P6 WEB - Japan - Oct 1, 2026.csv')
    if not path.exists():
        return
    result = parse_adobe_csv(path.read_bytes(), top_n=None, as_of_date=date(2026, 10, 1))
    assert result['last_week_start'] == '2026-09-21'
    assert result['last_week_end'] == '2026-09-27'
    assert len(result['pages']) == 10
    assert result['cta_section'] == 'Entry →PF・PD・BC'
    assert result['bounce_section'].strip().replace('  ', ' ') == 'Bounce Rate'
    first = result['pages'][0]
    assert first['current']['entry']['Total'] == 5041
    assert first['current']['cta']['Total'] == 2
    assert round(first['current']['bounce']['Total'], 1) == 12.3




def test_parse_matrix_skips_entry_pages_but_keeps_url():
    channel_row = [
        "",
        "変動",
        "[1] Organic",
        "[2] Direct",
        "[3] Referral",
        "[4] Owned Social",
        "[5] Social Network Referrals",
        "[6] CRM",
        "[7] Paid Search",
        "[8] Display AD",
        "[計] Total",
        "[1] Organic",
        "[2] Direct",
        "[3] Referral",
        "[4] Owned Social",
        "[5] Social Network Referrals",
        "[6] CRM",
        "[7] Paid Search",
        "[8] Display AD",
        "[計] Total",
    ]
    label_row = ["Entry Pages", "0"] + ["0"] * 18
    url_row = [
        "www.samsung.com/jp/support/mobile-devices/galaxy-device-lock-screen-features",
        "1",
    ] + ["0"] * 18

    parsed = _parse_matrix([channel_row, label_row, url_row])
    assert "Entry Pages" not in parsed["rows"]
    assert (
        "www.samsung.com/jp/support/mobile-devices/galaxy-device-lock-screen-features"
        in parsed["rows"]
    )
