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
- Temporary closures (venue closed, holiday closure, maintenance)
- Invite-only events where there's no way for the public to attend
- Commercial promotions disguised as events (gym promos, store sales)
- Religious services and study groups (ongoing congregational activities)
- In-school programs not open to the public (classroom residencies, student-only workshops)
- Closed/professional auditions (company auditions, industry-only sessions)
- Virtual events unrelated to the NYC metro area (other regions, other countries)
- Space rental listings, application deadlines, and other non-events

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
- Space rental or availability listings (rehearsal space co-op dates)
- School schedule notices (flex days, PD days, snow days — the schedule entry itself, not programming during that time)
- TBA/TBD placeholder events with no actual content
- Service office hours (benefits assistance, card pickup, literacy help — scheduled services, not events)
- Cancelled or postponed notices (the notice itself is not an event)
- Internal campus events (class fundraisers, student-only activities not open to the public)
- Websites whose events are entirely non-public (e.g., arts education nonprofits that only list school residencies) — disable the website and suppress all events

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

This runs 21 pattern checks (brunch/happy hour, closures, auditions, high-occurrence, etc.) and shows how many unreviewed events match each pattern. Events matching multiple patterns are most likely to need suppression.

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

The 21 patterns are defined in `scripts/find_review_candidates.py`. To add new patterns, add entries to the `PATTERNS` list in that file.

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
| **Campus** | 23241 | Student Legacy Challenge: Pickleball Tournament | Internal campus fundraiser for enrolled students |
| **Health Svc** | 10150 | NYP Mobile Medical Unit | Recurring health service, not event |

### Should Keep

| Category | ID | Name | Why |
|----------|-------|------|-----|
| **Live Music** | 4500 | Sunday Jazz Brunch | Live jazz performers |
| **DJ** | 14271 | [happy hour] BUMP | DJ sets listed |
| **Community** | 10098 | Humanist Happy Hour | Community social gathering |
| **Activity** | 13131 | Brunch Book Club | Specific activity (book discussion) |
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
