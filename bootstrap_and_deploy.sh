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

choose_project() {
  mapfile -t PROJECTS < <(gcloud projects list --format='value(projectId)' 2>/dev/null)
  if [[ "${#PROJECTS[@]}" -eq 0 ]]; then
    echo "No accessible Google Cloud projects were found for the current account." >&2
    exit 2
  fi

  echo "Accessible Google Cloud projects:"
  local i=1
  for project in "${PROJECTS[@]}"; do
    name="$(gcloud projects describe "$project" --format='value(name)' 2>/dev/null || true)"
    printf "  %d) %s  %s\n" "$i" "$project" "$name"
    i=$((i + 1))
  done

  echo ""
  read -r -p "Select project number: " choice
  if ! [[ "$choice" =~ ^[0-9]+$ ]] || (( choice < 1 || choice > ${#PROJECTS[@]} )); then
    echo "Invalid selection." >&2
    exit 2
  fi
  PROJECT_ID="${PROJECTS[$((choice - 1))]}"
}

if [[ -z "${PROJECT_ID}" || "${PROJECT_ID}" == "(unset)" ]]; then
  choose_project
elif ! gcloud projects describe "${PROJECT_ID}" >/dev/null 2>&1; then
  echo "Current PROJECT_ID is not accessible: ${PROJECT_ID}"
  echo ""
  choose_project
fi

export PROJECT_ID REGION SERVICE_NAME
gcloud config set project "${PROJECT_ID}" >/dev/null

echo "Project: ${PROJECT_ID}"
echo "Region:  ${REGION}"
echo "Service: ${SERVICE_NAME}"
echo ""

# Deploy first. Corporate GCP accounts often cannot create IAM service accounts;
# deploy_cloud_run.sh automatically falls back to the project default identity.
sh deploy_cloud_run.sh

URL="$(gcloud run services describe "${SERVICE_NAME}"   --project "${PROJECT_ID}"   --region "${REGION}"   --format='value(status.url)')"

RUNTIME_SA="$(gcloud run services describe "${SERVICE_NAME}"   --project "${PROJECT_ID}"   --region "${REGION}"   --format='value(spec.template.spec.serviceAccountName)' 2>/dev/null || true)"

if [[ -z "${RUNTIME_SA}" ]]; then
  PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')"
  RUNTIME_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
fi

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
echo "GSC Service Account: ${RUNTIME_SA}"
echo "========================================"
echo ""
echo "Add the GSC Service Account above as a user of the Samsung JP Search Console property."
echo ""
echo "Gemini is optional for the first deployment."
echo "If GEMINI_API_KEY is not configured, the app will use the rule-based analysis fallback."
