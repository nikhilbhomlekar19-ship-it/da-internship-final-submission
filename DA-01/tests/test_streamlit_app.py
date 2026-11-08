import importlib.util
from pathlib import Path

import pytest

from customer360 import config as cfg

APP = str(Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py")
DEMO_DB = Path(APP).parent / "demo.duckdb"  # slim database shipped with the repo (the app falls back to it)

pytestmark = pytest.mark.skipif(importlib.util.find_spec("streamlit") is None or not (cfg.DUCKDB_PATH.exists() or DEMO_DB.exists()),
                                reason="needs streamlit and a database (run `make demo` or use the shipped app/demo.duckdb)")
PAGES = ["Overview", "Attribution models", "Campaign ROI", "Budget recommendation", "Customer 360", "Data quality"]


@pytest.mark.parametrize("page", PAGES)
def test_every_page_renders_without_exceptions(page):
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(APP, default_timeout=60).run()
    at.sidebar.radio[0].set_value(page).run()
    assert not at.exception, [e.value for e in at.exception]
