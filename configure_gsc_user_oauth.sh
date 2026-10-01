#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="${SERVICE_NAME:-page-traffic-report}"
REGION="${REGION:-asia-northeast1}"
SECRET_NAME="${GSC_USER_SECRET_NAME:-page-traffic-report-gsc-user-oauth}"
PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}"
SCOPES="https://www.googleapis.com/auth/cloud-platform,https://www.googleapis.com/auth/webmasters.readonly"

if ! command -v gcloud >/dev/null 2>&1; then
  echo "gcloud CLI is required." >&2
  exit 1
fi

if [[ -z "${PROJECT_ID}" || "${PROJECT_ID}" == "(unset)" ]]; then
  echo "Set PROJECT_ID first." >&2
  exit 1
fi

if [[ -z "${GSC_OAUTH_CLIENT_FILE:-}" ]]; then
  read -r -p "Path to Google OAuth Desktop client JSON: " GSC_OAUTH_CLIENT_FILE
fi

if [[ ! -f "${GSC_OAUTH_CLIENT_FILE}" ]]; then
  echo "OAuth client JSON not found: ${GSC_OAUTH_CLIENT_FILE}" >&2
  exit 1
fi

echo "Opening Google login for the existing GSC user..."
gcloud auth application-default login \
  --client-id-file="${GSC_OAUTH_CLIENT_FILE}" \
  --scopes="${SCOPES}"

ADC_FILE="${HOME}/.config/gcloud/application_default_credentials.json"
if [[ ! -f "${ADC_FILE}" ]]; then
  echo "ADC file was not created: ${ADC_FILE}" >&2
  exit 1
fi

gcloud services enable secretmanager.googleapis.com --project "${PROJECT_ID}" >/dev/null 2>&1 || true

if ! gcloud secrets describe "${SECRET_NAME}" --project "${PROJECT_ID}" >/dev/null 2>&1; then
  gcloud secrets create "${SECRET_NAME}" \
    --project "${PROJECT_ID}" \
    --replication-policy automatic
fi

gcloud secrets versions add "${SECRET_NAME}" \
  --project "${PROJECT_ID}" \
  --data-file="${ADC_FILE}"

RUNTIME_SA="$(gcloud run services describe "${SERVICE_NAME}" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --format='value(spec.template.spec.serviceAccountName)' 2>/dev/null || true)"

if [[ -z "${RUNTIME_SA}" ]]; then
  PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')"
  RUNTIME_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
fi

gcloud secrets add-iam-policy-binding "${SECRET_NAME}" \
  --project "${PROJECT_ID}" \
  --member "serviceAccount:${RUNTIME_SA}" \
  --role "roles/secretmanager.secretAccessor" >/dev/null

gcloud run services update "${SERVICE_NAME}" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --update-secrets "GSC_AUTHORIZED_USER_JSON=${SECRET_NAME}:latest" >/dev/null

echo ""
echo "GSC OAuth configured."
echo "Cloud Run will now query Search Console as the Google user who completed the login."
echo "No Search Console user-management permission is required."
