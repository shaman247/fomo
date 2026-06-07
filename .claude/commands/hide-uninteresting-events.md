# Hide Uninteresting Events Command

Identify and suppress entries that don't qualify as real public events — routine commercial offerings, closures, religious services, non-public programs, closed auditions, non-NYC virtual events, and other non-events.

## Review Tracking

Two columns track review status:
- `reviewed` = Has this event been reviewed? (0=no, 1=yes)
- `suppressed` = Should this event be hidden? (0=no, 1=yes)

| State | reviewed | suppressed |
|-------|----------|------------|
| New/unreviewed | 0 | 0 |
| Reviewed & kept | 1 | 0 |
| Reviewed & suppressed | 1 | 1 |

## Background

fomo.nyc shows events - things with programming, performances, or specific activities that are open to the general public. We want to suppress entries that aren't real public events:
- Routine commercial offerings (brunch, happy hour without programming)
- Commercial drop-in recreation — a venue simply being open for its standard walk-in activity, e.g. a bowling alley's recurring "Open for Bowling!" / "Open Bowling" / "Public Bowling". The lanes being available is not programming. (Pattern 32. Note: a genuine bowling *event* — a league night, "Bowling Social", a tournament, a concert's VIP-lane add-on — is a keep.)
- Temporary closures (venue closed, holiday closure, maintenance)
- Invite-only events where there's no way for the public to attend
- Commercial promotions disguised as events (gym promos, store sales)
- Religious services and study groups (ongoing congregational activities)
- In-school programs not open to the public (classroom residencies, student-only workshops)
- Closed/professional auditions (company auditions, industry-only sessions)
- Virtual events unrelated to the NYC metro area (other regions, other countries)
- Space rental listings, application deadlines, and other non-events
- Shared-calendar leakage: internal placeholders (`HOLD:`, `Hold for ...`), admin notes ("2nd quarter over - collect info"), duplicate copies (`Copy of ...`), and personal appointments accidentally exposed via an embedded calendar widget (e.g., a member's electrolysis appointment showing up on a makerspace's public calendar)
- Organizational announcements/updates/letters disguised as events ("Update on Millerton Zendo", "Letter from the Director", "A Note from Our Founder", "Statement on ...") — these are written posts that the crawler ingests as recurring events because the source page assigns them an "as-of" date
- Academic-calendar non-events from university websites: drop/add deadlines, "Last Day to Complete Residency", "Summer 20XX Classes Begin", "WN Reversal Form", degree conferral dates, pass/fail deadlines, "Anniversary Day" (NYC schools staff-dev day). NYU and CUNY (esp. Bronx CC) publish whole rosters of these — they have dates but no public programming. Distinct from K-12 schedule notices (Flex Day, Spring Recess) already covered.
- Restaurant holiday menus presented as events: "Mother's Day at <Restaurant>", "Father's Day Brunch", "Memorial Day Specials", "Easter Menu 2026", "Valentine's Day Prix Fixe". Restaurant menu promotion for a holiday with no live performer/program. Distinct from real holiday programming ("Lunar New Year at Hudson Yards") — keep if description names a performer/DJ/host/comedy/trivia/etc.
- Job postings / hiring announcements that crawled from org calendars because the CMS treats every dated page as an event: "Community Engagement Coordinator - <Org>", "Marketing Coordinator - <Museum>", "Student Internship Opportunities", "Apply Now: <Fellowship Program>", "Now Hiring". The role title in the event name is the giveaway.
- Calendar negative-space and operational hour changes: "No Tuesday Program Tonight", "Bookstore Closing Early", "Will Open at 1 PM", "Closed Today", "Saturday Parking Pass Required", "Early Closing: 2 PM". These are operational notices that venues publish as calendar entries because their CMS dates everything. Distinct from outright closures already covered by Pattern 2 (e.g. "Venue Closed for Private Event") — this catches the "we'll be different today" variants.

