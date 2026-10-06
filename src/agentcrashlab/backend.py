"""SQLite business-state oracle with atomic idempotency and deterministic faults."""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from .errors import (CallLimitExceeded, IdempotencyConflict, InvalidRequest,
                     PermissionDenied, ToolError, ToolTimeout)
from .models import Event
from .scenario import Scenario, integer, text

SCHEMA = '''
CREATE TABLE orders (
    order_id INTEGER PRIMARY KEY AUTOINCREMENT,
    intent_id TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    sku TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK(quantity > 0),
    unit_price_cents INTEGER NOT NULL CHECK(unit_price_cents > 0),
    total_cents INTEGER NOT NULL,
    idempotency_key TEXT,
    authorized INTEGER NOT NULL CHECK(authorized IN (0, 1)),
    request_json TEXT NOT NULL,
    UNIQUE(customer_id, idempotency_key)
);
'''


class OrderService:
    """Local fixture only. Its catalog and authorization state belong to the oracle.

    The customer field is a fixture namespace, not a real authentication identity.
    A single RLock covers call ordering, fault injection and database transactions.
    """

    def __init__(self, scenario: Scenario, database: str | Path = ':memory:') -> None:
        self.scenario = scenario
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(database), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()
        self._calls = 0
        self._authorized = True
        self._limit_reported = False
        self.events: list[Event] = []
        self._faults = {f.on_call: f.kind for f in scenario.faults}

    def record(self, kind: str, **data: Any) -> None:
        with self._lock:
            self.events.append(Event(len(self.events) + 1, kind, data))

    @staticmethod
    def _public_row(row: sqlite3.Row) -> dict[str, Any]:
        return {k: (bool(row[k]) if k == 'authorized' else row[k])
                for k in row.keys() if k != 'request_json'}

    def snapshot(self) -> tuple[dict[str, Any], ...]:
        with self._lock:
            return tuple(self._public_row(r) for r in self._conn.execute(
                'SELECT * FROM orders ORDER BY order_id'))

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def create_order(self, *, intent_id: str, customer_id: str, sku: str, quantity: int,
                     idempotency_key: str | None = None) -> dict[str, Any]:
        # Validate before recording so objects, infinities and arbitrary types cannot
        # enter the trace. Rejected malformed calls do not consume a fault slot.
        try:
            text(intent_id, 'intent_id')
            text(customer_id, 'customer_id')
            text(sku, 'sku')
            integer(quantity, 'quantity', 1, 1000)
            if idempotency_key is not None:
                text(idempotency_key, 'idempotency_key')
        except ValueError as exc:
            raise InvalidRequest(str(exc)) from exc
        if sku not in self.scenario.catalog:
            raise InvalidRequest('SKU is not present in the fixture catalog')
        arguments = {'intent_id': intent_id, 'customer_id': customer_id, 'sku': sku,
                     'quantity': quantity, 'idempotency_key': idempotency_key}
        with self._lock:
            if self._calls >= self.scenario.max_tool_calls:
                if not self._limit_reported:
                    self.record('tool.limit_reached', limit=self.scenario.max_tool_calls)
                    self._limit_reported = True
                raise CallLimitExceeded()
            self._calls += 1
            self.record('tool.call', call=self._calls, tool='create_order', arguments=arguments)
            fault = self._faults.get(self._calls)
            if fault == 'permission_revoked':
                self._authorized = False
                self.record('fault.injected', fault_kind=fault, call=self._calls)
            try:
                if not self._authorized:
                    raise PermissionDenied()
                if fault == 'timeout_before_commit':
                    self.record('fault.injected', fault_kind=fault, call=self._calls)
                    raise ToolTimeout()
                result = self._commit(arguments)
                if fault == 'response_lost':
                    self.record('fault.injected', fault_kind=fault, call=self._calls)
                    self.record('transport.response_lost', call=self._calls,
                                order_id=result['order_id'])
                    raise ToolTimeout()
                self.record('tool.response', call=self._calls, order_id=result['order_id'])
                return result
            except ToolError as exc:
                self.record('tool.error', call=self._calls, code=exc.code)
                raise

    def _commit(self, arguments: dict[str, Any]) -> dict[str, Any]:
        payload = {k: v for k, v in arguments.items() if k != 'idempotency_key'}
        canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
        key = arguments['idempotency_key']
        self._conn.execute('BEGIN IMMEDIATE')
        try:
            if key is not None:
                old = self._conn.execute(
                    'SELECT * FROM orders WHERE customer_id = ? AND idempotency_key = ?',
                    (payload['customer_id'], key)).fetchone()
                if old is not None:
                    if old['request_json'] != canonical:
                        raise IdempotencyConflict()
                    self._conn.commit()
                    result = self._public_row(old)
                    self.record('backend.idempotent_replay', order_id=result['order_id'])
                    return result
            unit_price = self.scenario.catalog[payload['sku']]
            cursor = self._conn.execute('''INSERT INTO orders
                (intent_id, customer_id, sku, quantity, unit_price_cents, total_cents,
                 idempotency_key, authorized, request_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (payload['intent_id'], payload['customer_id'], payload['sku'], payload['quantity'],
                 unit_price, unit_price * payload['quantity'], key, int(self._authorized), canonical))
            row = self._conn.execute('SELECT * FROM orders WHERE order_id = ?',
                                     (cursor.lastrowid,)).fetchone()
            self._conn.commit()
            result = self._public_row(row)
            self.record('backend.order_created', order_id=result['order_id'],
                        total_cents=result['total_cents'], authorized=result['authorized'])
            return result
        except BaseException:
            self._conn.rollback()
            raise
