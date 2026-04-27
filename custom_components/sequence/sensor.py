"""Sensors for Sequence."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import SequenceAccount
from .const import ATTR_ACCOUNT_TYPE, ATTR_BALANCE_ERROR, DOMAIN
from .coordinator import SequenceDataUpdateCoordinator


def _sequence_name(name: str) -> str:
    """Return an account name with a single Sequence namespace prefix."""

    if name.casefold().startswith("sequence "):
        return name
    return f"Sequence {name}"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Sequence sensors."""

    coordinator: SequenceDataUpdateCoordinator = entry.runtime_data
    known_account_ids: set[str] = set()

    async def async_add_new_account_sensors() -> None:
        if not coordinator.account_sensors_enabled:
            return
        new_entities: list[SequenceBalanceSensor] = []
        for account_id in coordinator.accounts:
            if account_id in known_account_ids:
                continue
            known_account_ids.add(account_id)
            new_entities.append(SequenceBalanceSensor(coordinator, account_id))
        if new_entities:
            async_add_entities(new_entities)

    await async_add_new_account_sensors()

    def _schedule_add_new_accounts() -> None:
        hass.async_create_task(async_add_new_account_sensors())

    entry.async_on_unload(coordinator.async_add_listener(_schedule_add_new_accounts))


class SequenceBalanceSensor(CoordinatorEntity[SequenceDataUpdateCoordinator], SensorEntity):
    """Sequence account balance sensor."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_icon = "mdi:bank"
    _attr_state_class = SensorStateClass.TOTAL

    def __init__(self, coordinator: SequenceDataUpdateCoordinator, account_id: str) -> None:
        """Initialize the sensor."""

        super().__init__(coordinator)
        self._account_id = account_id
        self._attr_unique_id = f"{account_id}_balance"

    @property
    def account(self) -> SequenceAccount | None:
        """Return the current account data."""

        return self.coordinator.accounts.get(self._account_id)

    @property
    def name(self) -> str:
        """Return the sensor name."""

        account = self.account
        if account is None:
            return "Sequence Account Balance"
        return f"{_sequence_name(account.name)} Balance"

    @property
    def available(self) -> bool:
        """Return whether the sensor has usable data."""

        account = self.account
        return bool(self.coordinator.last_update_success and account and account.balance is not None)

    @property
    def native_value(self) -> float | None:
        """Return the account balance."""

        account = self.account
        return account.balance if account else None

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the account currency."""

        account = self.account
        return account.currency if account else "USD"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return non-sensitive attributes."""

        account = self.account
        if account is None:
            return {}
        attrs: dict[str, Any] = {}
        if account.type:
            attrs[ATTR_ACCOUNT_TYPE] = account.type
        if account.balance_error:
            attrs[ATTR_BALANCE_ERROR] = account.balance_error
        return attrs

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device info for this Sequence account."""

        account = self.account
        name = _sequence_name(account.name) if account else "Sequence Account"
        model = account.type if account and account.type else "Account"
        return {
            "identifiers": {(DOMAIN, self._account_id)},
            "manufacturer": "Sequence",
            "model": model,
            "name": name,
        }
