"""Tiny warehouse abstraction so the same Python steps run on DuckDB (local demo) and BigQuery (real GA4 sample)."""
from __future__ import annotations

import pandas as pd

from . import config as cfg


class Warehouse:
    def __init__(self, target: str | None = None, read_only: bool = False):
        self.target = (target or cfg.TARGET).lower()
        if self.target == "duckdb":
            import duckdb

            cfg.DUCKDB_PATH.parent.mkdir(parents=True, exist_ok=True)
            self.con = duckdb.connect(str(cfg.DUCKDB_PATH), read_only=read_only)
        elif self.target == "bigquery":
            from google.cloud import bigquery

            self.bq = bigquery
            self.client = bigquery.Client(project=cfg.GCP_PROJECT or None, location=cfg.BQ_LOCATION)
            self.project = self.client.project
        else:
            raise ValueError(f"Unknown target {self.target!r} (use duckdb or bigquery)")

    # ------------------------------------------------------------------ helpers
    def fq(self, schema: str, table: str) -> str:
        """Fully-qualified, quoted table name."""
        if self.target == "duckdb":
            return f"{schema}.{table}"
        return f"`{self.project}.{schema}.{table}`"

    def ensure_schema(self, schema: str) -> None:
        if self.target == "duckdb":
            self.con.execute(f"create schema if not exists {schema}")
        else:
            ds = self.bq.Dataset(f"{self.project}.{schema}")
            ds.location = cfg.BQ_LOCATION
            self.client.create_dataset(ds, exists_ok=True)

    def table_exists(self, schema: str, table: str) -> bool:
        if self.target == "duckdb":
            n = self.con.execute(
                "select count(*) from information_schema.tables where table_schema=? and table_name=?",
                [schema, table],
            ).fetchone()[0]
            return n > 0
        from google.api_core.exceptions import NotFound

        try:
            self.client.get_table(f"{self.project}.{schema}.{table}")
            return True
        except NotFound:
            return False

    # ------------------------------------------------------------------ read / write
    def query(self, sql: str) -> pd.DataFrame:
        if self.target == "duckdb":
            return self.con.execute(sql).df()
        return self.client.query(sql).to_dataframe(create_bqstorage_client=False)

    def execute(self, sql: str) -> None:
        if self.target == "duckdb":
            self.con.execute(sql)
        else:
            self.client.query(sql).result()

    def read_table(self, schema: str, table: str) -> pd.DataFrame:
        return self.query(f"select * from {self.fq(schema, table)}")

    def write_df(self, df: pd.DataFrame, schema: str, table: str) -> None:
        """Create-or-replace a table from a DataFrame."""
        self.ensure_schema(schema)
        if self.target == "duckdb":
            self.con.register("_df_in", df)
            self.con.execute(f"create or replace table {schema}.{table} as select * from _df_in")
            self.con.unregister("_df_in")
            return
        df = df.copy()
        for c in df.columns:  # naive datetimes -> tz-aware UTC so BigQuery creates TIMESTAMP columns
            if pd.api.types.is_datetime64_any_dtype(df[c]) and getattr(df[c].dt, "tz", None) is None:
                df[c] = df[c].dt.tz_localize("UTC")
        job = self.client.load_table_from_dataframe(
            df,
            f"{self.project}.{schema}.{table}",
            job_config=self.bq.LoadJobConfig(write_disposition="WRITE_TRUNCATE"),
        )
        job.result()

    def load_ga4_jsonl(self, path: str, schema: str, table: str = "ga4_events") -> int:
        """DuckDB only: load simulator output (GA4 export schema, nested) from newline-delimited JSON."""
        assert self.target == "duckdb", "synthetic GA4 events are only loaded locally; BigQuery uses the public sample"
        self.ensure_schema(schema)
        cols = (
            "{'event_date':'VARCHAR','event_timestamp':'BIGINT','event_name':'VARCHAR',"
            "'event_params':'STRUCT(key VARCHAR, value STRUCT(string_value VARCHAR, int_value BIGINT, "
            "float_value DOUBLE, double_value DOUBLE))[]',"
            "'user_id':'VARCHAR','user_pseudo_id':'VARCHAR','user_first_touch_timestamp':'BIGINT',"
            "'device':'STRUCT(category VARCHAR, operating_system VARCHAR, web_info STRUCT(browser VARCHAR))',"
            "'geo':'STRUCT(country VARCHAR, region VARCHAR, city VARCHAR)',"
            "'traffic_source':'STRUCT(name VARCHAR, medium VARCHAR, source VARCHAR)',"
            "'ecommerce':'STRUCT(total_item_quantity BIGINT, purchase_revenue_in_usd DOUBLE, "
            "purchase_revenue DOUBLE, unique_items BIGINT, transaction_id VARCHAR)',"
            "'platform':'VARCHAR','stream_id':'VARCHAR'}"
        )
        self.con.execute(
            f"create or replace table {schema}.{table} as "
            f"select * from read_json('{path}', format='newline_delimited', columns={cols})"
        )
        return self.con.execute(f"select count(*) from {schema}.{table}").fetchone()[0]

    def close(self) -> None:
        if self.target == "duckdb":
            self.con.close()
        else:
            self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
