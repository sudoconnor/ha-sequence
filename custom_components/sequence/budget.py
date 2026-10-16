"""Weekly household budget math.

This module is intentionally free of Home Assistant imports so the cycle,
refill, and spend rules can be tested with recorded Sequence payloads.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from zoneinfo import ZoneInfo

from .const import DEFAULT_REFILL_WEEKDAY, WEEKDAYS

POLL_INTERVAL_SECONDS = 15 * 60
POLL_JITTER_SECONDS = 90
RATE_LIMIT_JITTER_SECONDS = 5
REFILL_WINDOW = timedelta(hours=36)
ATTRIBUTE_BUDGET_BYTES = 14_000
_TRANSACTION_LIST_BUDGET = 12_000
_MERCHANT_LIST_BUDGET = 8_000

SPEND_CALCULATION = (
    "spent_incl_pending = budget + top_ups - balance; "
    "pending = max(0, spent_incl_pending - spent_settled); "
    "the weekly refill transfer is excluded from top_ups"
)
STATUS_THRESHOLDS = "Critical at or below 10%, Low at or below 20%, otherwise Healthy"
_COMPLETE = "COMPLETE"
_INCOMING_PENDING = {"APPROVAL_PENDING", "PROCESSING", "PENDING"}


class BudgetDataError(Exception):
    """Raised when a payload cannot produce a weekly budget snapshot."""


@dataclass(frozen=True, slots=True)
class AccountSummary:
    """Account row from GET /accounts, which does not include a balance."""

    id: str
    name: str
    type: str | None = None


@dataclass(frozen=True, slots=True)
class AccountSnapshot:
    """Balance fields from GET /accounts/{id}."""

    id: str
    name: str | None
    spendable_cents: int | None
    ledger_cents: int | None
    hold_cents: int | None
    balance_source: str


@dataclass(frozen=True, slots=True)
class CardTransaction:
    """One settled card row."""

    id: str
    card_id: str | None
    direction: str
    subtype: str | None
    status: str | None
    amount_cents: int
    description: str
    created_at: datetime
    completed_at: datetime | None


@dataclass(frozen=True, slots=True)
class AccountTransfer:
    """One account transfer row."""

    id: str
    amount_cents: int
    direction: str
    origin: str | None
    status: str | None
    execution_mode: str | None
    source_id: str | None
    destination_id: str | None
    created_at: datetime
    completed_at: datetime | None


@dataclass(frozen=True, slots=True)
class WeeklyBudgetSnapshot:
    """Computed household spend for the open weekly cycle."""

    currency: str
    account_id: str
    account_name: str | None
    balance_source: str
    budget: float
    balance: float
    ledger_balance: float | None
    hold: float | None
    top_ups: float
    top_up_count: int
    pending_incoming: float
    pending_incoming_count: int
    refill_amount: float | None
    refill_transfer_id: str | None
    refill_excluded: bool
    spent_settled: float
    spent_incl_pending: float
    pending: float
    remaining: float
    ratio: float
    percent: float
    status: str
    cycle_start: datetime
    next_refill: datetime
    days_until_refill: float
    days_elapsed: float
    last_sync: datetime
    burn_rate: float | None
    safe_daily_allowance: float | None
    average_transaction: float | None
    median_transaction: float | None
    largest_transaction: float | None
    purchase_count: int
    top_merchant: str | None
    top_merchant_spent: float | None
    top_merchant_count: int
    transaction_count: int
    transactions: tuple[dict[str, Any], ...]
    transactions_truncated: bool
    daily: tuple[dict[str, Any], ...]
    merchants: tuple[dict[str, Any], ...]
    merchants_truncated: bool
    history_truncated: bool
    card_id: str | None
    refill_weekday: str


def poll_interval_seconds(
    retry_after: float | None = None, *, jitter: float | None = None
) -> float:
    """Return the delay before the next weekly-budget poll.

    ``jitter`` is a unit interval in ``[0, 1)``. A normal poll waits about 15
    minutes plus up to 90 seconds. After HTTP 429, the wait is Retry-After
    plus up to 5 seconds.
    """

    if jitter is None:
        import random

        jitter = random.random()
    unit = min(1.0, max(0.0, jitter))
    if retry_after is not None:
        return max(float(retry_after), 1.0) + unit * RATE_LIMIT_JITTER_SECONDS
    return POLL_INTERVAL_SECONDS + unit * POLL_JITTER_SECONDS


def weekday_index(name: str | None) -> int:
    """Return a Monday=0 weekday index, defaulting to Friday."""

    if not name:
        return WEEKDAYS.index(DEFAULT_REFILL_WEEKDAY)
    try:
        return WEEKDAYS.index(name.strip().lower())
    except ValueError:
        return WEEKDAYS.index(DEFAULT_REFILL_WEEKDAY)


def zone_for(name: str | None) -> ZoneInfo:
    """Return a timezone, falling back to UTC when Home Assistant has none."""

    try:
        return ZoneInfo(name or "UTC")
    except Exception:
        return ZoneInfo("UTC")


def cycle_bounds(now: datetime, weekday: int, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """Return the current cycle start and the next refill, both local midnights.

    The cycle starts at 00:00 on the refill weekday in ``tz``. A timestamp that
    falls exactly on that midnight belongs to the new cycle.
    """

    if now.tzinfo is None:
        now = now.replace(tzinfo=tz)
    local_now = now.astimezone(tz)
    days_back = (local_now.weekday() - weekday) % 7
    start_date = (local_now - timedelta(days=days_back)).date()
    start = datetime(start_date.year, start_date.month, start_date.day, tzinfo=tz)
    if start > local_now:
        start = start - timedelta(days=7)
    return start, start + timedelta(days=7)


def to_rfc3339(moment: datetime) -> str:
    """Format an aware datetime as UTC RFC 3339 with a Z suffix."""

    if moment.tzinfo is None:
        raise BudgetDataError("Sequence timestamps must be timezone-aware")
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def dollars_to_cents(amount: float) -> int:
    """Convert a dollar amount to integer cents."""

    quantized = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return int(quantized * 100)


def cents_to_dollars(cents: int) -> float:
    """Convert integer cents to a dollar float."""

    return float(Decimal(cents) / Decimal(100))


def items_from_envelope(payload: Any) -> list[dict[str, Any]]:
    """Return ``data.items`` from a Sequence list envelope."""

    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if not isinstance(data, dict):
        return []
    items = data.get("items")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def has_next_page(payload: Any, *, page_size: int, item_count: int) -> bool:
    """Return whether another list page should be requested."""

    if not isinstance(payload, dict):
        return False
    data = payload.get("data")
    pagination = data.get("pagination") if isinstance(data, dict) else None
    if not isinstance(pagination, dict) or "hasNextPage" not in pagination:
        return item_count >= page_size
    return pagination.get("hasNextPage") is True


def parse_account_list(payload: Any) -> list[AccountSummary]:
    """Parse GET /accounts into account choices."""

    summaries: list[AccountSummary] = []
    for item in items_from_envelope(payload):
        account_id = _string(item.get("id"))
        if not account_id:
            continue
        summaries.append(
            AccountSummary(
                id=account_id,
                name=_string(item.get("name")) or "Sequence account",
                type=_string(item.get("type")),
            )
        )
    return summaries


def parse_account(payload: Any) -> AccountSnapshot:
    """Parse GET /accounts/{id}."""

    if not isinstance(payload, dict):
        raise BudgetDataError("Sequence account response was not an object")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise BudgetDataError("Sequence account response was missing data")
    account_id = _string(data.get("id"))
    if not account_id:
        raise BudgetDataError("Sequence account response was missing an id")
    balance = data.get("balance")
    spendable: int | None = None
    ledger: int | None = None
    hold: int | None = None
    source = "ledger"
    if isinstance(balance, dict):
        ledger = _cents(balance.get("balanceInCents"))
        available = _cents(balance.get("availableBalanceInCents"))
        hold = _cents(balance.get("holdInCents"))
        if available is not None:
            spendable = available
            source = "available"
        else:
            spendable = ledger
    return AccountSnapshot(
        id=account_id,
        name=_string(data.get("name")),
        spendable_cents=spendable,
        ledger_cents=ledger,
        hold_cents=hold,
        balance_source=source,
    )


def parse_card_transactions(items: list[dict[str, Any]]) -> list[CardTransaction]:
    """Parse card-transaction items with the recorded Sequence keys."""

    parsed: list[CardTransaction] = []
    for item in items:
        created_at = _datetime(item.get("createdAt"))
        amount = _cents(item.get("amountInCents"))
        direction = _string(item.get("direction"))
        transaction_id = _string(item.get("id"))
        if created_at is None or amount is None or direction is None or transaction_id is None:
            continue
        parsed.append(
            CardTransaction(
                id=transaction_id,
                card_id=_string(item.get("cardId")),
                direction=direction,
                subtype=_string(item.get("subtype")),
                status=_string(item.get("status")),
                amount_cents=amount,
                description=_string(item.get("description")) or "",
                created_at=created_at,
                completed_at=_datetime(item.get("completedAt")),
            )
        )
    return parsed


def parse_transfers(items: list[dict[str, Any]]) -> list[AccountTransfer]:
    """Parse transfer items from GET /accounts/{id}/transfers."""

    parsed: list[AccountTransfer] = []
    for item in items:
        created_at = _datetime(item.get("createdAt"))
        amount = _cents(item.get("amountInCents"))
        direction = _string(item.get("direction"))
        transfer_id = _string(item.get("id"))
        if created_at is None or amount is None or direction is None or transfer_id is None:
            continue
        parsed.append(
            AccountTransfer(
                id=transfer_id,
                amount_cents=amount,
                direction=direction,
                origin=_string(item.get("origin")),
                status=_string(item.get("status")),
                execution_mode=_string(item.get("executionMode")),
                source_id=_account_ref_id(item.get("source")),
                destination_id=_account_ref_id(item.get("destination")),
                created_at=created_at,
                completed_at=_datetime(item.get("completedAt")),
            )
        )
    return parsed


def compute_weekly_budget(
    *,
    account_id: str,
    account: AccountSnapshot,
    budget_dollars: float,
    refill_weekday: str,
    card_id: str | None,
    transactions: list[CardTransaction],
    transfers: list[AccountTransfer],
    now: datetime,
    tz: ZoneInfo,
    history_truncated: bool = False,
    currency: str = "USD",
) -> WeeklyBudgetSnapshot:
    """Compute the household spend snapshot for the open cycle."""

    budget_cents = dollars_to_cents(budget_dollars)
    if budget_cents <= 0:
        raise BudgetDataError("Weekly budget must be greater than zero")
    if account.spendable_cents is None:
        raise BudgetDataError("Sequence did not return a usable account balance")

    weekday = weekday_index(refill_weekday)
    cycle_start, next_refill = cycle_bounds(now, weekday, tz)
    window_end = cycle_start + REFILL_WINDOW
    card_filter = card_id.casefold() if card_id else None

    in_cycle = [
        tx
        for tx in transactions
        if cycle_start <= tx.created_at < next_refill and _card_matches(tx, card_filter)
    ]
    settled_rows = [tx for tx in in_cycle if _counts_as_settled(tx)]
    spent_settled_cents = sum(_signed_spend_cents(tx) for tx in settled_rows)

    live_transfers = [
        transfer
        for transfer in transfers
        if cycle_start <= transfer.created_at < next_refill and _is_live(transfer)
    ]
    refill = _select_refill(live_transfers, account_id, cycle_start, window_end, budget_cents)
    top_up_rows = [
        transfer
        for transfer in live_transfers
        if _credits_account(transfer, account_id)
        and transfer.status == _COMPLETE
        and (refill is None or transfer.id != refill.id)
    ]
    pending_rows = [
        transfer
        for transfer in live_transfers
        if _credits_account(transfer, account_id) and transfer.status in _INCOMING_PENDING
    ]
    top_up_cents = sum(transfer.amount_cents for transfer in top_up_rows)
    pending_incoming_cents = sum(transfer.amount_cents for transfer in pending_rows)

    balance_cents = account.spendable_cents
    spent_incl_cents = budget_cents + top_up_cents - balance_cents
    pending_cents = max(0, spent_incl_cents - spent_settled_cents)

    purchases = [tx for tx in settled_rows if tx.direction == "MONEY_OUT"]
    purchase_amounts = [tx.amount_cents for tx in purchases]
    merchant_rows, merchant_spent, merchant_counts = _merchant_totals(settled_rows)
    daily_rows = _daily_totals(settled_rows, tz)

    ordered = sorted(settled_rows, key=lambda item: item.created_at, reverse=True)
    transaction_rows = [_transaction_attribute(tx) for tx in ordered]
    transaction_rows, transactions_truncated = _cap_json_list(
        transaction_rows, _TRANSACTION_LIST_BUDGET
    )
    merchants, merchants_truncated = _cap_json_list(merchant_rows, _MERCHANT_LIST_BUDGET)

    elapsed_seconds = max(0.0, (now - cycle_start).total_seconds())
    elapsed_days = elapsed_seconds / 86400
    days_until = round(max(0.0, (next_refill - now).total_seconds()) / 86400, 2)
    burn_rate = None
    if elapsed_seconds >= 3600:
        burn_rate = round(cents_to_dollars(spent_incl_cents) / elapsed_days, 2)
    safe_daily = None
    if days_until > 0:
        safe_daily = round(cents_to_dollars(balance_cents) / days_until, 2)

    top_merchant = None
    top_merchant_spent = None
    top_merchant_count = 0
    if merchant_spent:
        top_merchant = max(merchant_spent, key=lambda name: (merchant_spent[name], name))
        top_merchant_spent = cents_to_dollars(merchant_spent[top_merchant])
        top_merchant_count = merchant_counts.get(top_merchant, 0)

    ratio = balance_cents / budget_cents
    percent = float(
        (Decimal(balance_cents) * Decimal(100) / Decimal(budget_cents)).quantize(
            Decimal("0.1"), rounding=ROUND_HALF_UP
        )
    )
    return WeeklyBudgetSnapshot(
        currency=currency,
        account_id=account_id,
        account_name=account.name,
        balance_source=account.balance_source,
        budget=cents_to_dollars(budget_cents),
        balance=cents_to_dollars(balance_cents),
        ledger_balance=(
            None if account.ledger_cents is None else cents_to_dollars(account.ledger_cents)
        ),
        hold=None if account.hold_cents is None else cents_to_dollars(account.hold_cents),
        top_ups=cents_to_dollars(top_up_cents),
        top_up_count=len(top_up_rows),
        pending_incoming=cents_to_dollars(pending_incoming_cents),
        pending_incoming_count=len(pending_rows),
        refill_amount=None if refill is None else cents_to_dollars(refill.amount_cents),
        refill_transfer_id=None if refill is None else refill.id,
        refill_excluded=refill is not None,
        spent_settled=cents_to_dollars(spent_settled_cents),
        spent_incl_pending=cents_to_dollars(spent_incl_cents),
        pending=cents_to_dollars(pending_cents),
        remaining=cents_to_dollars(balance_cents),
        ratio=ratio,
        percent=percent,
        status=_status(balance_cents, budget_cents),
        cycle_start=cycle_start,
        next_refill=next_refill,
        days_until_refill=days_until,
        days_elapsed=round(elapsed_days, 4),
        last_sync=now,
        burn_rate=burn_rate,
        safe_daily_allowance=safe_daily,
        average_transaction=_average_cents(purchase_amounts),
        median_transaction=_median_cents(purchase_amounts),
        largest_transaction=None
        if not purchase_amounts
        else cents_to_dollars(max(purchase_amounts)),
        purchase_count=len(purchase_amounts),
        top_merchant=top_merchant,
        top_merchant_spent=top_merchant_spent,
        top_merchant_count=top_merchant_count,
        transaction_count=len(settled_rows),
        transactions=tuple(transaction_rows),
        transactions_truncated=transactions_truncated,
        daily=tuple(daily_rows),
        merchants=tuple(merchants),
        merchants_truncated=merchants_truncated,
        history_truncated=history_truncated,
        card_id=card_id,
        refill_weekday=WEEKDAYS[weekday],
    )


def balance_attributes(snapshot: WeeklyBudgetSnapshot) -> dict[str, Any]:
    """Return the balance sensor attributes."""

    return {
        "account_id": snapshot.account_id,
        "account_name": snapshot.account_name,
        "balance_source": snapshot.balance_source,
        "ledger_balance": snapshot.ledger_balance,
        "hold": snapshot.hold,
        "budget": snapshot.budget,
        "cycle_start": to_rfc3339(snapshot.cycle_start),
        "next_refill": to_rfc3339(snapshot.next_refill),
    }


def weekly_spend_attributes(snapshot: WeeklyBudgetSnapshot) -> dict[str, Any]:
    """Return the weekly spend sensor attributes."""

    return {
        "spent_settled": snapshot.spent_settled,
        "pending": snapshot.pending,
        "top_ups": snapshot.top_ups,
        "budget": snapshot.budget,
        "balance": snapshot.balance,
        "refill_amount": snapshot.refill_amount,
        "refill_transfer_id": snapshot.refill_transfer_id,
        "refill_excluded": snapshot.refill_excluded,
        "top_up_count": snapshot.top_up_count,
        "pending_incoming": snapshot.pending_incoming,
        "calculation": SPEND_CALCULATION,
    }


def transactions_attributes(snapshot: WeeklyBudgetSnapshot) -> dict[str, Any]:
    """Return the transaction-list attributes, capped under 16 KB."""

    return {
        "card_id": snapshot.card_id,
        "transaction_count": snapshot.transaction_count,
        "transactions_truncated": snapshot.transactions_truncated,
        "history_truncated": snapshot.history_truncated,
        "transactions": list(snapshot.transactions),
    }


def breakdown_attributes(snapshot: WeeklyBudgetSnapshot) -> dict[str, Any]:
    """Return daily and merchant breakdown attributes."""

    return {
        "daily": list(snapshot.daily),
        "merchants": list(snapshot.merchants),
        "merchants_truncated": snapshot.merchants_truncated,
        "top_merchant": snapshot.top_merchant,
        "history_truncated": snapshot.history_truncated,
    }


def json_size(value: Any) -> int:
    """Return the UTF-8 JSON size of a sensor attribute payload."""

    encoded = json.dumps(value, separators=(",", ":"), ensure_ascii=False, default=str)
    return len(encoded.encode("utf-8"))


def _status(balance_cents: int, budget_cents: int) -> str:
    if budget_cents <= 0:
        return "Unknown"
    if balance_cents * 10 <= budget_cents:
        return "Critical"
    if balance_cents * 5 <= budget_cents:
        return "Low"
    return "Healthy"


def _card_matches(tx: CardTransaction, card_filter: str | None) -> bool:
    if card_filter is None:
        return True
    return (tx.card_id or "").casefold() == card_filter


def _counts_as_settled(tx: CardTransaction) -> bool:
    return tx.status in (None, _COMPLETE)


def _signed_spend_cents(tx: CardTransaction) -> int:
    if tx.direction == "MONEY_OUT":
        return tx.amount_cents
    if tx.direction == "MONEY_IN":
        return -tx.amount_cents
    return 0


def _is_live(transfer: AccountTransfer) -> bool:
    return transfer.execution_mode in (None, "LIVE")


def _credits_account(transfer: AccountTransfer, account_id: str) -> bool:
    """Return whether this transfer moves money into the budget account."""

    if transfer.direction == "MONEY_IN":
        return transfer.destination_id in (None, account_id)
    if transfer.direction == "INTERNAL":
        return transfer.destination_id == account_id and transfer.source_id != account_id
    return False


def _select_refill(
    transfers: list[AccountTransfer],
    account_id: str,
    cycle_start: datetime,
    window_end: datetime,
    budget_cents: int,
) -> AccountTransfer | None:
    """Pick the weekly refill so it is not counted as a top-up.

    Prefer the earliest incoming settled transfer in the first 36 hours whose
    amount equals the weekly budget. Otherwise use the earliest rule-origin
    incoming transfer in that window. Later incoming transfers stay top-ups.
    """

    candidates = [
        transfer
        for transfer in transfers
        if transfer.status == _COMPLETE
        and _credits_account(transfer, account_id)
        and cycle_start <= transfer.created_at <= window_end
    ]
    exact = [transfer for transfer in candidates if transfer.amount_cents == budget_cents]
    pool = exact or [transfer for transfer in candidates if transfer.origin == "RULE"]
    if not pool:
        return None
    return min(pool, key=lambda transfer: (transfer.created_at, transfer.id))


def _merchant_totals(
    transactions: list[CardTransaction],
) -> tuple[list[dict[str, Any]], dict[str, int], dict[str, int]]:
    spent: dict[str, int] = {}
    counts: dict[str, int] = {}
    for tx in transactions:
        signed = _signed_spend_cents(tx)
        if tx.direction not in ("MONEY_OUT", "MONEY_IN"):
            continue
        name = tx.description.strip() or "Unknown"
        spent[name] = spent.get(name, 0) + signed
        counts[name] = counts.get(name, 0) + 1
    rows = [
        {"merchant": name, "spent": cents_to_dollars(amount), "count": counts[name]}
        for name, amount in sorted(spent.items(), key=lambda item: (-item[1], item[0]))
    ]
    return rows, spent, counts


def _daily_totals(transactions: list[CardTransaction], tz: ZoneInfo) -> list[dict[str, Any]]:
    spent: dict[str, int] = {}
    counts: dict[str, int] = {}
    for tx in transactions:
        if tx.direction not in ("MONEY_OUT", "MONEY_IN"):
            continue
        day = tx.created_at.astimezone(tz).date().isoformat()
        spent[day] = spent.get(day, 0) + _signed_spend_cents(tx)
        counts[day] = counts.get(day, 0) + 1
    return [
        {"date": day, "spent": cents_to_dollars(spent[day]), "count": counts[day]}
        for day in sorted(spent)
    ]


def _transaction_attribute(tx: CardTransaction) -> dict[str, Any]:
    return {
        "id": tx.id,
        "description": tx.description,
        "amount": cents_to_dollars(tx.amount_cents),
        "direction": tx.direction,
        "subtype": tx.subtype,
        "status": tx.status,
        "created_at": to_rfc3339(tx.created_at),
        "completed_at": None if tx.completed_at is None else to_rfc3339(tx.completed_at),
        "card_id": tx.card_id,
    }


def _average_cents(amounts: list[int]) -> float | None:
    if not amounts:
        return None
    return round(sum(cents_to_dollars(amount) for amount in amounts) / len(amounts), 2)


def _median_cents(amounts: list[int]) -> float | None:
    if not amounts:
        return None
    ordered = sorted(cents_to_dollars(amount) for amount in amounts)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return round((ordered[mid - 1] + ordered[mid]) / 2, 2)


def _cap_json_list(
    items: list[dict[str, Any]], max_bytes: int
) -> tuple[list[dict[str, Any]], bool]:
    if json_size(items) <= max_bytes:
        return items, False
    low = 0
    high = len(items)
    best = 0
    while low <= high:
        mid = (low + high) // 2
        if json_size(items[:mid]) <= max_bytes:
            best = mid
            low = mid + 1
        else:
            high = mid - 1
    return items[:best], True


def _account_ref_id(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    return _string(value.get("id"))


def _string(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _cents(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed
