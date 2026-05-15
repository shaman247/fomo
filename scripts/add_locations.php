#!/usr/bin/env php
<?php
/**
 * Add new locations to the database (local or production)
 *
 * Usage:
 *   php scripts/add_locations.php                    # Add to local database
 *   php scripts/add_locations.php --production      # Add to production database
 *   php scripts/add_locations.php --dry-run         # Show what would be added
 *   php scripts/add_locations.php --production --dry-run
 *
 * Edit the $new_locations array below to specify locations to add.
 */

// ============================================================================
// EDIT THIS ARRAY TO ADD NEW LOCATIONS
// ============================================================================
$new_locations = [
    // 2026-05-15 — Blind Barber (East Village): barbershop with a hidden speakeasy bar in the back
    // at 339 E 10th St. Hosts third-party event-organizer programming (singles mixers via
    // PlentyofParties, etc.). Surfaced from Blankman List June 2026 cross-reference.
    [
        'name' => 'Blind Barber',
        'short_name' => 'Blind Barber',
        'address' => '339 E 10th St, New York, NY 10009, USA',
        'lat' => 40.72715, 'lng' => -73.98016,
        'emoji' => '💈',
        'tags' => ['Manhattan', 'East Village', 'Bar', 'Speakeasy', 'Cocktails'],
        'description' => 'East Village barbershop with a hidden speakeasy cocktail bar in the back; hosts third-party event programming (singles mixers, DJ nights, themed parties).',
    ],
    // 2026-05-15 — Nassau Community College: Long Island campus (Garden City) hosting the annual
    // Vaisakhi Mela Indian street fair and other large outdoor cultural events. Previously missing
    // from the DB, which caused fuzzy matcher to incorrectly map "Nassau Community College" mentions
    // to St. Joseph's University (Patchogue).
    [
        'name' => 'Nassau Community College',
        'short_name' => 'Nassau CC',
        'address' => '1 Education Dr, Garden City, NY 11530, USA',
        'lat' => 40.72910, 'lng' => -73.59404,
        'emoji' => '🏫',
        'tags' => ['Long Island', 'Garden City', 'School', 'Community Center'],
        'description' => 'Two-year community college in Garden City whose campus hosts large outdoor festivals and cultural events (e.g. the annual Vaisakhi Mela Indian street fair) alongside its academic programs.',
    ],
    // 2026-05-15 — College Point: Queens neighborhood corridor used for the College Point Memorial Day
    // Parade and other community street events along 26 Avenue / 14 Avenue. Previously missing from
    // the DB as a neighborhood-level location, which caused street-address parade entries to fuzzy-
    // match onto the wrong venue (e.g. "8th Avenue, Sunset Park" in Brooklyn).
    [
        'name' => 'College Point',
        'short_name' => 'College Point',
        'address' => 'College Point, Queens, NY, USA',
        'lat' => 40.78639, 'lng' => -73.83897,
        'emoji' => '📍',
        'tags' => ['Queens', 'College Point', 'neighborhood'],
        'description' => 'Northern Queens waterfront neighborhood on the East River; hosts the annual College Point Memorial Day Parade and other community street events.',
        'generic_location' => true,
    ],
    // 2026-05-14 — Croft Alley NYC: West Village wine-and-music venue at 210 6th Ave (West Village).
    // Surfaces from Partiful as host for recurring Stella Groove evenings of music + curated wines.
    [
        'name' => 'Croft Alley',
        'short_name' => 'Croft Alley',
        'address' => '210 6th Ave, New York, NY 10014, USA',
        'lat' => 40.72714, 'lng' => -74.00316,
        'emoji' => '🍷',
        'tags' => ['Manhattan', 'West Village', 'Wine Bar', 'Restaurant', 'Live Music'],
        'description' => 'West Village restaurant and wine bar hosting intimate music nights (Stella Groove series) with curated wines.',
    ],
    // 2026-05-14 — George Washington Bridge Bus Station: Washington Heights inter-state transit hub
    // (4211 Broadway between W 178th–179th Sts). Used as departure point for AMC Young Members NYC
    // and other group hikes to NJ/Hudson Valley trailheads.
    [
        'name' => 'George Washington Bridge Bus Station',
        'short_name' => 'GWB Bus Station',
        'address' => '4211 Broadway, New York, NY 10033, USA',
        'lat' => 40.84896, 'lng' => -73.93886,
        'emoji' => '🚌',
        'tags' => ['Manhattan', 'Washington Heights', 'Transit'],
        'description' => 'Major Washington Heights bus terminal at the upper Manhattan end of the George Washington Bridge; serves NJ Transit and inter-state coaches and is a frequent meet-up point for group hikes leaving NYC.',
    ],
    // 2026-05-14 — 5th Avenue (Park Slope): corridor location for the Park Slope Fifth Avenue BID
    // (website 4647). The BID's signature events (Fabulous Fifth Avenue Fair, Brooklyn Pride Day on
    // 5th, Street Tree workshops) roam blocks of 5th Ave between Sterling Place and 12th Street;
    // no single point covers them. Coordinates pin the midpoint at 4th St & 5th Ave. Marked generic
    // so it renders with the pushpin and reads as "broad area" in popups.
    [
        'name' => '5th Avenue (Park Slope)',
        'short_name' => '5th Ave',
        'address' => '5th Ave, Brooklyn, NY 11215, USA',
        'lat' => 40.672201, 'lng' => -73.983792,
        'emoji' => '📍',
        'tags' => ['Brooklyn', 'Park Slope', 'neighborhood'],
        'description' => 'Stretch of 5th Avenue running through Park Slope (Sterling Place to 12th Street); the Park Slope Fifth Avenue BID corridor hosts street fairs, pride events, and other roving sidewalk programming along these blocks.',
        'generic_location' => true,
    ],
    // 2026-05-14 — Pomo Ceramics: Bed-Stuy ceramics studio (951 Putnam Ave) offering wheel
    // throwing, hand-building, and one-day workshops for adults and families. IG @pomoceramics.
    [
        'name' => 'Pomo Ceramics',
        'address' => '951 Putnam Ave, Brooklyn, NY 11221, USA',
        'lat' => 40.68721, 'lng' => -73.92328,
        'emoji' => '🏺',
        'tags' => ['Brooklyn', 'Bed-Stuy', 'Ceramics', 'Pottery', 'Workshop', 'Studio'],
        'description' => 'Bed-Stuy ceramics studio running one-day adult wheel-throwing workshops, multi-week hand-building and wheel-throwing courses, and family/kids pottery programs.',
    ],
    // 2026-05-12 — La Cabra Brooklyn: Bushwick coffee roastery (Danish-Italian La Cabra chain).
    // Hosts Cake Picnic Brooklyn edition (2026-05-31) per cakepicnictour.com/nyc.
    [
        'name' => 'La Cabra Brooklyn',
        'short_name' => 'La Cabra',
        'address' => '1329 Willoughby Ave Unit # 161, Brooklyn, NY 11237, USA',
        'lat' => 40.70650, 'lng' => -73.92094,
        'emoji' => '☕',
        'tags' => ['Brooklyn', 'Bushwick', 'Cafe'],
        'description' => 'Bushwick roastery and cafe from the Danish-Italian La Cabra coffee company, occasionally hosting community events like cookbook launches.',
    ],
    // 2026-05-10 — Please, An Educated Pleasure Shop: South Slope sex-positive shop
    // (est. 2015) that hosts erotic life-drawing sessions, "Please Presentations" talks,
    // and other educational/artistic adult programming. Eventbrite organizer 72665370743.
    [
        'name' => 'Please, An Educated Pleasure Shop',
        'short_name' => 'Please',
        'address' => '635 5th Ave, Brooklyn, NY 11215, USA',
        'lat' => 40.66305, 'lng' => -73.99135,
        'emoji' => '🛍️',
        'tags' => ['Brooklyn', 'South Slope', 'Sex Positive', 'Adult', 'Education'],
        'description' => 'South Slope sex-positive shop hosting erotic life-drawing sessions, educational talks, and other adult-oriented art and learning events alongside its retail offerings.',
    ],
    // 2026-05-08 — Kosmic Community Anti Bar: East Village non-alcoholic "anti bar" / coffee shop
    // at 115 Ave C (Loisaida Ave). Linked to @kosmiccommunityantibar (website 4602) via
    // website_locations + location_instagram, set up separately after this insert.
    [
        'name' => 'Kosmic Community Anti Bar',
        'short_name' => 'Kosmic',
        'address' => '115 Avenue C, New York, NY 10009, USA',
        'lat' => 40.72440, 'lng' => -73.97878,
        'emoji' => '☕',
        'tags' => ['Manhattan', 'East Village', 'Cafe'],
        'description' => 'East Village non-alcoholic "anti bar" and coffee shop on Loisaida Ave (Avenue C).',
    ],
    // 2026-05-08 — NYC Community Gardens venues missing from the DB. These showed up
    // repeatedly as unmapped events (planting days, swaps, workshops). Addresses
    // confirmed via geocoding the listed street addresses; garden identities cross-checked
    // against the GreenThumb directory and individual garden websites.
    [
        'name' => 'Pleasant Village Community Garden',
        'address' => '342 Pleasant Ave, New York, NY 10035, USA',
        'lat' => 40.79663, 'lng' => -73.93167,
        'emoji' => '🌱',
        'tags' => ['Manhattan', 'East Harlem', 'Garden'],
        'description' => 'East Harlem GreenThumb community garden hosting herbal-arts workshops, music, and seasonal volunteer days.',
    ],
    [
        'name' => 'Carver Community Garden',
        'address' => '242 E 124th St, New York, NY 10035, USA',
        'lat' => 40.80210, 'lng' => -73.93469,
        'emoji' => '🌱',
        'tags' => ['Manhattan', 'East Harlem', 'Garden'],
        'description' => 'East Harlem community garden run by neighborhood volunteers, hosting planting days, craft workshops, and seasonal cultivation events.',
    ],
    [
        'name' => 'A Patch of Inspiration Garden',
        'address' => '633 Powell St, Brooklyn, NY 11212, USA',
        'lat' => 40.65855, 'lng' => -73.90088,
        'emoji' => '🌱',
        'tags' => ['Brooklyn', 'Brownsville', 'Garden'],
        'description' => 'Brownsville GreenThumb community garden hosting tours, garden luaus, and family-friendly events.',
    ],
    [
        'name' => 'East Fourth Street Community Garden',
        'address' => '270 E 4th St, New York, NY 10009, USA',
        'lat' => 40.72263, 'lng' => -73.98151,
        'emoji' => '🌱',
        'tags' => ['Manhattan', 'East Village', 'Garden'],
        'description' => 'East Village volunteer-run GreenThumb community garden hosting yoga, pollinator walks, and live jazz under the trees.',
    ],
    [
        'name' => 'Eastchester Road Community Garden',
        'address' => '3634 Eastchester Rd, Bronx, NY 10469, USA',
        'lat' => 40.88184, 'lng' => -73.84864,
        'emoji' => '🌱',
        'tags' => ['Bronx', 'Williamsbridge', 'Garden'],
        'description' => 'Northeast Bronx weekly community garden space welcoming residents to connect with nature, explore plants, and enjoy a relaxing environment.',
    ],
    [
        'name' => "Lydia's Magic Garden",
        'short_name' => "Lydia's Magic Garden",
        'address' => '626 E 11th St, New York, NY 10009, USA',
        'lat' => 40.72686, 'lng' => -73.97844,
        'emoji' => '🌱',
        'tags' => ['Manhattan', 'East Village', 'Garden'],
        'description' => 'East Village community garden (also known as El Girasol Magic Garden) celebrating Latinx culture with seasonal parades, music, and workshops.',
    ],
    [
        'name' => 'Elton Street Community Garden',
        'address' => '585 Elton St, Brooklyn, NY 11208, USA',
        'lat' => 40.66866, 'lng' => -73.88190,
        'emoji' => '🌱',
        'tags' => ['Brooklyn', 'East New York', 'Garden'],
        'description' => 'East New York volunteer-run community garden hosting seasonal beautification days and gardening workshops.',
    ],
    [
        'name' => 'La Finca del Sur',
        'address' => '175 E 138th St, Bronx, NY 10454, USA',
        'lat' => 40.81286, 'lng' => -73.92959,
        'emoji' => '🌱',
        'tags' => ['Bronx', 'Mott Haven', 'Garden'],
        'description' => 'South Bronx urban farm and community garden led by women of color, hosting fruit-tree workshops, harvest events, and educational programs.',
    ],
    [
        'name' => 'Walt L. Shamel Community Garden',
        'address' => '1095 Dean St, Brooklyn, NY 11216, USA',
        'lat' => 40.67752, 'lng' => -73.95366,
        'emoji' => '🌱',
        'tags' => ['Brooklyn', 'Crown Heights', 'Garden'],
        'description' => 'Crown Heights GreenThumb community garden hosting fruit-preservation workshops, food-justice programs, and seasonal community events.',
    ],
    [
        'name' => 'Tranquility Farm',
        'address' => '762 Herkimer St, Brooklyn, NY 11233, USA',
        'lat' => 40.67830, 'lng' => -73.92818,
        'emoji' => '🌱',
        'tags' => ['Brooklyn', 'Bedford-Stuyvesant', 'Garden'],
        'description' => 'Bedford-Stuyvesant community garden and urban farm hosting cultural workshops, ice-cream-making events, and diaspora food programming.',
    ],
    [
        'name' => 'Franklin Memorial Garden',
        'address' => '659 Willoughby Ave, Brooklyn, NY 11206, USA',
        'lat' => 40.69472, 'lng' => -73.94303,
        'emoji' => '🌱',
        'tags' => ['Brooklyn', 'Bedford-Stuyvesant', 'Garden'],
        'description' => 'Bedford-Stuyvesant community garden hosting free CPR trainings, arts and crafts, and family-friendly nature activities.',
    ],
    // 2026-05-06 — Hex House art studio / event space in East Williamsburg.
    // 4,000 sq ft warehouse hosting performances, ceremonies, classes, and one-off showcases.
    [
        'name' => 'Hex House',
        'address' => '50 Norman Ave, Brooklyn, NY 11222, USA',
        'lat' => 40.72469, 'lng' => -73.95366,
        'emoji' => '🎨',
        'tags' => ['Brooklyn', 'East Williamsburg', 'Art', 'Community Space'],
        'description' => '4,000 sq ft warehouse art studio and community event space in East Williamsburg, hosting performances, ceremonies, classes, and creative showcases.',
    ],
    // 2026-05-04 — Brooklyn Film Camera shop in East Williamsburg. Hosts photography classes,
    // gallery openings, and tintype workshops via the Mahina event calendar app on Shopify.
    [
        'name' => 'Brooklyn Film Camera',
        'address' => '855 Grand St, Brooklyn, NY 11221, USA',
        'lat' => 40.71243, 'lng' => -73.93966,
        'emoji' => '📷',
        'tags' => ['Brooklyn', 'East Williamsburg', 'Photography', 'Shop'],
        'description' => 'East Williamsburg film-camera shop and lab hosting photography classes, gallery openings, and tintype workshops.',
    ],
    // Added 2026-05-04 — second-pass venue additions from Luma migration batch.
    // Specific addresses surfaced by Luma API but no DB venue entry — researched and confirmed via WE ACT, Sixth Street CC, Brooklyn Running Co websites.
    [
        'name' => 'Brooklyn Running Co. (Park Slope)',
        'address' => '480 Bergen St, Brooklyn, NY 11217, USA',
        'lat' => 40.68066, 'lng' => -73.97549,
        'emoji' => '🏃',
        'tags' => ['Brooklyn', 'Park Slope', 'Shop', 'Sports'],
        'description' => 'Park Slope branch of the independent NYC running specialty shop, hosting yoga-for-runners classes, group runs, and gear nights.',
    ],
    [
        'name' => 'Sixth Street Community Center',
        'address' => '638 E 6th St, New York, NY 10009, USA',
        'lat' => 40.72368, 'lng' => -73.98025,
        'emoji' => '🌱',
        'tags' => ['Manhattan', 'East Village', 'Community Center'],
        'description' => 'Restored former synagogue in the East Village now home to a 50-year-old community center running food, environment, and youth-empowerment programming, plus the Organic Soul Cafe and event-rental space.',
    ],
    [
        'name' => 'Frederick Douglass Houses Community Center',
        'address' => '825 Columbus Ave, New York, NY 10025, USA',
        'lat' => 40.79568, 'lng' => -73.96494,
        'emoji' => '🏘️',
        'tags' => ['Manhattan', 'Manhattan Valley', 'Community Center'],
        'description' => 'NYCHA-operated community space within the Frederick Douglass Houses on the Upper West Side, occasional host of community gardening, environmental, and resident-engagement programming.',
    ],
    // Added 2026-05-04 — Luma migration batch (Girls Who Meet, Climate Cafe, NYC Running, etc.).
    // Extracted from geo_address_info on each calendar's API JSON. Each is a venue that was previously
    // surfacing events into "Manhattan (exact location unspecified)" or unmapped because the markdown
    // listing only showed venue names without addresses.
    [
        'name' => 'Madewell Flatiron',
        'address' => '156 5th Ave, New York, NY 10010, USA',
        'lat' => 40.7400338, 'lng' => -73.9912721,
        'emoji' => '👗',
        'tags' => ['Manhattan', 'Flatiron District', 'Shop'],
        'description' => 'Madewell apparel storefront in the Flatiron District; hosts members-only happy hours and small community events.',
    ],
    [
        'name' => 'CityPickle Times Square',
        'address' => '1501 Broadway 8th Floor, New York, NY 10036, USA',
        'lat' => 40.7571307, 'lng' => -73.9871167,
        'emoji' => '🏓',
        'tags' => ['Manhattan', 'Times Square', 'Sports'],
        'description' => 'Indoor pickleball courts on the 8th floor of 1501 Broadway in Times Square — open play, lessons, and social mixers.',
    ],
    [
        'name' => 'The Sewing Clubhouse',
        'address' => '44-02 23rd St, Long Island City, NY 11101, USA',
        'lat' => 40.7489473, 'lng' => -73.944852,
        'emoji' => '🧵',
        'tags' => ['Queens', 'Long Island City', 'Studio'],
        'description' => 'Long Island City sewing and clothing-mending workshop space hosting alterations classes and zero-waste clothing events.',
    ],
    [
        'name' => 'Brooklyn Queens Brewery',
        'address' => '70-02 Cooper Ave, Glendale, NY 11385, USA',
        'lat' => 40.7017536, 'lng' => -73.8802691,
        'emoji' => '🍺',
        'tags' => ['Queens', 'Glendale', 'Bar'],
        'description' => 'Glendale brewery and tap room hosting community events including running club gatherings and an annual half marathon.',
    ],
    // Added 2026-05-04 — craftnook Luma migration: extracted from geo_address_info in Luma calendar API JSON.
    // Single recurring venue for all craftnook (3646) events; previously mapped to "Manhattan (exact location unspecified)".
    [
        'name' => "haricot vert's dreamworld",
        'address' => '119 N 1st St, Brooklyn, NY 11249, USA',
        'lat' => 40.7155365, 'lng' => -73.9619548,
        'emoji' => '✨',
        'tags' => ['Brooklyn', 'Williamsburg', 'Performance Space', 'Shop'],
        'description' => 'Williamsburg craft and creative-event space hosting workshops, mosaic and jewelry-making classes, and other artist-run gatherings (frequent home of craftnook events).',
    ],
    // Added 2026-05-04 — Mambroso Luma crawl: extracted from geo_address_info in Luma calendar API JSON.
    // Two distinct suites in the same Flatiron building (different Google place_ids). The Luma calendar
    // surfaces each as its own venue, so we treat them as separate locations rather than one shared venue.
    [
        'name' => 'Loft on 5th',
        'address' => '20 W 23rd St Suite 5, New York, NY 10010, USA',
        'lat' => 40.7417143, 'lng' => -73.9905555,
        'emoji' => '🏙️',
        'tags' => ['Manhattan', 'Flatiron District', 'Performance Space'],
        'description' => 'Flatiron rental loft used by Luma organizers for rooftop salsa nights, dance socials, and singles parties.',
    ],
    [
        'name' => 'Loft in Flatiron',
        'address' => '20 W 23rd St Suite 4, New York, NY 10010, USA',
        'lat' => 40.7417143, 'lng' => -73.9905555,
        'emoji' => '🏙️',
        'tags' => ['Manhattan', 'Flatiron District', 'Performance Space'],
        'description' => 'Flatiron rental loft used by Luma organizers for cocktail lounge events, mahjong nights, and small dance parties.',
    ],
    // Added 2026-05-04 — City Happenings cross-ref. KREWE eyewear flagship hosts annual Krawfish Boil.
    [
        'name' => 'KREWE NYC',
        'address' => '67 Gansevoort St, New York, NY 10014, USA',
        'lat' => 40.7396, 'lng' => -74.0075,
        'emoji' => '🕶️',
        'tags' => ['Manhattan', 'Meatpacking District', 'Shopping'],
        'description' => 'New Orleans-born eyewear brand with a Meatpacking District flagship that hosts pop-up parties and an annual NYC Krawfish Boil benefiting City Harvest.',
    ],
    // Added 2026-05-02 — DUMBO board game café/lounge (sister of Last Place on Earth in Greenpoint).
    [
        'name' => '3rd Place from the Sun',
        'short_name' => '3rd Place',
        'address' => '80 John St, Brooklyn, NY 11201, USA',
        'lat' => 40.7043, 'lng' => -73.9852,
        'emoji' => '🎲',
        'tags' => ['Brooklyn', 'DUMBO', 'Games'],
        'description' => 'DUMBO board game café and community gaming lounge with 500+ curated games, hosting open play, themed nights, and immersive D&D campaigns.',
    ],
    // Added 2026-05-01 — Nonsense NYC newsletter cross-ref venues missing from DB.
    [
        'name' => 'Playwrights Downtown',
        'address' => '440 Lafayette St # 4, New York, NY 10003, USA',
        'lat' => 40.7295, 'lng' => -73.9922,
        'emoji' => '🎭',
        'tags' => ['Manhattan', 'NoHo', 'Theater', 'Performance Space'],
        'description' => 'A downtown Manhattan theater and rehearsal space on Lafayette Street hosting plays, workshops, and cultural performances.',
    ],
    [
        'name' => 'Time Out Market New York (Union Square)',
        'short_name' => 'Time Out Market Union Square',
        'address' => '124 E 14th St, New York, NY 10003, USA',
        'lat' => 40.7338, 'lng' => -73.9888,
        'emoji' => '🍽️',
        'tags' => ['Manhattan', 'Union Square', 'Food'],
        'description' => 'Union Square outpost of the Time Out Market food hall featuring chef-driven kitchens, bars, and event programming.',
    ],
    [
        'name' => 'Victorian Society New York',
        'address' => '521 W 23rd St, 2nd Floor, New York, NY 10011, USA',
        'lat' => 40.7484, 'lng' => -74.0049,
        'emoji' => '🏛️',
        'tags' => ['Manhattan', 'Chelsea', 'Lecture'],
        'description' => 'A nonprofit dedicated to preserving and studying 19th- and early 20th-century architecture and culture; hosts lectures, tours, and the Emerging Scholars program.',
    ],
    [
        'name' => 'Remedies Herb Shop',
        'address' => '453 Court St, Brooklyn, NY 11231, USA',
        'lat' => 40.6775, 'lng' => -73.9981,
        'emoji' => '🌿',
        'tags' => ['Brooklyn', 'Carroll Gardens', 'Wellness'],
        'description' => 'A Carroll Gardens herb shop offering bulk dried herbs, tinctures, and a calendar of herbalism workshops and classes.',
    ],
    // Added 2026-05-01 — onboarding NYC-metro Regal Cinemas (companion to AMC theaters added 2026-04-30).
    // Sheepshead Bay already exists as location 1014 — only added to add_websites.php below.
    [
        'name' => 'Regal Union Square',
        'address' => '850 Broadway, New York, NY 10003, USA',
        'lat' => 40.734, 'lng' => -73.9912,
        'emoji' => '🎬',
        'tags' => ['Manhattan', 'Union Square', 'Cinema'],
        'description' => 'A 14-screen multiplex movie theater on Broadway near Union Square showing first-run releases.',
    ],
    [
        'name' => 'Regal Battery Park',
        'address' => '102 North End Ave, New York, NY 10282, USA',
        'lat' => 40.7147, 'lng' => -74.0155,
        'emoji' => '🎬',
        'tags' => ['Manhattan', 'Battery Park City', 'Cinema'],
        'description' => '11-screen movie theater in Battery Park City showing first-run releases.',
    ],
    [
        'name' => 'Regal Essex Crossing',
        'address' => '129 Delancey Street, New York, NY 10002, USA',
        'lat' => 40.7182, 'lng' => -73.9881,
        'emoji' => '🎬',
        'tags' => ['Manhattan', 'Lower East Side', 'Cinema'],
        'description' => 'Lower East Side movie theater inside Essex Crossing development with RPX premium screens.',
    ],
    [
        'name' => 'Regal Times Square',
        'address' => '247 W. 42nd St, New York, NY 10036, USA',
        'lat' => 40.7565, 'lng' => -73.9883,
        'emoji' => '🎬',
        'tags' => ['Manhattan', 'Times Square', 'Cinema'],
        'description' => 'Times Square movie theater on 42nd Street showing first-run releases.',
    ],
    [
        'name' => 'Regal Atlas Park',
        'address' => '80-28 Cooper Ave, Suite #6216, Glendale, NY 11385, USA',
        'lat' => 40.709, 'lng' => -73.8705,
        'emoji' => '🎬',
        'tags' => ['Queens', 'Glendale', 'Cinema'],
        'description' => '8-screen Queens movie theater inside The Shops at Atlas Park.',
    ],
    [
        'name' => 'Regal UA Midway',
        'address' => '108-22 Queens Blvd, Forest Hills, NY 11375, USA',
        'lat' => 40.7209, 'lng' => -73.8442,
        'emoji' => '🎬',
        'tags' => ['Queens', 'Forest Hills', 'Cinema'],
        'description' => '9-screen Forest Hills movie theater on Queens Boulevard.',
    ],
    [
        'name' => 'Regal Kaufman Astoria',
        'address' => '35-30 38th Street, Long Island City, NY 11101, USA',
        'lat' => 40.7556, 'lng' => -73.9236,
        'emoji' => '🎬',
        'tags' => ['Queens', 'Long Island City', 'Cinema'],
        'description' => '14-screen multiplex inside Kaufman Astoria Studios with RPX premium screens.',
    ],
    [
        'name' => 'Regal Tangram',
        'address' => '133-36 37th Avenue, Flushing, NY 11354, USA',
        'lat' => 40.7602, 'lng' => -73.8336,
        'emoji' => '🎬',
        'tags' => ['Queens', 'Flushing', 'Cinema'],
        'description' => 'Flushing movie theater featuring 4DX premium screens.',
    ],
    [
        'name' => 'Regal Concourse',
        'address' => '214 E. 161st Street, Bronx, NY 10451, USA',
        'lat' => 40.8251, 'lng' => -73.9212,
        'emoji' => '🎬',
        'tags' => ['Bronx', 'Concourse', 'Cinema'],
        'description' => 'Bronx movie theater near Yankee Stadium showing first-run releases.',
    ],
    [
        'name' => 'Regal Bricktown Charleston',
        'address' => '165 Bricktown Way, Staten Island, NY 10309, USA',
        'lat' => 40.5303, 'lng' => -74.2302,
        'emoji' => '🎬',
        'tags' => ['Staten Island', 'Charleston', 'Cinema'],
        'description' => '10-screen Staten Island movie theater inside the Bricktown Center development.',
    ],
    [
        'name' => 'Regal Westbury',
        'address' => '7000 Brush Hollow Road, Westbury, NY 11590, USA',
        'lat' => 40.7767, 'lng' => -73.5596,
        'emoji' => '🎬',
        'tags' => ['Long Island', 'Nassau County', 'Westbury', 'Cinema'],
        'description' => '12-screen Long Island movie theater with IMAX and RPX premium screens.',
    ],
    [
        'name' => 'Regal Lynbrook',
        'address' => '321 Merrick Road, Lynbrook, NY 11563, USA',
        'lat' => 40.6573, 'lng' => -73.6716,
        'emoji' => '🎬',
        'tags' => ['Long Island', 'Nassau County', 'Lynbrook', 'Cinema'],
        'description' => '13-screen Nassau County movie theater with RPX premium screens.',
    ],
    [
        'name' => 'Regal UA Farmingdale',
        'address' => '20 Michael Avenue, Farmingdale, NY 11735, USA',
        'lat' => 40.7258, 'lng' => -73.4246,
        'emoji' => '🎬',
        'tags' => ['Long Island', 'Nassau County', 'Farmingdale', 'Cinema'],
        'description' => '10-screen Long Island movie theater with IMAX premium screens.',
    ],
    [
        'name' => 'Regal Ronkonkoma',
        'address' => '565 Portion Road, Ronkonkoma, NY 11779, USA',
        'lat' => 40.8307, 'lng' => -73.0913,
        'emoji' => '🎬',
        'tags' => ['Long Island', 'Suffolk County', 'Ronkonkoma', 'Cinema'],
        'description' => '9-screen Suffolk County movie theater showing first-run releases.',
    ],
    [
        'name' => 'Regal Deer Park',
        'address' => '1050 The Arches Circle, Deer Park, NY 11729, USA',
        'lat' => 40.7624, 'lng' => -73.3095,
        'emoji' => '🎬',
        'tags' => ['Long Island', 'Suffolk County', 'Deer Park', 'Cinema'],
        'description' => 'Suffolk County movie theater with IMAX premium screens.',
    ],
    [
        'name' => 'Regal UA East Hampton',
        'address' => '30 Main Street, East Hampton, NY 11937, USA',
        'lat' => 40.9637, 'lng' => -72.1855,
        'emoji' => '🎬',
        'tags' => ['Long Island', 'East Hampton', 'Cinema'],
        'description' => '6-screen movie theater in the Hamptons showing first-run releases.',
    ],
    [
        'name' => 'Regal New Roc',
        'address' => '33 Le Count Place, New Rochelle, NY 10801, USA',
        'lat' => 40.9108, 'lng' => -73.7803,
        'emoji' => '🎬',
        'tags' => ['Westchester', 'New Rochelle', 'Cinema'],
        'description' => '18-screen Westchester movie theater with IMAX and RPX premium screens.',
    ],
    [
        'name' => 'Regal Cortlandt Town Center',
        'address' => '3131 East Main Street, Mohegan Lake, NY 10547, USA',
        'lat' => 41.3199, 'lng' => -73.8573,
        'emoji' => '🎬',
        'tags' => ['Westchester', 'Mohegan Lake', 'Cinema'],
        'description' => '11-screen Westchester County movie theater showing first-run releases.',
    ],
    [
        'name' => 'Regal Nanuet',
        'address' => '6201 Fashion Drive, Nanuet, NY 10954, USA',
        'lat' => 41.0969, 'lng' => -74.0129,
        'emoji' => '🎬',
        'tags' => ['Hudson Valley', 'Rockland County', 'Nanuet', 'Cinema'],
        'description' => '12-screen Rockland County movie theater with RPX premium screens.',
    ],
    [
        'name' => 'Regal Galleria Mall (Poughkeepsie)',
        'address' => '2001 South Road, Poughkeepsie, NY 12601, USA',
        'lat' => 41.6268, 'lng' => -73.9194,
        'emoji' => '🎬',
        'tags' => ['Hudson Valley', 'Poughkeepsie', 'Cinema'],
        'description' => '16-screen Hudson Valley movie theater inside Poughkeepsie Galleria Mall.',
    ],
    [
        'name' => 'Regal Secaucus',
        'address' => '650 Plaza Drive, Secaucus, NJ 07094, USA',
        'lat' => 40.7853, 'lng' => -74.0465,
        'emoji' => '🎬',
        'tags' => ['New Jersey', 'Hudson County', 'Secaucus', 'Cinema'],
        'description' => '14-screen New Jersey movie theater inside Mill Creek Plaza.',
    ],
    // Added 2026-04-30 — onboarding remaining NYC-area AMC theaters
    [
        'name' => 'AMC Empire 25',
        'address' => '234 W 42nd St, New York, NY 10036, USA',
        'lat' => 40.756737, 'lng' => -73.989004,
        'emoji' => '🎬',
        'tags' => ['Manhattan', 'Times Square', 'Cinema'],
        'description' => 'A 25-screen multiplex movie theater in Times Square, one of the highest-grossing single cinemas in the U.S. First-run releases plus IMAX and Dolby Cinema.',
    ],
    [
        'name' => 'AMC 19th St. East 6',
        'short_name' => 'AMC 19th St East',
        'address' => '890 Broadway, New York, NY 10003, USA',
        'lat' => 40.738556, 'lng' => -73.989780,
        'emoji' => '🎬',
        'tags' => ['Manhattan', 'Union Square', 'Cinema'],
        'description' => 'Six-screen movie theater near Union Square showing first-run releases.',
    ],
    [
        'name' => 'AMC Kips Bay 15',
        'address' => '570 2nd Ave, New York, NY 10016, USA',
        'lat' => 40.742874, 'lng' => -73.976863,
        'emoji' => '🎬',
        'tags' => ['Manhattan', 'Kips Bay', 'Cinema'],
        'description' => 'A 15-screen movie theater in Kips Bay showing first-run releases and special programming.',
    ],
    [
        'name' => 'AMC Village 7',
        'address' => '66 Third Ave, New York, NY 10003, USA',
        'lat' => 40.731608, 'lng' => -73.988793,
        'emoji' => '🎬',
        'tags' => ['Manhattan', 'East Village', 'Cinema'],
        'description' => 'Seven-screen movie theater on Third Avenue at 11th Street showing first-run releases.',
    ],
    [
        'name' => 'AMC 84th Street 6',
        'address' => '2310 Broadway, New York, NY 10024, USA',
        'lat' => 40.786707, 'lng' => -73.977488,
        'emoji' => '🎬',
        'tags' => ['Manhattan', 'Upper West Side', 'Cinema'],
        'description' => 'Six-screen Upper West Side movie theater showing first-run releases.',
    ],
    [
        'name' => 'AMC Newport Centre 11',
        'address' => '30-300 Mall Dr W, Jersey City, NJ 07310, USA',
        'lat' => 40.726829, 'lng' => -74.037838,
        'emoji' => '🎬',
        'tags' => ['New Jersey', 'Jersey City', 'Cinema'],
        'description' => 'Eleven-screen movie theater inside Newport Centre Mall in Jersey City.',
    ],
    [
        'name' => 'AMC Orpheum 7',
        'address' => '1538 Third Ave, New York, NY 10028, USA',
        'lat' => 40.779357, 'lng' => -73.953964,
        'emoji' => '🎬',
        'tags' => ['Manhattan', 'Upper East Side', 'Cinema'],
        'description' => 'Seven-screen movie theater on the Upper East Side at 86th Street.',
    ],
    [
        'name' => 'AMC Magic Johnson Harlem 9',
        'short_name' => 'AMC Magic Johnson Harlem',
        'address' => '2309 Frederick Douglass Blvd, New York, NY 10027, USA',
        'lat' => 40.809735, 'lng' => -73.951802,
        'emoji' => '🎬',
        'tags' => ['Manhattan', 'Harlem', 'Cinema'],
        'description' => 'Nine-screen movie theater in Harlem (former Magic Johnson Theatres) showing first-run releases.',
    ],
    // Added 2026-04-30 from /fix-unmapped-events (Hudson Valley)
    [
        'name' => 'Catskill Mountain Shakespeare',
        'address' => '7950 Main St, Hunter, NY 12442, USA',
        'lat' => 42.212778, 'lng' => -74.217644,
        'emoji' => '🎭',
        'tags' => ['Hudson Valley', 'Theater', 'Shakespeare'],
        'description' => 'Outdoor Shakespeare company performing main-stage productions under the tent at The Red Barn in Hunter, NY.',
    ],
    [
        'name' => 'Rothermel Park',
        'address' => 'Rothermel Ave, Kinderhook, NY 12106, USA',
        'lat' => 42.395124, 'lng' => -73.706804,
        'emoji' => '🌳',
        'tags' => ['Hudson Valley', 'Park'],
        'description' => 'Public park on Rothermel Avenue in Kinderhook, Columbia County.',
    ],
    [
        'name' => 'Reading Room',
        'address' => '198 N 4th St, Brooklyn, NY 11211, USA',
        'lat' => 40.715015, 'lng' => -73.957954,
        'emoji' => '📚',
        'tags' => ['Brooklyn', 'Williamsburg', 'Bookstore', 'Cafe'],
        'description' => 'Williamsburg literary cafe and reading space adjoining Supernova.',
    ],
    // Added 2026-04-29 from BPL unmapped events
    [
        'name' => "Amnon's Kosher Pizza",
        'address' => '4814 13th Ave, Brooklyn, NY 11219, USA',
        'lat' => 40.638600, 'lng' => -73.996100,
        'emoji' => '🍕',
        'tags' => ['Brooklyn', 'Borough Park', 'Restaurant', 'Pizza'],
        'description' => 'Borough Park kosher pizzeria operating since the 1980s; hosts weekly community craft circles.',
    ],
    [
        'name' => 'Our Lady of Grace Church',
        'address' => '430 Avenue W, Brooklyn, NY 11223, USA',
        'lat' => 40.590500, 'lng' => -73.969400,
        'emoji' => '⛪',
        'tags' => ['Brooklyn', 'Gravesend', 'Religion', 'Community'],
        'description' => 'Gravesend Catholic parish with a community hall (Veltri Hall) hosting wellness and community programs.',
    ],
    // Added from borough-generic investigation (2026-04-28)
    [
        'name' => 'Mysstic Rooms',
        'address' => '794 Union St, Brooklyn, NY 11215, USA',
        'lat' => 40.677880, 'lng' => -73.978847,
        'emoji' => '🗝️',
        'tags' => ['Brooklyn', 'Park Slope', 'Escape Room', 'Activity'],
        'description' => 'Park Slope escape room company hosting themed escape experiences.',
    ],
    [
        'name' => 'Audible Story House',
        'address' => '260 Bowery, New York, NY 10012, USA',
        'lat' => 40.723500, 'lng' => -73.992500,
        'emoji' => '🎧',
        'tags' => ['Manhattan', 'NoHo', 'Event Space', 'Audio'],
        'description' => 'Audible-operated event space on the Bowery hosting book and audio storytelling events.',
    ],
    [
        'name' => 'one4one Sports Club & Lounge',
        'address' => '141 Chrystie St, New York, NY 10002, USA',
        'lat' => 40.720600, 'lng' => -73.992300,
        'emoji' => '🏓',
        'tags' => ['Manhattan', 'Lower East Side', 'Bar', 'Sports'],
        'description' => 'Lower East Side sports bar and lounge with TV screens for big matches and watch parties.',
    ],
    [
        'name' => 'Rema Hort Mann Fund',
        'short_name' => 'RHMF',
        'address' => '153 Hudson St, New York, NY 10013, USA',
        'lat' => 40.722500, 'lng' => -74.009000,
        'emoji' => '🎨',
        'tags' => ['Manhattan', 'Tribeca', 'Art', 'Foundation'],
        'description' => 'Tribeca-based foundation supporting emerging artists with grants and exhibitions.',
    ],
    [
        'name' => 'Mirelle\'s',
        'address' => '170 Post Ave, Westbury, NY 11590, USA',
        'lat' => 40.755200, 'lng' => -73.586600,
        'emoji' => '💃',
        'tags' => ['Long Island', 'Nassau County', 'Dance', 'Tango'],
        'description' => 'Long Island restaurant and ballroom hosting weekly Argentine tango practicas and milongas.',
    ],
    [
        'name' => 'Council of Peoples Organization',
        'short_name' => 'COPO',
        'address' => '1081 Coney Island Ave, Brooklyn, NY 11230, USA',
        'lat' => 40.628890, 'lng' => -73.967160,
        'emoji' => '🤝',
        'tags' => ['Brooklyn', 'Midwood', 'Community', 'Nonprofit'],
        'description' => 'Brooklyn community organization serving immigrant communities with social services and food distribution.',
    ],
    [
        'name' => 'Christ Disciples International Ministries',
        'address' => '3031 Webster Ave, Bronx, NY 10458, USA',
        'lat' => 40.870300, 'lng' => -73.886500,
        'emoji' => '⛪',
        'tags' => ['Bronx', 'Bedford Park', 'Religion', 'Community'],
        'description' => 'Bronx church and community ministry running food distribution and outreach programs.',
    ],
    [
        'name' => 'Good+Foundation',
        'address' => '307 W 36th St, New York, NY 10018, USA',
        'lat' => 40.754700, 'lng' => -73.995000,
        'emoji' => '👶',
        'tags' => ['Manhattan', 'Midtown Manhattan', 'Nonprofit', 'Family'],
        'description' => 'Family-focused nonprofit founded by Jessica Seinfeld with offices in the Garment District.',
    ],
    [
        'name' => 'Team TLC NYC',
        'address' => '12 W 40th St, New York, NY 10018, USA',
        'lat' => 40.752900, 'lng' => -73.984000,
        'emoji' => '🤝',
        'tags' => ['Manhattan', 'Midtown Manhattan', 'Nonprofit', 'Immigration'],
        'description' => 'Volunteer-run organization serving newly arrived immigrants, operating the Little Shop of Kindness near Bryant Park.',
    ],
    [
        'name' => 'Encore Community Services',
        'address' => '239 W 49th St, New York, NY 10019, USA',
        'lat' => 40.760900, 'lng' => -73.985300,
        'emoji' => '🍽️',
        'tags' => ['Manhattan', "Hell's Kitchen", 'Nonprofit', 'Seniors'],
        'description' => 'Theater District nonprofit serving older adults with meals, social programs, and supportive housing.',
    ],
    [
        'name' => 'Castleton Hill Moravian Community Garden',
        'address' => '1657 Victory Blvd, Staten Island, NY 10314, USA',
        'lat' => 40.613557, 'lng' => -74.119260,
        'emoji' => '🌱',
        'tags' => ['Staten Island', 'Castleton Corners', 'Garden', 'Community'],
        'description' => 'Community garden run by Castleton Hill Moravian Church on the central North Shore of Staten Island.',
    ],
    [
        'name' => 'St. Joseph\'s University Patchogue',
        'short_name' => 'SJU Patchogue',
        'address' => '155 W Roe Blvd, Patchogue, NY 11772, USA',
        'lat' => 40.756700, 'lng' => -73.011000,
        'emoji' => '🎓',
        'tags' => ['Long Island', 'Suffolk County', 'University'],
        'description' => 'Long Island campus of St. Joseph\'s University in Patchogue, Suffolk County.',
    ],
    [
        'name' => 'LOOVE Labs',
        'short_name' => 'LOOVE',
        'address' => '58 N 6th St, Brooklyn, NY 11249, USA',
        'lat' => 40.717400, 'lng' => -73.961800,
        'emoji' => '🎶',
        'tags' => ['Brooklyn', 'Williamsburg', 'Music', 'Studio'],
        'description' => 'Williamsburg recording studio and event space hosting music performances and listening parties.',
    ],
    [
        'name' => 'Allison Pond Park',
        'address' => 'Allison Pond Park, Staten Island, NY 10301, USA',
        'lat' => 40.629700, 'lng' => -74.087000,
        'emoji' => '🌳',
        'tags' => ['Staten Island', 'Randall Manor', 'Park'],
        'description' => 'Staten Island North Shore park with hiking trails and natural pond, in Randall Manor.',
    ],
    [
        'name' => 'Idlewild Environmental Science Learning Center',
        'address' => '222-02 149th Ave, Springfield Gardens, NY 11413, USA',
        'lat' => 40.671500, 'lng' => -73.760000,
        'emoji' => '🌿',
        'tags' => ['Queens', 'Springfield Gardens', 'Education', 'Environment'],
        'description' => 'Eastern Queens Alliance environmental education center near Idlewild Park.',
    ],
    [
        'name' => 'The Ivory On Park',
        'address' => '12 Park St, Brooklyn, NY 11206, USA',
        'lat' => 40.700000, 'lng' => -73.939000,
        'emoji' => '🏙️',
        'tags' => ['Brooklyn', 'Bushwick', 'Event Space'],
        'description' => 'Bushwick rooftop event venue.',
    ],

    // Added from Jane's Walk venue mapping (2026-04-28)
    [
        'name' => "St. Patrick's Cathedral",
        'address' => '460 Madison Ave, New York, NY 10022, USA',
        'lat' => 40.758612, 'lng' => -73.976195,
        'emoji' => '⛪',
        'tags' => ['Manhattan', 'Midtown Manhattan', 'Religion', 'Landmark'],
        'description' => 'Iconic Gothic Revival Roman Catholic cathedral on Fifth Avenue in Midtown Manhattan.',
    ],

    // Added from Partiful event investigation (2026-04-28)
    [
        'name' => 'Tashca',
        'address' => '151 Elizabeth St, New York, NY 10012, USA',
        'lat' => 40.720422, 'lng' => -73.995289,
        'emoji' => '🎨',
        'tags' => ['Manhattan', 'Nolita', 'Art', 'Event Space'],
        'description' => 'Nolita event space hosting paint-and-sip nights, pop-ups, and creative gatherings.',
    ],
    [
        'name' => 'Radio Star',
        'address' => '13 Greenpoint Ave, Brooklyn, NY 11222, USA',
        'lat' => 40.729796, 'lng' => -73.960159,
        'emoji' => '🍻',
        'tags' => ['Brooklyn', 'Greenpoint', 'Bar'],
        'description' => 'Greenpoint bar and event venue.',
    ],

    // Added from /fix-unmapped-events investigation (2026-04-28)
    [
        'name' => 'Tusten Theatre',
        'address' => '210 Bridge St, Narrowsburg, NY 12764, USA',
        'lat' => 41.608597, 'lng' => -75.059244,
        'emoji' => '🎬',
        'tags' => ['Hudson Valley', 'Sullivan County', 'Theater', 'Cinema'],
        'description' => 'Historic theater in Narrowsburg, NY hosting films, concerts, and community events.',
    ],
    [
        'name' => 'Riker Hill Art Park',
        'address' => '276 Beaufort Ave, Livingston, NJ 07039, USA',
        'lat' => 40.810210, 'lng' => -74.327220,
        'emoji' => '🎨',
        'tags' => ['New Jersey', 'Essex County', 'Art', 'Park'],
        'description' => 'Essex County art park housed in former Cold War-era Nike missile barracks, featuring artist studios and exhibitions.',
    ],
    [
        'name' => 'Brookdale Park',
        'address' => 'Brookdale Park, Bloomfield, NJ 07003, USA',
        'lat' => 40.834677, 'lng' => -74.192855,
        'emoji' => '🌳',
        'tags' => ['New Jersey', 'Essex County', 'Park'],
        'description' => 'Large Essex County park spanning Bloomfield and Montclair, with athletic fields, gardens, and event lawns.',
    ],
    [
        'name' => 'Mahlon Dickerson Reservation',
        'address' => '955 Weldon Rd, Lake Hopatcong, NJ 07849, USA',
        'lat' => 41.013353, 'lng' => -74.569510,
        'emoji' => '🥾',
        'tags' => ['New Jersey', 'Morris County', 'Park', 'Hiking'],
        'description' => 'Morris County\'s largest park with hiking trails, camping, and the highest point in the county.',
    ],
    [
        'name' => 'Irene Habernickel Family Park',
        'address' => '1037 Hillcrest Rd, Ridgewood, NJ 07450, USA',
        'lat' => 41.005173, 'lng' => -74.128033,
        'emoji' => '🌳',
        'tags' => ['New Jersey', 'Bergen County', 'Park'],
        'description' => 'Ridgewood community park with trails, gardens, and nature programs.',
    ],
    [
        'name' => 'The Viscardi Center',
        'address' => '201 I.U. Willets Rd, Albertson, NY 11507, USA',
        'lat' => 40.768849, 'lng' => -73.657475,
        'emoji' => '🎓',
        'tags' => ['Long Island', 'Nassau County', 'Education', 'Disability'],
        'description' => 'Long Island center providing education and services for people with disabilities.',
    ],
    [
        'name' => 'Long Beach Public Library',
        'address' => '111 W Park Ave, Long Beach, NY 11561, USA',
        'lat' => 40.588870, 'lng' => -73.667539,
        'emoji' => '📚',
        'tags' => ['Long Island', 'Nassau County', 'Library'],
        'description' => 'Public library in Long Beach, Long Island.',
    ],
    [
        'name' => 'Lolita NYC',
        'short_name' => 'Lolita',
        'address' => '266 Broome St, New York, NY 10002, USA',
        'lat' => 40.718311, 'lng' => -73.990543,
        'emoji' => '🍸',
        'tags' => ['Manhattan', 'Lower East Side', 'Bar'],
        'description' => 'Lower East Side cocktail bar with a lively neighborhood vibe.',
    ],
    [
        'name' => 'The Maybury',
        'address' => '224 Smith St, Brooklyn, NY 11231, USA',
        'lat' => 40.684135, 'lng' => -73.992498,
        'emoji' => '🍻',
        'tags' => ['Brooklyn', 'Carroll Gardens', 'Bar'],
        'description' => 'Carroll Gardens cocktail bar on Smith Street.',
    ],
    [
        'name' => 'The Earl',
        'address' => '233 Cumberland St, Brooklyn, NY 11205, USA',
        'lat' => 40.688954, 'lng' => -73.972780,
        'emoji' => '🍻',
        'tags' => ['Brooklyn', 'Fort Greene', 'Bar'],
        'description' => 'Fort Greene neighborhood bar.',
    ],
    [
        'name' => 'Silver Lining Lounge',
        'address' => '75 Murray St, New York, NY 10007, USA',
        'lat' => 40.714818, 'lng' => -74.010687,
        'emoji' => '🍸',
        'tags' => ['Manhattan', 'Tribeca', 'Bar'],
        'description' => 'Tribeca lounge with cocktails and live entertainment.',
    ],
    [
        'name' => 'Gratin',
        'address' => '105 1st Ave, New York, NY 10003, USA',
        'lat' => 40.726837, 'lng' => -73.986375,
        'emoji' => '🍽️',
        'tags' => ['Manhattan', 'East Village', 'Restaurant'],
        'description' => 'East Village restaurant on 1st Avenue.',
    ],
    [
        'name' => "Ryan's Daughter",
        'address' => '350 E 85th St, New York, NY 10028, USA',
        'lat' => 40.776291, 'lng' => -73.950478,
        'emoji' => '🍻',
        'tags' => ['Manhattan', 'Upper East Side', 'Bar', 'Irish'],
        'description' => 'Upper East Side Irish pub on 85th Street.',
    ],
    [
        'name' => 'Sutton Tower',
        'address' => '430 E 58th St, New York, NY 10022, USA',
        'lat' => 40.758293, 'lng' => -73.961267,
        'emoji' => '🏢',
        'tags' => ['Manhattan', 'Sutton Place', 'Building'],
        'description' => 'Luxury residential tower in Sutton Place, Manhattan.',
    ],
    [
        'name' => 'ModernHaus SoHo',
        'address' => '27 Grand St, New York, NY 10013, USA',
        'lat' => 40.722736, 'lng' => -74.004699,
        'emoji' => '🏨',
        'tags' => ['Manhattan', 'SoHo', 'Hotel'],
        'description' => 'Boutique hotel in SoHo with rooftop and event spaces.',
    ],
    [
        'name' => 'The Lighthouse at Chelsea Piers',
        'short_name' => 'The Lighthouse',
        'address' => 'Pier 61, 23rd St & Hudson River Park, New York, NY 10011, USA',
        'lat' => 40.747355, 'lng' => -74.008369,
        'emoji' => '🏛️',
        'tags' => ['Manhattan', 'Chelsea', 'Event Space'],
        'description' => 'Event venue at Chelsea Piers Pier 61, frequently hosting galas and large benefit events.',
    ],

    // Added from Dykes & Dolls / gayagenda.nyc cross-reference (2026-04-27)
    [
        'name' => 'MADabolic Brooklyn',
        'address' => '211 N 11th St, Brooklyn, NY 11211, USA',
        'lat' => 40.718941, 'lng' => -73.953091,
        'emoji' => '💪',
        'tags' => ['Brooklyn', 'Williamsburg', 'Gym', 'Sports'],
        'description' => 'Strength and conditioning gym in Williamsburg offering interval-based group classes.',
    ],
    [
        'name' => "Ray's",
        'short_name' => "Ray's",
        'address' => '177 Chrystie St, New York, NY 10002, USA',
        'lat' => 40.721182, 'lng' => -73.992504,
        'emoji' => '🍻',
        'tags' => ['Manhattan', 'Lower East Side', 'Bar', 'LGBTQ'],
        'description' => 'Lower East Side neighborhood dive bar known as a queer-friendly hangout with cold beer, cocktails, and bar food.',
    ],
    [
        'name' => 'Superfine',
        'address' => '126 Front St, Brooklyn, NY 11201, USA',
        'lat' => 40.702373, 'lng' => -73.987507,
        'emoji' => '🍻',
        'tags' => ['Brooklyn', 'DUMBO', 'Bar', 'Restaurant'],
        'description' => 'Long-running DUMBO bar and restaurant with live music, bluegrass brunch, and a pool table.',
    ],
    [
        'name' => 'Dayglow',
        'address' => '8 Wilson Ave, Brooklyn, NY 11237, USA',
        'lat' => 40.703544, 'lng' => -73.930970,
        'emoji' => '☕',
        'tags' => ['Brooklyn', 'Bushwick', 'Coffee Shop'],
        'description' => 'Specialty coffee shop in Bushwick known for rotating roasters from around the world.',
    ],
    [
        'name' => 'Cicchetti BK',
        'address' => '185 Howard Ave, Brooklyn, NY 11233, USA',
        'lat' => 40.681939, 'lng' => -73.919649,
        'emoji' => '🍷',
        'tags' => ['Brooklyn', 'Bed-Stuy', 'Bar', 'LGBTQ'],
        'description' => 'Queer-owned Venetian wine bar in Bed-Stuy/Ocean Hill with weekly Thursgay aperitivo nights and small plates.',
    ],
    [
        'name' => 'Sunset Stoop',
        'address' => '4114 5th Ave, Brooklyn, NY 11232, USA',
        'lat' => 40.649875, 'lng' => -74.005573,
        'emoji' => '🍻',
        'tags' => ['Brooklyn', 'Sunset Park', 'Bar', 'Music'],
        'description' => 'Sunset Park bar and music venue with a backyard hosting karaoke, salsa, comedy, and trivia nights.',
    ],
    [
        'name' => 'Lambda Lounge',
        'address' => '2256 Adam Clayton Powell Jr Blvd, New York, NY 10027, USA',
        'lat' => 40.814034, 'lng' => -73.945144,
        'emoji' => '🍻',
        'tags' => ['Manhattan', 'Harlem', 'Bar', 'LGBTQ'],
        'description' => 'Black-owned LGBTQ+ lounge in Harlem with neon-lit decor, signature vodka, and bottle service in a sofa-laden space.',
    ],
    // Cafe Erzulie already exists (ID 1088) — skipping
    [
        'name' => 'Loreley Beer Garden',
        'short_name' => 'Loreley',
        'address' => '7 Rivington St, New York, NY 10002, USA',
        'lat' => 40.721230, 'lng' => -73.992872,
        'emoji' => '🍺',
        'tags' => ['Manhattan', 'Lower East Side', 'Bar', 'Beer Garden'],
        'description' => 'Lower East Side German beer garden with a large outdoor space and rotating drafts.',
    ],
    [
        'name' => 'Paradise Factory',
        'address' => '64 E 4th St, New York, NY 10003, USA',
        'lat' => 40.726449, 'lng' => -73.990629,
        'emoji' => '🎭',
        'tags' => ['Manhattan', 'East Village', 'Theater', 'Performance'],
        'description' => 'East Village performance venue hosting plays, readings, and experimental theater.',
    ],
    [
        'name' => 'City Coffee & Bar',
        'address' => '914 Columbus Ave, New York, NY 10025, USA',
        'lat' => 40.798515, 'lng' => -73.963710,
        'emoji' => '☕',
        'tags' => ['Manhattan', 'Upper West Side', 'Coffee Shop', 'Bar'],
        'description' => 'Upper West Side cafe and bar serving coffee by day and cocktails by night, hosting community mixers.',
    ],
    [
        'name' => 'Fulton Grand',
        'address' => '1011 Fulton St, Brooklyn, NY 11238, USA',
        'lat' => 40.682507, 'lng' => -73.961446,
        'emoji' => '🍻',
        'tags' => ['Brooklyn', 'Clinton Hill', 'Bar'],
        'description' => 'Clinton Hill neighborhood bar with a backyard, board games, and a regular event calendar.',
    ],
    [
        'name' => 'Shy Shy',
        'address' => '169 8th Ave, New York, NY 10011, USA',
        'lat' => 40.742702, 'lng' => -74.000760,
        'emoji' => '🍸',
        'tags' => ['Manhattan', 'Chelsea', 'Bar', 'Cocktails'],
        'description' => 'Chelsea cocktail bar from the Jungle Bird team, evoking a coastal hideaway with botanical cocktails and Pacific Northwest small plates.',
    ],
    [
        'name' => 'Winnie Said',
        'address' => '1624 Amsterdam Ave, New York, NY 10031, USA',
        'lat' => 40.823011, 'lng' => -73.949355,
        'emoji' => '🍺',
        'tags' => ['Manhattan', 'Hamilton Heights', 'Bar'],
        'description' => 'Hamilton Heights beer bar hosting community mixers and networking events.',
    ],
    [
        'name' => 'We Are Here Studios',
        'address' => '563 Johnson Ave Floor 2, Brooklyn, NY 11237, USA',
        'lat' => 40.709347, 'lng' => -73.924807,
        'emoji' => '🎙️',
        'tags' => ['Brooklyn', 'Bushwick', 'Studio', 'Performance'],
        'description' => 'Bushwick creative studio and event space hosting performances, parties, and community gatherings.',
    ],
    [
        'name' => 'Upsoul Center',
        'address' => '141 W 28th St #301, New York, NY 10001, USA',
        'lat' => 40.746954, 'lng' => -73.992432,
        'emoji' => '🧘',
        'tags' => ['Manhattan', 'Chelsea', 'Wellness'],
        'description' => 'Chelsea holistic wellness center offering massage, reiki, sound healing, breathwork, and workshops.',
    ],
    [
        'name' => 'Ligaw',
        'address' => '87 Ludlow St, New York, NY 10002, USA',
        'lat' => 40.718349, 'lng' => -73.989494,
        'emoji' => '🍸',
        'tags' => ['Manhattan', 'Lower East Side', 'Bar', 'Cocktails'],
        'description' => 'Lower East Side cocktail bar from World\'s Best Mixologist Katrina Sobredilla, with French-Filipino inspired drinks and women-made wines.',
    ],
    [
        'name' => '148 Frost Street',
        'short_name' => '148 Frost',
        'address' => '148 Frost St, Brooklyn, NY 11211, USA',
        'lat' => 40.717796, 'lng' => -73.945543,
        'emoji' => '🎭',
        'tags' => ['Brooklyn', 'Williamsburg', 'Performance', 'Music'],
        'description' => 'Williamsburg event space hosting music, burlesque, and performance art events.',
    ],
    // Older batches below (kept for reference, will be no-ops since already in DB)
    // Added from BetaNYC civictech newsletter cross-reference (2026-04-27)
    [
        'name' => 'Pfizer Auditorium at NYU Tandon',
        'short_name' => 'Pfizer Auditorium',
        'address' => '5 MetroTech Center, Brooklyn, NY 11201, USA',
        'lat' => 40.694371, 'lng' => -73.986576,
        'emoji' => '🎤',
        'tags' => ['Brooklyn', 'Downtown Brooklyn', 'University', 'Auditorium'],
        'description' => 'Auditorium at NYU Tandon School of Engineering in Downtown Brooklyn, hosting lectures, conferences, demo days, and civic-tech events.',
    ],
    [
        'name' => 'Data Vandals Newsstand',
        'short_name' => 'Data Vandals',
        'address' => '51st St & Lexington Ave, New York, NY 10022, USA',
        'lat' => 40.757123, 'lng' => -73.971914,
        'emoji' => '📊',
        'tags' => ['Manhattan', 'Midtown East', 'Art', 'Civic Tech', 'Pop-Up'],
        'description' => 'Data-art kiosk on the downtown 6 train platform at 51st & Lexington, run by an art collective transforming civic data into interactive experiences. Open weekly Sundays 2-6pm.',
    ],
    [
        'name' => 'SVA MFA Interaction Design',
        'short_name' => 'SVA Interaction Design',
        'address' => '136 W 21st St, 3rd Floor, New York, NY 10011, USA',
        'lat' => 40.742146, 'lng' => -73.995516,
        'emoji' => '🎨',
        'tags' => ['Manhattan', 'Chelsea', 'University', 'Design'],
        'description' => 'Graduate program at the School of Visual Arts focused on interaction design, hosting talks, workshops, and convenings on design and technology.',
    ],
    // NYC City Hall already exists as location #2847 — use that for NYC Council hearing
    // Added from City Happenings cross-reference (2026-04-27)
    [
        'name' => 'ArtsClub',
        'address' => '311 E 3rd St, New York, NY 10009, USA',
        'lat' => 40.721224, 'lng' => -73.978940,
        'emoji' => '🎨',
        'tags' => ['Manhattan', 'East Village', 'Art', 'Workshop', 'Community'],
        'description' => 'East Village art studio and community space hosting weekend studio sessions, gallery crawls, wellness workshops, and creative classes.',
    ],
    [
        'name' => 'The Gem Saloon',
        'short_name' => 'Gem Saloon',
        'address' => '375 3rd Ave, New York, NY 10016, USA',
        'lat' => 40.741352, 'lng' => -73.981016,
        'emoji' => '🍻',
        'tags' => ['Manhattan', 'Murray Hill', 'Bar', 'Cocktails'],
        'description' => 'Modern American saloon in Murray Hill with a horseshoe bar, daily happy hour, weekend DJs, and bottomless brunch.',
    ],
    [
        'name' => "Annie's Blue Ribbon General Store",
        'short_name' => 'Blue Ribbon General Store',
        'address' => '232 5th Ave, Brooklyn, NY 11215, USA',
        'lat' => 40.675683, 'lng' => -73.981134,
        'emoji' => '🎁',
        'tags' => ['Brooklyn', 'Park Slope', 'Shop', 'Community'],
        'description' => 'General store in Park Slope hosting classes, happy hours, and community events in its retail space.',
    ],
    // Batch 7 — 2026-04-20, specific venues for generic-mapped/unmapped events
    [
        'name' => 'Edie Windsor SAGE Center',
        'short_name' => 'SAGE Center',
        'address' => '305 7th Ave 15th floor, New York, NY 10001, USA',
        'lat' => 40.746650, 'lng' => -73.993354,
        'emoji' => '🫱🏾‍🫲🏼',
        'tags' => ['Manhattan', 'Chelsea', 'LGBTQ', 'Community', 'Senior'],
        'description' => 'LGBTQ+ senior community center in Chelsea hosting arts programs, support groups, wellness activities, and social events for older adults.',
    ],
    [
        'name' => 'Kosciuszko Street Learning Garden',
        'short_name' => 'Kosciuszko Garden',
        'address' => 'Kosciuszko St, Brooklyn, NY 11221, USA',
        'lat' => 40.691800, 'lng' => -73.941181,
        'emoji' => '🌱',
        'tags' => ['Brooklyn', 'Bedford-Stuyvesant', 'Garden', 'Community'],
        'description' => 'Community learning garden in Bedford-Stuyvesant hosting volunteer days, gardening workshops, and environmental education events.',
    ],
    [
        'name' => 'Vesuvio Playground',
        'address' => '101 Thompson St, New York, NY 10012, USA',
        'lat' => 40.725362, 'lng' => -74.002621,
        'emoji' => '🌳',
        'tags' => ['Manhattan', 'SoHo', 'Park', 'Playground'],
        'description' => 'NYC Parks playground in SoHo hosting community volunteer days and neighborhood events.',
    ],
    [
        'name' => 'College Point Fields',
        'address' => '130th St, Flushing, NY 11354, USA',
        'lat' => 40.777747, 'lng' => -73.837627,
        'emoji' => '🌳',
        'tags' => ['Queens', 'College Point', 'Park'],
        'description' => 'NYC Parks athletic fields in College Point hosting community events, sports activities, and volunteer workdays.',
    ],
    [
        'name' => 'Hillside Dog Park',
        'address' => 'Vine St, Brooklyn, NY 11201, USA',
        'lat' => 40.701511, 'lng' => -73.994380,
        'emoji' => '🌳',
        'tags' => ['Brooklyn', 'Brooklyn Heights', 'Park', 'Dog Park'],
        'description' => 'NYC Parks dog park in Brooklyn Heights hosting community volunteer days and neighborhood events.',
    ],
    [
        'name' => 'Lincoln Park (Jersey City)',
        'short_name' => 'Lincoln Park JC',
        'address' => '1 County Rd 605, Jersey City, NJ 07304, USA',
        'lat' => 40.725243, 'lng' => -74.082826,
        'emoji' => '🌳',
        'tags' => ['New Jersey', 'Hudson County', 'Jersey City', 'Park'],
        'description' => 'Hudson County park in Jersey City hosting 5K runs, festivals, community events, and recreational activities.',
    ],
    [
        'name' => 'One Domino Square',
        'address' => '8 S 4th St, Brooklyn, NY 11249, USA',
        'lat' => 40.713375, 'lng' => -73.968224,
        'emoji' => '🏢',
        'tags' => ['Brooklyn', 'Williamsburg', 'Waterfront'],
        'description' => 'Mixed-use development at the Domino Sugar Refinery site in Williamsburg hosting events, workshops, and community gatherings.',
    ],
    [
        'name' => 'EmblemHealth Neighborhood Care Castle Hill',
        'short_name' => 'EmblemHealth Castle Hill',
        'address' => '450 Castle Hill Ave, Bronx, NY 10473, USA',
        'lat' => 40.816749, 'lng' => -73.847113,
        'emoji' => '🏥',
        'tags' => ['Bronx', 'Castle Hill', 'Community', 'Health'],
        'description' => 'Community health center in Castle Hill hosting wellness workshops, health education, and community support events.',
    ],
    [
        'name' => 'EmblemHealth Neighborhood Care Crown Heights',
        'short_name' => 'EmblemHealth Crown Heights',
        'address' => '546 Eastern Pkwy, Brooklyn, NY 11225, USA',
        'lat' => 40.669472, 'lng' => -73.950149,
        'emoji' => '🏥',
        'tags' => ['Brooklyn', 'Crown Heights', 'Community', 'Health'],
        'description' => 'Community health center in Crown Heights hosting wellness workshops, food distributions, and community support events.',
    ],
    [
        'name' => '80 Hanson Place',
        'short_name' => '80 Hanson',
        'address' => '80 Hanson Pl, Brooklyn, NY 11217, USA',
        'lat' => 40.685251, 'lng' => -73.974406,
        'emoji' => '🏢',
        'tags' => ['Brooklyn', 'Fort Greene', 'Arts', 'Coworking'],
        'description' => 'Arts and cultural building in Fort Greene housing arts organizations, hosting workshops, meetings, and community events.',
    ],
    [
        'name' => 'Serra by Birreria',
        'short_name' => 'Serra',
        'address' => '200 5th Ave, New York, NY 10010, USA',
        'lat' => 40.742018, 'lng' => -73.989906,
        'emoji' => '🍽️',
        'tags' => ['Manhattan', 'Flatiron', 'Dining', 'Rooftop', 'Italian'],
        'description' => 'Seasonally decorated rooftop restaurant atop Eataly Flatiron featuring Italian cuisine and themed pop-up dining experiences.',
    ],
    [
        'name' => 'The Junto: Attic Bar',
        'short_name' => 'The Junto',
        'address' => '68 Mercer St, Jersey City, NJ 07302, USA',
        'lat' => 40.718859, 'lng' => -74.045380,
        'emoji' => '🍹',
        'tags' => ['New Jersey', 'Hudson County', 'Jersey City', 'Bar', 'Nightlife'],
        'description' => 'Cocktail bar in Jersey City hosting jazz nights, community gatherings, and themed events.',
    ],
    [
        'name' => 'Paws Grocer',
        'address' => '490 Bergen St, Brooklyn, NY 11217, USA',
        'lat' => 40.680568, 'lng' => -73.974245,
        'emoji' => '🫱🏾‍🫲🏼',
        'tags' => ['Brooklyn', 'Park Slope', 'Community', 'Pet'],
        'description' => 'Pet grocer in Park Slope/Boerum Hill hosting cat and kitten adoption events and community pet programs.',
    ],
    [
        'name' => 'Plainfield Performing Arts Center',
        'short_name' => 'Plainfield PAC',
        'address' => '724 Park Ave, Plainfield, NJ 07060, USA',
        'lat' => 40.617889, 'lng' => -74.417639,
        'emoji' => '🎭',
        'tags' => ['New Jersey', 'Union County', 'Plainfield', 'Theater', 'Performing Arts'],
        'description' => 'Community performing arts center in Plainfield hosting theater productions, concerts, and cultural programs.',
    ],
    [
        'name' => 'Showcase Cinema de Lux Cross County',
        'short_name' => 'Showcase Cross County',
        'address' => '2 South Dr, Yonkers, NY 10704, USA',
        'lat' => 40.924869, 'lng' => -73.854498,
        'emoji' => '🎬',
        'tags' => ['Westchester', 'Yonkers', 'Film'],
        'description' => 'Multiplex cinema at Cross County Shopping Center in Yonkers hosting film screenings, traveling exhibits, and special events.',
    ],
    [
        'name' => 'Fair Lawn Maurice M. Pine Library',
        'short_name' => 'Fair Lawn Library',
        'address' => '10-01 Fair Lawn Ave, Fair Lawn, NJ 07410, USA',
        'lat' => 40.936567, 'lng' => -74.131442,
        'emoji' => '📚',
        'tags' => ['New Jersey', 'Bergen County', 'Fair Lawn', 'Library'],
        'description' => 'Public library in Fair Lawn hosting early literacy programs, community events, and educational workshops.',
    ],
    [
        'name' => 'Hillsdale Free Public Library',
        'short_name' => 'Hillsdale Library',
        'address' => '509 Hillsdale Ave, Hillsdale, NJ 07642, USA',
        'lat' => 41.002393, 'lng' => -74.045901,
        'emoji' => '📚',
        'tags' => ['New Jersey', 'Bergen County', 'Hillsdale', 'Library'],
        'description' => 'Public library in Hillsdale hosting meditation clubs, community programs, and educational events.',
    ],
    [
        'name' => 'Wyckoff Public Library',
        'short_name' => 'Wyckoff Library',
        'address' => '200 Woodland Ave, Wyckoff, NJ 07481, USA',
        'lat' => 41.007373, 'lng' => -74.166387,
        'emoji' => '📚',
        'tags' => ['New Jersey', 'Bergen County', 'Wyckoff NJ', 'Library'],
        'description' => 'Public library in Wyckoff hosting sensory storytime, children\'s programs, and community events.',
    ],
    [
        'name' => 'Roseland Free Public Library',
        'short_name' => 'Roseland Library',
        'address' => '20 Roseland Ave, Roseland, NJ 07068, USA',
        'lat' => 40.823195, 'lng' => -74.291392,
        'emoji' => '📚',
        'tags' => ['New Jersey', 'Essex County', 'Roseland', 'Library'],
        'description' => 'Public library in Roseland hosting senior fitness programs, community events, and educational workshops.',
    ],
    [
        'name' => 'Ridgefield Park Public Library',
        'short_name' => 'Ridgefield Park Library',
        'address' => '107 Cedar St, Ridgefield Park, NJ 07660, USA',
        'lat' => 40.854331, 'lng' => -74.022120,
        'emoji' => '📚',
        'tags' => ['New Jersey', 'Bergen County', 'Ridgefield Park', 'Library'],
        'description' => 'Public library in Ridgefield Park hosting baby storytime, children\'s programs, and community events.',
    ],
    // Batch 6 — 2026-04-18, BCCLS NJ libraries for unmapped events
    [
        'name' => 'Bloomfield Public Library',
        'address' => '90 Broad St, Bloomfield, NJ 07003, USA',
        'lat' => 40.796646, 'lng' => -74.198112,
        'emoji' => '📚',
        'tags' => ['Library', 'New Jersey', 'Essex County', 'Bloomfield'],
        'description' => 'Public library in Bloomfield hosting workshops, community events, tax prep, and programs for all ages.',
    ],
    [
        'name' => 'Garfield Public Library',
        'address' => '500 Midland Ave, Garfield, NJ 07026, USA',
        'lat' => 40.880714, 'lng' => -74.100936,
        'emoji' => '📚',
        'tags' => ['Library', 'New Jersey', 'Bergen County', 'Garfield'],
        'description' => 'Public library in Garfield hosting community events, programs, and meetings for local residents.',
    ],
    [
        'name' => 'Haworth Municipal Library',
        'address' => '165 Stevens Pl, Haworth, NJ 07641, USA',
        'lat' => 40.959957, 'lng' => -73.988373,
        'emoji' => '📚',
        'tags' => ['Library', 'New Jersey', 'Bergen County', 'Haworth'],
        'description' => 'Municipal library in Haworth hosting community programs, kids events, and educational workshops.',
    ],
    [
        'name' => 'Montclair Public Library',
        'short_name' => 'Montclair Library',
        'address' => '50 S Fullerton Ave, Montclair, NJ 07042, USA',
        'lat' => 40.811574, 'lng' => -74.218632,
        'emoji' => '📚',
        'tags' => ['Library', 'New Jersey', 'Essex County', 'Montclair'],
        'description' => "Montclair's main public library hosting author talks, workshops, community programs, and cultural events.",
    ],
    [
        'name' => 'Nutley Free Public Library',
        'address' => '93 Booth Dr, Nutley, NJ 07110, USA',
        'lat' => 40.817186, 'lng' => -74.158781,
        'emoji' => '📚',
        'tags' => ['Library', 'New Jersey', 'Essex County', 'Nutley'],
        'description' => 'Public library in Nutley hosting educational programs, ESL classes, community events, and activities for all ages.',
    ],
    [
        'name' => 'Oakland Public Library',
        'address' => '2 Municipal Plaza, Oakland, NJ 07436, USA',
        'lat' => 41.023583, 'lng' => -74.244939,
        'emoji' => '📚',
        'tags' => ['Library', 'New Jersey', 'Bergen County', 'Oakland NJ'],
        'description' => "Public library in Oakland hosting children's programs, community events, and educational workshops.",
    ],
    [
        'name' => 'Old Tappan Public Library',
        'address' => '56 Russell Ave, Old Tappan, NJ 07675, USA',
        'lat' => 41.009870, 'lng' => -73.981558,
        'emoji' => '📚',
        'tags' => ['Library', 'New Jersey', 'Bergen County', 'Old Tappan'],
        'description' => 'Public library in Old Tappan hosting community programs, exercise classes, and cultural events.',
    ],
    [
        'name' => 'Ramsey Free Public Library',
        'address' => '30 Wyckoff Ave, Ramsey, NJ 07446, USA',
        'lat' => 41.055908, 'lng' => -74.146632,
        'emoji' => '📚',
        'tags' => ['Library', 'New Jersey', 'Bergen County', 'Ramsey'],
        'description' => 'Public library in Ramsey hosting book sales, community events, and programs for all ages.',
    ],
    [
        'name' => 'River Edge Public Library',
        'address' => '685 Elm Ave, River Edge, NJ 07661, USA',
        'lat' => 40.933214, 'lng' => -74.038455,
        'emoji' => '📚',
        'tags' => ['Library', 'New Jersey', 'Bergen County', 'River Edge'],
        'description' => "Public library in River Edge hosting LEGO clubs, children's programs, and community events.",
    ],
    // Batch 5 — 2026-04-17, added from pipeline run
    [
        'name' => 'Opus 40',
        'address' => '356 George Sickle Rd, Saugerties, NY 12477, USA',
        'lat' => 42.052380, 'lng' => -74.028155,
        'emoji' => '🗿',
        'tags' => ['Hudson Valley', 'Ulster County', 'Saugerties', 'Sculpture Park', 'Outdoor Art'],
        'description' => 'Monumental environmental sculpture and 60-acre landscape park in Saugerties, built by Harvey Fite over 37 years from bluestone. Hosts concerts, performances, community events, and tours on its terraced ramps and monoliths.',
    ],
    // Batch 4
    [
        'name' => 'Diversity Edible Farm Garden',
        'address' => '486 Linden Blvd, Brooklyn, NY 11203, USA',
        'lat' => 40.652948, 'lng' => -73.940927,
        'emoji' => '🌱', 'tags' => ['Brooklyn', 'East Flatbush', 'garden', 'community'],
        'description' => 'Community garden in East Flatbush hosting garden tours, volunteer workdays, and food justice programming.',
    ],
    // Batch 3 — specific venues identified from remaining unmapped events
    [
        'name' => 'H.E.S. Community Center',
        'short_name' => 'H.E.S.',
        'address' => '9502 Seaview Ave, Brooklyn, NY 11236, USA',
        'lat' => 40.632370, 'lng' => -73.890788,
        'emoji' => '🫱🏾‍🫲🏼', 'tags' => ['Brooklyn', 'Canarsie', 'community'],
        'description' => 'Community center in Canarsie hosting job fairs, youth programs, and neighborhood events.',
    ],
    [
        'name' => 'Triumph Brewing (Red Bank)',
        'short_name' => 'Triumph Brewing',
        'address' => '1 Bridge Ave, Red Bank, NJ 07701, USA',
        'lat' => 40.350130, 'lng' => -74.075051,
        'emoji' => '🍺', 'tags' => ['Live Music', 'dining'],
        'description' => 'Brewpub in Red Bank, NJ with live music, workshops, and community events.',
    ],
    [
        'name' => 'Apple Fifth Avenue',
        'address' => '767 5th Ave, New York, NY 10153, USA',
        'lat' => 40.763848, 'lng' => -73.972978,
        'emoji' => '💻', 'tags' => ['Manhattan', 'Midtown'],
        'description' => 'Flagship Apple Store with iconic glass cube entrance on Fifth Avenue, hosting events and meetups in the plaza.',
    ],
    // Batch 2 — venues for unmapped events, 2026-04-12
    [
        'name' => 'Hoboken Public Library',
        'address' => '500 Park Ave, Hoboken, NJ 07030, USA',
        'lat' => 40.742818, 'lng' => -74.032343,
        'emoji' => '📚', 'tags' => ['library', 'community'],
        'description' => 'Public library in Hoboken hosting comedy shows, teen programs, readings, and community events.',
    ],
    [
        'name' => 'Little City Books',
        'address' => '100 Bloomfield St, Hoboken, NJ 07030, USA',
        'lat' => 40.737751, 'lng' => -74.031966,
        'emoji' => '📚', 'tags' => ['literature', 'community'],
        'description' => 'Independent bookstore in Hoboken hosting author events, book clubs, and the annual Hoboken Literary Weekend.',
    ],
    [
        'name' => 'Fiction',
        'short_name' => 'Fiction BK',
        'address' => '308 Hooper St, Brooklyn, NY 11211, USA',
        'lat' => 40.707327, 'lng' => -73.953716,
        'emoji' => '🎷', 'tags' => ['Brooklyn', 'Williamsburg', 'Jazz', 'Live Music', 'nightlife'],
        'description' => 'Late-night jazz lounge and bar in Williamsburg with live jazz nightly and French bistro fare.',
    ],
    [
        'name' => "Abe's Pagoda Bar",
        'address' => '108 Wyckoff Ave, Brooklyn, NY 11237, USA',
        'lat' => 40.703926, 'lng' => -73.918827,
        'emoji' => '🍹', 'tags' => ['Brooklyn', 'Bushwick', 'bar', 'nightlife'],
        'description' => 'Tiki bar in Bushwick hosting live music, DJ nights, and release parties.',
    ],
    [
        'name' => 'Goose Garage',
        'address' => '238 Franklin St, Brooklyn, NY 11222, USA',
        'lat' => 40.733982, 'lng' => -73.958093,
        'emoji' => '🎸', 'tags' => ['Brooklyn', 'Greenpoint', 'Live Music'],
        'description' => 'Community music and event space in Greenpoint hosting live shows, DJ sets, and art events.',
    ],
    [
        'name' => 'Acoustik Garden Lounge',
        'address' => '1515 Atlantic Ave, Brooklyn, NY 11213, USA',
        'lat' => 40.678097, 'lng' => -73.938836,
        'emoji' => '🍹', 'tags' => ['Brooklyn', 'Crown Heights', 'bar', 'nightlife'],
        'description' => 'Lounge in Crown Heights hosting themed parties, DJ nights, and community events.',
    ],
    [
        'name' => 'La Marchande',
        'address' => '88 Wall St, New York, NY 10005, USA',
        'lat' => 40.705465, 'lng' => -74.007641,
        'emoji' => '🍽️', 'tags' => ['Manhattan', 'Financial District', 'dining'],
        'description' => 'French chophouse by Chef John Fraser at The Wall Street Hotel, hosting dining events and tastings.',
    ],
    [
        'name' => 'Heaven & Earth',
        'address' => '290 Nassau Ave, Brooklyn, NY 11222, USA',
        'lat' => 40.725943, 'lng' => -73.939139,
        'emoji' => '🍹', 'tags' => ['Brooklyn', 'Greenpoint', 'bar', 'nightlife'],
        'description' => 'Natural wine and cocktail bar in Greenpoint hosting community events and pop-ups.',
    ],
    [
        'name' => 'Bell Slip',
        'short_name' => 'The Bellslip',
        'address' => '1 Bell Slip, Brooklyn, NY 11222, USA',
        'lat' => 40.737348, 'lng' => -73.958652,
        'emoji' => '🎨', 'tags' => ['Brooklyn', 'Greenpoint', 'art'],
        'description' => 'Waterfront residential building in Greenpoint with a public lobby gallery hosting art exhibitions and screenings.',
    ],
    [
        'name' => 'Milk Bar',
        'address' => '1196 Broadway, New York, NY 10001, USA',
        'lat' => 40.745821, 'lng' => -73.988392,
        'emoji' => '🍰', 'tags' => ['Manhattan', 'NoMad', 'dining'],
        'description' => 'Christina Tosi\'s flagship bakery in NoMad, hosting pop-ups and brand collaboration events.',
    ],
    [
        'name' => 'Qahwah Valley',
        'address' => '630 1st Ave, New York, NY 10016, USA',
        'lat' => 40.745212, 'lng' => -73.972202,
        'emoji' => '☕', 'tags' => ['Manhattan', 'Murray Hill', 'cafe'],
        'description' => 'Yemeni coffee cafe in Murray Hill known for Adeni chai, hosting social meetups and community events.',
    ],
    [
        'name' => 'Karazishi Botan',
        'address' => '255 Smith St, Brooklyn, NY 11231, USA',
        'lat' => 40.683146, 'lng' => -73.992688,
        'emoji' => '🍱', 'tags' => ['Brooklyn', 'Carroll Gardens', 'dining'],
        'description' => 'Ramen restaurant in Carroll Gardens hosting food meetups and community dinners.',
    ],
    [
        'name' => 'Gumption Coffee',
        'address' => '940 Broadway, New York, NY 10010, USA',
        'lat' => 40.740767, 'lng' => -73.989128,
        'emoji' => '☕', 'tags' => ['Manhattan', 'Flatiron', 'cafe'],
        'description' => 'Australian specialty coffee roaster in the Flatiron District.',
    ],
    [
        'name' => "Ralph's Coffee",
        'address' => '888 Madison Ave, New York, NY 10021, USA',
        'lat' => 40.771659, 'lng' => -73.965766,
        'emoji' => '☕', 'tags' => ['Manhattan', 'Upper East Side', 'cafe'],
        'description' => 'Ralph Lauren\'s cafe at the Madison Avenue flagship, a popular social meetup spot.',
    ],
    [
        'name' => 'Lowry Triangle',
        'address' => 'Underhill Ave & Pacific St, Brooklyn, NY 11238, USA',
        'lat' => 40.680560, 'lng' => -73.964545,
        'emoji' => '🌳', 'tags' => ['Brooklyn', 'Prospect Heights', 'park'],
        'description' => 'Small triangular public park in Prospect Heights used for neighborhood markets and sidewalk sales.',
    ],
    [
        'name' => 'Nuar',
        'address' => '48 W 27th St, New York, NY 10001, USA',
        'lat' => 40.745029, 'lng' => -73.990356,
        'emoji' => '☕', 'tags' => ['Manhattan', 'NoMad', 'cafe'],
        'description' => 'Thai tea shop and dessert spot in NoMad hosting pop-ups and community events.',
    ],
    [
        'name' => 'Teatro LATEA',
        'address' => '107 Suffolk St, New York, NY 10002, USA',
        'lat' => 40.719155, 'lng' => -73.986263,
        'emoji' => '🎭', 'tags' => ['Manhattan', 'Lower East Side', 'theater'],
        'description' => 'Latino theater and performing arts venue inside The Clemente Soto Vélez Cultural Center on the LES.',
    ],
    [
        'name' => 'DADA',
        'address' => '60-47 Myrtle Ave, Ridgewood, NY 11385, USA',
        'lat' => 40.700798, 'lng' => -73.896652,
        'emoji' => '🍹', 'tags' => ['Queens', 'Ridgewood', 'bar', 'Live Music', 'art'],
        'description' => 'Artist-owned cocktail club and music venue in Ridgewood hosting live performances, poetry, and brunch.',
    ],
    [
        'name' => 'Jones Woods Park',
        'address' => '90 Robert Ln, Staten Island, NY 10301, USA',
        'lat' => 40.637084, 'lng' => -74.090593,
        'emoji' => '🌳', 'tags' => ['Staten Island', 'nature', 'park'],
        'description' => '17-acre nature preserve on Staten Island with unique Serpentine Barrens ecosystem and forest restoration programs.',
    ],
    [
        'name' => 'Mad Fun Farm',
        'address' => '1775 Third Ave, New York, NY 10029, USA',
        'lat' => 40.785752, 'lng' => -73.947919,
        'emoji' => '🌱', 'tags' => ['Manhattan', 'East Harlem', 'garden', 'community'],
        'description' => 'Urban farm in East Harlem run by Concrete Safaris, offering youth gardening programs and volunteer sessions.',
    ],
    [
        'name' => "Betty's Community Garden",
        'address' => '227 Hull St, Brooklyn, NY 11233, USA',
        'lat' => 40.680038, 'lng' => -73.907599,
        'emoji' => '🌱', 'tags' => ['Brooklyn', 'Ocean Hill', 'garden', 'community'],
        'description' => 'Community garden in Ocean Hill, Brooklyn hosting volunteer workdays and neighborhood events since 1992.',
    ],
    [
        'name' => 'PS/IS 78',
        'address' => '48-09 Center Blvd, Long Island City, NY 11109, USA',
        'lat' => 40.744465, 'lng' => -73.957666,
        'emoji' => '🏫', 'tags' => ['Queens', 'Long Island City', 'education'],
        'description' => 'Public school in Long Island City hosting community tree care and green events.',
    ],
    [
        'name' => 'PS 216 Arturo Toscanini School',
        'short_name' => 'PS 216',
        'address' => '350 Avenue X, Brooklyn, NY 11223, USA',
        'lat' => 40.590219, 'lng' => -73.969871,
        'emoji' => '🏫', 'tags' => ['Brooklyn', 'Gravesend', 'education'],
        'description' => 'Public school in Gravesend, Brooklyn hosting school garden and pollinator habitat workshops.',
    ],
    [
        'name' => 'Acacia Network Elmhurst Older Adults Center',
        'short_name' => 'Acacia Elmhurst',
        'address' => '75-01 Broadway, Elmhurst, NY 11373, USA',
        'lat' => 40.746437, 'lng' => -73.890145,
        'emoji' => '🫱🏾‍🫲🏼', 'tags' => ['Queens', 'Elmhurst', 'community'],
        'description' => 'Senior center in Elmhurst hosting concerts, classes, and community programs for older adults.',
    ],
    [
        'name' => 'Middlesex County Fairgrounds',
        'address' => '655 Cranbury Rd, East Brunswick, NJ 08816, USA',
        'lat' => 40.402592, 'lng' => -74.428140,
        'emoji' => '🎪', 'tags' => ['family'],
        'description' => 'Fairgrounds in East Brunswick, NJ hosting festivals, powwows, fairs, and large community events.',
    ],
    [
        'name' => 'PCCC Founders Theater',
        'short_name' => 'PCCC Founders',
        'address' => '1 College Blvd, Paterson, NJ 07505, USA',
        'lat' => 40.917911, 'lng' => -74.168768,
        'emoji' => '🎭', 'tags' => ['theater', 'education'],
        'description' => 'Performance theater at Passaic County Community College in Paterson, NJ hosting plays, concerts, and educational events.',
    ],
    [
        'name' => 'The Tidewater Center',
        'address' => '57 E Bridge St, Saugerties, NY 12477, USA',
        'lat' => 42.072463, 'lng' => -73.945466,
        'emoji' => '🎭', 'tags' => ['Hudson Valley', 'performing-arts'],
        'description' => 'Home of Arm-of-the-Sea Theater in Saugerties, hosting weekly Waterfront Wednesday performances and puppet theater.',
    ],
    [
        'name' => 'The Newkirk',
        'address' => '10 E Chestnut St, Kingston, NY 12401, USA',
        'lat' => 41.924770, 'lng' => -73.987680,
        'emoji' => '🎭', 'tags' => ['Hudson Valley', 'performing-arts', 'Live Music'],
        'description' => 'Historic 1856 performance venue in Kingston hosting jazz, wine tastings, and arts events.',
    ],
    [
        'name' => 'Brentwood High School',
        'address' => '2 6th Ave, Brentwood, NY 11717, USA',
        'lat' => 40.774382, 'lng' => -73.253396,
        'emoji' => '🏫', 'tags' => ['Long Island', 'education'],
        'description' => 'High school in Brentwood, Long Island hosting school district community events.',
    ],
    [
        'name' => 'Sushi Mambo',
        'address' => '431 W 202nd St, New York, NY 10034, USA',
        'lat' => 40.861142, 'lng' => -73.920295,
        'emoji' => '🍱', 'tags' => ['Manhattan', 'Inwood', 'dining'],
        'description' => 'Sushi restaurant in Inwood hosting pop-up events and community gatherings.',
    ],
    [
        'name' => 'Greenville',
        'address' => 'Greenville, Jersey City, NJ, USA',
        'lat' => 40.701780, 'lng' => -74.092460,
        'emoji' => '📍', 'tags' => ['neighborhood'],
        'description' => 'Southernmost neighborhood of Jersey City with historic sites and community walking tours.',
        'generic_location' => true,
    ],
    [
        'name' => 'Happyfun Hideaway',
        'address' => '1213 Myrtle Ave, Brooklyn, NY 11221, USA',
        'lat' => 40.697554, 'lng' => -73.931579,
        'emoji' => '🏳️‍🌈', 'tags' => ['nightlife', 'bar', 'queer', 'Brooklyn', 'Bushwick'],
        'description' => 'Queer bar and event space in Bushwick hosting drag shows, DJ nights, and community events.',
    ],
    [
        'name' => 'MIXI',
        'address' => '179 Livingston St, Brooklyn, NY 11201',
        'lat' => 40.690114, 'lng' => -73.986546,
        'emoji' => '🔬', 'tags' => ['education', 'tech'],
        'description' => 'Adelphi University research center in Downtown Brooklyn exploring STEM and the imagination through lectures, workshops, and conferences.',
    ],
    // NJ cultural locations added on 2026-04-07
    [
        'name' => 'Palisades Interstate Park',
        'address' => 'Palisades Interstate Park, Alpine, NJ 07620',
        'lat' => 40.955394, 'lng' => -73.919726,
        'emoji' => '🏔️', 'tags' => ['nature', 'hiking', 'parks'],
        'description' => 'Park along the Hudson River Palisades cliffs in NJ. Features hiking trails, scenic overlooks, boat basin, and seasonal events.',
    ],
    [
        'name' => 'Mayo Performing Arts Center',
        'address' => '100 South St, Morristown, NJ 07960',
        'lat' => 40.794397, 'lng' => -74.477899,
        'emoji' => '🎭', 'tags' => ['performing-arts', 'music', 'comedy', 'theater'],
        'description' => 'Major performing arts center in Morristown, NJ hosting concerts, comedy, theater, and family shows.',
    ],
    [
        'name' => 'Whippany Railway Museum',
        'address' => '1 Railroad Plaza, Whippany, NJ 07981',
        'lat' => 40.823272, 'lng' => -74.412284,
        'emoji' => '🚂', 'tags' => ['family', 'education'],
        'description' => 'Railway museum in Whippany, NJ offering seasonal train excursions and railroad history exhibits.',
    ],
    [
        'name' => 'Little Firehouse Theatre',
        'address' => '298 Kinderkamack Rd, Oradell, NJ 07649',
        'lat' => 40.950659, 'lng' => -74.032053,
        'emoji' => '🎭', 'tags' => ['theater', 'community'],
        'description' => 'Home of the Bergen County Players community theater in Oradell, NJ.',
    ],
    // NJ museum/park locations added on 2026-04-07
    [
        'name' => 'Morris Museum',
        'address' => '6 Normandy Heights Rd, Morristown, NJ 07960',
        'lat' => 40.796041, 'lng' => -74.448296,
        'emoji' => '🏛️', 'tags' => ['art', 'music', 'film', 'education'],
        'description' => 'Museum in Morristown, NJ with art exhibitions, concerts, film screenings, and educational workshops.',
    ],
    [
        'name' => 'Grounds for Sculpture',
        'address' => '80 Sculptors Way, Hamilton Township, NJ 08619',
        'lat' => 40.236778, 'lng' => -74.718891,
        'emoji' => '🗿', 'tags' => ['art', 'sculpture', 'nature', 'wellness'],
        'description' => 'Outdoor sculpture park and museum in Hamilton, NJ with art workshops, wine tastings, wellness programs, and gardens.',
    ],
    [
        'name' => 'New Jersey Botanical Garden',
        'address' => '5 Morris Rd, Ringwood, NJ 07456',
        'lat' => 41.125134, 'lng' => -74.238166,
        'emoji' => '🌺', 'tags' => ['nature', 'garden', 'family', 'hiking'],
        'description' => 'Botanical garden at Skylands in Ringwood, NJ (Passaic County). Features themed gardens, nature walks, manor house tours, and seasonal events.',
    ],
    // Hudson County locations added on 2026-04-06
    [
        'name' => 'Abake - Books & Cafe',
        'address' => '2 Webster Ave, Jersey City, NJ 07307',
        'lat' => 40.738518, 'lng' => -74.050323,
        'emoji' => '📚', 'tags' => ['community', 'literature'],
        'description' => 'Bookstore and cafe in Jersey City Heights hosting poetry readings, open mics, and literary events.',
    ],
    [
        'name' => 'American Dream',
        'address' => '1 American Dream Way, East Rutherford, NJ 07073',
        'lat' => 40.809129, 'lng' => -74.068567,
        'emoji' => '🎢', 'tags' => ['family', 'entertainment'],
        'description' => 'Mega entertainment and retail complex in the Meadowlands with theme parks, water park, skiing, and events.',
    ],
    [
        'name' => 'Bayonne Public Library',
        'address' => '697 Avenue C, Bayonne, NJ 07002',
        'lat' => 40.671704, 'lng' => -74.115694,
        'emoji' => '📚', 'tags' => ['community', 'education'],
        'description' => 'Public library in Bayonne, NJ with community events, lectures, and cultural programs.',
    ],
    [
        'name' => 'Camp Liberty',
        'address' => '300 Morris Pesin Dr, Jersey City, NJ 07305',
        'lat' => 40.699305, 'lng' => -74.064221,
        'emoji' => '🎨', 'tags' => ['art', 'family', 'community'],
        'description' => 'Arts and recreation facility in Liberty State Park, Jersey City. Hosts pottery workshops, art programs, and kids activities.',
    ],
    [
        'name' => 'Church Square Park',
        'address' => '400 Garden St, Hoboken, NJ 07030',
        'lat' => 40.742190, 'lng' => -74.032361,
        'emoji' => '🌳', 'tags' => ['parks', 'community'],
        'description' => 'Historic park in Hoboken with a gazebo, playground, and community events.',
    ],
    [
        'name' => 'Cunningham Branch Library',
        'address' => '275 Martin Luther King Dr, Jersey City, NJ 07305',
        'lat' => 40.708646, 'lng' => -74.081890,
        'emoji' => '📚', 'tags' => ['community', 'education'],
        'description' => 'Branch library in Jersey City hosting community programs and events.',
    ],
    [
        'name' => 'Grove Street PATH Plaza',
        'address' => 'Grove St, Jersey City, NJ 07302',
        'lat' => 40.725345, 'lng' => -74.042068,
        'emoji' => '🏙️', 'tags' => ['community'],
        'description' => 'Public plaza at the Grove Street PATH station in downtown Jersey City. Hosts farmers markets and community events.',
    ],
    [
        'name' => 'Harborside Atrium',
        'address' => '210 Hudson St, Jersey City, NJ 07302',
        'lat' => 40.719296, 'lng' => -74.033103,
        'emoji' => '🏢', 'tags' => ['community', 'nightlife'],
        'description' => 'Event space on the Jersey City waterfront hosting markets, food festivals, and community events.',
    ],
    [
        'name' => 'Casa Colombo',
        'address' => '380 Monmouth St, Jersey City, NJ 07302',
        'lat' => 40.722495, 'lng' => -74.049147,
        'emoji' => '🎨', 'tags' => ['art', 'community'],
        'description' => 'Italian Educational & Cultural Center in Jersey City hosting art exhibitions, cultural events, and community programs.',
    ],
    [
        'name' => 'Jersey City Theater Center',
        'address' => '165 Newark Ave, Jersey City, NJ 07302',
        'lat' => 40.720750, 'lng' => -74.045173,
        'emoji' => '🎭', 'tags' => ['theater', 'performing-arts'],
        'description' => 'Theater and performing arts venue in downtown Jersey City.',
    ],
    [
        'name' => 'Meadowlands Expo Center',
        'address' => '355 Plaza Dr, Secaucus, NJ 07094',
        'lat' => 40.788238, 'lng' => -74.042358,
        'emoji' => '🏟️', 'tags' => ['entertainment', 'community'],
        'description' => 'Convention and expo center in Secaucus, NJ hosting conventions, trade shows, and special events.',
    ],
    [
        'name' => 'Mile Square Theatre',
        'address' => '1400 Clinton St, Hoboken, NJ 07030',
        'lat' => 40.754293, 'lng' => -74.030694,
        'emoji' => '🎭', 'tags' => ['theater', 'performing-arts', 'comedy'],
        'description' => 'Professional theater company in Hoboken producing plays, readings, and comedy events.',
    ],
    [
        'name' => 'Nimbus Arts Center',
        'address' => '329 Warren St, Jersey City, NJ 07302',
        'lat' => 40.719485, 'lng' => -74.038703,
        'emoji' => '💃', 'tags' => ['dance', 'performing-arts'],
        'description' => 'Dance and performing arts center in Jersey City offering classes, performances, and community events.',
    ],
    [
        'name' => 'Hudson Riverfront Performing Arts Center',
        'address' => '1200 Harbor Blvd, Weehawken, NJ 07086',
        'lat' => 40.760555, 'lng' => -74.023127,
        'emoji' => '🎭', 'tags' => ['performing-arts', 'music'],
        'description' => 'Performing arts venue on the Hudson River waterfront in Weehawken, NJ.',
    ],
    // Union County locations added on 2026-04-06
    [
        'name' => 'Beacon Unitarian Universalist Congregation',
        'address' => '4 Waldron Ave, Summit, NJ 07901',
        'lat' => 40.718484,
        'lng' => -74.354415,
        'emoji' => '⛪',
        'tags' => ['community', 'music'],
        'description' => 'Unitarian Universalist congregation in Summit, NJ hosting community events and concerts.',
    ],
    [
        'name' => 'Black Brook Park',
        'address' => '341 N 19th St, Kenilworth, NJ 07033',
        'lat' => 40.684027,
        'lng' => -74.295041,
        'emoji' => '🌳',
        'tags' => ['parks'],
        'description' => 'Union County park in Kenilworth, NJ with baseball fields, fishing, soccer, and softball.',
    ],
    [
        'name' => 'CDC Theatre',
        'address' => '78 Winans Ave, Cranford, NJ 07016',
        'lat' => 40.651098,
        'lng' => -74.293252,
        'emoji' => '🎭',
        'tags' => ['theater', 'community'],
        'description' => 'Community theater in Cranford, NJ presenting classic and contemporary productions.',
    ],
    [
        'name' => 'Cranford Community Center',
        'address' => '220 Walnut Ave, Cranford, NJ 07016',
        'lat' => 40.651868,
        'lng' => -74.304263,
        'emoji' => '🏛️',
        'tags' => ['community'],
        'description' => 'Community center in Cranford, NJ hosting events, meetings, and performances.',
    ],
    [
        'name' => 'Crescent Avenue Presbyterian Church',
        'address' => '716 Watchung Ave, Plainfield, NJ 07060',
        'lat' => 40.616811,
        'lng' => -74.414742,
        'emoji' => '⛪',
        'tags' => ['music', 'community'],
        'description' => 'Historic church in Plainfield, NJ hosting concerts and community events.',
    ],
    [
        'name' => 'Edison Intermediate School',
        'address' => '800 Rahway Ave, Westfield, NJ 07090',
        'lat' => 40.638147,
        'lng' => -74.342551,
        'emoji' => '🏫',
        'tags' => ['music', 'community'],
        'description' => 'Westfield school auditorium used for community band concerts and events.',
    ],
    [
        'name' => 'Galloping Hill Golf Course',
        'address' => '3 Golf Dr, Kenilworth, NJ 07033',
        'lat' => 40.684436,
        'lng' => -74.276342,
        'emoji' => '⛳',
        'tags' => ['sports', 'community'],
        'description' => 'Union County golf course in Kenilworth, NJ also hosting community events and conferences.',
    ],
    [
        'name' => 'Hillside Public Library',
        'address' => '1409 Liberty Ave, Hillside, NJ 07205',
        'lat' => 40.701117,
        'lng' => -74.228775,
        'emoji' => '📚',
        'tags' => ['community', 'education'],
        'description' => 'Public library in Hillside, NJ with community programs and events.',
    ],
    [
        'name' => 'Kenilworth Public Library',
        'address' => '548 Boulevard, Kenilworth, NJ 07033',
        'lat' => 40.676502,
        'lng' => -74.290298,
        'emoji' => '📚',
        'tags' => ['community', 'education'],
        'description' => 'Public library in Kenilworth, NJ with community programs and cultural events.',
    ],
    [
        'name' => 'Melao Cafe & Creamery',
        'address' => '1425 Irving St, Rahway, NJ 07065',
        'lat' => 40.606377,
        'lng' => -74.275561,
        'emoji' => '☕',
        'tags' => ['community'],
        'description' => 'Cafe in Rahway, NJ hosting community events and gatherings.',
    ],
    [
        'name' => 'Overlook Medical Center',
        'address' => '99 Beauvoir Ave, Summit, NJ 07901',
        'lat' => 40.712794,
        'lng' => -74.353632,
        'emoji' => '🏥',
        'tags' => ['community', 'wellness'],
        'description' => 'Medical center in Summit, NJ hosting wellness programs and community events.',
    ],
    [
        'name' => 'Peterstown Community Center',
        'address' => '418 Palmer St, Elizabeth, NJ 07202',
        'lat' => 40.652818,
        'lng' => -74.207585,
        'emoji' => '🏛️',
        'tags' => ['community', 'art'],
        'description' => 'Community center in Elizabeth, NJ hosting art programs and community events.',
    ],
    [
        'name' => 'The Cranford Theater',
        'address' => '25 N Ave W, Cranford, NJ 07016',
        'lat' => 40.655754,
        'lng' => -74.306141,
        'emoji' => '🎬',
        'tags' => ['film', 'community'],
        'description' => 'Historic movie theater in downtown Cranford, NJ showing films and hosting community screenings.',
    ],
    [
        'name' => 'Union County College',
        'address' => '1033 Springfield Ave, Cranford, NJ 07016',
        'lat' => 40.667895,
        'lng' => -74.319633,
        'emoji' => '🎓',
        'tags' => ['education', 'art', 'community'],
        'description' => 'Community college in Cranford, NJ with art exhibits, performances, and community events.',
    ],
    [
        'name' => 'Rahway River Park',
        'address' => 'St Georges Ave, Rahway, NJ 07065',
        'lat' => 40.618550,
        'lng' => -74.280844,
        'emoji' => '🌳',
        'tags' => ['parks'],
        'description' => 'Union County park along the Rahway River with sports fields, playgrounds, and community events.',
    ],
    [
        'name' => 'Trailside Nature & Science Center',
        'address' => '452 New Providence Rd, Mountainside, NJ 07092',
        'lat' => 40.683919,
        'lng' => -74.372678,
        'emoji' => '🌿',
        'tags' => ['nature', 'education', 'family', 'hiking'],
        'description' => 'Nature and science center in the Watchung Reservation, Union County NJ. Offers nature programs, hiking, workshops, and the annual Wild Earth Fest.',
    ],
    [
        'name' => 'Warinanco Park',
        'address' => 'Warinanco Park, Roselle, NJ 07036',
        'lat' => 40.655507,
        'lng' => -74.240713,
        'emoji' => '🌳',
        'tags' => ['parks', 'sports', 'family'],
        'description' => 'Union County park in Roselle/Elizabeth with ice skating, sports fields, playgrounds, and community events.',
    ],
    [
        'name' => 'Union County Performing Arts Center',
        'address' => '1601 Irving St, Rahway, NJ 07065',
        'lat' => 40.610564,
        'lng' => -74.276592,
        'emoji' => '🎭',
        'tags' => ['performing-arts', 'theater', 'music', 'family'],
        'description' => 'Performing arts center in Rahway, NJ hosting theater, ballet, concerts, comedy, and sensory-friendly shows.',
    ],
    [
        'name' => 'Watchung Reservation',
        'address' => 'Watchung Reservation, Mountainside, NJ 07092',
        'lat' => 40.681663,
        'lng' => -74.381135,
        'emoji' => '🥾',
        'tags' => ['nature', 'hiking', 'parks'],
        'description' => 'Large nature reserve in Union County NJ with hiking trails, nature programs, and the Trailside Nature & Science Center.',
    ],
    [
        'name' => 'Codey Arena',
        'address' => '560 Northfield Ave, West Orange, NJ 07052',
        'lat' => 40.769412,
        'lng' => -74.281961,
        'emoji' => '⛸️',
        'tags' => ['ice-skating', 'hockey', 'sports'],
        'description' => 'Essex County ice skating arena in West Orange, NJ. Offers public skating, learn-to-skate classes, hockey programs, and special events.',
    ],
    [
        'name' => 'Essex County Environmental Center',
        'address' => '621 Eagle Rock Ave, Roseland, NJ 07068',
        'lat' => 40.825433,
        'lng' => -74.331801,
        'emoji' => '🌿',
        'tags' => ['nature', 'education', 'family'],
        'description' => 'Nature education center in Roseland, NJ. Offers nature camps, field trips, environmental programs, and community events for families and children.',
    ],
    // Additional locations for unmapped events — 2026-04-12
    [
        'name' => '6th Street and Avenue B Community Garden',
        'short_name' => '6BC Garden',
        'address' => 'Avenue B & E 6th St, New York, NY 10009, USA',
        'lat' => 40.724497, 'lng' => -73.981639,
        'emoji' => '🌱', 'tags' => ['Manhattan', 'East Village', 'garden', 'community'],
        'description' => 'Community garden in the East Village, part of the Loisaida Green Corridor, with diverse plantings and community events.',
    ],
    [
        'name' => 'Gallery Space LES',
        'address' => '155 Suffolk St, New York, NY 10002, USA',
        'lat' => 40.720890, 'lng' => -73.985569,
        'emoji' => '🎨', 'tags' => ['Manhattan', 'Lower East Side', 'art'],
        'description' => 'Event and gallery space on the Lower East Side hosting wine fairs, art shows, and pop-up events.',
    ],
    [
        'name' => 'BPC Community Center',
        'short_name' => 'BPC Community Center',
        'address' => '200 Rector Pl, New York, NY 10280, USA',
        'lat' => 40.708369, 'lng' => -74.016797,
        'emoji' => '🫱🏾‍🫲🏼', 'tags' => ['Manhattan', 'Battery Park City', 'community'],
        'description' => 'Battery Park City community center at 200 Rector Place hosting arts, music, and wellness programs.',
    ],
    [
        'name' => 'Upper Saddle River Public Library',
        'address' => '245 Lake St, Upper Saddle River, NJ 07458, USA',
        'lat' => 41.059550, 'lng' => -74.094040,
        'emoji' => '📚', 'tags' => ['library'],
        'description' => 'Public library in Upper Saddle River, NJ with wellness programs, book clubs, and community events.',
    ],
    [
        'name' => 'West Caldwell Public Library',
        'address' => '30 Clinton Rd, West Caldwell, NJ 07006, USA',
        'lat' => 40.850765, 'lng' => -74.293479,
        'emoji' => '📚', 'tags' => ['library'],
        'description' => 'Public library in West Caldwell, NJ offering tax prep, book clubs, and community programs.',
    ],
    [
        'name' => 'St. Agnes Church',
        'address' => '143 E 43rd St, New York, NY 10017, USA',
        'lat' => 40.751879, 'lng' => -73.974767,
        'emoji' => '⛪', 'tags' => ['Manhattan', 'Midtown', 'music'],
        'description' => 'Roman Catholic church in Midtown Manhattan hosting classical and early music concerts in its sanctuary.',
    ],
    [
        'name' => "Udall's Cove Park Preserve",
        'address' => 'Little Neck Pkwy & 34th Ave, Douglaston, NY 11363, USA',
        'lat' => 40.772838, 'lng' => -73.744621,
        'emoji' => '🌳', 'tags' => ['Queens', 'Douglaston', 'nature', 'park'],
        'description' => 'Tidal wetlands preserve in northeast Queens with nature walks, birding, and environmental education programs.',
    ],
    // Locations added on 2026-04-12 — batch fix for unmapped events
    [
        'name' => 'Thomas Greene Playground',
        'address' => '225 Nevins St, Brooklyn, NY 11217, USA',
        'lat' => 40.680280, 'lng' => -73.985231,
        'emoji' => '🌳', 'tags' => ['Brooklyn', 'Gowanus', 'park'],
        'description' => 'Public playground and park in Gowanus, Brooklyn, hosting community festivals and outdoor events.',
    ],
    [
        'name' => 'The Paris Theater',
        'address' => '4 W 58th St, New York, NY 10019, USA',
        'lat' => 40.763761, 'lng' => -73.974292,
        'emoji' => '🎬', 'tags' => ['Manhattan', 'Midtown', 'film'],
        'description' => 'Historic single-screen movie theater near Central Park, now operated by Netflix for special screenings and premieres.',
    ],
    [
        'name' => 'Jackson Square',
        'address' => 'Greenwich Ave & 8th Ave, New York, NY 10014, USA',
        'lat' => 40.738968, 'lng' => -74.002846,
        'emoji' => '🌳', 'tags' => ['Manhattan', 'West Village', 'park'],
        'description' => 'Small triangular park in the West Village, used as a meeting point for walking tours and community gatherings.',
    ],
    [
        'name' => 'Madison Avenue Presbyterian Church',
        'address' => '921 Madison Ave, New York, NY 10021, USA',
        'lat' => 40.772576, 'lng' => -73.964674,
        'emoji' => '⛪', 'tags' => ['Manhattan', 'Upper East Side', 'music'],
        'description' => 'Historic Upper East Side church hosting concerts, recitals, and community events in its landmark sanctuary.',
    ],
    [
        'name' => 'Little Bay Park',
        'address' => 'Little Bay Park, Queens, NY, USA',
        'lat' => 40.790183, 'lng' => -73.785057,
        'emoji' => '🌳', 'tags' => ['Queens', 'Whitestone', 'park', 'nature'],
        'description' => 'Waterfront park in northeast Queens with trails, sports fields, and views of the Throgs Neck Bridge.',
    ],
    [
        'name' => 'Sherman Creek Park',
        'address' => '351 W 205th St, New York, NY 10034, USA',
        'lat' => 40.861996, 'lng' => -73.917044,
        'emoji' => '🌳', 'tags' => ['Manhattan', 'Inwood', 'park', 'nature'],
        'description' => 'Waterfront park on the Harlem River in Inwood with kayak launch, ecological restoration areas, and educational programs.',
    ],
    [
        'name' => 'Fraser Square Park',
        'address' => 'Kings Hwy & Avenue M, Brooklyn, NY 11234, USA',
        'lat' => 40.619962, 'lng' => -73.941243,
        'emoji' => '🌳', 'tags' => ['Brooklyn', 'Flatlands', 'park'],
        'description' => 'Small neighborhood park in Flatlands, Brooklyn used for community gardening and habitat restoration events.',
    ],
    [
        'name' => 'Secaucus Public Library',
        'address' => '1379 Paterson Plank Rd, Secaucus, NJ 07094, USA',
        'lat' => 40.794023, 'lng' => -74.059165,
        'emoji' => '📚', 'tags' => ['library'],
        'description' => 'Public library in Secaucus, NJ offering programs, movie screenings, and community events.',
    ],
    [
        'name' => 'Franklin Lakes Public Library',
        'address' => '470 De Korte Dr, Franklin Lakes, NJ 07417, USA',
        'lat' => 41.018698, 'lng' => -74.198401,
        'emoji' => '📚', 'tags' => ['library'],
        'description' => 'Public library in Franklin Lakes, NJ with children\'s programs, crafts, and community events.',
    ],
    [
        'name' => 'Glen Ridge Free Public Library',
        'address' => '240 Ridgewood Ave, Glen Ridge, NJ 07028, USA',
        'lat' => 40.801366, 'lng' => -74.203713,
        'emoji' => '📚', 'tags' => ['library'],
        'description' => 'Public library in Glen Ridge, NJ hosting book clubs, plant swaps, and community programs.',
    ],
    [
        'name' => 'Cresskill Public Library',
        'address' => '53 Union Ave, Cresskill, NJ 07626, USA',
        'lat' => 40.941982, 'lng' => -73.960361,
        'emoji' => '📚', 'tags' => ['library'],
        'description' => 'Public library in Cresskill, NJ with storytime, children\'s programs, and community events.',
    ],
    [
        'name' => 'Johnson Public Library',
        'short_name' => 'Johnson Library',
        'address' => '274 Main St, Hackensack, NJ 07601, USA',
        'lat' => 40.886730, 'lng' => -74.040753,
        'emoji' => '📚', 'tags' => ['library'],
        'description' => 'Main public library in Hackensack, NJ with music programs, cultural events, and children\'s activities.',
    ],
    [
        'name' => 'Palisades Park Public Library',
        'address' => '257 2nd St, Palisades Park, NJ 07650, USA',
        'lat' => 40.846967, 'lng' => -73.996922,
        'emoji' => '📚', 'tags' => ['library'],
        'description' => 'Public library in Palisades Park, NJ serving a diverse community with multilingual programs and events.',
    ],
    [
        'name' => 'River Vale Public Library',
        'address' => '412 Rivervale Rd, River Vale, NJ 07675, USA',
        'lat' => 41.008410, 'lng' => -74.008801,
        'emoji' => '📚', 'tags' => ['library'],
        'description' => 'Public library in River Vale, NJ with craft groups, book clubs, and community programs.',
    ],
    [
        'name' => 'Wallington Veterans Memorial Library',
        'address' => '125 Main Ave, Wallington, NJ 07057, USA',
        'lat' => 40.855173, 'lng' => -74.112541,
        'emoji' => '📚', 'tags' => ['library'],
        'description' => 'Public library in Wallington, NJ with take-home crafts, children\'s programs, and community events.',
    ],
    [
        'name' => 'Rutherford Free Public Library',
        'address' => '150 Park Ave, Rutherford, NJ 07070, USA',
        'lat' => 40.826706, 'lng' => -74.106614,
        'emoji' => '📚', 'tags' => ['library'],
        'description' => 'Public library in Rutherford, NJ hosting book sales, author talks, and community programs.',
    ],
    [
        'name' => 'Allaire State Park',
        'address' => '4265 Atlantic Ave, Wall Township, NJ 07727, USA',
        'lat' => 40.159157, 'lng' => -74.131817,
        'emoji' => '🌳', 'tags' => ['nature', 'park', 'family'],
        'description' => 'State park in Wall Township, NJ featuring the Historic Village at Allaire, nature trails, and seasonal family events.',
    ],
    [
        'name' => 'Cheesequake State Park',
        'address' => '300 Gordon Rd, Matawan, NJ 07747, USA',
        'lat' => 40.439748, 'lng' => -74.269223,
        'emoji' => '🌳', 'tags' => ['nature', 'park', 'hiking'],
        'description' => 'State park in Matawan, NJ with diverse ecosystems, hiking trails, and guided nature programs.',
    ],
    [
        'name' => 'Monmouth Battlefield State Park',
        'address' => '20 NJ-33 Business, Manalapan Township, NJ 07726, USA',
        'lat' => 40.263683, 'lng' => -74.320358,
        'emoji' => '🏛️', 'tags' => ['history', 'park', 'nature'],
        'description' => 'Revolutionary War battlefield site with a visitor center, hiking trails, and historical lectures and events.',
    ],
    [
        'name' => 'The Hermitage',
        'address' => '335 Franklin Turnpike, Ho-Ho-Kus, NJ 07423, USA',
        'lat' => 41.007122, 'lng' => -74.117783,
        'emoji' => '🏛️', 'tags' => ['history', 'museum'],
        'description' => 'National Historic Landmark in Ho-Ho-Kus, NJ with tours, lectures, and events spanning colonial to Victorian eras.',
    ],
    [
        'name' => 'New York-New Jersey Trail Conference',
        'short_name' => 'NY-NJ Trail Conference',
        'address' => '600 Ramapo Valley Rd, Mahwah, NJ 07430, USA',
        'lat' => 41.079606, 'lng' => -74.184339,
        'emoji' => '🥾', 'tags' => ['nature', 'hiking'],
        'description' => 'Trail conservation organization headquartered in Mahwah, NJ hosting workshops, volunteer workdays, and hiking programs.',
    ],
    [
        'name' => 'Belmont Lake State Park',
        'address' => '625 Belmont Ave, West Babylon, NY 11704, USA',
        'lat' => 40.736317, 'lng' => -73.340328,
        'emoji' => '🌳', 'tags' => ['Long Island', 'nature', 'park', 'family'],
        'description' => 'State park on Long Island with fishing, nature trails, playgrounds, and seasonal outdoor events.',
    ],
    [
        'name' => 'Highlawn Pavilion',
        'address' => '1 Crest Dr, West Orange, NJ 07052, USA',
        'lat' => 40.804324, 'lng' => -74.237454,
        'emoji' => '🍽️', 'tags' => ['dining'],
        'description' => 'Upscale restaurant in Eagle Rock Reservation with panoramic views of the NYC skyline, hosting galas and special events.',
    ],
    [
        'name' => 'Patchen Community Square Garden',
        'address' => '868 Putnam Ave, Brooklyn, NY 11221, USA',
        'lat' => 40.686484, 'lng' => -73.927055,
        'emoji' => '🌱', 'tags' => ['Brooklyn', 'Bed-Stuy', 'garden', 'community'],
        'description' => 'Community garden in Bed-Stuy, Brooklyn hosting art events, workshops, and neighborhood gatherings.',
    ],
    [
        'name' => 'John J. Carty Park',
        'address' => 'Fort Hamilton Pkwy, Brooklyn, NY 11209, USA',
        'lat' => 40.613508, 'lng' => -74.029788,
        'emoji' => '🌳', 'tags' => ['Brooklyn', 'Bay Ridge', 'park'],
        'description' => 'Neighborhood park in Bay Ridge, Brooklyn with playgrounds and sports facilities.',
    ],
    [
        'name' => 'ELOREA',
        'address' => '37 Orchard St, New York, NY 10002, USA',
        'lat' => 40.715886, 'lng' => -73.991545,
        'emoji' => '🎨', 'tags' => ['Manhattan', 'Lower East Side', 'art'],
        'description' => 'Korean fragrance brand with a Lower East Side retail space hosting art exhibitions and cultural events.',
    ],
    [
        'name' => 'Welcome to Chinatown',
        'address' => '115 Bowery, New York, NY 10002, USA',
        'lat' => 40.717918, 'lng' => -73.994786,
        'emoji' => '🎨', 'tags' => ['Manhattan', 'Chinatown', 'art', 'community'],
        'description' => 'Community space on the Bowery supporting Chinatown through art exhibitions, cultural events, and small business advocacy.',
    ],
    [
        'name' => 'PYO Chai',
        'address' => '28-23 Steinway St, Long Island City, NY 11103, USA',
        'lat' => 40.764695, 'lng' => -73.913914,
        'emoji' => '☕', 'tags' => ['Queens', 'Astoria', 'cafe'],
        'description' => 'South Asian chai cafe in Astoria serving fresh-brewed chai and snacks, hosting pop-ups and community events.',
    ],
    [
        'name' => 'Starchild Rooftop Bar & Lounge',
        'address' => '305 W 48th St, New York, NY 10036, USA',
        'lat' => 40.761421, 'lng' => -73.987442,
        'emoji' => '🍹', 'tags' => ['Manhattan', 'Midtown', 'nightlife', 'bar'],
        'description' => 'Rooftop bar and lounge in Hell\'s Kitchen with skyline views, hosting DJ nights and seasonal events.',
    ],
    [
        'name' => 'El Barrio Community Garden',
        'address' => '415 E 117th St, New York, NY 10035, USA',
        'lat' => 40.796483, 'lng' => -73.934050,
        'emoji' => '🌱', 'tags' => ['Manhattan', 'East Harlem', 'garden', 'community'],
        'description' => 'Community garden in East Harlem hosting volunteer workdays, educational programs, and neighborhood events.',
    ],
    [
        'name' => 'Bronx River Community Garden',
        'address' => '1086 E 180th St, Bronx, NY 10460, USA',
        'lat' => 40.841953, 'lng' => -73.876547,
        'emoji' => '🌱', 'tags' => ['Bronx', 'garden', 'community'],
        'description' => 'Community garden along the Bronx River Greenway hosting garden tours, bicycle tours, and environmental education.',
    ],
    [
        'name' => 'NYU Silver School of Social Work',
        'short_name' => 'NYU Silver',
        'address' => '1 Washington Square N, New York, NY 10003, USA',
        'lat' => 40.730885, 'lng' => -73.995624,
        'emoji' => '🎓', 'tags' => ['Manhattan', 'Greenwich Village', 'education'],
        'description' => 'NYU\'s school of social work at Washington Square, hosting lectures, panel discussions, and academic events.',
    ],
    [
        'name' => 'Respective HQ',
        'address' => '456 Johnson Ave Suite 204, Brooklyn, NY 11237, USA',
        'lat' => 40.707964, 'lng' => -73.929791,
        'emoji' => '💻', 'tags' => ['Brooklyn', 'Bushwick', 'tech', 'art'],
        'description' => 'Creative studio and event space in Bushwick hosting art shows, screenings, and community gatherings.',
    ],
    [
        'name' => 'Historic Hudson Valley',
        'address' => '639 Bedford Rd, Sleepy Hollow, NY 10591, USA',
        'lat' => 41.085652, 'lng' => -73.858468,
        'emoji' => '🏛️', 'tags' => ['Hudson Valley', 'history', 'family'],
        'description' => 'Historic sites in the Hudson Valley including Kykuit, Philipsburg Manor, and Van Cortlandt Manor, hosting tours, festivals, and seasonal events.',
    ],
    [
        'name' => 'Grace Lutheran Church of Brooklyn',
        'address' => '936 Bushwick Ave, Brooklyn, NY 11221, USA',
        'lat' => 40.692096, 'lng' => -73.927460,
        'emoji' => '⛪', 'tags' => ['Brooklyn', 'Bushwick', 'music'],
        'description' => 'Church in Bushwick hosting opera performances, concerts, and community arts events.',
    ],
    [
        'name' => 'SUPR OMEN',
        'address' => '113 Thompson St, New York, NY 10012, USA',
        'lat' => 40.726001, 'lng' => -74.001959,
        'emoji' => '🎨', 'tags' => ['Manhattan', 'SoHo', 'art'],
        'description' => 'Creative space in SoHo hosting interdisciplinary workshops, performances, and art events.',
    ],
    [
        'name' => '15th Street Friends Meetinghouse',
        'short_name' => '15th St Meetinghouse',
        'address' => '15 Rutherford Pl, New York, NY 10003, USA',
        'lat' => 40.735060, 'lng' => -73.986230,
        'emoji' => '🕊️', 'tags' => ['Manhattan', 'Gramercy', 'community'],
        'description' => 'Quaker meetinghouse near Stuyvesant Square hosting worship, community meetings, and social justice events.',
    ],
    // Brooklyn Bookstore Crawl 2026 participating bookstores (2026-04-20)
    [
        'name' => 'Adanne Bookshop',
        'address' => '115 Ralph Ave, Brooklyn, NY 11221, USA',
        'lat' => 40.686080, 'lng' => -73.923088,
        'emoji' => '📚',
        'tags' => ['Brooklyn', 'Bed-Stuy', 'Bookstore', 'Independent', 'Black-Owned'],
        'description' => 'Black-owned independent bookshop in Bed-Stuy hosting author readings, workshops, and community literary events.',
    ],
    [
        'name' => 'BEM | books & more',
        'address' => '373 Lewis Ave, Brooklyn, NY 11233, USA',
        'lat' => 40.682683, 'lng' => -73.934725,
        'emoji' => '📚',
        'tags' => ['Brooklyn', 'Bed-Stuy', 'Bookstore', 'Independent', 'Black-Owned'],
        'description' => 'Independent Bed-Stuy bookshop and cultural space showcasing books, art, and design by Black creators alongside community programming.',
    ],
    [
        'name' => 'Cafe con Libros',
        'address' => '724 Prospect Pl, Brooklyn, NY 11216, USA',
        'lat' => 40.674291, 'lng' => -73.952579,
        'emoji' => '📚',
        'tags' => ['Brooklyn', 'Crown Heights', 'Bookstore', 'Independent', 'Feminist', 'Cafe'],
        'description' => 'Intersectional feminist bookstore and cafe in Crown Heights hosting book clubs, author talks, and community gatherings.',
    ],
    [
        'name' => 'Mil Mundos Books',
        'address' => '323 Linden St, Brooklyn, NY 11237, USA',
        'lat' => 40.698699, 'lng' => -73.914394,
        'emoji' => '📚',
        'tags' => ['Brooklyn', 'Bushwick', 'Bookstore', 'Independent', 'Bilingual', 'Latinx'],
        'description' => 'Bilingual (Spanish/English) independent bookstore in Bushwick hosting readings, workshops, and Latinx literary and cultural events.',
    ],
    [
        'name' => 'Freebird Books',
        'address' => '123 Columbia St, Brooklyn, NY 11231, USA',
        'lat' => 40.687424, 'lng' => -74.001352,
        'emoji' => '📚',
        'tags' => ['Brooklyn', 'Columbia Waterfront', 'Bookstore', 'Independent', 'Used Books'],
        'description' => 'Used bookstore on the Columbia Waterfront specializing in New York City titles and hosting occasional readings and community events.',
    ],
    [
        'name' => 'Powerhouse Arena',
        'address' => '28 Adams St, Brooklyn, NY 11201, USA',
        'lat' => 40.702977, 'lng' => -73.988765,
        'emoji' => '📚',
        'tags' => ['Brooklyn', 'DUMBO', 'Bookstore', 'Independent'],
        'description' => 'DUMBO flagship bookstore and event space hosting author readings, book launches, panel discussions, and literary parties.',
    ],
    [
        'name' => 'leaves used bookstore',
        'address' => '140 Nassau Ave, Brooklyn, NY 11222, USA',
        'lat' => 40.724632, 'lng' => -73.947718,
        'emoji' => '📚',
        'tags' => ['Brooklyn', 'Greenpoint', 'Bookstore', 'Independent', 'Used Books'],
        'description' => 'Greenpoint used bookstore offering curated secondhand titles and occasional community literary events.',
    ],
    [
        'name' => 'The Little Bookshop',
        'address' => '239 Bushwick Ave, Brooklyn, NY 11206, USA',
        'lat' => 40.707929, 'lng' => -73.939733,
        'emoji' => '📚',
        'tags' => ['Brooklyn', 'Bushwick', 'Bookstore', 'Independent'],
        'description' => 'Small independent bookshop on Bushwick Ave hosting community book events and readings.',
    ],
    [
        'name' => "Quimby's Bookstore NYC",
        'address' => '536 Metropolitan Ave, Brooklyn, NY 11211, USA',
        'lat' => 40.713946, 'lng' => -73.950942,
        'emoji' => '📚',
        'tags' => ['Brooklyn', 'Williamsburg', 'Bookstore', 'Independent', 'Zines', 'Comics'],
        'description' => 'Williamsburg outpost of the legendary Chicago zine and underground comics shop, hosting readings, zine launches, and alternative literary events.',
    ],
    // 826NYC already exists as location 3513; added alternate name "Brooklyn Superhero Supply Co." instead
    [
        'name' => 'Love & Legends Books',
        'address' => '667 Washington Ave, Brooklyn, NY 11238, USA',
        'lat' => 40.677191, 'lng' => -73.963422,
        'emoji' => '📚',
        'tags' => ['Brooklyn', 'Prospect Heights', 'Bookstore', 'Independent', 'Romance'],
        'description' => 'Prospect Heights romance-focused independent bookstore hosting book clubs, author signings, and themed reader events.',
    ],
    [
        'name' => 'Powerhouse on 8th',
        'address' => '1111 8th Ave, Brooklyn, NY 11215, USA',
        'lat' => 40.664196, 'lng' => -73.980303,
        'emoji' => '📚',
        'tags' => ['Brooklyn', 'Park Slope', 'Bookstore', 'Independent', 'Kids'],
        'description' => 'Powerhouse Books\' Park Slope neighborhood shop focused on childrens and YA programming, with storytimes, book launches, and family events.',
    ],
    [
        'name' => 'Unnameable Books',
        'address' => '615 Vanderbilt Ave, Brooklyn, NY 11238, USA',
        'lat' => 40.678849, 'lng' => -73.968257,
        'emoji' => '📚',
        'tags' => ['Brooklyn', 'Prospect Heights', 'Bookstore', 'Independent', 'Used Books'],
        'description' => 'Prospect Heights independent bookstore known for deep fiction, poetry, and used-book selection, hosting poetry readings and launch events.',
    ],
    [
        'name' => 'The BookMark Shoppe',
        'address' => '8415 3rd Ave, Brooklyn, NY 11209, USA',
        'lat' => 40.624540, 'lng' => -74.030356,
        'emoji' => '📚',
        'tags' => ['Brooklyn', 'Bay Ridge', 'Bookstore', 'Independent'],
        'description' => 'Bay Ridge independent bookstore hosting author signings, release parties, Book Karaoke open mic nights, and family programming.',
    ],
    [
        'name' => "Here's A Book Store",
        'address' => '1964 Coney Island Ave, Brooklyn, NY 11223, USA',
        'lat' => 40.609260, 'lng' => -73.962456,
        'emoji' => '📚',
        'tags' => ['Brooklyn', 'Midwood', 'Bookstore', 'Independent', 'Used Books'],
        'description' => 'Longstanding independent bookstore on Coney Island Ave in Midwood offering new and used titles.',
    ],
    [
        'name' => 'Powerhouse at IC',
        'short_name' => 'Powerhouse @ IC',
        'address' => '220 36th St, Brooklyn, NY 11232, USA',
        'lat' => 40.656467, 'lng' => -74.006761,
        'emoji' => '📚',
        'tags' => ['Brooklyn', 'Sunset Park', 'Bookstore', 'Independent', 'Industry City'],
        'description' => 'Powerhouse Books\' Industry City location hosting storytimes, author events, and childrens and YA programming.',
    ],
    [
        'name' => 'Taylor & Co. Books',
        'address' => '1021 Cortelyou Rd, Brooklyn, NY 11218, USA',
        'lat' => 40.639606, 'lng' => -73.968376,
        'emoji' => '📚',
        'tags' => ['Brooklyn', 'Ditmas Park', 'Bookstore', 'Independent'],
        'description' => 'Ditmas Park neighborhood independent bookstore hosting author readings and community literary events.',
    ],
    [
        'name' => 'Woodlawn Cemetery',
        'address' => '4199 Webster Ave, Bronx, NY 10470, USA',
        'lat' => 40.888249, 'lng' => -73.872023,
        'emoji' => '🪦',
        'tags' => ['Bronx', 'Woodlawn', 'Cemetery', 'Historic', 'Tours', 'Outdoor'],
        'description' => 'Historic Bronx cemetery and National Historic Landmark with a Level II Arboretum, hosting public tours, trolley tours, and family programs highlighting notable residents and horticulture.',
    ],
    [
        'name' => 'Clinton Hall Bronx',
        'address' => '601 E 189th St, Bronx, NY 10458, USA',
        'lat' => 40.85739, 'lng' => -73.885694,
        'emoji' => '🍻',
        'tags' => ['Bronx', 'Belmont', 'Beer Bar', 'Pub', 'Trivia'],
        'description' => 'Bronx location of the Clinton Hall beer hall chain near Fordham, offering hard-to-find draft beers, burgers, and weekly trivia nights.',
    ],
    [
        'name' => 'Clinton Hall 36th Street',
        'address' => '16 W 36th St, New York, NY 10018, USA',
        'lat' => 40.750053, 'lng' => -73.984796,
        'emoji' => '🍻',
        'tags' => ['Manhattan', 'Midtown', 'Beer Bar', 'Pub', 'Trivia'],
        'description' => 'Midtown Manhattan location of the Clinton Hall beer hall chain, offering hard-to-find draft beers, burgers, and weekly trivia nights.',
    ],
    // Batch 2026-04-26 — off-site venues identified during mismap audit
    [
        'name' => 'Book Club Bar (Bushwick)',
        'short_name' => 'Book Club Bar Bushwick',
        'address' => '380 Troutman St, Brooklyn, NY 11237, USA',
        'lat' => 40.705891, 'lng' => -73.923400,
        'emoji' => '📚',
        'tags' => ['Brooklyn', 'Bushwick', 'Bar', 'Books', 'Literature'],
        'description' => 'Bushwick bookstore and bar hosting reading series, book clubs, author talks, and literary events alongside curated drinks.',
    ],
    [
        'name' => 'New York Studio Kitchen',
        'address' => '104 E 7th St, New York, NY 10009, USA',
        'lat' => 40.726475, 'lng' => -73.984999,
        'emoji' => '🍴',
        'tags' => ['Manhattan', 'East Village', 'Cooking', 'Workshop'],
        'description' => 'East Village studio kitchen hosting hands-on cooking classes, pastry workshops, and culinary events including programming by Atelier Sucré.',
    ],
    [
        'name' => 'East Midwood Jewish Center',
        'address' => '1625 Ocean Ave, Brooklyn, NY 11230, USA',
        'lat' => 40.622374, 'lng' => -73.955363,
        'emoji' => '🕍',
        'tags' => ['Brooklyn', 'Midwood', 'Synagogue', 'Community'],
        'description' => 'Conservative synagogue in Midwood serving as a community hub for Jewish religious services, cultural programs, and neighborhood meetings.',
    ],
    [
        'name' => 'Lisson Gallery',
        'address' => '508 W 24th St, New York, NY 10011, USA',
        'lat' => 40.748487, 'lng' => -74.004583,
        'emoji' => '🎨',
        'tags' => ['Manhattan', 'Chelsea', 'Art Gallery', 'Contemporary Art'],
        'description' => 'International contemporary art gallery in Chelsea showing established and emerging artists across painting, sculpture, photography, and new media.',
    ],
    [
        'name' => 'NYC Resistor',
        'address' => '87 3rd Ave, Brooklyn, NY 11217, USA',
        'lat' => 40.683611, 'lng' => -73.981667,
        'emoji' => '💻',
        'tags' => ['Brooklyn', 'Gowanus', 'Tech', 'Hackerspace', 'Workshop'],
        'description' => 'Brooklyn hackerspace and maker collective hosting electronics workshops, soldering classes, and technology meetups in a shared workshop environment.',
    ],
    [
        'name' => 'Pen + Brush',
        'address' => '29 E 22nd St, New York, NY 10010, USA',
        'lat' => 40.740149, 'lng' => -73.987824,
        'emoji' => '🎨',
        'tags' => ['Manhattan', 'Flatiron', 'Art Gallery', 'Literature'],
        'description' => 'Nonprofit organization in Flatiron supporting women in the arts and literature through exhibitions, readings, and public programs.',
    ],
    [
        'name' => 'Albert Einstein College of Medicine',
        'address' => '1300 Morris Park Ave, Bronx, NY 10461, USA',
        'lat' => 40.852357, 'lng' => -73.844296,
        'emoji' => '🏥',
        'tags' => ['Bronx', 'Morris Park', 'Education', 'Medicine'],
        'description' => 'Research medical school in the Bronx affiliated with Montefiore Health System, hosting academic lectures, public health events, and community programs across its Pelham Parkway campus.',
    ],
    // Added 2026-05-04 — venues surfaced by Posh organizer crawls (websites 4461-4478) that had
    // events but no matching DB location. Researched + verified by sub-agents.
    [
        'name' => 'Damballa',
        'description' => 'Brooklyn listening bar from the Cafe Erzulie team with a custom sound system, DJ sets blending Caribbean, reggae, and R&B classics, natural wine, and small plates.',
        'address' => '895 Broadway, Brooklyn, NY 11206, USA',
        'lat' => 40.6981183,
        'lng' => -73.9368944,
        'emoji' => '🍹',
        'tags' => ['Brooklyn', 'Bushwick', 'Latin', 'Bar', 'Nightlife'],
    ],
    [
        'name' => 'District 385',
        'description' => 'Three-floor Ridgewood tapas bar and lounge with chef-crafted small plates, signature cocktails, and weekend reggaeton/Latin DJ nights and live performances.',
        'address' => '57-36 Myrtle Ave, Ridgewood, NY 11385, USA',
        'lat' => 40.7002806,
        'lng' => -73.9022783,
        'emoji' => '🪩',
        'tags' => ['Queens', 'Ridgewood', 'Latin', 'Reggaeton', 'Dance Club'],
    ],
    [
        'name' => 'San Antonios',
        'description' => 'Lower East Side community bar with Latin-inspired cocktails, a lively dance floor, and DJs spinning reggaeton and Latin hits.',
        'address' => '247 Eldridge St, New York, NY 10002, USA',
        'lat' => 40.7228459,
        'lng' => -73.9898209,
        'emoji' => '🍹',
        'tags' => ['Manhattan', 'Lower East Side', 'Latin', 'Reggaeton', 'Bar'],
    ],
    [
        'name' => 'Zikrayat Restaurant & Lounge',
        'description' => 'Astoria Middle Eastern restaurant and lounge serving Lebanese and Mediterranean cuisine with a bar and late-night live entertainment including Latin/dembow events.',
        'address' => '24-17 Steinway St, Astoria, NY 11103, USA',
        'lat' => 40.7685467,
        'lng' => -73.9109632,
        'emoji' => '🍽️',
        'tags' => ['Queens', 'Astoria', 'Restaurant', 'Lounge', 'Live Music'],
    ],
    [
        'name' => 'Pier 78 at Hudson River Park',
        'description' => 'Hudson River departure pier for NYC boat parties and sightseeing cruises, featuring open-air decks, DJ sets, and Manhattan skyline views.',
        'address' => '455 12th Ave, New York, NY 10018, USA',
        'lat' => 40.759715,
        'lng' => -74.003970,
        'emoji' => '⛵',
        'tags' => ['Manhattan', "Hell's Kitchen", 'Outdoor', 'Boat', 'Nightlife'],
    ],
    [
        'name' => 'Creatures Rooftop',
        'description' => 'Rooftop bar and restaurant atop Hotel Almeda High Line in Chelsea, serving Mediterranean fare, cocktails, and live music with Empire State Building views.',
        'address' => '518 W 27th St, New York, NY 10001, USA',
        'lat' => 40.750413,
        'lng' => -74.003419,
        'emoji' => '🍹',
        'tags' => ['Manhattan', 'Chelsea', 'Rooftop', 'Bar', 'Restaurant'],
    ],
    [
        'name' => 'Bar 13',
        'description' => 'Two-floor Greenwich Village nightclub at 121 University Pl hosting Latin, reggaeton, salsa, bachata and dembow dance parties like Cabros Chicos.',
        'address' => '121 University Pl, New York, NY 10003, USA',
        'lat' => 40.734740,
        'lng' => -73.991888,
        'emoji' => '🪩',
        'tags' => ['Manhattan', 'Greenwich Village', 'Nightlife', 'Dance Club', 'Bar'],
    ],
    [
        'name' => 'Record Room',
        'description' => 'Hidden all-vinyl listening lounge in Long Island City behind Cafe by RR, known for craft cocktails, live music, and intimate dance nights.',
        'address' => '47-09 Center Blvd, Long Island City, NY 11109, USA',
        'lat' => 40.745821,
        'lng' => -73.956706,
        'emoji' => '🍹',
        'tags' => ['Queens', 'Long Island City', 'Bar', 'Live Music', 'Nightlife'],
    ],
    [
        'name' => 'Cafe Susanne',
        'description' => 'All-day cafe and bar on the Williamsburg waterfront at Domino Park, serving coffee, pastries, cocktails, and hosting community gatherings like run clubs.',
        'address' => '8 River St, Brooklyn, NY 11249, USA',
        'lat' => 40.713103,
        'lng' => -73.968200,
        'emoji' => '☕',
        'tags' => ['Brooklyn', 'Williamsburg', 'Cafe', 'Bar', 'Outdoor'],
    ],
    [
        'name' => 'The Ornate Studio',
        'description' => '4,400 sq ft industrial-chic duplex loft in Gowanus used for warehouse parties, weddings, and creative shoots; capacity up to 350.',
        'address' => '650 Sackett St, Brooklyn, NY 11217, USA',
        'lat' => 40.6781701,
        'lng' => -73.9835164,
        'emoji' => '🏭',
        'tags' => ['Brooklyn', 'Gowanus', 'Warehouse', 'Nightlife', 'Latin'],
    ],
    [
        'name' => 'Ritmos 60',
        'description' => 'Historic Colombian bar on Steinway St serving tapas, Guaro, and handcrafted cocktails with live salsa, vallenato, and reggaeton dancing.',
        'address' => '32-23 Steinway St, Astoria, NY 11103, USA',
        'lat' => 40.7584175,
        'lng' => -73.9192693,
        'emoji' => '🍹',
        'tags' => ['Queens', 'Astoria', 'Latin', 'Bar', 'Nightlife'],
    ],
    [
        'name' => 'Mi Casa Studios',
        'description' => 'Multi-purpose Lower East Side studio and event space hosting workshops, run club meetups, art shows, pop-ups, and private gatherings.',
        'address' => '70 Hester St, New York, NY 10002, USA',
        'lat' => 40.7159501,
        'lng' => -73.9915964,
        'emoji' => '🏭',
        'tags' => ['Manhattan', 'Lower East Side', 'Event Space', 'Community'],
    ],
    [
        'name' => 'Spring Place',
        'description' => 'Members-only creative club in Tribeca with 64,000 sq ft of coworking, restaurant, bar, and event programming including comedy and live music.',
        'address' => '6 St Johns Ln, New York, NY 10013, USA',
        'lat' => 40.7208609,
        'lng' => -74.0060942,
        'emoji' => '🏢',
        'tags' => ['Manhattan', 'Tribeca', 'Members Club', 'Coworking'],
    ],
    [
        'name' => 'The Ainsworth Brooklyn',
        'description' => 'Multi-purpose Bushwick venue blending restaurant, craft cocktail bar, lounge, and event space with R&B parties, brunch, and themed nightlife.',
        'address' => '2 Knickerbocker Ave, Brooklyn, NY 11237, USA',
        'lat' => 40.7074234,
        'lng' => -73.9319867,
        'emoji' => '🍹',
        'tags' => ['Brooklyn', 'Bushwick', 'Bar', 'Restaurant', 'Nightlife'],
    ],
    // Added 2026-05-04 — second-pass remaining orphan venues from Posh extractions.
    [
        'name' => 'Electrix Vintage',
        'description' => 'Permanent Brooklyn vintage clothing store hosting fill-a-bag sales, store openings, and curated vintage shopping events.',
        'address' => '103 Stuyvesant Ave, Brooklyn, NY 11221, USA',
        'lat' => 40.6920469,
        'lng' => -73.9337120,
        'emoji' => '🛍️',
        'tags' => ['Brooklyn', 'Bedford-Stuyvesant', 'Shop'],
    ],
    [
        'name' => '308 W 38th St',
        'description' => 'Garment District event space used for vintage pop-up sales and markets.',
        'address' => '308 W 38th St, New York, NY 10018, USA',
        'lat' => 40.7549112,
        'lng' => -73.9923397,
        'emoji' => '🏭',
        'tags' => ['Manhattan', 'Garment District', 'Event Space'],
    ],
    [
        'name' => '70 Scott Ave',
        'description' => 'East Williamsburg warehouse event space used for late-night electronic music and underground parties.',
        'address' => '70 Scott Ave, Brooklyn, NY 11237, USA',
        'lat' => 40.7098471,
        'lng' => -73.9224340,
        'emoji' => '🏭',
        'tags' => ['Brooklyn', 'East Williamsburg', 'Warehouse', 'Nightlife'],
    ],
    [
        'name' => '255 Randolph St',
        'description' => 'Bushwick warehouse event space hosting underground electronic music and immersive parties.',
        'address' => '255 Randolph St, Brooklyn, NY 11237, USA',
        'lat' => 40.7108584,
        'lng' => -73.9224288,
        'emoji' => '🏭',
        'tags' => ['Brooklyn', 'East Williamsburg', 'Warehouse', 'Nightlife'],
    ],
    [
        'name' => 'Mount Beacon Trailhead',
        'description' => 'Hudson Valley trailhead at the base of Mount Beacon, used as a meetup point for community hikes and outdoor group activities.',
        'address' => 'Mount Beacon Trailhead, Beacon, NY 12508, USA',
        'lat' => 41.4936558,
        'lng' => -73.9600475,
        'emoji' => '🥾',
        'tags' => ['Hudson Valley', 'Beacon', 'Outdoor', 'Hiking'],
    ],
    // Added 2026-05-04 — round-3 Posh organizer extractions (websites 4479-4503).
    [
        'name' => 'Skyport Marina',
        'description' => 'East River marina and departure point for NYC yacht parties (Cabana, Jewel, Harbor Lights, etc.) hosting nightly boat events.',
        'address' => '2430 FDR Dr, New York, NY 10010, USA',
        'lat' => 40.7355481,
        'lng' => -73.9744191,
        'emoji' => '⛵',
        'tags' => ['Manhattan', 'Stuyvesant Town', 'Outdoor', 'Boat'],
    ],
    [
        'name' => 'The Post BK',
        'description' => 'Renovated Greenpoint warehouse with indoor courts for open-play volleyball, basketball, pickleball, and futsal, plus rentals and leagues.',
        'address' => '100 Dobbin St, Brooklyn, NY 11222, USA',
        'lat' => 40.7251474,
        'lng' => -73.9544725,
        'emoji' => '🏃',
        'tags' => ['Brooklyn', 'Greenpoint', 'Sports', 'Indoor'],
    ],
    [
        'name' => 'Magic Hour Rooftop Bar & Lounge',
        'description' => 'NYC\'s largest indoor/outdoor rooftop bar atop Moxy Times Square (18th floor) with DJs, mini-golf, and Empire State Building views.',
        'address' => '485 7th Ave 18th floor, New York, NY 10018, USA',
        'lat' => 40.7524923,
        'lng' => -73.9893157,
        'emoji' => '🍹',
        'tags' => ['Manhattan', 'Midtown', 'Rooftop', 'Bar', 'Lounge'],
    ],
    [
        'name' => 'SAINT Resto-Lounge',
        'description' => 'Black-owned upscale Hell\'s Kitchen resto-lounge serving modern American cuisine and craft cocktails in an opulent, late-night setting.',
        'address' => '626B 10th Ave, New York, NY 10036, USA',
        'lat' => 40.7612101,
        'lng' => -73.9941161,
        'emoji' => '🍽️',
        'tags' => ['Manhattan', 'Hell\'s Kitchen', 'Restaurant', 'Lounge'],
    ],
    [
        'name' => 'Eden Nightclub',
        'description' => 'Midtown reggaeton and Latin nightclub with a main floor lounge and a darker, red-lit underground room; hosts Rompe and similar parties.',
        'address' => '20 W 36th St, New York, NY 10018, USA',
        'lat' => 40.7500975,
        'lng' => -73.9849826,
        'emoji' => '🪩',
        'tags' => ['Manhattan', 'Midtown', 'Nightclub', 'Dance Club'],
    ],
    [
        'name' => 'Elsie Penthouse',
        'description' => '25th-floor penthouse event space above Elsie Rooftop near Bryant Park, with skyline views and capacity for up to 600 guests.',
        'address' => '1412 Broadway, New York, NY 10018, USA',
        'lat' => 40.7537642,
        'lng' => -73.986739,
        'emoji' => '🏢',
        'tags' => ['Manhattan', 'Times Square', 'Garment District', 'Rooftop', 'Nightlife'],
    ],
    [
        'name' => 'Harbor NYC',
        'description' => "Hell's Kitchen rooftop nightclub and event space with a retractable glass roof and Hudson River views, open year-round.",
        'address' => '621 W 46th St, New York, NY 10036, USA',
        'lat' => 40.7640139,
        'lng' => -73.9976374,
        'emoji' => '🪩',
        'tags' => ['Manhattan', "Hell's Kitchen", 'Rooftop', 'Nightclub', 'Nightlife'],
    ],
    [
        'name' => 'LilliStar Rooftop at the Moxy Williamsburg',
        'description' => 'Indoor-outdoor rooftop cocktail bar on the 11th floor of Moxy Williamsburg with Asian-inspired small plates and skyline views.',
        'address' => '353 Bedford Ave, Brooklyn, NY 11211, USA',
        'lat' => 40.7117016,
        'lng' => -73.9628766,
        'emoji' => '🍹',
        'tags' => ['Brooklyn', 'Williamsburg', 'Rooftop', 'Bar', 'Nightlife'],
    ],
    [
        'name' => 'Lotus Rooftop',
        'description' => 'All-season rooftop lounge and hookah bar in Passaic with three floors, signature cocktails, and a NYC-style nightlife vibe.',
        'address' => '822 Main Ave Suite A, Passaic, NJ 07055, USA',
        'lat' => 40.8658465,
        'lng' => -74.130224,
        'emoji' => '🍹',
        'tags' => ['New Jersey', 'Passaic', 'Rooftop', 'Lounge', 'Nightlife'],
    ],
    // Added 2026-05-06 — venues needed to fix "Various / Multiple Venues" event splits.
    // Skinny Dennis (Whiskey Biscuits residency); Constantino Brumidi Lodge (Louis Del Prete dance party).
    // Mobile Unit "As You Like It" tour: Roy Wilkins Park (the actual park, distinct from
    // rec center loc 4752) and Prospect Park – The Peninsula (more specific than the generic
    // Prospect Park loc 682).
    // (Astor Place Cube, Saint Mary's Park, Sunset Park already in DB as locs 5053/1372/804.)
    [
        'name' => 'Skinny Dennis',
        'description' => 'Williamsburg honky-tonk bar with live country and Americana shows, no cover, and frequent residencies from local roots and bluegrass acts.',
        'address' => '152 Metropolitan Ave, Brooklyn, NY 11211, USA',
        'lat' => 40.71591, 'lng' => -73.96212,
        'emoji' => '🎸',
        'tags' => ['Brooklyn', 'Williamsburg', 'Bar', 'Live Music', 'Country'],
    ],
    [
        'name' => 'Constantino Brumidi Lodge',
        'description' => 'Sons of Italy lodge in Deer Park, Long Island, hosting community events, social dance parties, and Italian-American cultural programming.',
        'address' => '2075 Deer Park Ave, Deer Park, NY 11729, USA',
        'lat' => 40.77095, 'lng' => -73.33269,
        'emoji' => '💃',
        'tags' => ['Long Island', 'Deer Park', 'Community Center', 'Dance'],
    ],
    [
        'name' => 'Roy Wilkins Park',
        'description' => 'Major Southeast Queens park named for the civil rights leader, hosting summer concerts, festivals, and community events on its open lawns.',
        'address' => 'Roy Wilkins Park, Merrick Blvd, Jamaica, NY 11434, USA',
        'lat' => 40.68751, 'lng' => -73.77221,
        'emoji' => '🌳',
        'tags' => ['Queens', 'Jamaica', 'Park', 'Outdoor'],
    ],
    [
        'name' => 'Prospect Park – The Peninsula',
        'description' => 'Forested peninsula on the south end of Prospect Park\'s lake, accessed via Well House Dr; an outdoor performance site for Public Theater Mobile Unit and other free programming.',
        'address' => 'Well House Dr, Brooklyn, NY 11225, USA',
        'lat' => 40.65830, 'lng' => -73.96842,
        'emoji' => '🌳',
        'tags' => ['Brooklyn', 'Prospect Park', 'Park', 'Outdoor'],
    ],
    // 2026-05-09 — Nonsense NYC newsletter cross-reference. 5 venues that hosted listed events
    // but weren't yet in the DB. Geocoded via php scripts/geocode.php; proximity-checked.
    [
        'name' => 'Hendrick I. Lott House',
        'short_name' => 'Lott House',
        'description' => 'Historic 1720 Dutch farmhouse and museum in Marine Park, Brooklyn. Hosts educational programming and seasonal cultural events about Brooklyn\'s agricultural and waterfront history.',
        'address' => '1940 E 36th St, Brooklyn, NY 11234, USA',
        'lat' => 40.61030, 'lng' => -73.93258,
        'emoji' => '🏚️',
        'tags' => ['Brooklyn', 'Marine Park', 'Historic Site'],
    ],
    [
        'name' => 'Isabel Sullivan Gallery',
        'short_name' => 'IS-G',
        'description' => 'Tribeca contemporary art gallery hosting exhibitions and openings; also operates a Chelsea location at 501 W 23rd St.',
        'address' => '39 Lispenard St, New York, NY 10013, USA',
        'lat' => 40.71991, 'lng' => -74.00335,
        'emoji' => '🖼️',
        'tags' => ['Manhattan', 'Tribeca', 'Museum'],
    ],
    [
        'name' => 'Soho Live',
        'description' => '4,500 sq ft Manhattan concert hall (capacity 350, scaleable to 110) opened 2025 in the former Santos Party House space. Hosts hip-hop, indie bands, DJ sets, and themed dance parties. 21+.',
        'address' => '94 Lafayette St, New York, NY 10013, USA',
        'lat' => 40.71763, 'lng' => -74.00154,
        'emoji' => '🎶',
        'tags' => ['Manhattan', 'SoHo', 'Concert Hall'],
    ],
    [
        'name' => 'Acorn Craft Shop',
        'description' => 'Prospect Heights craft shop selling supplies and hosting hands-on workshops including portrait nights, knitting classes, mom\'s craft night, and collage workshops.',
        'address' => '727 Washington Ave, Brooklyn, NY 11238, USA',
        'lat' => 40.67509, 'lng' => -73.96305,
        'emoji' => '🛍️',
        'tags' => ['Brooklyn', 'Prospect Heights', 'Shop'],
    ],
    [
        'name' => 'Coucou French Classes',
        'short_name' => 'Coucou',
        'description' => 'French language school in SoHo offering group classes, workshops, and themed social events focused on French language and culture.',
        'address' => '253 Centre St 2nd and 3rd floor, New York, NY 10013, USA',
        'lat' => 40.72066, 'lng' => -73.99809,
        'emoji' => '🏫',
        'tags' => ['Manhattan', 'SoHo', 'School'],
    ],
    // 2026-05-11 — City Happenings newsletter cross-reference. Newly surfaced venues
    // and a Hudson Valley fairgrounds (in scope), plus a generic Brooklyn Heights
    // neighborhood row for citywide / block-party events.
    [
        'name' => 'The Bishop Gallery',
        'description' => 'Contemporary art gallery in the historic Pfizer Building (formerly Pfizer plant) hosting exhibitions, artist residencies, and educational workshops with a focus on accessibility and underrepresented voices.',
        'address' => '630 Flushing Ave, Brooklyn, NY 11206, USA',
        'lat' => 40.69966, 'lng' => -73.94976,
        'emoji' => '🖼️',
        'tags' => ['Brooklyn', 'East Williamsburg', 'Art Gallery'],
    ],
    [
        'name' => 'Art on the Block',
        'description' => 'Upper West Side nonprofit running affordable hands-on art workshops and accessible creative programming for NYC communities.',
        'address' => '107 W 86th St, New York, NY 10024, USA',
        'lat' => 40.78686, 'lng' => -73.97266,
        'emoji' => '🎨',
        'tags' => ['Manhattan', 'Upper West Side', 'Art', 'Workshop'],
    ],
    [
        'name' => 'Pasta Night',
        'description' => 'LGBTQIA+-owned Italian-American restaurant in Prospect Heights serving handmade pasta with a casual trattoria atmosphere; hosts guest-chef nights, themed weeklies, and pasta-forward social dinners.',
        'address' => '575 Vanderbilt Ave, Brooklyn, NY 11238, USA',
        'lat' => 40.68052, 'lng' => -73.96754,
        'emoji' => '🍝',
        'tags' => ['Brooklyn', 'Prospect Heights', 'Restaurant', 'Italian', 'LGBTQ'],
    ],
    [
        'name' => 'Dutchess County Fairgrounds',
        'description' => 'Year-round Hudson Valley fairgrounds in Rhinebeck hosting markets, festivals, the Dutchess County Fair, and large-scale bazaars (Spring Fling, Holiday).',
        'address' => '6550 Spring Brook Ave, Rhinebeck, NY 12572, USA',
        'lat' => 41.93671, 'lng' => -73.90970,
        'emoji' => '🎪',
        'tags' => ['Hudson Valley', 'Rhinebeck', 'Fairgrounds', 'Festival'],
    ],
    [
        'name' => 'Brooklyn Heights',
        'description' => 'Brownstone neighborhood on the Brooklyn waterfront, known for the Promenade, the Brooklyn Heights Association block-party events, and historic residential streets.',
        'address' => 'Brooklyn Heights, Brooklyn, NY, USA',
        'lat' => 40.69593, 'lng' => -73.99555,
        'emoji' => '📍',
        'tags' => ['Brooklyn', 'Brooklyn Heights', 'Neighborhood'],
        'generic_location' => 1,
    ],
    // 2026-05-15 — Batch of venues found via generic-location audit. Each had multiple
    // events mapping to neighborhood/borough generics because the venue wasn't in the
    // locations table. Addresses confirmed via Google Maps geocoding.
    [
        'name' => 'MITU580',
        'description' => 'Brooklyn experimental performance space and hub for IATI Theater / MITU\'s multidisciplinary, immigrant-rooted theater and music programming. Hosts ChamberQUEER and other contemporary performance series.',
        'address' => '580 Sackett St, Brooklyn, NY 11217, USA',
        'lat' => 40.67916, 'lng' => -73.98576,
        'emoji' => '🎭',
        'tags' => ['Brooklyn', 'Gowanus', 'Theater', 'Performance Space'],
    ],
    [
        'name' => 'Joffrey Ballet School',
        'short_name' => 'Joffrey Ballet',
        'description' => 'Greenwich Village ballet and contemporary dance school (main NYC campus at 434 Sixth Avenue). Studios are rented out for yoga, fitness, and community dance events.',
        'address' => '434 6th Ave, New York, NY 10011, USA',
        'lat' => 40.73458, 'lng' => -73.99863,
        'emoji' => '🩰',
        'tags' => ['Manhattan', 'Greenwich Village', 'Dance', 'Dance Studio'],
    ],
    [
        'name' => 'Greenacre Park',
        'description' => 'Midtown East pocket park (217 E 51st St) anchored by a 25-foot granite waterfall, hosting small free concerts and meditative lunchtime programming.',
        'address' => '217 E 51st St, New York, NY 10022, USA',
        'lat' => 40.75624, 'lng' => -73.96928,
        'emoji' => '🌳',
        'tags' => ['Manhattan', 'Midtown East', 'Park'],
    ],
    [
        'name' => 'Paley Park',
        'description' => 'Iconic Midtown pocket park at 3 East 53rd Street featuring a cascading water wall and shaded courtyard, used for free outdoor concerts and lunchtime gatherings.',
        'address' => '3 E 53rd St, New York, NY 10022, USA',
        'lat' => 40.76022, 'lng' => -73.97513,
        'emoji' => '🌳',
        'tags' => ['Manhattan', 'Midtown East', 'Park'],
    ],
    [
        'name' => 'Greeley Square Park',
        'description' => 'Triangular Midtown South park between Broadway and 6th Ave at 32nd–33rd Streets, in the heart of Koreatown / NoMad; hosts buskers, food vendors, and pop-up performances.',
        'address' => 'Greeley Square Park, Broadway & 6th Ave, New York, NY 10001, USA',
        'lat' => 40.74871, 'lng' => -73.98834,
        'emoji' => '🌳',
        'tags' => ['Manhattan', 'Midtown South', 'Koreatown', 'Park', 'Plaza'],
    ],
    [
        'name' => 'Italian Academy at Columbia',
        'short_name' => 'Italian Academy',
        'description' => 'Columbia University center for advanced studies in Italian culture (1161 Amsterdam Ave). Hosts public lectures, symposia, and concerts on Italian art, history, and science.',
        'address' => '1161 Amsterdam Ave, New York, NY 10027, USA',
        'lat' => 40.80759, 'lng' => -73.96020,
        'emoji' => '🎓',
        'tags' => ['Manhattan', 'Morningside Heights', 'University', 'Columbia University', 'Lectures'],
    ],
    [
        'name' => 'Borough of Manhattan Community College',
        'short_name' => 'BMCC',
        'description' => 'CUNY community college on Chambers Street in Tribeca, with the Tribeca Performing Arts Center and several event spaces used for community programs, concerts, and luncheons.',
        'address' => '199 Chambers St, New York, NY 10007, USA',
        'lat' => 40.71786, 'lng' => -74.01197,
        'emoji' => '🎓',
        'tags' => ['Manhattan', 'Tribeca', 'College', 'University'],
    ],
    [
        'name' => 'bitforms gallery',
        'description' => 'Lower East Side contemporary art gallery (131 Allen St) focused on new-media, software, and digital art; hosts openings, artist talks, and code-art events.',
        'address' => '131 Allen St, New York, NY 10002, USA',
        'lat' => 40.72010, 'lng' => -73.99024,
        'emoji' => '🖼️',
        'tags' => ['Manhattan', 'Lower East Side', 'Art Gallery'],
    ],
    [
        'name' => 'Harlem Yoga Studio',
        'description' => 'Harlem yoga studio (44 W 125th St) offering vinyasa, restorative, and themed events including rooftop yoga.',
        'address' => '44 W 125th St, New York, NY 10027, USA',
        'lat' => 40.80687, 'lng' => -73.94404,
        'emoji' => '🧘',
        'tags' => ['Manhattan', 'Harlem', 'Yoga', 'Yoga Studio', 'Wellness'],
    ],
    [
        'name' => 'Fort Defiance Park',
        'description' => 'Red Hook waterfront park at 165 Conover Street commemorating the Revolutionary War battery; hosts neighborhood history walks and climate-resilience programming.',
        'address' => '165 Conover St, Brooklyn, NY 11231, USA',
        'lat' => 40.67830, 'lng' => -74.01362,
        'emoji' => '🌳',
        'tags' => ['Brooklyn', 'Red Hook', 'Park', 'Waterfront'],
    ],
    [
        'name' => 'One Battery Park Plaza',
        'description' => 'Financial District office tower at the foot of Manhattan (1 Battery Pl), used as a common meet-up point for Lower Manhattan walking tours.',
        'address' => '1 Battery Pl, New York, NY 10004, USA',
        'lat' => 40.70336, 'lng' => -74.01363,
        'emoji' => '🏢',
        'tags' => ['Manhattan', 'Financial District', 'Walking Tours'],
    ],
    [
        'name' => 'New York Design Center',
        'short_name' => 'NY Design Center',
        'description' => 'Murray Hill design trade building at 200 Lexington Avenue (corner of 32nd Street), housing showrooms and hosting NYCxDesign festival programming, talks, and exhibitions.',
        'address' => '200 Lexington Ave, New York, NY 10016, USA',
        'lat' => 40.74548, 'lng' => -73.98058,
        'emoji' => '🎨',
        'tags' => ['Manhattan', 'Murray Hill', 'Design'],
    ],
    [
        'name' => "Hunter's Point South Park",
        'short_name' => "Hunter's Point Park",
        'description' => 'Long Island City waterfront park on Center Boulevard with sweeping Manhattan skyline views; hosts community programming run by the Hunters Point Parks Conservancy.',
        'address' => "Hunter's Point South Park, Center Blvd, Long Island City, NY 11101, USA",
        'lat' => 40.74229, 'lng' => -73.96068,
        'emoji' => '🌳',
        'tags' => ['Queens', 'Long Island City', 'Park', 'Waterfront'],
    ],
    [
        'name' => 'KR3TS',
        'description' => 'East Harlem cultural center and dance studio (208 E 126th St) supporting Latin music, dance, and youth arts programming; produces the annual "Breakin\' the Code" hip-hop showcase.',
        'address' => '208 E 126th St, New York, NY 10029, USA',
        'lat' => 40.80417, 'lng' => -73.93521,
        'emoji' => '💃',
        'tags' => ['Manhattan', 'East Harlem', 'Dance', 'Dance Studio', 'Performance Space'],
    ],
    [
        'name' => 'Annunciation Greek Orthodox Church',
        'description' => 'Upper West Side Greek Orthodox church at 302 W 91st St; sanctuary hosts free MasterVoices choral concerts and community programming.',
        'address' => '302 W 91st St, New York, NY 10024, USA',
        'lat' => 40.79201, 'lng' => -73.97597,
        'emoji' => '⛪',
        'tags' => ['Manhattan', 'Upper West Side', 'Church', 'Greek', 'Orthodox'],
    ],
    [
        'name' => 'Dumbo Ceramics',
        'description' => 'DUMBO ceramics studio (30 John St) offering hand-building and wheel workshops, including cacao-ceremony and craft-and-sip combo events.',
        'address' => '30 John St, Brooklyn, NY 11201, USA',
        'lat' => 40.70425, 'lng' => -73.98702,
        'emoji' => '🏺',
        'tags' => ['Brooklyn', 'DUMBO', 'Ceramics', 'Ceramics Studio', 'Workshop'],
    ],
    [
        'name' => 'Arya Cafe',
        'description' => 'Elmhurst Iranian-American cafe and meeting spot (81-05 Queens Blvd), used by local groups like NYC DSA for "Coffee With Comrades" community organizing meetups.',
        'address' => '81-05 Queens Blvd, Elmhurst, NY 11373, USA',
        'lat' => 40.73810, 'lng' => -73.88208,
        'emoji' => '☕',
        'tags' => ['Queens', 'Elmhurst', 'Cafe'],
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
Add new locations to the database

Usage:
  php scripts/add_locations.php [options]

Options:
  --production, -p    Add to production database (default: local)
  --dry-run, -n       Show what would be added without making changes
  --help, -h          Show this help message

Instructions:
  1. Edit the \$new_locations array at the top of this script
  2. Run with --dry-run first to verify
  3. Run without --dry-run to actually add the locations

Example location entry:
  [
      'name' => 'The Blue Note',
      'short_name' => 'Blue Note',        // Optional: shorter display name
      'description' => 'Legendary jazz club...',  // Optional: venue description
      'address' => '131 W 3rd St, New York, NY 10012',
      'lat' => 40.7308,
      'lng' => -74.0005,
      'emoji' => '🎷',
      'alt_emoji' => '🎵',                // Optional: alternative emoji
      'tags' => ['Jazz', 'Live Music', 'Manhattan', 'Greenwich Village'],  // Optional
  ]

Note: Instagram handles are stored separately in the instagram_accounts table.
Use location_instagram junction table to link locations to Instagram accounts.

HELP;
    exit(0);
}

$env = $is_production ? 'production' : 'local';
$db_config = $config[$env];

echo "=== Add Locations Script ===\n";
echo "Target: " . strtoupper($env) . " database\n";
echo "Mode: " . ($is_dry_run ? "DRY RUN (no changes will be made)" : "LIVE") . "\n";
echo "\n";

if (empty($new_locations)) {
    echo "No locations to add. Edit the \$new_locations array in this script.\n";
    exit(0);
}

echo "Locations to add: " . count($new_locations) . "\n\n";

// Validate locations before connecting
$errors = [];
foreach ($new_locations as $i => $loc) {
    $idx = $i + 1;
    if (empty($loc['name'])) {
        $errors[] = "Location #$idx: 'name' is required";
    }
    if (!isset($loc['lat']) || !is_numeric($loc['lat'])) {
        $errors[] = "Location #$idx ({$loc['name']}): 'lat' must be a number";
    }
    if (!isset($loc['lng']) || !is_numeric($loc['lng'])) {
        $errors[] = "Location #$idx ({$loc['name']}): 'lng' must be a number";
    }
    if (empty($loc['emoji'])) {
        $errors[] = "Location #$idx ({$loc['name']}): 'emoji' is required";
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
    // Test connection
    $test = run_ssh_query($db_config, "SELECT 1");
    if (trim($test) !== '1') {
        echo "Connection failed: $test\n";
        exit(1);
    }
    echo "Connected to $env database via SSH\n\n";
    $pdo = null;  // Not used for SSH mode
} else {
    // Connect to database directly (local)
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

function check_exists_pdo($pdo, $name) {
    $stmt = $pdo->prepare("SELECT id FROM locations WHERE name = ?");
    $stmt->execute([$name]);
    $row = $stmt->fetch(PDO::FETCH_ASSOC);
    return $row ? $row['id'] : null;
}

function check_exists_ssh($config, $name) {
    $sql = "SELECT id FROM locations WHERE name = " . escape_sql($name);
    $result = trim(run_ssh_query($config, $sql));
    return $result && is_numeric($result) ? $result : null;
}

function insert_location_pdo($pdo, $loc) {
    $sql = "INSERT INTO locations (name, short_name, very_short_name, description, address, lat, lng, emoji, alt_emoji)
            VALUES (:name, :short_name, :very_short_name, :description, :address, :lat, :lng, :emoji, :alt_emoji)";
    $stmt = $pdo->prepare($sql);
    $stmt->execute([
        ':name' => $loc['name'],
        ':short_name' => $loc['short_name'] ?? null,
        ':very_short_name' => $loc['very_short_name'] ?? null,
        ':description' => $loc['description'] ?? null,
        ':address' => $loc['address'] ?? null,
        ':lat' => $loc['lat'],
        ':lng' => $loc['lng'],
        ':emoji' => $loc['emoji'],
        ':alt_emoji' => $loc['alt_emoji'] ?? null,
    ]);
    return $pdo->lastInsertId();
}

function insert_location_ssh($config, $loc) {
    $sql = sprintf(
        "INSERT INTO locations (name, short_name, very_short_name, description, address, lat, lng, emoji, alt_emoji) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s); SELECT LAST_INSERT_ID();",
        escape_sql($loc['name']),
        escape_sql($loc['short_name'] ?? null),
        escape_sql($loc['very_short_name'] ?? null),
        escape_sql($loc['description'] ?? null),
        escape_sql($loc['address'] ?? null),
        $loc['lat'],
        $loc['lng'],
        escape_sql($loc['emoji']),
        escape_sql($loc['alt_emoji'] ?? null)
    );
    $result = trim(run_ssh_query($config, $sql));
    return $result;
}

function add_tags_pdo($pdo, $location_id, $tags) {
    $new_tags = [];
    $existing_tags = [];

    foreach ($tags as $tag_name) {
        // Check if tag exists
        $stmt = $pdo->prepare("SELECT id FROM tags WHERE name = ?");
        $stmt->execute([$tag_name]);
        $row = $stmt->fetch(PDO::FETCH_ASSOC);

        if ($row) {
            $tag_id = $row['id'];
            $existing_tags[] = $tag_name;
        } else {
            $stmt = $pdo->prepare("INSERT INTO tags (name) VALUES (?)");
            $stmt->execute([$tag_name]);
            $tag_id = $pdo->lastInsertId();
            $new_tags[] = $tag_name;
        }

        // Link tag to location
        $stmt = $pdo->prepare("INSERT INTO location_tags (location_id, tag_id) VALUES (?, ?)");
        $stmt->execute([$location_id, $tag_id]);
    }

    return ['existing' => $existing_tags, 'new' => $new_tags];
}

function add_tags_ssh($config, $location_id, $tags) {
    $new_tags = [];
    $existing_tags = [];

    // Build a single SQL to insert tags and link them
    $tag_values = [];
    foreach ($tags as $tag_name) {
        $tag_values[] = "(" . escape_sql($tag_name) . ")";
    }

    // Insert tags (ignore duplicates)
    $sql = "INSERT IGNORE INTO tags (name) VALUES " . implode(", ", $tag_values);
    run_ssh_query($config, $sql);

    // Link tags to location
    $tag_list = implode(", ", array_map('escape_sql', $tags));
    $sql = "INSERT INTO location_tags (location_id, tag_id) SELECT $location_id, id FROM tags WHERE name IN ($tag_list)";
    run_ssh_query($config, $sql);

    // Get which tags are new vs existing (approximate - all count as existing for SSH)
    return ['existing' => $tags, 'new' => []];
}

function get_stats_pdo($pdo) {
    $result = $pdo->query("SELECT COUNT(*) as total, MAX(id) as max_id FROM locations");
    return $result->fetch(PDO::FETCH_ASSOC);
}

function get_stats_ssh($config) {
    $result = run_ssh_query($config, "SELECT COUNT(*), MAX(id) FROM locations");
    $parts = explode("\t", trim($result));
    return ['total' => $parts[0] ?? '?', 'max_id' => $parts[1] ?? '?'];
}

// Check for duplicates
$duplicates = [];
foreach ($new_locations as $loc) {
    $existing_id = $use_ssh
        ? check_exists_ssh($db_config, $loc['name'])
        : check_exists_pdo($pdo, $loc['name']);
    if ($existing_id) {
        $duplicates[] = "'{$loc['name']}' already exists (ID: $existing_id)";
    }
}

if (!empty($duplicates)) {
    echo "Warning - these locations already exist:\n";
    foreach ($duplicates as $dup) {
        echo "  - $dup\n";
    }
    echo "\n";
}

// Process each location
$added = 0;
$skipped = 0;

foreach ($new_locations as $loc) {
    // Check if already exists
    $existing_id = $use_ssh
        ? check_exists_ssh($db_config, $loc['name'])
        : check_exists_pdo($pdo, $loc['name']);

    if ($existing_id) {
        echo "  SKIP: {$loc['name']} (already exists)\n";
        $skipped++;
        continue;
    }

    $tags = $loc['tags'] ?? [];

    if ($is_dry_run) {
        echo "  [DRY RUN] Would add: {$loc['name']} {$loc['emoji']}\n";
        echo "            Address: " . ($loc['address'] ?? 'N/A') . "\n";
        echo "            Coords: {$loc['lat']}, {$loc['lng']}\n";
        if (!empty($tags)) {
            echo "            Tags: " . implode(', ', $tags) . "\n";
        }
        $added++;
    } else {
        try {
            $new_id = $use_ssh
                ? insert_location_ssh($db_config, $loc)
                : insert_location_pdo($pdo, $loc);

            echo "  ADD: {$loc['name']} {$loc['emoji']} (ID: $new_id)\n";

            // Add tags
            if (!empty($tags)) {
                $tag_result = $use_ssh
                    ? add_tags_ssh($db_config, $new_id, $tags)
                    : add_tags_pdo($pdo, $new_id, $tags);

                if (!empty($tag_result['existing'])) {
                    echo "       Tags (existing): " . implode(', ', $tag_result['existing']) . "\n";
                }
                if (!empty($tag_result['new'])) {
                    echo "       Tags (NEW): " . implode(', ', $tag_result['new']) . "\n";
                }
            }

            $added++;
        } catch (Exception $e) {
            echo "  ERROR adding {$loc['name']}: " . $e->getMessage() . "\n";
        }
    }
}

echo "\n";
echo "=== Summary ===\n";
echo "Added: $added\n";
echo "Skipped: $skipped\n";

if ($is_dry_run && $added > 0) {
    echo "\nRun without --dry-run to actually add these locations.\n";
}

// Show current totals
$stats = $use_ssh ? get_stats_ssh($db_config) : get_stats_pdo($pdo);
echo "\nDatabase now has {$stats['total']} locations (max ID: {$stats['max_id']})\n";
