const esbuild = require('esbuild');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const yaml = require('yaml');

const SRC = path.join(__dirname, 'src');
const DIST = path.join(__dirname, 'dist');
const FLATPICKR_JS = path.join(__dirname, 'node_modules', 'flatpickr', 'dist', 'flatpickr.js');
const FLATPICKR_CSS = path.join(__dirname, 'node_modules', 'flatpickr', 'dist', 'flatpickr.css');

// City/region config (config/<FOMO_CITY>.yaml, default "nyc") — the single source of
// truth shared with the backend. Its `frontend` block is injected into the build.
const FOMO_CITY = process.env.FOMO_CITY || 'nyc';
const CITY_CONFIG_PATH = path.join(__dirname, 'config', `${FOMO_CITY}.yaml`);

// Directories to include in dist/ (everything the server needs)
const ASSET_DIRS = ['data', 'images', 'fonts', 'api', 'admin', 'vendor'];

// Generated data files are gitignored (the pipeline rewrites them every run). Each has a
// committed `<name>.example.json` fallback so a fresh checkout — with no pipeline export yet —
// still builds a functioning app. Map: live filename -> example filename (both under src/data/).
const EXAMPLE_DATA_FILES = { 'tag_hierarchy.json': 'tag_hierarchy.example.json' };

// Load and validate the full city config (frontend block + shared data like geotags).
function loadCityConfig() {
    const cfg = yaml.parse(fs.readFileSync(CITY_CONFIG_PATH, 'utf8')) || {};
    const fe = cfg.frontend || {};
    if (!fe.map || !fe.map.center) {
        throw new Error(`config/${FOMO_CITY}.yaml is missing a frontend.map.center`);
    }
    return cfg;
}

// The frontend fetches data/tags.json at runtime for the geotag picker and to hide
// neighborhood names from event tag displays. Its `geotags` are city data, so they
// live in config/<FOMO_CITY>.yaml (the single source of truth, shared with the
// backend via city_config.py) and are written here at build time rather than
// committed. `bgcolors` is a frontend runtime cache, always emitted empty.
function writeGeneratedTagsJson(cfg) {
    const geotags = cfg.geotags || [];
    const out = path.join(SRC, 'data', 'tags.json');
    fs.writeFileSync(out, JSON.stringify({ geotags, bgcolors: {} }, null, 2) + '\n');
}

// Runtime values injected as a window.__CITY__ global at the head of the JS bundle,
// so they're available before any IIFE module evaluates.
function cityPrelude(fe, isDev) {
    const jsSubset = {
        map: {
            center: fe.map.center,
            zoom: fe.map.zoom,
        },
        timezone: fe.timezone,
        // Service worker opt-out: config frontend.sw_enabled: false, or any dev
        // build (dev also emits the self-unregistering sw.js — see emitServiceWorker).
        swEnabled: !isDev && fe.sw_enabled !== false,
    };
    return `;window.__CITY__ = ${JSON.stringify(jsSubset)};\n`;
}

// Emit dist/sw.js from the src/sw.js template: inject the precache manifest
// (split into immutable hashed/versioned URLs vs unversioned ones the SW must
// revalidate at install) and a version hash so any shell change produces a
// byte-different sw.js → the browser reinstalls the precache. Disabled builds
// (dev, or frontend.sw_enabled: false) emit the same file as a "killer" that
// wipes all SW caches and unregisters itself — the rescue path for a bad SW.
function emitServiceWorker({ htmlSource, frontend, jsBundleName, cssBundleName, isDev }) {
    const disabled = isDev || frontend.sw_enabled === false;

    // Versioned vendor URLs exactly as index.html references them (?v=…).
    const vendorUrls = [...new Set(
        [...htmlSource.matchAll(/"(vendor\/[^"]+)"/g)].map(m => m[1])
    )];

    const immutable = [
        jsBundleName,
        cssBundleName,
        ...vendorUrls,
        'fonts/inter/InterVariable.woff2',
        'fonts/inter/InterVariable-Italic.woff2',
        'images/torch.svg',
        'images/trumpet.svg',
    ];
    // NOTE: fonts/NotoColorEmoji-COLRv1.woff2 (2 MB) is deliberately NOT
    // precached — it only loads when the user opts into Noto emoji, and the
    // SW's runtime-static cache picks it up on first use.
    const revalidate = [
        'index.html',
        'about.html',
        'privacy.html',
        'data/map-style-light.json',
        'data/map-style-dark.json',
    ];

    // Version over everything precache-relevant: bundle names cover JS/CSS
    // content; style bytes are hashed directly (they're revalidate-class, so
    // their content doesn't change the manifest itself).
    const versionHash = crypto.createHash('md5');
    versionHash.update(JSON.stringify({ immutable, revalidate, disabled }));
    versionHash.update(htmlSource);
    for (const style of ['map-style-light.json', 'map-style-dark.json']) {
        const stylePath = path.join(SRC, 'data', style);
        if (fs.existsSync(stylePath)) versionHash.update(fs.readFileSync(stylePath));
    }

    const sw = fs.readFileSync(path.join(SRC, 'sw.js'), 'utf8')
        .replace('__SW_VERSION__', versionHash.digest('hex').slice(0, 8))
        .replace('__SW_DISABLED__', String(disabled))
        .replace('__PRECACHE_IMMUTABLE__', JSON.stringify(immutable))
        .replace('__PRECACHE_REVALIDATE__', JSON.stringify(revalidate));
    fs.writeFileSync(path.join(DIST, 'sw.js'), sw);
    return disabled;
}

