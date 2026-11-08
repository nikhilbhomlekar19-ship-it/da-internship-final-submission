# Customer 360 & Marketing Attribution Platform
#   make demo        local end-to-end run on DuckDB (synthetic GA4-shaped data)        ~1 minute
#   make bq-demo     same pipeline on BigQuery using the REAL GA4 public sample          (needs GCP_PROJECT + auth)
SHELL := /bin/bash
PY    ?= python
TARGET ?= duckdb
SCALE ?= medium
export C360_TARGET := $(TARGET)
export C360_DUCKDB_PATH := $(abspath data/c360.duckdb)
export PYTHONPATH := $(abspath .)
DBT = dbt $(1) --project-dir dbt_project --profiles-dir dbt_project --target $(TARGET)

.PHONY: help setup demo bq-demo generate dbt-stage1 identity clv dbt-stage2 recommend evaluate report export test test-fast dbt-test bq-validate app docs clean

help:            ## list targets
	@grep -E '^[a-zA-Z_-]+:.*##' Makefile | sed 's/:.*##/ -/' | sort

setup:           ## create a virtualenv and install everything
	$(PY) -m venv .venv && . .venv/bin/activate && pip install -U pip && pip install -r requirements.txt
	@echo "Activate with: source .venv/bin/activate"

demo:            ## full local pipeline (generate -> dbt -> identity -> CLV -> dbt marts+tests -> budget -> evaluate -> report -> export)
	$(PY) -m customer360.pipeline --scale $(SCALE) --target duckdb

bq-demo:         ## full pipeline on BigQuery with the real GA4 sample (run `make bq-load` once first)
	C360_TARGET=bigquery $(PY) -m customer360.pipeline --target bigquery --skip-generate

bq-load:         ## build synthetic CRM / Segment / ads around the real GA4 users and load them into BigQuery
	C360_TARGET=bigquery $(PY) -m customer360 generate-bq

# ---- individual steps (same order as the pipeline) --------------------------------------------------------
generate:        ## simulate + load raw tables into DuckDB
	$(PY) -m customer360 generate --scale $(SCALE)
dbt-stage1:      ## seeds + staging + identity edges (and their tests)
	$(call DBT,seed)
	$(call DBT,build) --select +int_identity_edges
identity:        ## python: edges -> persons (ml.identity_nodes)
	$(PY) -m customer360 identity
clv:             ## python: BG/NBD + Gamma-Gamma forecast (ml.clv_forecast) + back-test
	$(PY) -m customer360 clv
dbt-stage2:      ## everything downstream: sessions, orders, profile, RFM, attribution, ROI (+ tests)
	$(call DBT,build) --exclude +int_identity_edges
recommend:       ## python: response curves + budget plan
	$(PY) -m customer360 recommend
evaluate:        ## accuracy / reconciliation metrics -> reports/metrics.json
	$(PY) -m customer360 evaluate
report:          ## figures + reports/findings.md
	$(PY) -m customer360 report
export:          ## CSV extracts for Tableau
	$(PY) -m customer360 export

# ---- quality ------------------------------------------------------------------------------------------------
test:            ## pytest (unit + integration) + dbt unit tests
	$(PY) -m pytest -q
	$(call DBT,test) --select "test_type:unit"
test-fast:       ## pytest without the end-to-end integration test
	$(PY) -m pytest -q -m "not integration"
dbt-test:        ## all dbt data + unit tests on the built models
	$(call DBT,test)
bq-validate:     ## compile the project for BigQuery offline and syntax-check every SQL file (no credentials needed)
	$(PY) scripts/validate_bigquery_sql.py

app:             ## Streamlit demo
	streamlit run app/streamlit_app.py
docs:            ## dbt docs site (lineage graph) at http://localhost:8080
	dbt docs generate --project-dir dbt_project --profiles-dir dbt_project --target $(TARGET)
	dbt docs serve --port 8080 --project-dir dbt_project --profiles-dir dbt_project --target $(TARGET)
clean:           ## remove generated data and build artefacts (keeps reports/ and exports/)
	rm -rf data/*.duckdb* data/raw dbt_project/target dbt_project/logs .pytest_cache
