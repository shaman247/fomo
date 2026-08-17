#!/usr/bin/env python3
"""
Find events that may need suppression based on pattern rules.

Scans unreviewed, non-archived events and flags candidates for human review.
Outputs candidates sorted by number of matching patterns (most suspicious first).

Usage:
    ./venv/bin/python scripts/find_review_candidates.py              # Show first 50
    ./venv/bin/python scripts/find_review_candidates.py --limit 100  # Show 100
    ./venv/bin/python scripts/find_review_candidates.py --offset 50  # Skip first 50
    ./venv/bin/python scripts/find_review_candidates.py --pattern 13 # Only pattern 13
    ./venv/bin/python scripts/find_review_candidates.py --count      # Summary counts
"""

import argparse
import sys

sys.path.insert(0, 'pipeline')
from db import create_connection
import city_config

# Places outside the metro region that, when they appear in an event's
# `location_name`, strongly suggest the event is not local (e.g. cultural tours
# abroad, off-region webinars whose mapped venue is the website's default).
# Word-boundary matched. Loaded from the city config (review.non_region_places).
NON_NYC_PLACES = city_config.non_region_place_patterns()
_NON_NYC_REGEXP = "[[:<:]](" + "|".join(NON_NYC_PLACES) + ")[[:>:]]"


