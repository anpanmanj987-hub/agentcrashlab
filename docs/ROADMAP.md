# Roadmap

The shipped scope is deliberately narrow. These are **unimplemented proposals**,
not promises of dates, integrations or reliability.

## 0.1 — implemented

- Deterministic order fixture and three numbered fault mechanisms.
- In-process and real loopback HTTP transports.
- Independent outcome checks; no-op and unreachable-fault detection.
- SQLite / JSON / JUnit evidence and recorded-tool-call replay.
- CLI, user-callable seam, static interactive evidence report.

## Next: validate the seam with real users

1. Connect two independently maintained tool-using agents in disposable test
   environments; publish reproducible configuration, not cherry-picked scores.
2. Collect actual failure cases where an outcome check caught a defect that the
   agent's status missed. Resist adding a general agent framework.
3. Investigate asynchronous policy support and outer-process execution budgets.
4. Explore a versioned custom-oracle API for another workflow, such as ticket
   updates or email drafts, without weakening the existing order semantics.
5. Evaluate framework-specific/MCP adapters only with protocol conformance tests.

## Later, only with evidence of demand

- Multi-agent call ordering and controlled scheduling.
- Result reconciliation when all success responses are lost.
- Fixture snapshot adapters for external staging systems, with explicit allowlists.
- Failure minimization, CI trend comparisons and user-managed signing of evidence.

## Not in scope now

Production traffic interception, financial transactions, autonomous remediation,
model training, a marketplace, hidden-knowledge model grading, universal agent
safety claims, live production deployments or an enterprise control plane.
