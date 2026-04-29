# Changelog

## Unreleased

- Added Home Assistant balance-change events derived from polled Sequence account balances: `sequence_account_balance_increased` and `sequence_account_balance_decreased`.
- Added stable `account_id` to balance sensor attributes for safer automations.
- Documented the limitation that balance-change events cannot see funds that arrive and sweep away between polls; a true activity feed still needs documented Sequence transaction/activity API support.

## 0.1.0 - 2026-04-27

- Initial HACS-ready Sequence custom integration.
- Added UI config flow for Sequence API token and base URL.
- Added read-only `POST /accounts` client.
- Added one monetary account balance sensor per Sequence account.
- Added Sequence namespacing for friendly names/entity IDs.
- Added privacy-redacted diagnostics.
- Added options for polling interval and account sensor enablement.
- Added local Home Assistant brand assets so the integration no longer shows the generic “icon not available” placeholder.
- Replaced the temporary generated icon with Sequence’s public website favicon/brand mark and added an unofficial/non-affiliation notice.
- Changed monetary balance sensors to use Home Assistant’s supported `total` state class.
