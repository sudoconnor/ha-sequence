# Sequence for Home Assistant

A HACS-ready custom integration for [Sequence](https://www.getsequence.io/) finance automation.

Licensed under Apache-2.0. This is an unofficial community integration and is not affiliated with, endorsed by, or sponsored by Sequence Ltd.

Current MVP: **read-only Sequence account balance sensors, API health, balance-change events, and an optional weekly household budget**. Transfers, bill payments, and direct account movement are not implemented. Rule triggers are available only as an explicit service call for rule IDs allowlisted in integration options. The weekly budget uses a second, read-only Platform API key and only sends `GET` requests.

## Status

Early dogfood build. The integration is intentionally conservative while the public Sequence API surface is confirmed.

## Features

- UI config flow for a Sequence API token and API base URL
- Password-style token field; tokens are not logged or exposed in diagnostics
- Cloud polling via Home Assistant `DataUpdateCoordinator`
- One monetary sensor per discovered Sequence account
- API health/problem binary sensor for polling/auth/rate-limit failures
- Home Assistant events when a polled Sequence account balance increases or decreases
- Friendly names and entity IDs are clearly namespaced as `Sequence ...` / `sensor.sequence_*`
- Stable unique IDs based on Sequence account IDs, so entities survive account renames
- Optional `sequence.trigger_rule` service for allowlisted Sequence Remote API rule triggers
- Privacy-first diagnostics: tokens, account IDs, names, balances, and account metadata are redacted or summarized
- Options flow for polling interval and account balance sensor enablement
- Optional weekly household budget, configured in options, with its own read-only API key

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

Unavailable sensors usually mean Sequence returned an account without usable balance data. If Sequence provides a balance error, the integration exposes it as the non-sensitive `balance_error` attribute. Sensors also expose the Sequence `account_id` attribute so automations can target a stable account identity instead of only a friendly name.

## Weekly budget

The weekly budget is optional and does not replace the account balance sensors. Open **Settings → Devices & services → Sequence → Configure → Weekly budget**.

The form asks for:

- A **separate** read-only Sequence API key (`READ_ACCOUNTS` and `READ_TRANSFERS` on the household spend account only). It is stored in the config entry, not in YAML, and it is not the token from the initial setup. Leave the field blank later to keep the saved key.
- The account, chosen from `GET /accounts`.
- Weekly budget in USD. The default is 400.
- Refill weekday. The default is Friday. The cycle starts at 00:00 that weekday in Home Assistant's time zone.
- An optional card ID. Blank includes every card funded by the account.

The integration then polls about every 15 minutes, plus up to 90 seconds of jitter. A `429` response waits for the `Retry-After` header before the next poll. Each poll sends only:

- `GET /accounts/{id}`
- `GET /card-transactions?accountId=&from=<cycle start>` (paginated; optional `cardId`)
- `GET /accounts/{id}/transfers?from=<cycle start>` (paginated)

Nothing in this feature calls `POST`, `PATCH`, `PUT`, or `DELETE`.

Spend for the open cycle:

- `spent_settled` sums settled `MONEY_OUT` card rows. Refunds and other `MONEY_IN` card rows reduce it.
- The weekly refill is the incoming settled transfer near the start of the cycle (the budget-sized one, or otherwise the earliest rule transfer in the first 36 hours). It resets the week and is **not** a top-up.
- Other incoming settled transfers in the cycle are top-ups. Outgoing transfers, simulations, and transfers that are still pending are not top-ups.
- `remaining` is the spendable balance (`availableBalanceInCents` when Sequence sends it, otherwise the ledger balance).
- `spent_incl_pending = budget + top-ups - balance`
- `pending = max(0, spent_incl_pending - spent_settled)`
- `percent = balance / budget`
- Status is Critical at or below 10%, Low at or below 20%, and Healthy above that.

The entities use an `hs2_` object id so they can run beside an existing MQTT `household_spend_*` dashboard:

- `sensor.hs2_balance`
- `sensor.hs2_weekly_spend`
- `sensor.hs2_spent_settled`
- `sensor.hs2_pending`
- `sensor.hs2_top_ups`
- `sensor.hs2_remaining_percent`
- `sensor.hs2_status`
- `sensor.hs2_days_until_refill`
- `sensor.hs2_next_refill`
- `sensor.hs2_last_sync`
- `sensor.hs2_burn_rate`
- `sensor.hs2_average_transaction`
- `sensor.hs2_median_transaction`
- `sensor.hs2_largest_transaction`
- `sensor.hs2_top_merchant`
- `sensor.hs2_transactions` (the settled list is in attributes)
- `sensor.hs2_breakdown` (daily and merchant breakdowns)

Transaction and breakdown attributes are capped under Home Assistant's 16 KB attribute limit. `transactions`, `daily`, and `merchants` are excluded from the recorder. Average, median, and largest use settled purchases only. Burn rate is spend-including-pending divided by the days elapsed in the cycle, and it stays empty during the first hour.

These sensors are grouped on a **Sequence Weekly Budget** device. A failed budget poll does not mark `binary_sensor.sequence_api_problem` and does not stop the account balance sensors. The budget sensors go unavailable until the next successful poll. Diagnostics include whether the feature is enabled and a transaction count, and they redact the budget key and account ID.

## Events

After the first successful poll establishes a baseline, the integration fires Home Assistant events when an account balance changes between polls:

- `sequence_account_balance_increased`
- `sequence_account_balance_decreased`

Event data:

- `account_id`
- `account_name`
- `account_type`
- `previous_balance`
- `balance`
- `balance_change`
- `currency`

Example automation trigger:

```yaml
triggers:
  - trigger: event
    event_type: sequence_account_balance_increased
    event_data:
      account_name: 11467 Rent
conditions:
  - condition: template
    value_template: "{{ trigger.event.data.account_type == 'Income Source' }}"
```

Important limitation: these events are derived from the public `POST /accounts` balance snapshots. If money arrives in an income source and Sequence sweeps it away before Home Assistant polls, no balance delta is visible to the integration. A true transfer/activity event feed still requires a documented Sequence transaction/activity API or webhook.

The integration also creates `binary_sensor.sequence_api_problem`, which turns on when the latest Sequence polling attempt fails. It exposes only non-sensitive health attributes such as account count and a generic error type.

## API scope

Account balances still use:

- `POST /accounts`
- Header: `x-sequence-access-token: Bearer <token>`

The optional weekly budget uses a different key and the Platform API at `https://api.getsequence.io/platform/v1`:

- `Authorization: Bearer <read-only key>`
- `GET /accounts`
- `GET /accounts/{id}`
- `GET /card-transactions`
- `GET /accounts/{id}/transfers`

Rule discovery, money movement, bill payment, card management, and webhook registration are still not implemented. Rule execution is available only through the explicit `sequence.trigger_rule` service for allowlisted rule IDs. Additional mutating features should only be added behind explicit opt-in services/buttons with allowlists, confirmation text, caps, idempotency, and auditability.

## Services

### `sequence.trigger_rule`

Triggers a Sequence rule configured for Remote API access.

Guardrails:

- Disabled unless the rule ID is listed in **Sequence options → Allowlisted rule IDs**.
- Requires the rule's API secret at call time. This is different from the account access token used for balance reads.
- Supports an optional `idempotency_key` so automations can make retries safer.
- Fires a `sequence_rule_triggered` Home Assistant event containing the rule ID and Sequence request ID, but not the API secret or payload.

Example service data:

```yaml
rule_id: ru_12345
api_secret: !secret sequence_rule_api_secret
idempotency_key: paycheck-routing-2026-04-27
payload: {}
```

See [`docs/API_BOUNDARY.md`](docs/API_BOUNDARY.md) for the current API findings.

## Privacy and backups

Home Assistant entities will naturally show account names and balances to anyone who can access your Home Assistant instance.

The Sequence API token, and the separate weekly-budget key when that feature is enabled, are stored in Home Assistant's config-entry storage. The budget key is not written to YAML. Home Assistant does not encrypt config entries at rest for this integration, so treat Home Assistant backups as sensitive. Use the most restrictive token each feature allows. The weekly budget key should be a different key from the one used for balance polling.

Diagnostics are more conservative and redact or summarize sensitive fields.

## Publishing a release

HACS installs this integration from a GitHub release tag. After the version in `custom_components/sequence/manifest.json` is merged:

1. Create a GitHub release whose tag is `v0.3.0` (or `0.3.0`) and points at the commit that contains `"version": "0.3.0"`.
2. Publish the release. HACS downloads the repository at that tag; a separate zip asset is not required.
3. In HACS, add `https://github.com/sudoconnor/ha-sequence` as a custom repository with category **Integration**, if it is not already added.
4. Install or update **Sequence**, then restart Home Assistant.
5. Configure the weekly budget from the integration options with a new read-only key. Do not reuse the existing balance-polling token.

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
