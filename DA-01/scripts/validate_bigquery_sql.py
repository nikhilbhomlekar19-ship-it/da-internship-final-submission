#!/usr/bin/env python
"""Offline check of the BigQuery target: compile the whole dbt project for BigQuery (no credentials, no network - a throw-away
service-account key is generated on the fly) and parse every compiled model/test with sqlglot's BigQuery dialect.

It proves the generated SQL is syntactically valid BigQuery; it does NOT execute it.  Run:  python scripts/validate_bigquery_sql.py
"""
from __future__ import annotations

import glob
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fake_key(path: str) -> None:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    pem = rsa.generate_private_key(public_exponent=65537, key_size=2048).private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    json.dump({"type": "service_account", "project_id": "demo-project", "private_key_id": "x", "private_key": pem,
               "client_email": "fake@demo-project.iam.gserviceaccount.com", "client_id": "1",
               "token_uri": "https://oauth2.googleapis.com/token"}, open(path, "w"))


def validate() -> tuple[int, list[str]]:
    import sqlglot

    with tempfile.TemporaryDirectory() as tmp:
        key = os.path.join(tmp, "key.json")
        fake_key(key)
        env = {**os.environ, "C360_TARGET": "bigquery", "GCP_PROJECT": "demo-project", "DBT_BQ_METHOD": "service-account", "GOOGLE_APPLICATION_CREDENTIALS": key}
        target = os.path.join(tmp, "target")
        cmd = ["dbt", "compile", "--target", "bigquery", "--no-populate-cache", "--target-path", target,
               "--project-dir", str(ROOT / "dbt_project"), "--profiles-dir", str(ROOT / "dbt_project")]
        r = subprocess.run(cmd, env=env, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(r.stdout[-2000:] + r.stderr[-2000:])
        files = sorted(glob.glob(f"{target}/compiled/**/*.sql", recursive=True))
        errors = []
        for f in files:
            try:
                sqlglot.parse(open(f).read(), read="bigquery")
            except Exception as ex:  # noqa: BLE001
                errors.append(f"{os.path.basename(f)}: {str(ex)[:200]}")
        return len(files), errors


if __name__ == "__main__":
    n, errs = validate()
    print(f"Compiled and parsed {n} SQL files for BigQuery; {len(errs)} problems")
    for e in errs:
        print("  -", e)
    sys.exit(1 if errs else 0)
