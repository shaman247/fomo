const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

// BL12: synthesized span endpoints (exporter's optional 5th occurrence element)
// must not render as published opening/closing dates.
function loadUtils() {
    const context = vm.createContext({ Intl, Date });
    vm.runInContext(fs.readFileSync(path.join(__dirname, '../core/utils.js'), 'utf8'), context);
    return vm.runInContext('Utils', context);
}

function occ(utils, sd, ed, precision) {
    const o = { start: utils.parseDateInZone(sd, ''), end: utils.parseDateInZone(ed, ''),
                originalStartTime: '', originalEndTime: '' };
    if (precision) o.precision = precision;
    return o;
}

test('exact spans keep both dates', () => {
    const u = loadUtils();
    const text = u.buildEventDateTime({ occurrences: [occ(u, '2026-04-23', '2026-11-08')] }).matchingText;
    assert.equal(text, 'Apr 23 – Nov 8');
});

test('as-of start shows only the published closing date', () => {
    const u = loadUtils();
    const e = { occurrences: [occ(u, '2026-10-19', '2026-11-08', { start: 'as_of' })] };
    assert.equal(u.buildEventDateTime(e).matchingText, 'Through Nov 8');
});

test('open-run horizon is not shown as a closing date', () => {
    const u = loadUtils();
    const past = { occurrences: [occ(u, '2020-09-18', '2020-11-30', { end: 'open' })] };
    assert.equal(u.buildEventDateTime(past).matchingText, 'Ongoing since Sep 18');
    const future = { occurrences: [occ(u, '2099-11-05', '2100-01-04', { end: 'open' })] };
    assert.equal(u.buildEventDateTime(future).matchingText, 'Opens Nov 5');
    const both = { occurrences: [occ(u, '2026-10-19', '2026-12-18', { start: 'as_of', end: 'open' })] };
    assert.equal(u.buildEventDateTime(both).matchingText, 'Ongoing');
});

test('identical multi-day texts collapse', () => {
    const u = loadUtils();
    const e = { occurrences: [
        occ(u, '2026-06-03', '2027-04-18', { start: 'as_of' }),
        occ(u, '2026-06-14', '2027-04-18', { start: 'as_of' }),
        occ(u, '2026-11-01', '2026-11-01'),
    ] };
    assert.equal(u.buildEventDateTime(e).matchingText, 'Through Apr 18; Nov 1');
});
