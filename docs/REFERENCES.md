# Implementation references

The code is a new implementation of the project brief: evaluate actual committed
business state when tool responses are ambiguous. No competitor implementation
was copied. Research-based market forecasts are not part of this release's
validated claims.

Primary technical references consulted during preparation:

- Python Packaging User Guide, command-line tools:
  https://packaging.python.org/en/latest/guides/creating-command-line-tools/
- Python standard-library `http.server`, including the explicit warning that it
  is not recommended for production:
  https://docs.python.org/3.13/library/http.server.html
- Python `sqlite3`, transactions and connection management:
  https://docs.python.org/3.13/library/sqlite3.html
- GitHub Actions secure use, especially immutable full-commit references:
  https://docs.github.com/en/actions/reference/security/secure-use

The CI workflow pins official actions to specific commits, verified against
upstream release/commit pages on 2026-10-06:

- checkout v7.0.1: https://github.com/actions/checkout/commit/3d3c42e5aac5ba805825da76410c181273ba90b1
- setup-python v7.0.0: https://github.com/actions/setup-python/commit/5fda3b95a4ea91299a34e894583c3862153e4b97
- upload-artifact v7.0.1: https://github.com/actions/upload-artifact/commit/043fb46d1a93c77aae656e7c1c64a875d1fc6a0a

Pinning does not establish future safety; review dependency-update PRs. GitHub
Actions was configured but not run on an actual hosted repository in this session.
