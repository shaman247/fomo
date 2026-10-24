/** Stable experience-family hues. Type membership comes from the exported taxonomy. */
const FormatColors = (() => {
    // Primaries go to the four largest families. Uniform lightness turns red coral,
    // blue periwinkle and yellow olive, so each hue carries the lift that keeps it
    // reading as itself: yellow only exists light, blue and red only deep.
    const hues = Object.freeze({ Performance: 29, Social: 335, Participatory: 92,
        Outing: 148, Browsable: 215, Gathering: 262, Other: null });
    const lifts = Object.freeze({ Performance: -.1, Social: -.04, Participatory: .13,
        Outing: -.04, Browsable: 0, Gathering: -.12 });
    const dotChroma = .18;
    let categories = new Map();
    const colors = new Map();
    function configure(formats = {}) {
        categories = new Map(Object.entries(formats).flatMap(([category, types]) =>
            types.map(type => [type, Object.hasOwn(hues, category) ? category : 'Other'])));
    }
    const categoryFor = event => categories.get(event?.event_type) || 'Other';
    const hueFor = category => Object.hasOwn(hues, category) ? hues[category] : null;
    // Darkening is halved on the dark map, where deep red and blue lose contrast.
    function lift(category, theme) {
        const value = lifts[category] || 0;
        return theme === 'dark' && value < 0 ? value / 2 : value;
    }
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
            ? { fill: '#222222', stroke: color(category, .68 + lift(category, theme), .2) } // Matches dark --secondary-bg.
            : { fill: color(category, .90, .09), stroke: color(category, .72 + lift(category, theme), .2) };
    }
    function dotColor(category, theme = Utils.getCurrentTheme()) {
        return color(category, (theme === 'dark' ? .74 : .55) + lift(category, theme), dotChroma);
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
