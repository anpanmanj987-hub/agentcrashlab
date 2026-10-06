import json

import pytest


def acl():
    import agentcrashlab
    return agentcrashlab


def raw():
    return acl().load_scenario('clean').to_dict()


def test_builtins_are_packaged():
    assert acl().list_scenarios() == ['clean', 'response-loss', 'pre-commit-timeout', 'permission-revoked']


def test_roundtrip(tmp_path):
    data = raw()
    path = tmp_path / 'case.json'
    path.write_text(json.dumps(data), encoding='utf-8')
    assert acl().load_scenario(path).to_dict() == data


@pytest.mark.parametrize('mutation', [
    lambda d: d.update(unexpected=True),
    lambda d: d.update(schema_version=2),
    lambda d: d.update(schema_version=True),
    lambda d: d.update(id='../oops'),
    lambda d: d.update(max_tool_calls=0),
    lambda d: d['task'].update(quantity=True),
    lambda d: d['task'].update(quantity=0),
    lambda d: d['task'].update(max_total_cents=-1),
    lambda d: d['task'].update(sku='missing'),
    lambda d: d['task'].update(command='echo hacked'),
    lambda d: d['catalog'].update({'demo-keyboard': -1}),
    lambda d: d.update(faults=[{'kind': 'arbitrary-code', 'on_call': 1}]),
    lambda d: d.update(faults=[{'kind': 'response_lost', 'on_call': 0}]),
    lambda d: d.update(faults=[{'kind': 'response_lost', 'on_call': True}]),
    lambda d: d.update(faults=[{'kind': 'response_lost', 'on_call': 1},
                              {'kind': 'timeout_before_commit', 'on_call': 1}]),
    lambda d: d['expect'].update(orders=True),
    lambda d: d['expect'].update(status='unknown'),
])
def test_strict_config_rejects_ambiguity(mutation):
    data = raw()
    mutation(data)
    with pytest.raises(ValueError):
        acl().Scenario.from_dict(data)


def test_duplicate_json_keys_rejected(tmp_path):
    path = tmp_path / 'dup.json'
    path.write_text('{"schema_version": 1, "schema_version": 2}')
    with pytest.raises(ValueError, match='Duplicate'):
        acl().load_scenario(path)


def test_large_config_rejected(tmp_path):
    path = tmp_path / 'huge.json'
    path.write_text(' ' * 1048577)
    with pytest.raises(ValueError, match='large'):
        acl().load_scenario(path)


def test_nonfinite_json_rejected(tmp_path):
    path = tmp_path / 'nan.json'
    path.write_text('{"schema_version": NaN}')
    with pytest.raises(ValueError):
        acl().load_scenario(path)
