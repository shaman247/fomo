const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
function setup() {
    const context = vm.createContext({ Utils: { getCurrentTheme: () => 'light' } });
    for (const file of ['core/colorUtils.js', 'core/formatColors.js']) {
        vm.runInContext(fs.readFileSync(path.join(__dirname, '..', file), 'utf8'), context);
    }
    return vm.runInContext('({ palette: FormatColors, color: ColorUtils })', context);
}
test('only the canonical format controls hue, including shared topic names and missing formats', () => {
    const { palette } = setup();
    palette.configure({ Performance: ['Concert', 'Sports'], Participatory: ['Fitness'], Outing: ['Outing', 'Tour'] });
    assert.equal(palette.categoryFor({ event_type: 'Fitness', tags: ['Sports', 'Concert'] }), 'Participatory');
    assert.equal(palette.categoryFor({ event_type: 'Tour' }), 'Outing');
    for (const event of [null, {}, { tags: ['Concert'] }, { event_type: 'Other' }, { event_type: '__proto__' }]) {
        assert.equal(palette.categoryFor(event), 'Other');
    }
    palette.configure({ Performance: ['New format'] });
    assert.equal(palette.categoryFor({ event_type: 'New format' }), 'Performance');
    assert.equal(palette.categoryFor({ event_type: 'Concert' }), 'Other');
});
test('all six category colors preserve their hues across themes and unknown formats are neutral', () => {
    const { palette, color } = setup();
    for (const [category, hue] of Object.entries({ Performance: 300, Social: 0, Participatory: 60, Outing: 120, Browsable: 180, Gathering: 240 })) {
        for (const theme of ['light', 'dark']) {
            for (const hex of [...Object.values(palette.discColors(category, theme)), palette.dotColor(category, theme)]) {
                const actual = color.oklchHueFromHex(hex);
                const error = Math.abs((actual - hue + 540) % 360 - 180);
                assert.ok(error < 4, `${category} ${theme}: ${hex} hue ${actual}`);
            }
        }
    }
    for (const theme of ['light', 'dark']) {
        for (const hex of [...Object.values(palette.discColors('Other', theme)), palette.dotColor('Other', theme)]) {
            const rgb = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16));
            assert.ok(Math.max(...rgb) - Math.min(...rgb) <= 1);
        }
    }
});
