# Changelog

## Unreleased

## 0.3.0 - 2026-10-16

- Added an optional weekly household budget that polls Sequence with its own read-only API key.
- The budget is configured in the options flow: account, weekly amount (default $400), refill weekday (default Friday), and an optional card ID.
- Polls about every 15 minutes with jitter, and backs off using the `Retry-After` header on HTTP 429.
- Computes settled spend, pending spend, top-ups, remaining balance, percent, status, refill timing, burn rate, and transaction statistics from `GET /accounts/{id}`, `GET /card-transactions`, and `GET /accounts/{id}/transfers`.
- The weekly refill transfer is excluded from top-ups. Refunds reduce settled spend.
- Publishes `sensor.hs2_*` entities, including separate transaction and breakdown sensors whose large attributes are capped and excluded from the recorder.
- Does not call mutating Platform API endpoints, and does not change the existing balance sensors, API health sensor, or `sequence.trigger_rule` service.

## 0.2.0 - 2026-05-07

- Added an API health/problem binary sensor for Sequence polling failures.
- Added a draft `sequence.trigger_rule` service for allowlisted Sequence Remote API rule triggers.
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
