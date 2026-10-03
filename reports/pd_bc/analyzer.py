from __future__ import annotations

import json
import re
import time
from typing import Any

from google import genai
from google.genai import types

from gemini_analyzer import DEFAULT_MODEL, FALLBACK_MODEL


def _is_retryable(exc: Exception) -> bool:
    text = str(exc).upper()
    return any(
        token in text
        for token in (
            "429",
            "503",
            "UNAVAILABLE",
            "RESOURCE_EXHAUSTED",
            "TIMEOUT",
        )
    )


def _change_rate(current: float, previous: float) -> float | None:
    if not previous:
        return None
    return (
        (float(current) - float(previous))
        / float(previous)
        * 100
    )


def _fallback_headline(product: dict[str, Any]) -> str:
    total = product.get("main", {}).get("Total", {})
    current = total.get("current", {})
    previous = total.get("previous", {})
    older = total.get("older", {})

    current_pd = int(current.get("pd_visit", 0) or 0)
    previous_pd = int(previous.get("pd_visit", 0) or 0)
    older_pd = int(older.get("pd_visit", 0) or 0)

    vs_previous = _change_rate(current_pd, previous_pd)
    vs_older = _change_rate(current_pd, older_pd)

    if vs_previous is not None and vs_previous < 0:
        if vs_older is not None and abs(vs_older) <= 10:
            return "PD Visitは前週比減も先々週水準"
        if vs_older is not None and vs_older < 0:
            return "PD Visitは2週連続で減少"
        if vs_older is not None:
            return "PD Visitは前週比減、先々週比では増加"
        return "PD Visitは前週比で減少"

    if vs_previous is not None and vs_previous > 0:
        if vs_older is not None and vs_older > 0:
            return "PD Visitは先週・先々週を上回る水準"
        return "PD Visitは前週比で増加"

    return "PD Visitは前週並み"


def _daily_summary(product: dict[str, Any]) -> dict[str, Any]:
    daily = product.get("piv_detail", {}).get("daily", {})
    result: dict[str, Any] = {}

    for period in ("older", "previous", "current"):
        rows = daily.get(period, [])
        if not rows:
            continue

        visits = [
            int(row.get("visits", 0) or 0)
            for row in rows
        ]
        if not visits:
            continue

        max_index = max(
            range(len(visits)),
            key=lambda index: visits[index],
        )
        min_index = min(
            range(len(visits)),
            key=lambda index: visits[index],
        )
        result[period] = {
            "days": rows,
            "average_visits": sum(visits) / len(visits),
            "max_day": rows[max_index],
            "min_day": rows[min_index],
        }

    return result


def build_analysis_payload(product: dict[str, Any]) -> dict[str, Any]:
    return {
        "product": product.get("product_name", ""),
        "url": product.get("url", ""),
        "period_dates": product.get("period_dates", {}),
        "main_metrics": product.get("main", {}),
        "device_mix": product.get("device_summary", {}),
        "device_ranking_current": product.get("device_ranking", []),
        "piv_detail": product.get("piv_detail", {}),
        "daily_summary": _daily_summary(product),
        "purchase_funnel": product.get("funnel", {}),
    }


def _grounding_sources(response) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []

    try:
        candidates = getattr(response, "candidates", None) or []
        if not candidates:
            return sources

        metadata = getattr(
            candidates[0],
            "grounding_metadata",
            None,
        )
        chunks = getattr(
            metadata,
            "grounding_chunks",
            None,
        ) or []

        for chunk in chunks:
            web = getattr(chunk, "web", None)
            if not web:
                continue

            title = str(
                getattr(web, "title", "") or ""
            ).strip()
            uri = str(
                getattr(web, "uri", "") or ""
            ).strip()

            if not uri:
                continue

            item = {
                "title": title,
                "url": uri,
            }
            if item not in sources:
                sources.append(item)
    except Exception:
        return sources

    return sources[:8]


