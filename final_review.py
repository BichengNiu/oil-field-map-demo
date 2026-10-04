"""October follow-up decisions; retain source dates and unresolved evidence."""
import json
from pathlib import Path

REVIEW_DATE = '2026-10-04'
EVIDENCE = json.loads(Path(__file__).with_name('FINAL_REVIEW_2026-10-04.json').read_text())
ADDED = {(r['country'], r['name']) for r in EVIDENCE['additions']}
MEASURED = {(r['country'], r['name']) for r in EVIDENCE['measurements']}
STATUS_REVIEWED = {(r['country'], r['name']) for r in EVIDENCE['statuses']} | ADDED


def additions(record):
    output = []
    for row in EVIDENCE['additions']:
        item = record(row['country'], row['name'], row['name_cn'], row['asset_type'],
                      None, None, source=row['source'], source_url=row['source_url'], note=row['note'])
        item['catalog_evidence_url'] = row['source_url']
        output.append(item)
    return output


def apply_measurements(assets):
    index = {(a['country'], a['name']): a for a in assets}
    for row in EVIDENCE['measurements']:
        item = index[row['country'], row['name']]
        item.setdefault('catalog_evidence_url', item['source_url'])
        item.update({k: v for k, v in row.items() if k not in {'country', 'name'}})


def levels():
    return {(r['country'], r['name']): r['asset_level'] for r in EVIDENCE['additions']}


def register_statuses(assign):
    for row in EVIDENCE['additions']:
        assign(row['country'], row['name'], row['state'], row['as_of'],
               row['confidence'], row['status_basis'], row['status_url'])


def revise_statuses(revise):
    for row in EVIDENCE['statuses']:
        revise(row['country'], row['name'], row['state'], row['as_of'],
               row['confidence'], row['status_basis'], row['status_url'])


def finish_review(assets):
    index = {(a['country'], a['name']): a for a in assets}
    for row in EVIDENCE['shared_countries']:
        item = index[row['country'], row['name']]
        item.update(countries=row['countries'], shared_country_evidence_url=row['evidence_url'])
    reviewed = ADDED | MEASURED | STATUS_REVIEWED
    for row in EVIDENCE['notes']:
        key = row['country'], row['name']
        reviewed.add(key)
        index[key]['note'] += ' ' + row['note']
        index[key].setdefault('followup_evidence', []).append(row)
    index["科威特", "Homah"]["aliases"].append("Houma")
    for key in reviewed:
        item = index[key]
        item['data_audit_date'] = REVIEW_DATE
        item['freshness_note'] = '仅适用于标注的证据期；复核日不是产量或停复产观测日'
        if key in STATUS_REVIEWED:
            item['status_audit_date'] = REVIEW_DATE
