/** Passive dark-theme dots: accumulate coverage, blend format hues and brighten overlaps in OKLab.
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
    const pointVertex = `attribute vec2 position;
        attribute vec2 formatDirection;
        varying vec2 hueDirection;
        uniform float size;
        void main() {
            hueDirection = formatDirection;
            gl_Position = vec4(position, 0., 1.); gl_PointSize = size;
        }`;
    // Use a distinct vertex shader for the fullscreen pass. Some GPU drivers
    // retain point-shader attributes even when its varying is unused by the
    // fragment shader; feeding the quad to that layout causes INVALID_OPERATION.
    const compositeVertex = `attribute vec2 position;
        void main() { gl_Position = vec4(position, 0., 1.); }`;
    const densityFragment = `precision highp float;
        uniform float size;
        uniform float pixelRatio;
        varying vec2 hueDirection;
        void main() {
            float distance = length(gl_PointCoord - .5) * size;
            float radius = size * .5;
            float radial = distance / radius;
            float core = 1. - smoothstep(2. * pixelRatio, 3. * pixelRatio, distance);
            float halo = .55 * exp(-4.5 * radial * radial) * (1. - smoothstep(.5, 1., radial));
            float coverage = max(core, halo);
            // R/A accumulate density; G/B carry the coverage-weighted hue.
            gl_FragColor = vec4(1., hueDirection * .5 + .5, 1.) * coverage * (${densityUnits}. / 255.);
        }`;
    const colorFragment = `precision highp float;
        uniform sampler2D density;
        uniform vec2 resolution;
        vec3 toSrgb(vec3 c) {
            return mix(12.92 * c, 1.055 * pow(c, vec3(1. / 2.4)) - .055, step(vec3(.0031308), c));
        }
        vec3 labToLinearRgb(float L, vec2 ab) {
            vec3 lms = vec3(L + .3963377774 * ab.x + .2158037573 * ab.y,
                L - .1055613458 * ab.x - .0638541728 * ab.y,
                L - .0894841775 * ab.x - 1.2914855480 * ab.y);
            lms = lms * lms * lms;
            return vec3(dot(vec3(4.0767416621, -3.3077115913, .2309699292), lms),
                dot(vec3(-1.2684380046, 2.6097574011, -.3413193965), lms),
                dot(vec3(-.0041960863, -.7034186147, 1.7076147010), lms));
        }
        bool inGamut(vec3 rgb) {
            return all(greaterThanEqual(rgb, vec3(0.))) && all(lessThanEqual(rgb, vec3(1.)));
        }
        void main() {
            vec4 sampleColor = texture2D(density, gl_FragCoord.xy / resolution);
            if (sampleColor.r == 0.) { gl_FragColor = vec4(0.); return; }
            float count = sampleColor.r * (255. / ${densityUnits}.);
            float heat = pow(clamp((count - 1.) / 4., 0., 1.), .7);
            float L = .74 + .245 * heat;
            // Opposing hues lose chroma rather than choosing an unrelated hue.
            vec2 ab = (sampleColor.gb / sampleColor.r * 2. - 1.) * mix(${FormatColors.dotChroma}, .008, heat);
            vec3 rgb = labToLinearRgb(L, ab);
            if (!inGamut(rgb)) {
                // Match ColorUtils: reduce chroma, preserving hue and lightness.
                float lo = 0., hi = 1.;
                for (int i = 0; i < 10; i++) {
                    float mid = (lo + hi) * .5;
                    if (inGamut(labToLinearRgb(L, ab * mid))) lo = mid;
                    else hi = mid;
                }
                rgb = labToLinearRgb(L, ab * lo);
            }
            float alpha = (.7 + .29 * heat) * min(1., count);
            gl_FragColor = vec4(toSrgb(clamp(rgb, 0., 1.)) * alpha, alpha);
        }`;

    function create(getData) {
        let map, gl, dots, composite, buffer, quad, texture, framebuffer;
        let width = 0, height = 0, cameraKey, previousPlaces, previousPromoted;
        function program(fragment, vertex) {
            const shaders = [[gl.VERTEX_SHADER, vertex], [gl.FRAGMENT_SHADER, fragment]].map(([type, source]) => {
                const shader = gl.createShader(type); gl.shaderSource(shader, source); gl.compileShader(shader);
                if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(shader));
                return shader;
            });
            const p = gl.createProgram(); shaders.forEach(s => gl.attachShader(p, s)); gl.linkProgram(p);
            shaders.forEach(s => gl.deleteShader(s));
            if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p));
            return { p, vao: gl.createVertexArray(), position: gl.getAttribLocation(p, 'position'), direction: gl.getAttribLocation(p, 'formatDirection'), size: gl.getUniformLocation(p, 'size') };
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
            dots = program(densityFragment, pointVertex); composite = program(colorFragment, compositeVertex);
            dots.pixelRatio = gl.getUniformLocation(dots.p, 'pixelRatio');
            composite.density = gl.getUniformLocation(composite.p, 'density');
            composite.resolution = gl.getUniformLocation(composite.p, 'resolution');
            buffer = gl.createBuffer(); quad = gl.createBuffer();
            gl.bindBuffer(gl.ARRAY_BUFFER, quad);
            gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
            gl.activeTexture(gl.TEXTURE0);
            texture = newTexture();
            framebuffer = gl.createFramebuffer();
            width = height = 0; cameraKey = null;
        }
        function bind(p, b) {
            gl.useProgram(p.p); gl.bindVertexArray(p.vao); gl.bindBuffer(gl.ARRAY_BUFFER, b);
            const stride = p === dots ? 16 : 0;
            gl.enableVertexAttribArray(p.position); gl.vertexAttribPointer(p.position, 2, gl.FLOAT, false, stride, 0);
            if (p.direction >= 0) {
                gl.enableVertexAttribArray(p.direction); gl.vertexAttribPointer(p.direction, 2, gl.FLOAT, false, stride, 8);
            }
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
                    points.push(p.x / w * 2 - 1, 1 - p.y / h * 2, ...FormatColors.direction(place.formatCategory));
                }
                bind(dots, buffer);
                gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(points), gl.DYNAMIC_DRAW);
                gl.uniform1f(dots.size, 2 * radius * width / w);
                gl.uniform1f(dots.pixelRatio, width / w);
                gl.enable(gl.BLEND); gl.blendEquation(gl.FUNC_ADD); gl.blendFunc(gl.ONE, gl.ONE);
                gl.drawArrays(gl.POINTS, 0, points.length / 4);
                gl.bindVertexArray(null);
                gl.bindFramebuffer(gl.FRAMEBUFFER, oldFramebuffer); gl.viewport(...oldViewport);
            },
            render() {
                if (gl.isContextLost() || !width || !height) return;
                bind(composite, quad);
                gl.disable(gl.STENCIL_TEST); gl.disable(gl.DEPTH_TEST);
                gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, texture);
                gl.uniform1i(composite.density, 0);
                gl.uniform2f(composite.resolution, width, height);
                gl.enable(gl.BLEND); gl.blendEquation(gl.FUNC_ADD); gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
                gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
                gl.bindVertexArray(null); gl.activeTexture(gl.TEXTURE0);
            },
            onRemove() {
                map.off('webglcontextrestored', initialize);
                gl.deleteProgram(dots.p); gl.deleteProgram(composite.p);
                gl.deleteBuffer(buffer); gl.deleteBuffer(quad);
                gl.deleteVertexArray(dots.vao); gl.deleteVertexArray(composite.vao);
                gl.deleteTexture(texture); gl.deleteFramebuffer(framebuffer);
            }
        };
    }
    return { create, haloRadius };
})();
