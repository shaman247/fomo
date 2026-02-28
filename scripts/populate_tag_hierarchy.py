#!/usr/bin/env python3
"""
Populate the tag hierarchy with intermediate levels and AI-classified keywords.

Phases:
  1. Fix orphan/duplicate tags (merge or reparent)
  2. Add intermediate hierarchy levels (e.g., Music → Jazz → Latin Jazz)
  3. AI-classify high-frequency keywords using Gemini → outputs review CSV
  4. Apply approved classifications from reviewed CSV

Usage:
    ./venv/bin/python scripts/populate_tag_hierarchy.py                          # Dry-run phases 1-2
    ./venv/bin/python scripts/populate_tag_hierarchy.py --apply                  # Apply phases 1-2
    ./venv/bin/python scripts/populate_tag_hierarchy.py --phase orphans          # Phase 1 only
    ./venv/bin/python scripts/populate_tag_hierarchy.py --phase intermediate     # Phase 2 only
    ./venv/bin/python scripts/populate_tag_hierarchy.py --phase classify         # Phase 3: AI → review CSV
    ./venv/bin/python scripts/populate_tag_hierarchy.py --phase apply-review     # Phase 4: apply from CSV
    ./venv/bin/python scripts/populate_tag_hierarchy.py --verify                 # Post-apply checks
"""

import argparse
import asyncio
import csv
import os
import sys
from datetime import datetime
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'pipeline'))
from db import create_connection, build_tag_ancestor_map

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Gemini setup (only needed for Phase 3)
try:
    from dotenv import load_dotenv
    load_dotenv()
    from google import genai
    from google.genai import types as genai_types
    from pydantic import BaseModel, Field
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
    GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-preview-05-20")
    GEMINI_TIMEOUT = int(os.environ.get("GEMINI_TIMEOUT", "120"))
    if GEMINI_API_KEY:
        genai_client = genai.Client(api_key=GEMINI_API_KEY)
    else:
        genai_client = None
except ImportError:
    genai_client = None
    GEMINI_API_KEY = None
    GEMINI_MODEL = None
    GEMINI_TIMEOUT = 120
    BaseModel = None


# =============================================================================
# Phase 1: Orphan/Duplicate Tag Fixes
# =============================================================================

# (orphan_name, canonical_name, action)
# "merge" = reassign event_tags + location_tags, delete orphan
# "child" = add as child of canonical (keep the tag)
ORPHAN_MERGES = [
    ("Night Life",       "Nightlife",        "merge"),
    ("Story Time",       "Storytime",        "merge"),
    ("Arts",             "Art",              "merge"),
    ("Fine Arts",        "Art",              "merge"),
    ("Theatre",          "Theater",          "merge"),
    ("Musical Theatre",  "Musical Theater",  "merge"),
    ("Creative Arts",    "Art",              "child"),
    ("Performing Arts",  "Theater",          "child"),
    # Round 2: additional orphans found during verification
    ("Hand Made",        "Handmade",         "merge"),
    ("Maker Space",      "Makerspace",       "merge"),
    ("Neuro Science",    "Neuroscience",     "merge"),
    ("Nonfiction",       "Non Fiction",      "merge"),
    ("Print Making",     "Printmaking",      "merge"),
    ("Synthpop",         "Synth Pop",        "merge"),
]


def find_tag_id(cursor, name):
    """Find a tag by exact name. Returns id or None."""
    cursor.execute("SELECT id FROM tags WHERE name = %s", (name,))
    row = cursor.fetchone()
    return row['id'] if isinstance(row, dict) else (row[0] if row else None)


def find_or_create_tag(cursor, name, tag_type='tag'):
    """Find a tag by name, or create it. Returns tag id."""
    tag_id = find_tag_id(cursor, name)
    if tag_id:
        return tag_id
    cursor.execute("INSERT INTO tags (name, type) VALUES (%s, %s)", (name, tag_type))
    return cursor.lastrowid


def phase_orphans(cursor, conn, apply=False):
    """Phase 1: Fix orphan/duplicate tags."""
    print("\n" + "=" * 60)
    print("PHASE 1: Fix Orphan/Duplicate Tags")
    print("=" * 60)

    for orphan_name, canonical_name, action in ORPHAN_MERGES:
        orphan_id = find_tag_id(cursor, orphan_name)
        canonical_id = find_tag_id(cursor, canonical_name)

        if not orphan_id:
            print(f"  SKIP: '{orphan_name}' not found in database")
            continue
        if not canonical_id:
            print(f"  SKIP: '{canonical_name}' not found in database")
            continue

        if action == "merge":
            # Count affected events/locations
            cursor.execute("SELECT COUNT(*) as cnt FROM event_tags WHERE tag_id = %s", (orphan_id,))
            row = cursor.fetchone()
            event_count = row['cnt'] if isinstance(row, dict) else row[0]

            cursor.execute("SELECT COUNT(*) as cnt FROM location_tags WHERE tag_id = %s", (orphan_id,))
            row = cursor.fetchone()
            location_count = row['cnt'] if isinstance(row, dict) else row[0]

            print(f"  MERGE: '{orphan_name}' → '{canonical_name}' "
                  f"({event_count} events, {location_count} locations)")

            if apply:
                # Reassign event_tags (skip dupes)
                cursor.execute(
                    "UPDATE IGNORE event_tags SET tag_id = %s WHERE tag_id = %s",
                    (canonical_id, orphan_id))
                cursor.execute(
                    "DELETE FROM event_tags WHERE tag_id = %s", (orphan_id,))
                # Reassign location_tags
                cursor.execute(
                    "UPDATE IGNORE location_tags SET tag_id = %s WHERE tag_id = %s",
                    (canonical_id, orphan_id))
                cursor.execute(
                    "DELETE FROM location_tags WHERE tag_id = %s", (orphan_id,))
                # Remove hierarchy references
                cursor.execute(
                    "DELETE FROM tag_hierarchy WHERE child_tag_id = %s OR parent_tag_id = %s",
                    (orphan_id, orphan_id))
                # Delete orphan tag
                cursor.execute("DELETE FROM tags WHERE id = %s", (orphan_id,))

        elif action == "child":
            # Check if relationship already exists
            cursor.execute(
                "SELECT 1 FROM tag_hierarchy WHERE parent_tag_id = %s AND child_tag_id = %s",
                (canonical_id, orphan_id))
            if cursor.fetchone():
                print(f"  SKIP: '{orphan_name}' already a child of '{canonical_name}'")
                continue

            print(f"  CHILD: '{orphan_name}' → child of '{canonical_name}'")
            if apply:
                cursor.execute(
                    "INSERT IGNORE INTO tag_hierarchy (parent_tag_id, child_tag_id) VALUES (%s, %s)",
                    (canonical_id, orphan_id))

    if apply:
        conn.commit()
        print("\n  Changes applied.")
    else:
        print("\n  [DRY-RUN] No changes applied.")


# =============================================================================
# Phase 2: Intermediate Hierarchy Levels
# =============================================================================

INTERMEDIATE_LEVELS = {
    "Music": {
        "Jazz": [
            "Latin Jazz", "Contemporary Jazz", "Modern Jazz",
            "Experimental Jazz", "Jazz Fusion",
            "Jazz Guitar", "Jazz Piano", "Jazz Quartet",
            "Jazz Trio", "Jazz Vocals", "Vocal Jazz",
        ],
        "Classical Music": [
            "Chamber Music", "Contemporary Classical", "Orchestra",
            "Choral Music", "String Quartet",
        ],
        "Electronic Music": [
            "House Music", "Techno", "Deep House",
            "Disco", "Bass Music", "Dance Music", "Synth Pop",
        ],
        "Rock": [
            "Indie Rock", "Punk Rock", "Classic Rock",
            "Alternative Rock", "Post Punk", "Folk Rock",
            "Blues Rock", "Rock and Roll", "Rock Music",
        ],
        "Hip Hop": ["Hip Hop Dance"],
        "Folk Music": [
            "Indie Folk", "Americana",
        ],
        "Blues": [
            "Blues Rock",
        ],
        "Live Music": [
            "Live Jazz", "Live Concert", "Live Show",
            "Live Entertainment", "Live Comedy",
        ],
        "Vocal Music": [
            "Singer Songwriter", "Vocalist", "Vocal Performance",
            "A Cappella",
        ],
    },
    "Art": {
        "Visual Arts": [
            "Photography", "Sculpture", "Painting", "Illustration",
            "Digital Art", "Public Art", "Modern Art", "Contemporary Art",
            "Graphic Design", "Fine Art", "Printmaking",
        ],
        "Crafts": [
            "Ceramics", "DIY", "Handmade", "Arts and Crafts",
            "Crafting", "Fiber Arts", "Makerspace",
        ],
    },
    "Film": {
        "Classic Film": [
            "Classic Cinema", "Cult Classic", "Cult Film",
        ],
    },
    "Theater": {
        "Musical Theater": [
            "Musical", "Musical Comedy",
        ],
    },
    "Community": {
        "Activism": [
            "Social Justice", "Civic Engagement", "Human Rights",
            "Civil Rights", "Advocacy", "Empowerment",
        ],
        "Cultural Heritage": [
            "Cultural Celebration", "Cultural Event", "Black History",
            "Black History Month",
        ],
        "Science": [
            "STEM", "Technology", "Artificial Intelligence", "Neuroscience",
        ],
    },
}

