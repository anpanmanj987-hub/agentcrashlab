"""Regression tests found during the pre-release review."""
import socket

import pytest


def test_unreached_fault_is_not_a_passing_fault_test():
    from agentcrashlab import Scenario, load_scenario, run_case
    data = load_scenario('response-loss').to_dict()
    data['faults'][0]['on_call'] = 99
    result = run_case(Scenario.from_dict(data), agent='resilient')
    assert not result.passed
    check = next(c for c in result.checks if c.id == 'faults_exercised')
    assert not check.passed
    assert check.actual == []


def test_all_timeouts_leave_explicitly_uncertain_outcome():
    from agentcrashlab import Scenario, load_scenario, run_case
    data = load_scenario('response-loss').to_dict()
    data['faults'] = [{'kind': 'response_lost', 'on_call': i} for i in (1, 2, 3)]
    result = run_case(Scenario.from_dict(data), agent='resilient')
    assert result.agent_result.status == 'uncertain'
    assert len(result.orders) == 1
    assert not result.passed


def test_fault_coverage_survives_bundle_replay(tmp_path):
    from agentcrashlab import Scenario, load_scenario, run_case
    from agentcrashlab.bundles import write_bundle, replay_bundle
    data = load_scenario('response-loss').to_dict()
    data['faults'][0]['on_call'] = 99
    case = run_case(Scenario.from_dict(data))
    write_bundle(case, tmp_path / 'original')
    replay = replay_bundle(tmp_path / 'original')
    assert not replay.passed
    assert replay.checks == case.checks


def test_manifest_is_required(tmp_path):
    from agentcrashlab.bundles import verify_bundle
    with pytest.raises(ValueError):
        verify_bundle(tmp_path)


def test_bundle_database_connection_is_closed(tmp_path):
    from agentcrashlab import run_case
    from agentcrashlab.bundles import write_bundle, verify_bundle
    path = tmp_path / 'run'
    write_bundle(run_case('clean'), path)
    verify_bundle(path)
    # On Windows this fails if the sqlite3 connection still owns the file handle.
    (path / 'orders.sqlite3').unlink()
    assert not (path / 'orders.sqlite3').exists()


def test_nonascii_manifest_rejected_as_value_error(tmp_path):
    from agentcrashlab.bundles import verify_bundle
    (tmp_path / 'SHA256SUMS').write_bytes(b'\xff')
    with pytest.raises(ValueError):
        verify_bundle(tmp_path)


def test_max_calls_does_not_silently_change_state():
    from agentcrashlab import Scenario, load_scenario
    from agentcrashlab.backend import OrderService
    from agentcrashlab.errors import CallLimitExceeded
    raw = load_scenario('clean').to_dict()
    raw['max_tool_calls'] = 1
    scenario = Scenario.from_dict(raw)
    service = OrderService(scenario)
    try:
        service.create_order(**scenario.task.order_args())
        for _ in range(3):
            with pytest.raises(CallLimitExceeded):
                service.create_order(**scenario.task.order_args())
        assert len(service.snapshot()) == 1
        assert sum(e.kind == 'tool.limit_reached' for e in service.events) == 1
    finally:
        service.close()


def test_oversized_description_is_rejected():
    from agentcrashlab import Scenario, load_scenario
    raw = load_scenario('clean').to_dict()
    raw['description'] = 'x' * 4001
    with pytest.raises(ValueError):
        Scenario.from_dict(raw)


def test_duplicate_content_length_is_rejected():
    from agentcrashlab import load_scenario
    from agentcrashlab.backend import OrderService
    from agentcrashlab.http import LocalOrderServer
    service = OrderService(load_scenario('clean'))
    try:
        with LocalOrderServer(service) as server:
            port = int(server.url.rsplit(':', 1)[1])
            with socket.create_connection(('127.0.0.1', port), timeout=3) as sock:
                sock.sendall((f'POST /orders HTTP/1.0\r\nHost: 127.0.0.1:{port}\r\n'
                              f'Authorization: Bearer {server.token}\r\nContent-Type: application/json\r\n'
                              'Content-Length: 2\r\nContent-Length: 2\r\n\r\n{}').encode())
                assert b'411' in sock.recv(4096)
            assert not service.snapshot()
    finally:
        service.close()


def test_header_token_is_never_returned_to_bad_client():
    from agentcrashlab import load_scenario
    from agentcrashlab.backend import OrderService
    from agentcrashlab.http import LocalOrderServer, HttpOrderClient
    from agentcrashlab.errors import ProtocolError
    service = OrderService(load_scenario('clean'))
    try:
        with LocalOrderServer(service) as server:
            with pytest.raises(ProtocolError) as caught:
                HttpOrderClient(server.url, 'wrong').create_order(**service.scenario.task.order_args())
            assert server.token not in str(caught.value)
    finally:
        service.close()


@pytest.mark.parametrize('timeout', [True, 0, -1, float('inf'), float('nan'), 31])
def test_invalid_client_timeouts(timeout):
    from agentcrashlab.http import HttpOrderClient
    with pytest.raises(ValueError):
        HttpOrderClient('http://127.0.0.1:12345', 'token', timeout=timeout)


def test_report_does_not_claim_arbitrary_keys_are_stable():
    from importlib.resources import files
    script = files('agentcrashlab').joinpath('assets/report.js').read_text(encoding='utf-8')
    assert "? ' · stable key'" not in script


def test_custom_case_with_wrong_backend_payload_still_has_valid_json(tmp_path):
    from agentcrashlab import run_case, AgentResult
    from agentcrashlab.bundles import write_bundle, verify_bundle
    def custom(tools, task):
        tools.create_order(**(task.order_args() | {'customer_id': 'someone-else'}))
        return AgentResult('success', 'complete')
    result = run_case('clean', agent=custom)
    assert not result.passed
    write_bundle(result, tmp_path / 'out')
    assert verify_bundle(tmp_path / 'out')['passed'] is False
