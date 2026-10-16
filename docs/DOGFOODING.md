# Dogfooding checklist

Use this before and after testing the integration in a real Home Assistant instance.

## Before install/update

- Take a Home Assistant backup.
- Copy or install only `custom_components/sequence` into Home Assistant's `custom_components` directory.
- Keep backup directories outside `custom_components`; Home Assistant treats every directory there as a potential integration.
- Run Home Assistant's configuration check.

## After restart

- Confirm the Sequence config entry is `loaded`.
- Confirm Sequence entity IDs are namespaced as `sensor.sequence_*`.
- Confirm no `Sequence Sequence ...` double-prefix friendly names.
- Confirm unavailable sensors have an upstream data reason where available.
- Check recent Home Assistant logs for `custom_components.sequence` errors.
- If comparing against an existing manual sync, verify matching account values line up before removing old entities.
- If the weekly budget is enabled, confirm the new entities are `sensor.hs2_*` and that `sensor.sequence_*` balance sensors are unchanged.
- Compare `sensor.hs2_*` with the existing household-spend dashboard before any entity rename. The Friday refill should not increase `sensor.hs2_top_ups`.

## Local dashboard idea

A private Home Assistant dashboard is useful during dogfooding, but should not be committed with personal entity names or balances. Suggested sections:

- Summary counts: total, available, unavailable
- Existing manual-sync comparison
- Active non-zero balances
- Unavailable/upstream issue balances
- Zero balances
