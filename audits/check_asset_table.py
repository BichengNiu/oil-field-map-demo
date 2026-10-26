"""Offline full-population audit. Never collects sources or writes the database."""
from __future__ import annotations
import argparse
from collections import Counter
from decimal import Decimal
import itertools
import json
import os
from pathlib import Path
import re
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

def independent_daily(m):
    raw = str(m.get('value', '')).replace(',', '').strip()
    if re.search(r'[<>≥≤]|以上|以下|超过|至少', raw + str(m.get('value_qualifier', ''))):
        return None
    raw = re.sub(r'^(约|大约|近|≈|~)\s*', '', raw)
    numbers = re.split(r'\s*[–—−~至-]\s*', raw)
    try:
        values = [Decimal(n) for n in numbers]
    except Exception:
        return None
    if not 1 <= len(values) <= 2 or any(n < 0 for n in values):
        return None
    value = sum(values) / len(values)
    units = {'千桶/日': Decimal('.1'), '桶/日': Decimal('.0001'),
             '百万标准立方英尺/日': Decimal('0.028316846592'), '百万立方米/日': Decimal(1)}
    return float(value * units[m['unit']])

def audit(database=None):
    if database:
        os.environ['MONITORING_DB_PATH'] = str(database)
    os.environ['MONITORING_READ_ONLY'] = 'true'
    import data_store
    import production_units as p
    assets = data_store.load_catalog('assets')
    chosen, rows, column, means = p.statistical_view(assets)
    assert len({(a['country'], a['name']) for a in assets}) == len(assets)
    assert len({(o['scope_id'], o['product']) for o in chosen}) == len(rows)
    comparisons = []
    for o, row in zip(chosen, rows):
        expected = independent_daily(o['measurement'])
        assert (expected is None and row[column] is None) or abs(expected-row[column]) < 1e-10, o['scope_id']
        assert row['商品'] in {'原油', '天然气'} and '土耳其' not in row['国家']
        assert row['数据来源'].startswith(('http://', 'https://'))
        assert row['备注'] in {'真实产量', '估算产量'}
        assert all(row[key] for key in ['名称','国家','类型','包含资产','状态','数据时间'])
        assert re.search(r'[\u3400-\u9fff]', row['名称']) and '（' in row['名称']
        assert '待核名称' not in row['包含资产']
        comparisons.append({'scope_id': o['scope_id'], 'product': o['product'], 'row': row,
                            'source_measurement': {k: o['measurement'].get(k) for k in ['value','unit','commodity','metric_type','data_date','source_url','ownership_basis','basis','value_qualifier','note','annual_barrels','calendar_days']}, 'status_evidence': o['operating_state'], 'independent_numeric': expected,
                            'coverage': sorted(o['coverage'])})
    independent_means = {}
    for product in p.STATISTICAL_PRODUCTS:
        values = [independent_daily(o['measurement']) for o in chosen if o['product'] == product]
        values = [v for v in values if v is not None]
        independent_means[product] = sum(values)/len(values) if values else None
        assert means[product] == independent_means[product]
    countries = sorted({c for a in assets for c in a.get('countries', [a['country']]) if c != '土耳其'})
    filter_checks = 0
    for countries_filter in [[], *[[c] for c in countries], countries]:
        for products in [[], ['crude_oil'], ['natural_gas'], ['crude_oil', 'natural_gas']]:
            obs, table, _, _ = p.statistical_view(assets, countries_filter, products)
            mapped = p.map_units(assets, obs, table)
            assert {o['scope_id'] for o in obs} == {a['scope_id'] for a in mapped}
            assert sum(len(a['production_rows']) for a in mapped) == len(table)
            for product in products:
                subset = [o for o in obs if o['product'] == product]
                assert all(not a['coverage'] & b['coverage'] for a,b in itertools.combinations(subset,2))
            filter_checks += 1
    all_obs = p.build_observations([a for a in assets if a['country'] != '土耳其'])
    excluded = {product: [{'scope_id': o['scope_id'], 'reason': o['status'],
                          'product': o['product'], 'measurement_date': o['measurement'].get('data_date')}
                         for o in p.select_units(all_obs, product=product, prefer_actual=True,
                                                require_reliable=True)[1] if o['status'] != '选用']
                for product in p.STATISTICAL_PRODUCTS}
    mapped = p.map_units(assets, chosen, rows)
    return {'review_date':'2026-10-26', 'catalog_assets':len(assets), 'table_rows':len(rows),
            'products':dict(Counter(o['product'] for o in chosen)), 'distinct_scopes':len(mapped),
            'mapped_scopes':sum(a['map_drawable'] for a in mapped),
            'unlocated_scopes':[a['display_name'] for a in mapped if not a['map_drawable']],
            'producing_scopes':p.producing_count(chosen), 'independent_means':independent_means,
            'filter_combinations_checked':filter_checks, 'unknown_production_years':sum(r['数据时间']=='未明确' for r in rows),
            'null_numeric_rows':sum(r[column] is None for r in rows),
            'remark_counts':dict(Counter(r['备注'] for r in rows)),
            'source_limitations':['Al-Omar来源仅摘要级核对；未取得LeMonde全文',
                                  '状态为最近可核实带时点记录，非实时生产监测',
                                  '地图未定位资产不使用代理点、区域中心或组成田均值伪造位置',
                                  '来源核查重用2026-10-25保存的原文，并于2026-10-26重新请求77个链接；可访问不等于事实验证'],
            'rows':comparisons, 'exclusion_ledger':excluded}

if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--database');parser.add_argument('--output',required=True)
    args=parser.parse_args();result=audit(args.database)
    Path(args.output).write_text(json.dumps(result,ensure_ascii=False,default=str,indent=2))
    print(json.dumps({k:v for k,v in result.items() if k not in {'rows','exclusion_ledger'}},ensure_ascii=False,indent=2))
