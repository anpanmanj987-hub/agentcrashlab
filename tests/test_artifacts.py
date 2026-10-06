from contextlib import closing
import hashlib
import json
import sqlite3
import xml.etree.ElementTree as ET

import pytest


def make_bundle(tmp_path, case='response-loss', agent='naive'):
    from agentcrashlab import run_case
    from agentcrashlab.bundles import write_bundle
    result = run_case(case, agent=agent)
    path = tmp_path / 'case'
    write_bundle(result, path)
    return result, path


def test_bundle_has_all_evidence(tmp_path):
    from agentcrashlab.bundles import verify_bundle
    result, path = make_bundle(tmp_path)
    assert {p.name for p in path.iterdir()} == {'scenario.json', 'run.json', 'events.jsonl',
        'orders.sqlite3', 'checks.junit.xml', 'report.html', 'SHA256SUMS'}
    assert verify_bundle(path)['passed'] is False
    with closing(sqlite3.connect(path / 'orders.sqlite3')) as conn:
        assert conn.execute('SELECT COUNT(*) FROM orders').fetchone()[0] == 2
    root = ET.parse(path / 'checks.junit.xml').getroot()
    assert int(root.attrib['tests']) == len(result.checks)
    assert int(root.attrib['failures']) >= 1
    assert len(root.findall('testcase/failure')) == int(root.attrib['failures'])


def test_bundle_does_not_overwrite_user_files(tmp_path):
    from agentcrashlab import run_case
    from agentcrashlab.bundles import write_bundle
    path = tmp_path / 'occupied'
    path.mkdir()
    (path / 'important.txt').write_text('do not touch')
    with pytest.raises(FileExistsError):
        write_bundle(run_case('clean'), path)
    assert (path / 'important.txt').read_text() == 'do not touch'
    assert len(list(path.iterdir())) == 1


def test_modified_bundle_fails_integrity(tmp_path):
    from agentcrashlab.bundles import verify_bundle
    _, path = make_bundle(tmp_path)
    (path / 'run.json').write_text('{}')
    with pytest.raises(ValueError, match='Checksum'):
        verify_bundle(path)


def test_manifest_path_traversal_rejected(tmp_path):
    from agentcrashlab.bundles import verify_bundle
    _, path = make_bundle(tmp_path)
    with (path / 'SHA256SUMS').open('a') as f:
        f.write('0' * 64 + '  ../outside.txt\n')
    with pytest.raises(ValueError):
        verify_bundle(path)


def test_missing_manifest_file_rejected(tmp_path):
    from agentcrashlab.bundles import verify_bundle
    _, path = make_bundle(tmp_path)
    (path / 'orders.sqlite3').unlink()
    with pytest.raises(ValueError):
        verify_bundle(path)


def test_required_file_symlink_rejected(tmp_path):
    from agentcrashlab.bundles import verify_bundle
    _, path = make_bundle(tmp_path)
    original = (path / 'run.json').read_bytes()
    target = tmp_path / 'outside.json'
    target.write_bytes(original)
    (path / 'run.json').unlink()
    try:
        (path / 'run.json').symlink_to(target)
    except OSError:
        pytest.skip('Symlinks not available on this host')
    with pytest.raises(ValueError):
        verify_bundle(path)


def test_tampered_checks_with_updated_hash_are_inconsistent(tmp_path):
    from agentcrashlab.bundles import verify_bundle
    _, path = make_bundle(tmp_path)
    run_file = path / 'run.json'
    data = json.loads(run_file.read_text())
    data['passed'] = True
    run_file.write_text(json.dumps(data))
    manifest = path / 'SHA256SUMS'
    lines = manifest.read_text().splitlines()
    lines = [(hashlib.sha256(run_file.read_bytes()).hexdigest() + '  run.json')
             if line.endswith('  run.json') else line for line in lines]
    manifest.write_text('\n'.join(lines) + '\n')
    with pytest.raises(ValueError, match='inconsistent'):
        verify_bundle(path)


@pytest.mark.parametrize('agent', ['naive', 'resilient'])
def test_replay_reconstructs_orders_and_checks(tmp_path, agent):
    from agentcrashlab.bundles import replay_bundle
    original, path = make_bundle(tmp_path, agent=agent)
    replay = replay_bundle(path)
    assert replay.orders == original.orders
    assert replay.checks == original.checks
    assert replay.passed == original.passed
    assert replay.mode == 'recorded-tool-calls'
    assert len(replay.replay_of) == 64


def test_replay_rejects_crashed_policy(tmp_path):
    from agentcrashlab import run_case
    from agentcrashlab.bundles import write_bundle, replay_bundle
    def bad(t, task):
        raise RuntimeError('nope')
    path = tmp_path / 'crash'
    write_bundle(run_case('clean', agent=bad), path)
    with pytest.raises(ValueError, match='exception'):
        replay_bundle(path)


def test_offline_report_escapes_untrusted_content():
    from agentcrashlab import AgentResult, run_case
    from agentcrashlab.reports import render_report
    payload = '</script><script>globalThis.PWNED=1</script><img src=x onerror=alert(1)>'
    result = run_case('clean', agent=lambda t, task: AgentResult('success', payload))
    html = render_report([result])
    assert payload not in html
    assert 'Content-Security-Policy' in html
    assert "connect-src 'none'" in html
    assert 'cdn.' not in html
    assert 'https://' not in html
    assert '\\u003c/script\\u003e' in html


def test_custom_policy_named_naive_is_not_labelled_model_free():
    from agentcrashlab import AgentResult, run_case
    result = run_case('clean', agent=lambda t, task: AgentResult('success'), agent_name='naive')
    assert result.to_dict()['policy_kind'] == 'custom'
