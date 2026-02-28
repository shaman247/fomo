# Write Description Command

Rewrite a location's description to match quality guidelines.

## Input

The user will provide a location ID (or multiple IDs). Example: `251` or `251, 410, 500`

## Instructions

For each location ID provided:

### Step 1: Fetch Location Data

Run this query to get location info and associated tags:

```bash
/Applications/XAMPP/xamppfiles/bin/php -r "
\$pdo = new PDO('mysql:host=localhost;dbname=fomo;charset=utf8mb4', 'root', '', [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]);

\$id = <LOCATION_ID>;

// Get location with location tags
\$stmt = \$pdo->prepare('
    SELECT l.id, l.name, l.address, l.description, l.emoji,
           GROUP_CONCAT(DISTINCT t.name ORDER BY t.name SEPARATOR \", \") as location_tags
    FROM locations l
    LEFT JOIN location_tags lt ON l.id = lt.location_id
    LEFT JOIN tags t ON lt.tag_id = t.id
    WHERE l.id = ?
    GROUP BY l.id
');
\$stmt->execute([\$id]);
\$location = \$stmt->fetch(PDO::FETCH_ASSOC);
echo \"=== Location ===\n\";
echo \"ID: {\$location['id']}\n\";
echo \"Name: {\$location['name']}\n\";
echo \"Address: {\$location['address']}\n\";
echo \"Emoji: {\$location['emoji']}\n\";
echo \"Current description: {\$location['description']}\n\";
echo \"Location tags: {\$location['location_tags']}\n\";

// Get event tags for this location
echo \"\n=== Event Tags ===\n\";
\$stmt = \$pdo->prepare('
    SELECT t.name, COUNT(*) as count
    FROM events e
    JOIN event_tags et ON e.id = et.event_id
    JOIN tags t ON et.tag_id = t.id
    WHERE e.location_id = ?
    GROUP BY t.id
    ORDER BY count DESC
    LIMIT 15
');
\$stmt->execute([\$id]);
foreach (\$stmt as \$row) {
    echo \"- {\$row['name']} ({\$row['count']})\n\";
}
"
```

### Step 2: Research the Venue

Use WebSearch to find accurate information about the venue:

```
Search: "[Venue Name]" [neighborhood] NYC
```

Look for:
- What type of venue it actually is (bar, club, gallery, theater, etc.)
- What kinds of events/programming it hosts
- Any unique features or history worth mentioning
- Official website or social media descriptions

### Step 3: Write New Description

Based on the research and tags, write a new description following these guidelines:

**Requirements:**
- 1-2 sentences maximum
- Explain what the venue IS (not just what it hosts)
- Be specific about event types/programming
- Avoid generic terms like "event space", "creative gatherings", "cultural events", "various events"
- Help users understand what to expect

**Good examples:**
- "Brooklyn-based community hub for experimental games, indie developers, and creative culture, hosting game showcases, film screenings, music performances, workshops, and LARPs."
- "World-renowned performing arts conservatory hosting over 700 annual public performances in music, dance, and drama at venues including Morse Hall, with most events free or under $50."
- "Historic Renaissance Revival building serving as a premier cultural center for Czech and Slovak communities, hosting festivals, concerts, art exhibitions, lectures, films, and dance events."
- "Acclaimed Bushwick dance club and cocktail bar with a tropical-goth aesthetic, featuring international DJs spinning house, techno, and electronic music nightly."

**Bad examples to avoid:**
- "Williamsburg venue and event space hosting live music, performances, art events, and creative gatherings." (too generic, unclear what it actually is)
- "Large creative and manufacturing complex in Sunset Park" (not specific or audience-focused)
- "Art gallery and community space in South Slope" (too short, no specifics)

### Step 4: Present for Approval

Show the user:
1. Current description
2. Research findings (brief summary)
3. Proposed new description

Ask for confirmation before updating.

### Step 5: Update Database

After approval, update both local and production databases:

```bash
# Local
/Applications/XAMPP/xamppfiles/bin/php -r "
\$pdo = new PDO('mysql:host=localhost;dbname=fomo;charset=utf8mb4', 'root', '', [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]);
\$stmt = \$pdo->prepare('UPDATE locations SET description = ? WHERE id = ?');
\$stmt->execute(['<NEW_DESCRIPTION>', <LOCATION_ID>]);
echo 'Local updated: ' . \$stmt->rowCount() . ' row(s)';
"

# Production
/Applications/XAMPP/xamppfiles/bin/php -r "
\$pdo = new PDO('mysql:host=localhost;dbname=fomoowsq_fomo;charset=utf8mb4', 'fomoowsq_root', 'pvj4]rEnTj2P', [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]);
\$stmt = \$pdo->prepare('UPDATE locations SET description = ? WHERE id = ?');
\$stmt->execute(['<NEW_DESCRIPTION>', <LOCATION_ID>]);
echo 'Production updated: ' . \$stmt->rowCount() . ' row(s)';
"
```

### Step 6: Confirm and Continue

After updating, show confirmation and move to the next location ID if multiple were provided.

## Batch Mode

When processing multiple locations, work through them one at a time, getting approval for each before moving to the next. This ensures accuracy and allows the user to provide feedback that improves subsequent descriptions.
