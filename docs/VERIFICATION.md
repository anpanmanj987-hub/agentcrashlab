# Verification record — 0.1.0 source release

Prepared **2026-10-06**. These are observations from the local build environment,
not claims that a hosted GitHub repository, published package, live LLM or real
business system was tested.

## Executed checks

| Check | Observed result |
|---|---|
| Python environment | Linux, CPython 3.13.5 |
| Full automated suite | **112 tests passed**, no warnings in the final suite run |
| Combined statement/branch coverage | **90%**, measured with pytest-cov |
| Fault behavior | Clean, post-commit loss, pre-commit timeout and permission revocation |
| HTTP | Real loopback sockets; lost responses terminate the connection |
| Concurrency | Stable-key parallel requests commit a single order |
| Integrity | Manifest modification, missing files, symlinks, path traversal, cross-file mismatch and recomputed checks |
| False-green regressions | No-op agents and unreached configured faults do not pass |
| Error classification | HTTP fixture startup error is a harness error (CLI 2), not a policy failure (CLI 1) |
| Packaging | Built a wheel and source distribution with setuptools' PEP 517 backend |
| Installed-wheel smoke | Fresh venv, outside source tree, no index and no runtime dependencies; demo/verify/replay/exit-code checks passed |
| Browser | Chromium 144.0.7559.96, Playwright |
| UI behavior | Four scenario tabs; keyboard arrows/Home; play/pause/reset/seek; SQLite snapshot expansion |
| Responsive layout | Desktop plus 390px and 320px; no horizontal document overflow on tested cases |
| Browser isolation | Zero report network requests and zero uncaught browser errors in the executed checks |
| Hostile report text | Script/image payload displayed literally, with no execution or image request |

Coverage includes in-process CLI tests. Some CLI entry-point subprocess activity
is deliberately not included in coverage measurement. Coverage is not a
correctness or security guarantee.

## Windows re-verification before publication

A second review ran the suite on **Windows 11, CPython 3.13.15** (Japanese locale,
cp932 default encoding). It found three Windows-only defects, all fixed:

| Defect | Fix |
|---|---|
| The HTTP fixture rejected requests (401, 403, 413, ...) without reading the body. Closing a socket with unread input makes Windows send RST, so clients intermittently saw `ConnectionAbortedError` instead of the HTTP error. | Rejections now drain a well-formed body of up to 1 MiB before responding. |
| A test read `report.js` with the locale's default encoding and failed under cp932. | Explicit UTF-8 decoding. |
| A parametrized test used a 70,000-byte body as its test ID, exceeding the Windows environment-variable limit that pytest uses for `PYTEST_CURRENT_TEST`. | Short explicit test IDs. |

After the fixes: **111 passed, 1 skipped** (symlink creation needs privileges on
Windows); the HTTP and hardening modules passed five consecutive runs; the HTTP
demo reproduced its expected pattern; `python -m build` and the installed-wheel
smoke passed. The pinned action commits in `.github/workflows/ci.yml` were checked
against the upstream tags through the GitHub API.

## Reproduce

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
python -m pytest --cov=agentcrashlab --cov-report=term-missing
python -m build
python scripts/smoke_wheel.py
```

The preparation environment could not reach external package registries. Build
verification therefore used the installed setuptools 82.0.1 via
`python scripts/build_dist.py`, which invokes the same PEP 517 backend rather
than the unavailable `build` frontend. The installed-wheel smoke sets
`PIP_NO_INDEX=1` and installs with `--no-deps` in a new virtual environment.

Optional browser verification (not a runtime requirement):

```bash
python -m pip install playwright Pillow
python -m playwright install chromium
python scripts/browser_check.py --capture
```

A system Chromium can be selected with `--browser /path/to/chromium`. Browser
checks load the self-contained report using `page.set_content`, because the
preparation browser blocks `file://` navigation. This executes the report's
actual CSS, JS, CSP and dataset; **it is not a test of opening the file by double
click or of a hosted GitHub Pages deployment**. The screenshot and GIF in
`docs/assets/` were captured from this real executed report, not rendered from
invented performance values. Trace playback reveals recorded events while final
outcome cards stay fixed.

## Deliberately not claimed

- GitHub publication, GitHub Actions execution or PyPI publication.
- Executed macOS or Python 3.11/3.14 runs (Windows with 3.13 was run locally; see
  above). The CI matrix is prepared for these environments.
- Live-model evaluation, framework/MCP conformance or cross-model determinism.
- Production payments/orders, arbitrary endpoint proxying or traffic interception.
- A sandbox for malicious policy code, an external penetration test or independent
  security audit. The code review in preparation was inline, not a separate reviewer.
- Ruff/mypy results: these tools were not available in this offline environment.
- General security, legal compliance, market demand, star counts or incident-prevention guarantees.

## Corrections made during review

The suite was extended to catch an unreachable-fault false pass, a false label
on user-supplied policies named like reference policies, SQLite handle lifetime,
and misclassification of HTTP startup failures. Each behavior regression was
observed failing before the fix. The browser harness initially used a polling
primitive that required `unsafe-eval`; the **test harness** was changed instead
of weakening the report CSP.
