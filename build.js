const esbuild = require('esbuild');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const SRC = path.join(__dirname, 'src');
const DIST = path.join(__dirname, 'dist');
const FLATPICKR_JS = path.join(__dirname, 'node_modules', 'flatpickr', 'dist', 'flatpickr.js');
const FLATPICKR_CSS = path.join(__dirname, 'node_modules', 'flatpickr', 'dist', 'flatpickr.css');

// Directories to include in dist/ (everything the server needs)
const ASSET_DIRS = ['data', 'images', 'fonts', 'api', 'admin'];

function copyDirSync(src, dest) {
    fs.mkdirSync(dest, { recursive: true });
    for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
        const srcPath = path.join(src, entry.name);
        const destPath = path.join(dest, entry.name);
        if (entry.isDirectory()) {
            copyDirSync(srcPath, destPath);
        } else {
            fs.copyFileSync(srcPath, destPath);
        }
    }
}

async function build(isDev) {
    const startTime = Date.now();

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
    const concatenated = flatpickrJs + '\n;\n' + appJs;

    // Minify JS in prod, pass through in dev
    let jsContent;
    if (isDev) {
        jsContent = concatenated;
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

    fs.writeFileSync(path.join(DIST, 'index.html'), html);

    // Copy about.html and .htaccess
    fs.copyFileSync(path.join(SRC, 'about.html'), path.join(DIST, 'about.html'));
    fs.copyFileSync(path.join(SRC, '.htaccess'), path.join(DIST, '.htaccess'));

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
