"""Read-only Sequence Platform API client for the weekly budget.

Only GET is implemented. Account creation, transfers, and rule triggers are
intentionally absent so this key cannot move money.
"""

from __future__ import annotations

import asyncio
from typing import Any, Protocol
from urllib.parse import quote, urljoin

from .api import (
    SequenceApiError,
    SequenceAuthError,
    SequenceRateLimitError,
    _bearer,
)
from .budget import (
    AccountSnapshot,
    AccountSummary,
    AccountTransfer,
    CardTransaction,
    has_next_page,
    items_from_envelope,
    parse_account,
    parse_account_list,
    parse_card_transactions,
    parse_transfers,
    to_rfc3339,
)
from .const import DEFAULT_BASE_URL

_PAGE_SIZE = 100
_MAX_PAGES = 20
_MAX_INLINE_RETRIES = 2
_MAX_INLINE_WAIT_SECONDS = 30
_CALLED_REASON = "Home Assistant sequence integration weekly budget (read-only)"


class _Headers(Protocol):
    """Subset of a response header mapping."""

    def get(self, key: str, default: str | None = None) -> str | None: ...


class _Response(Protocol):
    """Subset of aiohttp.ClientResponse used by the platform client."""

    status: int
    headers: _Headers

    async def text(self) -> str: ...

    async def json(self, *, content_type: str | None = None) -> Any: ...


class _RequestContext(Protocol):
    """Async context manager returned by aiohttp request helpers."""

    async def __aenter__(self) -> _Response: ...

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None: ...


class _Session(Protocol):
    """Subset of aiohttp.ClientSession. This client only calls GET."""

    def get(self, url: str, **kwargs: Any) -> _RequestContext: ...


class _Sleeper(Protocol):
    """Awaitable used to honor a short Retry-After without importing HA."""

    async def __call__(self, seconds: float) -> None: ...


def platform_base_url(base_url: str | None) -> str:
    """Return the Platform v1 base URL for a configured Sequence host."""

    base = (base_url or DEFAULT_BASE_URL).rstrip("/")
    if base.endswith("/platform/v1"):
        return base + "/"
    return base + "/platform/v1/"


def parse_retry_after(headers: Any) -> float | None:
    """Return a Retry-After delay in seconds, when the header is numeric."""

    if headers is None:
        return None
    getter = getattr(headers, "get", None)
    if getter is None:
        return None
    raw = getter("Retry-After")
    if raw is None:
        raw = getter("retry-after")
    if raw is None:
        return None
    try:
        return max(0.0, float(str(raw).strip()))
    except (TypeError, ValueError):
        return None


class SequencePlatformClient:
    """GET-only client for Sequence Platform account, card, and transfer reads."""

    def __init__(
        self,
        session: _Session,
        api_token: str,
        base_url: str = DEFAULT_BASE_URL,
        request_timeout: int = 20,
        sleep: _Sleeper | None = None,
    ) -> None:
        self._session = session
        self._api_token = api_token.strip()
        self._base_url = platform_base_url(base_url)
        self._request_timeout = request_timeout
        self._sleep = sleep or asyncio.sleep

    async def async_list_accounts(self) -> list[AccountSummary]:
        """Fetch account summaries with GET /accounts."""

        items, _truncated = await self._async_get_all_items("accounts", {})
        return parse_account_list({"data": {"items": items, "pagination": {"hasNextPage": False}}})

    async def async_get_account(self, account_id: str) -> AccountSnapshot:
        """Fetch one account balance with GET /accounts/{id}."""

        payload = await self._async_get_json(f"accounts/{quote(account_id, safe='')}")
        return parse_account(payload)

    async def async_list_card_transactions(
        self,
        account_id: str,
        *,
        created_from: Any,
        card_id: str | None = None,
    ) -> tuple[list[CardTransaction], bool]:
        """Fetch settled card transactions for an account since ``created_from``."""

        params: dict[str, Any] = {
            "accountId": account_id,
            "from": to_rfc3339(created_from),
        }
        if card_id:
            params["cardId"] = card_id
        items, truncated = await self._async_get_all_items("card-transactions", params)
        return parse_card_transactions(items), truncated

    async def async_list_transfers(
        self,
        account_id: str,
        *,
        created_from: Any,
    ) -> tuple[list[AccountTransfer], bool]:
        """Fetch transfers for an account since ``created_from``."""

        params = {"from": to_rfc3339(created_from)}
        path = f"accounts/{quote(account_id, safe='')}/transfers"
        items, truncated = await self._async_get_all_items(path, params)
        return parse_transfers(items), truncated

    async def _async_get_all_items(
        self, path: str, params: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], bool]:
        """Follow pagination and return items plus a truncation flag."""

        items: list[dict[str, Any]] = []
        page = 1
        while page <= _MAX_PAGES:
            query = {**params, "page": page, "pageSize": _PAGE_SIZE}
            payload = await self._async_get_json(path, query)
            batch = items_from_envelope(payload)
            items.extend(batch)
            if not has_next_page(payload, page_size=_PAGE_SIZE, item_count=len(batch)):
                return items, False
            page += 1
        return items, True

    async def _async_get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """GET JSON from the platform API, honoring a short Retry-After."""

        url = urljoin(self._base_url, path.lstrip("/"))
        headers = {
            "accept": "application/json",
            "authorization": _bearer(self._api_token),
            "x-called-reason": _CALLED_REASON,
        }
        attempt = 0
        while True:
            try:
                async with asyncio.timeout(self._request_timeout):
                    async with self._session.get(url, headers=headers, params=params) as response:
                        status = response.status
                        retry_after = (
                            parse_retry_after(response.headers) if status == 429 else None
                        )
                        if status == 429 or status in (401, 403):
                            await response.text()
                            payload = None
                            detail = None
                        elif status >= 400:
                            detail = await _error_code(response)
                            payload = None
                        else:
                            detail = None
                            try:
                                payload = await response.json(content_type=None)
                            except Exception as err:
                                text = await response.text()
                                raise SequenceApiError(
                                    f"Sequence API returned invalid JSON: {text[:120]}"
                                ) from err
            except TimeoutError as err:
                raise SequenceApiError("Timed out while talking to Sequence") from err
            except SequenceApiError:
                raise
            except Exception as err:
                raise SequenceApiError(f"Could not connect to Sequence: {err}") from err

            if status == 429:
                if (
                    attempt < _MAX_INLINE_RETRIES
                    and retry_after is not None
                    and retry_after <= _MAX_INLINE_WAIT_SECONDS
                ):
                    attempt += 1
                    await self._sleep(retry_after)
                    continue
                raise SequenceRateLimitError(
                    "Sequence API rate limit exceeded",
                    retry_after=retry_after,
                )
            if status in (401, 403):
                raise SequenceAuthError("Sequence rejected the read-only API key")
            if status >= 400:
                suffix = f": {detail}" if detail else ""
                raise SequenceApiError(f"Sequence API returned HTTP {status}{suffix}")
            return payload


async def _error_code(response: _Response) -> str | None:
    """Return a short machine-readable error code, without the response body."""

    try:
        payload = await response.json(content_type=None)
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    error = payload.get("error")
    if isinstance(error, dict):
        code = error.get("code")
        if isinstance(code, str) and code.strip():
            return code.strip()
    return None
