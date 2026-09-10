"""Build the compact jazz SVG from the four depth-ordered 3D render layers.

Usage: python trace-icon.py DIRECTORY_WITH_LAYER_PNGS OUTPUT.svg
The layer order is checked against the full depth-buffer render by visual QA.
"""
import argparse
import json
from pathlib import Path
import re
from fit_contours import fit_color_regions

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('input', type=Path)
parser.add_argument('output', type=Path)
parser.add_argument('--tolerance', type=float, default=.45,
                    help='Curve-fitting error in 128-unit viewBox coordinates')
parser.add_argument('--min-area', type=float, default=.3,
                    help='Omit subpixel regions below this viewBox area')
parser.add_argument('--palette-distance', type=float, default=22,
                    help='Maximum RGB distance for merging nearby colors')
args = parser.parse_args()
paths, regions = [], 0
projection = json.loads((args.input / 'projection.json').read_text())
for name in ['stage', 'Drums', 'Keyboard', 'Bass']:
    file = args.input / f'layer-{name}.png'
    if not file.is_file():
        parser.error(f'Missing rendered layer: {file}')
    eyes = [[(e['ndc'][0] + 1) * 64, (1 - e['ndc'][1]) * 64]
            for e in projection['eye_centers'] if e['performer'] == name]
    pieces, count = fit_color_regions(file, args.tolerance, args.min_area,
                                     args.palette_distance, eyes)
    paths.extend(pieces)
    regions += count
# Each path supplies currentColor once; fill and stroke inherit that color.
# Four coordinate units per viewBox unit allow short integer path coordinates.
body = ''.join(paths)
body = re.sub(r'fill="(#[0-9a-f]+)" stroke="\1"', r'color="\1"', body)
body = re.sub(r'l0(?: |(?=-))(-?\d+)', r'v\1', body)
body = re.sub(r'l(-?\d+) 0(?=[A-Za-z])', r'h\1', body)
svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128" '
       'stroke-width=".24" stroke-linejoin="round" fill-rule="evenodd" '
       'fill="currentColor" stroke="currentColor"><title>Jazz trio</title>'
       '<g transform="scale(.25)">' + body + '</g></svg>\n')
args.output.write_text(svg)
print(f'{len(paths)} color layers, {regions} regions, {len(svg.encode()):,} bytes.')
