const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

test('map labels strip unsupported flag glyphs without a platform font dependency', () => {
    const context = vm.createContext({});
    vm.runInContext(fs.readFileSync(path.join(__dirname, '../core/utils.js'), 'utf8'), context);
    const utils = vm.runInContext('Utils', context);
    assert.equal(utils.stripCountryFlagEmoji('🇺🇸 Summer 🇨🇦 , Festival'), 'Summer, Festival');
    assert.equal(utils.stripCountryFlagEmoji('🇫🇷 Concert'), 'Concert');
    assert.equal(utils.stripCountryFlagEmoji('Live 🎵 Music'), 'Live 🎵 Music');
    assert.equal(utils.stripCountryFlagEmoji(''), '');
});
