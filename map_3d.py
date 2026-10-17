"""On-demand Cesium view; consumes the same immutable snapshot as Leaflet."""
import json
from pathlib import Path
from html_transport import compressed_document


def build_3d_html(**payload):
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    script = Path(__file__).with_suffix(".js").read_text()
    return compressed_document("""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/cesium@1.124.0/Build/Cesium/Widgets/widgets.css">
<style>
html,body,#globe{height:100%;margin:0;font-family:system-ui,sans-serif;font-size:14px}
.panel{position:absolute;background:white;color:#172033;border-radius:8px;padding:12px;z-index:2;box-shadow:0 2px 12px #0003}
#legend{right:12px;top:12px;max-width:520px} .legend-row{display:flex;gap:12px;flex-wrap:wrap;margin-top:7px}
.legend-row span{display:inline-flex;align-items:center;gap:5px}.legend-row svg{width:14px;height:14px}
#detail{right:12px;max-width:380px;max-height:65%;overflow:auto;display:none}
#detail .row{display:flex;justify-content:space-between;gap:18px;margin:7px 0}
#detail .field-name{font-weight:bold;margin-bottom:10px}#detail .basis{display:none}
#dates{left:12px;bottom:30px;white-space:pre-line;pointer-events:none}
#status{left:12px;top:12px;max-width:340px}#status:empty{display:none}
.cesium-widget-credits{font-size:11px!important;color:gray!important}
.cesium-viewer-bottom{left:auto!important;right:10px;text-align:right}
button{font:inherit;cursor:pointer}#close{float:right;margin-left:10px}
</style></head><body><div id="globe"></div><div id="legend" class="panel"></div>
<div id="detail" class="panel"><button id="close" aria-label="关闭详情">×</button><div id="content"></div></div>
<div id="dates" class="panel"></div><div id="status" class="panel">正在载入三维地图…</div>
<script>window.CESIUM_BASE_URL='https://cdn.jsdelivr.net/npm/cesium@1.124.0/Build/Cesium/';</script>
<script src="https://cdn.jsdelivr.net/npm/cesium@1.124.0/Build/Cesium/Cesium.js" onerror="document.getElementById('status').textContent='三维引擎加载失败，请检查网络后重新打开三维视图。'"></script>
<script>const payload=""" + data + ";\n" + script + "</script></body></html>")
