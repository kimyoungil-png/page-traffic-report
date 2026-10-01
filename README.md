# page-traffic-report

Samsung Japan向け、URL単位の Page Traffic Report を自動生成する Streamlit アプリ。

## Flow

1. Adobe Analytics CSVを1つアップロード。
2. `Entry Visit` セクションのURL行数をそのままレポートページ数として取得。
3. Adobe URLに `https://` と末尾 `/` を付与。
4. ページHTMLの `<title>` を取得。
5. Google Search Console APIから同一URL・Last WeekのOrganic Search Query Top10を取得。
6. 既存Technical SEO CheckerのモバイルScreenshot APIを利用。
7. Adobeの `Entry Visit` / `Entry →PF・PD・BC` / `Bounce Rate` をURL×Channelで統合。
8. CTRは `Entry →PF・PD・BC ÷ Entry Visit` で計算。
9. Geminiは計算をせず、Pythonで確定した数値を根拠に青字分析コメントを生成。
10. 編集可能なPowerPointテンプレート1枚目を複製し、既存テキスト・表・スクリーンショット位置だけを差し替えてPPTを生成。

## URL rule

`www.samsung.com/jp/.../page` → `https://www.samsung.com/jp/.../page/`

canonicalによるURL書き換えは行わない。

## Page label rule

- `/jp/support/.../{slug}/` → `support > {slug}`
- `/jp/explore/{category}/{slug}/` → `{category} > {slug}`
- `explore` 配下のcategoryは固定せずURLの値をそのまま利用。

## Date rule

`Data：YYYY/M/D~YYYY/M/D` は**アプリ実行日の直前の月曜日〜日曜日**を自動表示する。

例: 2026/10/1実行 → `2026/9/21~2026/9/27`

Adobe CSVのヘッダー日付・ファイル名の日付はData表示の基準にはしない。

## Google Search Console

Cloud Runでは **Application Default Credentials (ADC)** を推奨する。

- Cloud Runのruntime Service AccountをSearch Console propertyのユーザーとして追加すれば、JSON秘密鍵なしでAPI取得できる。
- ローカル実行などADCを使わない場合のみ、`GSC_SERVICE_ACCOUNT_JSON` または `[gsc_service_account]` を設定する。
- `GSC_SITE_URL` は任意。省略時は認証ユーザーが参照できるpropertyを一覧取得し、対象URLに一致するものを自動選択する。
- URL-prefix propertyが複数一致する場合は最長prefixを優先し、なければ一致する `sc-domain:` propertyを利用する。

## Secrets

`.streamlit/secrets.toml.example` を参考に以下を設定する。

- `GEMINI_API_KEY`
- `GEMINI_MODEL`（任意）
- `GSC_SERVICE_ACCOUNT_JSON` または `[gsc_service_account]`
- `GSC_SITE_URL`（任意。自動判定可能）
- `SCREENSHOT_API_URL`（任意。未設定時は既存Technical SEO Screenshot API）

**`.streamlit/secrets.toml` はGitにcommitしない。**

## Local run

```bash
pip install -r requirements.txt
streamlit run app.py
```

接続確認:

```bash
python preflight.py
```

## Cloud Run

DockerfileはCloud Run対応済み。

```bash
export SERVICE_NAME=page-traffic-report
export REGION=asia-northeast1
./deploy_cloud_run.sh
```

Cloud Run側では `GEMINI_API_KEY` をSecret Manager等で設定する。GSCはruntime Service Account + ADCを推奨するため、Search Console側でそのService Accountメールアドレスに閲覧権限を付与すればよい。

## PowerPoint

`templates/explore_dotcom_sample_v2.pptx` を編集可能テンプレートとして使用する。

生成処理はTechnical SEO Checkerと同じ方針で、テンプレートの1枚目を複製して**既存のテキストボックス・表セル・スクリーンショット領域だけを差し替える**。レイアウトは再構築しない。

- テキストボックス: `自動調整なし`
- サマリー2行: テンプレートのPowerPoint箇条書き設定を維持
- モバイルスクリーンショットのみ画像として差し替え
- テンプレート内のアイコン画像relationshipも複製時に再マップ
