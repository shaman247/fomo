#!/usr/bin/env php
<?php
/**
 * Add new websites to the database (local or production)
 *
 * Usage:
 *   php scripts/add_websites.php                    # Add to local database
 *   php scripts/add_websites.php --production      # Add to production database
 *   php scripts/add_websites.php --dry-run         # Show what would be added
 *   php scripts/add_websites.php --production --dry-run
 *
 * Edit the $new_websites array below to specify websites to add.
 */

// ============================================================================
// EDIT THIS ARRAY TO ADD NEW WEBSITES
// ============================================================================
$new_websites = [
    // 2026-05-15 — NY Tech Week 2026 (a16z, tech-week.com). Annual week-long festival June 1-7;
    // 1409 in-person NYC events across 26 neighborhoods. Listing page is a Webflow Next.js SPA
    // that lazy-loads event rows; the FULL events array (id, name, host, date, time, neighborhood,
    // externalHref) lives in React state on each row. js_code (added post-insert via UPDATE because
    // add_websites.php drops js_code) scrolls to saturate the lazy-load, walks the React fiber to
    // pull the unfiltered events array, filters virtual + non-NYC, and renders one event per line
    // for clean Gemini extraction. Roving festival — no fixed location; let event-level neighborhood
    // drive mapping. Set crawl_frequency to 30d since the event runs once a year (scheduler will
    // auto-tune down after the week passes).
    [
        'name' => 'NY Tech Week',
        'description' => 'Annual week-long technology festival (presented by a16z) hosting ~1,400 in-person NYC events across networking, panels, demos, hackathons, and parties; events are scattered across Manhattan, Brooklyn, and Queens neighborhoods with each session hosted by a different company.',
        'base_url' => 'https://www.tech-week.com',
        'urls' => ['https://www.tech-week.com/calendar/nyc'],
        'crawl_frequency' => 30,
        'notes' => 'Content is pre-formatted via js_code as a clean list, one event per line: "* YYYY-MM-DD HH:MM — EVENT NAME (host: HOST_COMPANY; neighborhood: NEIGHBORHOOD; url: URL)". Extract each line as a single event. start_time is HH:MM 24-hour format — convert to compact lowercase (09:00 → 9am, 14:30 → 2:30pm). location_name is the NYC neighborhood (Chelsea, SoHo, Tribeca, etc.) — not a specific venue. description should be "Hosted by HOST_COMPANY at #NYTechWeek 2026." The url field is the per-event RSVP page (mostly Partiful/Luma/company sites) and is required. These are all in-person NYC events from June 1-7, 2026 — do NOT extract any Virtual events.',
    ],
    // 2026-05-15 — Middle Sibling Productions (Eventbrite organizer 113176279871). Independent NYC
    // theater company doing stage readings and small productions at rented venues (The Flea, etc.).
    // Eventbrite org page lists all upcoming events with venue + date/time. Roving — no fixed
    // website_locations; let per-event venue drive mapping. Surfaced from Blankman List Jun 2026
    // cross-reference (On the Mountain at The Flea, Jun 6).
    [
        'name' => 'Middle Sibling Productions',
        'description' => 'Independent NYC theater production company; stages readings and small productions of contemporary plays at rented venues including The Flea Theater.',
        'base_url' => 'https://www.eventbrite.com/o/113176279871',
        'urls' => ['https://www.eventbrite.com/o/113176279871'],
        'crawl_frequency' => 14,
        'notes' => 'Eventbrite organizer page. Each upcoming event has a dedicated detail page with venue and date/time. Venues vary — no fixed location, let per-event venue field drive mapping.',
    ],
    // 2026-05-15 — PlentyofParties (Eventbrite organizer 18245241891). NYC event-organizer brand running
    // singles mixers, happy hours, rooftop parties, and themed nights at rotating bar/restaurant venues
    // (Blind Barber, etc.). Roving — no fixed website_locations; let per-event venue drive mapping.
    // Surfaced from Blankman List Jun 2026 cross-reference (Come As You Were 90s Mixer at Blind Barber, Jun 4).
    [
        'name' => 'PlentyofParties',
        'description' => 'NYC event-production brand organizing recurring singles mixers, themed parties, happy hours, and rooftop events for various age brackets (20s/30s/40s/50s) at rotating bar and restaurant venues across Manhattan and Brooklyn.',
        'base_url' => 'https://www.eventbrite.com/o/18245241891',
        'urls' => ['https://www.eventbrite.com/o/18245241891'],
        'crawl_frequency' => 14,
        'notes' => 'Eventbrite organizer page. Many events per month at rotating venues. Each event has its venue in the title or detail page. No fixed location — let per-event venue drive mapping (Blind Barber, etc.).',
    ],
    // 2026-05-15 — City & State New York (cityandstateny.com). Politics-and-policy media org running
    // multiple structured NYC conferences each month (Nonprofit OpCon, Nonprofit Trailblazers, Food
    // Access Summit, Rebuilding NY Summit, etc.). Surfaced via /cross-reference-aggregator on the
    // BetaNYC #CivicTech roundup — Nonprofit OpCon was already in our DB (event 117417) but multiple
    // future C&S conferences are not. Clean Upcoming/Featured/Archived sections on the events page;
    // each event has a dedicated detail page with venue + time. Conference venues roam (Hebrew Union
    // College, Roosevelt House, etc.) so no fixed website_locations link — let per-event venue drive mapping.
    [
        'name' => 'City & State New York',
        'description' => 'NYC politics and policy media organization running monthly structured conferences on nonprofit operations, food access, infrastructure, and other civic topics; conference venues vary across Manhattan.',
        'base_url' => 'https://www.cityandstateny.com',
        'urls' => ['https://www.cityandstateny.com/events/'],
        'crawl_frequency' => 7,
    ],
    // 2026-05-14 — Salvation Army Centennial Memorial Temple (thecmt.org). Landmarked 1929 Art Deco
    // performance hall in Chelsea (location 4395). Site is venue-rental marketing only — no public
    // events calendar, sitemap covers just the rentable spaces (Auditorium, Railton Hall, Mumford Hall).
    // Added as informational-only (no urls/crawl_frequency) so the venue popup has a website link;
    // events at CMT come through outside organizers' sites.
    [
        'name' => 'Salvation Army Centennial Memorial Temple',
        'description' => 'Landmarked 1929 Art Deco performance hall in Chelsea, used for concerts, screenings, community meetings, and cultural events.',
        'base_url' => 'https://thecmt.org/',
        'location' => 'Salvation Army Centennial Memorial Temple',
        'notes' => 'Informational only — site has no public events calendar. Events at CMT are surfaced via outside organizers.',
    ],
    // 2026-05-14 — SCUFF (queer country line-dance org). Hosts classes and parties at NYC venues:
    // Gibney (Studio D, loc 349), Playhouse Bar (loc 2569), Red Eye NY (loc 2651). Upcoming page
    // serves all upcoming NYC events with structured "DAY DATE / TIME / EVENT NAME / VENUE" text —
    // clean for markdown extraction. Found via /cross-reference-aggregator on gayagenda.nyc which
    // listed 4+ SCUFF events at Gibney and Wilka's that our venue-page crawls miss.
    [
        'name' => 'SCUFF',
        'description' => 'Queer country line-dancing organization running beginner/intermediate classes and parties at NYC venues including Gibney (Studio D), Playhouse Bar, and Red Eye NY. Also has Bay Area and Joshua Tree chapters; only NYC events are surfaced via the category filter.',
        'base_url' => 'https://www.scuff.us/',
        'urls' => ['https://www.scuff.us/upcoming?event_category_id=scuff-nyc'],
        'crawl_frequency' => 7,
        'notes' => 'Each event listing has the format: "DAY, MONTH DATE / TIME / EVENT NAME / VENUE / NEW YORK CITY". Venue names use SCUFF\'s shorthand — map "GIBNEY (STUDIO D)" → Gibney Dance, "PLAYHOUSE" → Playhouse Bar, "RED EYE NY" → Red Eye NY. SKIP entries prefixed "COMING SOON:" (placeholders without confirmed tickets). Recurring weekly classes (NYC Beginner / Intermediate Line Dance Class) should be merged into ONE event with multiple occurrences. NYC PARTY at Playhouse Bar is a separate event.',
    ],
    // 2026-05-14 — Brooklyn Pride (brooklynpride.org). Annual LGBTQIA+ pride org running the Twilight
    // Parade, Multicultural Festival, 5K, Youth Pride, and Cyclones Pride Night. Squarespace events
    // collection — use ?format=json upcoming[] pattern (post-insert UPDATE because add_websites.php
    // drops js_code silently). Events span Park Slope (5th Ave parade route, Prospect Park 5K) and
    // citywide partner venues (Maimonides Park for Cyclones), so let per-event venue/sublocation drive
    // mapping; no website_locations fallback.
    [
        'name' => 'Brooklyn Pride',
        'description' => 'Volunteer-run Brooklyn LGBTQIA+ pride organization producing the annual Twilight Parade and Multicultural Festival on 5th Ave Park Slope, the LGBTQIA+ 5K in Prospect Park, Brooklyn Cyclones Pride Night, and Youth Pride.',
        'base_url' => 'https://brooklynpride.org',
        'urls' => ['https://brooklynpride.org/events'],
        'crawl_frequency' => 7,
    ],
    // 2026-05-14 — Park Slope Fifth Avenue BID. Organizes the Fabulous Fifth Avenue Fair, Brooklyn Pride
    // Day on 5th, Park Slope Picnic, and other 5th Ave (Sterling Pl to 12th St) street programming.
    // WordPress + Tribe Events Calendar plugin — use the REST API via the standard generic js_code
    // (post-insert UPDATE because add_websites.php drops js_code silently). Events roam across 5th Ave
    // blocks so no fixed location; let per-event venue/sublocation drive mapping.
    [
        'name' => 'Park Slope Fifth Avenue BID',
        'description' => 'Business Improvement District for 5th Avenue in Park Slope (Sterling Place to 12th Street); organizes the Fabulous Fifth Avenue Fair, Brooklyn Pride Day on 5th, Park Slope Picnic, and other neighborhood street events.',
        'base_url' => 'https://parkslopefifthavenuebid.com',
        'urls' => ['https://parkslopefifthavenuebid.com/events/'],
        'crawl_frequency' => 7,
    ],
    // 2026-05-14 — Pomo Ceramics (Bed-Stuy ceramics studio, 951 Putnam Ave). Single Squarespace
    // page lists one-day workshops, multi-week courses, and family programs. Updates infrequently
    // so low crawl frequency.
    [
        'name' => 'Pomo Ceramics',
        'description' => 'Bed-Stuy ceramics studio running one-day adult wheel-throwing workshops, multi-week hand-building and wheel-throwing courses, and family/kids pottery programs.',
        'base_url' => 'https://www.pomoceramics.com',
        'urls' => ['https://www.pomoceramics.com/one-day-workshops-and-events'],
        'crawl_frequency' => 30,
        'location' => 'Pomo Ceramics',
        'tags' => ['Ceramics', 'Pottery', 'Workshop'],
    ],
    // 2026-05-12 — Cake Picnic Tour (NYC stop). Touring community gathering where attendees bring whole
    // cakes to share. NYC events roam between venues (Little Island, La Cabra Brooklyn, Governors Island,
    // etc.) so no fixed location — let event-level venues drive mapping.
    [
        'name' => 'Cake Picnic NYC',
        'description' => 'Touring community cake-sharing event series; each NYC edition is hosted at a different outdoor or cafe venue and attendees bring whole cakes to share.',
        'base_url' => 'https://www.cakepicnictour.com',
        'urls' => ['https://www.cakepicnictour.com/nyc'],
        'crawl_frequency' => 14,
        'notes' => 'Only extract events listed on the NYC page. Save-the-date entries with no confirmed venue/time should still be captured with the date and a note that venue is TBD.',
    ],
    // 2026-05-11 — ITP|IMA at NYU Tisch: Interactive Telecommunications Program and Interactive Media
    // Arts run by Tisch School of the Arts. Hosts public shows, demos, talks, and the Spring Show at
    // 370 Jay St (NYU Brooklyn). Eventbrite organizer 3539473083 (canonical slug "itpima") is the
    // primary event channel. No fixed venue link — events are at NYU Tisch (721 Broadway) and NYU
    // Brooklyn (370 Jay St) depending on the program, so let event-level venues drive mapping.
    [
        'name' => 'ITP|IMA',
        'description' => 'NYU Tisch School of the Arts Interactive Telecommunications Program and Interactive Media Arts — graduate programs running public shows, demos, talks, and the semesterly ITP|IMA Show.',
        'base_url' => 'https://www.eventbrite.com',
        'urls' => ['https://www.eventbrite.com/o/itpima-3539473083'],
        'crawl_frequency' => 14,
        'notes' => 'IMPORTANT: Ignore any promoted events or events in "Other events you may like" or "Related events" sections. Only extract events directly from this organizer/venue.',
    ],
    // 2026-05-10 — Please, An Educated Pleasure Shop (South Slope sex-positive shop, location 6345).
    // Eventbrite organizer 72665370743 is the primary event channel; pleasenyc.com is informational only.
    [
        'name' => 'Please, An Educated Pleasure Shop',
        'description' => 'South Slope sex-positive shop hosting erotic life-drawing sessions, educational talks, and other adult-oriented art and learning events alongside its retail offerings.',
        'base_url' => 'https://www.eventbrite.com',
        'urls' => ['https://www.eventbrite.com/o/72665370743'],
        'location' => 'Please, An Educated Pleasure Shop',
    ],
    // 2026-05-10 — NYC choir/singing collectives discovered via Common Ground (Resonance ✕ Musicollage
    // at Crossroads Cafe, Bushwick, 2026-04-30). Gaia Music Collective already exists as website 1960
    // (Eventbrite); adding @gaiamusiccollective IG for the picnob rotation. Singing Resistance NYC and
    // Hands Off NYC are decentralized — no fixed venue. Musicollage/Resonance also roam; Crossroads
    // Cafe is the one venue with a known address (location 2639). Viewcy URL pattern matches existing
    // entries (LILA Series w2632, Huge Flop w2633, Dance Beyond w2635).
    [
        'name' => 'Singing Resistance NYC',
        'description' => 'Decentralized NYC sing-in movement organizing public solidarity singing with immigrant communities and at sites of ICE-related violence; events co-hosted by partner orgs like Middle Church, Riverside Church, Hands Off NYC, and the Resistance Revival Chorus.',
        'base_url' => 'https://www.instagram.com/singingresistancenyc/',
    ],
    [
        'name' => 'Hands Off NYC',
        'description' => 'NYC community activism coalition organizing protests, sing-ins, and mutual-aid events focused on immigration rights and resistance to ICE. Calendar links out to Mobilize.us per event.',
        'base_url' => 'https://www.handsoffnyc.com/calendar',
        'notes' => 'Aggregator — do not crawl on a regular cadence. Use /cross-reference-aggregator to surface coverage gaps; manually insert + AI-tag the events we want. Static HTML page with per-event Mobilize.us links.',
    ],
    [
        'name' => 'Musicollage',
        'description' => 'NYC improv singing collective offering inclusive vocal workshops and interactive concerts; collaborates with Resonance and Bushwick venues like Crossroads Cafe.',
        'base_url' => 'https://www.viewcy.com/musicollage',
        'urls' => ['https://www.viewcy.com/calendar/o/musicollage?defaultLayout=list&showDescription=true&showImage=true'],
    ],
    [
        'name' => 'Resonance',
        'description' => 'Creative-arts community hosting transformative gatherings through shared music and creative practice; partners with Musicollage and Bushwick venues like Crossroads Cafe.',
        'base_url' => 'https://www.viewcy.com/resonance1',
        'urls' => ['https://www.viewcy.com/calendar/o/resonance1?defaultLayout=list&showDescription=true&showImage=true'],
    ],
    // Crossroads Cafe already exists as website 3083 with base_url https://www.xroads.cafe/ and no
    // crawl URL. The Viewcy calendar URL is added separately to website_urls for that row (rather
    // than as a duplicate website).
    [
        'name' => 'Gaia Music Collective IG',
        'description' => 'Instagram presence for Gaia Music Collective (Brooklyn-founded community choir running CircleSings, One-Day Choirs, and open mics). Primary crawl is the Eventbrite organizer page (website 1960); this row adds the IG handle to the picnob rotation.',
        'base_url' => 'https://www.instagram.com/gaiamusiccollective/',
    ],
    [
        'name' => 'Musicollage IG',
        'description' => 'Instagram presence for Musicollage (NYC improv singing collective). Companion to the Viewcy crawl entry; this row adds the IG handle to the picnob rotation.',
        'base_url' => 'https://www.instagram.com/musicollage_org/',
    ],
    // 2026-05-10 — Feminist Bird Club: nationwide birding community with active NYC chapter running
    // weekly spring/fall migration walks at Prospect Park, Lincoln Terrace, Astoria Park, etc.
    // Squarespace site — uses ?format=json for the events collection. FBC has chapters worldwide
    // (Winnipeg, Rochester, Nashville, etc.) all listed on the same /events page, so the js_code
    // filters by lat/lng to NYC metro bounds before injecting events into the DOM. No fixed venue —
    // walks happen at various parks/trailheads, so no `location` link.
    [
        'name' => 'Feminist Bird Club',
        'description' => 'Feminist Bird Club NYC chapter — beginner-friendly bird walks during spring and fall migration at parks across the city, plus occasional virtual talks and meetups.',
        'base_url' => 'https://www.feministbirdclub.org/',
        'urls' => ['https://www.feministbirdclub.org/events'],
        'crawl_frequency' => 7,
        'notes' => 'Squarespace ?format=json endpoint — js_code fetches /events?format=json and injects only upcoming events whose mapLat/mapLng fall inside NYC metro bounds (lat 40.4–41.2, lng -74.5 to -73.4). FBC has chapters nationwide (Winnipeg, Rochester, Nashville, Tucson, etc.) all interleaved on the same page; lat/lng filter is reliable because each event carries map coordinates. Empty-address events still come through if their coordinates are in-bounds (some Astoria Park events have blank addressLine1/2 but valid lat/lng). Roaming organizer — walks happen at various parks, so no fixed location link. Most events recur weekly during migration season; merger should consolidate.',
        'js_code' => <<<'JS'
await new Promise(r => setTimeout(r, 1000));
try {
  const url = location.pathname + location.search + (location.search ? '&' : '?') + 'format=json';
  const r = await fetch(url);
  if (!r.ok) throw new Error('fetch failed');
  const j = await r.json();
  const upcoming = j.upcoming || [];
  const nyc = upcoming.filter(ev => {
    const lat = ev.location?.mapLat;
    const lng = ev.location?.mapLng;
    return lat && lng && lat > 40.4 && lat < 41.2 && lng > -74.5 && lng < -73.4;
  });
  const main = document.querySelector('main, #content, .content') || document.body;
  main.innerHTML = '';
  if (nyc.length) {
    const fmtDate = ms => new Date(ms).toLocaleString('en-US', { weekday:'short', month:'long', day:'numeric', year:'numeric', hour:'numeric', minute:'2-digit', hour12: true });
    const ul = document.createElement('ul');
    ul.id = 'sqs-events';
    for (const ev of nyc) {
      const li = document.createElement('li');
      const loc = ev.location || {};
      const addr = [loc.addressTitle, loc.addressLine1, loc.addressLine2].filter(Boolean).join(', ');
      const desc = (ev.excerpt || ev.body || '').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 600);
      const link = ev.fullUrl ? new URL(ev.fullUrl, location.origin).href : '';
      li.innerHTML = `<h3><a href="${link}">${ev.title}</a></h3>` +
        `<p><strong>${fmtDate(ev.startDate)} – ${fmtDate(ev.endDate)}</strong></p>` +
        `<p>${addr}</p>` +
        `<p>${desc}</p>`;
      ul.appendChild(li);
    }
    main.appendChild(ul);
  } else {
    const p = document.createElement('p');
    p.textContent = 'No upcoming NYC events.';
    main.appendChild(p);
  }
} catch (e) { console.error('Squarespace JSON fetch failed', e); }
JS,
        'tags' => ['Birding', 'Nature', 'Outdoor', 'Women', 'LGBTQ+'],
    ],
    // 2026-05-10 — Girls Gone Hiking: NYC women's hiking community running slow-paced day hikes
    // accessible from the city (no fixed venue — hikes at various trailheads). Luma calendar API
    // pattern — point crawl URL at api.lu.ma/url?url=<slug> for full structured event data with
    // geo_address_info; same extractor guidance as Climate Cafe NYC (w489). No upcoming events
    // listed at insertion time, so 14-day cadence is fine.
    [
        'name' => 'Girls Gone Hiking',
        'description' => "NYC women's hiking community building sisterhood on the trail with slow-paced day hikes accessible from the city.",
        'base_url' => 'https://luma.com/girlsgonehiking',
        'urls' => ['https://api.lu.ma/url?url=girlsgonehiking'],
        'crawl_frequency' => 14,
        'notes' => 'Luma calendar API JSON (https://api.lu.ma/url?url=<slug>). Returns full structured event data including geo_address_info (full_address, short_address, address, sublocality), coordinates, host info.

EXTRACTOR GUIDANCE:

1. TIMEZONE: All start_at and end_at timestamps are UTC. Each event has a timezone field (America/New_York). You MUST convert start_at from UTC to the local timezone before extracting start_date and start_time. Example: start_at="2026-05-09T01:00:00.000Z" with timezone="America/New_York" → start_date="2026-05-08", start_time="9:00 PM" (UTC-4 EDT).

2. VENUE NAME: location = geo_address_info.address.

3. STREET ADDRESS: sublocation = geo_address_info.short_address (e.g. "119 N 1st St, Brooklyn"). The street address is REQUIRED in sublocation — the processor uses this as a fallback to match the event to an existing location whose address matches. Without it, new venues stay unmapped.

4. SKIP events with no geo_address_info or geo_address_visibility != "public" — those are RSVP-gated and have no address to extract.

Roaming organizer — hikes at various trailheads (no fixed venue). Slug confirmed via /url API; IG is @girlsgonehikingnyc.',
        'tags' => ['Hiking', 'Outdoor', 'Nature'],
    ],
    // 2026-05-09 — Bhakti Center: yoga/kirtan/temple in East Village (25 First Ave). Listing page
    // /all-offerings-2/ shows event titles only as images — markdown crawl yields just dates and
    // "Follow a manual added link" labels. js_code below fetches each linked subpage and inlines
    // its title + main content into the listing DOM. Mix of dated workshops (Marma Workshop,
    // Ayurveda & Motherhood, 1-Day Retreat, India Pilgrimage) and recurring programs (Tuesday/
    // Thursday Night Kirtan, Soul Talks, NYC 6-Hour Kirtan, Urban Devi, community groups).
    [
        'name' => 'Bhakti Center',
        'description' => 'East Village yoga, kirtan, and temple center at 25 First Ave hosting workshops, retreats, weekly kirtan nights, and ongoing community groups rooted in Bhakti yoga.',
        'base_url' => 'https://bhakticenter.org/',
        'urls' => ['https://bhakticenter.org/all-offerings-2/'],
        'crawl_frequency' => 7,
        'notes' => 'Listing page event titles are images, not text — markdown extraction loses them. js_code fetches every linked subpage on /all-offerings-2/ and inlines `<h2>title</h2><p>url</p><p>full body text</p>` into the DOM so the crawler picks up structured event info. Each detail page has a clean title + description + date/time block (e.g., "Date: May 30 2-4pm" or "tuesdays 7:30pm-8:30pm EST"). Recurring programs (Tuesday Night Kirtan, Soul Talks, NYC 6-Hour Kirtan) should be ONE event with multiple occurrences.',
        'js_code' => <<<'JS'
const skip = ['/yoga/','/temple/','/amrita-boutique/','/about-2/','/donate/','/volunteer/','/join-our-team/','/feedbackform/','/payroll-giving/','/take-your-next-step/','/all-offerings-2/'];
const links = Array.from(document.querySelectorAll('a[href]'))
  .map(a => a.href.replace(/\/$/, ''))
  .filter(h => h.startsWith('https://bhakticenter.org/'))
  .filter(h => h !== 'https://bhakticenter.org')
  .filter(h => !h.includes('#') && !h.startsWith('mailto:'))
  .filter(h => !skip.some(s => h.includes(s.replace(/\/$/, ''))));
const unique = [...new Set(links)];
const container = document.createElement('div');
container.id = 'inlined-event-details';
for (const url of unique) {
  try {
    const r = await fetch(url);
    if (!r.ok) continue;
    const html = await r.text();
    const doc = new DOMParser().parseFromString(html, 'text/html');
    ['header','footer','nav','script','style','.fl-page-header','.fl-page-footer'].forEach(t => doc.querySelectorAll(t).forEach(e => e.remove()));
    const main = doc.querySelector('.fl-builder-content') || doc.body;
    const text = (main?.textContent || '').replace(/\s+/g, ' ').trim();
    if (!text) continue;
    const title = doc.querySelector('h1')?.textContent?.trim() || doc.querySelector('title')?.textContent?.trim() || url;
    const section = document.createElement('section');
    const h = document.createElement('h2'); h.textContent = title; section.appendChild(h);
    const u = document.createElement('p'); const a = document.createElement('a'); a.href = url; a.textContent = url; u.appendChild(a); section.appendChild(u);
    const p = document.createElement('p'); p.textContent = text; section.appendChild(p);
    container.appendChild(section);
  } catch(e) {}
}
document.body.appendChild(container);
JS,
        'tags' => ['Manhattan', 'East Village', 'Yoga', 'Spirituality'],
    ],
    // 2026-05-09 — Time Out Market Union Square (124 E 14th St) has its own /whats-on page distinct
    // from DUMBO. Recurring events: Trivia Tuesday, themed Happy Hour nights, weekly bRUNch run,
    // Fluffy Pop-up, Ultimate Cup watch parties. The DUMBO/Brooklyn market is already crawled as
    // website 107 against /time-out-market-new-york/things-to-do/shows-events.
    [
        'name' => 'Time Out Market Union Square',
        'description' => 'Union Square food hall at 124 E 14th St with seven kitchens, a bar, and a stage; hosts trivia nights, themed happy hours, a weekly run-and-brunch, pop-ups, and sports watch parties.',
        'base_url' => 'https://www.timeout.com/time-out-market-union-square',
        'urls' => ['https://www.timeout.com/time-out-market-union-square/whats-on'],
        'crawl_frequency' => 7,
        'location' => 'Time Out Market New York (Union Square)',
    ],
    // 2026-05-08 — Kosmic Community antibar Instagram (picnob-scrape source). No events posted yet,
    // so crawl_after is set to 2026-05-14 to avoid wasting crawls until they start posting.
    [
        'name' => '@kosmiccommunityantibar',
        'description' => 'Instagram for Kosmic Community antibar.',
        'base_url' => 'https://www.instagram.com/kosmiccommunityantibar/',
        'crawl_frequency' => 14,
        'crawl_after' => '2026-05-14',
    ],
    // 2026-05-06 — Hex House art studio in East Williamsburg. No crawlable events page —
    // events are posted to Instagram (@hexh0use) and one-off microsites; informational website only.
    [
        'name' => 'Hex House',
        'description' => '4,000 sq ft warehouse art studio and community event space in East Williamsburg, hosting performances, ceremonies, classes, and creative showcases.',
        'base_url' => 'https://hexhouse.studio',
        'location' => 'Hex House',
    ],
    // 2026-05-06 — Hex House Instagram (picnob-scrape source). Events posted as flyers/captions.
    // IG extraction guidance lives in pipeline/extractor.py INSTAGRAM_NOTES_DEFAULT —
    // leave `notes` blank unless this account needs handling beyond the default.
    [
        'name' => '@hexh0use',
        'description' => 'Instagram for Hex House — East Williamsburg art studio and event space.',
        'base_url' => 'https://www.instagram.com/hexh0use/',
        'crawl_frequency' => 14,
        'location' => 'Hex House',
    ],
    // 2026-05-04 — East Williamsburg film-camera shop. Calendar uses the Mahina Shopify app
    // (POST https://mahina.app/app/brooklyn-film-camera.myshopify.com → JSON). js_code patched
    // separately after insert to fetch that API and inject events into the DOM. Events are at
    // multiple venues (855 Grand, 56 Bogart, 26 Bridge, etc.) — extractor reads each from desc.
    [
        'name' => 'Brooklyn Film Camera',
        'description' => 'East Williamsburg film-camera shop and lab whose calendar lists in-house gallery openings plus partner photography classes and tintype workshops at venues across Brooklyn.',
        'base_url' => 'https://brooklynfilmcamera.com',
        'urls' => ['https://brooklynfilmcamera.com/pages/calendar'],
        'crawl_frequency' => 7,
        'notes' => 'Shopify site running the Mahina Event Calendar app. js_code POSTs to https://mahina.app/app/brooklyn-film-camera.myshopify.com and injects the returned events into the DOM (the widget is otherwise JS-rendered and slow to populate). Event venues vary — extractor should read each from the description (e.g., "26 Bridge", "56 Bogart", "855 Grand") rather than defaulting to the shop.',
        'location' => 'Brooklyn Film Camera',
        'tags' => ['Brooklyn', 'East Williamsburg', 'Photography'],
    ],
    // 2026-05-04 — Annual instant-film festival hosted at 26 Bridge in DUMBO. Wix blog post with rich
    // JSON-LD Event schema (name/dates/location/offers) — extractor reads it cleanly. Page is updated
    // each year with new dates, so a long crawl_frequency suffices.
    [
        'name' => 'Instant Film Society',
        'description' => 'Brooklyn-based 501c3 nonprofit promoting analog instant photography; hosts the annual three-day PolaCon NYC convention at 26 Bridge with Polaroid and Brooklyn Film Camera.',
        'base_url' => 'https://www.instantfilmsociety.org',
        'urls' => ['https://www.instantfilmsociety.org/post/polacon-nyc'],
        'crawl_frequency' => 60,
        'notes' => 'Wix blog post for the annual PolaCon NYC instant-film festival at 26 Bridge in DUMBO. Currently May 29-31, 2026. Three days of workshops, photo walks, vendor booths, and presentations. Page is updated each year with new dates.',
        'location' => '26 Bridge',
        'tags' => ['Brooklyn', 'DUMBO', 'Photography'],
    ],
    // 2026-05-04 — Sunnyside bar/restaurant with a packed live-music + brunch calendar (NFG showcases,
    // K-pop brunch, charity showcases, pottery paint brunch). Squarespace ?format=json — js_code patched
    // separately after insert. URL uses ?view=list so the JSON exposes top-level `upcoming` (the default
    // /calendar view returns calendarView with month-paginated `items`).
    [
        'name' => 'Sanger Hall',
        'description' => 'Sunnyside bar and restaurant hosting live-music showcases, themed brunches (K-pop, mimosa, pottery paint), and charity events.',
        'base_url' => 'https://www.sangerhall.com/',
        'urls' => ['https://www.sangerhall.com/calendar?view=list'],
        'crawl_frequency' => 7,
        'notes' => 'Squarespace site. js_code uses ?format=json pattern to inject upcoming events into the DOM. ?view=list in the URL ensures the JSON returns a top-level `upcoming` array instead of the month-paginated `items` array.',
        'location' => 'Sanger Hall',
        'tags' => ['Queens', 'Sunnyside', 'Live Music'],
    ],
    // 2026-05-04 — City Happenings cross-ref. New crawl sources for events not surfaced by existing
    // venue crawls: Mambroso roams between lofts (Luma organizer), KREWE flagship hosts annual NYC pop-ups.
    [
        'name' => 'Mambroso',
        'description' => 'Salsa and mambo dance event organizer hosting rooftop sessions, brunches, and singles socials at lofts around Manhattan.',
        'base_url' => 'https://luma.com/mambroso',
        'urls' => ['https://luma.com/mambroso'],
        'crawl_frequency' => 7,
        'notes' => 'Roaming dance organizer. Events held at various lofts/rooftops around NYC (Loft on 5th, Loft in Flatiron, Aura Cocina, etc.). No fixed venue.',
        'tags' => ['Manhattan', 'Dance', 'Music'],
    ],
    [
        'name' => 'KREWE NYC',
        'description' => 'New Orleans eyewear brand whose Meatpacking flagship hosts pop-up parties and an annual NYC Krawfish Boil benefiting City Harvest.',
        'base_url' => 'https://krewe.com/pages/events',
        'urls' => ['https://krewe.com/pages/events'],
        'crawl_frequency' => 30,
        'notes' => 'Multi-city events page (NOLA + NYC). Only extract events at the NYC flagship (67 Gansevoort St). Skip events at New Orleans venues like Fair Grounds, French Quarter Flagship, PATULA, Jazz Fest.',
        'location' => 'KREWE NYC',
        'tags' => ['Manhattan', 'Meatpacking District', 'Shopping'],
    ],
    // 2026-05-02 — DUMBO board game café, sister of Last Place on Earth in Greenpoint.
    [
        'name' => '3rd Place from the Sun',
        'description' => 'DUMBO board game café and gaming lounge with 500+ curated games, hosting open play and weekly recurring D&D campaigns.',
        'base_url' => 'https://www.3rdplacebk.com',
        'urls' => ['https://www.3rdplacebk.com/dungeons-dragons'],
        'notes' => 'Static page describing recurring weekly D&D programs (no individual dated sessions). Extract three recurring events: "Beginners D&D" (Fridays 7pm), "Ladies D&D" (Wednesdays 7pm, femmes/non-binary), "Queer D&D" (Thursdays 7pm). The /events page is just pricing/policy info — ignore.',
        'location' => '3rd Place from the Sun',
        'tags' => ['Brooklyn', 'DUMBO', 'Games'],
    ],
    // 2026-05-01 — Nonsense NYC newsletter cross-ref: 5 new organizer/venue sources whose events
    // we manually inserted last week (events 108471-108486). Adding so future cycles auto-crawl.
    // Brooklyn Contra (w2588) already exists — updated separately via SQL (URL + Squarespace js_code).
    [
        'name' => 'Remedies Herb Shop',
        'description' => 'Carroll Gardens herb shop offering bulk dried herbs, tinctures, and a regular calendar of herbalism workshops and classes.',
        'base_url' => 'https://remediesherbshop.com/',
        'urls' => ['https://remediesherbshop.com/classes-events/'],
        'crawl_frequency' => 14,
        'notes' => 'BigCommerce category page listing classes as products with date in title. Each class is a product page with date/time inside.',
        'location' => 'Remedies Herb Shop',
        'tags' => ['Brooklyn', 'Carroll Gardens', 'Wellness'],
    ],
    [
        'name' => 'Analytic Salon',
        'description' => 'Recurring philosophy salon at the CUNY Graduate Center, open to anyone interested in analytic philosophy regardless of background.',
        'base_url' => 'https://analytic-salon-nyc.github.io/',
        'urls' => ['https://analytic-salon-nyc.github.io/'],
        'crawl_frequency' => 14,
        'notes' => 'Plain static HTML; upcoming dates listed inline. Sessions at CUNY Graduate Center, 365 5th Ave.',
        'location' => 'CUNY Graduate Center',
        'tags' => ['Manhattan', 'Midtown', 'Lecture'],
    ],
    [
        'name' => 'The Spotlight Comedy',
        'description' => 'Pop-up comedy show producer hosting "secret" stand-up shows at Cozy Art Land in Long Island City and other unconventional venues.',
        'base_url' => 'https://www.eventbrite.com/o/the-spotlight-comedy-62788201173',
        'urls' => ['https://www.eventbrite.com/o/the-spotlight-comedy-62788201173'],
        'crawl_frequency' => 14,
        'notes' => 'IMPORTANT: Ignore any promoted events or events in "Other events you may like" or "Related events" sections. Only extract events directly from this organizer/venue. Mostly at Cozy Art Land, Long Island City.',
        'location' => 'Cozy Art Land',
        'tags' => ['Queens', 'Long Island City', 'Comedy'],
    ],
    [
        'name' => 'Boxcutter Collective',
        'description' => 'Brooklyn-based film and live performance collective producing screenings of original work paired with live music, often at Rubulad and other DIY venues.',
        'base_url' => 'https://www.eventbrite.com/o/121243139359',
        'urls' => ['https://www.eventbrite.com/o/121243139359'],
        'crawl_frequency' => 14,
        'notes' => 'IMPORTANT: Ignore any promoted events or events in "Other events you may like" or "Related events" sections. Only extract events directly from this organizer/venue. Multi-venue (Rubulad, Knickerbocker Ave, The Clemente, etc.).',
        'location' => 'Rubulad',
        'tags' => ['Brooklyn', 'Film', 'Music'],
    ],
    [
        'name' => 'Ukrainian Village Voices',
        'description' => 'NYC-based Eastern European folk choral and dance group hosting concerts, workshops, and community singing events.',
        'base_url' => 'https://www.eventbrite.com/o/ukrainian-village-voices-32104739983',
        'urls' => ['https://www.eventbrite.com/o/ukrainian-village-voices-32104739983'],
        'crawl_frequency' => 14,
        'notes' => 'IMPORTANT: Ignore any promoted events or events in "Other events you may like" or "Related events" sections. Only extract events directly from this organizer/venue. Multi-venue (Playwrights Downtown, Ukrainian National Home, etc.).',
        'location' => 'Playwrights Downtown',
        'tags' => ['Manhattan', 'Music', 'Dance'],
    ],
    // 2026-05-01 — onboarding NYC-metro Regal Cinemas (companion to AMC theaters added 2026-04-30).
    // Single URL per theater — Regal's Next.js SSR embeds all 60+ days of showtimes in __NEXT_DATA__,
    // so a single crawl per theater captures the full schedule (no ?date= multi-URL pattern needed).
    [
        'name' => 'Regal Union Square',
        'description' => 'A 14-screen multiplex movie theater on Broadway near Union Square showing first-run releases.',
        'base_url' => 'https://www.regmovies.com/theatres/regal-union-square-stadium-14-1320',
        'urls' => ['https://www.regmovies.com/theatres/regal-union-square-stadium-14-1320'],
        'crawl_frequency' => 2,
        'location' => 'Regal Union Square',
        'tags' => ['Manhattan', 'Union Square', 'Cinema'],
    ],
    [
        'name' => 'Regal Battery Park',
        'description' => '11-screen movie theater in Battery Park City showing first-run releases.',
        'base_url' => 'https://www.regmovies.com/theatres/regal-battery-park-stadium-11-1335',
        'urls' => ['https://www.regmovies.com/theatres/regal-battery-park-stadium-11-1335'],
        'crawl_frequency' => 2,
        'location' => 'Regal Battery Park',
        'tags' => ['Manhattan', 'Battery Park City', 'Cinema'],
    ],
    [
        'name' => 'Regal Essex Crossing',
        'description' => 'Lower East Side movie theater inside Essex Crossing development with RPX premium screens.',
        'base_url' => 'https://www.regmovies.com/theatres/regal-essex-crossing-rpx-1412',
        'urls' => ['https://www.regmovies.com/theatres/regal-essex-crossing-rpx-1412'],
        'crawl_frequency' => 2,
        'location' => 'Regal Essex Crossing',
        'tags' => ['Manhattan', 'Lower East Side', 'Cinema'],
    ],
    [
        'name' => 'Regal Times Square',
        'description' => 'Times Square movie theater on 42nd Street showing first-run releases.',
        'base_url' => 'https://www.regmovies.com/theatres/regal-times-square-1929',
        'urls' => ['https://www.regmovies.com/theatres/regal-times-square-1929'],
        'crawl_frequency' => 2,
        'location' => 'Regal Times Square',
        'tags' => ['Manhattan', 'Times Square', 'Cinema'],
    ],
    [
        'name' => 'Regal Cinema Sheepshead Bay',
        'description' => '14-screen Brooklyn multiplex with IMAX and RPX premium screens.',
        'base_url' => 'https://www.regmovies.com/theatres/sheepshead-stm-14-imax-rpx-1159',
        'urls' => ['https://www.regmovies.com/theatres/sheepshead-stm-14-imax-rpx-1159'],
        'crawl_frequency' => 2,
        'location' => 'Regal Cinema Sheepshead Bay',
        'tags' => ['Brooklyn', 'Sheepshead Bay', 'Cinema'],
    ],
    [
        'name' => 'Regal Atlas Park',
        'description' => '8-screen Queens movie theater inside The Shops at Atlas Park.',
        'base_url' => 'https://www.regmovies.com/theatres/regal-atlas-park-0688',
        'urls' => ['https://www.regmovies.com/theatres/regal-atlas-park-0688'],
        'crawl_frequency' => 2,
        'location' => 'Regal Atlas Park',
        'tags' => ['Queens', 'Glendale', 'Cinema'],
    ],
    [
        'name' => 'Regal UA Midway',
        'description' => '9-screen Forest Hills movie theater on Queens Boulevard.',
        'base_url' => 'https://www.regmovies.com/theatres/ua-midway-stadium-9-1143',
        'urls' => ['https://www.regmovies.com/theatres/ua-midway-stadium-9-1143'],
        'crawl_frequency' => 2,
        'location' => 'Regal UA Midway',
        'tags' => ['Queens', 'Forest Hills', 'Cinema'],
    ],
    [
        'name' => 'Regal Kaufman Astoria',
        'description' => '14-screen multiplex inside Kaufman Astoria Studios with RPX premium screens.',
        'base_url' => 'https://www.regmovies.com/theatres/kaufman-astoria-stm-14-rpx-1333',
        'urls' => ['https://www.regmovies.com/theatres/kaufman-astoria-stm-14-rpx-1333'],
        'crawl_frequency' => 2,
        'location' => 'Regal Kaufman Astoria',
        'tags' => ['Queens', 'Long Island City', 'Cinema'],
    ],
    [
        'name' => 'Regal Tangram',
        'description' => 'Flushing movie theater featuring 4DX premium screens.',
        'base_url' => 'https://www.regmovies.com/theatres/regal-tangram-4dx-1472',
        'urls' => ['https://www.regmovies.com/theatres/regal-tangram-4dx-1472'],
        'crawl_frequency' => 2,
        'location' => 'Regal Tangram',
        'tags' => ['Queens', 'Flushing', 'Cinema'],
    ],
    [
        'name' => 'Regal Concourse',
        'description' => 'Bronx movie theater near Yankee Stadium showing first-run releases.',
        'base_url' => 'https://www.regmovies.com/theatres/regal-concourse-1486',
        'urls' => ['https://www.regmovies.com/theatres/regal-concourse-1486'],
        'crawl_frequency' => 2,
        'location' => 'Regal Concourse',
        'tags' => ['Bronx', 'Concourse', 'Cinema'],
    ],
    [
        'name' => 'Regal Bricktown Charleston',
        'description' => '10-screen Staten Island movie theater inside the Bricktown Center development.',
        'base_url' => 'https://www.regmovies.com/theatres/regal-bricktown-charleston-10-1419',
        'urls' => ['https://www.regmovies.com/theatres/regal-bricktown-charleston-10-1419'],
        'crawl_frequency' => 2,
        'location' => 'Regal Bricktown Charleston',
        'tags' => ['Staten Island', 'Charleston', 'Cinema'],
    ],
    [
        'name' => 'Regal Westbury',
        'description' => '12-screen Long Island movie theater with IMAX and RPX premium screens.',
        'base_url' => 'https://www.regmovies.com/theatres/westbury-stadium-12-imax-rpx-1273',
        'urls' => ['https://www.regmovies.com/theatres/westbury-stadium-12-imax-rpx-1273'],
        'crawl_frequency' => 2,
        'location' => 'Regal Westbury',
        'tags' => ['Long Island', 'Nassau County', 'Westbury', 'Cinema'],
    ],
    [
        'name' => 'Regal Lynbrook',
        'description' => '13-screen Nassau County movie theater with RPX premium screens.',
        'base_url' => 'https://www.regmovies.com/theatres/lynbrook-13-rpx-1348',
        'urls' => ['https://www.regmovies.com/theatres/lynbrook-13-rpx-1348'],
        'crawl_frequency' => 2,
        'location' => 'Regal Lynbrook',
        'tags' => ['Long Island', 'Nassau County', 'Lynbrook', 'Cinema'],
    ],
    [
        'name' => 'Regal UA Farmingdale',
        'description' => '10-screen Long Island movie theater with IMAX premium screens.',
        'base_url' => 'https://www.regmovies.com/theatres/ua-farmingdale-stm-10-imax-1319',
        'urls' => ['https://www.regmovies.com/theatres/ua-farmingdale-stm-10-imax-1319'],
        'crawl_frequency' => 2,
        'location' => 'Regal UA Farmingdale',
        'tags' => ['Long Island', 'Nassau County', 'Farmingdale', 'Cinema'],
    ],
    [
        'name' => 'Regal Ronkonkoma',
        'description' => '9-screen Suffolk County movie theater showing first-run releases.',
        'base_url' => 'https://www.regmovies.com/theatres/regal-ronkonkoma-0632',
        'urls' => ['https://www.regmovies.com/theatres/regal-ronkonkoma-0632'],
        'crawl_frequency' => 2,
        'location' => 'Regal Ronkonkoma',
        'tags' => ['Long Island', 'Suffolk County', 'Ronkonkoma', 'Cinema'],
    ],
    [
        'name' => 'Regal Deer Park',
        'description' => 'Suffolk County movie theater with IMAX premium screens.',
        'base_url' => 'https://www.regmovies.com/theatres/regal-deer-park-0692',
        'urls' => ['https://www.regmovies.com/theatres/regal-deer-park-0692'],
        'crawl_frequency' => 2,
        'location' => 'Regal Deer Park',
        'tags' => ['Long Island', 'Suffolk County', 'Deer Park', 'Cinema'],
    ],
    [
        'name' => 'Regal UA East Hampton',
        'description' => '6-screen movie theater in the Hamptons showing first-run releases.',
        'base_url' => 'https://www.regmovies.com/theatres/ua-east-hampton-cinema-6-1138',
        'urls' => ['https://www.regmovies.com/theatres/ua-east-hampton-cinema-6-1138'],
        'crawl_frequency' => 2,
        'location' => 'Regal UA East Hampton',
        'tags' => ['Long Island', 'East Hampton', 'Cinema'],
    ],
    [
        'name' => 'Regal New Roc',
        'description' => '18-screen Westchester movie theater with IMAX and RPX premium screens.',
        'base_url' => 'https://www.regmovies.com/theatres/regal-new-roc-0297',
        'urls' => ['https://www.regmovies.com/theatres/regal-new-roc-0297'],
        'crawl_frequency' => 2,
        'location' => 'Regal New Roc',
        'tags' => ['Westchester', 'New Rochelle', 'Cinema'],
    ],
    [
        'name' => 'Regal Cortlandt Town Center',
        'description' => '11-screen Westchester County movie theater showing first-run releases.',
        'base_url' => 'https://www.regmovies.com/theatres/cortlandt-town-center-stm-11-1318',
        'urls' => ['https://www.regmovies.com/theatres/cortlandt-town-center-stm-11-1318'],
        'crawl_frequency' => 2,
        'location' => 'Regal Cortlandt Town Center',
        'tags' => ['Westchester', 'Mohegan Lake', 'Cinema'],
    ],
    [
        'name' => 'Regal Nanuet',
        'description' => '12-screen Rockland County movie theater with RPX premium screens.',
        'base_url' => 'https://www.regmovies.com/theatres/regal-nanuet-rpx-0558',
        'urls' => ['https://www.regmovies.com/theatres/regal-nanuet-rpx-0558'],
        'crawl_frequency' => 2,
        'location' => 'Regal Nanuet',
        'tags' => ['Hudson Valley', 'Rockland County', 'Nanuet', 'Cinema'],
    ],
    [
        'name' => 'Regal Galleria Mall (Poughkeepsie)',
        'description' => '16-screen Hudson Valley movie theater inside Poughkeepsie Galleria Mall.',
        'base_url' => 'https://www.regmovies.com/theatres/regal-galleria-mall-stadium-16-1740',
        'urls' => ['https://www.regmovies.com/theatres/regal-galleria-mall-stadium-16-1740'],
        'crawl_frequency' => 2,
        'location' => 'Regal Galleria Mall (Poughkeepsie)',
        'tags' => ['Hudson Valley', 'Poughkeepsie', 'Cinema'],
    ],
    [
        'name' => 'Regal Secaucus',
        'description' => '14-screen New Jersey movie theater inside Mill Creek Plaza.',
        'base_url' => 'https://www.regmovies.com/theatres/regal-secaucus-showplace-14-1665',
        'urls' => ['https://www.regmovies.com/theatres/regal-secaucus-showplace-14-1665'],
        'crawl_frequency' => 2,
        'location' => 'Regal Secaucus',
        'tags' => ['New Jersey', 'Hudson County', 'Secaucus', 'Cinema'],
    ],

    // 2026-04-30 — onboarding remaining NYC-area AMC theaters (sister venues to AMC 34th Street 14, id 3441).
    // URLs use {{date}} / {{date+N}} templates so they don't go stale; js_code + JS render settings
    // (delay, scan_full_page) get applied via a follow-up Python step (the PHP script doesn't yet support
    // per-URL js_code or website-level JS settings).
    [
        'name' => 'AMC Empire 25',
        'description' => 'A 25-screen multiplex movie theater in Times Square. First-run releases plus IMAX and Dolby Cinema.',
        'base_url' => 'https://www.amctheatres.com/movie-theatres/new-york-city/amc-empire-25',
        'urls' => [
            'https://www.amctheatres.com/movie-theatres/new-york-city/amc-empire-25/showtimes?date={{date}}',
            'https://www.amctheatres.com/movie-theatres/new-york-city/amc-empire-25/showtimes?date={{date+3}}',
            'https://www.amctheatres.com/movie-theatres/new-york-city/amc-empire-25/showtimes?date={{date+7}}',
            'https://www.amctheatres.com/movie-theatres/new-york-city/amc-empire-25/showtimes?date={{date+14}}',
            'https://www.amctheatres.com/movie-theatres/new-york-city/amc-empire-25/showtimes?date={{date+28}}',
            'https://www.amctheatres.com/movie-theatres/new-york-city/amc-empire-25/showtimes?date={{date+38}}',
        ],
        'crawl_frequency' => 2,
        'location' => 'AMC Empire 25',
        'tags' => ['Cinema', 'Manhattan', 'Times Square'],
    ],
    [
        'name' => 'AMC 19th St. East 6',
        'description' => 'Six-screen movie theater near Union Square showing first-run releases.',
        'base_url' => 'https://www.amctheatres.com/movie-theatres/new-york-city/amc-19th-st-east-6',
        'urls' => [
            'https://www.amctheatres.com/movie-theatres/new-york-city/amc-19th-st-east-6/showtimes?date={{date}}',
            'https://www.amctheatres.com/movie-theatres/new-york-city/amc-19th-st-east-6/showtimes?date={{date+3}}',
            'https://www.amctheatres.com/movie-theatres/new-york-city/amc-19th-st-east-6/showtimes?date={{date+7}}',
            'https://www.amctheatres.com/movie-theatres/new-york-city/amc-19th-st-east-6/showtimes?date={{date+14}}',
            'https://www.amctheatres.com/movie-theatres/new-york-city/amc-19th-st-east-6/showtimes?date={{date+28}}',
            'https://www.amctheatres.com/movie-theatres/new-york-city/amc-19th-st-east-6/showtimes?date={{date+38}}',
        ],
        'crawl_frequency' => 2,
        'location' => 'AMC 19th St. East 6',
        'tags' => ['Cinema', 'Manhattan', 'Union Square'],
    ],
    [
        'name' => 'AMC Kips Bay 15',
        'description' => 'A 15-screen movie theater in Kips Bay showing first-run releases and special programming.',
        'base_url' => 'https://www.amctheatres.com/movie-theatres/new-york-city/amc-kips-bay-15',
        'urls' => [
            'https://www.amctheatres.com/movie-theatres/new-york-city/amc-kips-bay-15/showtimes?date={{date}}',
            'https://www.amctheatres.com/movie-theatres/new-york-city/amc-kips-bay-15/showtimes?date={{date+3}}',
            'https://www.amctheatres.com/movie-theatres/new-york-city/amc-kips-bay-15/showtimes?date={{date+7}}',
            'https://www.amctheatres.com/movie-theatres/new-york-city/amc-kips-bay-15/showtimes?date={{date+14}}',
            'https://www.amctheatres.com/movie-theatres/new-york-city/amc-kips-bay-15/showtimes?date={{date+28}}',
            'https://www.amctheatres.com/movie-theatres/new-york-city/amc-kips-bay-15/showtimes?date={{date+38}}',
        ],
        'crawl_frequency' => 2,
        'location' => 'AMC Kips Bay 15',
        'tags' => ['Cinema', 'Manhattan', 'Kips Bay'],
    ],
    [
        'name' => 'AMC Village 7',
        'description' => 'Seven-screen movie theater on Third Avenue at 11th Street showing first-run releases.',
        'base_url' => 'https://www.amctheatres.com/movie-theatres/new-york-city/amc-village-7',
        'urls' => [
            'https://www.amctheatres.com/movie-theatres/new-york-city/amc-village-7/showtimes?date={{date}}',
            'https://www.amctheatres.com/movie-theatres/new-york-city/amc-village-7/showtimes?date={{date+3}}',
            'https://www.amctheatres.com/movie-theatres/new-york-city/amc-village-7/showtimes?date={{date+7}}',
            'https://www.amctheatres.com/movie-theatres/new-york-city/amc-village-7/showtimes?date={{date+14}}',
            'https://www.amctheatres.com/movie-theatres/new-york-city/amc-village-7/showtimes?date={{date+28}}',
            'https://www.amctheatres.com/movie-theatres/new-york-city/amc-village-7/showtimes?date={{date+38}}',
        ],
        'crawl_frequency' => 2,
        'location' => 'AMC Village 7',
        'tags' => ['Cinema', 'Manhattan', 'East Village'],
    ],
    [
        'name' => 'AMC Lincoln Square 13',
        'description' => 'A 13-screen multiplex movie theater on the Upper West Side, including an IMAX with Laser screen.',
        'base_url' => 'https://www.amctheatres.com/movie-theatres/new-york-city/amc-lincoln-square-13',
        'urls' => [
            'https://www.amctheatres.com/movie-theatres/new-york-city/amc-lincoln-square-13/showtimes?date={{date}}',
            'https://www.amctheatres.com/movie-theatres/new-york-city/amc-lincoln-square-13/showtimes?date={{date+3}}',
            'https://www.amctheatres.com/movie-theatres/new-york-city/amc-lincoln-square-13/showtimes?date={{date+7}}',
            'https://www.amctheatres.com/movie-theatres/new-york-city/amc-lincoln-square-13/showtimes?date={{date+14}}',
            'https://www.amctheatres.com/movie-theatres/new-york-city/amc-lincoln-square-13/showtimes?date={{date+28}}',
            'https://www.amctheatres.com/movie-theatres/new-york-city/amc-lincoln-square-13/showtimes?date={{date+38}}',
        ],
        'crawl_frequency' => 2,
        'location' => 'AMC Lincoln Square 13',
        'tags' => ['Cinema', 'Manhattan', 'Upper West Side'],
    ],
    [
        'name' => 'AMC 84th Street 6',
        'description' => 'Six-screen Upper West Side movie theater showing first-run releases.',
        'base_url' => 'https://www.amctheatres.com/movie-theatres/new-york-city/amc-84th-street-6',
        'urls' => [
            'https://www.amctheatres.com/movie-theatres/new-york-city/amc-84th-street-6/showtimes?date={{date}}',
            'https://www.amctheatres.com/movie-theatres/new-york-city/amc-84th-street-6/showtimes?date={{date+3}}',
            'https://www.amctheatres.com/movie-theatres/new-york-city/amc-84th-street-6/showtimes?date={{date+7}}',
            'https://www.amctheatres.com/movie-theatres/new-york-city/amc-84th-street-6/showtimes?date={{date+14}}',
            'https://www.amctheatres.com/movie-theatres/new-york-city/amc-84th-street-6/showtimes?date={{date+28}}',
            'https://www.amctheatres.com/movie-theatres/new-york-city/amc-84th-street-6/showtimes?date={{date+38}}',
        ],
        'crawl_frequency' => 2,
        'location' => 'AMC 84th Street 6',
        'tags' => ['Cinema', 'Manhattan', 'Upper West Side'],
    ],
    [
        'name' => 'AMC Newport Centre 11',
        'description' => 'Eleven-screen movie theater inside Newport Centre Mall in Jersey City.',
        'base_url' => 'https://www.amctheatres.com/movie-theatres/jersey-city/amc-newport-centre-11',
        'urls' => [
            'https://www.amctheatres.com/movie-theatres/jersey-city/amc-newport-centre-11/showtimes?date={{date}}',
            'https://www.amctheatres.com/movie-theatres/jersey-city/amc-newport-centre-11/showtimes?date={{date+3}}',
            'https://www.amctheatres.com/movie-theatres/jersey-city/amc-newport-centre-11/showtimes?date={{date+7}}',
            'https://www.amctheatres.com/movie-theatres/jersey-city/amc-newport-centre-11/showtimes?date={{date+14}}',
            'https://www.amctheatres.com/movie-theatres/jersey-city/amc-newport-centre-11/showtimes?date={{date+28}}',
            'https://www.amctheatres.com/movie-theatres/jersey-city/amc-newport-centre-11/showtimes?date={{date+38}}',
        ],
        'crawl_frequency' => 2,
        'location' => 'AMC Newport Centre 11',
        'tags' => ['Cinema', 'New Jersey', 'Jersey City'],
    ],
    [
        'name' => 'AMC Orpheum 7',
        'description' => 'Seven-screen movie theater on the Upper East Side at 86th Street.',
        'base_url' => 'https://www.amctheatres.com/movie-theatres/new-york-city/amc-orpheum-7',
        'urls' => [
            'https://www.amctheatres.com/movie-theatres/new-york-city/amc-orpheum-7/showtimes?date={{date}}',
            'https://www.amctheatres.com/movie-theatres/new-york-city/amc-orpheum-7/showtimes?date={{date+3}}',
            'https://www.amctheatres.com/movie-theatres/new-york-city/amc-orpheum-7/showtimes?date={{date+7}}',
            'https://www.amctheatres.com/movie-theatres/new-york-city/amc-orpheum-7/showtimes?date={{date+14}}',
            'https://www.amctheatres.com/movie-theatres/new-york-city/amc-orpheum-7/showtimes?date={{date+28}}',
            'https://www.amctheatres.com/movie-theatres/new-york-city/amc-orpheum-7/showtimes?date={{date+38}}',
        ],
        'crawl_frequency' => 2,
        'location' => 'AMC Orpheum 7',
        'tags' => ['Cinema', 'Manhattan', 'Upper East Side'],
    ],
    [
        'name' => 'AMC Magic Johnson Harlem 9',
        'description' => 'Nine-screen movie theater in Harlem (former Magic Johnson Theatres) showing first-run releases.',
        'base_url' => 'https://www.amctheatres.com/movie-theatres/new-york-city/amc-magic-johnson-harlem-9',
        'urls' => [
            'https://www.amctheatres.com/movie-theatres/new-york-city/amc-magic-johnson-harlem-9/showtimes?date={{date}}',
            'https://www.amctheatres.com/movie-theatres/new-york-city/amc-magic-johnson-harlem-9/showtimes?date={{date+3}}',
            'https://www.amctheatres.com/movie-theatres/new-york-city/amc-magic-johnson-harlem-9/showtimes?date={{date+7}}',
            'https://www.amctheatres.com/movie-theatres/new-york-city/amc-magic-johnson-harlem-9/showtimes?date={{date+14}}',
            'https://www.amctheatres.com/movie-theatres/new-york-city/amc-magic-johnson-harlem-9/showtimes?date={{date+28}}',
            'https://www.amctheatres.com/movie-theatres/new-york-city/amc-magic-johnson-harlem-9/showtimes?date={{date+38}}',
        ],
        'crawl_frequency' => 2,
        'location' => 'AMC Magic Johnson Harlem 9',
        'tags' => ['Cinema', 'Manhattan', 'Harlem'],
    ],

    // Meetup.com round-2 sweep (2026-04-28) — 20 more NYC-area groups
    // Board games / hobbies
    ['name' => 'Victory Pints: Board Games and Beer', 'description' => 'NYC board game meetup hosting drop-in game nights at bars and breweries.', 'base_url' => 'https://www.meetup.com/VictoryPints/', 'urls' => ['https://www.meetup.com/VictoryPints/events/']],
    ['name' => 'Tuesday Board Games', 'description' => 'NYC board game meetup with regular Tuesday evening game nights at bars and cafes.', 'base_url' => 'https://www.meetup.com/tuesday-board-games/', 'urls' => ['https://www.meetup.com/tuesday-board-games/events/']],
    ['name' => 'Nyeek Board Games', 'description' => 'NYC board game group with regular game nights and themed events at venues across the city.', 'base_url' => 'https://www.meetup.com/NyeekGames/', 'urls' => ['https://www.meetup.com/NyeekGames/events/']],
    ['name' => 'NYC Boardgames & Cardgames', 'description' => 'Large NYC boardgame community hosting regular game nights at The Hugh in midtown Manhattan.', 'base_url' => 'https://www.meetup.com/nyc-boardgames/', 'urls' => ['https://www.meetup.com/nyc-boardgames/events/'], 'location' => 'The Hugh', 'notes' => 'Members-only Meetup group ("Location visible to members"). Group consistently meets at The Hugh, 157 E 53rd St, New York. Treat all events as taking place at The Hugh unless the event title clearly names a different venue.'],

    // Sports / recreation
    ['name' => 'Pickleball for Fun NYC', 'description' => 'NYC pickleball meetup with regular drop-in play sessions at courts across the city.', 'base_url' => 'https://www.meetup.com/pickleball-fun/', 'urls' => ['https://www.meetup.com/pickleball-fun/events/']],
    ['name' => 'New York Sports Meetup Group', 'description' => 'Multi-sport NYC meetup with regular pick-up games for soccer, volleyball, basketball, and more.', 'base_url' => 'https://www.meetup.com/new-york-sports-meetup-group/', 'urls' => ['https://www.meetup.com/new-york-sports-meetup-group/events/']],
    ['name' => 'Brooklyn Rock Climb + Chill', 'description' => 'Casual Brooklyn rock-climbing meetup with regular indoor climbing sessions and post-climb hangs.', 'base_url' => 'https://www.meetup.com/casual-rock-climbing/', 'urls' => ['https://www.meetup.com/casual-rock-climbing/events/']],

    // Crafts
    ['name' => "NYC Pints 'n' Purls", 'description' => 'NYC knitting and crochet meetup combining stitching with drinks at bars and cafes.', 'base_url' => 'https://www.meetup.com/NYC-Pints-N-Purls/', 'urls' => ['https://www.meetup.com/NYC-Pints-N-Purls/events/']],
    ['name' => 'NYC Crochet Guild', 'description' => 'NYC crochet community with regular meetups, workshops, and stitch-and-chats.', 'base_url' => 'https://www.meetup.com/new-york-city-crochet-guild/', 'urls' => ['https://www.meetup.com/new-york-city-crochet-guild/events/']],

    // Food
    ['name' => 'Culinary Enthusiasts of NYC', 'description' => 'NYC dining meetup with regular group dinners exploring restaurants across the city.', 'base_url' => 'https://www.meetup.com/Culinary-Enthusiasts-of-NYC/', 'urls' => ['https://www.meetup.com/Culinary-Enthusiasts-of-NYC/events/']],
    ['name' => 'NYC Foodie Explorers', 'description' => 'NYC dining meetup with restaurant outings and culinary explorations across the boroughs.', 'base_url' => 'https://www.meetup.com/NYC-Foodie-Explorers/', 'urls' => ['https://www.meetup.com/NYC-Foodie-Explorers/events/']],
    ['name' => 'NYC Foodies', 'description' => 'NYC dining meetup with regular group meals at restaurants citywide.', 'base_url' => 'https://www.meetup.com/NYC-Foodies/', 'urls' => ['https://www.meetup.com/NYC-Foodies/events/']],

    // Outdoors / hiking
    ['name' => '5 Boro Exploration', 'description' => 'NYC walking and exploration meetup with regular neighborhood walks across all five boroughs.', 'base_url' => 'https://www.meetup.com/5BoroEXPLORATION/', 'urls' => ['https://www.meetup.com/5BoroEXPLORATION/events/']],
    ['name' => 'Explorer Chicks of NYC', 'description' => 'Women\'s outdoor adventure meetup with regular hikes, kayaks, and weekend trips in the tri-state area.', 'base_url' => 'https://www.meetup.com/explorer-chicks-of-nyc/', 'urls' => ['https://www.meetup.com/explorer-chicks-of-nyc/events/']],
    ['name' => 'AMC Young Members NYC', 'description' => 'NYC chapter of the Appalachian Mountain Club Young Members with regular hikes, climbs, and outdoor trips.', 'base_url' => 'https://www.meetup.com/amcyoungmembers/', 'urls' => ['https://www.meetup.com/amcyoungmembers/events/']],

    // Poker
    ['name' => 'LIC Poker Club', 'description' => 'Long Island City poker meetup with regular cash games and tournaments.', 'base_url' => 'https://www.meetup.com/lic-poker-club/', 'urls' => ['https://www.meetup.com/lic-poker-club/events/']],
    ['name' => 'Queens Poker Club', 'description' => 'Queens-based poker meetup with regular cash games at venues across the borough.', 'base_url' => 'https://www.meetup.com/queens-poker-club/', 'urls' => ['https://www.meetup.com/queens-poker-club/events/']],

    // Special interest
    ['name' => 'NYC Sci-Fi/Fantasy Meetup', 'description' => 'NYC science fiction and fantasy meetup with author events, book discussions, and themed gatherings.', 'base_url' => 'https://www.meetup.com/scifi-22/', 'urls' => ['https://www.meetup.com/scifi-22/events/']],
    ['name' => 'BirdingAroundNYC', 'description' => 'NYC birding meetup with regular birdwatching outings in city parks and surrounding nature areas.', 'base_url' => 'https://www.meetup.com/birdingaroundnyc/', 'urls' => ['https://www.meetup.com/birdingaroundnyc/events/']],
    ['name' => 'NYC Trivia & Friends', 'description' => 'NYC trivia meetup with regular pub-trivia nights at bars and restaurants citywide.', 'base_url' => 'https://www.meetup.com/NYCTrivia1/', 'urls' => ['https://www.meetup.com/NYCTrivia1/events/']],

    // Meetup.com broad sweep (2026-04-28) — 25 NYC-area groups across gap categories
    // (running, dance, writing, art, outdoors, books, cycling, lgbtq, language, comedy, music)
    // Note format for groups whose events vary by venue: omit `location`, let extractor pick up venues per-event.

    // Running clubs
    ['name' => 'TMIRCE Running Club NYC', 'description' => 'The Most Informal Running Club Ever — large casual NYC running community with weekly group runs across boroughs.', 'base_url' => 'https://www.meetup.com/nyc-informal-running-club-home-of-tmirce-nyc/', 'urls' => ['https://www.meetup.com/nyc-informal-running-club-home-of-tmirce-nyc/events/']],
    ['name' => 'Founders Running Club NY', 'description' => 'NYC running club for entrepreneurs and professionals with regular group runs.', 'base_url' => 'https://www.meetup.com/founders-running-club-new-york/', 'urls' => ['https://www.meetup.com/founders-running-club-new-york/events/']],
    ['name' => 'RUN LIC', 'description' => 'Long Island City running club with frequent group runs around Queens and the East River.', 'base_url' => 'https://www.meetup.com/longislandcity-runners/', 'urls' => ['https://www.meetup.com/longislandcity-runners/events/']],
    ['name' => 'Sweet Avenue Run Club', 'description' => 'Sunnyside, Queens run club with regular weekday and weekend group runs.', 'base_url' => 'https://www.meetup.com/sweet-avenue-run-club/', 'urls' => ['https://www.meetup.com/sweet-avenue-run-club/events/']],
    ['name' => 'Astoria Runners', 'description' => 'Astoria-based running community with weekly group runs around Queens.', 'base_url' => 'https://www.meetup.com/astoriarunners/', 'urls' => ['https://www.meetup.com/astoriarunners/events/']],
    ['name' => 'Brooklyn Beer Runners', 'description' => 'Brooklyn run club that combines group runs with post-run beers at local bars and breweries.', 'base_url' => 'https://www.meetup.com/Brooklyn-Beer-Runners/', 'urls' => ['https://www.meetup.com/Brooklyn-Beer-Runners/events/']],

    // Dance
    ['name' => 'NY/NJ Chicago Style Steppers', 'description' => 'Brooklyn-based meetup teaching Chicago-style stepping (smooth partner dance to R&B), with classes and social dances.', 'base_url' => 'https://www.meetup.com/steppers-16/', 'urls' => ['https://www.meetup.com/steppers-16/events/']],

    // Writing
    ['name' => 'Shut Up & Write NYC', 'description' => 'NYC chapter of Shut Up & Write — silent writing sessions at cafes and coworking spaces across the city.', 'base_url' => 'https://www.meetup.com/shutupandwritenyc/', 'urls' => ['https://www.meetup.com/shutupandwritenyc/events/']],
    ['name' => 'Do the Write Thing', 'description' => 'Brooklyn writing group led by Rafi Zabor with regular workshops and writing sessions.', 'base_url' => 'https://www.meetup.com/Do-the-Write-Thing-with-Rafi-Zabor/', 'urls' => ['https://www.meetup.com/Do-the-Write-Thing-with-Rafi-Zabor/events/']],
    ['name' => 'Write Wing', 'description' => 'Brooklyn writing meetup with silent writing sessions and feedback workshops.', 'base_url' => 'https://www.meetup.com/writewing/', 'urls' => ['https://www.meetup.com/writewing/events/']],
    ['name' => 'Writing Under the Influence', 'description' => 'Ridgewood/Bushwick writing meetup blending writing sessions with informal social drinks at neighborhood bars.', 'base_url' => 'https://www.meetup.com/writing-under-influence/', 'urls' => ['https://www.meetup.com/writing-under-influence/events/']],

    // Art
    ['name' => 'NYC Art Meetup', 'description' => 'Large NYC art community with gallery visits, museum tours, and art-related social events across the city.', 'base_url' => 'https://www.meetup.com/NYC-Art-Meetup/', 'urls' => ['https://www.meetup.com/NYC-Art-Meetup/events/']],
    ['name' => 'Contemporary Arts NYC', 'description' => 'NYC contemporary art meetup focused on gallery openings, museum exhibitions, and artist talks.', 'base_url' => 'https://www.meetup.com/contemporary-art-lovers/', 'urls' => ['https://www.meetup.com/contemporary-art-lovers/events/']],
    ['name' => 'Brooklyn Figure Drawing', 'description' => 'Brooklyn figure drawing sessions with live models hosted at studios across the borough.', 'base_url' => 'https://www.meetup.com/bkfiguredrawing/', 'urls' => ['https://www.meetup.com/bkfiguredrawing/events/']],

    // Outdoors / hiking / cycling
    ['name' => 'The Wandering Soles', 'description' => 'NYC outdoor adventure group with hikes, weekend trips, and travel meetups in the tri-state area and beyond.', 'base_url' => 'https://www.meetup.com/wanderingsolesnyc/', 'urls' => ['https://www.meetup.com/wanderingsolesnyc/events/']],
    ['name' => 'Neverwinter Hiking & Cycling', 'description' => 'NYC hiking and cycling group with frequent free outdoor activities across the metro area, Hudson Valley, and Long Island.', 'base_url' => 'https://www.meetup.com/neverwinter-free-hiking-and-cycling/', 'urls' => ['https://www.meetup.com/neverwinter-free-hiking-and-cycling/events/']],
    ['name' => 'Brompton New York', 'description' => 'Folding-bike community with group rides and social cycling events across NYC.', 'base_url' => 'https://www.meetup.com/bromptonnyc/', 'urls' => ['https://www.meetup.com/bromptonnyc/events/']],

    // Books
    ['name' => 'Smutty Book Club', 'description' => 'NYC book club discussing romance and erotic fiction at bars and cafes around Manhattan.', 'base_url' => 'https://www.meetup.com/smutty-book-club/', 'urls' => ['https://www.meetup.com/smutty-book-club/events/']],
    ['name' => 'Brooklyn Smutty Book Club', 'description' => 'Brooklyn-based book club discussing romance and erotic fiction at bars and venues across the borough.', 'base_url' => 'https://www.meetup.com/brooklyn-smutty-book-club/', 'urls' => ['https://www.meetup.com/brooklyn-smutty-book-club/events/']],

    // LGBTQ
    ['name' => 'NYC Tri-State Bi+ Queer Meetup', 'description' => 'NYC tri-state area community for bisexual, queer, and questioning folks with regular socials, support groups, and mixers.', 'base_url' => 'https://www.meetup.com/bisexual-nyc/', 'urls' => ['https://www.meetup.com/bisexual-nyc/events/']],
    ['name' => 'Queer Social NYC', 'description' => 'NYC LGBTQ+ social group with curated events including dinners, gallery visits, mixers, and outings.', 'base_url' => 'https://www.meetup.com/queersocial/', 'urls' => ['https://www.meetup.com/queersocial/events/']],

    // Language exchange
    ['name' => 'Langroops NYC Language Exchange', 'description' => 'NYC language exchange meetup connecting learners of multiple languages at bars and cafes around the city.', 'base_url' => 'https://www.meetup.com/new-york-langroops-language-exchange/', 'urls' => ['https://www.meetup.com/new-york-langroops-language-exchange/events/']],
    ['name' => 'NYC Spanish/English Intercambio', 'description' => 'Spanish-English language exchange meetup with regular intercambio sessions at NYC bars and venues.', 'base_url' => 'https://www.meetup.com/the-new-spanish-english-language-exchange/', 'urls' => ['https://www.meetup.com/the-new-spanish-english-language-exchange/events/']],

    // Members-only groups whose venue is reliably stated in event titles — extract venue from title
    ['name' => 'Fun Times Comedy Meetup', 'description' => 'NYC comedy meetup hosting weekly stand-up and improv shows at established comedy clubs.', 'base_url' => 'https://www.meetup.com/FunCrowd/', 'urls' => ['https://www.meetup.com/FunCrowd/events/'], 'notes' => 'Members-only Meetup group: venue is hidden as "Location visible to members". Extract venue from event title (e.g., "Comedy Meetup at Comic Strip Live!" → Comic Strip Live). Skip events whose titles do not name a specific venue.'],

    // Added 2026-04-28
    [
        'name' => 'Sip & Play',
        'description' => 'Park Slope board game cafe and tabletop gaming bar hosting weekly chess club, MTG/Lorcana/Flesh and Blood card game nights, board game meetups, and family game time.',
        'base_url' => 'https://sipnplaynyc.com/',
        'urls' => ['https://sipnplaynyc.com/general-5'],
        'location' => 'Sip & Play',
        'notes' => 'Page lists recurring weekly events organized by day of week (e.g., "Monday: Park Slope Chess Club 6pm"). Extract each as a recurring event with day of week + start time + description. Skip biweekly Meetup-linked items if no specific date is given on the page.',
    ],

    // Added from borough-generic investigation (2026-04-28)
    // Crawlable: organizations with native dated event listings
    [
        'name' => 'Council of Peoples Organization',
        'description' => 'Brooklyn community organization in Midwood serving immigrant communities with food pantry, tech help, and community programming.',
        'base_url' => 'https://copo.org/',
        'urls' => ['https://copo.org/events/'],
        'location' => 'Council of Peoples Organization',
    ],
    [
        'name' => 'Christ Disciples International Ministries',
        'description' => 'Bedford Park Bronx church with multi-category programming including youth, adult, food distribution, and worship events.',
        'base_url' => 'https://christdisciples.org/',
        'urls' => ['https://christdisciples.org/events/'],
        'location' => 'Christ Disciples International Ministries',
    ],
    [
        'name' => 'LOOVE Labs',
        'description' => 'Williamsburg recording studio and music venue hosting concerts, listening parties, and experimental music performances.',
        'base_url' => 'https://theloove.com/',
        'urls' => ['https://theloove.com/pages/events'],
        'location' => 'Loove Labs',
    ],
    [
        'name' => 'Eastern Queens Alliance',
        'description' => 'Queens nonprofit focused on environmental justice and community programming, hosting workshops, film festivals, and nature events at the Idlewild Environmental Science Learning Center.',
        'base_url' => 'https://easternqueensalliance.org/',
        'urls' => ['https://easternqueensalliance.org/calendar/'],
        'location' => 'Idlewild Environmental Science Learning Center',
    ],
    [
        'name' => 'Castleton Hill Moravian Church',
        'description' => 'Staten Island Moravian church and community garden hosting worship, fellowship, and community garden events.',
        'base_url' => 'https://www.castletonhill.org/',
        'urls' => ['https://www.castletonhill.org/events/'],
        'location' => 'Castleton Hill Moravian Community Garden',
    ],
    [
        'name' => "St. Joseph's University - Long Island",
        'description' => 'Patchogue, Long Island campus of St. Joseph\'s University hosting public lectures, conferences, and ceremonies.',
        'base_url' => 'https://www.sjny.edu/long-island',
        'urls' => ['https://www.eventbrite.com/d/ny--patchogue/st-joseph%27s-university-new-york-long-island/'],
        'location' => "St. Joseph's University Patchogue",
    ],

    // Informational only — no crawlable event listings
    [
        'name' => 'Mysstic Rooms',
        'description' => 'Park Slope escape room company hosting themed escape experiences (Montauk Project, Ghost Light).',
        'base_url' => 'https://www.myssticrooms.com/',
        'location' => 'Mysstic Rooms',
    ],
    [
        'name' => 'Audible Story House',
        'description' => 'Audible-operated pop-up event space on the Bowery (May 2026) with panels, book clubs, and crafting events.',
        'base_url' => 'https://audiblestoryhouse.com/',
        'location' => 'Audible Story House',
    ],
    [
        'name' => 'one4one Sports Club & Lounge',
        'description' => 'Lower East Side sports bar and lounge for big-game watch parties.',
        'base_url' => 'https://www.one4onenyc.com/',
        'location' => 'one4one Sports Club & Lounge',
    ],
    [
        'name' => 'Rema Hort Mann Foundation',
        'description' => 'Tribeca-based foundation supporting emerging artists, hosting an annual gala and occasional open houses.',
        'base_url' => 'https://www.remahortmannfoundation.org/',
        'location' => 'Rema Hort Mann Fund',
    ],
    [
        'name' => "Mirelle's",
        'description' => 'Westbury, Long Island restaurant and ballroom with weekly Argentine tango practicas, salsa nights, and milongas.',
        'base_url' => 'https://mirellesrestaurant.com/',
        'location' => "Mirelle's",
    ],
    [
        'name' => 'Good+ Foundation',
        'description' => 'Family-focused nonprofit founded by Jessica Seinfeld with offices in the Garment District; hosts annual fundraising events.',
        'base_url' => 'https://goodplusfoundation.org/',
        'location' => 'Good+Foundation',
    ],
    [
        'name' => 'Team TLC NYC',
        'description' => 'Volunteer organization serving newly arrived immigrants, operating the Little Shop of Kindness and weekly Kindness Center.',
        'base_url' => 'https://www.ttlcnyc.org/',
        'location' => 'Team TLC NYC',
    ],
    [
        'name' => 'Encore Community Services',
        'description' => 'Times Square area nonprofit serving older adults with meals, social programs, and supportive housing.',
        'base_url' => 'https://www.encorenyc.org/',
        'location' => 'Encore Community Services',
    ],

    // Added from Dykes & Dolls / gayagenda.nyc cross-reference (2026-04-27)
    // Informational websites (no crawl) for queer/community venues
    [
        'name' => 'MADabolic Brooklyn',
        'description' => 'Strength and conditioning gym in Williamsburg with interval-based group classes.',
        'base_url' => 'https://madabolic.com/locations/brooklyn',
        'location' => 'MADabolic Brooklyn',
    ],
    [
        'name' => "Ray's",
        'description' => 'Lower East Side dive bar known as a queer-friendly hangout.',
        'base_url' => 'https://www.raysbarnyc.com/location/les/',
        'location' => "Ray's",
    ],
    [
        'name' => 'Superfine',
        'description' => 'DUMBO bar/restaurant with live music, art, and bluegrass brunch.',
        'base_url' => 'https://www.superfine.nyc/',
        'location' => 'Superfine',
    ],
    [
        'name' => 'Dayglow',
        'description' => 'Specialty coffee shop in Bushwick with rotating roasters.',
        'base_url' => 'https://dayglow.coffee/',
        'location' => 'Dayglow',
    ],
    [
        'name' => 'Cicchetti BK',
        'description' => 'Queer-owned Venetian wine bar in Bed-Stuy/Ocean Hill with weekly Thursgay aperitivo.',
        'base_url' => 'https://www.cicchettibk.com/',
        'location' => 'Cicchetti BK',
    ],
    [
        'name' => 'Sunset Stoop',
        'description' => 'Sunset Park bar and music venue with karaoke, salsa, and trivia.',
        'base_url' => 'https://www.sunsetstoop.com/',
        'location' => 'Sunset Stoop',
    ],
    [
        'name' => 'Lambda Lounge',
        'description' => 'Black-owned LGBTQ+ lounge in Harlem with neon-lit decor and signature vodka.',
        'base_url' => 'https://lambdaloungeny.com/',
        'location' => 'Lambda Lounge',
    ],
    [
        'name' => 'Loreley Beer Garden',
        'description' => 'Lower East Side German beer garden with a large outdoor space.',
        'base_url' => 'https://loreleynyc.com/',
        'location' => 'Loreley Beer Garden',
    ],
    [
        'name' => 'Paradise Factory',
        'description' => 'East Village performance venue hosting plays, readings, and experimental theater.',
        'base_url' => 'https://www.paradisefactorynyc.com/',
        'location' => 'Paradise Factory',
    ],
    [
        'name' => 'Fulton Grand',
        'description' => 'Clinton Hill neighborhood bar with a backyard and event calendar.',
        'base_url' => 'https://www.fultongrand.com/',
        'location' => 'Fulton Grand',
    ],
    [
        'name' => 'Shy Shy',
        'description' => 'Chelsea cocktail bar from the Jungle Bird team with botanical cocktails.',
        'base_url' => 'https://www.shyshynyc.com/',
        'location' => 'Shy Shy',
    ],
    [
        'name' => 'Winnie Said',
        'description' => 'Hamilton Heights beer bar hosting community mixers and events.',
        'base_url' => 'https://www.winniesaid.com/',
        'location' => 'Winnie Said',
    ],
    [
        'name' => 'Upsoul Center',
        'description' => 'Chelsea holistic wellness center with massage, reiki, sound healing, and workshops.',
        'base_url' => 'https://upsoulcenter.com/',
        'location' => 'Upsoul Center',
    ],
    [
        'name' => 'Ligaw',
        'description' => 'LES cocktail bar from World\'s Best Mixologist Katrina Sobredilla. French-Filipino drinks.',
        'base_url' => 'https://ligawnyc.com/',
        'location' => 'Ligaw',
    ],
    [
        'name' => '148 Frost',
        'description' => 'Williamsburg event space hosting music, burlesque, and performance art.',
        'base_url' => 'https://thirdtassel.com/venue/148-frost',
        'location' => '148 Frost Street',
    ],
    [
        'name' => 'My First Ex-Husband',
        'description' => 'Off-Broadway show adapted from true stories by Joy Behar (co-host of The View). Bold, comedic exploration of love, sex, and relationships with a rotating cast of stars from theatre, TV, and film. NYC run at MMAC Theatre; additional tour dates being announced.',
        'base_url' => 'https://www.myfirstexhusband.com',
        'urls' => ['https://www.myfirstexhusband.com/', 'https://www.myfirstexhusband.com/schedule'],
        'crawl_frequency' => 21,
        'location' => 'Manhattan Movement & Arts Center',
        'notes' => 'No upcoming dates listed yet (as of 2026-04-27) — page says "New Tour Dates Coming Soon". Low crawl frequency until events are posted. NYC performances at the MMAC Theatre (248 W 60th St). Squarespace site.',
    ],
    // Added from BetaNYC civictech newsletter source-investigation (2026-04-27)
    [
        'name' => 'Data Vandals',
        'description' => 'Art collective running a data-art kiosk on the downtown 6 train platform at 51st & Lexington. Open every Sunday 2-6pm with rotating exhibitions, talks, and music performances. Featured as BetaNYC\'s Public Interest Technologist of the Month for April 2026.',
        'base_url' => 'https://datavandals.com',
        'urls' => ['https://datavandals.com/'],
        'crawl_frequency' => 14,
        'location' => 'Data Vandals Newsstand',
        'notes' => 'Homepage has an "Upcoming" section listing Sunday-newsstand recurring programming and special events. Only include NYC events — they also list LA programming that should be excluded.',
    ],
    [
        'name' => 'NYCxDESIGN Festival',
        'description' => 'Annual NYC design festival (May 14-20, 2026) featuring 250+ events across the city — talks, exhibitions, tours, parties, salons. Programming spans all 5 boroughs and many design disciplines.',
        'base_url' => 'https://nycxdesign.org',
        'urls' => ['https://nycxdesign.org/festival-calendar'],
        'crawl_frequency' => 7,
        'source_type' => 'aggregator',
        'notes' => 'Festival aggregator — events at varying venues across NYC. Calendar is JS-rendered; may need js_code to wait for events to load.',
    ],
    [
        'name' => 'MakeShift',
        'description' => 'Convening for designers, technologists, researchers, and advocates focused on accountable, transparent technology design. Inaugural MakeShift 2026: Accountable Tech by Design takes place May 20-21 at SVA in Chelsea. Hosted by Helpful Places, Superbloom Design, and SVA MFA Interaction Design.',
        'base_url' => 'https://makeshift2026.dtpr.io',
        'urls' => ['https://makeshift2026.dtpr.io/'],
        'crawl_frequency' => 30,
        'location' => 'SVA MFA Interaction Design',
        'notes' => 'Single-event landing page — keeps the May 20-21 MakeShift 2026 event details current. Low frequency.',
    ],
    [
        'name' => 'It\'s Happening at Hunter',
        'description' => 'Hunter College\'s curated public events series — talks, lectures, performances, and special events open to the community across Hunter campuses (main campus, Roosevelt House, Kaye Playhouse, Brookdale).',
        'base_url' => 'https://www.hunter.cuny.edu/series/its-happening-at-hunter/',
        'urls' => ['https://www.hunter.cuny.edu/series/its-happening-at-hunter/'],
        'crawl_frequency' => 7,
        'notes' => 'Hunter College curated public events series. Events take place at multiple Hunter locations — let AI pick up sublocation from each event. Uses The Events Calendar (Tribe Events) plugin.',
    ],
    // Added from BetaNYC civictech newsletter cross-reference (2026-04-27)
    [
        'name' => 'Columbia Preparedness & Recovery Institute',
        'description' => 'Columbia University institute (formerly Pandemic Response Institute) hosting forums, hackathons, workshops, and panels on public health preparedness, emergency response, and hyperlocal resilience. Events at The Forum at Columbia, online, and other venues.',
        'base_url' => 'https://pandemicresponse.columbia.edu',
        'urls' => ['https://pandemicresponse.columbia.edu/events/'],
        'crawl_frequency' => 14,
        'location' => 'The Forum at Columbia University',
        'notes' => 'Producer hosting events at multiple venues — primary location is The Forum at Columbia (601 W 125th St), but also hosts online and at Interchurch Center.',
    ],
    [
        'name' => 'Pilot City',
        'description' => 'Non-profit initiative of Renaissance Philanthropy connecting NYC government agencies with university expertise and civic talent. Hosts the annual Pitchfest at Pfizer Auditorium, NYU Tandon.',
        'base_url' => 'https://www.eventbrite.com/o/121208799652',
        'urls' => ['https://www.eventbrite.com/o/121208799652'],
        'crawl_frequency' => 30,
        'location' => 'Pfizer Auditorium at NYU Tandon',
        'notes' => 'Eventbrite organizer page. Annual Pitchfest event — low volume.',
    ],
    [
        'name' => 'CUSP at NYU Tandon',
        'description' => 'Center for Urban Science and Progress at NYU Tandon — events on urban informatics, data science, and applied research, posted on Luma.',
        'base_url' => 'https://luma.com/user/CUSP_NYU_Tandon',
        'urls' => ['https://luma.com/user/CUSP_NYU_Tandon'],
        'crawl_frequency' => 7,
    ],
    // Added from Luma NYC discover scan (2026-04-27)
    [
        'name' => 'Luma NYC Discover',
        'description' => 'Luma\'s curated feed of upcoming events in NYC. Aggregator surfacing events from many organizers across the city.',
        'base_url' => 'https://luma.com/nyc',
        'urls' => ['https://luma.com/nyc'],
        'crawl_frequency' => 3,
        'source_type' => 'aggregator',
        'notes' => 'Aggregator — events from many distinct organizers; no single location link.',
    ],
    [
        'name' => 'This Week in Fintech',
        'description' => 'Fintech newsletter and community hosting frequent industry meetups, panels, and networking events across NYC.',
        'base_url' => 'https://luma.com/twif',
        'urls' => ['https://luma.com/twif'],
        'crawl_frequency' => 7,
    ],
    [
        'name' => 'Lit Club NYC',
        'description' => 'NYC literary community hosting book clubs, readings, and writer meetups via Luma.',
        'base_url' => 'https://luma.com/LitClubNYC',
        'urls' => ['https://luma.com/LitClubNYC'],
        'crawl_frequency' => 14,
    ],
    [
        'name' => 'NYC B2B',
        'description' => 'B2B/SaaS networking community hosting founder, sales, and operator events in NYC.',
        'base_url' => 'https://luma.com/nycb2b',
        'urls' => ['https://luma.com/nycb2b'],
        'crawl_frequency' => 14,
    ],
    [
        'name' => 'Pulse NYC',
        'description' => 'NYC tech and startup community hosting networking events, demos, and panels via Luma.',
        'base_url' => 'https://luma.com/pulsenyc',
        'urls' => ['https://luma.com/pulsenyc'],
        'crawl_frequency' => 14,
    ],
    [
        'name' => 'All Tech Is Human',
        'description' => 'Nonprofit hosting events on responsible tech, AI ethics, and tech-policy intersections, often in NYC.',
        'base_url' => 'https://luma.com/AllTechIsHuman',
        'urls' => ['https://luma.com/AllTechIsHuman'],
        'crawl_frequency' => 14,
    ],
    [
        'name' => 'Endless Frontier Labs',
        'description' => 'NYU Stern startup accelerator hosting demo days, founder talks, and investor events.',
        'base_url' => 'https://luma.com/EndlessFrontier',
        'urls' => ['https://luma.com/EndlessFrontier'],
        'crawl_frequency' => 21,
    ],
    [
        'name' => 'NYU Stern Fubon Center',
        'description' => 'NYU Stern\'s Fubon Center for Technology, Business and Innovation hosting finance, tech, and business academic events.',
        'base_url' => 'https://luma.com/nyusternfubon',
        'urls' => ['https://luma.com/nyusternfubon'],
        'crawl_frequency' => 14,
    ],
    // Added from Luma NYC discover deep-dive — calendar slugs (2026-04-27)
    // Tech / AI
    [
        'name' => 'AI Engineers - NY',
        'description' => 'AI/ML community hosting talks, demos, and devs+drinks meetups in NYC.',
        'base_url' => 'https://luma.com/nyaiengineers',
        'urls' => ['https://luma.com/nyaiengineers'],
        'crawl_frequency' => 14,
    ],
    [
        'name' => 'Agentics NYC',
        'description' => 'NYC community focused on AI agents, agentic systems, and applied AI engineering.',
        'base_url' => 'https://luma.com/agenticsnyc',
        'urls' => ['https://luma.com/agenticsnyc'],
        'crawl_frequency' => 14,
    ],
    [
        'name' => 'LiveKit',
        'description' => 'Voice AI infrastructure company hosting NYC events on real-time AI, voice agents, and developer meetups.',
        'base_url' => 'https://luma.com/livekit',
        'urls' => ['https://luma.com/livekit'],
        'crawl_frequency' => 21,
    ],
    [
        'name' => 'Runway',
        'description' => 'AI video and creative tools company hosting NYC events including its annual AI Festival.',
        'base_url' => 'https://luma.com/runway',
        'urls' => ['https://luma.com/runway'],
        'crawl_frequency' => 21,
    ],
    [
        'name' => 'ODSC AI',
        'description' => 'Open Data Science Conference community hosting AI and data science events in NYC.',
        'base_url' => 'https://luma.com/odsc',
        'urls' => ['https://luma.com/odsc'],
        'crawl_frequency' => 21,
    ],
    [
        'name' => 'South Park Commons',
        'description' => 'Tech/founder community hosting demos, talks, and meetups in NYC.',
        'base_url' => 'https://luma.com/southparkcommons-events',
        'urls' => ['https://luma.com/southparkcommons-events'],
        'crawl_frequency' => 14,
    ],
    [
        'name' => 'NY Hardware Meetup',
        'description' => 'NYC hardware engineering and product design meetup.',
        'base_url' => 'https://luma.com/ny-hardware-meetup',
        'urls' => ['https://luma.com/ny-hardware-meetup'],
        'crawl_frequency' => 21,
    ],
    // Finance / Startups
    [
        'name' => 'NYC B2B Calendar',
        'description' => 'NYC B2B startup events calendar — official Luma calendar with all events from the host.',
        'base_url' => 'https://luma.com/b2bnyc',
        'urls' => ['https://luma.com/b2bnyc'],
        'crawl_frequency' => 14,
    ],
    [
        'name' => 'FirstMark Capital',
        'description' => 'NYC venture capital firm hosting Data Driven NYC and other founder/investor events.',
        'base_url' => 'https://luma.com/firstmarkcap',
        'urls' => ['https://luma.com/firstmarkcap'],
        'crawl_frequency' => 14,
    ],
    [
        'name' => 'Fintech Is Femme',
        'description' => 'Women in fintech community hosting NYC events including New York Fintech Week programming.',
        'base_url' => 'https://luma.com/fintechisfemme',
        'urls' => ['https://luma.com/fintechisfemme'],
        'crawl_frequency' => 14,
    ],
    [
        'name' => 'The Shortlist NY',
        'description' => 'Curated, application-only monthly founder showcase connecting early-stage founders with investors in NYC.',
        'base_url' => 'https://luma.com/shortlist',
        'urls' => ['https://luma.com/shortlist'],
        'crawl_frequency' => 21,
    ],
    // Art / Design / Culture
    // (ARTECHOUSE NYC's Luma calendar added as 2nd URL on existing website id 1166)
    [
        'name' => 'Brooklyn Product Design',
        'description' => 'Brooklyn product design community hosting talks and meetups for designers.',
        'base_url' => 'https://luma.com/bkproductdesign',
        'urls' => ['https://luma.com/bkproductdesign'],
        'crawl_frequency' => 21,
    ],
    [
        'name' => 'arts crafts interface-design club',
        'description' => 'Brooklyn-based interface design and crafts community hosting talks and workshops.',
        'base_url' => 'https://luma.com/aci-d.club',
        'urls' => ['https://luma.com/aci-d.club'],
        'crawl_frequency' => 21,
    ],
    [
        'name' => 'icon new york',
        'description' => 'NYC design community hosting design week kickoffs and design-focused events.',
        'base_url' => 'https://luma.com/icon.ny',
        'urls' => ['https://luma.com/icon.ny'],
        'crawl_frequency' => 21,
    ],
    [
        'name' => 'Index Chinatown',
        'description' => 'Cultural space in Chinatown hosting launches, parties, and community events.',
        'base_url' => 'https://luma.com/index_space',
        'urls' => ['https://luma.com/index_space'],
        'crawl_frequency' => 14,
    ],
    [
        'name' => 'Asian Creative Foundation',
        'description' => 'NYC community organizing events on creativity, social impact, and AI for Asian American communities.',
        'base_url' => 'https://luma.com/asaincreativefoundation',
        'urls' => ['https://luma.com/asaincreativefoundation'],
        'crawl_frequency' => 21,
    ],
    [
        'name' => 'Rema Hort Mann Fund',
        'description' => 'NYC art philanthropy organization supporting emerging artists, hosting fundraisers and exhibitions.',
        'base_url' => 'https://luma.com/RHMF',
        'urls' => ['https://luma.com/RHMF'],
        'crawl_frequency' => 30,
    ],
    // Social / Community
    [
        'name' => 'Girls Who Meet',
        'description' => 'NYC women\'s networking community hosting meetups and social gatherings.',
        'base_url' => 'https://luma.com/girlswhomeet',
        'urls' => ['https://luma.com/girlswhomeet'],
        'crawl_frequency' => 14,
    ],
    [
        'name' => 'NYC Backgammon Club',
        'description' => 'NYC backgammon community hosting recurring play nights at venues like ModernHaus SoHo.',
        'base_url' => 'https://luma.com/nycbackgammonclub',
        'urls' => ['https://luma.com/nycbackgammonclub'],
        'crawl_frequency' => 14,
    ],
    [
        'name' => 'NYC Pizza Crawl',
        'description' => 'NYC pizza tour group hosting themed pizza crawls across the city.',
        'base_url' => 'https://luma.com/newyorkcitypizzacrawl',
        'urls' => ['https://luma.com/newyorkcitypizzacrawl'],
        'crawl_frequency' => 21,
    ],
    [
        'name' => 'sudocute',
        'description' => 'NYC sudoku-meets-cute social events combining puzzle solving with meeting people.',
        'base_url' => 'https://luma.com/sudocute',
        'urls' => ['https://luma.com/sudocute'],
        'crawl_frequency' => 21,
    ],
    [
        'name' => 'soft(spaces)',
        'description' => 'NYC community hosting wellness, social, and house party events.',
        'base_url' => 'https://luma.com/softspaces',
        'urls' => ['https://luma.com/softspaces'],
        'crawl_frequency' => 21,
    ],
    [
        'name' => 'craftnook',
        'description' => 'NYC craft community hosting craft crawls and workshops for stationery and craft lovers.',
        'base_url' => 'https://luma.com/craftnook',
        'urls' => ['https://luma.com/craftnook'],
        'crawl_frequency' => 21,
    ],
    [
        'name' => 'Idealist Events',
        'description' => 'Nonprofit social-good community hosting NYC events including sunrise walks and meetups for changemakers.',
        'base_url' => 'https://luma.com/Idealist',
        'urls' => ['https://luma.com/Idealist'],
        'crawl_frequency' => 14,
    ],
    [
        'name' => 'Manhattan Tennis Association',
        'description' => 'NYC tennis association hosting recreational tennis events and tournament watch parties.',
        'base_url' => 'https://luma.com/manhattantennisassociation',
        'urls' => ['https://luma.com/manhattantennisassociation'],
        'crawl_frequency' => 21,
    ],
    [
        'name' => 'NYC Running Events Calendar',
        'description' => 'Brooklyn-based NYC running events calendar covering races, registrations, and run club meetups.',
        'base_url' => 'https://luma.com/bkrun',
        'urls' => ['https://luma.com/bkrun'],
        'crawl_frequency' => 14,
    ],
    [
        'name' => 'Masala Milers',
        'description' => 'NYC South Asian running community hosting themed runs (e.g., Rupee Beer 5K).',
        'base_url' => 'https://luma.com/Masala',
        'urls' => ['https://luma.com/Masala'],
        'crawl_frequency' => 30,
    ],
    [
        'name' => 'Journey Clinical',
        'description' => 'NYC psychedelic therapy community hosting panels and educational events on the future of psychedelics.',
        'base_url' => 'https://luma.com/journeyclinical',
        'urls' => ['https://luma.com/journeyclinical'],
        'crawl_frequency' => 30,
    ],
    [
        'name' => 'NY Comply',
        'description' => 'NYC fintech compliance community hosting events on applied AI, regulation, and fintech operations.',
        'base_url' => 'https://luma.com/nycomply',
        'urls' => ['https://luma.com/nycomply'],
        'crawl_frequency' => 30,
    ],
    // Added from City Happenings cross-reference (2026-04-27)
    [
        'name' => 'Orchestra Q',
        'description' => 'Producer/ensemble that stages live orchestral performances reimagined as DJ-style sets, blending classical composers with sampling, looping, and DJ transitions. Events take place at venues like SculptureCenter.',
        'base_url' => 'https://www.orchestraq.com',
        'urls' => ['https://www.orchestraq.com/events'],
        'crawl_frequency' => 21,
        'notes' => 'Producer — events happen at varying venues. No single location link.',
    ],
    [
        'name' => 'PEN World Voices Festival',
        'description' => 'Annual literary festival from PEN America bringing 140+ writers from 40+ countries together for talks, readings, panels, and performances at venues across NYC.',
        'base_url' => 'https://worldvoices.pen.org',
        'urls' => [
            'https://worldvoices.pen.org/events/?_event_location=nyc',
            'https://worldvoices.pen.org/events/?_event_location=nyc&_paged=2',
            'https://worldvoices.pen.org/events/?_event_location=nyc&_paged=3',
            'https://worldvoices.pen.org/events/?_event_location=nyc&_paged=4',
            'https://worldvoices.pen.org/events/?_event_location=nyc&_paged=5',
        ],
        'crawl_frequency' => 14,
        'notes' => 'Festival aggregator — events at varying NYC venues (The Center, AIA, Strand, Goethe-Institut, Judson Memorial Church, etc.). No single location link.',
    ],
    [
        'name' => 'ArtsClub',
        'description' => 'East Village art studio hosting weekly studio sessions, gallery crawls (LES, Chelsea), wellness sessions, and technique workshops.',
        'base_url' => 'https://www.artsclubstudios.com',
        'urls' => ['https://www.artsclubstudios.com/east-village-events'],
        'crawl_frequency' => 7,
        'location' => 'ArtsClub',
        'notes' => 'Producer hosting events at own East Village space plus offsite gallery crawls (Ki Smith Gallery, Chelsea galleries).',
    ],
    [
        'name' => 'The Gem Saloon',
        'description' => 'Murray Hill saloon hosting an annual Kentucky Derby Party plus weekend DJ nights. Event details posted in a homepage popup.',
        'base_url' => 'https://www.thegemsaloonnyc.com',
        'urls' => ['https://www.thegemsaloonnyc.com/'],
        'crawl_frequency' => 30,
        'location' => 'The Gem Saloon',
        'notes' => 'Events appear in homepage popup/notice. Low frequency since events are sporadic (annual Derby Party, etc.).',
    ],
    [
        'name' => 'Taste of Science NYC',
        'description' => 'NYC chapter of Taste of Science, a series of accessible science talks and field trips at bars, parks, and casual venues across the city.',
        'base_url' => 'https://nyc.tasteofscience.org',
        'urls' => ['https://www.tickettailor.com/events/tasteofsciencenewyork'],
        'crawl_frequency' => 14,
        'notes' => 'Producer — events happen at varying venues (Somethin\' Else, Ryan\'s Daughter, Central Park monuments). No single location link.',
    ],
    [
        'name' => "Annie's Blue Ribbon General Store",
        'description' => 'General store in Park Slope, Brooklyn hosting community events, classes (Mah Jongg, craft workshops), and happy hours in its retail space.',
        'base_url' => 'https://blueribbongeneralstore.com',
        'urls' => ['https://blueribbongeneralstore.com/pages/events'],
        'crawl_frequency' => 7,
        'location' => "Annie's Blue Ribbon General Store",
    ],
    // Added from City Happenings cross-reference (2026-04-20)
    [
        'name' => 'Manhattan Vintage',
        'description' => 'Traveling vintage fashion show hosting multi-day events and special editions at venues across NYC (Metropolitan Pavilion, Ukrainian Institute) and other cities (Hamptons, Miami, Austin).',
        'base_url' => 'https://manhattanvintage.com',
        'urls' => ['https://manhattanvintage.com/pages/vintage-shows'],
        'crawl_frequency' => 14,
        'notes' => 'Traveling show — events happen at different venues each edition. No single location link. Calendar page lists all upcoming editions with dates and venues.',
    ],
    // Venues from TechnoQueers cross-reference (2026-04-10)
    [
        'name' => 'Musica Club NYC',
        'base_url' => 'https://musicanewyork.net/',
        'urls' => ['https://www.songkick.com/venues/4430406-musica-club-nyc'],
        'crawl_frequency' => 14,
        'location' => 'Musica Club NYC',
    ],
    [
        'name' => 'Silence Please',
        'base_url' => 'https://www.silencepleasenyc.com',
        'urls' => ['https://www.songkick.com/venues/4584429-silence-please'],
        'crawl_frequency' => 14,
        'location' => 'Silence Please',
    ],
    [
        'name' => 'Happyfun Hideaway',
        'base_url' => 'https://www.happyfunhideaway.com',
        'urls' => ['https://www.songkick.com/venues/3371064-happyfun-hideaway'],
        'crawl_frequency' => 14,
        'location' => 'Happyfun Hideaway',
    ],
    [
        'name' => 'MIXI',
        'description' => 'Adelphi University research center in Downtown Brooklyn exploring STEM and the imagination through lectures, reading groups, workshops, and conferences.',
        'base_url' => 'https://mixi.nyc',
        'urls' => ['https://mixi.nyc/events/'],
        'crawl_frequency' => 14,
        'location' => 'MIXI',
    ],
    // Fort Defiance 250 added on 2026-04-06 - see git history
    // NJ cultural sites added on 2026-04-07
    [
        'name' => 'Palisades Interstate Park Conservancy',
        'base_url' => 'https://www.palisadesparks.org',
        'urls' => ['https://www.palisadesparks.org/events'],
        'crawl_frequency' => 30,
        'location' => 'Palisades Interstate Park',
        'notes' => 'Palisades parks conservancy events. Low volume (2-3 events/year) — annual gala, half marathon, and First Day Hike. Squarespace site.',
    ],
    [
        'name' => 'Mayo Performing Arts Center',
        'base_url' => 'https://www.mayoarts.org',
        'urls' => ['https://www.mayoarts.org/events/'],
        'crawl_frequency' => 7,
        'location' => 'Mayo Performing Arts Center',
        'notes' => 'Major performing arts center in Morristown, NJ. 70+ events including concerts, comedy, theater, and family shows. Hybrid static HTML with JS filtering.',
    ],
    [
        'name' => 'NJ Symphony',
        'base_url' => 'https://www.njsymphony.org',
        'urls' => ['https://www.njsymphony.org/events'],
        'crawl_frequency' => 14,
        'notes' => 'NJ Symphony Orchestra events at multiple venues across NJ (NJPAC Newark, Count Basie Center Red Bank, Richardson Auditorium Princeton, Mayo PAC Morristown). Extract each event with its specific venue.',
    ],
    [
        'name' => 'Mile Square Theatre',
        'base_url' => 'https://www.milesquaretheatre.org',
        'urls' => ['https://www.milesquaretheatre.org/shows-events'],
        'crawl_frequency' => 14,
        'location' => 'Mile Square Theatre',
        'notes' => 'Professional theater in Hoboken, NJ. Plays, readings, open mics, and comedy. Squarespace site with JSON-LD structured data.',
    ],
    [
        'name' => 'Whippany Railway Museum',
        'base_url' => 'https://www.whippanyrailwaymuseum.net',
        'urls' => ['https://www.whippanyrailwaymuseum.net/'],
        'crawl_frequency' => 30,
        'location' => 'Whippany Railway Museum',
        'notes' => 'Railway museum in Whippany, NJ. Seasonal train excursions (May-Oct) and special events. Low volume (~6 events/year). Static HTML WordPress site.',
    ],
    [
        'name' => 'Bergen County Players',
        'base_url' => 'https://www.bcplayers.org',
        'urls' => ['https://www.bcplayers.org/'],
        'crawl_frequency' => 30,
        'location' => 'Little Firehouse Theatre',
        'notes' => 'Community theater in Oradell, Bergen County NJ. ~6 shows per season. WordPress site.',
    ],
    // Essex County Parks, Union County Parks, Visit Hudson County added on 2026-04-06
    [
        'name' => 'BCCLS Libraries',
        'base_url' => 'https://bccls.libcal.com',
        'urls' => ['https://bccls.libcal.com/calendar/?cid=-1&t=m'],
        'crawl_frequency' => 3,
        'notes' => 'Bergen County Cooperative Library System — 77+ member libraries across Bergen, Passaic, and Essex counties. Calendar uses LibCal (SpringShare). Events at individual libraries — extract each with its specific library name as the location. High volume (100+ events/day).',
    ],
    [
        'name' => 'NJ State Parks Events',
        'base_url' => 'https://dep.nj.gov',
        'urls' => ['https://dep.nj.gov/events/'],
        'crawl_frequency' => 7,
        'notes' => 'NJ Dept of Environmental Protection events across all state parks. Static HTML with Tribe Events Calendar. Very large page (360+ events). Events at various state parks — extract each with its park name. Focus on parks within the NYC metro area: Liberty State Park, Cheesequake, Ringwood, High Point, Ramapo, Wawayanda, etc. Skip events at parks far from NYC (south of I-195).',
    ],
    [
        'name' => 'Morris Museum',
        'base_url' => 'https://morrismuseum.org',
        'urls' => ['https://morrismuseum.org/events/'],
        'crawl_frequency' => 14,
        'location' => 'Morris Museum',
        'notes' => 'Museum in Morristown, NJ with concerts, film screenings, workshops, and outdoor summer concert series (Back Deck).',
    ],
    [
        'name' => 'Grounds for Sculpture',
        'base_url' => 'https://www.groundsforsculpture.org',
        'urls' => ['https://www.groundsforsculpture.org/calendar/'],
        'crawl_frequency' => 14,
        'location' => 'Grounds for Sculpture',
        'notes' => 'Sculpture park and museum in Hamilton, NJ. Events include art workshops, wellness programs, wine tastings, family activities, and garden tours.',
    ],
    [
        'name' => 'NJ Botanical Garden',
        'base_url' => 'https://njbg.org',
        'urls' => ['https://njbg.org/events/'],
        'crawl_frequency' => 14,
        'location' => 'New Jersey Botanical Garden',
        'notes' => 'Botanical garden at Skylands in Ringwood, NJ (Passaic County). Events include nature walks, workshops, Earth Day celebrations, and garden tours. JS-rendered page — may need delay or js_code.',
    ],
    [
        'name' => 'NY-NJ Trail Conference',
        'base_url' => 'https://www.nynjtc.org',
        'urls' => ['https://www.nynjtc.org/calendar'],
        'crawl_frequency' => 7,
        'notes' => 'Trail maintenance, volunteer work trips, hikes, and workshops across NY-NJ Highlands, Harriman State Park, and the Appalachian Trail. Events at various trailheads and parks — extract each with its specific location.',
    ],
    [
        'name' => 'Visit Hudson County',
        'base_url' => 'https://www.visithudson.org',
        'urls' => ['https://www.visithudson.org/calendar/'],
        'crawl_frequency' => 7,
        'notes' => 'Hudson County tourism board event calendar. Uses imgoingcalendar.com JS widget. Events at various venues across Jersey City, Hoboken, Bayonne, and other Hudson County towns. Each event has a specific venue — extract with location name and address.',
    ],
    [
        'name' => 'Union County Parks',
        'base_url' => 'https://ucnj.org',
        'urls' => ['https://ucnj.org/calendar/'],
        'crawl_frequency' => 7,
        'notes' => 'Union County NJ parks and recreation. Calendar page is static HTML with community events at various county parks including Watchung Reservation, Trailside Nature Center, Warinanco Park, etc. Events include nature walks, art workshops, festivals, and community programs.',
    ],
    [
        'name' => 'Essex County Parks',
        'base_url' => 'https://essexcountyparks.org',
        'urls' => [
            'https://essexcountyparks.org/',
            'https://essexcountyparks.org/parks/branch-brook-park/calendar/bloomfest',
        ],
        'crawl_frequency' => 7,
        'location' => 'Branch Brook Park',
        'notes' => 'Essex County NJ parks system. Events at Branch Brook Park (cherry blossom festival, Bloomfest), Turtle Back Zoo, South Mountain, Codey Arena, etc. Homepage lists upcoming events. Individual event pages at /calendar/event/... have full details. Events happen at various parks — extract each event with its specific park/location name.',
    ],
    [
        'name' => 'Vine Wine',
        'base_url' => 'https://www.vine-wine.com',
        'urls' => ['https://www.vine-wine.com/classes'],
        'crawl_frequency' => 7,
        'location' => 'Vine Wine',
        'notes' => 'Wine and spirits shop in Williamsburg offering wine classes and tastings. Classes page lists upcoming sessions.',
    ],
    [
        'name' => 'MetLife Stadium',
        'base_url' => 'https://www.metlifestadium.com',
        'urls' => ['https://www.metlifestadium.com/events'],
        'crawl_frequency' => 7,
        'location' => 'MetLife Stadium',
        'notes' => 'Major stadium in East Rutherford, NJ. Home of Giants/Jets. Hosts concerts and FIFA World Cup 2026.',
    ],
    [
        'name' => 'Governors Ball Music Festival',
        'base_url' => 'https://www.governorsballmusicfestival.com',
        'urls' => ['https://www.governorsballmusicfestival.com/'],
        'crawl_frequency' => 14,
        'location' => 'Flushing Meadows Corona Park',
        'notes' => 'Annual 3-day music festival in Queens. June 5-7, 2026. Extract the festival dates and any announced lineup/headliners as a single event.',
    ],
    [
        'name' => 'NYC Pride',
        'base_url' => 'https://www.nycpride.org',
        'urls' => ['https://www.nycpride.org/events'],
        'crawl_frequency' => 14,
        'notes' => 'NYC Pride March and Festival events. Multiple events at various locations during Pride month (June). Extract each event separately with its specific location.',
    ],
    [
        'name' => 'NY International Auto Show',
        'base_url' => 'https://www.autoshowny.com',
        'urls' => ['https://www.autoshowny.com/'],
        'crawl_frequency' => 14,
        'location' => 'Javits Center',
        'notes' => 'Annual auto show at the Javits Center, typically in April. Extract the show dates as a single event.',
    ],
    [
        'name' => 'Petzel Gallery',
        'base_url' => 'https://www.petzel.com',
        'urls' => ['https://petzel.com/exhibitions'],
        'crawl_frequency' => 14,
        'location' => 'Petzel Gallery',
        'notes' => 'Contemporary art gallery in Chelsea. Exhibitions page lists current and upcoming shows.',
    ],
    [
        'name' => 'Tanya Bonakdar Gallery',
        'base_url' => 'https://tanyabonakdargallery.com',
        'urls' => ['https://tanyabonakdargallery.com/exhibitions'],
        'crawl_frequency' => 14,
        'location' => 'Tanya Bonakdar Gallery',
        'notes' => 'Contemporary art gallery in Chelsea. Exhibitions page lists current and upcoming shows with dates.',
    ],
    [
        'name' => 'White Cube',
        'base_url' => 'https://www.whitecube.com',
        'urls' => ['https://www.whitecube.com/exhibitions/new-york'],
        'crawl_frequency' => 14,
        'location' => 'White Cube',
        'notes' => 'International gallery, New York location on Madison Ave. Only extract exhibitions at the New York location.',
    ],
    [
        'name' => 'UBS Arena',
        'base_url' => 'https://ubsarena.com',
        'urls' => ['https://ubsarena.com/events/'],
        'crawl_frequency' => 7,
        'location' => 'UBS Arena',
        'notes' => 'Multi-purpose arena in Elmont, NY. Home of NY Islanders. Hosts concerts and events.',
    ],
    // Brooklyn Bookstore Crawl 2026 participating bookstores (2026-04-20)
    [
        'name' => 'Adanne Bookshop',
        'description' => 'Black-owned independent bookshop in Bed-Stuy hosting author readings, workshops, and community literary events.',
        'base_url' => 'https://adanne.co',
        'urls' => ['https://www.eventbrite.com/o/adanne-33506248345'],
        'location' => 'Adanne Bookshop',
        'notes' => 'Events hosted on Eventbrite. Homepage links to their Eventbrite organization page for workshops.',
    ],
    [
        'name' => 'BEM | books & more',
        'description' => 'Independent Bed-Stuy bookshop and cultural space showcasing books, art, and design by Black creators alongside community programming.',
        'base_url' => 'https://bembrooklyn.com',
        'location' => 'BEM | books & more',
        'notes' => 'No visible events page on homepage. Check social media for programming. Informational only for now.',
    ],
    [
        'name' => 'Cafe con Libros',
        'description' => 'Intersectional feminist bookstore and cafe in Crown Heights hosting book clubs, author talks, and community gatherings.',
        'base_url' => 'https://cafeconlibrosbk.com',
        'urls' => ['https://www.cafeconlibrosbk.com/events'],
        'location' => 'Cafe con Libros',
    ],
    [
        'name' => 'Mil Mundos Books',
        'description' => 'Bilingual (Spanish/English) independent bookstore in Bushwick hosting readings, workshops, and Latinx literary and cultural events.',
        'base_url' => 'https://milmundosbooks.com',
        'urls' => ['https://milmundosbooks.com/pages/events'],
        'location' => 'Mil Mundos Books',
        'notes' => 'Shopify site. Events page may be thin — crawl and verify. Consider social media fallback if empty.',
    ],
    [
        'name' => 'Freebird Books',
        'description' => 'Used bookstore on the Columbia Waterfront specializing in New York City titles and hosting occasional readings and community events.',
        'base_url' => 'https://freebirdbooks.com',
        'urls' => ['https://www.freebirdbooks.com/freebirdbooksnews.html'],
        'crawl_frequency' => 30,
        'location' => 'Freebird Books',
        'notes' => 'News/announcements page mostly covers monthly Books Through Bars drives and store closures. Low event volume.',
    ],
    [
        'name' => 'Powerhouse Arena',
        'description' => 'DUMBO flagship bookstore and event space hosting author readings, book launches, panel discussions, and literary parties.',
        'base_url' => 'https://powerhousearena.com',
        'urls' => ['https://powerhousearena.com/events/'],
        'location' => 'Powerhouse Arena',
        'notes' => 'Some events use external Eventbrite links. High volume of author events.',
    ],
    [
        'name' => 'Black Spring Books',
        'description' => 'Williamsburg independent bookstore hosting author readings, film screenings, magazine launches, reading series, and themed literary socials.',
        'base_url' => 'https://blackspringbookstore.com',
        'urls' => ['https://blackspringbookstore.com/events'],
        'location' => 'Black Spring Books',
    ],
    [
        'name' => 'leaves used bookstore',
        'description' => 'Greenpoint used bookstore offering curated secondhand titles and occasional community literary events.',
        'base_url' => 'https://leavesbookstore.com',
        'location' => 'leaves used bookstore',
        'notes' => 'Site blocks automated fetches (406). Informational only — may need manual investigation to find events URL.',
    ],
    [
        'name' => 'The Little Bookshop',
        'description' => 'Small independent bookshop on Bushwick Ave hosting community book events and readings.',
        'base_url' => 'https://thelittlebookshopbk.com',
        'location' => 'The Little Bookshop',
        'notes' => 'Site uses Linktree (linktr.ee/thelittlebookshopbk) for outbound links. No dedicated events page. Informational only.',
    ],
    [
        'name' => "Quimby's Bookstore NYC",
        'description' => 'Williamsburg outpost of the legendary Chicago zine and underground comics shop, hosting readings, zine launches, and alternative literary events.',
        'base_url' => 'https://quimbysnyc.com',
        'location' => "Quimby's Bookstore NYC",
        'notes' => 'Single-page website with social media links only. Events announced on Instagram/Facebook. Informational only.',
    ],
    // 826NYC website already exists (id 1850) — linked to location 3513
    [
        'name' => 'Love & Legends Books',
        'description' => 'Prospect Heights romance-focused independent bookstore hosting book clubs, author signings, and themed reader events.',
        'base_url' => 'https://loveandlegendsbooks.com',
        'urls' => ['https://love-legends-books-llc.square.site/events'],
        'location' => 'Love & Legends Books',
        'notes' => 'Events hosted on their Square site. Main domain redirects to the Square storefront.',
    ],
    [
        'name' => 'Powerhouse on 8th',
        'description' => 'Powerhouse Books Park Slope neighborhood shop focused on childrens and YA programming, with storytimes, book launches, and family events.',
        'base_url' => 'https://powerhouseon8th.com',
        'urls' => ['https://powerhouseon8th.com/events/'],
        'location' => 'Powerhouse on 8th',
    ],
    [
        'name' => 'Unnameable Books',
        'description' => 'Prospect Heights independent bookstore known for deep fiction, poetry, and used-book selection, hosting poetry readings and launch events.',
        'base_url' => 'https://unnameablebooks.square.site',
        'location' => 'Unnameable Books',
        'notes' => 'Square storefront site, no dedicated events page found. Events announced on Instagram. Informational only.',
    ],
    [
        'name' => 'The BookMark Shoppe',
        'description' => 'Bay Ridge independent bookstore hosting author signings, release parties, Book Karaoke open mic nights, and family programming.',
        'base_url' => 'https://bookmarkshoppe.com',
        'urls' => ['https://bookmarkshoppe.com/upcoming-events'],
        'location' => 'The BookMark Shoppe',
    ],
    [
        'name' => 'Powerhouse at IC',
        'description' => 'Powerhouse Books Industry City location hosting storytimes, author events, and childrens and YA programming.',
        'base_url' => 'https://powerhouseic.com',
        'urls' => ['https://powerhouseic.com/events/'],
        'location' => 'Powerhouse at IC',
    ],
    [
        'name' => 'Taylor & Co. Books',
        'description' => 'Ditmas Park neighborhood independent bookstore hosting author readings and community literary events.',
        'base_url' => 'https://taylorcobooks.com',
        'location' => 'Taylor & Co. Books',
        'notes' => 'No dedicated events URL found — /events, /pages/events, and /upcoming-events all 404. Events likely on Instagram. Informational only.',
    ],
    [
        'name' => 'Terrace Books',
        'description' => 'Community Bookstore annex in Windsor Terrace hosting readings and neighborhood literary events.',
        'base_url' => 'https://terracebooks.com',
        'location' => 'Terrace Books (Community Bookstore annex)',
        'notes' => 'SSL certificate verification failed on WebFetch. Sister store to Community Bookstore (Park Slope). Informational only — events may be covered via Community Bookstore listings.',
    ],
    // Organizers from Nonsense NYC cross-reference (2026-04-24)
    [
        'name' => 'Scream Scene',
        'description' => 'Horror film screening series hosting events at venues across NYC (Baker Falls, Pine Box Rock Shop, The Tiny Cupboard, etc.). No fixed venue.',
        'base_url' => 'https://screamscene.net',
        'urls' => ['https://screamscene.net'],
        'crawl_frequency' => 7,
        'notes' => 'Roving organizer — events listed on homepage, no dedicated calendar page. Each event has its own venue. Extract venue per event.',
    ],
    [
        'name' => 'Quacks & Whacks Comedy',
        'description' => 'Comedy show series with eccentric variety acts. Performs at venues across NYC including Freddy\'s Bar and Caveat.',
        'base_url' => 'https://quacksandwhackscomedy.com',
        'urls' => ['https://quacksandwhackscomedy.com'],
        'crawl_frequency' => 14,
        'notes' => 'Roving organizer — events on homepage. Extract venue per event.',
    ],
    [
        'name' => 'Uptown Synth Syndicate',
        'description' => 'Monthly synthesizer show-and-tell and open mic at Our Saviour\'s Atonement Lutheran Church in Washington Heights.',
        'base_url' => 'https://uptownsynthsyndicate.neocities.org',
        'urls' => ['https://uptownsynthsyndicate.neocities.org/events.html'],
        'crawl_frequency' => 14,
        'location' => "Our Saviour's Atonement Lutheran Church",
        'notes' => 'Hosts at Our Saviour\'s Atonement. Event pages link to partiful for RSVP/details.',
    ],
    [
        'name' => 'Coney Island Film Festival',
        'description' => 'Annual independent film festival held over a weekend in May at venues throughout Coney Island (CI Museum, Sideshow by the Seashore).',
        'base_url' => 'https://www.coneyislandfilmfestival.com',
        'urls' => ['https://www.coneyislandfilmfestival.com'],
        'crawl_frequency' => 30,
        'notes' => 'Annual festival (May 1-3 in 2026). Detailed schedule with multiple programs per day across multiple Coney Island venues.',
    ],
    [
        'name' => 'The Beer Garage',
        'description' => 'Female-owned NYC sports bar with locations in Park Slope and the West Village, hosting weekly Thursday trivia and the Good & Funny stand-up comedy series.',
        'base_url' => 'http://www.beergarageny.com/',
        'urls' => ['https://ma.to/venue/beergarageny'],
        'location' => 'Beer Garage',
        'notes' => 'Events sourced from ma.to venue page (their own site has no calendar). Venue has two locations: Park Slope (148 5th Ave) and West Village (118 Christopher St) — only Park Slope is in the locations table. Trivia is weekly at Park Slope; Good & Funny Comedy location varies.',
    ],
    [
        'name' => 'Woodlawn Cemetery',
        'description' => 'Historic Bronx cemetery and National Historic Landmark hosting public tours, trolley tours, and family programs highlighting notable residents, jazz heritage, and the Level II Arboretum.',
        'base_url' => 'https://www.woodlawn.org',
        'urls' => ['https://www.woodlawn.org/conservancy/tours-events/'],
    ],
    // Performing groups associated with Old First Reformed Church (Park Slope) — added 2026-04-27
    [
        'name' => 'Grace Chorale of Brooklyn',
        'description' => 'Brooklyn community chorus presenting two or three concerts a year of wide-ranging choral music with an emphasis on living composers, newly commissioned work, and underrepresented composers.',
        'base_url' => 'https://www.gracechorale.org',
        'urls' => ['https://www.gracechorale.org/upcoming-performances'],
        'crawl_frequency' => 14,
        'notes' => 'Squarespace site. Low volume (2-3 concerts/year). Concerts at various Brooklyn venues (St. Ann & the Holy Trinity, St. Paul\'s Episcopal, Old First). Extract each event with its venue.',
    ],
    [
        'name' => 'Baroquelyn',
        'description' => 'Professional Baroque chamber orchestra and music series founded by Aleeza Meir, based at Old First Reformed Church in Park Slope, performing masterpieces and rarer works in an intimate setting.',
        'base_url' => 'https://www.baroquelyn.com',
        'urls' => ['https://www.baroquelyn.com/events'],
        'crawl_frequency' => 14,
        'notes' => 'Squarespace site. Home base is Old First Reformed Church but performs at other venues too. Extract each event with its venue.',
    ],
    [
        'name' => 'Brooklyn Community Chorus',
        'description' => 'Independent community choir in Park Slope, Brooklyn, open to anyone who loves to sing a variety of music—sacred and secular, classical and popular, historic and contemporary.',
        'base_url' => 'https://brooklyncommunitychorus.org',
        'urls' => ['https://brooklyncommunitychorus.org/events/'],
        'crawl_frequency' => 14,
        'notes' => 'WordPress site. Low volume (2 concerts/year, spring and winter). Concerts often at Old First Reformed Church but venue can change. Extract each event with its venue.',
    ],
    [
        'name' => 'Accord Treble Choir',
        'description' => 'NYC a cappella choral ensemble for treble voices, presenting themed concerts including new commissions and music spanning humanitarian and contemplative themes.',
        'base_url' => 'https://www.accordchoir.com',
        'urls' => ['https://www.accordchoir.com/performances'],
        'crawl_frequency' => 14,
        'notes' => 'Concerts at various Brooklyn and Manhattan venues (Old First Reformed Church, Saint John\'s Church in the Village). Tickets via Eventbrite. Extract each event with its venue.',
    ],
    // Added from pools.events (formerly withfriends.events) NYC organizer scan (2026-04-27)
    [
        'name' => 'Sojourners for Justice Press',
        'description' => 'Brooklyn-based small press behind the Black Zine Fair, hosting zine fairs, readings, and community events in NYC.',
        'base_url' => 'https://pools.events/o/sojourners_for_justice_press/',
        'urls' => ['https://pools.events/o/sojourners_for_justice_press/'],
        'crawl_frequency' => 14,
        'delay_before_return_html' => 15,
        'scan_full_page' => 1,
        'notes' => 'pools.events organizer page — events list rendered via JS; needs delay_before_return_html and scan_full_page. Only extract events organized by Sojourners for Justice Press; ignore "Hot Events" or "Upcoming Events" sections featuring other organizers.',
    ],
    [
        'name' => 'SUPR OMEN',
        'description' => 'Cross-scene, interdisciplinary Brooklyn venue for experimental live performance and visual works at 1 Knickerbocker Ave (two blocks from the Morgan L).',
        'base_url' => 'https://pools.events/o/supr-omen/',
        'urls' => ['https://pools.events/o/supr-omen/'],
        'crawl_frequency' => 7,
        'delay_before_return_html' => 15,
        'scan_full_page' => 1,
        'notes' => 'pools.events organizer page — events list rendered via JS; needs delay_before_return_html and scan_full_page. Only extract events organized by SUPR OMEN; ignore "Hot Events" or "Upcoming Events" sections featuring other organizers.',
    ],
    [
        'name' => 'Positive Deviance',
        'description' => 'Brooklyn arts and culture collective hosting DJ nights, talks, and gatherings — often at Bogart House and other Brooklyn venues.',
        'base_url' => 'https://pools.events/o/positive-deviance/',
        'urls' => ['https://pools.events/o/positive-deviance/'],
        'crawl_frequency' => 14,
        'delay_before_return_html' => 15,
        'scan_full_page' => 1,
        'notes' => 'pools.events organizer page — events list rendered via JS; needs delay_before_return_html and scan_full_page. Only extract events organized by Positive Deviance; ignore "Hot Events" or "Upcoming Events" sections featuring other organizers.',
    ],
    [
        'name' => 'POWRPLNT',
        'description' => 'Brooklyn digital arts collective running workshops on Ableton, creative coding, and digital media tools for underrepresented youth and adult learners.',
        'base_url' => 'https://pools.events/o/powrplnt/',
        'urls' => ['https://pools.events/o/powrplnt/'],
        'crawl_frequency' => 14,
        'delay_before_return_html' => 15,
        'scan_full_page' => 1,
        'notes' => 'pools.events organizer page — events list rendered via JS; needs delay_before_return_html and scan_full_page. Only extract events organized by POWRPLNT; ignore "Hot Events" or "Upcoming Events" sections featuring other organizers.',
    ],

    // 2026-04-29 — informational website entries for venues missing website links (top 10 by event count).
    // No `urls`/`crawl_frequency` — these serve as the popup link only; events come from other crawled sources.
    [
        'name' => 'The Windjammer',
        'description' => 'Neighborhood bar and live music venue in Ridgewood, Queens, hosting bands, open mics, and arts programming via The Footlight Underground.',
        'base_url' => 'https://www.facebook.com/thewindjammerny/',
        'location' => 'The Windjammer',
    ],
    [
        'name' => 'Hello Meadow BK',
        'description' => 'Industrial-chic event space in East Williamsburg with exposed brick and large windows, used for community events, parties, and workshops for up to 150 guests.',
        'base_url' => 'https://www.hellomeadowbk.com',
        'location' => 'Hello Meadow BK',
    ],
    [
        'name' => 'Zen Mountain Monastery',
        'description' => '220-acre Zen Buddhist monastery and training center in the Catskills offering meditation retreats, Zen training programs, and dharma talks for practitioners of all backgrounds.',
        'base_url' => 'https://zmm.org',
        'location' => 'Zen Mountain Monastery',
    ],
    [
        'name' => 'Astoria Park',
        'description' => '60-acre waterfront park in Astoria with NYC\'s largest Olympic-size pool, running track, tennis courts, and a bandstand hosting a free Thursday-evening summer concert series.',
        'base_url' => 'https://www.nycgovparks.org/parks/astoria-park',
        'location' => 'Astoria Park',
    ],
    [
        'name' => 'Center for Architecture',
        'description' => 'AIA New York\'s storefront cultural center in Greenwich Village hosting exhibitions, lectures, and public programs about architecture and the built environment.',
        'base_url' => 'https://www.centerforarchitecture.org',
        'location' => 'Center for Architecture',
    ],
    [
        'name' => 'Sadie\'s NYC',
        'description' => 'Two-level New American restaurant and the Seaport\'s outdoor Garden Bar, a day-to-night destination at 19 Fulton Street with seasonal cocktails and indoor-outdoor seating.',
        'base_url' => 'https://www.sadies.nyc',
        'location' => 'Sadie\'s NYC',
    ],

    // 2026-04-29 batch 2 — informational website entries for next 10 locations missing website links.
    [
        'name' => 'The Church of the Village',
        'description' => 'Progressive, LGBTQ-affirming United Methodist congregation in the West Village hosting worship services, concerts, talks, and community events.',
        'base_url' => 'https://www.churchofthevillage.org',
        'location' => 'Church of the Village',
    ],
    [
        'name' => 'Tap Haus 33',
        'description' => 'NYC\'s first self-pour bar in NoMad with 40 taps — customers preload a card and pour their own beer, wine, and seltzer.',
        'base_url' => 'https://taphaus33.net',
        'location' => 'Tap Haus 33',
    ],
    [
        'name' => 'Adams Street Library (BPL)',
        'description' => 'Brooklyn Public Library\'s 60th branch in DUMBO, fronting Brooklyn Bridge Park, with story times, programs, and meeting rooms for children, teens, and adults.',
        'base_url' => 'https://www.bklynlibrary.org/locations/adams-street',
        'location' => 'Adams Street Library',
    ],
    [
        'name' => 'West Harlem Piers Park',
        'description' => 'Two-acre waterfront park connecting West Harlem to the Hudson River greenway, with recreational piers, bicycle and pedestrian paths, and landscaped open space.',
        'base_url' => 'https://www.nycgovparks.org/parks/west-harlem-piers',
        'location' => 'West Harlem Piers',
    ],
    [
        'name' => 'Union Square Park',
        'description' => '6.5-acre Manhattan public plaza between 14th and 17th Streets, home to the year-round Greenmarket and a long history of rallies, festivals, and community events.',
        'base_url' => 'https://www.nycgovparks.org/parks/union-square-park',
        'location' => 'Union Square',
    ],

    // 2026-04-29 batch 3 — informational website entries for next 4 locations missing website links.
    [
        'name' => 'Huntington Fine Arts',
        'description' => 'Long Island fine art studio founded in 1971 offering drawing, painting, and sculpture classes for ages eight through adult, plus a college portfolio prep program.',
        'base_url' => 'https://www.huntfinearts.com',
        'location' => 'Huntington Fine Arts',
    ],
    [
        'name' => 'West Side Campaign Against Hunger',
        'description' => 'Upper West Side anti-hunger nonprofit running a supermarket-style food pantry and connecting clients to SNAP, WIC, and other social services.',
        'base_url' => 'https://www.wscah.org',
        'location' => 'West Side Campaign Against Hunger - UWS',
    ],
    [
        'name' => 'Joy Flower Pot BK',
        'description' => 'Williamsburg coffee shop and floral studio at 713 Lorimer Street, serving Vietnamese coffee and matcha alongside seasonal flower arrangements.',
        'base_url' => 'https://www.joyflowerpot.com',
        'location' => 'Joy Flower Pot',
    ],
    [
        'name' => 'Nelson A. Rockefeller Park',
        'description' => 'Eight-acre Hudson River waterfront park at the north end of Battery Park City, with playgrounds, lawns, and seasonal events programmed by the Battery Park City Parks Conservancy.',
        'base_url' => 'https://bpcparks.org/venue/rockefeller-park/',
        'location' => 'Nelson A. Rockefeller Park',
    ],

    // 2026-04-29 batch 4 — informational website entries for next 6 specific-venue locations.
    [
        'name' => 'Battery Urban Farm',
        'description' => 'Educational urban farm in The Battery (Lower Manhattan) hosting school programs, public workshops, and community planting events run by The Battery Conservancy.',
        'base_url' => 'https://www.thebattery.org/destinations/urban-farm/',
        'location' => 'Battery Urban Farm',
    ],
    [
        'name' => 'Tipsy NoMad',
        'description' => 'NoMad bar, restaurant, and lounge with two full bars, craft cocktails, and flexible event space for private parties.',
        'base_url' => 'https://www.tipsynomadnyc.com',
        'location' => 'Tipsy Nomad',
    ],
    [
        'name' => 'Shorefront YM-YWHA',
        'description' => 'Brighton-Manhattan Beach Jewish community center on Coney Island Avenue offering programs, classes, and cultural events rooted in Jewish traditions.',
        'base_url' => 'https://www.shorefronty.org',
        'location' => 'Shorefront YM-YWHA',
    ],
    [
        'name' => '200 Rector Place (BPCA)',
        'description' => 'Battery Park City Authority community room at Liberty Court hosting choral, mah-jongg, fiber arts, and other neighborhood programs.',
        'base_url' => 'https://bpca.ny.gov/venue/200-rector-place/',
        'location' => '200 Rector Place',
    ],
    [
        'name' => 'Iggy\'s Karaoke Bar',
        'description' => 'Upper East Side karaoke and sports bar open daily until 4am, with 14 flat-screen TVs, a projector screen, and salsa lessons.',
        'base_url' => 'https://iggysnewyork.com',
        'location' => 'Iggy\'s Karaoke Bar',
    ],
    [
        'name' => 'St. Lydia\'s',
        'description' => 'Progressive, LGBTQ-affirming Lutheran "dinner church" in Gowanus where a sacred meal, simple music, and prayer are shared together each Sunday.',
        'base_url' => 'https://www.stlydias.org',
        'location' => 'St. Lydia',
    ],

    // 2026-04-29 batch 5 — informational website entries for next 5 specific-venue locations.
    [
        'name' => 'Montclair Public Library',
        'description' => 'Montclair, NJ\'s main public library hosting author talks, jazz listening sessions, teen programs, and community events.',
        'base_url' => 'https://montclairlibrary.org',
        'location' => 'Montclair Public Library',
    ],
    [
        'name' => 'P.S. 216 Arturo Toscanini',
        'description' => 'Public elementary school in Gravesend, Brooklyn whose Edible Schoolyard NYC garden hosts gardening, nutrition, and pollinator events.',
        'base_url' => 'http://www.ps216.com',
        'location' => 'PS 216 Arturo Toscanini School',
    ],
    [
        'name' => 'Fraser Square (NYC Parks)',
        'description' => '0.667-acre Brooklyn pocket park at Kings Highway and Avenue M, transformed from a traffic circle into a community garden and small gathering space.',
        'base_url' => 'https://www.nycgovparks.org/parks/fraser-square',
        'location' => 'Fraser Square Park',
    ],
    [
        'name' => 'Wagner Park (BPCA)',
        'description' => 'Battery Park City waterfront park reopened in 2025 after a $296M renovation, with public lawns, free art classes, sustainability programming, and summer performances.',
        'base_url' => 'https://bpca.ny.gov/venue/wagner-park/',
        'location' => 'Wagner Park',
    ],
    [
        'name' => 'Staten Island Ferry',
        'description' => 'Free 24/7 ferry service between Lower Manhattan\'s Whitehall Terminal and St. George Terminal on Staten Island, operated by NYC DOT.',
        'base_url' => 'https://siferry.com',
        'location' => 'Staten Island Ferry - Whitehall Terminal',
    ],

    // 2026-04-29 batch 6 — informational website entries for next 5 specific-venue locations.
    [
        'name' => 'United Nations Visitors Centre',
        'description' => 'UN Headquarters visitor program in Midtown East offering guided tours of the General Assembly, Security Council, and Trusteeship Council Chambers, plus exhibits and the UN Bookshop.',
        'base_url' => 'https://www.un.org/en/visit',
        'location' => 'United Nations Headquarters',
    ],
    [
        'name' => 'Slattery\'s Midtown Pub',
        'description' => 'Midtown Manhattan Irish pub and comfort-food restaurant near Madison Square Garden with 25 HD TVs, used for after-work gatherings and private events.',
        'base_url' => 'https://slatterysmidtownpub.com',
        'location' => 'Slattery\'s Midtown Pub',
    ],
    [
        'name' => 'Starlight Park (NYC Parks)',
        'description' => '13-acre Bronx waterfront park along the Bronx River Greenway with a turf field, playgrounds, kayaking docks, and free community paddling and stewardship events.',
        'base_url' => 'https://www.nycgovparks.org/parks/starlight-park',
        'location' => 'Starlight Park',
    ],
    [
        'name' => 'Circle Line Sightseeing Cruises',
        'description' => 'Iconic NYC sightseeing cruise operator at Pier 83 in Hudson River Park, running full-island, Liberty, sunset, and harbor cruises around Manhattan.',
        'base_url' => 'https://www.circleline.com',
        'location' => 'Pier 83 (Circle Line Cruises)',
    ],
    [
        'name' => 'John Jay College of Criminal Justice',
        'description' => 'CUNY senior college in Hell\'s Kitchen specializing in criminal justice and forensic science, with a public-facing event calendar including Gerald W. Lynch Theater performances.',
        'base_url' => 'https://www.jjay.cuny.edu',
        'location' => 'John Jay College of Criminal Justice',
    ],

    // 2026-04-29 batch 7 — informational website entries.
    [
        'name' => 'Williamsburgh Library (BPL)',
        'description' => 'Brooklyn Public Library branch in Williamsburg housed in the historic Williamsburgh Trust Company building, hosting reading programs, classes, and community events.',
        'base_url' => 'https://www.bklynlibrary.org/locations/williamsburgh',
        'location' => 'Williamsburgh Library',
    ],
    [
        'name' => 'Rugby Library (BPL)',
        'description' => 'Brooklyn Public Library branch on Utica Avenue in East Flatbush serving the Rugby and Remsen Village neighborhoods.',
        'base_url' => 'https://www.bklynlibrary.org/locations/rugby',
        'location' => 'Rugby Library',
    ],
    [
        'name' => 'Pacific Library (BPL)',
        'description' => 'Brooklyn Public Library branch in Boerum Hill (the borough\'s oldest active library) hosting story times, language learning, and community programs.',
        'base_url' => 'https://www.bklynlibrary.org/locations/pacific',
        'location' => 'Pacific Library',
    ],
    [
        'name' => 'NYU Global Spiritual Life',
        'description' => 'NYU\'s Global Center for Academic & Spiritual Life at 238 Thompson St, home to classrooms, religious observance spaces, and programs across more than 40 faith traditions.',
        'base_url' => 'https://www.nyu.edu/spiritual-life',
        'location' => 'NYU Global Center',
    ],
    [
        'name' => 'BrainStation New York',
        'description' => 'Soho-based technical school at 136 Crosby Street offering full-time bootcamps and part-time courses in software development, data science, design, and product management.',
        'base_url' => 'https://brainstation.io/new-york',
        'location' => 'BrainStation NYC',
    ],

    // 2026-04-29 batch 8 — informational website entries.
    [
        'name' => 'El Jardin del Paraiso',
        'description' => 'Nearly-acre Lower East Side community garden on East 5th Street featuring lawns, wetlands, a willow-tree treehouse, and a long-running NYC Parks GreenThumb education program.',
        'base_url' => 'https://eljardindelparaiso.org',
        'location' => 'El Jardin del Paraiso',
    ],
    [
        'name' => 'SMUSH Gallery',
        'description' => 'Jersey City community art space hosting rotating visual exhibitions, performances, workshops, and affordable space rentals — wheelchair accessible.',
        'base_url' => 'https://www.smushgallery.com',
        'location' => 'SMUSH Gallery',
    ],
    [
        'name' => 'Sour Mouse NYC',
        'description' => 'Lower East Side game hall and live-music bar at 110 Delancey featuring pool, ping-pong, shuffleboard, foosball, lifesize Jenga, DJs, and pizza.',
        'base_url' => 'https://www.sourmousenyc.com',
        'location' => 'Sour Mouse',
    ],
    [
        'name' => 'West Thames Park (BPCA)',
        'description' => 'Battery Park City park with a children\'s playground (water play, sand, climbing structures), turf soccer field, community garden, and dog run.',
        'base_url' => 'https://bpca.ny.gov/place/west-thames-park/',
        'location' => 'West Thames Park',
    ],
    [
        'name' => 'Cambria Heights Community Garden (BQLT)',
        'description' => 'Volunteer-run community garden at 227th Street and Linden Boulevard in Queens, managed by the Brooklyn Queens Land Trust, hosting tree care, composting, and library partner events.',
        'base_url' => 'https://bqlt.org/garden/227th-street-cambria-heights-community-garden',
        'location' => 'Cambria Heights Community Garden',
    ],
    [
        'name' => 'Pierre Augustin Rose',
        'description' => 'French furniture and lighting brand\'s 6,000-square-foot SoHo gallery (224 Centre Street, 4th floor), used for design talks and brand events alongside the showroom.',
        'base_url' => 'https://pierreaugustinrose.com/en',
        'location' => 'Pierre Augustin Rose',
    ],
    [
        'name' => 'Hill Street Community Garden',
        'description' => 'Resident-led NYC Parks GreenThumb community garden in Stapleton, Staten Island, focused on community organizing, shared governance, and food sovereignty.',
        'base_url' => 'https://www.nycgovparks.org/opportunities/volunteer/group/hill-street-community-garden',
        'location' => 'Hill Street Garden',
    ],
    [
        'name' => 'NYC Department of Veterans\' Services',
        'description' => 'NYC agency providing free in-person benefits help, programs, and outreach events for veterans, service members, caregivers, and their families.',
        'base_url' => 'https://www.nyc.gov/site/veterans',
        'location' => 'NYC Department of Veterans\' Services',
    ],
    [
        'name' => 'Italian Trade Agency NYC',
        'description' => 'Italian government trade office at 33 East 67th Street hosting design, fashion, food, and lifestyle showcases including the annual Italy on Madison program.',
        'base_url' => 'https://www.ice.it/en/events-in-month',
        'location' => 'Italian Trade Agency',
    ],

    // 2026-04-29 batch 9 — informational website entries.
    [
        'name' => 'Ryan\'s Daughter',
        'description' => 'Two-story Upper East Side Irish pub at 350 East 85th Street (since 1979) with a pool table, darts, jazz nights, play readings, and private events upstairs.',
        'base_url' => 'https://ryansdaughter.nyc',
        'location' => 'Ryan\'s Daughter',
    ],
    [
        'name' => 'Tusten Theatre / Delaware Valley Arts Alliance',
        'description' => '150-seat art deco theater in Narrowsburg, NY managed by the Delaware Valley Arts Alliance, presenting jazz, classical, folk, opera, and the Big Eddy Film Festival.',
        'base_url' => 'https://delawarevalleyartsalliance.org',
        'location' => 'Tusten Theatre',
    ],
    [
        'name' => 'East Midwood Jewish Center',
        'description' => 'Egalitarian Conservative synagogue in Midwood, Brooklyn (founded 1924; 1929 Renaissance Revival building on the National Register), offering worship, learning, and community programming.',
        'base_url' => 'https://www.emjc.org',
        'location' => 'East Midwood Jewish Center',
    ],
    [
        'name' => 'Clinton Hall',
        'description' => 'NYC craft-beer hall and restaurant chain — the 36th Street location near Herald Square offers a constantly rotating "Supercraft" beer list and a Midtown beer-garden vibe.',
        'base_url' => 'https://clintonhallny.com/36th-street/',
        'location' => 'Clinton Hall 36th Street',
    ],
    [
        'name' => 'The Davis Center at the Harlem Meer',
        'description' => 'Central Park Conservancy\'s new $160M waterfront recreation center at the Harlem Meer (opened April 2026), with a public swimming pool / winter ice rink and shoulder-season turf field.',
        'base_url' => 'https://daviscenter.centralparknyc.org',
        'location' => 'Davis Center at the Harlem Meer',
    ],
    [
        'name' => 'New York Common Pantry',
        'description' => 'East Harlem anti-hunger nonprofit running an on-site food pantry and soup kitchen plus mobile pantry programs across NYC.',
        'base_url' => 'https://nycommonpantry.org',
        'location' => 'New York Common Pantry',
    ],
    [
        'name' => 'The Lee C. Bollinger Forum (Columbia)',
        'description' => 'Columbia University community gathering space at 125th Street and Broadway anchoring the Manhattanville campus — a public auditorium, atrium, and event venue.',
        'base_url' => 'https://theforum.columbia.edu',
        'location' => 'Columbia Manhattanville - The Forum',
    ],
    [
        'name' => 'Abyssinian Baptist Church',
        'description' => 'Historic African-American Baptist church in Harlem (founded 1808 — the first African-American Baptist church in New York State) with worship services and gospel music programming.',
        'base_url' => 'https://www.abyssinian.org',
        'location' => 'Abyssinian Baptist Church',
    ],
    [
        'name' => 'City Harvest',
        'description' => 'NYC\'s largest food rescue nonprofit (founded 1982), redirecting nutritious food that would otherwise go to waste to New Yorkers experiencing hunger.',
        'base_url' => 'https://www.cityharvest.org',
        'location' => 'City Harvest',
    ],

    // 2026-04-29 batch 10 — informational website entries.
    [
        'name' => 'Kittatinny Valley State Park',
        'description' => 'New Jersey state park in Sussex County with glacial lakes, former-railroad multi-use trails (Paulinskill Valley, Sussex Branch, Great Valley), and year-round naturalist programs.',
        'base_url' => 'https://dep.nj.gov/parksandforests/state-park/kittatinny-valley-state-park/',
        'location' => 'Kittatinny Valley State Park',
    ],
    [
        'name' => 'High Point State Park',
        'description' => 'New Jersey state park straddling Wantage and Montague in Sussex County, home to High Point Monument and the NJ Veterans\' Memorial in the Skylands region.',
        'base_url' => 'https://dep.nj.gov/parksandforests/state-park/high-point-state-park/',
        'location' => 'High Point State Park',
    ],
    [
        'name' => 'Red Rooster Harlem',
        'description' => 'Marcus Samuelsson\'s Harlem restaurant on Lenox Avenue serving comfort food rooted in American and African diaspora culinary traditions, with regular live music and community events.',
        'base_url' => 'https://www.redroosterharlem.com',
        'location' => 'Red Rooster Harlem',
    ],
    [
        'name' => 'Fair Lawn Public Library (Maurice M. Pine)',
        'description' => 'Borough public library in Fair Lawn, NJ, offering programs, museum passes, hotspots, 3D printing, and a wedding-dress lending program.',
        'base_url' => 'https://www.fairlawnlibrary.org',
        'location' => 'Fair Lawn Maurice M. Pine Library',
    ],
    [
        'name' => 'Plainfield Performing Arts Center (PPAC)',
        'description' => 'Former landmark church reborn as Plainfield, NJ\'s city-run performing arts center, with a concert hall, theater, dance studio, gallery, and reception room.',
        'base_url' => 'https://plainfieldnj.gov/residents/play/plainfield_performing_arts_center_(ppac)/index.php',
        'location' => 'Plainfield Performing Arts Center',
    ],
    [
        'name' => 'BAFFA Art Gallery',
        'description' => 'Long Island visual-arts gallery (Bay Area Friends of the Fine Arts) in the historic Gillette House in Sayville, with monthly free exhibitions of regional artists.',
        'base_url' => 'https://www.baffa.org',
        'location' => 'BAFFA Gallery',
    ],
    [
        'name' => 'The Concord NYC',
        'description' => 'Lower East Side multi-level nightlife venue at 92 Ludlow Street (formerly Hotel Chantelle) with three levels of programming, a rooftop, and the Anbā omakase counter.',
        'base_url' => 'https://www.theconcordnyc.com',
        'location' => 'The Concord',
    ],
    [
        'name' => 'Columbus Park (NYC Parks)',
        'description' => 'Historic Chinatown park (formerly Mulberry Bend Park) bounded by Mulberry, Baxter, Worth, and Bayard Streets, used daily for mahjong, traditional Chinese music, and community events.',
        'base_url' => 'https://www.nycgovparks.org/parks/columbus-park-m015',
        'location' => 'Columbus Park (Chinatown)',
    ],
    [
        'name' => 'Old Tappan Free Public Library',
        'description' => 'Bergen County public library on Russell Avenue serving Old Tappan, NJ with programs, story times, and community events.',
        'base_url' => 'https://www.oldtappanlibrary.com',
        'location' => 'Old Tappan Public Library',
    ],
    [
        'name' => 'Verona Park',
        'description' => '54-acre Olmsted Brothers-designed Essex County park around a 13-acre lake in Verona, NJ, with paddle boats, tennis courts, a children\'s garden, and walking paths.',
        'base_url' => 'https://essexcountyparks.org/parks/verona-park',
        'location' => 'Verona Park',
    ],
    [
        'name' => 'Presby Memorial Iris Gardens',
        'description' => 'Upper Montclair "Rainbow on the Hill" featuring 14,000+ irises across 3,000 varieties — peak bloom mid-May through early June; donation-supported, free admission.',
        'base_url' => 'https://www.presbyirisgardens.org',
        'location' => 'Presby Memorial Iris Gardens',
    ],

    // 2026-04-29 batch 11 — informational website entries.
    [
        'name' => 'Hoboken Public Library',
        'description' => 'Hoboken, NJ\'s public library on Park Avenue hosting concerts, films, book clubs, story times, and educational programs for all ages.',
        'base_url' => 'https://hobokenlibrary.org',
        'location' => 'Hoboken Public Library',
    ],
    [
        'name' => 'Upper Saddle River Library',
        'description' => 'Bergen County public library serving Upper Saddle River, NJ with adult programs, kids and teen events, book clubs, and community classes.',
        'base_url' => 'https://uppersaddleriverlibrary.org',
        'location' => 'Upper Saddle River Public Library',
    ],
    [
        'name' => 'Secaucus Public Library',
        'description' => 'Hudson County, NJ public library and business resource center on Paterson Plank Road, with a second annex location on Riverside Station Boulevard.',
        'base_url' => 'https://secaucuslibrary.org',
        'location' => 'Secaucus Public Library',
    ],
    [
        'name' => 'Sherman Creek Park (NYC Parks)',
        'description' => '15-acre Inwood waterfront park along the Harlem River — five small street-end parks (West 202nd–206th) connecting Inwood to the river, with kayak launches and picnic areas.',
        'base_url' => 'https://www.nycgovparks.org/parks/sherman-creek-park/',
        'location' => 'Sherman Creek Park',
    ],
    [
        'name' => 'Paramus Public Library',
        'description' => 'Bergen County public library on Century Road with a second branch (Charles E. Reid) on West Midland Avenue, hosting community programs and classes.',
        'base_url' => 'https://paramuslibrary.org',
        'location' => 'Paramus Public Library',
    ],
    [
        'name' => 'Lincoln Terrace / Arthur S. Somers Park',
        'description' => '21-acre Brooklyn park (Crown Heights / Brownsville) at Eastern Parkway and E. New York Ave, with baseball, basketball, handball, tennis, fitness equipment, and playgrounds.',
        'base_url' => 'https://www.nycgovparks.org/parks/lincoln-terrace-arthur-s-somers-park',
        'location' => 'Lincoln Terrace Park',
    ],
    [
        'name' => 'The Nyack Library',
        'description' => 'Free association library in the village of Nyack, NY on South Broadway, offering programs, classes, and community events for Rockland County residents.',
        'base_url' => 'https://www.nyacklibrary.org',
        'location' => 'The Nyack Library',
    ],

    // 2026-04-29 batch 12 — informational website entries.
    [
        'name' => 'Darien Lakes State Park',
        'description' => '1,845-acre state park in western Genesee County, NY, with 154 campsites, a beach, hiking and horseback riding trails, picnic areas, and winter cross-country skiing.',
        'base_url' => 'https://parks.ny.gov/visit/state-parks/darien-lakes-state-park',
        'location' => 'Darien Lakes State Park',
    ],
    [
        'name' => 'Harriman State Park',
        'description' => 'NY\'s second-largest state park (Rockland and Orange counties) with 31 lakes, 200 miles of hiking trails, two beaches, and two public camping areas — bordered by Bear Mountain SP.',
        'base_url' => 'https://parks.ny.gov/visit/state-parks/harriman-state-park',
        'location' => 'Harriman State Park',
    ],
    [
        'name' => 'Roy Wilkins Recreation Center',
        'description' => '50,000 sq ft Jamaica, Queens recreation center in Roy Wilkins Park — Olympic-size swimming pool, summer camp, after-school activities, and family programs.',
        'base_url' => 'https://www.nycgovparks.org/facilities/recreationcenters/q448',
        'location' => 'Roy Wilkins Recreation Center',
    ],
    [
        'name' => 'Yume Brooklyn',
        'description' => 'Brooklyn (Prospect Lefferts Gardens) creative space and event venue at 671 Flatbush Avenue, hosting comedy, music, and community events.',
        'base_url' => 'https://www.instagram.com/yumebk/',
        'location' => 'Yume',
    ],
    [
        'name' => 'NYU Tisch School of the Arts (726 Broadway)',
        'description' => 'NYU Tisch Student Affairs building on Broadway housing Career Development, Counseling Services, and student programming spaces — host to the Tisch International Student Coffee Hour and showcases.',
        'base_url' => 'https://tisch.nyu.edu',
        'location' => '726 Broadway',
    ],
    [
        'name' => 'Stout NYC',
        'description' => 'New York\'s largest Irish pub, two blocks from Penn Station / Madison Square Garden, with three floors of bar/restaurant space and live sports.',
        'base_url' => 'https://www.stoutnyc.com/location/stout-nyc-penn-station/',
        'location' => 'Stout NYC',
    ],
    [
        'name' => 'New York City Hall',
        'description' => 'NYC\'s landmark city hall building (1812) in Lower Manhattan — site of the Mayor\'s office and free public tours run by the NYC Public Design Commission.',
        'base_url' => 'https://www.nyc.gov/site/designcommission/tours-events/city-hall-tours/city-hall.page',
        'location' => 'NYC City Hall',
    ],
    [
        'name' => 'Dive Bar BK',
        'description' => 'Bushwick Latin gastropub with brunch, live music, and private party space at 408 Troutman Street.',
        'base_url' => 'https://www.divebarbk.com',
        'location' => 'Dive Bar BK',
    ],

    // 2026-04-29 batch 13 — informational website entries.
    [
        'name' => 'PUBLIC Hotel New York',
        'description' => 'Ian Schrager\'s 367-room Lower East Side hotel at 215 Chrystie Street with two Jean-Georges restaurants, a market, and a rooftop bar.',
        'base_url' => 'https://www.publichotels.com/newyork',
        'location' => 'Public Hotel',
    ],
    [
        'name' => 'Poe Park (NYC Parks)',
        'description' => 'Bronx neighborhood park on Grand Concourse named for Edgar Allan Poe (who lived in the on-site Poe Cottage 1846–1849), with a Visitor Center hosting free arts and cultural programming.',
        'base_url' => 'https://www.nycgovparks.org/parks/poe-park',
        'location' => 'Poe Park',
    ],
    [
        'name' => 'Montclair State University Galleries',
        'description' => 'Montclair State University\'s on-campus art galleries — including the flagship George Segal Gallery — presenting free exhibitions and programs to the campus and public.',
        'base_url' => 'https://www.montclair.edu/galleries/',
        'location' => 'Montclair State University Galleries',
    ],
    [
        'name' => 'St. Mary\'s Park (Bronx)',
        'description' => 'Largest park in the South Bronx, with a track, handball and basketball courts, a baseball diamond, and a recreation center (currently under reconstruction).',
        'base_url' => 'https://www.nycgovparks.org/parks/st-marys-park',
        'location' => 'St. Mary\'s Park',
    ],
    [
        'name' => 'Windsor Terrace Library (BPL)',
        'description' => 'Brooklyn Public Library branch in Windsor Terrace at East 5th Street, hosting reading programs, story times, and community events.',
        'base_url' => 'https://www.bklynlibrary.org/locations/windsor-terrace',
        'location' => 'Windsor Terrace Library',
    ],
    [
        'name' => 'Ryder Library (BPL)',
        'description' => 'Brooklyn Public Library branch on 23rd Avenue serving Bensonhurst and the surrounding neighborhoods.',
        'base_url' => 'https://www.bklynlibrary.org/locations/ryder',
        'location' => 'Ryder Library',
    ],
    [
        'name' => 'Marcus Garvey Park',
        'description' => '20-acre Central Harlem park (renamed in 1977) with two playgrounds, an outdoor pool, the Pelham Fritz Recreation Center, and the Richard Rodgers Amphitheater for plays and concerts.',
        'base_url' => 'https://www.nycgovparks.org/parks/marcus-garvey-park',
        'location' => 'Marcus Garvey Park',
    ],

    // 2026-04-29 batch 14 — informational website entries.
    [
        'name' => 'Kings Bay Library (BPL)',
        'description' => 'Brooklyn Public Library branch on Nostrand Avenue serving Sheepshead Bay and the surrounding neighborhoods.',
        'base_url' => 'https://www.bklynlibrary.org/locations/kings-bay',
        'location' => 'Kings Bay Library',
    ],
    [
        'name' => 'Green Oasis Community Garden',
        'description' => 'NYC Parks GreenThumb community garden on East 8th Street in the East Village/Loisaida, hosting volunteer days, performances, and neighborhood gatherings.',
        'base_url' => 'https://www.nycgovparks.org/parks/green-oasis-community-garden',
        'location' => 'Green Oasis Community Garden',
    ],
    [
        'name' => 'Forest Hills Library (Queens Public Library)',
        'description' => 'Queens Public Library branch on 71st Avenue in Forest Hills, hosting children\'s programs, ESOL classes, and community events.',
        'base_url' => 'https://www.queenslibrary.org/about-us/our-locations/forest-hills',
        'location' => 'Forest Hills Library',
    ],
    [
        'name' => 'City Hall Park',
        'description' => 'Lower Manhattan public park surrounding NYC City Hall with a fountain, the African Burial Ground monument, and seasonal art installations.',
        'base_url' => 'https://www.nycgovparks.org/parks/city-hall-park',
        'location' => 'City Hall Park',
    ],
    [
        'name' => 'Brighton Beach Library (BPL)',
        'description' => 'Brooklyn Public Library branch in Brighton Beach hosting reading programs, language classes, and Russian-language collections.',
        'base_url' => 'https://www.bklynlibrary.org/locations/brighton-beach',
        'location' => 'Brighton Beach Library',
    ],
    [
        'name' => '42nd Street, Manhattan (Wikipedia)',
        'description' => 'Wikipedia article on Manhattan\'s 42nd Street.',
        'base_url' => 'https://en.wikipedia.org/wiki/42nd_Street_(Manhattan)',
        'location' => '42nd Street, Manhattan',
    ],
    [
        'name' => 'USS Maine Monument (Wikipedia)',
        'description' => 'Wikipedia article on the USS Maine National Monument at Columbus Circle.',
        'base_url' => 'https://en.wikipedia.org/wiki/USS_Maine_National_Monument',
        'location' => 'USS Maine Monument',
    ],

    // 2026-04-29 batch 15 — informational website entries.
    [
        'name' => 'NADA Art Fair',
        'description' => 'Annual contemporary art fair from the New Art Dealers Alliance — the 2026 NY edition hosts 121 galleries at the Starrett-Lehigh Building, May 13–17.',
        'base_url' => 'https://www.newartdealers.org/fairs/nada-new-york-2026/',
        'location' => 'NADA New York',
    ],
    [
        'name' => 'New York Tech (NYIT) Manhattan Campus',
        'description' => 'NYIT\'s Columbus Circle campus on Broadway (60th–61st Streets) housing 80 career-focused undergraduate and graduate programs.',
        'base_url' => 'https://www.nyit.edu/nyc',
        'location' => 'NYIT - Manhattan (Columbus Circle)',
    ],
    [
        'name' => 'Studio Solenne',
        'description' => 'Brooklyn creative studio in Clinton Hill at 4 St James Place — design consultations, photo shoots, and small events.',
        'base_url' => 'https://www.studiosolenne.com',
        'location' => 'Studio Solenne',
    ],
    [
        'name' => 'ASLA New York',
        'description' => 'New York chapter of the American Society of Landscape Architects (founded 1914) — the regional professional organization for landscape architects in the NYC metro / Long Island region.',
        'base_url' => 'https://www.aslany.org',
        'location' => 'ASLA NY',
    ],
    [
        'name' => 'Cadman Plaza Park',
        'description' => 'Downtown Brooklyn park anchoring Cadman Plaza, host to greenmarkets, Veterans Day ceremonies, the Juneteenth Grove memorial, and community events.',
        'base_url' => 'https://www.nycgovparks.org/parks/cadman-plaza-park',
        'location' => 'Juneteenth Grove (Cadman Plaza Park)',
    ],
    [
        'name' => 'Renaissance New York Times Square Hotel',
        'description' => 'Marriott\'s Renaissance Times Square hotel at 714 Seventh Avenue — 312 soundproofed rooms, terrace suites, and meeting/event space steps from the Theater District.',
        'base_url' => 'https://www.marriott.com/en-us/hotels/nycrt-renaissance-new-york-times-square-hotel/overview/',
        'location' => 'Renaissance New York Times Square',
    ],
    [
        'name' => 'Fire Island Pines (Wikipedia)',
        'description' => 'Wikipedia article on the Fire Island Pines hamlet on Fire Island, NY.',
        'base_url' => 'https://en.wikipedia.org/wiki/Fire_Island_Pines,_New_York',
        'location' => 'Fire Island Pines',
    ],
    [
        'name' => 'CHART Gallery',
        'description' => 'Tribeca contemporary art gallery at 74 Franklin Street founded by Clara Ha, with rotating exhibitions and site-specific installations by emerging and established artists.',
        'base_url' => 'https://chart-gallery.com',
        'location' => 'CHART Gallery',
    ],
    [
        'name' => 'The Compound Cowork',
        'description' => 'Flatbush, Brooklyn coworking space at 1120 Washington Avenue (founded 2014) offering desks, offices, and event/meeting space for community gatherings and workshops.',
        'base_url' => 'https://www.thecompoundcowork.com',
        'location' => 'The Compound Cowork',
    ],
    [
        'name' => 'NYC Velo',
        'description' => 'East Village independent bike shop (founded 2005) at 66 2nd Avenue offering sales, service, and community group rides.',
        'base_url' => 'https://www.nycvelo.com',
        'location' => 'NYC Velo',
    ],
    [
        'name' => 'ARF Hamptons',
        'description' => 'Animal Rescue Fund of the Hamptons (founded 1974) — East Hampton animal shelter and adoption center running spay/neuter programs and humane education.',
        'base_url' => 'https://arfhamptons.org',
        'location' => 'ARF Hamptons',
    ],

    // 2026-04-29 batch 16 — informational website entries.
    [
        'name' => 'Herkimer Home State Historic Site',
        'description' => 'Georgian-style mansion (c. 1764) in Little Falls, NY, the home of Revolutionary War General Nicholas Herkimer, with guided mansion tours, exhibits, and grounds along the Mohawk River.',
        'base_url' => 'https://parks.ny.gov/visit/historic-sites/herkimer-home-state-historic-site',
        'location' => 'Herkimer Home State Historic Site',
    ],
    [
        'name' => 'Brooklyn Commons at MetroTech',
        'description' => 'Downtown Brooklyn open-air park and campus at MetroTech Center, hosting 150+ free annual events including movie nights, fitness classes, fairs, and seasonal markets.',
        'base_url' => 'https://brooklyncommons.com',
        'location' => 'Brooklyn Commons Park',
    ],
    [
        'name' => 'Motto by Hilton NYC Chelsea',
        'description' => '374-room Hilton hotel at 113 W 24th Street with all-day Italian restaurant Lulla, two blocks from Madison Square Park.',
        'base_url' => 'https://www.hilton.com/en/hotels/nycdlua-motto-new-york-city-chelsea/',
        'location' => 'The Motto Chelsea by Hilton',
    ],
    [
        'name' => 'EVEN Hotel Times Square South',
        'description' => 'IHG wellness-focused hotel on West 35th Street with in-room fitness equipment, four blocks from Madison Square Garden / Penn Station.',
        'base_url' => 'https://www.ihg.com/evenhotels/hotels/us/en/new-york/nyctt/hoteldetail',
        'location' => 'EVEN Hotel Times Square South',
    ],
    [
        'name' => 'ATRA Form',
        'description' => 'Mexican design studio\'s Manhattan flagship at 43 Clarkson Street (former Vito Schnabel Gallery space) — collectible furniture, lighting, and the Morphus Experience Lab.',
        'base_url' => 'https://www.atraform.com',
        'location' => 'ATRA Form Gallery',
    ],
    [
        'name' => 'MUJI Fifth Avenue',
        'description' => 'MUJI\'s North America flagship at 475 5th Avenue (opened 2015) — three floors of household goods, stationery, clothing, and kitchen supplies, with workshops and brand events.',
        'base_url' => 'https://www.muji.com/us/flagship/fifth-avenue/',
        'location' => 'MUJI Fifth Avenue',
    ],

    // 2026-04-29 batch 17 — informational website entries.
    [
        'name' => 'SENTIENT Furniture',
        'description' => 'Brooklyn (Greenpoint) custom furniture studio and 25,000 sq ft workshop at 276 Greenpoint Avenue, with a gallery space used for design events.',
        'base_url' => 'https://sentientfurniture.com',
        'location' => 'SENTIENT Furniture',
    ],
    [
        'name' => 'Castle Hill YMCA',
        'description' => 'YMCA of Greater New York branch in the Bronx (the only NYC YMCA with an outdoor pool) — fitness equipment, indoor/outdoor pools, classes, and on-site child care.',
        'base_url' => 'https://ymcanyc.org/locations/castle-hill-ymca',
        'location' => 'Castle Hill YMCA',
    ],
    [
        'name' => 'Féau Boiseries',
        'description' => 'Paris atelier (founded 1875) specializing in historic wood paneling — 5th-floor showroom in NYC\'s D&D Building (979 3rd Avenue, opened Sept 2025) with seven rooms of period boiseries.',
        'base_url' => 'https://feauboiseries.com/en/',
        'location' => 'Féau Boiseries Showroom',
    ],
    [
        'name' => 'L\'Atelier Paris Haute Design',
        'description' => 'NYC showroom (80 Madison Avenue) for L\'Atelier Paris\'s custom French ranges and luxury kitchens — design consultations and trade events.',
        'base_url' => 'https://www.leatelierparis.com',
        'location' => 'L\'Atelier Paris Haute Design',
    ],
    [
        'name' => 'Porada NYC',
        'description' => 'Italian furniture brand Porada\'s first American flagship (NoMad, 185 Madison Avenue) — 400 m² showroom of immersive home zones from living to bedroom.',
        'base_url' => 'https://www.porada.it/en/',
        'location' => 'Porada NYC Showroom',
    ],
    [
        'name' => 'Bayswater Jewish Center',
        'description' => 'Conservative congregation (Congregation Darchay Noam) serving the Bayswater section of Far Rockaway, with daily minyans, Sabbath services, and community events.',
        'base_url' => 'https://www.angelfire.com/wy/bjcfr/home.html',
        'location' => 'Bayswater Jewish Center',
    ],
    [
        'name' => 'Ringolevio',
        'description' => 'East Williamsburg / Greenpoint Mediterranean restaurant and cafe (since 2014) at 490 Humboldt with handmade pastas and an adjoining lounge, FourFiveSix.',
        'base_url' => 'http://www.ringolevio.nyc',
        'location' => 'Ringolevio',
    ],
    [
        'name' => 'Chapin Hall (John J. Cali School of Music)',
        'description' => 'Original Montclair State University building (1908–1928), recently renovated to house the John J. Cali School of Music, hosting student and faculty performances.',
        'base_url' => 'https://www.montclair.edu/cali-school-music/',
        'location' => 'Chapin Hall (Montclair State)',
    ],
    [
        'name' => 'Steiny\'s Pub',
        'description' => 'Eclectic Staten Island neighborhood pub (since 2006) at 3 Hyatt Street, one block from the Staten Island Ferry.',
        'base_url' => 'https://www.steinys.pub',
        'location' => 'Steiny\'s Pub',
    ],
    [
        'name' => 'Carmen Pabon Del Amanecer Jardín',
        'description' => 'Lower East Side / Loisaida community garden founded by activist Carmen Pabón — reopened in 2016 after a 17-year fight, hosting performances, workshops, and the Harvest Arts Festival.',
        'base_url' => 'https://www.carmenpabongarden.org',
        'location' => 'Carmen\'s Garden',
    ],

    // 2026-04-29 batch 18 — informational website entries.
    [
        'name' => 'Apartment 5 (LES)',
        'description' => 'Lower East Side cocktail bar at 157 Ludlow Street with whimsical themed rooms, from the team behind The Little Shop in Seaport.',
        'base_url' => 'https://apt5ny.com',
        'location' => 'Apartment 5',
    ],
    [
        'name' => 'Abingdon Square Park (NYC Parks)',
        'description' => 'Triangular West Village park at the junction of Hudson, Bleecker, and 8th Avenue, host to the Saturday Abingdon Square Greenmarket and seasonal community events.',
        'base_url' => 'https://www.nycgovparks.org/parks/abingdon-square',
        'location' => 'Abingdon Square Park',
    ],
    [
        'name' => 'The Fleur Room (Moxy Chelsea)',
        'description' => 'Glass-encased rooftop lounge on the 35th floor of Moxy Chelsea (105 W 28th Street) with 360° Manhattan skyline views — 21+ all night.',
        'base_url' => 'https://moxychelsea.com/the-fleur-room-rooftop-bar-lounge/',
        'location' => 'The Fleur Room',
    ],
    [
        'name' => 'Impact Kitchen NoMad',
        'description' => 'NoMad flagship of the Toronto-founded Impact Kitchen at 1123 Broadway — gluten-free, refined-sugar-free, seed-oil-free menu of bowls, salads, sandwiches, and smoothies.',
        'base_url' => 'https://www.impactkitchen.com/locations',
        'location' => 'Impact Kitchen',
    ],
    [
        'name' => 'Pier 25 (Hudson River Park)',
        'description' => 'Tribeca\'s 985-foot Hudson River Park pier — Manhattan\'s only 18-hole mini golf, sand volleyball courts, water-feature playground, turf field, and small-boat moorings.',
        'base_url' => 'https://pier25.com',
        'location' => 'Pier 25 (Hudson River Park)',
    ],
    [
        'name' => 'Pier 84 (Hudson River Park)',
        'description' => 'Largest public pier in Hudson River Park (44th Street, opened 2006) with a water-themed playground, community garden, kayak launch, and seasonal restaurants.',
        'base_url' => 'https://hudsonriverpark.org/locations/pier-84/',
        'location' => 'Pier 84 (Hudson River Park)',
    ],
    [
        'name' => 'Allan H. Treman State Marine Park',
        'description' => 'NY State park on Cayuga Lake near Ithaca — one of the largest inland marinas in NY State with seasonal boat slips, dawn-to-dusk public access, and views of the Finger Lakes.',
        'base_url' => 'https://parks.ny.gov/parks/AllanTreman/',
        'location' => 'Allan H. Treman State Marine Park',
    ],
    [
        'name' => 'Stokes State Forest',
        'description' => 'NJ DEP state forest in Sandyston, Sussex County, with 63+ miles of trails leading to Sunrise Mountain, the Appalachian Trail, Tillman\'s Ravine, and Stepping Stones Falls.',
        'base_url' => 'https://dep.nj.gov/parksandforests/state-park/stokes-state-forest/',
        'location' => 'Stokes State Forest',
    ],
    [
        'name' => 'Hunters Point Community Middle School',
        'description' => 'NYC DOE public middle school in Long Island City (opened 2013) with partnerships including Cornell Tech and the Billion Oyster Project.',
        'base_url' => 'https://www.hunterspointcms.org',
        'location' => 'Hunters Point Community Middle School',
    ],

    // 2026-04-29 batch 19 — informational website entries.
    [
        'name' => 'World\'s Fair Marina (NYC Parks)',
        'description' => 'Public marina in Flushing Bay at the northern edge of Flushing Meadows–Corona Park, dating to the 1939 World\'s Fair, with seasonal slips and a 1.4-mile promenade.',
        'base_url' => 'https://www.nycgovparks.org/parks/flushing-meadows-corona-park/highlights/10392',
        'location' => 'World\'s Fair Marina',
    ],
    [
        'name' => 'Sports Illustrated Stadium',
        'description' => '25,000-seat Harrison, NJ stadium (formerly Red Bull Arena, renamed 2024) home to the New York Red Bulls (MLS) and Gotham FC (NWSL).',
        'base_url' => 'https://www.sportsillustratedstadium.com',
        'location' => 'Sports Illustrated Stadium',
    ],
    [
        'name' => 'Pennsylvania 6 NYC',
        'description' => 'Herald Square restaurant and sports bar at 132 W 31st Street steps from Madison Square Garden / Penn Station, with American comfort menu, craft cocktails, and weekend brunch.',
        'base_url' => 'http://www.pennsylvania6nyc.com',
        'location' => 'Pennsylvania 6',
    ],
    [
        'name' => 'Sanders Studios',
        'description' => 'Brooklyn (Clinton Hill) production and event space at 525 Waverly Avenue with four studios totaling 20,000+ sq ft, used for film, photo, and live events up to 300 people.',
        'base_url' => 'https://www.sandersstudiosbk.com',
        'location' => 'Sanders Studios',
    ],
    [
        'name' => 'Zatar Café & Bistro (Bushwick)',
        'description' => 'Bushwick Yemeni café and bistro on Myrtle Avenue serving traditional Yemeni cuisine and coffee — open daily until 1:45 AM.',
        'base_url' => 'https://zatar.nyc',
        'location' => 'Zatar Cafe & Bistro',
    ],
    [
        'name' => 'The Noodle Factory (LIC office building)',
        'description' => 'Long Island City office and warehouse loft building at 21-07 41st Avenue (the former Noodle Factory) housing creative tenants and event/workshop space.',
        'base_url' => 'https://noodlefactorylic.com',
        'location' => '21-07 41st Ave LIC',
    ],
    [
        'name' => 'CCNY Compton-Goethals Hall',
        'description' => 'Original 1930 City College building (combined Compton + Goethals into an H-plan structure) housing CCNY\'s Art and Theatre departments and the Compton-Goethals Gallery.',
        'base_url' => 'https://www.ccny.cuny.edu/theatre/comptongoethals',
        'location' => 'Compton-Goethals Hall (CCNY)',
    ],
    [
        'name' => 'CCNY North Academic Center',
        'description' => 'Main academic building at City College of New York at 160 Convent Avenue — houses the Cohen Library, multiple departments, and event spaces.',
        'base_url' => 'https://www.ccny.cuny.edu/education/about_us_nac_ccny',
        'location' => 'North Academic Center (CCNY)',
    ],

    // 2026-04-29 batch 20 — informational website entries.
    [
        'name' => 'The Corner Store BK',
        'description' => 'Crown Heights café and cocktail bar at 753 Nostrand Avenue serving brunch daily plus late-night food, wine, and cocktails Thursday–Sunday.',
        'base_url' => 'https://www.cornerstorebk.com',
        'location' => 'The Corner Store',
    ],
    [
        'name' => 'Half Hollow Hills Community Library',
        'description' => 'Suffolk County public library serving Dix Hills (main branch at 55 Vanderbilt Parkway) and Melville (510 Sweet Hollow Road), with programs for all ages.',
        'base_url' => 'https://www.hhhlibrary.org',
        'location' => 'Half Hollow Hills Community Library',
    ],
    [
        'name' => 'Allegria Hotel',
        'description' => 'Long Island\'s only oceanfront hotel — 156 rooms in Long Beach, NY, with rooftop infinity pool, Atlantica restaurant on the boardwalk, and event space.',
        'base_url' => 'https://www.allegriahotelny.com',
        'location' => 'Allegria Hotel',
    ],
    [
        'name' => 'Cornerstone Tavern',
        'description' => 'Midtown East sports bar at 961 2nd Avenue (51st Street) with 20 HD TVs, trivia and karaoke nights, and a private party space.',
        'base_url' => 'https://www.cornerstonetavern.com',
        'location' => 'Cornerstone Tavern',
    ],
    [
        'name' => 'Tappeto Volante',
        'description' => 'Brooklyn (Park Slope, 126 13th Street) contemporary art gallery and project space (since 2020) supporting underrepresented artists, performers, and emerging curators.',
        'base_url' => 'https://tappetovolantegallery.com',
        'location' => 'Tappeto Volante Gallery',
    ],
    [
        'name' => 'Frette Madison Avenue',
        'description' => 'Italian luxury linens flagship at 806 Madison Avenue (opened December 2023) — bedding, bath linens, loungewear, and accessories from Frette\'s collections since 1860.',
        'base_url' => 'https://www.frette.com/en_US/homepage',
        'location' => 'Frette Showroom',
    ],
    [
        'name' => 'Costantini Design',
        'description' => 'Custom luxury furniture and lighting atelier (since 2002) with showroom in the West Chelsea Arts Building (526 W 26th Street), open by appointment.',
        'base_url' => 'https://www.costantinidesign.com',
        'location' => 'Costantini',
    ],
    [
        'name' => 'Organic Erotic',
        'description' => 'Curated home and lifestyle store with a warehouse showroom at 2277 3rd Avenue in East Harlem, focusing on sustainable, organic, and adult-leaning home goods.',
        'base_url' => 'https://www.organicerotic.com',
        'location' => 'Organic Erotic',
    ],
    [
        'name' => 'Morningside Monthly Meeting',
        'description' => 'Quaker meeting (Religious Society of Friends) gathering on the 12th floor of Riverside Church\'s bell tower (Upper West Side / Morningside Heights) for hybrid Sunday worship.',
        'base_url' => 'https://morningsidemeeting.org',
        'location' => 'Morningside Meeting',
    ],
    [
        'name' => 'The Battery Labyrinth',
        'description' => 'Public meditation labyrinth in The Battery (Lower Manhattan), built in 2002 to honor 9/11 — 1,148 Belgian-block circular path in a grove of cedar trees.',
        'base_url' => 'https://www.thebattery.org/destinations/labyrinth/',
        'location' => 'Battery Labyrinth',
    ],
    [
        'name' => 'Londel\'s Restaurant',
        'description' => 'Harlem supper club on Frederick Douglass Boulevard near Striver\'s Row (since 1994) serving Southern, Cajun, and Continental cuisine with live music on weekends.',
        'base_url' => 'https://www.londelsrestaurant.com',
        'location' => 'Londel\'s Supper Club',
    ],

    // 2026-04-29 batch 21 — informational website entries.
    [
        'name' => 'Aloft Harlem',
        'description' => 'Marriott\'s Aloft Harlem at 2296 Frederick Douglass Boulevard — 124 loft-style rooms, the re:mix lounge, and the w xyz bar steps from the Apollo Theater.',
        'base_url' => 'https://www.marriott.com/en-us/hotels/nyclh-aloft-harlem/overview/',
        'location' => 'Aloft Harlem',
    ],
    [
        'name' => 'Go Hard Dance Studio',
        'description' => 'Women-owned, community-based dance studio in Harlem (2307 Adam Clayton Powell Jr Blvd) offering hip-hop, tap, African dance, ballet, and adult dance fitness classes.',
        'base_url' => 'https://www.goharddancenyc.com',
        'location' => 'Go Hard Dance Studio',
    ],
    [
        'name' => 'Heavy Woods',
        'description' => 'Bushwick bar (since 2012) at 50 Wyckoff Avenue serving cocktails, rotating drafts, and New Orleans-inspired bites via the in-house Tchoup Shop pop-up.',
        'base_url' => 'https://www.heavywoodsbar.com',
        'location' => 'Heavy Woods',
    ],
    [
        'name' => 'WatchHouse 5th Avenue',
        'description' => 'WatchHouse\'s first US location (2024) — a London specialty coffee brand at 660 5th Avenue, Midtown, transitioning from coffee/pastries by day to cocktails and bites at night.',
        'base_url' => 'https://watchhouse.com/en-us/blogs/locations/watchhouse-5th-ave',
        'location' => 'WatchHouse 5th Ave',
    ],
    [
        'name' => 'Greenspace on Fourth',
        'description' => 'Park Slope (207 4th Avenue) NYC Parks GreenThumb community garden and environmental center focused on native plants, with a rain harvesting system, rain garden, and community composting.',
        'base_url' => 'https://greenspaceon4th.org',
        'location' => '207 4th Ave Brooklyn',
    ],
    [
        'name' => 'Clinton Community Garden',
        'description' => 'Hell\'s Kitchen community garden (since 1978) on West 48th Street — the first NYC community garden granted permanent parkland status (1984).',
        'base_url' => 'https://clintongarden.org',
        'location' => 'Clinton Community Garden',
    ],
    [
        'name' => 'UN Plaza Grill',
        'description' => 'Kosher steak-and-sushi restaurant on the ground floor of UN Plaza (845 United Nations Plaza), Midtown East — 40-foot floor-to-ceiling windows overlooking the United Nations.',
        'base_url' => 'https://unplazagrill.com',
        'location' => 'UN Plaza Grill',
    ],
    [
        'name' => 'St. Paul\'s Evangelical Lutheran Church (Jersey City)',
        'description' => 'Jersey City ELCA congregation (founded 1884) at 440 Hoboken Avenue, home to The Sharing Place — one of Hudson County\'s oldest and largest food pantries.',
        'base_url' => 'https://www.stpauljerseycity.org',
        'location' => 'St. Paul\'s Lutheran Church Jersey City',
    ],
    [
        'name' => 'Jersey City Free Public Library — Pavonia',
        'description' => 'Jersey City Free Public Library\'s Pavonia branch in the Hamilton Park area at 326 Eighth Street, hosting community programs and events.',
        'base_url' => 'https://jclibrary.org/branch/pavonia-branch/',
        'location' => 'Jersey City Free Public Library',
    ],

    // 2026-04-29 batch 22 — informational website entries.
    [
        'name' => 'Azal Coffee',
        'description' => 'Forest Hills Yemeni coffee shop on 71st Avenue serving Yemeni and Middle Eastern coffees, Adeni tea, lattes, matcha, and pastries — open daily until 11:30 PM.',
        'base_url' => 'https://azalcoffeeusa.com/locations/flushing',
        'location' => 'Azal Coffee',
    ],
    [
        'name' => 'The French Workshop',
        'description' => 'Bayside artisan bakery and café on Bell Boulevard (since 2015) — croissants, pastries, cakes, sandwiches, and coffee, with sister locations across Long Island and Astoria.',
        'base_url' => 'https://www.thefrenchworkshop.com',
        'location' => 'The French Workshop',
    ],
    [
        'name' => 'John F. Murray Playground',
        'description' => 'Long Island City NYC Parks playground (45th Avenue / 21st Street) with a synthetic turf field, dog run, lawn performance area, and children\'s playground.',
        'base_url' => 'https://www.nycgovparks.org/parks/murray-playground',
        'location' => 'John Murray Park',
    ],
    [
        'name' => 'Crystal Lake Brooklyn',
        'description' => 'Williamsburg cocktail bar and event space at 647 Grand Street with a private back room (projector, sound, lighting, dance floor) for parties, screenings, and weddings.',
        'base_url' => 'https://www.crystallakebrooklyn.com',
        'location' => 'Crystal Lake',
    ],
    [
        'name' => 'Mombar',
        'description' => 'Astoria Egyptian restaurant on Steinway Street\'s "Little Egypt" block — chef-owner Mustafa El Sayed\'s eclectic, BYOB spot famous for lamb shank, tagines, and personal hospitality.',
        'base_url' => 'https://mombar.netwaiter.com/astoria/about/',
        'location' => 'Mombar',
    ],
    [
        'name' => 'Andrew Bellucci\'s Pizzeria',
        'description' => 'Astoria pizzeria at 37-08 30th Avenue from veteran pizza chef Andrew Bellucci — classic NYC pies and slices, traditional pasta, and the signature "Life-Changing" fresh-clam pizza.',
        'base_url' => 'https://andrewbelluccispizzeria.com',
        'location' => 'Andrew Bellucci\'s Pizzeria',
    ],
    [
        'name' => 'Amazon Go (Brookfield Place)',
        'description' => 'Cashier-less Amazon Go convenience store on Level 2 of Brookfield Place (Battery Park City) — grab-and-go meals, snacks, espresso, and pastries, open daily 7AM–8PM.',
        'base_url' => 'https://www.bfplny.com/food-drink/amazon-go/',
        'location' => 'Amazon Go - Brookfield Place',
    ],
    [
        'name' => 'New Haven Pride Center',
        'description' => 'New Haven, CT LGBTQIA+ community center (founded 1996) at 50 Orange Street offering case management, a food pantry, affinity groups, and arts/community programming.',
        'base_url' => 'https://www.newhavenpridecenter.org',
        'location' => 'New Haven Pride Center',
    ],

    // 2026-04-29 batch 23 — informational website entries.
    [
        'name' => 'Stumptown Coffee Roasters (Greenwich Village)',
        'description' => 'Stumptown Coffee\'s Greenwich Village café at 30 W 8th Street (in the former Eighth Street Bookshop) — espresso, cold brew, Spirit Tea drinks, pastries, and breakfast tacos.',
        'base_url' => 'https://www.stumptowncoffee.com/pages/new-york-greenwich-village-cafe',
        'location' => 'Stumptown Coffee Roasters (Outside)',
    ],
    [
        'name' => 'Shirokuro NYC',
        'description' => 'East Village 2D omakase restaurant at 103 Second Avenue — Manhattan\'s first black-and-white "two-dimensional" interior, opened 2025.',
        'base_url' => 'https://shirokuronyc.com',
        'location' => 'Shirokuro',
    ],
    [
        'name' => 'Stuyvesant High School',
        'description' => 'NYC DOE specialized public high school at 345 Chambers Street in Battery Park City (since 1992), with a community center used for evening classes and events.',
        'base_url' => 'http://www.stuy.edu',
        'location' => 'Stuyvesant High School',
    ],
    [
        'name' => 'Teardrop Park (BPCA)',
        'description' => 'Battery Park City landscape garden by Michael Van Valkenburgh (opened 2004) with rock formations, lush plantings, a small amphitheater, and water-play features.',
        'base_url' => 'https://bpca.ny.gov/place/teardrop-park/',
        'location' => 'Teardrop Park',
    ],
    [
        'name' => 'Rector Park East (BPCA)',
        'description' => 'Battery Park City park along Rector Place, hosting BPCA programming including birding walks and seasonal nature events.',
        'base_url' => 'https://bpca.ny.gov/venue/rector-park-east/',
        'location' => 'Rector Park East',
    ],
    [
        'name' => 'Irish Hunger Memorial',
        'description' => '0.5-acre Battery Park City memorial (dedicated 2002) at North End Avenue and Vesey Street — an authentic roofless Irish cottage, native plants, and limestone from all 32 counties of Ireland.',
        'base_url' => 'https://bpca.ny.gov/venue/irish-hunger-memorial/',
        'location' => 'Irish Hunger Memorial Plaza',
    ],
    [
        'name' => 'Montclair Brewery',
        'description' => 'Husband-and-wife-owned Montclair, NJ microbrewery and tasting room at 101 Walnut Street with African and Caribbean-influenced craft beers, indoor taproom, and outdoor beer garden.',
        'base_url' => 'https://www.montclairbrewery.com',
        'location' => 'Montclair Brewing',
    ],
    [
        'name' => 'Armageddon Brewing',
        'description' => 'Somerdale, NJ producer of hard ciders and meads at 900 Chestnut Avenue — small-batch fermentation with a tasting room and events.',
        'base_url' => 'https://www.armageddon-brewing.com',
        'location' => 'Armageddon Brewing',
    ],
    [
        'name' => 'Stratosphere Brewing Company',
        'description' => 'Mount Holly, NJ micro-brewery (since March 2023) at 72 Washington Street offering craft brews and community gathering events in Burlington County.',
        'base_url' => 'https://stratospherebrewingcompany.com',
        'location' => 'Stratosphere Brewing',
    ],

    // 2026-04-29 batch 24 — informational website entries.
    [
        'name' => 'Bonesaw Brewing Co.',
        'description' => 'NJ craft brewery — the Pilot House at the Deptford Mall is Bonesaw\'s second location, an 8,000 sq ft taproom focused on small-batch "pilot" recipes alongside flagship beers.',
        'base_url' => 'https://www.bonesawbrewing.com',
        'location' => 'Bonesaw\'s Pilot House',
    ],
    [
        'name' => 'Fort Nonsense Brewing Company',
        'description' => 'Family-run Morris County, NJ craft brewery and beer garden in Randolph (founded 2018, moved 2021) offering ales, lagers, and hard seltzers in a community-vibe taproom.',
        'base_url' => 'https://www.fortnonsensebrewing.com',
        'location' => 'Fort Nonsense Brewing',
    ],
    [
        'name' => 'Diamond Spring Brewing Co.',
        'description' => 'Denville, NJ craft brewery in a 1960s service-station building at 50 Broadway, with a downtown taproom and 6,000 sq ft beer garden.',
        'base_url' => 'https://diamondspringbrewing.com',
        'location' => 'Diamond Spring Brewing',
    ],
    [
        'name' => 'Alternate Ending Beer Co.',
        'description' => 'Aberdeen, NJ craft brewery and restaurant in a former Bow Tie Cinemas — thoughtful beer, gourmet food by Talula\'s, and classic-movie screenings.',
        'base_url' => 'https://www.alternateendingbeerco.com',
        'location' => 'Alternate Ending Beer Co.',
    ],
    [
        'name' => 'Whims Brewing',
        'description' => 'Atco, NJ craft brewery focused on expressive yeasts, mixed-fermentation beers, wood aging, and beers that highlight fruit, herbs, and flowers.',
        'base_url' => 'https://www.whimsbrewing.com',
        'location' => 'Whims Brewing',
    ],
    [
        'name' => 'Conclave Brewing',
        'description' => 'Flemington, NJ craft brewery (since 2015, expanded 2019) at 11 Minneakoning Road making distinctive, style-bending beers.',
        'base_url' => 'https://www.conclavebrewing.com',
        'location' => 'Conclave Brewing',
    ],
    [
        'name' => 'Raccoon Taproom (Swedesboro Brewing Co.)',
        'description' => 'Collingswood, NJ taproom (opened June 2024) of Swedesboro Brewing Co. at 1 Powell Lane, with a rotating selection of Swedesboro brews.',
        'base_url' => 'https://www.raccoontaproom.com',
        'location' => 'Raccoon Taproom',
    ],
    [
        'name' => 'Axe & Arrow Brewing',
        'description' => 'Glassboro Town Square 7-barrel craft brewery and tasting room (since April 2019) — BYO-food-friendly with garage parking validation.',
        'base_url' => 'https://axeandarrowbrewing.com',
        'location' => 'Axe & Arrow Brewing',
    ],
    [
        'name' => 'SPIN New York Midtown',
        'description' => 'Susan Sarandon\'s ping-pong social club\'s Times Square flagship at 1626 Broadway (in the former Carolines on Broadway space) with a full bar and 10+ Olympic tables.',
        'base_url' => 'https://wearespin.com/location/new-york-midtown/',
        'location' => 'SPIN Midtown',
    ],
    [
        'name' => 'Liberty Inn',
        'description' => 'Meatpacking District short-stay hotel at 51 10th Avenue (between 13th and 14th Streets) — intimate rooms with in-room jacuzzis, hourly and overnight stays.',
        'base_url' => 'https://libertyinnnyc.com',
        'location' => 'Liberty Inn',
    ],

    // 2026-04-29 batch 25 — informational website entries.
    [
        'name' => 'Stout NYC (Grand Central)',
        'description' => 'Stout NYC\'s Grand Central location at 60 East 41st Street (steps from Grand Central Terminal) — Irish pub, restaurant, and event space.',
        'base_url' => 'https://www.stoutnyc.com',
        'location' => 'Stout at Grand Central',
    ],
    [
        'name' => 'Starbucks Court Street (Brooklyn)',
        'description' => 'Starbucks branch at 50 Court Street in Downtown Brooklyn, frequently used as a meetup point for guided walks and singles events.',
        'base_url' => 'https://www.starbucks.com/store-locator/',
        'location' => 'Starbucks Court Street',
    ],
    [
        'name' => 'nosh! at Courtyard Times Square',
        'description' => 'Bistro at the Courtyard by Marriott New York Manhattan/Times Square (114 W 40th Street) — light breakfast, dinner, bar menu, and Starbucks coffee, used for hotel meetings.',
        'base_url' => 'https://www.marriott.com/en-us/dining/restaurant-bar/nycmd-courtyard-new-york-manhattan-times-square/75547-nosh.mi',
        'location' => 'Nosh @ The Courtyard Marriott',
    ],
    [
        'name' => 'Mamali NYC',
        'description' => 'All-day Georgian café and wine bar in the West Village (70 Christopher Street, in the former Village Cigars space) serving khachapuri, dumplings, coffee, and Georgian wine.',
        'base_url' => 'https://mamalinyc.com',
        'location' => 'Mamali',
    ],
    [
        'name' => '55 Washington Street (Two Trees DUMBO)',
        'description' => 'DUMBO 1905 manufacturing-loft building (now Two Trees-managed offices) housing Etsy headquarters and Gleason\'s Gym, hosting community talks and tenant events.',
        'base_url' => 'https://www.twotreesny.com/office-spaces/55-washington',
        'location' => '55 Washington Street',
    ],
    [
        'name' => 'AvaBrew by Oren\'s Coffee',
        'description' => 'Downtown Brooklyn café (100 Willoughby Street, AVA Dobro lobby) powered by Oren\'s Coffee — specialty coffee and local artisan pastries, open daily 8am–3pm.',
        'base_url' => 'https://orenscoffee.com/locations/',
        'location' => 'AvaBrew by Oren\'s Coffee',
    ],
    [
        'name' => 'Dive 75',
        'description' => 'Upper West Side dive bar (since 1998) at 101 W 75th Street with 30 craft taps, two cask-conditioned taps, late-night kitchen, board games, and a fish tank.',
        'base_url' => 'https://dive75.divebarnyc.com',
        'location' => 'Dive 75',
    ],
    [
        'name' => 'Brooklyn Public Library — Central',
        'description' => 'Brooklyn Public Library\'s Central Library at Grand Army Plaza (opened 1941) — Art Deco landmark designed to resemble an open book, with major collections, classes, and events.',
        'base_url' => 'https://www.bklynlibrary.org/locations/central',
        'location' => 'Central Library',
    ],

    // 2026-04-29 batch 26 — informational website entries.
    [
        'name' => 'Hyatt Place Flushing / LaGuardia Airport',
        'description' => '168-room Flushing hotel atop a glass-fronted retail and dining complex, with a rooftop garden lounge featuring Manhattan skyline views — minutes from LaGuardia and Citi Field.',
        'base_url' => 'https://www.hyatt.com/hyatt-place/en-US/nyczf-hyatt-place-flushing-laguardia-airport',
        'location' => 'Hyatt Place Flushing/LaGuardia Airport',
    ],
    [
        'name' => 'The Four-Faced Liar',
        'description' => 'Traditional Irish pub at 165 West 4th Street in the West Village — a welcoming neighborhood spot known as a transgender / LGBTQ+ safe space and for properly-pulled Guinness.',
        'base_url' => 'http://www.thefour-facedliar.com',
        'location' => 'The Four-Faced Liar',
    ],
    [
        'name' => 'Williamsburg, Brooklyn (Wikipedia)',
        'description' => 'Wikipedia article on the Williamsburg neighborhood of Brooklyn.',
        'base_url' => 'https://en.wikipedia.org/wiki/Williamsburg,_Brooklyn',
        'location' => 'Williamsburg',
    ],
    [
        'name' => 'Bust of Sylvette (NYU)',
        'description' => 'NYU\'s 36-foot Pablo Picasso–Carl Nesjar sculpture (1968) in the Silver Towers courtyard between Bleecker and Houston — one of only two outdoor Picasso sculptures in the Western Hemisphere.',
        'base_url' => 'https://www.nyu.edu/life/arts-culture-and-entertainment/galleries/galleries-and-sites/bust-of-sylvette.html',
        'location' => 'Bust of Sylvette Plaza',
    ],
    [
        'name' => 'Diana Ross Playground',
        'description' => 'Central Park playground at West 81st Street and Central Park West, named for Diana Ross (who funded its construction after her 1983 Great Lawn concert) — climbing structures, swings, water-spray.',
        'base_url' => 'https://www.centralparknyc.org/locations/diana-ross-playground',
        'location' => 'Diana Ross Playground',
    ],
    [
        'name' => 'Brooklyn (borough) (Wikipedia)',
        'description' => 'Wikipedia article on the borough of Brooklyn, NYC.',
        'base_url' => 'https://en.wikipedia.org/wiki/Brooklyn',
        'location' => 'Brooklyn (borough)',
    ],
    [
        'name' => 'Herbwell Cannabis (Madison Ave)',
        'description' => 'Herbwell Cannabis\'s Manhattan Midtown dispensary at 519 Madison Avenue — premium flower, pre-rolls, edibles, concentrates, and events.',
        'base_url' => 'https://herbwellcannabis.com',
        'location' => 'Herbwell Cannabis (Madison Ave)',
    ],

    // 2026-04-29 batch 27 — informational website entries.
    [
        'name' => 'East 35th Street Ferry Terminal (NYC Ferry)',
        'description' => 'East River ferry terminal on the FDR at East 35th Street served by NYC Ferry (East River route) and Seastreak (NJ commuter ferries).',
        'base_url' => 'https://www.ferry.nyc/routes-and-schedules/east-river/',
        'location' => 'East 35th Street Ferry Terminal',
    ],
    [
        'name' => 'Port Authority Bus Terminal',
        'description' => 'World\'s busiest bus terminal at 625 Eighth Avenue (Midtown Manhattan) — operated by the Port Authority of NY & NJ, serving ~225,000 commuters and 8,000 bus departures daily.',
        'base_url' => 'https://www.panynj.gov/bus-terminals/en/port-authority.html',
        'location' => 'Port Authority Bus Terminal',
    ],
    [
        'name' => 'Mink Hollow Trail (NY DEC)',
        'description' => '5.3-mile blue-blazed Catskills hiking trail in Indian Head Wilderness connecting Mink Hollow Road to the Devils Path — accessed from a DEC parking lot near West Kill, NY.',
        'base_url' => 'https://dec.ny.gov/places/indian-head-wilderness',
        'location' => 'Mink Hollow Trail Head',
    ],
    [
        'name' => 'Emma Peel Room',
        'description' => 'Lower East Side neighborhood bar at 266 Broome Street (formerly RPM Bar) — beer, wine, cocktails, and outdoor seating including a fenced street patio and back garden.',
        'base_url' => 'https://hellorpm.com',
        'location' => 'Emma Peel Room',
    ],
    [
        'name' => 'The Bedford Stone Street',
        'description' => 'Maritime-inspired gastropub and cocktail bar on Stone Street (55 Stone Street, Financial District) — sibling to The Bedford Brooklyn, with elevated bar food and oysters.',
        'base_url' => 'https://www.thebedford.nyc/stone-street',
        'location' => '55 Stone St',
    ],
    [
        'name' => 'HAGS',
        'description' => 'Queer-owned, queer-first East Village fine-dining restaurant at 163 First Avenue — chef Telly Justice and sommelier Camille Lindsley\'s tasting-menu spot (MICHELIN Young Chef Award 2023).',
        'base_url' => 'https://hagsnyc.com',
        'location' => 'HAGS',
    ],
    [
        'name' => 'Caravan Uyghur Cuisine',
        'description' => 'Family-owned Financial District restaurant at 60 Beaver Street serving authentic Uyghur cuisine — hand-pulled noodles, hearty stews, and flavorful kebabs.',
        'base_url' => 'https://www.caravanuyghur.com',
        'location' => 'Caravan Uyghur Cuisine',
    ],
    [
        'name' => 'Serendipity 3',
        'description' => 'Iconic Upper East Side restaurant (since 1954) at 225 East 60th Street — home of the Frrrozen Hot Chocolate (made with a secret blend of 14 exotic cocoas).',
        'base_url' => 'https://serendipity3.com',
        'location' => 'Serendipity 3',
    ],

    // 2026-04-29 batch 28 — informational website entries.
    [
        'name' => 'ASSAIA Restaurant Club & Lounge',
        'description' => 'Brooklyn (Bath Beach) Georgian fine-dining restaurant at 2158 Bath Avenue with a club and lounge — also functioning as a private event venue.',
        'base_url' => 'https://www.assaia.us',
        'location' => 'ASSAIA Restaurant Club & Lounge',
    ],
    [
        'name' => 'Welcome Home (Bed-Stuy)',
        'description' => 'Bed-Stuy bakery (1047 Bedford Avenue) named "Bakery of the Year" by the New York Times — sourdough loaves, croissants, cinnamon rolls, and pastries.',
        'base_url' => 'https://welcomehomebrooklyn.com',
        'location' => 'Welcome Home Bakery',
    ],
    [
        'name' => 'Piragua Art Space',
        'description' => 'East Village community arts space and gallery at 367 East 10th Street — pop-ups, exhibitions, screenings, intimate performances, plus rehearsal and meeting space.',
        'base_url' => 'https://dasoentertainment.com/piragua',
        'location' => 'Piragua Art Space',
    ],
    [
        'name' => 'Nassau Avenue Gallery',
        'description' => 'Greenpoint, Brooklyn art gallery (123 Nassau Avenue, opened 2025) showcasing local NYC-based artists with originals and prints — open Wed–Sun, 11–7.',
        'base_url' => 'https://nassauavenuegallery.square.site',
        'location' => 'Nassau Avenue Gallery',
    ],
    [
        'name' => 'MTA New York City Subway',
        'description' => 'NYC subway system operated by the Metropolitan Transportation Authority — used here as an event meetup spot at the 51st Street station (Lexington Ave / E 51st St).',
        'base_url' => 'https://new.mta.info/',
        'location' => 'MTA - 51st Street station',
    ],
    [
        'name' => 'Molasses Books',
        'description' => 'Bushwick used bookstore and bar (since 2012) at 770 Hart Street — curated used books, free Wi-Fi, coffee/tea/wine, and events including readings and DJ nights.',
        'base_url' => 'https://www.molassesbooks.org',
        'location' => 'Molasses Books',
    ],

    // 2026-04-29 batch 29 — informational website entries.
    [
        'name' => 'Milk and Roses',
        'description' => 'Greenpoint, Brooklyn restaurant (35 Box Street) serving American cuisine with Southern Italian influence — boutique wines, craft beer, classic cocktails, and a spacious garden.',
        'base_url' => 'https://milkandrosesbk.com',
        'location' => 'Milk and Roses',
    ],
    [
        'name' => 'Ke-nee-go-keshek Fine Art Workshop',
        'description' => 'Atelier of Konstance Patton Ke-nee-go-keshek, an award-winning Indigenous American (Little River Band of Ottawa) artist — open studios and Sculpture/mural workshops for artists of all ages.',
        'base_url' => 'https://www.instagram.com/keneegokeshekstudio/',
        'location' => 'Ke-nee-go-keshek Fine Arts Workshop',
    ],
    [
        'name' => 'Kalā Yoga (Bushwick)',
        'description' => 'Brooklyn (Bushwick) yoga studio at 331 Melrose Street with heated and non-heated yoga, pilates, strength classes, workshops, and teacher training.',
        'base_url' => 'https://www.kalayogabk.com',
        'location' => 'Kala Yoga',
    ],
    [
        'name' => 'Greenwich Village Comedy Club',
        'description' => 'Hip, intimate Greenwich Village comedy club at 99 MacDougal Street featuring nationally known comedians (Netflix, Comedy Central, Amazon) plus surprise drop-ins.',
        'base_url' => 'https://www.greenwichvillagecomedyclub.com',
        'location' => 'Greenwich Village Comedy Club',
    ],
    [
        'name' => 'DUMBO Archway & Plaza',
        'description' => 'Public plaza under the Manhattan Bridge in DUMBO (Water Street between Anchorage Place and Adams Street) hosting Brooklyn Flea, the Brooklyn Americana Music Festival, DUMBO Disco, and projection art.',
        'base_url' => 'https://dumbo.nyc/public-spaces/',
        'location' => 'Dumbo Archway Plaza',
    ],
    [
        'name' => 'CrossFit Wall Street',
        'description' => 'Financial District CrossFit gym at 60 New Street offering CrossFit classes, Olympic lifting, and personal training for beginners and competitive athletes.',
        'base_url' => 'https://www.crossfitwallstreet.com',
        'location' => 'CrossFit Wall Street',
    ],
    [
        'name' => 'The Table New York',
        'description' => 'NYC event styling, creative direction, and production company at 64 Allen Street #4A, hosting curated dinners and creative-industry events.',
        'base_url' => 'http://www.thetablenewyork.com',
        'location' => 'The Table New York',
    ],

    // 2026-04-29 batch 30 — informational website entries.
    [
        'name' => 'Vondom New York Showroom',
        'description' => 'Spanish luxury outdoor furniture brand\'s NYC flagship showroom (175 Madison Avenue, NoMad Design District) — 2,500 sq ft of indoor/outdoor design pieces.',
        'base_url' => 'https://www.vondom.com/us/',
        'location' => 'Vondom',
    ],
    [
        'name' => 'Vitra New York Showroom',
        'description' => 'Vitra/Artek\'s NYC showroom (46 Bowery, 3rd Floor — opened May 2025 in the former Jing Fong dim sum space) with public showroom, offices, and event space overlooking the Manhattan Bridge.',
        'base_url' => 'https://www.vitra.com/en-us/about-vitra/facts/contacts',
        'location' => 'Vitra',
    ],
    [
        'name' => 'Twenty First Gallery',
        'description' => 'Tribeca collectible-design gallery (76 Franklin Street, since 2007) presenting one-of-a-kind and limited-edition contemporary European functional art.',
        'base_url' => 'https://21stgallery.com',
        'location' => 'Twenty First Gallery',
    ],
    [
        'name' => 'Twelve Chairs Gallery',
        'description' => 'Williamsburg art gallery in The Mill Building (101-85 N 3rd Street, Suite 108) presenting figurative artists who merge classical training with contemporary vision, plus a sculpture garden on Wythe Avenue.',
        'base_url' => 'https://twelvechairsgallery.com',
        'location' => 'Twelve Chairs Gallery',
    ],
    [
        'name' => 'Tokio7',
        'description' => 'East Village luxury vintage and designer consignment store at 83 East 7th Street (3,000 sq ft) — second-hand designer clothing, shoes, and accessories.',
        'base_url' => 'https://tokio7ny.com',
        'location' => 'Tokio.',
    ],
    [
        'name' => 'TOAST',
        'description' => 'Toast Inc.\'s New York office (22 W 21st Street, 7th Floor, Flatiron) — restaurant-tech company, occasionally hosts industry gatherings and partner events.',
        'base_url' => 'https://careers.toasttab.com/blogs/life-at-toast/toast-in-the-big-apple',
        'location' => 'TOAST',
    ],
    [
        'name' => 'TM Italia New York',
        'description' => 'TM Italia\'s 1,200 sq ft Flatiron Design District showroom (20 W 20th Street, Suite 502) — Italian bespoke-kitchen atelier with three kitchen concepts on display by appointment.',
        'base_url' => 'https://newyork.tmitalia.com',
        'location' => 'TM ITALIA SRL',
    ],

    // 2026-04-29 batch 31 — informational website entries.
    [
        'name' => 'ThoughtMatter',
        'description' => 'Independent Flatiron creative studio (19 W 24th Street, 5th Floor) — branding and design firm, winner of the 2026 Cooper Hewitt National Design Award for Communication Design.',
        'base_url' => 'https://www.thoughtmatter.com',
        'location' => 'Thought Matter',
    ],
    [
        'name' => 'The One Club for Creativity',
        'description' => 'International nonprofit promoting creative excellence in advertising and design — host of the One Show, ADC Annual Awards, and Young Ones Student Awards (450 W 31st St, Floor 6).',
        'base_url' => 'https://www.oneclub.org',
        'location' => 'The One Club for Creativity',
    ],
    [
        'name' => 'TenBerke',
        'description' => 'NYC architecture and interior design firm (formerly Deborah Berke Partners), founded by Yale School of Architecture Dean Deborah Berke — 41 Madison Avenue, 17th Floor.',
        'base_url' => 'https://tenberke.com',
        'location' => 'TenBerke',
    ],
    [
        'name' => 'Technogym New York (SoHo)',
        'description' => 'Italian premium fitness brand\'s SoHo flagship at 380 West Broadway — 3,000 sq ft, two-story showroom, education center, and retail space focused on Wellness Lifestyle.',
        'base_url' => 'https://www.technogym.com/en-US/technogym-new-york/',
        'location' => 'Technogym',
    ],
    [
        'name' => 'Surfaces & Co. USA',
        'description' => 'Flatiron showroom (19 W 21st Street, Suite 204) of Surfaces & Co., a luxury surfaces, fittings, and accessories brand for kitchen and bath (NYC location opened 2024).',
        'base_url' => 'https://www.surfacesco.us',
        'location' => 'Surfaces & Co.',
    ],
    [
        'name' => 'Sea, New York',
        'description' => 'NYC fashion brand by childhood friends Sean Monahan and Monica Paolini — distinctive lace, embroidery, knits, and technical fabrics; Meatpacking flagship at 835 Washington Street.',
        'base_url' => 'https://sea-ny.com',
        'location' => 'Sea New York',
    ],
    [
        'name' => 'Sculpture Space NYC',
        'description' => 'Long Island City Center for Art & Ceramics (47-21 35th Street) offering classes, residencies, and exhibitions — public hours Wednesday evenings and weekends.',
        'base_url' => 'https://www.sculpturespacenyc.com',
        'location' => 'Sculpture Space',
    ],
    [
        'name' => 'SCAPE Landscape Architecture',
        'description' => 'Award-winning landscape architecture and urban design studio (277 Broadway, 9th Floor) led by MacArthur Fellow Kate Orff — 80+ landscape architects, planners, and ecologists.',
        'base_url' => 'https://www.scapestudio.com',
        'location' => 'SCAPE',
    ],
    [
        'name' => 'Salvatori New York',
        'description' => 'Italian marble and natural stone brand\'s SoHo flagship (102 Wooster Street, opened 2023) — 6,400 sq ft Yabu Pushelberg-designed showroom with themed home settings.',
        'base_url' => 'https://www.salvatoriofficial.com/en-us/us/showroom/salvatori-new-york/',
        'location' => 'Salvatori Inc',
    ],
    [
        'name' => 'Roca Tile Studio NYC',
        'description' => 'Spanish tile brand Roca Tile USA\'s Flatiron design studio at 18 W 21st Street showcasing the full Roca tile catalog for designers and consumers.',
        'base_url' => 'https://rocatileusa.com/design-new-york',
        'location' => 'Roca Tile USA',
    ],
    [
        'name' => 'Radnor',
        'description' => 'Furniture gallery and workshop founded by designer Susan Clark (2016) — Carnegie Hill showroom in Sutton Tower (180 E 88th St) presenting curated lighting, furniture, and Radnor Made / Represented collections.',
        'base_url' => 'https://www.radnor.co',
        'location' => 'Radnor',
    ],
    [
        'name' => 'Pierre Yovanovitch (New York)',
        'description' => 'French interior designer Pierre Yovanovitch\'s 10,000 sq ft Chelsea penthouse showroom and gallery (555 W 25th Street, 6th Floor) — first US showroom, opened 2023.',
        'base_url' => 'https://www.pierreyovanovitch.com/en/new-york-gallery/',
        'location' => 'Pierre Yovanovitch',
    ],

    // 2026-04-29 batch 32 — informational website entries (NYCxDESIGN showrooms).
    [
        'name' => 'Par Excellence New York',
        'description' => 'NoHo French craftsmanship collective showroom at 344 Bowery — Charles Jouffre\'s 12-artisan group, with a Thomas Pheasant–designed gallery showcasing custom furniture, lighting, and decorative arts.',
        'base_url' => 'https://www.parexcellenceny.com',
        'location' => 'Par Excellence',
    ],
    [
        'name' => 'Minotti New York (by ddc)',
        'description' => 'Italian furniture brand Minotti\'s NYC flagship at 134 Madison Avenue, operated in partnership with the DDC Group — sophisticated contemporary collections in an immersive showroom.',
        'base_url' => 'https://www.minottibyddc.com',
        'location' => 'Minotti by ddc',
    ],
    [
        'name' => 'Michele Varian Shop',
        'description' => 'Boerum Hill home-goods shop at 400 Atlantic Avenue (since 2001, moved to Brooklyn 2020) — handmade and locally sourced textiles, pillows, wallpaper, lighting, and 100+ guest designers.',
        'base_url' => 'https://michelevarian.com',
        'location' => 'Michele Varian',
    ],
    [
        'name' => 'Make A Frame Atlantic',
        'description' => 'Brooklyn (Cobble Hill) custom frame shop at 137 Atlantic Avenue (since 1978) — hand-built closed-corner hardwood frames, archival materials, in-home design, pickup, and drop-off.',
        'base_url' => 'https://frameatlantic.com',
        'location' => 'make a Frame Atlantic ltd.',
    ],
    [
        'name' => 'Maharam',
        'description' => 'North America\'s leading commercial and residential textile firm (founded 1902) — multibrand showroom (Edelman / Knoll Textiles / Maharam) at 257 Park Avenue South, opened October 2025.',
        'base_url' => 'https://www.maharam.com',
        'location' => 'Maharam',
    ],
    [
        'name' => 'M2L',
        'description' => 'Curated modern furniture, lighting, and accessories gallery (founded 30+ years ago by Michael Manes) at 10 East 38th Street, 2nd Floor — by appointment Monday–Friday.',
        'base_url' => 'https://m2l.com',
        'location' => 'M2L Inc',
    ],
    [
        'name' => 'Ligne Roset Park Avenue South',
        'description' => 'French furniture brand Ligne Roset\'s 5,600 sq ft NYC flagship at 250 Park Avenue South in the NoMad design district.',
        'base_url' => 'https://www.ligne-roset.com/us/retails/4611-ligne-roset-park-avenue-south-350',
        'location' => 'LUMAS x Ligne Roset',
    ],
    [
        'name' => 'Leroy Street Studio',
        'description' => 'Award-winning NYC architecture and interiors firm (since 1995) at 65 Allen Street — also home to the Allen Street Gallery, showcasing work at the intersection of architecture, art, and design.',
        'base_url' => 'https://www.leroystreetstudio.com',
        'location' => 'Leroy Street Studio',
    ],
    [
        'name' => 'Kvadrat New York',
        'description' => 'Danish design textile brand\'s 8,000 sq ft NYC flagship at 475 Park Avenue (former 1970s car dealership) — Jonathan Olivares–designed showroom of upholstery, curtains, and rugs.',
        'base_url' => 'https://www.kvadrat.dk/en/new-york-showroom',
        'location' => 'Kvadrat',
    ],
    [
        'name' => 'K\'ab Juun',
        'description' => 'Meatpacking District contemporary Mexican-design gallery at 38 Little West 12th Street — handcrafted furniture, lighting, art, and objects made in Mexico.',
        'base_url' => 'https://meatpacking-district.com/places/kab-juun',
        'location' => 'K\'ab Juun',
    ],
    [
        'name' => 'Jan Kath New York',
        'description' => 'Chelsea showroom (514 W 25th Street, run by Kyle & Kath LLC) for German rug designer Jan Kath\'s hand-knotted classic and contemporary carpets.',
        'base_url' => 'https://jan-kath.com/showrooms/new-york/',
        'location' => 'Jan Kath',
    ],
    [
        'name' => 'JADERALMEIDA NYC',
        'description' => 'Brazilian design brand JaderAlmeida\'s 500 sq m Tribeca showroom and "livable gallery" at 124 Hudson Street — flagship US location.',
        'base_url' => 'https://blog.jaderalmeida.com/jaderalmeida-showroom-new-york/',
        'location' => 'JADERALMEIDA',
    ],

    // 2026-04-29 batch 33 — informational website entries (more NYCxDESIGN showrooms).
    [
        'name' => 'iSiMAR New York',
        'description' => 'Spanish Mediterranean-style outdoor furniture brand iSiMAR\'s NYC showroom (183 Madison Avenue, 17th Floor) — shared with B.lux lighting and Woop Rugs.',
        'base_url' => 'https://www.isimar.es/en/showroom/new-york/',
        'location' => 'iSiMAR',
    ],
    [
        'name' => 'The Invisible Collection (New York)',
        'description' => 'Upper East Side townhouse gallery (24 East 64th Street) for The Invisible Collection — bespoke furniture and collectible design objects from 100+ international designers.',
        'base_url' => 'https://theinvisiblecollection.com/invisible-new-york/',
        'location' => 'Invisible Collection',
    ],
    [
        'name' => 'il Buco Vita',
        'description' => 'NYC headquarters and home-goods showroom of il Buco (4 East 2nd Street) — handmade rustic Italian home furnishings and kitchen supplies, much from recycled materials.',
        'base_url' => 'https://ilbucovita.com',
        'location' => 'il Buco Vita',
    ],
    [
        'name' => 'House of Santal',
        'description' => 'Contemporary South Asian design gallery (135 W 50th Street, 10th Floor) — 8,000 sq ft former Midtown office reimagined as a luxury South Asian craft showroom.',
        'base_url' => 'https://houseofsantal.com',
        'location' => 'House of Santal',
    ],
    [
        'name' => 'HBF NYC Showroom',
        'description' => 'HBF\'s contract office furniture and textiles showroom (155 5th Avenue, 6th Floor, Flatiron) — Alda Ly Architecture-designed showcase of HBF furniture and textiles vignettes.',
        'base_url' => 'https://www.hbf.com',
        'location' => 'HBF',
    ],
    [
        'name' => 'Harbour Outdoor (NYC)',
        'description' => 'Australian luxury outdoor furniture brand\'s 8,000 sq ft NYC flagship at 60 Madison Avenue (corner of E 27th Street) — opened May 2024 during NYCxDESIGN Week.',
        'base_url' => 'https://shopharbour.com/pages/new-york-showroom',
        'location' => 'Harbour',
    ],
    [
        'name' => 'Halo at 28 Liberty',
        'description' => 'Financial District event venue at 28 Liberty Street (entered via 28 Pine Street) — 30,000 sq ft of versatile space for up to 750 guests, plus a 15,000-person plaza.',
        'base_url' => 'https://www.husheventsnyc.com/halo',
        'location' => 'Halo Twenty Eight',
    ],
    [
        'name' => 'Galerie56',
        'description' => 'Tribeca art, architecture, and design platform at the base of Herzog & de Meuron\'s "Jenga" building (240 Church Street), opened by Lee F. Mindel of Shelton Mindel.',
        'base_url' => 'https://galerie56.com',
        'location' => 'Galerie56',
    ],
    [
        'name' => 'Foscarini Spazio Soho',
        'description' => 'Italian lighting brand Foscarini\'s SoHo flagship at 20 Greene Street (since 2013) — exhibitions, talks, and the brand\'s collections of decorative lighting.',
        'base_url' => 'https://www.foscarini.com/en/spazio-soho/',
        'location' => 'FOSCARINI',
    ],
    [
        'name' => 'Florim New York Flagship',
        'description' => 'Italian porcelain tile brand Florim\'s 6,000 sq ft NoMad flagship inside Rafael Viñoly\'s 277 Fifth Avenue tower — collections, conferences, and design events.',
        'base_url' => 'https://www.florim.com/en/company/showroom/new-york',
        'location' => 'Florim',
    ],
    [
        'name' => 'ESPASSO',
        'description' => 'Tribeca\'s 8,000 sq ft Brazilian-design flagship (38 N Moore Street) — the first US gallery dedicated entirely to Brazilian mid-century and contemporary design.',
        'base_url' => 'https://www.espasso.com',
        'location' => 'ESPASSO',
    ],
    [
        'name' => 'Nexus Club New York',
        'description' => 'Private social and business club (100 Church Street, 7th Floor) — 34,000+ sq ft of dining, fitness, meeting, and event space in Lower Manhattan.',
        'base_url' => 'https://nexusclubny.clubhouseonline-e3.net/',
        'location' => 'Design Nexus',
    ],

    // 2026-04-29 batch 34 — informational website entries.
    [
        'name' => 'Dacor Kitchen Theater (NYC)',
        'description' => 'Dacor\'s flagship NYC showroom and demo kitchen at the A&D Building (150 East 58th Street, Suite 602) — interactive cooking and design space for trade and homeowners.',
        'base_url' => 'https://www.dacor.com/us/experiences/kitchen-theaters/the-dacor-kitchen-theater-new-york/',
        'location' => 'dacor kitchen theater',
    ],
    [
        'name' => 'Carl Hansen & Søn — SoHo Flagship',
        'description' => 'Danish furniture brand Carl Hansen & Søn\'s 5,200 sq ft SoHo flagship at 150 Wooster Street (since 2022) — Hans Wegner, Kaare Klint, Poul Kjærholm, Arne Jacobsen, Børge Mogensen designs.',
        'base_url' => 'https://www.carlhansen.com/en/en/stores/flagship-store-new-york',
        'location' => 'Carl Hansen & Son',
    ],
    [
        'name' => 'Brooklyn Metal Works',
        'description' => 'Prospect Heights metalsmithing studio and gallery (640 Dean Street, 2nd Floor) — semi-private studio rentals, classes, exhibitions, and visiting-artist events focused on art jewelry.',
        'base_url' => 'https://www.bkmetalworks.com',
        'location' => 'Brooklyn Metal Works',
    ],
    [
        'name' => 'Automattic NoHo (166 Crosby)',
        'description' => 'Automattic\'s NYC office (166 Crosby Street, 11th Floor) — the maker of WordPress.com, WooCommerce, Tumblr, Jetpack — used for partner events and meetups.',
        'base_url' => 'https://automattic.space/',
        'location' => 'Automattic',
    ],
    [
        'name' => 'AREA New York',
        'description' => 'Japanese luxury furniture and interior brand AREA\'s NYC showroom (1 5th Avenue / Madison Avenue area) — exhibits Japanese-crafted chairs, live-edge tables, and architectural fixtures.',
        'base_url' => 'https://area-interior.com',
        'location' => 'AREA New York',
    ],
    [
        'name' => 'Adaptive Design Association',
        'description' => 'NYC nonprofit (313 West 36th Street) building custom adaptive equipment for children with disabilities, with hands-on volunteer workshops and adaptive-design training.',
        'base_url' => 'https://www.adaptivedesign.org',
        'location' => 'Adaptive Design Assocation',
    ],

    // 2026-04-29 batch 35 — informational website entries.
    [
        'name' => 'Queens Community House',
        'description' => 'Multi-site Queens nonprofit running community centers, after-school programs, and senior programs — Forest Hills HQ at 108-25 62nd Drive (renovated 2022–2024).',
        'base_url' => 'https://www.qchnyc.org',
        'location' => 'Queens Community House (Forest Hills)',
    ],
    [
        'name' => 'Bedford Stuyvesant Family Health Center',
        'description' => 'Federally Qualified Health Center serving Central Brooklyn since 1978 — primary, specialty, maternity, women\'s health, and pediatric care at 1456 Fulton Street and other Bed-Stuy sites.',
        'base_url' => 'https://www.bsfhc.org',
        'location' => 'Bedford Stuyvesant Family Health Center',
    ],
    // Children of Promise NYC: existing canonical website (id 3293) is already linked to canonical location 4266.
    // Stale duplicate (5623) was merged into 4266 — no new entry needed here.
    [
        'name' => 'WNYC Transmitter Park',
        'description' => '1.6-acre Greenpoint waterfront park (where Greenpoint Avenue meets the East River) — opened 2012 on the former WNYC transmitter site, with wetlands, a pedestrian bridge, and a pier.',
        'base_url' => 'https://www.nycgovparks.org/parks/transmitter-park',
        'location' => 'WNYC Transmitter Park',
    ],
    [
        'name' => 'Gorman Playground (NYC Parks)',
        'description' => 'East Elmhurst, Queens playground (renamed 1963 for civic leader Denis Gorman; originally Jackson Heights Model Playground, 1934) — calisthenics area, handball, basketball, and volleyball courts.',
        'base_url' => 'https://www.nycgovparks.org/parks/gorman-playground',
        'location' => 'Gorman Playground',
    ],

    // 2026-04-30 batch 36 — informational website entries.
    [
        'name' => 'Westchester County (Wikipedia)',
        'description' => 'Wikipedia article on Westchester County, NY.',
        'base_url' => 'https://en.wikipedia.org/wiki/Westchester_County,_New_York',
        'location' => 'Westchester County',
    ],
    [
        'name' => 'Stone Avenue Library (BPL)',
        'description' => 'Brooklyn Public Library branch in Brownsville on Mother Gaston Boulevard, with reading and youth programs.',
        'base_url' => 'https://www.bklynlibrary.org/locations/stone-avenue',
        'location' => 'Stone Avenue Library',
    ],
    [
        'name' => 'Bush Terminal Piers Park (NYC Parks)',
        'description' => 'Sunset Park, Brooklyn waterfront park on the former Bush Terminal piers, with athletic fields, walking paths, and Manhattan skyline views.',
        'base_url' => 'https://www.nycgovparks.org/parks/bush-terminal-piers-park',
        'location' => 'Bush Terminal Piers Park',
    ],
    [
        'name' => 'One and One',
        'description' => 'East Village landmark dual-concept venue (since 1989) at 76 East 1st Street — upstairs Irish sports bar, downstairs lounge for nightlife and dancing.',
        'base_url' => 'https://www.oneandone.nyc',
        'location' => 'One and One',
    ],
    [
        'name' => 'Rutherford Public Library',
        'description' => 'Bergen County, NJ public library (founded 1893, current building since 1896) at 150 Park Avenue, Rutherford.',
        'base_url' => 'https://rutherfordlibrary.org',
        'location' => 'Rutherford Free Public Library',
    ],
    [
        'name' => 'Glen Ridge Public Library',
        'description' => 'Essex County, NJ public library at 240 Ridgewood Avenue, Glen Ridge — programs for children, teens, and adults plus printing and research databases.',
        'base_url' => 'https://www.glenridgelibrary.org',
        'location' => 'Glen Ridge Free Public Library',
    ],
    [
        'name' => 'BEEPUBLIC',
        'description' => 'DUMBO sustainable, plant-forward cafe by day / bar by night at 181 Front Street — organic, pesticide-free pastries and food with a save-the-bees mission.',
        'base_url' => 'https://beepublic.com',
        'location' => 'BEEPUBLIC',
    ],
    [
        'name' => 'Red Hook Library (BPL)',
        'description' => 'Brooklyn Public Library\'s Red Hook Interim branch at 362 Van Brunt Street, hosting story times, programs, and community events.',
        'base_url' => 'https://www.bklynlibrary.org/locations/red-hook',
        'location' => 'Red Hook Interim Library',
    ],
    [
        'name' => 'Franz Sigel Park (NYC Parks)',
        'description' => 'Bronx park along the Grand Concourse near the Bronx County Courthouse — a hilly, tree-lined neighborhood park with playgrounds and seating areas.',
        'base_url' => 'https://www.nycgovparks.org/parks/franz-sigel-park',
        'location' => 'Franz Sigel Park',
    ],
    [
        'name' => 'Cortelyou Library (BPL)',
        'description' => 'Brooklyn Public Library branch in Ditmas Park / Flatbush at Cortelyou Road and Argyle Road, hosting community programs and events.',
        'base_url' => 'https://www.bklynlibrary.org/locations/cortelyou',
        'location' => 'Cortelyou Library',
    ],

    // 2026-04-30 batch 37 — informational website entries.
    [
        'name' => 'Reading Room NYC',
        'description' => 'Williamsburg BYO reading salon at 198 N 4th Street.',
        'base_url' => 'https://readingroom.nyc',
        'location' => 'Reading Room',
    ],
    [
        'name' => 'Rothermel Park (Village of Kinderhook)',
        'description' => '7.6-acre Village of Kinderhook park (Columbia County) with baseball fields, tennis and basketball courts, a playground, and trails — eastern terminus of the Albany-Hudson Electric Trail.',
        'base_url' => 'https://www.villageofkinderhook.org/parks_facilities/rothermel_park_and_playground/index.php',
        'location' => 'Rothermel Park',
    ],
    [
        'name' => 'St. Mary\'s Drama Guild',
        'description' => 'Woodside, Queens community theatre program (70-20 47th Avenue) producing shows for adults and children, with outreach to immigrant and lower-income families.',
        'base_url' => 'https://www.stmarysdramaguild.org',
        'location' => 'St. Mary\'s Drama Guild',
    ],
    [
        'name' => 'Rev J Polite Playground (NYC Parks)',
        'description' => 'Bronx playground (since 1938) on Rev James Polite Avenue, named for Reverend James Arthur Polite of Thessalonia Baptist Church — turf field, swings, and play equipment, jointly run with PS 99.',
        'base_url' => 'https://www.nycgovparks.org/parks/rev-j-polite-playground',
        'location' => 'Rev James A Polite Playground',
    ],
    [
        'name' => 'The Training Lab NYC',
        'description' => 'Midtown strength-and-conditioning gym at 54 W 39th Street, 9th Floor (since 2017) with team-based high-intensity classes and a recovery lounge (cold plunge, infrared sauna, Normatec).',
        'base_url' => 'https://traininglabnyc.com',
        'location' => 'The Training Lab NYC',
    ],
    [
        'name' => 'The River Fund New York',
        'description' => 'Richmond Hill, Queens nonprofit (89-11 Lefferts Boulevard) — one of NYC\'s largest emergency-food providers, distributing 1+ million pounds of groceries monthly to 35,000+ households.',
        'base_url' => 'https://www.river.fund',
        'location' => 'The River Fund New York',
    ],
    [
        'name' => 'The New Jewish Home — Manhattan',
        'description' => 'Comprehensive nonprofit senior-care system (since 1848) at 120 W 106th Street — home care, post-acute rehab, long-term care, and senior living services.',
        'base_url' => 'https://jewishhome.org',
        'location' => 'The New Jewish Home',
    ],
    [
        'name' => 'Salvation Army Brooklyn Sunset Park Corps',
        'description' => 'Salvation Army community center in Sunset Park, Brooklyn (520 50th Street) offering youth activities, recreation, counseling, and emergency food/clothing/financial assistance.',
        'base_url' => 'https://www.salvationarmyusa.org/ny/brooklyn/50th-street-corps/',
        'location' => 'Salvation Army Sunset Park',
    ],
    [
        'name' => 'Salvation Army Brooklyn Bedford Temple Corps',
        'description' => 'Salvation Army community center in Bedford-Stuyvesant (601 Lafayette Avenue) offering youth, recreation, counseling, and emergency-aid services.',
        'base_url' => 'https://www.easternusa.salvationarmy.org/greater-new-york/',
        'location' => 'Salvation Army Bedford Temple',
    ],
    [
        'name' => 'Rauschenbusch Metro Ministries',
        'description' => 'Hell\'s Kitchen social-ministry nonprofit (410 W 40th Street, founded 1995 by Metro Baptist Church) operating a food pantry, urban-immersion programs, and other community services.',
        'base_url' => 'https://rmmnyc.org',
        'location' => 'Rauschenbusch Metro Ministries',
    ],
    [
        'name' => 'Part of the Solution (POTS)',
        'description' => 'Bronx (2759 Webster Avenue) community-services nonprofit — daily Community Dining Room, food pantry, nutrition education, clothing/shower/mail facilities, barbershop, legal clinic, and medical/dental clinic.',
        'base_url' => 'https://potsbronx.org/english/',
        'location' => 'Part of the Solution (POTS)',
    ],

    // 2026-04-30 batch 38 — informational website entries (mostly social-services nonprofits).
    [
        'name' => 'LSA Family Health Service',
        'description' => 'East Harlem nonprofit (since 1958) at 333 East 115th Street offering health, food, education, and home services to vulnerable families and children.',
        'base_url' => 'https://littlesistersfamily.org',
        'location' => 'Little Sisters of the Assumption Family Health Service',
    ],
    [
        'name' => 'Transit Tech Career and Technical Education High School',
        'description' => 'NYC DOE CTE high school in East New York (1 Wells Street) offering electrical, automotive, and computer training plus college prep, with a longstanding partnership with MTA NYC Transit.',
        'base_url' => 'https://transittechhs.org',
        'location' => 'Transit Tech CTE High School',
    ],
    [
        'name' => 'Golden Harvest Food Pantry (NEBHDCo)',
        'description' => 'Bedford-Stuyvesant supermarket-style client-choice food pantry (376 Throop Avenue) operated by Northeast Brooklyn Housing Development Corporation since 1993.',
        'base_url' => 'https://nebhdco.org/golden-harvest-food-pantry/',
        'location' => 'Golden Harvest Food Pantry',
    ],
    [
        'name' => 'Fordham Bedford Community Services',
        'description' => 'Northwest Bronx nonprofit operated by Fordham Bedford Housing Corporation — adult education, after-school programs, and housing assistance with sites including 2848 Bainbridge Avenue.',
        'base_url' => 'https://www.fordham-bedford.org/affiliates',
        'location' => 'Fordham Bedford Community Services',
    ],
    [
        'name' => 'Emma\'s Torch',
        'description' => 'Carroll Gardens nonprofit cafe and culinary school (since 2016) at 345 Smith Street — empowers refugees through paid culinary training; serves all-day breakfast, weekend brunch, and event programming.',
        'base_url' => 'https://emmastorch.org',
        'location' => 'Emma\'s Torch',
    ],
    [
        'name' => 'Cornerstone Baptist Church',
        'description' => 'Bedford-Stuyvesant Baptist church at 574 Madison Street (led by Rev. Lawrence E. Aker, III) — runs the Cornerstone Baptist Food Pantry alongside worship and youth/community programs.',
        'base_url' => 'https://cbcbrooklyn.org',
        'location' => 'Cornerstone Baptist Food Pantry',
    ],
    [
        'name' => 'Christ Church Cobble Hill',
        'description' => 'Episcopal church in Cobble Hill, Brooklyn (326 Clinton Street) housed in a Richard Upjohn-designed Gothic Revival building (1841–42), with worship, music, and community programs.',
        'base_url' => 'https://christchurchcobblehill.net',
        'location' => 'Christ Church Cobble Hill',
    ],
    [
        'name' => 'Center for Employment Opportunities (CEO)',
        'description' => 'National reentry-employment nonprofit headquartered at 50 Broadway, Suite 1604 — provides job-readiness training and transitional work to people recently released from incarceration.',
        'base_url' => 'https://www.ceoworks.org',
        'location' => 'Center for Employment Opportunities',
    ],
    [
        'name' => 'Catholic Charities Community Services — Bronx Center',
        'description' => 'Catholic Charities Archdiocese of NY South Bronx hub at 402 East 152nd Street — housing assistance, tenant education, food distribution (FOOD HUB), and legal/budget support.',
        'base_url' => 'https://cccsny.org/services/neighborhood-centers-south-bronx',
        'location' => 'Catholic Charities Bronx Center',
    ],
    [
        'name' => 'Baruch Community Center (Henry Street Settlement)',
        'description' => 'Lower East Side community center at 605 FDR Drive in Baruch Houses (NYCHA), operated by Henry Street Settlement — youth, senior, and emergency-response programming.',
        'base_url' => 'https://www.henrystreet.org/about/our-buildings/baruch-and-fdr-drive-buildings/',
        'location' => 'Baruch Community Center',
    ],

    // 2026-04-30 batch 39 — informational website entries.
    [
        'name' => 'Our Lady of Grace (Brooklyn)',
        'description' => 'Roman Catholic parish in Gravesend, Brooklyn (corner of Avenue W and East 4th Street) — masses, parish ministry, and the affiliated Our Lady of Grace Catholic Academy.',
        'base_url' => 'https://ourladyofgrace-brooklyn.org',
        'location' => 'Our Lady of Grace Church',
    ],
    [
        'name' => 'The Ivory On Park',
        'description' => 'Three-story Bushwick rooftop and event space (12 Park Street) inside Bond Collective Bushwick — 20-foot ceilings, private backyard, multiple rooftops.',
        'base_url' => 'https://theivorybk.com',
        'location' => 'The Ivory On Park',
    ],
    [
        'name' => 'Allison Pond Park (NYC Parks)',
        'description' => 'Tranquil Staten Island park (Prospect Avenue / Randall Avenue / Brentwood Avenue) centered on a picturesque pond with fishing, hiking trails, and connections to Goodhue Park.',
        'base_url' => 'https://www.nycgovparks.org/parks/allison-park',
        'location' => 'Allison Pond Park',
    ],
    [
        'name' => 'Elmhurst, Queens (Wikipedia)',
        'description' => 'Wikipedia article on the Elmhurst neighborhood of Queens.',
        'base_url' => 'https://en.wikipedia.org/wiki/Elmhurst,_Queens',
        'location' => 'Elmhurst',
    ],
    [
        'name' => 'Radio Star',
        'description' => '1940s-radio-era-inspired Mediterranean restaurant, bar, and cafe in Greenpoint (13 Greenpoint Avenue, next to WNYC Transmitter Park) — from the team behind Glasserie.',
        'base_url' => 'https://www.theradiostar.com',
        'location' => 'Radio Star',
    ],
    [
        'name' => 'TASHCA NYC',
        'description' => 'NoLita Portuguese eatery (151 Elizabeth Street) — traditional Portuguese cooking, lively service, with limited weekly hours.',
        'base_url' => 'https://www.tashcanyc.com',
        'location' => 'Tashca',
    ],
    [
        'name' => 'NoMad, Manhattan (Wikipedia)',
        'description' => 'Wikipedia article on the NoMad neighborhood (North of Madison Square Park) of Manhattan.',
        'base_url' => 'https://en.wikipedia.org/wiki/NoMad,_Manhattan',
        'location' => 'NoMad',
    ],
    [
        'name' => 'Sutton Tower',
        'description' => 'Sutton Place luxury condominium at 430 East 58th Street — used here as the venue address for resident events and design programming.',
        'base_url' => 'https://suttontower.com',
        'location' => 'Sutton Tower',
    ],
    [
        'name' => 'Silver Lining Lounge',
        'description' => 'Tao Group jazz, blues, and live-music lounge at 75 Murray Street in Tribeca with cocktails, bottle service, and intimate live performances.',
        'base_url' => 'https://taogroup.com/venues/silver-lining-lounge-new-york/',
        'location' => 'Silver Lining Lounge',
    ],
    [
        'name' => 'Lolita NYC',
        'description' => 'Lower East Side terroir-driven Mexican cocktail bar and restaurant at 266 Broome Street — agave-forward menu, daily happy hour, and weekend "Golden Hour" tacos and guac.',
        'base_url' => 'https://www.lolitanewyorkcity.com',
        'location' => 'Lolita NYC',
    ],

    // 2026-04-30 batch 40 — informational website entries (NJ parks + Harlem/Bronx venues).
    [
        'name' => 'Irene Habernickel Family Park',
        'description' => '10-acre Ridgewood, NJ park (former Sweetbriar Farms horse farm; village acquired 2004) with walking trails, athletic field, playground, pond, and HealthBarn USA programming.',
        'base_url' => 'https://www.ridgewoodnj.net/Facilities/Facility/Details/Irene-Habernickel-Family-Park-3',
        'location' => 'Irene Habernickel Family Park',
    ],
    [
        'name' => 'Mahlon Dickerson Reservation',
        'description' => 'Morris County Park Commission reservation in Jefferson Township, NJ — 3,500+ acres with 27 miles of multi-use trails, RV/tent/Adirondack Shelter camping, and seasonal recreation.',
        'base_url' => 'https://www.morrisparks.net/parks_trails/mahlon-dickerson-reservation/',
        'location' => 'Mahlon Dickerson Reservation',
    ],
    [
        'name' => 'Brookdale Park (Essex County Parks)',
        'description' => '121-acre Essex County park spanning Bloomfield and Montclair — third-largest in the system, with trails, playgrounds, sports fields, a track, tennis courts, an archery range, and dog park.',
        'base_url' => 'https://essexcountyparks.org/parks/brookdale-park',
        'location' => 'Brookdale Park',
    ],
    [
        'name' => 'Riker Hill Art Park',
        'description' => 'Former US Army Nike Missile Base in Livingston, NJ (transformed into an art park 1974) — 38 artist-in-residence studios across painting, ceramics, glass, photography, and sculpture.',
        'base_url' => 'https://www.rikerhillartists.org',
        'location' => 'Riker Hill Art Park',
    ],
    [
        'name' => 'We Are Here Studios',
        'description' => 'Bushwick second-floor studio and event space at 563 Johnson Avenue used for music, art, and community events.',
        'base_url' => 'https://donyc.com/venues/we-are-here-studios',
        'location' => 'We Are Here Studios',
    ],
    [
        'name' => 'Patrick\'s on the Hill',
        'description' => 'Hamilton Heights Caribbean restaurant at 1635 Amsterdam Avenue near the Hamilton Grange National Memorial — Jamaican comfort food, Wednesday trivia, and Sunday live jazz.',
        'base_url' => 'https://www.patricksonthehill.com',
        'location' => 'Patrick\'s on the Hill',
    ],
    [
        'name' => 'PS 154 Harriet Tubman Learning Center',
        'description' => 'NYC DOE elementary public school in Harlem (250 W 127th Street) serving grades PK–5 in District 5.',
        'base_url' => 'https://www.ps154.com',
        'location' => 'Harriet Tubman Learning Center (PS 154)',
    ],
    [
        'name' => 'Hour Children',
        'description' => 'Long Island City nonprofit (since 1986) at 36-11 12th Street — community services, employment, mental health, and transitional housing for incarcerated and formerly incarcerated women and their children.',
        'base_url' => 'https://hourchildren.org',
        'location' => 'Hour Children',
    ],
    [
        'name' => 'Holyrood Episcopal Church',
        'description' => 'Washington Heights Episcopal Church (1911–1916, Gothic Revival, NYC landmark) at 715 W 179th Street — bilingual English/Spanish congregation with worship, community, and arts programming.',
        'base_url' => 'https://www.holyroodsantacruz.org',
        'location' => 'Holyrood Episcopal Church',
    ],
    [
        'name' => 'Bronx Music Heritage Center (WHEDco)',
        'description' => 'Bronx music presenter and lab (1303 Louis Niné Boulevard) operated by the Women\'s Housing and Economic Development Corporation — preserves Bronx music history and presents free programming.',
        'base_url' => 'https://whedco.org/bronx-music/bronx-music-heritage-center-bmhc/',
        'location' => 'Bronx Music Heritage Center',
    ],

    // 2026-04-30 batch 41 — informational website entries.
    [
        'name' => 'The Maybury (Gotham Organization)',
        'description' => '47-story Hudson Yards / Hell\'s Kitchen rental tower (550 Tenth Avenue, opened 2024) by Gotham Organization — 453 units, sky lounge, co-working, fitness club; used as a venue for resident-hosted events.',
        'base_url' => 'https://gothamorg.com/portfolio/the-maybury/',
        'location' => 'The Maybury',
    ],
    [
        'name' => 'Selis Manor / VISIONS at Selis Manor',
        'description' => 'Chelsea supportive-housing residence (135 W 23rd Street) for visually impaired and disabled New Yorkers (the first government-funded such residence in NYC) — VISIONS runs ground-floor programming including a gym, bowling alley, arts room, and library for the blind.',
        'base_url' => 'https://visionsvcb.org/locations-2/visions-at-selis-manor/',
        'location' => 'Selis Manor',
    ],
    [
        'name' => 'Huntington Moose Lodge 318',
        'description' => 'Greenlawn, Long Island Loyal Order of Moose lodge at 631 Pulaski Road — community programs, hall rentals, and private events.',
        'base_url' => 'http://moose318.com/',
        'location' => 'Huntington Moose Lodge',
    ],
    [
        'name' => 'Huntington Public Library',
        'description' => 'Long Island public library system serving Huntington, NY — Main Library on Main Street and a Station Branch in Huntington Station, with programs for adults, teens, and children.',
        'base_url' => 'https://myhpl.org/',
        'location' => 'Huntington Public Library',
    ],
    [
        'name' => 'Oak Ridge Park (Union County, NJ)',
        'description' => '90-acre Union County park in Clark, NJ — archery range, disc golf, multi-purpose turf, lacrosse and soccer fields, picnic areas, and walking paths.',
        'base_url' => 'https://exploreunioncounty.com/places/new-jersey/clark/parks-1/oak-ridge-park/',
        'location' => 'Oak Ridge Park',
    ],
    [
        'name' => 'Stewart Manor Country Club',
        'description' => 'Western Nassau County social/event venue (built 1927) — weddings, anniversaries, sweet sixteens, and reunions in a renovated club and garden setting.',
        'base_url' => 'https://www.stewartmanor.com/',
        'location' => 'Stewart Manor Country Club',
    ],
    [
        'name' => 'coLAB Arts',
        'description' => 'New Brunswick, NJ social-impact arts nonprofit engaging artists, social advocates, and communities to create transformative new work.',
        'base_url' => 'https://colab-arts.org',
        'location' => 'coLAB Arts Studios',
    ],
    [
        'name' => 'Macy\'s Herald Square',
        'description' => 'Macy\'s flagship department store at 151 W 34th Street — full-block, 2.5 million sq ft (largest department store in the U.S.); home to seasonal events including the Flower Show and Holiday Windows.',
        'base_url' => 'https://www.macys.com/stores/ny/newyork/herald-square_3.html',
        'location' => 'Macy\'s Herald Square',
    ],
    [
        'name' => 'First Presbyterian Church of East Hampton',
        'description' => 'Historic East Hampton, NY Presbyterian congregation at 120 Main Street with worship, music, youth, and community programs.',
        'base_url' => 'https://www.fpceh.org/',
        'location' => 'First Presbyterian Church of East Hampton',
    ],
    [
        'name' => 'Le Botaniste',
        'description' => 'Belgian-rooted, 100% plant-based, mostly-organic food and wine bar with multiple NYC locations — botanical bowls, mezze platters, hearty chili, and vegan desserts.',
        'base_url' => 'https://lebotaniste.us/',
        'location' => 'Le Botaniste UWS',
    ],
    [
        'name' => 'Franklin D. Roosevelt State Park',
        'description' => '960-acre Westchester County state park in Yorktown Heights, NY (~40 miles from NYC) with one of the largest pools in the system, freshwater fishing on Mohansic Lake / Crom Pond, and group picnic areas.',
        'base_url' => 'https://parks.ny.gov/visit/state-parks/franklin-d-roosevelt-state-park',
        'location' => 'Franklin D. Roosevelt State Park',
    ],

    // 2026-04-30 batch 42 — informational website entries (NJ libraries + schools).
    [
        'name' => 'Union County Courthouse',
        'description' => 'NJ Superior Court Union Vicinage courthouse at 2 Broad Street, Elizabeth, NJ — primary court facility for Union County including the County Clerk\'s office.',
        'base_url' => 'https://www.njcourts.gov/courts/vicinages/union',
        'location' => 'Union County Courthouse',
    ],
    [
        'name' => 'Summit High School (NJ)',
        'description' => 'Summit Public Schools four-year comprehensive high school at 125 Kent Place Boulevard — the lone secondary school in the Summit, NJ district.',
        'base_url' => 'https://www.summit.k12.nj.us/schools/summit-high-school',
        'location' => 'Summit High School',
    ],
    [
        'name' => 'Westfield Community Players',
        'description' => 'Westfield, NJ nonprofit theatre group (since 1934) with a 150-seat theater at 1000 North Avenue West — comedies, dramas, musicals, and mysteries.',
        'base_url' => 'https://www.wcptheatre.org',
        'location' => 'Westfield Community Players',
    ],
    [
        'name' => 'Lodi Memorial Library',
        'description' => 'BCCLS member library at One Memorial Drive, Lodi, NJ — programs for children, teens, and adults, computers, and digital resources.',
        'base_url' => 'https://www.lodilibrarynj.org/',
        'location' => 'Lodi Memorial Library',
    ],
    [
        'name' => 'Demarest Free Public Library',
        'description' => 'BCCLS member library at 90 Hardenburgh Avenue, Demarest, NJ (since 1964) — meeting rooms, museum passes, computers, and youth/adult programs.',
        'base_url' => 'https://www.demarestlibrary.org/',
        'location' => 'Demarest Public Library',
    ],
    [
        'name' => 'Bergenfield Public Library',
        'description' => 'Bergen County, NJ public library at 50 W Clinton Avenue, Bergenfield — programs, events, and digital resources via BCCLS.',
        'base_url' => 'https://www.bergenfieldlibrary.org/',
        'location' => 'Bergenfield Public Library',
    ],
    [
        'name' => 'Vassar College',
        'description' => 'Selective coeducational liberal-arts college (founded 1861) on a 1,000-acre Poughkeepsie campus — frequent host to public concerts, lectures, and exhibitions in the Hudson Valley.',
        'base_url' => 'https://www.vassar.edu/',
        'location' => 'Vassar College',
    ],
    [
        'name' => 'Hamilton Stage at UCPAC',
        'description' => '199-seat modern theater at Union County Performing Arts Center in Rahway, NJ (360 Hamilton Street) — opened 2012, renovated 2023–24, with a Bösendorfer grand piano and gallery lobby.',
        'base_url' => 'https://ucpac.org/',
        'location' => 'Hamilton Stage at UCPAC',
    ],
    [
        'name' => 'Southold Junior-Senior High School',
        'description' => 'Southold Union Free School District grades 7–12 public school on the North Fork of Long Island (420 Oaklawn Ave, Southold, NY).',
        'base_url' => 'https://hs.southoldufsd.com/',
        'location' => 'Southold High School',
    ],
    [
        'name' => 'Ridgefield Park Public Library',
        'description' => 'BCCLS member library at 107 Cedar Street, Ridgefield Park, NJ — programs, digital resources, museum passes, and meeting rooms.',
        'base_url' => 'https://www.ridgefieldparkpubliclibrary.org/',
        'location' => 'Ridgefield Park Public Library',
    ],
    [
        'name' => 'Roseland Public Library',
        'description' => 'Essex County, NJ public library at 20 Roseland Avenue with adult, teen, and youth programs and digital borrowing.',
        'base_url' => 'https://roselandpubliclibrary.org/',
        'location' => 'Roseland Free Public Library',
    ],
    [
        'name' => 'Wyckoff Free Public Library',
        'description' => 'Bergen County, NJ public library (BCCLS) at 200 Woodland Avenue, Wyckoff — adult programs, computers, and community events.',
        'base_url' => 'https://wyckofflibrary.org/',
        'location' => 'Wyckoff Public Library',
    ],

    // 2026-04-30 batch 43 — informational website entries.
    [
        'name' => 'The Junto Attic Bar',
        'description' => 'Speakeasy above Franklin Social in Jersey City (68 Mercer St) — Gilded Age decor, stained-glass bar backdrop, craft cocktails, first-come/first-served seating for groups of four or fewer.',
        'base_url' => 'https://www.thejuntojc.com/',
        'location' => 'The Junto: Attic Bar',
    ],
    [
        'name' => 'EmblemHealth Neighborhood Care',
        'description' => 'EmblemHealth\'s neighborhood-care community resource centers offering health classes, social services, and community programming — Crown Heights branch at 546 Eastern Parkway.',
        'base_url' => 'https://www.emblemhealth.com/community/neighborhood-care',
        'location' => 'EmblemHealth Neighborhood Care Crown Heights',
    ],
    [
        'name' => 'Lincoln Park (Hudson County)',
        'description' => '273-acre Hudson County Park in Jersey City (since 1905) — tennis courts, ball fields, soccer, the world\'s largest concrete monument fountain (53 ft, 365 tons), and Edgewood Lake.',
        'base_url' => 'https://www.hcnj.us/parks/lincoln-park/',
        'location' => 'Lincoln Park (Jersey City)',
    ],
    [
        'name' => 'Edie Windsor SAGE Center',
        'description' => 'SAGE\'s Chelsea (305 7th Avenue, 15th Floor) flagship and national headquarters — the nation\'s first full-time LGBT senior center, providing case management, health/wellness, and cultural programming.',
        'base_url' => 'https://sagenyc.org/nyc/centers/index.cfm',
        'location' => 'Edie Windsor SAGE Center',
    ],
    [
        'name' => 'Local Hops',
        'description' => 'Forest Hills, Queens beer bar and restaurant at 66-75 Selfridge Street with 200+ craft beers (rotating taps, bottles, cans) and locally-sourced American food.',
        'base_url' => 'https://localhopsny.com/',
        'location' => 'Local Hops',
    ],
    [
        'name' => 'Bull Moose Dog Run (Theodore Roosevelt Park)',
        'description' => 'Upper West Side dog run in Theodore Roosevelt Park (next to the American Museum of Natural History) — one of the largest in NYC Parks, with separate areas for big and small dogs.',
        'base_url' => 'https://www.nycgovparks.org/parks/theodore-roosevelt-park',
        'location' => 'Bull Moose Dog Run',
    ],
    [
        'name' => 'HART HS — Health, Arts, Robotics & Technology High School',
        'description' => 'NYC DOE magnet high school in Cambria Heights, Queens (207-01 116th Avenue) — grades 9–12, with a Visual Arts major and a Future-Ready small-school community model.',
        'base_url' => 'https://www.hartshs.org/',
        'location' => 'HARTHS Cambria Heights',
    ],
    [
        'name' => '375 Pearl Street (Intergate.Manhattan)',
        'description' => 'Lower Manhattan 32-story former Verizon switching center (now a Sabey data center / office tower) at the Manhattan end of the Brooklyn Bridge — used for tenant events.',
        'base_url' => 'https://375pearl.com/',
        'location' => '375 Pearl St',
    ],
    [
        'name' => 'Rebél Restaurant and Bar',
        'description' => 'Lower East Side Haitian restaurant and bar (29 Clinton Street) with traditional Haitian dishes and a strong cocktail program.',
        'base_url' => 'https://rebelrestaurantandbarnyc.com/',
        'location' => 'Rebel Restaurant',
    ],
    [
        'name' => '34th Avenue Open Streets Coalition',
        'description' => 'Volunteer-run NYC DOT Open Street program along 26 blocks of 34th Avenue (69th Street to Junction Boulevard) — daily 7 AM–8 PM with classes, festivals, and community programming for Woodside / Jackson Heights / Corona.',
        'base_url' => 'https://www.34aveopenstreets.com/',
        'location' => '34th Ave Open Street (Jackson Heights)',
    ],
    [
        'name' => 'Hot Club of New York',
        'description' => 'Private Flatiron music club for jazz, vinyl listening sessions, and record-related events.',
        'base_url' => 'https://hotclubny.org/',
        'location' => 'Hot Club of New York',
    ],
    [
        'name' => 'Mulford Farmstead',
        'description' => 'Historic East Hampton farmstead operated by the East Hampton Historical Society, hosting benefit events, antique shows, and heritage programming.',
        'base_url' => 'https://easthamptonhistory.org/visit-us/mulford-farmstead/',
        'location' => 'Mulford Farmstead',
    ],
    [
        'name' => 'Manhattan Games Center',
        'description' => 'Midtown games club hosting backgammon tournaments, chess, and board game meetups (12th floor of 110 E 55th St).',
        'base_url' => 'https://www.meetup.com/manhattan-games-center/',
        'location' => 'Manhattan Games Center',
    ],
    [
        'name' => 'Cavendish Club',
        'description' => 'Midtown bridge and backgammon club hosting tournaments, lessons, and social gaming nights.',
        'base_url' => 'https://www.ny-bridge.com/cavendish/index.html',
        'location' => 'Cavendish Club',
    ],
    [
        'name' => 'Scenic Hudson — Long Dock Park',
        'description' => 'Scenic Hudson waterfront park and event center on Long Dock in Beacon, NY, with art installations, environmental programming, and cultural events.',
        'base_url' => 'https://www.scenichudson.org/explore-the-valley/scenic-hudson-parks/scenic-hudsons-long-dock-park/',
        'location' => 'Scenic Hudson River Center',
    ],
    [
        'name' => 'Twin Lights Brewing',
        'description' => 'Tinton Falls, NJ craft brewery with a taproom, community events, and tabletop gaming nights.',
        'base_url' => 'https://twinlightsbrewing.com/',
        'location' => 'Twin Lights Brewing',
    ],
    [
        'name' => 'Roivant Sciences',
        'description' => 'Biopharmaceutical company headquartered in Midtown Manhattan, hosting benefit events and industry gatherings at its office.',
        'base_url' => 'https://roivant.com/',
        'location' => 'Roivant Sciences',
    ],
    [
        'name' => 'Instituto Cervantes — New York',
        'description' => 'Spanish cultural institute in Midtown East offering Spanish-language programming, concerts, film, and cultural events.',
        'base_url' => 'https://nyork.cervantes.es/en/default.shtm',
        'location' => 'Instituto Cervantes - New York',
    ],
    [
        'name' => 'Express Newark',
        'description' => 'Rutgers University-Newark community arts collaboratory in downtown Newark hosting film festivals, exhibitions, and cultural events.',
        'base_url' => 'https://expressnewark.org/',
        'location' => 'Express Newark',
    ],
    [
        'name' => 'Queens Adult Learning Center (Adult Ed School #2)',
        'description' => 'Long Island City adult learning center offering workshops, literacy programs, and community education.',
        'base_url' => 'https://www.adultedschool2.org/',
        'location' => 'Queens Adult Learning Center',
    ],
    [
        'name' => 'Warwick Valley Community Center',
        'description' => 'Community center in Warwick, NY hosting Pride celebrations, arts events, and local community programming.',
        'base_url' => 'https://www.warwickvalleycommunitycenter.org/',
        'location' => 'Warwick Valley Community Center',
    ],
    [
        'name' => 'Silvermine Dual Language Magnet School',
        'description' => 'Norwalk, CT public elementary K-5 dual language immersion magnet school within Norwalk Public Schools.',
        'base_url' => 'https://ses.norwalkps.org/',
        'location' => 'Silvermine Dual Language Magnet School',
    ],
    [
        'name' => 'Brooklyn Running Company',
        'description' => 'NYC independent specialty running shop founded in 2013 with stores in Williamsburg (222 Grand St) and Park Slope (480 Bergen St) — hosts group runs and brand events.',
        'base_url' => 'https://www.brooklynrunningco.com/',
        'location' => 'Brooklyn Running Co.',
    ],
    [
        'name' => 'Electric Shuffle NYC',
        'description' => 'NoMad shuffleboard bar inside Virgin Hotels NYC with 13 hi-tech tables, craft cocktails, and event space — UK-founded chain\'s first US flagship.',
        'base_url' => 'https://electricshuffle.com/us/nyc',
        'location' => 'Electric Shuffle',
    ],
    [
        'name' => 'Chola',
        'description' => 'Long-running Midtown East coastal Indian restaurant (Michelin Plate) hosting tasting events and food collaborations.',
        'base_url' => 'https://www.cholany.com/',
        'location' => 'Chola',
    ],
    [
        'name' => 'BLVD Bistro',
        'description' => 'Harlem soul food restaurant on Frederick Douglass Blvd, family-owned, hosting Thursday comedy and weekend DJ nights alongside Southern dinner service.',
        'base_url' => 'https://boulevardbistrony.com/',
        'location' => 'BLVD Bistro Harlem',
    ],
    [
        'name' => '875 Third Avenue',
        'description' => 'Midtown East / Turtle Bay full-blockfront office tower with a three-level privately-owned public space (POPS) including covered pedestrian arcade and seating.',
        'base_url' => 'https://875third.com/',
        'location' => '875 Third Ave. Public Space',
    ],
    [
        'name' => 'Home Studios Inc.',
        'description' => 'Flatiron event venue at 873 Broadway with three daylight studio spaces used for film/photo shoots, private events, and corporate gatherings.',
        'base_url' => 'https://www.homestudiosinc.com/',
        'location' => '873 Broadway',
    ],
    [
        'name' => 'Academy for Advanced Women\'s Health Medicine',
        'description' => 'Education and clinical training organization founded by Dr. Heather Hirsch, headquartered at 227 W 29th St — runs Grand Rounds lectures, courses, and conferences on women\'s health and menopause.',
        'base_url' => 'https://www.academyaawhm.com/',
        'location' => '227 W 29th St',
    ],
    [
        'name' => 'Northern Manhattan Arts Alliance (NoMAA)',
        'description' => 'Arts service organization in Washington Heights / Inwood — produces the Community Subway Elevator Program rotating poster exhibitions inside the 181 St and 190 St A-train elevators.',
        'base_url' => 'https://www.nomaanyc.org/',
        'location' => 'A train 181 and 190 Street subway elevators',
    ],
    [
        'name' => 'Times Square Tower',
        'description' => 'Skidmore, Owings & Merrill–designed 47-story office tower at 7 Times Square (Broadway & W 41st) housing law firms and corporate tenants — hosts industry summits and tenant events.',
        'base_url' => 'https://7timessquare.com/',
        'location' => '7 Times Sq',
    ],
    [
        'name' => 'International Burgers',
        'description' => 'Midtown East burger restaurant on East 45th Street with globally-inspired sandwich combinations.',
        'base_url' => 'https://iburgers.com/',
        'location' => 'International Burgers',
    ],
    [
        'name' => 'Our Saviour New York',
        'description' => 'Hell\'s Kitchen Roman Catholic parish in the Late Victorian Gothic 1886 landmark at 417 W 57th St (designed by Francis H. Kimball) — also a concert venue for the Choir of Our Saviour and Sacred Hearts.',
        'base_url' => 'https://oursaviournyc.org/',
        'location' => 'Our Saviour New York',
    ],
    [
        'name' => 'Community United Methodist Church (Jackson Heights)',
        'description' => 'Jackson Heights Queens United Methodist Church (One Church NYC) hosting the monthly Methodist Flea Market and community programming.',
        'base_url' => 'https://onechurchnyc.com/',
        'location' => 'Community United Methodist Church (Jackson Heights)',
    ],
    [
        'name' => 'Bronx Borough Hall',
        'description' => 'Office of the Bronx Borough President in the Mario Merola Building at 851 Grand Concourse — hosts public programming, resource fairs, and community celebrations in the Rotunda.',
        'base_url' => 'https://bronxboropres.nyc.gov/',
        'location' => 'Bronx Borough Hall',
    ],
    [
        'name' => 'Tangram (Flushing)',
        'description' => 'Mixed-use shopping and entertainment complex in downtown Flushing with retail, a food hall, Regal Cinemas, and event space.',
        'base_url' => 'https://tangramnyc.com/',
        'location' => 'Tangram (Flushing)',
    ],
    [
        'name' => 'Amnon\'s Kosher Pizza',
        'description' => 'Borough Park Brooklyn kosher pizzeria and bakery on 13th Avenue, family-run since 1979 — hosts community craft circles and gatherings.',
        'base_url' => 'https://amnonskosherpizza.com/',
        'location' => 'Amnon\'s Kosher Pizza',
    ],
    [
        'name' => 'Breads Bakery',
        'description' => 'Israeli-style artisanal bakery (Union Square flagship at 18 E 16th St) known for chocolate babka, challah, and rugelach — multiple Manhattan locations.',
        'base_url' => 'https://breadsbakery.com/',
        'location' => 'Breads Bakery',
    ],
    [
        'name' => 'Wikipedia — Fordham, Bronx',
        'description' => 'Wikipedia article for Fordham, a neighborhood in the Bronx.',
        'base_url' => 'https://en.wikipedia.org/wiki/Fordham,_Bronx',
        'location' => 'Fordham',
    ],
    [
        'name' => 'Wikipedia — Clinton Hill, Brooklyn',
        'description' => 'Wikipedia article for Clinton Hill, a neighborhood in Brooklyn.',
        'base_url' => 'https://en.wikipedia.org/wiki/Clinton_Hill,_Brooklyn',
        'location' => 'Clinton Hill',
    ],
    [
        'name' => 'Wikipedia — Fort Greene, Brooklyn',
        'description' => 'Wikipedia article for Fort Greene, a neighborhood in Brooklyn.',
        'base_url' => 'https://en.wikipedia.org/wiki/Fort_Greene,_Brooklyn',
        'location' => 'Fort Greene',
    ],
    [
        'name' => 'Wikipedia — Cobble Hill, Brooklyn',
        'description' => 'Wikipedia article for Cobble Hill, a neighborhood in Brooklyn.',
        'base_url' => 'https://en.wikipedia.org/wiki/Cobble_Hill,_Brooklyn',
        'location' => 'Cobble Hill',
    ],
    [
        'name' => 'Wikipedia — Boerum Hill',
        'description' => 'Wikipedia article for Boerum Hill, a neighborhood in Brooklyn.',
        'base_url' => 'https://en.wikipedia.org/wiki/Boerum_Hill',
        'location' => 'Boerum Hill',
    ],
    [
        'name' => 'Wikipedia — Brighton Beach',
        'description' => 'Wikipedia article for Brighton Beach, a neighborhood in Brooklyn.',
        'base_url' => 'https://en.wikipedia.org/wiki/Brighton_Beach',
        'location' => 'Brighton Beach',
    ],
    [
        'name' => 'Wikipedia — East New York',
        'description' => 'Wikipedia article for East New York, a neighborhood in Brooklyn.',
        'base_url' => 'https://en.wikipedia.org/wiki/East_New_York',
        'location' => 'East New York',
    ],
    [
        'name' => 'Wikipedia — Stapleton, Staten Island',
        'description' => 'Wikipedia article for Stapleton, a neighborhood on Staten Island.',
        'base_url' => 'https://en.wikipedia.org/wiki/Stapleton,_Staten_Island',
        'location' => 'Stapleton',
    ],
    [
        'name' => 'Wikipedia — St. George, Staten Island',
        'description' => 'Wikipedia article for St. George, a neighborhood on Staten Island.',
        'base_url' => 'https://en.wikipedia.org/wiki/St._George,_Staten_Island',
        'location' => 'St. George',
    ],
    [
        'name' => 'Wikipedia — Castle Hill, Bronx',
        'description' => 'Wikipedia article for Castle Hill, a neighborhood in the Bronx.',
        'base_url' => 'https://en.wikipedia.org/wiki/Castle_Hill,_Bronx',
        'location' => 'Castle Hill',
    ],
    [
        'name' => 'Wikipedia — Morris Park, Bronx',
        'description' => 'Wikipedia article for Morris Park, a neighborhood in the Bronx.',
        'base_url' => 'https://en.wikipedia.org/wiki/Morris_Park,_Bronx',
        'location' => 'Morris Park',
    ],
    [
        'name' => 'Wikipedia — West Farms, Bronx',
        'description' => 'Wikipedia article for West Farms, a neighborhood in the Bronx.',
        'base_url' => 'https://en.wikipedia.org/wiki/West_Farms,_Bronx',
        'location' => 'West Farms',
    ],
    [
        'name' => 'St. Patrick\'s Cathedral',
        'description' => 'Largest Roman Catholic cathedral in the United States, occupying a Midtown Manhattan block bounded by Fifth Ave, Madison Ave, 50th & 51st St — hosts Masses, organ recitals, and the Cathedral Concert Series.',
        'base_url' => 'https://saintpatrickscathedral.org/',
        'location' => 'St. Patrick\'s Cathedral',
    ],
    [
        'name' => 'The Lighthouse at Chelsea Piers',
        'description' => 'Waterfront event venue at the end of Pier 61, Chelsea Piers — 10,000 sq ft hall with Hudson River views and a glass terrace for galas, conferences, and weddings.',
        'base_url' => 'https://piersixty.com/venues/the-lighthouse/',
        'location' => 'The Lighthouse at Chelsea Piers',
    ],
    [
        'name' => 'ModernHaus SoHo',
        'description' => 'Boutique hotel at 27 Grand Street in SoHo with the JIMMY rooftop bar and pool deck on the 18th floor.',
        'base_url' => 'https://www.modernhaushotel.com/',
        'location' => 'ModernHaus SoHo',
    ],
    [
        'name' => 'Long Beach Public Library',
        'description' => 'Long Beach, NY public library main branch on West Park Avenue (Nassau County) — events programming, meeting spaces, and three branches.',
        'base_url' => 'https://longbeachlibrary.org/',
        'location' => 'Long Beach Public Library',
    ],
    [
        'name' => 'The Viscardi Center',
        'description' => 'Albertson, Long Island nonprofit (founded 1952) serving people with disabilities — operates Henry Viscardi School, Abilities Inc., and the Kornreich Technology Center.',
        'base_url' => 'https://www.viscardicenter.org/',
        'location' => 'The Viscardi Center',
    ],
    [
        'name' => 'City Coffee & Bar',
        'description' => 'Upper West Side café (Columbus Ave) — coffee + brunch by day, Latin/Caribbean lounge with DJs and hookah by night.',
        'base_url' => 'https://citycoffeebar.com/',
        'location' => 'City Coffee & Bar',
    ],
    [
        'name' => 'Dolly\'s Swing & Dive',
        'description' => 'Williamsburg Brooklyn neighborhood cocktail bar (Wythe Ave location since 2026) — frozen drinks, signature cocktails, and a Dolly Parton bathroom shrine.',
        'base_url' => 'https://www.dollysbk.com/',
        'location' => 'Dolly\'s Swing & Dive',
    ],
    [
        'name' => 'Aura Cocina & Bar',
        'description' => 'East Williamsburg Brooklyn Cuban–Asian fusion restaurant and bar with live music Friday and Saturday nights.',
        'base_url' => 'https://auracocinanyc.com/',
        'location' => 'Aura Cocina & Bar',
    ],
    [
        'name' => 'Rebecca\'s Bar',
        'description' => 'Bushwick Brooklyn neighborhood bar (since 2016) at Jefferson & Bushwick Ave — late-night reggaeton/cumbia DJs and a small dance floor, from the team behind Norbert\'s Pizza.',
        'base_url' => 'https://www.rebeccasbar.com/',
        'location' => 'Rebecca\'s Bar',
    ],
    [
        'name' => 'Ore Bar',
        'description' => 'Williamsburg Brooklyn rustic pub on Graham Ave with weekend DJs, dancing, draft beer, a backyard, and rotating pop-up food vendors.',
        'base_url' => 'http://www.orebar.com/',
        'location' => 'Ore Bar',
    ],
    [
        'name' => 'Madame George',
        'description' => 'Subterranean Midtown West cocktail lounge (opened 2022) on West 45th St — vintage NYC cocktail program, live music Mon–Sat.',
        'base_url' => 'https://www.madamegeorgenyc.com/',
        'location' => 'Madame George',
    ],
    [
        'name' => 'Famous Last Words',
        'description' => 'Clinton Hill Brooklyn tropical/tiki bar from the team behind Hanson Dry — Margarita Mondays, monthly art shows, and a heated backyard.',
        'base_url' => 'https://www.famouslastwordsbk.com/',
        'location' => 'Famous Last Words',
    ],
    [
        'name' => 'Coffee Uplifts People',
        'description' => 'Bed-Stuy Brooklyn specialty coffee shop and roaster founded 2020 — direct-trade beans, POC-led supply chain, community-focused café programming.',
        'base_url' => 'https://coffeeupliftspeople.com/',
        'location' => 'Coffee Uplifts People (CUP)',
    ],
    [
        'name' => 'Aftermath NYC',
        'description' => 'Ridgewood Queens cocktail bar with empanadas and pasta from Chef Frances — hosts salsa/bachata nights and DJ events.',
        'base_url' => 'https://www.aftermathnyc.com/',
        'location' => 'Aftermath NYC',
    ],
    [
        'name' => 'Taglialatella Galleries',
        'description' => 'Chelsea contemporary art gallery (since 1978) on 10th Ave specializing in Pop and Street Art, with sister locations in Palm Beach, Paris, and Toronto.',
        'base_url' => 'https://www.taglialatellagalleries.com/',
        'location' => 'Taglialatella Galleries',
    ],
    [
        'name' => 'Wikipedia — Prospect Heights, Brooklyn',
        'description' => 'Wikipedia article for Prospect Heights, a neighborhood in Brooklyn.',
        'base_url' => 'https://en.wikipedia.org/wiki/Prospect_Heights,_Brooklyn',
        'location' => 'Prospect Heights',
    ],
    [
        'name' => 'Wikipedia — Sunset Park, Brooklyn',
        'description' => 'Wikipedia article for Sunset Park, a neighborhood in Brooklyn.',
        'base_url' => 'https://en.wikipedia.org/wiki/Sunset_Park,_Brooklyn',
        'location' => 'Sunset Park',
    ],
    [
        'name' => 'Wikipedia — Forest Hills, Queens',
        'description' => 'Wikipedia article for Forest Hills, a neighborhood in Queens.',
        'base_url' => 'https://en.wikipedia.org/wiki/Forest_Hills,_Queens',
        'location' => 'Forest Hills',
    ],
    [
        'name' => 'Wikipedia — Jackson Heights, Queens',
        'description' => 'Wikipedia article for Jackson Heights, a neighborhood in Queens.',
        'base_url' => 'https://en.wikipedia.org/wiki/Jackson_Heights,_Queens',
        'location' => 'Jackson Heights',
    ],
    [
        'name' => 'Wikipedia — Flushing, Queens',
        'description' => 'Wikipedia article for Flushing, a neighborhood in Queens.',
        'base_url' => 'https://en.wikipedia.org/wiki/Flushing,_Queens',
        'location' => 'Flushing',
    ],
    [
        'name' => 'Wikipedia — Jamaica, Queens',
        'description' => 'Wikipedia article for Jamaica, a neighborhood in Queens.',
        'base_url' => 'https://en.wikipedia.org/wiki/Jamaica,_Queens',
        'location' => 'Jamaica',
    ],
    [
        'name' => 'Wikipedia — Mott Haven, Bronx',
        'description' => 'Wikipedia article for Mott Haven, a neighborhood in the Bronx.',
        'base_url' => 'https://en.wikipedia.org/wiki/Mott_Haven,_Bronx',
        'location' => 'Mott Haven',
    ],
    // 2026-05-01 — informational website entries for top-25 unlinked event venues.
    [
        'name' => 'The Keep',
        'description' => 'Ridgewood dive bar and late-night hangout featuring pool tables, jukebox selections, and a loyal neighborhood crowd.',
        'base_url' => 'https://thekeepnyc.com',
        'location' => 'The Keep',
        'tags' => ['Queens', 'Ridgewood', 'Bar'],
    ],
    [
        'name' => 'Arlo Williamsburg',
        'description' => 'Boutique hotel in Williamsburg (formerly The Williamsburg Hotel) with rooftop pool and bar, hosting events and social programming.',
        'base_url' => 'https://arlohotels.com/williamsburg',
        'location' => 'Arlo Williamsburg',
        'tags' => ['Brooklyn', 'Williamsburg', 'Hotel'],
    ],
    [
        'name' => 'Sweet Avenue',
        'description' => 'Sunnyside bottle shop and tap room near the 7 Train, featuring rotating American craft beers and weekly Tuesday trivia.',
        'base_url' => 'https://www.sweetavenuenyc.com',
        'location' => 'Sweet Avenue',
        'tags' => ['Queens', 'Sunnyside', 'Bar'],
    ],
    // 2026-05-01 batch 2 — informational website entries for next-25 unlinked event venues.
    [
        'name' => 'Bay Ridge Library',
        'description' => 'Brooklyn Public Library branch in Bay Ridge offering programs, classes, and events for the local community.',
        'base_url' => 'https://www.bklynlibrary.org/locations/bay-ridge',
        'location' => 'Bay Ridge Library',
        'tags' => ['Brooklyn', 'Bay Ridge', 'Library'],
    ],
    [
        'name' => 'Sheffield Garden',
        'description' => 'East New York community farm and garden run by the Sheffield South Block Association since 1990.',
        'base_url' => 'https://bqlt.org/garden/sheffield-garden',
        'location' => 'Sheffield Garden',
        'tags' => ['Brooklyn', 'East New York', 'Garden', 'Outdoor'],
    ],
    [
        'name' => 'Ralph Ellison Plaza',
        'description' => 'Public plaza on Riverside Drive in Hamilton Heights honoring author Ralph Ellison, hosting summer outdoor performances.',
        'base_url' => 'https://www.nycgovparks.org/parks/ralph-ellison-park',
        'location' => 'Ralph Ellison Plaza',
        'tags' => ['Manhattan', 'Hamilton Heights', 'Park', 'Outdoor'],
    ],
    [
        'name' => 'Croton Point Park',
        'description' => 'Westchester County park on a peninsula in the Hudson River, offering camping, hiking, swimming, and seasonal performances.',
        'base_url' => 'https://parks.westchestergov.com/croton-point-park',
        'location' => 'Croton Point Park',
        'tags' => ['Westchester', 'Park', 'Outdoor'],
    ],
    [
        'name' => "McSwiggan's Pub",
        'description' => 'Hoboken Irish pub and sports bar on 1st Street with live music on weekends, brunch, and pub-grub specials.',
        'base_url' => 'https://www.mcswigganshoboken.com',
        'location' => "McSwiggan's Pub",
        'tags' => ['New Jersey', 'Hoboken', 'Bar'],
    ],
    [
        'name' => 'OFVS Williamsburg Studio',
        'description' => 'Our Fabulous Variety Show production studio at the Most Holy Trinity church complex in Williamsburg, hosting circus, drag, and variety performances.',
        'base_url' => 'https://www.ofvs.org',
        'location' => 'OFVS Studio at Most Holy Trinity',
        'tags' => ['Brooklyn', 'Williamsburg', 'Theater'],
    ],
    [
        'name' => 'The Summit Playhouse',
        'description' => 'Non-profit community theatre in Summit, NJ — one of the oldest continuously operating community theatres in the US, founded 1918.',
        'base_url' => 'https://www.thesummitplayhouse.org',
        'location' => 'The Summit Playhouse',
        'tags' => ['New Jersey', 'Theater'],
    ],
    [
        'name' => 'Heckscher Museum of Art',
        'description' => 'Beaux-Arts art museum in Heckscher Park, Huntington, with 2,300+ works focused on American and Long Island artists.',
        'base_url' => 'https://www.heckscher.org',
        'location' => 'Heckscher Museum of Art',
        'tags' => ['Long Island', 'Museum', 'Art'],
    ],
    [
        'name' => '5th House Studios',
        'description' => 'Williamsburg private production and event space in a 1920s brick machine shop, featuring a gallery, vintage loft, garden, and rooftop deck.',
        'base_url' => 'https://www.5thouse.com',
        'location' => '5th House Studios',
        'tags' => ['Brooklyn', 'Williamsburg', 'Event Space'],
    ],
    // 2026-05-01 batch 3 — informational website entries for next-25 unlinked event venues.
    [
        'name' => 'Fordham Road BID',
        'description' => 'Bronx business improvement district managing the Fordham Road shopping corridor, hosting walking tours, public art programs, and free outdoor events.',
        'base_url' => 'https://www.fordhamroadbid.org',
        'location' => 'Fordham Road BID',
        'tags' => ['Bronx', 'Fordham', 'Outdoor'],
    ],
    [
        'name' => 'Battery Park City Authority',
        'description' => 'Public benefit corporation that runs free community programs, exercise classes, and cultural events throughout Battery Park City — including 6 River Terrace.',
        'base_url' => 'https://bpca.ny.gov',
        'location' => '6 River Terrace',
        'tags' => ['Manhattan', 'Battery Park City', 'Community Center', 'Free'],
    ],
    [
        'name' => 'Tapville Social Jersey City',
        'description' => 'Self-pour craft beer, wine, and cocktail taproom inside Newport Centre Mall with 64+ taps and weekly board game nights.',
        'base_url' => 'https://www.tapvillesocial.com/jerseycity',
        'location' => 'TapVille',
        'tags' => ['New Jersey', 'Jersey City', 'Bar'],
    ],
    [
        'name' => 'Chelsea Industrial',
        'description' => '22,000 sq ft transformative event venue on West 28th Street with 18ft ceilings and 3 distinct rooms — hosting fundraisers, trade shows, and cultural events.',
        'base_url' => 'https://chelseaindustrial.com',
        'location' => 'Chelsea Industrial',
        'tags' => ['Manhattan', 'Chelsea', 'Event Space'],
    ],
    [
        'name' => "Fool's Gold NYC",
        'description' => 'Lower East Side craft beer bar on Houston Street with 34 drafts, full whiskey bar, weekly trivia, darts, and board games.',
        'base_url' => 'https://foolsgoldnyc.com',
        'location' => "Fool's Gold",
        'tags' => ['Manhattan', 'Lower East Side', 'Bar'],
    ],
    [
        'name' => 'Jackson Square (NYC Parks)',
        'description' => 'Triangular West Village park at Greenwich Avenue and 8th Avenue, hosting walking tours and seasonal community programming.',
        'base_url' => 'https://www.nycgovparks.org/parks/jackson-square',
        'location' => 'Jackson Square',
        'tags' => ['Manhattan', 'West Village', 'Park', 'Outdoor'],
    ],
    [
        'name' => 'ELOREA',
        'description' => 'Modern Korean perfumery and gallery space showcasing Korean artisans alongside fragrance launches and tasting events.',
        'base_url' => 'https://elorea.com',
        'location' => 'ELOREA',
        'tags' => ['Manhattan', 'Lower East Side', 'Art'],
    ],
    [
        'name' => 'Ferry Point Park (NYC Parks)',
        'description' => 'Bronx waterfront park along the East River with sports fields, walking paths, and seasonal community events.',
        'base_url' => 'https://www.nycgovparks.org/parks/ferry-point-park',
        'location' => 'Ferry Point Park',
        'tags' => ['Bronx', 'Park', 'Outdoor'],
    ],
    [
        'name' => 'Old Cathedral Outdoor Market',
        'description' => "Outdoor market on the historic grounds of Old St. Patrick's Cathedral in Nolita, hosting artisan vendors and community events.",
        'base_url' => 'https://oldcathedral.org',
        'location' => 'Old Cathedral Outdoor Market',
        'tags' => ['Manhattan', 'Nolita', 'Outdoor'],
    ],
    [
        'name' => 'Shoelace Park (NYC Parks)',
        'description' => 'Linear park along the Bronx River Greenway named for its long, narrow shape — hosting bike tours and outdoor programming.',
        'base_url' => 'https://www.nycgovparks.org/parks/shoelace-park',
        'location' => 'Shoelace Park',
        'tags' => ['Bronx', 'Park', 'Outdoor'],
    ],
    [
        'name' => 'Tappeto Volante Gallery',
        'description' => 'Gowanus contemporary art gallery and project space supporting underrepresented artists, performers, and emerging curators (since 2020).',
        'base_url' => 'https://tappetovolantegallery.com',
        'location' => 'Tappeto Volante Gallery',
        'tags' => ['Brooklyn', 'Gowanus', 'Art'],
    ],
    [
        'name' => 'Pat Auletta Steeplechase Pier',
        'description' => 'Coney Island fishing pier on the Riegelmann Boardwalk, hosting community walks, fishing programs, and seasonal events.',
        'base_url' => 'https://www.nycgovparks.org/parks/coney-island-beach-and-boardwalk',
        'location' => 'Pat Auletta Steeplechase Pier',
        'tags' => ['Brooklyn', 'Coney Island', 'Outdoor'],
    ],
    [
        'name' => '30th Street Theater (Urban Stages)',
        'description' => '75-seat Off-Broadway theater in Chelsea operated by Urban Stages, championing diverse stories and emerging artists with low or free ticket pricing.',
        'base_url' => 'https://www.urbanstages.org',
        'location' => '30th Street Theater (Urban Stages)',
        'tags' => ['Manhattan', 'Chelsea', 'Theater'],
    ],
    // 2026-05-01 batch 4 — informational website entries for next-25 unlinked event venues.
    [
        'name' => 'CSB Fine Arts',
        'description' => 'DUMBO contemporary art gallery representing Puerto Rican and Latin American artists, with exhibitions exploring identity, memory, culture, and abstraction.',
        'base_url' => 'https://csbfinearts.com',
        'location' => 'CSB Fine Arts',
        'tags' => ['Brooklyn', 'DUMBO', 'Art'],
    ],
    [
        'name' => 'Bronx Borough Hall Greenmarket',
        'description' => 'GrowNYC-run Greenmarket at Bronx Borough Hall offering fresh produce from regional farms — a SNAP and EBT-friendly source of locally-grown food.',
        'base_url' => 'https://www.grownyc.org/greenmarket/bronx-borough-hall',
        'location' => 'Bronx Borough Hall Greenmarket',
        'tags' => ['Bronx', 'Greenmarket', 'Outdoor'],
    ],
    [
        'name' => 'East Flatbush Library',
        'description' => 'Brooklyn Public Library branch on Church Avenue offering programs, classes, and events for the East Flatbush community.',
        'base_url' => 'https://www.bklynlibrary.org/locations/east-flatbush',
        'location' => 'East Flatbush Library',
        'tags' => ['Brooklyn', 'East Flatbush', 'Library'],
    ],
    [
        'name' => 'Jackie Robinson Park (NYC Parks)',
        'description' => 'Harlem park named for the baseball pioneer, hosting summer concerts, family events, and recreational programming.',
        'base_url' => 'https://www.nycgovparks.org/parks/jackie-robinson-park',
        'location' => 'Jackie Robinson Park',
        'tags' => ['Manhattan', 'Harlem', 'Park', 'Outdoor'],
    ],
    [
        'name' => 'Seward Park (NYC Parks)',
        'description' => 'Lower East Side public park at Canal and Essex streets — the first municipally-built playground in the country, hosting tours and community events.',
        'base_url' => 'https://www.nycgovparks.org/parks/seward-park',
        'location' => 'Seward Park',
        'tags' => ['Manhattan', 'Lower East Side', 'Park', 'Outdoor'],
    ],
    [
        'name' => "St. Anthony's Market",
        'description' => 'Outdoor weekend market on Houston Street between MacDougal and Sullivan, with two blocks of arts, crafts, vintage items, and street food.',
        'base_url' => 'https://stanthonynyc.org/st-anthony-market',
        'location' => "St. Anthony's Market",
        'tags' => ['Manhattan', 'SoHo', 'Outdoor'],
    ],
    [
        'name' => 'East River Waterfront Esplanade',
        'description' => 'Lower Manhattan waterfront promenade along South Street with public art, walking and cycling paths, and seasonal events.',
        'base_url' => 'https://www.lowermanhattan.info/explore/parks-public-spaces/east-river-esplanade',
        'location' => 'East River Waterfront Esplanade',
        'tags' => ['Manhattan', 'Financial District', 'Outdoor'],
    ],
    [
        'name' => 'Our Lady of Mount Carmel Church (Bronx)',
        'description' => 'Romanesque-style Roman Catholic parish in Belmont (Bronx Little Italy), founded in 1906 to serve Italian immigrants — host to the annual Feast of Our Lady of Mt. Carmel.',
        'base_url' => 'https://ourladymtcarmelbx.org',
        'location' => 'Our Lady of Mount Carmel Church',
        'tags' => ['Bronx', 'Belmont', 'Church'],
    ],
    [
        'name' => 'Mt. Ollie Baptist Church',
        'description' => 'Historic Baptist church in the Brownsville district of Brooklyn, hosting community gatherings and worship services.',
        'base_url' => 'http://www.mtolliebaptistchurch.org',
        'location' => 'Mt. Ollie Baptist Church',
        'tags' => ['Brooklyn', 'Brownsville', 'Church'],
    ],
    [
        'name' => 'Eibs Pond Park (NYC Parks)',
        'description' => 'Staten Island park surrounding a freshwater pond, with nature trails, wildlife viewing, and community programs.',
        'base_url' => 'https://www.nycgovparks.org/parks/eibs-pond-park',
        'location' => 'Eibs Pond Park',
        'tags' => ['Staten Island', 'Park', 'Outdoor'],
    ],
    [
        'name' => "Triona's On Third",
        'description' => 'Gramercy Irish pub and sports bar with pool tables, dartboards, and a strong beer selection.',
        'base_url' => 'https://easttrionasnyc.com',
        'location' => "Triona's On Third",
        'tags' => ['Manhattan', 'Gramercy', 'Bar'],
    ],
    [
        'name' => "Triona's Sullivan Street",
        'description' => 'Greenwich Village Irish pub and sports bar with pool tables and weekly trivia nights.',
        'base_url' => 'https://nyctrionas.com',
        'location' => "Triona's Sullivan Street",
        'tags' => ['Manhattan', 'Greenwich Village', 'Bar'],
    ],
    [
        'name' => 'Beach 109th Street Boardwalk',
        'description' => 'Section of the Rockaway Beach Boardwalk at Beach 109th Street in Queens, hosting outdoor concerts and beach community events.',
        'base_url' => 'https://www.nycgovparks.org/parks/rockaway-beach-and-boardwalk',
        'location' => 'Beach 109th Street Boardwalk',
        'tags' => ['Queens', 'Rockaway Beach', 'Beach', 'Outdoor'],
    ],
    // 2026-05-01 batch 6 — informational website entries for next-25 unlinked event venues.
    [
        'name' => 'Coney Island Beach & Boardwalk (NYC Parks)',
        'description' => 'Iconic Brooklyn beach and 2.7-mile Riegelmann Boardwalk, hosting concerts, fireworks, the annual Mermaid Parade, and seasonal community events.',
        'base_url' => 'https://www.nycgovparks.org/parks/coney-island-beach-and-boardwalk',
        'location' => 'Coney Island Beach & Boardwalk',
        'tags' => ['Brooklyn', 'Coney Island', 'Beach', 'Outdoor'],
    ],
    [
        'name' => 'Edenwald Library',
        'description' => 'New York Public Library branch in the Edenwald neighborhood of the Bronx offering programs and events for the community.',
        'base_url' => 'https://www.nypl.org/locations/edenwald',
        'location' => 'Edenwald Library',
        'tags' => ['Bronx', 'Edenwald', 'Library'],
    ],
    [
        'name' => 'J.J. Byrne Playground (Washington Park, NYC Parks)',
        'description' => 'Park Slope playground inside Washington Park (3rd Street between 4th and 5th Avenues), hosting outdoor concerts, family programs, and seasonal events.',
        'base_url' => 'https://www.nycgovparks.org/parks/washington-park-brooklyn',
        'location' => 'J.J. Byrne Playground',
        'tags' => ['Brooklyn', 'Park Slope', 'Park', 'Outdoor'],
    ],
    [
        'name' => 'Laurelton Library (Queens Public Library)',
        'description' => 'Queens Public Library branch in Laurelton offering programs, classes, and events for the surrounding community.',
        'base_url' => 'https://www.queenslibrary.org/about-us/our-locations/laurelton',
        'location' => 'Laurelton Library',
        'tags' => ['Queens', 'Laurelton', 'Library'],
    ],
    [
        'name' => 'Mt. Olivet Baptist Church (Harlem)',
        'description' => 'Historic Harlem Baptist church (founded 1878) housed in a former Temple Israel synagogue on Malcolm X Boulevard, hosting community gatherings and worship services.',
        'base_url' => 'http://mountolivetbaptistchurch.org',
        'location' => 'Mt. Olivet Baptist Church',
        'tags' => ['Manhattan', 'Harlem', 'Church'],
    ],
    [
        'name' => 'New Amsterdam Library',
        'description' => 'New York Public Library branch in Tribeca on Murray Street offering programs, classes, and community events.',
        'base_url' => 'https://www.nypl.org/locations/new-amsterdam',
        'location' => 'New Amsterdam Library',
        'tags' => ['Manhattan', 'Tribeca', 'Library'],
    ],
    [
        'name' => 'St. Nicholas Park (NYC Parks)',
        'description' => 'Hilly Hamilton Heights park along St. Nicholas Avenue, hosting summer concerts, community programs, and outdoor events.',
        'base_url' => 'https://www.nycgovparks.org/parks/st-nicholas-park',
        'location' => 'St. Nicholas Park',
        'tags' => ['Manhattan', 'Hamilton Heights', 'Park', 'Outdoor'],
    ],
    [
        'name' => 'The Connelly Theater',
        'description' => 'Historic Off-Broadway theater in the East Village (built 1860s), with a distinctive gold proscenium and intimate seating — proceeds support the Cornelia Connelly Center.',
        'base_url' => 'https://www.connellytheater.org',
        'location' => 'The Connelly Theater',
        'tags' => ['Manhattan', 'East Village', 'Theater'],
    ],
    [
        'name' => 'St. Francis College',
        'description' => 'Brooklyn Catholic college on Livingston Street hosting public lectures, concerts, athletics, and cultural events.',
        'base_url' => 'https://www.sfc.edu',
        'location' => 'St Francis College',
        'tags' => ['Brooklyn', 'Downtown Brooklyn', 'Education', 'College'],
    ],
    [
        'name' => 'Devoe Park (NYC Parks)',
        'description' => 'Bronx neighborhood park near Fordham University with athletic fields, summer concerts, and community programming.',
        'base_url' => 'https://www.nycgovparks.org/parks/devoe-park',
        'location' => 'Devoe Park',
        'tags' => ['Bronx', 'Fordham', 'Park', 'Outdoor'],
    ],
    [
        'name' => 'Phil "Scooter" Rizzuto Park (NYC Parks)',
        'description' => 'Queens park in South Richmond Hill named for the Yankees shortstop, with athletic fields, playgrounds, and outdoor community events.',
        'base_url' => 'https://www.nycgovparks.org/parks/phil-rizzuto-park',
        'location' => 'Phil "Scooter" Rizzuto Park',
        'tags' => ['Queens', 'Richmond Hill', 'Park', 'Outdoor'],
    ],
    [
        'name' => 'Brownsville Heritage House',
        'description' => 'Brownsville cultural center (since 1981) on the second floor of the Stone Avenue Library, housing local history archives and hosting jazz, art, and youth programs.',
        'base_url' => 'https://www.brownsvilleheritagehouse.org',
        'location' => 'Brownsville Heritage House',
        'tags' => ['Brooklyn', 'Brownsville', 'Cultural Center'],
    ],
    [
        'name' => 'Mishkin Gallery (Baruch College)',
        'description' => 'Free contemporary art gallery at Baruch College/CUNY in Gramercy, with rotating exhibitions and public programs.',
        'base_url' => 'https://weissman.baruch.cuny.edu/mishkin-gallery',
        'location' => 'Mishkin Gallery',
        'tags' => ['Manhattan', 'Gramercy', 'Art', 'Free'],
    ],
    [
        'name' => 'Montclair Art Museum',
        'description' => 'Montclair NJ museum focused on American and Native American art, with rotating exhibitions, family programs, and public events.',
        'base_url' => 'https://www.montclairartmuseum.org',
        'location' => 'Montclair Art Museum',
        'tags' => ['New Jersey', 'Montclair', 'Museum', 'Art'],
    ],
    [
        'name' => 'Brooklyn Masonic Temple',
        'description' => 'Historic Clinton Hill venue with towering columns and a spacious main room, hosting indie/hip-hop concerts, DJ sets, podcasts, and stand-up comedy.',
        'base_url' => 'http://brooklynmasonictempleny.com',
        'location' => 'Brooklyn Masonic Temple',
        'tags' => ['Brooklyn', 'Clinton Hill', 'Live Music', 'Event Space'],
    ],
    [
        'name' => 'Espresso 77',
        'description' => 'Independent Jackson Heights all-day cafe with espresso, breakfast, sandwiches, rotating local-artist gallery shows, and the monthly Jackson Heights Art Talks program.',
        'base_url' => 'http://www.espresso77.com',
        'location' => 'Espresso 77',
        'tags' => ['Queens', 'Jackson Heights', 'Cafe'],
    ],
    [
        'name' => 'Fort Tilden (Gateway National Recreation Area)',
        'description' => 'Former military base turned National Park Service beach and nature preserve in Breezy Point, with WWII bunkers, art studios, and seasonal community events.',
        'base_url' => 'https://www.nps.gov/gate/learn/historyculture/fort-tilden',
        'location' => 'Fort Tilden',
        'tags' => ['Queens', 'Rockaway Beach', 'Beach', 'Outdoor'],
    ],
    [
        'name' => "Powell's Cove Park (NYC Parks)",
        'description' => 'Whitestone waterfront park along the East River with marshland, walking paths, and outdoor community events.',
        'base_url' => 'https://www.nycgovparks.org/parks/powells-cove-park',
        'location' => "Powell's Cove Park",
        'tags' => ['Queens', 'Whitestone', 'Park', 'Outdoor'],
    ],
    [
        'name' => 'Arverne East Nature Preserve',
        'description' => 'Far Rockaway nature preserve with restored coastal habitat, walking trails, and outdoor environmental programs.',
        'base_url' => 'https://www.nycgovparks.org/parks/arverne-east-nature-preserve',
        'location' => 'Arverne East Nature Preserve',
        'tags' => ['Queens', 'Far Rockaway', 'Beach', 'Outdoor'],
    ],
    [
        'name' => 'Pompeii Flea Market (Our Lady of Pompeii Church)',
        'description' => 'Outdoor weekend flea market on Bleecker Street near Leroy in the West Village (April–December), with handmade goods, vintage items, and crafts — proceeds benefit Our Lady of Pompeii Church.',
        'base_url' => 'https://www.olpchurch.org',
        'location' => 'Pompeii Flea Market',
        'tags' => ['Manhattan', 'West Village', 'Outdoor'],
    ],
    [
        'name' => 'Fordham Plaza (NYC DOT)',
        'description' => 'Bronx public plaza next to Fordham Road and the Metro-North station, hosting outdoor markets, concerts, and community events.',
        'base_url' => 'https://www.nyc.gov/html/dot/html/pedestrians/fordham-plaza.shtml',
        'location' => 'Fordham Plaza',
        'tags' => ['Bronx', 'Fordham', 'Outdoor'],
    ],
    // 2026-05-01 batch 7 — informational website entries for next-25 unlinked event venues.
    [
        'name' => 'Pugsley Creek Park (NYC Parks)',
        'description' => 'Bronx waterfront park along Pugsley Creek with marshland, hiking trails, and outdoor community events.',
        'base_url' => 'https://www.nycgovparks.org/parks/pugsley-creek-park',
        'location' => 'Pugsley Creek Park',
        'tags' => ['Bronx', 'Park', 'Outdoor'],
    ],
    [
        'name' => 'The Loft New York',
        'description' => 'Chinatown 1,750 sq ft dance and creative studio with parquet floor, mirrored wall, and projector — host to classes, workshops, and rehearsals.',
        'base_url' => 'https://www.peerspace.com/pages/listings/618c3fa5bdb172000d288abe',
        'location' => 'The Loft New York',
        'tags' => ['Manhattan', 'Chinatown', 'Dance', 'Event Space'],
    ],
    [
        'name' => 'Donna NYC',
        'description' => 'West Village worker-owned cocktail bar on Cornelia Street with a pan-Latin menu, Mediterranean influences, and Filipino-influenced cocktail program.',
        'base_url' => 'https://www.donnanyc.com',
        'location' => 'Donna',
        'tags' => ['Manhattan', 'West Village', 'Bar'],
    ],
    [
        'name' => 'Trailside Museums and Zoo',
        'description' => 'Bear Mountain State Park nature center with four small museums (herpetology, geology, nature, history) and a zoo of non-releasable native animals — free admission.',
        'base_url' => 'https://trailsidemuseumsandzoo.org',
        'location' => 'Trailside Museums and Zoo',
        'tags' => ['Hudson Valley', 'Museum', 'Outdoor'],
    ],
    [
        'name' => 'Andrew Freedman Home',
        'description' => 'Landmarked 1924 Bronx Concourse mansion (originally a retirement home) now operating as a multipurpose arts and events venue with exhibits, screenings, and workshops.',
        'base_url' => 'https://www.theafh.org',
        'location' => 'Andrew Freedman Home',
        'tags' => ['Bronx', 'Concourse', 'Cultural Center', 'Event Space'],
    ],
    [
        'name' => 'Bridgehampton Presbyterian Church',
        'description' => 'Hamptons church (founded 1660s, current building 1842) — a National Historic Place and home to the Bridgehampton Chamber Music Festival, the Choral Society of the Hamptons, antique fairs, and flea markets.',
        'base_url' => 'https://www.bridgehamptonpc.org',
        'location' => 'Bridgehampton Presbyterian Church',
        'tags' => ['Long Island', 'Church'],
    ],
    [
        'name' => 'Dobbin St',
        'description' => 'Greenpoint event venue in a transformed Brooklyn factory with 4,250 sq ft of indoor space, a 3,000 sq ft rooftop terrace with Manhattan skyline views, and a courtyard.',
        'base_url' => 'https://www.dobbinst.com',
        'location' => 'Dobbin St',
        'tags' => ['Brooklyn', 'Greenpoint', 'Event Space'],
    ],
    [
        'name' => 'Holy Trinity Episcopal Church (Greenport)',
        'description' => 'Episcopal church on the North Fork of Long Island (organized 1863), part of the North Fork Episcopal Ministries — hosts community concerts and gatherings alongside worship.',
        'base_url' => 'https://www.holytrinitygreenport.com',
        'location' => 'Holy Trinity Episcopal Church (Greenport)',
        'tags' => ['Long Island', 'Church'],
    ],
    [
        'name' => 'Shake Shack Meatpacking',
        'description' => 'Meatpacking District location of Shake Shack, the New York burger institution, hosting occasional pop-ups and community meetups.',
        'base_url' => 'https://shakeshack.com/location/meatpacking-ny',
        'location' => 'Shake Shack Meatpacking',
        'tags' => ['Manhattan', 'Meatpacking District', 'Restaurant'],
    ],
    [
        'name' => 'Genesee Valley Greenway State Park',
        'description' => 'Linear NY State park along a former canal and rail corridor running 90 miles through the Genesee Valley, with hiking, biking, and seasonal nature programs.',
        'base_url' => 'https://parks.ny.gov/visit/state-parks/genesee-valley-greenway-state-park',
        'location' => 'Genesee Valley Greenway State Park',
        'tags' => ['Western New York', 'Park', 'Outdoor'],
    ],
    [
        'name' => 'Hamlin Beach State Park',
        'description' => 'Lake Ontario beach in Hamlin NY (1,287 acres) with swimming, camping, fishing, and seasonal events.',
        'base_url' => 'https://parks.ny.gov/visit/state-parks/hamlin-beach-state-park',
        'location' => 'Hamlin Beach State Park',
        'tags' => ['Western New York', 'Beach', 'Outdoor'],
    ],
    [
        'name' => 'Living Room Theaters (Portland)',
        'description' => 'Independent cinema in downtown Portland, OR with a full bar/restaurant — primarily a satellite venue for touring film events.',
        'base_url' => 'https://pdx.livingroomtheaters.com',
        'location' => 'Living Room Theaters (Portland)',
        'tags' => ['Cinema'],
    ],
    [
        'name' => 'Arts Council for Wyoming County',
        'description' => 'Wyoming County (Western NY) arts council based in Perry, presenting visual arts exhibitions and live music in the historic Town Hall.',
        'base_url' => 'https://artswyco.org',
        'location' => 'Arts Council for Wyoming County',
        'tags' => ['Western New York', 'Art', 'Cultural Center'],
    ],
    // 2026-05-01 batch 8 — informational website entries for next-25 unlinked event venues.
    [
        'name' => '19 Washington Square North (NYU Abu Dhabi)',
        'description' => 'NYU Abu Dhabi New York office in a historic 19th-century townhouse on Washington Square North, hosting public lectures, conferences, and academic events.',
        'base_url' => 'https://nyuad.nyu.edu/en/about/the-nyuad-campus/19-washington-square-north.html',
        'location' => '19 Washington Square North',
        'tags' => ['Manhattan', 'Greenwich Village', 'Education'],
    ],
    [
        'name' => 'Record City BK',
        'description' => 'Brooklyn vintage record store in Prospect Lefferts Gardens specializing in reggae, soul, jazz, and rock — also a venue for community events and the Flatbush Comedy Festival.',
        'base_url' => 'https://recordcity.net',
        'location' => 'Record City',
        'tags' => ['Brooklyn', 'Music', 'Comedy'],
    ],
    [
        'name' => 'ErF World',
        'description' => '15,000 sq ft Bushwick artist-built studio collective with 40+ artists, hosting markets, showcases, workshops, and music events.',
        'base_url' => 'https://www.instagram.com/erf.nyc/',
        'location' => 'ErF World',
        'tags' => ['Brooklyn', 'Bushwick', 'Art', 'Live Music'],
    ],
    [
        'name' => 'Consulate General of India in NY',
        'description' => 'Diplomatic mission of India in NYC, hosting cultural events, lectures, and Indian Independence Day celebrations.',
        'base_url' => 'https://www.indiainnewyork.gov.in',
        'location' => 'Consulate General of India',
        'tags' => ['Manhattan', 'Upper East Side', 'Cultural Center'],
    ],
    [
        'name' => 'Consulate General of Hungary in NY',
        'description' => 'Diplomatic mission of Hungary in NYC, hosting cultural exchanges, lectures, and arts events.',
        'base_url' => 'https://newyork.mfa.gov.hu/eng',
        'location' => 'Consulate General of Hungary',
        'tags' => ['Manhattan', 'Midtown East', 'Cultural Center'],
    ],
    [
        'name' => 'United Irish Counties Association of NY',
        'description' => 'Long Island City hall of the United Irish Counties Association of New York (founded 1904), hosting Irish music, dance, comedy, and cultural events.',
        'base_url' => 'https://www.uicany.org',
        'location' => 'United Irish Cultural Center',
        'tags' => ['Queens', 'Long Island City', 'Cultural Center'],
    ],
    [
        'name' => 'Yonkers Parks & Recreation',
        'description' => 'Municipal parks department for the City of Yonkers — manages recreational programs, public events, and the local park system, with public Parks Board meetings.',
        'base_url' => 'https://www.yonkersny.gov/government/departments/parks-recreation-conservation',
        'location' => 'Yonkers Parks Department',
        'tags' => ['Westchester', 'Yonkers'],
    ],
    [
        'name' => 'Liberty State Park',
        'description' => 'Jersey City NJ State Park along the Hudson with views of the Statue of Liberty and Lower Manhattan, hosting concerts, festivals, and family events.',
        'base_url' => 'https://www.libertystatepark.com',
        'location' => 'Liberty State Park',
        'tags' => ['New Jersey', 'Jersey City', 'Park', 'Outdoor'],
    ],
    [
        'name' => 'Romanian Cultural Institute',
        'description' => 'Diplomatic cultural institute on East 38th Street in Murray Hill, hosting Romanian film screenings, art exhibitions, lectures, and music events.',
        'base_url' => 'https://www.icrny.org',
        'location' => 'Romanian Cultural Institute',
        'tags' => ['Manhattan', 'Murray Hill', 'Cultural Center'],
    ],
    [
        'name' => 'Cresskill Public Library',
        'description' => 'Northern Bergen County NJ public library on Union Avenue offering programs, classes, and events for the Cresskill community.',
        'base_url' => 'https://www.cresskillpubliclibrary.org',
        'location' => 'Cresskill Public Library',
        'tags' => ['New Jersey', 'Library'],
    ],
    [
        'name' => 'Wallington Veterans Memorial Library',
        'description' => 'Public library serving Wallington, NJ, with community programs, classes, and events.',
        'base_url' => 'https://www.wallingtonpubliclibrary.org',
        'location' => 'Wallington Veterans Memorial Library',
        'tags' => ['New Jersey', 'Library'],
    ],
    [
        'name' => 'Allaire State Park',
        'description' => 'Monmouth County NJ State Park with hiking trails, the historic Allaire Village (a restored 19th-century iron-making town), and seasonal events.',
        'base_url' => 'https://www.nj.gov/dep/parksandforests/parks/allairestatepark.html',
        'location' => 'Allaire State Park',
        'tags' => ['New Jersey', 'Park', 'Outdoor'],
    ],
    [
        'name' => 'Monmouth Battlefield State Park',
        'description' => 'Manalapan NJ State Park preserving the site of the 1778 Battle of Monmouth, with historical reenactments, walking tours, and museum exhibitions.',
        'base_url' => 'https://www.nj.gov/dep/parksandforests/parks/monbat.html',
        'location' => 'Monmouth Battlefield State Park',
        'tags' => ['New Jersey', 'Park', 'Outdoor'],
    ],
    [
        'name' => 'Patchen Community Square Garden',
        'description' => 'Bedford-Stuyvesant community garden on Putnam Avenue, hosting workdays, plant sales, music, and seasonal events.',
        'base_url' => 'https://www.nycgovparks.org/parks/patchen-community-square-garden',
        'location' => 'Patchen Community Square Garden',
        'tags' => ['Brooklyn', 'Bed-Stuy', 'Garden', 'Outdoor'],
    ],
    [
        'name' => 'Welcome to Chinatown',
        'description' => 'Grassroots initiative supporting Manhattan Chinatown small businesses through pop-ups, community events, and the Bowery storefront on East Broadway.',
        'base_url' => 'https://www.welcometochinatown.com',
        'location' => 'Welcome to Chinatown',
        'tags' => ['Manhattan', 'Chinatown', 'Cultural Center'],
    ],
    [
        'name' => 'Bronx River Community Garden',
        'description' => 'Bronx community garden on East 180th Street near the Bronx River, hosting workdays and seasonal events.',
        'base_url' => 'https://www.nycgovparks.org/parks/bronx-river-community-garden',
        'location' => 'Bronx River Community Garden',
        'tags' => ['Bronx', 'Garden', 'Outdoor'],
    ],
    [
        'name' => '6th Street and Avenue B Community Garden',
        'description' => 'East Village community garden at the corner of 6th Street and Avenue B, hosting concerts, plant sales, and seasonal community events.',
        'base_url' => 'https://6bgarden.org',
        'location' => '6th Street and Avenue B Community Garden',
        'tags' => ['Manhattan', 'East Village', 'Garden', 'Outdoor'],
    ],
    [
        'name' => "Abe's Pagoda Bar",
        'description' => 'Bushwick bar on Wyckoff Avenue with cocktails, kitsch decor, and live music or DJ programming.',
        'base_url' => 'https://www.instagram.com/abespagodabar/',
        'location' => "Abe's Pagoda Bar",
        'tags' => ['Brooklyn', 'Bushwick', 'Bar'],
    ],
    [
        'name' => 'Bell Slip',
        'description' => 'Greenpoint waterfront park along the East River with scenic Manhattan skyline views, hosting outdoor performances and community events.',
        'base_url' => 'https://bushwickinletpark.org/visit/bell-slip',
        'location' => 'Bell Slip',
        'tags' => ['Brooklyn', 'Greenpoint', 'Park', 'Outdoor'],
    ],
    [
        'name' => 'Nuar',
        'description' => 'NoMad coffee shop and creative space on West 27th Street, hosting community workshops and creative gatherings.',
        'base_url' => 'https://www.nuar.nyc',
        'location' => 'Nuar',
        'tags' => ['Manhattan', 'NoMad', 'Cafe'],
    ],
    // 2026-05-01 batch 9 — informational website entries.
    [
        'name' => 'Wikipedia — Alamo (sculpture)',
        'description' => "Wikipedia article for the Alamo (the Astor Place Cube) — Tony Rosenthal's 1967 rotatable steel sculpture at Astor Place and Lafayette.",
        'base_url' => 'https://en.wikipedia.org/wiki/Alamo_(sculpture)',
        'location' => 'Astor Place Cube',
        'tags' => ['Manhattan', 'East Village', 'Outdoor'],
    ],
    [
        'name' => 'Workforce1 Career Center — Upper Manhattan',
        'description' => 'NYC Workforce1 Career Center on West 125th Street in Harlem, providing job training, employment services, and host venue for community food pantry and outreach events.',
        'base_url' => 'https://www.nyc.gov/site/sbs/careers/workforce1.page',
        'location' => '215 W 125th St',
        'tags' => ['Manhattan', 'Harlem', 'Community Center'],
    ],
    // 2026-05-01 batch 13 — informational website entries.
    [
        'name' => 'Court Square Market',
        'description' => 'Outdoor weekend market in Long Island City near Court Square (Saturdays/Sundays 11–6) — 30+ independent vendors of handmade goods, vintage, art, and food, with live jazz.',
        'base_url' => 'https://www.courtsquaremarket.com',
        'location' => 'Court Square Market',
        'tags' => ['Queens', 'Long Island City', 'Outdoor'],
    ],
    [
        'name' => 'Acacia Network Elmhurst Older Adults Center',
        'description' => 'Elmhurst senior center run by Acacia Network, offering programs, activities, and community events for older adults.',
        'base_url' => 'https://www.acacianetwork.org',
        'location' => 'Acacia Network Elmhurst Older Adults Center',
        'tags' => ['Queens', 'Elmhurst', 'Community Center'],
    ],
    [
        'name' => 'PS 149Q (Christa McAuliffe School)',
        'description' => 'NYC Department of Education public school in Jackson Heights — host venue for Queens Weekend Workshops and community programs.',
        'base_url' => 'https://www.ps149q.org',
        'location' => 'PS 149',
        'tags' => ['Queens', 'Jackson Heights', 'School', 'Education'],
    ],
    [
        'name' => 'VERS Clothing for People',
        'description' => 'Bushwick boutique and creative hub (since 2021) — a consortium of ~30 queer designers handmaking sustainable, size- and gender-inclusive clothing, with workshops, drag shows, and fashion events.',
        'base_url' => 'https://www.versbk.nyc',
        'location' => 'Vers bk.nyc',
        'tags' => ['Brooklyn', 'Bushwick', 'Queer', 'Art'],
    ],
    // 2026-05-01 batch 14 — informational website entries.
    [
        'name' => 'Brower Park (NYC Parks)',
        'description' => "Crown Heights park spanning four blocks, home to the Brooklyn Children's Museum and host to summer concerts and community events.",
        'base_url' => 'https://www.nycgovparks.org/parks/brower-park',
        'location' => 'Brower Park',
        'tags' => ['Brooklyn', 'Crown Heights', 'Park', 'Outdoor'],
    ],
    [
        'name' => 'Stapleton Library (NYPL)',
        'description' => 'New York Public Library branch in Stapleton, Staten Island — programs, classes, and community events.',
        'base_url' => 'https://www.nypl.org/locations/stapleton',
        'location' => 'Stapleton Library',
        'tags' => ['Staten Island', 'Library'],
    ],
    [
        'name' => "Marjorie Eliot's Parlor Jazz",
        'description' => "Free Sunday jazz concerts (3pm) since 1993 in Marjorie Eliot's Sugar Hill apartment at 555 Edgecombe Avenue (Studio 3F) — an intimate Harlem tradition started as a tribute to her late son.",
        'base_url' => 'https://jazzfoundation.org/parlor/',
        'location' => "Marjorie Eliot's Parlor Entertainment Harlem",
        'tags' => ['Manhattan', 'Hamilton Heights', 'Jazz', 'Live Music', 'Free'],
    ],
    [
        'name' => 'Jane Hartsook Gallery (Greenwich House Pottery)',
        'description' => 'West Village contemporary ceramics gallery at Greenwich House Pottery, hosting rotating exhibitions of clay-based art.',
        'base_url' => 'https://www.greenwichhouse.org/pottery/jane-hartsook-gallery',
        'location' => 'Jane Hartsook Gallery',
        'tags' => ['Manhattan', 'West Village', 'Art'],
    ],
    [
        'name' => 'Sakura Park (NYC Parks)',
        'description' => 'Morningside Heights park along Riverside Drive, named for the cherry trees gifted by Japan in 1912 — host to outdoor concerts and family programs.',
        'base_url' => 'https://www.nycgovparks.org/parks/sakura-park',
        'location' => 'Sakura Park',
        'tags' => ['Manhattan', 'Morningside Heights', 'Park', 'Outdoor'],
    ],
    [
        'name' => 'Carl Schurz Park Conservancy',
        'description' => "Upper East Side waterfront park along the East River, home to Gracie Mansion (the NYC mayor's residence) and host to seasonal performances and community events.",
        'base_url' => 'https://carlschurzparknyc.org',
        'location' => 'Carl Schurz Park',
        'tags' => ['Manhattan', 'Upper East Side', 'Park', 'Outdoor', 'Free'],
    ],
    [
        'name' => 'The Tidewater Center (Arm-of-the-Sea Theater)',
        'description' => "Saugerties NY theater arts and ecology center on the Esopus Creek waterfront, hosting Arm-of-the-Sea Theater's mask and puppet performances and Waterfront Wednesdays.",
        'base_url' => 'https://www.armofthesea.org/the-tidewater-center',
        'location' => 'The Tidewater Center',
        'tags' => ['Hudson Valley', 'Theater'],
    ],
    [
        'name' => 'Art House Productions',
        'description' => 'Jersey City pioneering arts nonprofit (since 2001) — theater, gallery, festivals, comedy, and arts classes; new home at The Hendrix near Grove St PATH.',
        'base_url' => 'https://www.arthouseproductions.org',
        'location' => 'Art House Productions',
        'tags' => ['New Jersey', 'Jersey City', 'Theater', 'Art'],
    ],
    [
        'name' => 'Haworth Municipal Library',
        'description' => 'Public library in Haworth, NJ — programs, classes, and community events for Bergen County residents.',
        'base_url' => 'https://haworthlibrary.org',
        'location' => 'Haworth Municipal Library',
        'tags' => ['New Jersey', 'Library'],
    ],
    [
        'name' => 'Epiphany Library (NYPL)',
        'description' => 'New York Public Library branch on East 23rd Street in Gramercy/Kips Bay, with programs, classes, and community events.',
        'base_url' => 'https://www.nypl.org/locations/epiphany',
        'location' => 'Epiphany Library',
        'tags' => ['Manhattan', 'Gramercy', 'Library'],
    ],
    [
        'name' => 'Shirley Chisholm Recreation Center (NYC Parks)',
        'description' => 'East New York public recreation center with pool, gym, and fitness programs operated by NYC Parks.',
        'base_url' => 'https://www.nycgovparks.org/facilities/recreationcenters/B144',
        'location' => 'Shirley Chisholm Recreation Center',
        'tags' => ['Brooklyn', 'East New York', 'Fitness', 'Community Center'],
    ],
    [
        'name' => 'Parkour Park (Riverside Park)',
        'description' => 'Riverside Park parkour training course in Hamilton Heights with bars, walls, and obstacles for free outdoor parkour practice.',
        'base_url' => 'https://riversideparknyc.org/places/parkour-park/',
        'location' => 'Parkour Park (Riverside Park)',
        'tags' => ['Manhattan', 'Hamilton Heights', 'Park', 'Fitness', 'Outdoor', 'Free'],
    ],
    // 2026-05-01 batch 15 — informational website entries.
    [
        'name' => 'Pier 36 NYC',
        'description' => 'Lower East Side waterfront event venue at Basketball City, hosting yacht parties, dance events, and large-scale productions on the East River.',
        'base_url' => 'https://www.pier36nyc.com',
        'location' => 'Pier 36 NYC',
        'tags' => ['Manhattan', 'Lower East Side', 'Event Space'],
    ],
    [
        'name' => "Paddy's of Park Slope",
        'description' => 'Park Slope Irish pub on 13th Street with craft beer, weekly trivia, and book club nights.',
        'base_url' => 'https://www.paddysofparkslope.com',
        'location' => "Paddy's of Park Slope",
        'tags' => ['Brooklyn', 'Park Slope', 'Bar'],
    ],
    [
        'name' => 'New York Center for Creativity and Dance',
        'description' => 'East Village dance studio offering classes, workshops, and rehearsal space for the NYC dance community.',
        'base_url' => 'https://www.nyccd.org',
        'location' => 'New York Center for Creativity and Dance',
        'tags' => ['Manhattan', 'East Village', 'Dance'],
    ],
    [
        'name' => 'Brick Presbyterian Church',
        'description' => 'Upper East Side Presbyterian church on East 92nd Street, hosting concerts, lectures, and community events alongside worship.',
        'base_url' => 'https://www.brickchurch.org',
        'location' => 'Brick Presbyterian Church',
        'tags' => ['Manhattan', 'Upper East Side', 'Church'],
    ],
    [
        'name' => '26Bridge',
        'description' => 'DUMBO event space and gallery on Plymouth Street, hosting art markets, pop-ups, and community events.',
        'base_url' => 'https://www.26bridge.com',
        'location' => '26Bridge',
        'tags' => ['Brooklyn', 'DUMBO', 'Event Space', 'Art'],
    ],
    [
        'name' => 'New Design High School',
        'description' => 'NYC public high school in the Lower East Side with a turf field used for outdoor sports leagues, fitness events, and community recreation.',
        'base_url' => 'https://www.newdesignhighschool.com',
        'location' => 'New Design High School Field',
        'tags' => ['Manhattan', 'Lower East Side', 'School', 'Outdoor'],
    ],
    [
        'name' => 'Hotel New Yorker',
        'description' => '1930 Art Deco midtown Manhattan hotel on Eighth Avenue near Penn Station, hosting conferences (HOPE hacker conference) and community events.',
        'base_url' => 'https://www.newyorkerhotel.com',
        'location' => 'Hotel New Yorker',
        'tags' => ['Manhattan', 'Hotel'],
    ],
    [
        'name' => 'The Parlour at Brooklyn High',
        'description' => 'Park Slope tea/coffee parlor and event space inside Brooklyn High Coffee, hosting weekly game nights and community gatherings.',
        'base_url' => 'https://brooklynhighcoffee.com',
        'location' => 'The Parlour at Brooklyn High',
        'tags' => ['Brooklyn', 'Park Slope', 'Cafe'],
    ],
    [
        'name' => 'Sunnyside Arch',
        'description' => 'Public archway over Queens Boulevard at 46th Street in Sunnyside — host to outdoor block parties, music programs, and community events.',
        'base_url' => 'https://sunnysideshines.org',
        'location' => 'Sunnyside Arch',
        'tags' => ['Queens', 'Sunnyside', 'Outdoor'],
    ],
    [
        'name' => 'The Old American Can Factory',
        'description' => 'Industrial Gowanus complex housing artist studios, galleries, and event spaces, hosting installations, multi-screen exhibitions, and creative gatherings.',
        'base_url' => 'https://www.americancanfactory.com',
        'location' => 'The Old American Can Factory',
        'tags' => ['Brooklyn', 'Gowanus', 'Art', 'Event Space'],
    ],
    [
        'name' => 'Mriga',
        'description' => 'Sunnyside South Indian restaurant on Skillman Avenue (newly opened) with regional dosas, sambhar, and community supper events.',
        'base_url' => 'https://www.mrignyc.com',
        'location' => 'Mriga',
        'tags' => ['Queens', 'Sunnyside', 'Restaurant'],
    ],
    // 2026-05-01 batch 16 — informational website entries.
    [
        'name' => 'Cuban Art Space (Center for Cuban Studies)',
        'description' => 'DUMBO gallery and home of the Center for Cuban Studies, exhibiting contemporary Cuban art, photography, and posters with rotating shows and talks.',
        'base_url' => 'https://cubanartspace.net',
        'location' => 'Cuban Art Space',
        'tags' => ['Brooklyn', 'DUMBO', 'Art'],
    ],
    [
        'name' => 'Pershing Field Park (Jersey City)',
        'description' => 'Jersey City Heights public park and recreation center with athletic fields, swimming pool, ice rink, and seasonal community events.',
        'base_url' => 'https://www.jerseycitynj.gov/cityhall/recreation/parks/pershingfieldpark',
        'location' => 'Pershing Field',
        'tags' => ['New Jersey', 'Jersey City', 'Park', 'Outdoor'],
    ],
    [
        'name' => 'MacDowell NYC',
        'description' => 'Chelsea NYC office of MacDowell, the historic New Hampshire artist residency program (since 1907) — host to public talks, fellow showcases, and arts events.',
        'base_url' => 'https://www.macdowell.org',
        'location' => 'MacDowell NYC',
        'tags' => ['Manhattan', 'Chelsea', 'Art', 'Cultural Center'],
    ],
    [
        'name' => 'Factory by Beer Tree Brew',
        'description' => 'Southern Tier (Johnson City, NY) brewery and taproom from Beer Tree Brew Co — craft beer flights, food, and live events.',
        'base_url' => 'https://www.beertreebrew.com',
        'location' => 'Factory by Beer Tree Brew',
        'tags' => ['Bar'],
    ],
    [
        'name' => 'Hammerstein Ballroom (Manhattan Center)',
        'description' => 'Historic 12,000-capacity ballroom inside Manhattan Center on West 34th Street, hosting concerts, awards shows, and large productions.',
        'base_url' => 'https://www.mcstudios.com/our-spaces/the-hammerstein-ballroom',
        'location' => 'Hammerstein Ballroom',
        'tags' => ['Manhattan', 'Hell\'s Kitchen', 'Live Music', 'Event Space'],
    ],
    [
        'name' => 'Bronx Drafthouse',
        'description' => 'South Bronx craft beer hall on Gerard Avenue near Yankee Stadium, with rotating taps and event programming.',
        'base_url' => 'https://www.bronxdrafthouse.com',
        'location' => 'Bronx Drafthouse',
        'tags' => ['Bronx', 'Concourse', 'Bar'],
    ],
    [
        'name' => 'Catskills Visitor Center',
        'description' => 'Mt. Tremper visitor center for the Catskill Park, with hiking maps, wildlife exhibits, and educational nature programs.',
        'base_url' => 'https://catskillsvisitorcenter.org',
        'location' => 'Catskills Visitor Center',
        'tags' => ['Hudson Valley', 'Outdoor'],
    ],
    [
        'name' => 'Mid-Hudson Children\'s Museum',
        'description' => 'Poughkeepsie hands-on children\'s museum on the Hudson Riverfront, with interactive science exhibits, art activities, and family programs.',
        'base_url' => 'https://www.mhcm.org',
        'location' => 'Mid-Hudson Discovery Museum',
        'tags' => ['Hudson Valley', 'Museum'],
    ],
    [
        'name' => 'The Factory 380',
        'description' => 'Murray Hill bar and event space on 3rd Avenue with cocktails and rotating event programming.',
        'base_url' => 'https://www.thefactory380.com',
        'location' => 'The Factory 380',
        'tags' => ['Manhattan', 'Murray Hill', 'Bar'],
    ],
    [
        'name' => 'Careers In Sports High School',
        'description' => 'Bronx public high school in Concourse Village, hosting community workshops and events.',
        'base_url' => 'https://www.cishs.com',
        'location' => 'Careers In Sports High School',
        'tags' => ['Bronx', 'School', 'Education'],
    ],
    [
        'name' => 'The Paris Theater',
        'description' => 'Single-screen Manhattan art house cinema on West 58th Street near Central Park (since 1948), now operated by Netflix — premieres, retrospectives, and special events.',
        'base_url' => 'https://www.theparistheater.com',
        'location' => 'The Paris Theater',
        'tags' => ['Manhattan', 'Midtown', 'Cinema'],
    ],
    [
        'name' => 'Franklin Lakes Public Library',
        'description' => 'Bergen County NJ public library with programs, classes, and community events.',
        'base_url' => 'https://franklinlakeslibrary.org',
        'location' => 'Franklin Lakes Public Library',
        'tags' => ['New Jersey', 'Library'],
    ],
    [
        'name' => 'Diversity Edible Farm Garden',
        'description' => 'East Harlem urban farm garden on Madison Avenue, hosting growing days, plant sales, and community workshops.',
        'base_url' => 'https://www.nycgovparks.org/parks/diversity-plaza-garden',
        'location' => 'Diversity Edible Farm Garden',
        'tags' => ['Manhattan', 'East Harlem', 'Garden', 'Outdoor'],
    ],
    // 2026-05-01 batch 17 — informational website entries.
    [
        'name' => 'Englewood Public Library',
        'description' => 'Bergen County NJ public library on Engle Street with programs, classes, and community events.',
        'base_url' => 'https://www.englewoodlibrary.org',
        'location' => 'Englewood Public Library',
        'tags' => ['New Jersey', 'Library'],
    ],
    [
        'name' => 'Salvation Army Bedford Temple',
        'description' => 'Bedford-Stuyvesant Salvation Army community center and church on Lafayette Avenue, hosting worship services and community programs.',
        'base_url' => 'https://easternusa.salvationarmy.org/greater-new-york/bedford-temple',
        'location' => 'Salvation Army Bedford Temple',
        'tags' => ['Brooklyn', 'Bed-Stuy', 'Church', 'Community Center'],
    ],
    [
        'name' => 'Beach 44th Street Boardwalk',
        'description' => 'Section of the Rockaway Beach Boardwalk at Beach 44th Street in Far Rockaway, hosting outdoor community events.',
        'base_url' => 'https://www.nycgovparks.org/parks/rockaway-beach-and-boardwalk',
        'location' => 'Beach 44th Street Boardwalk',
        'tags' => ['Queens', 'Rockaway Beach', 'Beach', 'Outdoor'],
    ],
    // 2026-05-01 batch 18 — informational website entries.
    [
        'name' => 'Bay Ridge Greenmarket (GrowNYC)',
        'description' => 'GrowNYC weekly farmers market in Bay Ridge with fresh produce from regional farms — SNAP/EBT friendly.',
        'base_url' => 'https://www.grownyc.org/greenmarket/brooklyn-bay-ridge',
        'location' => 'Bay Ridge Greenmarket',
        'tags' => ['Brooklyn', 'Bay Ridge', 'Greenmarket', 'Outdoor'],
    ],
    [
        'name' => 'Bella Abzug Park (Hudson Yards)',
        'description' => 'Hudson Yards public park named for the activist congresswoman, with fountains, lawns, and seasonal community programming.',
        'base_url' => 'https://www.hudsonyardsnewyork.com/discover/public-art-and-public-square',
        'location' => 'Bella Abzug Park',
        'tags' => ['Manhattan', 'Hell\'s Kitchen', 'Park', 'Outdoor'],
    ],
    [
        'name' => 'Broadhurst Theatre (Shubert Organization)',
        'description' => '1917 Broadway theater on West 44th Street in the Theater District, owned by the Shubert Organization — staging Broadway plays and musicals.',
        'base_url' => 'https://shubert.nyc/theatres/broadhurst',
        'location' => 'Broadhurst Theatre',
        'tags' => ['Manhattan', 'Times Square', 'Theater', 'Broadway'],
    ],
    [
        'name' => 'BronxWorks',
        'description' => 'Bronx-based community nonprofit serving over 50,000 people annually with senior services, youth programs, workforce development, and housing assistance.',
        'base_url' => 'https://bronxworks.org',
        'location' => 'BronxWorks',
        'tags' => ['Bronx', 'Community Center'],
    ],
    [
        'name' => 'Bobst Library (NYU)',
        'description' => 'NYU Elmer Holmes Bobst Library on Washington Square South — 12-story research library hosting public lectures, exhibitions, and academic events.',
        'base_url' => 'https://library.nyu.edu',
        'location' => 'Bobst Library',
        'tags' => ['Manhattan', 'Greenwich Village', 'Library', 'Education'],
    ],
    [
        'name' => '82nd Street Academics',
        'description' => 'Jackson Heights nonprofit running after-school programs, youth services, and the 82nd Street Partnership business improvement district programming.',
        'base_url' => 'https://www.82streetacademics.org',
        'location' => '82nd Street Academics',
        'tags' => ['Queens', 'Jackson Heights', 'Education', 'Community Center'],
    ],
    [
        'name' => 'The Times Center',
        'description' => 'Auditorium and event space inside The New York Times building on West 41st Street, hosting talks, panels, and conferences.',
        'base_url' => 'https://timescenter.com',
        'location' => 'The Times Center',
        'tags' => ['Manhattan', 'Times Square', 'Event Space'],
    ],
    // 2026-05-01 batch 19 — informational website entries.
    [
        'name' => 'Fogo de Chão (Brooklyn)',
        'description' => 'Brazilian steakhouse chain location in Downtown Brooklyn at City Point, with churrasco service and event hosting.',
        'base_url' => 'https://fogodechao.com/location/brooklyn',
        'location' => 'Fogo de Chão',
        'tags' => ['Brooklyn', 'Downtown Brooklyn', 'Restaurant'],
    ],
    [
        'name' => 'East River Esplanade',
        'description' => 'Manhattan East Side waterfront promenade (Bobby Wagner Walk) along the East River, with walking and cycling paths and seasonal community events.',
        'base_url' => 'https://www.nycgovparks.org/parks/east-river-esplanade',
        'location' => 'East River Esplanade',
        'tags' => ['Manhattan', 'Outdoor'],
    ],
    [
        'name' => 'Harvey Fierstein Theatre Lab (American Theatre Wing)',
        'description' => 'Lincoln Square new-works development space named for the playwright/actor, hosting readings, workshops, and emerging-playwright showcases.',
        'base_url' => 'https://americantheatrewing.org/program/harvey-fierstein-theatre-lab/',
        'location' => 'Harvey Fierstein Theatre Lab',
        'tags' => ['Manhattan', 'Lincoln Square', 'Theater'],
    ],
    [
        'name' => 'Friends Seminary',
        'description' => 'Quaker independent K-12 school on East 16th Street in Gramercy/Stuyvesant Square, hosting community events and meetinghouse talks.',
        'base_url' => 'https://www.friendsseminary.org',
        'location' => 'Friends Seminary',
        'tags' => ['Manhattan', 'Gramercy', 'School', 'Education'],
    ],
    [
        'name' => 'DoubleTree Times Square South',
        'description' => 'Hilton-brand hotel in Times Square area on 8th Avenue, hosting conferences and events.',
        'base_url' => 'https://www.hilton.com/en/hotels/nycwsdt-doubletree-new-york-times-square-south/',
        'location' => 'DoubleTree Times Square South',
        'tags' => ['Manhattan', 'Times Square', 'Hotel'],
    ],
    [
        'name' => 'Residence Inn Times Square',
        'description' => 'Marriott extended-stay hotel on 6th Avenue near Times Square, hosting events and conferences.',
        'base_url' => 'https://www.marriott.com/en-us/hotels/nycrt-residence-inn-new-york-manhattan-times-square/overview/',
        'location' => 'Residence Inn Times Square',
        'tags' => ['Manhattan', 'Times Square', 'Hotel'],
    ],
    [
        'name' => 'Panda Harlem',
        'description' => 'West Harlem Asian-fusion restaurant on 12th Avenue, hosting community meetups and events.',
        'base_url' => 'https://www.pandaharlem.com',
        'location' => 'Panda Harlem',
        'tags' => ['Manhattan', 'Harlem', 'Restaurant'],
    ],
    [
        'name' => 'The Maze NYC',
        'description' => 'Lower East Side underground nightclub on Delancey Street with electronic and dance programming.',
        'base_url' => 'https://www.themazenyc.com',
        'location' => 'The Maze NYC',
        'tags' => ['Manhattan', 'Lower East Side', 'Bar'],
    ],
    [
        'name' => 'The Folly',
        'description' => 'SoHo cocktail bar and event space on West Houston Street with eclectic programming.',
        'base_url' => 'https://www.thefollynyc.com',
        'location' => 'The Folly',
        'tags' => ['Manhattan', 'SoHo', 'Bar'],
    ],
    [
        'name' => 'PushUp Gallery',
        'description' => 'Bushwick contemporary art gallery on Bogart Street, hosting rotating exhibitions and openings.',
        'base_url' => 'https://www.instagram.com/pushupgallery/',
        'location' => 'PushUp Gallery',
        'tags' => ['Brooklyn', 'Bushwick', 'Art'],
    ],
    [
        'name' => 'Joe Michaels Mile',
        'description' => 'Queens linear waterfront park along Little Neck Bay, named for the cyclist — popular for running, biking, and walking events.',
        'base_url' => 'https://www.nycgovparks.org/parks/joe-michaels-mile',
        'location' => 'Joe Michaels Mile',
        'tags' => ['Queens', 'Park', 'Outdoor'],
    ],
    [
        'name' => 'Colden Auditorium (Queens College)',
        'description' => '2,143-seat performing arts auditorium at Queens College in Flushing, hosting concerts, dance, and academic events.',
        'base_url' => 'https://kupferbergcenter.org/venue/colden-auditorium/',
        'location' => 'Colden Auditorium',
        'tags' => ['Queens', 'Flushing', 'Performing Arts', 'Music'],
    ],
    [
        'name' => 'Torch & Crown Brewing Co.',
        'description' => 'Manhattan-based brewery on Vandam Street in SoHo with house-brewed beers, food, and event programming.',
        'base_url' => 'https://www.torchandcrown.com',
        'location' => 'Torch & Crown Brewing Co.',
        'tags' => ['Manhattan', 'SoHo', 'Bar'],
    ],
    [
        'name' => 'All City Leadership Secondary School',
        'description' => 'NYC Department of Education public secondary school in Bushwick, hosting community workshops and events.',
        'base_url' => 'https://www.allcityleadership.org',
        'location' => 'All City Leadership Secondary School',
        'tags' => ['Brooklyn', 'Bushwick', 'School', 'Education'],
    ],
    [
        'name' => 'Fashion Institute of Technology (FIT)',
        'description' => 'Public art and design college on West 27th Street in Chelsea, hosting fashion shows, lectures, exhibitions, and student showcases.',
        'base_url' => 'https://www.fitnyc.edu',
        'location' => 'Fashion Institute of Technology (FIT)',
        'tags' => ['Manhattan', 'Chelsea', 'Education', 'College'],
    ],
    [
        'name' => 'Brownsville Recreation Center (NYC Parks)',
        'description' => 'East New York/Brownsville public recreation center on Linden Boulevard with gym, pool, and fitness programs.',
        'base_url' => 'https://www.nycgovparks.org/facilities/recreationcenters/B019',
        'location' => 'Brownsville Recreation Center',
        'tags' => ['Brooklyn', 'Brownsville', 'Fitness', 'Community Center'],
    ],
    [
        'name' => 'LoFi Bar',
        'description' => 'Park Slope cocktail bar on 2nd Street with vinyl listening sessions and cozy neighborhood atmosphere.',
        'base_url' => 'https://lofibarnyc.com',
        'location' => 'LoFi Bar',
        'tags' => ['Brooklyn', 'Park Slope', 'Bar'],
    ],
    [
        'name' => 'Myrtle Village Green Community Garden',
        'description' => 'Bed-Stuy community garden on Myrtle Avenue, hosting plant sales, workdays, and community events.',
        'base_url' => 'https://www.nycgovparks.org/parks/myrtle-village-green',
        'location' => 'Myrtle Village Green Community Garden',
        'tags' => ['Brooklyn', 'Bed-Stuy', 'Garden', 'Outdoor'],
    ],
    [
        'name' => 'Newport Community Garden',
        'description' => 'Brownsville community garden on Newport Street, hosting workdays and seasonal events.',
        'base_url' => 'https://bqlt.org/garden/newport-community-garden',
        'location' => 'Newport Community Garden',
        'tags' => ['Brooklyn', 'Brownsville', 'Garden', 'Outdoor'],
    ],
    [
        'name' => 'Northerleigh Park (NYC Parks)',
        'description' => 'Staten Island park on the North Shore, with athletic fields and outdoor community events.',
        'base_url' => 'https://www.nycgovparks.org/parks/northerleigh-park',
        'location' => 'Northerleigh Park',
        'tags' => ['Staten Island', 'Park', 'Outdoor'],
    ],
    [
        'name' => 'Pier 66 (Hudson River Park)',
        'description' => 'Hudson River Park pier in Chelsea with floating bar, kayak launch, and outdoor performances.',
        'base_url' => 'https://hudsonriverpark.org/locations/pier-66/',
        'location' => 'Pier 66 at Hudson River Park',
        'tags' => ['Manhattan', 'Chelsea', 'Park', 'Outdoor'],
    ],
    [
        'name' => 'Bar Pinky Swear',
        'description' => 'Lower East Side cocktail bar on Chrystie Street with creative drinks and DJ programming.',
        'base_url' => 'https://www.barpinkyswear.com',
        'location' => 'Bar Pinky Swear',
        'tags' => ['Manhattan', 'Lower East Side', 'Bar'],
    ],
    // 2026-05-02
    [
        'name' => 'New York Chamber Choirs',
        'description' => 'NYC choral organization led by Artistic Director Maia McCormick, presenting classical choral concerts at churches and venues around the city.',
        'base_url' => 'https://www.chamberchoirs.nyc',
        'urls' => ['https://www.chamberchoirs.nyc/concerts'],
        'notes' => 'Itinerant choir performing at varying venues (e.g. Brick Church). Extract the concert venue from each event listing.',
    ],
    // 2026-05-09 — Nonsense NYC newsletter cross-reference: 5 venues newly added.
    [
        'name' => 'Hendrick I. Lott House',
        'description' => 'Historic 1720 Dutch farmhouse and museum in Marine Park, Brooklyn — hosts educational programming and seasonal cultural events.',
        'base_url' => 'https://lotthouse.org',
        'urls' => ['https://lotthouse.org/events-and-programs'],
        'crawl_frequency' => 14,
        'location' => 'Hendrick I. Lott House',
    ],
    [
        'name' => 'Isabel Sullivan Gallery',
        'description' => 'Tribeca contemporary art gallery hosting exhibitions and openings.',
        'base_url' => 'https://is.gallery',
        'urls' => ['https://is.gallery/exhibition'],
        'crawl_frequency' => 14,
        'location' => 'Isabel Sullivan Gallery',
    ],
    [
        'name' => 'Soho Live',
        'description' => 'Manhattan concert hall hosting hip-hop, indie, DJs, and themed dance parties.',
        'base_url' => 'https://www.soholivenyc.com',
        'urls' => ['https://www.soholivenyc.com/whats-on/'],
        'crawl_frequency' => 7,
        'location' => 'Soho Live',
    ],
    [
        'name' => 'Acorn Craft Shop',
        'description' => 'Prospect Heights craft shop running hands-on workshops including portrait nights, knitting, and collage classes.',
        'base_url' => 'https://acorncraftshop.com',
        'urls' => ['https://acorncraftshop.com/collections/classes-and-events'],
        'crawl_frequency' => 7,
        'location' => 'Acorn Craft Shop',
    ],
    [
        'name' => 'Coucou French Classes',
        'description' => 'SoHo French language school running group classes, workshops, and themed social events.',
        'base_url' => 'https://coucoufrenchclasses.com',
        'urls' => ['https://coucoufrenchclasses.com/coucou-events/'],
        'crawl_frequency' => 14,
        'location' => 'Coucou French Classes',
    ],
    // 2026-05-09 — Lauren LoGiudice's Eventbrite organizer page. Comedian/producer running Capish?! Club
    // and other comedy shows at varying venues (currently Lunella Ristorante in Little Italy).
    [
        'name' => 'Lauren LoGiudice (Capish?! Club)',
        'description' => 'Comedian/producer Lauren LoGiudice\'s Eventbrite organizer for stand-up, joke labs, and themed comedy nights — currently running Capish?! Club at Lunella Ristorante in Little Italy.',
        'base_url' => 'https://www.eventbrite.com/o/35910907953',
        'urls' => ['https://www.eventbrite.com/o/35910907953'],
        'crawl_frequency' => 14,
        'notes' => 'Itinerant comedy producer — extract the venue from each event listing rather than defaulting to a single location.',
    ],
    // 2026-05-11 — City Happenings newsletter cross-reference: new venues and organizers.
    [
        'name' => 'The Bishop Gallery',
        'description' => 'Contemporary art gallery in the Pfizer Building (East Williamsburg) showing rotating exhibitions, artist residencies, and educational programming.',
        'base_url' => 'https://thebishopgallery.com',
        'urls' => ['https://thebishopgallery.com/exhibitions/'],
        'crawl_frequency' => 14,
        'location' => 'The Bishop Gallery',
    ],
    [
        'name' => 'Art on the Block',
        'description' => 'Upper West Side nonprofit running affordable hands-on art workshops and accessible creative programming for NYC communities.',
        'base_url' => 'https://artontheblocknyc.org',
        'urls' => ['https://artontheblocknyc.org/special-events/'],
        'crawl_frequency' => 14,
        'location' => 'Art on the Block',
    ],
    [
        'name' => '@pastanightbk',
        'description' => 'Instagram handle for Pasta Night, a Prospect Heights Italian restaurant. No public events calendar on the website; programming (Sunday Sauced guest-chef series, themed weeklies) is announced via Instagram only.',
        'base_url' => 'https://www.instagram.com/pastanightbk/',
        'urls' => ['https://www.instagram.com/pastanightbk/'],
        'crawl_frequency' => 14,
        'location' => 'Pasta Night',
        'source_type' => 'instagram',
    ],
    [
        'name' => 'Dutchess County Fairgrounds',
        'description' => 'Hudson Valley fairgrounds in Rhinebeck hosting year-round bazaars, festivals, and the annual Dutchess County Fair.',
        'base_url' => 'https://dutchessfair.com',
        'urls' => ['https://dutchessfair.com/all-events/'],
        'crawl_frequency' => 14,
        'location' => 'Dutchess County Fairgrounds',
    ],
    [
        'name' => 'James Beard Foundation',
        'description' => 'Culinary nonprofit hosting dinner series, awards events, and educational programming at the JBF Platform (Pier 57), the James Beard House (167 W 12th St), and other NYC venues. Itinerant — extract per-event venue from each listing.',
        'base_url' => 'https://www.jamesbeard.org',
        'urls' => ['https://www.jamesbeard.org/events/event-calendar'],
        'crawl_frequency' => 7,
        'notes' => 'Itinerant culinary organizer — events happen at JBF Platform (Pier 57), the James Beard House (167 W 12th St, West Village), and other partner venues. Map each event to the venue named in its listing rather than a single default location.',
    ],
    [
        'name' => 'CreativeMornings NYC',
        'description' => 'NYC chapter of the global free breakfast lecture series; also produces neighborhood food crawls (WANDER) and other community events. Events happen at varied venues across the city.',
        'base_url' => 'https://creativemornings.com/cities/nyc',
        'urls' => ['https://creativemornings.com/cities/nyc'],
        'crawl_frequency' => 7,
        'notes' => 'Itinerant organizer — events move between venues and neighborhoods. Map each event to the venue/neighborhood in its listing.',
    ],
    [
        'name' => 'Dance Parade NYC',
        'description' => 'Annual May parade and free Tompkins Square Park festival celebrating 100+ dance styles. Also hosts year-round social dances and dance education programming.',
        'base_url' => 'https://danceparade.org',
        'urls' => ['https://danceparade.org'],
        'crawl_frequency' => 30,
        'notes' => 'Annual headline event is the May parade from W 17th & 6th Ave to Tompkins Square Park, finishing with DanceFest. Other year-round programming as listed.',
    ],
    [
        'name' => 'Brooklyn Heights Association',
        'description' => 'Civic association for the Brooklyn Heights neighborhood; runs The Longest Table annual block-party picnic plus other community events.',
        'base_url' => 'https://thebha.org',
        'urls' => ['https://thebha.org/events/'],
        'crawl_frequency' => 14,
        'location' => 'Brooklyn Heights',
    ],
    [
        'name' => '@takingupspacebook',
        'description' => 'Instagram-only events arm of the Taking Up Space book (Chelsea Kwakye & Ore Ogunbiyi); curates monthly small-group Chelsea gallery hops finishing with drinks at The Tippler.',
        'base_url' => 'https://www.instagram.com/takingupspacebook/',
        'urls' => ['https://www.instagram.com/takingupspacebook/'],
        'crawl_frequency' => 14,
        'source_type' => 'instagram',
        'notes' => 'Roving organizer — gallery hops move through Chelsea each month. Map events to "Chelsea" (generic location) unless a specific Chelsea venue is named.',
    ],
    [
        'name' => '@curiouselixirs',
        'description' => 'Instagram handle for Curious Elixirs, the non-alcoholic craft cocktail brand. Hosts the nationwide "Great Curious Cocktail Party" sober-curious series; NYC flagship is at Club Curious in Williamsburg.',
        'base_url' => 'https://www.instagram.com/curiouselixirs/',
        'urls' => ['https://www.instagram.com/curiouselixirs/'],
        'crawl_frequency' => 14,
        'source_type' => 'instagram',
        'notes' => 'Brand/organizer — map events to the venue (often Club Curious in Williamsburg) named in the post.',
    ],
];

// ============================================================================
// DATABASE CONFIGURATION
// ============================================================================

// Load .env file
function load_env($path) {
    if (!file_exists($path)) return;
    $lines = file($path, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
    foreach ($lines as $line) {
        if (strpos(trim($line), '#') === 0) continue;
        if (strpos($line, '=') === false) continue;
        list($name, $value) = explode('=', $line, 2);
        $name = trim($name);
        $value = trim($value, " \t\n\r\0\x0B\"'");
        if (!getenv($name)) putenv("$name=$value");
    }
}
load_env(__DIR__ . '/../.env');

$config = [
    'local' => [
        'host' => 'localhost',
        'port' => 3306,
        'dbname' => 'fomo',
        'user' => 'root',
        'password' => '',
    ],
    'production' => [
        'via_ssh' => true,
        'ssh_host' => getenv('SSH_HOST') ?: '69.57.162.203',
        'ssh_port' => getenv('SSH_PORT') ?: 21098,
        'ssh_user' => getenv('SSH_USER') ?: 'fomoowsq',
        'ssh_key' => __DIR__ . '/' . (getenv('SSH_KEY') ?: 'id_rsa_sync'),
        'dbname' => getenv('PROD_DB_NAME') ?: die("Error: PROD_DB_NAME not set in .env\n"),
        'user' => getenv('PROD_DB_USER') ?: die("Error: PROD_DB_USER not set in .env\n"),
        'password' => getenv('PROD_DB_PASS') ?: die("Error: PROD_DB_PASS not set in .env\n"),
    ],
];

// ============================================================================
// SCRIPT LOGIC (no need to edit below)
// ============================================================================

// Parse command line arguments
$is_production = in_array('--production', $argv) || in_array('-p', $argv);
$is_dry_run = in_array('--dry-run', $argv) || in_array('-n', $argv);
$show_help = in_array('--help', $argv) || in_array('-h', $argv);

if ($show_help) {
    echo <<<HELP
Add new websites to the database

Usage:
  php scripts/add_websites.php [options]

Options:
  --production, -p    Add to production database (default: local)
  --dry-run, -n       Show what would be added without making changes
  --help, -h          Show this help message

Instructions:
  1. Edit the \$new_websites array at the top of this script
  2. Run with --dry-run first to verify
  3. Run without --dry-run to actually add the websites

ID Sync (Production):
  When adding to production, the script will:
  - Look up the website's ID in local database
  - Use that same ID in production to keep databases in sync
  - Skip if the website doesn't exist locally (add to local first!)
  - Error if the local ID is already used by a different website in production

Example website entry:
  [
      'name' => 'Blue Note',
      'description' => 'Legendary jazz club...',  // Optional: organization description
      'base_url' => 'https://www.bluenotejazz.com/',  // Root domain (optional)
      'urls' => ['https://www.bluenotejazz.com/nyc/schedule'],  // Crawl URLs (optional)
      'crawl_frequency' => 4,      // Days between crawls (optional)
      'crawl_after' => '2026-06-01', // Don't crawl until this date (optional, for seasonal events)
      'keywords' => '&event_id=',  // URL keywords to follow (optional)
      'max_pages' => 50,           // Max pages to crawl (optional)
      'location' => 'Blue Note',   // Links to existing location (optional)
      'tags' => ['Jazz', 'Live Music'],  // Website tags (optional)
  ]

HELP;
    exit(0);
}

$env = $is_production ? 'production' : 'local';
$db_config = $config[$env];

echo "=== Add Websites Script ===\n";
echo "Target: " . strtoupper($env) . " database\n";
echo "Mode: " . ($is_dry_run ? "DRY RUN (no changes will be made)" : "LIVE") . "\n";
echo "\n";

if (empty($new_websites)) {
    echo "No websites to add. Edit the \$new_websites array in this script.\n";
    exit(0);
}

echo "Websites to add: " . count($new_websites) . "\n\n";

// Validate websites before connecting
$errors = [];
foreach ($new_websites as $i => $site) {
    $idx = $i + 1;
    if (empty($site['name'])) {
        $errors[] = "Website #$idx: 'name' is required";
    }
    if (empty($site['base_url'])) {
        $errors[] = "Website #$idx ({$site['name']}): 'base_url' is required";
    }
}

if (!empty($errors)) {
    echo "Validation errors:\n";
    foreach ($errors as $error) {
        echo "  - $error\n";
    }
    exit(1);
}

// Helper function to run SQL via SSH for production
function run_ssh_query($config, $sql) {
    $escaped_password = str_replace(']', '\\]', $config['password']);
    $cmd = sprintf(
        'ssh -p %d -i %s -o StrictHostKeyChecking=no %s@%s %s 2>&1',
        $config['ssh_port'],
        escapeshellarg($config['ssh_key']),
        $config['ssh_user'],
        $config['ssh_host'],
        escapeshellarg("mariadb -u {$config['user']} -p{$escaped_password} {$config['dbname']} -N -e " . escapeshellarg($sql))
    );
    $output = shell_exec($cmd);
    return $output;
}

// Check if using SSH for production
$use_ssh = $is_production && !empty($db_config['via_ssh']);

if ($use_ssh) {
    echo "Connecting to production via SSH...\n";
    $test = run_ssh_query($db_config, "SELECT 1");
    if (trim($test) !== '1') {
        echo "Connection failed: $test\n";
        exit(1);
    }
    echo "Connected to $env database via SSH\n\n";
    $pdo = null;
} else {
    $port = $db_config['port'] ?? 3306;
    try {
        $dsn = "mysql:host={$db_config['host']};port={$port};dbname={$db_config['dbname']};charset=utf8mb4";
        $pdo = new PDO($dsn, $db_config['user'], $db_config['password'], [
            PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
            PDO::MYSQL_ATTR_INIT_COMMAND => "SET NAMES utf8mb4"
        ]);
        echo "Connected to $env database\n\n";
    } catch (PDOException $e) {
        echo "Connection failed: " . $e->getMessage() . "\n";
        exit(1);
    }
}

// Helper functions for database operations
function escape_sql($value) {
    if ($value === null) return 'NULL';
    return "'" . addslashes($value) . "'";
}

function check_website_exists_pdo($pdo, $name) {
    $stmt = $pdo->prepare("SELECT id FROM websites WHERE name = ?");
    $stmt->execute([$name]);
    $row = $stmt->fetch(PDO::FETCH_ASSOC);
    return $row ? $row['id'] : null;
}

function check_website_exists_ssh($config, $name) {
    $sql = "SELECT id FROM websites WHERE name = " . escape_sql($name);
    $result = trim(run_ssh_query($config, $sql));
    return $result && is_numeric($result) ? $result : null;
}

function check_website_id_exists_ssh($config, $id) {
    $sql = "SELECT name FROM websites WHERE id = " . intval($id);
    $result = trim(run_ssh_query($config, $sql));
    return $result && strlen($result) > 0 ? $result : null;
}

function get_local_website_id($local_config, $name) {
    // Connect to local database to get the ID
    $port = $local_config['port'] ?? 3306;
    try {
        $dsn = "mysql:host={$local_config['host']};port={$port};dbname={$local_config['dbname']};charset=utf8mb4";
        $local_pdo = new PDO($dsn, $local_config['user'], $local_config['password'], [
            PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
        ]);
        $stmt = $local_pdo->prepare("SELECT id FROM websites WHERE name = ?");
        $stmt->execute([$name]);
        $row = $stmt->fetch(PDO::FETCH_ASSOC);
        return $row ? $row['id'] : null;
    } catch (PDOException $e) {
        echo "  Warning: Could not connect to local database to get ID: " . $e->getMessage() . "\n";
        return null;
    }
}

function get_location_id_pdo($pdo, $name) {
    $stmt = $pdo->prepare("SELECT id FROM locations WHERE name = ?");
    $stmt->execute([$name]);
    $row = $stmt->fetch(PDO::FETCH_ASSOC);
    return $row ? $row['id'] : null;
}

function get_location_id_ssh($config, $name) {
    $sql = "SELECT id FROM locations WHERE name = " . escape_sql($name);
    $result = trim(run_ssh_query($config, $sql));
    return $result && is_numeric($result) ? $result : null;
}

function insert_website_pdo($pdo, $site) {
    $sql = "INSERT INTO websites (name, description, base_url, crawl_frequency, crawl_after, selector, keywords, max_pages, notes)
            VALUES (:name, :description, :base_url, :crawl_frequency, :crawl_after, :selector, :keywords, :max_pages, :notes)";
    $stmt = $pdo->prepare($sql);
    $stmt->execute([
        ':name' => $site['name'],
        ':description' => $site['description'] ?? null,
        ':base_url' => $site['base_url'] ?? null,
        ':crawl_frequency' => $site['crawl_frequency'] ?? null,
        ':crawl_after' => $site['crawl_after'] ?? null,
        ':selector' => $site['selector'] ?? null,
        ':keywords' => $site['keywords'] ?? null,
        ':max_pages' => $site['max_pages'] ?? null,
        ':notes' => $site['notes'] ?? null,
    ]);
    return $pdo->lastInsertId();
}

function insert_website_ssh($config, $site, $explicit_id = null) {
    $crawl_after = isset($site['crawl_after']) ? escape_sql($site['crawl_after']) : 'NULL';
    if ($explicit_id !== null) {
        // Insert with explicit ID to match local database
        $sql = sprintf(
            "INSERT INTO websites (id, name, description, base_url, crawl_frequency, crawl_after, selector, keywords, max_pages, notes) VALUES (%d, %s, %s, %s, %s, %s, %s, %s, %s, %s); SELECT LAST_INSERT_ID();",
            intval($explicit_id),
            escape_sql($site['name']),
            escape_sql($site['description'] ?? null),
            escape_sql($site['base_url'] ?? null),
            $site['crawl_frequency'] ?? 'NULL',
            $crawl_after,
            escape_sql($site['selector'] ?? null),
            escape_sql($site['keywords'] ?? null),
            $site['max_pages'] ?? 'NULL',
            escape_sql($site['notes'] ?? null)
        );
    } else {
        $sql = sprintf(
            "INSERT INTO websites (name, description, base_url, crawl_frequency, crawl_after, selector, keywords, max_pages, notes) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s); SELECT LAST_INSERT_ID();",
            escape_sql($site['name']),
            escape_sql($site['description'] ?? null),
            escape_sql($site['base_url'] ?? null),
            $site['crawl_frequency'] ?? 'NULL',
            $crawl_after,
            escape_sql($site['selector'] ?? null),
            escape_sql($site['keywords'] ?? null),
            $site['max_pages'] ?? 'NULL',
            escape_sql($site['notes'] ?? null)
        );
    }
    $result = trim(run_ssh_query($config, $sql));
    return $result;
}

function add_website_urls_pdo($pdo, $website_id, $urls) {
    $stmt = $pdo->prepare("INSERT INTO website_urls (website_id, url, sort_order) VALUES (?, ?, ?)");
    foreach ($urls as $i => $url) {
        $stmt->execute([$website_id, $url, $i]);
    }
}

function add_website_urls_ssh($config, $website_id, $urls) {
    $values = [];
    foreach ($urls as $i => $url) {
        $values[] = "($website_id, " . escape_sql($url) . ", $i)";
    }
    if (!empty($values)) {
        $sql = "INSERT INTO website_urls (website_id, url, sort_order) VALUES " . implode(", ", $values);
        run_ssh_query($config, $sql);
    }
}

function link_website_location_pdo($pdo, $website_id, $location_id) {
    $stmt = $pdo->prepare("INSERT INTO website_locations (website_id, location_id) VALUES (?, ?)");
    $stmt->execute([$website_id, $location_id]);
}

function link_website_location_ssh($config, $website_id, $location_id) {
    $sql = "INSERT INTO website_locations (website_id, location_id) VALUES ($website_id, $location_id)";
    run_ssh_query($config, $sql);
}

function add_website_tags_pdo($pdo, $website_id, $tags) {
    foreach ($tags as $tag) {
        $stmt = $pdo->prepare("INSERT INTO website_tags (website_id, tag) VALUES (?, ?)");
        $stmt->execute([$website_id, $tag]);
    }
}

function add_website_tags_ssh($config, $website_id, $tags) {
    $values = [];
    foreach ($tags as $tag) {
        $values[] = "($website_id, " . escape_sql($tag) . ")";
    }
    if (!empty($values)) {
        $sql = "INSERT INTO website_tags (website_id, tag) VALUES " . implode(", ", $values);
        run_ssh_query($config, $sql);
    }
}

function get_stats_pdo($pdo) {
    $result = $pdo->query("SELECT COUNT(*) as total, MAX(id) as max_id FROM websites");
    return $result->fetch(PDO::FETCH_ASSOC);
}

function get_stats_ssh($config) {
    $result = run_ssh_query($config, "SELECT COUNT(*), MAX(id) FROM websites");
    $parts = explode("\t", trim($result));
    return ['total' => $parts[0] ?? '?', 'max_id' => $parts[1] ?? '?'];
}

// Check for duplicates
$duplicates = [];
foreach ($new_websites as $site) {
    $existing_id = $use_ssh
        ? check_website_exists_ssh($db_config, $site['name'])
        : check_website_exists_pdo($pdo, $site['name']);
    if ($existing_id) {
        $duplicates[] = "'{$site['name']}' already exists (ID: $existing_id)";
    }
}

if (!empty($duplicates)) {
    echo "Warning - these websites already exist:\n";
    foreach ($duplicates as $dup) {
        echo "  - $dup\n";
    }
    echo "\n";
}

// Process each website
$added = 0;
$skipped = 0;

foreach ($new_websites as $site) {
    // Check if already exists
    $existing_id = $use_ssh
        ? check_website_exists_ssh($db_config, $site['name'])
        : check_website_exists_pdo($pdo, $site['name']);

    if ($existing_id) {
        echo "  SKIP: {$site['name']} (already exists)\n";
        $skipped++;
        continue;
    }

    // Check if location exists (if specified)
    $location_id = null;
    if (!empty($site['location'])) {
        $location_id = $use_ssh
            ? get_location_id_ssh($db_config, $site['location'])
            : get_location_id_pdo($pdo, $site['location']);

        if (!$location_id) {
            echo "  WARNING: Location '{$site['location']}' not found for {$site['name']}\n";
        }
    }

    $tags = $site['tags'] ?? [];

    $urls = $site['urls'] ?? [];

    // For production, look up the local ID to ensure sync
    $explicit_id = null;
    if ($use_ssh) {
        $local_id = get_local_website_id($config['local'], $site['name']);
        if ($local_id) {
            // Check if this ID is already in use in production
            $existing_name = check_website_id_exists_ssh($db_config, $local_id);
            if ($existing_name) {
                echo "  ERROR: Cannot add '{$site['name']}' - Local ID $local_id is already used by '$existing_name' in production.\n";
                echo "         Please resolve this ID conflict manually before continuing.\n";
                $skipped++;
                continue;
            }
            $explicit_id = $local_id;
            echo "  (Using local ID: $local_id)\n";
        } else {
            echo "  WARNING: Website '{$site['name']}' not found in local database.\n";
            echo "           You should add it to LOCAL first, then to production.\n";
            echo "           Skipping to prevent ID mismatch.\n";
            $skipped++;
            continue;
        }
    }

    if ($is_dry_run) {
        echo "  [DRY RUN] Would add: {$site['name']}\n";
        if ($explicit_id) {
            echo "            ID: $explicit_id (from local)\n";
        }
        if (!empty($site['base_url'])) {
            echo "            Base URL: {$site['base_url']}\n";
        }
        if (!empty($urls)) {
            foreach ($urls as $url) {
                echo "            Crawl URL: {$url}\n";
            }
        }
        if (!empty($site['crawl_frequency'])) {
            echo "            Crawl frequency: every {$site['crawl_frequency']} days\n";
        }
        if (!empty($site['crawl_after'])) {
            echo "            Crawl after: {$site['crawl_after']}\n";
        }
        if (!empty($site['max_pages'])) {
            echo "            Max pages: {$site['max_pages']}\n";
        }
        if ($location_id) {
            echo "            Location: {$site['location']} (ID: $location_id)\n";
        } elseif (!empty($site['location'])) {
            echo "            Location: {$site['location']} (NOT FOUND)\n";
        }
        if (!empty($tags)) {
            echo "            Tags: " . implode(', ', $tags) . "\n";
        }
        $added++;
    } else {
        try {
            $new_id = $use_ssh
                ? insert_website_ssh($db_config, $site, $explicit_id)
                : insert_website_pdo($pdo, $site);

            echo "  ADD: {$site['name']} (ID: $new_id)\n";
            if (!empty($site['base_url'])) {
                echo "       Base URL: {$site['base_url']}\n";
            }

            // Add crawl URLs
            if (!empty($urls)) {
                if ($use_ssh) {
                    add_website_urls_ssh($db_config, $new_id, $urls);
                } else {
                    add_website_urls_pdo($pdo, $new_id, $urls);
                }
                foreach ($urls as $url) {
                    echo "       Crawl URL: {$url}\n";
                }
            }

            // Link to location
            if ($location_id) {
                if ($use_ssh) {
                    link_website_location_ssh($db_config, $new_id, $location_id);
                } else {
                    link_website_location_pdo($pdo, $new_id, $location_id);
                }
                echo "       Location: {$site['location']} (ID: $location_id)\n";
            }

            // Add tags
            if (!empty($tags)) {
                if ($use_ssh) {
                    add_website_tags_ssh($db_config, $new_id, $tags);
                } else {
                    add_website_tags_pdo($pdo, $new_id, $tags);
                }
                echo "       Tags: " . implode(', ', $tags) . "\n";
            }

            $added++;
        } catch (Exception $e) {
            echo "  ERROR adding {$site['name']}: " . $e->getMessage() . "\n";
        }
    }
}

echo "\n";
echo "=== Summary ===\n";
echo "Added: $added\n";
echo "Skipped: $skipped\n";

if ($is_dry_run && $added > 0) {
    echo "\nRun without --dry-run to actually add these websites.\n";
}

// Show current totals
$stats = $use_ssh ? get_stats_ssh($db_config) : get_stats_pdo($pdo);
echo "\nDatabase now has {$stats['total']} websites (max ID: {$stats['max_id']})\n";
