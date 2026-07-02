#!/usr/bin/env python3
"""Generate Android + iOS app icons from the adaptive-icon foreground vector.

Rasterizes the torch paths in
mobile/android/app/src/main/res/drawable/ic_launcher_foreground.xml
(supersampled polygon fills via Pillow) and produces:

  Android:
  - mobile/android/play-store-icon.png     512x512 opaque PNG (Play listing icon:
    full square, no rounded corners/shadow -- Google Play applies those)
  - mobile/android/app/src/main/res/mipmap-*/ic_launcher.webp        (rounded square)
  - mobile/android/app/src/main/res/mipmap-*/ic_launcher_round.webp  (circle)

  iOS (single-size 1024x1024 asset-catalog variants; the system masks corners):
  - AppIcon.appiconset/icon-1024.png        any/light: opaque, alpha stripped
  - AppIcon.appiconset/icon-1024-dark.png   dark: transparent bg, colored torch
  - AppIcon.appiconset/icon-1024-tinted.png tinted: transparent bg, grayscale torch
  plus the matching Contents.json.

Usage: ./venv/bin/python scripts/generate_app_icons.py
"""
import json
import os
import sys
import xml.etree.ElementTree as ET

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'pipeline'))
from svgpathtools import parse_path, Line

ROOT = os.path.join(os.path.dirname(__file__), '..')
FOREGROUND_XML = os.path.join(
    ROOT, 'mobile/android/app/src/main/res/drawable/ic_launcher_foreground.xml')
RES_DIR = os.path.join(ROOT, 'mobile/android/app/src/main/res')
PLAY_ICON = os.path.join(ROOT, 'mobile/android/play-store-icon.png')
APPICONSET = os.path.join(
    ROOT, 'mobile/ios/fomo/fomo/Assets.xcassets/AppIcon.appiconset')

BACKGROUND = '#1A1A2E'  # matches drawable/ic_launcher_background.xml
SUPERSAMPLE = 4
TORCH_FRAC = 0.75  # torch height as a fraction of the icon (Play keyline grid)

ANDROID_NS = '{http://schemas.android.com/apk/res/android}'

# Legacy (pre-adaptive) mipmap densities: unused at minSdk 26 but kept in sync
# with the adaptive icon so nothing stale ships in the APK.
DENSITIES = {'mdpi': 48, 'hdpi': 72, 'xhdpi': 96, 'xxhdpi': 144, 'xxxhdpi': 192}


def load_paths():
    """Return [(fill_color, svgpathtools.Path)] from the vector drawable."""
    tree = ET.parse(FOREGROUND_XML)
    out = []
    for el in tree.getroot().iter():
        d = el.get(ANDROID_NS + 'pathData')
        if d:
            out.append((el.get(ANDROID_NS + 'fillColor'), parse_path(d)))
    return out


def path_bbox(paths):
    xmin = ymin = float('inf')
    xmax = ymax = float('-inf')
    for _, p in paths:
        x0, x1, y0, y1 = p.bbox()
        xmin, xmax = min(xmin, x0), max(xmax, x1)
        ymin, ymax = min(ymin, y0), max(ymax, y1)
    return xmin, ymin, xmax, ymax


def subpath_polygons(path, transform, samples_per_unit=2.0):
    """Flatten each closed subpath into a polygon point list (canvas coords)."""
    polys = []
    for sub in path.continuous_subpaths():
        pts = []
        for seg in sub:
            if isinstance(seg, Line):
                n = 1
            else:
                n = max(2, int(seg.length() * samples_per_unit))
            for i in range(n):
                z = seg.point(i / n)
                pts.append(transform(z.real, z.imag))
        if len(pts) >= 3:
            polys.append(pts)
    return polys


def to_gray(color):
    """Rec. 709 luminance of a #RRGGBB fill, as a gray hex color."""
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    y = round(0.2126 * r + 0.7152 * g + 0.0722 * b)
    return f'#{y:02X}{y:02X}{y:02X}'


