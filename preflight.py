from __future__ import annotations

import os
from pathlib import Path

from page_fetcher import fetch_meta_title
from screenshot import get_mobile_screenshot


TEST_URL = "https://www.samsung.com/jp/support/mobile-devices/galaxy-device-lock-screen-features/"


def main():
    print("[1/4] Template")
    template = Path(__file__).resolve().parent / "templates" / "explore_dotcom_sample_v2.pptx"
    print(" OK" if template.exists() else f" NG: {template}")

    print("[2/4] Page title")
    try:
        result = fetch_meta_title(TEST_URL)
        print(" OK:", result.get("title", "")[:120])
    except Exception as exc:
        print(" NG:", exc)

    print("[3/4] Screenshot API")
    try:
        data = get_mobile_screenshot(TEST_URL)
        print(" OK:", len(data), "bytes")
    except Exception as exc:
        print(" NG:", exc)

    print("[4/4] Secrets presence (values are not printed)")
    print(" GEMINI_API_KEY:", "set" if os.getenv("GEMINI_API_KEY") else "not set")
    print(" GSC_SERVICE_ACCOUNT_JSON:", "set" if os.getenv("GSC_SERVICE_ACCOUNT_JSON") else "not set")


if __name__ == "__main__":
    main()
