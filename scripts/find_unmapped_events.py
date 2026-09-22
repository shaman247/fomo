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
import re
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
    'zoom/online', 'live on zoom', 'via webex platform', 'virtual/online workshop', 'virtual offering',
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
    'play area', 'playground', 'playground area', 'open area',
    'multi-purpose play area', 'multi-use room', 'parking lot',
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
    '4th avenue', 'atlantic avenue', 'broad street', 'lenox avenue',
    # room/area descriptors, tabling spots, and one-off series names that sit
    # inside the mapped venue
    'cafe area', 'deadass', 'manhattan venue',
    # host ORG's own site emitting a catch-all city label for a multi-studio series
    'manhattan (various)',
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
    # membership clubs / hobby societies with no premises of their own. Each
    # posts from its own site, so the club name arrives as location_name on
    # every listing while the actual address is emailed after RSVP.
    'tribeca club', 'lower east side cactus & succulent society',
    # bare hotel brand — a 'Hilton' alias would be a catch-all across every
    # Hilton property, and the real one is only ever named in the listing body.
    'hilton',
    # contentless venue labels: too generic to ever resolve, and the sources
    # that emit them (Partiful DIY shows, queer party series) withhold the
    # address until RSVP.
    'the basement', 'the location will be revealed on the event date.',
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
    '10 avenue', '11 madison avenue', '118 street', '37 avenue', '5 avenue',
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
    # "we haven't picked/published the room yet" labels. Each event is already
    # pinned to the host org's own venue (or its neighborhood), which is the best
    # mapping that will ever exist for them.
    'no location specified', 'event location coming soon',
    # multi-venue series run by one operator out of one studio
    'manhattan and brooklyn venues',
    # 2026-09-07 unmapped sweep: contentless labels whose events are already
    # pinned to the right venue. Each was verified against the live page before
    # being added here, so a "mismatch" against the string is pure noise.
    'various/artists', 'to be emailed prior to concert.', 'west lobby', 'window',
    'off site', 'off-site location', 'room 674', 'location not specified',
    # street with no number: nine distinct Bogart St venues in the DB, so the
    # bare street can never resolve.
    'bogart st',
    # address deliberately withheld by the organizer; the neighborhood/host pin
    # is the best mapping that will ever exist.
    'soho sukkah', 'connors elementary school', 'throughout the rivertowns',
    # 2026-09-09 unmapped sweep. Each string was verified against the live source page
    # before being listed: the event is already pinned as well as it ever can be, and the
    # string names no resolvable venue (virtual platform, withheld/private address, an
    # org/agency label, a multi-block street-fair route, or a bare neighborhood/ZIP).
    'online goto webinar', 'online meeting', 'teams (virtual)', 'zoom webinar',
    'links will be provided after registration', 'virtual/online events',
    'a secret private social club', "ami's", 'flower district', 'tbd, brooklyn',
    'uptown + the bronx (exact location tba)', 'multiple locations around brooklyn',
    'manhattan & brooklyn', 'manhattan to liberty island', 'check site for details.',
    'third avenue', '129 atlantic avenue', 'corner of 6th street and 8th avenue',
    'cadman plaza in brooklyn, across the brooklyn bridge, concluding at foley square, manhattan',
    'bensonhurst', 'yorkville', 'bronx, ny 10467', 'new york, ny 10007',
    # ORG/agency names emitted as the venue by their own feed. Each rovers between venues,
    # so an alt name would mis-pin every future listing.
    'russian american cultural center', 'union county park system',
    # 2026-09-11 unmapped sweep. Each string was researched against the live source page
    # before being listed; none names a venue that can ever resolve, and the event is
    # already pinned as well as it ever will be.
    #   org / program name emitted as the venue
    'spike polite radio show', 'amadou ly foundation', 'bronx poetry house',
    #   organizer withholds the address until signup/RSVP
    'tbd / sent to registrants', 'location tbu', 'brooklyn industrial space',
    'williamsburg rooftop', 'brooklyn, ny',
    #   private residences (Partiful house shows) — must never get a locations row
    "1120 st. john's place", '413 e 84th st apt 1 (buzz bartos, kitchin, or imamura)',
    #   bare ZIP with the real address emailed after signup (NYC Service)
    'new york, ny 10037', 'queens, ny 11377',
    #   sub-facility label inside the mapped park, and in-park route endpoints
    'ballfield 11', 'dinosaur playground to ellington in the park, new york',
    #   street the PuppetMobile performs on; the event is pinned to the neighborhood
    '5th avenue',
    # 2026-09-13 unmapped sweep. Each string was researched against the live source page
    # before being listed; the event is already pinned to the right venue and the string
    # names no venue that can ever resolve.
    #   festival / fundraiser / program names emitted as the venue by their own site
    'bicycle film festival', 'brooklyn heights designer showhouse',
    'independent 20th century', 'lit society', 'nightboat books',
    'east hampton historical society', 'puppetmobile',
    #   agency / civic-body labels that are not the meeting venue
    'nyc department of records and information services (doris)',
    'brooklyn community board 2',
    #   contentless descriptors of the already-pinned venue
    'areas surrounding the museum of natural history', 'private historic home',
    'offsite location', 'the great lawn',
    # 2026-09-14 unmapped sweep. Every one of these was verified against the live
    # source page: the event's current pin is right and the extracted string is
    # either a person's name or a DIFFERENT real venue, so aliasing it would build
    # a catch-all onto the wrong place.
    #   pools.events emits the SPEAKER/HOST name as location_name when the listing
    #   has no venue field. Open-ended pattern — extend as new ones surface.
    'eric athas', 'thomas woodward davis',
    #   cross-entity contamination: each names a real venue that is NOT this event's
    #   (Joe Holder's Seaport pop-up; The Local Eatery & Craft Beer in Forest Hills)
    'the clubhouse by joe holder', 'the local eatery & craft beer',
    #   neighborhood / transit landmark, not the venue
    'prospect park south', 'ossining station',
    # 2026-09-15 unmapped sweep. Each string was researched against the live source page
    # before being listed; the event is now pinned as well as it ever can be and the
    # string names no venue that will ever resolve.
    #   organizer withholds the venue until a newsletter / weekly IG post goes out
    'off-site restaurant — announced in organizer newsletter',
    'location varies — see @badassladygangnyc',
    #   citywide route, not a venue (TCS NYC Marathon)
    'locations citywide; see links for details',
    #   sub-facility label inside the already-mapped park
    'softball field',
    #   mixed-use Bay Ridge building with no host venue — PEU sidewalk canvassing;
    #   the Arab American Association is at 6803 5th Ave, NOT 7111 (verified 2026-09-15)
    '7111 5th ave',
    #   party series / private spaces whose address is RSVP-gated, so no venue exists:
    #   'Hide and Seek' is a queer party series (Partiful's own venue field says "ETET"),
    #   'Apt.11R' is a Groupmuse private residence, 'The Fairy Backyard' a private yard
    'hide and seek', 'apt.11r', 'the fairy backyard',
    # 2026-09-17 unmapped sweep. Researched against the live source page; each names
    # something that can never resolve to a venue, and the event is already pinned as
    # well as it ever can be.
    #   broadcaster / tour-operator brands emitted as the venue
    'radio garden state', 'central park guided tours | wander nyc',
    #   contentless NYC Parks shelter label — Shorewalkers meet at a different park
    #   pavilion every week, so even a website-scoped alias would mis-pin them
    'nyc park pavilion',
    # 2026-09-19 unmapped/generic sweep (/fix-unmapped-events). Every string below was reviewed
    # against the event it came from: the event is ALREADY pinned to the right row and the string
    # names something with no independent identity of its own — a sub-facility, lawn, playground,
    # terrace, entrance, plaza or picnic area inside the pinned park; a street/intersection meeting
    # point for a tour or run club; a bare neighborhood/municipality label; the host org's or the
    # event series' own name; or a festival stage on the pinned plaza. Named destinations that DO
    # deserve their own row (carousels, piers, visitor centers, historic houses) were created or
    # matched instead and are deliberately absent from this list.
    #
    # Second pass, same sweep: strings researched venue-by-venue against the live source page.
    # Each is either a sub-space whose parent row is the right pin, a platform/placeholder
    # pseudo-venue, an org name on a virtual event, a bare street/borough label, or an
    # administrative label on an item that turned out not to be an event at all.
    '1619 3rd ave parking', '50 haven ave., new york, ny 10032',
     'arverne east nature preserve welcome center', 'bayshore waterfront park activity center',
     'beacon institute dock', 'boe borough offices', 'brooklyn, brooklyn, ny, usa',
     'clinton avenue', 'conference house visitors center', 'dust bowl field',
     'freneau woods park visitor center', 'hartsdale', 'l train station',
     'le carrousel in bryant park', 'liberty street', 'little hell gate salt marsh',
     'main stage on borough hall plaza', 'mccarren park greenmarket', 'monolith studio',
    # Correctly pinned, but the pinned row is a generic_location park/preserve, so the GENERIC
    # branch fires before the alias check can clear them. Each already carries the matching
    # alternate name on the right row; the string itself names no separately-mappable venue.
    'the art gallery at rockefeller state park', 'bayswater city park', '67 mulberry st',
    'popps memorial park',
     'poll sites citywide', 'queens, ny', 'restaurant of the week', 'samaritans of new york',
     'seaglass carousel',
     'the amph, pier 55 at hudson river park, hudson river greenway, new york',
     'the battery - seaglass carousel',
     'the glade, pier55 in hudson river park west 13th street, new york', 'the hills',
     'the play ground',
    '1 plaza street', '1095 6th ave', '1408 saint nicholas avenue, new york, ny, 10033',
     '200 nevada avenue', '207 water street, new york, ny, 10038', '34th street',
     '72nd street and broadway', 'appalachian trail - harriman state park',
     'astoria park track', 'beach 59th street playground, rockaway beach and boardwalk',
     'bed-stuy', 'bella abzug park fountains', 'bethpage polo in the park',
     'broadway and dongan place entrance, fort tryon park', 'broadway boulevard',
     'broadway/arden entrance, new york city, new york, united states',
     'brookville playground (in brookville park), queens', 'brower park lawn',
     'bryant park (meet at nyc public library front steps by the lions)', 'carnegie hall area',
     'cascade falls palisades', 'catbird playground', 'center stage (columbus park)',
     'central park dene area', 'centre street & chambers street, new york, ny, 10013',
     'cloisters lawn, fort tryon park', 'conservatory garden - italian garden',
     'council district 45', 'creekside - under the k bridge',
     'discovery playground, discovery playground', 'dongan lawn', 'dumbo-wide', 'dyckman',
     'edison (exact location unspecified)', 'end of gerritsen avenue',
     'entrance - center boulevard and borden avenue',
     'entrance - continental place and grandview avenue',
     'entrance - lafayette avenue and morrison avenue in soundview park',
     'fort greene park, starting at the monument', 'fountain in city hall park',
     'fountain of the planet', 'fountain terrace', 'gapstow bridge', 'garibaldi plaza',
     'garibaldi plaza (in washington square park), manhattan', 'gowanus canal',
     'grand army plaza, flatbush ave, brooklyn, ny, us',
     'green space near the grand army plaza entrance, prospect park',
     'grove street and sheridan square', 'hilltop picnic area, 11 wards meadow loop, new york',
     'historic cottage, fort tryon park', 'jacob mould fountain',
     'juniper valley park tennis courts',
     'lawn near 79th street entrance (in shore park and parkway)',
     'leif ericson park and square', 'little west street @2nd place',
     'located at the intersection of canal street, east broadway, and essex street.',
     'locomotive lawn', 'lower manhattan + midtown (exact location tba)',
     'madison avenue and east 78th street, southwest corner', 'manhattan bridge / chinatown',
     'mccarren park, new york, ny, us', 'met’s stadium/willet’s point subway stop, queens, ny',
     'mulberry street & worth st, new york, ny, 10013', 'multipurpose room in betsy head park',
     'myrtle avenue and park lane south in forest park', 'new york (irl)',
     'north stage, cadman plaza east', 'overpeck county park-ridgefield park area',
     'parkside + ocean avenue entrance', 'pelham bay park - picnic area, the bronx',
     'pelham bay park and orchard beach: orchard beach boardwalk bronx',
     'pier at w 125th & marginal streets', 'plainsboro (exact location unspecified)',
     'ploutz road trailhead parking', 'prospect park yoga', 'riverbank (camel) playground',
     'riverbank park entrance', 'riverside park traveling rings',
     'riverside park: esplanade - 72nd st-83rd st-rsp manhattan',
     'rockefeller park children’s garden', 'soldiers and sailors memorial arch',
     'south of hudson river greenway', 'south williamsburg', "st. mary's annual 5k start",
     'sunset park center lawn', 'the east river esplanade at 34th street', 'the ramble',
     'thomas paine park (foley square): fountain plaza manhattan', 'ues', 'upper terrace',
     'upper terrace in bryant park', 'upper west side (council district 6; see event flyer)',
     'vcpa learning garden', 'w 125th & marginal streets', 'w 143rd street & riverside drive',
     'w 145th street lawn', 'w 153rd st and riverside drive', 'w 68th street & riverside blvd',
     'w 72nd street & riverside drive', 'w. 145th st. / riverside drive',
     'wagner pavilion classroom', 'walkway over the hudson state historic park',
     'warner leroy place', 'west 84th street & columbus avenue', 'west harlem',
    # 2026-09-20 unmapped/generic sweep (/fix-unmapped-events). Each string below was researched
    # against the live source page; the event is already pinned to the right row and the string
    # names nothing separately mappable.
    #   Brooklyn Book Festival Children's Day stages. Columbus Park (row 9425) IS the plaza in
    #   front of Brooklyn Borough Hall — NYC Parks puts Columbus Park (B113C) at "Adam St., Court
    #   St., Cadman Plaza West bet. Johnson St. and Fulton St." and the Borough Hall Greenmarket
    #   is published as being "in Columbus Park". Each stage already carries a website-scoped alt
    #   on 9425; only the generic_location=1 flag on that row keeps them in the queue. Indoor
    #   Borough Hall rooms are correctly pinned to 136 instead.
    'picture book stage, brooklyn borough hall plaza',
    'makers and creators area, brooklyn borough plaza',
    'young readers stage, brooklyn borough hall plaza',
    #   Firm/employer name emitted as the venue by an Eventbrite listing. 300 Madison Ave is PwC's
    #   New York office and the pin is right, but PwC also has Stamford / Florham Park / Melville
    #   offices inside our coverage, so a global alias would be a catch-all onto the wrong one.
    'pricewaterhousecoopers llp',
    #   Named sub-place / meeting point inside the row it is already pinned to. Each row carries a
    #   matching alternate name now; they stay in the queue only because the pinned row is
    #   generic_location=1 (park / boardwalk / neighborhood), which fires before the alias check.
    #     - Wagner Park Pavilion: the pavilion inside Wagner Park (5021)
    #     - National Blvd Boardwalk Entrance: 8032 Long Beach Boardwalk is ALREADY pinned at this
    #       entrance (identical coords to the Allegria Hotel at 80 W Broadway), so an entrance row
    #       would have been an exact-duplicate-coordinate pin
    #     - Grand Concourse & East 153rd Street: inside Franz Sigel Park's own address range (324)
    #     - 111th St & Adam Clayton Powell Jr Blvd: African American Day Parade step-off, pinned to
    #       Harlem (2698), which is how two other sources pin the same parade
    'wagner park pavilion', 'national blvd boardwalk entrance',
    'grand concourse & east 153rd street',
    '111th street and adam clayton powell, jr. blvd',
    # 2026-09-21 unmapped/generic sweep (/fix-unmapped-events). Verified against the live
    # source page: the event is already pinned to the right row and the string names the
    # umbrella INSTITUTION or the HOST ORG, not the building.
    #   SVA is a multi-building Manhattan campus and sva.edu emits the school name as the
    #   venue for every listing while the actual building lives in `sublocation`
    #   ('Room 101C' -> 133/141 W 21st St = SVA Flatiron Gallery; '1st floor' -> 214 E 21st
    #   St = SVA MFA Photography). Matching the bare school name would pull all three
    #   buildings onto 209 E 23rd St, which is only the mailing address in the page footer.
    'school of visual arts',
    #   Speed-dating promoter that emits its own brand as the venue on listings with no
    #   venue field; the event is pinned to the Manhattan generic, which is the best
    #   mapping that will ever exist for an apply-to-attend event with a withheld address.
    'plentyofparties',
    #   The FESTIVAL's own name, emitted as location_name for all 86 screenings because the
    #   Eventive `?_escaped_fragment_=` schedule renders title + time and no venue. The real
    #   venue per screening comes from the Eventive JSON API (see websites.notes for w2450);
    #   every event is now pinned to its own venue, so the string names nothing mappable.
    'woodstock film festival',
    #   Production company (A Bright Room Called Day runs in a private Crown Heights
    #   townhouse whose address is emailed to ticket holders) — never gets a locations row.
    '697 productions',
    #   pools.events listing whose venue line is literally "RSVP for Addy"; the organizer
    #   withholds the address, so the Manhattan generic is the best pin that will ever exist.
    'moonlight palace',
    #   Citi Bike dock used as the ride's meeting corner; pinned to the Harlem generic.
    'citi bike dock, saint nicholas avenue & west 126th street',
    # 2026-09-22 unmapped/generic sweep (/fix-unmapped-events). Every event below was researched
    # against its own source page and is now pinned to the right row; the string itself names
    # something that can never resolve to that row, so a "mismatch" against it is noise.
    #   Brooklyn CB6 (w415) emits the HOST ORG as location_name and the real venue lives only in
    #   the linked Eventbrite listing. GCC sets a DIFFERENT correct venue per stewardship series —
    #   these five events land on four venues (Salt Lot, Dredgers boathouse, the GCC office at the
    #   Old American Can Factory, Lowlands Nursery) — so the org name must never become an alias.
    'gowanus canal conservancy',
    #   The corridor is the WORK site; the Eventbrite meeting point is the Salt Lot two blocks
    #   away, so aliasing the corridor onto the Salt Lot would be an alt-on-the-wrong-row hijack.
    '6th street green corridor',
    #   The forum is ABOUT the Brooklyn Marine Terminal; the CB6 page says "More details to come"
    #   and names no venue, so the event is pinned to the Red Hook generic. A "Brooklyn Marine
    #   Terminal" row would be a wrong pin for the forum and a large-industrial-site catch-all.
    'brooklyn marine terminal',
    #   A sitting Assemblymember's name, emitted as the venue for a pop-up clinic she co-hosts.
    #   The RSVP form names the real venue (NYU Langone Health-Cobble Hill); her district office
    #   is NOT it, and she holds pop-ups at many venues, so this must never become an alias.
    'assemblymember jo anne simon',
    #   A lawn inside Highland Park (385), which already carries the matching alternate name.
    #   It stays in the queue only because 385 is generic_location=1 and the GENERIC branch fires
    #   before the alias check.
    'upper highland lawn',
    #   NYC Parks' park-association metadata, not the meeting point. The page's own
    #   "Meeting Location: E 17th Street and Albemarle Road", the title ("Prospect Park South")
    #   and the funder (CM Rita Joseph, District 40) all place this in Prospect Park South /
    #   Ditmas Park, ~1.5 mi from the real Mount Prospect Park at Eastern Pkwy/Underhill Ave.
    'mount prospect park',
    #   The FESTIVAL's own name. Cinema Tropical's page names no venue at all; the event is pinned
    #   at the institution level to Film at Lincoln Center, which presents NYFF. A bare alias would
    #   hijack every future NYFF screening from every source onto one theater.
    'new york film festival',
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
    # Emits its own shop name as location_name for group rides that actually start at
    # Ronkonkoma LIRR. Handled here rather than in SKIP_LOCATION_NAMES because
    # "Principles GI Coffee House" is a legitimate venue (location 2214) for other sources.
    'Principles GI Coffee House',
}