# Additional cross-cutting parent edges (DAG: child gets multiple parents).
# Format: (child_tag, additional_parent) — adds parent WITHOUT removing existing ones.
ADDITIONAL_PARENTS = [
    # "Live Jazz" is under "Live Music" (via INTERMEDIATE_LEVELS) AND also under "Jazz"
    ("Live Jazz",           "Jazz"),
    # "Live Comedy" is under "Live Music" AND also under "Comedy"
    ("Live Comedy",         "Comedy"),
    # "Live Concert" also under general Music (already via Live Music → Music)
    # "Hip Hop Dance" also under "Dance"
    ("Hip Hop Dance",       "Dance"),
    # "Blues Rock" under both Rock and Blues
    ("Blues Rock",          "Blues"),
    # "Singer Songwriter" also under Literature (for spoken word / poetry crossover)
    # "Vocal Jazz" under both Jazz and Vocal Music
    ("Vocal Jazz",          "Vocal Music"),
    ("Jazz Vocals",         "Vocal Music"),
    # Indie crossovers
    ("Indie Pop",           "Rock"),
    ("Indie Music",         "Rock"),
    # "Folk Rock" under both Rock and Folk Music
    ("Folk Rock",           "Folk Music"),
    # "Dance Party" under both Nightlife and Dance
    ("Dance Party",         "Dance"),
    # "Social Dance" under both Dance and Nightlife
    ("Social Dance",        "Nightlife"),
]


def phase_intermediate(cursor, conn, apply=False):
    """Phase 2: Add intermediate hierarchy levels."""
    print("\n" + "=" * 60)
    print("PHASE 2: Add Intermediate Hierarchy Levels")
    print("=" * 60)

    relationships_added = 0
    relationships_removed = 0
    tags_created = 0

    for root_name, intermediates in INTERMEDIATE_LEVELS.items():
        root_id = find_tag_id(cursor, root_name)
        if not root_id:
            print(f"\n  WARNING: Root tag '{root_name}' not found!")
            continue

        print(f"\n  {root_name}:")

        for intermediate_name, children in intermediates.items():
            # Find or create the intermediate tag
            intermediate_id = find_tag_id(cursor, intermediate_name)
            created = False
            if not intermediate_id:
                if apply:
                    intermediate_id = find_or_create_tag(cursor, intermediate_name, 'tag')
                    created = True
                    tags_created += 1
                else:
                    created = True
                    tags_created += 1

            if not created and apply:
                # Ensure it's type='tag'
                cursor.execute("UPDATE tags SET type = 'tag' WHERE id = %s AND type != 'tag'",
                               (intermediate_id,))

            tag_label = f"[NEW] {intermediate_name}" if created else intermediate_name
            print(f"    {tag_label} ({len(children)} children)")

            # Add root → intermediate relationship
            if apply and intermediate_id:
                cursor.execute(
                    "INSERT IGNORE INTO tag_hierarchy (parent_tag_id, child_tag_id) VALUES (%s, %s)",
                    (root_id, intermediate_id))
                if cursor.rowcount > 0:
                    relationships_added += 1
            else:
                relationships_added += 1  # Count for dry-run

            # Reparent children from root → intermediate
            for child_name in children:
                child_id = find_tag_id(cursor, child_name)
                if not child_id:
                    print(f"      SKIP: '{child_name}' not found")
                    continue

                if apply and intermediate_id:
                    # Remove direct root → child edge
                    cursor.execute(
                        "DELETE FROM tag_hierarchy WHERE parent_tag_id = %s AND child_tag_id = %s",
                        (root_id, child_id))
                    if cursor.rowcount > 0:
                        relationships_removed += 1

                    # Add intermediate → child edge
                    cursor.execute(
                        "INSERT IGNORE INTO tag_hierarchy (parent_tag_id, child_tag_id) VALUES (%s, %s)",
                        (intermediate_id, child_id))
                    if cursor.rowcount > 0:
                        relationships_added += 1
                else:
                    print(f"      {child_name}: {root_name} → {intermediate_name} → {child_name}")
                    relationships_removed += 1
                    relationships_added += 1

    # Apply additional cross-cutting parent edges
    if ADDITIONAL_PARENTS:
        print(f"\n  Cross-cutting parent edges:")
        for child_name, parent_name in ADDITIONAL_PARENTS:
            child_id = find_tag_id(cursor, child_name)
            parent_id = find_tag_id(cursor, parent_name)
            if not child_id:
                print(f"    SKIP: '{child_name}' not found")
                continue
            if not parent_id:
                print(f"    SKIP: parent '{parent_name}' not found")
                continue

            if apply:
                cursor.execute(
                    "INSERT IGNORE INTO tag_hierarchy (parent_tag_id, child_tag_id) VALUES (%s, %s)",
                    (parent_id, child_id))
                if cursor.rowcount > 0:
                    relationships_added += 1
                    print(f"    {child_name} ← {parent_name}")
            else:
                print(f"    {child_name} ← {parent_name} (additional parent)")
                relationships_added += 1

    # Cycle detection
    if apply:
        print("\n  Checking for cycles...")
        if _detect_cycles(cursor):
            print("  CYCLE DETECTED! Rolling back.")
            conn.rollback()
            return
        print("  No cycles detected.")
        conn.commit()
        print(f"\n  Applied: {tags_created} tags created, "
              f"{relationships_added} relationships added, "
              f"{relationships_removed} removed.")
    else:
        print(f"\n  [DRY-RUN] Would create {tags_created} tags, "
              f"add {relationships_added} relationships, "
              f"remove {relationships_removed}.")


def _detect_cycles(cursor):
    """Check for cycles in the tag hierarchy. Returns True if cycle found."""
    cursor.execute("SELECT parent_tag_id, child_tag_id FROM tag_hierarchy")
    rows = cursor.fetchall()
    children_of = {}
    for row in rows:
        parent = row['parent_tag_id'] if isinstance(row, dict) else row[0]
        child = row['child_tag_id'] if isinstance(row, dict) else row[1]
        children_of.setdefault(parent, set()).add(child)

    def has_cycle(start, visited=None):
        if visited is None:
            visited = set()
        if start in visited:
            return True
        visited.add(start)
        for child in children_of.get(start, set()):
            if has_cycle(child, visited.copy()):
                return True
        return False

    for node in children_of:
        if has_cycle(node):
            return True
    return False


# =============================================================================
# Phase 3: AI Classification of Keywords
# =============================================================================

CLASSIFICATION_PROMPT = """You are classifying keywords for an NYC events map (fomo.nyc).
The map organizes events into a hierarchy of tags. Below is the current tag hierarchy.

CURRENT HIERARCHY:
{hierarchy_text}

INSTRUCTIONS:
For each keyword below, decide one of three actions:

1. "promote" — This keyword represents a meaningful event category or genre. It should become
   a curated tag in the hierarchy. Specify which existing parent tag(s) it belongs under.
   Only promote keywords that represent genuine event types, genres, activities, or themes.
   Do NOT promote:
   - Proper nouns (artist names, venue names like "Brooklyn Museum", "John Coltrane")
   - Generic adjectives ("Amazing", "Best", "New", "Special")
   - Time/date terms ("Weekend", "Tonight", "Spring 2026", "Saturday")
   - Specific location/neighborhood names ("Brooklyn", "Manhattan", "Harlem", "Bushwick")
   - Event series names or branded event names
   - Overly specific terms that would only match a handful of events conceptually

2. "skip" — This keyword is fine as-is (stays as a searchable keyword, not in the hierarchy).
   Use this for proper nouns, adjectives, place names, branded terms, and overly specific terms.

3. "merge" — This keyword is a synonym, alternate spelling, or close variant of an existing
   curated tag. Specify which existing tag it should merge into.
   Examples: "Standup" → "Stand-up", "Hip-Hop" → "Hip Hop"

KEYWORDS TO CLASSIFY (keyword: event_count):
{keywords_text}

For each keyword, provide:
- action: "promote", "skip", or "merge"
- parent_tags: list of parent tag names (only for promote; must be existing tags from the hierarchy)
- merge_into: existing tag name (only for merge)
- reasoning: one sentence explaining the decision
- confidence: "high", "medium", or "low"
"""


