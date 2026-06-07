# Discover Venues Command

Discover and add new locations and websites to the fomo.nyc database through a systematic research, verification, and addition workflow.

## Overview

This command handles the full workflow for expanding the database:
- **Research** - Find candidate venues based on user input or open-ended search
- **Verify** - Check venues exist, geocode addresses, validate websites
- **Deduplicate** - Check against existing database entries
- **Add** - Insert verified venues using the standard PHP scripts
- **Test** - Verify crawls work for websites with event pages

## Instructions

### Phase 1: Research & Discovery

Based on the user's request, research candidate venues. The user may provide:
- Specific venue names to add
- A category to explore (e.g., "jazz clubs", "escape rooms", "cat cafes")
- An open-ended request (e.g., "find more entertainment venues")
- A newsletter or blog post to scan for venues (e.g., Nonsense NYC, The Blankman List)

**For open-ended requests**, search for venues in categories like:
- Music venues (jazz, rock, classical, electronic)
- Performance venues (comedy, theatre, cabaret, burlesque)
- Entertainment (bowling, mini golf, arcades, escape rooms, axe throwing)
- Experiential (immersive experiences, VR, museums, tours)
- Food & drink with events (breweries, wine bars, speakeasies)
- Activity venues (climbing, skating, pottery, crafts, dance studios)
- Community spaces (cultural centers, makerspaces, bookstores)

Use web search to find venues, focusing on NYC metro area.

### Phase 2: Duplicate Checking

Before adding any venue, thoroughly check if it already exists in the database.

**When processing many venues at once** (e.g., from a newsletter), batch all checks into a single query with multiple OR conditions for efficiency:

```bash
# Batch check all venue names at once
mysql -u root fomo -e "SELECT id, name, address FROM locations WHERE
  name LIKE '%Venue A%' OR
  name LIKE '%Venue B%' OR
  name LIKE '%Venue C%'
ORDER BY name"
```

#### Location Duplicate Checks (by name)

```bash
# 1. Check by name (use LIKE for partial matches)
mysql -u root fomo -e "SELECT id, name, address FROM locations WHERE name LIKE '%venue name%'"

# 2. Check alternate names
mysql -u root fomo -e "
  SELECT l.id, l.name, lan.alternate_name, l.address
  FROM locations l
  JOIN location_alternate_names lan ON l.id = lan.location_id
  WHERE lan.alternate_name LIKE '%venue name%'"
```

#### Website Duplicate Checks

```bash
# 1. Check by name
mysql -u root fomo -e "SELECT id, name, base_url FROM websites WHERE name LIKE '%venue name%'"

# 2. Check by base_url domain
mysql -u root fomo -e "SELECT id, name, base_url FROM websites WHERE base_url LIKE '%example.com%'"

# 3. Check by crawl URLs
mysql -u root fomo -e "
  SELECT w.id, w.name, wu.url
  FROM websites w
  JOIN website_urls wu ON w.id = wu.website_id
  WHERE wu.url LIKE '%example.com%'"
```

**Skip any venue that already exists.** If a location exists but lacks a website (or vice versa), only add the missing component.

### Phase 3: Geocoding & Verification

For each candidate venue, use the geocode script to verify it exists and get coordinates:

```bash
# Geocode by venue name (automatically biased toward NYC)
php scripts/geocode.php --json "Venue Name"

# If venue name doesn't resolve, fall back to address
php scripts/geocode.php --json "267 Douglass Street Brooklyn"
```

**Output example:**
```json
{"name":"Marshall Chess Club","address":"23 W 10th St, New York, NY 10011, USA","lat":40.7341,"lng":-73.9967}
```

**Verification criteria:**
1. **Geocode succeeds** - If the venue name returns just a neighborhood/city, try the street address instead. If neither works, the venue may not exist or may have closed
2. **Address is in NYC metro area** - Verify the address is in NYC, NJ (close to NYC), or nearby suburbs
3. **Website loads** - Use WebFetch to verify the website is accessible (not 404, not redirecting to spam)
4. **Website matches venue** - Confirm the website is actually for this venue

**Reject venues that:**
- Don't geocode successfully by name
- Are outside the NYC metro area
- Have websites that don't load or redirect to unrelated sites
- Have closed or no longer exist

### Phase 4: Address & Proximity Duplicate Check

After geocoding, check for duplicates by address and coordinates:

```bash
# 1. Check by similar address (use street number and name from geocode output)
mysql -u root fomo -e "SELECT id, name, address FROM locations WHERE address LIKE '%23 W 10th St%'"

# 2. Check by proximity (within ~100 meters of geocoded coordinates)
# Replace LAT and LNG with values from geocode.php output
mysql -u root fomo -e "
  SELECT id, name, address,
    ROUND(ST_Distance_Sphere(POINT(lng, lat), POINT(-73.9967, 40.7341))) as distance_meters
  FROM locations
  WHERE lat BETWEEN 40.7341 - 0.001 AND 40.7341 + 0.001
    AND lng BETWEEN -73.9967 - 0.001 AND -73.9967 + 0.001
  ORDER BY distance_meters"
```

