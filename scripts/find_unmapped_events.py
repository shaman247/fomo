#!/usr/bin/env python3
"""
Surface events whose location mapping likely needs human review.

Three issue classes:
- NO_LOCATION: events.location_id IS NULL
- GENERIC:    mapped to a neighborhood/borough placeholder (locations.generic_location=1)
- MISMATCHED: mapped to a specific venue, but events.location_name does not match
              the venue's name/address/alternate-names. Subset of these are real
              mis-maps (AI extracted a specific venue but the matcher fell back to
              the website's tied default); others are sublocation refs that the
              reviewer can ignore.

Re-uses pipeline/processor.py's _normalize_location_name so this script stays in
sync with the pipeline matcher (apostrophe-strip, & + → and, diacritic strip,
borough-suffix strip, etc.).

Pass --suggest-fixes to additionally re-run get_location_id() against the current
locations table and report events where the matcher would route somewhere different.

Usage:
    ./venv/bin/python scripts/find_unmapped_events.py --count
    ./venv/bin/python scripts/find_unmapped_events.py --limit 50
    ./venv/bin/python scripts/find_unmapped_events.py --issue MISMATCHED
    ./venv/bin/python scripts/find_unmapped_events.py --website "NY Tech Week"
    ./venv/bin/python scripts/find_unmapped_events.py --suggest-fixes --limit 100
"""

import argparse
import sys
from collections import Counter, defaultdict

sys.path.insert(0, 'pipeline')
from db import create_connection
from processor import _normalize_location_name, build_locations_map, get_location_id