def _build_hierarchy_text(cursor):
    """Build a human-readable representation of the current tag hierarchy."""
    cursor.execute("""
        SELECT p.name AS parent_name, c.name AS child_name
        FROM tag_hierarchy th
        JOIN tags p ON th.parent_tag_id = p.id
        JOIN tags c ON th.child_tag_id = c.id
        WHERE p.type = 'tag' AND c.type = 'tag'
        ORDER BY p.name, c.name
    """)
    rows = cursor.fetchall()

    children_of = {}
    for row in rows:
        parent = row['parent_name'] if isinstance(row, dict) else row[0]
        child = row['child_name'] if isinstance(row, dict) else row[1]
        children_of.setdefault(parent, []).append(child)

    # Find roots (parents that are not children)
    all_children = set()
    for kids in children_of.values():
        all_children.update(kids)
    roots = sorted(k for k in children_of if k not in all_children)

    lines = []
    for root in roots:
        lines.append(f"- {root}")
        for child in sorted(children_of.get(root, [])):
            grandchildren = children_of.get(child, [])
            if grandchildren:
                lines.append(f"  - {child}")
                for gc in sorted(grandchildren):
                    lines.append(f"    - {gc}")
            else:
                lines.append(f"  - {child}")

    return "\n".join(lines)


def _get_keyword_candidates(cursor, min_events=20):
    """Get keywords with at least min_events events."""
    cursor.execute("""
        SELECT t.id, t.name, COUNT(et.event_id) as event_count
        FROM tags t
        JOIN event_tags et ON t.id = et.tag_id
        WHERE t.type = 'keyword'
        GROUP BY t.id
        HAVING event_count >= %s
        ORDER BY event_count DESC
    """, (min_events,))
    rows = cursor.fetchall()
    return [
        {
            'id': row['id'] if isinstance(row, dict) else row[0],
            'name': row['name'] if isinstance(row, dict) else row[1],
            'event_count': row['event_count'] if isinstance(row, dict) else row[2],
        }
        for row in rows
    ]


def _get_existing_tag_names(cursor):
    """Get set of all curated tag names for validation."""
    cursor.execute("SELECT name FROM tags WHERE type = 'tag'")
    return {(row['name'] if isinstance(row, dict) else row[0]) for row in cursor.fetchall()}


async def _classify_batch(keywords_batch, hierarchy_text, existing_tags):
    """Classify a batch of keywords using Gemini."""
    if not genai_client:
        raise RuntimeError("Gemini client not initialized. Set GEMINI_API_KEY.")
    if not BaseModel:
        raise RuntimeError("pydantic not installed.")

    # Define Pydantic models here (requires BaseModel to be available)
    class KeywordClassification(BaseModel):
        keyword: str = Field(description="The keyword being classified")
        action: str = Field(description="One of: 'promote', 'skip', 'merge'")
        parent_tags: list[str] = Field(
            default_factory=list,
            description="Parent tag(s) if action='promote' (must be existing tags)")
        merge_into: Optional[str] = Field(
            default=None,
            description="Existing tag to merge into if action='merge'")
        reasoning: str = Field(description="One sentence explaining the decision")
        confidence: str = Field(description="'high', 'medium', or 'low'")

    class ClassificationBatch(BaseModel):
        classifications: list[KeywordClassification]

    keywords_text = "\n".join(
        f"- {kw['name']}: {kw['event_count']} events"
        for kw in keywords_batch
    )
    prompt = CLASSIFICATION_PROMPT.format(
        hierarchy_text=hierarchy_text,
        keywords_text=keywords_text,
    )

    response = await asyncio.wait_for(
        genai_client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": ClassificationBatch,
            },
        ),
        timeout=GEMINI_TIMEOUT,
    )

    batch_result = ClassificationBatch.model_validate_json(response.text)
    results = []
    for c in batch_result.classifications:
        d = c.model_dump()
        # Validate parent_tags exist
        if d['action'] == 'promote':
            invalid = [p for p in d['parent_tags'] if p not in existing_tags]
            if invalid:
                d['reasoning'] += f" [WARNING: invalid parents: {', '.join(invalid)}]"
                d['confidence'] = 'low'
        if d['action'] == 'merge' and d.get('merge_into') and d['merge_into'] not in existing_tags:
            d['reasoning'] += f" [WARNING: merge target '{d['merge_into']}' not found]"
            d['confidence'] = 'low'
        results.append(d)
    return results


async def phase_classify(cursor, min_events=20, batch_size=50):
    """Phase 3: AI-classify keywords and output review CSV."""
    print("\n" + "=" * 60)
    print("PHASE 3: AI Classification of Keywords")
    print("=" * 60)

    if not genai_client:
        print("  ERROR: Gemini client not available. Set GEMINI_API_KEY.")
        return

    # Get candidates
    candidates = _get_keyword_candidates(cursor, min_events)
    print(f"  Found {len(candidates)} keywords with >= {min_events} events")

    if not candidates:
        print("  No candidates to classify.")
        return

    # Build hierarchy text and get existing tags
    hierarchy_text = _build_hierarchy_text(cursor)
    existing_tags = _get_existing_tag_names(cursor)

    # Process in batches
    all_results = []
    batches = [candidates[i:i+batch_size] for i in range(0, len(candidates), batch_size)]
    total_batches = len(batches)

    for i, batch in enumerate(batches, 1):
        print(f"\n  Batch {i}/{total_batches}: classifying {len(batch)} keywords...")
        try:
            results = await _classify_batch(batch, hierarchy_text, existing_tags)
            # Attach event counts
            count_map = {kw['name']: kw['event_count'] for kw in batch}
            for r in results:
                r['event_count'] = count_map.get(r['keyword'], 0)
            all_results.extend(results)

            counts = {'promote': 0, 'skip': 0, 'merge': 0}
            for r in results:
                counts[r.get('action', 'skip')] = counts.get(r.get('action', 'skip'), 0) + 1
            print(f"    → {counts.get('promote', 0)} promote, "
                  f"{counts.get('skip', 0)} skip, "
                  f"{counts.get('merge', 0)} merge")

        except Exception as e:
            print(f"    → ERROR: {e}")
            # Add unclassified entries for this batch
            for kw in batch:
                all_results.append({
                    'keyword': kw['name'],
                    'event_count': kw['event_count'],
                    'action': 'skip',
                    'parent_tags': [],
                    'merge_into': None,
                    'reasoning': f'Classification failed: {e}',
                    'confidence': 'low',
                })

    # Write review CSV
    timestamp = datetime.now().strftime('%Y%m%d')
    csv_path = os.path.join(SCRIPT_DIR, f'tag_classification_review_{timestamp}.csv')
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'keyword', 'event_count', 'action', 'parent_tags',
            'merge_into', 'reasoning', 'confidence', 'approved',
        ])
        writer.writeheader()
        for r in all_results:
            writer.writerow({
                'keyword': r['keyword'],
                'event_count': r.get('event_count', ''),
                'action': r['action'],
                'parent_tags': '|'.join(r.get('parent_tags', [])),
                'merge_into': r.get('merge_into', '') or '',
                'reasoning': r['reasoning'],
                'confidence': r['confidence'],
                'approved': '',
            })

    # Summary
    totals = {'promote': 0, 'skip': 0, 'merge': 0}
    for r in all_results:
        totals[r.get('action', 'skip')] = totals.get(r.get('action', 'skip'), 0) + 1

    print(f"\n{'=' * 60}")
    print(f"Classification Summary:")
    print(f"  Total classified: {len(all_results)}")
    print(f"  Promote: {totals['promote']} ({100*totals['promote']/max(len(all_results),1):.0f}%)")
    print(f"  Skip:    {totals['skip']} ({100*totals['skip']/max(len(all_results),1):.0f}%)")
    print(f"  Merge:   {totals['merge']} ({100*totals['merge']/max(len(all_results),1):.0f}%)")
    print(f"\n  Review file: {csv_path}")
    print(f"  Edit the 'approved' column (yes/no), then run:")
    print(f"  ./venv/bin/python scripts/populate_tag_hierarchy.py --phase apply-review "
          f"--review-file {csv_path} --apply")


