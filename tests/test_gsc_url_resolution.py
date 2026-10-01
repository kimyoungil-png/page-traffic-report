from gsc_client import resolve_adobe_page_url
from url_utils import normalize_adobe_url_prefix


class _Request:
    def __init__(self, payload):
        self.payload = payload

    def execute(self):
        return self.payload


class _SearchAnalytics:
    def __init__(self, payload):
        self.payload = payload
        self.last_body = None

    def query(self, siteUrl, body):
        self.last_body = body
        return _Request(self.payload)


class _Service:
    def __init__(self, payload):
        self.sa = _SearchAnalytics(payload)

    def searchanalytics(self):
        return self.sa


def test_normalize_adobe_url_prefix_does_not_add_slash():
    raw = "www.samsung.com/jp/support/mobile-devices/how-do-i-move-data-between-the-external-sd-card-and-the-co"
    assert normalize_adobe_url_prefix(raw) == (
        "https://www.samsung.com/jp/support/mobile-devices/"
        "how-do-i-move-data-between-the-external-sd-card-and-the-co"
    )


def test_resolve_unique_truncated_url_from_gsc():
    full = (
        "https://www.samsung.com/jp/support/mobile-devices/"
        "how-do-i-move-data-between-the-external-sd-card-and-the-console-of-galaxy/"
    )
    service = _Service(
        {
            "rows": [
                {
                    "keys": [full],
                    "clicks": 10550,
                    "impressions": 316827,
                }
            ]
        }
    )
    result = resolve_adobe_page_url(
        service,
        "https://www.samsung.com/jp/",
        "www.samsung.com/jp/support/mobile-devices/how-do-i-move-data-between-the-external-sd-card-and-the-co",
        "2026-09-27",
    )
    assert result["url"] == full
    assert result["resolved"] is True
    assert result["reason"] == "unique_prefix_match"


def test_resolve_dominant_candidate_when_gsc_has_minor_variants():
    canonical = (
        "https://www.samsung.com/jp/support/mobile-devices/"
        "how-to-troubleshoot-a-galaxy-phone-that-wont-connect-to-a-wi-fi-network/"
    )
    service = _Service(
        {
            "rows": [
                {"keys": [canonical], "clicks": 4278, "impressions": 77902},
                {
                    "keys": [
                        "https://www.samsung.com/jp/support/mobile-devices/"
                        "how-to-troubleshoot-a-galaxy-phone-that-wont-connect-to-a-wi-Fi-network/"
                    ],
                    "clicks": 2,
                    "impressions": 62,
                },
            ]
        }
    )
    result = resolve_adobe_page_url(
        service,
        "https://www.samsung.com/jp/",
        "www.samsung.com/jp/support/mobile-devices/how-to-troubleshoot-a-galaxy-phone-that-wont-connect-to-a-",
        "2026-09-27",
    )
    assert result["url"] == canonical
    assert result["reason"] == "dominant_prefix_match"
