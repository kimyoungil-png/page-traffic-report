from __future__ import annotations

import os
from pathlib import Path

from gsc_client import (
    build_gsc_service,
    list_accessible_sites,
    load_service_account_info,
)
from page_fetcher import fetch_meta_title
from screenshot import get_mobile_screenshot


TEST_URL = "https://www.samsung.com/jp/support/mobile-devices/galaxy-device-lock-screen-features/"


def main():
    print("[1/5] Template")
    template = Path(__file__).resolve().parent / "templates" / "explore_dotcom_sample_v2.pptx"
    print(" OK" if template.exists() else f" NG: {template}")

    print("[2/5] Page title")
    try:
        result = fetch_meta_title(TEST_URL)
        print(" OK:", result.get("title", "")[:120])
    except Exception as exc:
        print(" NG:", exc)

    print("[3/5] Screenshot API")
    try:
        data = get_mobile_screenshot(TEST_URL)
        print(" OK:", len(data), "bytes")
    except Exception as exc:
        print(" NG:", exc)

    print("[4/5] Google Search Console")
    try:
        json_text = os.getenv("GSC_SERVICE_ACCOUNT_JSON")
        if json_text:
            info = load_service_account_info(json_text=json_text)
            service = build_gsc_service(info)
            auth_mode = "explicit service-account JSON"
        else:
            service = build_gsc_service()
            auth_mode = "Application Default Credentials"

        sites = list_accessible_sites(service)
        print(" OK:", auth_mode, "-", len(sites), "accessible properties")
        for item in sites[:5]:
            print("   ", item["siteUrl"], item["permissionLevel"])
    except Exception as exc:
        print(" NG:", exc)

    print("[5/5] Gemini")
    print(" GEMINI_API_KEY:", "set" if os.getenv("GEMINI_API_KEY") else "not set")


if __name__ == "__main__":
    main()
