"""Shared report/map cards with daily counts and confirmed sea-passage totals."""
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


SEA_MONITORING_AREAS = ('波斯湾', '红海', '阿曼湾', '亚丁湾')


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


def sea_activity_card(history, day):
    """Sum verified daily entry events across all four seas.

    Rows contain sea, date, and passages. Repeated confirmed entries by the
    same MMSI are separate passages. A reported zero is valid; missing sea/day
    records remain unavailable. AIS position samples are not passage events.
    """
    rows = [{'portid': row.get('sea'), 'date': row.get('date'),
             'passages': row.get('passages')} for row in history]
    values = [None] * 5
    if day:
        periods = windows(day)
        values[:2] = [total(rows, set(SEA_MONITORING_AREAS), 'passages', *window)
                      for window in periods[:2]]
        # Provider history consists of completed natural days. Use the latest
        # common completed day within THIS month, without moving the week anchor
        # backwards on Monday or silently presenting a previous month as current.
        coverage = {sea: {str(r.get('date'))[:10] for r in history
                          if r.get('sea') == sea and number(r.get('passages')) is not None}
                    for sea in SEA_MONITORING_AREAS}
        common = set.intersection(*coverage.values())
        current = sorted(d for d in common if day.replace(day=1).isoformat() <= d <= day.isoformat())
        if current:
            month_day = date.fromisoformat(current[-1])
            values[2:] = [total(rows, set(SEA_MONITORING_AREAS), 'passages', *window)
                          for window in windows(month_day)[2:]]
    week, prior_week, month, prior_month, prior_year = values
    return ('海域监测', f'{len(SEA_MONITORING_AREAS)}个',
            f'上周累计通过{fmt(week)}艘次（环比 {change(week, prior_week)}）',
            f'本月累计通过{fmt(month)}艘次（环比 {change(month, prior_month)}，同比 {change(month, prior_year)}）')


def build_cards(port_catalog, choke_catalog, port_history, choke_history, vessels,
                port_day, choke_day, vessel_day=None, assets=(), sea_passage_history=()):
    cards = [activity_card('港口监测', port_catalog, port_history, 'portcalls', '停泊', port_day, True),
             activity_card('通道监测', choke_catalog, choke_history, 'n_total', '通过', choke_day)]
    cards.append(sea_activity_card(sea_passage_history, vessel_day or date.today()))
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
