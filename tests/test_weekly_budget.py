"""Tests for the read-only weekly budget."""

from __future__ import annotations

import json
import pathlib
import unittest
from datetime import UTC, datetime, timedelta

from sequence_test_loader import COMPONENT, load_sequence_module

budget = load_sequence_module("budget")
api = load_sequence_module("api")
platform_api = load_sequence_module("platform_api")

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"
ACCOUNT_ID = "d29dfeca-1111-4000-8000-000000000001"
CARD_ID = "3d2a8b91-3f1e-4a73-9f6a-7c1d2e3b4a55"
RECORDED_CARD_KEYS = {
    "id",
    "account",
    "amountInCents",
    "cardId",
    "cardType",
    "completedAt",
    "createdAt",
    "description",
    "direction",
    "status",
    "subtype",
}


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


class WeeklyBudgetMathTest(unittest.TestCase):
    """Cover cycle bounds, refill exclusion, and spend math."""

    def setUp(self) -> None:
        self.tz = budget.zone_for("America/New_York")
        self.now = datetime(2026, 10, 16, 15, 0, tzinfo=self.tz)
        self.account = budget.parse_account(_load("account.json"))
        self.transactions = budget.parse_card_transactions(
            budget.items_from_envelope(_load("card_transactions.json"))
        )
        self.transfers = budget.parse_transfers(budget.items_from_envelope(_load("transfers.json")))

    def _compute(self, **overrides):
        values = {
            "account_id": ACCOUNT_ID,
            "account": self.account,
            "budget_dollars": 400,
            "refill_weekday": "friday",
            "card_id": None,
            "transactions": self.transactions,
            "transfers": self.transfers,
            "now": self.now,
            "tz": self.tz,
        }
        values.update(overrides)
        return budget.compute_weekly_budget(**values)

    def test_recorded_card_transaction_shape(self) -> None:
        payload = _load("card_transactions.json")
        self.assertEqual(set(payload), {"requestId", "data"})
        self.assertEqual(set(payload["data"]), {"items", "pagination"})
        for item in payload["data"]["items"]:
            self.assertEqual(set(item), RECORDED_CARD_KEYS)

        parsed = self.transactions[0]
        self.assertEqual(parsed.id, "5fb1c2a4-7d1e-4b08-9d2c-2e5b1d6a4c12")
        self.assertEqual(parsed.amount_cents, 2000)
        self.assertEqual(parsed.direction, "MONEY_OUT")
        self.assertEqual(parsed.description, "BLUE BOTTLE COFFEE")
        self.assertEqual(parsed.card_id, CARD_ID)
        self.assertEqual(parsed.subtype, "PURCHASE")
        self.assertEqual(parsed.status, "COMPLETE")

    def test_recorded_account_uses_available_balance(self) -> None:
        self.assertEqual(self.account.spendable_cents, 35000)
        self.assertEqual(self.account.ledger_cents, 36000)
        self.assertEqual(self.account.hold_cents, 1000)
        self.assertEqual(self.account.balance_source, "available")
        self.assertEqual(self.account.name, "Household Spend")

    def test_ledger_balance_is_used_when_available_is_missing(self) -> None:
        payload = _load("account.json")
        payload["data"]["balance"]["availableBalanceInCents"] = None
        account = budget.parse_account(payload)
        self.assertEqual(account.spendable_cents, 36000)
        self.assertEqual(account.balance_source, "ledger")

    def test_missing_balance_cannot_build_a_snapshot(self) -> None:
        payload = _load("account.json")
        payload["data"]["balance"] = {
            "balanceInCents": None,
            "availableBalanceInCents": None,
            "holdInCents": None,
            "error": "temporarily_unavailable",
        }
        account = budget.parse_account(payload)
        with self.assertRaises(budget.BudgetDataError):
            self._compute(account=account)

    def test_friday_cycle_starts_at_local_midnight(self) -> None:
        start, nxt = budget.cycle_bounds(self.now, budget.weekday_index("friday"), self.tz)
        self.assertEqual(start, datetime(2026, 10, 16, 0, 0, tzinfo=self.tz))
        self.assertEqual(nxt, datetime(2026, 10, 23, 0, 0, tzinfo=self.tz))
        self.assertEqual(budget.to_rfc3339(start), "2026-10-16T04:00:00Z")

        thursday_night = datetime(2026, 10, 15, 23, 59, tzinfo=self.tz)
        previous, upcoming = budget.cycle_bounds(
            thursday_night, budget.weekday_index("friday"), self.tz
        )
        self.assertEqual(previous, datetime(2026, 10, 9, 0, 0, tzinfo=self.tz))
        self.assertEqual(upcoming, datetime(2026, 10, 16, 0, 0, tzinfo=self.tz))

        exactly = datetime(2026, 10, 16, 0, 0, tzinfo=self.tz)
        start, _nxt = budget.cycle_bounds(exactly, 4, self.tz)
        self.assertEqual(start, exactly)

    def test_refill_is_excluded_and_other_incoming_transfers_are_top_ups(self) -> None:
        snapshot = self._compute()

        self.assertTrue(snapshot.refill_excluded)
        self.assertEqual(snapshot.refill_amount, 400.0)
        self.assertEqual(snapshot.refill_transfer_id, "809e5e0b-bb0b-49b2-867a-8b44d04d9179")
        self.assertEqual(snapshot.top_ups, 50.0)
        self.assertEqual(snapshot.top_up_count, 1)
        self.assertEqual(snapshot.pending_incoming, 10.0)
        self.assertEqual(snapshot.spent_settled, 45.0)
        self.assertEqual(snapshot.spent_incl_pending, 100.0)
        self.assertEqual(snapshot.pending, 55.0)
        self.assertEqual(snapshot.remaining, 350.0)
        self.assertEqual(snapshot.balance, 350.0)
        self.assertEqual(snapshot.percent, 87.5)
        self.assertEqual(snapshot.ratio, 0.875)
        self.assertEqual(snapshot.status, "Healthy")
        self.assertEqual(snapshot.days_until_refill, 6.38)
        self.assertEqual(snapshot.days_elapsed, 0.625)
        self.assertEqual(snapshot.burn_rate, 160.0)
        self.assertEqual(snapshot.safe_daily_allowance, 54.86)
        self.assertEqual(snapshot.average_transaction, 25.0)
        self.assertEqual(snapshot.median_transaction, 25.0)
        self.assertEqual(snapshot.largest_transaction, 30.0)
        self.assertEqual(snapshot.purchase_count, 2)
        self.assertEqual(snapshot.top_merchant, "GROCERY")
        self.assertEqual(snapshot.top_merchant_spent, 30.0)
        self.assertEqual(snapshot.transaction_count, 3)
        self.assertEqual(
            list(snapshot.daily),
            [
                {"date": "2026-10-16", "spent": 20.0, "count": 1},
                {"date": "2026-10-17", "spent": 25.0, "count": 2},
            ],
        )
        merchants = {row["merchant"]: row for row in snapshot.merchants}
        self.assertEqual(merchants["GROCERY"]["spent"], 30.0)
        self.assertEqual(merchants["BLUE BOTTLE COFFEE"]["spent"], 15.0)
        self.assertFalse(snapshot.transactions_truncated)
        self.assertLess(budget.json_size(budget.transactions_attributes(snapshot)), 16384)
        self.assertLess(budget.json_size(budget.breakdown_attributes(snapshot)), 16384)

    def test_status_thresholds_use_remaining_balance(self) -> None:
        critical = self._account_with_cents(4000)
        low = self._account_with_cents(8000)
        just_over_low = self._account_with_cents(8001)
        just_over_critical = self._account_with_cents(4001)
        self.assertEqual(self._compute(account=critical).status, "Critical")
        self.assertEqual(self._compute(account=low).status, "Low")
        self.assertEqual(self._compute(account=just_over_critical).status, "Low")
        self.assertEqual(self._compute(account=just_over_low).status, "Healthy")
        self.assertEqual(self._compute(account=self._account_with_cents(-100)).status, "Critical")

    def test_later_budget_sized_transfer_is_a_top_up(self) -> None:
        transfers = [
            self._transfer("early", 40000, "2026-10-16T04:02:00Z", origin="RULE"),
            self._transfer("later", 40000, "2026-10-20T15:00:00Z", origin="USER"),
        ]
        snapshot = self._compute(transfers=transfers, transactions=[])
        self.assertEqual(snapshot.refill_transfer_id, "early")
        self.assertEqual(snapshot.top_ups, 400.0)
        self.assertEqual(snapshot.top_up_count, 1)

    def test_rule_transfer_is_the_refill_when_the_amount_differs(self) -> None:
        transfers = [
            self._transfer("manual", 2500, "2026-10-16T04:10:00Z", origin="USER"),
            self._transfer("rule", 37500, "2026-10-16T05:00:00Z", origin="RULE"),
        ]
        snapshot = self._compute(transfers=transfers, transactions=[])
        self.assertEqual(snapshot.refill_transfer_id, "rule")
        self.assertEqual(snapshot.top_ups, 25.0)

    def test_card_filter_and_refunds(self) -> None:
        other = budget.CardTransaction(
            id="other-card",
            card_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            direction="MONEY_OUT",
            subtype="PURCHASE",
            status="COMPLETE",
            amount_cents=9000,
            description="OTHER CARD",
            created_at=_utc("2026-10-16T20:00:00Z"),
            completed_at=_utc("2026-10-16T20:00:00Z"),
        )
        snapshot = self._compute(transactions=[*self.transactions, other], card_id=CARD_ID)
        self.assertEqual(snapshot.spent_settled, 45.0)
        self.assertEqual(snapshot.transaction_count, 3)

    def test_even_purchase_count_median(self) -> None:
        purchases = [
            self._card("a", 1000, "MONEY_OUT"),
            self._card("b", 4000, "MONEY_OUT", created="2026-10-17T12:00:00Z"),
        ]
        snapshot = self._compute(transactions=purchases, transfers=[])
        self.assertEqual(snapshot.average_transaction, 25.0)
        self.assertEqual(snapshot.median_transaction, 25.0)
        self.assertEqual(snapshot.largest_transaction, 40.0)

    def test_attribute_lists_stay_under_16kb(self) -> None:
        transactions = []
        for index in range(300):
            created = datetime(2026, 10, 16, 5, 0, tzinfo=UTC) + timedelta(minutes=index)
            transactions.append(
                budget.CardTransaction(
                    id=f"tx-{index:04d}",
                    card_id=CARD_ID,
                    direction="MONEY_OUT",
                    subtype="PURCHASE",
                    status="COMPLETE",
                    amount_cents=100 + index,
                    description=f"MERCHANT {index:03d} " + ("X" * 80),
                    created_at=created,
                    completed_at=created,
                )
            )
        snapshot = self._compute(transactions=transactions, transfers=[])
        self.assertTrue(snapshot.transactions_truncated or snapshot.merchants_truncated)
        self.assertLess(budget.json_size(budget.transactions_attributes(snapshot)), 16384)
        self.assertLess(budget.json_size(budget.breakdown_attributes(snapshot)), 16384)
        self.assertLess(budget.json_size(list(snapshot.transactions)), 16384)
        self.assertEqual(snapshot.transaction_count, 300)

    def test_poll_interval_jitters_and_honors_retry_after(self) -> None:
        self.assertEqual(budget.poll_interval_seconds(jitter=0), 15 * 60)
        self.assertEqual(budget.poll_interval_seconds(jitter=1), 15 * 60 + 90)
        self.assertEqual(budget.poll_interval_seconds(12, jitter=0), 12)
        self.assertEqual(budget.poll_interval_seconds(0, jitter=0), 1)
        self.assertEqual(budget.poll_interval_seconds(30, jitter=1), 35)

    def test_sensor_object_ids_use_the_hs2_prefix(self) -> None:
        text = (COMPONENT / "budget_sensor.py").read_text()
        for object_id in (
            "hs2_balance",
            "hs2_weekly_spend",
            "hs2_transactions",
            "hs2_status",
            "hs2_breakdown",
        ):
            self.assertIn(f'object_id="{object_id}"', text)
        self.assertIn('unrecorded=frozenset({"transactions"})', text)
        self.assertIn('unrecorded=frozenset({"daily", "merchants"})', text)
        coordinator = (COMPONENT / "budget_coordinator.py").read_text()
        platform = (COMPONENT / "platform_api.py").read_text()
        for source in (coordinator, platform):
            self.assertNotIn(".post(", source)
            self.assertNotIn(".put(", source)
            self.assertNotIn(".patch(", source)
            self.assertNotIn(".delete(", source)

    def _account_with_cents(self, cents: int) -> budget.AccountSnapshot:
        return budget.AccountSnapshot(
            id=ACCOUNT_ID,
            name="Household Spend",
            spendable_cents=cents,
            ledger_cents=cents,
            hold_cents=0,
            balance_source="available",
        )

    def _transfer(
        self,
        transfer_id: str,
        amount: int,
        created: str,
        *,
        origin: str,
        direction: str = "INTERNAL",
    ) -> budget.AccountTransfer:
        return budget.AccountTransfer(
            id=transfer_id,
            amount_cents=amount,
            direction=direction,
            origin=origin,
            status="COMPLETE",
            execution_mode="LIVE",
            source_id="c7a7f26f-2ca5-4ae5-825a-70260591247c",
            destination_id=ACCOUNT_ID,
            created_at=_utc(created),
            completed_at=_utc(created),
        )

    def _card(
        self,
        transaction_id: str,
        amount: int,
        direction: str,
        created: str = "2026-10-16T18:00:00Z",
    ) -> budget.CardTransaction:
        return budget.CardTransaction(
            id=transaction_id,
            card_id=CARD_ID,
            direction=direction,
            subtype="PURCHASE" if direction == "MONEY_OUT" else "REFUND",
            status="COMPLETE",
            amount_cents=amount,
            description="SHOP",
            created_at=_utc(created),
            completed_at=_utc(created),
        )


