"""Bound PortWatch request time across a single explicit refresh operation."""
import io
import json
import time
import unittest
from unittest.mock import patch

import portwatch


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class PortWatchBudgetTest(unittest.TestCase):
    def test_request_timeout_is_capped_by_remaining_operation_budget(self):
        timeouts = []

        def response(_request, timeout):
            timeouts.append(timeout)
            return _Response(json.dumps({"features": []}).encode())

        with patch.object(portwatch, "_LAST_REQUEST", time.monotonic() - 1), \
             patch("portwatch.urlopen", side_effect=response):
            with portwatch.request_budget(0.25):
                result = portwatch.query("https://example.test/FeatureServer/0/query")

        self.assertEqual(result, {"features": []})
        self.assertEqual(len(timeouts), 1)
        self.assertGreater(timeouts[0], 0)
        self.assertLessEqual(timeouts[0], 0.25)

    def test_retry_backoff_stops_when_it_would_exceed_operation_budget(self):
        calls = []

        def response(_request, timeout):
            calls.append(timeout)
            return _Response(json.dumps({"error": {"message": "Too many requests"}}).encode())

        with patch.object(portwatch, "_LAST_REQUEST", time.monotonic() - 1), \
             patch("portwatch.urlopen", side_effect=response):
            with portwatch.request_budget(0.25):
                with self.assertRaises(portwatch.RequestBudgetExceeded):
                    portwatch.query("https://example.test/FeatureServer/0/query")

        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