# Each pattern: id, name, and SQL WHERE clause (applied to events e)
# JOINs are specified separately for patterns that need them
PATTERNS = [
    {
        'id': 1,
        'name': 'Generic brunch/happy hour',
        'query': """
            SELECT DISTINCT e.id FROM events e
            WHERE e.archived = 0 AND e.reviewed = 0
              AND e.name REGEXP '(brunch|happy hour)'
        """,
    },
    {
        'id': 2,
        'name': 'Closures and non-events',
        'query': """
            SELECT DISTINCT e.id FROM events e
            WHERE e.archived = 0 AND e.reviewed = 0
              AND (
                e.name REGEXP '(^Closed|Closed$|^CLOSED|\\\\bClosed for\\\\b|\\\\bClosure\\\\b|\\\\bOffice Closed\\\\b)'
                OR e.name REGEXP 'Venue Closed|We Are Closed|Closed Due'
                OR e.name LIKE '%Private Party%'
                OR e.name REGEXP '^Private [Ee]vent'
                OR (e.name LIKE '%Private Dining%' AND e.name NOT REGEXP '(show|perform|comedy|music|concert)')
                OR (e.description LIKE '%closed for a private event%')
                OR (e.name LIKE '%Recess%' AND (e.name LIKE '%Closed%' OR e.name LIKE '%No Programming%' OR e.description LIKE '%closed%'))
                OR (e.name LIKE '%Recess%' AND e.location_name LIKE '%Public Schools%')
              )
        """,
    },
    {
        'id': 3,
        'name': 'Invite-only and non-public',
        'query': """
            SELECT DISTINCT e.id FROM events e
            WHERE e.archived = 0 AND e.reviewed = 0
              AND (
                e.name LIKE '%Invite-Only%'
                OR e.name LIKE '%Invite Only%'
                OR e.description LIKE '%invite-only%'
                OR e.description LIKE '%invited guests only%'
              )
        """,
    },
    {
        'id': 4,
        'name': 'Religious services and study groups',
        'query': """
            SELECT DISTINCT e.id FROM events e
            WHERE e.archived = 0 AND e.reviewed = 0
              AND (
                e.name REGEXP '(Bible Study|Prayer Group|Sunday School|Worship Service|Torah Study|Shabbat Service)'
                OR e.name REGEXP '^(Sunday|Weekly|Morning|Evening) (Service|Worship|Prayer|Mass)$'
              )
        """,
    },
    {
        'id': 5,
        'name': 'Auditions and rehearsals',
        'query': """
            SELECT DISTINCT e.id FROM events e
            WHERE e.archived = 0 AND e.reviewed = 0
              AND (
                e.name LIKE '%Audition%'
                OR e.name LIKE '%Rehearsal%'
              )
        """,
    },
    {
        'id': 6,
        'name': 'In-school programs',
        'query': """
            SELECT DISTINCT e.id FROM events e
            WHERE e.archived = 0 AND e.reviewed = 0
              AND (
                (e.name REGEXP '(Residency|Workshop)' AND e.name REGEXP '(PS |P\\\\.S\\\\.|School)')
                OR e.description LIKE '%in-school%'
                OR (e.description LIKE '%grade%' AND e.description LIKE '%residency%')
                OR (e.description LIKE '%curriculum%' AND e.description LIKE '%student%')
              )
        """,
    },
    {
        'id': 7,
        'name': 'Non-NYC virtual events',
        'query': """
            SELECT DISTINCT e.id FROM events e
            WHERE e.archived = 0 AND e.reviewed = 0
              AND e.location_name IN ('Online', 'Virtual', 'Online Event', 'Virtual Event', 'ZOOM', 'Online via Zoom', 'Webex')
              AND (
                e.name LIKE '%Region %' AND e.name NOT LIKE '%Region 2%'
                OR e.description LIKE '%DC/DE/MD%'
                OR e.description LIKE '%Scotland%'
                OR e.description LIKE '%UK %'
                OR e.description REGEXP 'for (the )?[A-Z][a-z]+ region'
                OR e.name REGEXP '^[^a-zA-Z0-9]*[À-ÿ]'
              )
        """,
    },
    {
        'id': 8,
        'name': 'Members-only / exclusive access',
        'query': """
            SELECT DISTINCT e.id FROM events e
            WHERE e.archived = 0 AND e.reviewed = 0
              AND (
                e.name LIKE '%Member Exclusive%'
                OR e.name LIKE '%Members Only%'
                OR e.name LIKE '%Members-Only%'
                OR e.name LIKE '%Member Only%'
                OR e.name LIKE '%Member-Only%'
                OR e.name LIKE '%Members Event%'
                OR e.description LIKE '%member-exclusive%'
                OR e.description LIKE '%members only%'
                OR e.description LIKE '%members-only%'
                OR e.description LIKE '%donors and subscribers%'
                OR e.description LIKE '%invited guests only%'
              )
        """,
    },
    {
        'id': 9,
        'name': 'Registration dates and non-events',
        'query': """
            SELECT DISTINCT e.id FROM events e
            WHERE e.archived = 0 AND e.reviewed = 0
              AND (
                e.name LIKE '%Registration Start%'
                OR e.name LIKE '%Registration Opens%'
                OR e.name LIKE '%Application Deadline%'
                OR e.name LIKE '%Availability%'
                OR e.name LIKE '%Now Open%'
              )
        """,
    },
    {
        'id': 10,
        'name': 'Price-focused (no programming)',
        'query': """
            SELECT DISTINCT e.id FROM events e
            WHERE e.archived = 0 AND e.reviewed = 0
              AND (
                e.description REGEXP '\\\\$[0-9]+ (drinks|cocktails|beers|wines|mimosas)'
                OR e.description REGEXP '(drinks|cocktails|beers) (starting at|for just|from) \\\\$[0-9]+'
              )
              AND e.description NOT REGEXP '(dj|live|perform|comedy|class|workshop|fundrais|benefit)'
        """,
    },
    {
        'id': 11,
        'name': '"Every week" without programming',
        'query': """
            SELECT DISTINCT e.id FROM events e
            WHERE e.archived = 0 AND e.reviewed = 0
              AND e.description REGEXP 'every (day|week|weekend|saturday|sunday)'
              AND e.description NOT REGEXP '(dj|live|perform|artist|musician|comedy|comedian|host|featuring|present|trivia|karaoke|open mic)'
        """,
    },
    {
        'id': 12,
        'name': 'Food/drink-only tags',
        'query': """
            SELECT e.id FROM events e
            JOIN event_tags et ON e.id = et.event_id
            JOIN tags t ON et.tag_id = t.id
            WHERE e.archived = 0 AND e.reviewed = 0
            GROUP BY e.id
            HAVING GROUP_CONCAT(t.name SEPARATOR ', ')
              REGEXP '^(Dining|Brunch|Food|Cocktails|Happy Hour|Weekend|Sunday|Saturday|Bottomless|Drinks|Bar|Restaurant|Eats|,| )+$'
        """,
    },
    {
        'id': 13,
        'name': 'High-occurrence (30+ occurrences or 60+ day span)',
        'query': """
            SELECT e.id FROM events e
            LEFT JOIN event_occurrences eo ON e.id = eo.event_id
            WHERE e.archived = 0 AND e.reviewed = 0
            GROUP BY e.id
            HAVING COUNT(eo.id) >= 30
              OR DATEDIFF(MAX(eo.start_date), MIN(eo.start_date)) >= 60
        """,
    },
    {
        'id': 14,
        'name': 'Shopping center promotions',
        'query': """
            SELECT DISTINCT e.id FROM events e
            JOIN websites w ON e.website_id = w.id
            WHERE e.archived = 0 AND e.reviewed = 0
              AND w.name IN ('Hudson Yards', 'The Shops at Columbus Circle',
                             'Brookfield Place', 'Industry City', 'Olly Olly Market')
        """,
    },
    {
        'id': 15,
        'name': 'Shops, sales, and permanent attractions',
        'query': """
            SELECT DISTINCT e.id FROM events e
            WHERE e.archived = 0 AND e.reviewed = 0
              AND (
                -- The leading (^|space|hyphen) is load-bearing: a bare
                -- '(Sale|Shop|Store|Boutique)$' matches the TAIL of ordinary words and
                -- flooded this queue with real programming — "Workshop" (235 rows),
                -- "Bishop" ("An Evening with Kelly Bishop"), "Bookshop"/"Bookstore"
                -- (author events at Astoria Bookshop, Greenlight Bookstore) and
                -- "Restore" ("Women Who Restore"). Measured 2026-08-16: 267 matches
                -- → 26, and every dropped row ended in one of those words. The hyphen
                -- alternative keeps genuinely-hyphenated shops ("Rex's Dino-Store").
                e.name REGEXP '(^|[[:space:]]|-)(Sale|Shop|Store|Boutique)$'
                OR e.name LIKE '%Grand Opening%'
                OR e.name LIKE '%Now Open%'
                OR e.name LIKE '%% Off%'
                OR (e.description LIKE '%shop %' AND e.description LIKE '%save %')
              )
        """,
    },
    {
        'id': 16,
        'name': 'Zoo/aquarium daily activities',
        'query': """
            SELECT DISTINCT e.id FROM events e
            WHERE e.archived = 0 AND e.reviewed = 0
              AND (
                e.name LIKE '%Feeding%'
                OR e.name LIKE '%Daily %'
                OR (e.description LIKE '%daily %' AND e.description LIKE '%scheduled%')
              )
        """,
    },
    {
        'id': 17,
        'name': 'School schedule notices',
        'query': """
            SELECT DISTINCT e.id FROM events e
            WHERE e.archived = 0 AND e.reviewed = 0
              AND (
                e.name REGEXP '^Flex Day'
                OR e.name REGEXP '(Professional Development|PD Day|Staff Development|Teacher).*Day'
                OR e.name REGEXP '^No (School|Classes|Programming)'
                OR e.name LIKE '%School Closed%'
                OR e.name LIKE '%Classes Canceled%'
                OR e.name LIKE '%Classes Cancelled%'
                OR e.name REGEXP '^(Spring|Winter|Summer|Fall|Holiday|Thanksgiving|Christmas) (Break|Recess|Vacation)$'
              )
        """,
    },
    {
        'id': 18,
        'name': 'TBA/placeholder events',
        'query': """
            SELECT DISTINCT e.id FROM events e
            WHERE e.archived = 0 AND e.reviewed = 0
              AND (
                e.name REGEXP '^TBA$'
                OR e.name REGEXP '^TBD$'
                OR e.name LIKE '%Coming Soon%'
                OR e.name LIKE '%To Be Announced%'
                OR e.name LIKE '%To Be Determined%'
                OR e.name LIKE '%Stay Tuned%'
              )
        """,
    },
    {
        'id': 19,
        'name': 'Cancelled/postponed notices',
        'query': """
            SELECT DISTINCT e.id FROM events e
            WHERE e.archived = 0 AND e.reviewed = 0
              AND (
                e.name LIKE '%CANCELLED%'
                OR e.name LIKE '%CANCELED%'
                OR e.name LIKE '%Cancelled%'
                OR e.name LIKE '%Canceled%'
                OR e.name LIKE '%POSTPONED%'
                OR e.name LIKE '%Postponed%'
                OR e.name REGEXP 'postponed$'
              )
        """,
    },
    {
        'id': 20,
        'name': 'Service office hours (non-events)',
        'query': """
            SELECT DISTINCT e.id FROM events e
            WHERE e.archived = 0 AND e.reviewed = 0
              AND (
                e.name LIKE '%Office Hours%'
                OR e.name LIKE '%Office hours%'
              )
              AND e.description NOT REGEXP '(perform|music|comedy|dj|live|concert|show)'
        """,
    },
    {
        'id': 21,
        'name': 'Internal campus events',
        'query': """
            SELECT DISTINCT e.id FROM events e
            WHERE e.archived = 0 AND e.reviewed = 0
              AND (
                e.name REGEXP 'Class of 20[0-9]{2}'
                OR e.name LIKE '%Student Legacy%'
                OR e.name LIKE '%Commencement%'
                OR e.name LIKE '%Convocation%'
              )
        """,
    },
    {
        'id': 22,
        'name': 'Shared-calendar leakage (placeholders, admin, personal appts)',
        'query': """
            SELECT DISTINCT e.id FROM events e
            WHERE e.archived = 0 AND e.reviewed = 0
              AND (
                e.name REGEXP '^(HOLD|Hold):'
                OR e.name REGEXP '^(HOLD|Hold) for '
                OR e.name REGEXP '^(HOLD|Hold) ?- '
                OR e.name LIKE 'Copy of %'
                OR e.name REGEXP '^[Tt]est$'
                OR e.name REGEXP '^[Tt]est [Ee]vent$'
                OR e.name LIKE '%quarter over%'
                OR e.name LIKE '%collect info%'
                OR e.name LIKE '%Payroll%'
              )
        """,
    },
    {
        # Municipal operational notices that community-board/NYC.gov calendars
        # republish — alternate-side parking suspensions, street-cleaning rules,
        # sanitation holiday schedules, etc. NOT a real public event.
        # Keep this narrow: "Recycling Collection" / "Garbage Pickup" alone are
        # too broad — community drop-off drives use the same words. Only flag
        # when paired with a notice keyword (Suspended/Schedule/Holiday/Notice).
        'id': 24,
        'name': 'Municipal service notices (parking, sanitation)',
        'query': r"""
            SELECT DISTINCT e.id FROM events e
            WHERE e.archived = 0 AND e.reviewed = 0
              AND (
                e.name REGEXP 'Alternate Side Parking'
                OR e.name REGEXP 'Parking (Suspended|Regulations|Rules|In Effect)'
                OR e.name REGEXP 'Street Cleaning (Suspended|In Effect|Schedule|Rules)'
                OR e.name REGEXP '^ASP (Suspended|In Effect|On|Off)'
                OR e.name REGEXP '(Garbage|Trash|Recycling|Sanitation) (Pickup|Pick-Up|Pick Up|Collection|Service) (Suspended|Schedule|Holiday)'
                OR e.name REGEXP 'Sanitation (Holiday|Schedule|Notice)'
                OR e.name LIKE '%Waste Basket Pick%'
              )
        """,
    },
    {
        # Catches organizational announcements/news/letters that crawlers
        # extract as events. e.g. "Update on Millerton Zendo" at Brooklyn Zen
        # Center — a written post about a sangha splitting off, not a scheduled
        # event. Narrow phrases only: leading "Update on/from", "An update
        # on/from", "Letter from", "A Note from", "From Our Director", "Notice
        # of <noun>" (but excluding "Notice of Meeting" since that IS a real
        # public meeting). False positives: "Message from the Mud" (artwork
        # title), "Remembering the U.S. Colored Troops" (commemorative event)
        # — keep regex anchored and specific.
        'id': 25,
        'name': 'Organizational announcements/updates (not events)',
        'query': """
            SELECT DISTINCT e.id FROM events e
            WHERE e.archived = 0 AND e.reviewed = 0
              AND (
                e.name REGEXP '^(An )?[Uu]pdate (on|from|about|regarding) '
                OR e.name REGEXP '^(A )?[Ll]etter (from|to) (the|our) '
                OR e.name REGEXP '^A Note from '
                OR e.name REGEXP '^From (Our|the) (Director|Founder|Editor|Board|Team|President|CEO|Pastor|Rabbi|Rector)'
                OR e.name REGEXP '^Statement (on|from|of|by|regarding) '
                OR e.name REGEXP '^Open Letter '
              )
        """,
    },
    {
        # Academic-calendar non-events that crawled from university sites: drop/add
        # deadlines, "Last day to complete residency", "Classes Begin", degree
        # conferral dates, "Anniversary Day" (NYC schools staff-dev day). These
        # have a date but no public programming. NYU and CUNY (esp. Bronx CC)
        # publish whole rosters of these. Pattern 17 catches K-12 schedule
        # notices; this catches higher-ed academic-calendar entries.
        'id': 26,
        'name': 'Academic calendar deadlines (drop/add, conferral, residency)',
        'query': r"""
            SELECT DISTINCT e.id FROM events e
            WHERE e.archived = 0 AND e.reviewed = 0
              AND (
                e.name REGEXP '(Drop/Add Deadline|Add/Drop Deadline)'
                OR e.name REGEXP 'Last [Dd]ay to (Drop|Withdraw|Complete|Apply|Register|Add)'
                OR e.name REGEXP '(Residency|Tuition) (Deadline|Refund|Reversal)'
                OR e.name REGEXP '(Degree|Diploma) [Cc]onferral'
                OR e.name REGEXP '^Classes (Begin|Start|End)( |$)'
                OR e.name REGEXP '^(Spring|Summer|Fall|Winter) 20[0-9]{2} (Classes|Session|Term)'
                OR e.name REGEXP 'WN Reversal|WN Form'
                OR e.name LIKE '%Last Day of School%'
                OR e.name REGEXP '^Anniversary Day( - |$)'
                OR e.name LIKE '%College Closed%'
                OR e.name LIKE '%Pass/Fail Deadline%'
                OR e.name REGEXP '^(End|Beginning|Start) of (Summer|Spring|Fall|Winter) 20'
              )
        """,
    },
    {
        # Restaurant holiday menus: "Mother's Day at <Restaurant>", "Father's Day
        # Brunch", "Memorial Day Specials" — restaurant promo for a holiday menu
        # with no live performer/program. We keep if there's any programming
        # signal in the description (live music, DJ, performer). Pattern 1 only
        # catches the literal "brunch"/"happy hour" words; this catches
        # holiday-themed restaurant offerings whose name is just the holiday.
        'id': 27,
        'name': 'Restaurant holiday menu (no programming)',
        'query': r"""
            SELECT DISTINCT e.id FROM events e
            WHERE e.archived = 0 AND e.reviewed = 0
              AND (
                e.name REGEXP "[[:<:]](Mother'?s Day|Father'?s Day|Memorial Day|Valentine'?s Day|Christmas Eve|Christmas Day|New Year'?s Eve|New Year'?s Day|Easter|Thanksgiving|St\\\\. Patrick'?s Day|Independence Day|Fourth of July|4th of July)[[:>:]]"
                OR e.name REGEXP "[[:<:]](Holiday Brunch|Holiday Dinner|Holiday Menu|Holiday Special|Holiday Weekend)[[:>:]]"
              )
              AND e.name NOT REGEXP "[[:<:]](Comedy|Concert|Parade|Festival|Tournament|Watch Party|Fireworks|Screening|Show|Dance|Live Music|Mass|Service|Worship|Game|Match|Race|March|Vigil|Rally|Run|Walk|Hike|Tour)[[:>:]]"
              AND (
                e.description IS NULL
                OR e.description = ''
                OR e.description = 'No description available.'
                OR (
                  e.description NOT REGEXP '(perform|live music|live act|dj |featuring|guest |host|comedian|comedy|trivia|karaoke|workshop|class|tour|reading|talk|panel|dance|fireworks|parade|watch party|screening|game|tournament|festival|celebration|programming|special programming)'
                  AND e.description REGEXP '(prix-?fixe|brunch menu|tasting menu|holiday menu|special menu|dinner menu|seasonal menu|chef|wine pairing|three-course|delicious meal|treat your)'
                )
              )
        """,
    },
    {
        # Job postings / hiring announcements that crawled from org calendars:
        # "Community Engagement Coordinator - <Org>", "Now Hiring", "Internship
        # Opportunities". These show up because orgs put their jobs page in the
        # same CMS as their events page. The description gives them away with
        # "applications", "full-time", "salary", "candidate".
        'id': 28,
        'name': 'Job postings / hiring announcements (not events)',
        'query': r"""
            SELECT DISTINCT e.id FROM events e
            WHERE e.archived = 0 AND e.reviewed = 0
              AND (
                e.name REGEXP "(Coordinator|Manager|Specialist|Administrator) - "
                OR e.name REGEXP "(Now Hiring|We'?re Hiring|Career Opportunity|Job Opening|Open Position)"
                OR e.name REGEXP "^(Student )?Internship Opportunit(y|ies)"
                OR e.name REGEXP "^Apply Now[: ]"
              )
        """,
    },
    {
        # Calendar negative-space and operational hour changes: "No Tuesday
        # Program Tonight", "Bookstore Closing Early", "OS NYC Will Open at 1
        # PM", "Saturday Parking Pass Required". These are operational notices
        # that the venue published as calendar entries because their CMS treats
        # everything dated as an event. Pattern 2 catches outright closures
        # ("CLOSED", "Closed for Private Event"). This catches the "we'll be
        # different today" variants.
        'id': 29,
        'name': 'Calendar negative-space (cancellations, hour changes, op notices)',
        'query': r"""
            SELECT DISTINCT e.id FROM events e
            WHERE e.archived = 0 AND e.reviewed = 0
              AND (
                e.name REGEXP '^No (Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|Monday|Weekly|Evening|Morning|Afternoon) (Program|Class|Service|Meditation|Practice)'
                OR e.name REGEXP '(Closing|Closes) Early'
                OR e.name REGEXP '(Will Open|Opens|Opening) (at|Late)'
                OR e.name REGEXP 'Open at [0-9]'
                OR e.name REGEXP '(Parking Pass|Permit) Required'
                OR e.name REGEXP '^(Early|Late) (Opening|Closing|Close)'
                OR e.name REGEXP '(Closed|Open) (Today|Tomorrow|This [A-Z])'
                OR e.name LIKE '%Reservations Required%'
                OR e.name REGEXP '(Bookstore|Library|Shop|Store|Office) (Closing|Closes|Closed)'
              )
        """,
    },
    {
        # Catches events whose extracted `location_name` is a non-NYC place
        # (country, US state, major non-NYC city) AND the mapped venue doesn't
        # share that name. Surfaces cultural-tour trips (e.g. "OlioTrip Morocco"
        # at Think Olio) and off-region mis-maps (e.g. Houston museum event
        # mapped onto a NYC venue because the AI fell back to the website's
        # default location). The venue-name/address/alt-name comparison is what
        # prevents NYC venues that happen to contain a place name (Tibet House,
        # Japan Society, Washington Square Park) from being flagged.
        'id': 23,
        'name': 'Location outside NYC metro (cultural tours, off-region events)',
        'query': f"""
            SELECT DISTINCT e.id FROM events e
            LEFT JOIN locations l ON e.location_id = l.id
            WHERE e.archived = 0 AND e.reviewed = 0
              AND e.location_name REGEXP '{_NON_NYC_REGEXP}'
              AND (
                l.id IS NULL
                OR (
                  LOWER(l.name) NOT LIKE CONCAT('%', LOWER(e.location_name), '%')
                  AND LOWER(e.location_name) NOT LIKE CONCAT('%', LOWER(l.name), '%')
                  AND LOWER(l.address) NOT LIKE CONCAT('%', LOWER(e.location_name), '%')
                  AND NOT EXISTS (
                    SELECT 1 FROM location_alternate_names lan
                    WHERE lan.location_id = e.location_id
                      AND LOWER(lan.alternate_name) = LOWER(e.location_name)
                  )
                )
              )
        """,
    },
    {
        # Calls for submissions/grants, venue rentals, season passes, showtime
        # placeholders, and SEO spam. The processor's is_obvious_non_event()
        # now drops the clearest of these at extraction time; this pattern is
        # the safety net for rows that predate the filter or slip past it (e.g.
        # disguised festival pages whose title looks real but whose body is a
        # call for submissions).
        'id': 30,
        'name': 'Submissions/grants/rentals/passes (non-events)',
        'query': r"""
            SELECT DISTINCT e.id FROM events e
            WHERE e.archived = 0 AND e.reviewed = 0
              AND (
                e.name REGEXP 'Open Call|Call for (Artists?|Art|Submissions?|Entries|Proposals|Vendors?|Applicants?)'
                OR e.name REGEXP 'Submissions? (Period|Deadline|Window|Open)'
                OR e.name REGEXP '^Submissions?:'
                OR e.name REGEXP 'Accepting (Submissions|Applications|Entries|Proposals)'
                OR e.name REGEXP '^Grants?:'
                OR e.name REGEXP 'Micro[ -]?Grants?'
                OR e.name REGEXP 'Grants? (Cycle|Round|Application|Deadline)'
                OR e.name REGEXP '(Venue|Space|Room|Hall|Studio|Facility|Point|Field|Court|Table) Rental'
                OR e.name REGEXP '^Rentals?([: -]|$)'
                OR e.name REGEXP 'Available for (Booking|Rent|Hire|Private)'
                OR e.name REGEXP 'Season ?Pass|Summer ?Pass'
                OR e.name REGEXP 'Showtimes'
                OR e.name REGEXP '\\[[^]]*~[^]]*\\]'
                OR e.description LIKE '%call for submission%'
                OR e.description LIKE '%accepting submission%'
                OR e.description LIKE '%submission deadline%'
              )
        """,
    },
    {
        # Recurring restaurant dining/drink specials masquerading as events:
        # "Taco Tuesday", "Wurst Wednesday", "Bao Buns", "Jerk Fest" — weekly menu
        # promos with no live programming. The AI tags these "Weekly Special" (a
        # near-perfect junk marker), and/or describes them as "<food> specials"
        # every week. Pattern 1 only catches the literal brunch/happy-hour words;
        # Pattern 12 requires the ENTIRE tag set to be food words, which fails the
        # moment the AI also assigns Community/Tacos/etc. This catches the rest.
        # The programming guard keeps a genuinely-programmed weekly night (live
        # music, DJ, trivia) from being flagged even if mistagged "Weekly Special".
        #
        # THIS PATTERN OWNS THE WEEKDAY FOOD/DRINK-SPECIAL CLASS. An automatic
        # drop in processor.is_obvious_non_event was prototyped for it twice and
        # rejected both times (see the rejected-siblings block there): the call
        # is a venue-by-venue judgment, not a fact — "Whiskey Wednesday" (18533)
        # and "Happy Hour Friday" (139462) were reviewed and KEPT while the
        # near-identical "Taco Tuesday" (210703) and "Steak Monday" (138556)
        # were reviewed and suppressed. Keep it here, where the call stays
        # visible and reversible.
        #
        # 2026-08-17: the offer gate now also accepts "Special(s)" in the NAME.
        # The 2026-08-11 classifier found Bear Mountain Inn's (w4738) standing
        # weekly offerings — e216685 "Tuesday Burger Special", e216686 "Cellar
        # Wine Wednesdays", e216689 "Sunday Brunch at Restaurant 1915" — and the
        # scheduled task asked for exactly one thing: make sure THIS pattern
        # surfaces the family reliably, since an automatic processor rule for it
        # is a documented rejection. It did not. All three cleared the cadence
        # gate, but e216685's body is pure value-marketing with no number and no
        # literal "special" ("Big flavors, bigger value ... Available open to
        # close every Tuesday") — the word lives only in its title.
        #
        # Measured: cadence + name-"Special" + the programming veto matches 7
        # events DB-wide, ALL of them dining specials and ZERO reviewed-and-kept
        # (4 already suppressed by hand, 3 untouched). A widening keyed on
        # dining vocabulary instead ("bottles", "our legendary", "prix fixe")
        # was prototyped in the same pass and REJECTED: its one net-new match
        # was e204628 "Gumpy", a real Legendary Locals music night that the
        # programming veto failed to spare.
        #
        # 2026-08-09: the "specials" description gate was too literal to catch
        # Greenwood Park's rows ("$5 tacos and half-price margaritas ... every
        # Tuesday", "Buy any burger and get a free beer on Mondays") — they
        # state the offer without ever using the word "special", so all three
        # reached the map and were hand-suppressed at classification. Gate
        # widened to bare price-offer language, and the programming guard
        # extended in the same pass so the widening doesn't sweep in real weekly
        # nights (verified spared: "Wednesday Pinball League", "Thursgay"
        # aperitivo night, "Bingo Wednesday", "Throwback Sing-Along Bottomless
        # Brunch"). Blank-description rows like "Sunday Funday" (215105) stay
        # deliberately uncovered — "Sunday Funday" is a real party name at
        # plenty of venues and the name alone carries no signal.
        'id': 31,
        'name': 'Recurring dining/drink specials (no programming)',
        'query': r"""
            SELECT DISTINCT e.id FROM events e
            WHERE e.archived = 0 AND e.reviewed = 0
              AND (
                EXISTS (
                  SELECT 1 FROM event_tags et JOIN tags t ON et.tag_id = t.id
                  WHERE et.event_id = e.id AND t.name = 'Weekly Special'
                )
                OR (
                  e.description REGEXP '(weekly|every (mon|tues|wednes|thurs|fri|satur|sun)day|on (mon|tues|wednes|thurs|fri|satur|sun)days?)'
                  AND (
                    e.description REGEXP '([[:<:]]specials?[[:>:]]|\\$[0-9]|half[ -]?price|half[ -]?off|[0-9]+% off|[[:<:]]buy[[:>:]].{0,30}[[:<:]]get[[:>:]])'
                    OR e.name REGEXP '[[:<:]]specials?[[:>:]]'
                  )
                )
              )
              AND (
                e.description IS NULL
                OR e.description = ''
                OR e.description = 'No description available.'
                OR e.description NOT REGEXP '(perform|live music|live act|dj |featuring|guest |host|comedian|comedy|trivia|karaoke|workshop|class|tour|reading|talk|panel|dance|fireworks|parade|watch party|screening|game|tournament|festival|celebration|programming|bingo|league|sing-?along|open mic|jam|quiz|aperitivo|book club|movie|film|concert|show)'
              )
        """,
    },
    {
        # Commercial drop-in recreation — a venue simply being open for its
        # standard walk-in activity is not an event. The canonical case is a
        # bowling alley: "Open Bowling", "Open for Bowling!", "Public Bowling"
        # are just the lanes being available, not programming. (Brooklyn Bowl's
        # recurring "Open for Bowling!" even surfaces under the Music filter,
        # because the venue carries the Music tag.) Scoped tightly to bowling
        # on purpose: the same "open <activity>" phrasing is legitimate
        # programming elsewhere (library "Open Play", rec-center "Open Gym",
        # rink "Free Skate"), so do NOT generalize it here. Genuine bowling
        # events (leagues, socials, "Bowling Night", concert VIP-lane add-ons)
        # don't match.
        'id': 32,
        'name': 'Commercial drop-in bowling (venue just open)',
        'query': r"""
            SELECT DISTINCT e.id FROM events e
            WHERE e.archived = 0 AND e.reviewed = 0
              AND e.name REGEXP '[[:<:]](open([[:space:]]+for)?|public)[[:space:]]+bowling[[:>:]]'
        """,
    },
    {
        # Ticket giveaways/distributions for an event happening SOMEWHERE ELSE.
        # Three "Shakespeare in the Park … Free Tickets Giveaway" rows reached
        # the map from three Queens Public Library branches on 2026-08-05 (the
        # play is in Central Park), and were only caught downstream by the
        # event-type classifier labelling them UNKNOWN.
        #
        # This is REVIEW-ONLY on purpose — it was prototyped as an automatic
        # `is_obvious_non_event` rule and rejected. Of 6 DB-wide matches,
        # e191251 "Free Shakespeare in the Park Ticket Giveaway" at Snug Harbor
        # is a REAL attendable in-person distribution event. A promo notice and
        # a distribution event are not separable from the text, so a human
        # decides. See the rejection note in processor.is_obvious_non_event.
        'id': 33,
        'name': 'Ticket giveaway/distribution (event is elsewhere)',
        'query': r"""
            SELECT DISTINCT e.id FROM events e
            WHERE e.archived = 0 AND e.reviewed = 0
              AND e.name REGEXP '[[:<:]](free[[:space:]]+)?tickets?[[:space:]]+giveaway[[:>:]]'
        """,
    },
    {
        # Standing food/drink features branded as their own name ("Taco
        # Tuesday", "Jerk Fest"), which the processor's _MENU_SPECIAL_NAME_RE
        # misses because it expects a literal "Lunch Specials" shape.
        #
        # Also REVIEW-ONLY by measurement: gating on the dining-offer
        # description alone matched 109 events DB-wide, many of them real —
        # "Soul Supper - Live Motown & Soul Dining Experience", the immersive
        # murder mystery "Speakeasy, Die Softly", the "Month Of Love" jazz
        # series, a community potluck. A multi-course meal is a very common
        # COMPONENT of a real event, so the programming veto below is wide and
        # a human still makes the call.
        'id': 34,
        'name': 'Standing food/drink feature (no programming)',
        'query': r"""
            SELECT DISTINCT e.id FROM events e
            WHERE e.archived = 0 AND e.reviewed = 0
              AND e.description REGEXP '(all[- ]you[- ]can[- ]eat|prix[- ]?fixe|(two|three|four|multi)[- ]course|dining experience|offers a choice of)'
              AND e.description NOT REGEXP '(dj|live|perform|artist|musician|band|comedy|comedian|trivia|bingo|karaoke|screening|concert|class|workshop|tasting|tour|potluck|immersive|murder mystery|ticket|rsvp|fundrais|benefit|gala)'
              AND e.name NOT REGEXP '(party|gala|concert|show|festival|series|supper club|dinner party|celebration|new year|valentine)'
        """,
    },
    {
        # Awareness-observance titles ("National … Day/Week", "World … Day")
        # published as events when nothing is actually being held — either a
        # park conservancy inviting you to visit on your own ("Fort Tryon Park
        # is the perfect place to celebrate National Walk Your Dog Week") or a
        # bar hanging a promo on the calendar ("National Chicken Wing Day").
        # Raised by the 2026-07-16 run's Step 4, which suppressed four by hand.
        #
        # REVIEW-ONLY by measurement, and emphatically so: as an automatic
        # `is_obvious_non_event` rule the bare title shape matched 75 events
        # DB-wide and the large majority are REAL programming — World Tai Chi
        # Day at Bryant Park (free instruction), National Trails Day (a hike),
        # World Fish Migration Day (seining the Harlem River), National
        # Scrabble Day, World Circus Day. Scoping it to the Parks source that
        # raised it does not rescue it either: Fort Tryon's own "National
        # Wildflower Week" and "World Migratory Bird Day" are guided tours and
        # bird walks. Only the DESCRIPTION separates junk from real, and only
        # fuzzily, so a human decides. See the rejection note in
        # processor.is_obvious_non_event.
        #
        # The programming veto below is what keeps this queue small (9 live
        # candidates vs 13 on the bare title shape) — widen it, don't narrow it.
        'id': 35,
        'name': 'Awareness observance with no programming',
        'query': r"""
            SELECT DISTINCT e.id FROM events e
            WHERE e.archived = 0 AND e.reviewed = 0
              AND e.name REGEXP '^(national|world|international)[[:space:]].+[[:space:]](day|week|month)$'
              AND COALESCE(e.description,'') NOT REGEXP '(join|guided|instruct|demonstrat|[[:<:]]tour|[[:<:]]walk|hike|workshop|class|register|rsvp|ticket|perform|speaker|activit|station|seine|volunteer|screening|concert|party|festival)'
        """,
    },
    {
        # A bookable party PACKAGE with no rental vocabulary. e217188 "Pool
        # Birthday Party" (Commonpoint Bronx, w3027): "120 minute pool party.
        # Party host, pool space, and party decor is provided." It is a facility
        # rental, but it never says "rental", "reserve", "booking" or "room", so
        # every `is_obvious_non_event` booking arm misses it. The only tell is
        # that it is described in AMENITIES SUPPLIED terms — "X is provided",
        # a duration, a host.
        #
        # REVIEW-ONLY by measurement, and this is the disposition the scheduled
        # task asked for if precision was not compelling. Both gates are very
        # live in isolation over all 191,070 events: the party-noun name gate
        # alone matches 186 rows (10 live, 2 reviewed-and-KEPT — "Homeboy
        # Steve's Birthday Party with The Blue Chieftains", "Commonpoint Bronx
        # Back-to-School Pool Party", a free family event at the SAME venue);
        # the amenities description gate alone matches 974 rows (102 live, 94
        # reviewed-and-KEPT — every D&D one-shot "where all materials are
        # provided", every drop-in drawing session).
        #
        # Their conjunction matches exactly ONE row DB-wide (e217188 itself,
        # already suppressed), 0 reviewed-and-kept. One row of yield resting on
        # two words that carry hundreds of real events between them is the same
        # shape as the refuted "dark night" arm, so it does not go in the
        # processor — it goes here, where the call stays visible and reversible.
        'id': 36,
        'name': 'Amenities-supplied party package (facility rental)',
        'query': r"""
            SELECT DISTINCT e.id FROM events e
            WHERE e.archived = 0 AND e.reviewed = 0
              AND e.name REGEXP '[[:<:]](birthday|anniversary|graduation|corporate|kids?|children.?s?|teen|pool|private|group)[[:space:]]+part(y|ies)[[:>:]]'
              AND e.description REGEXP '((is|are)[[:space:]]+provided|we[[:space:]]+provide|party[[:space:]]+host|party[[:space:]]+decor)'
              AND e.description NOT REGEXP '(perform|live music|dj|band|comedian|comedy|screening|concert|festival|fundrais|benefit|ticket|rsvp|open to the public|all ages welcome|free)'
        """,
    },
]


