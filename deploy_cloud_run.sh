#!/bin/sh
set -eu

SERVICE_NAME="${SERVICE_NAME:-page-traffic-report}"
REGION="${REGION:-asia-northeast1}"
TIMEOUT="${TIMEOUT:-900}"
MEMORY="${MEMORY:-1Gi}"
SERVICE_ACCOUNT_NAME="${SERVICE_ACCOUNT_NAME:-page-traffic-report}"
GEMINI_SECRET_NAME="${GEMINI_SECRET_NAME:-page-traffic-report-gemini-api-key}"
PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}"

if ! command -v gcloud >/dev/null 2>&1; then
  echo "gcloud CLI is required" >&2
  exit 1
fi

if [ -z "$PROJECT_ID" ] || [ "$PROJECT_ID" = "(unset)" ]; then
  echo "Set PROJECT_ID or run: gcloud config set project YOUR_PROJECT_ID" >&2
  exit 1
fi

if [ ! -f "templates/explore_dotcom_sample_v2.pptx" ]; then
  echo "PowerPoint template is missing: templates/explore_dotcom_sample_v2.pptx" >&2
  exit 1
fi

SERVICE_ACCOUNT_EMAIL="$SERVICE_ACCOUNT_NAME@$PROJECT_ID.iam.gserviceaccount.com"

if ! gcloud iam service-accounts describe "$SERVICE_ACCOUNT_EMAIL" \
  --project "$PROJECT_ID" >/dev/null 2>&1; then
  echo "Creating runtime service account: $SERVICE_ACCOUNT_EMAIL"
  gcloud iam service-accounts create "$SERVICE_ACCOUNT_NAME" \
    --project "$PROJECT_ID" \
    --display-name "Page Traffic Report"
fi

if gcloud secrets describe "$GEMINI_SECRET_NAME" \
  --project "$PROJECT_ID" >/dev/null 2>&1; then
  gcloud secrets add-iam-policy-binding "$GEMINI_SECRET_NAME" \
    --project "$PROJECT_ID" \
    --member "serviceAccount:$SERVICE_ACCOUNT_EMAIL" \
    --role "roles/secretmanager.secretAccessor" >/dev/null

  gcloud run deploy "$SERVICE_NAME" \
    --project "$PROJECT_ID" \
    --source . \
    --region "$REGION" \
    --allow-unauthenticated \
    --service-account "$SERVICE_ACCOUNT_EMAIL" \
    --timeout "$TIMEOUT" \
    --memory "$MEMORY" \
    --set-env-vars "TZ=Asia/Tokyo" \
    --set-secrets "GEMINI_API_KEY=$GEMINI_SECRET_NAME:latest"
else
  gcloud run deploy "$SERVICE_NAME" \
    --project "$PROJECT_ID" \
    --source . \
    --region "$REGION" \
    --allow-unauthenticated \
    --service-account "$SERVICE_ACCOUNT_EMAIL" \
    --timeout "$TIMEOUT" \
    --memory "$MEMORY" \
    --set-env-vars "TZ=Asia/Tokyo"

  echo ""
  echo "Gemini secret is not configured yet."
  echo "Run ./configure_gemini_secret.sh when ready."
fi

echo ""
echo "Cloud Run URL:"
gcloud run services describe "$SERVICE_NAME" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --format "value(status.url)"

echo ""
echo "Google Search Console:"
echo "Add this Cloud Run runtime service account as a user of the Search Console property:"
echo "$SERVICE_ACCOUNT_EMAIL"
