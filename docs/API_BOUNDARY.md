# Sequence API boundary

This project currently treats Sequence as a read-only source for account balances.

## Confirmed working

- Base URL: `https://api.getsequence.io`
- Auth header: `x-sequence-access-token: Bearer <token>`
- Account discovery/balance read: `POST /accounts`

## Documented but not dogfooded

- Rule trigger: `POST /remote-api/rules/{ruleId}/trigger`
- Auth header for rule triggers: `x-sequence-signature: Bearer <rule API secret>`
- Optional idempotency header: `idempotency-key: <unique trigger key>`

## Not implemented yet

The following areas are intentionally out of scope until they are documented and can be implemented with Home Assistant guardrails:

- Rule discovery/listing
- Transfers or other money movement
- Bill payment
- Card management
- Webhook registration
- Transaction firehose/history

## Dogfood findings

A read-only probe against likely list-style endpoints found `POST /accounts` working. Candidate `GET` endpoints such as `/accounts`, `/pods`, `/rules`, `/cards`, `/transfers`, `/transactions`, `/webhooks`, and related rule-execution paths returned `405 Method Not Allowed` with the current public token/API shape. Earlier empty-body `POST` probes of `/pods`, `/rules`, and `/cards` returned route-not-found responses.

That finding is deliberately phrased narrowly: it means these resources are not available through the currently tested public API paths and scopes, not that Sequence cannot expose them through another documented API.

## Safety bar for future mutating features

Before adding any mutating feature beyond allowlisted rule triggers, require all of the following:

- Explicit opt-in in the config/options flow
- Allowlist of permitted Sequence rule/action IDs
- Clear Home Assistant service/button confirmation language
- Idempotency key support where the API permits it
- Transfer/action caps where the API permits it
- Audit trail in Home Assistant logs/events without leaking tokens or raw financial details
- Tests proving read-only defaults remain read-only
