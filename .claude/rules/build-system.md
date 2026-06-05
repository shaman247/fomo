---
paths:
  - "build.js"
  - "package.json"
  - "src/index.html"
  - "scripts/upload_public_html.py"
---

# Build System Details

## JS Build

- JS modules use IIFE pattern with globals — they are **concatenated** (not bundled) then minified via `esbuild.transform()`. esbuild's bundler mode would break global scope.
- `build.js` reads `src/index.html` to determine JS file order — no separate manifest
- flatpickr installed via npm, prepended to JS/CSS bundles

## CSS Build

- CSS `@import` chain resolved and minified via `esbuild.build()` with `bundle: true`
- Font path rewrite: `../fonts/` → `fonts/` (CSS moves from subdir to root in bundle)

## Dev vs Prod

- Dev (`npm run dev`): unminified, stable filenames, symlinks `data/`, `images/`, `fonts/`, `api/`, `admin/` from `dist/` → `src/`
- Prod (`npm run build`): minified, content-hashed filenames, copies those directories into `dist/`

## Deployment

```bash
npm run build                          # Build to dist/
python scripts/upload_public_html.py   # Upload dist/ to server via FTP
```

The upload script tracks file modification times in `scripts/upload_state.json` and only uploads changed files. Use `--force` to upload everything.
