# Contributing

Thanks for helping make this integration safer and more useful.

## Principles

- Read-only by default.
- No money movement without explicit opt-in, allowlists, confirmations, caps, and tests.
- Never log or expose API tokens.
- Keep diagnostics privacy-first.
- Keep personal dogfood setup out of the public repo.

## Local checks

```bash
python3 -m unittest discover -s tests
python3 -m compileall custom_components tests
python3 -m json.tool custom_components/sequence/manifest.json >/dev/null
python3 -m json.tool custom_components/sequence/strings.json >/dev/null
python3 -m json.tool custom_components/sequence/translations/en.json >/dev/null
python3 -m json.tool hacs.json >/dev/null
```
