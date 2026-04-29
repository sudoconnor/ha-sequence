"""Binary sensors for Sequence."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SequenceDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Sequence binary sensors."""

    coordinator: SequenceDataUpdateCoordinator = entry.runtime_data
    async_add_entities([SequenceApiProblemBinarySensor(coordinator, entry)])


class SequenceApiProblemBinarySensor(
    CoordinatorEntity[SequenceDataUpdateCoordinator], BinarySensorEntity
):
    """Expose Sequence API health as a Home Assistant problem sensor."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_has_entity_name = True
    _attr_name = "API Problem"

    def __init__(
        self,
        coordinator: SequenceDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the binary sensor."""

        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_api_problem"

        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "manufacturer": "Sequence",
            "name": "Sequence",
        }

    @property
    def available(self) -> bool:
        """Keep the health sensor available even when Sequence polling fails."""

        return True

    @property
    def is_on(self) -> bool:
        """Return true when the latest Sequence update failed."""

        return not self.coordinator.last_update_success

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return non-sensitive health attributes."""

        attrs: dict[str, Any] = {
            "account_count": len(self.coordinator.accounts),
        }
        if self.coordinator.last_error_type:
            attrs["last_error_type"] = self.coordinator.last_error_type
        return attrs
