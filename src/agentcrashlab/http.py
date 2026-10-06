"""Authenticated loopback-only HTTP fixture; not a production proxy or sandbox.

A response-loss fault really closes the TCP connection without returning HTTP.
No external URL, shell command, model credential or proxy configuration is used.
"""
from __future__ import annotations

import hmac
import http.client
import json
import math
import re
import secrets
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .backend import OrderService
from .errors import (CallLimitExceeded, IdempotencyConflict, InvalidRequest,
                     PermissionDenied, ProtocolError, ToolError, ToolTimeout)
from .scenario import object_fields, parse_json

MAX_BODY = 65536
# Rejected bodies up to this size are read and discarded before closing; see discard_body.
MAX_DRAIN = 1_048_576


class _FixtureServer(ThreadingHTTPServer):
    daemon_threads = False
    block_on_close = True
    request_queue_size = 32
    allow_reuse_address = False

    def __init__(self, handler: type[BaseHTTPRequestHandler]) -> None:
        self._slots = threading.BoundedSemaphore(32)
        super().__init__(('127.0.0.1', 0), handler)

    def process_request(self, request: socket.socket, client_address: tuple[str, int]) -> None:
        if not self._slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._slots.release()
            raise

    def process_request_thread(self, request: socket.socket,
                               client_address: tuple[str, int]) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()

    def get_request(self) -> tuple[socket.socket, Any]:
        request, address = super().get_request()
        request.settimeout(2.0)
        return request, address

    def handle_error(self, request: socket.socket, client_address: Any) -> None:
        # Never emit request bodies, auth headers or arbitrary exception messages.
        return


class LocalOrderServer:
    def __init__(self, service: OrderService) -> None:
        self.service = service
        self.token = secrets.token_urlsafe(32)
        self.dropped_connections = 0
        self._counter_lock = threading.Lock()
        self._server: _FixtureServer | None = None
        self._thread: threading.Thread | None = None
        self.url = ''

    def __enter__(self) -> LocalOrderServer:
        if self._server is not None:
            raise RuntimeError('Server context is already active')
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.0'
            server_version = 'AgentCrashLab-fixture'
            sys_version = ''
            body_consumed = False

            def log_message(self, format: str, *args: Any) -> None:
                return

            def respond(self, status: int, payload: dict[str, Any]) -> None:
                raw = json.dumps(payload, allow_nan=False, ensure_ascii=True).encode('utf-8')
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw)))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('Connection', 'close')
                self.end_headers()
                self.close_connection = True
                try:
                    self.wfile.write(raw)
                except OSError:
                    pass

            def discard_body(self) -> None:
                # Closing a socket with unread input makes Windows send RST, so the
                # client sees a connection abort instead of this HTTP error. Drain
                # a bounded, well-formed body first; larger bodies are not read.
                if self.body_consumed:
                    return
                self.body_consumed = True
                lengths = self.headers.get_all('Content-Length', [])
                if len(lengths) != 1 or not re.fullmatch(r'[0-9]{1,10}', lengths[0]):
                    return
                remaining = int(lengths[0])
                if remaining > MAX_DRAIN:
                    return
                try:
                    while remaining > 0:
                        chunk = self.rfile.read(min(remaining, MAX_BODY))
                        if not chunk:
                            return
                        remaining -= len(chunk)
                except OSError:
                    pass

            def reject(self, status: int, code: str) -> None:
                self.discard_body()
                self.respond(status, {'error': code})

            def do_GET(self) -> None:
                self.reject(404, 'not_found')

            def do_OPTIONS(self) -> None:
                self.reject(403, 'browser_access_disabled')

            def do_POST(self) -> None:
                if self.headers.get_all('Origin') or self.headers.get_all('Sec-Fetch-Site'):
                    self.reject(403, 'browser_access_disabled')
                    return
                if self.headers.get_all('Host') != [owner.url.removeprefix('http://')]:
                    self.reject(403, 'invalid_host')
                    return
                auth = self.headers.get_all('Authorization', [])
                if len(auth) != 1 or not hmac.compare_digest(
                        auth[0].encode('utf-8'), ('Bearer ' + owner.token).encode('utf-8')):
                    self.reject(401, 'unauthorized')
                    return
                if self.path != '/orders':
                    self.reject(404, 'not_found')
                    return
                if self.headers.get('Transfer-Encoding'):
                    self.reject(400, 'transfer_encoding_not_supported')
                    return
                if self.headers.get('Content-Type', '').split(';')[0].strip() != 'application/json':
                    self.reject(415, 'json_required')
                    return
                lengths = self.headers.get_all('Content-Length', [])
                if len(lengths) != 1 or not re.fullmatch(r'[0-9]{1,10}', lengths[0]):
                    self.reject(411, 'content_length_required')
                    return
                size = int(lengths[0])
                if size > MAX_BODY:
                    self.reject(413, 'request_too_large')
                    return
                self.body_consumed = True
                try:
                    raw = self.rfile.read(size)
                except (OSError, TimeoutError):
                    self.reject(408, 'request_timeout')
                    return
                if len(raw) != size:
                    self.reject(400, 'incomplete_body')
                    return
                try:
                    data = object_fields(parse_json(raw),
                                         {'intent_id', 'customer_id', 'sku', 'quantity'},
                                         {'idempotency_key'}, 'order')
                    result = owner.service.create_order(**data)
                except (ValueError, InvalidRequest):
                    self.reject(400, 'invalid_request')
                    return
                except ToolTimeout:
                    with owner._counter_lock:
                        owner.dropped_connections += 1
                    self.close_connection = True
                    try:
                        self.connection.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
                    self.connection.close()
                    return
                except PermissionDenied:
                    self.reject(403, 'permission_denied')
                    return
                except IdempotencyConflict:
                    self.reject(409, 'idempotency_conflict')
                    return
                except CallLimitExceeded:
                    self.reject(429, 'call_limit')
                    return
                except Exception:
                    self.reject(500, 'fixture_error')
                    return
                self.respond(200, result)

        self._server = _FixtureServer(Handler)
        self.url = f'http://127.0.0.1:{self._server.server_address[1]}'
        self._thread = threading.Thread(target=self._server.serve_forever,
                                        kwargs={'poll_interval': 0.02}, daemon=True,
                                        name='agentcrashlab-local-fixture')
        self._thread.start()
        return self

    def client(self) -> HttpOrderClient:
        if self._server is None:
            raise RuntimeError('Enter the LocalOrderServer context before creating a client')
        return HttpOrderClient(self.url, self.token)

    def __exit__(self, *args: Any) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            if self._thread:
                self._thread.join(timeout=3)
            self._server = None