# Location names that are correctly mapped via website-default fallback or are
# generic enough that mismatch is expected. Lowercase comparison.
SKIP_LOCATION_NAMES = {
    # vague/virtual placeholders
    'online', 'virtual', 'online event', 'virtual event', 'zoom', 'webex',
    'online via zoom', 'livestream', 'live stream', 'tba', 'tbd', 'n/a',
    'hybrid', 'in person', 'in-person', 'not specified', 'location not specified yet',
    'no location provided', 'off campus', 'various', 'not provided',
    'zoom/online', 'live on zoom', 'via webex platform', 'virtual/online workshop',
    'off-site', 'main stage', 'open streets program', 'online or on-site',
    'virtual on zoom', 'zoom virtual meeting', 'zoom (from your home)',
    'varies', 'varies by session', 'see the flyer', 'please see the flyer.',
    'nyc (to be confirmed)', 'hidden until attendee is approved',
    'location visible to members', 'location to be revealed',
    'location to be determined', 'details tba', 'around the boroughs',
    'citywide', 'teams', 'nyc multiple locations', 'various nyc locations',
    'various historic sites', 'new york (exact location unspecified)',
    'remote', 'google meet', 'google hangouts', 'microsoft teams', 'your phone',
    'online streaming', 'online through zoom', 'online live', 'online streaming, new york',
    'various locations', 'various sites', 'multiple locations', 'virtual/online events',
    # contentless labels emitted verbatim by a source instead of a venue
    'unknown', 'no location provided.',
    # library-feed placeholders: the branch/venue is named in the description or
    # event title, and the reviewer has already pinned each event individually.
    # The literal string carries no venue info, so a mismatch against it is noise.
    'bookmobile', 'offsite- please see description',
    'offsite (venue named in description)',
    'other offsite location [1]', 'ys dept', 'offsite 2',
    'outdoors - open spaces, parks & streets', 'outdoors - open spaces, parks& streets',
    'various nyc venues', 'the pier',
    'secret brooklyn location', 'tba - open air', 'details tba.', 'please see the flyer',
    # theater chain brand names (events correctly mapped to specific theaters)
    'amc theatres', 'amc theater', 'amc theatre', 'regal cinemas', 'regal cinema',
    # aggregator/host ORG names that the source emits as location_name for every
    # listing — the real venue arrives from the listing body, so a "mismatch"
    # against it is meaningless (NYC Service, New York Cares, Hudson County…).
    'nyc service', 'new york cares', 'nyc parks greenthumb', 'bowery boys walks',
    'hudson county, nj, hudson county, new jersey',
    'black health matters', 'harlem week inc.', 'harlem week inc',
    'monmouth county park system', 'union county park', 'union county parks',
    # chain "pick a branch" strings — the real branch comes from the listing URL
    'total wine & more | multiple locations, nearby',
    # remote venue/event named only because the mapped venue is BROADCASTING or
    # performing AT it (cinema simulcasts, marathon-route performances)
    'xfinity mobile arena', 'nyc marathon', 'tcs new york city marathon',
    # generic sublocation labels (room/area within mapped venue)
    'the rooftop', 'full venue', 'poolside', 'main hall', 'main room',
    'play area', 'playground', 'multi-use room', 'parking lot',
    'tennis courts', 'basketball courts', 'turf field', 'athletic field',
    'main pool', 'our tent',
    'concert hall', 'screen 1', 'community board office - conference room',
    # aggregated nav labels a site emits instead of a venue
    'online talks webinars performances',
    # vague geo labels
    'brooklyn, new york', 'midtown, new york', 'manhattan (exact location unspecified)',
    'multiple venues', 'kids', 'offsite', 'no location', 'varies - see monthly newsletter',
    # bare city labels — carry no venue information, so a "mismatch" against the
    # pinned venue is meaningless noise (walking-tour sites emit these for every event).
    'new york', 'new york city', 'nyc', 'new york, ny', 'new york city (exact location unspecified)',
    'manhattan', 'brooklyn', 'queens', 'bronx', 'staten island',
    'east side, new york, ny', 'west side, new york, ny',
    # bare avenue/street names — the mapped venue is the market/plaza ON that
    # street, so the "mismatch" is just the street name minus the venue name.
    '4th avenue', 'atlantic avenue', 'broad street',
    # room/area descriptors, tabling spots, and one-off series names that sit
    # inside the mapped venue
    'cafe area', 'deadass', 'manhattan venue',
    'montefiore organ/tissue donation', 'montefiore organ/ tissue donation',
    # neighborhood labels that are NOT generic_location rows (so the placeholder
    # check below can't catch them) but still carry no venue information
    'red hook',
    # host ORG emitted as the venue by its own site
    'community-word project',
    # chain branch names — the real branch comes from the listing body/URL.
    # Skip-listing (rather than aliasing) is deliberate: an alt would silently
    # hijack every other branch of the chain to this one venue.
    'td bank',
    # walking-tour / advocacy ORGS that emit their own name as the venue. Each
    # event is already pinned to the neighborhood the tour or action covers.
    'mas tours', 'mas nyc', 'dancing classrooms', 'hands off nyc',
    'nyc bike + brew', 'nyc bike and brew',
    # extraction placeholders
    'not specified in provided content',
    'new york city metro area (exact location unspecified)',
    'nyc (venue tba)', 'location in manhattan to be announced.',
    # citywide multi-venue promotions — no single venue exists
    'various nyc restaurants',
    # unhyphenated neighborhood spellings that are not generic_location rows
    'bedstuy',
    # nyc.gov street-event permits: location_name is the parade / street-fair
    # ROUTE, not a venue. The event is pinned to the right neighborhood generic.
    '11 madison avenue', '118 street', '37 avenue', '5 avenue',
    'crossbay boulevard', 'hillside avenue', 'st john place',
    # deliberately-unnamed / address-withheld venues (Partiful DIY shows, private
    # backyard parties, Meetup series that email the meeting spot to registrants).
    # The borough/neighborhood generic is the best mapping that will ever exist.
    'brooklyn diy venue', 'nells, brooklyn', '4106 2nd ave', 'dear summer bbq',
    'woodbury/plainview area park', 'sent to rsvps, new york',
    'meatpacking district', 'harlem multiple sites outdoor',
    # more org / operator / installation names emitted as the venue, already
    # pinned to the right place
    'calpulli mexican dance company', 'untapped new york',
    'fort defiance sidewalk galleries', 'queens waterfront', 'new york harbor',
    # more generic sub-facility labels (NYC Parks emits these for many parks;
    # the real park is named in the event title, resolved per event)
    'lawn', 'handball court',
    # room descriptor inside an already-mapped venue
    'community center, room 31',
    # chain branch with no branch identifier — BPL runs this series at several
    # stores, so the string must be re-resolved from the page each time
    'starbucks',
}

# Websites whose feed emits the HOST/PARTNER ORG as `location_name` for every
# listing, by design — the real venue lives in a different field. New York Cares
# is the clearest case: its session API carries the venue in `Location_Name__tl`
# while `Community_Partner_Name__tl` (the partner charity: KEEN New York, City
# Harvest, Achilles International, BloomAgainBklyn…) is what gets extracted. A
# MISMATCHED verdict against a partner name is meaningless, and the partner list
# is open-ended, so skip the class for these sources rather than enumerating
# every charity in SKIP_LOCATION_NAMES.
SKIP_MISMATCH_WEBSITES = {
    'New York Cares',
    'NYC Service',
}

