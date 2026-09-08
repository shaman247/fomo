/** Passive dark-theme dots: accumulate coverage, then color by OKLCH lightness.
 * Custom-layer API: https://maplibre.org/maplibre-gl-js/docs/API/interfaces/CustomLayerInterface/
 * No map-pixel readbacks or DOM overlays; the density buffer is cached until
 * the camera, viewport or eligible/promoted places change.
 */
const DotDensityLayer = (() => {
    const id = 'marker-dot-density';
    // Forty density units per full core leave room for >5 overlaps in RGBA8,
    // with enough precision to keep the low-opacity halo smooth.
    const densityUnits = 40;
    const haloRadius = zoom => Math.max(4, Math.min(10, 18 - zoom));
    const vertex = `attribute vec2 position;
        uniform float size;
        void main() { gl_Position = vec4(position, 0., 1.); gl_PointSize = size; }`;
    const densityFragment = `precision highp float;
        uniform float size;
        uniform float pixelRatio;
        void main() {
            float distance = length(gl_PointCoord - .5) * size;
            float radius = size * .5;
            float radial = distance / radius;
            float core = 1. - smoothstep(2. * pixelRatio, 3. * pixelRatio, distance);
            float halo = .55 * exp(-4.5 * radial * radial) * (1. - smoothstep(.5, 1., radial));
            float coverage = max(core, halo);
            gl_FragColor = vec4(coverage * (${densityUnits}. / 255.));
        }`;
    const colorFragment = `precision highp float;
        uniform sampler2D density;
        uniform sampler2D palette;
        uniform vec2 resolution;
        void main() {
            float count = texture2D(density, gl_FragCoord.xy / resolution).r;
            gl_FragColor = texture2D(palette, vec2((count * 255. + .5) / 256., .5));
        }`;

    function paletteBytes(hex) {
        const hue = ColorUtils.oklchHueFromHex(hex);
        const bytes = new Uint8Array(256 * 4);
        for (let i = 1; i < 256; i++) {
            const count = i / densityUnits;
            // Build rapidly from teal to nearly white at five overlapping cores.
            // Increasing opacity too makes the hotspot read white on a dark map.
            const heat = Math.pow(Math.max(0, Math.min(1, (count - 1) / 4)), .7);
            const L = .74 + .245 * heat;
            const C = hue === null ? 0 : .06 - .052 * heat;
            const color = ColorUtils.oklchToHex(L, C, hue || 0);
            const alpha = (.7 + .29 * heat) * Math.min(1, count);
            for (let c = 0; c < 3; c++) bytes[i * 4 + c] = Math.round(parseInt(color.slice(1 + c * 2, 3 + c * 2), 16) * alpha);
            bytes[i * 4 + 3] = Math.round(255 * alpha);
        }
        return bytes;
    }

    function create(getData, color) {
        let map, gl, dots, composite, buffer, quad, vao, texture, palette, framebuffer;
        let width = 0, height = 0, cameraKey, previousPlaces, previousPromoted;
        function program(fragment) {
            const shaders = [[gl.VERTEX_SHADER, vertex], [gl.FRAGMENT_SHADER, fragment]].map(([type, source]) => {
                const shader = gl.createShader(type); gl.shaderSource(shader, source); gl.compileShader(shader);
                if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(shader));
                return shader;
            });
            const p = gl.createProgram(); shaders.forEach(s => gl.attachShader(p, s)); gl.linkProgram(p);
            shaders.forEach(s => gl.deleteShader(s));
            if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p));
            return { p, position: gl.getAttribLocation(p, 'position'), size: gl.getUniformLocation(p, 'size') };
        }
        function newTexture() {
            const t = gl.createTexture(); gl.bindTexture(gl.TEXTURE_2D, t);
            gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
            gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
            gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
            gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
            return t;
        }
        function initialize() {
            dots = program(densityFragment); composite = program(colorFragment);
            dots.pixelRatio = gl.getUniformLocation(dots.p, 'pixelRatio');
            composite.density = gl.getUniformLocation(composite.p, 'density');
            composite.palette = gl.getUniformLocation(composite.p, 'palette');
            composite.resolution = gl.getUniformLocation(composite.p, 'resolution');
            buffer = gl.createBuffer(); quad = gl.createBuffer(); vao = gl.createVertexArray();
            gl.bindBuffer(gl.ARRAY_BUFFER, quad);
            gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
            gl.activeTexture(gl.TEXTURE0);
            texture = newTexture(); palette = newTexture();
            gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, 256, 1, 0, gl.RGBA, gl.UNSIGNED_BYTE, paletteBytes(color));
            framebuffer = gl.createFramebuffer();
            width = height = 0; cameraKey = null;
        }
        function bind(p, b) {
            gl.useProgram(p.p); gl.bindVertexArray(vao); gl.bindBuffer(gl.ARRAY_BUFFER, b);
            gl.enableVertexAttribArray(p.position); gl.vertexAttribPointer(p.position, 2, gl.FLOAT, false, 0, 0);
        }
        return {
            id, type: 'custom', renderingMode: '2d',
            onAdd(m, context) {
                map = m; gl = context; initialize();
                map.on('webglcontextrestored', initialize);
            },
            prerender() {
                if (gl.isContextLost()) return;
                const canvas = map.getCanvas(), w = canvas.clientWidth, h = canvas.clientHeight;
                if (!w || !h) return;
                const { places, promoted } = getData();
                const key = [map.getCenter().toArray(), map.getZoom(), map.getBearing(), map.getPitch(),
                    JSON.stringify(map.getPadding()), w, h, gl.drawingBufferWidth, gl.drawingBufferHeight].join('|');
                if (key === cameraKey && places === previousPlaces && promoted === previousPromoted) return;
                cameraKey = key; previousPlaces = places; previousPromoted = promoted;
                const oldFramebuffer = gl.getParameter(gl.FRAMEBUFFER_BINDING);
                const oldViewport = gl.getParameter(gl.VIEWPORT);
                gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, texture);
                if (width !== gl.drawingBufferWidth || height !== gl.drawingBufferHeight) {
                    width = gl.drawingBufferWidth; height = gl.drawingBufferHeight;
                    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, width, height, 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
                }
                gl.bindFramebuffer(gl.FRAMEBUFFER, framebuffer);
                gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, texture, 0);
                gl.viewport(0, 0, width, height);
                gl.disable(gl.SCISSOR_TEST); gl.disable(gl.STENCIL_TEST); gl.disable(gl.DEPTH_TEST);
                gl.colorMask(true, true, true, true); gl.clearColor(0, 0, 0, 0); gl.clear(gl.COLOR_BUFFER_BIT);
                const radius = haloRadius(map.getZoom());
                const points = [];
                for (const place of places) {
                    if (promoted.has(place.key)) continue;
                    const p = map.project(place.coordinates);
                    if (p.x < -radius || p.y < -radius || p.x > w + radius || p.y > h + radius) continue;
                    points.push(p.x / w * 2 - 1, 1 - p.y / h * 2);
                }
                bind(dots, buffer);
                gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(points), gl.DYNAMIC_DRAW);
                gl.uniform1f(dots.size, 2 * radius * width / w);
                gl.uniform1f(dots.pixelRatio, width / w);
                gl.enable(gl.BLEND); gl.blendEquation(gl.FUNC_ADD); gl.blendFunc(gl.ONE, gl.ONE);
                gl.drawArrays(gl.POINTS, 0, points.length / 2);
                gl.bindVertexArray(null);
                gl.bindFramebuffer(gl.FRAMEBUFFER, oldFramebuffer); gl.viewport(...oldViewport);
            },
            render() {
                if (gl.isContextLost() || !width || !height) return;
                bind(composite, quad);
                gl.disable(gl.STENCIL_TEST); gl.disable(gl.DEPTH_TEST);
                gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, texture);
                gl.activeTexture(gl.TEXTURE1); gl.bindTexture(gl.TEXTURE_2D, palette);
                gl.uniform1i(composite.density, 0); gl.uniform1i(composite.palette, 1);
                gl.uniform2f(composite.resolution, width, height);
                gl.enable(gl.BLEND); gl.blendEquation(gl.FUNC_ADD); gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
                gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
                gl.bindVertexArray(null); gl.activeTexture(gl.TEXTURE0);
            },
            onRemove() {
                map.off('webglcontextrestored', initialize);
                gl.deleteProgram(dots.p); gl.deleteProgram(composite.p);
                gl.deleteBuffer(buffer); gl.deleteBuffer(quad); gl.deleteVertexArray(vao);
                gl.deleteTexture(texture); gl.deleteTexture(palette); gl.deleteFramebuffer(framebuffer);
            }
        };
    }
    return { create, paletteBytes, haloRadius };
})();
