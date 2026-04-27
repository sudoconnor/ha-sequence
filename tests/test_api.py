"""Tests for Sequence API normalization."""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import types
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "sequence"

# Load api.py without importing custom_components.sequence.__init__, which requires Home Assistant.
sys.modules.setdefault("custom_components", types.ModuleType("custom_components"))
sys.modules["custom_components"].__path__ = [str(ROOT / "custom_components")]
sequence_package = types.ModuleType("custom_components.sequence")
sequence_package.__path__ = [str(COMPONENT)]
sys.modules["custom_components.sequence"] = sequence_package

spec = importlib.util.spec_from_file_location("custom_components.sequence.api", COMPONENT / "api.py")
assert spec and spec.loader
api = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = api
spec.loader.exec_module(api)


class SequenceApiNormalizationTest(unittest.TestCase):
    """Test Sequence API payload normalization."""

    def test_extract_accounts_from_sequence_envelope(self) -> None:
        accounts = api._extract_accounts(
            {
                "message": "OK",
                "data": {
                    "accounts": [
                        {
                            "id": "acct_1",
                            "name": "Household Spend",
                            "type": "pod",
                            "balance": {"amountInDollars": 123.45, "error": None},
                        }
                    ],
                    "errors": [],
                },
            }
        )

        self.assertEqual(len(accounts), 1)
        self.assertEqual(accounts[0].id, "acct_1")
        self.assertEqual(accounts[0].name, "Household Spend")
        self.assertEqual(accounts[0].type, "pod")
        self.assertEqual(accounts[0].balance, 123.45)
        self.assertEqual(accounts[0].currency, "USD")

    def test_extract_accounts_from_cents_and_formatted_balances(self) -> None:
        accounts = api._extract_accounts(
            {
                "accounts": [
                    {"id": "acct_1", "name": "A", "balance": {"amountInCents": 12345}},
                    {"id": "acct_2", "name": "B", "balance": {"formatted": "($10.25)"}},
                ]
            }
        )

        self.assertEqual(accounts[0].balance, 123.45)
        self.assertEqual(accounts[1].balance, -10.25)

    def test_extract_accounts_preserves_balance_errors(self) -> None:
        accounts = api._extract_accounts(
            {
                "accounts": [
                    {
                        "id": "acct_1",
                        "name": "A",
                        "balance": {"amountInDollars": None, "error": "temporarily_unavailable"},
                    }
                ]
            }
        )

        self.assertIsNone(accounts[0].balance)
        self.assertEqual(accounts[0].balance_error, "temporarily_unavailable")

    def test_extract_accounts_skips_items_without_ids(self) -> None:
        accounts = api._extract_accounts({"accounts": [{"name": "Nope"}, {"id": "acct_1"}]})

        self.assertEqual(len(accounts), 1)
        self.assertEqual(accounts[0].name, "Sequence Account")

    def test_bearer_header(self) -> None:
        self.assertEqual(api._bearer("abc"), "Bearer abc")
        self.assertEqual(api._bearer("Bearer abc"), "Bearer abc")


if __name__ == "__main__":
    unittest.main()