# Street-intersection patterns: outdoor markets / waste drop-offs / flea markets
# whose location_name names the street but whose mapping to a specific venue is
# correct.
SKIP_LOCATION_NAME_SUBSTRINGS = (' between ', ' btwn ')

# Prefixes for "location withheld until later" labels. Resident Advisor in
# particular emits a long tail of unique strings ('TBA - Secret Bedstuy Loft',
# 'TBA - WAREHOUSE TBA', 'TBA - Brooklyn Open Air', …) that can never resolve to
# a venue; matching the prefix keeps them out of the queue without listing each.
SKIP_LOCATION_NAME_PREFIXES = (
    'tba -', 'tba-', 'tba —', 'tba, ', 'location tba', 'location to be announced',
    'location announced', 'location annouced', 'venue tba', 'venue not specified',
    'private residence', 'secret location',
    # 'Online, 7–9 PM' and friends — an online label with a time tacked on
    'online,', 'online -', 'online (', 'virtual,', 'virtual -',
)

ISSUE_ORDER = ('NO_LOCATION', 'GENERIC', 'MISMATCHED')


def load_data(cursor, website_filter=None):
    """One pass through events + locations + alts + websites."""
    where = "e.suppressed = 0 AND e.archived = 0"
    params = []
    if website_filter:
        where += " AND w.name = %s"
        params.append(website_filter)

    cursor.execute(f"""
        SELECT e.id, e.name, e.location_id, e.location_name, e.sublocation,
               e.website_id, w.name AS website_name,
               l.name AS venue_name, l.address AS venue_address,
               l.generic_location AS venue_generic
        FROM events e
        LEFT JOIN locations l ON e.location_id = l.id
        LEFT JOIN websites w ON e.website_id = w.id
        WHERE {where}
    """, params)
    events = cursor.fetchall()

    cursor.execute("""
        SELECT location_id, alternate_name, website_id
        FROM location_alternate_names
    """)
    alts_by_loc = defaultdict(list)
    for row in cursor.fetchall():
        alts_by_loc[row['location_id']].append((row['alternate_name'], row['website_id']))

    # Cache the placeholder names so classify() can recognise a location_name
    # that is merely a neighborhood/borough label. Populated here (rather than
    # returned) so the (events, alts_by_loc) contract stays intact for callers.
    cursor.execute("SELECT name FROM locations WHERE generic_location = 1")
    _GENERIC_NAMES.clear()
    _GENERIC_NAMES.update(
        n for n in (_normalize_location_name(r['name'] or '') for r in cursor.fetchall()) if n
    )

    return events, alts_by_loc


# Normalized names of every generic_location=1 row; filled by load_data().
_GENERIC_NAMES = set()


def classify(event, alts_by_loc, generic_names=None):
    """Return one of NO_LOCATION / GENERIC / MISMATCHED / None.

    `generic_names` is the set of normalized names of every generic_location=1
    row. A location_name that merely repeats a neighborhood/borough placeholder
    ('Greenpoint', 'Harlem', 'Red Hook', 'Times Square') carries no venue
    information, so it can never contradict the specific venue it is pinned to.
    """
    if event['location_id'] is None:
        return 'NO_LOCATION'

    if event['venue_generic']:
        return 'GENERIC'

    location_name = (event['location_name'] or '').strip()
    if len(location_name) < 3:
        return None

    if (event['website_name'] or '') in SKIP_MISMATCH_WEBSITES:
        return None

    ln_lower = location_name.lower()
    if ln_lower in SKIP_LOCATION_NAMES:
        return None
    if _normalize_location_name(location_name) in (
            _GENERIC_NAMES if generic_names is None else generic_names):
        return None
    if any(s in ln_lower for s in SKIP_LOCATION_NAME_SUBSTRINGS):
        return None
    if ln_lower.startswith(SKIP_LOCATION_NAME_PREFIXES):
        return None

    n_loc = _normalize_location_name(location_name)
    n_name = _normalize_location_name(event['venue_name'] or '')
    n_addr = _normalize_location_name(event['venue_address'] or '')
    if not n_loc or not n_name:
        return None

    # Mapping is consistent if normalized location_name and venue name/address
    # are substrings of each other (in either direction).
    if n_loc in n_name or n_name in n_loc:
        return None
    if n_loc in n_addr:
        return None

    # Check alt names (global + website-scoped to this event)
    website_id = event['website_id']
    for alt_name, alt_wid in alts_by_loc.get(event['location_id'], ()):
        if alt_wid is not None and alt_wid != website_id:
            continue
        n_alt = _normalize_location_name(alt_name)
        if not n_alt:
            continue
        if n_alt in n_loc or n_loc in n_alt:
            return None

    return 'MISMATCHED'


