#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="${SERVICE_NAME:-page-traffic-report}"
REGION="${REGION:-asia-northeast1}"
SERVICE_ACCOUNT_NAME="${SERVICE_ACCOUNT_NAME:-page-traffic-report}"
SECRET_NAME="${APP_PASSWORD_SECRET_NAME:-page-traffic-report-app-password}"
PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}"
REDEPLOY_SOURCE="${REDEPLOY_SOURCE:-1}"
ACCESS_MODE="${ACCESS_MODE:-iap}"

if [[ -z "${PROJECT_ID}" || "${PROJECT_ID}" == "(unset)" ]]; then
  echo "Set PROJECT_ID first." >&2
  exit 1
fi

SERVICE_ACCOUNT_EMAIL="${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

if [[ -z "${APP_PASSWORD:-}" ]]; then
  read -r -s -p "App password: " APP_PASSWORD
  echo
fi

if [[ -z "${APP_PASSWORD}" ]]; then
  echo "App password is empty." >&2
  exit 1
fi

gcloud services enable secretmanager.googleapis.com --project "${PROJECT_ID}" >/dev/null

if ! gcloud secrets describe "${SECRET_NAME}" --project "${PROJECT_ID}" >/dev/null 2>&1; then
  gcloud secrets create "${SECRET_NAME}"     --project "${PROJECT_ID}"     --replication-policy automatic
fi

printf '%s' "${APP_PASSWORD}" | gcloud secrets versions add "${SECRET_NAME}"   --project "${PROJECT_ID}"   --data-file=-

gcloud secrets add-iam-policy-binding "${SECRET_NAME}"   --project "${PROJECT_ID}"   --member "serviceAccount:${SERVICE_ACCOUNT_EMAIL}"   --role "roles/secretmanager.secretAccessor" >/dev/null

gcloud run services update "${SERVICE_NAME}"   --project "${PROJECT_ID}"   --region "${REGION}"   --update-secrets "APP_PASSWORD=${SECRET_NAME}:latest"

unset APP_PASSWORD

echo "App password configured."

if [[ "${REDEPLOY_SOURCE}" == "1" && -f "./deploy_cloud_run.sh" ]]; then
  echo "Redeploying latest app source so the password gate code is active..."
  ACCESS_MODE="${ACCESS_MODE}" PROJECT_ID="${PROJECT_ID}" sh ./deploy_cloud_run.sh
fi
