"""Public types and deterministic serializable run records."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from ._version import __version__
from .scenario import Scenario, text


class OrderTools(Protocol):
    def create_order(self, *, intent_id: str, customer_id: str, sku: str,
                     quantity: int, idempotency_key: str | None = None) -> dict[str, Any]: ...


@dataclass(frozen=True)
class AgentResult:
    status: str
    message: str = ''

    def __post_init__(self) -> None:
        if self.status not in ('success', 'blocked', 'uncertain', 'failed'):
            raise ValueError('Agent status must be success, blocked, uncertain or failed')
        if not isinstance(self.message, str) or len(self.message) > 4000:
            raise ValueError('Agent message must be a string of at most 4000 characters')
        if self.message:
            text(self.message, 'agent message', 4000)

    def to_dict(self) -> dict[str, str]:
        return {'status': self.status, 'message': self.message}


@dataclass(frozen=True)
class Event:
    seq: int
    kind: str
    data: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {'seq': self.seq, 'kind': self.kind, 'data': self.data}


@dataclass(frozen=True)
class Check:
    id: str
    title: str
    passed: bool
    expected: Any
    actual: Any
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {'id': self.id, 'title': self.title, 'passed': self.passed,
                'expected': self.expected, 'actual': self.actual, 'detail': self.detail}


@dataclass(frozen=True)
class CaseResult:
    scenario: Scenario
    agent_name: str
    transport: str
    agent_result: AgentResult
    orders: tuple[dict[str, Any], ...]
    events: tuple[Event, ...]
    checks: tuple[Check, ...]
    database: bytes = field(repr=False, compare=False)
    execution_error: str | None = None
    mode: str = 'live-policy'
    replay_of: str | None = None
    policy_kind: str = 'reference'

    @property
    def passed(self) -> bool:
        return bool(self.checks) and all(c.passed for c in self.checks) and self.execution_error is None

    def to_dict(self) -> dict[str, Any]:
        return {'schema_version': 1, 'agentcrashlab_version': __version__,
                'scenario': self.scenario.to_dict(), 'agent_name': self.agent_name,
                'transport': self.transport, 'mode': self.mode, 'replay_of': self.replay_of,
                'policy_kind': self.policy_kind,
                'agent_result': self.agent_result.to_dict(), 'execution_error': self.execution_error,
                'passed': self.passed, 'orders': list(self.orders),
                'events': [e.to_dict() for e in self.events],
                'checks': [c.to_dict() for c in self.checks]}