# =============================================================================
# Phase 4: Apply Reviewed Classifications
# =============================================================================

def phase_apply_review(cursor, conn, review_file, apply=False):
    """Phase 4: Apply approved classifications from review CSV."""
    print("\n" + "=" * 60)
    print("PHASE 4: Apply Reviewed Classifications")
    print("=" * 60)

    if not os.path.exists(review_file):
        print(f"  ERROR: Review file not found: {review_file}")
        return

    with open(review_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    approved = [r for r in rows if r.get('approved', '').strip().lower() == 'yes']
    print(f"  Total rows: {len(rows)}")
    print(f"  Approved: {len(approved)}")

    if not approved:
        print("  No approved entries to apply.")
        return

    promoted = 0
    merged = 0
    skipped = 0
    errors = 0

    for row in approved:
        keyword = row['keyword']
        action = row['action']

        if action == 'promote':
            parent_tags = [p.strip() for p in row.get('parent_tags', '').split('|') if p.strip()]
            tag_id = find_tag_id(cursor, keyword)
            if not tag_id:
                print(f"  ERROR: Tag '{keyword}' not found in database")
                errors += 1
                continue

            print(f"  PROMOTE: '{keyword}' → parents: {parent_tags}")
            if apply:
                cursor.execute("UPDATE tags SET type = 'tag' WHERE id = %s", (tag_id,))
                for parent_name in parent_tags:
                    parent_id = find_tag_id(cursor, parent_name)
                    if not parent_id:
                        print(f"    WARNING: Parent '{parent_name}' not found, skipping")
                        continue
                    cursor.execute(
                        "INSERT IGNORE INTO tag_hierarchy (parent_tag_id, child_tag_id) "
                        "VALUES (%s, %s)", (parent_id, tag_id))
            promoted += 1

        elif action == 'merge':
            merge_into = row.get('merge_into', '').strip()
            if not merge_into:
                print(f"  ERROR: No merge target for '{keyword}'")
                errors += 1
                continue

            orphan_id = find_tag_id(cursor, keyword)
            canonical_id = find_tag_id(cursor, merge_into)
            if not orphan_id:
                print(f"  ERROR: '{keyword}' not found")
                errors += 1
                continue
            if not canonical_id:
                print(f"  ERROR: Merge target '{merge_into}' not found")
                errors += 1
                continue

            print(f"  MERGE: '{keyword}' → '{merge_into}'")
            if apply:
                cursor.execute(
                    "UPDATE IGNORE event_tags SET tag_id = %s WHERE tag_id = %s",
                    (canonical_id, orphan_id))
                cursor.execute("DELETE FROM event_tags WHERE tag_id = %s", (orphan_id,))
                cursor.execute(
                    "UPDATE IGNORE location_tags SET tag_id = %s WHERE tag_id = %s",
                    (canonical_id, orphan_id))
                cursor.execute("DELETE FROM location_tags WHERE tag_id = %s", (orphan_id,))
                cursor.execute(
                    "DELETE FROM tag_hierarchy WHERE child_tag_id = %s OR parent_tag_id = %s",
                    (orphan_id, orphan_id))
                cursor.execute("DELETE FROM tags WHERE id = %s", (orphan_id,))
            merged += 1

        elif action == 'skip':
            skipped += 1
        else:
            print(f"  WARNING: Unknown action '{action}' for '{keyword}'")
            errors += 1

    if apply:
        # Cycle detection
        print("\n  Checking for cycles...")
        if _detect_cycles(cursor):
            print("  CYCLE DETECTED! Rolling back.")
            conn.rollback()
            return
        print("  No cycles detected.")
        conn.commit()

    print(f"\n  Summary: {promoted} promoted, {merged} merged, {skipped} skipped, {errors} errors")
    if not apply:
        print("  [DRY-RUN] No changes applied.")


# =============================================================================
# Phase 6: Geographic Hierarchy
# =============================================================================

# Root → borough/region → neighborhood structure.
# Tags are promoted from keyword → tag (or created) and placed in hierarchy.
# Comprehensive list sourced from src/data/tags.json geotags.
GEOGRAPHIC_HIERARCHY = {
    "Neighborhood": {
        "Manhattan": [
            "Battery Park City", "Central Park", "Chelsea", "Chinatown",
            "Civic Center", "Columbus Circle", "East Harlem", "East Village",
            "Financial District", "Flatiron", "Gramercy", "Greenwich Village",
            "Hamilton Heights", "Harlem", "Hell's Kitchen", "Herald Square",
            "Inwood", "Kips Bay", "Little Italy", "Lower East Side",
            "Lower Manhattan", "Midtown", "Midtown East", "Midtown West",
            "Morningside Heights", "Murray Hill", "NoHo", "NoMad", "Nolita",
            "Randall's Island", "Roosevelt Island", "SoHo",
            "Stuyvesant Town", "Theater District", "Times Square",
            "Tribeca", "Union Square", "Upper East Side", "Upper West Side",
            "Washington Heights", "West Village",
        ],
        "Brooklyn": [
            "Bay Ridge", "Bed-Stuy", "Bensonhurst", "Bergen Beach",
            "Boerum Hill", "Borough Park", "Brighton Beach",
            "Brooklyn Heights", "Brownsville", "Bushwick", "Canarsie",
            "Carroll Gardens", "Clinton Hill", "Cobble Hill", "Columbia St",
            "Coney Island", "Crown Heights", "Cypress Hills",
            "Downtown Brooklyn", "DUMBO", "Dyker Heights", "East Flatbush",
            "East New York", "East Williamsburg", "Flatbush", "Flatlands",
            "Fort Greene", "Fort Hamilton", "Gerritsen Beach", "Gowanus",
            "Gravesend", "Green-Wood Cemetery", "Greenpoint", "Kensington",
            "Manhattan Beach", "Marine Park", "Midwood", "Navy Yard",
            "Park Slope", "Prospect Heights", "Prospect Park",
            "Prospect-Lefferts Gardens", "Red Hook", "Sheepshead Bay",
            "South Slope", "Sunset Park", "Williamsburg", "Windsor Terrace",
        ],
        "Queens": [
            "Alley Pond Park", "Astoria", "Bay Terrace", "Bayside",
            "Bayswater", "Bellerose", "Breezy Point", "Briarwood",
            "Broad Channel", "Cambria Heights", "College Point", "Corona",
            "Cunningham Park", "Ditmars Steinway", "Douglaston",
            "East Elmhurst", "Edgemere", "Elmhurst", "Far Rockaway",
            "Floral Park", "Flushing", "Flushing Meadows Corona Park",
            "Forest Hills", "Forest Park", "Fresh Meadows", "Glendale",
            "Hollis Hills", "Holliswood", "Howard Beach", "Jackson Heights",
            "Jamaica", "Kew Gardens Hills", "Laurelton", "Long Island City",
            "Maspeth", "Middle Village", "Ozone Park", "Queens Village",
            "Rego Park", "Richmond Hill", "Ridgewood", "Rockaway",
            "Rockaway Beach", "Rockaway Park", "Rosedale",
            "South Ozone Park", "Springfield Gardens", "St. Albans",
            "Sunnyside", "Whitestone", "Woodhaven", "Woodside",
        ],
        "Bronx": [
            "Allerton", "Baychester", "Belmont", "Bronx Park", "Bronxdale",
            "City Island", "Claremont Village", "Clason Point", "Co-op City",
            "Concourse", "Concourse Village", "Crotona Park", "Edenwald",
            "Ferry Point Park", "Fordham", "Highbridge", "Hunts Point",
            "Kingsbridge", "Longwood", "Melrose", "Morris Heights",
            "Morris Park", "Morrisania", "Mott Haven", "North Riverdale",
            "Norwood", "Parkchester", "Pelham Bay", "Pelham Bay Park",
            "Riverdale", "Schuylerville", "South Bronx", "Throgs Neck",
            "Tremont", "University Heights", "Van Cortlandt Park",
            "Wakefield", "West Farms", "Westchester Square", "Woodlawn",
        ],
        "Staten Island": [
            "Arrochar", "Bay Terrace, Staten Island", "Bull's Head",
            "Castleton Corners", "Charleston", "Freshkills Park",
            "Graniteville", "Great Kills", "Great Kills Park", "Huguenot",
            "Latourette Park", "Mariners Harbor", "New Dorp",
            "New Springville", "Port Richmond", "Prince's Bay",
            "Randall Manor", "Shore Acres", "Silver Lake", "South Beach",
            "St. George", "Stapleton", "Todt Hill", "Tottenville",
            "West Brighton", "Westerleigh",
        ],
        "Long Island": [],
        "Westchester": [
            "Yonkers",
        ],
        "Hudson Valley": [],
        "New Jersey": [
            "Hoboken", "Jersey City", "Newark", "Union City",
        ],
        "Connecticut": [],
    },
}

# Geographic keyword merges (alternate spellings → canonical).
GEOGRAPHIC_MERGES = [
    ("Bedford-Stuyvesant", "Bed-Stuy"),
    ("Hells Kitchen",      "Hell's Kitchen"),
    ("The Bronx",          "Bronx"),
    ("LIC",                "Long Island City"),
    ("LES",                "Lower East Side"),
    ("UES",                "Upper East Side"),
    ("UWS",                "Upper West Side"),
    ("Dumbo",              "DUMBO"),
    ("Flatiron District",  "Flatiron"),
    ("Northern New Jersey", "New Jersey"),
    ("Southern Connecticut", "Connecticut"),
]


def phase_geographic(cursor, conn, apply=False):
    """Phase 6: Build geographic hierarchy (Neighborhood → Borough → Neighborhood)."""
    print("\n" + "=" * 60)
    print("PHASE 6: Geographic Hierarchy")
    print("=" * 60)

    # --- Merge geographic aliases first ---
    print("\n  Merging geographic aliases:")
    for orphan_name, canonical_name in GEOGRAPHIC_MERGES:
        orphan_id = find_tag_id(cursor, orphan_name)
        if not orphan_id:
            print(f"    SKIP: '{orphan_name}' not found")
            continue
        canonical_id = find_tag_id(cursor, canonical_name)
        if not canonical_id:
            # The canonical might not exist yet — it'll be created below
            print(f"    SKIP: '{canonical_name}' not found yet (will be created)")
            continue

        # Guard: case-insensitive collation may resolve both names to the same row
        if orphan_id == canonical_id:
            print(f"    SKIP: '{orphan_name}' and '{canonical_name}' resolve to same tag (id={orphan_id})")
            continue

        cursor.execute("SELECT COUNT(*) as cnt FROM event_tags WHERE tag_id = %s", (orphan_id,))
        row = cursor.fetchone()
        event_count = row['cnt'] if isinstance(row, dict) else row[0]
        print(f"    MERGE: '{orphan_name}' → '{canonical_name}' ({event_count} events)")

        if apply:
            cursor.execute(
                "UPDATE IGNORE event_tags SET tag_id = %s WHERE tag_id = %s",
                (canonical_id, orphan_id))
            cursor.execute("DELETE FROM event_tags WHERE tag_id = %s", (orphan_id,))
            cursor.execute(
                "UPDATE IGNORE location_tags SET tag_id = %s WHERE tag_id = %s",
                (canonical_id, orphan_id))
            cursor.execute("DELETE FROM location_tags WHERE tag_id = %s", (orphan_id,))
            cursor.execute(
                "DELETE FROM tag_hierarchy WHERE child_tag_id = %s OR parent_tag_id = %s",
                (orphan_id, orphan_id))
            cursor.execute("DELETE FROM tags WHERE id = %s", (orphan_id,))

    # --- Build hierarchy ---
    tags_created = 0
    tags_promoted = 0
    relationships_added = 0

    for root_name, boroughs in GEOGRAPHIC_HIERARCHY.items():
        # Find or create the root
        root_id = find_tag_id(cursor, root_name)
        if not root_id:
            print(f"\n  Creating root: '{root_name}'")
            if apply:
                root_id = find_or_create_tag(cursor, root_name, 'tag')
            tags_created += 1
        else:
            if apply:
                cursor.execute("UPDATE tags SET type = 'tag' WHERE id = %s AND type != 'tag'",
                               (root_id,))
                if cursor.rowcount > 0:
                    tags_promoted += 1

        print(f"\n  {root_name}:")
        for borough_name, neighborhoods in boroughs.items():
            # Find or create borough
            borough_id = find_tag_id(cursor, borough_name)
            created = False
            if not borough_id:
                if apply:
                    borough_id = find_or_create_tag(cursor, borough_name, 'tag')
                    created = True
                tags_created += 1
            else:
                if apply:
                    cursor.execute("UPDATE tags SET type = 'tag' WHERE id = %s AND type != 'tag'",
                                   (borough_id,))
                    if cursor.rowcount > 0:
                        tags_promoted += 1

            label = f"[NEW] {borough_name}" if created else borough_name
            print(f"    {label} ({len(neighborhoods)} neighborhoods)")

            # Add root → borough edge
            if apply and root_id and borough_id:
                cursor.execute(
                    "INSERT IGNORE INTO tag_hierarchy (parent_tag_id, child_tag_id) VALUES (%s, %s)",
                    (root_id, borough_id))
                if cursor.rowcount > 0:
                    relationships_added += 1
            else:
                relationships_added += 1

            # Add borough → neighborhood edges
            for hood_name in neighborhoods:
                hood_id = find_tag_id(cursor, hood_name)
                if not hood_id:
                    if apply:
                        hood_id = find_or_create_tag(cursor, hood_name, 'tag')
                    tags_created += 1
                    print(f"      [NEW] {hood_name}")
                else:
                    if apply:
                        cursor.execute("UPDATE tags SET type = 'tag' WHERE id = %s AND type != 'tag'",
                                       (hood_id,))
                        if cursor.rowcount > 0:
                            tags_promoted += 1

                if apply and borough_id and hood_id:
                    cursor.execute(
                        "INSERT IGNORE INTO tag_hierarchy (parent_tag_id, child_tag_id) VALUES (%s, %s)",
                        (borough_id, hood_id))
                    if cursor.rowcount > 0:
                        relationships_added += 1
                else:
                    relationships_added += 1

    if apply:
        print("\n  Checking for cycles...")
        if _detect_cycles(cursor):
            print("  CYCLE DETECTED! Rolling back.")
            conn.rollback()
            return
        print("  No cycles detected.")
        conn.commit()
        print(f"\n  Applied: {tags_created} created, {tags_promoted} promoted, "
              f"{relationships_added} relationships added.")
    else:
        print(f"\n  [DRY-RUN] Would create {tags_created} tags, promote {tags_promoted}, "
              f"add {relationships_added} relationships.")


# =============================================================================
# Phase 7: Assign Emojis to Curated Tags
# =============================================================================

EMOJI_PROMPT = """You are assigning a single emoji to each event tag for an NYC events map (fomo.nyc).

Each tag represents an event category, genre, or activity. Pick the BEST single emoji that
visually represents the tag. Rules:
- Use a SINGLE emoji character (no text, no sequences of multiple emoji)
- Pick the most specific and recognizable emoji for the concept
- Avoid reusing the same emoji for different tags when possible
- For music genres, use instrument emojis (🎷 jazz, 🎸 rock, 🎹 classical, etc.)
- For dance styles, use 💃 or related movement emojis
- For food/drink tags, use the most specific food emoji
- For abstract concepts, pick the closest visual metaphor

PARENT CONTEXT: These tags belong to the "{parent}" category.

TAGS TO ASSIGN EMOJIS:
{tags_text}

For each tag, respond with the tag name and its emoji.
"""


def _get_emoji_models():
    """Build Pydantic models for emoji assignment (requires BaseModel)."""
    if not BaseModel:
        return None

    class _EmojiAssignment(BaseModel):
        tag: str = Field(description="The tag name")
        emoji: str = Field(description="A single emoji character")

    class _EmojiBatch(BaseModel):
        assignments: list[_EmojiAssignment]

    return _EmojiBatch


# Hardcoded emojis for geographic and special tags
GEO_EMOJIS = {
    "Neighborhood": "📍",
    "Manhattan": "🏙️",
    "Brooklyn": "🌉",
    "Queens": "👑",
    "Bronx": "🐻",
    "Staten Island": "⛴️",
    "Long Island": "🏖️",
    "Westchester": "🌳",
    "Hudson Valley": "⛰️",
    "New Jersey": "🛣️",
    "Connecticut": "🏡",
}

# Default emoji for all neighborhoods
GEO_DEFAULT_EMOJI = "📍"


async def _assign_emojis_batch(tags_batch, parent_name):
    """Assign emojis to a batch of tags using Gemini."""
    EmojiBatch = _get_emoji_models()
    if not genai_client or not EmojiBatch:
        raise RuntimeError("Gemini client or pydantic not available")

    tags_text = "\n".join(f"- {t['name']}" for t in tags_batch)
    prompt = EMOJI_PROMPT.format(parent=parent_name, tags_text=tags_text)

    response = await asyncio.wait_for(
        genai_client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": EmojiBatch,
            },
        ),
        timeout=GEMINI_TIMEOUT,
    )

    result = EmojiBatch.model_validate_json(response.text)
    return {a.tag: a.emoji for a in result.assignments}


