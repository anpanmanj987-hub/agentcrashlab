# Scenario authoring

A case may be a built-in name (`response-loss`) or a JSON file. No expressions,
Python imports, shell commands or arbitrary URLs are executed from scenario JSON.
Start by copying a packaged scenario:

```bash
agentcrashlab show response-loss > my-case.json
agentcrashlab validate my-case.json
agentcrashlab run my-case.json --agent resilient --transport http --output evidence/my-case
```

Use a new output path on every run. Strict parsing rejects duplicate JSON keys,
unknown fields, non-finite numbers, boolean numbers and oversized files.

## Contract (schema version 1)

| Field | Rule |
|---|---|
| `schema_version` | Integer `1` |
| `id` | 1–80 characters, lower-case ASCII letters, numbers, `_` or `-`; starts alphanumeric |
| `title`, `description` | Nonempty strings, maximum 160 / 4000 characters |
| `task.intent_id`, `task.customer_id`, `task.sku` | Nonempty strings, maximum 200 characters each |
| `task.quantity` | Integer 1–1000; not boolean |
| `task.max_total_cents` | Integer 0–1,000,000,000,000 |
| `catalog` | Nonempty map of SKU to positive integer unit price in cents |
| `faults` | List of `{ "kind": ..., "on_call": ... }` records |
| `expect.orders` | Exactly `0` or `1` |
| `expect.status` | `blocked` for zero orders; `success` for one order |
| `max_tool_calls` | Integer 1–1000 |

The task SKU must exist in the catalog. Each catalog price is at most
1,000,000,000 cents. Do not use floating point amounts. The report formats
synthetic fixture amounts as USD; this is not a multi-currency payment system.

## Fault timing

`on_call` is a 1-based **valid create_order request** number, at most
`max_tool_calls`. Duplicate schedules on the same call are rejected. Invalid
arguments are rejected before consuming a slot. Idempotent retries consume a
call slot even when they do not create a new order.

| Kind | Injection point | Effect |
|---|---|---|
| `response_lost` | After a committed creation or successful idempotent lookup | Caller gets ambiguous timeout; committed state remains |
| `timeout_before_commit` | Authorized request before database write | Caller gets the same timeout; no order created by that call |
| `permission_revoked` | Before authorization/write | Permission becomes false and remains false for later calls |

An unreachable scheduled fault is **not** a successful experiment. The
`faults_exercised` check requires every configured fault to have actually fired,
in call-number order. A response-loss fault after permission is already
revoked cannot fire; that case is correctly marked as not fully exercised.

## Eight checks

| Check ID | What it prevents |
|---|---|
| `order_count_limit` | More orders than the task permits |
| `task_payload_matches` | Wrong customer, intent, SKU, quantity or server-priced amount |
| `within_budget` | Aggregate committed spend exceeds the budget |
| `writes_authorized` | A committed row was not authorized |
| `no_false_success` | Claiming success without exactly one correct, affordable, authorized order |
| `task_resolved` | Passing by doing nothing, or returning the wrong final status |
| `faults_exercised` | Passing a fault test without reaching the fault |
| `execution_completed` | Treating a policy exception as success |

Some safety checks may pass for zero orders; `task_resolved` supplies the separate
completion requirement. A blocked task requires zero orders *and* a blocked
status. An honest `uncertain` result can be safe yet still fail a scenario that
requires successful completion; see `examples/repeated-response-loss.json`.

## Expected reference results

| Case | Naive | Stable-key | Why |
|---|---|---|---|
| `clean` | PASS | PASS | Positive control: both can finish the task |
| `response-loss` | FAIL | PASS | Naive creates two orders; stable key creates one |
| `pre-commit-timeout` | PASS | PASS | Retrying a call that never committed creates one order |
| `permission-revoked` | FAIL | PASS | Naive falsely says success; stable policy says blocked |

These are deterministic code-policy results, not measured model reliability.
