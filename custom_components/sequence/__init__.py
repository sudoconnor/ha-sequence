"""Home Assistant integration for Sequence."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SequenceApiClient
from .const import (
    ATTR_API_SECRET,
    ATTR_IDEMPOTENCY_KEY,
    ATTR_PAYLOAD,
    ATTR_RULE_ID,
    CONF_ALLOWED_RULE_IDS,
    CONF_API_TOKEN,
    CONF_BASE_URL,
    DEFAULT_BASE_URL,
    DOMAIN,
    EVENT_RULE_TRIGGERED,
    SERVICE_TRIGGER_RULE,
)
from .coordinator import SequenceDataUpdateCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]

TRIGGER_RULE_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_RULE_ID): str,
        vol.Required(ATTR_API_SECRET): str,
        vol.Optional(ATTR_IDEMPOTENCY_KEY): str,
        vol.Optional(ATTR_PAYLOAD, default=dict): dict,
    }
)


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
    if not hass.services.has_service(DOMAIN, SERVICE_TRIGGER_RULE):

        async def _handle_trigger_rule(call: ServiceCall) -> None:
            await _async_trigger_rule_service(hass, call)

        hass.services.async_register(
            DOMAIN,
            SERVICE_TRIGGER_RULE,
            _handle_trigger_rule,
            schema=TRIGGER_RULE_SERVICE_SCHEMA,
        )
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SequenceConfigEntry) -> bool:
    """Unload a Sequence config entry."""

    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(hass: HomeAssistant, entry: SequenceConfigEntry) -> None:
    """Reload the integration when options change."""

    await hass.config_entries.async_reload(entry.entry_id)


async def _async_trigger_rule_service(hass: HomeAssistant, call: ServiceCall) -> None:
    """Handle the sequence.trigger_rule service."""

    coordinator = _get_loaded_coordinator(hass)
    rule_id = call.data[ATTR_RULE_ID].strip()
    api_secret = call.data[ATTR_API_SECRET].strip()
    if not api_secret:
        raise HomeAssistantError("Sequence rule API secret is required")
    allowed_rule_ids = _parse_allowed_rule_ids(
        coordinator.config_entry.options.get(CONF_ALLOWED_RULE_IDS, "")
    )
    if rule_id not in allowed_rule_ids:
        raise HomeAssistantError(
            "Sequence rule is not allowlisted. Add the rule ID in Sequence options first."
        )

    result = await coordinator.client.async_trigger_rule(
        rule_id=rule_id,
        api_secret=api_secret,
        payload=call.data[ATTR_PAYLOAD],
        idempotency_key=call.data.get(ATTR_IDEMPOTENCY_KEY),
    )
    hass.bus.async_fire(
        EVENT_RULE_TRIGGERED,
        {
            ATTR_RULE_ID: rule_id,
            "request_id": result.request_id,
            "message": result.message,
        },
    )


def _get_loaded_coordinator(hass: HomeAssistant) -> SequenceDataUpdateCoordinator:
    """Return the loaded Sequence coordinator for service calls."""

    for entry in hass.config_entries.async_entries(DOMAIN):
        coordinator: Any = getattr(entry, "runtime_data", None)
        if isinstance(coordinator, SequenceDataUpdateCoordinator):
            return coordinator
    raise HomeAssistantError("No loaded Sequence config entry found")


def _parse_allowed_rule_ids(raw_value: str) -> set[str]:
    """Parse a comma/newline separated rule allowlist."""

    normalized = raw_value.replace(",", "\n")
    return {rule_id.strip() for rule_id in normalized.splitlines() if rule_id.strip()}
