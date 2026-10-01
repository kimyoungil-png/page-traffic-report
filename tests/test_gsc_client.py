from gsc_client import resolve_site_url


class _SitesList:
    def __init__(self, entries):
        self.entries = entries

    def execute(self):
        return {"siteEntry": self.entries}


class _Sites:
    def __init__(self, entries):
        self.entries = entries

    def list(self):
        return _SitesList(self.entries)


class _Service:
    def __init__(self, entries):
        self.entries = entries

    def sites(self):
        return _Sites(self.entries)


def test_resolve_longest_url_prefix():
    service = _Service([
        {"siteUrl": "https://www.samsung.com/", "permissionLevel": "siteOwner"},
        {"siteUrl": "https://www.samsung.com/jp/", "permissionLevel": "siteFullUser"},
        {"siteUrl": "sc-domain:samsung.com", "permissionLevel": "siteFullUser"},
    ])
    result = resolve_site_url(
        service,
        "https://www.samsung.com/jp/explore/hint/example/",
    )
    assert result == "https://www.samsung.com/jp/"


def test_resolve_domain_property():
    service = _Service([
        {"siteUrl": "sc-domain:samsung.com", "permissionLevel": "siteFullUser"},
    ])
    result = resolve_site_url(
        service,
        "https://www.samsung.com/jp/explore/hint/example/",
    )
    assert result == "sc-domain:samsung.com"
