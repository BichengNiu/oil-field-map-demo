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

    def test_source_query_failure_preserves_details_and_safe_query_context(self):
        error = {"error": {"code": 400, "message": "", "details": ["Invalid query parameters"]}}
        with patch.object(portwatch, "_LAST_REQUEST", time.monotonic() - 1), \
             patch("portwatch.urlopen", side_effect=lambda *a, **k: _Response(json.dumps(error).encode())):
            with self.assertRaises(ValueError) as failure:
                portwatch.query("https://example.test/query", where="portid='port105'",
                                token="must-not-be-logged")
        message = str(failure.exception)
        self.assertIn("Invalid query parameters", message)
        self.assertIn("port105", message)
        self.assertNotIn("must-not-be-logged", message)

    def test_generic_arcgis_query_error_retries_without_changing_the_query(self):
        responses = [
            {"error": {"code": 400, "message": "Cannot perform query. Invalid query parameters."}},
            {"count": 14},
        ]
        requests = []
        def respond(request, timeout):
            requests.append(request.full_url)
            return _Response(json.dumps(responses.pop(0)).encode())
        with patch.object(portwatch, "_LAST_REQUEST", time.monotonic() - 1), \
             patch("portwatch.urlopen", side_effect=respond), patch("portwatch._budget_sleep"):
            self.assertEqual(portwatch.query("https://example.test/query", where="portid='fso151'"),
                             {"count": 14})
        self.assertEqual(requests[0], requests[1])

    def test_persistent_backend_error_never_becomes_a_successful_empty_response(self):
        error = {"error": {"code": 400, "message": "Cannot perform query. Invalid query parameters."}}
        with patch.object(portwatch, "_LAST_REQUEST", time.monotonic() - 1), \
             patch("portwatch.urlopen", side_effect=lambda *a, **k: _Response(json.dumps(error).encode())) as query, \
             patch("portwatch._budget_sleep"):
            with self.assertRaisesRegex(ValueError, "Invalid query parameters"):
                portwatch.query("https://example.test/query")
        self.assertEqual(query.call_count, 3)


if __name__ == "__main__":
    unittest.main()
