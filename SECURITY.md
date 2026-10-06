# Security policy and trust boundaries

AgentCrashLab 0.1.x is an experimental test laboratory, not a sandbox, access-control
product, production proxy or safety certification system.

## What is trusted

Python policy callables execute in the current process with your OS user's privileges.
They can read files, access a network, inspect Python objects, spawn processes or hang.
Do not run untrusted policies on your workstation. Use a separately configured disposable
container/VM with no production credentials when evaluating code you do not trust.
The tool-call limit does not terminate an infinite loop or bound LLM cost.

The direct Python fixture is intentionally inspectable for testing; it is not an
isolation boundary against a policy that actively tries to cheat. For representative
measurements, do not pass the fault schedule, oracle trace or database to the agent.

## HTTP fixture

The server uses Python's standard-library HTTP server for local tests only. It binds
only to an OS-assigned port on 127.0.0.1. Every order request requires a generated
per-instance bearer token; Host must match the fixture, browser Origin/Sec-Fetch
headers are rejected, and there is no CORS enablement or redirect following.
Bodies are limited to 64 KiB and socket read time is bounded. Handler concurrency is
limited. This is defense in depth for a local fixture, not a hardened network service.

The customer_id in fixture requests is a business-test namespace, not a real authenticated
end-user identity. Permission revocation is a synthetic backend state. Do not expose the
fixture publicly, mount a real order database or route real payments into it.

## Evidence and report files

Evidence may contain customer IDs, item names, idempotency keys and policy messages.
Only the shipped fixtures use synthetic data. **There is no general PII detector or
automatic secret scrubber.** Do not publish custom evidence without reviewing it.
Tokens and HTTP Authorization headers are never added to traces. Unexpected policy
exception messages and tracebacks are omitted; only the exception class is recorded.

Reports render strings as text, escape embedded JSON, use inline-content CSP hashes,
and make no network requests. Do not open arbitrary modified HTML supplied by an
untrusted party merely because it is named report.html. A regenerated malicious HTML
file and its new checksum are still malicious; this project does not authenticate authors.

`verify` checks allowed filenames, hashes, event agreement, the SQLite snapshot and
recomputed business assertions. `replay` checks that recorded calls reproduce the effects.
SHA256SUMS is an integrity manifest, not a signed attestation. An attacker controlling
both files and the manifest can forge a self-consistent bundle.

## CI

The supplied workflow uses pull_request (not pull_request_target), read-only repository
permissions, non-persistent checkout credentials and full-SHA action pins. No repository
secrets, production endpoints, auto-publish workflow or privileged container is needed.
Do not introduce privileged credentials to run untrusted pull-request code.

## Reporting a vulnerability

After the repository is published, use its Security tab's private vulnerability reporting
feature if enabled. Otherwise, open a minimal issue requesting a private reporting channel
without exploit details, personal data or credentials. Maintainers should enable private
reporting before announcing the project. No response-time SLA is promised.

## External guidance

See the upstream Python `http.server` documentation and GitHub Actions secure-use guidance
listed in [References](docs/REFERENCES.md). Keep the interpreter, build tools and action pins updated.