class PlatformClientTest(unittest.IsolatedAsyncioTestCase):
    """The platform client is GET-only and follows recorded envelopes."""

    async def test_poll_uses_three_read_endpoints(self) -> None:
        account = _load("account.json")
        cards = _load("card_transactions.json")
        transfers = _load("transfers.json")
        session = FakeSession(
            {
                f"/accounts/{ACCOUNT_ID}/transfers": transfers,
                f"/accounts/{ACCOUNT_ID}": account,
                "/card-transactions": cards,
            }
        )
        client = platform_api.SequencePlatformClient(
            session, "sk_test_readonly", "https://api.getsequence.io"
        )
        created_from = datetime(2026, 10, 16, 0, 0, tzinfo=budget.zone_for("America/New_York"))
        fetched_account = await client.async_get_account(ACCOUNT_ID)
        fetched_cards, cards_truncated = await client.async_list_card_transactions(
            ACCOUNT_ID, created_from=created_from, card_id=CARD_ID
        )
        fetched_transfers, transfers_truncated = await client.async_list_transfers(
            ACCOUNT_ID, created_from=created_from
        )

        self.assertEqual(fetched_account.spendable_cents, 35000)
        self.assertEqual(len(fetched_cards), 3)
        self.assertEqual(len(fetched_transfers), 6)
        self.assertFalse(cards_truncated)
        self.assertFalse(transfers_truncated)
        self.assertTrue(all(call["method"] == "GET" for call in session.calls))
        card_call = next(
            call for call in session.calls if call["url"].endswith("/card-transactions")
        )
        self.assertEqual(card_call["params"]["accountId"], ACCOUNT_ID)
        self.assertEqual(card_call["params"]["from"], "2026-10-16T04:00:00Z")
        self.assertEqual(card_call["params"]["cardId"], CARD_ID)
        self.assertEqual(card_call["params"]["pageSize"], 100)
        self.assertTrue(card_call["headers"]["authorization"].startswith("Bearer sk_test_readonly"))
        self.assertNotIn("sk_test_readonly", card_call["url"])
        self.assertIn("read-only", card_call["headers"]["x-called-reason"])

    async def test_pagination_follows_has_next_page(self) -> None:
        first = {
            "data": {
                "items": [_card_item("page-1")],
                "pagination": {"page": 1, "pageSize": 100, "hasNextPage": True},
            }
        }
        second = {
            "data": {
                "items": [_card_item("page-2")],
                "pagination": {"page": 2, "pageSize": 100, "hasNextPage": False},
            }
        }
        session = SequenceSession([FakeResponse(200, first), FakeResponse(200, second)])
        client = platform_api.SequencePlatformClient(session, "sk_test")
        items, truncated = await client.async_list_card_transactions(
            ACCOUNT_ID, created_from=datetime(2026, 10, 16, tzinfo=UTC)
        )
        self.assertEqual([item.id for item in items], ["page-1", "page-2"])
        self.assertFalse(truncated)
        self.assertEqual(session.calls[0]["params"]["page"], 1)
        self.assertEqual(session.calls[1]["params"]["page"], 2)

    async def test_short_retry_after_is_waited_then_retried(self) -> None:
        slept: list[float] = []

        async def _sleep(seconds: float) -> None:
            slept.append(seconds)

        payload = _load("accounts_list.json")
        session = SequenceSession(
            [
                FakeResponse(429, {"error": {"code": "RATE_LIMIT_EXCEEDED"}}, {"Retry-After": "2"}),
                FakeResponse(200, payload),
            ]
        )
        client = platform_api.SequencePlatformClient(session, "sk_test", sleep=_sleep)
        accounts = await client.async_list_accounts()
        self.assertEqual(slept, [2.0])
        self.assertEqual(accounts[0].name, "Household Spend")
        self.assertEqual(len(session.calls), 2)

    async def test_long_retry_after_is_not_waited_inline(self) -> None:
        slept: list[float] = []

        async def _sleep(seconds: float) -> None:
            slept.append(seconds)

        session = SequenceSession(
            [FakeResponse(429, {"error": {"code": "RATE_LIMIT_EXCEEDED"}}, {"Retry-After": "90"})]
        )
        client = platform_api.SequencePlatformClient(session, "sk_test", sleep=_sleep)
        with self.assertRaises(api.SequenceRateLimitError) as raised:
            await client.async_list_accounts()
        self.assertEqual(raised.exception.retry_after, 90.0)
        self.assertEqual(slept, [])
        self.assertEqual(len(session.calls), 1)

    async def test_unauthorized_key_does_not_mutate(self) -> None:
        session = SequenceSession([FakeResponse(401, {"error": {"code": "UNAUTHORIZED"}})])
        client = platform_api.SequencePlatformClient(session, "sk_test")
        with self.assertRaises(api.SequenceAuthError):
            await client.async_get_account(ACCOUNT_ID)
        self.assertEqual(session.calls[0]["method"], "GET")

    def test_platform_base_url(self) -> None:
        self.assertEqual(
            platform_api.platform_base_url("https://api.getsequence.io"),
            "https://api.getsequence.io/platform/v1/",
        )
        self.assertEqual(
            platform_api.platform_base_url("https://api.getsequence.io/platform/v1"),
            "https://api.getsequence.io/platform/v1/",
        )


