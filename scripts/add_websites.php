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
    [
        'name' => 'Outsider Art Fair',
        'description' => 'Established in 1993, the premier fair dedicated to Self-Taught Art, Art Brut, and Outsider Art, held annually in New York.',
        'base_url' => 'https://www.outsiderartfair.com/visit',
        'location' => 'Metropolitan Pavilion',
    ],
    // === Real Venues (Batch 1 - from agent research) ===
    [
        'name' => 'Metropolitan Club',
        'description' => 'Historic private social club at 1 E 60th St, New York, founded in 1891.',
        'base_url' => 'https://www.metropolitanclubnyc.org/',
        'location' => 'Metropolitan Club',
    ],
    [
        'name' => 'Custom House (Sag Harbor)',
        'description' => 'Historic house museum in Sag Harbor operated by the Preservation Long Island.',
        'base_url' => 'https://www.preservationlongisland.org/custom-house/',
        'location' => 'Custom House (Sag Harbor)',
    ],
    [
        'name' => 'Conwell Coffee Hall',
        'description' => 'Coffee shop and event space at 6 Hanover St in the Financial District.',
        'base_url' => 'https://conwellhall.com/',
        'location' => 'Conwell Coffee Hall',
    ],
    [
        'name' => 'Riverdale Temple',
        'description' => 'Reform Jewish congregation in the Riverdale section of the Bronx.',
        'base_url' => 'https://www.riverdaletemple.org/',
        'location' => 'Riverdale Temple',
    ],
    [
        'name' => 'Stephen Wise Free Synagogue',
        'description' => 'Reform Jewish congregation on the Upper West Side, founded in 1907.',
        'base_url' => 'https://swfs.org/',
        'location' => 'Stephen Wise Free Synagogue',
    ],
    [
        'name' => 'Stand Up NY',
        'description' => 'Comedy club in the Theater District presenting stand-up shows nightly.',
        'base_url' => 'https://standupny.com/',
        'location' => 'Stand Up NY',
        'tags' => ['Comedy'],
    ],
    [
        'name' => 'Helen Mills Event Space',
        'description' => 'Event and production space in Chelsea for private events and meetings.',
        'base_url' => 'https://www.helenmills.com/',
        'location' => 'Helen Mills Event Space',
    ],
    [
        'name' => 'Tracksmith Trackhouse',
        'description' => 'Running brand retail store and community space in Williamsburg, Brooklyn.',
        'base_url' => 'https://www.tracksmith.com/',
        'location' => 'Tracksmith Trackhouse',
    ],
    [
        'name' => 'Bronx Council on the Arts',
        'description' => 'Arts service organization supporting and developing the arts in the Bronx.',
        'base_url' => 'https://www.bronxarts.org/',
        'location' => 'Bronx Council on the Arts',
        'tags' => ['Art'],
    ],
    [
        'name' => 'EMERGE125',
        'description' => 'Community arts organization in Harlem focused on arts programming and events.',
        'base_url' => 'https://emerge125.org/',
        'location' => 'EMERGE125',
        'tags' => ['Art', 'Community Space'],
    ],
    [
        'name' => 'Harvestworks Digital Media Arts Center',
        'description' => 'Nonprofit arts organization in SoHo supporting artists working with technology and electronic media.',
        'base_url' => 'https://www.harvestworks.org/',
        'location' => 'Harvestworks Digital Media Arts Center',
        'tags' => ['Art'],
    ],
    [
        'name' => 'Kato Sake Works',
        'description' => 'Brooklyn-based sake brewery in Bushwick producing craft sake.',
        'base_url' => 'https://www.katosakeworks.com/',
        'location' => 'Kato Sake Works',
    ],
    [
        'name' => 'Penguin Rep Theatre',
        'description' => 'Professional Equity theater in Stony Point, NY presenting new and classic works.',
        'base_url' => 'https://www.penguinrep.org/',
        'location' => 'Penguin Rep Theatre',
        'tags' => ['Theater'],
    ],
    [
        'name' => 'Hive Mind Books & Coffee',
        'description' => 'Independent bookstore and coffee shop in Brooklyn.',
        'base_url' => 'https://www.hivemindbooks.com/',
        'location' => 'Hive Mind Books & Coffee',
    ],
    [
        'name' => 'Ensemble Studio Theatre',
        'description' => 'Off-Broadway theater company at 545 W 52nd St dedicated to nurturing new American plays.',
        'base_url' => 'https://www.ensemblestudiotheatre.org/',
        'location' => 'Ensemble Studio Theatre',
        'tags' => ['Theater'],
    ],
    [
        'name' => 'CITYarts',
        'description' => 'Nonprofit bringing young people and professional artists together to create public art.',
        'base_url' => 'https://www.cityarts.org/',
        'location' => 'CITYarts',
        'tags' => ['Art'],
    ],
    // === Real Venues (Batch 2 - from agent research) ===
    [
        'name' => 'Urbani Truffles',
        'description' => 'Italian truffle company with a New York showroom and tasting events.',
        'base_url' => 'https://urbani.com/',
        'location' => 'Urbani Truffles',
    ],
    [
        'name' => 'Waldorf Astoria New York',
        'description' => 'Landmark luxury hotel on Park Avenue, New York.',
        'base_url' => 'https://www.waldorfastorianewyork.com/',
        'location' => 'Waldorf Astoria New York',
    ],
    [
        'name' => 'Mohonk Preserve',
        'description' => 'Nature preserve in New Paltz, NY with hiking, climbing, and nature programs.',
        'base_url' => 'https://www.mohonkpreserve.org/',
        'location' => 'Mohonk Preserve',
    ],
    [
        'name' => 'Chelsea Factory',
        'description' => 'Multidisciplinary arts center in Chelsea presenting performances, exhibitions, and community events.',
        'base_url' => 'https://www.chelseafactory.org/',
        'location' => 'Chelsea Factory',
        'tags' => ['Art'],
    ],
    [
        'name' => 'Make Manifest',
        'description' => 'Creative hub in Bed-Stuy with a vegan café, handmade goods, and community programming.',
        'base_url' => 'https://www.makemanifestbk.com/',
        'location' => 'Make Manifest',
    ],
    [
        'name' => 'Gallery Hyundai New York',
        'description' => 'New York outpost of Gallery Hyundai, one of South Korea\'s leading contemporary art galleries.',
        'base_url' => 'https://www.galleryhyundai.com/',
        'location' => 'Gallery Hyundai New York',
        'tags' => ['Art', 'Gallery'],
    ],
    [
        'name' => 'Kumble Theater at LIU Brooklyn',
        'description' => 'Performing arts venue at Long Island University Brooklyn campus.',
        'base_url' => 'https://kumbletheater.org/',
        'location' => 'Kumble Theater at LIU Brooklyn',
        'tags' => ['Theater'],
    ],
    [
        'name' => 'DR2 Theatre',
        'description' => 'Off-Broadway theater at 103 E 15th St operated by Daryl Roth.',
        'base_url' => 'https://www.darylroththeatre.com/',
        'location' => 'DR2 Theatre',
        'tags' => ['Theater'],
    ],
    [
        'name' => 'The Door',
        'description' => 'Youth development organization in SoHo providing services including arts and education.',
        'base_url' => 'https://www.door.org/',
        'location' => 'The Door',
    ],
    [
        'name' => 'Tishman Auditorium',
        'description' => 'Auditorium at The New School at 63 5th Ave used for lectures and events.',
        'base_url' => 'https://www.newschool.edu/',
        'location' => 'Tishman Auditorium',
    ],
    [
        'name' => 'New York Hilton Midtown',
        'description' => 'Large convention hotel in Midtown Manhattan.',
        'base_url' => 'https://www.hilton.com/en/hotels/nycnhhh-new-york-hilton-midtown/',
        'location' => 'New York Hilton Midtown',
    ],
    [
        'name' => 'New York Marriott at the Brooklyn Bridge',
        'description' => 'Hotel in Downtown Brooklyn near the Brooklyn Bridge.',
        'base_url' => 'https://www.marriott.com/en-us/hotels/nycbk-new-york-marriott-at-the-brooklyn-bridge/overview/',
        'location' => 'New York Marriott at the Brooklyn Bridge',
    ],
    [
        'name' => 'Peconic Landing',
        'description' => 'Continuing care retirement community in Greenport on the North Fork of Long Island.',
        'base_url' => 'https://peconiclanding.org/',
        'location' => 'Peconic Landing',
    ],
    [
        'name' => 'Fei Tian College',
        'description' => 'Private liberal arts college in Cuddebackville, NY.',
        'base_url' => 'https://feitian.edu/',
        'location' => 'Fei Tian College',
    ],
    [
        'name' => 'QUNO Quaker House',
        'description' => 'Quaker United Nations Office near the UN headquarters in Manhattan.',
        'base_url' => 'https://quno.org/',
        'location' => 'QUNO Quaker House',
    ],
    [
        'name' => 'Eastern Queens Alliance',
        'description' => 'Environmental justice organization serving southeastern Queens communities.',
        'base_url' => 'https://easternqueensalliance.org/',
        'location' => 'Eastern Queens Alliance',
    ],
    [
        'name' => 'The Climate Imaginarium',
        'description' => 'Immersive climate experience on Governors Island.',
        'base_url' => 'https://www.climateimaginarium.org/',
        'location' => 'The Climate Imaginarium',
    ],
    [
        'name' => 'Boucherie West Village',
        'description' => 'French bistro and steakhouse in the West Village.',
        'base_url' => 'https://www.boucherieus.com/',
        'location' => 'Boucherie West Village',
    ],
    [
        'name' => 'Rain Rain Gallery',
        'description' => 'Contemporary art gallery in Lower Manhattan.',
        'base_url' => 'https://www.rainraingallery.com/',
        'location' => 'Rain Rain Gallery',
        'tags' => ['Art', 'Gallery'],
    ],
    [
        'name' => 'Seven House Gallery',
        'description' => 'Art gallery at 35 Meadow St in Brooklyn.',
        'base_url' => 'https://www.sevenhousenewyork.com/',
        'location' => 'Seven House Gallery',
        'tags' => ['Art', 'Gallery'],
    ],
    [
        'name' => 'Stump Gallery',
        'description' => 'Art gallery at 70 John St in Brooklyn.',
        'base_url' => 'https://www.stumpgallery.com/',
        'location' => 'Stump Gallery',
        'tags' => ['Art', 'Gallery'],
    ],
    [
        'name' => 'Blue Pomelo Studio',
        'description' => 'Design studio at 117 9th St in Brooklyn.',
        'base_url' => 'https://www.bluepomelo.studio/',
        'location' => 'Blue Pomelo Studio',
    ],
    [
        'name' => 'Form + Flow Waterfront',
        'description' => 'Yoga studio in Long Island City offering classes, workshops, and retreats.',
        'base_url' => 'https://www.formandflow.co/',
        'location' => 'Form + Flow Waterfront',
    ],
    [
        'name' => 'NOFLEX NYC',
        'description' => 'Media art restaurant and cocktail bar with a 72-foot LED wall at 286 5th Ave.',
        'base_url' => 'https://noflex.nyc/',
        'location' => 'NOFLEX NYC',
    ],
    [
        'name' => 'The West Village Rehearsal Co-op',
        'description' => 'Affordable rehearsal space for indie theater at Westbeth, operated by IndieSpace.',
        'base_url' => 'https://www.indiespace.org/wvrc',
        'location' => 'The West Village Rehearsal Co-op',
        'tags' => ['Theater'],
    ],
    [
        'name' => 'Caravan of Dreams',
        'description' => 'Mediterranean organic vegan restaurant in the East Village.',
        'base_url' => 'https://www.caravanofdreams.net/',
        'location' => 'Caravan of Dreams',
    ],
    [
        'name' => 'Indochine',
        'description' => 'Iconic French-Vietnamese restaurant on Lafayette St, opened in 1984.',
        'base_url' => 'https://www.indochinenyc.com/',
        'location' => 'Indochine',
    ],
    [
        'name' => "Jake's Steakhouse",
        'description' => 'Steakhouse in the Riverdale section of the Bronx.',
        'base_url' => 'https://www.jakessteakhouse.com/',
        'location' => 'Jake\'s Steakhouse (Bronx)',
    ],
    [
        'name' => 'ZAROLAT',
        'description' => 'Venue at 140 Plymouth St in Brooklyn.',
        'base_url' => 'https://www.zarolat.com/',
        'location' => 'ZAROLAT',
    ],
    [
        'name' => 'The Noortwyck',
        'description' => 'Elevated neighborhood restaurant in the West Village by Chef Andy Quinn.',
        'base_url' => 'https://www.thenoortwyck.com/',
        'location' => 'The Noortwyck',
    ],
    [
        'name' => 'Bouquet',
        'description' => 'Wine bar and restaurant in Greenpoint, Brooklyn featuring low-intervention wines.',
        'base_url' => 'https://www.bouquetbk.com/',
        'location' => 'Bouquet',
    ],
    [
        'name' => 'Red Sorghum',
        'description' => 'Hunan cuisine restaurant in Long Island City.',
        'base_url' => 'https://www.redsorghumlic.com/',
        'location' => 'Red Sorghum',
    ],
    [
        'name' => 'SAINT',
        'description' => 'Restaurant, bar, and speakeasy at 136 2nd Ave in the East Village.',
        'base_url' => 'https://saintny.com/',
        'location' => 'SAINT',
    ],
    [
        'name' => 'Bkloft26',
        'description' => 'Event space at 153 26th St in Brooklyn.',
        'base_url' => 'https://bkloft26.com/',
        'location' => 'Bkloft26',
    ],
    [
        'name' => 'Ainslie Bowery',
        'description' => 'Multi-level Italian dining and events venue at 199 Bowery.',
        'base_url' => 'https://ainsliebowery.com/',
        'location' => 'Ainslie Bowery',
    ],
    [
        'name' => "Nature's Grill Cafe",
        'description' => 'Cafe on Hylan Blvd in Staten Island.',
        'base_url' => 'https://www.naturesgrillcafe.com/',
        'location' => "Nature's Grill Cafe",
    ],
    [
        'name' => 'Élan Flowers',
        'description' => 'Flower shop at 1 Worth St in Tribeca.',
        'base_url' => 'https://elanflowers.com/',
        'location' => 'Élan Flowers',
    ],
    [
        'name' => "Misha's Flower Shop",
        'description' => 'Flower shop at 299 Knickerbocker Ave in Brooklyn.',
        'base_url' => 'https://mishasflowershop.com/',
        'location' => "Misha's Flower Shop",
    ],
    [
        'name' => 'AMC 34th Street 14',
        'description' => 'AMC movie theater at 312 W 34th St in Midtown Manhattan.',
        'base_url' => 'https://www.amctheatres.com/movie-theatres/new-york-city/amc-34th-street-14',
        'location' => 'AMC 34th Street 14',
    ],
    [
        'name' => 'Bananas',
        'description' => 'Restaurant at 174 1st Ave in the East Village.',
        'base_url' => 'https://www.bananasrestaurant.com/',
        'location' => 'Bananas',
    ],
    [
        'name' => 'The Pierre',
        'description' => 'Luxury hotel at 2 E 61st St on the Upper East Side.',
        'base_url' => 'https://www.thepierreny.com/',
        'location' => 'The Pierre',
    ],
    [
        'name' => 'Random House Tower',
        'description' => 'Penguin Random House corporate headquarters at 1745 Broadway.',
        'base_url' => 'https://www.penguinrandomhouse.com/',
        'location' => 'Random House Tower',
    ],
    [
        'name' => 'The Glen Oaks Club',
        'description' => 'Private golf club in Old Westbury, Long Island.',
        'base_url' => 'https://www.glenoaksclub.org/',
        'location' => 'The Glen Oaks Club',
    ],
    [
        'name' => 'EmblemHealth Neighborhood Care Chinatown',
        'description' => 'EmblemHealth community health center at 87 Bowery in Chinatown.',
        'base_url' => 'https://www.emblemhealth.com/',
        'location' => 'EmblemHealth Neighborhood Care Chinatown',
    ],
    [
        'name' => 'Mingles Event Space',
        'description' => 'Event venue at 4012 Boston Rd in the Bronx.',
        'base_url' => 'https://minglesnyc.com/',
        'location' => 'Mingles Event Space',
    ],
    [
        'name' => 'The Word Is Change',
        'description' => 'Neighborhood bookstore in Bed-Stuy selling used and new books and hosting readings.',
        'base_url' => 'https://www.thewordischange.com/',
        'location' => 'The Word Is Change',
    ],
    [
        'name' => 'Springs Projects',
        'description' => 'Art space at 20 Jay St in DUMBO, Brooklyn.',
        'base_url' => 'https://www.springsprojects.com/',
        'location' => 'Springs Projects',
        'tags' => ['Art'],
    ],
    // === Remaining misc locations ===
    [
        'name' => 'Knights of Columbus Hall (Flushing)',
        'description' => 'Knights of Columbus hall in Flushing, Queens used for community events.',
        'base_url' => 'https://en.wikipedia.org/wiki/Knights_of_Columbus',
        'location' => 'Knights of Columbus Hall',
    ],
    [
        'name' => 'The Castle at Fort Totten',
        'description' => 'Historic structure in Fort Totten Park, Bayside, Queens.',
        'base_url' => 'https://www.nycgovparks.org/parks/fort-totten-park',
        'location' => 'The Castle at Fort Totten',
    ],
    [
        'name' => 'Kwame Ture Recreation Center',
        'description' => 'NYC Parks recreation center in the Highbridge section of the Bronx.',
        'base_url' => 'https://www.nycgovparks.org/facilities/recreationcenters/B089',
        'location' => 'Kwame Ture Recreation Center',
    ],
    [
        'name' => 'High School of Fashion Industries',
        'description' => 'NYC public high school in Chelsea focused on fashion and design.',
        'base_url' => 'https://en.wikipedia.org/wiki/High_School_of_Fashion_Industries',
        'location' => 'High School of Fashion Industries',
    ],
    [
        'name' => 'Queens UFT Office',
        'description' => 'United Federation of Teachers office in Forest Hills, Queens.',
        'base_url' => 'https://www.uft.org/',
        'location' => 'Queens UFT Office',
    ],
    [
        'name' => 'Albee Square',
        'description' => 'Public plaza in Downtown Brooklyn.',
        'base_url' => 'https://en.wikipedia.org/wiki/Albee_Square',
        'location' => 'Albee Square',
    ],
    [
        'name' => '1 Liberty Plaza',
        'description' => 'Office tower in Lower Manhattan near the World Trade Center.',
        'base_url' => 'https://en.wikipedia.org/wiki/One_Liberty_Plaza',
        'location' => '1 Liberty Plaza',
    ],
    [
        'name' => 'Jefferson Gardens',
        'description' => 'Community garden at 300 E 115th St in East Harlem.',
        'base_url' => 'https://www.nycgovparks.org/parks/jefferson-garden',
        'location' => 'Jefferson Gardens',
    ],
    [
        'name' => "Jemmy's Dog Run",
        'description' => 'Dog run in Madison Square Park, Manhattan.',
        'base_url' => 'https://www.nycgovparks.org/parks/madison-square-park',
        'location' => "Jemmy's Dog Run",
    ],
    [
        'name' => "O'Byrne Chapel at Manhattanville University",
        'description' => 'Chapel at Manhattanville University in Purchase, NY.',
        'base_url' => 'https://www.mville.edu/',
        'location' => "O'Byrne Chapel at Manhattanville University",
    ],
    [
        'name' => '2900 Southern Boulevard',
        'description' => 'Location near the New York Botanical Garden in the Bronx.',
        'base_url' => 'https://en.wikipedia.org/wiki/Belmont,_Bronx',
        'location' => '2900 Southern Boulevard',
    ],
    [
        'name' => '44 Union Square East',
        'description' => 'Building in Union Square, Manhattan.',
        'base_url' => 'https://en.wikipedia.org/wiki/Union_Square,_Manhattan',
        'location' => '44 Union Square East',
    ],
    [
        'name' => '506 Fifth Avenue',
        'description' => 'Building on Fifth Avenue in Midtown Manhattan.',
        'base_url' => 'https://en.wikipedia.org/wiki/Fifth_Avenue',
        'location' => '506 Fifth Avenue',
    ],
    [
        'name' => '15-39 Covert St',
        'description' => 'Address in Ridgewood, Queens.',
        'base_url' => 'https://en.wikipedia.org/wiki/Ridgewood,_Queens',
        'location' => '15-39 Covert St',
    ],
    [
        'name' => 'Lafayette Street, Tribeca',
        'description' => 'Location in the Tribeca neighborhood of Manhattan.',
        'base_url' => 'https://en.wikipedia.org/wiki/Tribeca',
        'location' => 'Lafayette Street, Tribeca',
    ],
    [
        'name' => '21 Golf Range',
        'description' => 'Golf driving range in Palisades Park, NJ.',
        'base_url' => 'https://en.wikipedia.org/wiki/Palisades_Park,_New_Jersey',
        'location' => '21 Golf Range',
    ],
    [
        'name' => 'Salon on Kingston',
        'description' => 'Venue at 105 Kingston Ave in Crown Heights, Brooklyn.',
        'base_url' => 'https://en.wikipedia.org/wiki/Crown_Heights,_Brooklyn',
        'location' => 'Salon on Kingston',
    ],
    // === Neighborhoods (Wikipedia) ===
    [
        'name' => 'Chelsea, Manhattan',
        'description' => 'Neighborhood in the west side of the borough of Manhattan in New York City.',
        'base_url' => 'https://en.wikipedia.org/wiki/Chelsea,_Manhattan',
        'location' => 'Chelsea',
    ],
    [
        'name' => 'Williamsburg, Brooklyn',
        'description' => 'Neighborhood in the north side of the borough of Brooklyn in New York City.',
        'base_url' => 'https://en.wikipedia.org/wiki/Williamsburg,_Brooklyn',
        'location' => 'Williamsburg',
    ],
    [
        'name' => 'Garment District, Manhattan',
        'description' => 'Neighborhood in Midtown Manhattan known for its fashion industry.',
        'base_url' => 'https://en.wikipedia.org/wiki/Garment_District,_Manhattan',
        'location' => 'Garment District',
    ],
    [
        'name' => 'Harlem',
        'description' => 'Neighborhood in the northern section of the borough of Manhattan in New York City.',
        'base_url' => 'https://en.wikipedia.org/wiki/Harlem',
        'location' => 'Harlem',
    ],
    [
        'name' => 'Midtown Manhattan',
        'description' => 'Central business district of Manhattan, New York City.',
        'base_url' => 'https://en.wikipedia.org/wiki/Midtown_Manhattan',
        'location' => 'Midtown Manhattan',
    ],
    [
        'name' => 'Downtown Brooklyn',
        'description' => 'Central business district of the borough of Brooklyn in New York City.',
        'base_url' => 'https://en.wikipedia.org/wiki/Downtown_Brooklyn',
        'location' => 'Downtown Brooklyn',
    ],
    [
        'name' => 'Flatbush, Brooklyn',
        'description' => 'Neighborhood in the center of the borough of Brooklyn in New York City.',
        'base_url' => 'https://en.wikipedia.org/wiki/Flatbush,_Brooklyn',
        'location' => 'Flatbush',
    ],
    [
        'name' => 'Long Island City',
        'description' => 'Neighborhood on the western tip of the borough of Queens in New York City.',
        'base_url' => 'https://en.wikipedia.org/wiki/Long_Island_City',
        'location' => 'Long Island City',
    ],
    [
        'name' => 'East Village, Manhattan',
        'description' => 'Neighborhood on the east side of Lower Manhattan in New York City.',
        'base_url' => 'https://en.wikipedia.org/wiki/East_Village,_Manhattan',
        'location' => 'East Village',
    ],
    [
        'name' => 'Bedford-Stuyvesant',
        'description' => 'Neighborhood in the north-central portion of the borough of Brooklyn in New York City.',
        'base_url' => 'https://en.wikipedia.org/wiki/Bedford%E2%80%93Stuyvesant,_Brooklyn',
        'location' => 'Bedford-Stuyvesant',
    ],
    [
        'name' => 'Upper East Side',
        'description' => 'Neighborhood in the borough of Manhattan in New York City.',
        'base_url' => 'https://en.wikipedia.org/wiki/Upper_East_Side',
        'location' => 'Upper East Side',
    ],
    [
        'name' => "Hell's Kitchen, Manhattan",
        'description' => 'Neighborhood on the West Side of Midtown Manhattan in New York City.',
        'base_url' => "https://en.wikipedia.org/wiki/Hell%27s_Kitchen,_Manhattan",
        'location' => "Hell's Kitchen",
    ],
    [
        'name' => 'Greenpoint, Brooklyn',
        'description' => 'Neighborhood at the northern tip of the borough of Brooklyn in New York City.',
        'base_url' => 'https://en.wikipedia.org/wiki/Greenpoint,_Brooklyn',
        'location' => 'Greenpoint',
    ],
    [
        'name' => 'Tribeca',
        'description' => 'Neighborhood in Lower Manhattan, New York City.',
        'base_url' => 'https://en.wikipedia.org/wiki/Tribeca',
        'location' => 'Tribeca',
    ],
    [
        'name' => 'Washington Heights, Manhattan',
        'description' => 'Neighborhood in the northern portion of the borough of Manhattan in New York City.',
        'base_url' => 'https://en.wikipedia.org/wiki/Washington_Heights,_Manhattan',
        'location' => 'Washington Heights',
    ],
    [
        'name' => "Ladies' Mile Historic District",
        'description' => 'Historic district in Manhattan known for its cast-iron buildings and former department stores.',
        'base_url' => "https://en.wikipedia.org/wiki/Ladies%27_Mile_Historic_District",
        'location' => "Ladies' Mile Historic District",
    ],
    // === Broadway Theaters ===
    [
        'name' => 'Booth Theatre',
        'description' => 'Shubert Organization Broadway theater at 222 W 45th St with 766 seats, opened in 1913.',
        'base_url' => 'https://shubert.nyc/theatres/booth/',
        'location' => 'Booth Theatre',
        'tags' => ['Theater'],
    ],
    [
        'name' => 'Al Hirschfeld Theatre',
        'description' => 'Jujamcyn-owned Broadway theater at 302 W 45th St, opened in 1924.',
        'base_url' => 'https://www.jujamcyn.com/theatres/al-hirschfeld',
        'location' => 'Al Hirschfeld Theatre',
        'tags' => ['Theater'],
    ],
    [
        'name' => 'Imperial Theatre',
        'description' => 'Shubert Organization Broadway theater at 249 W 45th St with 1,417 seats, opened in 1923.',
        'base_url' => 'https://shubert.nyc/theatres/imperial/',
        'location' => 'Imperial Theatre',
        'tags' => ['Theater'],
    ],
    [
        'name' => 'Music Box Theatre',
        'description' => 'Shubert Organization Broadway theater at 239 W 45th St with 1,009 seats, opened in 1921.',
        'base_url' => 'https://shubert.nyc/theatres/music-box/',
        'location' => 'Music Box Theatre',
        'tags' => ['Theater'],
    ],
    [
        'name' => 'Golden Theatre',
        'description' => 'Shubert Organization Broadway theater at 252 W 45th St with 805 seats, opened in 1927.',
        'base_url' => 'https://shubert.nyc/theatres/golden/',
        'location' => 'Golden Theatre',
        'tags' => ['Theater'],
    ],
    [
        'name' => 'Lincoln Center Theater - Claire Tow',
        'description' => 'Intimate theater atop the Vivian Beaumont at Lincoln Center for new work development.',
        'base_url' => 'https://www.lct.org/',
        'location' => 'Lincoln Center Theater - Claire Tow',
        'tags' => ['Theater'],
    ],
    // === Parks ===
    [
        'name' => 'Thomas Jefferson Park',
        'description' => 'NYC Parks facility in East Harlem with a pool, playground, and recreation center.',
        'base_url' => 'https://www.nycgovparks.org/parks/thomas-jefferson-park',
        'location' => 'Thomas Jefferson Park',
    ],
    [
        'name' => 'Alley Pond Park',
        'description' => 'NYC park in Queens featuring wetlands, trails, and the Alley Pond Environmental Center.',
        'base_url' => 'https://www.nycgovparks.org/parks/alley-pond-park',
        'location' => 'Alley Pond Park',
    ],
    [
        'name' => 'Goodhue Park',
        'description' => 'Small park in the St. George neighborhood of Staten Island.',
        'base_url' => 'https://www.nycgovparks.org/parks/goodhue-park',
        'location' => 'Goodhue Park',
    ],
    [
        'name' => 'Lemon Creek Park',
        'description' => 'NYC park in the Pleasant Plains neighborhood of Staten Island.',
        'base_url' => 'https://www.nycgovparks.org/parks/lemon-creek-park',
        'location' => 'Lemon Creek Park',
    ],
    [
        'name' => 'Soundview Park',
        'description' => 'NYC park in the Soundview neighborhood of the Bronx along the Bronx River.',
        'base_url' => 'https://www.nycgovparks.org/parks/soundview-park',
        'location' => 'Soundview Park',
    ],
    [
        'name' => 'Kissena Corridor Park',
        'description' => 'Linear park in Flushing, Queens connecting Kissena Park to other green spaces.',
        'base_url' => 'https://www.nycgovparks.org/parks/kissena-corridor-park',
        'location' => 'Kissena Corridor Park',
    ],
    [
        'name' => 'Idlewild Park',
        'description' => 'NYC park in Springfield Gardens, Queens near JFK Airport with nature trails.',
        'base_url' => 'https://www.nycgovparks.org/parks/idlewild-park-preserve',
        'location' => 'Idlewild Park',
    ],
    [
        'name' => 'Prospect Park Carousel',
        'description' => 'Historic carousel in Prospect Park, Brooklyn operated by NYC Parks.',
        'base_url' => 'https://www.nycgovparks.org/parks/prospect-park',
        'location' => 'Prospect Park Carousel',
    ],
    [
        'name' => 'Pier 76 in Hudson River Park',
        'description' => 'Public open space on the Hudson River waterfront in Midtown Manhattan.',
        'base_url' => 'https://hudsonriverpark.org/the-park/parks-attractions/pier-76/',
        'location' => 'Pier 76 in Hudson River Park',
    ],
    [
        'name' => 'Shu Swamp Nature Preserve',
        'description' => 'Nature preserve in Mill Neck, Long Island managed by the North Shore Wildlife Sanctuary.',
        'base_url' => 'https://en.wikipedia.org/wiki/Shu_Swamp',
        'location' => 'Shu Swamp Nature Preserve',
    ],
    [
        'name' => 'Walkway Over the Hudson',
        'description' => 'Historic linear park spanning the Hudson River in Poughkeepsie, NY.',
        'base_url' => 'https://walkway.org/',
        'location' => 'Walkway Over the Hudson',
    ],
    [
        'name' => 'Sunset Park Recreation Center',
        'description' => 'NYC Parks recreation center in Sunset Park, Brooklyn.',
        'base_url' => 'https://www.nycgovparks.org/parks/sunset-park',
        'location' => 'Sunset Park Recreation Center',
    ],
    // === Community Gardens ===
    [
        'name' => 'Maple Street Community Garden',
        'description' => 'Community garden in Prospect Lefferts Gardens, Brooklyn.',
        'base_url' => 'https://www.nycgovparks.org/parks/maple-street-community-garden',
        'location' => 'Maple Street Community Garden',
    ],
    [
        'name' => 'Frank White Memorial Garden',
        'description' => 'Community garden at 506 W 143rd St in Hamilton Heights, Manhattan.',
        'base_url' => 'https://www.nycgovparks.org/parks/frank-white-memorial-garden',
        'location' => 'Frank White Memorial Garden',
    ],
    [
        'name' => 'Olive Street Garden',
        'description' => 'Community garden in Williamsburg, Brooklyn.',
        'base_url' => 'https://www.nycgovparks.org/parks/olive-street-garden',
        'location' => 'Olive Street Garden',
    ],
    [
        'name' => '400 Montauk Community Garden',
        'description' => 'Community garden in East New York, Brooklyn.',
        'base_url' => 'https://www.nycgovparks.org/parks/400-montauk-community-garden',
        'location' => '400 Montauk Community Garden',
    ],
    [
        'name' => 'Harlem Valley Garden',
        'description' => 'Community garden at 197 W 134th St in Harlem, Manhattan.',
        'base_url' => 'https://www.nycgovparks.org/parks/harlem-valley-garden',
        'location' => 'Harlem Valley Garden',
    ],
    [
        'name' => "Brooklyn's Finest Garden",
        'description' => 'Community garden at 48 Lefferts Pl in Clinton Hill, Brooklyn.',
        'base_url' => 'https://www.nycgovparks.org/parks/brooklyns-finest-garden',
        'location' => "Brooklyn's Finest Garden",
    ],
    [
        'name' => 'Amboy Street Garden',
        'description' => 'Community garden at 208 Amboy St in Brownsville, Brooklyn.',
        'base_url' => 'https://www.nycgovparks.org/parks/amboy-street-garden',
        'location' => 'Amboy Street Garden',
    ],
    // === Libraries ===
    [
        'name' => 'Uniondale Public Library',
        'description' => 'Public library serving the Uniondale community on Long Island.',
        'base_url' => 'https://www.uniondalelibrary.org/',
        'location' => 'Uniondale Public Library',
    ],
    [
        'name' => 'DeKalb Library',
        'description' => 'Brooklyn Public Library branch at 790 Bushwick Ave in Bushwick.',
        'base_url' => 'https://www.bklynlibrary.org/locations/dekalb',
        'location' => 'DeKalb Library',
    ],
    [
        'name' => 'Sedgwick Library',
        'description' => 'New York Public Library branch in the University Heights neighborhood of the Bronx.',
        'base_url' => 'https://www.nypl.org/locations/sedgwick',
        'location' => 'Sedgwick Library',
    ],
    [
        'name' => 'Bedford Library',
        'description' => 'Brooklyn Public Library branch at 496 Franklin Ave in Bedford-Stuyvesant.',
        'base_url' => 'https://www.bklynlibrary.org/locations/bedford',
        'location' => 'Bedford Library',
    ],
    // === Street / Address locations (Wikipedia or Google Maps) ===
    [
        'name' => 'Murray Hill, Manhattan',
        'description' => 'Neighborhood in Midtown Manhattan, New York City.',
        'base_url' => 'https://en.wikipedia.org/wiki/Murray_Hill,_Manhattan',
        'location' => 'Park Avenue, Murray Hill',
    ],
    [
        'name' => 'Sheepshead Bay, Brooklyn',
        'description' => 'Neighborhood in the southern portion of the borough of Brooklyn.',
        'base_url' => 'https://en.wikipedia.org/wiki/Sheepshead_Bay,_Brooklyn',
        'location' => 'Avenue Z, Sheepshead Bay',
    ],
    [
        'name' => 'Woodlawn, Bronx',
        'description' => 'Neighborhood in the northern part of the Bronx.',
        'base_url' => 'https://en.wikipedia.org/wiki/Woodlawn,_Bronx',
        'location' => 'Jerome Avenue, Woodlawn',
    ],
    [
        'name' => 'Oakwood, Staten Island',
        'description' => 'Neighborhood on the East Shore of Staten Island.',
        'base_url' => 'https://en.wikipedia.org/wiki/Oakwood,_Staten_Island',
        'location' => 'Oakwood Beach',
    ],
    [
        'name' => 'Flushing, Queens',
        'description' => 'Neighborhood in the north-central part of the borough of Queens.',
        'base_url' => 'https://en.wikipedia.org/wiki/Flushing,_Queens',
        'location' => 'Prince Street, Flushing',
    ],
    [
        'name' => 'Harbor Square, Ossining',
        'description' => 'Waterfront area in the Village of Ossining, Westchester County.',
        'base_url' => 'https://en.wikipedia.org/wiki/Ossining_(village),_New_York',
        'location' => 'Harbor Square',
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