def collect_candidates(cursor, pattern_filter=None):
    """Run all patterns and collect {event_id: [pattern_names]}."""
    candidates = {}  # event_id -> list of pattern dicts

    for p in PATTERNS:
        if pattern_filter is not None and p['id'] != pattern_filter:
            continue

        cursor.execute(p['query'])
        for (event_id,) in cursor.fetchall():
            if event_id not in candidates:
                candidates[event_id] = []
            candidates[event_id].append(p)

    return candidates


def print_counts(cursor, pattern_filter=None):
    """Print match counts per pattern."""
    total_ids = set()

    print(f"{'#':>3}  {'Pattern':<50} {'Matches':>7}")
    print("─" * 64)

    for p in PATTERNS:
        if pattern_filter is not None and p['id'] != pattern_filter:
            continue

        cursor.execute(p['query'])
        ids = {row[0] for row in cursor.fetchall()}
        total_ids |= ids

        count = len(ids)
        if count > 0:
            print(f"{p['id']:>3}. {p['name']:<50} {count:>7}")

    print("─" * 64)
    print(f"     {'Total unique candidates':<50} {len(total_ids):>7}")

    # Also show total unreviewed for context
    cursor.execute("SELECT COUNT(*) FROM events WHERE archived = 0 AND reviewed = 0")
    (total_unreviewed,) = cursor.fetchone()
    print(f"     {'Total unreviewed events':<50} {total_unreviewed:>7}")


