from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request


DEFAULT_SCREENSHOT_API = (
    "https://technical-seo-unlighthouse-api-231228645606."
    "asia-northeast1.run.app/screenshot"
)


def get_mobile_screenshot(url: str, api_url: str = DEFAULT_SCREENSHOT_API, timeout: int = 90) -> bytes:
    body = json.dumps({"url": url}, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        api_url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Screenshot API HTTP {exc.code}: {detail}") from exc

    if not data.get("success"):
        raise RuntimeError(data.get("error") or "Screenshot failed")
    encoded = data.get("imageBase64")
    if not encoded:
        raise RuntimeError("Screenshot data was not returned")
    return base64.b64decode(encoded)
