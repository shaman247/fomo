/** Stable experience-family hues. Type membership comes from the exported taxonomy. */
const FormatColors = (() => {
    const hues = Object.freeze({ Performance: 300, Social: 0, Participatory: 60,
        Outing: 120, Browsable: 180, Gathering: 240, Other: null });
    const dotChroma = .16;
    let categories = new Map();
    const colors = new Map();
    function configure(formats = {}) {
        categories = new Map(Object.entries(formats).flatMap(([category, types]) =>
            types.map(type => [type, Object.hasOwn(hues, category) ? category : 'Other'])));
    }
    const categoryFor = event => categories.get(event?.event_type) || 'Other';
    const hueFor = category => Object.hasOwn(hues, category) ? hues[category] : null;
    function color(category, lightness, chroma) {
        const hue = hueFor(category);
        const key = `${hue}|${lightness}|${chroma}`;
        if (!colors.has(key)) colors.set(key, ColorUtils.oklchToHex(lightness, hue === null ? 0 : chroma, hue ?? 0));
        return colors.get(key);
    }
    // Leave enough lightness headroom for vivid fills in both themes; the shared
    // converter reduces chroma at the sRGB boundary without shifting hue.
    function discColors(category, theme = Utils.getCurrentTheme()) {
        return theme === 'dark'
            ? { fill: '#222222', stroke: color(category, .68, .18) } // Matches dark --secondary-bg.
            : { fill: color(category, .90, .09), stroke: color(category, .72, .17) };
    }
    function dotColor(category, theme = Utils.getCurrentTheme()) {
        return color(category, theme === 'dark' ? .74 : .55, dotChroma);
    }
    function dotExpression(theme = Utils.getCurrentTheme()) {
        return ['match', ['get', 'formatCategory'],
            ...Object.keys(hues).flatMap(category => [category, dotColor(category, theme)]), dotColor('Other', theme)];
    }
    // Circular components let overlapping dark-map dots blend without a red/0° seam.
    function direction(category) {
        const hue = hueFor(category);
        return hue === null ? [0, 0] : [Math.cos(hue * Math.PI / 180), Math.sin(hue * Math.PI / 180)];
    }
    return { configure, categoryFor, discColors, dotColor, dotExpression, direction, dotChroma };
})();