def fetch_event_details(cursor, event_ids):
    """Fetch full details for a list of event IDs."""
    if not event_ids:
        return {}

    placeholders = ','.join(['%s'] * len(event_ids))
    cursor.execute(f"""
        SELECT e.id, e.name, e.location_name, LEFT(e.description, 250) as description,
               w.name as website_name,
               (SELECT GROUP_CONCAT(t.name SEPARATOR ', ')
                FROM event_tags et JOIN tags t ON et.tag_id = t.id
                WHERE et.event_id = e.id) as tags,
               (SELECT COUNT(*) FROM event_occurrences eo WHERE eo.event_id = e.id) as occ_count,
               (SELECT DATEDIFF(MAX(eo2.start_date), MIN(eo2.start_date))
                FROM event_occurrences eo2 WHERE eo2.event_id = e.id) as span_days
        FROM events e
        LEFT JOIN websites w ON e.website_id = w.id
        WHERE e.id IN ({placeholders})
    """, event_ids)

    details = {}
    for row in cursor.fetchall():
        details[row[0]] = {
            'id': row[0],
            'name': row[1],
            'location_name': row[2],
            'description': row[3],
            'website_name': row[4],
            'tags': row[5],
            'occ_count': row[6],
            'span_days': row[7],
        }
    return details


