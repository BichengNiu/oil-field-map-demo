"""Report data boundary tests independent of a live PortWatch source."""
import unittest

import report_data


class ReportDataTests(unittest.TestCase):
    def test_latest_rows_match_by_node_and_keep_nodes_without_history(self):
        catalog = [
            {"portid": "port1", "name": "港一"},
            {"portid": "port2", "name": "港二"},
        ]
        history = [
            {"portid": "port1", "date": "2026-09-24", "portcalls": 5},
            {"portid": "port1", "date": "2026-09-25", "portcalls": 8},
            {"portid": "unknown", "date": "2026-09-25", "portcalls": 99},
        ]

        rows = report_data.merge_latest_rows(catalog, history)

        self.assertEqual(rows[0]["portcalls"], 8)
        self.assertNotIn("date", rows[1])
        self.assertEqual([row["portid"] for row in rows], ["port1", "port2"])


if __name__ == "__main__":
    unittest.main()
