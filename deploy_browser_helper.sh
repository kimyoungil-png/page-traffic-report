#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}"
REGION="${REGION:-asia-northeast1}"
BROWSER_SERVICE="${BROWSER_SERVICE:-page-traffic-browser-api}"
REPORT_SERVICE="${REPORT_SERVICE:-page-traffic-report}"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

if [[ -z "${PROJECT_ID}" || "${PROJECT_ID}" == "(unset)" ]]; then
  echo "Set PROJECT_ID first." >&2
  exit 1
fi

echo "Deploying browser helper to project: ${PROJECT_ID}"

git clone --depth 1 https://github.com/kimyoungil-png/technical-seo-unlighthouse-api.git "${TMP_DIR}/browser-api"

gcloud run deploy "${BROWSER_SERVICE}" \
  --project "${PROJECT_ID}" \
  --source "${TMP_DIR}/browser-api" \
  --region "${REGION}" \
  --allow-unauthenticated \
  --memory 1Gi \
  --cpu 1 \
  --concurrency 4 \
  --timeout 120 \
  --max-instances 3

BROWSER_URL="$(gcloud run services describe "${BROWSER_SERVICE}" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --format='value(status.url)')"

SCREENSHOT_API_URL="${BROWSER_URL}/screenshot"

echo "Updating ${REPORT_SERVICE} to use: ${SCREENSHOT_API_URL}"

gcloud run services update "${REPORT_SERVICE}" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --update-env-vars "SCREENSHOT_API_URL=${SCREENSHOT_API_URL}"

echo ""
echo "Browser helper deployed."
echo "Screenshot + browser title endpoint: ${SCREENSHOT_API_URL}"
echo "Page Traffic Report now uses Chromium-rendered titles."
