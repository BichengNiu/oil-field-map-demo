"""A truncated AIS query is complete only after all smaller requests succeed."""
import io
import json
import os
import unittest
from unittest.mock import patch

import ais


class AisQuerySplitTest(unittest.TestCase):
    def result(self, count, truncated=False):
        return io.BytesIO(json.dumps({
            'type': 'FeatureCollection', 'features': [{'id': i} for i in range(count)],
            'attribution': {'test': 'provider'}, 'truncated': truncated,
        }).encode())

    def test_partial_parent_is_replaced_by_complete_child_responses(self):
        with patch.dict(os.environ, {'MONITORING_READ_ONLY': 'false'}), \
             patch('ais.data_store.save_query') as save, \
             patch('ais.urlopen', side_effect=[self.result(1, True), self.result(2), self.result(3)]) as request:
            result = ais._fetch_openwaters_group(((20, 24, 40, 50),), 120)
        self.assertEqual(len(result['features']), 5)
        self.assertFalse(result['truncated'])
        urls = [call.args[0].full_url for call in request.call_args_list]
        self.assertIn('40%2C24%2C45.0', urls[1])
        self.assertIn('45.0%2C24%2C50', urls[2])
        self.assertEqual(save.call_count, 3)

    def test_persistent_truncation_is_bounded_and_still_reported(self):
        with patch.dict(os.environ, {'MONITORING_READ_ONLY': 'false'}), \
             patch('ais.data_store.save_query'), \
             patch('ais.urlopen', side_effect=lambda *a, **kw: self.result(1, True)) as request:
            result = ais._fetch_openwaters_group(((20, 24, 40, 50),), 120)
        self.assertTrue(result['truncated'])
        self.assertEqual(request.call_count, 15)

    def test_child_failure_rejects_the_whole_query(self):
        with patch.dict(os.environ, {'MONITORING_READ_ONLY': 'false'}), \
             patch('ais.data_store.save_query'), \
             patch('ais.urlopen', side_effect=[self.result(1, True), self.result(2), TimeoutError('source offline')]):
            with self.assertRaises(TimeoutError):
                ais._fetch_openwaters_group(((20, 24, 40, 50),), 120)


if __name__ == '__main__':
    unittest.main()
