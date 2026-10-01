from __future__ import annotations

import json
import time
from typing import Any

from google import genai
from google.genai import types

from traffic_analyzer import fallback_headline


DEFAULT_MODEL = "gemini-flash-latest"
FALLBACK_MODEL = "gemini-3.1-flash-lite"


def _is_retryable(exc: Exception) -> bool:
    text = str(exc).upper()
    return any(x in text for x in ("429", "503", "UNAVAILABLE", "RESOURCE_EXHAUSTED", "TIMEOUT"))


def _call(client, model: str, system_prompt: str, payload: dict[str, Any]):
    return client.models.generate_content(
        model=model,
        contents=json.dumps(payload, ensure_ascii=False),
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.1,
            max_output_tokens=350,
            response_mime_type="application/json",
        ),
    )


def generate_traffic_insight(
    *,
    page: dict[str, Any],
    analysis_payload: dict[str, Any],
    api_key: str,
    model: str = DEFAULT_MODEL,
) -> dict[str, str]:
    client = genai.Client(api_key=api_key)
    system_prompt = """
あなたはSamsung Japan向けPage Traffic ReportのWebアナリストです。
入力されたAdobe AnalyticsとGoogle Search Consoleの数値だけを根拠に、簡潔な日本語の分析文を作成してください。

必ず次のJSONだけを返してください。
{
  "headline_comment": "スライド上部の青字に入れる1文",
  "detail_comment": "必要に応じて補足に使う1文"
}

ルール:
- 入力にない原因・施策・キャンペーン名・Push・広告要因を推測しない。
- 前週比、流入構成、チャネル別増減、Entry→PF・PD・BC、CTR、Bounce Rate、GSC Queryを根拠にする。
- headline_commentは45文字程度、最大60文字。最も重要な変化を1つか2つだけ要約する。
- detail_commentは最大75文字。headlineと重複しない補足がある場合のみ書く。
- 数値と矛盾する「維持」「増加」「減少」を書かない。
- 前週値が0の場合は「前週比◯倍」と書かず、「新規流入」「前週実績なし」等の事実表現にする。
- 「と思われる」「可能性がある」は使わない。
- GSCデータが空なら検索クエリには触れない。
- 文章はレポート向けの簡潔な「だ・である」調ではなく、テンプレに合う名詞止め/簡潔表現を優先する。
""".strip()

    last_error: Exception | None = None
    for candidate in (model, FALLBACK_MODEL):
        for delay in (0, 2):
            if delay:
                time.sleep(delay)
            try:
                response = _call(client, candidate, system_prompt, analysis_payload)
                data = json.loads((response.text or "{}").strip())
                headline = str(data.get("headline_comment") or "").strip()
                detail = str(data.get("detail_comment") or "").strip()
                if not headline:
                    raise RuntimeError("Gemini headline_comment was empty")
                return {"headline_comment": headline, "detail_comment": detail, "model": candidate}
            except Exception as exc:
                last_error = exc
                if not _is_retryable(exc):
                    break

    return {
        "headline_comment": fallback_headline(page),
        "detail_comment": "",
        "model": "fallback",
        "error": str(last_error) if last_error else "",
    }
