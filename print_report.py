"""Build a source-dated, print-ready report from the map's current data."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from html import escape
import math
from zoneinfo import ZoneInfo


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


def _line_chart(title: str, series: list[tuple[str, list[tuple[object, object]]]],
                unit: str = "", height: int = 278) -> str:
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

    first, last = min(all_dates), max(all_dates)
    span = max(1, (last - first).days)
    width = 820
    left, right, top, bottom = 64, 20, 38, height - 44
    plot_w, plot_h = width - left - right, bottom - top
    valid_values = [value for values in parsed.values() for value in values.values()
                    if value is not None]
    maximum = max(valid_values, default=1.0)
    y_max = maximum * 1.12 if maximum > 0 else 1.0
    y_max = max(y_max, 1.0)
    pieces = [
        f'<div class="chart-card"><h3>{_esc(title)}</h3>',
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{_esc(title)}" '
        'xmlns="http://www.w3.org/2000/svg">',
    ]
    for tick in range(5):
        y = top + plot_h * tick / 4
        value = y_max * (1 - tick / 4)
        pieces.append(f'<line x1="{left}" y1="{y:.1f}" x2="{width-right}" y2="{y:.1f}" class="grid"/>')
        pieces.append(f'<text x="{left-8}" y="{y+4:.1f}" text-anchor="end" class="axis">{_fmt(value, 0)}</text>')
    tick_count = min(6, max(2, len(all_dates)))
    for tick in range(tick_count):
        day = first + timedelta(days=round(span * tick / (tick_count - 1)))
        x = left + plot_w * (day - first).days / span
        pieces.append(f'<text x="{x:.1f}" y="{height-14}" text-anchor="middle" class="axis">{day.strftime("%m-%d")}</text>')
    for index, (label, values) in enumerate(parsed.items()):
        color = COLORS[index % len(COLORS)]
        segments: list[list[tuple[float, float]]] = []
        current: list[tuple[float, float]] = []
        day = first
        while day <= last:
            value = values.get(day)
            if value is None:
                if current:
                    segments.append(current)
                    current = []
            else:
                x = left + plot_w * (day - first).days / span
                y = top + plot_h * (1 - value / y_max)
                current.append((x, y))
            day += timedelta(days=1)
        if current:
            segments.append(current)
        for segment in segments:
            if len(segment) == 1:
                x, y = segment[0]
                pieces.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.5" fill="{color}"/>')
            else:
                coords = " ".join(f"{x:.1f},{y:.1f}" for x, y in segment)
                pieces.append(f'<polyline points="{coords}" fill="none" stroke="{color}" '
                              'stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>')
    pieces.append("</svg><div class=\"legend\">")
    pieces.extend(
        f'<span><i style="background:{COLORS[index % len(COLORS)]}"></i>{_esc(label)}</span>'
        for index, (label, _) in enumerate(series)
    )
    pieces.append(f'</div><small class="unit">{_esc(unit)} · 日期按 UTC；缺报保留为空</small></div>')
    return "".join(pieces)


def _history_by_node(rows: list[dict]) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        result[str(row.get("portid", ""))].append(row)
    for values in result.values():
        values.sort(key=lambda item: str(item.get("date", "")))
    return result


def _latest_by_node(rows: list[dict]) -> dict[str, dict]:
    latest: dict[str, dict] = {}
    for row in rows:
        key = str(row.get("portid", ""))
        day = str(row.get("date", ""))
        if key and day and (key not in latest or day > str(latest[key].get("date", ""))):
            latest[key] = row
    return latest


def _aggregate(rows: list[dict], metric: str, scale: float = 1.0) -> tuple[list[tuple[str, object]], dict[str, int]]:
    values: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        day = _date(row.get("date"))
        number = _number(row.get(metric))
        if day is not None and number is not None:
            values[day.isoformat()].append(number / scale)
    dates = sorted({_date(row.get("date")) for row in rows if _date(row.get("date"))})
    output = [(day.isoformat(), sum(values[day.isoformat()]) if values.get(day.isoformat()) else None)
              for day in dates]
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


def _overview_svg(ports: list[dict], chokes: list[dict], assets: list[dict],
                  regions: dict[str, tuple[float, float, float, float]],
                  vessels: list[dict] | None = None) -> str:
    width, height = 860, 430
    left, right, top, bottom = 72, 28, 28, 52
    lon_min, lon_max, lat_min, lat_max = 29.0, 64.0, 8.0, 34.0
    plot_w, plot_h = width - left - right, height - top - bottom
    def xy(lat: object, lon: object) -> tuple[float, float] | None:
        yv, xv = _number(lat), _number(lon)
        if yv is None or xv is None or not (lat_min <= yv <= lat_max and lon_min <= xv <= lon_max):
            return None
        return left + (xv - lon_min) / (lon_max - lon_min) * plot_w, top + (lat_max - yv) / (lat_max - lat_min) * plot_h
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="监测水域与节点空间分布示意" xmlns="http://www.w3.org/2000/svg">',
             f'<rect x="{left}" y="{top}" width="{plot_w}" height="{plot_h}" fill="#f8fafc" stroke="#94a3b8"/>']
    for lon in range(30, 65, 5):
        x = left + (lon - lon_min) / (lon_max - lon_min) * plot_w
        parts.append(f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{top+plot_h}" class="grid"/>')
        parts.append(f'<text x="{x:.1f}" y="{height-25}" text-anchor="middle" class="axis">{lon}°E</text>')
    for lat in range(10, 35, 5):
        y = top + (lat_max - lat) / (lat_max - lat_min) * plot_h
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left+plot_w}" y2="{y:.1f}" class="grid"/>')
        parts.append(f'<text x="{left-8}" y="{y+4:.1f}" text-anchor="end" class="axis">{lat}°N</text>')
    for region, bounds in regions.items():
        south, north, west, east = bounds
        p1, p2 = xy(south, west), xy(north, east)
        if p1 and p2:
            x1, y1 = p1
            x2, y2 = p2
            parts.append(f'<rect x="{x1:.1f}" y="{y2:.1f}" width="{x2-x1:.1f}" height="{y1-y2:.1f}" '
                         'fill="#bfdbfe" fill-opacity=".08" stroke="#64748b" stroke-dasharray="4 4"/>')
            parts.append(f'<text x="{x1+4:.1f}" y="{y2+13:.1f}" class="zone-label">{_esc(region)}</text>')
    for port in ports:
        point = xy(port.get("lat"), port.get("lon"))
        if point:
            x, y = point
            parts.append(f'<rect x="{x-3:.1f}" y="{y-3:.1f}" width="6" height="6" fill="#1769aa"/>')
    for asset in assets:
        if not asset.get("map_drawable", True):
            continue
        point = xy(asset.get("lat"), asset.get("lon"))
        if point:
            x, y = point
            parts.append(f'<polygon points="{x:.1f},{y-4:.1f} {x+4:.1f},{y:.1f} {x:.1f},{y+4:.1f} {x-4:.1f},{y:.1f}" fill="#d97706"/>')
    for choke in chokes:
        point = xy(choke.get("lat"), choke.get("lon"))
        if point:
            x, y = point
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="#7c3aed"/>')
    for vessel in (vessels or []):
        point = xy(vessel.get("lat"), vessel.get("lon"))
        if point:
            x, y = point
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="1.8" fill="#14866d" fill-opacity=".65"/>')
    parts.append("</svg>")
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
    latest_chokes: list[dict],
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
    covered_calls = sum(_number(p.get("portcalls")) or 0 for p in dated_calls)
    catalog_chokes = len(choke_catalog)
    report_assets = list(assets)
    map_html = _overview_svg(port_catalog, choke_catalog, report_assets, regions, vessels)
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

    latest_choke_by_id = {str(row.get("portid")): row for row in latest_chokes}
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
        + _line_chart("咽喉点每日通过船次", n_series, "艘次/日")
        + _line_chart("咽喉点估算承载能力", capacity_series, "载重吨/日（源站口径）")
        + '</div><h3>最近7日与前7日</h3>'
        + _change_table(choke_history, choke_catalog, choke_day)
    )

    history_ids = sorted({str(row.get("portid")) for row in port_history})
    port_name = {str(row.get("portid")): row.get("name") or row.get("portname") or row.get("portid")
                 for row in port_catalog}
    node_daily = _history_by_node(port_history)
    top_ids = sorted(
        history_ids,
        key=lambda pid: _number((_latest_by_node(node_daily[pid]).get(pid) or {}).get("portcalls")) or 0,
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
        + _line_chart("重点港口每日有效进港艘次", port_series, "艘次/日")
        + _line_chart("港口估算进出口货量", [
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
            row.get("本层级日产量"),
            row.get("其他日量指标") if row.get("其他日量指标") not in (None, "—") else row.get("指标口径"),
            row.get("数据日期"),
            row.get("地图坐标精度"),
        ])
    oil_content = (
        '<p class="note">只列公开披露且可定位的战略节点；实际产量、产能、目标与历史值按资产逐项区分，'
        '不跨口径相加。虚线边框代理点的坐标仅用于定位。</p>'
        + '<div class="map-frame">' + _overview_svg([], [], report_assets, regions) + '</div>'
        + '<h3>战略油气资产（最多20项）</h3>'
        + _table(["资产", "国家", "状态", "本层级日产量", "其他指标", "披露日期", "坐标精度"], assets_table_rows)
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
        + '<div class="map-frame">' + _overview_svg([], [], [], regions, vessels) + '</div>'
        + _distribution(vessels)
    )

    source_content = _table(
        ["数据", "来源", "更新与解释边界"],
        [
            ["港口日活动", "IMF PortWatch", "每日源站汇总；受AIS识别、挂靠规则和发布时间影响；缺报不补零。"],
            ["咽喉点日活动", "IMF PortWatch", "总船次与承载能力按每个通道单独解释。"],
            ["AIS船位", "Open Waters / 可选 AISStream", "公开快照与WebSocket事件按MMSI去重；观测数量不等于总船数。"],
            ["油气资产", "公开披露及项目核验目录", "状态、产量、产能和目标保留各自日期与指标口径。"],
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


def build_standalone_document(report_html: str) -> str:
    """Wrap the report as a visible, browser-printable HTML document."""
    standalone_css = PRINT_CSS.replace(
        ".print-report { display: none;",
        ".print-report { display: block;",
        1,
    )
    standalone_css += """
