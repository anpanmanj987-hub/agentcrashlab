import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def cli(*args):
    env = os.environ.copy()
    env['PYTHONPATH'] = str(ROOT / 'src')
    return subprocess.run([sys.executable, '-m', 'agentcrashlab', *map(str, args)],
                          text=True, capture_output=True, env=env, timeout=15)


def test_help_and_list():
    assert cli('--help').returncode == 0
    assert 'response-loss' in cli('list').stdout
    assert cli('--version').stdout.strip() == 'AgentCrashLab 0.1.0'


def test_run_exit_codes(tmp_path):
    for policy, expected in [('naive', 1), ('resilient', 0)]:
        result = cli('run', 'response-loss', '--agent', policy, '--output', tmp_path / policy)
        assert result.returncode == expected, result.stderr
        data = json.loads((tmp_path / policy / 'run.json').read_text())
        assert data['passed'] is (expected == 0)
    assert cli('run', 'missing-file.json').returncode == 2


def test_demo_expected_failures_are_not_a_bad_ci_exit(tmp_path):
    output = tmp_path / 'demo'
    result = cli('demo', '--output', output, '--transport', 'http')
    assert result.returncode == 0, result.stderr
    assert (output / 'index.html').is_file()
    assert len(list(output.glob('*/*/run.json'))) == 8
    assert 'intentional' in result.stdout.lower()
    assert cli('demo', '--output', output).returncode == 2


def test_verify_replay_and_show(tmp_path):
    original = tmp_path / 'original'
    assert cli('run', 'response-loss', '--agent', 'resilient', '--output', original).returncode == 0
    assert cli('verify', original).returncode == 0
    assert cli('replay', original, '--output', tmp_path / 'replay').returncode == 0
    shown = cli('show', 'clean')
    assert shown.returncode == 0
    assert json.loads(shown.stdout)['id'] == 'clean'
    assert cli('validate', original / 'scenario.json').returncode == 0


def test_cli_does_not_overwrite(tmp_path):
    tmp_path.joinpath('original.txt').write_text('unchanged')
    assert cli('run', 'clean', '--output', tmp_path).returncode == 2
    assert tmp_path.joinpath('original.txt').read_text() == 'unchanged'
