"""Compact curves from rendered color masks, with safe underpainting.

Later layers cover any extra paint added beneath them. Polygon simplification,
curve fitting, and coordinate quantization are the only geometric approximations.
"""
from pathlib import Path
from types import SimpleNamespace
import re
import numpy as np
from PIL import Image
from shapely.geometry import box, Polygon
from shapely.ops import unary_union

def fit_color_regions(input_path, tolerance=0.45, min_area=0.3, palette_distance=22, eye_centers=()):
    """Fit a single transparent layer into compact SVG paths.

Merge nearby colors, allow earlier paint to extend beneath later paint,
and fit recursive least-squares Bezier curves. Visible geometry is only
approximated by the requested tolerance and quarter-unit coordinates.
The jazz face-paint color gets round small eye dots to avoid triangular eyes.
Returns path elements and retained region count; no raster is embedded."""
    a = SimpleNamespace(input=Path(input_path), tolerance=tolerance, min_area=min_area, palette_distance=palette_distance)
    im = np.asarray(Image.open(a.input).convert('RGBA'))
    h, w = im.shape[:2]
    scale = 128 / w
    packed = im[:, :, 0].astype(np.int32) << 16 | im[:, :, 1].astype(np.int32) << 8 | im[:, :, 2].astype(np.int32)
    vals, counts = np.unique(packed[im[:, :, 3] > 0], return_counts=True)

    def rgb(k):
        return np.array([int(k) >> 16 & 255, int(k) >> 8 & 255, int(k) & 255], float)
    clusters = []
    for i in np.argsort(-counts):
        value = int(vals[i])
        target = next((c for c in clusters if np.linalg.norm(rgb(value) - rgb(c['color'])) <= a.palette_distance), None)
        if target:
            target['values'].append(value)
            target['count'] += int(counts[i])
        else:
            clusters.append({'color': value, 'values': [value], 'count': int(counts[i])})

    def unit(v):
        return v / max(np.linalg.norm(v), 1e-12)

    def cubic(b, u):
        q = 1 - u
        return q[:, None] ** 3 * b[0] + 3 * (q * q * u)[:, None] * b[1] + 3 * (q * u * u)[:, None] * b[2] + u[:, None] ** 3 * b[3]

    def fit(pts, t1, t2, depth=0):
        if len(pts) < 2:
            return []
        start, end = (pts[0], pts[-1])
        delta = end - start
        length = np.linalg.norm(delta)
        if length > 1e-09:
            u = np.clip((pts - start) @ delta / (length * length), 0, 1)
            if np.max(np.linalg.norm(pts - start - u[:, None] * delta, axis=1)) <= a.tolerance:
                return [('L', end)]
        if len(pts) == 2:
            return [('L', end)]
        lengths = np.linalg.norm(np.diff(pts, axis=0), axis=1)
        u = np.r_[0, np.cumsum(lengths)]
        u /= max(u[-1], 1e-10)
        q = 1 - u
        A = 3 * (q * q * u)[:, None] * t1
        B = 3 * (q * u * u)[:, None] * t2
        rhs = pts - ((q ** 3 + 3 * q * q * u)[:, None] * start + (3 * q * u * u + u ** 3)[:, None] * end)
        lhs = np.array([[np.sum(A * A), np.sum(A * B)], [np.sum(A * B), np.sum(B * B)]])
        v = np.array([np.sum(A * rhs), np.sum(B * rhs)])
        try:
            alpha = np.linalg.solve(lhs, v)
        except np.linalg.LinAlgError:
            alpha = [length / 3] * 2
        if min(alpha) < 1e-05 or max(alpha) > length * 2:
            alpha = [length / 3] * 2
        b = np.array([start, start + t1 * alpha[0], end + t2 * alpha[1], end])
        errors = np.linalg.norm(cubic(b, u) - pts, axis=1)
        idx = int(np.argmax(errors))
        if errors[idx] <= a.tolerance or depth > 20:
            return [('C', b[1], b[2], end)]
        idx = max(1, min(len(pts) - 2, idx))
        t = unit(pts[idx - 1] - pts[idx + 1])
        return fit(pts[:idx + 1], t1, t, depth + 1) + fit(pts[idx:], -t, t2, depth + 1)

    def number(x):
        s = str(round(x))
        if s in ['-0', '']:
            s = '0'
        return s[1:] if s.startswith('0.') else '-' + s[2:] if s.startswith('-0.') else s

    def pairs(points):
        return ' '.join((number(x) for p in points for x in p))

    def ring(coords):
        pts = np.asarray(coords[:-1], float) * scale
        n = len(pts)
        if n < 3:
            return ''
        corners = []
        for i in range(n):
            before = unit(pts[i] - pts[i - 1])
            after = unit(pts[(i + 1) % n] - pts[i])
            if np.dot(before, after) < 0.7:
                corners.append(i)
        if len(corners) < 2:
            corners = sorted(set(corners + [0, n // 4, n // 2, 3 * n // 4]))
        cmds = []
        current = pts[corners[0]].copy()
        d = 'M' + pairs([current * 4])
        for i, start in enumerate(corners):
            end = corners[(i + 1) % len(corners)]
            indices = np.arange(start, end + 1 if end > start else end + n + 1) % n
            seg = pts[indices]
            for cmd in fit(seg, unit(seg[1] - seg[0]), unit(seg[-2] - seg[-1])):
                if cmd[0] == 'C':
                    b = np.array([current, *cmd[1:]])
                    control = (3 * b[1] - b[0] + 3 * b[2] - b[3]) / 4
                    qb = np.array([b[0], b[0] + 2 / 3 * (control - b[0]), b[3] + 2 / 3 * (control - b[3]), b[3]])
                    if np.max(np.linalg.norm(cubic(b, np.linspace(0, 1, 15)) - cubic(qb, np.linspace(0, 1, 15)), axis=1)) < 0.2:
                        cmd = ('Q', control, b[3])
                absolute = cmd[0] + pairs([x * 4 for x in cmd[1:]])
                relative = cmd[0].lower() + pairs([(x - current) * 4 for x in cmd[1:]])
                d += min([absolute, relative], key=len)
                current = np.array([round(x * 4) / 4 for x in cmd[-1]])
        return re.sub(' (?=-)', '', d) + 'Z'
    paths = []
    regions = 0
    originals = []
    for c in clusters:
        mask = np.isin(packed, c['values']) & (im[:, :, 3] > 0)
        rects = []
        for y in np.flatnonzero(mask.any(axis=1)):
            changes = np.diff(np.r_[False, mask[y], False].astype(np.int8))
            starts = np.flatnonzero(changes == 1)
            ends = np.flatnonzero(changes == -1)
            rects.extend((box(int(x0), int(y), int(x1), int(y) + 1) for x0, x1 in zip(starts, ends)))
        originals.append(unary_union(rects).simplify(1.7, preserve_topology=True))
    future = []
    allowed = Polygon()
    for geom in originals[::-1]:
        allowed = allowed.union(geom)
        future.append(allowed)
    future.reverse()
    for c, geom, allowed in zip(clusters, originals, future):
        polys = [geom] if isinstance(geom, Polygon) else list(geom.geoms)
        hulls = unary_union([poly.convex_hull for poly in polys if isinstance(poly, Polygon)])
        geom = hulls.intersection(allowed).simplify(1.7, preserve_topology=True)
        polys = [geom] if isinstance(geom, Polygon) else list(geom.geoms)
        parts = []
        for poly in polys:
            if poly.area * scale * scale < a.min_area:
                continue
            xmin, ymin, xmax, ymax = poly.bounds
            width, height = ((xmax - xmin) * scale, (ymax - ymin) * scale)
            eye_color = any((np.linalg.norm(rgb(value) - [81, 60, 49]) < 2 for value in c['values']))
            center = np.array([(xmin + xmax) * scale / 2, (ymin + ymax) * scale / 2])
            at_eye = any(np.linalg.norm(center - e) < .4 for e in eye_centers)
            if eye_color and at_eye and 0.5 < width / max(height, 1e-09) < 1.6 and (poly.area * scale * scale < 1.4):
                cx, cy = (round((xmin + xmax) * scale * 2), round((ymin + ymax) * scale * 2))
                rx, ry = (max(1, round(width * 2)), max(1, round(height * 2)))
                parts.append(f'M{cx - rx} {cy}a{rx} {ry} 0 1 0 {2 * rx} 0a{rx} {ry} 0 1 0-{2 * rx} 0Z')
            else:
                parts.append(ring(poly.exterior.coords))
                parts.extend((ring(hole.coords) for hole in poly.interiors if Polygon(hole).area * scale * scale >= a.min_area))
            regions += 1
        if parts:
            col = f"#{c['color']:06x}"
            paths.append(f'<path fill="{col}" stroke="{col}" d="' + ''.join(parts) + '"/>')
    return (paths, regions)
