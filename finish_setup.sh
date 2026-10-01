#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}"
export PROJECT_ID

if [[ -z "${PROJECT_ID}" || "${PROJECT_ID}" == "(unset)" ]]; then
  echo "Set PROJECT_ID first." >&2
  exit 1
fi

echo "=== 1/4 Deploy report app ==="
sh deploy_cloud_run.sh

echo ""
echo "=== 2/4 Deploy browser helper ==="
bash deploy_browser_helper.sh

echo ""
echo "=== 3/4 Configure Gemini ==="
if gcloud secrets describe page-traffic-report-gemini-api-key --project "${PROJECT_ID}" >/dev/null 2>&1; then
  echo "Gemini secret already exists; keeping current secret."
else
  echo "Gemini API key is not configured yet."
  echo "You can paste it safely now (input is hidden)."
  bash configure_gemini_secret.sh
fi

echo ""
echo "=== 4/4 Security ==="
if [[ "${ENABLE_IAP:-0}" == "1" ]]; then
  bash secure_cloud_run_iap.sh
else
  echo "IAP not enabled in this run."
  echo "After confirming the app works, run:"
  echo "  ENABLE_IAP=1 bash finish_setup.sh"
fi

echo ""
echo "Setup complete."
