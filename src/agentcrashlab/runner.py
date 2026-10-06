"""Isolated case lifecycle. User Python callables are trusted, not sandboxed."""
from __future__ import annotations

import tempfile
from collections.abc import Callable
from contextlib import nullcontext
from pathlib import Path

from .backend import OrderService
from .checks import evaluate
from .models import AgentResult, CaseResult, OrderTools
from .policies import POLICIES
from .scenario import Scenario, Task, load_scenario, text

Agent = Callable[[OrderTools, Task], AgentResult]


def run_case(scenario: str | Path | Scenario, *, agent: str | Agent = 'resilient',
             transport: str = 'inprocess', agent_name: str | None = None) -> CaseResult:
    scenario = load_scenario(scenario)
    if transport not in ('inprocess', 'http'):
        raise ValueError('transport must be inprocess or http')
    if isinstance(agent, str):
        if agent not in POLICIES:
            raise ValueError(f'Unknown reference policy: {agent}')
        policy = POLICIES[agent]
        name = agent_name or agent
    elif callable(agent):
        policy = agent
        name = agent_name or getattr(agent, '__name__', 'custom-policy')
    else:
        raise ValueError('agent must be a known policy name or trusted Python callable')
    name = text(name, 'agent_name', 160)
    with tempfile.TemporaryDirectory(prefix='acl-case-') as directory:
        db = Path(directory) / 'orders.sqlite3'
        service = OrderService(scenario, db)
        error = None
        try:
            service.record('run.started', agent=name, transport=transport)
            context = nullcontext(None)
            if transport == 'http':
                from .http import LocalOrderServer
                context = LocalOrderServer(service)
            # Server startup/shutdown failures belong to the harness, not the policy.
            with context as server:
                tools = server.client() if server is not None else service
                try:
                    outcome = policy(tools, scenario.task)
                    if not isinstance(outcome, AgentResult):
                        raise TypeError('Policy must return AgentResult')
                except Exception as exc:
                    # Messages can contain credentials. Store only the exception class.
                    error = type(exc).__name__
                    outcome = AgentResult('failed', 'Policy execution failed; see execution_error type.')
                    service.record('agent.error', exception_type=error)
            service.record('agent.finished', **outcome.to_dict())
            orders = service.snapshot()
            events = tuple(service.events)
        finally:
            service.close()
        database = db.read_bytes()
    return CaseResult(scenario, name, transport, outcome, orders, events,
                      evaluate(scenario, orders, outcome, error, events), database, error,
                      policy_kind='reference' if isinstance(agent, str) else 'custom')
