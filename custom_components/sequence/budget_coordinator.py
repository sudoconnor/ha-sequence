"""Polling coordinator for the read-only weekly budget."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import SequenceApiError, SequenceAuthError, SequenceRateLimitError
from .budget import (
    POLL_INTERVAL_SECONDS,
    BudgetDataError,
    WeeklyBudgetSnapshot,
    compute_weekly_budget,
    cycle_bounds,
    poll_interval_seconds,
    weekday_index,
    zone_for,
)
from .const import (
    CONF_BUDGET_ACCOUNT_ID,
    CONF_BUDGET_AMOUNT,
    CONF_BUDGET_API_TOKEN,
    CONF_BUDGET_CARD_ID,
    CONF_BUDGET_ENABLED,
    CONF_BUDGET_REFILL_WEEKDAY,
    DEFAULT_REFILL_WEEKDAY,
    DEFAULT_WEEKLY_BUDGET,
    DOMAIN,
)
from .platform_api import SequencePlatformClient

_LOGGER = logging.getLogger(__name__)


def budget_entry_enabled(entry: ConfigEntry) -> bool:
    """Return whether the weekly budget should poll."""

    if not entry.options.get(CONF_BUDGET_ENABLED, False):
        return False
    token = str(entry.data.get(CONF_BUDGET_API_TOKEN, "")).strip()
    account_id = str(entry.options.get(CONF_BUDGET_ACCOUNT_ID, "")).strip()
    return bool(token and account_id)


class WeeklyBudgetDataUpdateCoordinator(DataUpdateCoordinator[WeeklyBudgetSnapshot]):
    """Poll Sequence every 15 minutes, with jitter and Retry-After backoff."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: SequencePlatformClient,
    ) -> None:
        """Initialize the coordinator."""

        self.client = client
        self.config_entry = entry
        self.last_error_type: str | None = None
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_weekly_budget",
            update_interval=timedelta(seconds=POLL_INTERVAL_SECONDS),
            config_entry=entry,
        )

    async def _async_update_data(self) -> WeeklyBudgetSnapshot:
        """Fetch the account, settled card rows, and transfers, then compute."""

        retry_after: float | None = None
        try:
            snapshot = await self._async_fetch_snapshot()
        except SequenceAuthError as err:
            self.last_error_type = "auth"
            raise UpdateFailed(str(err)) from err
        except SequenceRateLimitError as err:
            self.last_error_type = "rate_limit"
            retry_after = err.retry_after
            raise UpdateFailed(str(err)) from err
        except SequenceApiError as err:
            self.last_error_type = "api"
            raise UpdateFailed(str(err)) from err
        except BudgetDataError as err:
            self.last_error_type = "api"
            raise UpdateFailed(str(err)) from err
        else:
            self.last_error_type = None
            return snapshot
        finally:
            self.update_interval = timedelta(seconds=poll_interval_seconds(retry_after))

    async def _async_fetch_snapshot(self) -> WeeklyBudgetSnapshot:
        """Read the three platform endpoints and compute the open cycle."""

        options: dict[str, Any] = self.config_entry.options
        account_id = str(options.get(CONF_BUDGET_ACCOUNT_ID, "")).strip()
        if not account_id:
            raise BudgetDataError("Weekly budget account is not configured")
        amount = float(options.get(CONF_BUDGET_AMOUNT, DEFAULT_WEEKLY_BUDGET))
        weekday = str(options.get(CONF_BUDGET_REFILL_WEEKDAY, DEFAULT_REFILL_WEEKDAY))
        card_id = str(options.get(CONF_BUDGET_CARD_ID, "")).strip() or None
        tz = zone_for(self.hass.config.time_zone)
        now = datetime.now(tz)
        cycle_start, _next_refill = cycle_bounds(now, weekday_index(weekday), tz)
        account = await self.client.async_get_account(account_id)
        transactions, transactions_truncated = await self.client.async_list_card_transactions(
            account_id,
            created_from=cycle_start,
            card_id=card_id,
        )
        transfers, transfers_truncated = await self.client.async_list_transfers(
            account_id,
            created_from=cycle_start,
        )
        return compute_weekly_budget(
            account_id=account_id,
            account=account,
            budget_dollars=amount,
            refill_weekday=weekday,
            card_id=card_id,
            transactions=transactions,
            transfers=transfers,
            now=now,
            tz=tz,
            history_truncated=transactions_truncated or transfers_truncated,
        )
