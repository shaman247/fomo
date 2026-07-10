/**
 * Themes Registry
 *
 * Single source of truth for every UI theme. `dark` and `light` are the
 * built-in production themes; entries with `proto: true` are prototype
 * themes selectable only via the prototype picker / ?theme= URL param.
 *
 * Loaded before every other module (pure data, no dependencies) so anything
 * can consult it. All fields except label/base are optional — an absent
 * field means "behave like the base theme":
 *
 *   label            display name for pickers
 *   base             'dark' | 'light' — what unconverted binary code should
 *                    assume (CSS reads it via the data-theme-base attr)
 *   proto            true for prototype themes (never in share URLs by default)
 *   mapStyle         style JSON URL; absent → base's MAP_STYLE_DARK/LIGHT
 *   tagPalette       chip/tag color array; absent → base's palette
 *   marker           {label, hoverLabel, halo, eventLabelL} map-label overrides
 *   emojiTransform   EmojiTransforms spec applied to rasterized emoji markers
 *   uiFontLoad       document.fonts.load() spec awaited before map glyphs
 *                    rasterize (themes with a custom webfont only)
 *   mapLabelFont     MapLibre fontstack for marker labels; absent → Inter
 *   chipColors       'emoji' (default: chip colors derived from emoji pixels)
 *                    | 'palette' (skip emoji derivation — for themes whose
 *                    emoji transform collapses hue)
 *   achromaticFallback  ring color for near-gray emoji; absent → default
 *   markerOklch      {L, C} overrides for marker-ring color normalization
 *   ringGlow         true → soft glow on marker highlight rings
 *
 * @module Themes
 */
const Themes = (() => {
    const REGISTRY = {
        dark: { label: 'Dark', base: 'dark', builtin: true },
        light: { label: 'Light', base: 'light', builtin: true },

        'warm-cozy': {
            label: 'Warm & Cozy', base: 'dark', proto: true,
            mapStyle: 'data/map-style-warm-cozy.json?v=1',
            tagPalette: ['#c96f4a', '#b8563e', '#d99a3d', '#a87f3a', '#8f9a4a',
                '#5f8f6a', '#4f7d8c', '#8a6aa0', '#b05f7d', '#c98a68'],
            marker: { label: '#f2e3cd', hoverLabel: '#fff6e6', halo: '#201713' },
            emojiTransform: { type: 'sepia', params: { strength: 0.35 } },
            markerOklch: { L: 0.64, C: 0.11 }
        },

        'vintage-paper-map': {
            label: 'Vintage Paper Map', base: 'light', proto: true,
            mapStyle: 'data/map-style-vintage-paper-map.json?v=1',
            tagPalette: ['#a5533f', '#5f7a52', '#4f6b8a', '#8a6f3f', '#7d5a7d',
                '#647d74', '#9a744a', '#6b5540', '#8a4f5f', '#54657d'],
            marker: { label: '#3a2f21', hoverLabel: '#241c11', halo: '#efe5cf' },
            emojiTransform: { type: 'sepia', params: { strength: 0.85 } },
            markerOklch: { L: 0.55, C: 0.09 }
        },

        'neon-night-transit': {
            label: 'Neon Night Transit', base: 'dark', proto: true,
            mapStyle: 'data/map-style-neon-night-transit.json?v=1',
            tagPalette: ['#ff4fd8', '#00e5c3', '#ffd60a', '#7c4dff', '#ff5c5c',
                '#38b6ff', '#a3ff4f', '#ff8f3d', '#4fffa3', '#ff4f8f'],
            marker: { label: '#e9e4ff', hoverLabel: '#ffffff', halo: '#0d0b16' },
            emojiTransform: { type: 'duotone', params: { shadow: '#171233', highlight: '#e6e1ff', blend: 0.45 } },
            markerOklch: { L: 0.7, C: 0.19 },
            ringGlow: true
        },

        '16-bit-pixel': {
            label: '16-Bit Pixel', base: 'dark', proto: true,
            mapStyle: 'data/map-style-16-bit-pixel.json?v=1',
            tagPalette: ['#ef7d57', '#ffcd75', '#a7f070', '#38b764', '#29adff',
                '#4d6ae0', '#b13e53', '#ff77a8', '#73eff7', '#a884f3'],
            marker: { label: '#f4f4f4', hoverLabel: '#ffffff', halo: '#1a1c2c' },
            emojiTransform: { type: 'pixelate', params: { block: 4, posterize: 6 } },
            uiFontLoad: '14px "Pixelify Sans"',
            mapLabelFont: ['Pixelify Sans Regular']
        },

        blueprint: {
            label: 'Blueprint', base: 'dark', proto: true,
            mapStyle: 'data/map-style-blueprint.json?v=1',
            tagPalette: ['#7fd1ff', '#4f9fe0', '#a8c4e0', '#ffd166', '#ff9f66',
                '#8fe0c8', '#c8a8f0', '#e08fb8', '#d0e08f', '#66b8d8'],
            marker: { label: '#dbe9f7', hoverLabel: '#ffffff', halo: '#0f2a4a' },
            emojiTransform: { type: 'duotone', params: { shadow: '#0f2a4a', highlight: '#eaf4ff', blend: 0 } },
            chipColors: 'palette',
            achromaticFallback: '#7fd1ff'
        },

        'newsprint-zine': {
            label: 'Newsprint Zine', base: 'light', proto: true,
            mapStyle: 'data/map-style-newsprint-zine.json?v=1',
            tagPalette: ['#d92b2b', '#191919', '#6e6e6e', '#a81f1f', '#3d3d3d',
                '#8f8578', '#5a1414', '#996a5c', '#4a443a', '#b5442b'],
            marker: { label: '#191919', hoverLabel: '#000000', halo: '#f4f1ea' },
            emojiTransform: { type: 'duotone', params: { shadow: '#191919', highlight: '#f4f1ea', blend: 0, dither: true } },
            chipColors: 'palette',
            achromaticFallback: '#d92b2b'
        },

        'sticker-pop': {
            label: 'Sticker Pop', base: 'light', proto: true,
            mapStyle: 'data/map-style-sticker-pop.json?v=1',
            tagPalette: ['#ff5fa2', '#ff9f45', '#ffd23f', '#5fd068', '#4fc4e8',
                '#7a5cff', '#ff6b6b', '#3ec9a7', '#f78fb3', '#9b8cff'],
            marker: { label: '#33224a', hoverLabel: '#1e1230', halo: '#fdf6ef' },
            emojiTransform: { type: 'sticker', params: { outline: 3, color: '#ffffff', shadowAlpha: 0.22 } },
            markerOklch: { L: 0.66, C: 0.16 }
        }
    };

    const DEFAULT = 'dark';

    function isKnown(name) {
        return Object.prototype.hasOwnProperty.call(REGISTRY, name);
    }

    function resolve(name) {
        return REGISTRY[name] || REGISTRY[DEFAULT];
    }

    function baseOf(name) {
        return resolve(name).base || 'dark';
    }

    function list() {
        return Object.keys(REGISTRY).map(name => ({ name, ...REGISTRY[name] }));
    }

    /**
     * Stable key describing a theme's emoji-rendering recipe. Used to decide
     * whether a theme switch must re-rasterize marker images and to key the
     * emoji color-extraction cache.
     */
    function transformKey(name) {
        const t = resolve(name).emojiTransform;
        return t ? JSON.stringify(t) : 'none';
    }

    return { REGISTRY, DEFAULT, isKnown, resolve, baseOf, list, transformKey };
})();
