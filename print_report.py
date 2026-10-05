"""Build a source-dated, print-ready report from the map's current data."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from html import escape
import math
from zoneinfo import ZoneInfo

from portwatch_records import latest_by_node


TITLE = "中东能源与战略通道运输监测"
COLORS = ("#1769aa", "#d97706", "#7c3aed", "#14866d", "#dc4b4b", "#64748b")


def _esc(value: object) -> str:
    return escape(str(value if value not in (None, "") else "—"), quote=True)


def _number(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _date(value: object) -> date | None:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _display_date(value: object) -> str:
    day = _date(value)
    return day.isoformat() if day else "无可用记录"


def _fmt(value: object, digits: int = 0) -> str:
    number = _number(value)
    if number is None:
        return "—"
    return f"{number:,.{digits}f}"


def _section(title: str, body: str, page: bool = False) -> str:
    cls = "report-page" if page else "report-cover"
    return f'<section class="{cls}"><h2>{_esc(title)}</h2>{body}</section>'


def _table(headers: list[str], rows: list[list[object]], empty: str = "当前范围没有可用记录") -> str:
    if not rows:
        return f'<p class="empty">{_esc(empty)}</p>'
    head = "".join(f"<th>{_esc(item)}</th>" for item in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{_esc(value)}</td>" for value in row) + "</tr>"
        for row in rows
    )
    return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def _metric_cards(cards: list[tuple[str, str, str]]) -> str:
    return '<div class="metric-grid">' + "".join(
        f'<div class="metric-card"><span>{_esc(label)}</span><strong>{_esc(value)}</strong>'
        f'<small>{_esc(note)}</small></div>'
        for label, value, note in cards
    ) + "</div>"


def _time_series_chart(title: str, series: list[tuple[str, list[tuple[object, object]]]],
                      unit: str = "") -> str:
    parsed: dict[str, dict[date, float | None]] = {}
    all_dates: set[date] = set()
    for label, pairs in series:
        values: dict[date, float | None] = {}
        for raw_day, raw_value in pairs:
            day = _date(raw_day)
            if day is None:
                continue
            values[day] = _number(raw_value)
            all_dates.add(day)
        parsed[label] = values
    if not all_dates:
        return f'<div class="chart-card"><h3>{_esc(title)}</h3><p class="empty">历史记录不可用</p></div>'

    dates = sorted(all_dates)
    valid_values = [value for values in parsed.values() for value in values.values()
                    if value is not None]
    maximum = max(valid_values, default=1.0)
    y_max = max(maximum * 1.12, 1.0)
    tick_count = min(6, max(2, len(dates)))
    label_indexes = sorted({round(index * (len(dates) - 1) / (tick_count - 1))
                            for index in range(tick_count)})
    pieces = [f'<div class="chart-card"><h3>{_esc(title)}</h3>', '<div class="chart-legend">']
    pieces.extend(
        f'<span><i style="background:{COLORS[index % len(COLORS)]}"></i>{_esc(label)}</span>'
        for index, label in enumerate(parsed)
    )
    pieces.append(
        f'</div><small class="chart-scale">纵轴范围：0–{_fmt(y_max, 1)} {_esc(unit)}</small>'
        '<div class="chart-series">'
    )
    for index, (label, values) in enumerate(parsed.items()):
        color = COLORS[index % len(COLORS)]
        pieces.append(f'<div class="chart-series-row"><span class="chart-series-label">{_esc(label)}</span>')
        pieces.append('<div class="chart-bars" role="img" aria-label="' + _esc(label) + '">')
        for day in dates:
            value = values.get(day)
            if value is None:
                pieces.append(f'<span class="chart-bar missing" title="{day.isoformat()}：无记录"></span>')
                continue
            bar_height = max(1.0, min(100.0, value / y_max * 100))
            pieces.append(
                f'<span class="chart-bar" style="height:{bar_height:.2f}%;background:{color}" '
                f'title="{day.isoformat()}：{_fmt(value, 1)}"></span>'
            )
        pieces.append('</div></div>')
    pieces.append('</div><div class="chart-date-labels">')
    pieces.extend(f'<span>{dates[index].strftime("%m-%d")}</span>' for index in label_indexes)
    pieces.append(f'</div><small class="unit">{_esc(unit)} · 按同一量程展示；日期按 UTC，缺报保留为空</small></div>')
    return "".join(pieces)


def _history_by_node(rows: list[dict]) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        result[str(row.get("portid", ""))].append(row)
    for values in result.values():
        values.sort(key=lambda item: str(item.get("date", "")))
    return result


def _aggregate(rows: list[dict], metric: str, scale: float = 1.0) -> tuple[list[tuple[str, object]], dict[str, int]]:
    values: dict[str, list[float]] = defaultdict(list)
    dates = set()
    for row in rows:
        day = _date(row.get("date"))
        if day is not None:
            dates.add(day)
        number = _number(row.get(metric))
        if day is not None and number is not None:
            values[day.isoformat()].append(number / scale)
    output = [(day.isoformat(), sum(values[day.isoformat()]) if values.get(day.isoformat()) else None)
              for day in sorted(dates)]
    coverage = {day: len(numbers) for day, numbers in values.items()}
    return output, coverage


def _window_mean(by_date: dict[date, dict], end: date, days: int, metric: str) -> float | None:
    values: list[float] = []
    for offset in range(days):
        row = by_date.get(end - timedelta(days=offset))
        number = _number(row.get(metric)) if row else None
        if number is None:
            return None
        values.append(number)
    return sum(values) / days


def _change_table(choke_rows: list[dict], choke_catalog: list[dict],
                  latest_day: object) -> str:
    catalog = {str(row.get("portid")): row for row in choke_catalog}
    by_node: dict[str, dict[date, dict]] = defaultdict(dict)
    for row in choke_rows:
        day = _date(row.get("date"))
        if day:
            by_node[str(row.get("portid"))][day] = row
    rows: list[list[object]] = []
    for point_id, point_rows in by_node.items():
        if not point_rows:
            continue
        end = _date(latest_day) or max(point_rows)
        if end not in point_rows:
            end = max(point_rows)
        current = _window_mean(point_rows, end, 7, "n_total")
        previous = _window_mean(point_rows, end - timedelta(days=7), 7, "n_total")
        if current is None or previous is None or previous == 0:
            delta: object = "窗口记录不完整或基期为0"
        else:
            delta = f"{(current / previous - 1) * 100:+.1f}%"
        point = catalog.get(point_id, {})
        rows.append([
            point.get("name_cn") or point.get("name") or point_id,
            end.isoformat(),
            _fmt(previous, 1),
            _fmt(current, 1),
            delta,
        ])
    return _table(["咽喉点", "节点最新日", "前7日均值（艘次/日）",
                   "最近7日均值（艘次/日）", "环比变化"], rows)


def _overview_map(ports: list[dict], chokes: list[dict], assets: list[dict],
                  regions: dict[str, tuple[float, float, float, float]],
                  vessels: list[dict] | None = None) -> str:
    # st.html sanitizes SVG tags, so print graphics use HTML elements and CSS.
    coordinates = []
    for row in ports + chokes + (vessels or []):
        coordinates.append((_number(row.get("lat")), _number(row.get("lon"))))
    for asset in assets:
        if asset.get("map_drawable", True):
            coordinates.append((
                _number(asset.get("map_lat", asset.get("lat"))),
                _number(asset.get("map_lon", asset.get("lon"))),
            ))
    for south, north, west, east in regions.values():
        coordinates.extend(((south, west), (north, east)))
    coordinates = [(lat, lon) for lat, lon in coordinates
                   if lat is not None and lon is not None]
    if coordinates:
        lat_min, lat_max = min(lat for lat, _ in coordinates), max(lat for lat, _ in coordinates)
        lon_min, lon_max = min(lon for _, lon in coordinates), max(lon for _, lon in coordinates)
        lat_padding = max(0.5, (lat_max - lat_min) * 0.05)
        lon_padding = max(0.5, (lon_max - lon_min) * 0.05)
        lat_min, lat_max = lat_min - lat_padding, lat_max + lat_padding
        lon_min, lon_max = lon_min - lon_padding, lon_max + lon_padding
    else:
        lon_min, lon_max, lat_min, lat_max = 29.0, 64.0, 8.0, 34.0
    lon_span, lat_span = lon_max - lon_min, lat_max - lat_min

    def xy(lat: object, lon: object) -> tuple[float, float] | None:
        yv, xv = _number(lat), _number(lon)
        if yv is None or xv is None or not (lat_min <= yv <= lat_max and lon_min <= xv <= lon_max):
            return None
        return (xv - lon_min) / lon_span * 100, (lat_max - yv) / lat_span * 100

    lon_step = 10 if lon_span > 40 else 5 if lon_span > 20 else 2 if lon_span > 10 else 1
    lat_step = 10 if lat_span > 40 else 5 if lat_span > 20 else 2 if lat_span > 10 else 1
    lon_start = math.ceil(lon_min / lon_step) * lon_step
    lat_start = math.ceil(lat_min / lat_step) * lat_step
    parts = ['<div class="overview-map" role="img" aria-label="监测水域与节点空间分布示意">',
             '<div class="overview-map-plot">']
    for lon in range(lon_start, math.floor(lon_max) + 1, lon_step):
        x = (lon - lon_min) / lon_span * 100
        parts.append(f'<span class="map-gridline vertical" style="left:{x:.3f}%"></span>')
        parts.append(f'<span class="map-axis-label map-axis-x" style="left:{x:.3f}%">{lon}°E</span>')
    for lat in range(lat_start, math.floor(lat_max) + 1, lat_step):
        y = (lat_max - lat) / lat_span * 100
        parts.append(f'<span class="map-gridline horizontal" style="top:{y:.3f}%"></span>')
        parts.append(f'<span class="map-axis-label map-axis-y" style="top:{y:.3f}%">{lat}°N</span>')
    for region, bounds in regions.items():
        south, north, west, east = bounds
        x1, y1 = xy(south, west) or (None, None)
        x2, y2 = xy(north, east) or (None, None)
        if x1 is not None and y1 is not None and x2 is not None and y2 is not None:
            parts.append(
                f'<div class="map-zone" title="{_esc(region)}" style="left:{x1:.3f}%;top:{y2:.3f}%;'
                f'width:{x2-x1:.3f}%;height:{y1-y2:.3f}%"><span>{_esc(region)}</span></div>'
            )

    def append_point(kind: str, label: object, lat: object, lon: object,
                     proxy: bool = False) -> None:
        point = xy(lat, lon)
        if point:
            x, y = point
            proxy_class = " proxy" if proxy else ""
            parts.append(
                f'<span class="map-point {kind}{proxy_class}" title="{_esc(label)}" '
                f'style="left:{x:.3f}%;top:{y:.3f}%"></span>'
            )

    for port in ports:
        append_point("port", port.get("name_cn") or port.get("name") or port.get("portname") or "港口",
                     port.get("lat"), port.get("lon"))
    for asset in assets:
        if not asset.get("map_drawable", True):
            continue
        append_point("asset", asset.get("name_cn") or asset.get("name") or "油气资产",
                     asset.get("map_lat", asset.get("lat")),
                     asset.get("map_lon", asset.get("lon")), bool(asset.get("map_is_proxy")))
    for choke in chokes:
        append_point("choke", choke.get("name_cn") or choke.get("name") or "咽喉点",
                     choke.get("lat"), choke.get("lon"))
    for vessel in (vessels or []):
        append_point("vessel", vessel.get("name") or vessel.get("mmsi") or "AIS船位",
                     vessel.get("lat"), vessel.get("lon"))
    parts.append('</div></div>')
    return "".join(parts)


def _distribution(vessels: list[dict]) -> str:
    if not vessels:
        return '<p class="empty">当前快照没有可用船位；这不表示监测水域内没有船舶。</p>'
    region_counts = Counter(str(v.get("region") or "水域未知") for v in vessels)
    type_counts = Counter(str(v.get("category_label") or "船型待识别") for v in vessels)
    rows = [[label, count] for label, count in region_counts.most_common()]
    type_rows = [[label, count] for label, count in type_counts.most_common()]
    return ('<div class="chart-grid"><div><h3>水域分布</h3>' +
            _table(["监测水域", "快照船位数"], rows) +
            '</div><div><h3>船型分布</h3>' +
            _table(["船型", "快照船位数"], type_rows) + '</div></div>')


def build_report_html(
    *,
    scope_label: str,
    generated_at: datetime | None,
    port_catalog: list[dict],
    choke_catalog: list[dict],
    latest_ports: list[dict],
    port_history: list[dict],
    choke_history: list[dict],
    assets: list[dict],
    asset_table: list[dict],
    vessels: list[dict],
    regions: dict[str, tuple[float, float, float, float]],
    port_day: object,
    choke_day: object,
    ais_status: str,
    ais_source_note: str,
    errors: list[str] | None = None,
) -> str:
    """Return self-contained HTML for browser preview and print/PDF."""
    timestamp = generated_at or datetime.now(ZoneInfo("Asia/Shanghai"))
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
    timestamp = timestamp.astimezone(ZoneInfo("Asia/Shanghai"))
    # Supplementary WPI/industry entries are map-only unless the catalog
    # explicitly marks them as independent PortWatch statistics.
    stat_ports = [p for p in port_catalog if p.get("statistics_available", False)]
    dated_calls = [p for p in latest_ports if _number(p.get("portcalls")) is not None]
    catalog_chokes = len(choke_catalog)
    report_assets = list(assets)
    map_html = _overview_map(port_catalog, choke_catalog, report_assets, regions, vessels)
    cover_cards = _metric_cards([
        ("港口监测点", str(len(port_catalog)), f"其中独立统计点 {len(stat_ports)} 个"),
        ("战略通道", str(catalog_chokes), "逐节点分别报告，不合并解释"),
        ("AIS快照船位", str(len(vessels)) if vessels else "—",
         "公开观测样本，不代表区域全量船舶"),
        ("油气资产节点", str(len(report_assets)), "目录节点数，指标口径分别列示"),
    ])
    cover_table = _table(
        ["数据", "源站观测日 / 状态", "说明"],
        [
            ["PortWatch 港口", _display_date(port_day), f"所选报告范围内 {len(dated_calls)}/{len(latest_ports)} 个点位有当日记录"],
            ["PortWatch 咽喉点", _display_date(choke_day), f"纳入 {catalog_chokes} 个节点"],
            ["AIS 船位", ais_status, ais_source_note],
            ["油气资产", "逐项列示披露日期", "静态公开披露；不视为实时遥测"],
        ],
    )
    overview = (
        f'<div class="report-date-rule"><span>生成时间：{timestamp.strftime("%Y年%m月")}</span></div>'
        + '<p class="report-sponsor">中国驻阿联酋大使馆、国家发改委国家信息中心</p>'
        + f'<div class="report-meta"><span>报告范围：{_esc(scope_label)}</span></div>'
        + '<h3>能源资产与战略通道监测范围</h3>'
        + f'<div class="map-frame">{map_html}</div>'
        + '<div class="map-legend">'
          '<span><i style="background:#1769aa"></i>港口</span>'
          '<span><i style="background:#7c3aed"></i>咽喉点</span>'
          '<span><i style="background:#d97706"></i>油气资产</span>'
          '<span><i style="background:#14866d"></i>AIS船位</span>'
          '</div>'
        + '<p class="note">点位按经纬度绘制，区域框为项目监测范围；'
          '空间分布示意不代表海岸线或实际航迹。</p>'
        + cover_cards
        + cover_table
    )

    choke_names = {str(row.get("portid")): row.get("name_cn") or row.get("name") or row.get("portname") or row.get("portid")
                   for row in choke_catalog}
    n_series = [(str(choke_names.get(point_id, point_id)),
                 [(row.get("date"), row.get("n_total")) for row in choke_history
                  if str(row.get("portid")) == point_id])
                for point_id in sorted({str(row.get("portid")) for row in choke_history})]
    capacity_series = [(str(choke_names.get(point_id, point_id)),
                        [(row.get("date"), row.get("capacity")) for row in choke_history
                         if str(row.get("portid")) == point_id])
                       for point_id in sorted({str(row.get("portid")) for row in choke_history})]
    choke_content = (
        '<p class="note">按通道分别呈现每日源站记录。不同通道的船次不相加；承载能力为 PortWatch 估算口径。</p>'
        + '<div class="chart-grid">'
        + _time_series_chart("咽喉点每日通过船次", n_series, "艘次/日")
        + _time_series_chart("咽喉点估算承载能力", capacity_series, "载重吨/日（源站口径）")
        + '</div><h3>最近7日与前7日</h3>'
        + _change_table(choke_history, choke_catalog, choke_day)
    )

    history_ids = sorted({str(row.get("portid")) for row in port_history})
    port_name = {str(row.get("portid")): row.get("name") or row.get("portname") or row.get("portid")
                 for row in port_catalog}
    node_daily = _history_by_node(port_history)
    latest_daily = latest_by_node(port_history)
    top_ids = sorted(
        history_ids,
        key=lambda pid: _number((latest_daily.get(pid) or {}).get("portcalls")) or 0,
        reverse=True,
    )[:6]
    port_series = [(str(port_name.get(pid, pid)),
                    [(row.get("date"), row.get("portcalls")) for row in node_daily[pid]])
                   for pid in top_ids]
    calls, calls_coverage = _aggregate(port_history, "portcalls")
    imports, import_coverage = _aggregate(port_history, "import", scale=10000)
    exports, export_coverage = _aggregate(port_history, "export", scale=10000)
    port_content = (
        '<p class="note">缺报日留空。进出口图按当日有源记录的点位合计，并在表中列出覆盖点位数；'
        '油气货量为 AIS 推算，不是海关实测。</p>'
        + '<div class="chart-grid">'
        + _time_series_chart("重点港口每日有效进港艘次", port_series, "艘次/日")
        + _time_series_chart("港口估算进出口货量", [
            ("进口", imports), ("出口", exports)], "万吨/日")
        + '</div><h3>港口记录覆盖与最新值</h3>'
    )
    coverage_days = sorted(set(calls_coverage) | set(import_coverage) | set(export_coverage))
    coverage_rows = []
    for day in coverage_days[-14:]:
        coverage_rows.append([
            day,
            f"{calls_coverage.get(day, 0)}/{len(stat_ports)}",
            f"{_fmt(dict(calls).get(day), 0)}",
            f"{import_coverage.get(day, 0)}/{len(stat_ports)}",
            f"{export_coverage.get(day, 0)}/{len(stat_ports)}",
        ])
    port_content += _table(["日期 UTC", "有进港记录点位", "进港艘次合计",
                            "有进口记录点位", "有出口记录点位"], coverage_rows)
    top_ports = sorted(
        latest_ports,
        key=lambda row: _number(row.get("portcalls")) if _number(row.get("portcalls")) is not None else -1,
        reverse=True,
    )[:12]
    port_content += '<h3>港口最新日记录（最多12个）</h3>' + _table(
        ["港口", "国家", "观测日 UTC", "有效进港艘次", "估算进口（万吨）", "估算出口（万吨）"],
        [[row.get("name") or row.get("portname"), row.get("country"), row.get("date"),
          _fmt(row.get("portcalls")), _fmt((_number(row.get("import")) or 0) / 10000, 2)
          if _number(row.get("import")) is not None else "—",
          _fmt((_number(row.get("export")) or 0) / 10000, 2)
          if _number(row.get("export")) is not None else "—"] for row in top_ports]
    )

    assets_table_rows = []
    for row in asset_table[:20]:
        assets_table_rows.append([
            row.get("中文名称") or row.get("英文名称"),
            row.get("国家"),
            row.get("生产状态"),
            row.get("产量显示") or row.get("本层级日产量"),
            row.get("其他日量指标") if row.get("其他日量指标") not in (None, "—") else row.get("指标口径"),
            row.get("数据日期"),
            row.get("产量口径说明") or row.get("合计口径说明") or row.get("地图坐标精度"),
        ])
    oil_content = (
        '<p class="note">只列公开披露且可定位的战略节点；实际产量、产能、目标与历史值按资产逐项区分，'
        '不跨口径相加。虚线边框代理点的坐标仅用于定位。</p>'
        + '<div class="map-frame">' + _overview_map([], [], report_assets, regions) + '</div>'
        + '<h3>战略油气资产（最多20项）</h3>'
        + _table(["资产", "国家", "状态", "产量／注明范围的合计参考", "其他指标", "披露日期", "合计／权益口径说明"], assets_table_rows)
        + '<h3>产量来源与检索结论（对应以上资产）</h3>'
        + _table(
            ["资产", "产量检索复核", "资产指标来源", "合计参考来源"],
            [[row.get("英文名称"), row.get("产量检索复核"), row.get("来源链接"),
              row.get("合计参考证据链接")] for row in asset_table[:20]],
        )
    )
    reference_rows = [row for row in asset_table[:20] if row.get("GEM Unit ID")]
    if reference_rows:
        oil_content += (
            '<h3>公开目录背景（2026-03版本；最多20项）</h3>'
            '<p class="note">Global Energy Monitor（CC BY 4.0）公开镜像；运营商和权益仅为目录参考，'
            '投产年不表示当前在产；未披露字段保持为空。</p>'
            + _table(
                ["资产", "运营商（参考）", "发现年", "商业投产年", "GEM ID", "固定版本来源"],
                [[row.get("英文名称"), row.get("运营商（2026-03目录参考）"),
                  row.get("发现年（目录参考）"), row.get("商业投产年（目录参考）"),
                  row.get("GEM Unit ID"), row.get("参考资料链接")] for row in reference_rows],
            )
        )

    ais_content = (
        '<p class="note">AIS 是事件驱动的公开/订阅观测快照，不是监测水域内全部船舶的普查；'
        '点位可能受接收站覆盖和报文年龄影响。</p>'
        + _metric_cards([
            ("当前可用船位", str(len(vessels)) if vessels else "—", ais_source_note),
            ("航行中", str(sum(bool(row.get("moving")) for row in vessels)) if vessels else "—", "航速至少0.5节"),
            ("油轮/液货船", str(sum(row.get("category") == "tanker" for row in vessels)) if vessels else "—", "按AIS基础船型分类"),
            ("数据来源", ais_status, "以当前会话可用状态为准"),
        ])
        + '<div class="map-frame">' + _overview_map([], [], [], regions, vessels) + '</div>'
        + _distribution(vessels)
    )

    source_content = _table(
        ["数据", "来源", "更新与解释边界"],
        [
            ["港口日活动", "IMF PortWatch", "每日源站汇总；受AIS识别、挂靠规则和发布时间影响；缺报不补零。"],
            ["咽喉点日活动", "IMF PortWatch", "总船次与承载能力按每个通道单独解释。"],
            ["AIS船位", "Open Waters / 可选 AISStream", "公开快照与WebSocket事件按MMSI去重；观测数量不等于总船数。"],
            ["油气资产", "公开披露及项目核验目录", "状态、产量、产能和目标保留各自日期与指标口径。"],
            ["油气目录背景", "Global Energy Monitor / CC BY 4.0 公开镜像", "2026-03版本；运营商、发现和投产年份仅为参考，不据此填补日产量或当前停复产状态。"],
        ],
    )
    source_content += '<h3>异常与缺报</h3>' + _table(
        ["检查项", "当前状态"], [[f"报告数据获取：{index+1}", error] for index, error in enumerate(errors or [])],
        empty="本次报告数据请求未返回错误；空值仍按源站缺报处理。",
    )
    source_content += '<p class="note">港口进口/出口货量是 PortWatch 基于 AIS 推算的估算值；AIS 船位点不能替代逐船航迹；油气目录中的静态披露不能作为实时生产监测。</p>'

    body = (
        f'<section class="report-cover report-overview">{overview}</section>'
        + _section("战略通道运输", choke_content, page=True)
        + _section("港口运输活动", port_content, page=True)
        + _section("油气供给与资产", oil_content, page=True)
        + _section("AIS 船位观测", ais_content, page=True)
        + _section("数据来源与口径", source_content, page=True)
    )
    return f'<div class="print-report"><header><h1>{_esc(TITLE)}</h1>{body}</header></div>'


PRINT_CSS = """
<style>
.print-report { display: none; color: #17212b; background: #fff; font: 10pt/1.38 Arial, "Noto Sans CJK SC", sans-serif; -webkit-print-color-adjust:exact; print-color-adjust:exact; }
.print-report * { box-sizing: border-box; }
@media print { .print-report { display: block !important; } }
.print-report h1 { text-align: center; font-size: 22pt; margin: 0 0 4mm; line-height: 1.2; }
.report-date-rule { position:relative; border-top:1px solid #9aa7b4; text-align:center; margin:0 0 3mm; height:4mm; }
.report-date-rule span { position:relative; top:-.7em; padding:0 4mm; background:#fff; font-size:9pt; }
.report-sponsor { margin:0 0 3mm; text-align:center; font-size:10pt; font-weight:400!important; }
.map-legend { display:flex; justify-content:center; flex-wrap:wrap; gap:2mm 5mm; font-size:8pt; margin:1mm 0 2mm; }
.map-legend i { display:inline-block; width:2.5mm; height:2.5mm; margin-right:1mm; vertical-align:middle; }
.print-report h2 { font-size: 15pt; border-bottom: 1px solid #9aa7b4; padding-bottom: 2mm; margin: 0 0 4mm; }
.print-report h3 { font-size: 10.5pt; margin: 4mm 0 2mm; }
.report-page { break-before: page; page-break-before: always; }
.metric-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 3mm; margin: 4mm 0; }
.metric-card { border: 1px solid #ccd5de; border-radius: 2mm; padding: 3mm; min-width: 0; }
.metric-card span, .metric-card small { display: block; color: #516171; font-size: 8pt; }
.metric-card strong { display: block; font-size: 17pt; margin: 1.5mm 0; overflow-wrap: anywhere; }
.report-meta { display:flex; justify-content:space-between; gap:4mm; margin-bottom:4mm; font-size:9pt; }
.chart-grid { display:grid; grid-template-columns:1fr 1fr; gap:4mm; align-items:start; }
.chart-card { border:1px solid #d6dde5; padding:2mm; break-inside:avoid; page-break-inside:avoid; min-width:0; }
.chart-card h3 { margin:1mm 1mm 0; }
.chart-legend { display:flex; flex-wrap:wrap; gap:1mm 3mm; margin:1mm; font-size:7pt; }
.chart-legend i { display:inline-block; width:2mm; height:2mm; margin-right:1mm; }
.chart-scale { display:block; margin:0 1mm; color:#52606d; font-size:6.5pt; }
.chart-series-row { display:flex; align-items:center; gap:2mm; margin:1mm 0; }
.chart-series-label { width:20%; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:7pt; }
.chart-bars { display:flex; align-items:flex-end; flex:1; height:16mm; min-width:0; border-bottom:1px solid #9aa7b4; background:repeating-linear-gradient(to bottom, transparent 0, transparent calc(25% - 1px), #e8edf2 25%); }
.chart-bar { display:block; flex:1 1 0; min-width:0; margin-right:.35px; }
.chart-bar.missing { height:1px; background:transparent !important; border-top:1px dotted #aab4be; }
.chart-date-labels { display:flex; justify-content:space-between; margin-left:22%; color:#52606d; font-size:6.5pt; }
.unit,.note,.empty { color:#52606d; font-size:8pt; }
.note { margin:2mm 0; }
.map-frame { border:1px solid #d6dde5; padding:2mm; break-inside:avoid; page-break-inside:avoid; }
.overview-map { position:relative; width:100%; aspect-ratio:2/1; background:#f8fafc; border:1px solid #94a3b8; }
.overview-map-plot { position:absolute; left:8.4%; right:3.3%; top:6.5%; bottom:12.1%; border:1px solid #94a3b8; }
.map-gridline { position:absolute; display:block; z-index:0; }
.map-gridline.vertical { top:0; bottom:0; border-left:1px solid #dce3e9; }
.map-gridline.horizontal { left:0; right:0; border-top:1px solid #dce3e9; }
.map-axis-label { position:absolute; color:#52606d; font-size:6.5pt; white-space:nowrap; }
.map-axis-x { top:calc(100% + 2px); transform:translateX(-50%); }
.map-axis-y { left:-3px; transform:translate(-100%,-50%); }
.map-zone { position:absolute; z-index:1; border:1px dashed #64748b; background:rgba(191,219,254,.08); }
.map-zone span { position:absolute; top:1px; left:2px; color:#435466; font-size:6.5pt; white-space:nowrap; }
.map-point { position:absolute; z-index:2; display:block; transform:translate(-50%,-50%); }
.map-point.port { width:1.5mm; height:1.5mm; border:.3mm solid #1769aa; background:#1769aa; }
.map-point.asset { width:2mm; height:2mm; border:.3mm solid #d97706; background:#d97706; transform:translate(-50%,-50%) rotate(45deg); }
.map-point.asset.proxy { border:1px dashed #7c2d12; }
.map-point.choke { width:2.5mm; height:2.5mm; border:.4mm solid #7c3aed; border-radius:50%; background:#7c3aed; }
.map-point.vessel { width:1mm; height:1mm; border:.3mm solid #14866d; border-radius:50%; background:#14866d; opacity:.7; }
.table-wrap { overflow:visible; }
.print-report table { width:100%; border-collapse:collapse; font-size:8pt; margin:2mm 0 4mm; }
.print-report th,.print-report td { border:1px solid #cbd5df; padding:1.3mm 1.6mm; text-align:left; vertical-align:top; overflow-wrap:anywhere; }
.print-report th { background:#eef2f6; font-weight:700; }
.print-report thead { display:table-header-group; }
.print-report tr { break-inside:avoid; page-break-inside:avoid; }
</style>
"""