class HttpOrderClient:
    def __init__(self, url: str, token: str, *, timeout: float = 3.0) -> None:
        match = re.fullmatch(r'http://127\.0\.0\.1:([0-9]{1,5})', url)
        if match is None or not 1 <= int(match[1]) <= 65535:
            raise ValueError('Only http://127.0.0.1:<port> fixture URLs are accepted')
        if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', token):
            raise ValueError('Invalid fixture token')
        if type(timeout) not in (float, int) or not math.isfinite(timeout) or not 0 < timeout <= 30:
            raise ValueError('timeout must be finite and between 0 and 30 seconds')
        self._port = int(match[1])
        self._token = token
        self._timeout = timeout

    def create_order(self, *, intent_id: str, customer_id: str, sku: str, quantity: int,
                     idempotency_key: str | None = None) -> dict[str, Any]:
        try:
            raw = json.dumps({'intent_id': intent_id, 'customer_id': customer_id, 'sku': sku,
                              'quantity': quantity, 'idempotency_key': idempotency_key},
                             allow_nan=False).encode('utf-8')
        except (ValueError, TypeError) as exc:
            raise InvalidRequest('Order arguments must be finite JSON data') from exc
        if len(raw) > MAX_BODY:
            raise InvalidRequest('Order request exceeds 64 KiB')
        # http.client neither uses environment proxy settings nor follows redirects.
        connection = http.client.HTTPConnection('127.0.0.1', self._port, timeout=self._timeout)
        try:
            connection.request('POST', '/orders', body=raw,
                               headers={'Content-Type': 'application/json',
                                        'Authorization': 'Bearer ' + self._token})
            response = connection.getresponse()
            body = response.read(MAX_BODY + 1)
            if len(body) > MAX_BODY:
                raise ProtocolError('Fixture response exceeds limit')
            try:
                data = parse_json(body)
            except ValueError as exc:
                raise ProtocolError('Fixture returned invalid JSON') from exc
            if not isinstance(data, dict):
                raise ProtocolError('Fixture returned a non-object response')
            if response.status == 200:
                if type(data.get('order_id')) is not int:
                    raise ProtocolError('Fixture response has no valid order ID')
                return data
            errors: dict[str, type[ToolError]] = {
                'permission_denied': PermissionDenied,
                'idempotency_conflict': IdempotencyConflict,
                'call_limit': CallLimitExceeded,
            }
            code = data.get('error')
            if isinstance(code, str) and code in errors:
                raise errors[code]()
            if code == 'invalid_request':
                raise InvalidRequest('Fixture rejected order arguments')
            raise ProtocolError(f'Fixture request rejected with HTTP {response.status}')
        except (http.client.RemoteDisconnected, http.client.IncompleteRead,
                ConnectionError, TimeoutError, OSError) as exc:
            raise ToolTimeout() from exc
        finally:
            connection.close()
