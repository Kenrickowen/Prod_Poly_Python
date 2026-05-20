from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from polymarket_python.models import AppState
from polymarket_python.runtime_config import load_position_size, save_position_size


class RuntimeConfigTests(unittest.TestCase):
    def test_position_size_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "position_size.json"
            state = AppState()
            state.position_size_mode = "percent"
            state.position_fixed_usd = 7.5
            state.position_equity_percent = 3.25

            save_position_size(state, path)

            loaded = AppState()
            load_position_size(loaded, path)

            self.assertEqual(loaded.position_size_mode, "percent")
            self.assertEqual(loaded.position_fixed_usd, 7.5)
            self.assertEqual(loaded.position_equity_percent, 3.25)


if __name__ == "__main__":
    unittest.main()
