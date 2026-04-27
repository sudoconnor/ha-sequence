"""Data update coordinator for Sequence."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import SequenceAccount, SequenceApiClient, SequenceApiError
from .const import CONF_ENABLE_ACCOUNT_SENSORS, DEFAULT_OPTIONS, DEFAULT_SCAN_INTERVAL, DOMAIN

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
        return {"accounts": accounts}
