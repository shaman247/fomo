# Add Websites Command

Add new websites to crawl for the fomo.nyc database.

## Instructions

You are helping the user add new websites to the crawl pipeline. Follow these steps:

### Step 1: Gather Website Information

Ask the user for the websites they want to add. For each website, you need:
- **name** (required): Website/venue name
- **base_url** (required): The venue's root domain URL (informational only, not directly crawled)
- **urls** (recommended): Array of specific pages to crawl (e.g., calendar/events pages)
- **location** (recommended): Name of an existing location to link to
- **description** (required): 1-2 sentence description of the organization and its programming
- **notes** (optional): Special event extraction instructions, which will be added to the Gemini prompt when extracting events from the page.

Optional fields (usually leave unset):
- **crawl_frequency**: Days between crawls (default: 7 days) - only set if you have a reason
- **selector**: CSS selector for event content
- **tags**: Array of tags to force on all events - usually unnecessary, events get tags automatically

If the user provides a venue name, check if a matching location exists in the database. If not, suggest using `/add-locations` first.

### Step 2: Navigate Websites to Find Crawl URLs

**IMPORTANT**: Before adding a website, you MUST visit and navigate it to find the correct events/calendar page. Use the WebFetch tool to:

1. **Visit the main site** - Fetch the homepage to understand the site structure
2. **Find the events page** - Look for navigation links like "Events", "Calendar", "Schedule", "What's On", "Shows", or "Tickets"
3. **Verify event content** - Fetch the events page to confirm it contains actual event listings with dates, times, and descriptions
4. **Check for external platforms** - Many venues use external ticketing/calendar systems:
   - Eventbrite (`eventbrite.com/o/...`)
   - Ovation Tix (`web.ovationtix.com/trs/cal/...`)
   - Dice (`dice.fm/...`)
   - See Tickets, etc.

**What to look for on the events page:**
- Event names/titles
- Dates and times
- Descriptions or details
- A calendar or list format

**Common patterns:**
| URL Pattern | Notes |
|-------------|-------|
| `/events`, `/calendar`, `/schedule` | Standard events pages |
| `/whats-on`, `/shows`, `/performances` | Theater/venue variants |
| `/buy-tickets`, `/tickets` | Ticketing pages with show listings |
| `/news` | Some theaters list shows here |
| External Eventbrite/Ovation Tix | Use the external URL as the crawl URL |

**If no events page exists**, note this and consider whether the site is worth adding (events may only be on social media).

### Description Guidelines

Write descriptions that are:
- **Concise**: 1-2 sentences maximum
- **Organization-focused**: Explain what the organization/venue is
- **Programming-focused**: Mention the types of events they host
- **Helpful**: Give users context about what to expect

Examples:
- "Cultural organization promoting Czech arts, innovations, and creativity through concerts, exhibitions, screenings, panel discussions, and performances at Bohemian National Hall."
- "World-renowned performing arts conservatory presenting student and faculty performances in music, dance, and drama."
- "Brooklyn music venue and bar hosting live punk, metal, and alternative music with burlesque performances."

### Step 3: Edit the Script

Once you have all the website details, edit the `$new_websites` array in `scripts/add_websites.php`:

```php
$new_websites = [
    [
        'name' => 'Venue Name',
        'description' => 'Brief description of organization and programming...',  // recommended
        'base_url' => 'https://example.com',           // Root domain (informational)
        'urls' => ['https://example.com/events'],      // Specific pages to crawl
        'location' => 'Exact Location Name',           // Must match existing location
        'notes' => 'Special instructions',             // Notes (optional)
    ],
    // ... more websites
];
```

### Step 4: Dry Run

First, run a dry run to preview what will be added:

```bash
php scripts/add_websites.php --dry-run
```

Show the user the output and confirm they want to proceed. Pay attention to any "Location NOT FOUND" warnings.

### Step 5: Add to Local Database

```bash
php scripts/add_websites.php
```

### Step 6: Test the Crawl

After adding websites, test that they can be crawled successfully:

```bash
# Activate the virtual environment
source venv/bin/activate

# Run a test crawl on specific websites (by ID)
python pipeline/main.py --website-ids 123,124,125

# Check the results
mysql -u root fomo -e "SELECT w.name, cr.status, LENGTH(cr.crawled_content) as content_size
FROM crawl_results cr
JOIN websites w ON cr.website_id = w.id
WHERE w.id IN (123,124,125)
ORDER BY cr.created_at DESC;"
```

