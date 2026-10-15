"""Start the complete Streamlit app with production imports and persisted data."""
import os
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]


class AppStartupTest(unittest.TestCase):
    def test_cold_start_with_unavailable_sources_displays_cached_app_without_exception(self):
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "monitoring.duckdb"
            shutil.copy2(ROOT / "runtime" / "monitoring.duckdb", database)
            env = {**os.environ,
                   "MONITORING_DB_PATH": str(database),
                   "XDG_CACHE_HOME": str(Path(temporary) / "cache"),
                   "XDG_STATE_HOME": str(Path(temporary) / "state")}
            script = textwrap.dedent("""
                from unittest.mock import patch
                from urllib.error import URLError
                from streamlit.testing.v1 import AppTest

                with patch('urllib.request.urlopen', side_effect=URLError('offline startup check')) as upstream:
                    app = AppTest.from_file('app.py').run(timeout=30)
                    assert not app.exception, [str(error.value) for error in app.exception]
                    assert len(app.checkbox) >= 3
                    assert any(element.label == '保存地图PNG' for element in app.button)
                    assert not any(element.label in ('刷新港口数据', '刷新船舶数据') for element in app.button)
                    app.session_state['main_tabs'] = '船舶'
                    app.run(timeout=30)
                    assert not app.exception, [str(error.value) for error in app.exception]
                    app.session_state['main_tabs'] = '数据下载'
                    app.run(timeout=30)
                    assert not app.exception, [str(error.value) for error in app.exception]
                    assert any(element.label == '生成下载数据' for element in app.button)
                    assert not any(element.label == '刷新 PortWatch 数据' for element in app.button)
                    next(element for element in app.button if element.label == '生成下载数据').click()
                    app.run(timeout=30)
                    assert not app.exception, [str(error.value) for error in app.exception]
                    assert not app.error, [str(error.value) for error in app.error]
                    assert upstream.call_count == 0, upstream.call_args_list
                    import data_store
                    assert data_store.read_only()
                    try:
                        data_store.set_meta('forbidden', True)
                    except Exception as error:
                        assert 'read-only' in str(error).lower(), str(error)
                    else:
                        raise AssertionError('App database permits writes')
            """)
            before = hashlib.sha256(database.read_bytes()).hexdigest()
            result = subprocess.run(
                [sys.executable, "-c", script], cwd=ROOT, env=env,
                capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(hashlib.sha256(database.read_bytes()).hexdigest(), before)
            self.assertFalse(database.with_suffix(".duckdb.lock").exists())


if __name__ == "__main__":
    unittest.main()