def maybe_suggest_fix(event, locations_map, locations_by_id):
    """Re-run the matcher against current data. Returns dict or None."""
    result = get_location_id(
        event['location_name'] or '',
        event['sublocation'] or '',
        event['website_name'] or '',
        event['name'] or '',
        locations_map,
        website_id=event['website_id'],
    )
    if not result:
        return None
    suggested_id = result.get('id')
    if suggested_id == event['location_id']:
        return None
    suggested = locations_by_id.get(suggested_id)
    if not suggested:
        return None
    return {'id': suggested_id, 'name': suggested.get('name'),
            'address': suggested.get('address')}


def print_counts(events, alts_by_loc):
    counts = Counter()
    for e in events:
        issue = classify(e, alts_by_loc)
        if issue:
            counts[issue] += 1

    print(f"{'Issue':<14}{'Count':>8}")
    print('─' * 22)
    for issue in ISSUE_ORDER:
        if counts[issue]:
            print(f"{issue:<14}{counts[issue]:>8}")
    print('─' * 22)
    print(f"{'Total':<14}{sum(counts.values()):>8}")


def print_candidates(events, alts_by_loc, *, issue_filter=None, limit=50, offset=0,
                     suggest_fixes=False, locations_map=None, locations_by_id=None):
    flagged = []
    for e in events:
        issue = classify(e, alts_by_loc)
        if not issue:
            continue
        if issue_filter and issue != issue_filter:
            continue
        flagged.append((issue, e))

    # Order: issue (NO_LOCATION → GENERIC → MISMATCHED) → website → id
    issue_rank = {k: i for i, k in enumerate(ISSUE_ORDER)}
    flagged.sort(key=lambda x: (issue_rank[x[0]], x[1]['website_name'] or '', x[1]['id']))

    page = flagged[offset:offset + limit]
    total = len(flagged)
    print(f"=== Unmapped Candidates ({offset + 1}-{min(offset + len(page), total)} of {total}) ===\n")

    for i, (issue, e) in enumerate(page, start=offset + 1):
        venue = e['venue_name'] if e['location_id'] else '—'
        venue_id = e['location_id'] or '—'
        print(f"[{i}] {issue}  event #{e['id']}: {e['name']}")
        print(f"    location_name: {e['location_name']!r}")
        print(f"    mapped venue:  #{venue_id} {venue!r}" + (
            f" @ {e['venue_address']}" if e['venue_address'] else ""))
        if e['website_name']:
            print(f"    website:       {e['website_name']!r}")
        if suggest_fixes and locations_map:
            fix = maybe_suggest_fix(e, locations_map, locations_by_id)
            if fix:
                print(f"    → matcher would now route to #{fix['id']} {fix['name']!r}"
                      + (f" @ {fix['address']}" if fix['address'] else ""))
        print()


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--count', action='store_true', help='Just print issue counts')
    parser.add_argument('--limit', type=int, default=50, help='Max candidates to print (default 50)')
    parser.add_argument('--offset', type=int, default=0, help='Skip first N candidates (pagination)')
    parser.add_argument('--issue', choices=ISSUE_ORDER,
                        help='Only show events with this issue class')
    parser.add_argument('--website', help='Only show events from this website (exact name)')
    parser.add_argument('--suggest-fixes', action='store_true',
                        help='Re-run get_location_id and report when the matcher would route differently')
    args = parser.parse_args()

    conn = create_connection()
    if not conn:
        sys.exit('Failed to connect to database')
    cur = conn.cursor(dictionary=True)

    try:
        events, alts_by_loc = load_data(cur, website_filter=args.website)

        if args.count:
            print_counts(events, alts_by_loc)
            return

        locations_map = None
        locations_by_id = None
        if args.suggest_fixes:
            # build_locations_map() uses tuple cursor under the hood
            tuple_cur = conn.cursor()
            locations_map = build_locations_map(tuple_cur)
            tuple_cur.close()
            cur.execute("SELECT id, name, address FROM locations")
            locations_by_id = {r['id']: r for r in cur.fetchall()}

        print_candidates(
            events, alts_by_loc,
            issue_filter=args.issue,
            limit=args.limit,
            offset=args.offset,
            suggest_fixes=args.suggest_fixes,
            locations_map=locations_map,
            locations_by_id=locations_by_id,
        )
    finally:
        cur.close()
        conn.close()


if __name__ == '__main__':
    main()
