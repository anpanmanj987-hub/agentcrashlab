"""Exercise CLI return contracts in-process as well as subprocess smoke tests."""
import json
import sqlite3
from contextlib import closing

import pytest

from agentcrashlab.cli import main


def test_list_show_validate_and_invalid_configuration(capsys, tmp_path):
    assert main(['list']) == 0
    assert 'response-loss' in capsys.readouterr().out
    assert main(['show', 'response-loss']) == 0
    assert json.loads(capsys.readouterr().out)['id'] == 'response-loss'
    assert main(['validate', 'clean']) == 0
    assert 'VALID' in capsys.readouterr().out
    bad = tmp_path / 'bad.json'
    bad.write_text('{"schema_version": true}')
    assert main(['validate', str(bad)]) == 2
    assert 'agentcrashlab:' in capsys.readouterr().err


def test_full_cli_roundtrip_return_codes(tmp_path, capsys):
    failed = tmp_path / 'failed'
    assert main(['run', 'response-loss', '--agent', 'naive', '--output', str(failed)]) == 1
    assert 'FAIL' in capsys.readouterr().out
    assert main(['verify', str(failed)]) == 0
    assert 'Not an authenticity proof' in capsys.readouterr().out
    assert main(['replay', str(failed), '--output', str(tmp_path / 'replayed')]) == 1
    assert 'original model was NOT invoked' in capsys.readouterr().out
    assert main(['run', 'clean', '--output', str(tmp_path / 'good')]) == 0
    assert main(['run', 'clean', '--output', str(failed)]) == 2


def test_default_paths_are_unique_and_browser_open_is_explicit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    opened = []
    monkeypatch.setattr('agentcrashlab.cli.webbrowser.open', opened.append)
    assert main(['run', 'clean']) == 0
    assert main(['run', 'clean']) == 0
    assert len(list(tmp_path.glob('agentcrashlab-run-*'))) == 2
    assert opened == []
    assert main(['demo', '--open']) == 0
    assert len(opened) == 1 and opened[0].endswith('/index.html')


def test_cli_harness_startup_failure_is_error_not_business_failure(tmp_path, monkeypatch):
    from agentcrashlab.http import LocalOrderServer
    def fail_start(self):
        raise OSError('Port binding unavailable')
    monkeypatch.setattr(LocalOrderServer, '__enter__', fail_start)
    assert main(['run', 'clean', '--transport', 'http', '--output', str(tmp_path / 'bad')]) == 2
    assert not (tmp_path / 'bad').exists()


def test_bundled_database_connection_is_closed(tmp_path):
    assert main(['run', 'clean', '--output', str(tmp_path / 'evidence')]) == 0
    path = tmp_path / 'evidence' / 'orders.sqlite3'
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute('SELECT COUNT(*) FROM orders').fetchone()[0] == 1
    path.unlink()
