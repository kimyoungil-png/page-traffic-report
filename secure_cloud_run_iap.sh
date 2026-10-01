#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="${SERVICE_NAME:-page-traffic-report}"
REGION="${REGION:-asia-northeast1}"
PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}"

if [[ -z "${PROJECT_ID}" || "${PROJECT_ID}" == "(unset)" ]]; then
  echo "Set PROJECT_ID first." >&2
  exit 1
fi

if [[ -z "${IAP_MEMBER:-}" ]]; then
  ACTIVE_ACCOUNT="$(gcloud auth list --filter=status:ACTIVE --format='value(account)' | head -n 1)"
  if [[ -z "${ACTIVE_ACCOUNT}" ]]; then
    echo "No active gcloud account found." >&2
    exit 1
  fi
  IAP_MEMBER="user:${ACTIVE_ACCOUNT}"
fi

echo "Project: ${PROJECT_ID}"
echo "Service: ${SERVICE_NAME}"
echo "IAP access member: ${IAP_MEMBER}"

gcloud services enable iap.googleapis.com run.googleapis.com --project "${PROJECT_ID}"

# Enable IAP directly on Cloud Run.
gcloud run services update "${SERVICE_NAME}"   --project "${PROJECT_ID}"   --region "${REGION}"   --iap

PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')"
IAP_SA="service-${PROJECT_NUMBER}@gcp-sa-iap.iam.gserviceaccount.com"

gcloud run services add-iam-policy-binding "${SERVICE_NAME}"   --project "${PROJECT_ID}"   --region "${REGION}"   --member "serviceAccount:${IAP_SA}"   --role "roles/run.invoker" >/dev/null

gcloud iap web add-iam-policy-binding   --project "${PROJECT_ID}"   --member "${IAP_MEMBER}"   --role "roles/iap.httpsResourceAccessor"   --region "${REGION}"   --resource-type cloud-run   --service "${SERVICE_NAME}"

echo ""
echo "IAP enabled."
echo "Only principals granted roles/iap.httpsResourceAccessor can open the report app."
echo "To add another user later:"
echo "  IAP_MEMBER='user:someone@example.com' bash secure_cloud_run_iap.sh"