**Key distinctions**:
- A "Sunday Jazz Brunch" with live performers is an event. A "Sunday Brunch" that's just a restaurant's regular menu is not.
- "Venue Closed for Private Event" is not an event — it's a closure notice.
- Members-only events at museums and similar institutions (where membership is easily available to the public for a fee) **are fine to keep**. But invite-only events with no public access should be suppressed.
- Community board meetings and public hearings **are events** — we want to encourage civic engagement. But internal organizational meetings (staff meetings, working group meetings for a specific org) are not.
- Support groups and 12-step meetings (AA, NA, Al-Anon) **are events** — they're open to anyone who needs them. Niche is fine; closed is not.
- Open dress rehearsals and comedy audition shows **are events** — the public can attend. But closed company auditions and professional development sessions for industry professionals are not.
- A free open rehearsal is an event. A "rehearsal space availability" listing is not.
- An art exhibition by students is a public event. An in-school classroom residency for enrolled students is not.
- A "Class of 2026" showcase at 54 Below is a public ticketed event. A "Class of 2027 Pickleball Tournament" at a university campus is an internal student event.
- A "Flex Day" on a school calendar is a schedule notice, not an event. But a movie called "Snow Day" is a real event.
- "Office Hours" at a library for benefits assistance is a service. "Office Hours" at Berlin (a music venue) is a live show.

## What to Suppress

