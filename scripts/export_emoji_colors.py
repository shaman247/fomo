#!/usr/bin/env python3
"""Export emoji color tool as an interactive HTML page.

Generates scripts/emoji_colors.html — a browser-based tool that:
- Extracts dominant colors from emoji via canvas pixel analysis
- Shows curated vs extracted colors with ring and tag chip previews
- Allows curator overrides (persisted in localStorage)
- Exports final bgcolors JSON for pasting into src/data/tags.json

Usage:
    ./venv/bin/python scripts/export_emoji_colors.py
"""

import json
import os
import re
import sys
from html import escape

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'pipeline'))
from db import create_connection

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Emoji are 1-4 codepoints (plus ZWJ sequences); reject plain ASCII text
_EMOJI_PATTERN = re.compile(
    r'^[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0000FE00-\U0000FE0F'
    r'\U0000200D\U0001F1E0-\U0001F1FF\U00002702-\U000027B0'
    r'\U0000231A-\U000023F3\U00002934-\U00002935\U000025AA-\U000025FE'
    r'\U00002B05-\U00002B55\U00003030\U0000303D\U00003297\U00003299'
    r'\U0000200D\U000020E3\U0000FE0F\U000E0020-\U000E007F'
    r'\u0030-\u0039\u002A\u0023]+$'
)


def is_emoji(s):
    """Check if string looks like an emoji (not plain text or stray Unicode)."""
    if not s or len(s) > 15:
        return False
    # Must contain at least one character in a known emoji range
    return bool(re.search(
        r'[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0000FE0F'
        r'\U00002702-\U000027B0\U0000231A-\U000023F3\U000025AA-\U000025FE'
        r'\U00002B05-\U00002B55\U0000203C\U00002049\U000020E3]', s
    ))


