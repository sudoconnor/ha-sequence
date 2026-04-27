"""Small async client for the public Sequence API.

The public API currently exposes accounts via POST /accounts with the
`x-sequence-access-token` header. Keep this module intentionally narrow and
read-only until Sequence documents broader discovery and mutation APIs.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urljoin

from .const import DEFAULT_BASE_URL


class SequenceApiError(Exception):
    """Base error raised by the Sequence API client."""


class SequenceAuthError(SequenceApiError):
    """Raised when the Sequence token is rejected."""


class SequenceRateLimitError(SequenceApiError):
    """Raised when Sequence rate limits the request."""


class _Response(Protocol):
    """Subset of aiohttp.ClientResponse used by the client."""

    status: int

    async def text(self) -> str: ...

    async def json(self, *, content_type: str | None = None) -> Any: ...


class _RequestContext(Protocol):
    """Async context manager returned by aiohttp request helpers."""

    async def __aenter__(self) -> _Response: ...

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None: ...


class _Session(Protocol):
    """Subset of aiohttp.ClientSession used by the client."""

    def post(self, url: str, **kwargs: Any) -> _RequestContext: ...


@dataclass(slots=True, frozen=True)
class SequenceAccount:
    """Normalized Sequence account."""

    id: str
    name: str
    type: str | None = None
    balance: float | None = None
    balance_error: str | None = None
    currency: str = "USD"


class SequenceApiClient:
    """Read-only Sequence API client."""

    def __init__(
        self,
        session: _Session,
        api_token: str,
        base_url: str = DEFAULT_BASE_URL,
        request_timeout: int = 20,
    ) -> None:
        self._session = session
        self._api_token = api_token.strip()
        self._base_url = base_url.rstrip("/") + "/"
        self._request_timeout = request_timeout

    async def async_get_accounts(self) -> list[SequenceAccount]:
        """Fetch and normalize Sequence accounts."""

        payload = await self._async_post_json("accounts", {})
        return _extract_accounts(payload)

    async def _async_post_json(self, path: str, body: dict[str, Any]) -> Any:
        """POST JSON to Sequence and return decoded JSON."""

        url = urljoin(self._base_url, path.lstrip("/"))
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "x-sequence-access-token": _bearer(self._api_token),
        }

        try:
            async with asyncio.timeout(self._request_timeout):
                async with self._session.post(url, headers=headers, json=body) as response:
                    if response.status in (401, 403):
                        raise SequenceAuthError("Sequence rejected the API token")
                    if response.status == 429:
                        raise SequenceRateLimitError("Sequence API rate limit exceeded")
                    if response.status >= 400:
                        text = await response.text()
                        raise SequenceApiError(
                            f"Sequence API returned HTTP {response.status}: {text[:300]}"
                        )
                    try:
                        return await response.json(content_type=None)
                    except Exception as err:  # pragma: no cover - aiohttp/json edge
                        text = await response.text()
                        raise SequenceApiError(
                            f"Sequence API returned invalid JSON: {text[:300]}"
                        ) from err
        except TimeoutError as err:
            raise SequenceApiError("Timed out while talking to Sequence") from err
        except SequenceApiError:
            raise
        except Exception as err:  # aiohttp is intentionally not imported at module import time
            raise SequenceApiError(f"Could not connect to Sequence: {err}") from err


def _bearer(token: str) -> str:
    """Return a Bearer token header value."""

    if token.lower().startswith("bearer "):
        return token
    return f"Bearer {token}"


def _extract_accounts(payload: Any) -> list[SequenceAccount]:
    """Extract accounts from known Sequence response shapes."""

    accounts = _find_accounts(payload)
    normalized: list[SequenceAccount] = []
    for account in accounts:
        if not isinstance(account, dict):
            continue
        account_id = _first_string(account, "id", "accountId", "uuid")
        if not account_id:
            continue
        name = _first_string(account, "name", "nickname", "displayName") or "Sequence Account"
        balance, balance_error, currency = _parse_balance(account.get("balance"))
        normalized.append(
            SequenceAccount(
                id=account_id,
                name=name,
                type=_first_string(account, "type", "subtype", "accountType"),
                balance=balance,
                balance_error=balance_error,
                currency=currency or "USD",
            )
        )
    return normalized


def _find_accounts(payload: Any) -> list[Any]:
    """Return account list from common Sequence envelopes."""

    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []

    candidates = (
        payload.get("accounts"),
        payload.get("data", {}).get("accounts") if isinstance(payload.get("data"), dict) else None,
        payload.get("data") if isinstance(payload.get("data"), list) else None,
        payload.get("items"),
    )
    for candidate in candidates:
        if isinstance(candidate, list):
            return candidate
    return []


def _parse_balance(balance: Any) -> tuple[float | None, str | None, str | None]:
    """Normalize a Sequence balance object into dollars, error, and currency."""

    if isinstance(balance, (int, float)):
        return float(balance), None, "USD"
    if not isinstance(balance, dict):
        return None, None, "USD"

    error = balance.get("error")
    balance_error = str(error) if error not in (None, "") else None
    currency = _first_string(balance, "currency", "currencyCode") or "USD"

    for key in ("amountInDollars", "dollars", "amount"):
        value = _as_float(balance.get(key))
        if value is not None:
            return value, balance_error, currency

    for key in ("amountInCents", "cents"):
        value = _as_float(balance.get(key))
        if value is not None:
            return value / 100, balance_error, currency

    formatted = balance.get("formatted")
    if isinstance(formatted, str):
        parsed = _money_string_to_float(formatted)
        if parsed is not None:
            return parsed, balance_error, currency

    return None, balance_error, currency


def _first_string(obj: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = obj.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", ""))
        except ValueError:
            return None
    return None


def _money_string_to_float(value: str) -> float | None:
    cleaned = value.replace("$", "").replace(",", "").strip()
    negative = cleaned.startswith("(") and cleaned.endswith(")")
    cleaned = cleaned.strip("()")
    parsed = _as_float(cleaned)
    if parsed is None:
        return None
    return -parsed if negative else parsed
