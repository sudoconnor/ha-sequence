"""Data update coordinator for Sequence."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import SequenceAccount, SequenceApiClient, SequenceApiError
from .const import (
    ATTR_ACCOUNT_ID,
    ATTR_ACCOUNT_NAME,
    ATTR_ACCOUNT_TYPE,
    ATTR_BALANCE,
    ATTR_BALANCE_CHANGE,
    ATTR_PREVIOUS_BALANCE,
    CONF_ENABLE_ACCOUNT_SENSORS,
    DEFAULT_OPTIONS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    EVENT_ACCOUNT_BALANCE_DECREASED,
    EVENT_ACCOUNT_BALANCE_INCREASED,
)

_LOGGER = logging.getLogger(__name__)


class SequenceDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinate Sequence API polling."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: SequenceApiClient,
    ) -> None:
        """Initialize the coordinator."""

        self.client = client
        self.config_entry = entry
        self._last_balances: dict[str, float] = {}
        self._has_baseline = False
        interval_seconds = int(
            entry.options.get("scan_interval", entry.data.get("scan_interval", DEFAULT_SCAN_INTERVAL))
        )
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval_seconds),
            config_entry=entry,
        )

    @property
    def accounts(self) -> dict[str, SequenceAccount]:
        """Return accounts keyed by Sequence account id."""

        accounts = (self.data or {}).get("accounts", [])
        return {account.id: account for account in accounts}

    @property
    def account_sensors_enabled(self) -> bool:
        """Return whether account sensors are enabled."""

        return bool(
            self.config_entry.options.get(
                CONF_ENABLE_ACCOUNT_SENSORS,
                DEFAULT_OPTIONS[CONF_ENABLE_ACCOUNT_SENSORS],
            )
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch latest data from Sequence."""

        try:
            accounts = await self.client.async_get_accounts()
        except SequenceApiError as err:
            raise UpdateFailed(str(err)) from err

        self._async_fire_balance_change_events(accounts)
        return {"accounts": accounts}

    def _async_fire_balance_change_events(self, accounts: list[SequenceAccount]) -> None:
        """Fire Home Assistant events for Sequence account balance changes."""

        current_balances = {
            account.id: account.balance
            for account in accounts
            if account.balance is not None
        }

        if not self._has_baseline:
            self._last_balances = current_balances
            self._has_baseline = True
            return

        for account in accounts:
            current = account.balance
            previous = self._last_balances.get(account.id)
            if current is None or previous is None or current == previous:
                continue

            change = round(current - previous, 2)
            event_type = (
                EVENT_ACCOUNT_BALANCE_INCREASED
                if change > 0
                else EVENT_ACCOUNT_BALANCE_DECREASED
            )
            self.hass.bus.async_fire(
                event_type,
                {
                    ATTR_ACCOUNT_ID: account.id,
                    ATTR_ACCOUNT_NAME: account.name,
                    ATTR_ACCOUNT_TYPE: account.type,
                    ATTR_PREVIOUS_BALANCE: previous,
                    ATTR_BALANCE: current,
                    ATTR_BALANCE_CHANGE: change,
                    "currency": account.currency,
                },
            )

        self._last_balances = current_balances
