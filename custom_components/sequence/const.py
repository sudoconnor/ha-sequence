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
CONF_ALLOWED_RULE_IDS = "allowed_rule_ids"

DEFAULT_OPTIONS = {
    CONF_ENABLE_ACCOUNT_SENSORS: True,
    CONF_ALLOWED_RULE_IDS: "",
}

PLATFORMS = ["sensor"]
DEFAULT_UPDATE_INTERVAL = timedelta(seconds=DEFAULT_SCAN_INTERVAL)

ATTR_ACCOUNT_TYPE = "account_type"
ATTR_BALANCE_ERROR = "balance_error"

SERVICE_TRIGGER_RULE = "trigger_rule"

ATTR_API_SECRET = "api_secret"
ATTR_IDEMPOTENCY_KEY = "idempotency_key"
ATTR_PAYLOAD = "payload"
ATTR_RULE_ID = "rule_id"

EVENT_RULE_TRIGGERED = "sequence_rule_triggered"
