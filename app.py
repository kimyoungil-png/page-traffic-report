from __future__ import annotations

import os
import base64
from pathlib import Path
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from adobe_parser import parse_adobe_csv
from gemini_analyzer import DEFAULT_MODEL, generate_traffic_insight
from gsc_client import (
    build_gsc_service,
    fetch_top_queries,
    gsc_reporting_period,
    load_authorized_user_info,
    load_service_account_info,
    resolve_site_url,
    resolve_adobe_page_url,
    validate_gsc_access,
)
from page_fetcher import fetch_meta_title
from ppt_report import build_ppt_report
from screenshot import DEFAULT_SCREENSHOT_API, get_mobile_page
from traffic_analyzer import (
    build_analysis_payload,
    build_table_rows,
    channel_share_line,
    cta_summary_line,
    fallback_headline,
    format_compact,
    format_ratio,
)
from url_utils import breadcrumb_label, report_path


st.set_page_config(page_title="Page Traffic Report", page_icon="📊", layout="wide")

APP_DIR = Path(__file__).resolve().parent
LOGIN_IMAGE_PATH = APP_DIR / "assets" / "momoko2.png"


def require_app_password():
    expected = os.getenv("APP_PASSWORD", "")
    try:
        expected = str(st.secrets.get("APP_PASSWORD", expected) or "")
    except Exception:
        pass

    # No password configured -> no gate.
    if not expected:
        return

    if st.session_state.get("app_authenticated") is True:
        return

    st.title("Page Traffic Report")
    st.caption("Access restricted")

    if LOGIN_IMAGE_PATH.exists():
        encoded = base64.b64encode(LOGIN_IMAGE_PATH.read_bytes()).decode("ascii")
        st.markdown(
            f"""
            <div style="text-align:center; margin: 0.5rem 0 1.25rem 0;">
              <img
                src="data:image/png;base64,{encoded}"
                alt="Login"
                style="width:260px; max-width:45vw; height:auto; border-radius:18px;"
              />
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.error(f"Login image not found: {LOGIN_IMAGE_PATH}")

    build_id = os.getenv("APP_BUILD_SHA", "")
    if build_id:
        st.caption(f"Build: {build_id}")

    entered = st.text_input("Password", type="password", placeholder="4-digit password")
    if st.button("Login", type="primary"):
        if entered == expected:
            st.session_state["app_authenticated"] = True
            st.rerun()
        else:
            st.error("パスワードが違います。")
    st.stop()


require_app_password()

st.title("Page Traffic Report")
st.caption("Adobe Analytics × Google Search Console × Gemini")
st.write(
    "Adobe Analytics CSVをアップロードすると、CSV内のURL行数に合わせて、"
    "GSC Query Top10・ページタイトル・モバイルスクリーンショット・分析コメントを取得し、"
    "PowerPointレポートを生成します。"
)


def configured_status(label: str, ok: bool, detail: str = ""):
    icon = "✅" if ok else "⚪"
    text = f"{icon} **{label}**"
    if detail:
        text += f"  \n{detail}"
    st.markdown(text)


def get_secret(name: str, default=None):
    try:
        value = st.secrets.get(name)
        if value is not None:
            return value
    except Exception:
        pass
    return os.getenv(name, default)


def get_gsc_service():
    # Preferred: OAuth credentials for an existing GSC user account.
    # This works even when the user cannot add a Service Account to the property.
    user_json = get_secret("GSC_AUTHORIZED_USER_JSON")
    user_mapping = None
    try:
        user_mapping = st.secrets.get("gsc_authorized_user")
    except Exception:
        pass

    if user_json or user_mapping:
        info = load_authorized_user_info(json_text=user_json, mapping=user_mapping)
        return build_gsc_service(authorized_user_info=info)

    # Backward-compatible Service Account option.
    sa_json = get_secret("GSC_SERVICE_ACCOUNT_JSON")
    sa_mapping = None
    try:
        sa_mapping = st.secrets.get("gsc_service_account")
    except Exception:
        pass

    if sa_json or sa_mapping:
        info = load_service_account_info(json_text=sa_json, mapping=sa_mapping)
        return build_gsc_service(service_account_info=info)

    # Final fallback: Cloud Run / local ADC.
    return build_gsc_service()


def report_anchor_date() -> date:
    # Cloud Run runs in UTC by default, so use Japan time explicitly.
    return datetime.now(ZoneInfo("Asia/Tokyo")).date()


def period_label(parsed: dict) -> str:
    start = date.fromisoformat(parsed["last_week_start"])
    end = date.fromisoformat(parsed["last_week_end"])
    return f"{start.year}/{start.month}/{start.day}~{end.year}/{end.month}/{end.day}"


def gsc_period_label(start: date, end: date) -> str:
    return f"{start.year}/{start.month}/{start.day}~{end.year}/{end.month}/{end.day}"


status1, status2, status3 = st.columns(3)
with status1:
    configured_status(
        "GSC",
        bool(get_secret("GSC_AUTHORIZED_USER_JSON") or get_secret("GSC_SERVICE_ACCOUNT_JSON")),
        "OAuth/認証設定済み" if (get_secret("GSC_AUTHORIZED_USER_JSON") or get_secret("GSC_SERVICE_ACCOUNT_JSON")) else "未設定",
    )
with status2:
    configured_status(
        "Gemini",
        bool(get_secret("GEMINI_API_KEY")),
        "AI分析有効" if get_secret("GEMINI_API_KEY") else "ルールベース分析",
    )
with status3:
    browser_api = str(get_secret("SCREENSHOT_API_URL", DEFAULT_SCREENSHOT_API) or "")
    configured_status(
        "Browser",
        bool(browser_api),
        "Title + Screenshot取得",
    )

uploaded = st.file_uploader("Adobe Analytics CSV", type=["csv"])

if uploaded:
    try:
        parsed = parse_adobe_csv(
            uploaded.getvalue(),
            top_n=None,
            as_of_date=report_anchor_date(),
        )
    except Exception as exc:
        st.error(f"Adobe CSVを解析できませんでした: {exc}")
        st.stop()

    st.success(
        f"URL {len(parsed['pages'])}件を取得しました。 "
        f"Last Week: {period_label(parsed)}"
    )
    if parsed.get("warnings"):
        for warning in parsed["warnings"]:
            st.warning(warning)

    preview = []
    for i, page in enumerate(parsed["pages"], start=1):
        preview.append(
            {
                "No": i,
                "URL": page["url"],
                "Last Week Entry Visit": page["current"]["entry"].get("Total", 0),
                "2 weeks ago": page["previous"]["entry"].get("Total", 0),
            }
        )
    st.dataframe(pd.DataFrame(preview), use_container_width=True, hide_index=True)

    col1, col2, col3 = st.columns(3)
    with col1:
        use_gsc = st.checkbox("Google Search Console API", value=True)
    with col2:
        use_gemini = st.checkbox("Gemini分析", value=True)
    with col3:
        use_screenshot = st.checkbox("モバイルスクリーンショット", value=True)

    if st.button("Traffic Report生成", type="primary"):
        request_date = report_anchor_date()
        gsc_start, gsc_end = gsc_reporting_period(request_date)
        gsc_start_iso = gsc_start.isoformat()
        gsc_end_iso = gsc_end.isoformat()

        gsc_service = None
        gsc_site_url = ""
        configured_gsc_site_url = str(
            get_secret("GSC_SITE_URL", "https://www.samsung.com/jp/") or ""
        ).strip()
        if use_gsc:
            try:
                gsc_service = get_gsc_service()
                first_url = parsed["pages"][0]["url"] if parsed.get("pages") else ""
                gsc_site_url = resolve_site_url(
                    gsc_service,
                    first_url,
                    configured_site_url=configured_gsc_site_url or None,
                )
                probe = validate_gsc_access(
                    gsc_service,
                    gsc_site_url,
                    gsc_start_iso,
                    gsc_end_iso,
                )
                st.success(
                    f"GSC接続OK: {gsc_site_url} / "
                    f"Query period: {gsc_period_label(gsc_start, gsc_end)} / "
                    f"probe rows: {probe.get('row_count', 0)}"
                )
            except Exception as exc:
                st.error(
                    "GSC API接続に失敗しました。空欄のPPTは生成せず処理を停止します。"
                )
                st.exception(exc)
                st.stop()

        gemini_key = get_secret("GEMINI_API_KEY") if use_gemini else None
        gemini_model = str(get_secret("GEMINI_MODEL", DEFAULT_MODEL))
        screenshot_api = str(get_secret("SCREENSHOT_API_URL", DEFAULT_SCREENSHOT_API))

        if use_gemini and not gemini_key:
            st.warning(
                "GEMINI_API_KEYが未設定のため、Gemini分析は使わず"
                "ルールベースの分析コメントで続行します。"
            )

        report_pages = []
        resolved_url_count = 0
        progress = st.progress(0, text="レポート生成を開始します...")

        for idx, page in enumerate(parsed["pages"], start=1):
            url = page["url"]
            warnings = []

            # Adobe Analytics may truncate long URLs mid-slug. Recover the full
            # page URL from GSC before requesting Title, Query Top10 or screenshot.
            if gsc_service:
                try:
                    resolved = resolve_adobe_page_url(
                        gsc_service,
                        gsc_site_url,
                        page.get("raw_url") or url,
                        gsc_end_iso,
                    )
                    resolved_url = str(resolved.get("url") or url)
                    if resolved_url != url:
                        st.info(
                            f"[{idx}/{len(parsed['pages'])}] Adobe URL補完: "
                            f"{url} → {resolved_url}"
                        )
                        warnings.append(
                            f"Adobe URLをGSCから補完: {url} → {resolved_url}"
                        )
                        resolved_url_count += 1
                        url = resolved_url
                    elif resolved.get("reason") == "ambiguous":
                        warnings.append(
                            "Adobe URL候補が複数見つかったため自動補完せず、"
                            "CSVのURLをそのまま使用しました。"
                        )
                except Exception as exc:
                    warnings.append(f"Adobe URL補完失敗: {exc}")

            meta_title = ""
            screenshot_bytes = None

            # Chromium is the primary source for Title even when the user does
            # not want the screenshot embedded in the PPT. Samsung pages can
            # render a valid browser title while plain HTTP returns incomplete HTML.
            with st.spinner(f"[{idx}/{len(parsed['pages'])}] Page取得: {url}"):
                try:
                    snapshot = get_mobile_page(url, api_url=screenshot_api)
                    if use_screenshot:
                        screenshot_bytes = snapshot.get("image_bytes")
                    meta_title = str(snapshot.get("title") or "").strip()
                    browser_final_url = str(snapshot.get("final_url") or "").strip()
                    if browser_final_url and browser_final_url != url:
                        url = browser_final_url
                except Exception as exc:
                    warnings.append(f"Browser取得失敗: {exc}")

            if not meta_title:
                with st.spinner(f"[{idx}/{len(parsed['pages'])}] Title取得: {url}"):
                    try:
                        meta = fetch_meta_title(url)
                        meta_title = meta.get("title", "")
                    except Exception as exc:
                        warnings.append(f"Title取得失敗: {exc}")

            gsc_queries = []
            if gsc_service:
                with st.spinner(f"[{idx}/{len(parsed['pages'])}] GSC取得: {url}"):
                    try:
                        gsc_queries = fetch_top_queries(
                            gsc_service,
                            gsc_site_url,
                            url,
                            gsc_start_iso,
                            gsc_end_iso,
                            row_limit=10,
                        )
                    except Exception as exc:
                        st.error(f"GSC取得失敗: {url}")
                        st.exception(exc)
                        st.stop()

            share_line = channel_share_line(page)
            secondary_line = cta_summary_line(page)
            analysis_payload = build_analysis_payload(page, gsc_queries)
            headline = fallback_headline(page)
            detail_comment = ""
            gemini_used = "fallback"
            if gemini_key:
                with st.spinner(f"[{idx}/{len(parsed['pages'])}] Gemini分析: {url}"):
                    insight = generate_traffic_insight(
                        page=page,
                        analysis_payload=analysis_payload,
                        api_key=gemini_key,
                        model=gemini_model,
                    )
                    headline = insight.get("headline_comment") or headline
                    detail_comment = insight.get("detail_comment") or ""
                    gemini_used = insight.get("model", "")
                    if insight.get("error"):
                        warnings.append(f"Gemini fallback: {insight['error']}")

            if not secondary_line and detail_comment:
                secondary_line = detail_comment

            prev_total = int(page["previous"]["entry"].get("Total", 0) or 0)
            curr_total = int(page["current"]["entry"].get("Total", 0) or 0)
            report_pages.append(
                {
                    "url": url,
                    "raw_url": page["raw_url"],
                    "meta_title": meta_title,
                    "report_path": report_path(url),
                    "breadcrumb": breadcrumb_label(url),
                    "period_label": period_label(parsed),
                    "gsc_period_label": gsc_period_label(gsc_start, gsc_end),
                    "total_current": curr_total,
                    "total_previous": prev_total,
                    "total_current_compact": format_compact(curr_total),
                    "total_ratio_label": format_ratio(curr_total, prev_total),
                    "headline_comment": headline,
                    "detail_comment": detail_comment,
                    "share_line": share_line,
                    "secondary_line": secondary_line,
                    "table_rows": build_table_rows(page),
                    "gsc_queries": gsc_queries,
                    "screenshot_bytes": screenshot_bytes,
                    "gemini_model": gemini_used,
                    "warnings": warnings,
                }
            )
            progress.progress(idx / len(parsed["pages"]), text=f"{idx}/{len(parsed['pages'])}ページ処理完了")

        with st.spinner("PowerPointを生成中..."):
            ppt_bytes = build_ppt_report(report_pages)

        st.session_state["report_pages"] = report_pages
        st.session_state["ppt_bytes"] = ppt_bytes
        st.success(
            f"Page Traffic Reportを生成しました。 "
            f"URL補完 {resolved_url_count}件 / "
            f"Gemini {'ON' if gemini_key else 'Fallback'} / "
            f"{len(report_pages)}ページ"
        )

if st.session_state.get("report_pages"):
    pages = st.session_state["report_pages"]
    st.divider()
    st.header("Report Preview")
    st.download_button(
        "PowerPointをダウンロード",
        data=st.session_state["ppt_bytes"],
        file_name="page-traffic-report.pptx",
        mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )

    tabs = st.tabs([f"{i}. {p['breadcrumb']}" for i, p in enumerate(pages, start=1)])
    for tab, page in zip(tabs, pages):
        with tab:
            st.subheader(page["report_path"])
            st.markdown(f"**Title:** {page['meta_title'] or '取得できず'}")
            st.markdown(f"**Analysis:** {page['headline_comment']}")
            st.write(page["share_line"])
            if page["secondary_line"]:
                st.write(page["secondary_line"])

            left, right = st.columns([1, 2.4])
            with left:
                if page.get("screenshot_bytes"):
                    st.image(page["screenshot_bytes"], use_container_width=True)
            with right:
                table_df = pd.DataFrame(page["table_rows"])
                st.dataframe(table_df, use_container_width=True, hide_index=True)
                st.markdown(
                    f"#### Organic Search Queries Top10 "
                    f"({page.get('gsc_period_label', '')})"
                )
                st.dataframe(pd.DataFrame(page["gsc_queries"]), use_container_width=True, hide_index=True)
            if page.get("warnings"):
                with st.expander("取得時のWarning"):
                    for warning in page["warnings"]:
                        st.write(warning)
