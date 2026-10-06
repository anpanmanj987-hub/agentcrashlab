#!/usr/bin/env python3
"""Optional browser checks and actual UI captures; not a runtime dependency.

Install playwright and Pillow separately, plus a Playwright Chromium browser.
Use --browser /path/to/chromium when using a system browser.
"""
from __future__ import annotations

import argparse
import io
import json
from pathlib import Path
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    parser.add_argument('--html', type=Path, default=root / 'site/index.html')
    parser.add_argument('--browser', help='Optional system Chromium executable')
    parser.add_argument('--output', type=Path, default=root / 'artifacts/browser-check')
    parser.add_argument('--capture', action='store_true', help='Save screenshots and GIF of real report events')
    args = parser.parse_args()
    from playwright.sync_api import sync_playwright
    args.output.mkdir(parents=True, exist_ok=True)
    html = args.html.read_text(encoding='utf-8')
    errors: list[str] = []
    requests: list[str] = []
    checks: list[str] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, executable_path=args.browser)
        page = browser.new_page(viewport={'width': 1440, 'height': 1080}, device_scale_factor=1)
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('request', lambda request: requests.append(request.url))
        # set_content makes this test independent of sandbox file:// navigation policy.
        # It still executes the embedded CSS, CSP, data and JS as a browser document.
        page.set_content(html, wait_until='load')
        assert page.locator('.panel').count() == 2
        assert page.locator('.check').count() == 16
        assert page.locator('[data-agent="naive"] .badge.fail').count() == 1
        assert page.locator('[data-agent="resilient"] .badge.pass').count() == 1
        assert page.locator('[data-agent="naive"] .metric-value').first.inner_text() == '2'
        assert page.locator('[data-agent="resilient"] .metric-value').first.inner_text() == '1'
        checks.append('Executed comparison: 2 panels, 8 checks each, naive 2 orders / resilient 1')
        for name, fails in [('01 / Clean control', 0), ('03 / Before commit', 0), ('04 / Revoked access', 1), ('02 / Response lost', 1)]:
            page.get_by_role('tab', name=name, exact=True).click()
            assert page.locator('.panel').count() == 2
            assert page.locator('.badge.fail').count() == fails
        checks.append('All four scenario tabs show the expected verdict pattern')
        page.get_by_role('tab', name='02 / Response lost', exact=True).focus()
        page.keyboard.press('ArrowRight')
        assert page.locator('[role=tab][aria-selected=true]').inner_text() == '03 / Before commit'
        page.keyboard.press('Home')
        assert page.locator('[role=tab][aria-selected=true]').inner_text() == '01 / Clean control'
        page.get_by_role('tab', name='02 / Response lost', exact=True).click()
        checks.append('Keyboard arrow and Home navigation')
        page.locator('#reset').click()
        assert page.locator('#frame-counter').inner_text().startswith('0 /')
        page.locator('#play').click()
        page.wait_for_timeout(650)
        assert int(page.locator('#scrubber').input_value()) > 0
        page.locator('#play').click()
        paused = page.locator('#frame-counter').inner_text()
        page.wait_for_timeout(650)
        assert page.locator('#frame-counter').inner_text() == paused
        page.locator('#scrubber').evaluate("e=>{e.value=e.max;e.dispatchEvent(new Event('input'));}")
        page.locator('details.evidence summary').first.click()
        assert page.locator('details.evidence[open] tbody tr').count() == 2
        page.locator('details.evidence summary').first.click()
        checks.append('Play, pause, reset, range seeking and real database snapshot expansion')
        assert not errors, errors
        assert not requests, requests
        checks.append('No browser exceptions and zero external network requests')
        if args.capture:
            page.screenshot(path=str(args.output / 'desktop.png'), full_page=True)
            from PIL import Image
            frames = []
            page.set_viewport_size({'width': 1280, 'height': 1100})
            box = page.locator('.lab').bounding_box()
            clip = {'x': 32, 'y': box['y'], 'width': 1216, 'height': min(1030, box['height'])}
            steps = [0, 2, 3, 4, 6, 8, 10, 12, 1000]
            for step in steps:
                page.locator('#scrubber').evaluate('(e,v)=>{e.value=Math.min(v,Number(e.max));e.dispatchEvent(new Event("input"));}', step)
                frames.append(Image.open(io.BytesIO(page.screenshot(clip=clip))).convert('RGB'))
            # Show the permission scenario, then return to the key duplicate-order example.
            for label in ['04 / Revoked access', '02 / Response lost']:
                page.get_by_role('tab', name=label, exact=True).click()
                frames.append(Image.open(io.BytesIO(page.screenshot(clip=clip))).convert('RGB'))
            frames[0].save(args.output / 'demo.gif', save_all=True, append_images=frames[1:],
                           duration=[1000, 600, 600, 600, 900, 600, 600, 600, 1800, 1800, 2400],
                           loop=0, optimize=True)
        for width in [390, 320]:
            page.set_viewport_size({'width': width, 'height': 844})
            for label in ['02 / Response lost', '04 / Revoked access']:
                page.get_by_role('tab', name=label, exact=True).click()
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (width, label)
            if args.capture and width == 390:
                page.get_by_role('tab', name='02 / Response lost', exact=True).click()
                page.screenshot(path=str(args.output / 'mobile.png'), full_page=True)
        checks.append('390px and 320px responsive layouts: no horizontal document overflow')
        # Render adversarial result text through the actual package template.
        sys.path.insert(0, str(root / 'src'))
        from agentcrashlab import AgentResult, run_case
        from agentcrashlab.reports import render_report
        payload = '</script><script>globalThis.PWNED=1</script><img src=x onerror=alert(1)>'
        result = run_case('clean', agent=lambda t, task: AgentResult('success', payload))
        page.set_content(render_report([result]), wait_until='load')
        assert page.locator('.claim-text').inner_text() == payload
        assert page.evaluate('typeof globalThis.PWNED') == 'undefined'
        assert page.locator('img').count() == 0
        assert not errors and not requests, (errors, requests)
        checks.append('Adversarial script/image payload rendered literally; no execution or request')
        browser_version = browser.version
        browser.close()
    summary = {'status': 'passed', 'browser': 'Chromium ' + browser_version,
               'load_method': 'Playwright set_content; not a file:// navigation test',
               'checks': checks, 'requests': requests, 'errors': errors}
    (args.output / 'checks.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
