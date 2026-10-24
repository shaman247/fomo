const { test } = require('node:test');
const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

// Event times are city instants (window.__CITY__.timezone). Whatever zone the
// viewer's device is in, they must display, group and filter by the city's
// clock and calendar. Node fixes its zone at startup, so each device zone runs
// this file in a child process (FOMO_TZ_PROBE) that prints what the real
// modules produce.
const DEVICE_ZONES = ['America/New_York', 'America/Los_Angeles', 'Europe/London', 'Asia/Tokyo', 'Pacific/Kiritimati'];
// 2026-10-30 22:30 in New York: already Oct 31 in London, Tokyo and Kiritimati.
const NOW = Date.parse('2026-10-31T02:30:00Z');

function probe() {
    class FixedDate extends Date {
        constructor(...args) { super(...(args.length ? args : [NOW])); }
        static now() { return NOW; }
    }
    const context = vm.createContext({ window: { __CITY__: { timezone: 'America/New_York' } }, Date: FixedDate,
        Constants: { TIME: { EARLY_MORNING_CUTOFF_HOUR: 5 } } });
    for (const [file, name] of [['core/utils.js', 'Utils'], ['data/filterManager.js', 'FilterManager']]) {
        vm.runInContext(`${fs.readFileSync(path.join(__dirname, '..', file), 'utf8')}\nthis.${name} = ${name};`, context);
    }
    const { Utils, FilterManager } = context;
    const at = (date, time) => Utils.parseDateInZone(date, time);
    const occ = (sd, st, ed, et) => ({ start: at(sd, st), end: at(ed || sd, et || st), originalStartTime: st, originalEndTime: et || '' });
    const text = (...occurrences) => Utils.buildEventDateTime({ occurrences }).matchingText;
    const events = [
        { id: 'evening', occurrences: [occ('2026-10-30', '19:00', '2026-10-30', '23:30')] },
        { id: 'late', occurrences: [occ('2026-10-30', '23:45')] },
        { id: 'afterMidnight', occurrences: [occ('2026-10-31', '00:15')] },
        { id: 'overnight', occurrences: [occ('2026-10-30', '22:00', '2026-10-31', '02:00')] },
        { id: 'nextDay', occurrences: [occ('2026-10-31', '12:00')] },
        { id: 'fallBack', occurrences: [occ('2026-11-01', '23:30')] },
    ];
    FilterManager.init({ appState: { allEvents: events }, config: {} });
    // Picker days are device-local midnights; only their calendar date is meant.
    const pick = (y, m, d) => new context.Date(y, m - 1, d);
    const ids = (from, to) => FilterManager.filterEventsByDateRange(from, to).map(e => e.id);
    const today = Utils.todayInZone();
    return {
        display: [
            text(occ('2026-10-30', '19:00', '2026-10-30', '23:30')),
            text(occ('2026-10-30', '22:00', '2026-10-31', '02:00')),
            text(occ('2026-10-30', '19:00'), occ('2026-10-30', '21:00'), occ('2026-10-31', '19:00')),
        ],
        instants: [at('2026-03-08', '19:00'), at('2026-11-01', '19:00'), at('2026-11-01', '00:30')].map(d => d.toISOString()),
        days: [at('2026-11-01', '00:30'), at('2026-11-01', '23:30')].map(d => Utils.dayIndexInZone(d) - Utils.dayIndexInZone(at('2026-10-31', '12:00'))),
        hours: [at('2026-10-30', '23:45'), at('2026-11-01', '01:30')].map(Utils.hourInZone),
        dayStarts: [Utils.calendarDayIndex(pick(2026, 11, 1)), Utils.calendarDayIndex(pick(2026, 11, 2))]
            .map(day => new Date(Utils.dayStartMsInZone(day)).toISOString()),
        today: [today.getFullYear(), today.getMonth() + 1, today.getDate()],
        filters: {
            oct30: ids(pick(2026, 10, 30), pick(2026, 10, 30)),
            oct31: ids(pick(2026, 10, 31), pick(2026, 10, 31)),
            nov1: ids(pick(2026, 11, 1), pick(2026, 11, 1)),
        },
    };
}

if (process.env.FOMO_TZ_PROBE) {
    process.stdout.write(JSON.stringify(probe()));
    return;
}

const EXPECTED = {
    display: ['Oct 30, 7pm–11:30pm', 'Oct 30, 10pm – Oct 31, 2am', 'Oct 30: 7pm, 9pm; Oct 31: 7pm'],
    // EDT before the Nov 1 fall-back; EST from its 2am, including that evening.
    instants: ['2026-03-08T23:00:00.000Z', '2026-11-02T00:00:00.000Z', '2026-11-01T04:30:00.000Z'],
    days: [1, 1],
    hours: [23, 1],
    dayStarts: ['2026-11-01T04:00:00.000Z', '2026-11-02T05:00:00.000Z'],
    today: [2026, 10, 30],
    filters: {
        // The overnight show ending before 5am counts as an Oct 30 event only.
        oct30: ['evening', 'late', 'overnight'],
        oct31: ['afterMidnight', 'nextDay'],
        nov1: ['fallBack'],
    },
};

for (const zone of DEVICE_ZONES) {
    test(`a device in ${zone} sees the city's times, days and filters`, () => {
        const output = execFileSync(process.execPath, [__filename], {
            env: { ...process.env, TZ: zone, FOMO_TZ_PROBE: '1' }, encoding: 'utf8'
        });
        assert.deepEqual(JSON.parse(output), EXPECTED);
    });
}
