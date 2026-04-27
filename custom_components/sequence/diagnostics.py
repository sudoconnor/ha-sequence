"""Diagnostics for Sequence."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_API_TOKEN
from .coordinator import SequenceDataUpdateCoordinator

TO_REDACT = {CONF_API_TOKEN, "id", "name", "balance"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry.

    Account names, ids, balances, and tokens are deliberately omitted/redacted.
    """

    coordinator: SequenceDataUpdateCoordinator = entry.runtime_data
    accounts = list(coordinator.accounts.values())
    account_types: dict[str, int] = {}
    for account in accounts:
        key = account.type or "unknown"
        account_types[key] = account_types.get(key, 0) + 1

    return {
        "entry": async_redact_data(
            {
                "data": dict(entry.data),
                "options": dict(entry.options),
            },
            TO_REDACT,
        ),
        "last_update_success": coordinator.last_update_success,
        "account_count": len(accounts),
        "account_type_counts": account_types,
    }
