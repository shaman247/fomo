const Beacon = (() => {
    // Shared plumbing for the page's first-party beacons (ErrorReporter and
    // Analytics): the device context both attach, URL scrubbing, and a
    // sendBeacon wrapper that never throws. Loaded first in the bundle.

    // currentScript is only set while the bundle evaluates, so read it now.
    const script = document.currentScript;
    const bundleMatch = script && /\/app\.([0-9a-f]{8})\.js/.exec(script.src);
    const bundle = bundleMatch ? bundleMatch[1] : (script && /\/app\.js$/.test(script.src) ? 'dev' : 'unbundled');

    // Any URL → its last path segment; keeps ":line:col" suffixes.
    const URL_PATTERN = /\b(?:https?|file|blob|webpack|[a-z]+-extension):\/\/[^\s()'"<>]*/gi;
    const fileName = url => url.replace(/[?#].*$/, m => (m.match(/(:\d+){1,2}$/) || [''])[0]).replace(/^.*\//, '');
    const scrub = (text, max) => String(text == null ? '' : text).replace(URL_PATTERN, fileName).slice(0, max);

    // The native apps append a marker (config frontend.native_app_ua) to the WebView UA.
    const appMarker = (window.__CITY__ || {}).nativeAppUa;
    function platform() {
        const ua = navigator.userAgent;
        if (appMarker && ua.includes(`${appMarker}/`)) return /Android/.test(ua) ? 'android-app' : 'ios-app';
        try {
            if (navigator.standalone || window.matchMedia('(display-mode: standalone)').matches) return 'pwa';
        } catch (e) { /* matchMedia unavailable */ }
        return 'web';
    }

    function timezone() {
        try { return Intl.DateTimeFormat().resolvedOptions().timeZone || ''; } catch (e) { return ''; }
    }

    const context = () => ({
        bundle,
        platform: platform(),
        dpr: window.devicePixelRatio || 1,
        tz: timezone(),
        viewport: `${window.innerWidth}x${window.innerHeight}`,
        path: location.pathname.slice(0, 100)
    });

    function send(endpoint, payload) {
        if (!navigator.sendBeacon) return false;
        try { return navigator.sendBeacon(endpoint, JSON.stringify(payload)); } catch (e) { return false; }
    }

    return { bundle, scrub, context, send };
})();