async def phase_emojis(cursor, conn, apply=False):
    """Phase 7: Assign emojis to all curated tags missing them."""
    print("\n" + "=" * 60)
    print("PHASE 7: Assign Emojis to Curated Tags")
    print("=" * 60)

    # Get all curated tags without emojis
    cursor.execute("""
        SELECT t.id, t.name,
               GROUP_CONCAT(DISTINCT p.name ORDER BY p.name SEPARATOR ', ') as parents
        FROM tags t
        LEFT JOIN tag_hierarchy th ON th.child_tag_id = t.id
        LEFT JOIN tags p ON th.parent_tag_id = p.id
        WHERE t.type = 'tag' AND (t.emoji IS NULL OR t.emoji = '')
        GROUP BY t.id
        ORDER BY t.name
    """)
    tags_needing_emoji = cursor.fetchall()
    print(f"  Tags needing emojis: {len(tags_needing_emoji)}")

    if not tags_needing_emoji:
        print("  All tags have emojis!")
        return

    # Build ancestor map to identify geographic tags
    ancestor_map, _ = build_tag_ancestor_map(cursor)
    neighborhood_id = find_tag_id(cursor, 'Neighborhood')

    geo_assigned = 0
    ai_tags = []

    # Separate geographic tags (assign programmatically) from others (use Gemini)
    for tag in tags_needing_emoji:
        tag_id = tag['id']
        name = tag['name']

        # Check if this tag is under the Neighborhood root
        ancestors = ancestor_map.get(tag_id, set())
        is_geo = neighborhood_id and neighborhood_id in ancestors

        if is_geo or name in GEO_EMOJIS:
            emoji = GEO_EMOJIS.get(name, GEO_DEFAULT_EMOJI)
            print(f"    GEO: {emoji} {name}")
            if apply:
                cursor.execute("UPDATE tags SET emoji = %s WHERE id = %s", (emoji, tag_id))
            geo_assigned += 1
        else:
            ai_tags.append(tag)

    print(f"\n  Geographic tags assigned: {geo_assigned}")
    print(f"  Tags for AI assignment: {len(ai_tags)}")

    if not ai_tags:
        if apply:
            conn.commit()
        return

    if not genai_client:
        print("  ERROR: Gemini client not available. Set GEMINI_API_KEY.")
        print("  Geographic emojis were assigned. Run again with Gemini for the rest.")
        if apply:
            conn.commit()
        return

    # Group by parent for better context in prompts
    by_parent = {}
    for tag in ai_tags:
        parent = tag['parents'] or 'General'
        # Use first parent for grouping
        first_parent = parent.split(',')[0].strip()
        by_parent.setdefault(first_parent, []).append(tag)

    ai_assigned = 0
    batch_size = 80

    for parent_name, parent_tags in sorted(by_parent.items()):
        # Process in batches
        for i in range(0, len(parent_tags), batch_size):
            batch = parent_tags[i:i+batch_size]
            print(f"\n  Batch: {parent_name} ({len(batch)} tags)...")

            try:
                emoji_map = await _assign_emojis_batch(batch, parent_name)

                for tag in batch:
                    name = tag['name']
                    emoji = emoji_map.get(name, '')
                    if emoji:
                        print(f"    {emoji} {name}")
                        if apply:
                            cursor.execute("UPDATE tags SET emoji = %s WHERE id = %s",
                                           (emoji, tag['id']))
                        ai_assigned += 1
                    else:
                        print(f"    ⚠️  {name} — no emoji returned")

            except Exception as e:
                print(f"    ERROR: {e}")

    if apply:
        conn.commit()
        print(f"\n  Applied: {geo_assigned} geographic + {ai_assigned} AI-assigned emojis.")
    else:
        print(f"\n  [DRY-RUN] Would assign {geo_assigned} geographic + {ai_assigned} AI emojis.")


