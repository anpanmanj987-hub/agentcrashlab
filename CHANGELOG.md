# Changelog

## 0.1.0 — 2026-10-06

Initial experimental release candidate.

- Four data-only order scenarios; three fault kinds with exact call scheduling.
- Deterministic naive and stable-key reference policies; trusted callable SDK.
- SQLite business-state oracle with atomic per-customer idempotency.
- In-process and authenticated loopback HTTP transports; real socket response loss.
- Eight independent checks, including no-op/false-success protection and fault coverage.
- Immutable JSON/JSONL/SQLite/JUnit/HTML evidence bundles with SHA256 manifests.
- Cross-file evidence verification and recorded-tool-call replay on a fresh backend.
- Offline interactive compare report with keyboard navigation and trace playback.
- English and Japanese README, source runner, packaging, tests and CI workflow.
- Windows fixes found in pre-publication review: HTTP rejections drain the request
  body so clients receive the HTTP error instead of a connection reset; tests no
  longer depend on the locale encoding or oversized test IDs.
- The HTTP fixture skips the reverse DNS lookup in `HTTPServer.server_bind()`,
  which delayed every fixture start by seconds on macOS.

No PyPI publication, genuine-model evaluation or production certification is implied.
