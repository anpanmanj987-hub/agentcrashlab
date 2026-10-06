"""Portable HTML and JUnit reports. Data is never evaluated as code."""
from __future__ import annotations

import base64
import hashlib
import html
import json
import re
import xml.etree.ElementTree as ET
from importlib.resources import files
from typing import Iterable

from .models import CaseResult


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _csp_hash(value: str) -> str:
    digest = base64.b64encode(hashlib.sha256(value.encode('utf-8')).digest()).decode('ascii')
    return f"'sha256-{digest}'"


def render_report(results: Iterable[CaseResult], *, title: str = 'AgentCrashLab / Evidence report') -> str:
    runs = list(results)
    if not runs:
        raise ValueError('Cannot render an empty report')
    assets = files('agentcrashlab').joinpath('assets')
    css = assets.joinpath('report.css').read_text(encoding='utf-8')
    script = assets.joinpath('report.js').read_text(encoding='utf-8')
    template = assets.joinpath('report.html').read_text(encoding='utf-8')
    data = canonical_json({'schema_version': 1, 'runs': [r.to_dict() for r in runs]})
    # Protect the inert JSON script block against </script>, HTML parser quirks and XSS.
    data = data.replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e')
    csp = (f"default-src 'none'; script-src {_csp_hash(script)}; style-src {_csp_hash(css)}; "
           "connect-src 'none'; img-src data:; base-uri 'none'; form-action 'none'")
    # Replace markers in one pass: user strings cannot inject a second template marker.
    values = {'@@TITLE@@': html.escape(title, quote=True), '@@CSP@@': html.escape(csp, quote=False),
              '@@CSS@@': css, '@@JS@@': script, '@@DATA@@': data}
    return re.sub(r'@@(?:TITLE|CSP|CSS|JS|DATA)@@', lambda m: values[m[0]], template)


def render_junit(result: CaseResult) -> str:
    failures = sum(not c.passed and c.id != 'execution_completed' for c in result.checks)
    errors = int(result.execution_error is not None)
    root = ET.Element('testsuite', name='AgentCrashLab', tests=str(len(result.checks)),
                      failures=str(failures), errors=str(errors))
    props = ET.SubElement(root, 'properties')
    for name, value in [('scenario', result.scenario.id), ('agent', result.agent_name),
                        ('transport', result.transport), ('mode', result.mode)]:
        ET.SubElement(props, 'property', name=name, value=value)
    for check in result.checks:
        case = ET.SubElement(root, 'testcase', classname=result.scenario.id, name=check.id)
        if not check.passed:
            tag = 'error' if check.id == 'execution_completed' else 'failure'
            failure = ET.SubElement(case, tag, message=check.title)
            failure.text = f'{check.detail}\nExpected: {canonical_json(check.expected)}\nActual: {canonical_json(check.actual)}'
    ET.indent(root, space='  ')
    return ET.tostring(root, encoding='unicode', xml_declaration=True) + '\n'
