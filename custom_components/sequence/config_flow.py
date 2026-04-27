"""Config flow for Sequence."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SequenceApiClient, SequenceApiError, SequenceAuthError
from .const import (
    CONF_API_TOKEN,
    CONF_BASE_URL,
    CONF_ENABLE_ACCOUNT_SENSORS,
    DEFAULT_BASE_URL,
    DEFAULT_OPTIONS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)


def _user_schema(user_input: dict[str, Any] | None = None) -> vol.Schema:
    """Return the user step schema."""

    user_input = user_input or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_API_TOKEN,
                default="",
            ): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
            vol.Required(CONF_BASE_URL, default=user_input.get(CONF_BASE_URL, DEFAULT_BASE_URL)): str,
            vol.Optional(
                CONF_SCAN_INTERVAL,
                default=user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            ): vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL)),
        }
    )


def _options_schema(options: dict[str, Any]) -> vol.Schema:
    """Return the options schema."""

    return vol.Schema(
        {
            vol.Optional(
                CONF_SCAN_INTERVAL,
                default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            ): vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL)),
            vol.Optional(
                CONF_ENABLE_ACCOUNT_SENSORS,
                default=options.get(
                    CONF_ENABLE_ACCOUNT_SENSORS,
                    DEFAULT_OPTIONS[CONF_ENABLE_ACCOUNT_SENSORS],
                ),
            ): bool,
        }
    )


class SequenceConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a Sequence config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial step."""

        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await _validate_input(self.hass, user_input)
            except SequenceAuthError:
                errors["base"] = "invalid_auth"
            except SequenceApiError:
                errors["base"] = "cannot_connect"
            except Exception:  # pragma: no cover - defensive HA flow guard
                errors["base"] = "unknown"
            else:
                base_url = user_input[CONF_BASE_URL].rstrip("/")
                await self.async_set_unique_id(base_url)
                self._abort_if_unique_id_configured()

                data = {
                    CONF_API_TOKEN: user_input[CONF_API_TOKEN].strip(),
                    CONF_BASE_URL: base_url,
                    CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL],
                }
                return self.async_create_entry(title="Sequence", data=data)

        return self.async_show_form(
            step_id="user",
            data_schema=_user_schema(user_input),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> SequenceOptionsFlow:
        """Create the options flow."""

        return SequenceOptionsFlow(config_entry)


class SequenceOptionsFlow(config_entries.OptionsFlow):
    """Handle Sequence options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""

        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Manage Sequence options."""

        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        merged_options = {
            CONF_SCAN_INTERVAL: self._config_entry.options.get(
                CONF_SCAN_INTERVAL,
                self._config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            ),
            CONF_ENABLE_ACCOUNT_SENSORS: self._config_entry.options.get(
                CONF_ENABLE_ACCOUNT_SENSORS,
                DEFAULT_OPTIONS[CONF_ENABLE_ACCOUNT_SENSORS],
            ),
        }
        return self.async_show_form(
            step_id="init",
            data_schema=_options_schema(merged_options),
        )


async def _validate_input(hass: HomeAssistant, user_input: dict[str, Any]) -> None:
    """Validate credentials by fetching accounts."""

    session = async_get_clientsession(hass)
    client = SequenceApiClient(
        session=session,
        api_token=user_input[CONF_API_TOKEN],
        base_url=user_input[CONF_BASE_URL],
    )
    await client.async_get_accounts()
