const ErrorReporter = (() => {
    // Beacons uncaught errors, unhandled rejections and console.error calls to
    // api/client_errors.php, so breakage that only shows on devices unlike the
    // developer's (fractional devicePixelRatio, another timezone) is visible
    // without a bug report. Loaded first so it sees every later module's
    // evaluation. Read the log with scripts/client_errors.py.
    //
    // Privacy: no cookies, no IDs, no user input beyond the error text itself,
    // and every URL is cut to its file name (no host, path, query or fragment).

    const ENDPOINT = 'api/client_errors.php';
    const MAX_REPORTS_PER_PAGE = 5;
    const SEEN_KEY = 'errorReporterSeen';

    // currentScript is only set while the bundle evaluates, so read it now.
    const script = document.currentScript;
    const bundleMatch = script && /\/app\.([0-9a-f]{8})\.js/.exec(script.src);
    const bundle = bundleMatch ? bundleMatch[1] : (script && /\/app\.js$/.test(script.src) ? 'dev' : 'unbundled');

    let sentCount = 0;
    let sending = false;
    const seen = new Set();
    try {
        for (const signature of JSON.parse(sessionStorage.getItem(SEEN_KEY) || '[]')) seen.add(signature);
    } catch (e) { /* storage blocked: dedupe per page only */ }

    // Any URL → its last path segment; keeps ":line:col" suffixes.
    const URL_PATTERN = /\b(?:https?|file|blob|webpack|[a-z]+-extension):\/\/[^\s()'"<>]*/gi;
    const fileName = url => url.replace(/[?#].*$/, m => (m.match(/(:\d+){1,2}$/) || [''])[0]).replace(/^.*\//, '');
    const scrub = (text, max) => String(text == null ? '' : text).replace(URL_PATTERN, fileName).slice(0, max);
    const fromExtension = text => /\b[a-z]+-extension:\/\//i.test(text || '');

    function report(kind, message, source, stack) {
        if (sending || sentCount >= MAX_REPORTS_PER_PAGE || !navigator.sendBeacon) return;
        if (fromExtension(source) || fromExtension(stack)) return;
        // Opaque cross-origin errors carry nothing actionable.
        if (!message || (message === 'Script error.' && !source)) return;

        const payload = {
            kind,
            message: scrub(message, 300),
            source: scrub(source, 120),
            stack: scrub(stack, 800).split('\n').slice(0, 6).join('\n'),
            bundle,
            dpr: window.devicePixelRatio || 1,
            tz: (() => { try { return Intl.DateTimeFormat().resolvedOptions().timeZone || ''; } catch (e) { return ''; } })(),
            viewport: `${window.innerWidth}x${window.innerHeight}`,
            ua: navigator.userAgent.slice(0, 300),
            path: location.pathname.slice(0, 100)
        };
        const signature = `${kind}|${payload.message}|${payload.source}`;
        if (seen.has(signature)) return;
        seen.add(signature);
        try { sessionStorage.setItem(SEEN_KEY, JSON.stringify([...seen].slice(-50))); } catch (e) { /* ignore */ }

        sending = true;
        try {
            if (navigator.sendBeacon(ENDPOINT, JSON.stringify(payload))) sentCount++;
        } catch (e) { /* never let reporting throw */ }
        sending = false;
    }

    const position = (file, line, col) => (file ? `${file}:${line || 0}:${col || 0}` : '');

    window.addEventListener('error', event => {
        // Resource load failures (img/script 404) bubble here without a message.
        if (!event.message) return;
        report('error', event.message, position(event.filename, event.lineno, event.colno), event.error && event.error.stack);
    });

    window.addEventListener('unhandledrejection', event => {
        const reason = event.reason;
        const message = reason instanceof Error ? `${reason.name}: ${reason.message}` : typeof reason === 'string' ? reason : 'Unhandled rejection';
        report('rejection', message, '', reason instanceof Error ? reason.stack : '');
    });

    // MapLibre reports runtime failures (e.g. a rejected sprite update) through
    // console.error rather than throwing; so does the app's own failure paths.
    // Only strings and Error messages are kept — logged objects may hold data.
    const consoleError = console.error;
    console.error = function (...args) {
        consoleError.apply(this, args);
        const error = args.find(arg => arg instanceof Error);
        const message = args
            .map(arg => (arg instanceof Error ? `${arg.name}: ${arg.message}` : typeof arg === 'string' ? arg : ''))
            .filter(Boolean)
            .join(' ');
        report('console', message, '', error ? error.stack : '');
    };

    return { report };
})();