**If a nearby location is found:**
- If it's the same venue under a different name, skip adding (it's a duplicate)
- If it's a different venue at the same address (e.g., venue inside a hotel), consider whether both should exist

### Phase 5: Adding Locations

Edit `scripts/add_locations.php` with verified locations:

```php
$new_locations = [
    [
        'name' => 'Venue Name',
        'short_name' => 'Short Name',  // optional
        'description' => 'Brief description (1-2 sentences) of venue and what it offers.',
        'address' => '123 Main St, New York, NY 10001, USA',  // from geocode
        'lat' => 40.7128,   // from geocode
        'lng' => -74.0060,  // from geocode
        'emoji' => '🎭',
        'tags' => ['Manhattan', 'Greenwich Village', 'Music'],
    ],
];
```

**Required fields:**
- `name` - Full venue name
- `address` - Full address from geocode.php output
- `lat`, `lng` - Coordinates from geocode.php output
- `emoji` - Single emoji representing venue type (see Emoji Guide below)
- `description` - 1-2 sentences about what the venue is and what events it hosts
- `tags` - Borough, neighborhood, venue type

Run the script:
```bash
php scripts/add_locations.php --dry-run  # Preview first
php scripts/add_locations.php            # Add to local database
```

**Alternate names:** If a venue is commonly known by multiple names (e.g., "Gemini & Scorpio Loft" is also called "House of Scorpio"), add alternate names after creating the location:

```bash
mysql -u root fomo -e "INSERT INTO location_alternate_names (location_id, alternate_name) VALUES (<location_id>, 'Alternate Name')"
```

### Phase 6: Adding Websites

Edit `scripts/add_websites.php` with verified websites:

```php
$new_websites = [
    [
        'name' => 'Venue Name',
        'description' => 'Brief description of the organization/website.',
        'base_url' => 'https://example.com/',
        'location' => 'Venue Name',  // Links to the location added above
        // Only include these if the site has a crawlable events page:
        'urls' => ['https://example.com/events'],  // Crawl URLs
        'crawl_frequency' => 7,  // Days between crawls
    ],
];
```

**For venues WITHOUT crawlable event pages:**
- Include only `name`, `description`, `base_url`, and `location`
- Do NOT include `urls` or `crawl_frequency`
- These websites serve as informational links for users viewing the location

**For venues WITH crawlable event pages:**
- Include `urls` array with specific event page URLs
- Set `crawl_frequency` (typically 7 for weekly)
- Optionally set `crawl_after` for seasonal venues

**Multiple websites per location:** Different organizations can share the same venue. Add separate website entries each linked to the same location (e.g., a venue website and a separate events-programming brand that hosts events there).

Run the script:
```bash
php scripts/add_websites.php --dry-run  # Preview first
php scripts/add_websites.php            # Add to local database
```

### Phase 7: Adding Instagram Accounts (Optional)

If a venue has an Instagram account, add it to the database for social media tracking.

#### Check for Existing Instagram Account

```bash
# Check if account already exists
mysql -u root fomo -e "SELECT id, handle, name FROM instagram_accounts WHERE handle = 'venuehandle'"
```

#### Add the Instagram Account

```bash
# Add the account (handle without @ symbol)
mysql -u root fomo -e "INSERT INTO instagram_accounts (handle, name) VALUES ('venuehandle', 'Venue Name')"

# Get the new account ID
mysql -u root fomo -e "SELECT id FROM instagram_accounts WHERE handle = 'venuehandle'"
```

#### Link to Location

```bash
# Link Instagram account to location
mysql -u root fomo -e "INSERT INTO location_instagram (location_id, instagram_id) VALUES (<location_id>, <instagram_id>)"
```

#### Batch Insert Example

For multiple accounts at once:

```sql
INSERT INTO instagram_accounts (handle, name) VALUES
('venue1handle', 'Venue 1 Name'),
('venue2handle', 'Venue 2 Name');

INSERT INTO location_instagram (location_id, instagram_id) VALUES
(<location_id_1>, (SELECT id FROM instagram_accounts WHERE handle = 'venue1handle')),
(<location_id_2>, (SELECT id FROM instagram_accounts WHERE handle = 'venue2handle'));
```

**Notes:**
- Instagram handles should NOT include the `@` symbol
- Only add Instagram accounts for venues where you've verified the handle is correct
- Look for Instagram links on venue websites or search Instagram directly

### Phase 8: Testing Crawls

