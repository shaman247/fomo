"""
Generate the link-preview image (og:image) from the live map.

Screenshots the map (dark theme, markers, no UI chrome) and lays the site's
logo and description over it, at the 1200x630 size link previews use.
Everything city-specific comes from config/<FOMO_CITY>.yaml `frontend`:
`domain`, `site_name`, `description` and `share_image` (the output path under
src/, which index.html's og:image points at).

Usage:
    ./venv/bin/python scripts/generate_share_card.py                # from https://<domain>/
    ./venv/bin/python scripts/generate_share_card.py --url http://127.0.0.1:8765/
Then deploy with scripts/upload_public_html.py.
"""

import argparse
import base64
import html
import os
import sys

import yaml
from playwright.sync_api import sync_playwright

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WIDTH, HEIGHT = 1200, 630

# Captures the MapLibre map (the app keeps it in a closure) so marker labels can
# be hidden: event titles would date the card within weeks; the icons stay.
CAPTURE_MAP = """(() => { let lib; Object.defineProperty(window, 'maplibregl', { configurable: true,
  get() { return lib; }, set(value) { lib = value; const proto = value.Map.prototype, addImage = proto.addImage;
  proto.addImage = function (...args) { window.__shareMap = this; return addImage.apply(this, args); }; } }); })();"""
HIDE_LABELS = """() => { const map = window.__shareMap; if (!map) return false;
  for (const id of ['marker-symbols', 'marker-symbols-hover']) if (map.getLayer(id)) map.setPaintProperty(id, 'text-opacity', 0);
  return true; }"""

# Everything but the map canvas is hidden for the screenshot.
HIDE_CHROME = """
body > *:not(#app-container), #app-container > *:not(#map-container),
#map-container > *:not(#map-wrapper), .maplibregl-control-container,
.maplibregl-popup, #sheet, #sheet-handle, #welcome-modal { visibility: hidden !important; }
"""


def load_frontend_config():
    city = os.getenv('FOMO_CITY', 'nyc')
    with open(os.path.join(PROJECT_ROOT, 'config', f'{city}.yaml'), encoding='utf-8') as f:
        frontend = (yaml.safe_load(f) or {}).get('frontend', {})
    missing = [key for key in ('domain', 'site_name', 'description', 'share_image') if not frontend.get(key)]
    if missing:
        sys.exit(f'config/{city}.yaml frontend is missing: {", ".join(missing)}')
    return frontend


def card_html(frontend, map_png):
    logo = os.path.join(PROJECT_ROOT, 'src', 'images', 'logo.svg')
    logo_uri = 'data:image/svg+xml;base64,' + base64.b64encode(open(logo, 'rb').read()).decode()
    font = os.path.join(PROJECT_ROOT, 'src', 'fonts', 'inter', 'InterVariable.woff2')
    font_uri = 'data:font/woff2;base64,' + base64.b64encode(open(font, 'rb').read()).decode()
    esc = html.escape
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
@font-face {{ font-family: Inter; src: url({font_uri}) format('woff2'); font-weight: 100 900; }}
* {{ margin: 0; box-sizing: border-box; }}
body {{ width: {WIDTH}px; height: {HEIGHT}px; overflow: hidden; background: #111; font-family: Inter, sans-serif;
  font-feature-settings: 'liga' 1, 'calt' 1; letter-spacing: -0.02em; color: #eee; }}
.map {{ position: absolute; inset: 0; background: url(data:image/png;base64,{base64.b64encode(map_png).decode()}) center / cover; }}
.shade {{ position: absolute; inset: 0; background: linear-gradient(90deg, rgba(17,17,17,.96) 0%, rgba(17,17,17,.9) 38%, rgba(17,17,17,.35) 68%, rgba(17,17,17,0) 100%); }}
.text {{ position: absolute; left: 72px; top: 0; bottom: 0; width: 560px; display: flex; flex-direction: column; justify-content: center; gap: 28px; }}
.logo {{ width: 300px; height: auto; }}
.desc {{ font-size: 38px; line-height: 1.22; font-weight: 600; color: #eee; text-wrap: balance; }}
.credit {{ position: absolute; right: 12px; bottom: 10px; padding: 3px 8px; border-radius: 6px; background: rgba(17,17,17,.8);
  font-size: 13px; color: rgba(238,238,238,.75); letter-spacing: 0; }}
</style></head><body>
<div class="map"></div><div class="shade"></div>
<div class="text">
  <img class="logo" src="{logo_uri}" alt="">
  <div class="desc">{esc(frontend['description'])}</div>
</div>
<div class="credit">Map data © OpenStreetMap contributors · Protomaps</div>
</body></html>"""


def main():
    parser = argparse.ArgumentParser(description='Generate the og:image link-preview card from the live map')
    parser.add_argument('--url', help='Site to screenshot (default https://<frontend.domain>/)')
    args = parser.parse_args()

    frontend = load_frontend_config()
    url = args.url or f"https://{frontend['domain']}/"
    output = os.path.join(PROJECT_ROOT, 'src', frontend['share_image'])

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': WIDTH, 'height': HEIGHT}, device_scale_factor=2, color_scheme='dark')
        page.add_init_script(CAPTURE_MAP)
        page.goto(url, wait_until='load')
        page.wait_for_timeout(1500)
        page.keyboard.press('Escape')  # close the first-visit welcome modal and its backdrop
        page.wait_for_timeout(7000)  # data, tiles and marker sprites
        page.add_style_tag(content=HIDE_CHROME)
        if not page.evaluate(HIDE_LABELS):
            print('warning: map not captured; marker labels stay visible', file=sys.stderr)
        page.wait_for_timeout(800)
        map_png = page.screenshot()

        card = browser.new_page(viewport={'width': WIDTH, 'height': HEIGHT}, device_scale_factor=1)
        card.set_content(card_html(frontend, map_png), wait_until='load')
        card.wait_for_timeout(300)
        os.makedirs(os.path.dirname(output), exist_ok=True)
        card.screenshot(path=output, type='png')
        browser.close()
    print(f'Wrote {os.path.relpath(output, PROJECT_ROOT)} ({WIDTH}x{HEIGHT}) from {url}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
