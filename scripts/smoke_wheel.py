#!/usr/bin/env python3
"""Install the wheel into a dependency-free venv, outside the source tree."""
from pathlib import Path
import json
import os
import subprocess
import tempfile
import venv


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    wheels = sorted((root / 'dist').glob('agentcrashlab-*.whl'))
    if len(wheels) != 1:
        raise RuntimeError('Expected exactly one built wheel in dist/')
    output = root / 'artifacts' / 'wheel-smoke'
    output.mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in os.environ.items() if k not in ('PYTHONPATH', 'PYTHONHOME')}
    env['PIP_NO_INDEX'] = '1'
    env['PIP_DISABLE_PIP_VERSION_CHECK'] = '1'
    with tempfile.TemporaryDirectory(prefix='acl-wheel-smoke-') as temp:
        temp = Path(temp)
        venv.EnvBuilder(with_pip=True).create(temp / 'env')
        python = temp / 'env' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        def run(*args: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run([str(python), *map(str, args)], cwd=temp, env=env,
                                  text=True, capture_output=True, check=True, timeout=45)
        logs = [run('-m', 'pip', 'install', '--no-deps', str(wheels[0])).stdout]
        logs.append(run('-m', 'agentcrashlab', '--version').stdout)
        logs.append(run('-m', 'agentcrashlab', 'demo', '--transport', 'http',
                        '--output', str(temp / 'demo')).stdout)
        original = temp / 'demo' / 'response-loss' / 'resilient'
        logs.append(run('-m', 'agentcrashlab', 'verify', str(original)).stdout)
        logs.append(run('-m', 'agentcrashlab', 'replay', str(original),
                        '--output', str(temp / 'replay')).stdout)
        bad = subprocess.run([str(python), '-m', 'agentcrashlab', 'run', 'response-loss',
                              '--agent', 'naive', '--output', str(temp / 'bad')],
                             cwd=temp, env=env, capture_output=True, text=True, timeout=30)
        assert bad.returncode == 1, (bad.returncode, bad.stderr)
        assert json.loads((temp / 'bad' / 'run.json').read_text())['passed'] is False
        logs.append(bad.stdout)
        (output / 'smoke.txt').write_text('\n'.join(logs), encoding='utf-8')
        (output / 'demo.html').write_bytes((temp / 'demo' / 'index.html').read_bytes())
    print('Installed-wheel smoke: PASS (offline, no-deps, outside checkout)')


if __name__ == '__main__':
    main()
