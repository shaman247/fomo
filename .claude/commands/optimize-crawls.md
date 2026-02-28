---
name: optimize-crawls
description: Systematically investigate and fix websites with crawling issues
args: --limit <number>
---

You are tasked with investigating and optimizing websites that have crawling issues. Follow these steps systematically:

## Step 1: Identify Problem Websites

Find websites with crawling issues using this SQL query:

```sql
SELECT 
    w.id,
    w.name,
    w.base_url,
    cr.status,
    LENGTH(cr.crawled_content) as content_size,
    SUBSTRING(cr.error_message, 1, 80) as error_msg,
    w.delay_before_return_html,
    w.scan_full_page,
    w.use_stealth
FROM websites w
INNER JOIN crawl_results cr ON w.id = cr.website_id
WHERE cr.id IN (
    SELECT MAX(id) FROM crawl_results GROUP BY website_id
)
AND w.disabled = FALSE
AND (
    cr.status = 'failed' 
    OR (cr.status = 'crawled' AND LENGTH(cr.crawled_content) < 5000)
)
ORDER BY content_size ASC
LIMIT {limit};
```

Default limit: 10 if not specified by user

## Step 2: Test Sites with Better Settings

For each problematic site, test with improved crawl settings:

```python
import asyncio
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

async def test_sites():
    browser_config = BrowserConfig(
        headless=False, 
        java_script_enabled=True, 
        text_mode=True, 
        light_mode=True
    )
    
    crawler_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        delay_before_return_html=15,
        scan_full_page=True,
        scroll_delay=0.5,
        page_timeout=60000,
        markdown_generator=DefaultMarkdownGenerator(options={'ignore_links': False})
    )
    
    async with AsyncWebCrawler(config=browser_config) as crawler:
        # Test each URL
        result = await crawler.arun(url=url, config=crawler_config)
        # Check content length and presence of event data
```

## Step 3: Search for Alternative Sources

For sites still failing, search for alternative event sources:
- **dice.fm** - Excellent reliability, no stealth needed
- **Songkick** - Good for music venues
- **Eventbrite** - Great when venues use it
- **Resident Advisor** - Requires stealth mode (use_stealth=1)

Search query pattern:
```
"<venue name>" <city> events dice.fm songkick eventbrite 2026
```

## Step 4: Apply Fixes

Based on test results, apply appropriate fixes:

### For sites that work with better settings:
```sql
UPDATE websites 
SET delay_before_return_html = 15, 
    scan_full_page = 1, 
    scroll_delay = 0.5
WHERE id = {website_id};
```

### For sites needing alternative URLs:
```sql
DELETE FROM website_urls WHERE website_id = {website_id};
INSERT INTO website_urls (website_id, url, sort_order) 
VALUES ({website_id}, '{new_url}', 1);
```

### For sites needing stealth mode (RA, Cloudflare):
```sql
UPDATE websites 
SET use_stealth = 1,
    delay_before_return_html = 15,
    scan_full_page = 1
WHERE id = {website_id};
```

### For permanently closed venues:
```sql
UPDATE websites 
SET disabled = TRUE, 
    notes = 'Venue permanently closed {date}'
WHERE id = {website_id};
```

## Step 5: Test Fixed Sites

Run the pipeline to verify fixes work:
```bash
cd /Applications/XAMPP/xamppfiles/htdocs/fomo/pipeline
../venv/bin/python main.py --ids {comma_separated_ids}
```

Test in small batches (3-5 sites) to avoid browser issues.

## Step 6: Report Results

Provide a summary table showing:

| Website | Original Issue | Solution Applied | Events | Status |
|---------|---------------|------------------|--------|--------|
| Name    | Error/size    | Config/URL/Stealth | Count | ✅/❌ |

## Known Patterns & Solutions

### Squarespace/Wix Sites
**Symptoms:** Small content (< 500 bytes), missing dynamic content
**Fix:** delay=15s, scan_full_page=1, scroll_delay=0.5
**Examples:** Club Cumming, Coney Island USA, Berry Park

