"""Small, portable CLI. Test failures and harness errors have distinct exit codes."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import uuid
import webbrowser
from pathlib import Path

from . import __version__
from .bundles import replay_bundle, verify_bundle, write_bundle
from .models import CaseResult
from .reports import render_report
from .runner import run_case
from .scenario import list_scenarios, load_scenario


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog='agentcrashlab', description='Test business outcomes, not agent success claims.')
    p.add_argument('--version', action='version', version=f'AgentCrashLab {__version__}')
    commands = p.add_subparsers(dest='command', required=True)
    commands.add_parser('list', help='List packaged deterministic scenarios')
    for verb in ('show', 'validate'):
        sub = commands.add_parser(verb, help=f'{verb.title()} a built-in or JSON scenario')
        sub.add_argument('scenario')
    demo = commands.add_parser('demo', help='Run both reference policies on four fault cases')
    demo.add_argument('--transport', choices=('inprocess', 'http'), default='inprocess')
    demo.add_argument('--output', type=Path, help='A NEW output directory; existing paths are never overwritten')
    demo.add_argument('--open', action='store_true', help='Open the local HTML report in your browser')
    run = commands.add_parser('run', help='Run one policy; exits 1 when business checks fail')
    run.add_argument('scenario')
    run.add_argument('--agent', choices=('naive', 'resilient'), default='resilient')
    run.add_argument('--transport', choices=('inprocess', 'http'), default='inprocess')
    run.add_argument('--output', type=Path, help='A NEW output directory')
    replay = commands.add_parser('replay', help='Reconstruct recorded tool effects, NOT rerun an LLM')
    replay.add_argument('bundle', type=Path)
    replay.add_argument('--output', type=Path, help='A NEW output directory')
    verify = commands.add_parser('verify', help='Verify bundle hashes and consistency, not authenticity')
    verify.add_argument('bundle', type=Path)
    return p


def _new_path(kind: str) -> Path:
    return Path(f'agentcrashlab-{kind}-{uuid.uuid4().hex[:8]}')


def _summary(result: CaseResult) -> None:
    # Called only with the library CaseResult, never arbitrary plugin objects.
    verdict = 'PASS' if result.passed else 'FAIL'
    print(f'{verdict:4}  {result.scenario.id:22}  {result.agent_name:12}  '
          f'orders={len(result.orders)}  claim={result.agent_result.status}  '
          f'checks={sum(c.passed for c in result.checks)}/{len(result.checks)}')


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == 'list':
            for name in list_scenarios():
                scenario = load_scenario(name)
                print(f'{name:22} {scenario.title}')
            return 0
        if args.command in ('show', 'validate'):
            scenario = load_scenario(args.scenario)
            if args.command == 'show':
                print(json.dumps(scenario.to_dict(), indent=2, ensure_ascii=True))
            else:
                print(f'VALID  {scenario.id}')
            return 0
        if args.command == 'verify':
            verify_bundle(args.bundle)
            print('VERIFIED  Checksums and cross-file consistency match. Not an authenticity proof.')
            return 0
        if args.command == 'demo':
            root = args.output or _new_path('demo')
            root.parent.mkdir(parents=True, exist_ok=True)
            root.mkdir(exist_ok=False)
            results = []
            expected_ok = True
            for scenario in list_scenarios():
                for agent in ('naive', 'resilient'):
                    result = run_case(scenario, agent=agent, transport=args.transport)
                    write_bundle(result, root / scenario / agent)
                    results.append(result)
                    expected = not (agent == 'naive' and scenario in ('response-loss', 'permission-revoked'))
                    expected_ok = expected_ok and result.passed == expected and result.execution_error is None
                    _summary(result)
            report_path = root / 'index.html'
            report_path.write_text(render_report(results), encoding='utf-8')
            print('\n2 intentional failing runs expose the flawed naive reference policy.')
            print('This demo uses deterministic policies. No LLM or real order service was invoked.')
            print(f'Report: {report_path.resolve()}')
            if args.open:
                webbrowser.open(report_path.resolve().as_uri())
            return 0 if expected_ok else 1
        output = args.output or _new_path('run')
        result = (replay_bundle(args.bundle) if args.command == 'replay' else
                  run_case(args.scenario, agent=args.agent, transport=args.transport))
        write_bundle(result, output)
        _summary(result)
        print(f'Evidence: {output.resolve()}')
        if args.command == 'replay':
            print('Replay mode: recorded tool calls on a fresh backend; the original model was NOT invoked.')
        return 0 if result.passed else 1
    except (ValueError, OSError, RuntimeError, sqlite3.Error) as exc:
        message = str(exc).encode('unicode_escape').decode('ascii')
        print(f'agentcrashlab: {message}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