# =============================================================================
# Phase 5: Cleanup — Demote vague tags, delete zero-event tags
# =============================================================================

# Tags to demote from type='tag' back to type='keyword'.
# Children are reparented to the demoted tag's parent(s) before removal.
DEMOTE_TO_KEYWORD = [
    # Vague/ambiguous — not useful as filters
    'Performance',          # 2,277 events — too vague (children: Cultural Performance, Student Performance)
    'Showcase',             # 393 events — too vague (child: Student Showcase)
    'New Work',             # 302 events — too vague
    'Experimental',         # 248 events — too vague (under Art, Film, Music, Theater)
    'Emerging Artists',     # 140 events — too vague
    'Creative Expression',  # 123 events — too vague
    'Interactive',          # 106 events — too vague
    # Delivery method — belongs in separate "Live Music" keyword, not event type hierarchy
    'Live Music',           # 809 events (children: Live Comedy, Live Concert, etc.)
    # Venue-specific — not event types
    'Broadway',             # 208 events — venue category, not event type
    'Off Broadway',         # 116 events — venue category
    'Community Board',      # 503 events — administrative, not event type
    # Low-event niche tags (< 5 events)
    'Ballroom',             # 4 events
    'Cycling',              # 4 events
    'Tennis',               # 3 events
    'Baseball',             # 3 events
    'Soccer',               # 3 events
]

# Zero-event tags to delete entirely (tag + hierarchy edges).
DELETE_TAGS = [
    'Free Admission',       # 0 events — redundant with "Free" root
    'Pay What You Wish',    # 0 events — redundant with "Free" root
    'Remote',               # 0 events — redundant with "Virtual" root
]


def phase_cleanup(cursor, conn, apply=False):
    """Phase 5: Demote vague tags to keywords, delete zero-event tags."""
    print("\n" + "=" * 60)
    print("PHASE 5: Cleanup — Demote Vague Tags, Delete Zero-Event Tags")
    print("=" * 60)

    demoted = 0
    deleted = 0
    reparented = 0

    # --- Demote tags ---
    print("\n  Demoting tags to keywords:")
    for tag_name in DEMOTE_TO_KEYWORD:
        tag_id = find_tag_id(cursor, tag_name)
        if not tag_id:
            print(f"    SKIP: '{tag_name}' not found")
            continue

        # Find this tag's parents (where to reparent children)
        cursor.execute("""
            SELECT p.id, p.name FROM tag_hierarchy th
            JOIN tags p ON th.parent_tag_id = p.id
            WHERE th.child_tag_id = %s
        """, (tag_id,))
        parents = cursor.fetchall()
        parent_names = [p['name'] for p in parents]

        # Find this tag's children (need reparenting)
        cursor.execute("""
            SELECT c.id, c.name FROM tag_hierarchy th
            JOIN tags c ON th.child_tag_id = c.id
            WHERE th.parent_tag_id = %s
        """, (tag_id,))
        children = cursor.fetchall()

        child_info = f" → reparent {len(children)} children to {parent_names}" if children else ""
        print(f"    DEMOTE: '{tag_name}' (parents={parent_names}){child_info}")

        if children:
            for child in children:
                for parent in parents:
                    print(f"      Reparent: '{child['name']}' → '{parent['name']}'")
                    if apply:
                        cursor.execute(
                            "INSERT IGNORE INTO tag_hierarchy (parent_tag_id, child_tag_id) VALUES (%s, %s)",
                            (parent['id'], child['id']))
                    reparented += 1

        if apply:
            # Remove all hierarchy edges involving this tag
            cursor.execute(
                "DELETE FROM tag_hierarchy WHERE parent_tag_id = %s OR child_tag_id = %s",
                (tag_id, tag_id))
            # Change type to keyword
            cursor.execute("UPDATE tags SET type = 'keyword' WHERE id = %s", (tag_id,))

        demoted += 1

    # --- Delete zero-event tags ---
    print("\n  Deleting zero-event tags:")
    for tag_name in DELETE_TAGS:
        tag_id = find_tag_id(cursor, tag_name)
        if not tag_id:
            print(f"    SKIP: '{tag_name}' not found")
            continue

        # Verify zero events
        cursor.execute("SELECT COUNT(*) as cnt FROM event_tags WHERE tag_id = %s", (tag_id,))
        row = cursor.fetchone()
        event_count = row['cnt'] if isinstance(row, dict) else row[0]

        if event_count > 0:
            print(f"    SKIP: '{tag_name}' has {event_count} events — not deleting")
            continue

        print(f"    DELETE: '{tag_name}' (0 events)")
        if apply:
            cursor.execute(
                "DELETE FROM tag_hierarchy WHERE parent_tag_id = %s OR child_tag_id = %s",
                (tag_id, tag_id))
            cursor.execute("DELETE FROM location_tags WHERE tag_id = %s", (tag_id,))
            cursor.execute("DELETE FROM tags WHERE id = %s", (tag_id,))
        deleted += 1

    if apply:
        print("\n  Checking for cycles...")
        if _detect_cycles(cursor):
            print("  CYCLE DETECTED! Rolling back.")
            conn.rollback()
            return
        print("  No cycles detected.")
        conn.commit()
        print(f"\n  Applied: {demoted} demoted, {deleted} deleted, {reparented} children reparented.")
    else:
        print(f"\n  [DRY-RUN] Would demote {demoted} tags, delete {deleted} tags, "
              f"reparent {reparented} children.")


