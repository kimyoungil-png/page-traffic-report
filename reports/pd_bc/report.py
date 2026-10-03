from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from gemini_analyzer import DEFAULT_MODEL
from report_runtime import get_secret
from reports.pd_bc.analyzer import (
    fallback_pd_bc_insight,
    generate_pd_bc_insight,
    research_market_context,
)
from reports.pd_bc.parser import parse_pd_bc_csv
from reports.pd_bc.ppt import DEFAULT_TEMPLATE_PATH, build_pd_bc_report
from screenshot import DEFAULT_SCREENSHOT_API, get_mobile_page


STATE_PRODUCTS = "pd_bc:products"
STATE_PPT = "pd_bc:ppt_bytes"
STATE_FILENAME = "pd_bc:output_filename"
STATE_MARKET_CONTEXT = "pd_bc:market_context"


def _preview_rows(products: list[dict]) -> list[dict]:
    rows = []
    for index, product in enumerate(products, start=1):
        total = product.get("main", {}).get("Total", {})
        current = total.get("current", {})
        rows.append(
            {
                "No": index,
                "Product": product.get("product_name", ""),
                "URL": product.get("url", ""),
                "PD Visit": current.get("pd_visit", 0),
                "BC Visit": current.get("bc_visit", 0),
                "PIV": current.get("piv_total", 0),
                "購入経路": "あり" if product.get("funnel", {}).get("current") else "なし",
                "生成Slide": 2 if product.get("funnel", {}).get("current") else 1,
            }
        )
    return rows


