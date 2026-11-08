import importlib.util
import shutil
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(shutil.which("dbt") is None or importlib.util.find_spec("dbt.adapters.bigquery") is None,
                                reason="dbt-bigquery not installed")


def test_all_models_and_tests_compile_to_valid_bigquery_sql():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from validate_bigquery_sql import validate

    n, errors = validate()
    assert n > 50 and errors == []
