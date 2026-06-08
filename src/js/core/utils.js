const Utils = (() => {
    function escapeHtml(unsafe) {
        if (typeof unsafe !== 'string') return '';
        return unsafe
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function decodeHtml(html) {
        if (typeof html !== 'string') return '';
        const txt = document.createElement("textarea");
        txt.innerHTML = html;
        return txt.value;
    }

    function formatAndSanitize(text) {
        if (typeof text !== 'string') return '';

        // 1. Decode HTML entities
        let decodedText = decodeHtml(text);

        // 2. Convert markdown-like bold and italics to HTML tags
        // Bold: **text** or __text__ (but not underscores within words like user__name)
        decodedText = decodedText.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        decodedText = decodedText.replace(/(?<!\w)__(.*?)__(?!\w)/g, '<strong>$1</strong>');
        // Italics: *text* or _text_ (but not underscores within words like user_name)
        decodedText = decodedText.replace(/\*(.*?)\*/g, '<em>$1</em>');
        decodedText = decodedText.replace(/(?<!\w)_(.*?)_(?!\w)/g, '<em>$1</em>');
        return decodedText;
    }

    function isValidUrl(string) {
        return string && (string.startsWith('http://') || string.startsWith('https://'));
    }

    function formatDateForDisplay(timestamp) {
        const date = new Date(Number(timestamp));
        if (isNaN(date.getTime())) {
            console.warn("Utils.formatDateForDisplay received an invalid timestamp:", timestamp);
            return "Invalid Date";
        }
        return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    }

    // Shared date/time formatting options
    const DATE_OPTIONS = { month: 'short', day: 'numeric' };
    const TIME_OPTIONS = { hour: 'numeric', minute: 'numeric', hour12: true };

    /**
     * Formats a time string in compact form (e.g., "7pm" instead of "7:00 PM")
     * @param {Date} date - Date object to format time from
     * @returns {string} Formatted time string
     */
    function formatTimeCompact(date) {
        return date.toLocaleTimeString('en-US', TIME_OPTIONS)
            .replace(':00', '')
            .replace(' AM', 'am')
            .replace(' PM', 'pm')
            .replace(' ', '');
    }

    /**
     * Returns structured datetime data for an event, separating occurrences that
     * match the active date filter from those that don't. The popup uses this to
     * show matching dates prominently while keeping the rest accessible.
     *
     * @param {Object} event - Event with `occurrences` and optional `matching_occurrences`
     * @returns {{matchingText: string, otherText: string, otherCount: number}}
     */
    function buildEventDateTime(event) {
        const all = event && Array.isArray(event.occurrences) ? event.occurrences : null;
        if (!all || all.length === 0) {
            return { matchingText: 'Date/Time N/A', otherText: '', otherCount: 0 };
        }

        if (all.length === 1) {
            return { matchingText: formatSingleOccurrence(all[0]), otherText: '', otherCount: 0 };
        }

        const matching = Array.isArray(event.matching_occurrences) ? event.matching_occurrences : all;
        const matchingKeys = new Set(
            matching
                .filter(o => o.start instanceof Date && !isNaN(o.start))
                .map(o => o.start.toISOString())
        );

        const matchingOccs = [];
        const otherOccs = [];
        for (const occ of all) {
            if (!(occ.start instanceof Date) || isNaN(occ.start)) continue;
            if (matchingKeys.has(occ.start.toISOString())) {
                matchingOccs.push(occ);
            } else {
                otherOccs.push(occ);
            }
        }

        return {
            matchingText: matchingOccs.length > 0 ? formatMultipleOccurrences(matchingOccs) : '',
            otherText: otherOccs.length > 0 ? formatMultipleOccurrences(otherOccs) : '',
            otherCount: otherOccs.length
        };
    }

    function formatSingleOccurrence(occurrence) {
        const { start, end, originalStartTime, originalEndTime } = occurrence;
        if (!(start instanceof Date) || isNaN(start) || !(end instanceof Date) || isNaN(end)) {
            return "Date/Time N/A";
        }

        const hasStartTime = originalStartTime && originalStartTime.trim() !== '';
        const hasEndTime = originalEndTime && originalEndTime.trim() !== '';

        const startDateStr = start.toLocaleDateString('en-US', DATE_OPTIONS);
        const endDateStr = end.toLocaleDateString('en-US', DATE_OPTIONS);
        const isSameDay = start.toDateString() === end.toDateString();

        const startTimeStr = hasStartTime ? formatTimeCompact(start) : '';
        const endTimeStr = hasEndTime ? formatTimeCompact(end) : '';

        if (isSameDay) {
            if (startTimeStr && endTimeStr && startTimeStr !== endTimeStr) {
                return `${startDateStr}, ${startTimeStr}–${endTimeStr}`;
            }
            if (startTimeStr) {
                return `${startDateStr}, ${startTimeStr}`;
            }
            return startDateStr;
        }

        let result = startDateStr;
        if (startTimeStr) {
            result += `, ${startTimeStr}`;
        }
        result += ` – ${endDateStr}`;
        if (endTimeStr) {
            result += `, ${endTimeStr}`;
        }
        return result;
    }

    function formatMultipleOccurrences(occurrences) {
        const segments = [];        // ordered output segments
        const groupByDate = {};     // dateKey -> segment, for merging single-day occurrences

        occurrences.forEach(occurrence => {
            const { start, end, originalStartTime, originalEndTime } = occurrence;
            if (!(start instanceof Date) || isNaN(start)) return;

            const hasEnd = end instanceof Date && !isNaN(end);
            const isMultiDay = hasEnd && start.toDateString() !== end.toDateString();

            // Multi-day spans (e.g. exhibition runs) render as their own "start – end"
            // range so the end date isn't lost when grouping by start date.
            if (isMultiDay) {
                segments.push({ text: formatSingleOccurrence(occurrence) });
                return;
            }

            const dateKey = start.toISOString().split('T')[0];
            let segment = groupByDate[dateKey];
            if (!segment) {
                segment = { displayDate: start.toLocaleDateString('en-US', DATE_OPTIONS), times: new Set() };
                groupByDate[dateKey] = segment;
                segments.push(segment);
            }

            const hasStartTime = originalStartTime && originalStartTime.trim() !== '';
            const hasEndTime = hasEnd && originalEndTime && originalEndTime.trim() !== '';

            let timeStr = '';
            if (hasStartTime && hasEndTime) {
                const startTime = formatTimeCompact(start);
                const endTime = formatTimeCompact(end);
                timeStr = (startTime !== endTime) ? `${startTime}–${endTime}` : startTime;
            } else if (hasStartTime) {
                timeStr = formatTimeCompact(start);
            }

            if (timeStr) {
                segment.times.add(timeStr);
            }
        });

        return segments.map(segment => {
            if (segment.text) return segment.text;
            return segment.times.size > 0
                ? `${segment.displayDate}: ${Array.from(segment.times).join(', ')}`
                : segment.displayDate;
        }).join('; ');
    }

    function parseTime(timeStr) {
        if (!timeStr || !timeStr.trim()) return { hours: 12, minutes: 0, seconds: 0 };
        const lcTime = timeStr.toLowerCase();
        const modifier = lcTime.includes('pm') ? 'pm' : lcTime.includes('am') ? 'am' : null;

        let [hours, minutes] = lcTime.replace(/am|pm/g, '').trim().split(':').map(Number);
        minutes = minutes || 0;

        if (isNaN(hours) || isNaN(minutes)) return { hours: 12, minutes: 0, seconds: 0 };

        if (modifier === 'pm' && hours < 12) {
            hours += 12;
        }
        if (modifier === 'am' && hours === 12) {
            hours = 0;
        }
        return { hours, minutes, seconds: 0 };
    }

    // The app's timezone, injected by build.js (window.__CITY__.timezone). Used to
    // interpret event dates/times and "today" regardless of the user's local zone.
    const APP_TIMEZONE = (typeof window !== 'undefined' && window.__CITY__ && window.__CITY__.timezone) || 'America/New_York';

    // UTC offset (e.g. "-04:00") for APP_TIMEZONE at the given date. Driven by the
    // IANA database via Intl, so it's correct for any zone's DST rules — not just US.
    function getZoneOffset(date) {
        const parts = new Intl.DateTimeFormat('en-US', {
            timeZone: APP_TIMEZONE, timeZoneName: 'longOffset'
        }).formatToParts(date);
        const tzName = parts.find(p => p.type === 'timeZoneName');
        const m = tzName && tzName.value.match(/GMT([+-]\d{2}:\d{2})/);
        return m ? m[1] : '+00:00'; // "GMT" (no suffix) => UTC
    }

    function parseDateInZone(dateStr, timeStr) {
        if (!dateStr) return null;
        const tempDate = new Date(dateStr.replace(/-/g, '/') + ' 12:00:00');
        if (isNaN(tempDate.getTime())) return null;

        const offset = getZoneOffset(tempDate);
        const timeParts = parseTime(timeStr);
        const isoString = `${dateStr}T${String(timeParts.hours).padStart(2, '0')}:${String(timeParts.minutes).padStart(2, '0')}:${String(timeParts.seconds).padStart(2, '0')}${offset}`;
        const finalDate = new Date(isoString);

        return isNaN(finalDate.getTime()) ? null : finalDate;
    }

    // Today's date in the app timezone as YYYY-MM-DD. Used to pick the matching
    // events.{day}.json chunk regardless of the user's local timezone.
    const _todayFormatter = new Intl.DateTimeFormat('en-CA', {
        timeZone: APP_TIMEZONE,
        year: 'numeric', month: '2-digit', day: '2-digit'
    });
    function getTodayInZone() {
        return _todayFormatter.format(new Date());
    }

    function isWindows() {
        return navigator.platform.toLowerCase().includes('win');
    }

    function isCountryFlagEmoji(str) {
        if (!str || str.length < 2) return false;
        const codePoints = [...str].map(char => char.codePointAt(0));
        return codePoints.every(cp => cp >= 0x1F1E6 && cp <= 0x1F1FF);
    }

    /**
     * Resolves the emoji to actually display. Country-flag emoji (regional-
     * indicator pairs) have no glyphs in Windows' system emoji font and render
     * as two letter boxes (e.g. "IT"). On Windows only, a flag emoji is swapped
     * for the record's configured `alt_emoji` (a per-location/per-tag fallback);
     * if none is set it falls back to the globe so a flag never shows as boxes.
     * On other platforms, and for non-flag emoji, the original is returned.
     */
    function resolveDisplayEmoji(emoji, altEmoji) {
        if (!emoji || !isWindows() || !isCountryFlagEmoji(emoji)) return emoji;
        return altEmoji || '🌐';
    }

    /**
     * Normalizes text for accent-insensitive, case-insensitive search.
     * Decomposes accented characters and removes diacritical marks.
     * @param {string} text - Text to normalize
     * @returns {string} Normalized lowercase text without accents
     */
    function normalizeForSearch(text) {
        if (!text) return '';
        return text
            .normalize('NFD')                    // Decompose accents (é → e + combining accent)
            .replace(/[\u0300-\u036f]/g, '')     // Remove combining diacritical marks
            .replace(/['']/g, "'")               // Normalize curly apostrophes to straight
            .toLowerCase();
    }

    /**
     * Gets the display name for an item (event or location)
     * Uses short_name if available, otherwise uses the full name
     * Truncates long names to 40 characters
     * @param {Object} item - Item with name or short_name property
     * @returns {string} Display name
     */
    function getDisplayName(item) {
        if (!item) return '';

        // Use short_name if available, otherwise use the full name
        let nameToDisplay = item.short_name || item.name || '';

        // Truncate long names
        if (nameToDisplay.length > 40) {
            nameToDisplay = nameToDisplay.substring(0, 35) + '…';
        }

        return nameToDisplay;
    }

    /**
     * Creates a debounced function that delays invoking func until after wait milliseconds
     * @param {Function} func - Function to debounce
     * @param {number} wait - Delay in milliseconds
     * @returns {Function} Debounced function
     */
    function debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }

    /**
     * Creates a throttled function that only invokes func at most once per every wait milliseconds
     * @param {Function} func - Function to throttle
     * @param {number} wait - Delay in milliseconds
     * @returns {Function} Throttled function
     */
    function throttle(func, wait) {
        let inThrottle;
        return function executedFunction(...args) {
            if (!inThrottle) {
                func.apply(this, args);
                inThrottle = true;
                setTimeout(() => inThrottle = false, wait);
            }
        };
    }

    /**
     * Calculates distance between two lat/lng points using Haversine formula
     * @param {Object} point1 - First point {lat, lng}
     * @param {Object} point2 - Second point {lat, lng}
     * @returns {number} Distance in meters
     */
    function calculateHaversineDistance(point1, point2) {
        const R = 6371000; // Earth's radius in meters
        const lat1 = point1.lat * Math.PI / 180;
        const lat2 = point2.lat * Math.PI / 180;
        const deltaLat = (point2.lat - point1.lat) * Math.PI / 180;
        const deltaLng = (point2.lng - point1.lng) * Math.PI / 180;

        const a = Math.sin(deltaLat / 2) * Math.sin(deltaLat / 2) +
            Math.cos(lat1) * Math.cos(lat2) *
            Math.sin(deltaLng / 2) * Math.sin(deltaLng / 2);
        const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));

        return R * c;
    }

    /**
     * Safe localStorage wrapper with error handling
     */
    const SafeStorage = {
        /**
         * Safely get an item from localStorage
         * @param {string} key - Storage key
         * @returns {string|null} Value or null if error/not found
         */
        getItem(key) {
            try {
                return localStorage.getItem(key);
            } catch (error) {
                console.warn(`Failed to read from localStorage (key: ${key}):`, error);
                return null;
            }
        },

        /**
         * Safely set an item in localStorage
         * @param {string} key - Storage key
         * @param {string} value - Value to store
         * @returns {boolean} True if successful, false otherwise
         */
        setItem(key, value) {
            try {
                localStorage.setItem(key, value);
                return true;
            } catch (error) {
                if (error.name === 'QuotaExceededError') {
                    console.error('localStorage quota exceeded. Cannot save preferences.');
                } else {
                    console.error(`Failed to write to localStorage (key: ${key}):`, error);
                }
                return false;
            }
        },

        /**
         * Safely remove an item from localStorage
         * @param {string} key - Storage key
         * @returns {boolean} True if successful, false otherwise
         */
        removeItem(key) {
            try {
                localStorage.removeItem(key);
                return true;
            } catch (error) {
                console.warn(`Failed to remove from localStorage (key: ${key}):`, error);
                return false;
            }
        }
    };

    // ========================================
    // ORGANIZER PSEUDO-TAGS
    // ========================================
    // Organizers participate in the tag filter system as namespaced pseudo-tags
    // (e.g. "organizer:123"). They ride the same tagStates / eventTagIndex /
    // color machinery as curated tags, but are kept out of the curated hierarchy
    // so they never appear in the browsable tag tree. The name lookup below lets
    // getTagDisplayName() render an organizer chip with the organizer's real name.

    const ORGANIZER_TAG_PREFIX = 'organizer:';
    let organizerNameMap = {};

    /** Populates the organizer-name lookup from the loaded organizers map. */
    function registerOrganizers(organizersById) {
        organizerNameMap = {};
        if (!organizersById) return;
        for (const [id, org] of Object.entries(organizersById)) {
            if (org && org.name) organizerNameMap[ORGANIZER_TAG_PREFIX + id] = org.name;
        }
    }

    /** Builds the pseudo-tag key for an organizer id, or null if id is absent. */
    function makeOrganizerTag(id) {
        return (id === null || id === undefined || id === '') ? null : ORGANIZER_TAG_PREFIX + id;
    }

    /** True if the tag string is an organizer pseudo-tag. */
    function isOrganizerTag(tag) {
        return typeof tag === 'string' && tag.startsWith(ORGANIZER_TAG_PREFIX);
    }

    /** True if the pseudo-tag resolves to a known (loaded) organizer. */
    function isKnownOrganizerTag(tag) {
        return Object.prototype.hasOwnProperty.call(organizerNameMap, tag);
    }

    /**
     * Returns the organizer pseudo-tags for an event (one per source website in
     * event.organizer_ids). A merged event can have several. Order is preserved
     * (primary first). Includes unknown/aggregator ids — callers that render
     * chips should filter with isKnownOrganizerTag.
     */
    function organizerTagsForEvent(event) {
        const ids = event && event.organizer_ids;
        if (!Array.isArray(ids) || ids.length === 0) return [];
        return ids.map(id => ORGANIZER_TAG_PREFIX + id);
    }

    /**
     * Returns the human-readable form of a tag name, stripping any
     * disambiguator suffix (everything after " / "). The internal tag
     * name (with disambiguator) remains the unique identifier — only
     * rendered text is shortened. e.g. "Avant Garde / Music" → "Avant Garde".
     * Organizer pseudo-tags resolve to the organizer's display name.
     */
    function getTagDisplayName(tag) {
        if (!tag) return tag;
        if (organizerNameMap[tag]) return organizerNameMap[tag];
        const idx = tag.indexOf(' / ');
        return idx === -1 ? tag : tag.slice(0, idx);
    }

    return {
        escapeHtml,
        decodeHtml,
        formatAndSanitize,
        getTagDisplayName,
        registerOrganizers,
        makeOrganizerTag,
        isOrganizerTag,
        isKnownOrganizerTag,
        organizerTagsForEvent,
        isValidUrl,
        formatDateForDisplay,
        buildEventDateTime,
        parseDateInZone,
        getTodayInZone,
        isWindows,
        isCountryFlagEmoji,
        resolveDisplayEmoji,
        normalizeForSearch,
        getDisplayName,
        debounce,
        throttle,
        calculateHaversineDistance,
        SafeStorage,
    };
})();