# Street-intersection patterns: outdoor markets / waste drop-offs / flea markets
# whose location_name names the street but whose mapping to a specific venue is
# correct.
SKIP_LOCATION_NAME_SUBSTRINGS = (
    ' between ', ' btwn ',
    # "<neighborhood> location provided upon RSVP" / "address provided upon
    # registration" — the org withholds the room; the host venue is the pin.
    'location provided upon', 'provided upon rsvp',
)

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
_IN_VENUE_RE = re.compile(r'^.*?\(\s*(?:in|at|inside)\s+(.+?)\s*\)\s*$', re.IGNORECASE)


def classify(event, alts_by_loc, generic_names=None):
    """Return one of NO_LOCATION / GENERIC / MISMATCHED / None.

    `generic_names` is the set of normalized names of every generic_location=1
    row. A location_name that merely repeats a neighborhood/borough placeholder
    ('Greenpoint', 'Harlem', 'Red Hook', 'Times Square') carries no venue
    information, so it can never contradict the specific venue it is pinned to.
    """
    if event['location_id'] is None:
        return 'NO_LOCATION'

    location_name = (event['location_name'] or '').strip()
    if len(location_name) < 3:
        return None

    # The name-based skip filters apply to BOTH the GENERIC and the MISMATCHED
    # queue. Until 2026-09-17 the GENERIC return sat above them, so nothing could
    # be skip-listed out of that queue and ~1,750 of its ~1,950 rows were
    # already-correct pins (a location_name that IS the pinned park's own name,
    # a sub-facility label inside it, or a meeting point inside it).
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
    # are substrings of each other (in either direction). For a GENERIC pin only
    # the forward direction counts: "Central Park" -> Central Park is fine, but
    # "Central Park Zoo" pinned to the Central Park placeholder is exactly the
    # venue-inside-a-park miss the GENERIC queue exists to surface.
    if n_loc in n_name:
        return None
    if n_name in n_loc and not event['venue_generic']:
        return None
    if n_loc in n_addr:
        return None

    # "<sub-facility> (in <venue>)" is consistent when <venue> is the pinned row
    # ("Great Lawn (in Central Park)", "Tennis Courts (in Prospect Park)").
    m = _IN_VENUE_RE.match(location_name)
    if m:
        n_in = _normalize_location_name(m.group(1))
        if n_in and (n_in in n_name or n_name in n_in or n_in in n_addr):
            return None

    if event['venue_generic']:
        return 'GENERIC'

    if (event['website_name'] or '') in SKIP_MISMATCH_WEBSITES:
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