Verify that:
- Crawl status is 'success' or 'extracted'
- Content was retrieved (content_size > 0)
- Events were extracted (check `crawl_events` table)

### Step 7: Clean Up (REQUIRED)

After successfully adding websites, reset the `$new_websites` array back to empty. Do NOT leave previous entries, dated comments, or "see git history" trail markers behind — git is the source of truth for what was added when.

```php
$new_websites = [
];
```

## URL Structure

- **base_url**: The venue's root domain (e.g., `https://www.thebellhouseny.com`). This is informational only and helps identify the website. It is NOT directly crawled.
- **urls**: Array of specific pages to crawl, stored in the `website_urls` table. These should be calendar/events pages (e.g., `https://www.thebellhouseny.com/events`).

## Crawl Frequency

Leave `crawl_frequency` unset in almost all cases. The default is 7 days, which works for most venues.

Only suggest a different frequency if you have a specific reason:
- `1` - Daily (very high-traffic venues with events changing constantly)
- `2-4` - Active venues with frequent updates
- `14+` - Annual events or festivals

If you think a website needs a non-default frequency, ask the user first.

## Tags

Leave `tags` unset in almost all cases. Events are automatically tagged based on content during extraction.

Only add website-level tags if specifically requested by the user.

## Example Usage

User: "Add the Bell House website"

You would:
1. **Fetch the main site**: Use WebFetch on `https://www.thebellhouseny.com` to find navigation
2. **Find events page**: Look for "Events" or "Calendar" link
3. **Fetch events page**: Verify `https://www.thebellhouseny.com/events` has event listings
4. **Check location exists**: Query database for "The Bell House"
5. **Edit the script**:
```php
$new_websites = [
    [
        'name' => 'The Bell House',
        'description' => 'Brooklyn music venue and event space hosting concerts, comedy shows, and special events.',
        'base_url' => 'https://www.thebellhouseny.com',
        'urls' => ['https://www.thebellhouseny.com/events'],
        'location' => 'The Bell House',
    ],
];
```
6. Run dry-run, add to local db, and test crawl

## Checking for Existing Locations

Before adding a website, verify the location exists:

```bash
# Search for a location in local database
mysql -u root fomo -e "SELECT id, name FROM locations WHERE name LIKE '%Bell House%';"
```

If the location doesn't exist, use `/add-locations` to add it first.

## Troubleshooting Crawl Issues

If a crawl fails or returns no events:

1. **Check the crawl URL** - Visit it manually to verify events are visible
2. **Check for JavaScript rendering** - Some sites load events dynamically; note this in `notes`
3. **Check for anti-bot measures** - Some sites block crawlers
4. **Try alternative URLs** - Look for API endpoints, RSS feeds, or embedded calendars
5. **Consider external platforms** - Check if they use Eventbrite, Dice, etc. instead

## Adding Instagram Accounts

When adding websites, also check if the venue has an Instagram account. This is especially useful for venues without a dedicated events page, as events may only be posted on social media.

### Finding Instagram Handles

When researching a venue, look for:
- Instagram links in the website footer or header
- Social media icons on the homepage
- Search `"venue name" Instagram` to find their handle

### Adding to Database

```bash
# Add the Instagram account
mysql -u root fomo -e "INSERT INTO instagram_accounts (handle, name) VALUES ('venuehandle', 'Venue Name');"

# Link to location (get location_id and instagram_id first)
mysql -u root fomo -e "INSERT INTO location_instagram (location_id, instagram_id) VALUES (<location_id>, <instagram_id>);"
```

### Batch Insert Example

```sql
-- Add multiple accounts
INSERT IGNORE INTO instagram_accounts (handle, name) VALUES
('thebellhouseny', 'The Bell House'),
('unionhallny', 'Union Hall');

-- Link to locations
INSERT INTO location_instagram (location_id, instagram_id)
SELECT l.id, ia.id
FROM locations l, instagram_accounts ia
WHERE l.name = 'The Bell House' AND ia.handle = 'thebellhouseny';
```

### Informational Websites

Some venues don't have a crawlable events page, but do have a website which can be useful for users. In these cases, we should still add the website to the database, using only base_url and leaving the crawl urls empty.