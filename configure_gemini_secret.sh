#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="${SERVICE_NAME:-page-traffic-report}"
REGION="${REGION:-asia-northeast1}"
SERVICE_ACCOUNT_NAME="${SERVICE_ACCOUNT_NAME:-page-traffic-report}"
SECRET_NAME="${GEMINI_SECRET_NAME:-page-traffic-report-gemini-api-key}"
PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}"

if ! command -v gcloud >/dev/null 2>&1; then
  echo "gcloud CLI is required" >&2
  exit 1
fi

if [[ -z "$PROJECT_ID" || "$PROJECT_ID" == "(unset)" ]]; then
  echo "Set PROJECT_ID or run: gcloud config set project YOUR_PROJECT_ID" >&2
  exit 1
fi

SERVICE_ACCOUNT_EMAIL="$SERVICE_ACCOUNT_NAME@$PROJECT_ID.iam.gserviceaccount.com"

if [[ -z "${GEMINI_API_KEY:-}" ]]; then
  read -r -s -p "Gemini API key: " GEMINI_API_KEY
  echo
fi

if [[ -z "$GEMINI_API_KEY" ]]; then
  echo "Gemini API key is empty." >&2
  exit 1
fi

gcloud services enable secretmanager.googleapis.com --project "$PROJECT_ID"

if ! gcloud secrets describe "$SECRET_NAME" --project "$PROJECT_ID" >/dev/null 2>&1; then
  gcloud secrets create "$SECRET_NAME" \
    --project "$PROJECT_ID" \
    --replication-policy automatic
fi

printf '%s' "$GEMINI_API_KEY" | gcloud secrets versions add "$SECRET_NAME" \
  --project "$PROJECT_ID" \
  --data-file=-

gcloud secrets add-iam-policy-binding "$SECRET_NAME" \
  --project "$PROJECT_ID" \
  --member "serviceAccount:$SERVICE_ACCOUNT_EMAIL" \
  --role "roles/secretmanager.secretAccessor" >/dev/null

if gcloud run services describe "$SERVICE_NAME" \
  --project "$PROJECT_ID" \
  --region "$REGION" >/dev/null 2>&1; then
  gcloud run services update "$SERVICE_NAME" \
    --project "$PROJECT_ID" \
    --region "$REGION" \
    --set-secrets "GEMINI_API_KEY=$SECRET_NAME:latest"
  echo "Gemini secret attached to Cloud Run."
else
  echo "Secret created. Deploy Cloud Run first, then run this script again to attach it."
fi

unset GEMINI_API_KEY
