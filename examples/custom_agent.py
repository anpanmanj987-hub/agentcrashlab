"""Executable custom-policy example. No LLM or production service is invoked."""
from __future__ import annotations

import argparse
from pathlib import Path

from agentcrashlab import AgentResult, OrderTools, Task, run_case
from agentcrashlab.bundles import write_bundle
from agentcrashlab.errors import PermissionDenied, ToolError, ToolTimeout


def purchase(tools: OrderTools, task: Task) -> AgentResult:
    stable_key = f'{task.customer_id}:{task.intent_id}'
    for _ in range(3):
        try:
            response = tools.create_order(**task.order_args(), idempotency_key=stable_key)
            return AgentResult('success', f'Confirmed order #{response["order_id"]}.')
        except ToolTimeout:
            continue
        except PermissionDenied:
            return AgentResult('blocked', 'Order permission was revoked.')
        except ToolError:
            return AgentResult('failed', 'Non-retryable tool failure.')
    return AgentResult('uncertain', 'No definitive response; manual reconciliation is required.')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=Path('artifacts/custom-agent'))
    args = parser.parse_args()
    result = run_case('response-loss', agent=purchase, transport='http')
    write_bundle(result, args.output)
    print(f'passed={result.passed}; committed_orders={len(result.orders)}')
    return 0 if result.passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
