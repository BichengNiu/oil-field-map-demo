"""Pure Leaflet map HTML renderer; UI state stays in the Streamlit page."""
from __future__ import annotations

import html
import json

import map_tools

MAP_LAYER_LABELS = {
    "vessels": "船舶",
    "ports": "港口",
    "assets": "油气",
    "chokepoints": "咽喉点",
}


def build_map_html(assets: list[dict[str, object]], ports: list[dict],
              chokepoints: list[dict], vessels: list[dict], day: str, chokepoint_day: str,
              focus_assets: bool = False, ais_configured: bool = True,
              visible_layers: set[str] | None = None, *,
              asset_popup, port_popup, chokepoint_popup, vessel_popup) -> str:
    visible_layers = set(MAP_LAYER_LABELS) if visible_layers is None else visible_layers
    show_assets = "assets" in visible_layers
    show_ports = "ports" in visible_layers
    show_chokepoints = "chokepoints" in visible_layers
    show_vessels = "vessels" in visible_layers and ais_configured
    markers = [
        {
            "lat": asset["map_lat"],
            "lon": asset["map_lon"],
            "is_proxy": asset.get("map_is_proxy", False),
            "name": f'{asset["name_cn"]} · {asset["name"]}',
            "popup": asset_popup(asset),
        }
        for asset in assets
        if asset["map_drawable"]
    ]
    marker_json = json.dumps(markers, ensure_ascii=False).replace("</", "<\\/")
    port_json = json.dumps([
        {"lat": port["lat"], "lon": port["lon"], "name": port["name"],
         "calls": port.get("portcalls"),
         "popup": port_popup(port, day)}
        for port in ports
    ], ensure_ascii=False).replace("</", "<\\/")
    chokepoint_json = json.dumps([
        {"lat": point["lat"], "lon": point["lon"], "name": point.get("name_cn", point["portname"]),
         "calls": point.get("n_total"),
         "popup": chokepoint_popup(point, chokepoint_day)}
        for point in chokepoints
    ], ensure_ascii=False).replace("</", "<\\/")
    vessel_json = json.dumps([
        {
            "lat": vessel["lat"], "lon": vessel["lon"],
            "name": html.escape(str(vessel.get("name") or f'MMSI {vessel["mmsi"]}')),
            "category": vessel.get("category", "unknown"),
            "course": vessel.get("course") or 0,
            "popup": vessel_popup(vessel),
        }
        for vessel in vessels
    ], ensure_ascii=False).replace("</", "<\\/")
    legend_lines = ["<b>地图符号</b>"]
    def legend_icon(shape: str, color: str, proxy: bool = False) -> str:
        paths = {"asset": "M6 1 L11 6 L6 11 L1 6 Z",
                 "port": "M2 2 H10 V10 H2 Z",
                 "choke": "M3 1 H9 L12 6 L9 11 H3 L0 6 Z",
                 "vessel": "M6 0 L12 12 L6 9 L0 12 Z"}
        stroke = 'stroke="#7c2d12" stroke-dasharray="2 2"' if proxy else ''
        return f'<svg viewBox="0 0 12 12"><path d="{paths[shape]}" fill="{color}" {stroke}/></svg>'

    if show_assets:
        legend_lines.append(f'<span>{legend_icon("asset", "#ea580c")}油气：菱形</span>')
    if show_ports:
        legend_lines.append(f'<span>{legend_icon("port", "#2563eb")}港口：方形</span>')
    if show_chokepoints:
        legend_lines.append(f'<span>{legend_icon("choke", "#7c3aed")}咽喉点：六边形</span>')
    if show_vessels:
        legend_lines.append(f'<span>{legend_icon("vessel", "#64748b")}船舶：三角形</span>')
    if show_assets:
        legend_lines.append(f'<span>{legend_icon("asset", "#ea580c", proxy=True)}油气虚线边：近似坐标</span>')
    if show_vessels:
        legend_lines.extend([
            f'<span>{legend_icon("vessel", "#ef4444")}油轮/液货船　{legend_icon("vessel", "#2563eb")}货船</span>',
            f'<span>{legend_icon("vessel", "#64748b")}其他船舶/船型未知</span>',
        ])
    legend_json = json.dumps("".join(legend_lines), ensure_ascii=False).replace("</", "<\\/")
    focus_json = json.dumps(focus_assets)
    visible_layers_json = json.dumps(sorted(visible_layers))
    screenshot_date_json = json.dumps(day if day != "无数据" else chokepoint_day)
    return f"""
    <!doctype html><html lang="zh-CN"><head>
    <meta charset="utf-8" />
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css" />
    <link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css" />
    <style>
      html, body, #map {{ height: 100%; margin: 0; }}
      #map {{ background: #e8eef4; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
      .leaflet-popup-content-wrapper {{ border-radius: 10px; box-shadow: 0 8px 24px rgba(15, 23, 42, .25); }}
      .leaflet-popup-content {{ margin: 13px 15px; min-width: 300px; max-width: 360px; }}
      .field-name {{ font-weight: 750; color: #0f172a; font-size: 14px; line-height: 1.35; margin-bottom: 3px; }}
      .country {{ color: #64748b; font-size: 12px; margin-bottom: 10px; }}
      .row {{ display: flex; justify-content: space-between; gap: 14px; padding: 5px 0; border-top: 1px solid #e2e8f0; font-size: 12px; }}
      .row span, .basis, .status {{ color: #64748b; }}
      .row strong {{ color: #0f172a; text-align: right; }}
      .hierarchy-title {{ margin-top: 10px; padding-top: 8px; border-top: 2px solid #cbd5e1; color: #334155; font-size: 12px; font-weight: 700; }}
      .level-metric {{ padding: 7px 8px; margin-top: 6px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 7px; }}
      .level-head, .output-line {{ display: flex; justify-content: space-between; gap: 10px; font-size: 11px; }}
      .level-head span, .output-line span, .metric-detail {{ color: #64748b; }}
      .level-head b {{ color: #334155; text-align: right; }}
      .output-line {{ margin-top: 4px; align-items: baseline; }}
      .output-line strong {{ color: #991b1b; font-size: 13px; }}
      .metric-detail, .other-metric {{ font-size: 10px; margin-top: 2px; line-height: 1.35; }}
      .other-metric {{ color: #92400e; }}
      .mix-row {{ display: grid; grid-template-columns: 72px 1fr 92px; gap: 7px; align-items: center; margin-top: 6px; font-size: 10px; }}
      .mix-row span {{ color: #475569; }}
      .mix-row b {{ color: #334155; text-align: right; font-weight: 600; }}
      .mix-track {{ height: 6px; border-radius: 999px; background: #e2e8f0; overflow: hidden; }}
      .mix-track i {{ display: block; height: 100%; border-radius: 999px; }}
      .status, .basis {{ font-size: 11px; margin-top: 8px; line-height: 1.4; }}
      .source {{ display: block; color: #2563eb; font-size: 11px; margin-top: 8px; text-decoration: none; }}
      .map-legend {{ background: rgba(255,255,255,.95); padding: 9px 11px; border-radius: 8px; box-shadow: 0 2px 10px rgba(15,23,42,.15); color: #0f172a; font-size: 11px; line-height: 1.45; }}
      .map-legend b {{ font-size: 13px; }}
      .map-legend span {{ display: block; margin-top: 4px; white-space: nowrap; }}
      .map-legend svg {{ display: inline-block; width: 10px; height: 10px; margin-right: 6px; vertical-align: -1px; }}
      .asset-icon, .port-icon, .chokepoint-icon, .vessel-icon, .vessel-cluster {{ background: transparent; border: 0; }}
      .asset-icon svg, .port-icon svg, .chokepoint-icon svg, .vessel-icon svg, .vessel-cluster svg {{ display: block; filter: drop-shadow(0 1px 1px rgba(15,23,42,.45)); }}
      .leaflet-tooltip {{ border: 0; border-radius: 7px; padding: 5px 8px; box-shadow: 0 3px 12px rgba(15,23,42,.18); font-size: 11px; }}
      .marker-cluster-small, .marker-cluster-medium, .marker-cluster-large {{ background: transparent; }}
      .marker-cluster-small div, .marker-cluster-medium div, .marker-cluster-large div {{ background: #ea580c; color: white; font-weight: 700; border-radius: 7px; transform: rotate(45deg); box-shadow: 0 0 0 5px rgba(234,88,12,.22); }}
      .marker-cluster-small span, .marker-cluster-medium span, .marker-cluster-large span {{ display: block; transform: rotate(-45deg); }}
      .map-tools {{ background: rgba(255,255,255,.96); border-radius: 8px; padding: 8px 10px; color: #172b4d; box-shadow: 0 2px 10px #0f172a26; }}
      .map-tools button {{ background: #0e5570; color: white; border: 0; border-radius: 5px; padding: 8px 12px; cursor: pointer; font-size: 13px; }}
      .map-tools button:disabled {{ opacity: .6; cursor: wait; }}
      .map-tools span {{ display: block; max-width: 230px; font-size: 11px; margin-top: 4px; }}
      .map-tools span:empty {{ display: none; }}
    </style></head><body><div id="map"></div>
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>
    <script src="https://unpkg.com/html2canvas@1.4.1/dist/html2canvas.min.js"></script>
    <script>
      const map = L.map('map', {{zoomControl: true}}).setView([25.5, 48.5], 4);
      L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
        attribution: 'Tiles &copy; Esri', maxZoom: 18, crossOrigin: true
      }}).addTo(map);
      const screenshotDate = {screenshot_date_json};
      const legend = L.control({{position: 'bottomright'}});
      legend.onAdd = () => {{
        const el = L.DomUtil.create('div', 'map-legend');
        el.innerHTML = {legend_json};
        return el;
      }};
      legend.addTo(map);
      const assets = {marker_json};
      const ports = {port_json};
      const chokepoints = {chokepoint_json};
      const vessels = {vessel_json};
      const assetLayer = L.markerClusterGroup({{showCoverageOnHover: false, maxClusterRadius: 34,
          disableClusteringAtZoom: 8, spiderfyOnMaxZoom: true}}).addTo(map);
      const portLayer = L.layerGroup().addTo(map);
      const chokepointLayer = L.layerGroup().addTo(map);
      const vesselLayer = L.markerClusterGroup({{
        showCoverageOnHover: false, maxClusterRadius: 24, disableClusteringAtZoom: 7,
        spiderfyOnMaxZoom: true,
        iconCreateFunction: (cluster) => {{
          const count = cluster.getChildCount();
          const label = count > 999 ? `${{Math.round(count / 100) / 10}}k` : String(count);
          return L.divIcon({{
            className: 'vessel-cluster', iconSize: [38, 34], iconAnchor: [19, 17],
            html: `<svg width="38" height="34" viewBox="0 0 38 34">
              <path d="M19 1 L37 32 L19 26 L1 32 Z" fill="#334155" stroke="#ffffff" stroke-width="1.4"/>
              <text x="19" y="22" text-anchor="middle" fill="#ffffff" font-size="10" font-weight="700">${{label}}</text>
            </svg>`
          }});
        }}
      }}).addTo(map);
      assets.forEach((asset) => {{
        const size = 18;
        const dash = asset.is_proxy ? '3 2' : 'none';
        const icon = L.divIcon({{
          className: 'asset-icon', iconSize: [size, size], iconAnchor: [size / 2, size / 2],
          html: `<svg width="${{size}}" height="${{size}}" viewBox="0 0 ${{size}} ${{size}}">
            <polygon points="${{size/2}},1 ${{size-1}},${{size/2}} ${{size/2}},${{size-1}} 1,${{size/2}}"
              fill="#ea580c" fill-opacity=".94" stroke="#7c2d12"
              stroke-width="1.5" stroke-dasharray="${{dash}}"/>
          </svg>`
        }});
        L.marker([asset.lat, asset.lon], {{icon}}).bindTooltip(asset.name, {{direction: 'top', opacity: .95}})
          .bindPopup(asset.popup, {{maxWidth: 390}}).addTo(assetLayer);
      }});
      ports.forEach((port) => {{
        const size = 16;
        const icon = L.divIcon({{
          className: 'port-icon', iconSize: [size, size], iconAnchor: [size / 2, size / 2],
          html: `<svg width="${{size}}" height="${{size}}" viewBox="0 0 ${{size}} ${{size}}">
            <rect x="1.5" y="1.5" width="${{size-3}}" height="${{size-3}}" rx="2.5"
              fill="#2563eb" fill-opacity=".9" stroke="#ffffff" stroke-width="1.5"/>
          </svg>`
        }});
        const label = document.createElement('div');
        label.textContent = `${{port.name}} · ${{port.calls == null ? '无日度记录' : port.calls + ' 艘次进港'}}`;
        L.marker([port.lat, port.lon], {{icon}}).bindTooltip(label, {{direction: 'top', opacity: .95}})
          .bindPopup(port.popup, {{maxWidth: 410}}).addTo(portLayer);
      }});
      chokepoints.forEach((point) => {{
        const size = 22;
        const icon = L.divIcon({{
          className: 'chokepoint-icon', iconSize: [size, size], iconAnchor: [size / 2, size / 2],
          html: `<svg width="${{size}}" height="${{size}}" viewBox="0 0 24 24">
            <polygon points="6,2 18,2 23,12 18,22 6,22 1,12"
              fill="#7c3aed" fill-opacity=".94" stroke="#ffffff" stroke-width="1.5"/>
          </svg>`
        }});
        const label = document.createElement('div');
        label.textContent = `${{point.name}} · ${{point.calls == null ? '无日度记录' : point.calls + ' 艘通过'}}`;
        L.marker([point.lat, point.lon], {{icon}}).bindTooltip(label, {{direction: 'top', opacity: .95, permanent: true}})
          .bindPopup(point.popup, {{maxWidth: 410}}).addTo(chokepointLayer);
      }});
      const vesselColors = {{
        tanker: '#ef4444', cargo: '#2563eb', other: '#64748b'
      }};
      vessels.forEach((vessel) => {{
        const color = vesselColors[vessel.category] || vesselColors.other;
        const angle = Number.isFinite(Number(vessel.course)) ? Number(vessel.course) : 0;
        const icon = L.divIcon({{
          className: 'vessel-icon', iconSize: [18, 18], iconAnchor: [9, 9],
          html: `<svg width="18" height="18" viewBox="0 0 18 18" style="transform:rotate(${{angle}}deg)">
            <path d="M9 1 L16 16 L9 12.8 L2 16 Z" fill="${{color}}" stroke="#ffffff" stroke-width="1.15"/>
          </svg>`
        }});
        const marker = L.marker([vessel.lat, vessel.lon], {{icon}});
        marker.bindTooltip(vessel.name, {{direction: 'top', opacity: .95}})
          .bindPopup(vessel.popup, {{maxWidth: 410}}).addTo(vesselLayer);
      }});
      const allPoints = ports.map((p) => [p.lat, p.lon])
        .concat(chokepoints.map((p) => [p.lat, p.lon]))
        .concat(assets.map((a) => [a.lat, a.lon]))
        .concat(vessels.map((v) => [v.lat, v.lon]));
      const focusAssets = {focus_json};
      const visibleLayers = {visible_layers_json};
      if (focusAssets && assets.length === 1) {{
        map.setView([assets[0].lat, assets[0].lon], 8);
      }} else if (focusAssets && assets.length > 1) {{
        map.fitBounds(L.latLngBounds(assets.map((a) => [a.lat, a.lon])),
          {{padding: [42, 42], maxZoom: 7}});
      }} else if (allPoints.length) {{
        map.fitBounds(L.latLngBounds(allPoints), {{padding: [36, 36], maxZoom: 5}});
      }}
      // Keep the viewport only while the selected layers and marker locations match.
      const pointSignature = allPoints
        .map(([lat, lon]) => [Number(lat), Number(lon)])
        .sort((left, right) => left[0] - right[0] || left[1] - right[1]);
      const viewKey = 'energy-map-view';
      const viewSignature = JSON.stringify([focusAssets, visibleLayers, pointSignature]);
      try {{
        const saved = JSON.parse(sessionStorage.getItem(viewKey));
        if (saved && saved.signature === viewSignature) map.setView(saved.center, saved.zoom);
      }} catch (error) {{ /* Storage can be disabled by the embedding browser. */ }}
      map.on('moveend', () => {{
        try {{ sessionStorage.setItem(viewKey, JSON.stringify({{
          signature: viewSignature,
          center: [map.getCenter().lat, map.getCenter().lng], zoom: map.getZoom()
        }})); }} catch (error) {{ }}
      }});
      {map_tools.SCREENSHOT_SCRIPT}
    </script></body></html>
    """
