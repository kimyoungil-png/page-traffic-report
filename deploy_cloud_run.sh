#!/bin/sh
set -eu

SERVICE_NAME="${SERVICE_NAME:-page-traffic-report}"
REGION="${REGION:-asia-northeast1}"
TIMEOUT="${TIMEOUT:-900}"
MEMORY="${MEMORY:-1Gi}"
SERVICE_ACCOUNT_NAME="${SERVICE_ACCOUNT_NAME:-page-traffic-report}"
GEMINI_SECRET_NAME="${GEMINI_SECRET_NAME:-page-traffic-report-gemini-api-key}"
GSC_USER_SECRET_NAME="${GSC_USER_SECRET_NAME:-page-traffic-report-gsc-user-oauth}"
PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}"

if ! command -v gcloud >/dev/null 2>&1; then
  echo "gcloud CLI is required" >&2
  exit 1
fi

if [ -z "$PROJECT_ID" ] || [ "$PROJECT_ID" = "(unset)" ]; then
  echo "Set PROJECT_ID or run: gcloud config set project YOUR_PROJECT_ID" >&2
  exit 1
fi

if ! gcloud projects describe "$PROJECT_ID" >/dev/null 2>&1; then
  echo "ERROR: You do not have access to GCP project: $PROJECT_ID" >&2
  exit 2
fi

if [ ! -f "templates/explore_dotcom_sample_v2.pptx" ]; then
  echo "PowerPoint template is missing: templates/explore_dotcom_sample_v2.pptx" >&2
  exit 1
fi

# Enable what we can. Some corporate accounts cannot enable APIs; in that case
# deployment may still work if the APIs are already enabled.
gcloud services enable   run.googleapis.com   cloudbuild.googleapis.com   artifactregistry.googleapis.com   secretmanager.googleapis.com   iam.googleapis.com   searchconsole.googleapis.com   --project "$PROJECT_ID" >/dev/null 2>&1 || true

SERVICE_ACCOUNT_EMAIL="$SERVICE_ACCOUNT_NAME@$PROJECT_ID.iam.gserviceaccount.com"
USE_DEDICATED_SA=0

if gcloud iam service-accounts describe "$SERVICE_ACCOUNT_EMAIL"   --project "$PROJECT_ID" >/dev/null 2>&1; then
  USE_DEDICATED_SA=1
else
  echo "Dedicated runtime service account does not exist."
  echo "Trying to create: $SERVICE_ACCOUNT_EMAIL"
  if gcloud iam service-accounts create "$SERVICE_ACCOUNT_NAME"     --project "$PROJECT_ID"     --display-name "Page Traffic Report" >/dev/null 2>&1; then
    USE_DEDICATED_SA=1
    echo "Created dedicated runtime service account."
  else
    echo "No permission to create a Service Account."
    echo "Falling back to the project's default Cloud Run runtime identity."
  fi
fi

set --   "$SERVICE_NAME"   --project "$PROJECT_ID"   --source .   --region "$REGION"   --allow-unauthenticated   --timeout "$TIMEOUT"   --memory "$MEMORY"   --cpu 1   --concurrency 10   --max-instances 5   --set-env-vars "TZ=Asia/Tokyo,GSC_SITE_URL=https://www.samsung.com/jp/"

if [ "$USE_DEDICATED_SA" -eq 1 ]; then
  set -- "$@" --service-account "$SERVICE_ACCOUNT_EMAIL"
fi

# Attach Gemini only when a preconfigured secret exists and the runtime identity
# can read it. Otherwise deploy normally; the app uses its rule-based fallback.
if gcloud secrets describe "$GSC_USER_SECRET_NAME" --project "$PROJECT_ID" >/dev/null 2>&1; then
  if [ "$USE_DEDICATED_SA" -eq 1 ]; then
    gcloud secrets add-iam-policy-binding "$GSC_USER_SECRET_NAME" \
      --project "$PROJECT_ID" \
      --member "serviceAccount:$SERVICE_ACCOUNT_EMAIL" \
      --role "roles/secretmanager.secretAccessor" >/dev/null 2>&1 || true
  fi
  set -- "$@" --set-secrets "GSC_AUTHORIZED_USER_JSON=$GSC_USER_SECRET_NAME:latest"
fi

if gcloud secrets describe "$GEMINI_SECRET_NAME" --project "$PROJECT_ID" >/dev/null 2>&1; then
  if [ "$USE_DEDICATED_SA" -eq 1 ]; then
    gcloud secrets add-iam-policy-binding "$GEMINI_SECRET_NAME"       --project "$PROJECT_ID"       --member "serviceAccount:$SERVICE_ACCOUNT_EMAIL"       --role "roles/secretmanager.secretAccessor" >/dev/null 2>&1 || true
  fi
  set -- "$@" --set-secrets "GEMINI_API_KEY=$GEMINI_SECRET_NAME:latest"
fi

gcloud run deploy "$@"

URL="$(gcloud run services describe "$SERVICE_NAME"   --project "$PROJECT_ID"   --region "$REGION"   --format 'value(status.url)')"

RUNTIME_SA="$(gcloud run services describe "$SERVICE_NAME"   --project "$PROJECT_ID"   --region "$REGION"   --format 'value(spec.template.spec.serviceAccountName)' 2>/dev/null || true)"

if [ -z "$RUNTIME_SA" ]; then
  PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
  RUNTIME_SA="$PROJECT_NUMBER-compute@developer.gserviceaccount.com"
fi

echo ""
echo "Cloud Run URL:"
echo "$URL"
echo ""
echo "Runtime Service Account:"
echo "$RUNTIME_SA"
