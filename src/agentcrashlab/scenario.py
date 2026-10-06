"""Strict, data-only scenario definitions. No YAML constructors, eval or commands."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

MAX_CONFIG_BYTES = 1_048_576
BUILTINS = ('clean', 'response-loss', 'pre-commit-timeout', 'permission-revoked')
FAULT_KINDS = frozenset({'response_lost', 'timeout_before_commit', 'permission_revoked'})


def object_fields(value: Any, required: set[str], optional: set[str] | None = None,
                  label: str = 'object') -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f'{label} must be an object')
    missing = required - value.keys()
    unknown = value.keys() - required - (optional or set())
    if missing or unknown:
        raise ValueError(f'{label}: missing={sorted(missing)}, unknown={sorted(unknown)}')
    return value


def integer(value: Any, label: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{label} must be an integer from {low} to {high}')
    return value


def text(value: Any, label: str, limit: int = 200) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f'{label} must be a non-empty string of at most {limit} characters')
    if any(ord(c) < 32 and c not in '\n\t' for c in value):
        raise ValueError(f'{label} contains control characters')
    return value


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'Duplicate JSON key: {key}')
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f'Non-finite JSON constant: {value}')


def parse_json(raw: str | bytes) -> Any:
    try:
        return json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    except (json.JSONDecodeError, UnicodeDecodeError, RecursionError) as exc:
        raise ValueError('Invalid JSON data') from exc


@dataclass(frozen=True)
class Task:
    intent_id: str
    customer_id: str
    sku: str
    quantity: int
    max_total_cents: int

    def order_args(self) -> dict[str, Any]:
        return {'intent_id': self.intent_id, 'customer_id': self.customer_id,
                'sku': self.sku, 'quantity': self.quantity}

    def to_dict(self) -> dict[str, Any]:
        return self.order_args() | {'max_total_cents': self.max_total_cents}


@dataclass(frozen=True)
class Fault:
    kind: str
    on_call: int

    def to_dict(self) -> dict[str, Any]:
        return {'kind': self.kind, 'on_call': self.on_call}


@dataclass(frozen=True)
class Scenario:
    id: str
    title: str
    description: str
    task: Task
    catalog: Mapping[str, int]
    faults: tuple[Fault, ...]
    expected_orders: int = 1
    expected_status: str = 'success'
    max_tool_calls: int = 100

    @classmethod
    def from_dict(cls, raw: Any) -> Scenario:
        data = object_fields(raw, {'schema_version', 'id', 'title', 'description', 'task',
                                  'catalog', 'faults', 'expect', 'max_tool_calls'}, label='scenario')
        integer(data['schema_version'], 'schema_version', 1, 1)
        sid = text(data['id'], 'id', 80)
        if re.fullmatch(r'[a-z0-9][a-z0-9_-]*', sid) is None:
            raise ValueError('id must be lowercase letters, digits, underscores or hyphens')
        title = text(data['title'], 'title', 160)
        description = text(data['description'], 'description', 4000)
        task = object_fields(data['task'], {'intent_id', 'customer_id', 'sku', 'quantity',
                                          'max_total_cents'}, label='task')
        parsed_task = Task(text(task['intent_id'], 'intent_id'),
                           text(task['customer_id'], 'customer_id'), text(task['sku'], 'sku'),
                           integer(task['quantity'], 'quantity', 1, 1000),
                           integer(task['max_total_cents'], 'max_total_cents', 0, 10**12))
        catalog = data['catalog']
        if not isinstance(catalog, dict) or not 1 <= len(catalog) <= 1000:
            raise ValueError('catalog must contain between 1 and 1000 SKUs')
        normalized_catalog = {text(k, 'catalog SKU'): integer(v, 'unit price', 1, 10**9)
                              for k, v in catalog.items()}
        if parsed_task.sku not in catalog:
            raise ValueError('task SKU is missing from catalog')
        max_calls = integer(data['max_tool_calls'], 'max_tool_calls', 1, 1000)
        if not isinstance(data['faults'], list) or len(data['faults']) > max_calls:
            raise ValueError('faults must be a list no longer than max_tool_calls')
        faults = []
        seen_calls = set()
        for item in data['faults']:
            fault = object_fields(item, {'kind', 'on_call'}, label='fault')
            if not isinstance(fault['kind'], str) or fault['kind'] not in FAULT_KINDS:
                raise ValueError(f'Unknown fault kind; expected {sorted(FAULT_KINDS)}')
            call = integer(fault['on_call'], 'on_call', 1, max_calls)
            if call in seen_calls:
                raise ValueError('Only one fault may target a given call number')
            seen_calls.add(call)
            faults.append(Fault(fault['kind'], call))
        expect = object_fields(data['expect'], {'orders', 'status'}, label='expect')
        orders = integer(expect['orders'], 'expected orders', 0, 1)
        status = expect['status']
        if status not in ('success', 'blocked'):
            raise ValueError('Expected status must be success or blocked')
        if (orders == 1) != (status == 'success'):
            raise ValueError('Expect one order and success, or zero orders and blocked')
        return cls(sid, title, description, parsed_task, MappingProxyType(normalized_catalog),
                   tuple(sorted(faults, key=lambda f: f.on_call)), orders, status, max_calls)

    def to_dict(self) -> dict[str, Any]:
        return {'schema_version': 1, 'id': self.id, 'title': self.title,
                'description': self.description, 'task': self.task.to_dict(),
                'catalog': dict(self.catalog), 'faults': [f.to_dict() for f in self.faults],
                'expect': {'orders': self.expected_orders, 'status': self.expected_status},
                'max_tool_calls': self.max_tool_calls}


def list_scenarios() -> list[str]:
    return list(BUILTINS)


def load_scenario(source: str | Path | Scenario) -> Scenario:
    if isinstance(source, Scenario):
        # Revalidate even direct dataclass construction; makes the public runner fail closed.
        return Scenario.from_dict(source.to_dict())
    if str(source) in BUILTINS:
        raw = files('agentcrashlab').joinpath('scenarios', f'{source}.json').read_bytes()
    else:
        path = Path(source)
        with path.open('rb') as stream:
            raw = stream.read(MAX_CONFIG_BYTES + 1)
    if len(raw) > MAX_CONFIG_BYTES:
        raise ValueError('Scenario file is too large (limit: 1 MiB)')
    return Scenario.from_dict(parse_json(raw))