### Bot-Protected Sites
**Symptoms:** "Verifying browser", "Challenge", very small content
**Fix:** use_stealth=1
**Examples:** 
- Resident Advisor (ra.co) - verification page
- Cloudflare protection - Juilliard
- Vercel protection - Met Museum (no current bypass)

### Broken Calendar Widgets
**Symptoms:** Widget mentioned in HTML but no event data
**Fix:** Find alternative platform or disable iframe processing
**Examples:**
- POWR widgets (Cafe Wha?) - often unclaimed/broken
- Solution: Switch to Eventbrite, dice.fm, or Songkick

### Calendar Navigation Issues
**Symptoms:** Only current month events captured, future months missing
**Fix:** Add second URL with JS code to navigate to next month (see "JS Navigation for Calendar Sites" section)
**Examples:** Eastville Comedy Club, Magnet Theater, St. Marks Comedy Club
**Key:** Use `wait_until='domcontentloaded'` and generic date calculations (not hardcoded months)

### Deep Crawling Issues
**Symptoms:** Timeout, crawling hundreds of linked pages
**Fix:** Set keywords=NULL to disable deep crawling
**Examples:** Angelika theaters (was crawling every movie page)

### SSL/Connection Errors
**Symptoms:** ERR_SSL_PROTOCOL_ERROR, ERR_ABORTED, ERR_NAME_NOT_RESOLVED
**Fix:** Check if site is down, try alternative sources
**Examples:** Bossa Nova Civic Club direct site (use RA instead)