def main():
    conn = create_connection()
    if not conn:
        print("Failed to connect to database")
        sys.exit(1)

    cursor = conn.cursor(dictionary=True)

    # Get all unique emoji from locations, with location names
    cursor.execute("""
        SELECT l.emoji, GROUP_CONCAT(l.name ORDER BY l.name SEPARATOR ', ') AS locations,
               COUNT(*) AS location_count
        FROM locations l
        WHERE l.emoji IS NOT NULL AND l.emoji != ''
        GROUP BY l.emoji
        ORDER BY location_count DESC, l.emoji
    """)
    db_emoji = cursor.fetchall()

    # Also get emoji from active events (these appear on the map via event markers)
    cursor.execute("""
        SELECT e.emoji, COUNT(DISTINCT e.id) AS event_count
        FROM events e
        WHERE e.emoji IS NOT NULL AND e.emoji != ''
          AND e.archived = FALSE AND e.suppressed = FALSE
        GROUP BY e.emoji
        ORDER BY event_count DESC
    """)
    event_emoji = cursor.fetchall()

    cursor.close()
    conn.close()

    # Load current bgcolors from tags.json
    tags_json_path = os.path.join(SCRIPT_DIR, '..', 'src', 'data', 'tags.json')
    with open(tags_json_path, 'r', encoding='utf-8') as f:
        tags_json = json.load(f)
    curated_colors = tags_json.get('bgcolors', {})

    # Also collect emoji from exported location JSON files (may have more than current DB)
    data_dir = os.path.join(SCRIPT_DIR, '..', 'src', 'data')
    exported_emoji = set()
    for filename in ('locations.init.json', 'locations.full.json'):
        filepath = os.path.join(data_dir, filename)
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                for loc in json.load(f):
                    if loc.get('emoji'):
                        exported_emoji.add(loc['emoji'])

    # Build emoji data — merge locations, events, exported, and curated sources
    emoji_info = {}  # emoji -> {locations, loc_count, event_count}

    for row in db_emoji:
        if not is_emoji(row['emoji']):
            continue
        locs = row['locations']
        if len(locs) > 120:
            locs = locs[:117] + '...'
        emoji_info[row['emoji']] = {
            'locations': locs,
            'loc_count': row['location_count'],
            'event_count': 0,
        }

    for row in event_emoji:
        e = row['emoji']
        if not is_emoji(e):
            continue
        if e in emoji_info:
            emoji_info[e]['event_count'] = row['event_count']
        else:
            emoji_info[e] = {
                'locations': '(events only)',
                'loc_count': 0,
                'event_count': row['event_count'],
            }

    # Add any emoji from exported JSON or curated colors not yet seen
    for e in exported_emoji | set(curated_colors.keys()):
        if not is_emoji(e):
            continue
        if e not in emoji_info:
            source = 'exported JSON' if e in exported_emoji else 'curated only'
            emoji_info[e] = {
                'locations': f'({source})',
                'loc_count': 0,
                'event_count': 0,
            }

    # Sort: by location count desc, then event count desc, then emoji
    emoji_data = []
    for emoji, info in sorted(emoji_info.items(),
                               key=lambda x: (-x[1]['loc_count'], -x[1]['event_count'], x[0])):
        emoji_data.append({
            'emoji': emoji,
            'locations': info['locations'],
            'count': info['loc_count'],
            'events': info['event_count'],
        })

    n_total = len(emoji_data)
    n_curated = sum(1 for e in emoji_data if e['emoji'] in curated_colors)
    n_missing = n_total - n_curated

    # JSON-encode data for embedding in HTML
    emoji_data_json = json.dumps(emoji_data, ensure_ascii=False)
    curated_json = json.dumps(curated_colors, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Emoji Colors — fomo.nyc</title>
<style>
@font-face {{
    font-family: 'Noto Color Emoji';
    src: url('../src/fonts/NotoColorEmoji-COLRv1.woff2') format('woff2');
    font-display: swap;
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    font-family: 'SF Mono', 'Menlo', 'Consolas', monospace;
    background: #0d1117; color: #c9d1d9; padding: 20px; font-size: 13px;
}}
h1 {{ margin-bottom: 4px; font-size: 1.3em; color: #e6edf3; font-weight: 600; }}
.subtitle {{ color: #7d8590; margin-bottom: 16px; font-size: 0.85em; }}
.controls {{
    display: flex; gap: 8px; margin-bottom: 16px; align-items: center; flex-wrap: wrap;
}}
input[type="text"] {{
    padding: 6px 10px; border: 1px solid #30363d; border-radius: 6px;
    font-size: 13px; width: 220px; background: #161b22; color: #c9d1d9;
    font-family: inherit;
}}
input[type="text"]::placeholder {{ color: #484f58; }}
input[type="text"]:focus {{ outline: none; border-color: #58a6ff; }}
select, button {{
    padding: 6px 12px; border: 1px solid #30363d; border-radius: 6px;
    font-size: 13px; background: #161b22; color: #c9d1d9; font-family: inherit;
    cursor: pointer;
}}
button:hover {{ background: #21262d; border-color: #58a6ff; }}
button.primary {{ background: #238636; border-color: #2ea043; color: #fff; }}
button.primary:hover {{ background: #2ea043; }}

.grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
    gap: 10px;
}}

.card {{
    background: #161b22; border: 1px solid #21262d; border-radius: 8px;
    padding: 12px; display: flex; flex-direction: column; gap: 8px;
    transition: border-color 0.15s;
}}
.card:hover {{ border-color: #30363d; }}
.card.has-override {{ border-color: #d29922; }}

.card-header {{
    display: flex; align-items: center; gap: 10px;
}}
.emoji-large {{ font-size: 36px; line-height: 1; flex-shrink: 0; }}
.card-info {{ flex: 1; min-width: 0; }}
.card-locations {{
    font-size: 11px; color: #484f58; white-space: nowrap;
    overflow: hidden; text-overflow: ellipsis;
}}
.card-count {{ font-size: 11px; color: #7d8590; }}

.previews {{
    display: flex; gap: 12px; align-items: center; justify-content: center;
    padding: 8px 0;
}}

.ring-preview {{
    width: 52px; height: 52px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 28px; border: 3px solid #444;
    background: rgba(255,255,255,0.03);
}}

.chip-preview {{
    display: inline-flex; align-items: center; gap: 4px;
    padding: 4px 10px; border-radius: 14px;
    font-size: 12px; color: #fff; white-space: nowrap;
}}
.chip-emoji {{ font-size: 14px; }}

.swatches {{
    display: flex; gap: 4px; align-items: center;
}}
.swatch-group {{
    display: flex; flex-direction: column; align-items: center; gap: 2px; flex: 1;
}}
.swatch {{
    width: 100%; height: 24px; border-radius: 4px;
    border: 1px solid #30363d; cursor: pointer;
    position: relative;
}}
.swatch:hover {{ border-color: #58a6ff; }}
.swatch.none {{
    background: repeating-linear-gradient(
        45deg, #21262d, #21262d 4px, #161b22 4px, #161b22 8px
    );
    cursor: default;
}}
.swatch-label {{ font-size: 10px; color: #484f58; }}
.swatch-hex {{ font-size: 9px; color: #484f58; font-variant-numeric: tabular-nums; }}

.override-controls {{
    display: flex; gap: 4px; align-items: center; justify-content: flex-end;
}}
.override-controls button {{
    font-size: 11px; padding: 2px 8px;
}}
input[type="color"] {{
    width: 28px; height: 24px; border: 1px solid #30363d; border-radius: 4px;
    background: none; cursor: pointer; padding: 0;
}}

.status-bar {{
    position: sticky; bottom: 0; background: #161b22;
    border-top: 1px solid #21262d; padding: 8px 16px;
    display: flex; gap: 16px; align-items: center; font-size: 12px;
    margin: 16px -20px -20px; z-index: 10;
}}
.status-bar .stat {{ color: #7d8590; }}
.status-bar .stat b {{ color: #e6edf3; }}

.hidden {{ display: none; }}
</style>
</head>
<body>
<h1>Emoji Colors</h1>
<p class="subtitle">{n_total} emoji &middot; {n_curated} curated &middot; {n_missing} need colors</p>

<div class="controls">
    <input type="text" id="search" placeholder="Filter by location..." oninput="filterCards()">
    <select id="filterMode" onchange="filterCards()">
        <option value="all">All</option>
        <option value="missing">Missing curated</option>
        <option value="overridden">Has override</option>
        <option value="mismatch">Curated differs from extracted</option>
    </select>
    <select id="fontMode" onchange="switchFont()">
        <option value="serif">System emoji (serif)</option>
        <option value="noto">Noto Color Emoji</option>
    </select>
    <button class="primary" onclick="exportJSON()">Export JSON</button>
    <button onclick="clearAllOverrides()">Clear All Overrides</button>
</div>

<div class="grid" id="grid"></div>

<div class="status-bar">
    <span class="stat">Total: <b id="statTotal">{n_total}</b></span>
    <span class="stat">Extracted: <b id="statExtracted">0</b></span>
    <span class="stat">Overrides: <b id="statOverrides">0</b></span>
    <span class="stat">Visible: <b id="statVisible">{n_total}</b></span>
</div>

<script>
// ========================================
// EMBEDDED DATA
// ========================================
const EMOJI_DATA = {emoji_data_json};
const CURATED_COLORS = {curated_json};

// ========================================
// STATE
// ========================================
const extractedColors = {{}};  // emoji -> hex
const overrides = JSON.parse(localStorage.getItem('emojiColorOverrides') || '{{}}');

// ========================================
// COLOR EXTRACTION
// ========================================
function extractColor(emoji, fontFamily) {{
    const size = 128;
    const canvas = document.createElement('canvas');
    canvas.width = size;
    canvas.height = size;
    const ctx = canvas.getContext('2d');
    ctx.font = size * 0.85 + 'px ' + fontFamily;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(emoji, size / 2, size / 2);

    const data = ctx.getImageData(0, 0, size, size).data;
    const buckets = new Array(36).fill(0);
    const bucketColors = Array.from({{length: 36}}, () => []);

    for (let i = 0; i < data.length; i += 4) {{
        const r = data[i], g = data[i+1], b = data[i+2], a = data[i+3];
        if (a < 30) continue;
        const rn = r/255, gn = g/255, bn = b/255;
        const mx = Math.max(rn, gn, bn), mn = Math.min(rn, gn, bn);
        const l = (mx + mn) / 2, d = mx - mn;
        if (d < 0.05) continue;
        const s = l > 0.5 ? d / (2 - mx - mn) : d / (mx + mn);
        if (s < 0.15 || l < 0.08 || l > 0.92) continue;
        let h;
        if (mx === rn) h = ((gn - bn) / d + (gn < bn ? 6 : 0)) / 6;
        else if (mx === gn) h = ((bn - rn) / d + 2) / 6;
        else h = ((rn - gn) / d + 4) / 6;
        const bucket = Math.floor((h * 360) / 10) % 36;
        buckets[bucket] += s * s;
        bucketColors[bucket].push({{r, g, b, s, l}});
    }}

    let best = 0, bestScore = 0;
    for (let i = 0; i < 36; i++) {{
        const sc = buckets[(i+35)%36]*0.5 + buckets[i] + buckets[(i+1)%36]*0.5;
        if (sc > bestScore) {{ bestScore = sc; best = i; }}
    }}

    const nearby = [
        ...bucketColors[(best+35)%36],
        ...bucketColors[best],
        ...bucketColors[(best+1)%36]
    ];
    if (!nearby.length) return '#555555';

    let sR=0, sG=0, sB=0, sW=0;
    nearby.forEach(c => {{
        const w = c.s * c.s;
        sR += c.r*w; sG += c.g*w; sB += c.b*w; sW += w;
    }});
    const aR = sR/sW, aG = sG/sW, aB = sB/sW;
    const rn2 = aR/255, gn2 = aG/255, bn2 = aB/255;
    const mx2 = Math.max(rn2,gn2,bn2), mn2 = Math.min(rn2,gn2,bn2);
    const l2 = (mx2+mn2)/2, d2 = mx2-mn2;
    let h2, s2;
    if (d2 === 0) {{ h2=0; s2=0; }}
    else {{
        s2 = l2>0.5 ? d2/(2-mx2-mn2) : d2/(mx2+mn2);
        if (mx2===rn2) h2=((gn2-bn2)/d2+(gn2<bn2?6:0))/6;
        else if (mx2===gn2) h2=((bn2-rn2)/d2+2)/6;
        else h2=((rn2-gn2)/d2+4)/6;
    }}

    const tS = Math.min(1, s2 * 1.6);
    const [fR, fG, fB] = hsl2rgb(h2, tS, 0.45);
    return '#' + [fR, fG, fB].map(c => c.toString(16).padStart(2, '0')).join('');
}}

function hsl2rgb(h, s, l) {{
    const c = (1 - Math.abs(2*l - 1)) * s;
    const x = c * (1 - Math.abs((h*6) % 2 - 1));
    const m = l - c/2;
    let r, g, b;
    const i = Math.floor(h * 6) % 6;
    if (i===0) {{r=c;g=x;b=0}} else if (i===1) {{r=x;g=c;b=0}} else if (i===2) {{r=0;g=c;b=x}}
    else if (i===3) {{r=0;g=x;b=c}} else if (i===4) {{r=x;g=0;b=c}} else {{r=c;g=0;b=x}}
    return [Math.round((r+m)*255), Math.round((g+m)*255), Math.round((b+m)*255)];
}}

// ========================================
// FINAL COLOR RESOLUTION
// ========================================
function getFinalColor(emoji) {{
    if (overrides[emoji]) return overrides[emoji];
    if (CURATED_COLORS[emoji]) return CURATED_COLORS[emoji];
    if (extractedColors[emoji]) return extractedColors[emoji];
    return '#555555';
}}

// ========================================
// UI RENDERING
// ========================================
function buildGrid() {{
    const grid = document.getElementById('grid');
    grid.innerHTML = '';

    EMOJI_DATA.forEach((item, idx) => {{
        const emoji = item.emoji;
        const curated = CURATED_COLORS[emoji] || null;
        const extracted = extractedColors[emoji] || '#555555';
        const override = overrides[emoji] || null;
        const final_ = getFinalColor(emoji);

        const card = document.createElement('div');
        card.className = 'card' + (override ? ' has-override' : '');
        card.dataset.emoji = emoji;
        card.dataset.locations = (item.locations || '').toLowerCase();
        card.dataset.idx = idx;

        card.innerHTML = `
            <div class="card-header">
                <span class="emoji-large">${{emoji}}</span>
                <div class="card-info">
                    <div class="card-locations" title="${{escapeAttr(item.locations)}}">${{escapeHtml(item.locations)}}</div>
                    <div class="card-count">${{item.count}} location${{item.count !== 1 ? 's' : ''}}</div>
                </div>
            </div>

            <div class="previews">
                <div class="ring-preview" style="border-color: ${{final_}}">${{emoji}}</div>
                <div class="chip-preview" style="background: ${{final_}}">
                    <span class="chip-emoji">${{emoji}}</span> Sample Tag
                </div>
            </div>

            <div class="swatches">
                <div class="swatch-group">
                    <div class="swatch" style="background: ${{extracted}}" title="Extracted: ${{extracted}}"></div>
                    <span class="swatch-label">extracted</span>
                    <span class="swatch-hex">${{extracted}}</span>
                </div>
                <div class="swatch-group">
                    ${{curated
                        ? `<div class="swatch" style="background: ${{curated}}" title="Curated: ${{curated}}"></div>`
                        : '<div class="swatch none" title="No curated color"></div>'
                    }}
                    <span class="swatch-label">curated</span>
                    <span class="swatch-hex">${{curated || 'none'}}</span>
                </div>
                <div class="swatch-group">
                    <div class="swatch" style="background: ${{final_}}; border-color: ${{override ? '#d29922' : '#30363d'}}"
                         title="Final: ${{final_}}"></div>
                    <span class="swatch-label">final</span>
                    <span class="swatch-hex">${{final_}}</span>
                </div>
            </div>

            <div class="override-controls">
                <input type="color" value="${{override || final_}}"
                       onchange="setOverride('${{escapeAttr(emoji)}}', this.value)">
                ${{override
                    ? `<button onclick="clearOverride('${{escapeAttr(emoji)}}')">reset</button>`
                    : ''
                }}
            </div>
        `;
        grid.appendChild(card);
    }});

    updateStats();
}}

function escapeHtml(s) {{ const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }}
function escapeAttr(s) {{ return s.replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/'/g,'&#39;'); }}

// ========================================
// EXTRACTION
// ========================================
function extractAll() {{
    const fontFamily = document.getElementById('fontMode').value === 'noto'
        ? '"Noto Color Emoji", serif' : 'serif';

    let count = 0;
    EMOJI_DATA.forEach(item => {{
        extractedColors[item.emoji] = extractColor(item.emoji, fontFamily);
        count++;
    }});

    document.getElementById('statExtracted').textContent = count;
    buildGrid();
}}

// ========================================
// OVERRIDES
// ========================================
function setOverride(emoji, color) {{
    overrides[emoji] = color;
    saveOverrides();
    buildGrid();
}}

function clearOverride(emoji) {{
    delete overrides[emoji];
    saveOverrides();
    buildGrid();
}}

function clearAllOverrides() {{
    if (!confirm('Clear all ' + Object.keys(overrides).length + ' overrides?')) return;
    Object.keys(overrides).forEach(k => delete overrides[k]);
    saveOverrides();
    buildGrid();
}}

function saveOverrides() {{
    localStorage.setItem('emojiColorOverrides', JSON.stringify(overrides));
}}

// ========================================
// FONT SWITCHING
// ========================================
function switchFont() {{
    const mode = document.getElementById('fontMode').value;
    if (mode === 'noto') {{
        // Ensure Noto is loaded before extracting
        document.fonts.load('1em "Noto Color Emoji"').then(() => extractAll());
    }} else {{
        extractAll();
    }}
}}

// ========================================
// FILTERING
// ========================================
function filterCards() {{
    const search = document.getElementById('search').value.toLowerCase();
    const mode = document.getElementById('filterMode').value;
    let visible = 0;

    document.querySelectorAll('.card').forEach(card => {{
        const emoji = card.dataset.emoji;
        const locations = card.dataset.locations;

        let show = true;
        if (search && !locations.includes(search) && !emoji.includes(search)) show = false;
        if (mode === 'missing' && CURATED_COLORS[emoji]) show = false;
        if (mode === 'overridden' && !overrides[emoji]) show = false;
        if (mode === 'mismatch') {{
            const ext = extractedColors[emoji];
            const cur = CURATED_COLORS[emoji];
            if (!cur || !ext || cur === ext) show = false;
        }}

        card.classList.toggle('hidden', !show);
        if (show) visible++;
    }});

    document.getElementById('statVisible').textContent = visible;
}}

// ========================================
// EXPORT
// ========================================
function exportJSON() {{
    const result = {{}};
    EMOJI_DATA.forEach(item => {{
        result[item.emoji] = getFinalColor(item.emoji);
    }});

    // Sort by emoji codepoint
    const sorted = {{}};
    Object.keys(result).sort().forEach(k => {{ sorted[k] = result[k]; }});

    const json = JSON.stringify(sorted, null, 4);

    // Copy to clipboard
    navigator.clipboard.writeText(json).then(() => {{
        alert('Copied ' + Object.keys(sorted).length + ' emoji colors to clipboard.\\n\\nPaste into src/data/tags.json under "bgcolors".');
    }}).catch(() => {{
        // Fallback: download as file
        const blob = new Blob([json], {{type: 'application/json'}});
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'bgcolors.json';
        a.click();
        URL.revokeObjectURL(url);
    }});
}}

// ========================================
// STATS
// ========================================
function updateStats() {{
    document.getElementById('statOverrides').textContent = Object.keys(overrides).length;
    document.getElementById('statVisible').textContent =
        document.querySelectorAll('.card:not(.hidden)').length;
}}

// ========================================
// INIT
// ========================================
extractAll();
</script>
</body>
</html>"""

    output_path = os.path.join(SCRIPT_DIR, 'emoji_colors.html')
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"Exported {n_total} emoji to {output_path}")
    print(f"  {n_curated} have curated colors, {n_missing} need colors")
    print(f"  Open in browser: file://{output_path}")


if __name__ == '__main__':
    main()
