# page-traffic-report

Samsung Japan向け、URL単位の Page Traffic Report を自動生成する Streamlit アプリ。

## Flow

1. Adobe Analytics CSVを1つアップロード。
2. `Entry Visit` セクションのURL行数をそのままレポートページ数として取得。
3. Adobe URLに `https://` と末尾 `/` を付与。
4. ページHTMLの `<title>` を取得。
5. Google Search Console APIから同一URLのOrganic Search Query Top10を取得。GSCの遅延を考慮し、実行曜日に応じて7日間の取得期間を自動調整する。
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

GSCは2〜3日程度のデータ遅延を考慮し、アプリ実行日を基準に以下の7日間を取得する。

- 月曜実行: 先々週 土曜〜先週 金曜
- 火曜実行: 先々週 日曜〜先週 土曜
- 水曜〜日曜実行: 先週 月曜〜先週 日曜

PowerPoint右側のGSC表には `GSC: YYYY/M/D~YYYY/M/D` と実際の取得期間を表示する。Adobe Analyticsの `Data：...` 期間とは月曜・火曜のみ数日ずれる。

Cloud Runでは、Search Console側でユーザー追加権限がない場合は **既存GSCユーザーのOAuth** を推奨する。

- `GSC_AUTHORIZED_USER_JSON`: 既存GSCユーザーのOAuth認証情報。Samsung JP propertyをすでに閲覧できるGoogleアカウントで認証する。
- `GSC_SERVICE_ACCOUNT_JSON`: Search Console propertyへService Accountを追加できる場合のみ使う代替方式。
- どちらも未設定の場合はApplication Default Credentials (ADC)を使う。
- `GSC_SITE_URL` は任意。省略時は認証ユーザーが参照できるpropertyを一覧取得し、対象URLに一致するものを自動選択する。
- URL-prefix propertyが複数一致する場合は最長prefixを優先し、なければ一致する `sc-domain:` propertyを利用する。

## Secrets

`.streamlit/secrets.toml.example` を参考に以下を設定する。

- `GEMINI_API_KEY`
- `GEMINI_MODEL`（任意）
- `GSC_AUTHORIZED_USER_JSON` または `[gsc_authorized_user]`（推奨）
- `GSC_SERVICE_ACCOUNT_JSON` または `[gsc_service_account]`（代替）
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

### GitHub Actionsからデプロイ

`.github/workflows/deploy-cloud-run.yml` を用意している。Repository Secretsに次を登録すると、GitHubのActions画面から **Deploy to Cloud Run** を手動実行できる。

- `GCP_PROJECT_ID`
- `GCP_SA_KEY`
- `GEMINI_API_KEY`

デプロイ完了後、GSCは既存GoogleユーザーのOAuthをSecret Managerへ設定する方式を推奨する。Search Console側で新しいユーザーを追加する必要はない。

### ローカル / Cloud Shellから一括デプロイ

Google Cloudへログイン済みなら、Gemini Secret設定 → Cloud Run deploy → health checkまで一括で実行できる。

```bash
export PROJECT_ID="your-gcp-project-id"
bash bootstrap_and_deploy.sh
```

GSCは既存のSearch Console閲覧ユーザーでOAuth認証できるため、Samsung JP propertyへService Accountを追加する必要はない。

### GSCを既存Googleユーザーで接続

Google Cloud ConsoleでOAuth Client ID（Desktop app）を1つ作成してJSONをダウンロードし、Samsung JPのSearch Consoleを閲覧できるGoogleアカウントで次を実行する。

```bash
export PROJECT_ID="your-gcp-project-id"
export GSC_OAUTH_CLIENT_FILE="$HOME/Downloads/client_secret_xxx.json"
bash configure_gsc_user_oauth.sh
```

この処理は `webmasters.readonly` のOAuth refresh credentialをSecret Managerへ保存し、Cloud Runへ `GSC_AUTHORIZED_USER_JSON` として接続する。Search Console側のユーザー追加権限は不要。

個別に実行する場合:

```bash
export SERVICE_NAME=page-traffic-report
export REGION=asia-northeast1
bash configure_gemini_secret.sh
bash configure_gsc_user_oauth.sh
sh deploy_cloud_run.sh
```

deploy scriptは専用runtime Service Account
`page-traffic-report@<PROJECT_ID>.iam.gserviceaccount.com`
をCloud Run実行用に利用するが、GSCアクセス権はそのService Accountへ付与しなくてもよい。GSCは既存ユーザーOAuthのSecretを利用できる。

`GEMINI_API_KEY` はCloud RunのSecret Manager等で環境変数として設定する。

Gemini Secret Manager設定用のhelperも用意済み。

```bash
bash configure_gemini_secret.sh
```

API Keyは画面上で非表示入力され、GitHubには保存しない。

## PowerPoint

`templates/explore_dotcom_sample_v2.pptx` を編集可能テンプレートとして使用する。

生成処理はTechnical SEO Checkerと同じ方針で、テンプレートの1枚目を複製して**既存のテキストボックス・表セル・スクリーンショット領域だけを差し替える**。レイアウトは再構築しない。

- テキストボックス: `自動調整なし`
- サマリー2行: テンプレートのPowerPoint箇条書き設定を維持
- モバイルスクリーンショットのみ画像として差し替え
- テンプレート内のアイコン画像relationshipも複製時に再マップ
