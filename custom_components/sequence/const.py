"""Constants for the Sequence integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "sequence"

DEFAULT_BASE_URL = "https://api.getsequence.io"
DEFAULT_SCAN_INTERVAL = 300
MIN_SCAN_INTERVAL = 60

CONF_API_TOKEN = "api_token"
CONF_BASE_URL = "base_url"
CONF_ENABLE_ACCOUNT_SENSORS = "enable_account_sensors"

DEFAULT_OPTIONS = {
    CONF_ENABLE_ACCOUNT_SENSORS: True,
}

PLATFORMS = ["sensor"]
DEFAULT_UPDATE_INTERVAL = timedelta(seconds=DEFAULT_SCAN_INTERVAL)

ATTR_ACCOUNT_TYPE = "account_type"
ATTR_BALANCE_ERROR = "balance_error"
