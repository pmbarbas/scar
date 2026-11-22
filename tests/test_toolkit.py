from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from scar_toolkit.kit import run_kit


class ToolkitSmokeTests(unittest.TestCase):
    def test_installed_core_recovery_test_kit(self):
        result = run_kit()
        self.assertEqual(result["status"], "PASS")
        self.assertIn("digest_only_abstains", result["checks"])
        self.assertEqual(result["core_outcome"], "STALE_EPOCH")
        from scar_toolkit.cli import main
        output = io.StringIO()
        with patch("importlib.metadata.version", return_value="0.2.0"):
            with redirect_stdout(output):
                self.assertEqual(main(["version"]), 0)
        version = json.loads(output.getvalue())
        self.assertEqual(version, {"toolkit": "0.2.0", "core_api": "0.2.0"})


if __name__ == "__main__":
    unittest.main()
