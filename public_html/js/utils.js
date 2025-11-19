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

    function formatEventDateTimeCompactly(event) {
        const occurrencesToDisplay = event.matching_occurrences || event.occurrences;
        if (!event || !Array.isArray(occurrencesToDisplay) || occurrencesToDisplay.length === 0) {
            return "Date/Time N/A";
        }

        if (occurrencesToDisplay.length === 1) {
            return formatSingleOccurrence(occurrencesToDisplay[0]);
        }

        return formatMultipleOccurrences(occurrencesToDisplay);
    }

    function formatSingleOccurrence(occurrence) {
        const { start, end, originalStartTime, originalEndTime } = occurrence;
        if (!(start instanceof Date) || isNaN(start) || !(end instanceof Date) || isNaN(end)) {
            return "Date/Time N/A";
        }

        const optionsDate = { month: 'short', day: 'numeric' };
        const optionsTime = { hour: 'numeric', minute: 'numeric', hour12: true };

        const hasStartTime = originalStartTime && originalStartTime.trim() !== '';
        const hasEndTime = originalEndTime && originalEndTime.trim() !== '';

        const formatTime = (date) => date.toLocaleTimeString('en-US', optionsTime).replace(':00', '').replace(' AM', 'am').replace(' PM', 'pm').replace(' ', '');

        const startDateStr = start.toLocaleDateString('en-US', optionsDate);
        const endDateStr = end.toLocaleDateString('en-US', optionsDate);

        const isSameDay = start.toDateString() === end.toDateString();

        let startTimeStr = hasStartTime ? formatTime(start) : '';
        let endTimeStr = hasEndTime ? formatTime(end) : '';

        if (isSameDay) {
            if (startTimeStr && endTimeStr && startTimeStr !== endTimeStr) {
                return `${startDateStr}, ${startTimeStr}–${endTimeStr}`;
            } else if (startTimeStr) {
                return `${startDateStr}, ${startTimeStr}`;
            } else {
                return startDateStr;
            }
        } else {
            let finalString = `${startDateStr}`;
            if (startTimeStr) {
                finalString += `, ${startTimeStr}`;
            }
            finalString += ` – ${endDateStr}`;
            if (endTimeStr) {
                finalString += `, ${endTimeStr}`;
            }
            return finalString;
        }
    }

    function formatMultipleOccurrences(occurrences) {
        const dateGroups = {};
        const optionsDate = { month: 'short', day: 'numeric' };
        const optionsTime = { hour: 'numeric', minute: 'numeric', hour12: true };
        const formatTime = (date) => date.toLocaleTimeString('en-US', optionsTime).replace(':00', '').replace(' AM', 'am').replace(' PM', 'pm').replace(' ', '');

        occurrences.forEach(occurrence => {
            const { start, end, originalStartTime, originalEndTime } = occurrence;
            if (!(start instanceof Date) || isNaN(start)) return;

            const dateKey = start.toISOString().split('T')[0];
            if (!dateGroups[dateKey]) {
                dateGroups[dateKey] = { displayDate: start.toLocaleDateString('en-US', optionsDate), times: new Set() };
            }

            const hasStartTime = originalStartTime && originalStartTime.trim() !== '';
            const hasEndTime = end && originalEndTime && originalEndTime.trim() !== '';
            const isSameDay = end && start.toDateString() === end.toDateString();

            let timeStr = '';
            if (hasStartTime && hasEndTime && isSameDay) {
                const startTime = formatTime(start);
                const endTime = formatTime(end);
                timeStr = (startTime !== endTime) ? `${startTime}–${endTime}` : startTime;
            } else if (hasStartTime) {
                timeStr = formatTime(start);
            }

            if (timeStr) {
                dateGroups[dateKey].times.add(timeStr);
            }
        });

        return Object.values(dateGroups).map(group => {
            return group.times.size > 0 ? `${group.displayDate}: ${Array.from(group.times).join(', ')}` : group.displayDate;
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

    function getNewYorkOffset(date) {
        const year = date.getFullYear();
        const mar1 = new Date(year, 2, 1);
        const firstSundayInMarch = new Date(mar1);
        firstSundayInMarch.setDate(1 + (7 - mar1.getDay()) % 7);
        const dstStart = new Date(firstSundayInMarch);
        dstStart.setDate(firstSundayInMarch.getDate() + 7);
        dstStart.setHours(2);

        const nov1 = new Date(year, 10, 1);
        const dstEnd = new Date(nov1);
        dstEnd.setDate(1 + (7 - nov1.getDay()) % 7);
        dstEnd.setHours(2);

        return (date >= dstStart && date < dstEnd) ? '-04:00' : '-05:00';
    }

    function parseDateInNewYork(dateStr, timeStr) {
        if (!dateStr) return null;
        const tempDate = new Date(dateStr.replace(/-/g, '/') + ' 12:00:00');
        if (isNaN(tempDate.getTime())) return null;

        const offset = getNewYorkOffset(tempDate);
        const timeParts = parseTime(timeStr);
        const isoString = `${dateStr}T${String(timeParts.hours).padStart(2, '0')}:${String(timeParts.minutes).padStart(2, '0')}:${String(timeParts.seconds).padStart(2, '0')}${offset}`;
        const finalDate = new Date(isoString);

        return isNaN(finalDate.getTime()) ? null : finalDate;
    }

    function isWindows() {
        return navigator.platform.toLowerCase().includes('win');
    }

    function isCountryFlagEmoji(str) {
        if (!str || str.length < 2) return false;
        const codePoints = [...str].map(char => char.codePointAt(0));
        return codePoints.every(cp => cp >= 0x1F1E6 && cp <= 0x1F1FF);
    }

    return {
        escapeHtml,
        decodeHtml,
        formatAndSanitize,
        isValidUrl,
        formatDateForDisplay,
        formatEventDateTimeCompactly,
        parseDateInNewYork,
        isWindows,
        isCountryFlagEmoji,
    };
})();