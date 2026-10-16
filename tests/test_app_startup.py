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
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


class AppStartupTest(unittest.TestCase):
    def test_cold_start_with_unavailable_sources_displays_cached_app_without_exception(self):
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "monitoring.duckdb"
            shutil.copy2(ROOT / "runtime" / "monitoring.duckdb", database)
            # Model the candidate published with this code version, including
            # the new source document; the app itself must never import it.
            import data_store
            with patch.dict(os.environ, {"MONITORING_DB_PATH": str(database), "MONITORING_READ_ONLY": "false"}):
                data_store.ingest_document("data/oil_pipelines.geojson")
                data_store.ingest_document("data/pipeline_capacity_review.json")
                data_store.ingest_document("data/uae_gas_connections.geojson")
                data_store.ingest_document("data/bilingual_names.json")
                for kind in ("assets", "ports", "chokepoints"):
                    data_store.save_catalog(kind, data_store.load_catalog(kind))
            database.with_suffix(".duckdb.lock").unlink(missing_ok=True)
            env = {**os.environ,
                   "MONITORING_DB_PATH": str(database),
                   "XDG_CACHE_HOME": str(Path(temporary) / "cache"),
                   "XDG_STATE_HOME": str(Path(temporary) / "state")}
            script = textwrap.dedent("""
                from unittest.mock import patch
                from urllib.error import URLError
                from streamlit.testing.v1 import AppTest
                from datetime import date

                with patch('urllib.request.urlopen', side_effect=URLError('offline startup check')) as upstream:
                    app = AppTest.from_file('app.py').run(timeout=30)
                    assert not app.exception, [str(error.value) for error in app.exception]
                    assert len(app.checkbox) >= 3
                    assert any(element.label == '输油管线' for element in app.checkbox)
                    assert any(element.label == '输气管线' for element in app.checkbox)
                    assert not any(element.label == '输气联络' for element in app.checkbox)
                    assert not app.error, [str(error.value) for error in app.error]
                    assert any(element.label == '保存图片' for element in app.button)
                    assert not any(element.label in ('刷新港口数据', '刷新船舶数据') for element in app.button)
                    assert app.date_input(key='map_snapshot_day').value is None
                    app.date_input(key='map_snapshot_day').set_value(date(2020, 1, 2))
                    app.run(timeout=30)
                    assert not app.exception, [str(error.value) for error in app.exception]
                    assert not app.error, [str(error.value) for error in app.error]
                    assert app.date_input(key='map_snapshot_day').value == date(2020, 1, 2)
                    app.session_state['main_tabs'] = '船舶'
                    app.run(timeout=30)
                    assert not app.exception, [str(error.value) for error in app.exception]
                    assert app.date_input(key='map_snapshot_day').value == date(2020, 1, 2)
                    assert app.metric[0].value == '—', app.metric[0].value
                    app.date_input(key='map_snapshot_day').set_value(None)
                    app.run(timeout=30)
                    assert not app.exception, [str(error.value) for error in app.exception]
                    assert app.date_input(key='map_snapshot_day').value is None
                    assert app.date_input(key='map_snapshot_day').label == '选择日期'
                    app.session_state['main_tabs'] = '港口'
                    app.run(timeout=30)
                    assert not app.exception, [str(error.value) for error in app.exception]
                    assert len(app.metric) == 8
                    assert app.metric[0].label == '港口总数'
                    assert app.metric[1].label.startswith('当日进港艘次（')
                    assert app.metric[2].label.startswith('本周累计艘次（')
                    assert not any(h.value == '港口日活动' for h in app.subheader)
                    assert len(app.image) == 6  # Titles are inside the Ts figures.
                    chart_downloads = [b for b in app.get('download_button') if b.label == '下载数据']
                    assert len(chart_downloads) == 6
                    assert all(b.proto.type == 'primary' for b in chart_downloads)
                    assert app.selectbox(key='port_chart_period').value == '近1年'
                    assert app.selectbox(key='port_chart_period').options == ['近1周','近1个月','近1个季度','近半年','近1年','近3年','近5年','近10年','全部']
                    assert list(app.dataframe[0].value.columns)[:8] == ['港口名','港口类型','国家','水域','日期','经营状态','当日进港艘次','本周累计艘次']
                    assert len(app.dataframe[0].value.columns) == 22
                    assert not app.dataframe[0].value['港口类型'].isin(['待核实', '未知', '']).any()
                    assert '本月累计艘次' in app.dataframe[0].value.columns
                    assert '本月油轮/液货船累计艘次' in app.dataframe[0].value.columns
                    assert any(b.label == '下载列表' for b in app.get('download_button'))
                    assert not any(b.label == '下载所列港口历史' for b in app.button)
                    assert set(app.dataframe[0].value['经营状态']) <= {'正常','停运','未知'}
                    assert all(any('\u4e00' <= ch <= '\u9fff' for ch in value) for value in app.dataframe[0].value['国家'])
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
                capture_output=True, text=True, timeout=90,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(hashlib.sha256(database.read_bytes()).hexdigest(), before)
            self.assertFalse(database.with_suffix(".duckdb.lock").exists())


if __name__ == "__main__":
    unittest.main()
