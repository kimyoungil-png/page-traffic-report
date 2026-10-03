from __future__ import annotations

import base64
import os
from pathlib import Path

import streamlit as st

from report_runtime import get_secret
from reports.registry import available_reports, render_report
from screenshot import DEFAULT_SCREENSHOT_API


st.set_page_config(
    page_title="Page Traffic Report",
    page_icon="📊",
    layout="wide",
)

APP_DIR = Path(__file__).resolve().parent
LOGIN_IMAGE_PATH = APP_DIR / "assets" / "momoko2.png"


def require_app_password() -> None:
    expected = str(get_secret("APP_PASSWORD", "") or "")
    if not expected:
        return

    if st.session_state.get("app_authenticated") is True:
        return

    st.title("Page Traffic Report")
    st.caption("Access restricted")

    if LOGIN_IMAGE_PATH.exists():
        encoded = base64.b64encode(
            LOGIN_IMAGE_PATH.read_bytes()
        ).decode("ascii")
        st.markdown(
            f"""
            <div style="text-align:center; margin:0.5rem 0 1.25rem 0;">
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

    entered = st.text_input(
        "Password",
        type="password",
        placeholder="4-digit password",
    )
    if st.button("Login", type="primary"):
        if entered == expected:
            st.session_state["app_authenticated"] = True
            st.rerun()
        else:
            st.error("パスワードが違います。")
    st.stop()


def configured_status(
    label: str,
    ok: bool,
    detail: str = "",
) -> None:
    icon = "✅" if ok else "⚪"
    text = f"{icon} **{label}**"
    if detail:
        text += f"  \n{detail}"
    st.markdown(text)


require_app_password()

st.title("Page Traffic Report")
st.caption("Samsung Japan Weekly Report Generator")
st.write(
    "レポート形式ごとにCSV解析・計算・PowerPoint生成を独立させています。"
    "新しいレポートを追加しても、既存レポートの処理には影響しない構成です。"
)

status1, status2, status3 = st.columns(3)
with status1:
    gsc_configured = bool(
        get_secret("GSC_AUTHORIZED_USER_JSON")
        or get_secret("GSC_SERVICE_ACCOUNT_JSON")
    )
    configured_status(
        "GSC",
        gsc_configured,
        "OAuth/認証設定済み" if gsc_configured else "未設定",
    )

with status2:
    gemini_configured = bool(get_secret("GEMINI_API_KEY"))
    configured_status(
        "Gemini",
        gemini_configured,
        "AI分析有効" if gemini_configured else "ルールベース分析",
    )

with status3:
    browser_api = str(
        get_secret(
            "SCREENSHOT_API_URL",
            DEFAULT_SCREENSHOT_API,
        )
        or ""
    )
    configured_status(
        "Browser",
        bool(browser_api),
        "Title + Screenshot取得",
    )

st.divider()

reports = available_reports()
if not reports:
    st.error("利用可能なレポート形式がありません。")
    st.stop()

if len(reports) == 1:
    selected = reports[0]
else:
    labels = {report.label: report for report in reports}
    selected_label = st.selectbox(
        "Report Type",
        options=list(labels.keys()),
        key="report:type",
    )
    selected = labels[selected_label]
    st.caption(selected.description)

render_report(selected.key)