**Suppress** if:
- Generic name without performers/themes (e.g., "Brunch", "Happy Hour", "Weekend Brunch")
- Description focuses on prices/menu ("$5 beer, $10 cocktails")
- Description says "every weekend" without mentioning specific programming
- No performers, hosts, themes, speakers, or activities mentioned
- Tags are exclusively food/drink related (Dining, Brunch, Cocktails)
- Venue/office/school closure (closed for holiday, maintenance, weather, recess, private event)
- Invite-only with no membership or ticket purchase option
- Internal organizational meeting (staff meeting, working group for a specific org)
- Registration date or deadline (not an event itself)
- Commercial promotion (gym founding memberships, store sales)
- Religious services and study groups (Bible study, prayer group, Sunday school, worship service)
- In-school programs (classroom residencies, curriculum-integrated workshops for enrolled students)
- Closed/professional auditions (company auditions, ballet auditions, invitation-only auditions)
- Professional development sessions for industry professionals (audition technique workshops, feedback sessions for opera singers)
- Virtual events for non-NYC regions (webinars for other states/countries)
- Off-region in-person events that got mis-mapped to an NYC venue: cultural-tour trips ("OlioTrip Morocco" 8-day journey at Think Olio), sister-venue listings (an NYC venue's website surfacing its Miami/Idaho/Chicago location's calendar), and academic/professional events at off-region campuses (Columbia Global Centers Paris, Wine School of Philadelphia). The AI extracts the real location but `get_location_id` falls back to the website's tied NYC venue when no match is found
- Space rental or availability listings (rehearsal space co-op dates)
- School schedule notices (flex days, PD days, snow days — the schedule entry itself, not programming during that time)
- Commercial drop-in recreation (a bowling alley "Open for Bowling!", "Open Bowling", "Public Bowling" — walk-in lanes, not a programmed event)
- TBA/TBD placeholder events with no actual content
- Service office hours (benefits assistance, card pickup, literacy help — scheduled services, not events)
- Municipal service notices (alternate-side parking suspended/in effect, street cleaning, garbage/recycling pickup schedules, sanitation holiday schedules) — these are city operational notices that community-board calendars republish, not events
- Cancelled or postponed notices (the notice itself is not an event)
- Internal campus events (class fundraisers, student-only activities not open to the public)
- Websites whose events are entirely non-public (e.g., arts education nonprofits that only list school residencies) — disable the website and suppress all events
- Calendar-widget leakage: `HOLD:` / `Hold for ...` / `Hold - ...` placeholders, `Copy of ...` duplicates, internal admin notes ("collect info", "quarter over", "payroll"), and personal appointments at unrelated venues. When a site embeds a shared iCal/Google Calendar, member-added private entries can leak through. Common giveaways: bare lowercase noun names ("electrolysis", "haircut", "physical"), venue address completely unrelated to the host website, names of individuals in parens (e.g., "(Maurice)", "(Host Karen)") that signal an internal scheduling hold.
- Organizational news/updates/letters that the crawler treats as events: `^Update on ...`, `^An update from ...`, `^A Letter from the ...`, `^A Note from ...`, `^From Our Director ...`, `^Statement on ...`, `^Open Letter ...`. Description reads as prose about org news (a sangha splitting off, a director's farewell, a policy stance) with no scheduled programming. Keep "Notice of Meeting" — that's a real public meeting. Keep titled artworks/shows that happen to use these words ("Message from the Mud", "Remembering the U.S. Colored Troops" — both real events). Note: source pages assign these announcements an "as-of" date that the extractor then mistakes for recurring occurrences (e.g. 121905 got 3 weekly occurrences).

**Keep** if:
- Mentions specific performers (DJ, musician, comedian, author, speaker)
- Has educational/activity component (class, workshop, tour, lesson)
- Community-organized social gathering (meetup, alumni, networking)
- Themed event (Lunar New Year, book discussion, trivia, bingo, karaoke)
- Open mic, comedy show, or any performance element
- Volunteer opportunities (food rescue, community service, garden workdays)
- Members-only at museums/gardens/art centers/cultural institutions (membership is publicly available for a fee)
- Special programming during school recess (art camps, family workshops — the programming is an event even if the recess itself is not)
- Sold-out events (they were public events, just no more tickets)
- Community board meetings, committee meetings, and public hearings (civic engagement)
- Support groups and 12-step meetings (AA, NA, Al-Anon — open to anyone who needs them)
- Open audition shows (comedy audition shows where public can watch)
- Open dress rehearsals and open workshops (free/public rehearsals)
- Choir/ensemble rehearsals that welcome new participants ("all voices welcome")
- Student exhibitions and public-facing art shows (even if made by students)
- Public info sessions (open to anyone interested)
- NYC-relevant or general-topic virtual events (birding webinar, urban farming)
- Student showcases at public venues (54 Below class showcases, MFA exhibitions at galleries)
- Programming during school schedule changes (art camps during flex days, workshops during recess)
- "Snow Day" or "Flex Day" as a movie/show title (not a schedule notice)

## Instructions

### Step 1: Check candidate counts

```bash
./venv/bin/python scripts/find_review_candidates.py --count
```

This runs 32 pattern checks (brunch/happy hour, closures, auditions, high-occurrence, shared-calendar leakage, off-region location_name, municipal-service notices, organizational announcements, academic-calendar deadlines, restaurant holiday menus, job postings, calendar negative-space, commercial drop-in bowling, etc.) and shows how many unreviewed events match each pattern. Events matching multiple patterns are most likely to need suppression.

### Step 2: Get a batch of candidates

```bash
./venv/bin/python scripts/find_review_candidates.py --limit 50
```

Candidates are sorted by number of matching patterns (most suspicious first). Each entry shows: name, location, website, tags, occurrence count, matched patterns, and description.

### Step 3: Review and classify each event

For each candidate, decide suppress or keep based on:
1. **Name**: Generic ("Brunch") or specific ("Jazz Brunch with the Hot Club")?
2. **Description**: Performers/themes/activities, or just prices/menu/schedule notice?
3. **Tags**: Non-food tags present (Music, Comedy, Community)?
4. **Pattern context**: Which pattern(s) flagged it? Many false positives exist (see examples below).

### Step 4: Update the database

```sql
-- Suppress non-events
UPDATE events SET reviewed = 1, suppressed = 1 WHERE id IN (...);

-- Keep real events
UPDATE events SET reviewed = 1, suppressed = 0 WHERE id IN (...);
```

### Step 5: Repeat

Run Step 2 again — the script automatically skips already-reviewed events. Continue until `--count` shows 0.

### Other script options

```bash
./venv/bin/python scripts/find_review_candidates.py --pattern 13    # Only high-occurrence pattern
./venv/bin/python scripts/find_review_candidates.py --offset 50     # Skip first 50 (pagination)
```

The 32 patterns are defined in `scripts/find_review_candidates.py`. To add new patterns, add entries to the `PATTERNS` list in that file. Pattern 23's place list (countries, US states, major non-NYC cities) comes from `NON_NYC_PLACES = city_config.non_region_place_patterns()` at the top of the file — it's sourced from `config/<FOMO_CITY>.yaml` (city-agnostic), so extend it by editing the `non_region_place_patterns` list in `config/nyc.yaml`, not the constant in this script.

### Spotting calendar-widget leaks manually

Pattern 22 catches the obvious internal entries (`HOLD:`, `Hold for ...`, `Copy of ...`, "collect info"). Personal-appointment leaks (e.g., a member's electrolysis appointment at "Nios Spa" showing up on the NYC Resistor calendar) won't fire any text pattern — the name and venue are real, just irrelevant. Spot them via:

```sql
-- Events whose location_id is NOT linked to their website (cross-venue mismatch)
SELECT e.id, e.name, e.location_name, w.name AS website, LEFT(e.description, 120) AS description
FROM events e
JOIN websites w ON e.website_id = w.id
WHERE e.archived = 0 AND e.suppressed = 0
  AND e.location_id IS NOT NULL
  AND EXISTS (SELECT 1 FROM website_locations wl WHERE wl.website_id = e.website_id)
  AND e.location_id NOT IN (SELECT wl.location_id FROM website_locations wl WHERE wl.website_id = e.website_id)
  AND (e.description IS NULL OR e.description = '' OR e.description = 'No description available.' OR CHAR_LENGTH(e.description) < 30)
  AND CHAR_LENGTH(e.name) < 30
ORDER BY w.name, e.id;
```

Most rows will be legit cross-venue partnerships (Knitting Factory shows at "The District", touring acts, etc.). The leaks stand out as: bare lowercase noun names, venue clearly unrelated to the host site (spa, salon, dental office), no real description. When you find one, also check the source crawl content (`crawl_results.crawled_content` for the relevant `crawl_run`) — if the entry only appears as a one-line embed without a public registration link, it's a leak.

---

## Examples

### Should Suppress

| Category | ID | Name | Why |
|----------|-------|------|-----|
| **Food/Drink** | 7887 | Brunch | Generic restaurant brunch, no programming |
| **Food/Drink** | 7888 | Happy Hour | Just drink prices, no entertainment |
| **Food/Drink** | 14348 | $8 Happy Hour at Eataly | Price promotion, no programming |
| **Food/Drink** | 13180 | Savory Sunday Brunch | Generic weekend brunch at restaurant |
| **Closure** | 18590 | Closed | Brooklyn Bowl closed notice |
| **Closure** | 17907 | Sorry, We Are Closed! (Maintenance Mid Feb) | Venue maintenance closure |
| **Closure** | 18030 | 9:30Pm - Venue Closed for Private Event | Venue closure for private function |
| **Closure** | 26168 | The Morbid Anatomy Library... is Closed Due Weather | Weather closure |
| **Holiday** | 24372 | City Hall Closed \| Lincoln's Birthday | Office closed for holiday |
| **Holiday** | 25740 | Easter (Bms Closed) | School closed for holiday |
| **Holiday** | 5897 | Presidents Day - Washington's Birthday | Holiday notice, not an event |
| **Recess** | 19996 | Mid-Winter Recess (Bms Closed) | School closed for recess |
| **Recess** | 5896 | Midwinter Recess | NYC public schools closed notice |
| **Private** | 17224 | Private Party | Bar reserved for private group |
| **Invite-Only** | 12998 | WATERWORKS Works-in-Process I Invite-Only | No public access |
| **Internal** | 27044 | Salmagundi members meeting | Internal org business meeting |
| **Not Event** | 24707 | Spring I Programs Member Registration Start | Registration date, not an event |
| **Store Promo** | 14349 | Heartfelt gifts at Pandora | Shopping promotion |
| **Store Promo** | 14343 | Tumi Semi-Annual Sale | Sale event |
| **Store Promo** | 26277 | SLT Hudson Yards Founding Memberships | Gym membership promo |
| **Routine** | 100294 | Open for Bowling! | Brooklyn Bowl's lanes open for walk-in bowling — venue just open, not a programmed event (surfaces under Music because the venue is Music-tagged) |
| **Routine** | 7826 | Bee-Eater Feeding | Daily zoo schedule |
| **Routine** | 7827 | Sea Lion Feeding | Daily zoo schedule |
| **Shop** | 8833 | Bryant Park Shop | Shop being open |
| **Attraction** | 14351 | Propose at Edge | Permanent service, not event |
| **Religious** | 442 | Bible Study Group | Ongoing congregational study group |
| **Religious** | 9553 | Sunday School | Weekly children's religious education |
| **Religious** | 9629 | Sunday Worship Service | Regular worship service |
| **Religious** | 30757 | Tuesday Afternoon Prayer Group | Small group prayer meeting |
| **Audition** | 21021 | BBT Junior Company Auditions | Closed ballet audition |
| **Audition** | 28634 | 2026 National Audition Tour: NYC Final Auditions | Professional ballet audition |
| **Audition** | 23639 | MDP Company Audition for 2026/2027 | Invitation-only dance audition |
| **Pro Dev** | 13043 | Audition Workshop | Professional development for performers |
| **Pro Dev** | 23464 | Feedback Auditions | Industry feedback sessions for opera singers |
| **In-School** | 23668 | Puppetry + Storytelling at PS 6 | Classroom residency for enrolled students |
| **Non-NYC** | 32527 | CISA Active Shooter Webinar - Region 3 | For DC/DE/MD/PA/VA/WV, not NYC |
| **Non-NYC** | 32531 | Cyber Scotland Week: Keeping children safe online | Scottish event, not NYC |
| **Non-NYC** | 30732 | IRS Jovem e Crédito: O que Muda | Portuguese tax webinar |
| **Non-NYC** | 27691 | Isadora Goes to Iowa | Event in Iowa, not NYC |
| **Off-Region Trip** | 59195 | OlioTrip Morocco: Music, Spirit & Living Tradition | 8-day immersive trip in Morocco listed on Think Olio's NYC calendar; `location_name='Morocco'` mapped to Think Olio's NYC venue by `get_location_id` fallback |
| **Off-Region Trip** | 59239 | OlioTrip Morocco: Music, Spirit & Living Tradition | Same trip listed on Olio Lighthouse's calendar — mapped to its Brooklyn venue |
| **Off-Region Sister Venue** | 116349 | The Sewing Circle: Sewing 101 | `location_name='Fabrik Chicago'` mapped to Fabrik Tribeca |
| **Off-Region Sister Venue** | 135627 | DJ Friday Nights at Wyn Wyn | Arlo Wynwood, Miami event leaking onto The Water Tower Bar's NYC calendar |
| **Off-Region Sister Venue** | 95182 | Max McNown: The Summer Vacation Tour | Outlaw Field at the Idaho Botanical Garden listed on Knitting Factory at Baker Falls's calendar |
| **Off-Region Campus** | 110787 | Hegel 13/13 with Étienne Balibar | Columbia Global Centers Paris event mapped to Columbia University NYC |
| **Off-Region Campus** | 132570 | Accelerated Sommelier Course (Summer) | Wine School of Philadelphia course aggregated by Local Wine Events (NYC) |
| **Off-Region Trip** | 111866 | Maccabi Games 2026 | Kansas City sports tournament listed on JCC of Staten Island |
| **Exclusive** | 28603 | Finding the Issues: A Member Exclusive Webinar | PEN America members only |
| **Exclusive** | 26586 | Open Rehearsal: Marc-André Hamelin | Donors/subscribers only |
| **Not Event** | 23603 | West Village Rehearsal Co-Op Availability | Space rental listing |
| **Not Event** | 23449 | Audition Workshop 2026 Application Deadline | Application deadline |
| **Schedule** | 21876 | Flex Day | Music conservatory schedule notice |
| **Schedule** | 21877 | Lunar New Year – Flex Day | School flex day, not a celebration |
| **Placeholder** | 18462 | TBA | No actual event details |
| **Placeholder** | 17774 | TBD | No actual event details |
| **Cancelled** | 27032 | Art class by Joseph Perez postponed | Postponement notice |
| **Service** | 35631 | Access Benefits at NYPL - Office hours | Benefits assistance service |
| **Service** | 30043 | Office Hours Card Set Pick Up | Pickup window, not event |
| **Municipal** | 95097 | Alternate Side Parking Suspended | NYC parking-rule notice republished on a community-board calendar; not an event |
| **Municipal** | 125059 | Waste Basket Pick Up Service | Sanitation pickup schedule, not a public event |
| **Campus** | 23241 | Student Legacy Challenge: Pickleball Tournament | Internal campus fundraiser for enrolled students |
| **Health Svc** | 10150 | NYP Mobile Medical Unit | Recurring health service, not event |
| **Calendar Leak** | 24672 | HOLD: NYC Mesh (Guillaume) | Internal calendar placeholder, not a public event |
| **Calendar Leak** | 115002 | HOLD: Repair Event (Maurice) | Internal hold for a member; no public details |
| **Calendar Leak** | 115000 | Hold for Wax to Metal - jewelry | Placeholder reservation for class prep |
| **Calendar Leak** | 122779 | 2nd quarter over - collect info | Internal admin note on shared calendar |
| **Calendar Leak** | 114996 | electrolysis | Member's personal appointment at Nios Spa leaked through NYC Resistor's embedded calendar |
| **Announcement** | 121905 | Update on Millerton Zendo | Brooklyn Zen Center news post about a sangha splitting off — written announcement, not a scheduled event (extracted as 3 recurring occurrences) |
| **Academic Cal** | 100426 | Summer 2026 Drop/Add Deadline: Second 3-Week Session | NYU academic-calendar deadline; no public programming |
| **Academic Cal** | 117760 | Last day to drop Summer 2026 3W1 courses with 100% Tuition Refund | Bronx Community College tuition-refund deadline |
| **Academic Cal** | 108162 | Spring 2026 Degree Conferral Date | Date credentials are issued; not a ceremony |
| **Academic Cal** | 122506 | Anniversary Day | NYC schools staff-development day; standalone entry, not a school event |
| **Holiday Menu** | 121386 | Mother's Day Celebration at The Fulton by Jean-Georges | Restaurant prix-fixe promotion, no programming |
| **Holiday Menu** | 92510 | Mother's Day at Bar San Miguel | Restaurant brunch promo |
| **Holiday Menu** | 59223 | Easter Menu 2026 | Restaurant holiday menu |
| **Holiday Menu** | 44876 | Memorial Day Brunch | Generic holiday brunch at a restaurant |
| **Job Posting** | 116080 | Community Engagement Coordinator - Planting Fields Foundation | Job listing on org calendar |
| **Job Posting** | 96165 | Student Internship Opportunities | Internship recruitment, not an event |
| **Job Posting** | 97203 | Apply Now: NYSCA/NYFA Artist as Entrepreneur Program in Syracuse | Program application call |
| **No Program** | 139212 | No Tuesday General Program Tonight (Williamsburg Branch) | Programming cancellation notice |
| **Hour Change** | 139396 | OS Nyc Will Open at 1 PM | Late-opening notice |
| **Hour Change** | 97820 | Bookstore Closing Early | Early-close announcement |
| **Op Notice** | 139328 | Saturday Parking Pass Required | Visitor parking rule, not a public event |

### Should Keep

| Category | ID | Name | Why |
|----------|-------|------|-----|
| **Live Music** | 4500 | Sunday Jazz Brunch | Live jazz performers |
| **DJ** | 14271 | [happy hour] BUMP | DJ sets listed |
| **Community** | 10098 | Humanist Happy Hour | Community social gathering |
| **Activity** | 13131 | Brunch Book Club | Specific activity (book discussion) |
| **Social** | — | Bowling Night / Bowling Social [18+] | Organized social bowling event, not just open lanes |
| **Live Music** | 12777 | Friday Happy Hour w/ Peter Watrous | Named performer |
| **Live Music** | 14647 | $12 Martini & Jazz Thursday | Live jazz quartet |
| **Comedy** | 10404 | Tall Boy Comedy | Comedy show at distillery |
| **Activity** | 2991 | Origami Workshop | Educational class |
| **Celebration** | 14342 | Lunar New Year at Hudson Yards | Community celebration with performances |
| **Broadway** | 5676 | All Out: Comedy About Ambition | Theatrical run (high occurrence OK) |
| **Museum Members** | 3329 | Member Early Hour (MoMA) | Museum membership available to public |
| **Museum Members** | 13072 | Member Star Party (AMNH) | Museum membership available to public |
| **Recess Event** | 26480 | Mid-Winter Recess Art Camp! | Real programming during recess |
| **Recess Event** | 3901 | Midwinter Recess – Family Art Workshops | Real programming during recess |
| **Sold Out** | 12484 | SOLD OUT - Haley Pham + Alex Aster | Was public, just no more tickets |
| **Civic** | 25533 | Full Board Meeting (CB2) | Community board — civic engagement |
| **Civic** | 9168 | ULURP Public Hearing | Public participation welcome |
| **Support** | 20134 | Friday Sober Agnostics | Open AA meeting |
| **Support** | 2457 | Queers Do Recover NA | Open recovery meeting |
| **Open Audition** | 20749 | The Industry Room Audition Show | Comedy show — public can watch |
| **Open Audition** | 31077 | New Talent/Weekly Stand Up Auditions | Open mic — public event |
| **Open Rehearsal** | 23508 | Free Open Dress Rehearsals: Suor Angelica | Free public performance |
| **Open Rehearsal** | 23511 | Free Open Dress Rehearsal: Carmen | Free public performance |
| **Open Rehearsal** | 23645 | Spring 2026 Open Rehearsal | Public behind-the-scenes event |
| **Open Workshop** | 3777 | Fat Cats Youth Orchestra Open Workshop | Open to participants |
| **Open Choir** | 30905 | Sing in Solidarity Rehearsal | "All voices welcome" |
| **Student Show** | 19243 | MPS Art Therapy Spring 2026 Exhibition | Public exhibition |
| **Info Session** | 23269 | Virtual Info Session: Scholarships at Usdan | Open to prospective families |
| **Museum Member** | 3329 | Member Early Hour (MoMA) | Membership available to anyone |
| **False Positive** | 26628 | A Private Life | Movie title, not a private event |
| **False Positive** | 25683 | Charlie and the Darlings @ Private Curtain | KGB Bar series name |
| **False Positive** | 26313 | Maintenance Artist | Movie title, not maintenance |
| **False Positive** | 776 | Dianna Agron at Café Carlyle | "residency" = musical residency, not school |
| **False Positive** | 20994 | TRIPLET AUDITIONS | Comedy show parody concept |
| **False Positive** | 19493 | Snow Day | Movie screening at Nitehawk, not a school closure |
| **False Positive** | 23712 | Office Hours \| Mars Rodriguez \| Death Drive | Live music show, "Office Hours" is series name |
| **Student Show** | 26864 | Ithaca College's Performance Class of 2026 | Public ticketed showcase at 54 Below |
| **Student Show** | 36402 | Class of 2027 First Year MFA Exhibition | Public gallery exhibition at Columbia |

---

## Reverting Mistakes

If an event was incorrectly suppressed, mark it as kept:

```sql
UPDATE events SET suppressed = 0 WHERE id = <event_id>;
```

If an event should be re-reviewed:

```sql
UPDATE events SET reviewed = 0 WHERE id = <event_id>;
```
