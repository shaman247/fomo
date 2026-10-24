"""
Frontend browser smoke matrix.

Serves a built dist/ on an ephemeral localhost port and loads the app in a
fresh headless-Chromium context per device profile, because the bugs that
reach production are the ones that only appear on devices unlike the
developer's: a fractional devicePixelRatio (browser zoom, 125%/175% Windows
scaling) broke every map sprite, and a non-New-York device timezone shifted
every event time.

Per case it fails on:
- any `pageerror` or `console.error`
- map sprites that never render (rendered `marker-symbols` features whose
  sprite image is missing or fully transparent) — the DPR 1.25 bug was a
  console error plus blank sprites, not an exception
- (timezone cases) event times or the default list differing from the
  America/New_York-device reference run
- (reference case) the client ErrorReporter not beaconing a deliberate error

Matrix: every DPR at desktop + New York; every timezone at DPR 1; one mobile
(375x812, isMobile/hasTouch) case.

Usage:
    ./venv/bin/python scripts/frontend_smoke.py               # test dist/
    ./venv/bin/python scripts/frontend_smoke.py --dist path/to/dist
    ./venv/bin/python scripts/frontend_smoke.py --only dpr-1.25,tz-london

Exit status: 0 all cases passed, 1 a case failed, 2 setup error.
Called by scripts/upload_public_html.py before uploading a changed bundle.
"""

import argparse
import asyncio
import functools
import http.server
import json
import re
import sys
import threading
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DESKTOP = {'width': 1200, 'height': 800}
MOBILE = {'width': 375, 'height': 812}
REFERENCE_TZ = 'America/New_York'


def build_cases():
    cases = []
    for dpr in (0.9, 1, 1.1, 1.25, 1.5, 1.75, 2):
        cases.append({'name': f'dpr-{dpr:g}', 'dpr': dpr, 'tz': REFERENCE_TZ, 'viewport': DESKTOP,
                      'mobile': False, 'tz_probe': dpr == 1, 'reporter_probe': dpr == 1})
    for tz, label in (('America/Los_Angeles', 'la'), ('Europe/London', 'london')):
        cases.append({'name': f'tz-{label}', 'dpr': 1, 'tz': tz, 'viewport': DESKTOP,
                      'mobile': False, 'tz_probe': True, 'reporter_probe': False})
    cases.append({'name': 'mobile', 'dpr': 2, 'tz': REFERENCE_TZ, 'viewport': MOBILE,
                  'mobile': True, 'tz_probe': False, 'reporter_probe': False})
    return cases


# Captures the MapLibre map: the app keeps it inside a closure in production
# builds, so hook the constructor's prototype as soon as the UMD global lands.
INIT_SCRIPT = """
(() => {
    let lib;
    Object.defineProperty(window, 'maplibregl', {
        configurable: true,
        get() { return lib; },
        set(value) {
            lib = value;
            const proto = value && value.Map && value.Map.prototype;
            if (!proto || proto.__smokeHooked) return;
            proto.__smokeHooked = true;
            for (const method of ['addImage', 'addLayer']) {
                const original = proto[method];
                proto[method] = function (...args) { window.__smokeMap = this; return original.apply(this, args); };
            }
        }
    });
})();
"""

SPRITE_STATUS_JS = """
() => {
    const map = window.__smokeMap;
    if (!map) return { stage: 'no map' };
    if (!map.getLayer('marker-symbols')) return { stage: 'no marker layer' };
    const features = map.queryRenderedFeatures({ layers: ['marker-symbols'] });
    const ids = [...new Set(features.map(f => f.properties.iconImageId).filter(Boolean))];
    let ok = 0, blank = 0, missing = 0;
    for (const id of ids) {
        const image = map.style.getImage(id);
        if (!image) { missing++; continue; }
        const data = image.data.data;
        let opaque = false;
        for (let i = 3; i < data.length; i += 16) if (data[i]) { opaque = true; break; }
        if (opaque) ok++; else blank++;
    }
    return { stage: 'markers', features: features.length, ids: ids.length, ok, blank, missing };
}
"""

LIST_NAMES_JS = """
() => [...document.querySelectorAll('#results-container .popup-event-card')]
    .slice(0, 10).map(card => (card.getAttribute('aria-label') || '').replace(/^Open /, ''))
"""

POPUP_TIMES_JS = """
() => [...document.querySelectorAll('.maplibre-popup-content .popup-event-card')]
    .filter(card => card.querySelector('.popup-event-card-datetime'))
    .map(card => [
        (card.querySelector('.popup-event-card-name')?.textContent || '').replace(/[\\s\\u00a0\\u2606\\u2605]+$/, ''),
        card.querySelector('.popup-event-card-datetime').innerText.trim()
    ])
"""

REPORTER_PROBE_MESSAGE = 'frontend-smoke reporter probe'


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class SmokeServer(http.server.ThreadingHTTPServer):
    # Four contexts fetch dozens of data chunks at once; the default listen
    # backlog of 5 resets connections and fakes "offline" failures.
    request_queue_size = 256
    daemon_threads = True


