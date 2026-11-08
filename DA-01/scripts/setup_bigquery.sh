#!/usr/bin/env bash
# One-time GCP setup for the BigQuery target. Usage:  GCP_PROJECT=my-project ./scripts/setup_bigquery.sh
set -euo pipefail
: "${GCP_PROJECT:?set GCP_PROJECT}"
LOCATION="${BQ_LOCATION:-US}"      # the GA4 public sample is in the US multi-region -> your datasets must be US too
SA="c360-dbt"

gcloud config set project "$GCP_PROJECT"
gcloud services enable bigquery.googleapis.com

# datasets (same names the project uses everywhere)
for ds in c360_raw c360_ml c360_truth c360_staging c360_intermediate c360_marts; do
  bq --location="$LOCATION" mk --dataset --if_not_exists "${GCP_PROJECT}:${ds}"
done

# service account for dbt / python (skip if you use `gcloud auth application-default login`)
if ! gcloud iam service-accounts describe "${SA}@${GCP_PROJECT}.iam.gserviceaccount.com" >/dev/null 2>&1; then
  gcloud iam service-accounts create "$SA" --display-name "Customer360 dbt runner"
fi
for role in roles/bigquery.dataEditor roles/bigquery.jobUser; do
  gcloud projects add-iam-policy-binding "$GCP_PROJECT" --member "serviceAccount:${SA}@${GCP_PROJECT}.iam.gserviceaccount.com" --role "$role" --quiet >/dev/null
done
echo "Optional key (keep it OUT of git):"
echo "  gcloud iam service-accounts keys create ~/c360-key.json --iam-account ${SA}@${GCP_PROJECT}.iam.gserviceaccount.com"

# sanity check: can we read the public GA4 sample?
bq query --use_legacy_sql=false --location="$LOCATION" \
  'select count(*) as events, count(distinct user_pseudo_id) as users from `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*` where _table_suffix between "20201101" and "20210131"'
echo "BigQuery is ready. Next:  make bq-load && make bq-demo"
