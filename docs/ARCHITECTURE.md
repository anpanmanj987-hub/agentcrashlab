# Architecture and trust boundaries

AgentCrashLab 0.1 is a test fixture for **one order workflow**, not a universal
agent platform. The task's business outcome is judged independently of the
agent's declared status.

```text
Scenario JSON ──────┬─────────────────────────────────────────┐
                   ▼                                         ▼
            trusted policy ── OrderTools ── fault schedule ── SQLite
                   │            │                              │
                   │       in-process or                       │
                   │       loopback HTTP                       │
                   ▼                                           ▼
              AgentResult                              committed snapshot
                   └────────────────┬──────────────────────────┘
                                    ▼
                       eight independent checks
                                    ▼
                   evidence bundle / JUnit / offline HTML
```

## Modules

| Module | Responsibility |
|---|---|
| `scenario.py` | Strict declarative JSON validation and packaged cases |
| `models.py` | Public task, outcome, event, check and result contracts |
| `backend.py` | Transactional order store, fault scheduling, structured events |
| `http.py` | Real loopback HTTP fixture and narrow authenticated client |
| `policies.py` | Intentionally flawed and stable-key reference policies |
| `runner.py` | Fresh per-case lifecycle; trusted policy execution |
| `checks.py` | Independent business outcome and fault-coverage checks |
| `bundles.py` | New-directory evidence writes, consistency checks, tool replay |
| `reports.py`, `assets/` | JUnit and self-contained evidence viewer |
| `cli.py` | Human commands and machine-readable exit semantics |

## Commit, then lose the response

The `response_lost` fault runs after the SQLite write commits. The HTTP transport
then closes the socket without sending a response. The agent receives the same
`ToolTimeout` as a timeout before commit. There is no secret `committed=True` flag
in the exception: the policy must treat the outcome as ambiguous.

The naive policy retries without an idempotency key. The stable-key reference
policy retries with one key derived from the task's customer and intent. SQLite
uniqueness and a transaction ensure a retry with the same customer, key and
payload returns the existing order rather than creating another. Reusing the key
with a different payload raises `IdempotencyConflict`.

This is not a general exactly-once delivery guarantee. The example requires
backend idempotency support. `customer_id` is a fixture namespace, not a
production authentication claim. No external orders, payments or messages occur.

## Isolation and concurrency

Each run creates a new temporary SQLite database and closes it before exporting
its bytes. An `RLock` serializes calls within the service, including the numbered
fault schedule and SQLite transaction. Concurrent requests with the same key are
tested; arbitrary concurrent policy scheduling is not promised deterministic.

The HTTP server binds `127.0.0.1` on an ephemeral port and uses a random bearer
token. Requests have bounded body size, read time and concurrent handler count.
Host and browser-origin checks reduce accidental local exposure. The client does
not accept arbitrary remote URLs, environment proxies or redirects.

**A trusted Python policy runs in-process.** A tool-call budget limits accepted
fixture calls, not CPU time or a policy's own network access. This is not a Docker
sandbox, an egress firewall or a safe way to execute unknown agent code. Keep
real credentials and production endpoints out of experiments.

## Evidence and replay

`write_bundle()` writes to a new directory and never overwrites existing output.
The manifest is last; interruption may leave an incomplete directory that must
not be treated as valid evidence. The bundle contains structured events, run
metadata, scenario, the actual SQLite snapshot, JUnit, HTML and SHA-256 checksums.

`verify_bundle()` checks hashes, file names/limits and cross-file consistency,
then recomputes the business verdict. It does not authenticate the author: a
person controlling the entire bundle can forge a self-consistent replacement.
Do not treat an untrusted HTML file as safe merely because its hash matches its
own manifest. The generated viewer uses escaped data, text-only DOM rendering,
no remote assets and a restrictive content security policy.

`replay_bundle()` reissues recorded valid tool calls against a fresh in-process
fixture. It requires equivalent committed state and recorded effect events. The
saved agent declaration is reused, not regenerated. It neither invokes nor
reproduces an LLM's private reasoning. Policy exceptions cannot be replayed.

Reports contain final results throughout trace playback: the slider reveals
recorded events; it does not recompute intermediate verdicts or rerun a model.