def render_torch(size, torch_frac, paths, bbox, background=BACKGROUND,
                 color_fn=None):
    """Render the torch centered at torch_frac of canvas height; supersampled.

    background=None leaves the canvas transparent; color_fn remaps fill colors.
    """
    ss = size * SUPERSAMPLE
    img = Image.new('RGBA', (ss, ss), background or (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    xmin, ymin, xmax, ymax = bbox
    scale = ss * torch_frac / (ymax - ymin)  # torch is taller than wide
    cx, cy = (xmin + xmax) / 2, (ymin + ymax) / 2

    def tf(x, y):
        return ((x - cx) * scale + ss / 2, (y - cy) * scale + ss / 2)

    for color, path in paths:
        if color_fn:
            color = color_fn(color)
        for poly in subpath_polygons(path, tf, samples_per_unit=scale / 4):
            draw.polygon(poly, fill=color)
    return img.resize((size, size), Image.LANCZOS)


def mask_shape(img, shape):
    """Apply a rounded-square or circular alpha mask (for legacy launcher icons)."""
    size = img.size[0]
    mask = Image.new('L', (size * SUPERSAMPLE,) * 2, 0)
    d = ImageDraw.Draw(mask)
    full = size * SUPERSAMPLE - 1
    if shape == 'circle':
        d.ellipse([0, 0, full, full], fill=255)
    else:
        d.rounded_rectangle([0, 0, full, full], radius=int(full * 0.18), fill=255)
    img = img.copy()
    img.putalpha(mask.resize((size, size), Image.LANCZOS))
    return img


def generate_android(paths, bbox):
    # Play Store listing icon: 512px full square, opaque, torch on the vertical
    # keyline (75% of icon height), no rounding/shadow (Google Play adds them).
    # 32-bit PNG per spec: keep the (fully opaque) alpha channel.
    icon = render_torch(512, TORCH_FRAC, paths, bbox)
    icon.save(PLAY_ICON, 'PNG')
    print(f'wrote {os.path.relpath(PLAY_ICON, ROOT)} '
          f'({os.path.getsize(PLAY_ICON) // 1024}KB)')

    # Legacy mipmaps: match the adaptive icon's look (torch fills the same
    # fraction of the visible area as the 108dp foreground does after the
    # 72dp mask crop).
    torch_frac = (bbox[3] - bbox[1]) / 72.0
    for density, size in DENSITIES.items():
        base = render_torch(size, torch_frac, paths, bbox)
        for name, shape in (('ic_launcher', 'square'), ('ic_launcher_round', 'circle')):
            out = os.path.join(RES_DIR, f'mipmap-{density}', f'{name}.webp')
            mask_shape(base, shape).save(out, 'WEBP', lossless=True)
        print(f'wrote mipmap-{density} ({size}px)')


def generate_ios(paths, bbox):
    variants = [
        # (filename, appearance) -- appearance None = any/light
        ('icon-1024.png', None),
        ('icon-1024-dark.png', 'dark'),
        ('icon-1024-tinted.png', 'tinted'),
    ]
    for filename, appearance in variants:
        if appearance is None:
            # App Store icon: opaque, no alpha channel allowed.
            img = render_torch(1024, TORCH_FRAC, paths, bbox).convert('RGB')
        elif appearance == 'dark':
            # System supplies the dark backdrop; ship glyph on transparency.
            img = render_torch(1024, TORCH_FRAC, paths, bbox, background=None)
        else:
            # Tinted: grayscale glyph on transparency; system applies the tint.
            img = render_torch(1024, TORCH_FRAC, paths, bbox, background=None,
                               color_fn=to_gray)
        img.save(os.path.join(APPICONSET, filename), 'PNG')
        print(f'wrote AppIcon.appiconset/{filename}')

    contents = {
        'images': [
            {
                **({'appearances': [{'appearance': 'luminosity',
                                     'value': appearance}]} if appearance else {}),
                'filename': filename,
                'idiom': 'universal',
                'platform': 'ios',
                'size': '1024x1024',
            }
            for filename, appearance in variants
        ],
        'info': {'author': 'xcode', 'version': 1},
    }
    with open(os.path.join(APPICONSET, 'Contents.json'), 'w') as f:
        json.dump(contents, f, indent=2)
        f.write('\n')
    print('wrote AppIcon.appiconset/Contents.json')


def main():
    paths = load_paths()
    bbox = path_bbox(paths)
    generate_android(paths, bbox)
    generate_ios(paths, bbox)


if __name__ == '__main__':
    main()
