from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]


def build_gsc_service(service_account_info: dict[str, Any] | None = None):
    """Build Search Console API service.

    If explicit Service Account JSON is supplied, use it.
    Otherwise use Application Default Credentials (ADC). On Cloud Run this
    means the runtime service account can be granted Search Console access
    directly, avoiding a downloadable private-key JSON file.
    """
    from googleapiclient.discovery import build

    if service_account_info:
        from google.oauth2 import service_account

        credentials = service_account.Credentials.from_service_account_info(
            service_account_info,
            scopes=SCOPES,
        )
    else:
        import google.auth

        credentials, _ = google.auth.default(scopes=SCOPES)

    return build("searchconsole", "v1", credentials=credentials, cache_discovery=False)


def load_service_account_info(*, json_text: str | None = None, mapping: Any = None) -> dict[str, Any]:
    if json_text:
        return json.loads(json_text)
    if mapping:
        return {str(k): v for k, v in dict(mapping).items()}
    raise ValueError("GSC Service Account情報が設定されていません。")


def list_accessible_sites(service) -> list[dict[str, str]]:
    result = service.sites().list().execute()
    sites = []
    for item in result.get("siteEntry", []) or []:
        site_url = str(item.get("siteUrl") or "").strip()
        if not site_url:
            continue
        sites.append(
            {
                "siteUrl": site_url,
                "permissionLevel": str(item.get("permissionLevel") or ""),
            }
        )
    return sites


def _domain_matches_sc_property(page_url: str, site_url: str) -> bool:
    if not site_url.startswith("sc-domain:"):
        return False
    domain = site_url.split(":", 1)[1].strip().lower().lstrip(".")
    host = (urlparse(page_url).hostname or "").lower()
    return host == domain or host.endswith("." + domain)


def resolve_site_url(service, page_url: str, configured_site_url: str | None = None) -> str:
    """Resolve the Search Console property accessible to the service account.

    Priority:
    1) Explicit GSC_SITE_URL if configured and accessible.
    2) Longest URL-prefix property matching the page URL.
    3) Matching sc-domain property.
    """
    sites = list_accessible_sites(service)
    available = {item["siteUrl"] for item in sites}

    configured = str(configured_site_url or "").strip()
    if configured:
        if configured in available:
            return configured
        raise ValueError(
            f"GSC_SITE_URL '{configured}' はService Accountから参照できません。"
            f" Accessible properties: {', '.join(sorted(available)) or '(none)'}"
        )

    prefix_candidates = [
        site
        for site in available
        if site.startswith(("http://", "https://")) and page_url.startswith(site)
    ]
    if prefix_candidates:
        return max(prefix_candidates, key=len)

    domain_candidates = [site for site in available if _domain_matches_sc_property(page_url, site)]
    if domain_candidates:
        return sorted(domain_candidates, key=len, reverse=True)[0]

    raise ValueError(
        "対象URLに一致するSearch Console propertyを見つけられません。"
        f" Accessible properties: {', '.join(sorted(available)) or '(none)'}"
    )


def fetch_top_queries(
    service,
    site_url: str,
    page_url: str,
    start_date: str,
    end_date: str,
    row_limit: int = 10,
) -> list[dict[str, Any]]:
    body = {
        "startDate": start_date,
        "endDate": end_date,
        "dimensions": ["query"],
        "dimensionFilterGroups": [
            {
                "groupType": "and",
                "filters": [
                    {
                        "dimension": "page",
                        "operator": "equals",
                        "expression": page_url,
                    }
                ],
            }
        ],
        "rowLimit": row_limit,
        "searchType": "web",
        "dataState": "final",
    }
    result = service.searchanalytics().query(siteUrl=site_url, body=body).execute()
    output = []
    for row in result.get("rows", [])[:row_limit]:
        keys = row.get("keys") or []
        output.append(
            {
                "query": str(keys[0]) if keys else "",
                "clicks": float(row.get("clicks", 0) or 0),
                "impressions": float(row.get("impressions", 0) or 0),
                "ctr": float(row.get("ctr", 0) or 0),
                "position": float(row.get("position", 0) or 0),
            }
        )
    return output
