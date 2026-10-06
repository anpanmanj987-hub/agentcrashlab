# Contributing

A small, reproducible failure case is more valuable than a large untestable platform.
Start with a synthetic scenario, a business invariant and an agent behavior that breaks it.

## Setup and checks

```bash
python -m venv .venv
# Activate .venv using your shell's normal command.
python -m pip install -e ".[dev]"
python -m pytest -q
python -m pytest --cov=agentcrashlab --cov-report=term-missing
python -m build
```

No model credentials are needed for the test suite. Use only synthetic inputs. Do not
add real incident traces, prompts, tokens or customer data to issues, tests or screenshots.

## Pull requests

Write a failing regression test first and include the command that demonstrates the
failure. Preserve distinct agent observations and oracle-side effects. A timeout must
not disclose whether a write committed. Keep amounts as integers and idempotency atomic.

New scenarios need strict validation, expected outcomes for both reference policies,
and tests that their scheduled fault is actually exercised. New transports need
behavioral parity tests, bounded input, resource cleanup and explicit trust boundaries.

Do not add fabricated benchmark numbers, star targets presented as forecasts, dummy
company logos or a claim of general safety. If using a real LLM, document model/version,
prompt/configuration, repeated trials, failures, uncertainty and all relevant cost assumptions.

The zero-runtime-dependency core is deliberate. Propose optional integrations before
adding heavy frameworks. See [the roadmap](docs/ROADMAP.md).

## Report changes

Keep report assets self-contained and keyboard usable. Render data with textContent,
not innerHTML. Do not add analytics, external fonts or CDN scripts. Run
`scripts/browser_check.py` in a Playwright/Chromium-equipped development environment.
Browser tooling is not a runtime requirement.

## License

By submitting a contribution you agree that your contribution is licensed under this
repository's MIT license. Only contribute material you are entitled to share.
