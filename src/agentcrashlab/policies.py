"""Deterministic teaching policies, NOT real LLM benchmarks."""
from __future__ import annotations

import hashlib

from .errors import PermissionDenied, ToolError, ToolTimeout
from .models import AgentResult, OrderTools
from .scenario import Task


def naive(tools: OrderTools, task: Task) -> AgentResult:
    """Intentionally flawed: no idempotency, retries all errors, then claims success.

    The unconditional success is deliberately visible rather than hidden in a
    model prompt. Do not copy this policy into an application.
    """
    for _ in range(3):
        try:
            tools.create_order(**task.order_args())
            break
        except ToolError:
            continue
    return AgentResult('success', 'Your order is confirmed.')


def resilient(tools: OrderTools, task: Task) -> AgentResult:
    """Stable logical-operation key, bounded ambiguous retries, honest stop status.

    Only resilient to the tested fixture faults; not a claim of general safety.
    Keys must survive process restarts in real applications. Never generate a new
    key per retry. A backend must actually support atomic idempotency for this to work.
    """
    key = 'acl-' + hashlib.sha256(
        (task.customer_id + '\0' + task.intent_id).encode('utf-8')).hexdigest()[:32]
    for _ in range(3):
        try:
            order = tools.create_order(**task.order_args(), idempotency_key=key)
            return AgentResult('success', f'Order #{order["order_id"]} is confirmed.')
        except ToolTimeout:
            continue
        except PermissionDenied:
            return AgentResult('blocked', 'Permission was revoked. No success is claimed.')
        except ToolError:
            return AgentResult('failed', 'A non-retryable tool error stopped this task.')
    return AgentResult('uncertain', 'No definitive response. Reconcile before starting a new operation.')


POLICIES = {'naive': naive, 'resilient': resilient}