def print_candidates(candidates, details, offset, limit):
    """Print formatted candidate list."""
    # Sort: most matching patterns first, then by event name
    sorted_ids = sorted(
        candidates.keys(),
        key=lambda eid: (-len(candidates[eid]), details.get(eid, {}).get('name', ''))
    )

    page = sorted_ids[offset:offset + limit]
    total = len(sorted_ids)

    print(f"=== Review Candidates ({offset + 1}-{min(offset + len(page), total)} of {total}) ===\n")

    for i, eid in enumerate(page, start=offset + 1):
        d = details.get(eid)
        if not d:
            continue

        pattern_labels = ', '.join(f"#{p['id']} {p['name']}" for p in candidates[eid])

        print(f"[{i}] ID {d['id']}: {d['name']}")
        print(f"    Location: {d['location_name'] or '(none)'}")
        if d['website_name']:
            print(f"    Website: {d['website_name']}")
        if d['tags']:
            print(f"    Tags: {d['tags']}")
        if d['occ_count'] and d['occ_count'] > 1:
            print(f"    Occurrences: {d['occ_count']} (span: {d['span_days'] or 0} days)")
        print(f"    Patterns: {pattern_labels}")
        print(f"    Desc: {d['description']}")
        print()


def main():
    parser = argparse.ArgumentParser(description='Find events that may need suppression')
    parser.add_argument('--limit', type=int, default=50, help='Number of candidates to show (default: 50)')
    parser.add_argument('--offset', type=int, default=0, help='Skip first N candidates')
    parser.add_argument('--pattern', type=int, help='Only show matches for this pattern number (1-29)')
    parser.add_argument('--count', action='store_true', help='Just show match counts per pattern')
    args = parser.parse_args()

    conn = create_connection()
    if not conn:
        print("Failed to connect to database")
        sys.exit(1)

    cursor = conn.cursor(buffered=True)

    try:
        if args.count:
            print_counts(cursor, args.pattern)
        else:
            candidates = collect_candidates(cursor, args.pattern)
            if not candidates:
                print("No candidates found.")
                return

            event_ids = list(candidates.keys())
            details = fetch_event_details(cursor, event_ids)
            print_candidates(candidates, details, args.offset, args.limit)
    finally:
        cursor.close()
        conn.close()


if __name__ == '__main__':
    main()
