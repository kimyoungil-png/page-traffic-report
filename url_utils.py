from urllib.parse import urlsplit


def normalize_adobe_url_prefix(raw_url: str) -> str:
    """Normalize an Adobe URL without inventing a trailing slash.

    Adobe Analytics can truncate long URLs mid-slug. Keeping the raw prefix
    intact lets GSC be used to recover the full canonical page URL.
    """
    url = (raw_url or "").strip()
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def normalize_adobe_url(raw_url: str) -> str:
    """Apply the fixed Adobe Analytics URL pattern used by this report."""
    url = normalize_adobe_url_prefix(raw_url)
    if not url:
        return ""
    if not url.endswith("/"):
        url += "/"
    return url


def report_path(url: str) -> str:
    """Return the headline path with the /jp prefix removed."""
    path = urlsplit(url).path.rstrip("/") or "/"
    if path == "/jp":
        return "/"
    if path.startswith("/jp/"):
        path = path[3:]
        if not path.startswith("/"):
            path = "/" + path
    return path


def breadcrumb_label(url: str) -> str:
    """
    Build the compact report label.

    Rules:
    - /jp/support/.../{slug}/ -> support > {slug}
    - /jp/explore/{category}/{slug}/ -> {category} > {slug}
    - otherwise -> first path group > final slug
    """
    parts = [p for p in urlsplit(url).path.split("/") if p]
    if parts and parts[0].lower() == "jp":
        parts = parts[1:]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]

    if parts[0].lower() == "support":
        return f"support > {parts[-1]}"

    if parts[0].lower() == "explore" and len(parts) >= 3:
        return f"{parts[1]} > {parts[-1]}"

    return f"{parts[0]} > {parts[-1]}"
