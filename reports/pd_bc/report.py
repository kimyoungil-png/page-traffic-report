from __future__ import annotations

import pandas as pd
import streamlit as st

from report_runtime import get_secret
from reports.pd_bc.parser import parse_pd_bc_csv
from reports.pd_bc.ppt import build_pd_bc_ppt, template_path
from screenshot import DEFAULT_SCREENSHOT_API, get_mobile_page


STATE_PRODUCTS = "pd_bc:products"
STATE_PPT = "pd_bc:ppt_bytes"


def _preview_rows(products: list[dict]) -> list[dict]:
    rows = []
    for index, product in enumerate(products, start=1):
        total = product["channels"]["Total"]["current"]
        piv = (
            product.get("piv_detail", {})
            .get("current", {})
            .get(
                "total_piv",
                total["carrier_piv"] + total["estore_piv"],
            )
        )
        rows.append(
            {
                "No": index,
                "Product": product["name"],
                "URL": product["url"],
                "PD Visit": total["pd_visit"],
                "BC Visit": total["bc_visit"],
                "PIV": piv,
                "購入経路": "あり" if product.get("funnel") else "なし",
                "生成Slide": 2 if product.get("funnel") else 1,
            }
        )
    return rows


def render() -> None:
    st.subheader("PD+BC Page レポート")
    st.caption(
        "ProductごとにPD+BC集計Slideを生成し、"
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
        2 if product.get("funnel") else 1
        for product in products
    )

    st.success(
        f"Product {len(products)}件を取得しました。"
        f"生成予定 {total_slides} Slides"
    )

    st.dataframe(
        pd.DataFrame(_preview_rows(products)),
        use_container_width=True,
        hide_index=True,
    )

    use_screenshot = st.checkbox(
        "モバイルスクリーンショット",
        value=True,
        key="pd_bc:use_screenshot",
    )

    template = template_path()
    if not template.exists():
        st.error(
            "PD+BC PowerPointテンプレートが未配置です。 "
            f"{template} に配置してください。"
        )
        st.stop()

    if st.button(
        "PD+BC Report生成",
        type="primary",
        key="pd_bc:generate",
    ):
        screenshot_api = str(
            get_secret(
                "SCREENSHOT_API_URL",
                DEFAULT_SCREENSHOT_API,
            )
        )

        working_products = []
        progress = st.progress(
            0,
            text="PD+BCレポート生成を開始します...",
        )

        for index, product in enumerate(products, start=1):
            item = dict(product)
            item["screenshot_bytes"] = None
            item["warnings"] = []

            if use_screenshot:
                with st.spinner(
                    f"[{index}/{len(products)}] "
                    f"Screenshot取得: {product['url']}"
                ):
                    try:
                        page = get_mobile_page(
                            product["url"],
                            api_url=screenshot_api,
                        )
                        item["screenshot_bytes"] = page.get(
                            "image_bytes"
                        )
                    except Exception as exc:
                        item["warnings"].append(
                            f"Screenshot取得失敗: {exc}"
                        )

            working_products.append(item)
            progress.progress(
                index / len(products),
                text=(
                    f"{index}/{len(products)}"
                    " Product処理完了"
                ),
            )

        with st.spinner("PowerPointを生成中..."):
            ppt_bytes = build_pd_bc_ppt(
                working_products
            )

        st.session_state[STATE_PRODUCTS] = working_products
        st.session_state[STATE_PPT] = ppt_bytes
        st.success(
            f"PD+BC Page Reportを生成しました。"
            f"{len(products)} Products / "
            f"{total_slides} Slides"
        )

    if st.session_state.get(STATE_PRODUCTS):
        st.divider()
        st.header("Report Preview")
        st.download_button(
            "PowerPointをダウンロード",
            data=st.session_state[STATE_PPT],
            file_name="pd-bc-page-report.pptx",
            mime=(
                "application/vnd.openxmlformats-officedocument."
                "presentationml.presentation"
            ),
            key="pd_bc:download",
        )

        generated = st.session_state[STATE_PRODUCTS]
        tabs = st.tabs(
            [
                f"{index}. {product['name']}"
                for index, product in enumerate(
                    generated,
                    start=1,
                )
            ]
        )
        for tab, product in zip(tabs, generated):
            with tab:
                total = product["channels"]["Total"]
                current = total["current"]
                previous = total["previous"]
                piv = (
                    product.get("piv_detail", {})
                    .get("current", {})
                    .get(
                        "total_piv",
                        current["carrier_piv"]
                        + current["estore_piv"],
                    )
                )
                st.markdown(f"**URL:** {product['url']}")
                st.write(
                    {
                        "PD Visit": current["pd_visit"],
                        "PD Visit 2 weeks ago": previous["pd_visit"],
                        "BC Visit": current["bc_visit"],
                        "BC Visit 2 weeks ago": previous["bc_visit"],
                        "PIV": piv,
                        "Funnel Slide": bool(
                            product.get("funnel")
                        ),
                    }
                )
                if product.get("screenshot_bytes"):
                    st.image(
                        product["screenshot_bytes"],
                        width=240,
                    )
                if product.get("warnings"):
                    with st.expander("取得時のWarning"):
                        for warning in product["warnings"]:
                            st.write(warning)
