"""Compatibility tests for pure app helpers that need no Streamlit runtime."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest


class AppHelperTests(unittest.TestCase):
    def test_independent_statistics_fallback_handles_old_portwatch_modules(self):
        tree = ast.parse(Path(__file__).with_name("app.py").read_text(encoding="utf-8"))
        function = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "_has_independent_port_statistics"
        )
        namespace = {"PORTWATCH": SimpleNamespace()}
        exec(compile(ast.Module(body=[function], type_ignores=[]), "app.py", "exec"), namespace)
        check = namespace["_has_independent_port_statistics"]

        self.assertTrue(check({"portid": "port123"}))
        self.assertTrue(check({"portid": "fso7"}))
        self.assertFalse(check({"portid": "wpi123"}))
        self.assertFalse(check({"portid": "port123", "statistics_available": False}))


if __name__ == "__main__":
    unittest.main()
