/**
 * ColorUtils Module
 *
 * Shared OKLCH/OKLab color helpers (Björn Ottosson's sRGB ↔ OKLab matrices).
 *
 * We normalize colors in OKLab/OKLCH rather than HSL because HSL "lightness"
 * is not perceptually uniform — yellow at L=52% reads far brighter than blue
 * at the same L. In OKLCH, fixing L and C and varying only the hue yields
 * colors that actually look equally bright/saturated across hues. This module
 * is the single home for that math, shared by the emoji-derived marker/chip
 * colors (TagColorManager) and the event-label recoloring (MapManager).
 *
 * @module ColorUtils
 */
const ColorUtils = (() => {
    function srgbToLinear(c) {
        return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
    }
    function linearToSrgb(c) {
        return c <= 0.0031308 ? 12.92 * c : 1.055 * Math.pow(c, 1 / 2.4) - 0.055;
    }

    /**
     * sRGB (0–255 channels) → OKLCH { L (0..1), C (chroma), h (degrees 0..360) }.
     * h is meaningless when C is ~0 (achromatic) — callers should gate on C.
     * @param {number} r255
     * @param {number} g255
     * @param {number} b255
     * @returns {{L: number, C: number, h: number}}
     */
    function rgbToOklch(r255, g255, b255) {
        const r = srgbToLinear(r255 / 255);
        const g = srgbToLinear(g255 / 255);
        const b = srgbToLinear(b255 / 255);
        const l_ = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
        const m_ = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
        const s_ = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
        const L = 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_;
        const a = 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_;
        const bb = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_;
        const C = Math.hypot(a, bb);
        let h = Math.atan2(bb, a) * 180 / Math.PI;
        if (h < 0) h += 360;
        return { L, C, h };
    }

    /**
     * OKLCH hue (degrees) of a hex color, or null if (near-)achromatic.
     * @param {string} hexColor - e.g. "#3a7" or "#33aa77"
     * @returns {number|null} hue in [0, 360), or null when there's no usable chroma
     */
    function oklchHueFromHex(hexColor) {
        const hex = (hexColor || '#888').replace(/^#/, '');
        const full = hex.length === 3 ? hex.split('').map(c => c + c).join('') : hex;
        const { C, h } = rgbToOklch(
            parseInt(full.slice(0, 2), 16),
            parseInt(full.slice(2, 4), 16),
            parseInt(full.slice(4, 6), 16)
        );
        return C < 1e-4 ? null : h;
    }

    /**
     * OKLCH (L 0..1, C, h°) → sRGB hex, reducing chroma until the color fits the
     * sRGB gamut so fixed-C inputs always produce a valid, near-uniform color.
     * @param {number} L - lightness, 0..1
     * @param {number} C - chroma (≈0–0.37); gamut-clamped per hue
     * @param {number} h - hue in degrees
     * @returns {string} sRGB hex (parsed equally well by CSS and MapLibre)
     */
    function oklchToHex(L, C, h) {
        const hr = h * Math.PI / 180, ca = Math.cos(hr), cb = Math.sin(hr);
        const linAt = (c) => {
            const a = c * ca, b = c * cb;
            const l = Math.pow(L + 0.3963377774 * a + 0.2158037573 * b, 3);
            const m = Math.pow(L - 0.1055613458 * a - 0.0638541728 * b, 3);
            const s = Math.pow(L - 0.0894841775 * a - 1.2914855480 * b, 3);
            return [
                4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
                -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
                -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s
            ];
        };
        const inGamut = (rgb) => rgb.every(v => v >= -1e-4 && v <= 1 + 1e-4);
        let lin = linAt(C);
        if (!inGamut(lin)) {
            let lo = 0, hi = C;
            for (let i = 0; i < 18; i++) {
                const mid = (lo + hi) / 2;
                if (inGamut(linAt(mid))) lo = mid; else hi = mid;
            }
            lin = linAt(lo);
        }
        const toHex = (v) => {
            const s = linearToSrgb(Math.min(1, Math.max(0, v)));
            return Math.round(s * 255).toString(16).padStart(2, '0');
        };
        return '#' + toHex(lin[0]) + toHex(lin[1]) + toHex(lin[2]);
    }

    return { srgbToLinear, linearToSrgb, rgbToOklch, oklchHueFromHex, oklchToHex };
})();
