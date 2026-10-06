"""Shared report/map cards, using complete daily PortWatch windows and AIS samples."""
from calendar import monthrange
from datetime import date, timedelta
from html import escape
import math


def number(value):
    try:
        value = float(value)
        return value if math.isfinite(value) and value >= 0 else None
    except (TypeError, ValueError):
        return None


def fmt(value):
    return '—' if value is None else f'{value:,.0f}'


def change(current, previous):
    return '—' if current is None or previous in (None, 0) else f'{(current / previous - 1) * 100:+.1f}%'


def unique_mmsis(rows, regions):
    return {str(row['mmsi']) for row in rows
            if row.get('region') in regions and row.get('mmsi')}


def windows(day):
    month = day.replace(day=1)
    previous = month - timedelta(days=1)
    prior_end = previous.replace(day=min(day.day, previous.day))
    year_end = day.replace(year=day.year - 1, day=min(day.day, monthrange(day.year - 1, day.month)[1]))
    monday = day - timedelta(days=day.weekday())
    return [(monday - timedelta(days=7), monday - timedelta(days=1)),
            (monday - timedelta(days=14), monday - timedelta(days=8)),
            (month, day), (previous.replace(day=1), prior_end),
            (year_end.replace(day=1), year_end)]


def total(rows, ids, metric, start, end):
    cells = {(str(r.get('portid')), str(r.get('date'))[:10]): number(r.get(metric)) for r in rows}
    values = [cells.get((node, (start + timedelta(days=i)).isoformat()))
              for node in ids for i in range((end - start).days + 1)]
    return sum(values) if values and all(v is not None for v in values) else None


def activity_card(label, catalog, rows, metric, verb, day, statistical=False):
    ids = {str(r['portid']) for r in catalog if not statistical or r.get('statistics_available', False)}
    values = [total(rows, ids, metric, *window) for window in windows(day)] if day else [None] * 5
    week, prior_week, month, prior_month, prior_year = values
    return (label, f'{len(catalog):,}个',
            f'上周累计{verb}{fmt(week)}艘（环比 {change(week, prior_week)}）',
            f'本月累计{verb}{fmt(month)}艘（环比 {change(month, prior_month)}，同比 {change(month, prior_year)}）')


def build_cards(port_catalog, choke_catalog, port_history, choke_history, vessels,
                port_day, choke_day, vessel_history=(), vessel_day=None, assets=()):
    cards = [activity_card('港口监测', port_catalog, port_history, 'portcalls', '停泊', port_day, True),
             activity_card('通道监测', choke_catalog, choke_history, 'n_total', '通过', choke_day)]
    day = vessel_day or date.today()
    region_groups = [('波斯湾', {'波斯湾'}), ('红海', {'红海', '红海北段', '红海南段', '苏伊士运河', '曼德海峡'})]
    vessel_lines = []
    for label, regions in region_groups:
        current = unique_mmsis(vessels, regions)
        def sample(start, end):
            rows = [v for v in vessel_history
                    if start.isoformat() <= str(v.get('observed_at', ''))[:10] <= end.isoformat()]
            found = unique_mmsis(rows, regions)
            return len(found) if found else None
        month, prior_month, prior_year = [sample(*w) for w in windows(day)[2:]]
        previous = sample(day - timedelta(days=7), day - timedelta(days=7))
        count = len(current) if vessels else None
        vessel_lines.extend([
            f'{label} {fmt(count)}艘（环比 {change(count, previous)}）',
            f'本月累计{fmt(month)}艘（环比 {change(month, prior_month)}，同比 {change(month, prior_year)}）',
        ])
    cards.append(('船只监测', '', *vessel_lines, 'AIS观测船只，统一按MMSI去重'))
    oil_fields = {(asset.get('country'), asset.get('name')) for asset in assets
                  if asset.get('asset_level') == 'field'
                  and asset.get('commodity') in {'crude_oil', 'oil_and_gas'}}
    cards.append(('油田监测', f'{len(oil_fields):,}个',
                  '上周产量 —万桶（环比 —）',
                  '本月累计 —万桶（环比 —，同比 —）'))
    return cards


def cards_html(cards, css_class='monitoring-cards'):
    return f'<div class="{css_class}">' + ''.join(
        '<div class="monitoring-card">' + f'<span>{escape(label)}</span>'
        + (f'<strong>{escape(value)}</strong>' if value else '')
        + ''.join(f'<small>{escape(line)}</small>' for line in lines) + '</div>'
        for label, value, *lines in cards) + '</div>'