def render() -> None:
    st.subheader("PD+BC Page レポート")
    st.caption(
        "3週比較・PIV詳細・日別推移・端末/キャリア構成まで解析し、"
        "市場イベントも確認してPD+BC集計Slideを生成します。"
        "購入経路データがあるProductのみFunnel Slideも生成します。"
    )

    uploaded = st.file_uploader(
        "PD+BC Adobe Analytics CSV",
        type=["csv"],
        key="pd_bc:csv",
    )
    if not uploaded:
        return

    try:
        parsed = parse_pd_bc_csv(uploaded.getvalue())
    except Exception as exc:
        st.error(f"PD+BC CSVを解析できませんでした: {exc}")
        st.stop()

    products = parsed["products"]
    total_slides = sum(
        2 if product.get("funnel", {}).get("current") else 1
        for product in products
    )

    st.success(
        f"Product {len(products)}件を取得しました。 "
        f"生成予定 {total_slides} Slides"
    )
    st.dataframe(
        pd.DataFrame(_preview_rows(products)),
        use_container_width=True,
        hide_index=True,
    )

    option1, option2 = st.columns(2)
    with option1:
        use_gemini = st.checkbox(
            "Gemini分析（市場イベント検索含む）",
            value=True,
            key="pd_bc:use_gemini",
        )
    with option2:
        use_screenshot = st.checkbox(
            "モバイルスクリーンショット",
            value=True,
            key="pd_bc:use_screenshot",
        )

    gemini_key = get_secret("GEMINI_API_KEY") if use_gemini else None
    vertex_project = str(
        get_secret("GOOGLE_CLOUD_PROJECT", "") or ""
    ).strip()
    gemini_available = bool(
        use_gemini
        and (
            gemini_key
            or vertex_project
        )
    )
    gemini_model = str(
        get_secret("GEMINI_MODEL", DEFAULT_MODEL)
    )
    if use_gemini and not gemini_available:
        st.warning(
            "Gemini認証が未設定のため、"
            "3週比較のルールベースコメントで続行します。"
        )

    if not DEFAULT_TEMPLATE_PATH.exists():
        st.error(
            "PD+BC PowerPointテンプレートが未配置です: "
            f"{DEFAULT_TEMPLATE_PATH}"
        )
        st.stop()

    if st.button(
        "PD+BC Report生成",
        type="primary",
        key="pd_bc:generate",
    ):
        screenshot_api = str(
            get_secret("SCREENSHOT_API_URL", DEFAULT_SCREENSHOT_API)
        )

        market_context = {
            "text": "",
            "sources": [],
            "model": "none",
        }
        if gemini_available and products:
            dates = products[0].get("period_dates", {})
            start_date = (
                dates.get("older", {}).get("start")
                or products[0].get("date_start", "")
            )
            end_date = (
                dates.get("current", {}).get("end")
                or products[0].get("date_end", "")
            )
            with st.spinner(
                "Samsung・競合製品・祝日などの市場イベントを確認中..."
            ):
                market_context = research_market_context(
                    api_key=(
                        str(gemini_key)
                        if gemini_key
                        else None
                    ),
                    start_date=str(start_date),
                    end_date=str(end_date),
                    model=gemini_model,
                )
            if market_context.get("error"):
                st.warning(
                    "市場イベント検索は取得できなかったため、"
                    "CSVデータのみで分析します。"
                )
                with st.expander("市場イベント検索エラー詳細"):
                    st.code(str(market_context.get("error", "")))

        working_products = []
        progress = st.progress(0, text="PD+BCレポート生成を開始します...")

        for index, product in enumerate(products, start=1):
            item = dict(product)
            item["screenshot_bytes"] = None
            item["warnings"] = []

            if use_screenshot:
                with st.spinner(
                    f"[{index}/{len(products)}] Screenshot取得: {product['url']}"
                ):
                    try:
                        page = get_mobile_page(
                            product["url"],
                            api_url=screenshot_api,
                        )
                        item["screenshot_bytes"] = page.get("image_bytes")
                    except Exception as exc:
                        item["warnings"].append(
                            f"Screenshot取得失敗: {exc}"
                        )

            if gemini_available:
                with st.spinner(
                    f"[{index}/{len(products)}] AI分析: "
                    f"{product['product_name']}"
                ):
                    item["analysis"] = generate_pd_bc_insight(
                        product=item,
                        api_key=(
                            str(gemini_key)
                            if gemini_key
                            else None
                        ),
                        market_context=market_context,
                        model=gemini_model,
                    )
                if item["analysis"].get("error"):
                    item["warnings"].append(
                        "Gemini分析はFallbackを使用: "
                        + str(item["analysis"]["error"])
                    )
            else:
                item["analysis"] = fallback_pd_bc_insight(item)

            working_products.append(item)
            progress.progress(
                index / len(products),
                text=f"{index}/{len(products)} Product処理完了",
            )

        with st.spinner("PowerPointを生成中..."):
            ppt_bytes = build_pd_bc_report(working_products)

        st.session_state[STATE_PRODUCTS] = working_products
        st.session_state[STATE_PPT] = ppt_bytes
        st.session_state[STATE_FILENAME] = f"{Path(uploaded.name).stem}.pptx"
        st.session_state[STATE_MARKET_CONTEXT] = market_context
        st.success(
            f"PD+BC Page Reportを生成しました。 "
            f"{len(products)} Products / {total_slides} Slides"
        )

    if st.session_state.get(STATE_PRODUCTS):
        generated = st.session_state[STATE_PRODUCTS]
        st.divider()
        st.header("Report Preview")
        market_context = st.session_state.get(
            STATE_MARKET_CONTEXT,
            {},
        )
        if market_context.get("text"):
            with st.expander("AI分析で参照した市場イベント"):
                st.write(market_context["text"])
                for source in market_context.get("sources", []):
                    title = source.get("title") or source.get("url")
                    st.markdown(
                        f"- [{title}]({source.get('url', '')})"
                    )

        st.download_button(
            "PowerPointをダウンロード",
            data=st.session_state[STATE_PPT],
            file_name=st.session_state.get(
                STATE_FILENAME,
                "pd-bc-page-report.pptx",
            ),
            mime=(
                "application/vnd.openxmlformats-officedocument."
                "presentationml.presentation"
            ),
            key="pd_bc:download",
        )

        tabs = st.tabs(
            [
                f"{index}. {product.get('product_name', '')}"
                for index, product in enumerate(generated, start=1)
            ]
        )
        for tab, product in zip(tabs, generated):
            with tab:
                total = product.get("main", {}).get("Total", {})
                current = total.get("current", {})
                previous = total.get("previous", {})
                st.markdown(f"**URL:** {product.get('url', '')}")
                analysis = product.get("analysis", {})
                if analysis.get("headline_comment"):
                    st.markdown(
                        f"**Analysis:** {analysis['headline_comment']}"
                    )
                if analysis.get("detail_comment"):
                    st.write(analysis["detail_comment"])
                st.write(
                    {
                        "PD Visit 今週": current.get("pd_visit", 0),
                        "PD Visit 先週": previous.get("pd_visit", 0),
                        "PD Visit 先々週": total.get("older", {}).get("pd_visit", 0),
                        "BC Visit 今週": current.get("bc_visit", 0),
                        "BC Visit 先週": previous.get("bc_visit", 0),
                        "BC Visit 先々週": total.get("older", {}).get("bc_visit", 0),
                        "PIV": current.get("piv_total", 0),
                        "Funnel Slide": bool(
                            product.get("funnel", {}).get("current")
                        ),
                    }
                )
                if product.get("screenshot_bytes"):
                    st.image(product["screenshot_bytes"], width=240)
                if product.get("warnings"):
                    with st.expander("取得時のWarning"):
                        for warning in product["warnings"]:
                            st.write(warning)