def _card_item(transaction_id: str) -> dict:
    return {
        "id": transaction_id,
        "account": {
            "id": ACCOUNT_ID,
            "name": "Household Spend",
            "type": "POD",
            "isDeleted": False,
        },
        "amountInCents": 100,
        "cardId": CARD_ID,
        "cardType": "DEBIT_CARD",
        "completedAt": "2026-10-16T18:00:00Z",
        "createdAt": "2026-10-16T18:00:00Z",
        "description": "COFFEE",
        "direction": "MONEY_OUT",
        "status": "COMPLETE",
        "subtype": "PURCHASE",
    }


class FakeResponse:
    """Minimal aiohttp-style response."""

    def __init__(self, status: int, payload: dict, headers: dict | None = None) -> None:
        self.status = status
        self._payload = payload
        self.headers = headers or {}

    async def json(self, content_type: str | None = None) -> dict:
        del content_type
        return self._payload

    async def text(self) -> str:
        return json.dumps(self._payload)

    async def __aenter__(self) -> FakeResponse:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class SequenceSession:
    """Scripted GET session. POST is a test failure."""

    def __init__(self, responses: list[FakeResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    def get(self, url: str, **kwargs):
        self.calls.append(
            {
                "method": "GET",
                "url": url,
                "params": kwargs.get("params"),
                "headers": kwargs.get("headers"),
            }
        )
        if not self._responses:
            raise AssertionError(f"unexpected GET {url}")
        return self._responses.pop(0)

    def post(self, url: str, **kwargs):
        raise AssertionError(f"mutating POST is not allowed: {url}")


class FakeSession(SequenceSession):
    """Route table used when each endpoint is fetched once."""

    def __init__(self, routes: dict[str, dict]) -> None:
        super().__init__([])
        self._routes = routes

    def get(self, url: str, **kwargs):
        self.calls.append(
            {
                "method": "GET",
                "url": url,
                "params": kwargs.get("params"),
                "headers": kwargs.get("headers"),
            }
        )
        for suffix, payload in self._routes.items():
            if suffix in url and not (suffix.endswith(ACCOUNT_ID) and url.endswith("/transfers")):
                if suffix.endswith("/transfers") and not url.endswith("/transfers"):
                    continue
                return FakeResponse(200, payload)
        raise AssertionError(f"unrouted GET {url}")


if __name__ == "__main__":
    unittest.main()
