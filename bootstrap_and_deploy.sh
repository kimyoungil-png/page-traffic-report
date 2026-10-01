#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="${SERVICE_NAME:-page-traffic-report}"
REGION="${REGION:-asia-northeast1}"
PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}"

if ! command -v gcloud >/dev/null 2>&1; then
  echo "gcloud CLI is required." >&2
  exit 1
fi

ACTIVE_ACCOUNT="$(gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null | head -n 1 || true)"
if [[ -z "${ACTIVE_ACCOUNT}" ]]; then
  echo "No active Google Cloud login was found."
  echo "Run: gcloud auth login"
  exit 1
fi

if [[ -z "${PROJECT_ID}" || "${PROJECT_ID}" == "(unset)" ]]; then
  read -r -p "GCP project ID: " PROJECT_ID
fi

if [[ -z "${PROJECT_ID}" ]]; then
  echo "GCP project ID is required." >&2
  exit 1
fi

export PROJECT_ID REGION SERVICE_NAME
gcloud config set project "${PROJECT_ID}" >/dev/null

echo "Project: ${PROJECT_ID}"
echo "Region:  ${REGION}"
echo "Service: ${SERVICE_NAME}"
echo ""

# Store Gemini key safely in Secret Manager. The helper prompts with hidden input
# when GEMINI_API_KEY is not already exported.
bash configure_gemini_secret.sh

# Deploy the Streamlit app. This creates/uses the dedicated runtime service
# account and attaches the Gemini secret.
sh deploy_cloud_run.sh

URL="$(gcloud run services describe "${SERVICE_NAME}"   --project "${PROJECT_ID}"   --region "${REGION}"   --format='value(status.url)')"

SA_EMAIL="page-traffic-report@${PROJECT_ID}.iam.gserviceaccount.com"

echo ""
echo "Checking Streamlit health..."
ok=0
for _ in $(seq 1 12); do
  if curl -fsS "${URL}/_stcore/health" >/dev/null 2>&1; then
    ok=1
    break
  fi
  sleep 5
done

if [[ "${ok}" -eq 1 ]]; then
  echo "Health check: OK"
else
  echo "Health check: not confirmed yet. Open the URL manually."
fi

echo ""
echo "========================================"
echo "Cloud Run: ${URL}"
echo "GSC Service Account: ${SA_EMAIL}"
echo "========================================"
echo ""
echo "Final manual step:"
echo "Add the GSC Service Account above as a user of the Samsung JP Search Console property."
