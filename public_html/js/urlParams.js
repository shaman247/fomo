const URLParams = (() => {
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

        // Parse latitude
        const lat = urlParams.get('lat');
        if (lat !== null) {
            const latNum = parseFloat(lat);
            if (!isNaN(latNum) && latNum >= -90 && latNum <= 90) {
                params.lat = latNum;
            }
        }

        // Parse longitude
        const lng = urlParams.get('lng');
        if (lng !== null) {
            const lngNum = parseFloat(lng);
            if (!isNaN(lngNum) && lngNum >= -180 && lngNum <= 180) {
                params.lng = lngNum;
            }
        }

        // Parse zoom
        const zoom = urlParams.get('zoom');
        if (zoom !== null) {
            const zoomNum = parseInt(zoom, 10);
            if (!isNaN(zoomNum) && zoomNum >= 1 && zoomNum <= 20) {
                params.zoom = zoomNum;
            }
        }

        // Parse start date
        const start = urlParams.get('start');
        if (start !== null) {
            const startDate = parseDate(start);
            if (startDate) {
                params.start = startDate;
            }
        }

        // Parse end date
        const end = urlParams.get('end');
        if (end !== null) {
            const endDate = parseDate(end);
            if (endDate) {
                params.end = endDate;
            }
        }

        // Parse tags (comma-separated)
        const tags = urlParams.get('tags');
        if (tags !== null && tags.trim() !== '') {
            // Split by comma and trim whitespace
            params.tags = tags.split(',').map(tag => tag.trim()).filter(tag => tag.length > 0);
        }

        return params;
    }

    /**
     * Parse a date string in YYYY-MM-DD format
     * Returns a Date object or null if invalid
     */
    function parseDate(dateStr) {
        if (!dateStr || typeof dateStr !== 'string') {
            return null;
        }

        // Check for YYYY-MM-DD format
        const dateRegex = /^(\d{4})-(\d{2})-(\d{2})$/;
        const match = dateStr.match(dateRegex);

        if (!match) {
            return null;
        }

        const year = parseInt(match[1], 10);
        const month = parseInt(match[2], 10) - 1; // Months are 0-indexed
        const day = parseInt(match[3], 10);

        const date = new Date(year, month, day);

        // Verify the date is valid and matches the input
        if (isNaN(date.getTime()) ||
            date.getFullYear() !== year ||
            date.getMonth() !== month ||
            date.getDate() !== day) {
            return null;
        }

        return date;
    }

    /**
     * Update the URL with current parameters without reloading the page
     */
    function update(params) {
        const urlParams = new URLSearchParams(window.location.search);

        // Update or remove lat/lng
        if (params.lat !== undefined && params.lng !== undefined) {
            urlParams.set('lat', params.lat.toFixed(5));
            urlParams.set('lng', params.lng.toFixed(5));
        } else {
            urlParams.delete('lat');
            urlParams.delete('lng');
        }

        // Update or remove zoom
        if (params.zoom !== undefined) {
            urlParams.set('zoom', params.zoom.toString());
        } else {
            urlParams.delete('zoom');
        }

        // Update or remove start date
        if (params.start !== undefined && params.start instanceof Date) {
            urlParams.set('start', formatDate(params.start));
        } else {
            urlParams.delete('start');
        }

        // Update or remove end date
        if (params.end !== undefined && params.end instanceof Date) {
            urlParams.set('end', formatDate(params.end));
        } else {
            urlParams.delete('end');
        }

        // Update or remove tags
        if (params.tags !== undefined && Array.isArray(params.tags) && params.tags.length > 0) {
            urlParams.set('tags', params.tags.join(','));
        } else {
            urlParams.delete('tags');
        }

        // Update the URL without reloading
        const newUrl = urlParams.toString() ? `${window.location.pathname}?${urlParams.toString()}` : window.location.pathname;
        window.history.replaceState({}, '', newUrl);
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

    return {
        parse,
        update,
        formatDate
    };
})();