For websites with crawl URLs, test that they work:

```bash
# Get the website IDs that were just added
mysql -u root fomo -e "SELECT id, name FROM websites ORDER BY id DESC LIMIT 10"

# Run the pipeline for specific website IDs
source venv/bin/activate
python pipeline/main.py --ids 1234,1235,1236
```

**Verify:**
- Crawl completes without errors
- Events are extracted (check "Events extracted" count)
- Events are processed and merged

If a crawl fails:
- Check if the URL is correct
- Try a different events page URL
- If no crawlable page exists, remove the crawl URL (keep website as informational only)

If a crawl extracts too many events (e.g., pages with years of historical events):
- **Best fix: Add per-URL `js_code`** to trim old content from the DOM before scraping:
  ```bash
  mysql -u root fomo -e "UPDATE website_urls SET js_code = '<javascript to trim old content>' WHERE website_id = <id>"
  ```
  Example: For a Squarespace page with year headers, remove all `<p>` elements after the second year header to keep only the current year's events.
- **Fallback: Set `max_batches`** on the website to limit AI enrichment cost:
  ```bash
  mysql -u root fomo -e "UPDATE websites SET max_batches = 5 WHERE id = <id>"
  ```
  The pipeline defaults to 3 enrichment batches (90 events max). Set higher for sites that legitimately have many upcoming events.
- After changing `js_code`, clear crawl results and re-crawl:
  ```bash
  mysql -u root fomo -e "DELETE FROM crawl_results WHERE website_id = <id>"
  ```

### Phase 9: Cleanup

After successfully adding venues, reset the PHP arrays to empty — do **not** leave dated comments or "see git history" trail markers behind (the git log is the record). This matches the cleanup convention in `/add-locations` and `/add-websites`:

```php
// In add_locations.php
$new_locations = [
];

// In add_websites.php
$new_websites = [
];
```

## Example Workflow

**User:** "Find some pottery studios to add"

**Step 1: Research**
```
Web search for "pottery studios NYC events classes 2026"
Found candidates: Gasworks NYC, Bushwick Ceramics, Maison Clay
```

**Step 2: Check for duplicates**
```bash
# Check location names and alternate names
mysql -u root fomo -e "SELECT id, name, address FROM locations WHERE name LIKE '%Gasworks%'"
mysql -u root fomo -e "SELECT l.id, l.name, lan.alternate_name FROM locations l JOIN location_alternate_names lan ON l.id = lan.location_id WHERE lan.alternate_name LIKE '%Gasworks%'"

# Check website names and URLs
mysql -u root fomo -e "SELECT id, name, base_url FROM websites WHERE name LIKE '%Gasworks%' OR base_url LIKE '%gasworks%'"
```

**Step 3: Geocode and verify**
```bash
php scripts/geocode.php --json "Gasworks NYC"
# Verify output shows NYC address
# WebFetch the website to confirm it loads
```

**Step 4: Add locations** (edit add_locations.php)
```php
$new_locations = [
    [
        'name' => 'Gasworks NYC',
        'description' => 'Pottery studio in Bushwick offering wheel throwing and hand-building classes.',
        'address' => '123 Troutman St, Brooklyn, NY 11237, USA',
        'lat' => 40.7068,
        'lng' => -73.9212,
        'emoji' => '🎨',
        'tags' => ['Brooklyn', 'Bushwick', 'Art', 'Pottery'],
    ],
];
```

**Step 5: Add websites** (edit add_websites.php)
```php
$new_websites = [
    [
        'name' => 'Gasworks NYC',
        'description' => 'Pottery studio offering classes and studio memberships',
        'base_url' => 'https://gasworksnyc.com/',
        'location' => 'Gasworks NYC',
        // If they have a classes page:
        'urls' => ['https://gasworksnyc.com/classes'],
        'crawl_frequency' => 7,
    ],
];
```

**Step 6: Run scripts**
```bash
php scripts/add_locations.php --dry-run
php scripts/add_locations.php
php scripts/add_websites.php --dry-run
php scripts/add_websites.php
```

**Step 7: Test crawl**
```bash
source venv/bin/activate
python pipeline/main.py --ids <new_website_id>
```

## Key Principles

1. **Verify before adding** - Every venue must geocode successfully and have a working website
2. **Use geocode coordinates** - Always use lat/lng from geocode.php, not manually entered
3. **Check for duplicates first** - Never add a venue that already exists. Batch checks for efficiency when processing many venues
4. **Websites are optional for locations** - But locations are required for websites
5. **Crawl URLs are optional for websites** - Informational websites (no events page) are still valuable
6. **Test crawls** - Always verify new crawlable websites work before considering the task complete
7. **Watch for large pages** - Sites with historical event archives need `js_code` trimming or `max_batches` limits to avoid wasting API calls
