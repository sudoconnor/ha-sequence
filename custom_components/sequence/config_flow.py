"""Config flow for Sequence."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    SequenceApiClient,
    SequenceApiError,
    SequenceAuthError,
    SequenceRateLimitError,
)
from .budget import AccountSummary
from .const import (
    CONF_ALLOWED_RULE_IDS,
    CONF_API_TOKEN,
    CONF_BASE_URL,
    CONF_BUDGET_ACCOUNT_ID,
    CONF_BUDGET_AMOUNT,
    CONF_BUDGET_API_TOKEN,
    CONF_BUDGET_CARD_ID,
    CONF_BUDGET_ENABLED,
    CONF_BUDGET_REFILL_WEEKDAY,
    CONF_ENABLE_ACCOUNT_SENSORS,
    DEFAULT_BASE_URL,
    DEFAULT_OPTIONS,
    DEFAULT_REFILL_WEEKDAY,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_WEEKLY_BUDGET,
    DOMAIN,
    MIN_SCAN_INTERVAL,
    WEEKDAYS,
)
from .platform_api import SequencePlatformClient

_CARD_ID = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
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
            vol.Optional(
                CONF_ALLOWED_RULE_IDS,
                default=options.get(
                    CONF_ALLOWED_RULE_IDS,
                    DEFAULT_OPTIONS[CONF_ALLOWED_RULE_IDS],
                ),
            ): selector.TextSelector(selector.TextSelectorConfig(multiline=True)),
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
        self._budget_accounts: list[AccountSummary] = []
        self._budget_token = ""
        self._budget_values: dict[str, Any] = {}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Offer polling options or the weekly budget."""

        _ = user_input
        return self.async_show_menu(
            step_id="init",
            menu_options=["general", "weekly_budget"],
        )

    async def async_step_general(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Manage polling, account sensors, and the rule allowlist."""

        if user_input is not None:
            options = _without_budget_secret(self._config_entry.options)
            options.update(user_input)
            return self.async_create_entry(title="", data=options)

        merged_options = {
            CONF_SCAN_INTERVAL: self._config_entry.options.get(
                CONF_SCAN_INTERVAL,
                self._config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            ),
            CONF_ENABLE_ACCOUNT_SENSORS: self._config_entry.options.get(
                CONF_ENABLE_ACCOUNT_SENSORS,
                DEFAULT_OPTIONS[CONF_ENABLE_ACCOUNT_SENSORS],
            ),
            CONF_ALLOWED_RULE_IDS: self._config_entry.options.get(
                CONF_ALLOWED_RULE_IDS,
                DEFAULT_OPTIONS[CONF_ALLOWED_RULE_IDS],
            ),
        }
        return self.async_show_form(
            step_id="general",
            data_schema=_options_schema(merged_options),
        )

    async def async_step_weekly_budget(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Collect the read-only key, budget, refill weekday, and optional card."""

        errors: dict[str, str] = {}
        current = _budget_form_defaults(self._config_entry.options)
        if user_input is not None:
            current.update(
                {
                    CONF_BUDGET_ENABLED: user_input[CONF_BUDGET_ENABLED],
                    CONF_BUDGET_AMOUNT: user_input[CONF_BUDGET_AMOUNT],
                    CONF_BUDGET_REFILL_WEEKDAY: user_input[CONF_BUDGET_REFILL_WEEKDAY],
                    CONF_BUDGET_CARD_ID: user_input.get(CONF_BUDGET_CARD_ID, ""),
                }
            )
            card_id = str(user_input.get(CONF_BUDGET_CARD_ID, "")).strip()
            if card_id and _CARD_ID.fullmatch(card_id) is None:
                errors[CONF_BUDGET_CARD_ID] = "invalid_card_id"
            elif not user_input[CONF_BUDGET_ENABLED]:
                return self._save_budget(
                    token=None,
                    values={
                        CONF_BUDGET_ENABLED: False,
                        CONF_BUDGET_AMOUNT: user_input[CONF_BUDGET_AMOUNT],
                        CONF_BUDGET_REFILL_WEEKDAY: user_input[CONF_BUDGET_REFILL_WEEKDAY],
                        CONF_BUDGET_CARD_ID: card_id,
                    },
                )
            else:
                typed_token = str(user_input.get(CONF_BUDGET_API_TOKEN, "")).strip()
                stored_token = str(self._config_entry.data.get(CONF_BUDGET_API_TOKEN, "")).strip()
                token = typed_token or stored_token
                if not token:
                    errors[CONF_BUDGET_API_TOKEN] = "invalid_auth"
                else:
                    try:
                        accounts = await _async_list_budget_accounts(
                            self.hass, self._config_entry, token
                        )
                    except SequenceAuthError:
                        errors["base"] = "invalid_auth"
                    except SequenceRateLimitError:
                        errors["base"] = "rate_limited"
                    except SequenceApiError:
                        errors["base"] = "cannot_connect"
                    except Exception:  # pragma: no cover - defensive HA flow guard
                        errors["base"] = "unknown"
                    else:
                        if not accounts:
                            errors["base"] = "no_accounts"
                        else:
                            self._budget_accounts = accounts
                            self._budget_token = token if typed_token else ""
                            self._budget_values = {
                                CONF_BUDGET_ENABLED: True,
                                CONF_BUDGET_AMOUNT: user_input[CONF_BUDGET_AMOUNT],
                                CONF_BUDGET_REFILL_WEEKDAY: user_input[CONF_BUDGET_REFILL_WEEKDAY],
                                CONF_BUDGET_CARD_ID: card_id,
                            }
                            return await self.async_step_weekly_budget_account()

        return self.async_show_form(
            step_id="weekly_budget",
            data_schema=_weekly_budget_schema(current),
            errors=errors,
        )

    async def async_step_weekly_budget_account(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Choose the account the read-only key should track."""

        if not self._budget_accounts:
            return await self.async_step_weekly_budget()

        errors: dict[str, str] = {}
        options = _account_options(self._budget_accounts)
        known_ids = {option["value"] for option in options}
        if user_input is not None:
            account_id = str(user_input[CONF_BUDGET_ACCOUNT_ID])
            if account_id not in known_ids:
                errors[CONF_BUDGET_ACCOUNT_ID] = "account_required"
            else:
                token = self._budget_token or str(
                    self._config_entry.data.get(CONF_BUDGET_API_TOKEN, "")
                ).strip()
                try:
                    await _async_get_budget_account(
                        self.hass, self._config_entry, token, account_id
                    )
                except SequenceAuthError:
                    errors["base"] = "forbidden_account"
                except SequenceRateLimitError:
                    errors["base"] = "rate_limited"
                except SequenceApiError:
                    errors["base"] = "cannot_connect"
                except Exception:  # pragma: no cover - defensive HA flow guard
                    errors["base"] = "unknown"
                else:
                    values = dict(self._budget_values)
                    values[CONF_BUDGET_ACCOUNT_ID] = account_id
                    return self._save_budget(token=self._budget_token or None, values=values)

        previous = self._config_entry.options.get(CONF_BUDGET_ACCOUNT_ID)
        submitted = None if user_input is None else user_input.get(CONF_BUDGET_ACCOUNT_ID)
        if submitted in known_ids:
            default_account = submitted
        elif previous in known_ids:
            default_account = previous
        else:
            default_account = options[0]["value"]
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_BUDGET_ACCOUNT_ID, default=default_account
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                )
            }
        )
        return self.async_show_form(
            step_id="weekly_budget_account",
            data_schema=schema,
            errors=errors,
        )

    def _save_budget(
        self, *, token: str | None, values: dict[str, Any]
    ) -> config_entries.ConfigFlowResult:
        """Store the read-only key in entry data and the other fields in options."""

        options = _without_budget_secret(self._config_entry.options)
        options.update(values)
        data = dict(self._config_entry.data)
        if token:
            data[CONF_BUDGET_API_TOKEN] = token.strip()
        if data != dict(self._config_entry.data):
            self.hass.config_entries.async_update_entry(self._config_entry, data=data)
        return self.async_create_entry(title="", data=options)


def _weekly_budget_schema(current: dict[str, Any]) -> vol.Schema:
    """Return the weekly budget form."""

    return vol.Schema(
        {
            vol.Required(
                CONF_BUDGET_ENABLED, default=current.get(CONF_BUDGET_ENABLED, True)
            ): bool,
            vol.Optional(CONF_BUDGET_API_TOKEN, default=""): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
            vol.Required(
                CONF_BUDGET_AMOUNT,
                default=current.get(CONF_BUDGET_AMOUNT, DEFAULT_WEEKLY_BUDGET),
            ): vol.All(vol.Coerce(float), vol.Range(min=1, max=1_000_000)),
            vol.Required(
                CONF_BUDGET_REFILL_WEEKDAY,
                default=current.get(CONF_BUDGET_REFILL_WEEKDAY, DEFAULT_REFILL_WEEKDAY),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[{"value": day, "label": day.capitalize()} for day in WEEKDAYS],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                CONF_BUDGET_CARD_ID, default=current.get(CONF_BUDGET_CARD_ID, "")
            ): str,
        }
    )


def _budget_form_defaults(options: Mapping[str, Any]) -> dict[str, Any]:
    """Return non-secret weekly budget defaults."""

    return {
        CONF_BUDGET_ENABLED: options.get(CONF_BUDGET_ENABLED, True),
        CONF_BUDGET_AMOUNT: options.get(CONF_BUDGET_AMOUNT, DEFAULT_WEEKLY_BUDGET),
        CONF_BUDGET_REFILL_WEEKDAY: options.get(CONF_BUDGET_REFILL_WEEKDAY, DEFAULT_REFILL_WEEKDAY),
        CONF_BUDGET_CARD_ID: options.get(CONF_BUDGET_CARD_ID, ""),
    }


def _without_budget_secret(options: Mapping[str, Any]) -> dict[str, Any]:
    """Copy options without ever persisting the read-only key there."""

    copied = dict(options)
    copied.pop(CONF_BUDGET_API_TOKEN, None)
    return copied


def _account_options(accounts: list[AccountSummary]) -> list[dict[str, str]]:
    """Build a dropdown where duplicate names stay distinguishable."""

    ordered = sorted(accounts, key=lambda item: (item.name.casefold(), item.id))
    bases = [
        f"{account.name} ({account.type})" if account.type else account.name for account in ordered
    ]
    counts: dict[str, int] = {}
    for base in bases:
        counts[base] = counts.get(base, 0) + 1
    options: list[dict[str, str]] = []
    for account, base in zip(ordered, bases, strict=True):
        label = base if counts[base] == 1 else f"{base} {account.id[-4:]}"
        options.append({"value": account.id, "label": label[:80]})
    return options


async def _async_list_budget_accounts(
    hass: HomeAssistant,
    entry: config_entries.ConfigEntry,
    token: str,
) -> list[AccountSummary]:
    """Validate a read-only key with GET /accounts."""

    client = _budget_client(hass, entry, token)
    return await client.async_list_accounts()


async def _async_get_budget_account(
    hass: HomeAssistant,
    entry: config_entries.ConfigEntry,
    token: str,
    account_id: str,
) -> None:
    """Confirm the key can read the selected account."""

    client = _budget_client(hass, entry, token)
    await client.async_get_account(account_id)


def _budget_client(
    hass: HomeAssistant,
    entry: config_entries.ConfigEntry,
    token: str,
) -> SequencePlatformClient:
    """Build a platform client from the integration host and a budget key."""

    session = async_get_clientsession(hass)
    return SequencePlatformClient(
        session=session,
        api_token=token,
        base_url=entry.data.get(CONF_BASE_URL, DEFAULT_BASE_URL),
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
