const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const context = vm.createContext({});
for (const file of ['core/formatColors.js', 'map/dotDensityLayer.js']) {
    vm.runInContext(fs.readFileSync(path.join(__dirname, '..', file), 'utf8'), context);
}
const { create, haloRadius } = vm.runInContext('DotDensityLayer', context);
function harness({ retainUnusedAttributes = false } = {}) {
    const buffers = [], draws = [];
    let programId = 0, currentBuffer, currentVao, currentProgram;
    const gl = new Proxy({
        drawingBufferWidth: 100, drawingBufferHeight: 100,
        createShader: type => ({ type }),
        shaderSource: (shader, source) => { shader.source = source; },
        createProgram: () => ({ id: programId++, shaders: [] }),
        attachShader: (p, shader) => p.shaders.push(shader),
        createBuffer: () => ({ bytes: 0 }),
        bindBuffer: (_, buffer) => { currentBuffer = buffer; },
        createVertexArray: () => new Map(),
        bindVertexArray: vao => { currentVao = vao; },
        useProgram: p => { currentProgram = p; },
        enableVertexAttribArray() {},
        vertexAttribPointer: (index, size, type, normalized, stride, offset) => {
            currentVao.set(index, { buffer: currentBuffer, size, stride, offset });
        },
        getShaderParameter: () => true, getProgramParameter: () => true,
        getAttribLocation: (p, name) => {
            const shader = p.shaders.find(s => s.type === 'VERTEX_SHADER').source;
            if (!shader.includes(`attribute vec2 ${name};`)) return -1;
            if (p.id === 0) return name === 'position' ? 1 : 0;
            return name === 'position' ? 0 : retainUnusedAttributes ? 1 : -1;
        },
        getParameter: name => name === 'VIEWPORT' ? [0, 0, 100, 100] : null,
        isContextLost: () => false,
        bufferData: (_, data, usage) => {
            currentBuffer.bytes = data.byteLength;
            if (usage === 'DYNAMIC_DRAW') buffers.push([...data]);
        },
        drawArrays: (mode, start, count) => {
            if (count) for (const name of ['position', 'formatDirection']) {
                const index = gl.getAttribLocation(currentProgram, name);
                if (index < 0) continue;
                const a = currentVao.get(index);
                assert.ok(a, `missing ${name} attribute`);
                const required = a.offset + (start + count - 1) * (a.stride || a.size * 4) + a.size * 4;
                assert.ok(a.buffer.bytes >= required, `${name}: vertex buffer is not big enough (${a.buffer.bytes} < ${required})`);
            }
            draws.push({ mode, count });
        }
    }, { get: (target, key) => key in target ? target[key] : /^[A-Z0-9_]+$/.test(key) ? key : () => ({}) });
    const map = { on() {}, off() {},
        getCanvas: () => ({ clientWidth: 100, clientHeight: 100 }),
        getCenter: () => ({ toArray: () => [0, 0] }), getZoom: () => 12,
        getBearing: () => 0, getPitch: () => 0, getPadding: () => ({}),
        project: coordinates => ({ x: coordinates[0], y: coordinates[1] }) };
    let data = { places: [], promoted: new Set() };
    const layer = create(() => data); layer.onAdd(map, gl);
    return { layer, buffers, draws, set: value => { data = value; } };
}
test('dark dots carry each place format hue and exclude promoted/offscreen places', () => {
    const h = harness();
    const places = [
        { key: 'rose', coordinates: [50, 50], formatCategory: 'Social' },
        { key: 'neutral', coordinates: [60, 50], formatCategory: 'Other' },
        { key: 'promoted', coordinates: [50, 60], formatCategory: 'Performance' },
        { key: 'offscreen', coordinates: [200, 50], formatCategory: 'Participatory' }
    ];
    h.set({ places, promoted: new Set(['promoted']) }); h.layer.prerender();
    assert.equal(h.draws[0].count, 2);
    assert.deepEqual(h.buffers[0].slice(0, 4), [0, 0, 1, 0]);
    assert.deepEqual(h.buffers[0].slice(6, 8), [0, 0]);
    h.layer.prerender();
    assert.equal(h.buffers.length, 1, 'unchanged data reuses the density buffer');
    h.set({ places: [{ ...places[0], formatCategory: 'Browsable' }], promoted: new Set() });
    h.layer.prerender();
    assert.equal(h.buffers[1][2], -1, 'format changes invalidate the cached hue');
    h.layer.render(); h.layer.onRemove();
});
test('zooming out expands the heat halo while bounding its size', () => {
    assert.equal(haloRadius(12), 6);
    assert.ok(haloRadius(10) > haloRadius(12));
    assert.ok(haloRadius(16) < haloRadius(12));
    assert.equal(haloRadius(0), 10);
    assert.equal(haloRadius(24), 4);
});

test('fullscreen composite does not read point attributes retained by a GPU driver', () => {
    const h = harness({ retainUnusedAttributes: true });
    for (const count of [0, 1, 8, 0]) {
        h.set({ places: Array.from({ length: count }, (_, i) =>
            ({ key: String(i), coordinates: [50, 50], formatCategory: 'Performance' })), promoted: new Set() });
        h.layer.prerender();
        h.layer.render();
        assert.equal(h.draws.at(-1).count, 4, 'the fullscreen pass always has four valid vertices');
    }
    h.layer.onRemove();
});