# =============================================================================
# Verification
# =============================================================================

def verify(cursor):
    """Run post-apply verification checks."""
    print("\n" + "=" * 60)
    print("VERIFICATION")
    print("=" * 60)

    issues = 0

    # 1. Orphan tags (type='tag' with no parent, excluding roots)
    print("\n  1. Checking for orphan tags...")
    cursor.execute("""
        SELECT t.name FROM tags t
        WHERE t.type = 'tag'
          AND NOT EXISTS (
              SELECT 1 FROM tag_hierarchy th WHERE th.child_tag_id = t.id
          )
        ORDER BY t.name
    """)
    rows = cursor.fetchall()
    orphans = [(row['name'] if isinstance(row, dict) else row[0]) for row in rows]

    # Root tags are expected to have no parent
    root_tags = {
        'Music', 'Nightlife', 'Comedy', 'Art', 'Theater', 'Dance', 'Film',
        'Literature', 'Community', 'Family', 'Wellness', 'Education',
        'Outdoor', 'Sports', 'Games', 'Free', 'Virtual', 'Other',
        'Neighborhood',
    }
    unexpected_orphans = [o for o in orphans if o not in root_tags]
    if unexpected_orphans:
        print(f"    WARNING: {len(unexpected_orphans)} orphan tags found:")
        for name in unexpected_orphans[:20]:
            print(f"      - {name}")
        if len(unexpected_orphans) > 20:
            print(f"      ... and {len(unexpected_orphans) - 20} more")
        issues += 1
    else:
        print(f"    OK ({len(orphans)} root tags, no unexpected orphans)")

    # 2. Cycle detection
    print("\n  2. Checking for cycles...")
    if _detect_cycles(cursor):
        print("    FAIL: Cycle detected in hierarchy!")
        issues += 1
    else:
        print("    OK (no cycles)")

    # 3. Max depth check
    print("\n  3. Checking hierarchy depth...")
    cursor.execute("""
        SELECT p.name AS parent_name, c.name AS child_name
        FROM tag_hierarchy th
        JOIN tags p ON th.parent_tag_id = p.id
        JOIN tags c ON th.child_tag_id = c.id
    """)
    rows = cursor.fetchall()
    children_of = {}
    for row in rows:
        parent = row['parent_name'] if isinstance(row, dict) else row[0]
        child = row['child_name'] if isinstance(row, dict) else row[1]
        children_of.setdefault(parent, []).append(child)

    def max_depth(node, visited=None):
        if visited is None:
            visited = set()
        if node in visited:
            return 0
        visited.add(node)
        kids = children_of.get(node, [])
        if not kids:
            return 1
        return 1 + max(max_depth(k, visited.copy()) for k in kids)

    # Find roots
    all_children_set = set()
    for kids in children_of.values():
        all_children_set.update(kids)
    roots = [k for k in children_of if k not in all_children_set]

    max_d = 0
    deepest = None
    for root in roots:
        d = max_depth(root)
        if d > max_d:
            max_d = d
            deepest = root

    if max_d > 4:
        print(f"    WARNING: Max depth is {max_d} (starting from '{deepest}')")
        issues += 1
    else:
        print(f"    OK (max depth: {max_d}, root: '{deepest}')")

    # 4. "Other" event count
    print("\n  4. Checking 'Other' event count...")
    cursor.execute("""
        SELECT COUNT(DISTINCT et.event_id) as cnt
        FROM event_tags et
        JOIN tags t ON et.tag_id = t.id
        JOIN events e ON et.event_id = e.id
        WHERE t.name = 'Other' AND e.archived = FALSE AND e.suppressed = FALSE
    """)
    row = cursor.fetchone()
    other_count = row['cnt'] if isinstance(row, dict) else row[0]
    print(f"    Events tagged 'Other': {other_count}")

    # 5. Duplicate detection
    print("\n  5. Checking for duplicate tags (same normalized name)...")
    cursor.execute("""
        SELECT LOWER(REPLACE(name, ' ', '')) as normalized,
               GROUP_CONCAT(name SEPARATOR ', ') as variants,
               COUNT(*) as cnt
        FROM tags
        GROUP BY normalized
        HAVING cnt > 1
        ORDER BY cnt DESC
        LIMIT 20
    """)
    rows = cursor.fetchall()
    if rows:
        dupes = [(
            row['normalized'] if isinstance(row, dict) else row[0],
            row['variants'] if isinstance(row, dict) else row[1],
        ) for row in rows]
        print(f"    WARNING: {len(dupes)} duplicate groups found:")
        for norm, variants in dupes:
            print(f"      {variants}")
        issues += 1
    else:
        print("    OK (no duplicates)")

    # 6. Hierarchy stats
    print("\n  6. Hierarchy stats:")
    cursor.execute("SELECT COUNT(*) as cnt FROM tags WHERE type = 'tag'")
    row = cursor.fetchone()
    tag_count = row['cnt'] if isinstance(row, dict) else row[0]
    cursor.execute("SELECT COUNT(*) as cnt FROM tags WHERE type = 'keyword'")
    row = cursor.fetchone()
    keyword_count = row['cnt'] if isinstance(row, dict) else row[0]
    cursor.execute("SELECT COUNT(*) as cnt FROM tag_hierarchy")
    row = cursor.fetchone()
    rel_count = row['cnt'] if isinstance(row, dict) else row[0]
    print(f"    Curated tags: {tag_count}")
    print(f"    Keywords: {keyword_count}")
    print(f"    Hierarchy relationships: {rel_count}")

    print(f"\n{'=' * 60}")
    if issues:
        print(f"  {issues} issue(s) found.")
    else:
        print("  All checks passed.")


# =============================================================================
# Phase 8: Review & Fix Ambiguous Parent Assignments
# =============================================================================

# Tags that need additional parents added (tag_name -> [parents to ADD])
ADD_PARENTS = {
    "Open Mic":         ["Music", "Comedy"],
    "Competition":      ["Games", "Community"],
    "Tournament":       ["Games"],
    "Avant Garde":      ["Music", "Theater", "Film"],
    "Storytelling":     ["Theater", "Community"],
    "Opera":            ["Music"],
    "Cabaret":          ["Music", "Nightlife"],
    "Burlesque":        ["Theater", "Dance"],
    "Drag Show":        ["Theater", "Comedy"],
    "DJ":               ["Nightlife"],
    "Variety Show":     ["Theater", "Nightlife"],
    "Game Show":        ["Comedy", "Nightlife"],
    "Bingo":            ["Nightlife"],
    "Roller Skating":   ["Nightlife"],
    "Puppetry":         ["Family"],
    "Sing Along":       ["Family"],
    "Scavenger Hunt":   ["Outdoor", "Family"],
    "Magic":            ["Family"],
    "Magic Show":       ["Family"],
    "Walking Tour":     ["Education"],
    "Museum":           ["Art"],
    "Science":          ["Education"],
    "Spoken Word":      ["Theater"],
    "Performance Art":  ["Art"],
    "Sound Art":        ["Art"],
    "Karaoke":          ["Music"],
    "Improv":           ["Theater"],
    "Biography":        ["Literature"],
    "Fantasy":          ["Literature"],
    "Sci-fi":           ["Literature"],
    "Horror":           ["Literature"],
    "Mystery":          ["Literature"],
    "Architecture":     ["Education"],
    "Fashion":          ["Community"],
}

