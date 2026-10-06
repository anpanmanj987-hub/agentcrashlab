#!/usr/bin/env python3
"""Offline build using an already-installed setuptools >=77 PEP 517 backend.

Normal development can use `python -m build`; this helper avoids downloading a
build frontend in offline environments. It does not publish anything.
"""
from pathlib import Path
import os
import sys


def main() -> int:
    import setuptools
    if int(setuptools.__version__.split('.')[0]) < 77:
        raise RuntimeError('Install setuptools 77 or newer before building')
    from setuptools import build_meta
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    output = root / 'dist'
    output.mkdir(exist_ok=True)
    print(build_meta.build_wheel(str(output)))
    print(build_meta.build_sdist(str(output)))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ImportError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc
