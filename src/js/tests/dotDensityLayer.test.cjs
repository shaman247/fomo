const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const context = vm.createContext({});
for (const file of ['core/colorUtils.js', 'map/dotDensityLayer.js']) {
    vm.runInContext(fs.readFileSync(path.join(__dirname, '..', file), 'utf8'), context);
}
const { palette, color, haloRadius } = vm.runInContext('({palette: DotDensityLayer.paletteBytes, color: ColorUtils, haloRadius: DotDensityLayer.haloRadius})', context);

test('overlap becomes near-white at five cores while single dots stay translucent teal', () => {
    const bytes = palette('#4b7d84');
    const hue = color.oklchHueFromHex('#4b7d84');
    let previous = 0;
    for (const count of [1, 2, 3, 4, 5]) {
        const offset = count * 40 * 4;
        const alpha = bytes[offset + 3] / 255;
        const rgb = Array.from(bytes.slice(offset, offset + 3), c => c / alpha);
        const oklch = color.rgbToOklch(...rgb);
        assert.ok(oklch.L > previous);
        if (count === 1) {
            assert.ok(Math.abs(alpha - .7) < .004);
            assert.ok(Math.abs(oklch.h - hue) < 4);
        }
        if (count === 5) {
            assert.ok(alpha > .98);
            assert.ok(oklch.L > .975);
            assert.ok(oklch.C < .015);
            // Actual premultiplied RGB stays nearly white even over black.
            assert.ok([...bytes.slice(offset, offset + 3)].every(c => c >= 240));
        }
        previous = oklch.L;
    }
    assert.deepEqual(Array.from(bytes.slice(0, 4)), [0, 0, 0, 0]);
});

test('radial edges fade smoothly and five-plus overlaps saturate safely', () => {
    const bytes = palette('#4b7d84');
    for (let i = 1; i < 256; i++) {
        const alpha = bytes[i * 4 + 3];
        assert.ok(alpha >= bytes[(i - 1) * 4 + 3]);
        for (let c = 0; c < 3; c++) assert.ok(bytes[i * 4 + c] <= alpha);
    }
    assert.deepEqual(Array.from(bytes.slice(200 * 4, 200 * 4 + 4)), Array.from(bytes.slice(255 * 4, 256 * 4)));
    assert.ok(bytes[4] > 0); // Preserve low-coverage halo contributions.
});

test('zooming out expands the heat halo while bounding its size', () => {
    assert.equal(haloRadius(12), 6);
    assert.ok(haloRadius(10) > haloRadius(12));
    assert.ok(haloRadius(16) < haloRadius(12));
    assert.equal(haloRadius(0), 10);
    assert.equal(haloRadius(24), 4);
});