def research_market_context(
    *,
    api_key: str,
    start_date: str,
    end_date: str,
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    client = genai.Client(api_key=api_key)

    prompt = f"""
日本のスマートフォンECトラフィックの週次分析に使うため、
{start_date} から {end_date} の期間について、次の事実をGoogle検索で確認してください。

対象:
- Samsung Japanの大型キャンペーン、Samsung Week、製品発売・予約開始・主要販促
- Apple、Google Pixel、Sony Xperia、Xiaomi、OPPOなど主要競合の日本向け発表・発売・予約開始
- 日本の祝日、大型連休、連休の谷間などECトラフィックに影響し得るカレンダー要因

条件:
- 日付を確認できる事実だけを書く。
- 一般論や推測は書かない。
- トラフィック増減の原因だと断定しない。
- 該当事項がなければ「特記事項なし」とする。
- 300文字程度の簡潔な箇条書きにする。
""".strip()

    last_error: Exception | None = None

    for candidate in (model, FALLBACK_MODEL):
        for delay in (0, 2):
            if delay:
                time.sleep(delay)

            try:
                response = client.models.generate_content(
                    model=candidate,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        tools=[
                            types.Tool(
                                google_search=types.GoogleSearch()
                            )
                        ],
                        temperature=0.0,
                        max_output_tokens=600,
                    ),
                )

                text = str(response.text or "").strip()
                if not text:
                    raise RuntimeError(
                        "Gemini market context was empty"
                    )

                return {
                    "text": text,
                    "sources": _grounding_sources(response),
                    "model": candidate,
                }
            except Exception as exc:
                last_error = exc
                if not _is_retryable(exc):
                    break

    return {
        "text": "",
        "sources": [],
        "model": "none",
        "error": str(last_error) if last_error else "",
    }


def _parse_json_text(text: str) -> dict[str, Any]:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(
            r"^```(?:json)?\s*",
            "",
            cleaned,
        )
        cleaned = re.sub(
            r"\s*```$",
            "",
            cleaned,
        )

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(
            r"\{.*\}",
            cleaned,
            flags=re.S,
        )
        if not match:
            raise
        return json.loads(match.group(0))


def generate_pd_bc_insight(
    *,
    product: dict[str, Any],
    api_key: str,
    market_context: dict[str, Any] | None = None,
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    payload = build_analysis_payload(product)
    payload["market_context"] = market_context or {}

    client = genai.Client(api_key=api_key)

    system_prompt = """
あなたはSamsung Japan向けPD+BC Page週次レポートのWebアナリストです。
入力されたAdobe Analyticsデータと、別途Google検索で確認済みのmarket_contextだけを根拠に、
PowerPoint上部の短い分析コメントを作成してください。

必ず次のJSONだけを返してください。
{
  "headline_comment": "スライド上部の青字に入れる短い分析文",
  "detail_comment": "プレビュー用の補足分析"
}

分析ルール:
- older=先々週、previous=先週、current=今週として3週トレンドを見る。
- 今週が先週より減少していても、先々週と同水準なら「先々週水準」など3週比較を優先する。
- Totalだけでなく、Channel別PD/BC Visit、PIV/PIR、購入経路も比較する。
- PIV詳細、キャリア別PIV、eStore PIV、日別Visit/PIVを必ず確認する。
- 端末別はGalaxy/iPhone/Sony固定ではなく、currentのPIV量・構成比・PIR・変化が目立つ端末を選ぶ。
- Google PixelやPC Userが重要ならSony Xperiaより優先する。
- 日別データから祝日・連休・イベント日に対応する山谷が見える場合のみ触れる。
- market_contextのイベントは検索で確認済みの事実として背景に使えるが、
  データだけで因果関係を断定しない。「〜と重なる」「〜を含む週」など事実表現にする。
- market_contextにない外部イベントを新しく作らない。
- 数値にない原因、広告配信変更、キャンペーン要因を推測しない。
- headline_commentは最大60文字。最重要ポイントを1〜2個に絞る。
- detail_commentは最大120文字。3週比較、端末構成、日別、外部イベントのうち、
  headlineに入らなかった有用な補足を1文でまとめる。
- 「と思われる」「〜のはず」は使わない。
""".strip()

    last_error: Exception | None = None

    for candidate in (model, FALLBACK_MODEL):
        for delay in (0, 2):
            if delay:
                time.sleep(delay)

            try:
                response = client.models.generate_content(
                    model=candidate,
                    contents=json.dumps(
                        payload,
                        ensure_ascii=False,
                    ),
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        temperature=0.1,
                        max_output_tokens=450,
                        response_mime_type="application/json",
                    ),
                )

                data = _parse_json_text(
                    response.text or "{}"
                )

                headline = str(
                    data.get("headline_comment", "") or ""
                ).strip()
                detail = str(
                    data.get("detail_comment", "") or ""
                ).strip()

                if not headline:
                    raise RuntimeError(
                        "Gemini headline_comment was empty"
                    )

                return {
                    "headline_comment": headline,
                    "detail_comment": detail,
                    "model": candidate,
                    "market_context": market_context or {},
                }
            except Exception as exc:
                last_error = exc
                if not _is_retryable(exc):
                    break

    return {
        "headline_comment": _fallback_headline(product),
        "detail_comment": "",
        "model": "fallback",
        "market_context": market_context or {},
        "error": str(last_error) if last_error else "",
    }


def fallback_pd_bc_insight(
    product: dict[str, Any],
) -> dict[str, Any]:
    return {
        "headline_comment": _fallback_headline(product),
        "detail_comment": "",
        "model": "fallback",
        "market_context": {},
    }