def serve(directory):
    server = SmokeServer(
        ('127.0.0.1', 0), functools.partial(QuietHandler, directory=str(directory)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def short(text, limit=150):
    text = ' '.join(str(text).split())
    return text if len(text) <= limit else text[:limit - 1] + '…'


async def run_case(browser, base_url, case, timeout, reference=None):
    result = {'case': case, 'errors': {}, 'sprites': None, 'failures': [], 'reporter': '-',
              'tz': '-', 'list': None, 'times': None}
    beacons = []

    def record_error(kind, text):
        text = str(text)
        if REPORTER_PROBE_MESSAGE in text:
            return
        key = f'{kind}: {short(text)}'
        result['errors'][key] = result['errors'].get(key, 0) + 1

    context = await browser.new_context(
        viewport=case['viewport'], device_scale_factor=case['dpr'], timezone_id=case['tz'],
        is_mobile=case['mobile'], has_touch=case['mobile'], locale='en-US')
    await context.add_init_script(INIT_SCRIPT)

    async def capture_beacon(route):
        try:
            beacons.append(json.loads(route.request.post_data or '{}'))
        except ValueError:
            beacons.append({})
        await route.fulfill(status=204)
    await context.route('**/api/client_errors.php', capture_beacon)

    page = await context.new_page()
    page.on('pageerror', lambda exc: record_error('pageerror', exc))
    page.on('console', lambda msg: record_error('console.error', msg.text) if msg.type == 'error' else None)
    started = time.monotonic()
    try:
        await page.goto(base_url, wait_until='load', timeout=timeout * 1000)

        # Sprites: wait until every rendered marker's sprite has visible pixels.
        status = {}
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status = await page.evaluate(SPRITE_STATUS_JS)
            if status.get('stage') == 'markers' and status['ids'] and status['ok'] == status['ids']:
                break
            # A page that already errored gets a short grace, not the full timeout.
            if result['errors'] and time.monotonic() - started > 8:
                break
            await asyncio.sleep(0.5)
        result['sprites'] = status
        if status.get('stage') != 'markers':
            result['failures'].append(f"map: {status.get('stage', 'not ready')}")
        elif not status['ids']:
            result['failures'].append('sprites: no event markers rendered')
        elif status['ok'] != status['ids']:
            result['failures'].append(
                f"sprites: {status['ok']}/{status['ids']} rendered "
                f"({status['blank']} blank, {status['missing']} missing)")

        if case['tz_probe'] and not result['failures']:
            await probe_times(page, result, reference)

        if case['reporter_probe']:
            await page.evaluate(f"setTimeout(() => {{ throw new Error('{REPORTER_PROBE_MESSAGE}'); }})")
            for _ in range(20):
                if any(REPORTER_PROBE_MESSAGE in b.get('message', '') for b in beacons):
                    break
                await asyncio.sleep(0.15)
            probe = next((b for b in beacons if REPORTER_PROBE_MESSAGE in b.get('message', '')), None)
            if not probe:
                result['reporter'] = 'missing'
                result['failures'].append('reporter: no beacon for a deliberate error')
            else:
                problems = [k for k, ok in (
                    ('bundle', re.fullmatch(r'[0-9a-f]{8}|dev', str(probe.get('bundle', '')))),
                    ('dpr', probe.get('dpr') == case['dpr']),
                    ('tz', probe.get('tz') == case['tz']),
                    ('viewport', probe.get('viewport') == f"{case['viewport']['width']}x{case['viewport']['height']}"),
                    ('no query strings', '?' not in json.dumps(probe)),
                ) if not ok]
                result['reporter'] = 'ok' if not problems else 'bad'
                if problems:
                    result['failures'].append(f"reporter: bad fields {problems} in {short(json.dumps(probe), 200)}")

        await asyncio.sleep(1.5)  # late console errors (sprite decode, idle work)
    except Exception as exc:
        result['failures'].append(f'harness: {short(exc)}')
    finally:
        result['seconds'] = time.monotonic() - started
        await context.close()

    for key, count in result['errors'].items():
        result['failures'].append(key + (f' (×{count})' if count > 1 else ''))
    result['beacons'] = [b for b in beacons if REPORTER_PROBE_MESSAGE not in b.get('message', '')]
    return result


async def probe_times(page, result, reference):
    """Record the default list and one popup's event times; compare to the NY run."""
    # DOM clicks: the first-visit welcome modal covers the page for real pointer input.
    await page.evaluate("() => document.querySelector('#sheet-handle')?.click()")
    try:
        await page.wait_for_selector('#results-container .popup-event-card', state='attached', timeout=8000)
    except Exception:
        result['failures'].append('tz: event list never rendered')
        return
    result['list'] = await page.evaluate(LIST_NAMES_JS)
    target = (reference or {}).get('times_target') or result['list'][0]
    result['times_target'] = target
    await page.evaluate("""target => {
        const cards = [...document.querySelectorAll('#results-container .popup-event-card')];
        (cards.find(card => card.getAttribute('aria-label') === 'Open ' + target) || cards[0]).click();
    }""", target)
    try:
        await page.wait_for_selector('.maplibre-popup-content .popup-event-card-datetime', state='attached', timeout=8000)
    except Exception:
        result['failures'].append('tz: no event popup with times opened')
        return
    await asyncio.sleep(0.5)
    result['times'] = dict(await page.evaluate(POPUP_TIMES_JS))
    if reference is None:
        result['tz'] = 'ref'
        return
    diffs = []
    if reference.get('list') and result['list'] != reference['list']:
        diffs.append('default list differs from the New York device')
    common = set(result['times']) & set(reference.get('times') or {})
    if not common:
        diffs.append(f'no common event to compare times (target {target!r})')
    for name in sorted(common):
        if result['times'][name] != reference['times'][name]:
            diffs.append(f"{name!r}: {result['times'][name]!r} vs NY device {reference['times'][name]!r}")
    result['tz'] = 'ok' if not diffs else 'DIFF'
    result['failures'].extend(f'tz: {short(d, 200)}' for d in diffs[:4])


def print_table(results):
    header = f"{'case':<10} {'dpr':>4}  {'timezone':<19} {'viewport':<15} {'sprites':>8} {'errors':>6} {'tz':>4} {'reporter':>8} {'time':>5}  result"
    print(header)
    print('-' * len(header))
    for r in results:
        c, s = r['case'], r['sprites'] or {}
        sprites = f"{s['ok']}/{s['ids']}" if s.get('stage') == 'markers' else '—'
        viewport = f"{c['viewport']['width']}x{c['viewport']['height']}" + (' mob' if c['mobile'] else '')
        errors = sum(r['errors'].values())
        print(f"{c['name']:<10} {c['dpr']:>4g}  {c['tz']:<19} {viewport:<15} {sprites:>8} {errors:>6} "
              f"{r['tz']:>4} {r['reporter']:>8} {r['seconds']:>4.0f}s  {'FAIL' if r['failures'] else 'ok'}")
    failed = [r for r in results if r['failures']]
    for r in failed:
        print(f"\n✗ {r['case']['name']}:")
        for failure in r['failures'][:8]:
            print(f'    {failure}')
        if len(r['failures']) > 8:
            print(f"    … {len(r['failures']) - 8} more")


async def main_async(args):
    from playwright.async_api import async_playwright

    cases = build_cases()
    if args.only:
        wanted = set(args.only.split(','))
        cases = [c for c in cases if c['name'] in wanted]
        if not cases:
            print(f'No cases match --only {args.only}', file=sys.stderr)
            return 2
    server = serve(args.dist)
    base_url = f'http://127.0.0.1:{server.server_port}/'
    print(f'Frontend smoke: {len(cases)} cases against {args.dist} ({base_url})\n')

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=not args.headed)
        limit = asyncio.Semaphore(args.concurrency)

        async def limited(case, reference=None):
            async with limit:
                return await run_case(browser, base_url, case, args.timeout, reference)

        # The timezone cases compare against the New York reference run, so it goes first.
        is_ref = lambda c: c['tz_probe'] and c['tz'] == REFERENCE_TZ
        first = [c for c in cases if not (c['tz_probe'] and not is_ref(c))]
        results = await asyncio.gather(*(limited(c) for c in first))
        reference = next((r for r in results if is_ref(r['case'])), None)
        later = [c for c in cases if c['tz_probe'] and not is_ref(c)]
        if later and reference is None:
            reference = await limited(next(c for c in build_cases() if is_ref(c)))
        results += await asyncio.gather(*(limited(c, reference) for c in later))
        await browser.close()
    server.shutdown()

    order = {c['name']: i for i, c in enumerate(build_cases())}
    results.sort(key=lambda r: order[r['case']['name']])
    print_table(results)
    failed = sum(1 for r in results if r['failures'])
    print(f"\n{'FAILED' if failed else 'PASSED'}: {len(results) - failed}/{len(results)} cases passed")
    return 1 if failed else 0


def main():
    parser = argparse.ArgumentParser(description='Browser smoke matrix over DPRs, timezones and a mobile viewport')
    parser.add_argument('--dist', type=Path, default=PROJECT_ROOT / 'dist', help='Built site to serve (default dist/)')
    parser.add_argument('--only', help='Comma-separated case names (e.g. dpr-1.25,tz-london,mobile)')
    parser.add_argument('--timeout', type=float, default=25, help='Seconds per case for the map and sprites (default 25)')
    parser.add_argument('--concurrency', type=int, default=4, help='Browser contexts at once (default 4)')
    parser.add_argument('--headed', action='store_true', help='Show the browser')
    args = parser.parse_args()

    if not (args.dist / 'index.html').exists():
        print(f'No built site at {args.dist} — run `npm run build` first', file=sys.stderr)
        return 2
    try:
        import playwright  # noqa: F401
    except ImportError:
        print('Playwright is not installed in this interpreter; use ./venv/bin/python', file=sys.stderr)
        return 2
    return asyncio.run(main_async(args))


if __name__ == '__main__':
    sys.exit(main())
