#!/bin/sh
set -eu

SERVICE_NAME="${SERVICE_NAME:-page-traffic-report}"
REGION="${REGION:-asia-northeast1}"
TIMEOUT="${TIMEOUT:-900}"
MEMORY="${MEMORY:-1Gi}"
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

gcloud run deploy "$SERVICE_NAME" \
  --project "$PROJECT_ID" \
  --source . \
  --region "$REGION" \
  --allow-unauthenticated \
  --timeout "$TIMEOUT" \
  --memory "$MEMORY" \
  --set-env-vars "TZ=Asia/Tokyo"

echo ""
echo "Cloud Run URL:"
gcloud run services describe "$SERVICE_NAME" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --format "value(status.url)"
