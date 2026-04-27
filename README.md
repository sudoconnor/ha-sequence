# Sequence for Home Assistant

A HACS-ready custom integration for [Sequence](https://www.getsequence.io/) finance automation.

Licensed under Apache-2.0.

Current MVP: **read-only Sequence account balance sensors**. No transfers, rule triggers, bill payments, or other money-moving actions are implemented.

## Status

Early dogfood build. The integration is intentionally conservative while the public Sequence API surface is confirmed.

## Features

- UI config flow for a Sequence API token and API base URL
- Password-style token field; tokens are not logged or exposed in diagnostics
- Cloud polling via Home Assistant `DataUpdateCoordinator`
- One monetary sensor per discovered Sequence account
- Friendly names and entity IDs are clearly namespaced as `Sequence ...` / `sensor.sequence_*`
- Stable unique IDs based on Sequence account IDs, so entities survive account renames
- Privacy-first diagnostics: tokens, account IDs, names, balances, and account metadata are redacted or summarized
- Options flow for polling interval and account balance sensor enablement

## Install with HACS

1. In HACS, add this repository as a **custom repository** with category **Integration**.
2. Install **Sequence**.
3. Restart Home Assistant.
4. Go to **Settings → Devices & services → Add integration → Sequence**.
5. Enter a Sequence API token. Use the most restrictive/read-only token Sequence allows for this integration.

Default API base URL: `https://api.getsequence.io`

## Entities

The integration currently creates monetary sensors for Sequence account balances.

Example entity IDs:

- `sensor.sequence_operating_account_balance`
- `sensor.sequence_rent_balance`
- `sensor.sequence_credit_card_balance`

Unavailable sensors usually mean Sequence returned an account without usable balance data. If Sequence provides a balance error, the integration exposes it as the non-sensitive `balance_error` attribute.

## API scope

The integration currently uses:

- `POST /accounts`
- Header: `x-sequence-access-token: Bearer <token>`

Sequence rule discovery, rule execution, transfers, cards, webhooks, and other non-account resources are deliberately **not** implemented yet. Mutating features should only be added behind explicit opt-in services/buttons with allowlists, confirmation text, caps, idempotency, and auditability.

See [`docs/API_BOUNDARY.md`](docs/API_BOUNDARY.md) for the current API findings.

## Privacy and backups

Home Assistant entities will naturally show account names and balances to anyone who can access your Home Assistant instance.

The Sequence API token is stored in Home Assistant's config-entry storage, following the normal UI integration pattern. Home Assistant does not encrypt config entries at rest for this integration, so treat Home Assistant backups as sensitive. Use the most restrictive/read-only Sequence API token available.

Diagnostics are more conservative and redact or summarize sensitive fields.

## Development

Run the offline checks from the repo root:

```bash
python3 -m unittest discover -s tests
python3 -m compileall custom_components tests
python3 -m json.tool custom_components/sequence/manifest.json >/dev/null
python3 -m json.tool custom_components/sequence/strings.json >/dev/null
python3 -m json.tool custom_components/sequence/translations/en.json >/dev/null
python3 -m json.tool hacs.json >/dev/null
```

The unit tests cover local normalization logic and do not hit Sequence.

Optional read-only API probe:

```bash
SEQUENCE_API_TOKEN='...' node tools/probe-readonly-api.mjs
```

The probe only calls the known read-only `POST /accounts` endpoint and safe `GET` checks for candidate discovery endpoints.
