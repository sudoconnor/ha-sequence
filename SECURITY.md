# Security policy

## Supported versions

This is an early pre-release integration. Until the first public release, security fixes land on `main`.

## Sensitive data

The integration stores the Sequence API token in Home Assistant config-entry storage, which is the normal pattern for UI-configured integrations. Treat Home Assistant backups as sensitive. Use the most restrictive/read-only Sequence API token available.

Diagnostics should not include raw tokens, account IDs, account names, balances, or transaction-like details.

## Reporting a vulnerability

Open a private security advisory or contact the maintainer privately before filing a public issue. Do not include API tokens, account IDs, balances, logs with secrets, or Home Assistant backup files in public reports.
