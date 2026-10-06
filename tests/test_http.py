import json
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler

import pytest


def open_request(request):
    return build_opener(ProxyHandler({})).open(request, timeout=3)


def setup_service(case='clean'):
    from agentcrashlab import load_scenario
    from agentcrashlab.backend import OrderService
    from agentcrashlab.http import LocalOrderServer
    service = OrderService(load_scenario(case))
    return service, LocalOrderServer(service)


@pytest.mark.parametrize('case', ['clean', 'response-loss', 'pre-commit-timeout', 'permission-revoked'])
@pytest.mark.parametrize('agent', ['naive', 'resilient'])
def test_real_http_matches_inprocess(case, agent):
    from agentcrashlab import run_case
    direct = run_case(case, agent=agent)
    http = run_case(case, agent=agent, transport='http')
    assert http.execution_error is None
    assert http.passed == direct.passed
    assert http.orders == direct.orders
    assert http.agent_result == direct.agent_result


def test_response_is_actually_dropped_after_commit():
    from agentcrashlab.errors import ToolTimeout
    service, server = setup_service('response-loss')
    try:
        with server:
            with pytest.raises(ToolTimeout):
                server.client().create_order(intent_id='task-001', customer_id='demo-customer',
                                             sku='demo-keyboard', quantity=1)
            assert len(service.snapshot()) == 1
            assert server.dropped_connections == 1
    finally:
        service.close()


def test_server_start_skips_reverse_dns(monkeypatch):
    import socket

    def no_lookup(*args):
        raise AssertionError('getfqdn can block for seconds on some hosts')
    monkeypatch.setattr(socket, 'getfqdn', no_lookup)
    service, server = setup_service()
    try:
        with server:
            server.client().create_order(intent_id='task-001', customer_id='demo-customer',
                                         sku='demo-keyboard', quantity=1)
    finally:
        service.close()


def test_authentication_required():
    service, server = setup_service()
    try:
        with server:
            for token in ('', 'Bearer incorrect'):
                request = Request(server.url + '/orders', data=b'{}',
                                  headers={'Content-Type': 'application/json', 'Authorization': token})
                with pytest.raises(HTTPError) as caught:
                    open_request(request)
                assert caught.value.code == 401
                caught.value.close()
            assert not service.snapshot()
    finally:
        service.close()


@pytest.mark.parametrize(('body', 'headers', 'status'), [
    (b'{}', {'Origin': 'https://evil.example'}, 403),
    (b'{}', {'Host': 'evil.example'}, 403),
    (b'{}', {'Content-Type': 'text/plain'}, 415),
    (b'not json', {}, 400),
    (b'{"quantity":1,"quantity":2}', {}, 400),
    (b'{}', {}, 400),
    (b'[]', {}, 400),
    (b' ' * 70000, {}, 413),
], ids=['origin', 'host', 'content-type', 'not-json', 'duplicate-key', 'missing-fields',
        'non-object', 'too-large'])
def test_invalid_http_inputs_fail_closed(body, headers, status):
    service, server = setup_service()
    try:
        with server:
            merged = {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + server.token}
            merged.update(headers)
            request = Request(server.url + '/orders', data=body, headers=merged)
            with pytest.raises(HTTPError) as caught:
                open_request(request)
            assert caught.value.code == status
            caught.value.close()
            assert len(service.snapshot()) == 0
    finally:
        service.close()


def test_http_same_key_concurrency():
    service, server = setup_service()
    try:
        with server:
            def call(_):
                return server.client().create_order(intent_id='task-001', customer_id='demo-customer',
                                                    sku='demo-keyboard', quantity=1,
                                                    idempotency_key='one-operation')
            with ThreadPoolExecutor(max_workers=5) as pool:
                results = list(pool.map(call, range(10)))
            assert len({r['order_id'] for r in results}) == 1
            assert len(service.snapshot()) == 1
    finally:
        service.close()


def test_http_token_never_in_run_evidence():
    service, server = setup_service()
    try:
        with server:
            server.client().create_order(intent_id='task-001', customer_id='demo-customer',
                                         sku='demo-keyboard', quantity=1)
            assert server.token not in json.dumps([e.to_dict() for e in service.events])
    finally:
        service.close()


@pytest.mark.parametrize('url', ['https://example.com', 'http://localhost:80',
                                'http://127.0.0.1:80@evil.example', 'http://127.0.0.1:80/path',
                                'http://0.0.0.0:8000'])
def test_client_rejects_nonfixture_urls(url):
    from agentcrashlab.http import HttpOrderClient
    with pytest.raises(ValueError):
        HttpOrderClient(url, 'dummy-token')