// Replace {{TOKEN}} branding placeholders, then fail the build on any leftover token.
function applyBranding(html, fe) {
    const tokens = {
        '{{SITE_NAME}}': fe.site_name,
        '{{DOMAIN}}': fe.domain,
        '{{EMOJI}}': fe.emoji,
        '{{WELCOME_MODAL}}': fe.welcome_modal,
    };
    for (const [token, value] of Object.entries(tokens)) {
        html = html.split(token).join(value);
    }
    const leftover = html.match(/\{\{[A-Z_]+\}\}/);
    if (leftover) {
        throw new Error(`Unreplaced branding token ${leftover[0]} — add it to config/${FOMO_CITY}.yaml frontend block`);
    }
    return html;
}

function copyDirSync(src, dest) {
    fs.mkdirSync(dest, { recursive: true });
    for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
        // Example files are a build-time fallback, not a shipped asset — keep them out of dist/.
        if (entry.name.endsWith('.example.json')) continue;
        const srcPath = path.join(src, entry.name);
        const destPath = path.join(dest, entry.name);
        if (entry.isDirectory()) {
            copyDirSync(srcPath, destPath);
        } else {
            fs.copyFileSync(srcPath, destPath);
        }
    }
}

// Ensure each generated data file exists, falling back to its committed example when the
// pipeline hasn't produced one yet (fresh checkout / fork). The live file, once present,
// is never overwritten — a real export always wins.
function ensureSeededData() {
    for (const [live, example] of Object.entries(EXAMPLE_DATA_FILES)) {
        const livePath = path.join(SRC, 'data', live);
        const examplePath = path.join(SRC, 'data', example);
        if (!fs.existsSync(livePath) && fs.existsSync(examplePath)) {
            fs.copyFileSync(examplePath, livePath);
            console.log(`  Seeded src/data/${live} from ${example} (no pipeline export found)`);
        }
    }
}

