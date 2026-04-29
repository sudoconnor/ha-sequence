"""Home Assistant integration for Sequence."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SequenceApiClient
from .const import CONF_API_TOKEN, CONF_BASE_URL, DOMAIN, DEFAULT_BASE_URL
from .coordinator import SequenceDataUpdateCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]


SequenceConfigEntry = ConfigEntry


async def async_setup_entry(hass: HomeAssistant, entry: SequenceConfigEntry) -> bool:
    """Set up Sequence from a config entry."""

    session = async_get_clientsession(hass)
    client = SequenceApiClient(
        session=session,
        api_token=entry.data[CONF_API_TOKEN],
        base_url=entry.data.get(CONF_BASE_URL, DEFAULT_BASE_URL),
    )
    coordinator = SequenceDataUpdateCoordinator(hass, entry, client)

    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SequenceConfigEntry) -> bool:
    """Unload a Sequence config entry."""

    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(hass: HomeAssistant, entry: SequenceConfigEntry) -> None:
    """Reload the integration when options change."""

    await hass.config_entries.async_reload(entry.entry_id)
