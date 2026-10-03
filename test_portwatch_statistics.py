"""Contract tests for the PortWatch statistics eligibility API."""
import ast
from pathlib import Path
import re
import unittest


def portwatch_api():
    tree = ast.parse(Path(__file__).with_name("portwatch.py").read_text(encoding="utf-8"))
    functions = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name in {"_valid_port_ids", "has_independent_statistics"}
    ]
    namespace = {"re": re}
    exec(compile(ast.Module(body=functions, type_ignores=[]), "portwatch.py", "exec"), namespace)
    return namespace["has_independent_statistics"]


class PortWatchStatisticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.check = staticmethod(portwatch_api())

    def test_catalog_flag_is_authoritative(self):
        self.assertTrue(self.check({
            "portid": "port123", "statistics_available": True,
        }))
        self.assertFalse(self.check({
            "portid": "port123", "statistics_available": False,
        }))

    def test_only_supported_portwatch_id_prefixes_are_eligible(self):
        self.assertTrue(self.check({"portid": "port123"}))
        self.assertTrue(self.check({"portid": "fso7"}))
        self.assertFalse(self.check({"portid": "wpi123"}))


if __name__ == "__main__":
    unittest.main()
