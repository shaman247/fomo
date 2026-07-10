/**
 * TagColorManager Module
 *
 * Manages tag color assignments and maintains the mapping between
 * selected tags and their assigned colors from the palette.
 *
 * Features:
 * - Assigns colors from theme-appropriate palette
 * - Tracks selected tags with their colors
 * - Handles color reuse when palette is exhausted
 * - Reassigns colors when theme changes
 * - Provides display order for selected tags
 *
 * @module TagColorManager
 */
const TagColorManager = (() => {
    // ========================================
    // STATE
    // ========================================

    /**
     * Module state
     */
    const state = {
        // Color palettes (injected during init)
        darkPalette: [],
        lightPalette: [],

        // Emoji-based color lookup
        tagEmojiMap: {},   // tag name -> emoji
        bgcolors: {},      // "<font>|<emoji>" -> hex color (runtime cache of live-extracted colors)

        // Selected tags with their assigned colors
        // Array of [tag, color] tuples, maintains selection order
        selectedTagsWithColors: []
    };

    // ========================================
    // UTILITY FUNCTIONS
    // ========================================

    /**
     * Gets the current theme
     * @returns {string} 'dark' or 'light'
     */
    function getCurrentTheme() {
        return Utils.getCurrentTheme();
    }

    /**
     * Gets the color palette for the current theme. Prototype themes may
     * supply their own palette; otherwise the theme's base picks dark/light.
     * @returns {Array<string>} Array of color hex codes
     */
    function getCurrentPalette() {
        const def = Themes.resolve(getCurrentTheme());
        if (def.tagPalette && def.tagPalette.length) return def.tagPalette;
        return def.base === 'light' ? state.lightPalette : state.darkPalette;
    }

    /**
     * Gets all currently used colors
     * @returns {Set<string>} Set of color hex codes
     */
    function getUsedColors() {
        return new Set(state.selectedTagsWithColors.map(([, color]) => color));
    }

    /**
     * Finds the first unused color in the palette
     * @returns {string|null} Color hex code or null if all colors are used
     */
    function findUnusedColor() {
        const palette = getCurrentPalette();
        const usedColors = getUsedColors();

        return palette.find(color => !usedColors.has(color)) || null;
    }

    /**
     * Returns the font-family string for the emoji font currently in use — the
     * single source of truth for emoji font resolution, also consumed by
     * MapManager._addEmojiImage when rendering map glyphs. When the user switches
     * to Noto, the body gets the `use-noto-emoji` class; otherwise the
     * platform/system emoji font (via `serif` fallback) is used. Sharing one
     * resolver keeps color extraction on the same font as the rendered glyph,
     * so the derived color matches it.
     * @returns {string} CSS font-family
     */
    function getActiveEmojiFont() {
        return (typeof document !== 'undefined' &&
                document.body && document.body.classList.contains('use-noto-emoji'))
            ? '"Noto Color Emoji"'
            : 'serif';
    }

    // OKLCH targets for the final emoji-derived color. Lightness and chroma are
    // pinned (only the hue, found below, varies per emoji) so every marker/chip
    // color reads as equally vivid regardless of hue — the same perceptual
    // normalization MapManager applies to event labels. Gamut-clamped per hue by
    // ColorUtils.oklchToHex, so unreachable chromas reduce gracefully.
    const MARKER_OKLCH_L = 0.62;
    const MARKER_OKLCH_C = 0.15;

    // Pixel clustering thresholds, in OKLab terms. Note OKLab chroma is numerically
    // ~10× smaller than HSL saturation — a glyph that reads as clearly colored (e.g.
    // 🎵) can have a max per-pixel chroma of only ~0.035, so these floors are far
    // lower than the old HSL s≈0.15 cutoff would suggest.
    const MIN_PIXEL_CHROMA = 0.02;   // reject achromatic (gray/white/black) pixels
    const MIN_PIXEL_L = 0.12;        // reject near-black outline pixels
    const MIN_RESULT_CHROMA = 0.015; // averaged result this gray ⇒ achromatic glyph (⚽) → fallback

    /**
     * Extracts a dominant color from an emoji by drawing it on canvas and analyzing pixels.
     * Renders with the active emoji font (system or Noto), so the result tracks the
     * glyph the viewer actually sees. Callers go through getColorForEmoji, which caches;
     * this function does the raw extraction.
     *
     * The dominant hue is found by clustering pixels into OKLCH hue buckets (weighted
     * by OKLab chroma²), and the final color is built in OKLCH (see MARKER_OKLCH_*
     * above) at a pinned lightness/chroma, so brightness/saturation are perceptually
     * uniform across hues.
     * @param {string} emoji - Emoji character(s)
     * @param {string} [fontFamily] - Font to render with; defaults to the active emoji font
     * @returns {string} Hex color code
     */
    function extractColorFromEmoji(emoji, fontFamily) {
        const size = 64;
        const canvas = document.createElement('canvas');
        canvas.width = size;
        canvas.height = size;
        const ctx = canvas.getContext('2d');
        ctx.font = size * 0.85 + 'px ' + (fontFamily || getActiveEmojiFont());
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(emoji, size / 2, size / 2);

        // Themed rendering knobs: the emoji transform must match what
        // MapManager._addEmojiImage draws so the derived color tracks the
        // glyph on screen; L/C pins and the achromatic fallback are also
        // theme-overridable (e.g. softer rings on parchment).
        const themeDef = Themes.resolve(Utils.getCurrentTheme());
        const fallback = themeDef.achromaticFallback || '#8899aa';
        const targetL = (themeDef.markerOklch && themeDef.markerOklch.L) || MARKER_OKLCH_L;
        const targetC = (themeDef.markerOklch && themeDef.markerOklch.C) || MARKER_OKLCH_C;

        let imageData = ctx.getImageData(0, 0, size, size);
        if (themeDef.emojiTransform) {
            imageData = EmojiTransforms.apply(imageData, themeDef.emojiTransform, 1);
        }
        const data = imageData.data;
        const buckets = new Array(36).fill(0);
        const bucketColors = Array.from({length: 36}, () => []);

        // Cluster pixels by perceptual (OKLCH) hue, weighting each by its OKLab
        // chroma² so the most colorful pixels dominate the pick. We reject only
        // achromatic pixels (chroma alone rejects white — we must NOT reject on
        // high L, since saturated yellow has L≈0.96) and near-black outline pixels.
        for (let i = 0; i < data.length; i += 4) {
            const r = data[i], g = data[i+1], b = data[i+2], a = data[i+3];
            if (a < 30) continue;
            const { L, C, h } = ColorUtils.rgbToOklch(r, g, b);
            if (C < MIN_PIXEL_CHROMA || L < MIN_PIXEL_L) continue;
            const bucket = Math.floor(h / 10) % 36;
            buckets[bucket] += C * C;
            bucketColors[bucket].push({r, g, b, c: C});
        }

        let best = 0, bestScore = 0;
        for (let i = 0; i < 36; i++) {
            const sc = buckets[(i+35)%36]*0.5 + buckets[i] + buckets[(i+1)%36]*0.5;
            if (sc > bestScore) { bestScore = sc; best = i; }
        }

        const nearby = [
            ...bucketColors[(best+35)%36],
            ...bucketColors[best],
            ...bucketColors[(best+1)%36]
        ];
        if (!nearby.length) return fallback;

        let sR=0, sG=0, sB=0, sW=0;
        nearby.forEach(c => {
            const w = c.c * c.c;
            sR += c.r*w; sG += c.g*w; sB += c.b*w; sW += w;
        });
        const aR = sR/sW, aG = sG/sW, aB = sB/sW;

        // Normalize the dominant color in OKLCH: keep its perceptual hue but pin
        // lightness and chroma to the (theme-overridable) targets; cached per
        // font+theme in getColorForEmoji. If the dominant color is itself
        // near-gray, the glyph is achromatic (e.g. ⚽) → fallback.
        const avg = ColorUtils.rgbToOklch(aR, aG, aB);
        if (avg.C < MIN_RESULT_CHROMA) return fallback;
        return ColorUtils.oklchToHex(targetL, targetC, avg.h);
    }

    /**
     * Resolves a color for an emoji, extracting it live from the rendered glyph on
     * first use and caching the result. There is no precomputed/curated table — the
     * viewer's own emoji font determines the color. The cache is keyed by font too,
     * so switching between system and Noto emoji yields (and retains) distinct colors
     * without stale hits.
     * @param {string} emoji - Emoji character(s)
     * @returns {string|null} Color hex code, or null if no emoji given
     */
    function getColorForEmoji(emoji) {
        if (!emoji) return null;
        const font = getActiveEmojiFont();
        // Theme participates in the key: emoji transforms and L/C overrides
        // change the derived color per theme (dark/light share values but
        // recompute once each — cheap, and keeps invalidation trivial).
        const key = font + '|' + getCurrentTheme() + '|' + emoji;
        if (state.bgcolors[key]) return state.bgcolors[key];  // cache hit
        const color = extractColorFromEmoji(emoji, font);
        state.bgcolors[key] = color;
        return color;
    }

    /**
     * Resolves a color for a tag via its emoji. Themes whose emoji transform
     * collapses hue (cyanotype, newsprint) opt out with chipColors:'palette'
     * so chip colors come from their palette and stay distinguishable.
     * @param {string} tag - Tag name
     * @returns {string|null} Color hex code, or null if the tag has no emoji
     */
    function getEmojiBgColor(tag) {
        if (Themes.resolve(getCurrentTheme()).chipColors === 'palette') return null;
        return getColorForEmoji(state.tagEmojiMap[tag]);
    }

    /**
     * Gets a color for a new tag assignment
     * Uses first unused color, or wraps around if palette is exhausted
     * @returns {string} Color hex code
     */
    function getNextColor() {
        const palette = getCurrentPalette();

        // Try to find unused color
        const unusedColor = findUnusedColor();
        if (unusedColor) {
            return unusedColor;
        }

        // All colors used, wrap around
        const colorIndex = state.selectedTagsWithColors.length % palette.length;
        return palette[colorIndex];
    }

    // ========================================
    // COLOR MANAGEMENT
    // ========================================

    /**
     * Gets the assigned color for a tag
     * @param {string} tag - Tag name
     * @returns {string|null} Color hex code or null if tag is not selected
     */
    function getTagColor(tag) {
        const entry = state.selectedTagsWithColors.find(([t]) => t === tag);
        return entry ? entry[1] : null;
    }

    /**
     * Assigns a color to a tag
     * If tag already has a color, does nothing
     * @param {string} tag - Tag name
     * @returns {string} The assigned color
     */
    function assignColorToTag(tag) {
        // Check if already assigned
        const existingEntry = state.selectedTagsWithColors.find(([t]) => t === tag);
        if (existingEntry) {
            return existingEntry[1];
        }

        // Prefer emoji bgcolor, fall back to palette
        const color = getEmojiBgColor(tag) || getNextColor();
        state.selectedTagsWithColors.push([tag, color]);

        return color;
    }

    /**
     * Removes color assignment from a tag
     * @param {string} tag - Tag name
     * @returns {boolean} True if tag was found and removed, false otherwise
     */
    function unassignColorFromTag(tag) {
        const index = state.selectedTagsWithColors.findIndex(([t]) => t === tag);

        if (index > -1) {
            state.selectedTagsWithColors.splice(index, 1);
            return true;
        }

        return false;
    }

    /**
     * Reassigns colors to all selected tags using the current theme's palette
     * Maintains the selection order but updates colors
     * Used when theme changes
     */
    function reassignTagColors() {
        const palette = getCurrentPalette();
        let paletteIndex = 0;

        state.selectedTagsWithColors.forEach((entry) => {
            // Keep emoji bgcolors (theme-independent); reassign palette colors
            const emojiBg = getEmojiBgColor(entry[0]);
            if (emojiBg) {
                entry[1] = emojiBg;
            } else {
                entry[1] = palette[paletteIndex % palette.length];
                paletteIndex++;
            }
        });
    }

    // ========================================
    // QUERY FUNCTIONS
    // ========================================

    /**
     * Gets all tags with their colors
     * @returns {Array<[string, string]>} Array of [tag, color] tuples
     */
    function getSelectedTagsWithColors() {
        return [...state.selectedTagsWithColors];
    }

    // ========================================
    // PUBLIC API
    // ========================================

    /**
     * Initializes the TagColorManager module
     * @param {Object} config - Configuration object
     * @param {Array<string>} config.darkPalette - Color palette for dark theme
     * @param {Array<string>} config.lightPalette - Color palette for light theme
     */
    function init(config) {
        state.darkPalette = config.darkPalette || [];
        state.lightPalette = config.lightPalette || [];
        state.tagEmojiMap = config.tagEmojiMap || {};
        // Colors are derived live from each emoji's rendered pixels (see
        // getColorForEmoji), reflecting the viewer's active emoji font. bgcolors is
        // purely a runtime cache keyed by "<font>|<emoji>"; it starts empty.
        state.bgcolors = {};
        state.selectedTagsWithColors = [];
    }

    // ========================================
    // EXPORTS
    // ========================================

    return {
        // Initialization
        init,

        // Color management
        getColorForEmoji,
        getTagColor,
        assignColorToTag,
        unassignColorFromTag,
        reassignTagColors,

        // Query functions
        getSelectedTagsWithColors,

        // Emoji font resolution (single source — consumed by MapManager._addEmojiImage)
        getActiveEmojiFont
    };
})();
