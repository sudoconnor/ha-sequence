"""Diagnostics for Sequence."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_API_TOKEN,
    CONF_BUDGET_ACCOUNT_ID,
    CONF_BUDGET_API_TOKEN,
    CONF_BUDGET_ENABLED,
)
from .coordinator import SequenceDataUpdateCoordinator

TO_REDACT = {
    CONF_API_TOKEN,
    CONF_BUDGET_API_TOKEN,
    CONF_BUDGET_ACCOUNT_ID,
    "id",
    "name",
    "balance",
}


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

    weekly: dict[str, Any] = {
        "enabled": bool(entry.options.get(CONF_BUDGET_ENABLED, False)),
        "configured": bool(
            entry.data.get(CONF_BUDGET_API_TOKEN) and entry.options.get(CONF_BUDGET_ACCOUNT_ID)
        ),
    }
    budget = coordinator.weekly_budget
    if budget is not None:
        weekly["last_update_success"] = budget.last_update_success
        if budget.last_error_type:
            weekly["last_error_type"] = budget.last_error_type
        if budget.data is not None:
            weekly["transaction_count"] = budget.data.transaction_count

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
        "weekly_budget": weekly,
    }
