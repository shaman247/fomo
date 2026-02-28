#!/usr/bin/env python3
"""Export the tag hierarchy as a browsable HTML table.

Generates scripts/tag_hierarchy.html with all curated tags sorted by
event frequency, showing parents and event count for each tag.

Usage:
    ./venv/bin/python scripts/export_tag_hierarchy_html.py
"""

import os
import sys
from html import escape

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'pipeline'))
from db import create_connection

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def main():
    conn = create_connection()
    if not conn:
        print("Failed to connect to database")
        sys.exit(1)

    cursor = conn.cursor(dictionary=True)

    # Get all curated tags with event counts
    cursor.execute("""
        SELECT t.id, t.name, t.emoji, t.type,
               COUNT(DISTINCT et.event_id) as event_count
        FROM tags t
        LEFT JOIN event_tags et ON t.id = et.tag_id
        LEFT JOIN events e ON et.event_id = e.id AND e.archived = FALSE AND e.suppressed = FALSE
        WHERE t.type = 'tag'
        GROUP BY t.id
        ORDER BY event_count DESC, t.name
    """)
    tags = cursor.fetchall()

    # Get hierarchy edges
    cursor.execute("""
        SELECT p.name AS parent_name, c.name AS child_name
        FROM tag_hierarchy th
        JOIN tags p ON th.parent_tag_id = p.id
        JOIN tags c ON th.child_tag_id = c.id
    """)
    edges = cursor.fetchall()

    parents_of = {}
    children_of = {}
    for row in edges:
        parent = row['parent_name']
        child = row['child_name']
        parents_of.setdefault(child, []).append(parent)
        children_of.setdefault(parent, []).append(child)

    # Find root tags (no parents)
    all_children = set()
    for kids in children_of.values():
        all_children.update(kids)
    root_tags = {t['name'] for t in tags if t['name'] not in all_children}

    # Compute depth for each tag
    def get_depth(name, visited=None):
        if visited is None:
            visited = set()
        if name in visited:
            return 0
        visited.add(name)
        parents = parents_of.get(name, [])
        if not parents:
            return 0
        return 1 + min(get_depth(p, visited.copy()) for p in parents)

    for t in tags:
        t['depth'] = get_depth(t['name'])
        t['parents'] = sorted(parents_of.get(t['name'], []))
        t['children'] = sorted(children_of.get(t['name'], []))

    cursor.close()
    conn.close()

    # Generate HTML
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Tag Hierarchy — fomo.nyc</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: 'SF Mono', 'Menlo', 'Consolas', monospace;
         background: #0d1117; color: #c9d1d9; padding: 20px; font-size: 13px; }}
  h1 {{ margin-bottom: 4px; font-size: 1.3em; color: #e6edf3; font-weight: 600; }}
  .subtitle {{ color: #7d8590; margin-bottom: 16px; font-size: 0.85em; }}
  .controls {{ display: flex; gap: 8px; margin-bottom: 12px; align-items: center; flex-wrap: wrap; }}
  input[type="text"] {{ padding: 6px 10px; border: 1px solid #30363d; border-radius: 6px;
                        font-size: 13px; width: 220px; background: #161b22; color: #c9d1d9;
                        font-family: inherit; }}
  input[type="text"]::placeholder {{ color: #484f58; }}
  input[type="text"]:focus {{ outline: none; border-color: #58a6ff; }}
  select {{ padding: 6px 10px; border: 1px solid #30363d; border-radius: 6px;
           font-size: 13px; background: #161b22; color: #c9d1d9; font-family: inherit; }}
  table {{ width: auto; border-collapse: collapse; }}
  thead {{ position: sticky; top: 0; z-index: 1; }}
  th {{ padding: 6px 10px; text-align: left; font-weight: 600; font-size: 12px;
        background: #161b22; color: #7d8590; border-bottom: 1px solid #21262d;
        cursor: pointer; user-select: none; white-space: nowrap;
        text-transform: uppercase; letter-spacing: 0.5px; }}
  th:hover {{ color: #c9d1d9; }}
  td {{ padding: 4px 10px; border-top: 1px solid #161b22; white-space: nowrap; }}
  tr:hover td {{ background: #161b22; }}
  .col-freq {{ text-align: right; color: #7d8590; font-variant-numeric: tabular-nums;
               padding-right: 12px; min-width: 44px; }}
  .col-freq-high {{ color: #e6edf3; font-weight: 600; }}
  .tag-name {{ color: #e6edf3; }}
  .emoji {{ margin-right: 3px; }}
  .parents, .children {{ color: #484f58; }}
  .parent-tag, .child-tag {{ color: #58a6ff; cursor: pointer; text-decoration: none; }}
  .parent-tag:hover, .child-tag:hover {{ text-decoration: underline; }}
  .sep {{ color: #30363d; margin: 0 3px; }}
  .hidden {{ display: none; }}
</style>
</head>
<body>
<h1>Tag Hierarchy</h1>
<p class="subtitle">{len(tags)} curated tags &middot; {sum(1 for t in tags if t['name'] in root_tags)} roots &middot; {len(edges)} edges</p>

<div class="controls">
  <input type="text" id="search" placeholder="Filter..." oninput="filterTable()">
  <select id="depthFilter" onchange="filterTable()">
    <option value="all">All depths</option>
    <option value="0">Roots</option>
    <option value="1">Depth 1</option>
    <option value="2">Depth 2</option>
    <option value="3">Depth 3+</option>
  </select>
  <select id="sortBy" onchange="sortTable()">
    <option value="freq-desc">Freq desc</option>
    <option value="freq-asc">Freq asc</option>
    <option value="name-asc">A → Z</option>
    <option value="depth-asc">By depth</option>
  </select>
</div>

<table id="tagTable">
<thead>
<tr>
  <th style="text-align:right;padding-right:12px" onclick="setSortAndSort(this.dataset.next);this.dataset.next=this.dataset.next==='freq-desc'?'freq-asc':'freq-desc'" data-next="freq-asc">#</th>
  <th onclick="setSortAndSort('name-asc')">Tag</th>
  <th>Parents</th>
  <th>Children</th>
</tr>
</thead>
<tbody>
"""

    for t in tags:
        name = escape(t['name'])
        emoji = escape(t['emoji']) + ' ' if t['emoji'] else ''
        count = t['event_count']
        depth = t['depth']
        parents = t['parents']

        freq_class = 'col-freq col-freq-high' if count >= 100 else 'col-freq'

        children = t['children']

        parents_html = '<span class="sep">,</span> '.join(
            f'<span class="parent-tag" onclick="searchFor(\'{escape(p)}\')">{escape(p)}</span>'
            for p in parents
        ) if parents else ''

        children_html = '<span class="sep">,</span> '.join(
            f'<span class="child-tag" onclick="searchFor(\'{escape(c)}\')">{escape(c)}</span>'
            for c in children
        ) if children else ''

        html += f"""<tr data-name="{escape(name.lower())}" data-freq="{count}" data-depth="{depth}">
  <td class="{freq_class}">{count}</td>
  <td><span class="emoji">{emoji}</span><span class="tag-name">{name}</span></td>
  <td class="parents">{parents_html}</td>
  <td class="children">{children_html}</td>
</tr>
"""

    html += """</tbody>
</table>

<script>
function filterTable() {
  const search = document.getElementById('search').value.toLowerCase();
  const depthFilter = document.getElementById('depthFilter').value;
  const rows = document.querySelectorAll('#tagTable tbody tr');
  rows.forEach(row => {
    const name = row.dataset.name;
    const depth = parseInt(row.dataset.depth);
    const matchesSearch = !search || name.includes(search) ||
      row.querySelector('.parents').textContent.toLowerCase().includes(search);
    let matchesDepth = depthFilter === 'all';
    if (depthFilter === '0') matchesDepth = depth === 0;
    else if (depthFilter === '1') matchesDepth = depth === 1;
    else if (depthFilter === '2') matchesDepth = depth === 2;
    else if (depthFilter === '3') matchesDepth = depth >= 3;
    row.classList.toggle('hidden', !(matchesSearch && matchesDepth));
  });
}

function sortTable() {
  const sortBy = document.getElementById('sortBy').value;
  const tbody = document.querySelector('#tagTable tbody');
  const rows = Array.from(tbody.querySelectorAll('tr'));
  rows.sort((a, b) => {
    if (sortBy === 'freq-desc') return parseInt(b.dataset.freq) - parseInt(a.dataset.freq);
    if (sortBy === 'freq-asc') return parseInt(a.dataset.freq) - parseInt(b.dataset.freq);
    if (sortBy === 'name-asc') return a.dataset.name.localeCompare(b.dataset.name);
    if (sortBy === 'depth-asc') {
      const d = parseInt(a.dataset.depth) - parseInt(b.dataset.depth);
      return d !== 0 ? d : parseInt(b.dataset.freq) - parseInt(a.dataset.freq);
    }
    return 0;
  });
  rows.forEach(row => tbody.appendChild(row));
}

function setSortAndSort(val) {
  document.getElementById('sortBy').value = val;
  sortTable();
}

function searchFor(term) {
  document.getElementById('search').value = term;
  filterTable();
}
</script>
</body>
</html>"""

    output_path = os.path.join(SCRIPT_DIR, 'tag_hierarchy.html')
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"Exported {len(tags)} tags to {output_path}")


if __name__ == '__main__':
    main()