<style>
body { margin: 0; padding: 18px; background: #eef2f6; }
.print-report { max-width: 1100px; margin: 0 auto; padding: 28px; background: #fff; }
.standalone-print-action { max-width: 1100px; margin: 0 auto 12px; text-align: right; }
.standalone-print-action button { padding: 9px 14px; border: 0; border-radius: 6px;
  color: #fff; background: #1769aa; font-size: 14px; cursor: pointer; }
@media print {
  body { padding: 0; background: #fff; }
  .print-report { max-width: none; margin: 0; padding: 0; }
  .standalone-print-action { display: none !important; }
}
</style>
"""
    return (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<title>{_esc(TITLE)}</title>{standalone_css}</head><body>'
        '<div class="standalone-print-action"><button type="button" '
        'onclick="window.print()">打印 / 另存为 PDF</button></div>'
        f'{report_html}</body></html>'
    )


PRINT_CSS = """
<style>
.print-report { display: none; color: #17212b; background: #fff; font: 10pt/1.38 Arial, "Noto Sans CJK SC", sans-serif; }
.print-report * { box-sizing: border-box; }
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
.chart-card svg, .map-frame svg { width:100%; height:auto; display:block; }
.grid { stroke:#dce3e9; stroke-width:1; }
.axis { fill:#52606d; font-size:11px; }
.zone-label { fill:#435466; font-size:10px; }
.legend { display:flex; flex-wrap:wrap; gap:2mm 4mm; font-size:8pt; margin:1mm 2mm; }
.legend i { display:inline-block; width:3mm; height:1.5mm; margin-right:1mm; }
.unit,.note,.empty { color:#52606d; font-size:8pt; }
.note { margin:2mm 0; }
.map-frame { border:1px solid #d6dde5; padding:2mm; break-inside:avoid; page-break-inside:avoid; }
.table-wrap { overflow:visible; }
.print-report table { width:100%; border-collapse:collapse; font-size:8pt; margin:2mm 0 4mm; }
.print-report th,.print-report td { border:1px solid #cbd5df; padding:1.3mm 1.6mm; text-align:left; vertical-align:top; overflow-wrap:anywhere; }
.print-report th { background:#eef2f6; font-weight:700; }
.print-report thead { display:table-header-group; }
.print-report tr { break-inside:avoid; page-break-inside:avoid; }
@page { size:A4 portrait; margin:10mm 10mm 14mm; }
@media print {
  @page { @bottom-center { content:"第 " counter(page) " 页"; color:#64748b; font-size:8pt; } }
  [data-testid="stTabs"] { display:none!important; }
  html,body,#root,.stApp,[data-testid="stAppViewContainer"],[data-testid="stMain"],[data-testid="stMainBlockContainer"] { height:auto!important; min-height:0!important; background:#fff!important; }
  [data-testid="stSidebar"],[data-testid="stHeader"],[data-testid="stToolbar"],[data-testid="stDecoration"],[data-testid="stStatusWidget"],[data-testid="stToast"],[data-testid="stToastContainer"] { display:none!important; }
  [data-testid="stMainBlockContainer"] > div[data-testid="stElementContainer"]:not(:has(.print-report)) { display:none!important; }
  [data-testid="stMainBlockContainer"] > div[data-testid="stElementContainer"]:has(.print-report) { display:block!important; width:100%!important; max-width:none!important; margin:0!important; padding:0!important; }
  .print-report { display:block!important; color:#17212b!important; width:100%!important; }
  .stApp,[data-testid="stAppViewContainer"],[data-testid="stMainBlockContainer"] { overflow:visible!important; }
  a { color:inherit!important; text-decoration:none!important; }
}
</style>
"""
