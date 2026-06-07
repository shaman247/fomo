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
        bgcolors: {},      // emoji -> hex color

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
        return document.documentElement.getAttribute('data-theme') || 'dark';
    }

    /**
     * Gets the color palette for the current theme
     * @returns {Array<string>} Array of color hex codes
     */
    function getCurrentPalette() {
        const theme = getCurrentTheme();
        return theme === 'dark' ? state.darkPalette : state.lightPalette;
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
     * Extracts a dominant color from an emoji by drawing it on canvas and analyzing pixels.
     * Result is cached in state.bgcolors for subsequent lookups.
     * @param {string} emoji - Emoji character(s)
     * @returns {string} Hex color code
     */
    function extractColorFromEmoji(emoji) {
        const size = 64;
        const canvas = document.createElement('canvas');
        canvas.width = size;
        canvas.height = size;
        const ctx = canvas.getContext('2d');
        ctx.font = size * 0.85 + 'px serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(emoji, size / 2, size / 2);

        const data = ctx.getImageData(0, 0, size, size).data;
        const buckets = new Array(36).fill(0);
        const bucketColors = Array.from({length: 36}, () => []);

        for (let i = 0; i < data.length; i += 4) {
            const r = data[i], g = data[i+1], b = data[i+2], a = data[i+3];
            if (a < 30) continue;
            const rn = r/255, gn = g/255, bn = b/255;
            const mx = Math.max(rn, gn, bn), mn = Math.min(rn, gn, bn);
            const l = (mx + mn) / 2, d = mx - mn;
            if (d < 0.05) continue;
            const s = l > 0.5 ? d / (2 - mx - mn) : d / (mx + mn);
            if (s < 0.15 || l < 0.08 || l > 0.92) continue;
            let h;
            if (mx === rn) h = ((gn - bn) / d + (gn < bn ? 6 : 0)) / 6;
            else if (mx === gn) h = ((bn - rn) / d + 2) / 6;
            else h = ((rn - gn) / d + 4) / 6;
            const bucket = Math.floor((h * 360) / 10) % 36;
            buckets[bucket] += s * s;
            bucketColors[bucket].push({r, g, b, s});
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
        if (!nearby.length) return '#8899aa';

        let sR=0, sG=0, sB=0, sW=0;
        nearby.forEach(c => {
            const w = c.s * c.s;
            sR += c.r*w; sG += c.g*w; sB += c.b*w; sW += w;
        });
        const aR = sR/sW, aG = sG/sW, aB = sB/sW;
        const rn2 = aR/255, gn2 = aG/255, bn2 = aB/255;
        const mx2 = Math.max(rn2,gn2,bn2), mn2 = Math.min(rn2,gn2,bn2);
        const d2 = mx2-mn2;
        let h2, s2;
        if (d2 === 0) { h2=0; s2=0; }
        else {
            const l2 = (mx2+mn2)/2;
            s2 = l2>0.5 ? d2/(2-mx2-mn2) : d2/(mx2+mn2);
            if (mx2===rn2) h2=((gn2-bn2)/d2+(gn2<bn2?6:0))/6;
            else if (mx2===gn2) h2=((bn2-rn2)/d2+2)/6;
            else h2=((rn2-gn2)/d2+4)/6;
        }

        const tS = Math.min(1, s2 * 1.6);
        // HSL to RGB
        const c2 = (1 - Math.abs(2*0.45 - 1)) * tS;
        const x2 = c2 * (1 - Math.abs((h2*6) % 2 - 1));
        const m2 = 0.45 - c2/2;
        let fr, fg, fb;
        const sector = Math.floor(h2 * 6) % 6;
        if (sector === 0) { fr=c2; fg=x2; fb=0; }
        else if (sector === 1) { fr=x2; fg=c2; fb=0; }
        else if (sector === 2) { fr=0; fg=c2; fb=x2; }
        else if (sector === 3) { fr=0; fg=x2; fb=c2; }
        else if (sector === 4) { fr=x2; fg=0; fb=c2; }
        else { fr=c2; fg=0; fb=x2; }
        const toHex = v => Math.round((v + m2) * 255).toString(16).padStart(2, '0');
        return '#' + toHex(fr) + toHex(fg) + toHex(fb);
    }

    /**
     * Gets the emoji bgcolor for a tag. Checks precomputed bgcolors first,
     * then extracts from canvas if the tag has an emoji but no precomputed color.
     * @param {string} tag - Tag name
     * @returns {string|null} Color hex code or null if tag has no emoji
     */
    function getColorForEmoji(emoji) {
        if (!emoji) return null;
        if (state.bgcolors[emoji]) return state.bgcolors[emoji];
        // Extract and cache
        const color = extractColorFromEmoji(emoji);
        state.bgcolors[emoji] = color;
        return color;
    }

    function getEmojiBgColor(tag) {
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

    /**
     * Clears all color assignments
     */
    function clearAll() {
        state.selectedTagsWithColors = [];
    }

    // ========================================
    // QUERY FUNCTIONS
    // ========================================

    /**
     * Gets all selected tags in selection order
     * @returns {Array<string>} Array of tag names
     */
    function getSelectedTags() {
        return state.selectedTagsWithColors.map(([tag]) => tag);
    }

    /**
     * Gets all tags with their colors
     * @returns {Array<[string, string]>} Array of [tag, color] tuples
     */
    function getSelectedTagsWithColors() {
        return [...state.selectedTagsWithColors];
    }

    /**
     * Gets the number of selected tags
     * @returns {number} Count of selected tags
     */
    function getSelectedTagCount() {
        return state.selectedTagsWithColors.length;
    }

    /**
     * Checks if a tag is selected
     * @param {string} tag - Tag name
     * @returns {boolean} True if tag is selected
     */
    function isTagSelected(tag) {
        return state.selectedTagsWithColors.some(([t]) => t === tag);
    }

    /**
     * Gets color statistics for debugging/monitoring
     * @returns {Object} Object with color usage stats
     */
    function getColorStats() {
        const palette = getCurrentPalette();
        const usedColors = getUsedColors();

        return {
            theme: getCurrentTheme(),
            paletteSize: palette.length,
            tagCount: state.selectedTagsWithColors.length,
            uniqueColorsUsed: usedColors.size,
            allColorsUsed: usedColors.size >= palette.length
        };
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
        state.bgcolors = config.bgcolors || {};
        state.selectedTagsWithColors = [];
    }

    /**
     * Resets the manager to initial state
     */
    function reset() {
        state.selectedTagsWithColors = [];
    }

    // ========================================
    // EXPORTS
    // ========================================

    return {
        // Initialization
        init,
        reset,

        // Color management
        getColorForEmoji,
        getTagColor,
        assignColorToTag,
        unassignColorFromTag,
        reassignTagColors,
        clearAll,

        // Query functions
        getSelectedTags,
        getSelectedTagsWithColors,
        getSelectedTagCount,
        isTagSelected,
        getColorStats,

        // Utility (exposed for testing/debugging)
        getCurrentTheme,
        getCurrentPalette
    };
})();
