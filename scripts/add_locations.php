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
    // Interference Archive, People's Forum, Topos Bookstore, Topos Too, Rodeo - added 2026-02-07
];

/*
// --- Batch 4+5 reference data (already added) ---
$done_batch4_5 = [
    [
        'name' => 'Howe Theatre',
        'description' => 'Community theater on Roosevelt Island, home to Main Street Theatre & Dance Alliance.',
        'address' => '548 Main St, New York, NY 10044, USA',
        'lat' => 40.7618021,
        'lng' => -73.9496283,
        'emoji' => '🎭',
        'tags' => ['Manhattan', 'Roosevelt Island', 'Theater'],
    ],
    [
        'name' => 'Rhythmic Arts Center NYC',
        'short_name' => 'Rhythmic Arts Center',
        'description' => 'Dance and percussion studio in East Harlem, the first NYC studio designed specifically for percussive and rhythmic arts.',
        'address' => '175 E 105th St, New York, NY 10029, USA',
        'lat' => 40.7912954,
        'lng' => -73.945572,
        'emoji' => '🥁',
        'tags' => ['Manhattan', 'East Harlem', 'Dance', 'Music'],
    ],
    [
        'name' => 'Jazz WaHi',
        'description' => 'Non-profit jazz venue in Washington Heights promoting jazz performance and music education.',
        'address' => '839 W 181st St, New York, NY 10033, USA',
        'lat' => 40.8514952,
        'lng' => -73.9399876,
        'emoji' => '🎷',
        'tags' => ['Manhattan', 'Washington Heights', 'Jazz', 'Music'],
    ],
    [
        'name' => 'Handbell Studio at the Shirt Factory',
        'short_name' => 'Handbell Studio',
        'description' => 'Music studio in The Shirt Factory creative complex in Glens Falls, hosting handbell and other musical events.',
        'address' => 'The Shirt Factory, Glens Falls, NY 12801, USA',
        'lat' => 43.313372,
        'lng' => -73.636926,
        'emoji' => '🔔',
        'tags' => ['Upstate NY', 'Glens Falls', 'Music'],
    ],
    [
        'name' => 'Holocaust Memorial & Tolerance Center of Nassau County',
        'short_name' => 'Holocaust Memorial Center',
        'description' => 'Museum and education center in Glen Cove dedicated to Holocaust remembrance and promoting tolerance.',
        'address' => '100 Crescent Beach Rd, Glen Cove, NY 11542, USA',
        'lat' => 40.8840942,
        'lng' => -73.6416685,
        'emoji' => '🕯️',
        'tags' => ['Long Island', 'Glen Cove', 'Museum', 'Education'],
    ],
    [
        'name' => 'The Stissing Center',
        'description' => 'Community arts and events center in Pine Plains, Dutchess County, offering performances and cultural programming.',
        'address' => '2950 Church St, Pine Plains, NY 12567, USA',
        'lat' => 41.9796378,
        'lng' => -73.6571565,
        'emoji' => '🎶',
        'tags' => ['Hudson Valley', 'Pine Plains', 'Performing Arts'],
    ],
    [
        'name' => 'Kodak Hall at Eastman Theatre',
        'short_name' => 'Kodak Hall',
        'description' => 'Historic concert hall in Rochester, home of the Rochester Philharmonic Orchestra and Eastman School of Music.',
        'address' => '26 Gibbs St, Rochester, NY 14604, USA',
        'lat' => 43.1579205,
        'lng' => -77.6009462,
        'emoji' => '🎻',
        'tags' => ['Upstate NY', 'Rochester', 'Concert Hall', 'Music'],
    ],
    [
        'name' => 'PS 19: The Curtis School',
        'short_name' => 'PS 19',
        'description' => 'Public elementary school on Staten Island.',
        'address' => '780 Post Ave, Staten Island, NY 10310, USA',
        'lat' => 40.6307516,
        'lng' => -74.1272534,
        'emoji' => '🏫',
        'tags' => ['Staten Island', 'School'],
    ],
    [
        'name' => 'Mandala Cafe',
        'description' => 'Community cafe and event space in Harlem offering cultural programming and gatherings.',
        'address' => '1912 Adam Clayton Powell Jr Blvd, New York, NY 10026, USA',
        'lat' => 40.8031965,
        'lng' => -73.9531111,
        'emoji' => '☕',
        'tags' => ['Manhattan', 'Harlem', 'Cafe', 'Community Space'],
    ],
    [
        'name' => 'Riverfront Library',
        'description' => 'Yonkers Public Library branch on the Yonkers waterfront, hosting community and cultural events.',
        'address' => '1 Larkin Center, Yonkers, NY 10701, USA',
        'lat' => 40.9360015,
        'lng' => -73.9016259,
        'emoji' => '📚',
        'tags' => ['Westchester', 'Yonkers', 'Library'],
    ],
    [
        'name' => 'East Hampton Library',
        'description' => 'Public library in East Hampton village, hosting author talks, film screenings, and cultural events.',
        'address' => '159 Main St, East Hampton, NY 11937, USA',
        'lat' => 40.9581832,
        'lng' => -72.1913375,
        'emoji' => '📚',
        'tags' => ['Long Island', 'East Hampton', 'Library'],
    ],
    [
        'name' => 'Amanda Selwyn Dance Theatre',
        'short_name' => 'Amanda Selwyn',
        'description' => 'Contemporary dance company and studio in Tribeca offering performances, classes, and arts education.',
        'address' => '412 Broadway, 2nd Floor, New York, NY 10013, USA',
        'lat' => 40.7189067,
        'lng' => -74.0017643,
        'emoji' => '💃',
        'tags' => ['Manhattan', 'Tribeca', 'Dance'],
    ],
    [
        'name' => 'The Creative Center',
        'description' => 'Arts organization on the Lower East Side providing creative programming and workshops.',
        'address' => '184 Eldridge St, New York, NY 10002, USA',
        'lat' => 40.7205521,
        'lng' => -73.9905885,
        'emoji' => '🎨',
        'tags' => ['Manhattan', 'Lower East Side', 'Art'],
    ],
    [
        'name' => 'Grinton I. Will Library',
        'short_name' => 'Will Library',
        'description' => 'Yonkers Public Library branch hosting community events and cultural programming.',
        'address' => '1500 Central Park Ave, Yonkers, NY 10710, USA',
        'lat' => 40.9511614,
        'lng' => -73.844927,
        'emoji' => '📚',
        'tags' => ['Westchester', 'Yonkers', 'Library'],
    ],
    [
        'name' => 'The Angel Nyack',
        'description' => 'Music and performance venue at the First Reformed Church of Nyack, hosting concerts and cultural events.',
        'address' => '18 S Broadway, Nyack, NY 10960, USA',
        'lat' => 41.0903752,
        'lng' => -73.9188523,
        'emoji' => '🎵',
        'tags' => ['Rockland County', 'Nyack', 'Music'],
    ],
    [
        'name' => 'Sag Harbor Masonic Temple',
        'short_name' => 'Masonic Temple',
        'description' => 'Historic Masonic lodge in Sag Harbor hosting The Jam Session jazz series and community events.',
        'address' => '200 Main St, Sag Harbor, NY 11963, USA',
        'lat' => 40.997705,
        'lng' => -72.2972714,
        'emoji' => '🎷',
        'tags' => ['Long Island', 'Sag Harbor', 'Jazz', 'Music'],
    ],
    [
        'name' => 'Success Garden',
        'description' => 'Community garden in East New York, Brooklyn, hosting outdoor events and gatherings.',
        'address' => '461 Williams Ave, Brooklyn, NY 11207, USA',
        'lat' => 40.664556,
        'lng' => -73.897431,
        'emoji' => '🌱',
        'tags' => ['Brooklyn', 'East New York', 'Garden', 'Community Space'],
    ],
    [
        'name' => 'Church of St. Paul & St. Andrew',
        'short_name' => 'St. Paul & St. Andrew',
        'description' => 'United Methodist church on the Upper West Side hosting concerts, performances, and community events.',
        'address' => '263 W 86th St, New York, NY 10024, USA',
        'lat' => 40.788876,
        'lng' => -73.9772585,
        'emoji' => '⛪',
        'tags' => ['Manhattan', 'Upper West Side', 'Church', 'Music'],
    ],
    [
        'name' => 'Sleepy Hollow High School',
        'description' => 'Public high school in Sleepy Hollow, Westchester County.',
        'address' => '210 North Broadway, Sleepy Hollow, NY 10591, USA',
        'lat' => 41.0837486,
        'lng' => -73.8576587,
        'emoji' => '🏫',
        'tags' => ['Westchester', 'Sleepy Hollow', 'School'],
    ],
    [
        'name' => 'ARC Stages',
        'description' => 'Community theater and performing arts center in Pleasantville, Westchester County.',
        'address' => '147 Wheeler Ave, Pleasantville, NY 10570, USA',
        'lat' => 41.1325103,
        'lng' => -73.7904093,
        'emoji' => '🎭',
        'tags' => ['Westchester', 'Pleasantville', 'Theater'],
    ],
    [
        'name' => 'PS 69: Daniel D. Tompkins School',
        'short_name' => 'PS 69',
        'description' => 'Public elementary school on Staten Island.',
        'address' => '144 Keating Pl, Staten Island, NY 10314, USA',
        'lat' => 40.591282,
        'lng' => -74.1571739,
        'emoji' => '🏫',
        'tags' => ['Staten Island', 'School'],
    ],
    [
        'name' => 'Norte Maar',
        'description' => 'Non-profit arts organization in Bushwick promoting collaborative projects across visual art, music, and dance.',
        'address' => '83 Wyckoff Ave, Brooklyn, NY 11237, USA',
        'lat' => 40.705204,
        'lng' => -73.9203735,
        'emoji' => '🎨',
        'tags' => ['Brooklyn', 'Bushwick', 'Art', 'Music'],
    ],
    [
        'name' => 'Corlears School',
        'description' => 'Progressive independent school in Chelsea for children ages 2-10.',
        'address' => '324 W 15th St, New York, NY 10011, USA',
        'lat' => 40.7407773,
        'lng' => -74.0032338,
        'emoji' => '🏫',
        'tags' => ['Manhattan', 'Chelsea', 'School'],
    ],
    // --- Batch 4b: Venues with 2 upcoming events ---
    [
        'name' => 'Church of the Ascension',
        'description' => 'Historic Episcopal church in Greenwich Village, a National Historic Landmark hosting concerts and cultural events.',
        'address' => '12 W 11th St, New York, NY 10011, USA',
        'lat' => 40.7341139,
        'lng' => -73.995769,
        'emoji' => '⛪',
        'tags' => ['Manhattan', 'Greenwich Village', 'Church', 'Music'],
    ],
    [
        'name' => 'Ballet Tech',
        'description' => 'Dance school offering free ballet training, housed in the historic 890 Broadway building near Union Square.',
        'address' => '890 Broadway, New York, NY 10003, USA',
        'lat' => 40.7386777,
        'lng' => -73.9897382,
        'emoji' => '🩰',
        'tags' => ['Manhattan', 'Union Square', 'Dance', 'Education'],
    ],
    [
        'name' => 'Positive Exposure Gallery',
        'description' => 'Photography gallery and arts organization in Lower Manhattan celebrating diversity through visual arts.',
        'address' => '83 Maiden Ln, 4th Floor, New York, NY 10038, USA',
        'lat' => 40.7075186,
        'lng' => -74.0075098,
        'emoji' => '📷',
        'tags' => ['Manhattan', 'Financial District', 'Gallery', 'Photography'],
    ],
    [
        'name' => 'Jewish Currents',
        'description' => 'Progressive Jewish magazine and cultural space in Crown Heights, Brooklyn, hosting readings and discussions.',
        'address' => '188 Rochester Ave, Brooklyn, NY 11213, USA',
        'lat' => 40.6726739,
        'lng' => -73.9283126,
        'emoji' => '📰',
        'tags' => ['Brooklyn', 'Crown Heights', 'Media', 'Culture'],
    ],
    [
        'name' => 'Corpus Christi Church',
        'description' => 'Roman Catholic church in Morningside Heights hosting concerts and community events.',
        'address' => '529 W 121st St, New York, NY 10027, USA',
        'lat' => 40.8110842,
        'lng' => -73.9607941,
        'emoji' => '⛪',
        'tags' => ['Manhattan', 'Morningside Heights', 'Church', 'Music'],
    ],
    [
        'name' => 'Centro Cultural Cubano de Nueva York',
        'short_name' => 'Centro Cultural Cubano',
        'description' => 'Cuban cultural center in Sunnyside, Queens, presenting music, dance, film, and visual arts programs.',
        'address' => '39-51 49th St, Sunnyside, NY 11104, USA',
        'lat' => 40.7474689,
        'lng' => -73.9147416,
        'emoji' => '🇨🇺',
        'tags' => ['Queens', 'Sunnyside', 'Culture', 'Music'],
    ],
    [
        'name' => 'Think!Chinatown',
        'description' => 'Community arts organization in Manhattan Chinatown fostering intergenerational storytelling and cultural programs.',
        'address' => '1 Pike St, New York, NY 10002, USA',
        'lat' => 40.7142846,
        'lng' => -73.992356,
        'emoji' => '🏮',
        'tags' => ['Manhattan', 'Chinatown', 'Community Space', 'Culture'],
    ],
    [
        'name' => 'Theatre Three',
        'description' => 'Professional theater company in Port Jefferson, Long Island, presenting plays and musicals.',
        'address' => '412 Main St, Port Jefferson, NY 11777, USA',
        'lat' => 40.9436909,
        'lng' => -73.0675371,
        'emoji' => '🎭',
        'tags' => ['Long Island', 'Port Jefferson', 'Theater'],
    ],
    [
        'name' => 'Mount Saint Mary College',
        'short_name' => 'Mount Saint Mary',
        'description' => 'Private liberal arts college in Newburgh, NY, hosting cultural events and performances.',
        'address' => '330 Powell Ave, Newburgh, NY 12550, USA',
        'lat' => 41.511404,
        'lng' => -74.0131367,
        'emoji' => '🏛️',
        'tags' => ['Hudson Valley', 'Newburgh', 'College'],
    ],
    [
        'name' => 'BOFFO',
        'description' => 'Non-profit arts organization in Tribeca curating site-specific art installations and performances.',
        'address' => '57 Walker St, New York, NY 10013, USA',
        'lat' => 40.7188049,
        'lng' => -74.0033701,
        'emoji' => '🎨',
        'tags' => ['Manhattan', 'Tribeca', 'Art'],
    ],
    [
        'name' => 'School of American Ballet',
        'short_name' => 'SAB',
        'description' => 'The official school of New York City Ballet at Lincoln Center, the leading ballet academy in America.',
        'address' => '70 Lincoln Center Plaza, New York, NY 10023, USA',
        'lat' => 40.77451,
        'lng' => -73.9841086,
        'emoji' => '🩰',
        'tags' => ['Manhattan', 'Lincoln Center', 'Dance', 'Education'],
    ],
    [
        'name' => 'Joffrey Ballet School Long Island City',
        'short_name' => 'Joffrey LIC',
        'description' => 'Dance school campus of the Joffrey Ballet in Long Island City, Queens.',
        'address' => '47-10 Austell Pl, Long Island City, NY 11101, USA',
        'lat' => 40.7425064,
        'lng' => -73.9416653,
        'emoji' => '🩰',
        'tags' => ['Queens', 'Long Island City', 'Dance', 'Education'],
    ],
    [
        'name' => 'Sellersville Theater',
        'description' => 'Intimate live music and performance venue in Sellersville, Bucks County, Pennsylvania.',
        'address' => '24 W Temple Ave, Sellersville, PA 18960, USA',
        'lat' => 40.3593326,
        'lng' => -75.3115239,
        'emoji' => '🎵',
        'tags' => ['Pennsylvania', 'Sellersville', 'Music', 'Theater'],
    ],
    [
        'name' => 'Theater 2020',
        'description' => 'Theater company based at St. Francis College in Brooklyn Heights, producing classic and contemporary plays.',
        'address' => '180 Remsen St, Brooklyn, NY 11201, USA',
        'lat' => 40.6933174,
        'lng' => -73.9922772,
        'emoji' => '🎭',
        'tags' => ['Brooklyn', 'Brooklyn Heights', 'Theater'],
    ],
    [
        'name' => 'National Susan B. Anthony Museum & House',
        'short_name' => 'Susan B. Anthony Museum',
        'description' => 'Historic house museum in Rochester, NY, preserving the home of suffragist Susan B. Anthony.',
        'address' => '17 Madison St, Rochester, NY 14608, USA',
        'lat' => 43.1531919,
        'lng' => -77.6279635,
        'emoji' => '🏠',
        'tags' => ['Upstate NY', 'Rochester', 'Museum'],
    ],
    [
        'name' => 'Good Shepherd-Faith Presbyterian Church',
        'short_name' => 'Good Shepherd-Faith',
        'description' => 'Presbyterian church on the Upper West Side hosting concerts and community events.',
        'address' => '152 W 66th St, New York, NY 10023, USA',
        'lat' => 40.7743229,
        'lng' => -73.9839099,
        'emoji' => '⛪',
        'tags' => ['Manhattan', 'Upper West Side', 'Church', 'Music'],
    ],
    [
        'name' => 'Voices in the Heights',
        'description' => 'Concert series and arts organization in Washington Heights celebrating music and community.',
        'address' => '54 Nagle Ave, New York, NY 10040, USA',
        'lat' => 40.8601596,
        'lng' => -73.9295067,
        'emoji' => '🎵',
        'tags' => ['Manhattan', 'Washington Heights', 'Music'],
    ],
    // --- Batch 5: 1-event venues (named NYC-area venues) ---
    [
        'name' => 'National Opera Center',
        'description' => 'OPERA America headquarters with performance and rehearsal spaces for opera companies and artists.',
        'address' => '330 7th Ave, New York, NY 10001, USA',
        'lat' => 40.7477463,
        'lng' => -73.9933782,
        'emoji' => '🎶',
        'tags' => ['Manhattan', 'Chelsea', 'Opera', 'Music'],
    ],
    [
        'name' => 'East Meadow Public Library',
        'description' => 'Public library in East Meadow, Long Island, hosting author events and community programming.',
        'address' => '1886 Front St, East Meadow, NY 11554, USA',
        'lat' => 40.719977,
        'lng' => -73.563342,
        'emoji' => '📚',
        'tags' => ['Long Island', 'East Meadow', 'Library'],
    ],
    [
        'name' => 'Franklin Furnace Archive',
        'description' => 'Non-profit arts organization dedicated to avant-garde art, performance, and artist books.',
        'address' => '30-30 47th Ave, Long Island City, NY 11101, USA',
        'lat' => 40.7423837,
        'lng' => -73.9364608,
        'emoji' => '🔥',
        'tags' => ['Queens', 'Long Island City', 'Art'],
    ],
    [
        'name' => 'International Studio & Curatorial Program',
        'short_name' => 'ISCP',
        'description' => 'Residency program in East Williamsburg providing studio space for international artists and curators.',
        'address' => '1040 Metropolitan Ave, Brooklyn, NY 11211, USA',
        'lat' => 40.7141639,
        'lng' => -73.9343024,
        'emoji' => '🎨',
        'tags' => ['Brooklyn', 'East Williamsburg', 'Art', 'Gallery'],
    ],
    [
        'name' => 'Kaatsbaan Cultural Park',
        'short_name' => 'Kaatsbaan',
        'description' => 'Dance and performing arts center on 153 acres in Tivoli, Hudson Valley, hosting residencies and performances.',
        'address' => '120 Broadway, Tivoli, NY 12583, USA',
        'lat' => 42.0557899,
        'lng' => -73.9164428,
        'emoji' => '💃',
        'tags' => ['Hudson Valley', 'Tivoli', 'Dance', 'Performing Arts'],
    ],
    [
        'name' => 'KinoSaito',
        'description' => 'Art center in Verplanck, Westchester County, founded by filmmaker Noriko Shinohara, hosting film screenings and art events.',
        'address' => '115 7th St, Verplanck, NY 10596, USA',
        'lat' => 41.2522081,
        'lng' => -73.9568679,
        'emoji' => '🎬',
        'tags' => ['Westchester', 'Verplanck', 'Film', 'Art'],
    ],
    [
        'name' => 'Desert 5 Spot',
        'description' => 'Honky-tonk bar and live music venue in the East Village with a Texas roadhouse vibe.',
        'address' => '511 E 12th St, New York, NY 10009, USA',
        'lat' => 40.7289591,
        'lng' => -73.9806098,
        'emoji' => '🤠',
        'tags' => ['Manhattan', 'East Village', 'Bar', 'Music'],
    ],
    [
        'name' => 'Chez Bushwick',
        'description' => 'Artist-run space supporting experimental dance and performance in Brooklyn.',
        'address' => '72 Ralph Ave, Brooklyn, NY 11221, USA',
        'lat' => 40.6875187,
        'lng' => -73.9237947,
        'emoji' => '💃',
        'tags' => ['Brooklyn', 'Bed-Stuy', 'Dance'],
    ],
    [
        'name' => 'Verso Books',
        'description' => 'Independent publisher in DUMBO with a bookstore and event space hosting readings and discussions.',
        'address' => '20 Jay St, Brooklyn, NY 11201, USA',
        'lat' => 40.7040297,
        'lng' => -73.9867893,
        'emoji' => '📖',
        'tags' => ['Brooklyn', 'DUMBO', 'Books', 'Culture'],
    ],
    [
        'name' => 'Church of St. Francis Xavier',
        'short_name' => 'St. Francis Xavier',
        'description' => 'Jesuit Catholic church in Chelsea known for its music program and community outreach.',
        'address' => '46 W 16th St, New York, NY 10011, USA',
        'lat' => 40.7382085,
        'lng' => -73.9951897,
        'emoji' => '⛪',
        'tags' => ['Manhattan', 'Chelsea', 'Church', 'Music'],
    ],
    [
        'name' => 'Church of St. Luke & St. Matthew',
        'short_name' => 'St. Luke & St. Matthew',
        'description' => 'Episcopal church in Clinton Hill, Brooklyn, hosting concerts and cultural events.',
        'address' => '520 Clinton Ave, Brooklyn, NY 11238, USA',
        'lat' => 40.682702,
        'lng' => -73.9672458,
        'emoji' => '⛪',
        'tags' => ['Brooklyn', 'Clinton Hill', 'Church', 'Music'],
    ],
    [
        'name' => 'Mother AME Zion Church',
        'description' => 'Historic African Methodist Episcopal church in Harlem, the oldest Black church in New York State.',
        'address' => '140 W 137th St, New York, NY 10030, USA',
        'lat' => 40.8159,
        'lng' => -73.9418,
        'emoji' => '⛪',
        'tags' => ['Manhattan', 'Harlem', 'Church', 'Music'],
    ],
    [
        'name' => 'Rutgers Presbyterian Church',
        'description' => 'Presbyterian church on the Upper West Side hosting concerts and community events.',
        'address' => '236 W 73rd St, New York, NY 10023, USA',
        'lat' => 40.7795884,
        'lng' => -73.9822695,
        'emoji' => '⛪',
        'tags' => ['Manhattan', 'Upper West Side', 'Church', 'Music'],
    ],
    [
        'name' => 'Taiwan Center',
        'description' => 'Cultural center in Flushing serving the Taiwanese American community with events and programming.',
        'address' => '137-44 Northern Blvd, Flushing, NY 11354, USA',
        'lat' => 40.7632855,
        'lng' => -73.8295544,
        'emoji' => '🏮',
        'tags' => ['Queens', 'Flushing', 'Culture'],
    ],
    [
        'name' => 'Hungarian House',
        'description' => 'Cultural center on the Upper East Side preserving Hungarian heritage through concerts, exhibitions, and events.',
        'address' => '213 E 82nd St, New York, NY 10028, USA',
        'lat' => 40.7760723,
        'lng' => -73.9550627,
        'emoji' => '🏠',
        'tags' => ['Manhattan', 'Upper East Side', 'Culture', 'Music'],
    ],
    [
        'name' => 'New York Theatre Barn',
        'description' => 'Development hub for new musicals and plays in the Theater District.',
        'address' => '145 W 46th St, New York, NY 10036, USA',
        'lat' => 40.758313,
        'lng' => -73.9836046,
        'emoji' => '🎭',
        'tags' => ['Manhattan', 'Theater District', 'Theater'],
    ],
    [
        'name' => 'Tiger Strikes Asteroid',
        'short_name' => 'TSA',
        'description' => 'Artist-run gallery in Bushwick showcasing contemporary art.',
        'address' => '1329 Willoughby Ave, Brooklyn, NY 11237, USA',
        'lat' => 40.7062335,
        'lng' => -73.9211939,
        'emoji' => '🎨',
        'tags' => ['Brooklyn', 'Bushwick', 'Gallery', 'Art'],
    ],
    [
        'name' => 'Fourth Arts Block',
        'short_name' => 'FABnyc',
        'description' => 'Cultural district organization on East 4th Street supporting arts venues and community programming.',
        'address' => '70 E 4th St, New York, NY 10003, USA',
        'lat' => 40.7263608,
        'lng' => -73.9903719,
        'emoji' => '🎨',
        'tags' => ['Manhattan', 'East Village', 'Art', 'Community Space'],
    ],
    [
        'name' => 'Stella Adler Center for the Arts',
        'short_name' => 'Stella Adler',
        'description' => 'Acting school and performance space founded by legendary acting teacher Stella Adler.',
        'address' => '31 W 27th St, New York, NY 10001, USA',
        'lat' => 40.7449032,
        'lng' => -73.9894749,
        'emoji' => '🎭',
        'tags' => ['Manhattan', 'NoMad', 'Theater', 'Education'],
    ],
    [
        'name' => 'CARA (Center for Art, Research and Alliances)',
        'short_name' => 'CARA',
        'description' => 'Art center in the West Village presenting exhibitions and public programs exploring art and social practice.',
        'address' => '225 W 13th St, New York, NY 10011, USA',
        'lat' => 40.7385041,
        'lng' => -74.0013329,
        'emoji' => '🎨',
        'tags' => ['Manhattan', 'West Village', 'Art', 'Gallery'],
    ],
    [
        'name' => "Christie's New York",
        'short_name' => "Christie's",
        'description' => 'World-renowned auction house at Rockefeller Center hosting art auctions and cultural events.',
        'address' => '20 Rockefeller Plaza, New York, NY 10020, USA',
        'lat' => 40.758575,
        'lng' => -73.9800230,
        'emoji' => '🖼️',
        'tags' => ['Manhattan', 'Midtown', 'Art', 'Auction House'],
    ],
    [
        'name' => 'Philipstown Depot Theatre',
        'description' => 'Intimate community theater in a converted train depot in Garrison, Putnam County.',
        'address' => '10 Garrisons Landing, Garrison, NY 10524, USA',
        'lat' => 41.3824257,
        'lng' => -73.9471239,
        'emoji' => '🎭',
        'tags' => ['Hudson Valley', 'Garrison', 'Theater'],
    ],
    [
        'name' => 'Grimm Taproom',
        'description' => 'Craft brewery taproom in East Williamsburg hosting events and tastings.',
        'address' => '990 Metropolitan Ave, Brooklyn, NY 11211, USA',
        'lat' => 40.7142805,
        'lng' => -73.936528,
        'emoji' => '🍺',
        'tags' => ['Brooklyn', 'East Williamsburg', 'Bar', 'Brewery'],
    ],
    [
        'name' => 'Aisling Irish Community and Cultural Center',
        'short_name' => 'Aisling Center',
        'description' => 'Irish community center in Yonkers providing cultural programming and community services.',
        'address' => '990 McLean Ave, Yonkers, NY 10704, USA',
        'lat' => 40.9029511,
        'lng' => -73.8647568,
        'emoji' => '☘️',
        'tags' => ['Westchester', 'Yonkers', 'Culture', 'Community Space'],
    ],
    [
        'name' => 'Maspeth Town Hall',
        'description' => 'Community event space in Maspeth, Queens.',
        'address' => '53-37 72nd St, Maspeth, NY 11378, USA',
        'lat' => 40.7303524,
        'lng' => -73.8921762,
        'emoji' => '🏛️',
        'tags' => ['Queens', 'Maspeth', 'Community Space'],
    ],
    [
        'name' => 'Rogers Memorial Library',
        'description' => 'Public library in Southampton, Long Island, hosting author events and cultural programming.',
        'address' => '91 Coopers Farm Rd, Southampton, NY 11968, USA',
        'lat' => 40.8864351,
        'lng' => -72.3933798,
        'emoji' => '📚',
        'tags' => ['Long Island', 'Southampton', 'Library'],
    ],
    [
        'name' => 'Vietnam Heritage Center',
        'description' => 'Cultural center in Chelsea dedicated to Vietnamese heritage, arts, and community programming.',
        'address' => '225 W 23rd St, New York, NY 10011, USA',
        'lat' => 40.7447352,
        'lng' => -73.9964597,
        'emoji' => '🏮',
        'tags' => ['Manhattan', 'Chelsea', 'Culture', 'Museum'],
    ],
    [
        'name' => 'EMERGE125',
        'description' => 'Community arts and cultural space in Harlem.',
        'address' => '8 W 126th St, New York, NY 10027, USA',
        'lat' => 40.8071338,
        'lng' => -73.9425488,
        'emoji' => '🎨',
        'tags' => ['Manhattan', 'Harlem', 'Art', 'Community Space'],
    ],
    [
        'name' => 'The Reformed Church of Bronxville',
        'short_name' => 'Reformed Church Bronxville',
        'description' => 'Historic church in Bronxville hosting concerts and community events.',
        'address' => '180 Pondfield Rd, Bronxville, NY 10708, USA',
        'lat' => 40.9364076,
        'lng' => -73.8322757,
        'emoji' => '⛪',
        'tags' => ['Westchester', 'Bronxville', 'Church', 'Music'],
    ],
    [
        'name' => "Our Saviour's Atonement Lutheran Church",
        'short_name' => "Our Saviour's Atonement",
        'description' => 'Lutheran church in Washington Heights hosting concerts and cultural events.',
        'address' => '178 Bennett Ave, New York, NY 10040, USA',
        'lat' => 40.8560299,
        'lng' => -73.934364,
        'emoji' => '⛪',
        'tags' => ['Manhattan', 'Washington Heights', 'Church', 'Music'],
    ],
    [
        'name' => 'Glow Center',
        'description' => 'Cultural and performing arts space in Flushing, Queens.',
        'address' => '133-29 41st Ave, Flushing, NY 11355, USA',
        'lat' => 40.7575405,
        'lng' => -73.8311571,
        'emoji' => '✨',
        'tags' => ['Queens', 'Flushing', 'Performing Arts'],
    ],
    [
        'name' => 'MorDance Studio',
        'description' => 'Dance studio and company in Yonkers offering performances and classes.',
        'address' => '86 Main St, 6th Floor, Yonkers, NY 10701, USA',
        'lat' => 40.9346434,
        'lng' => -73.9018536,
        'emoji' => '💃',
        'tags' => ['Westchester', 'Yonkers', 'Dance'],
    ],
    [
        'name' => 'The Allen-Stevenson School',
        'short_name' => 'Allen-Stevenson',
        'description' => 'Independent boys school on the Upper East Side.',
        'address' => '132 E 78th St, New York, NY 10075, USA',
        'lat' => 40.7742851,
        'lng' => -73.9598715,
        'emoji' => '🏫',
        'tags' => ['Manhattan', 'Upper East Side', 'School'],
    ],
    [
        'name' => 'Vesuvio Restaurant',
        'description' => 'Italian restaurant in Bay Ridge, Brooklyn, hosting live entertainment and community events.',
        'address' => '7305 3rd Ave, Brooklyn, NY 11209, USA',
        'lat' => 40.6325896,
        'lng' => -74.0271415,
        'emoji' => '🍝',
        'tags' => ['Brooklyn', 'Bay Ridge', 'Restaurant'],
    ],
];
$done_batch3 = [
    [
        'name' => 'The Strong National Museum of Play',
        'short_name' => 'Museum of Play',
        'description' => 'Interactive museum dedicated to play in Rochester, NY, home to the National Toy Hall of Fame.',
        'address' => '1 Manhattan Square Dr, Rochester, NY 14607, USA',
        'lat' => 43.1525482,
        'lng' => -77.601629,
        'emoji' => '🎮',
        'tags' => ['Upstate NY', 'Rochester', 'Museum'],
    ],
    [
        'name' => 'Bedford Playhouse',
        'description' => 'Independent cinema and cultural center in Bedford, Westchester County.',
        'address' => '633 Old Post Rd, Bedford, NY 10506, USA',
        'lat' => 41.2042059,
        'lng' => -73.6441648,
        'emoji' => '🎬',
        'tags' => ['Westchester', 'Bedford', 'Cinema'],
    ],
    [
        'name' => 'The Nathaniel Rogers House',
        'description' => 'Historic house museum at the Bridgehampton Museum, hosting exhibitions and cultural events.',
        'address' => '2539 Montauk Hwy, Bridgehampton, NY 11932, USA',
        'lat' => 40.9374112,
        'lng' => -72.3004525,
        'emoji' => '🏠',
        'tags' => ['Long Island', 'Bridgehampton', 'Museum'],
    ],
    [
        'name' => 'Sag Harbor Cinema',
        'description' => 'Art house cinema in a restored 1936 movie palace in Sag Harbor village.',
        'address' => '90 Main St, Sag Harbor, NY 11963, USA',
        'lat' => 41.0003459,
        'lng' => -72.2954964,
        'emoji' => '🎬',
        'tags' => ['Long Island', 'Sag Harbor', 'Cinema'],
    ],
    [
        'name' => 'Usdan Summer Camp for the Arts',
        'short_name' => 'Usdan',
        'description' => 'Summer arts day camp on 95 acres in Wheatley Heights offering music, art, dance, theater, and nature programs.',
        'address' => '185 Colonial Springs Rd, Wheatley Heights, NY 11798, USA',
        'lat' => 40.7691279,
        'lng' => -73.386863,
        'emoji' => '🎨',
        'tags' => ['Long Island', 'Wheatley Heights', 'Art', 'Education'],
    ],
    [
        'name' => 'White Feather Farm',
        'description' => 'Farm and creative arts venue in the Hudson Valley offering workshops, retreats, and events.',
        'address' => '1389 NY-212, Saugerties, NY 12477, USA',
        'lat' => 42.0624352,
        'lng' => -74.0519538,
        'emoji' => '🌾',
        'tags' => ['Hudson Valley', 'Saugerties'],
    ],
    [
        'name' => 'Catskill Fly Fishing Center & Museum',
        'short_name' => 'Catskill Fly Fishing',
        'description' => 'Museum and education center preserving the heritage of fly fishing in the Catskills.',
        'address' => '1031 Old Rte 17, Livingston Manor, NY 12758, USA',
        'lat' => 41.9268758,
        'lng' => -74.8427519,
        'emoji' => '🎣',
        'tags' => ['Catskills', 'Livingston Manor', 'Museum'],
    ],
    [
        'name' => 'Putnam Arts Council',
        'description' => 'Community arts center in Mahopac offering exhibitions, workshops, and performances.',
        'address' => '521 Kennicut Hill Rd, Mahopac, NY 10541, USA',
        'lat' => 41.3676285,
        'lng' => -73.7330524,
        'emoji' => '🎨',
        'tags' => ['Putnam County', 'Mahopac', 'Art'],
    ],
    [
        'name' => 'The Vanaver Caravan',
        'description' => 'Dance company and school in New Paltz offering world dance classes and performances.',
        'address' => '10 Main St, New Paltz, NY 12561, USA',
        'lat' => 41.7463604,
        'lng' => -74.0893392,
        'emoji' => '💃',
        'tags' => ['Hudson Valley', 'New Paltz', 'Dance'],
    ],
    [
        'name' => 'Westbury Arts',
        'description' => 'Community arts council on Long Island providing cultural programming and events.',
        'address' => '255 Schenck Ave, Westbury, NY 11590, USA',
        'lat' => 40.7565961,
        'lng' => -73.5885054,
        'emoji' => '🎨',
        'tags' => ['Long Island', 'Westbury', 'Art'],
    ],
    [
        'name' => 'Heartbeat Opera',
        'description' => 'Innovative opera company reimagining classics through modern, socially relevant productions.',
        'address' => '526 W 26th St, New York, NY 10001, USA',
        'lat' => 40.7500522,
        'lng' => -74.0042667,
        'emoji' => '🎤',
        'tags' => ['Manhattan', 'Chelsea', 'Opera'],
    ],
    [
        'name' => 'OLPH Catholic Academy of Brooklyn',
        'short_name' => 'OLPH Academy',
        'description' => 'Catholic school in Sunset Park, Brooklyn, hosting opera performances and community events.',
        'address' => '5902 6th Ave, Brooklyn, NY 11220, USA',
        'lat' => 40.6385516,
        'lng' => -74.0138564,
        'emoji' => '🏫',
        'tags' => ['Brooklyn', 'Sunset Park', 'School'],
    ],
    // === NYC schools (Arts For All programs) ===
    [
        'name' => 'Renaissance Charter School (Jackson Heights)',
        'short_name' => 'Renaissance CS JH',
        'description' => 'Charter school in Jackson Heights hosting Arts For All programs.',
        'address' => '35-59 81st St, Jackson Heights, NY 11372, USA',
        'lat' => 40.7499835,
        'lng' => -73.8851717,
        'emoji' => '🏫',
        'tags' => ['Queens', 'Jackson Heights', 'School'],
    ],
    [
        'name' => 'Renaissance Charter School (Elmhurst)',
        'short_name' => 'Renaissance CS Elm',
        'description' => 'Charter school in Elmhurst hosting Arts For All programs.',
        'address' => '81-14 Queens Blvd, Elmhurst, NY 11373, USA',
        'lat' => 40.7366,
        'lng' => -73.8782,
        'emoji' => '🏫',
        'tags' => ['Queens', 'Elmhurst', 'School'],
    ],
    [
        'name' => 'PS 163: Arthur A. Schomburg',
        'short_name' => 'PS 163',
        'description' => 'Bronx elementary school hosting Arts For All programs.',
        'address' => '2075 Webster Ave, Bronx, NY 10457, USA',
        'lat' => 40.8516239,
        'lng' => -73.8987889,
        'emoji' => '🏫',
        'tags' => ['Bronx', 'Tremont', 'School'],
    ],
    [
        'name' => 'PS 76: The William Hallet School',
        'short_name' => 'PS 76',
        'description' => 'Queens school in Astoria hosting Arts For All programs.',
        'address' => '36-36 10th St, Long Island City, NY 11106, USA',
        'lat' => 40.7609462,
        'lng' => -73.941645,
        'emoji' => '🏫',
        'tags' => ['Queens', 'Astoria', 'School'],
    ],
    [
        'name' => 'PS 15: The Roberto Clemente School',
        'short_name' => 'PS 15',
        'description' => 'Lower East Side elementary school hosting Arts For All programs.',
        'address' => '333 E 4th St, New York, NY 10009, USA',
        'lat' => 40.72171,
        'lng' => -73.9785786,
        'emoji' => '🏫',
        'tags' => ['Manhattan', 'East Village', 'School'],
    ],
    [
        'name' => 'PS 194: Countee Cullen Academy',
        'short_name' => 'PS 194',
        'description' => 'Harlem school hosting Arts For All programs.',
        'address' => '244 W 144th St, New York, NY 10030, USA',
        'lat' => 40.82126,
        'lng' => -73.9407875,
        'emoji' => '🏫',
        'tags' => ['Manhattan', 'Harlem', 'School'],
    ],
    [
        'name' => 'PS 243: The Weeksville School',
        'short_name' => 'PS 243',
        'description' => 'Brooklyn school in Crown Heights hosting Arts For All programs.',
        'address' => '1580 Dean St, Brooklyn, NY 11213, USA',
        'lat' => 40.6757996,
        'lng' => -73.9353392,
        'emoji' => '🏫',
        'tags' => ['Brooklyn', 'Crown Heights', 'School'],
    ],
    [
        'name' => 'PS 155: William Paca School',
        'short_name' => 'PS 155',
        'description' => 'Bronx school hosting Arts For All programs.',
        'address' => '800 Home St, Bronx, NY 10459, USA',
        'lat' => 40.8248,
        'lng' => -73.8932,
        'emoji' => '🏫',
        'tags' => ['Bronx', 'School'],
    ],
    // === NYC venues (continued) ===
    [
        'name' => 'La Nacional',
        'description' => 'Spanish Benevolent Society in Chelsea hosting flamenco, cultural events, and community gatherings since 1868.',
        'address' => '239 W 14th St, New York, NY 10011, USA',
        'lat' => 40.7394905,
        'lng' => -74.001176,
        'emoji' => '💃',
        'tags' => ['Manhattan', 'Chelsea', 'Dance', 'Cultural Center'],
    ],
    [
        'name' => 'Kismat',
        'description' => 'Washington Heights restaurant and event space hosting jazz performances and community events.',
        'address' => '603 Fort Washington Ave, New York, NY 10040, USA',
        'lat' => 40.8553122,
        'lng' => -73.9370321,
        'emoji' => '🎵',
        'tags' => ['Manhattan', 'Washington Heights', 'Jazz', 'Restaurant'],
    ],
    [
        'name' => 'The 14th Street Y',
        'short_name' => '14th St Y',
        'description' => 'Community center on the Lower East Side offering performing arts, classes, and family programming.',
        'address' => '344 E 14th St, New York, NY 10003, USA',
        'lat' => 40.7313444,
        'lng' => -73.9832545,
        'emoji' => '🏛️',
        'tags' => ['Manhattan', 'East Village', 'Community', 'Theater'],
    ],
    [
        'name' => 'Ciao Ciao Disco',
        'description' => 'Italian-inspired disco bar in Williamsburg hosting social events and meetups.',
        'address' => '97 N 10th St, Brooklyn, NY 11249, USA',
        'lat' => 40.721049,
        'lng' => -73.9581196,
        'emoji' => '🪩',
        'tags' => ['Brooklyn', 'Williamsburg', 'Bar', 'Nightlife'],
    ],
    [
        'name' => 'Dutch Baby Bakery',
        'description' => 'Washington Heights bakery hosting jazz performances and community events.',
        'address' => '813 W 187th St, New York, NY 10040, USA',
        'lat' => 40.8553526,
        'lng' => -73.9373304,
        'emoji' => '🥐',
        'tags' => ['Manhattan', 'Washington Heights', 'Jazz', 'Bakery'],
    ],
    [
        'name' => "Rudy's Bar and Grill",
        'short_name' => "Rudy's Bar",
        'description' => 'Iconic Hell\'s Kitchen dive bar known for free hot dogs and cheap pitchers, hosting meetups and social events.',
        'address' => '627 9th Ave, New York, NY 10036, USA',
        'lat' => 40.7600309,
        'lng' => -73.9917951,
        'emoji' => '🍺',
        'tags' => ['Manhattan', "Hell's Kitchen", 'Bar'],
    ],
    [
        'name' => 'Casa Belvedere',
        'description' => 'Italian cultural center in a historic mansion on Staten Island offering concerts, exhibits, and language classes.',
        'address' => '79 Howard Ave, Staten Island, NY 10301, USA',
        'lat' => 40.6284634,
        'lng' => -74.0880772,
        'emoji' => '🏛️',
        'tags' => ['Staten Island', 'Cultural Center'],
    ],
    [
        'name' => "Wendy's Subway",
        'description' => 'Library and reading room in Bushwick supporting artist books, periodicals, and community programming.',
        'address' => '379 Bushwick Ave, Brooklyn, NY 11206, USA',
        'lat' => 40.70384,
        'lng' => -73.9379809,
        'emoji' => '📚',
        'tags' => ['Brooklyn', 'Bushwick', 'Art', 'Library'],
    ],
    [
        'name' => 'The Center at West Park',
        'description' => 'Performing arts and community center on the Upper West Side in a historic Presbyterian church.',
        'address' => '165 W 86th St, New York, NY 10024, USA',
        'lat' => 40.7889677,
        'lng' => -73.9772637,
        'emoji' => '⛪',
        'tags' => ['Manhattan', 'Upper West Side', 'Theater', 'Community'],
    ],
    [
        'name' => 'The New York Society Library',
        'short_name' => 'NY Society Library',
        'description' => 'America\'s oldest cultural institution (1754), a membership library hosting author talks, lectures, and literary events.',
        'address' => '53 E 79th St, New York, NY 10075, USA',
        'lat' => 40.77634,
        'lng' => -73.96144,
        'emoji' => '📖',
        'tags' => ['Manhattan', 'Upper East Side', 'Library', 'Literature'],
    ],
    [
        'name' => 'Huge Flop',
        'description' => 'Comedy and variety show venue in the Flatiron District.',
        'address' => '53 W 23rd St, New York, NY 10010, USA',
        'lat' => 40.7429606,
        'lng' => -73.991313,
        'emoji' => '😂',
        'tags' => ['Manhattan', 'Flatiron', 'Comedy'],
    ],
    [
        'name' => 'Church of St. Ignatius Loyola',
        'short_name' => 'St. Ignatius Loyola',
        'description' => 'Landmark Jesuit church on Park Avenue known for its acclaimed Sacred Music concert series.',
        'address' => '980 Park Ave, New York, NY 10028, USA',
        'lat' => 40.778881,
        'lng' => -73.958712,
        'emoji' => '⛪',
        'tags' => ['Manhattan', 'Upper East Side', 'Music', 'Church'],
    ],
    [
        'name' => 'Manny Cantor Center',
        'description' => 'Lower East Side community center offering arts, education, and family programming as part of Educational Alliance.',
        'address' => '197 E Broadway, New York, NY 10002, USA',
        'lat' => 40.7139708,
        'lng' => -73.9883748,
        'emoji' => '🏛️',
        'tags' => ['Manhattan', 'Lower East Side', 'Community'],
    ],
    [
        'name' => 'Jamel Gaines Creative Outlet',
        'description' => 'Dance studio and performing arts center in Fort Greene offering classes and performances.',
        'address' => '138 S Oxford St, Brooklyn, NY 11217, USA',
        'lat' => 40.685155,
        'lng' => -73.973504,
        'emoji' => '💃',
        'tags' => ['Brooklyn', 'Fort Greene', 'Dance'],
    ],
    [
        'name' => 'Noel Pointer Foundation',
        'description' => 'Music education organization in Bedford-Stuyvesant providing violin and string instruction to youth.',
        'address' => '1360 Fulton St, Brooklyn, NY 11216, USA',
        'lat' => 40.6796637,
        'lng' => -73.9460248,
        'emoji' => '🎻',
        'tags' => ['Brooklyn', 'Bed-Stuy', 'Music', 'Education'],
    ],
    [
        'name' => 'Mare Nostrum Elements',
        'description' => 'Performance and rehearsal space at The Clemente Center on the Lower East Side for dance, theater, and music.',
        'address' => '107 Suffolk St, New York, NY 10002, USA',
        'lat' => 40.7191552,
        'lng' => -73.9862627,
        'emoji' => '🎭',
        'tags' => ['Manhattan', 'Lower East Side', 'Dance', 'Theater'],
    ],
    [
        'name' => 'Hi-ARTS',
        'description' => 'Arts organization in Harlem supporting multidisciplinary artists of color through performances and residencies.',
        'address' => '145 W 125th St, New York, NY 10027, USA',
        'lat' => 40.8089191,
        'lng' => -73.9470421,
        'emoji' => '🎨',
        'tags' => ['Manhattan', 'Harlem', 'Art'],
    ],
    [
        'name' => 'Sea Dog Theater',
        'description' => 'Intimate Off-Off-Broadway theater space in Gramercy.',
        'address' => '209 E 16th St, New York, NY 10003, USA',
        'lat' => 40.7343503,
        'lng' => -73.9849615,
        'emoji' => '🎭',
        'tags' => ['Manhattan', 'Gramercy', 'Theater'],
    ],
    [
        'name' => 'Think Olio',
        'description' => 'Educational organization offering immersive seminars, lectures, and cultural experiences across NYC.',
        'address' => '828 Broadway, New York, NY 10003, USA',
        'lat' => 40.7333171,
        'lng' => -73.9909639,
        'emoji' => '🧠',
        'tags' => ['Manhattan', 'Union Square', 'Education'],
    ],
    [
        'name' => 'EFA Robert Blackburn Printmaking Workshop',
        'short_name' => 'EFA Printmaking',
        'description' => 'Community printmaking studio at the Elizabeth Foundation for the Arts, offering workshops and artist residencies.',
        'address' => '323 W 39th St, New York, NY 10018, USA',
        'lat' => 40.7561631,
        'lng' => -73.9924149,
        'emoji' => '🖨️',
        'tags' => ['Manhattan', 'Garment District', 'Art'],
    ],
    [
        'name' => 'Volunteer Lawyers for the Arts',
        'short_name' => 'VLA',
        'description' => 'Legal services organization for artists, offering workshops and educational programs in Midtown.',
        'address' => '729 7th Ave, New York, NY 10019, USA',
        'lat' => 40.7602421,
        'lng' => -73.983606,
        'emoji' => '⚖️',
        'tags' => ['Manhattan', 'Midtown', 'Education'],
    ],
    [
        'name' => "Ma's House",
        'description' => 'BIPOC art studio and gallery in Bushwick fostering community through exhibitions, workshops, and residencies.',
        'address' => '164 Suydam St, Brooklyn, NY 11221, USA',
        'lat' => 40.6992517,
        'lng' => -73.9262689,
        'emoji' => '🎨',
        'tags' => ['Brooklyn', 'Bushwick', 'Art', 'Gallery'],
    ],
    [
        'name' => 'A.R.T./New York South Oxford Space',
        'short_name' => 'South Oxford Space',
        'description' => 'Affordable rehearsal and performance space for independent theater companies in Fort Greene.',
        'address' => '138 S Oxford St, Brooklyn, NY 11217, USA',
        'lat' => 40.6850973,
        'lng' => -73.9734932,
        'emoji' => '🎭',
        'tags' => ['Brooklyn', 'Fort Greene', 'Theater'],
    ],
    [
        'name' => 'Theater in Asylum',
        'description' => 'Experimental theater company creating original and devised works in the Flatiron area.',
        'address' => '123 E 24th St, New York, NY 10010, USA',
        'lat' => 40.7405602,
        'lng' => -73.984683,
        'emoji' => '🎭',
        'tags' => ['Manhattan', 'Flatiron', 'Theater'],
    ],
    [
        'name' => 'Maimouna Keita School of African Dance',
        'short_name' => 'Maimouna Keita Dance',
        'description' => 'School dedicated to West African dance traditions, offering classes and performances in Brooklyn.',
        'address' => '1195 Bedford Ave, Brooklyn, NY 11216, USA',
        'lat' => 40.6824551,
        'lng' => -73.9535359,
        'emoji' => '💃',
        'tags' => ['Brooklyn', 'Bed-Stuy', 'Dance'],
    ],
    [
        'name' => 'McKoy Dance Project',
        'description' => 'Dance company and studio in Brooklyn offering classes and performances.',
        'address' => '1107 Atlantic Ave, Brooklyn, NY 11216, USA',
        'lat' => 40.679129,
        'lng' => -73.9545185,
        'emoji' => '💃',
        'tags' => ['Brooklyn', 'Crown Heights', 'Dance'],
    ],
    [
        'name' => 'Essence Theatre-Studio',
        'short_name' => 'ESSENCE Theatre',
        'description' => 'Theater studio in Gravesend, Brooklyn, creating original theatrical productions.',
        'address' => '2653 Coney Island Ave, Brooklyn, NY 11223, USA',
        'lat' => 40.5920719,
        'lng' => -73.9604353,
        'emoji' => '🎭',
        'tags' => ['Brooklyn', 'Gravesend', 'Theater'],
    ],
    // === Outside NYC (high event count) ===
    [
        'name' => 'Manitoga',
        'description' => 'Historic home and studio of industrial designer Russel Wright in the Hudson Highlands, offering tours and nature programs.',
        'address' => '584 NY-9D, Garrison, NY 10524, USA',
        'lat' => 41.3485649,
        'lng' => -73.9526328,
        'emoji' => '🏡',
        'tags' => ['Hudson Valley', 'Garrison', 'Museum'],
    ],
    [
        'name' => 'Crestwood Library',
        'description' => 'Yonkers Public Library branch offering programs, workshops, and community events.',
        'address' => '16 Thompson St, Yonkers, NY 10707, USA',
        'lat' => 40.9618161,
        'lng' => -73.8232975,
        'emoji' => '📚',
        'tags' => ['Westchester', 'Yonkers', 'Library'],
    ],
    [
        'name' => 'Planting Fields Foundation',
        'short_name' => 'Planting Fields',
        'description' => 'Gold Coast estate in Oyster Bay with 400+ acres of gardens, greenhouses, and Coe Hall mansion offering tours and events.',
        'address' => '1395 Planting Fields Rd, Oyster Bay, NY 11771, USA',
        'lat' => 40.8679016,
        'lng' => -73.5529554,
        'emoji' => '🌺',
        'tags' => ['Long Island', 'Oyster Bay', 'Garden', 'Museum'],
    ],
    [
        'name' => 'Arts Society of Kingston',
        'short_name' => 'ASK',
        'description' => 'Community arts center in Kingston\'s Rondout District offering exhibitions, classes, and performances.',
        'address' => '97 Broadway, Kingston, NY 12401, USA',
        'lat' => 41.9200909,
        'lng' => -73.9857859,
        'emoji' => '🎨',
        'tags' => ['Hudson Valley', 'Kingston', 'Art', 'Gallery'],
    ],
    [
        'name' => 'Nassau County Museum of Art',
        'description' => 'Art museum on a 145-acre estate in Roslyn Harbor featuring rotating exhibitions, sculpture garden, and events.',
        'address' => 'One Museum Dr, Roslyn, NY 11576, USA',
        'lat' => 40.8096523,
        'lng' => -73.642799,
        'emoji' => '🖼️',
        'tags' => ['Long Island', 'Roslyn', 'Museum', 'Art'],
    ],
    [
        'name' => 'Safe Harbors of the Hudson',
        'short_name' => 'Safe Harbors',
        'description' => 'Arts and housing organization in Newburgh operating the Ritz Theater and providing affordable housing for artists.',
        'address' => '111 Broadway, Newburgh, NY 12550, USA',
        'lat' => 41.4997949,
        'lng' => -74.0116384,
        'emoji' => '🎭',
        'tags' => ['Hudson Valley', 'Newburgh', 'Theater'],
    ],
    [
        'name' => 'Rosendale Theatre',
        'description' => 'Community-owned movie theater in a converted 1949 cinema, showing indie films and hosting live events.',
        'address' => '408 Main St, Rosendale, NY 12472, USA',
        'lat' => 41.8443232,
        'lng' => -74.0822053,
        'emoji' => '🎬',
        'tags' => ['Hudson Valley', 'Rosendale', 'Cinema'],
    ],
    [
        'name' => 'The Ark at Shames JCC',
        'short_name' => 'The Ark',
        'description' => 'Jewish Community Center in Tarrytown offering performances, family events, and cultural programs.',
        'address' => '371 S Broadway, Tarrytown, NY 10591, USA',
        'lat' => 41.0619719,
        'lng' => -73.8636624,
        'emoji' => '🏛️',
        'tags' => ['Westchester', 'Tarrytown', 'Community'],
    ],
    [
        'name' => 'The Gateway',
        'description' => 'Performing arts center in Bellport, Long Island, offering theater, music, comedy, and family programming.',
        'address' => '215 S Country Rd, Bellport, NY 11713, USA',
        'lat' => 40.7625773,
        'lng' => -72.9325768,
        'emoji' => '🎭',
        'tags' => ['Long Island', 'Bellport', 'Theater'],
    ],
    [
        'name' => 'Washington Lodge',
        'description' => 'Event venue and community space in Hempstead, Long Island, used for educational and cultural programs.',
        'address' => '111 Pierson Ave, Hempstead, NY 11550, USA',
        'lat' => 40.6915674,
        'lng' => -73.6160447,
        'emoji' => '🏛️',
        'tags' => ['Long Island', 'Hempstead', 'Community'],
    ],
];
*/

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