### Wrong Domain/URL Issues
**Symptoms:** ERR_NAME_NOT_RESOLVED, No content retrieved, but venue is active
**Fix:** Web search to find correct domain, check for domain changes
**Examples:**
- Welancora Gallery: welancora.com → welancoragallery.com
- Dorsey's Fine Art Gallery: dorseysartgallery.com → dorseysfineartgallery.com
- Yeh Art: yeh-art.com → sjuartgallery.org (St. John's University)
- The Woods: /events-1 → /events (Squarespace path change)

### Relative URL Issues
**Symptoms:** 404 errors, invalid URL structure
**Fix:** Ensure URLs include full protocol (https://)
**Examples:** Manhattan Borough President had "resources/events/" without base URL

### Fire/Closure Events
**Symptoms:** Multiple alternative sources all failing, recent news about closure
**Fix:** Web search "<venue> closed fire status 2026" to verify
**Examples:** Bossa Nova Civic Club (Jan 2022 fire, conflicting status)

### Image-Based Event Pages (Flyers/Posters)
**Symptoms:** Events are posted as image flyers/posters, not text. Crawl returns content but 0 events extracted.
**Fix:** Enable `process_images=1` and `text_mode=0` (both required). `scan_full_page=1` recommended.
**Why text_mode=0?** `text_mode=True` (default) disables image loading in the browser. Without images loaded, lazy-loading never triggers and `extract_image_urls()` finds no valid URLs.
**How it works:** `extract_image_urls()` parses `![alt](url)` from crawled markdown. Gemini vision API then reads the flyer images to extract event details.
**Examples:**
- The House BK - WordPress/Elementor with lazy-loaded event poster images
- TEMPEST - Squarespace with event flyers
- Marian's - Squarespace with event images
- Boyfriend Co-op - Astro site with event images

```sql
UPDATE websites
SET process_images = 1,
    text_mode = 0,
    scan_full_page = 1
WHERE id = {website_id};
```

**WordPress/Elementor lazy loading:** Images use `data-src` or `data-lazy-src` attributes with placeholder `src` values. The browser must load images (`text_mode=0`) and scroll the page (`scan_full_page=1`) to trigger lazy loading. If images still don't resolve, add `js_code` to force them:
```javascript
document.querySelectorAll('img[data-src], img[data-lazy-src]').forEach(function(img) {
    var realSrc = img.dataset.src || img.dataset.lazySrc;
    if (realSrc && realSrc.indexOf('data:') !== 0) img.src = realSrc;
});
```

### Iframe/Widget Calendar Sites
**Symptoms:** Events page loads but events are inside an iframe (Tockify, POWR, etc.)
**Fix:** Crawl the iframe source URL directly instead of the parent page
**How to find:** Use Playwright browser to inspect the page, look for `<iframe>` elements
**Examples:**
- The Rosemont - Tockify iframe → crawl `https://tockify.com/therosemontnyc/agenda`

### External Ticketing Platform Sites
**Symptoms:** Venue site links to external ticketing (TicketWeb, Dice, Eventbrite) for events
**Fix:** Crawl the external platform's venue page instead
**Examples:**
- Night Club 101 - TicketWeb → crawl `https://www.ticketweb.com/venue/night-club-101-new-york-ny/686683`

## Instagram Fallback

For venues with no working web calendar but active Instagram:

```sql
-- Insert Instagram account
INSERT INTO instagram_accounts (handle, name, description) 
VALUES ('{handle}', '{venue_name}', '{description}');

-- Link to website
INSERT INTO website_instagram (website_id, instagram_id) 
VALUES ({website_id}, LAST_INSERT_ID());
```

**Example:** The Duplex (theduplex_nyc) - only posts events on Instagram

## Venue Type Patterns

### Comedy Clubs
**Best Source:** Eventbrite (most comedy clubs use it)
**Example:** West Side Comedy Club - https://www.eventbrite.com/o/108546285201

### Movie Theaters
**Issue:** Deep crawling every movie page causes timeouts
**Fix:** Set keywords=NULL to disable deep crawling, increase crawl_timeout to 90
**Alternative:** Fandango, IMDb showtimes (but these are harder to parse)

### Art Galleries
**Pattern:** Often have sparse calendars (0 events between exhibitions is normal)
**Best Sources:** Gallery's direct site with delay=15s, Eventbrite if they use it
**Note:** Many galleries are appointment-only or have websites with wrong domains

### Museums
**Best Source:** Eventbrite for special events, direct site for regular exhibitions
**Example:** Museum of Interesting Things - 8 events via Eventbrite

### Music Venues
**Best Sources (in order):**
1. dice.fm - Excellent, no stealth needed
2. Songkick - Good, venue-specific pages
3. Eventbrite - Good if venue uses it
4. Resident Advisor - Requires use_stealth=1
5. Direct site - Last resort

### Private Event Spaces
**Action:** Disable - these venues rent for weddings/corporate, not public events
**Examples:** The Greenpoint Loft

### Public Parks/Squares
**Action:** Disable - no regular event schedule
**Examples:** Kimlau Square

## Best Practices

1. **Always test before applying** - Verify settings work with test script
2. **Prefer third-party platforms** - dice.fm > Songkick > Eventbrite > direct sites
3. **Check for venue closures** - Web search for recent news and fire incidents
4. **Verify domain accuracy** - Search "[venue name] official website" if domain fails
5. **Document changes** - Update notes field explaining configuration
6. **Batch testing** - Test 3-5 sites at a time, not all at once
7. **Start conservative** - Try delay=15s first, only increase if needed
8. **Monitor stealth mode** - Group all stealth sites in same batch
9. **Check URL paths** - Squarespace sites may change /events-1 to /events
10. **0 events is OK** - Galleries/museums between exhibitions will have empty calendars

## Troubleshooting Workflow

When a site fails, follow this decision tree:

1. **Check error message:**
   - `ERR_NAME_NOT_RESOLVED` → Search for correct domain
   - `ERR_SSL_*` or `ERR_ABORTED` → Site may be down, search for alternatives
   - `Timeout` → Check if keywords enabled (movie theaters), increase delay/timeout
   - `No content retrieved` → Try better settings (delay=15, scan_full_page=1)
   - `Content too small` → Same as "No content", or site uses heavy JavaScript

2. **If error unclear, web search:**
   - `"[venue name] [city] events eventbrite dice.fm songkick 2026"`
   - `"[venue name] closed status 2026"` (check for closures)
   - `"[venue name] official website"` (verify domain)

3. **Try alternative sources:**
   - Check venue type patterns above for best platform
   - Eventbrite: Search for venue name as organizer
   - dice.fm: Search venue name, look for venue page
   - Songkick: /venues/[venue-name] pattern

4. **If all alternatives fail:**
   - Check if venue is private/rental space → Disable
   - Check if venue closed/out of business → Disable with notes
   - Check if venue is public park → Disable

## Common SQL Queries

**Find sites with specific error patterns:**
```sql
SELECT id, name, base_url
FROM websites w
JOIN crawl_results cr ON w.id = cr.website_id
WHERE cr.error_message LIKE '%cloudflare%'
AND cr.id IN (SELECT MAX(id) FROM crawl_results GROUP BY website_id);
```

**Check current settings for a site:**
```sql
SELECT w.id, w.name, wu.url, 
       w.delay_before_return_html, w.scan_full_page, 
       w.use_stealth, w.keywords
FROM websites w
LEFT JOIN website_urls wu ON w.id = wu.website_id
WHERE w.id = {website_id};
```

**Find sites by content size:**
```sql
SELECT w.id, w.name, LENGTH(cr.crawled_content) as size
FROM websites w
JOIN crawl_results cr ON w.id = cr.website_id
WHERE cr.id IN (SELECT MAX(id) FROM crawl_results GROUP BY website_id)
ORDER BY size ASC
LIMIT 20;
```

## Expected Output Format

After completing optimization:

```
=== CRAWL OPTIMIZATION SUMMARY ===

Sites Investigated: X
Sites Fixed: Y  
Sites Disabled: Z
New Events Added: N

Detailed Results:
[Table with each site's outcome]

Applied Solutions:
- Better settings: X sites
- Alternative URLs: Y sites  
- Stealth mode enabled: Z sites
- Instagram fallback: N sites
- Disabled (closed): M sites

Key Findings:
- [Patterns noticed]
- [Common issues]

Next Steps:
- [Recommended follow-ups]
- [Sites needing manual investigation]
```

## JS Navigation for Calendar Sites

Many sites have calendar navigation that requires JavaScript to view future months. Use the `website_urls` table with `js_code` to handle this.

### Pattern: Two URLs per Website
- **sort_order=0**: Crawl current page (no JS) - captures current month
- **sort_order=1**: Same URL with JS code - navigates to next month

```sql
-- Check existing URLs for a website
SELECT id, url, sort_order, js_code FROM website_urls WHERE website_id = {id} ORDER BY sort_order;

-- Add JS navigation URL
INSERT INTO website_urls (website_id, url, sort_order, js_code)
VALUES ({website_id}, '{url}', 1, '{js_code}');
```

### JS Navigation Approaches

**1. Dynamic URL Navigation** (Best for link-based calendars)
Use when the site has URL patterns like `/calendar/2026-02` or `?date=2026-02-01`:

```javascript
// Generic next month calculation - works long-term
await new Promise(r => setTimeout(r, 2000));
const now = new Date();
const nextMonth = new Date(now.getFullYear(), now.getMonth() + 1, 1);
const year = nextMonth.getFullYear();
const month = String(nextMonth.getMonth() + 1).padStart(2, '0');
// Adjust URL pattern for the specific site:
window.location.href = '/calendar/' + year + '-' + month;  // Eastville format
// window.location.href = '/calendar/month/?date=' + year + '-' + month + '-01';  // Magnet format
// window.location.href = '/events/calendar/?yr=' + year + '&mo=' + month;  // Center for Fiction format
await new Promise(r => setTimeout(r, 3000));
```

**2. Button Click Navigation** (For AJAX calendars)
Use when clicking a button updates content without page reload:

```javascript
// Wait for calendar to load
await new Promise(r => setTimeout(r, 2000));
// Find and click the next month button
// IMPORTANT: Identify correct button index - may have hidden buttons before nav buttons
const buttons = document.querySelectorAll('button');
// Example: buttons[2] for St. Marks (0=mobile menu, 1=prev, 2=next)
buttons[2].click();
await new Promise(r => setTimeout(r, 2000));
```

**3. Load More Button** (For infinite scroll sites)
Use when site has "Load more" or "Show more" buttons:

```javascript
await new Promise(r => setTimeout(r, 2000));
for (let i = 0; i < 4; i++) {
    const allBtns = Array.from(document.querySelectorAll('button'));
    const loadMore = allBtns.find(b => b.textContent.includes('Load more'));
    if (loadMore) {
        loadMore.click();
        await new Promise(r => setTimeout(r, 1500));
    }
}
```

### Critical Settings

The crawler MUST use `wait_until='domcontentloaded'` for JS navigation to work:

```python
# In crawler.py - already configured globally
CrawlerRunConfig(
    wait_until='domcontentloaded',  # NOT networkidle - causes timeouts
    page_timeout=90000,
    # ... other settings
)
```

### Testing JS Navigation

```python
import asyncio
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, BrowserConfig

async def test_js_nav():
    browser_config = BrowserConfig(headless=True)

    # Test without JS
    config_no_js = CrawlerRunConfig(wait_until='domcontentloaded', page_timeout=60000)

    # Test with JS
    js_code = "..." # Your JS code
    config_with_js = CrawlerRunConfig(
        js_code=js_code,
        wait_until='domcontentloaded',
        page_timeout=90000
    )

    async with AsyncWebCrawler(config=browser_config) as crawler:
        result_no_js = await crawler.arun(url=url, config=config_no_js)
        result_with_js = await crawler.arun(url=url, config=config_with_js)

        # Compare: JS version should have more/different content
        print(f'Without JS: {len(result_no_js.html)} chars')
        print(f'With JS: {len(result_with_js.html)} chars')

        # Check for month indicators
        if 'February 2026' in result_with_js.html:
            print('Navigation working - found February 2026')

asyncio.run(test_js_nav())
```

### Finding Correct Button Selectors

Use Playwright browser tools to inspect the page structure:

```python
# Run in browser to see button order
const buttons = document.querySelectorAll('button');
Array.from(buttons).slice(0, 10).map((b, i) => ({
    index: i,
    text: b.textContent.trim().substring(0, 30),
    className: b.className.substring(0, 50)
}));
```

Common issues:
- **Hidden mobile menu buttons** - May be index 0, shifting other buttons
- **Multiple nav button types** - prev/next may not be at expected indices
- **Dynamic button creation** - Wait longer before querying buttons

### Sites Using JS Navigation

| Site | Type | JS Approach |
|------|------|-------------|
| Eastville Comedy Club | Dynamic URL | `/calendar/YYYY-MM` |
| Magnet Theater | Dynamic URL | `?date=YYYY-MM-01` |
| Center for Fiction | Dynamic URL | `?yr=YYYY&mo=MM` |
| St. Marks Comedy Club | Button click | `buttons[2].click()` |
| Brooklyn Museum | Load more | Multiple button clicks |
| Alvin Ailey | Button click | AJAX calendar |
| MoMA PS1 | Button click | AJAX calendar |

### Common Pitfalls

1. **Hardcoding months** - NEVER use hardcoded dates like `'2026-02'`. Always calculate dynamically.
2. **Using networkidle** - Causes timeouts. Use `domcontentloaded`.
3. **Wrong button index** - Inspect page to find correct index.
4. **Not waiting enough** - Calendar content may load async. Add delays.
5. **Link clicks destroying context** - Use `window.location.href` instead of `link.click()` for `<a>` tags.

## Notes

- Work in the `/Applications/XAMPP/xamppfiles/htdocs/fomo/pipeline` directory
- Use `../venv/bin/python` for Python scripts
- Database: MariaDB on localhost, user: root, database: fomo
- Always verify changes with pipeline test before marking complete
- Document why you made each change for future reference
