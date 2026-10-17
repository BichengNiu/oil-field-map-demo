"""Windy webcam metadata, adapted from Eagle Eye's camera source boundary.

Only snapshot_update collects. The map reads the published catalog and loads
Windy's public player on explicit clicks; API credentials never leave Python.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from urllib.parse import urlsplit

import time

import requests
import data_store

API = 'https://api.windy.com/webcams/api/v3/webcams'
CATALOG_KEY = 'windy_webcam_catalog'
STATUS_KEY = 'windy_webcam_status'
COUNTRY_GROUPS = ('AE,SA,IR,OM,EG,QA,IQ,KW,BH,YE', 'DJ')
PLAYER_HOSTS = {'webcams.windy.com', 'windy.com', 'www.windy.com', 'player.windy.com'}
PERIODS = ('live', 'day', 'month', 'year', 'lifetime')


def player_url(value):
    # V3 returns strings. Eagle Eye's original parser assumes the old nested
    # day.embed shape, which would discard valid V3 replay URLs.
    if isinstance(value, dict):
        if value.get('available') is False:
            return None
        value = value.get('embed')
    if not isinstance(value, str):
        return None
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError:
        return None
    if (parts.scheme != 'https' or parts.hostname not in PLAYER_HOSTS
            or parts.username or parts.password or port not in (None, 443)):
        return None
    return value


def parse_cameras(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get('webcams'), list):
        raise ValueError('Windy webcam response has no webcams list')
    result = {}
    for row in payload['webcams']:
        if not isinstance(row, dict) or row.get('status') != 'active':
            continue
        location = row.get('location') or {}
        try:
            lat, lon = float(location['latitude']), float(location['longitude'])
        except (KeyError, TypeError, ValueError):
            continue
        webcam_id = str(row.get('webcamId') or row.get('id') or '')
        if not webcam_id.isdigit() or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue
        players = {period: url for period in PERIODS
                   if (url := player_url((row.get('player') or {}).get(period)))}
        if not players:
            continue
        result[webcam_id] = {'id': webcam_id, 'title': str(row.get('title') or webcam_id),
                            'lat': lat, 'lon': lon, 'players': players,
                            'updated_at': row.get('lastUpdatedOn'),
                            'source_url': f'https://www.windy.com/webcams/{webcam_id}',
                            'source': 'Windy Webcams'}
    return list(result.values())


def collect(now=None):
    """Optional source. Failures retain the last catalog and report its state."""
    if data_store.read_only():
        raise RuntimeError('Webcam collection is only available to the snapshot publisher')
    now = now or datetime.now(timezone.utc)
    key = data_store.setting('WINDY_WEBCAMS_KEY')
    previous = data_store.meta(STATUS_KEY, {}) or {}
    if not key:
        status = {**previous, 'status': 'not_configured', 'checked_at': now.isoformat()}
        data_store.set_meta(STATUS_KEY, status)
        return status
    try:
        last = datetime.fromisoformat(previous.get('completed_at', ''))
        if previous.get('status') == 'ok' and timedelta(0) <= now - last < timedelta(hours=4):
            return previous
    except (ValueError, TypeError):
        pass
    cameras, truncated = {}, False
    # Only the project's eleven countries, bounded pagination and total budget.
    # No world-wide scans and no new background worker/schedule.
    deadline = time.monotonic() + 60
    try:
        for countries in COUNTRY_GROUPS:
            offset = 0
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('Webcam collection budget exceeded')
                response = requests.get(API, params={'countries': countries, 'limit': 50,
                    'offset': offset, 'include': 'location,player,urls'},
                    headers={'x-windy-api-key': key}, timeout=min(12, remaining))
                if response.status_code != 200:
                    raise ValueError(f'Windy HTTP {response.status_code}')
                payload = response.json()
                for camera in parse_cameras(payload):
                    cameras[camera['id']] = camera
                count = len(payload['webcams'])
                offset += count
                total = payload.get('total', offset)
                if count < 50 or offset >= total:
                    break
                if offset >= 1000:
                    truncated = True
                    break
        status = {'status': 'ok', 'completed_at': now.isoformat(),
                  'count': len(cameras), 'truncated': truncated}
        data_store.set_meta(CATALOG_KEY, list(cameras.values()))
    except Exception as exc:
        # Do not persist raw exception/request strings: they can contain secrets.
        status = {**previous, 'status': 'error', 'checked_at': now.isoformat(),
                  'error': type(exc).__name__}
    data_store.set_meta(STATUS_KEY, status)
    return status


def published():
    """Read only; safe for old snapshots and environments without a key."""
    return {'cameras': data_store.meta(CATALOG_KEY, []) or [],
            'status': data_store.meta(STATUS_KEY, {'status': 'not_configured'}) or {}}
