/**
 * EmojiTransforms Module
 *
 * Deterministic pixel-level transforms applied to canvas-rasterized emoji
 * before they are uploaded as MapLibre images (and, in parallel, before
 * TagColorManager extracts marker colors from the same pixels — keeping
 * ring/label colors consistent with the transformed glyphs by construction).
 *
 * All transforms operate directly on ImageData. ctx.filter is deliberately
 * NOT used (inconsistent Safari support); results are identical across
 * browsers and device pixel ratios.
 *
 * Spec format: { type, params } — see individual transforms.
 *
 * @module EmojiTransforms
 */
const EmojiTransforms = (() => {
    // 4×4 ordered-dither thresholds (Bayer matrix), normalized 0..1
    const BAYER_4 = [
        [0.5 / 16, 8.5 / 16, 2.5 / 16, 10.5 / 16],
        [12.5 / 16, 4.5 / 16, 14.5 / 16, 6.5 / 16],
        [3.5 / 16, 11.5 / 16, 1.5 / 16, 9.5 / 16],
        [15.5 / 16, 7.5 / 16, 13.5 / 16, 5.5 / 16]
    ];

    function _hexToRgb(hex) {
        const h = hex.replace('#', '');
        const full = h.length === 3 ? h.split('').map(c => c + c).join('') : h;
        const n = parseInt(full, 16);
        return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
    }

    function _luminance(r, g, b) {
        return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
    }

    /**
     * Classic sepia matrix, lerped with the original by `strength` (0..1).
     * strength 0.35 = warm cast; 0.85 = full antique plate.
     */
    function _sepia(data, { strength = 0.8 }) {
        const s = Math.max(0, Math.min(1, strength));
        for (let i = 0; i < data.length; i += 4) {
            if (data[i + 3] === 0) continue;
            const r = data[i], g = data[i + 1], b = data[i + 2];
            const sr = Math.min(255, 0.393 * r + 0.769 * g + 0.189 * b);
            const sg = Math.min(255, 0.349 * r + 0.686 * g + 0.168 * b);
            const sb = Math.min(255, 0.272 * r + 0.534 * g + 0.131 * b);
            data[i] = r + (sr - r) * s;
            data[i + 1] = g + (sg - g) * s;
            data[i + 2] = b + (sb - b) * s;
        }
    }

    /**
     * Luminance ramp between two colors.
     *   shadow/highlight: hex endpoints of the ramp
     *   blend: 0..1 — how much of the ORIGINAL color to mix back in
     *          (0 = pure duotone, ~0.45 = tinted but hue survives)
     *   dither: true → 2-level Bayer halftone instead of a smooth ramp
     */
    function _duotone(data, { shadow = '#000000', highlight = '#ffffff', blend = 0, dither = false }, width) {
        const lo = _hexToRgb(shadow);
        const hi = _hexToRgb(highlight);
        const keep = Math.max(0, Math.min(1, blend));
        for (let i = 0; i < data.length; i += 4) {
            if (data[i + 3] === 0) continue;
            let lum = _luminance(data[i], data[i + 1], data[i + 2]);
            if (dither) {
                const p = i / 4;
                const x = p % width;
                const y = (p / width) | 0;
                lum = lum >= BAYER_4[y % 4][x % 4] ? 1 : 0;
            }
            for (let c = 0; c < 3; c++) {
                const ramp = lo[c] + (hi[c] - lo[c]) * lum;
                data[i + c] = ramp + (data[i + c] - ramp) * keep;
            }
        }
    }

    /**
     * Block-averaging pixelation (no canvas redraw — identical everywhere).
     *   block: cell size in CSS px (multiplied by dpr internally so 1× and
     *          2× screens produce the same visual chunkiness)
     *   posterize: optional levels-per-channel quantization for a retro ramp
     */
    function _pixelate(imageData, { block = 4, posterize = 0 }, dpr) {
        const { data, width, height } = imageData;
        const cell = Math.max(2, Math.round(block * dpr));
        const post = posterize >= 2 ? posterize : 0;
        const step = post ? 255 / (post - 1) : 0;
        for (let by = 0; by < height; by += cell) {
            for (let bx = 0; bx < width; bx += cell) {
                const maxY = Math.min(by + cell, height);
                const maxX = Math.min(bx + cell, width);
                // Alpha-weighted color average — plain averaging would drag
                // edge cells toward black via their transparent pixels.
                let r = 0, g = 0, b = 0, a = 0, n = 0;
                for (let y = by; y < maxY; y++) {
                    for (let x = bx; x < maxX; x++) {
                        const i = (y * width + x) * 4;
                        const pa = data[i + 3];
                        r += data[i] * pa;
                        g += data[i + 1] * pa;
                        b += data[i + 2] * pa;
                        a += pa;
                        n++;
                    }
                }
                const avgA = a / n;
                let cr = 0, cg = 0, cb = 0;
                if (a > 0) {
                    cr = r / a;
                    cg = g / a;
                    cb = b / a;
                    if (post) {
                        cr = Math.round(cr / step) * step;
                        cg = Math.round(cg / step) * step;
                        cb = Math.round(cb / step) * step;
                    }
                }
                // Cells below ~15% coverage clear entirely — crisp silhouette
                const outA = avgA < 38 ? 0 : Math.round(avgA);
                for (let y = by; y < maxY; y++) {
                    for (let x = bx; x < maxX; x++) {
                        const i = (y * width + x) * 4;
                        data[i] = cr;
                        data[i + 1] = cg;
                        data[i + 2] = cb;
                        data[i + 3] = outA;
                    }
                }
            }
        }
    }

    /**
     * Die-cut sticker outline via alpha dilation.
     *   outline: silhouette thickness in CSS px (× dpr internally)
     *   color: outline color (typically white)
     *   shadowAlpha: optional 0..0.3 — darker rim just outside the outline
     * Original pixels stay untouched; only transparent pixels near opaque
     * ones are filled, so color extraction keeps rejecting the (achromatic)
     * outline and ring colors stay true to the emoji.
     */
    function _sticker(imageData, { outline = 3, color = '#ffffff', shadowAlpha = 0 }, dpr) {
        const { data, width, height } = imageData;
        const r = Math.max(1, Math.round(outline * dpr));
        const rimW = shadowAlpha > 0 ? Math.max(1, Math.round(dpr)) : 0;
        const rTotal = r + rimW;
        const [or, og, ob] = _hexToRgb(color);

        // Pass 1: solidity mask (original alpha above threshold)
        const solid = new Uint8Array(width * height);
        for (let p = 0, i = 3; p < solid.length; p++, i += 4) {
            if (data[i] > 40) solid[p] = 1;
        }

        // Pass 2: for each transparent pixel, Chebyshev-scan for the nearest
        // solid pixel within rTotal. Canvas is 128² max — brute window is fine.
        for (let y = 0; y < height; y++) {
            for (let x = 0; x < width; x++) {
                const p = y * width + x;
                if (solid[p]) continue;
                let best = Infinity;
                const y0 = Math.max(0, y - rTotal), y1 = Math.min(height - 1, y + rTotal);
                const x0 = Math.max(0, x - rTotal), x1 = Math.min(width - 1, x + rTotal);
                for (let yy = y0; yy <= y1 && best > r; yy++) {
                    const dy = Math.abs(yy - y);
                    const row = yy * width;
                    for (let xx = x0; xx <= x1; xx++) {
                        if (!solid[row + xx]) continue;
                        const d = Math.max(dy, Math.abs(xx - x));
                        if (d < best) {
                            best = d;
                            if (best <= r) break;
                        }
                    }
                }
                if (best <= r) {
                    const i = p * 4;
                    data[i] = or;
                    data[i + 1] = og;
                    data[i + 2] = ob;
                    data[i + 3] = 255;
                } else if (best <= rTotal) {
                    const i = p * 4;
                    data[i] = 0;
                    data[i + 1] = 0;
                    data[i + 2] = 0;
                    data[i + 3] = Math.round(255 * shadowAlpha);
                }
            }
        }
    }

    function _desaturate(data, { amount = 1 }) {
        const s = Math.max(0, Math.min(1, amount));
        for (let i = 0; i < data.length; i += 4) {
            if (data[i + 3] === 0) continue;
            const gray = _luminance(data[i], data[i + 1], data[i + 2]) * 255;
            data[i] += (gray - data[i]) * s;
            data[i + 1] += (gray - data[i + 1]) * s;
            data[i + 2] += (gray - data[i + 2]) * s;
        }
    }

    /**
     * Applies a transform spec to an ImageData in place and returns it.
     * Null/unknown specs are a no-op (returns the input unchanged).
     *
     * @param {ImageData} imageData - pixels to transform (mutated)
     * @param {?Object} spec - {type, params} from a Themes registry entry
     * @param {number} dpr - device pixel ratio the canvas was rendered at
     * @returns {ImageData}
     */
    function apply(imageData, spec, dpr) {
        if (!imageData || !spec || !spec.type) return imageData;
        const params = spec.params || {};
        const ratio = dpr || 1;
        switch (spec.type) {
            case 'sepia':
                _sepia(imageData.data, params);
                break;
            case 'duotone':
                _duotone(imageData.data, params, imageData.width);
                break;
            case 'pixelate':
                _pixelate(imageData, params, ratio);
                break;
            case 'sticker':
                _sticker(imageData, params, ratio);
                break;
            case 'desaturate':
                _desaturate(imageData.data, params);
                break;
            default:
                break;
        }
        return imageData;
    }

    return { apply };
})();
