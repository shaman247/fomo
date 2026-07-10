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
        light: { label: 'Light', base: 'light', builtin: true }
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