async function build(isDev) {
    const startTime = Date.now();

    // Load city/region config (map, timezone, branding, shared geotags).
    const cfg = loadCityConfig();
    const frontend = cfg.frontend;

    // Clean dist/
    if (fs.existsSync(DIST)) {
        fs.rmSync(DIST, { recursive: true });
    }
    fs.mkdirSync(DIST, { recursive: true });

    // Parse index.html to extract JS file list in load order
    const htmlSource = fs.readFileSync(path.join(SRC, 'index.html'), 'utf8');
    const jsFileRegex = /<script\s+src="(js\/[^"?]+)/g;
    const jsFiles = [];
    let match;
    while ((match = jsFileRegex.exec(htmlSource)) !== null) {
        jsFiles.push(match[1]);
    }

    if (jsFiles.length === 0) {
        throw new Error('No JS files found in index.html');
    }

    // Concatenate JS: flatpickr first, then app modules in order
    const flatpickrJs = fs.readFileSync(FLATPICKR_JS, 'utf8');
    let originalJsSize = 0;
    const appJs = jsFiles.map(f => {
        const filePath = path.join(SRC, f);
        const content = fs.readFileSync(filePath, 'utf8');
        originalJsSize += Buffer.byteLength(content, 'utf8');
        return content;
    }).join('\n;\n');
    // Prepend the city config global so it exists before any module evaluates.
    const concatenated = cityPrelude(frontend, isDev) + flatpickrJs + '\n;\n' + appJs;

    // Minify JS in prod, pass through in dev
    let jsContent;
    if (isDev) {
        // Dev-only: expose the App orchestrator (and via it state.map,
        // datePickerInstance, filtered-event arrays) on window for Playwright
        // UX verification. App is scoped inside the DOMContentLoaded closure,
        // so inject the handle there where it's in scope. Never in prod.
        jsContent = concatenated.replace(
            'App.init();',
            'App.init();\n    if (typeof window !== "undefined") window.__fomo = App;'
        );
    } else {
        const jsResult = await esbuild.transform(concatenated, {
            minify: true,
            target: ['es2020'],
        });
        jsContent = jsResult.code;
    }

    // Bundle CSS (esbuild resolves @import natively)
    const cssResult = await esbuild.build({
        entryPoints: [path.join(SRC, 'css', 'index.css')],
        bundle: true,
        minify: !isDev,
        write: false,
        external: ['*.ttf', '*.woff2'],
    });

    // Prepend flatpickr CSS
    const flatpickrCss = fs.readFileSync(FLATPICKR_CSS, 'utf8');
    let flatpickrCssOut;
    if (isDev) {
        flatpickrCssOut = flatpickrCss;
    } else {
        flatpickrCssOut = (await esbuild.transform(flatpickrCss, { loader: 'css', minify: true })).code;
    }
    let cssContent = flatpickrCssOut + cssResult.outputFiles[0].text;

    // Fix font path: source uses ../fonts/ (relative to css/), but bundled CSS is at root level
    cssContent = cssContent.replace(/\.\.\/fonts\//g, 'fonts/');

    // Generate filenames (content-hashed for prod, stable for dev)
    let jsBundleName, cssBundleName;
    if (isDev) {
        jsBundleName = 'app.js';
        cssBundleName = 'app.css';
    } else {
        const jsHash = crypto.createHash('md5').update(jsContent).digest('hex').slice(0, 8);
        const cssHash = crypto.createHash('md5').update(cssContent).digest('hex').slice(0, 8);
        jsBundleName = `app.${jsHash}.js`;
        cssBundleName = `app.${cssHash}.css`;
    }

    // Write bundles
    fs.writeFileSync(path.join(DIST, jsBundleName), jsContent);
    fs.writeFileSync(path.join(DIST, cssBundleName), cssContent);

    // Transform index.html
    let html = htmlSource;

    // Remove flatpickr CDN references (now bundled)
    html = html.replace(/\s*<link\s+rel="stylesheet"\s+href="https:\/\/cdn\.jsdelivr\.net\/npm\/flatpickr[^>]*>\s*\n?/, '\n');
    html = html.replace(/\s*<script\s+src="https:\/\/cdn\.jsdelivr\.net\/npm\/flatpickr[^>]*><\/script>\s*\n?/, '\n');

    // Replace CSS link with bundle
    html = html.replace(
        /<link\s+rel="stylesheet"\s+href="css\/index\.css">/,
        `<link rel="stylesheet" href="${cssBundleName}">`
    );

    // Replace all individual JS script tags with single bundle
    html = html.replace(
        /\n\s*<!-- Core -->[\s\S]*<script src="js\/[^"]*"><\/script>\s*/,
        `\n\n    <script src="${jsBundleName}"></script>\n`
    );

    // Inject city branding (must run last; fails the build on any leftover token).
    html = applyBranding(html, frontend);

    fs.writeFileSync(path.join(DIST, 'index.html'), html);

    // Copy about.html, privacy.html, and .htaccess
    fs.copyFileSync(path.join(SRC, 'about.html'), path.join(DIST, 'about.html'));
    fs.copyFileSync(path.join(SRC, 'privacy.html'), path.join(DIST, 'privacy.html'));
    fs.copyFileSync(path.join(SRC, '.htaccess'), path.join(DIST, '.htaccess'));
    if (isDev) {
        // Dev bundles use STABLE filenames (app.js/app.css), so the 1-year
        // ExpiresByType cache above would pin a stale bundle in the browser
        // for anyone serving dist/ through Apache/XAMPP — rebuilds would
        // appear to do nothing. Force revalidation on everything in dev.
        // (Prod is safe: bundle filenames are content-hashed.)
        fs.appendFileSync(path.join(DIST, '.htaccess'), `
# --- DEV BUILD ONLY (appended by build.js --dev) ---
# Stable dev filenames + long-lived caches pin stale bundles; disable caching.
<IfModule mod_headers.c>
    Header set Cache-Control "no-cache, must-revalidate"
</IfModule>
<IfModule mod_expires.c>
    ExpiresActive Off
</IfModule>
`);
    }

    // Emit the service worker (or its self-unregistering "killer" variant).
    const swDisabled = emitServiceWorker({ htmlSource, frontend, jsBundleName, cssBundleName, isDev });

    // Seed any missing generated data files before they get symlinked/copied below.
    ensureSeededData();

    // Generate src/data/tags.json from the city config (geotags live in config, not git).
    writeGeneratedTagsJson(cfg);

    // Copy asset directories into dist/
    // Dev: symlinks (fast, live updates); Prod: full copies (self-contained)
    for (const dir of ASSET_DIRS) {
        const target = path.join(SRC, dir);
        const link = path.join(DIST, dir);
        if (!fs.existsSync(target)) continue;
        if (isDev) {
            fs.symlinkSync(target, link);
        } else {
            copyDirSync(target, link);
        }
    }

    // Print summary
    const jsBundleSize = Buffer.byteLength(jsContent, 'utf8');
    const cssBundleSize = Buffer.byteLength(cssContent, 'utf8');
    const elapsed = Date.now() - startTime;
    const mode = isDev ? 'dev' : 'prod';

    console.log(`\n[${mode}] Build complete in ${elapsed}ms\n`);
    if (isDev) {
        console.log(`  JS:  ${jsFiles.length} files → ${(jsBundleSize / 1024).toFixed(1)} KB (${jsBundleName})`);
    } else {
        console.log(`  JS:  ${jsFiles.length} files, ${(originalJsSize / 1024).toFixed(1)} KB → ${(jsBundleSize / 1024).toFixed(1)} KB (${Math.round((1 - jsBundleSize / originalJsSize) * 100)}% smaller)`);
    }
    console.log(`  CSS: ${(cssBundleSize / 1024).toFixed(1)} KB (${cssBundleName})`);
    console.log(`  SW:  sw.js (${swDisabled ? 'DISABLED — self-unregistering' : 'enabled'})`);
    console.log(`  Output: dist/\n`);
}

// Watch mode: rebuild on file changes in src/js/ and src/css/
function watch() {
    let buildTimeout = null;
    const rebuild = () => {
        if (buildTimeout) clearTimeout(buildTimeout);
        buildTimeout = setTimeout(async () => {
            try {
                await build(true);
            } catch (err) {
                console.error('Build error:', err.message);
            }
        }, 50);
    };

    const watchDirs = [
        path.join(SRC, 'js'),
        path.join(SRC, 'css'),
    ];

    for (const dir of watchDirs) {
        fs.watch(dir, { recursive: true }, (event, filename) => {
            if (filename && /\.(js|css)$/.test(filename)) {
                console.log(`  Changed: ${filename}`);
                rebuild();
            }
        });
    }

    // Also watch index.html for structural changes
    fs.watch(path.join(SRC, 'index.html'), () => {
        console.log('  Changed: index.html');
        rebuild();
    });

    // Watch the city config so branding / map / timezone changes rebuild in dev.
    if (fs.existsSync(CITY_CONFIG_PATH)) {
        fs.watch(CITY_CONFIG_PATH, () => {
            console.log(`  Changed: config/${FOMO_CITY}.yaml`);
            rebuild();
        });
    }

    console.log('Watching for changes... (Ctrl+C to stop)\n');
}

// CLI
const args = process.argv.slice(2);
const isDev = args.includes('--dev');
const isWatch = args.includes('--watch');

build(isDev)
    .then(() => {
        if (isWatch) watch();
    })
    .catch(err => {
        console.error('Build failed:', err);
        process.exit(1);
    });
