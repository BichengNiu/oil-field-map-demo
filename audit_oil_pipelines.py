"""Reconcile map coverage/geometry and capacity decisions with the pinned raw export.

Usage: python audit_oil_pipelines.py downloaded-goit.geojson --csv data/pipeline_audit.csv
No network requests or database writes.
"""
import argparse
from collections import Counter
import csv
from decimal import Decimal
import hashlib
import json
from pathlib import Path

from shapely.geometry import shape

from build_pipeline_data import COUNTRIES, SOURCE_SHA256
import pipeline_catalog
from pipeline_capacity import million_bpd

ROOT = Path(__file__).parent


def audit(source_path, csv_path=None):
    raw = Path(source_path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA256:
        raise ValueError('Raw source SHA256 mismatch')
    source = json.loads(raw)
    document = pipeline_catalog.validate(json.loads((ROOT / pipeline_catalog.DOCUMENT).read_text()))
    review = json.loads((ROOT / 'data/pipeline_capacity_review.json').read_text())
    source_rows = {}
    for feature in source['features']:
        p = feature['properties']
        countries = {x.strip() for x in p.get('CountriesOrAreas', '').split(';')}
        countries.update((p.get('StartCountryOrArea'), p.get('EndCountryOrArea')))
        if p['Fuel'] == 'Oil' and countries.intersection(COUNTRIES):
            if p['ProjectID'] in source_rows:
                raise ValueError('Duplicate key in raw source')
            source_rows[p['ProjectID']] = feature
    actual = {f['properties']['project_id']: f for f in document['features']}
    if set(actual) != set(source_rows):
        raise ValueError('Missing or extra scope routes')
    decisions = {r['project_id']: r for r in review['records']}
    if set(decisions) != set(actual):
        raise ValueError('Capacity review is incomplete')
    rows = []
    for pid, feature in sorted(actual.items()):
        p = feature['properties']
        original = source_rows[pid]['properties']
        if (p['capacity'], p['capacity_unit']) != (original['Capacity'], original['CapacityUnits']):
            raise ValueError('Raw capacity evidence changed: ' + pid)
        if p['capacity_million_bpd'] != decisions[pid]['capacity_million_bpd']:
            raise ValueError('Displayed capacity differs from review: ' + pid)
        if p['capacity_million_bpd'] is not None and p['capacity_review_status'] != 'primary_capacity_confirmed':
            if p['capacity_million_bpd'] != million_bpd(p['capacity'], p['capacity_unit']):
                raise ValueError('Wrong factor of one million: ' + pid)
        old, new = shape(source_rows[pid]['geometry']), shape(feature['geometry'])
        if old.geom_type != new.geom_type or old.hausdorff_distance(new) > .00301:
            raise ValueError('Geometry changed beyond declared simplification: ' + pid)
        if hasattr(old, 'geoms') and len(old.geoms) != len(new.geoms):
            raise ValueError('A geometry branch was lost: ' + pid)
        rows.append({
            'project_id': pid, 'pipeline': p['name_en'], 'segment': p['segment'],
            'countries': '; '.join(p['countries']), 'status': p['status'],
            'source_capacity': p['capacity'], 'source_unit': p['capacity_unit'],
            'million_barrels_per_day': p['capacity_million_bpd'],
            'range_million_barrels_per_day': '—'.join(p.get('capacity_range_million_bpd', [])),
            'review_status': p['capacity_review_status'], 'capacity_basis': p['capacity_basis'],
            'capacity_reference_date': p['capacity_reference_date'],
            'capacity_reference_url': p['capacity_reference_url'], 'record_date': p['updated_at'],
            'route_accuracy': p['route_accuracy'], 'geometry_check': 'within_0.003_degrees',
        })
    if csv_path:
        with Path(csv_path).open('w', encoding='utf-8-sig', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    return {
        'mapped_scope_expected': len(source_rows), 'mapped_scope_actual': len(actual),
        'missing_ids': sorted(set(source_rows)-set(actual)), 'extra_ids': sorted(set(actual)-set(source_rows)),
        'capacity_review_status': dict(Counter(row['review_status'] for row in rows)),
        'numeric_single_capacities': sum(row['million_barrels_per_day'] is not None for row in rows),
        'coverage_limits': review['coverage']['known_source_geometry_gaps'],
        'source_page_access': review['reference_page_summary'],
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source')
    parser.add_argument('--csv')
    options = parser.parse_args()
    print(json.dumps(audit(options.source, options.csv), ensure_ascii=False, indent=2))