# Tags with wrong parents: (tag_name, parents_to_remove, parents_to_add)
FIX_PARENTS = [
    ("Live Comedy",   ["Music"],      []),                        # remove Music, keep Comedy
    ("Romance",       ["Nightlife"],   ["Film", "Literature"]),   # nightlife -> film/lit genre
    ("Worship",       ["Wellness"],    ["Spirituality"]),         # wellness -> spirituality
    ("Faith",         ["Wellness"],    ["Spirituality"]),         # wellness -> spirituality
    ("Sound Design",  ["Art"],         ["Music"]),                # art -> music
    ("Celebration",   [],              ["Community"]),            # add Community, keep Nightlife
    ("Dining",        ["Nightlife"],   ["Community"]),            # nightlife -> community
]

# Tags to demote from curated tag to keyword (too niche for filtering)
DEMOTE_TO_KEYWORD_2 = [
    "Handmade Pasta", "Pasta Making", "Culinary Skills",
    "Jazz Bass", "Jazz Drums", "Trumpet Jazz",
    "College Swimming", "College Volleyball",
    "Acoustic Rock", "Soulful House", "Art Pop",
    "Landscape Painting", "Portraiture",
]


def phase_review(cursor, conn, apply=False):
    """Phase 8: Fix ambiguous parent assignments, wrong parents, and demote niche tags."""
    print("\n" + "=" * 60)
    print("PHASE 8: Review & Fix Ambiguous Parent Assignments")
    print("=" * 60)

    added = 0
    fixed = 0
    demoted = 0

    # --- Step 1: Add missing parents ---
    print("\n  Step 1: Add missing parents")
    for tag_name, new_parents in ADD_PARENTS.items():
        tag_id = find_tag_id(cursor, tag_name)
        if not tag_id:
            print(f"    SKIP: '{tag_name}' not found")
            continue

        for parent_name in new_parents:
            parent_id = find_tag_id(cursor, parent_name)
            if not parent_id:
                print(f"    SKIP: parent '{parent_name}' not found")
                continue

            # Check if relationship already exists
            cursor.execute(
                "SELECT 1 FROM tag_hierarchy WHERE parent_tag_id = %s AND child_tag_id = %s",
                (parent_id, tag_id))
            if cursor.fetchone():
                continue  # already exists

            print(f"    ADD: {tag_name} → parent: {parent_name}")
            added += 1
            if apply:
                cursor.execute(
                    "INSERT IGNORE INTO tag_hierarchy (parent_tag_id, child_tag_id) VALUES (%s, %s)",
                    (parent_id, tag_id))

    # --- Step 2: Fix wrong parents ---
    print(f"\n  Step 2: Fix wrong parents")
    for tag_name, remove_parents, add_parents in FIX_PARENTS:
        tag_id = find_tag_id(cursor, tag_name)
        if not tag_id:
            print(f"    SKIP: '{tag_name}' not found")
            continue

        for parent_name in remove_parents:
            parent_id = find_tag_id(cursor, parent_name)
            if not parent_id:
                continue
            cursor.execute(
                "SELECT 1 FROM tag_hierarchy WHERE parent_tag_id = %s AND child_tag_id = %s",
                (parent_id, tag_id))
            if not cursor.fetchone():
                continue
            print(f"    REMOVE: {tag_name} -/-> {parent_name}")
            fixed += 1
            if apply:
                cursor.execute(
                    "DELETE FROM tag_hierarchy WHERE parent_tag_id = %s AND child_tag_id = %s",
                    (parent_id, tag_id))

        for parent_name in add_parents:
            parent_id = find_tag_id(cursor, parent_name)
            if not parent_id:
                print(f"    SKIP: parent '{parent_name}' not found")
                continue
            cursor.execute(
                "SELECT 1 FROM tag_hierarchy WHERE parent_tag_id = %s AND child_tag_id = %s",
                (parent_id, tag_id))
            if cursor.fetchone():
                continue
            print(f"    ADD: {tag_name} → parent: {parent_name}")
            fixed += 1
            if apply:
                cursor.execute(
                    "INSERT IGNORE INTO tag_hierarchy (parent_tag_id, child_tag_id) VALUES (%s, %s)",
                    (parent_id, tag_id))

    # --- Step 3: Demote niche tags ---
    print(f"\n  Step 3: Demote niche tags to keywords")
    for tag_name in DEMOTE_TO_KEYWORD_2:
        tag_id = find_tag_id(cursor, tag_name)
        if not tag_id:
            print(f"    SKIP: '{tag_name}' not found")
            continue

        # Check current type
        cursor.execute("SELECT type FROM tags WHERE id = %s", (tag_id,))
        row = cursor.fetchone()
        current_type = row['type'] if isinstance(row, dict) else row[0]
        if current_type == 'keyword':
            continue

        # Count events
        cursor.execute("SELECT COUNT(*) as cnt FROM event_tags WHERE tag_id = %s", (tag_id,))
        row = cursor.fetchone()
        event_count = row['cnt'] if isinstance(row, dict) else row[0]

        # Check for children
        cursor.execute("SELECT COUNT(*) as cnt FROM tag_hierarchy WHERE parent_tag_id = %s", (tag_id,))
        row = cursor.fetchone()
        child_count = row['cnt'] if isinstance(row, dict) else row[0]

        if child_count > 0:
            print(f"    SKIP: '{tag_name}' has {child_count} children — reparent first")
            continue

        print(f"    DEMOTE: '{tag_name}' ({event_count} events) tag → keyword")
        demoted += 1
        if apply:
            cursor.execute("UPDATE tags SET type = 'keyword' WHERE id = %s", (tag_id,))
            # Remove from hierarchy
            cursor.execute(
                "DELETE FROM tag_hierarchy WHERE child_tag_id = %s OR parent_tag_id = %s",
                (tag_id, tag_id))

    # --- Cycle check ---
    if apply:
        print("\n  Checking for cycles...")
        if _detect_cycles(cursor):
            print("    CYCLE DETECTED — rolling back!")
            conn.rollback()
            return
        print("    OK (no cycles)")
        conn.commit()

    print(f"\n  Summary: {added} parents added, {fixed} parents fixed, {demoted} tags demoted")
    if not apply:
        print("  (dry-run — no changes applied)")


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Populate tag hierarchy with intermediate levels and AI-classified keywords',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--apply', action='store_true',
                        help='Apply changes (default: dry-run)')
    parser.add_argument('--phase', choices=[
                            'orphans', 'intermediate', 'classify', 'apply-review',
                            'cleanup', 'geographic', 'emojis', 'review'],
                        help='Run only a specific phase (default: phases 1-2)')
    parser.add_argument('--verify', action='store_true',
                        help='Run verification checks only')
    parser.add_argument('--review-file', type=str,
                        help='Path to review CSV for apply-review phase')
    parser.add_argument('--min-events', type=int, default=20,
                        help='Minimum event count for keyword classification (default: 20)')
    parser.add_argument('--batch-size', type=int, default=50,
                        help='Keywords per Gemini API call (default: 50)')
    args = parser.parse_args()

    conn = create_connection()
    if not conn:
        print("Failed to connect to database")
        sys.exit(1)

    cursor = conn.cursor(dictionary=True)

    try:
        if args.verify:
            verify(cursor)
            return

        if args.phase == 'classify':
            asyncio.run(phase_classify(cursor, args.min_events, args.batch_size))
            return

        if args.phase == 'apply-review':
            review_file = args.review_file
            if not review_file:
                # Find the most recent review file
                review_files = sorted(
                    [f for f in os.listdir(SCRIPT_DIR) if f.startswith('tag_classification_review_')],
                    reverse=True)
                if review_files:
                    review_file = os.path.join(SCRIPT_DIR, review_files[0])
                    print(f"Using most recent review file: {review_file}")
                else:
                    print("ERROR: No review file found. Run --phase classify first.")
                    sys.exit(1)
            phase_apply_review(cursor, conn, review_file, apply=args.apply)
            return

        if args.phase == 'cleanup':
            phase_cleanup(cursor, conn, apply=args.apply)
            return

        if args.phase == 'geographic':
            phase_geographic(cursor, conn, apply=args.apply)
            return

        if args.phase == 'emojis':
            asyncio.run(phase_emojis(cursor, conn, apply=args.apply))
            return

        if args.phase == 'review':
            phase_review(cursor, conn, apply=args.apply)
            return

        # Default: run phases 1-2
        if args.phase is None or args.phase == 'orphans':
            phase_orphans(cursor, conn, apply=args.apply)

        if args.phase is None or args.phase == 'intermediate':
            phase_intermediate(cursor, conn, apply=args.apply)

        if not args.apply:
            print(f"\n{'=' * 60}")
            print("Run with --apply to apply changes.")

    finally:
        cursor.close()
        conn.close()


if __name__ == '__main__':
    main()
