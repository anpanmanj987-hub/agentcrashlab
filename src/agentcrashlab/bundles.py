"""Immutable evidence bundles and replay of recorded tool calls, not model reasoning."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from typing import Any

from .checks import evaluate
from .errors import ToolError
from .models import AgentResult, CaseResult, Event
from .reports import canonical_json, render_junit, render_report
from .runner import run_case
from .scenario import Scenario, parse_json

EVIDENCE_FILES = frozenset({'scenario.json', 'run.json', 'events.jsonl', 'orders.sqlite3',
                            'checks.junit.xml', 'report.html'})
MAX_EVIDENCE_BYTES = 32 * 1024 * 1024


def write_bundle(result: CaseResult, destination: str | Path) -> Path:
    """Never overwrite an existing directory. Manifest is written last.

    Interrupted writes may leave an incomplete directory; verify rejects it.
    No automatic cleanup removes user files. Choose a new path for another run.
    """
    output = Path(destination)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir(exist_ok=False)
    payloads = {
        'scenario.json': (json.dumps(result.scenario.to_dict(), indent=2, ensure_ascii=True) + '\n').encode(),
        'run.json': (json.dumps(result.to_dict(), indent=2, ensure_ascii=True) + '\n').encode(),
        'events.jsonl': ''.join(canonical_json(e.to_dict()) + '\n' for e in result.events).encode(),
        'orders.sqlite3': result.database,
        'checks.junit.xml': render_junit(result).encode('utf-8'),
        'report.html': render_report([result]).encode('utf-8'),
    }
    for name, content in payloads.items():
        with (output / name).open('xb') as file:
            file.write(content)
    manifest = ''.join(hashlib.sha256(payloads[name]).hexdigest() + '  ' + name + '\n'
                       for name in sorted(payloads))
    with (output / 'SHA256SUMS').open('x', encoding='ascii') as file:
        file.write(manifest)
    return output


def _read_bounded(path: Path, limit: int = MAX_EVIDENCE_BYTES) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f'Missing or unsafe evidence file: {path.name}')
    with path.open('rb') as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f'Evidence file too large: {path.name}')
    return data


def verify_bundle(source: str | Path) -> dict[str, Any]:
    """Check hashes AND cross-file semantic consistency; not authenticity.

    An author who changes both evidence and manifest can forge a new bundle.
    Trusted provenance/signatures are out of scope. Treat sources as untrusted data.
    """
    directory = Path(source)
    manifest = _read_bounded(directory / 'SHA256SUMS', 8192).decode('ascii')
    hashes = {}
    for line in manifest.splitlines():
        match = re.fullmatch(r'([a-f0-9]{64})  ([a-zA-Z0-9_.-]+)', line)
        if match is None or match[2] not in EVIDENCE_FILES or match[2] in hashes:
            raise ValueError('Invalid or unexpected manifest entry')
        hashes[match[2]] = match[1]
    if hashes.keys() != EVIDENCE_FILES:
        raise ValueError('Incomplete evidence manifest')
    payloads = {}
    for name, checksum in hashes.items():
        data = _read_bounded(directory / name)
        if hashlib.sha256(data).hexdigest() != checksum:
            raise ValueError(f'Checksum mismatch: {name}')
        payloads[name] = data
    try:
        run = parse_json(payloads['run.json'])
        scenario = Scenario.from_dict(parse_json(payloads['scenario.json']))
        if not isinstance(run, dict) or type(run.get('schema_version')) is not int or run['schema_version'] != 1:
            raise ValueError('Invalid run schema')
        if run['scenario'] != scenario.to_dict():
            raise ValueError('Scenario is inconsistent with run record')
        events = [parse_json(line) for line in payloads['events.jsonl'].splitlines() if line.strip()]
        if events != run['events'] or not events:
            raise ValueError('Event trace is inconsistent with run record')
        if len(events) > 10 * scenario.max_tool_calls + 10:
            raise ValueError('Event trace exceeds scenario limits')
        if any(type(e.get('seq')) is not int or e['seq'] != i for i, e in enumerate(events, 1)):
            raise ValueError('Event sequence is inconsistent')
        db_uri = (directory / 'orders.sqlite3').resolve().as_uri() + '?mode=ro'
        with closing(sqlite3.connect(db_uri, uri=True)) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute('PRAGMA trusted_schema=OFF')
            row = conn.execute("SELECT type FROM sqlite_master WHERE name='orders'").fetchone()
            if row is None or row['type'] != 'table':
                raise ValueError('Evidence database must contain an orders table')
            orders = tuple({k: (bool(row[k]) if k == 'authorized' else row[k])
                            for k in row.keys() if k != 'request_json'}
                           for row in conn.execute('SELECT * FROM orders ORDER BY order_id LIMIT ?',
                                                   (scenario.max_tool_calls + 1,)))
            if len(orders) > scenario.max_tool_calls:
                raise ValueError('Database contains more orders than the tool-call limit')
        if list(orders) != run['orders']:
            raise ValueError('Database state is inconsistent with run record')
        outcome = AgentResult(**run['agent_result'])
        checks = evaluate(scenario, orders, outcome, run['execution_error'],
                          tuple(Event(e['seq'], e['kind'], e['data']) for e in events))
        passed = all(c.passed for c in checks) and run['execution_error'] is None
        if [c.to_dict() for c in checks] != run['checks'] or type(run['passed']) is not bool or run['passed'] != passed:
            raise ValueError('Stored verdict is inconsistent with independent checks')
    except (KeyError, TypeError, AttributeError, sqlite3.Error) as exc:
        raise ValueError('Malformed or inconsistent evidence bundle') from exc
    return run


def replay_bundle(source: str | Path) -> CaseResult:
    original = verify_bundle(source)
    if original['execution_error'] is not None:
        raise ValueError('Cannot replay a policy exception; rerun the original trusted policy instead')
    scenario = Scenario.from_dict(original['scenario'])
    calls = [e['data'] for e in original['events'] if e['kind'] == 'tool.call']
    if len(calls) > scenario.max_tool_calls or any(c.get('tool') != 'create_order' for c in calls):
        raise ValueError('Unsupported or excessive recorded tool calls')
    recorded_result = AgentResult(**original['agent_result'])

    def recorded_policy(tools: Any, task: Any) -> AgentResult:
        for call in calls:
            try:
                tools.create_order(**call['arguments'])
            except ToolError:
                pass
        if calls and any(e['kind'] == 'tool.limit_reached' for e in original['events']):
            try:
                tools.create_order(**calls[-1]['arguments'])
            except ToolError:
                pass
        return recorded_result

    result = run_case(scenario, agent=recorded_policy, agent_name=original['agent_name'])
    if result.execution_error or list(result.orders) != original['orders']:
        raise ValueError('Recorded calls do not reproduce the saved backend state')
    original_effects = [e for e in original['events'] if e['kind'] != 'run.started']
    replay_effects = [e.to_dict() for e in result.events if e.kind != 'run.started']
    if original_effects != replay_effects:
        raise ValueError('Recorded calls do not reproduce the saved effect trace')
    return replace(result, mode='recorded-tool-calls', policy_kind='recorded',
                   replay_of=hashlib.sha256(canonical_json(original).encode()).hexdigest())
