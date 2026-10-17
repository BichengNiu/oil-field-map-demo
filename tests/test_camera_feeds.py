"""Camera capability, publication and credential isolation contracts."""
from datetime import datetime, timezone
import os
import unittest
from unittest.mock import patch, Mock

import camera_feeds as cameras


def payload(players=None):
    return {'total': 1, 'webcams': [{'webcamId': 123, 'status': 'active',
        'title': 'Port Camera', 'location': {'latitude': 26.5, 'longitude': 56.4},
        'lastUpdatedOn': '2026-10-17T00:00:00Z',
        'player': players or {'day': 'https://webcams.windy.com/webcams/public/embed/player/123/day'}}]}


class CameraFeedsTest(unittest.TestCase):
    def test_v3_replay_is_not_mislabelled_as_live_and_bad_urls_rejected(self):
        result = cameras.parse_cameras(payload())[0]
        self.assertIn('day', result['players'])
        self.assertNotIn('live', result['players'])
        for url in ['javascript:alert(1)', 'https://evil.example/live',
                    'https://webcams.windy.com@evil.example/live',
                    'https://webcams.windy.com:bad/live', 'http://webcams.windy.com/live']:
            self.assertIsNone(cameras.player_url(url))
        self.assertIsNone(cameras.player_url({'available': False, 'embed': 'https://webcams.windy.com/live'}))
        self.assertEqual(cameras.parse_cameras(payload({'live': {'embed': 'https://webcams.windy.com/live'}}))[0]['players']['live'], 'https://webcams.windy.com/live')

    def test_invalid_positions_and_inactive_cameras_are_not_displayed(self):
        value = payload()
        value['webcams'][0]['location']['latitude'] = float('nan')
        self.assertEqual(cameras.parse_cameras(value), [])
        value = payload();value['webcams'][0]['status'] = 'inactive'
        self.assertEqual(cameras.parse_cameras(value), [])
        with self.assertRaises(ValueError):cameras.parse_cameras({'error':'quota'})

    def test_missing_key_does_not_network_or_delete_last_catalog(self):
        with patch('data_store.read_only', return_value=False), patch('data_store.setting',return_value=''), \
             patch('data_store.meta',return_value={}), patch('data_store.set_meta') as save, \
             patch('requests.get') as upstream:
            self.assertEqual(cameras.collect()['status'], 'not_configured')
            upstream.assert_not_called()
            self.assertTrue(all(c.args[0] != cameras.CATALOG_KEY for c in save.call_args_list))

    def test_failed_source_preserves_catalog_without_leaking_request_or_secret(self):
        with patch('data_store.read_only',return_value=False), patch('data_store.setting',return_value='secret-key'), \
             patch('data_store.meta',return_value={}), patch('data_store.set_meta') as save, \
             patch('requests.get',side_effect=RuntimeError('secret-key')):
            result=cameras.collect()
            self.assertEqual(result['status'],'error')
            self.assertNotIn('secret-key',str(save.call_args_list))
            self.assertTrue(all(c.args[0] != cameras.CATALOG_KEY for c in save.call_args_list))

    def test_publisher_deduplicates_countries_and_keeps_key_in_header(self):
        response=Mock(status_code=200);response.json.return_value=payload()
        with patch('data_store.read_only',return_value=False), patch('data_store.setting',return_value='secret-key'), \
             patch('data_store.meta',return_value={}), patch('data_store.set_meta') as save, \
             patch('requests.get',return_value=response) as upstream:
            self.assertEqual(cameras.collect()['count'],1)
            self.assertEqual(upstream.call_count,2)
            self.assertEqual(upstream.call_args.kwargs['headers']['x-windy-api-key'],'secret-key')
            self.assertNotIn('secret-key',str(upstream.call_args.kwargs['params']))
            saved=[c.args[1] for c in save.call_args_list if c.args[0]==cameras.CATALOG_KEY][0]
            self.assertEqual(len(saved),1)
            self.assertNotIn('secret-key',str(saved))

    def test_display_boundary_never_collects(self):
        with patch('data_store.meta',return_value=[]), patch('requests.get') as upstream:
            cameras.published();upstream.assert_not_called()
        with patch('data_store.read_only',return_value=True):
            with self.assertRaises(RuntimeError):cameras.collect()
