"""Behavioral contracts: deliberately bad policies must produce red test reports."""
from concurrent.futures import ThreadPoolExecutor

import pytest


def core():
    import agentcrashlab as acl
    return acl


@pytest.mark.parametrize(
    ('case', 'policy', 'passed', 'orders'),
    [('clean', 'naive', True, 1), ('clean', 'resilient', True, 1),
     ('response-loss', 'naive', False, 2), ('response-loss', 'resilient', True, 1),
     ('pre-commit-timeout', 'naive', True, 1),
     ('pre-commit-timeout', 'resilient', True, 1),
     ('permission-revoked', 'naive', False, 0),
     ('permission-revoked', 'resilient', True, 0)],
)
def test_reference_policies(case, policy, passed, orders):
    result = core().run_case(case, agent=policy)
    assert result.passed is passed
    assert len(result.orders) == orders
    assert len(result.checks) >= 6
    assert result.events
    assert result.database.startswith(b'SQLite format 3')


def test_success_claim_does_not_prove_correctness():
    result = core().run_case('response-loss', agent='naive')
    assert result.agent_result.status == 'success'
    assert not result.passed
    assert not next(c for c in result.checks if c.id == 'no_false_success').passed


def test_noop_and_lying_agents_fail():
    acl = core()
    for status in ('success', 'blocked', 'failed', 'uncertain'):
        result = acl.run_case('clean', agent=lambda tools, task: acl.AgentResult(status))
        assert not result.passed
        assert len(result.orders) == 0


def test_exception_is_failed_not_green_and_does_not_leak_message():
    def broken(tools, task):
        raise RuntimeError('secret-do-not-log-this')
    result = core().run_case('clean', agent=broken)
    assert not result.passed
    assert result.execution_error == 'RuntimeError'
    assert 'secret-do-not-log-this' not in str(result.to_dict())


def test_wrong_return_type_fails():
    result = core().run_case('clean', agent=lambda t, task: 'success')
    assert not result.passed
    assert result.execution_error == 'TypeError'


def test_stable_scenario_run_repeats_exactly():
    a = core().run_case('response-loss', agent='resilient')
    b = core().run_case('response-loss', agent='resilient')
    assert a.to_dict() == b.to_dict()


def test_invalid_agent_and_transport_rejected():
    with pytest.raises(ValueError):
        core().run_case('clean', agent='imaginary')
    with pytest.raises(ValueError):
        core().run_case('clean', transport='production')


def test_payload_change_with_same_key_conflicts():
    from agentcrashlab.backend import OrderService
    from agentcrashlab.errors import IdempotencyConflict
    service = OrderService(core().load_scenario('clean'))
    args = dict(intent_id='task-001', customer_id='demo-customer', sku='demo-keyboard', quantity=1)
    try:
        first = service.create_order(**args, idempotency_key='key-1')
        second = service.create_order(**args, idempotency_key='key-1')
        assert first == second
        with pytest.raises(IdempotencyConflict):
            service.create_order(**(args | {'quantity': 2}), idempotency_key='key-1')
        assert len(service.snapshot()) == 1
    finally:
        service.close()


def test_concurrent_same_key_commits_once():
    from agentcrashlab.backend import OrderService
    service = OrderService(core().load_scenario('clean'))
    args = dict(intent_id='task-001', customer_id='demo-customer', sku='demo-keyboard', quantity=1,
                idempotency_key='concurrent-1')
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: service.create_order(**args), range(20)))
        assert all(r == results[0] for r in results)
        assert len(service.snapshot()) == 1
    finally:
        service.close()


def test_same_key_is_scoped_per_customer():
    from agentcrashlab.backend import OrderService
    service = OrderService(core().load_scenario('clean'))
    try:
        for customer in ('a', 'b'):
            service.create_order(intent_id='task-001', customer_id=customer, sku='demo-keyboard',
                                 quantity=1, idempotency_key='same-key')
        assert len(service.snapshot()) == 2
    finally:
        service.close()


def test_pre_and_post_commit_timeout_have_same_agent_surface():
    from agentcrashlab.backend import OrderService
    from agentcrashlab.errors import ToolTimeout
    seen = []
    counts = []
    for name in ('pre-commit-timeout', 'response-loss'):
        service = OrderService(core().load_scenario(name))
        try:
            with pytest.raises(ToolTimeout) as caught:
                service.create_order(intent_id='task-001', customer_id='demo-customer',
                                     sku='demo-keyboard', quantity=1)
            seen.append((type(caught.value), str(caught.value)))
            counts.append(len(service.snapshot()))
        finally:
            service.close()
    assert seen[0] == seen[1]
    assert counts == [0, 1]


def test_wrong_payload_and_budget_are_caught_independently():
    acl = core()
    def bad(tools, task):
        tools.create_order(intent_id=task.intent_id, customer_id=task.customer_id,
                           sku=task.sku, quantity=2)
        return acl.AgentResult('success')
    result = acl.run_case('clean', agent=bad)
    checks = {c.id: c.passed for c in result.checks}
    assert checks['order_count_limit']
    assert not checks['task_payload_matches']
    assert not checks['within_budget']
    assert not checks['no_false_success']


@pytest.mark.parametrize('quantity', [True, 0, -1, 1.5, '1', 1001])
def test_backend_rejects_invalid_quantities(quantity):
    from agentcrashlab.backend import OrderService
    from agentcrashlab.errors import InvalidRequest
    service = OrderService(core().load_scenario('clean'))
    try:
        with pytest.raises(InvalidRequest):
            service.create_order(intent_id='task-001', customer_id='demo-customer',
                                 sku='demo-keyboard', quantity=quantity)
        assert len(service.snapshot()) == 0
    finally:
        service.close()
