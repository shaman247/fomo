// Transport groups are explicit and independent of daily event/tag exports.
const crypto = require('node:crypto');
const { gzipSync } = require('node:zlib');
const MAX_PACK_BYTES = 128 * 1024;
const MAX_STARTUP_BYTES = 384 * 1024;
const serialize = icons => Buffer.from(JSON.stringify({ schemaVersion: 1, icons }));

function buildPacks(artwork, config) {
    if (config.schema_version !== 1 || !config.groups?.startup) throw Error('Invalid icon pack configuration');
    const packs = {}, membership = {}, files = new Map(), seen = new Set();
    for (const [group, ids] of Object.entries(config.groups)) {
        if (!/^[a-z][a-z0-9-]*$/.test(group) || !Array.isArray(ids)) throw Error('Invalid icon pack group');
        let current = {}, part = 0;
        const limit = group === 'startup' ? MAX_STARTUP_BYTES : MAX_PACK_BYTES;
        function emit() {
            if (!Object.keys(current).length) return;
            const bytes = serialize(current);
            const revision = crypto.createHash('sha256').update(bytes).digest('hex').slice(0, 12);
            const id = group === 'startup' ? group : `${group}-${part++}`;
            const url = `images/event-icons/icons-${id}.${revision}.json`;
            packs[id] = { url, revision, gzipBytes: gzipSync(bytes).length };
            files.set(url, bytes);
            for (const icon of Object.keys(current)) membership[icon] = id;
            current = {};
        }
        for (const id of [...ids].sort()) {
            if (seen.has(id)) throw Error(`Icon belongs to multiple packs: ${id}`);
            seen.add(id);
            const entry = artwork.get(id);
            if (!entry || typeof entry.svg !== 'string') throw Error(`Pack requires a known SVG: ${id}`);
            if (serialize({ [id]: entry }).length > limit) {
                if (group === 'startup') throw Error(`Startup icon exceeds pack budget: ${id}`);
                continue; // Unusually large artwork keeps its individual download.
            }
            if (serialize({ ...current, [id]: entry }).length > limit) {
                if (group === 'startup') throw Error('Startup icon pack exceeds 384 KiB; trim its membership');
                emit();
            }
            current[id] = entry;
        }
        emit();
    }
    if (!packs.startup) throw Error('Startup icon pack is empty');
    return { packs, membership, files };
}

module.exports = { buildPacks, MAX_PACK_BYTES, MAX_STARTUP_BYTES };
