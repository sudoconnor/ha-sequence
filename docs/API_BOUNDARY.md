# Sequence API boundary

This project currently treats Sequence as a read-only source for account balances. Balance-change events are derived locally by comparing successive account-balance polls.

## Confirmed working

- Base URL: `https://api.getsequence.io`
- Auth header: `x-sequence-access-token: Bearer <token>`
- Account discovery/balance read: `POST /accounts`
- Locally derived Home Assistant balance-change events when an account balance changes between successful polls

## Not implemented yet

The following areas are intentionally out of scope until they are documented and can be implemented with Home Assistant guardrails:

- Rule discovery/listing
- Rule triggering
- Transfers or other money movement
- Bill payment
- Card management
- Webhook registration
- Transaction firehose/history

## Balance-change event limitation

The integration fires `sequence_account_balance_increased` and `sequence_account_balance_decreased` events by comparing current `POST /accounts` balances to the previous successful poll. This is useful for automations when funds remain visible in an account long enough for Home Assistant to sample the balance.

It is not a substitute for a transfer/activity feed. If money lands in an income source and Sequence immediately routes it elsewhere between polls, the public account snapshot can show no observable delta. A reliable "money arrived" event for that case requires a documented Sequence transaction/activity endpoint or webhook that includes transfer IDs, amounts, sources, destinations, statuses, and timestamps.

## Dogfood findings

A read-only probe against likely list-style endpoints found `POST /accounts` working. Candidate `GET` endpoints such as `/accounts`, `/pods`, `/rules`, `/cards`, `/transfers`, `/transactions`, `/webhooks`, and related rule-execution paths returned `405 Method Not Allowed` with the current public token/API shape. Earlier empty-body `POST` probes of `/pods`, `/rules`, and `/cards` returned route-not-found responses.

That finding is deliberately phrased narrowly: it means these resources are not available through the currently tested public API paths and scopes, not that Sequence cannot expose them through another documented API.

## Safety bar for future mutating features

Before adding any mutating feature, require all of the following:

- Explicit opt-in in the config/options flow
- Allowlist of permitted Sequence rule/action IDs
- Clear Home Assistant service/button confirmation language
- Idempotency key support where the API permits it
- Transfer/action caps where the API permits it
- Audit trail in Home Assistant logs/events without leaking tokens or raw financial details
- Tests proving read-only defaults remain read-only
