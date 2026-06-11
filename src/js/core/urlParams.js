const URLParams = (() => {
    // ========================================
    // VALIDATION CONSTANTS
    // ========================================

    const VALIDATION = {
        // Coordinate bounds
        LAT_MIN: -90,
        LAT_MAX: 90,
        LNG_MIN: -180,
        LNG_MAX: 180,

        // Zoom bounds (MapLibre standard)
        ZOOM_MIN: 1,
        ZOOM_MAX: 20,

        // Date bounds (reasonable range)
        YEAR_MIN: 2000,
        YEAR_MAX: 2100,

        // Tag validation
        MAX_TAG_LENGTH: 100,
        MAX_TAGS_COUNT: 50,
        TAG_PATTERN: /^[a-zA-Z0-9\s\-_&:]+$/,  // Alphanumeric, spaces, hyphens, underscores, ampersands, colons (organizer:<id> pseudo-tags)

        // Input length limits (prevent DoS)
        MAX_PARAM_LENGTH: 1000
    };

    /**
     * Parse URL parameters and return an object with the values
     * Supported parameters:
     * - lat: latitude for map center
     * - lng: longitude for map center
     * - zoom: map zoom level
     * - start: start date (YYYY-MM-DD format)
     * - end: end date (YYYY-MM-DD format)
     * - tags: comma-separated list of tags to pre-select
     */
    function parse() {
        const urlParams = new URLSearchParams(window.location.search);
        const params = {};
        const warnings = [];

        const lat = readNumber(urlParams, warnings, 'lat', 'Latitude', VALIDATION.LAT_MIN, VALIDATION.LAT_MAX, parseFloat);
        if (lat !== undefined) params.lat = lat;

        const lng = readNumber(urlParams, warnings, 'lng', 'Longitude', VALIDATION.LNG_MIN, VALIDATION.LNG_MAX, parseFloat);
        if (lng !== undefined) params.lng = lng;

        const zoom = readNumber(urlParams, warnings, 'zoom', 'Zoom', VALIDATION.ZOOM_MIN, VALIDATION.ZOOM_MAX, parseFloat);
        if (zoom !== undefined) params.zoom = zoom;

        const start = readDate(urlParams, warnings, 'start', 'Start date');
        if (start !== undefined) params.start = start;

        const end = readDate(urlParams, warnings, 'end', 'End date');
        if (end !== undefined) params.end = end;

        // Parse tags (comma-separated)
        const tags = urlParams.get('tags');
        if (tags !== null && tags.trim() !== '') {
            if (tags.length > VALIDATION.MAX_PARAM_LENGTH) {
                warnings.push('Tags parameter too long, ignoring');
            } else {
                const parsedTags = parseTags(tags);
                if (parsedTags.tags.length > 0) {
                    params.tags = parsedTags.tags;
                }
                if (parsedTags.warnings.length > 0) {
                    warnings.push(...parsedTags.warnings);
                }
            }
        }

        // Log warnings if any validation issues occurred
        if (warnings.length > 0) {
            console.warn('URL parameter validation warnings:', warnings);
        }

        return params;
    }

    /**
     * Read and validate a numeric URL parameter.
     * Returns the parsed number, or undefined when the param is absent, too long,
     * or out of range. Unparseable (NaN) input is silently ignored — only
     * parseable-but-out-of-range values produce a warning.
     */
    function readNumber(urlParams, warnings, key, label, min, max, parseFn) {
        const raw = urlParams.get(key);
        if (raw === null) return undefined;
        if (raw.length > VALIDATION.MAX_PARAM_LENGTH) {
            warnings.push(`${label} parameter too long, ignoring`);
            return undefined;
        }
        const num = parseFn(raw);
        if (!isNaN(num) && num >= min && num <= max) {
            return num;
        }
        if (!isNaN(num)) {
            warnings.push(`Invalid ${label.toLowerCase()} value: ${raw} (must be between ${min} and ${max})`);
        }
        return undefined;
    }

    /**
     * Read and validate a YYYY-MM-DD date URL parameter via parseDate().
     * Returns a Date, or undefined when the param is absent, too long, or invalid.
     */
    function readDate(urlParams, warnings, key, label) {
        const raw = urlParams.get(key);
        if (raw === null) return undefined;
        if (raw.length > VALIDATION.MAX_PARAM_LENGTH) {
            warnings.push(`${label} parameter too long, ignoring`);
            return undefined;
        }
        const result = parseDate(raw);
        if (result.date) {
            return result.date;
        }
        if (result.error) {
            warnings.push(`Invalid ${label.toLowerCase()}: ${result.error}`);
        }
        return undefined;
    }

    /**
     * Parse a date string in YYYY-MM-DD format with validation
     * Returns an object with { date: Date|null, error: string|null }
     */
    function parseDate(dateStr) {
        if (!dateStr || typeof dateStr !== 'string') {
            return { date: null, error: 'Empty or invalid date string' };
        }

        // Check for YYYY-MM-DD format
        const dateRegex = /^(\d{4})-(\d{2})-(\d{2})$/;
        const match = dateStr.match(dateRegex);

        if (!match) {
            return { date: null, error: `Invalid date format "${dateStr}" (expected YYYY-MM-DD)` };
        }

        const year = parseInt(match[1], 10);
        const month = parseInt(match[2], 10) - 1; // Months are 0-indexed
        const day = parseInt(match[3], 10);

        // Validate year bounds
        if (year < VALIDATION.YEAR_MIN || year > VALIDATION.YEAR_MAX) {
            return { date: null, error: `Year ${year} out of range (${VALIDATION.YEAR_MIN}-${VALIDATION.YEAR_MAX})` };
        }

        const date = new Date(year, month, day);

        // Verify the date is valid and matches the input
        if (isNaN(date.getTime()) ||
            date.getFullYear() !== year ||
            date.getMonth() !== month ||
            date.getDate() !== day) {
            return { date: null, error: `Invalid date "${dateStr}"` };
        }

        return { date, error: null };
    }

    /**
     * Parse and validate tags from comma-separated string
     * Returns an object with { tags: string[], warnings: string[] }
     */
    function parseTags(tagsStr) {
        const tags = [];
        const warnings = [];

        if (!tagsStr || typeof tagsStr !== 'string') {
            return { tags, warnings };
        }

        // Split by comma and trim whitespace
        const rawTags = tagsStr.split(',').map(tag => tag.trim());

        // Check total count
        if (rawTags.length > VALIDATION.MAX_TAGS_COUNT) {
            warnings.push(`Too many tags (${rawTags.length}), limiting to ${VALIDATION.MAX_TAGS_COUNT}`);
        }

        // Validate each tag
        for (let i = 0; i < Math.min(rawTags.length, VALIDATION.MAX_TAGS_COUNT); i++) {
            const tag = rawTags[i];

            if (tag.length === 0) {
                continue; // Skip empty tags
            }

            // Check tag length
            if (tag.length > VALIDATION.MAX_TAG_LENGTH) {
                warnings.push(`Tag too long (${tag.length} chars): "${tag.substring(0, 20)}..." - skipping`);
                continue;
            }

            // Check tag pattern (prevent XSS and injection attacks)
            if (!VALIDATION.TAG_PATTERN.test(tag)) {
                warnings.push(`Tag contains invalid characters: "${tag}" - skipping`);
                continue;
            }

            tags.push(tag);
        }

        return { tags, warnings };
    }

    /**
     * Format a Date object as YYYY-MM-DD
     */
    function formatDate(date) {
        if (!(date instanceof Date) || isNaN(date.getTime())) {
            return '';
        }

        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');

        return `${year}-${month}-${day}`;
    }

    /**
     * Generate a shareable URL with the given parameters
     * @param {Object} params - Parameters to include in the URL
     * @param {number} params.lat - Latitude
     * @param {number} params.lng - Longitude
     * @param {number} params.zoom - Zoom level
     * @param {Date} [params.start] - Start date
     * @param {Date} [params.end] - End date
     * @param {Array<string>} [params.tags] - Selected tags
     * @returns {string} The shareable URL
     */
    function generateShareUrl(params) {
        const baseUrl = window.location.origin + window.location.pathname;
        const urlParams = new URLSearchParams();

        urlParams.set('lat', params.lat.toFixed(5));
        urlParams.set('lng', params.lng.toFixed(5));
        urlParams.set('zoom', params.zoom.toFixed(2));

        if (params.start && params.end) {
            urlParams.set('start', formatDate(params.start));
            urlParams.set('end', formatDate(params.end));
        }

        if (params.tags && params.tags.length > 0) {
            urlParams.set('tags', params.tags.join(','));
        }

        return `${baseUrl}?${urlParams.toString()}`;
    }

    return {
        parse,
        parseDate,
        formatDate,
        generateShareUrl
    };
})();
