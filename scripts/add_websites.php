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
$prev_websites = [
    // Brooklyn Bridge parkrun added on 2026-02-22 - see git history
    // Previous batch - see git history
    ['name' => 'Ciao Ciao Disco', 'base_url' => 'https://www.ciaociaodisco.com/', 'location' => 'Ciao Ciao Disco'],
    ['name' => 'Eavesdrop', 'base_url' => 'https://www.eavesdrop.nyc/', 'location' => 'Eavesdrop'],
    ['name' => 'EDEN NYC', 'base_url' => 'https://www.edennewyork.com/', 'location' => 'EDEN NYC'],
    ['name' => 'Hart Island', 'base_url' => 'https://www.nyc.gov/site/hartisland/index.page', 'location' => 'Hart Island'],
    ['name' => 'Here.BK', 'base_url' => 'https://www.herebk.com/', 'location' => 'Here.BK'],
    ['name' => 'Hyatt Place Midtown-South', 'base_url' => 'https://www.hyatt.com/hyatt-place/en-US/nyczm-hyatt-place-new-york-midtown-south', 'location' => 'Hyatt Place New York/Midtown-South'],
    ['name' => 'Kismat', 'base_url' => 'https://www.kismatrestaurant.com/', 'location' => 'Kismat'],
    ['name' => 'New Settlement Community Center', 'base_url' => 'https://newsettlement.org/', 'location' => 'New Settlement Community Center'],
    ['name' => 'The Club by Mr. Purple', 'base_url' => 'https://www.mrpurplenyc.com/', 'location' => 'The Club by Mr. Purple'],
    ['name' => 'The Onyx Room', 'base_url' => 'https://www.theonyxroom.nyc/', 'location' => 'The Onyx Room'],
    ['name' => 'Ace Hotel Brooklyn', 'base_url' => 'https://acehotel.com/brooklyn/', 'location' => 'Ace Hotel Brooklyn'],
    ['name' => 'Motto by Hilton Chelsea', 'base_url' => 'https://www.hilton.com/en/hotels/nycdlua-motto-new-york-city-chelsea/', 'location' => 'Motto by Hilton (Chelsea)'],
    ['name' => 'Vesuvio Restaurant', 'base_url' => 'https://vesuviobayridge.com/', 'location' => 'Vesuvio Restaurant'],
    ['name' => 'GuestHouse Restaurant & Bar', 'base_url' => 'https://guesthouse265.com/', 'location' => 'GuestHouse Restaurant & Bar'],
    ['name' => 'Industry Kitchen', 'base_url' => 'https://www.industry-kitchen.com/', 'location' => 'Industry Kitchen'],
    ["name" => "Mama's TOO!", 'base_url' => 'https://www.mamastoo.com/', 'location' => "Mama's TOO!"],
    ['name' => 'New York Beer Dispensary', 'base_url' => 'https://www.nybeerdispensary.com/', 'location' => 'New York Beer Dispensary'],
    ['name' => 'Dutch Baby Bakery', 'base_url' => 'https://www.dutchbabybakery.com/', 'location' => 'Dutch Baby Bakery'],
    ['name' => 'Table 87', 'base_url' => 'https://www.table87.com/', 'location' => 'Table 87'],
    ['name' => 'Nexo', 'base_url' => 'https://nexonyc.com/', 'location' => 'Nexo'],
    ['name' => 'Abilene', 'base_url' => 'https://www.abilenebarbrooklyn.com/', 'location' => 'Abilene'],
    ['name' => 'Alphabet City Beer Co', 'base_url' => 'https://www.abcbeer.co/', 'location' => 'Alphabet City Beer Co'],
    ['name' => 'Another Country', 'base_url' => 'https://www.anothercountry.nyc/', 'location' => 'Another Country'],
    ['name' => 'Anything Bar', 'base_url' => 'https://anythingbklyn.com/', 'location' => 'Anything Bar'],
    ['name' => 'Banter Bar', 'base_url' => 'https://banterbrooklyn.com/', 'location' => 'Banter Bar'],
    ['name' => 'Barrow Street Alehouse', 'base_url' => 'https://barrowstreetalehouse.com/', 'location' => 'Barrow Street Alehouse'],
    ['name' => 'Black Horse Pub', 'base_url' => 'https://www.blackhorsebrooklyn.com/', 'location' => 'Black Horse Pub'],
    ['name' => 'Black Rabbit', 'base_url' => 'https://blackrabbitbar.com/', 'location' => 'Black Rabbit'],
    ['name' => 'Brindle Room', 'base_url' => 'https://brindleroomny.com/', 'location' => 'Brindle Room'],
    ['name' => "Caf\u{00E9} Balearica", 'base_url' => 'https://www.cafebalearica.com/', 'location' => "Caf\u{00E9} Balearica"],
    ['name' => 'Caffeine Underground', 'base_url' => 'https://www.caffeineunderground.com/', 'location' => 'Caffeine Underground'],
    ['name' => 'Circa Brewing Co', 'base_url' => 'https://www.circabrewing.co/', 'location' => 'Circa Brewing Co'],
    ['name' => 'Common Mollies', 'base_url' => 'https://commonmolliesnyc.com/', 'location' => 'Common Mollies'],
    ['name' => 'Commonwealth', 'base_url' => 'https://commonwealthbar.com/', 'location' => 'Commonwealth'],
    ['name' => 'Covenhoven', 'base_url' => 'https://www.covenhovennyc.com/', 'location' => 'Covenhoven'],
    ['name' => 'Crossroads Cafe', 'base_url' => 'https://www.xroads.cafe/', 'location' => 'Crossroads Cafe'],
    ['name' => 'Emblem Sports Bar', 'base_url' => 'https://www.emblembk.com/', 'location' => 'Emblem Sports Bar'],
    ['name' => 'Endless Life Brewing', 'base_url' => 'https://www.endlesslifebrewing.com/', 'location' => 'Endless Life Brewing'],
    ["name" => "Everything's Jake NYC", 'base_url' => 'https://everythingsjake.com/', 'location' => "Everything's Jake NYC Bar & Lounge"],
    ['name' => 'Fette Sau', 'base_url' => 'http://www.fettesaubbq.com/', 'location' => 'Fette Sau'],
    ['name' => 'Fine Time', 'base_url' => 'https://www.finetimebar.com/', 'location' => 'Fine Time'],
    ['name' => 'Franklin Park', 'base_url' => 'https://www.franklinparkbk.com/', 'location' => 'Franklin Park'],
    ['name' => 'Fulton Hall', 'base_url' => 'https://fultonhall.com/', 'location' => 'Fulton Hall'],
    ['name' => 'Hair of the Dog', 'base_url' => 'https://www.hairofthedognyc.com/', 'location' => 'Hair of the Dog'],
    ['name' => 'Halyards', 'base_url' => 'https://barhalyards.com/', 'location' => 'Halyards'],
    ['name' => 'Hamilton Hall', 'base_url' => 'https://hamiltonhallnyc.com/', 'location' => 'Hamilton Hall'],
    ["name" => "Hendrickson's", 'base_url' => 'https://www.hendricksonsnyc.com/', 'location' => "Hendrickson's"],
    ['name' => 'Houston Hall', 'base_url' => 'https://www.houstonhallny.com/', 'location' => 'Houston Hall'],
    ["name" => "Jean's", 'base_url' => 'https://jeans.nyc/', 'location' => "Jean's"],
    ["name" => "Joanne's Trattoria", 'base_url' => 'https://joannenyc.com/', 'location' => "Joanne's Trattoria"],
    ['name' => 'Le Pistol Bar & Cafe', 'base_url' => 'https://www.lepistolbk.com/', 'location' => 'Le Pistol Bar & Cafe'],
    ['name' => 'Lexington Publick', 'base_url' => 'https://www.lexingtonpublicknyc.com/', 'location' => 'Lexington Publick'],
    ['name' => 'LoHi', 'base_url' => 'https://www.lohibk.com/', 'location' => 'LoHi'],
    ["name" => "Loafer's Cocktail Bar", 'base_url' => 'https://loafersbar.com/', 'location' => "Loafer's Cocktail Bar"],
    ['name' => 'Mad Donkey Beer Bar & Grill', 'base_url' => 'https://maddonkeybar.com/', 'location' => 'Mad Donkey Beer Bar & Grill'],
    ['name' => 'Maiden Lane', 'base_url' => 'http://www.themaidenlane.com/', 'location' => 'Maiden Lane'],
    ["name" => "Mama's Bar", 'base_url' => 'https://www.mamasbar.nyc/', 'location' => "Mama\u{2019}s Bar"],
    ['name' => 'Mess Hall', 'base_url' => 'https://www.messhallharlem.com/', 'location' => 'Mess Hall'],
    ['name' => 'Milk & Hops', 'base_url' => 'https://www.milknhops.com/', 'location' => 'Milk & Hops'],
    ['name' => 'Montague Diner', 'base_url' => 'https://montaguediner.com/', 'location' => 'Montague Diner'],
    ["name" => "Mommy's Bar", 'base_url' => 'https://www.mommysbar.com/', 'location' => "Mommy's Bar"],
    ['name' => 'Moot Bar', 'base_url' => 'https://www.mootbar.com/', 'location' => 'Moot Bar'],
    ['name' => 'Peculier Pub', 'base_url' => 'http://www.peculierpub.com/', 'location' => 'Peculier Pub'],
    ['name' => 'Pubkey NYC', 'base_url' => 'https://www.pubkey.bar/', 'location' => 'Pubkey NYC'],
    ["name" => "Reilly's Plates & Pours", 'base_url' => 'https://reillysnyc.com/', 'location' => "Reilly\u{2019}s Plates & Pours"],
    ["name" => "Rudy's Bar and Grill", 'base_url' => 'https://rudysbarnyc.com/', 'location' => "Rudy's Bar and Grill"],
    ["name" => "Ryan Maguire's", 'base_url' => 'https://ryanmaguiresalehouse.com/', 'location' => "Ryan Maguire\u{2019}s"],
    ["name" => "Saluggi's East", 'base_url' => 'https://east.saluggis.com/', 'location' => "Saluggi\u{2019}s East"],
    ['name' => 'Skylark', 'base_url' => 'https://www.skylarkbarbrooklyn.com/', 'location' => 'Skylark'],
    ['name' => 'Solas', 'base_url' => 'https://www.solasbar.com/', 'location' => 'Solas'],
    ['name' => 'Solid State', 'base_url' => 'https://solidstatenyc.com/', 'location' => 'Solid State'],
    ['name' => 'Spritzenhaus 33', 'base_url' => 'https://www.spritzenhaus33.com/', 'location' => 'Spritzenhaus 33'],
    ['name' => 'The Bad Old Days', 'base_url' => 'https://thebadolddays.com/', 'location' => 'The Bad Old Days'],
    ['name' => 'The Commissioner', 'base_url' => 'https://thecommissionerbk.com/', 'location' => 'The Commissioner'],
    ['name' => 'The Dakota Bar', 'base_url' => 'https://www.thedakotabar.nyc/', 'location' => 'The Dakota Bar'],
    ['name' => 'The Gray Mare', 'base_url' => 'https://www.thegraymarenyc.com/', 'location' => 'The Gray Mare'],
    ['name' => 'The High Note', 'base_url' => 'https://www.thehighnoteny.com/', 'location' => 'The High Note'],
    ['name' => 'The Hunterian', 'base_url' => 'https://thehunterianues.com/', 'location' => 'The Hunterian'],
    ['name' => 'The Mayfly', 'base_url' => 'https://themayflynyc.com/', 'location' => 'The Mayfly'],
    ['name' => 'The Overlook Bar', 'base_url' => 'https://overlooknyc.com/', 'location' => 'The Overlook Bar'],
    ['name' => 'The Waylon', 'base_url' => 'https://www.thewaylon.com/', 'location' => 'The Waylon'],
    ['name' => 'The Winslow', 'base_url' => 'https://thewinslownyc.com/', 'location' => 'The Winslow'],
    ['name' => 'Ten Degrees', 'base_url' => 'https://www.tendegreesbar.com/', 'location' => 'Ten Degrees'],
    ['name' => 'Treadwell Park', 'base_url' => 'https://www.treadwellpark.com/', 'location' => 'Treadwell Park'],
    ["name" => "Triona's On Third", 'base_url' => 'https://nyctrionas.com/', 'location' => "Triona\u{2019}s On Third"],
    ["name" => "Triona's Sullivan Street", 'base_url' => 'https://nyctrionas.com/', 'location' => "Triona\u{2019}s Sullivan Street"],
    ["name" => "Uncle Barry's", 'base_url' => 'https://www.unclebarrys.com/', 'location' => "Uncle Barry's"],
    ['name' => 'Valhalla Bar', 'base_url' => 'https://valhallabarnyc.com/', 'location' => 'Valhalla Bar'],
    ['name' => 'Vineapple Cafe', 'base_url' => 'https://www.vineapple.cafe/', 'location' => 'Vineapple Cafe'],
    ['name' => 'one star bar', 'base_url' => 'http://onestarnyc.com/', 'location' => 'one star bar'],
    ['name' => 'Home Sweet Home', 'base_url' => 'https://www.homesweethomethebar.com/', 'location' => 'Home Sweet Home'],
    ['name' => 'Hart Bar', 'base_url' => 'https://www.hartbarnyc.com/', 'location' => 'Hart Bar'],
    ["name" => "Rebecca's", 'base_url' => 'https://www.rebeccasbar.com/', 'location' => "Rebecca's"],
    ['name' => 'Bar 13', 'base_url' => 'https://www.bar13nyc.com/', 'location' => 'Bar 13'],
    ['name' => 'Grand Central Terminal', 'base_url' => 'https://grandcentralterminal.com/', 'location' => 'Grand Central Station'],

    // Batch 3h: Remaining venues - arts, institutions, historic sites, other (1 event)
    ['name' => 'Body by Brooklyn', 'base_url' => 'https://bodybybrooklyn.com/', 'location' => 'Body by Brooklyn'],
    ['name' => 'Hana House', 'base_url' => 'https://www.hanahouseny.com/', 'location' => 'Hana House'],
    ['name' => 'Kitsby', 'base_url' => 'https://www.kitsby.com/', 'location' => 'Kitsby'],
    ['name' => 'Fit4Dance', 'base_url' => 'https://fit4dancenyc.com/', 'location' => 'Fit4Dance'],
    ['name' => 'Nublu Classic', 'base_url' => 'https://nublu.net/', 'location' => 'Nublu Classic'],
    ['name' => 'Fifth Hammer Brewing Co.', 'base_url' => 'https://www.fifthhammerbrewing.com/', 'location' => 'Fifth Hammer Brewing Co.'],
    ['name' => 'Edgar Allan Poe Cottage', 'base_url' => 'https://bronxhistoricalsociety.org/poe-cottage', 'location' => 'Edgar Allan Poe Cottage'],
    ['name' => 'The Glasshouse', 'base_url' => 'https://www.theglasshouses.com/', 'location' => 'The Glass House'],
    ['name' => 'Kingsland Homestead', 'base_url' => 'https://queenshistoricalsociety.org/kingsland-homestead/', 'location' => 'Kingsland Homestead'],
    ['name' => 'Valentine-Varian House', 'base_url' => 'https://bronxhistoricalsociety.org/museum', 'location' => 'Valentine-Varian House'],
    ['name' => 'Newark Artist Collaboration', 'base_url' => 'https://www.newarkartistcollaboration.com/', 'location' => 'Newark Artist Collaboration'],
    ['name' => 'The Newark Museum of Art', 'base_url' => 'https://newarkmuseumart.org/', 'location' => 'The Newark Museum of Art'],
    ['name' => 'Herbert Von King Cultural Arts Center', 'base_url' => 'https://www.nycgovparks.org/facilities/recreationcenters/B088', 'location' => 'Herbert Von King Cultural Arts Center'],
    ['name' => 'Vanderbilt Hall', 'base_url' => 'https://grandcentralterminal.com/vanderbilt-hall-venue/', 'location' => 'Vanderbilt Hall at Grand Central Terminal'],
    ['name' => 'CCCADI', 'base_url' => 'https://www.cccadi.org/', 'location' => 'Caribbean Cultural Center African Diaspora Institute (CCCADI)'],
    ['name' => 'Harlem School of the Arts', 'base_url' => 'https://hsanyc.org/', 'location' => 'Harlem School of the Arts'],
    ['name' => 'Van Cortlandt House Museum', 'base_url' => 'https://www.vchm.org/', 'location' => 'Van Cortlandt House Museum'],
    ['name' => 'Sunnyside Community Services', 'base_url' => 'https://scsny.org/', 'location' => 'Sunnyside Community Services'],
    ['name' => 'Hope Gardens Older Adult Center', 'base_url' => 'https://riseboro.org/', 'location' => 'Hope Gardens Older Adult Center'],
    ['name' => 'Brownsville Neighborhood Health Action Center', 'base_url' => 'https://www.nyc.gov/site/doh/health/neighborhood-health/action-center-brownsville.page', 'location' => 'Brownsville Neighborhood Health Action Center'],
    ['name' => 'The Armory', 'base_url' => 'https://allstars.org/', 'location' => 'The Armory'],
    ['name' => 'Rustik Tavern', 'base_url' => 'https://www.rustiktavern.com/', 'location' => 'Rustik Tavern'],
    ['name' => 'Jamaica Bay Wildlife Refuge', 'base_url' => 'https://www.nps.gov/gate/learn/historyculture/jamaica-bay-wildlife-refuge.htm', 'location' => 'Jamaica Bay Wildlife Refuge Visitor Center'],
    ['name' => 'Ripley-Grier Studios', 'base_url' => 'https://ripleygrier.com/', 'location' => 'Ripley-Grier Studios'],
    ['name' => 'SVA Flatiron Gallery', 'base_url' => 'https://sva.edu/', 'location' => 'SVA Flatiron Gallery'],
    ['name' => 'SVA Gramercy Gallery', 'base_url' => 'https://sva.edu/', 'location' => 'SVA Gramercy Gallery'],
    ['name' => 'Tribeca Rooftop', 'base_url' => 'https://tribecarooftopnyc.com/', 'location' => "Tribeca Rooftop + 360\u{00B0}"],
    ['name' => 'Whiskey Cellar NYC', 'base_url' => 'https://www.whiskeycellarnyc.com/', 'location' => 'Whiskey Cellar NYC'],
    ['name' => 'Starrett-Lehigh Building', 'base_url' => 'https://starrett-lehigh.com/', 'location' => 'Starrett-Lehigh Building'],
    ['name' => 'David Rubenstein Atrium', 'base_url' => 'https://www.lincolncenter.org/venue/atrium', 'location' => 'David Rubenstein Atrium'],
    ['name' => 'BAX Annex', 'base_url' => 'https://www.bax.org/', 'location' => 'BAX Annex'],
    ['name' => 'Taiwan Center', 'base_url' => 'https://nytaiwancenter.org/', 'location' => 'Taiwan Center'],
    ['name' => 'Aisling Irish Community and Cultural Center', 'base_url' => 'https://aislingcenter.org/', 'location' => 'Aisling Irish Community and Cultural Center'],
    ['name' => 'Glow Center', 'base_url' => 'https://glownyc.org/', 'location' => 'Glow Center'],
    ["name" => "Christie's New York", 'base_url' => 'https://www.christies.com/', 'location' => "Christie's New York"],
    ['name' => 'CARA', 'base_url' => 'https://www.cara-nyc.org/', 'location' => 'Center for Art, Research and Alliances (CARA)'],
    ['name' => 'Verso Books', 'base_url' => 'https://www.versobooks.com/', 'location' => 'Verso Books'],
    ['name' => 'Joffrey Ballet School LIC', 'base_url' => 'https://www.joffreyballetschool.com/', 'location' => 'Joffrey Ballet School Long Island City'],
    ['name' => 'Sellersville Theater', 'base_url' => 'https://www.st94.com/', 'location' => 'Sellersville Theater'],
    ['name' => 'Rhythmic Arts Center NYC', 'base_url' => 'https://www.rhythmicartscenternyc.com/', 'location' => 'Rhythmic Arts Center NYC'],
    ['name' => 'Premiere Vibes', 'base_url' => 'https://www.premierevibes.com/', 'location' => 'Premiere Vibes Event Design & Production'],
    ['name' => 'Moxy NYC East Village', 'base_url' => 'https://www.marriott.com/en-us/hotels/nycot-moxy-nyc-east-village/overview/', 'location' => 'Moxy NYC East Village'],
    ['name' => 'The Altman Building', 'base_url' => 'https://www.altmanbldg.com/', 'location' => 'The Altman Building'],
    ['name' => 'Brooklyn Kura', 'base_url' => 'https://www.brooklynkura.com/', 'location' => 'Brooklyn Kura'],
    ['name' => 'Eckhart Beer Co.', 'base_url' => 'https://eckhartbeer.com/', 'location' => 'Eckhart Beer Co.'],
    ['name' => "Devocion Williamsburg", 'base_url' => 'https://www.devocion.com/', 'location' => "Devoci\u{00F3}n (Williamsburg)"],
    ['name' => 'Mandala Cafe', 'base_url' => 'https://www.mandalacafe.org/', 'location' => 'Mandala Cafe'],
    ['name' => 'Cipriani 42nd Street', 'base_url' => 'https://ciprianievents.com/', 'location' => 'Cipriani 42nd Street'],
    ['name' => 'Culture House', 'base_url' => 'https://culturehousenyc.com/', 'location' => 'Culture House'],
    ['name' => 'EFA Robert Blackburn Printmaking Workshop', 'base_url' => 'https://www.rbpmw-efanyc.org/', 'location' => 'EFA Robert Blackburn Printmaking Workshop'],
    ['name' => 'The REP Music Cafe', 'base_url' => 'https://www.repmusiccafe.com/', 'location' => 'The REP Music Cafe'],
    ['name' => 'Chez Bushwick', 'base_url' => 'https://www.chezbushwick.net/', 'location' => 'Chez Bushwick'],
    ['name' => 'Commonpoint Bronx Center', 'base_url' => 'https://www.commonpoint.org/', 'location' => 'Commonpoint Bronx Center'],
    ['name' => 'Brooklyn Winery', 'base_url' => 'https://www.bkwinery.com/', 'location' => 'Brooklyn Winery'],
    ['name' => 'Commonpoint Queens Bay Terrace', 'base_url' => 'https://www.commonpoint.org/', 'location' => 'Commonpoint Queens Bay Terrace Center'],
    ['name' => 'Bonus Room', 'base_url' => 'http://bonusroombar.com/', 'location' => 'Bonus Room'],
    ['name' => 'The Seneca', 'base_url' => 'http://www.thesenecanyc.com/', 'location' => 'The Seneca'],
    ['name' => 'AKINO Flushing', 'base_url' => 'https://www.akinonyc.com/', 'location' => 'AKINO Flushing'],
    ['name' => 'Karaoke Boho', 'base_url' => 'https://www.karaokeboho.com/', 'location' => 'Karaoke Boho'],
    ['name' => 'Work Cafe Santander', 'base_url' => 'https://www.santanderbank.com/workcafe/', 'location' => 'Work Cafe Santander'],
    ['name' => 'Ariva', 'base_url' => 'https://ariva.org/', 'location' => 'Ariva'],
    ['name' => 'Lightning Society', 'base_url' => 'https://lightningsociety.com/', 'location' => 'Lightning Society'],
    ['name' => 'Penington Friends House', 'base_url' => 'https://www.penington.org/', 'location' => 'Penington Friends House'],
    ['name' => 'Anyone Comics', 'base_url' => 'https://www.anyonecomics.com/', 'location' => 'Anyone Comics'],
    ['name' => 'Lofty Pigeon Books', 'base_url' => 'https://www.loftypigeonbooks.com/', 'location' => 'Lofty Pigeon Books'],
    ['name' => 'Michaelian Office Building', 'base_url' => 'https://www.westchestergov.com/', 'location' => 'Michaelian Office Building'],
    ['name' => 'H.E.A.L.T.H. for Youths', 'base_url' => 'https://www.health4youths.org/', 'location' => 'H.E.A.L.T.H. for Youths'],
    ['name' => "Z\u{00FC}rcher Gallery", 'base_url' => 'https://www.galeriezurcher.com/', 'location' => "Z\u{00FC}rcher Gallery"],
    ['name' => 'NeueHouse Madison Square', 'base_url' => 'https://www.neuehouse.com/', 'location' => 'NeueHouse Madison Square'],
    ['name' => 'Queens College Art Center', 'base_url' => 'https://www.qc.cuny.edu/academics/soa/queens-college-art-center/', 'location' => 'Queens College Art Center'],
    ['name' => 'Jamaica Colosseum Mall', 'base_url' => 'https://www.thejamaicacolosseummall.com/', 'location' => 'Jamaica Colosseum Mall'],
    ['name' => 'Grimm Taproom', 'base_url' => 'https://grimmales.com/', 'location' => 'Grimm Taproom'],
    ['name' => 'Selva', 'base_url' => 'https://selva.nyc/', 'location' => 'Selva'],

    // Batch 3f: Schools and Universities (1 event)
    ['name' => 'Fordham University at Lincoln Center', 'base_url' => 'https://www.fordham.edu/lincoln-center-campus/', 'location' => 'Fordham University at Lincoln Center'],
    ['name' => 'Kingsborough Community College', 'base_url' => 'https://www.kbcc.cuny.edu/', 'location' => 'Kingsborough Community College'],
    ['name' => 'NYU Gould Welcome Center', 'base_url' => 'https://www.nyu.edu/', 'location' => 'NYU Gould Welcome Center'],
    ['name' => 'P.S. 020 Anna Silver', 'base_url' => 'https://www.ps20m.org/', 'location' => 'P.S. 020 Anna Silver'],
    ['name' => 'Bronx Community College', 'base_url' => 'https://www.bcc.cuny.edu/', 'location' => 'Bronx Community College'],
    ['name' => 'Lehman College', 'base_url' => 'https://www.lehman.edu/', 'location' => 'Lehman College'],
    ['name' => 'Voorhees Theatre (City Tech)', 'base_url' => 'https://www.citytech.cuny.edu/', 'location' => 'Voorhees Theatre (City Tech)'],
    ['name' => 'Kimmel Center for University Life', 'base_url' => 'https://www.nyu.edu/students/student-information-and-resources/student-life/kimmel-center.html', 'location' => 'Kimmel Center for University Life'],
    ['name' => 'The Senesh School', 'base_url' => 'https://www.seneshschool.org/', 'location' => 'The Senesh School'],
    ['name' => 'King Juan Carlos I of Spain Center', 'base_url' => 'https://www.nyu.edu/community/government-affairs/king-juan-carlos-i-of-spain-center.html', 'location' => 'King Juan Carlos I of Spain Center'],
    ['name' => 'Buell Hall (Columbia)', 'base_url' => 'https://www.arch.columbia.edu/', 'location' => 'Buell Hall'],
    ['name' => 'Tisch Cinema at NYU', 'base_url' => 'https://tisch.nyu.edu/', 'location' => 'Tisch Cinema at NYU'],
    ['name' => 'Clive Davis Gallery', 'base_url' => 'https://tisch.nyu.edu/', 'location' => 'Clive Davis Gallery'],
    ['name' => 'Faculty House at Columbia', 'base_url' => 'https://www.columbia.edu/', 'location' => 'Faculty House at Columbia'],
    ['name' => 'Baruch College', 'base_url' => 'https://www.baruch.cuny.edu/', 'location' => 'Baruch College'],
    ['name' => 'PS 307 Pioneer Academy', 'base_url' => 'https://www.schools.nyc.gov/schools/Q307', 'location' => 'PS 307 Pioneer Academy'],
    ['name' => 'Scarsdale High School', 'base_url' => 'https://www.scarsdaleschools.k12.ny.us/shs', 'location' => 'Scarsdale High School'],
    ['name' => 'William A. Shine Great Neck South High School', 'base_url' => 'https://www.greatneck.k12.ny.us/southhigh', 'location' => 'William A. Shine Great Neck South High School'],
    ['name' => 'PS 123 Mahalia Jackson', 'base_url' => 'https://www.schools.nyc.gov/schools/M123', 'location' => 'PS 123 Mahalia Jackson'],

    // Batch 3g: Churches (1 event)
    ['name' => "Saint Paul's Roman Catholic Church", 'base_url' => 'https://stpaulcobblehill.org/', 'location' => "Saint Paul's Roman Catholic Church"],
    ['name' => 'Interchurch Center', 'base_url' => 'https://interchurch-center.org/', 'location' => 'Interchurch Center'],
    ['name' => 'Ridgewood Presbyterian Church', 'base_url' => 'https://www.ridgewoodpres.org/', 'location' => 'Ridgewood Presbyterian Church'],
    ['name' => 'Our Lady of the Rosary', 'base_url' => 'https://www.ourladyoftherosarynyc.org/', 'location' => 'Our Lady of the Rosary'],
    ['name' => 'Broadway Presbyterian Church', 'base_url' => 'https://www.broadwaypres.org/', 'location' => 'Broadway Presbyterian Church'],
    ['name' => 'Good Shepherd-Faith Presbyterian Church', 'base_url' => 'https://www.goodshepherdfaith.org/', 'location' => 'Good Shepherd-Faith Presbyterian Church'],
    ['name' => 'Church of St. Francis Xavier', 'base_url' => 'https://www.sfxavier.org/', 'location' => 'Church of St. Francis Xavier'],
    ['name' => 'Church of St. Luke & St. Matthew', 'base_url' => 'https://stlukeandstmatthew.org/', 'location' => 'Church of St. Luke & St. Matthew'],
    ['name' => 'Mother AME Zion Church', 'base_url' => 'https://www.motheramezion.org/', 'location' => 'Mother AME Zion Church'],
    ['name' => 'Rutgers Presbyterian Church', 'base_url' => 'https://rutgerschurch.com/', 'location' => 'Rutgers Presbyterian Church'],
    ['name' => 'The Reformed Church of Bronxville', 'base_url' => 'https://www.reformedchurch.org/', 'location' => 'The Reformed Church of Bronxville'],

    // Batch 3d: Broadway Theaters (1 event)
    ['name' => 'Ambassador Theatre', 'base_url' => 'https://shubert.nyc/theatres/ambassador/', 'location' => 'Ambassador Theatre'],
    ['name' => 'Gerald Schoenfeld Theatre', 'base_url' => 'https://shubert.nyc/theatres/gerald-schoenfeld/', 'location' => 'Gerald Schoenfeld Theatre'],
    ['name' => 'The Theater Center', 'base_url' => 'https://www.telecharge.com/Off-Broadway/Venues/The-Theater-Center', 'location' => 'The Theater Center'],
    ['name' => 'Majestic Theatre', 'base_url' => 'https://shubert.nyc/theatres/majestic/', 'location' => 'Majestic Theatre'],
    ['name' => 'Marquis Theatre', 'base_url' => 'https://www.nederlander.com/theatres/marquis-theatre', 'location' => 'Marquis Theatre'],
    ['name' => 'Stephen Sondheim Theatre', 'base_url' => 'https://www.roundabouttheatre.org/theatres/stephen-sondheim-theatre', 'location' => 'Stephen Sondheim Theatre'],
    ['name' => 'The Ruby Theatre', 'base_url' => 'https://www.second-stage.org/the-ruby-theatre', 'location' => 'The Ruby Theatre'],
    ['name' => 'Winter Garden Theatre', 'base_url' => 'https://shubert.nyc/theatres/winter-garden/', 'location' => 'Winter Garden Theatre'],
    ['name' => 'Nederlander Theatre', 'base_url' => 'https://www.nederlander.com/theatres/nederlander-theatre', 'location' => 'Nederlander Theatre'],
    ['name' => 'Lunt-Fontanne Theatre', 'base_url' => 'https://www.nederlander.com/theatres/lunt-fontanne-theatre', 'location' => 'Lunt-Fontanne Theatre'],
    ['name' => 'Richard Rodgers Theatre', 'base_url' => 'https://www.nederlander.com/theatres/richard-rodgers-theatre', 'location' => 'Richard Rodgers Theatre'],
    ['name' => 'BAM Fisher', 'base_url' => 'https://www.bam.org/fisher', 'location' => 'BAM Fisher'],
    ['name' => 'Brick Aux', 'base_url' => 'https://www.bricktheater.com/', 'location' => 'Brick Aux'],
    ['name' => 'Stella Adler Center for the Arts', 'base_url' => 'https://stellaadler.com/', 'location' => 'Stella Adler Center for the Arts'],
    ['name' => 'Goldstein Theatre at Queens College', 'base_url' => 'https://www.qc.cuny.edu/academics/art/drama-theatre-dance/', 'location' => 'Goldstein Theatre at Queens College'],

    // Batch 3e: Recreation Centers (1 event)
    ['name' => 'Chelsea Recreation Center', 'base_url' => 'https://www.nycgovparks.org/facilities/recreationcenters/M071', 'location' => 'Chelsea Recreation Center'],
    ['name' => 'Gertrude Ederle Recreation Center', 'base_url' => 'https://www.nycgovparks.org/facilities/recreationcenters/M145', 'location' => 'Gertrude Ederle Recreation Center'],
    ['name' => 'Greenbelt Recreation Center', 'base_url' => 'https://www.nycgovparks.org/facilities/recreationcenters/R012', 'location' => 'Greenbelt Recreation Center'],
    ['name' => 'Hamilton Fish Recreation Center', 'base_url' => 'https://www.nycgovparks.org/facilities/recreationcenters/M034', 'location' => 'Hamilton Fish Recreation Center'],
    ['name' => 'Highbridge Recreation Center', 'base_url' => 'https://www.nycgovparks.org/facilities/recreationcenters/M069', 'location' => 'Highbridge Recreation Center'],
    ['name' => 'McCarren Play Center', 'base_url' => 'https://www.nycgovparks.org/facilities/recreationcenters/B073', 'location' => 'McCarren Play Center'],
    ['name' => "St. John\u{2019}s Recreation Center", 'base_url' => 'https://www.nycgovparks.org/facilities/recreationcenters/B034', 'location' => "St. John\u{2019}s Recreation Center"],
    ['name' => 'Al Oerter Recreation Center', 'base_url' => 'https://www.nycgovparks.org/facilities/recreationcenters/Q099', 'location' => 'Al Oerter Recreation Center'],
    ['name' => 'Williamsbridge Oval Recreation Center', 'base_url' => 'https://www.nycgovparks.org/facilities/recreationcenters/X010', 'location' => 'Williamsbridge Oval Recreation Center'],
    ['name' => 'Asser Levy Recreation Center', 'base_url' => 'https://www.nycgovparks.org/facilities/recreationcenters/M137', 'location' => 'Asser Levy Recreation Center'],
    ['name' => 'J. Hood Wright Recreation Center', 'base_url' => 'https://www.nycgovparks.org/facilities/recreationcenters/M072', 'location' => 'J. Hood Wright Recreation Center'],
    ['name' => 'Alfred E. Smith Recreation Center', 'base_url' => 'https://www.nycgovparks.org/facilities/recreationcenters/M035', 'location' => 'Alfred E. Smith Recreation Center'],

    // Batch 3c: Parks and Gardens (1 event)
    ['name' => 'Bowne Park', 'base_url' => 'https://www.nycgovparks.org/parks/bowne-park', 'location' => 'Bowne Park'],
    ['name' => 'Brookfield Park', 'base_url' => 'https://freshkillspark.org/', 'location' => 'Brookfield Park'],
    ['name' => 'Canarsie Park', 'base_url' => 'https://www.nycgovparks.org/parks/canarsie-park', 'location' => 'Canarsie Park'],
    ['name' => 'Clove Lakes Park', 'base_url' => 'https://www.nycgovparks.org/parks/clove-lakes-park', 'location' => 'Clove Lakes Park'],
    ['name' => 'Forest Park', 'base_url' => 'https://www.nycgovparks.org/parks/forest-park', 'location' => 'Forest Park'],
    ['name' => 'Franklin D. Roosevelt Boardwalk and Beach', 'base_url' => 'https://www.nycgovparks.org/parks/franklin-d-roosevelt-boardwalk-and-beach', 'location' => 'Franklin D. Roosevelt Boardwalk And Beach'],
    ['name' => 'Gantry Plaza State Park', 'base_url' => 'https://parks.ny.gov/parks/gantry-plaza', 'location' => 'Gantry Plaza State Park'],
    ['name' => 'Highland Park', 'base_url' => 'https://www.nycgovparks.org/parks/highland-park', 'location' => 'Highland Park'],
    ['name' => 'Kissena Park', 'base_url' => 'https://www.nycgovparks.org/parks/kissena-park', 'location' => 'Kissena Park'],
    ['name' => 'Pelham Bay Park', 'base_url' => 'https://www.nycgovparks.org/parks/pelham-bay-park', 'location' => 'Pelham Bay Park'],
    ['name' => 'Stuyvesant Square', 'base_url' => 'https://www.nycgovparks.org/parks/stuyvesant-square', 'location' => 'Stuyvesant Square'],
    ['name' => 'Van Cortlandt Park', 'base_url' => 'https://www.nycgovparks.org/parks/van-cortlandt-park', 'location' => 'Van Cortlandt Park'],
    ['name' => 'Betsy Head Park', 'base_url' => 'https://www.nycgovparks.org/parks/betsy-head-park', 'location' => 'Betsy Head Park'],
    ['name' => 'Msgr. McGolrick Park', 'base_url' => 'https://www.nycgovparks.org/parks/mcgolrick-park', 'location' => 'Msgr. McGolrick Park'],
    ['name' => 'Long Pond Park', 'base_url' => 'https://www.nycgovparks.org/parks/long-pond-park', 'location' => 'Long Pond Park'],
    ['name' => 'Greenbelt Nature Center', 'base_url' => 'https://www.sigreenbelt.org/', 'location' => 'Greenbelt Nature Center'],
    ['name' => 'Plumb Beach', 'base_url' => 'https://www.nps.gov/gate/planyourvisit/plumb-beach.htm', 'location' => 'Plumb Beach'],
    ['name' => 'Rockaway Community Park', 'base_url' => 'https://www.nycgovparks.org/parks/rockaway-community-park', 'location' => 'Rockaway Community Park'],
    ['name' => 'Ewen Park', 'base_url' => 'https://www.nycgovparks.org/parks/ewen-park', 'location' => 'Ewen Park'],
    ['name' => 'Stuyvesant Cove Park', 'base_url' => 'https://www.nycgovparks.org/parks/stuyvesant-cove-park', 'location' => 'Stuyvesant Cove Park'],
    ['name' => 'Mount Loretto Unique Area', 'base_url' => 'https://www.dec.ny.gov/lands/75543.html', 'location' => 'Mount Loretto Unique Area'],
    ['name' => 'Grafton Lakes State Park', 'base_url' => 'https://parks.ny.gov/parks/grafton-lakes', 'location' => 'Grafton Lakes State Park'],
    ['name' => 'Grover Cleveland Playground', 'base_url' => 'https://www.nycgovparks.org/parks/grover-cleveland-playground', 'location' => 'Grover Cleveland Playground'],
    ['name' => 'Lou Lodati Playground', 'base_url' => 'https://www.nycgovparks.org/parks/torsney-lou-lodati-playground', 'location' => 'Lou Lodati Playground'],
    ['name' => 'Torsney Playground', 'base_url' => 'https://www.nycgovparks.org/parks/torsney-lou-lodati-playground', 'location' => 'Torsney Playground'],
    ['name' => 'Family Community Garden', 'base_url' => 'https://www.nycgovparks.org/parks/family-community-garden', 'location' => 'Family Community Garden'],
    ['name' => "Maggie's Magic Garden", 'base_url' => 'https://www.nycgovparks.org/parks/maggies-magic-garden', 'location' => 'Maggies Magic Garden'],
    ['name' => "Sparrow's Nest Community Garden", 'base_url' => 'https://www.nycgovparks.org/parks/sparrows-nest-community-garden', 'location' => "Sparrow's Nest Community Garden"],
    ['name' => 'El Garden', 'base_url' => 'https://www.nycgovparks.org/parks/el-garden', 'location' => 'El Garden'],
    ['name' => 'Earth Matter', 'base_url' => 'https://earthmatter.org/', 'location' => 'Earth Matter'],
    ['name' => 'Sky Farm LIC', 'base_url' => 'https://www.skyfarmnyc.com/', 'location' => 'Sky Farm LIC'],

    // Batch 3b: Libraries (1 event)
    ['name' => 'Art and Artifacts Division (Schomburg)', 'base_url' => 'https://www.nypl.org/locations/schomburg', 'location' => 'Art and Artifacts Division'],
    ['name' => 'Astoria Library', 'base_url' => 'https://www.queenslibrary.org/about-us/locations/astoria', 'location' => 'Astoria Library'],
    ['name' => 'Cypress Hills Library', 'base_url' => 'https://www.bklynlibrary.org/locations/cypress-hills', 'location' => 'Cypress Hills Library'],
    ['name' => 'Elmhurst Library', 'base_url' => 'https://www.queenslibrary.org/about-us/locations/elmhurst', 'location' => 'Elmhurst Library'],
    ['name' => 'Flatlands Library', 'base_url' => 'https://www.bklynlibrary.org/locations/flatlands', 'location' => 'Flatlands Library'],
    ['name' => 'Henry W. and Albert A. Berg Collection', 'base_url' => 'https://www.nypl.org/locations/schwarzman', 'location' => 'Henry W. and Albert A. Berg Collection'],
    ['name' => 'Kew Gardens Hills Library', 'base_url' => 'https://www.queenslibrary.org/about-us/locations/kew-gardens-hills', 'location' => 'Kew Gardens Hills Library'],
    ['name' => 'Mill Basin Library', 'base_url' => 'https://www.bklynlibrary.org/locations/mill-basin', 'location' => 'Mill Basin Library'],
    ['name' => 'Morningside Heights Library', 'base_url' => 'https://www.nypl.org/locations/morningside-heights', 'location' => 'Morningside Heights Library'],
    ['name' => 'North Forest Park Library', 'base_url' => 'https://www.queenslibrary.org/about-us/locations/north-forest-park', 'location' => 'North Forest Park Library'],
    ['name' => 'Ozone Park Library', 'base_url' => 'https://www.queenslibrary.org/about-us/locations/ozone-park', 'location' => 'Ozone Park Library'],
    ['name' => 'Ravenswood Library', 'base_url' => 'https://www.queenslibrary.org/about-us/locations/ravenswood', 'location' => 'Ravenswood Library'],
    ['name' => 'Seaside Library', 'base_url' => 'https://www.queenslibrary.org/about-us/locations/seaside', 'location' => 'Seaside Library'],
    ['name' => 'Spring Creek Library', 'base_url' => 'https://www.bklynlibrary.org/locations/spring-creek', 'location' => 'Spring Creek Library'],
    ['name' => 'Steinway Library', 'base_url' => 'https://www.queenslibrary.org/about-us/locations/steinway', 'location' => 'Steinway Library'],
    ['name' => 'Todt Hill-Westerleigh Library', 'base_url' => 'https://www.nypl.org/locations/todt-hill-westerleigh', 'location' => 'Todt Hill-Westerleigh Library'],
    ['name' => 'Tottenville Library', 'base_url' => 'https://www.nypl.org/locations/tottenville', 'location' => 'Tottenville Library'],
    ['name' => 'Rogers Memorial Library', 'base_url' => 'https://www.myrfrpl.org/', 'location' => 'Rogers Memorial Library'],

    // Batch 1: locations with 3+ active events missing websites (already added)
    ['name' => 'Letchworth State Park', 'base_url' => 'https://parks.ny.gov/parks/letchworth', 'location' => 'Letchworth State Park'],
    ['name' => 'Detective Keith L. Williams Field House', 'base_url' => 'https://www.nycgovparks.org/facilities/recreationcenters/q121', 'location' => 'Detective Keith L. Williams Field House'],
    ['name' => 'Jones Beach State Park', 'base_url' => 'https://parks.ny.gov/parks/jones-beach', 'location' => 'Jones Beach State Park'],
    ['name' => 'Thacher State Park', 'base_url' => 'https://parks.ny.gov/parks/thacher', 'location' => 'Thacher State Park'],
    ['name' => 'Minnewaska State Park Preserve', 'base_url' => 'https://parks.ny.gov/parks/minnewaska', 'location' => 'Minnewaska State Park Preserve'],
    ['name' => 'Environmental Education Center', 'base_url' => 'https://www.brooklynbridgepark.org/places-to-see/environmental-education-center/', 'location' => 'Environmental Education Center'],
    ['name' => 'Sunset Park', 'base_url' => 'https://www.nycgovparks.org/parks/sunset-park', 'location' => 'Sunset Park'],
    ['name' => 'NYU Stern School of Business', 'base_url' => 'https://www.stern.nyu.edu/', 'location' => 'NYU Stern School of Business'],
    ['name' => 'Moreau Lake State Park', 'base_url' => 'https://parks.ny.gov/parks/moreau-lake', 'location' => 'Moreau Lake State Park'],
    ['name' => 'Inwood Hill Park', 'base_url' => 'https://www.nycgovparks.org/parks/inwood-hill-park', 'location' => 'Inwood Hill Park'],
    ['name' => 'Jackson Heights Greenmarket', 'base_url' => 'https://www.grownyc.org/greenmarket/queens/jackson-heights', 'location' => 'Jackson Heights Greenmarket'],
    ['name' => 'La Plaza Cultural', 'base_url' => 'https://www.laplazacultural.com/', 'location' => 'La Plaza Cultural'],
    ['name' => 'Schomburg Center for Research in Black Culture', 'base_url' => 'https://www.nypl.org/locations/schomburg', 'location' => 'Schomburg Center for Research in Black Culture'],
    ['name' => 'Sunnyside Greenmarket', 'base_url' => 'https://www.grownyc.org/greenmarket/queens/sunnyside', 'location' => 'Sunnyside Greenmarket'],
    ['name' => 'Washington Square Park', 'base_url' => 'https://www.nycgovparks.org/parks/washington-square-park', 'location' => 'Washington Square Park'],
    ['name' => 'World Trade Center', 'base_url' => 'https://www.wtc.com/', 'location' => 'World Trade Center'],
    ['name' => 'Atlantic Terminal Mall', 'base_url' => 'https://www.shopatlanticterminal.com/', 'location' => 'Atlantic Terminal Mall'],
    ['name' => 'Denny Farrell Riverbank State Park', 'base_url' => 'https://parks.ny.gov/parks/riverbank', 'location' => 'Denny Farrell Riverbank State Park'],
    ['name' => 'Medgar Evers College', 'base_url' => 'https://www.mec.cuny.edu/', 'location' => 'Medgar Evers College'],
    ['name' => 'Rockefeller State Park Preserve', 'base_url' => 'https://parks.ny.gov/parks/rockefeller', 'location' => 'Rockefeller State Park Preserve'],
    ['name' => 'Connetquot River State Park Preserve', 'base_url' => 'https://parks.ny.gov/parks/connetquot-river', 'location' => 'Connetquot River State Park Preserve'],
    ['name' => 'NYU School of Global Public Health', 'base_url' => 'https://publichealth.nyu.edu/', 'location' => '708 Broadway (NYU)'],
    ['name' => 'Success Garden', 'base_url' => 'https://www.grownyc.org/openspace/gardens/bk/eny-success-garden', 'location' => 'Success Garden'],
    ['name' => 'Maspeth Town Hall', 'base_url' => 'https://www.maspethtownhall.org/', 'location' => 'Maspeth Town Hall'],
    ['name' => 'Van Cortlandt Golf House', 'base_url' => 'https://www.vancortlandtlakehouse.com/', 'location' => 'Van Cortlandt Golf House'],
    ['name' => 'Swinging Sixties Older Adult Center', 'base_url' => 'https://stnicksalliance.org/elder-care/older-adult-centers-oac/', 'location' => 'Swinging Sixties Older Adult Center'],
    ['name' => '133rd Swing Street Community Garden', 'base_url' => 'https://www.nycgovparks.org/parks/133rd-swing-street-community-garden', 'location' => '133rd Swing Street Community Garden'],
    ['name' => 'The Creative Center', 'base_url' => 'https://www.thecreativecenter.org/', 'location' => 'The Creative Center'],
    ['name' => 'Corpus Christi Church', 'base_url' => 'https://ccnd-nyc.org/', 'location' => 'Corpus Christi Church'],
    // Batch 2: locations with 2 active events missing websites
    ['name' => 'A.R.R.O.W. Field House', 'base_url' => 'https://www.nycgovparks.org/parks/arrow-field-house', 'location' => 'A.R.R.O.W. Field House'],
    ['name' => 'Actors Temple Theatre', 'base_url' => 'https://actorstempletheatre.com/', 'location' => 'Actors Temple Theatre'],
    ['name' => 'Advent Lutheran Church', 'base_url' => 'https://www.adventnyc.org/', 'location' => 'Advent Lutheran Church'],
    ['name' => 'Anthroposophy NYC', 'base_url' => 'https://www.anthroposophynyc.org/', 'location' => 'Anthroposophical Society NY Branch'],
    ['name' => 'Bowling Green', 'base_url' => 'https://www.nycgovparks.org/parks/bowling-green', 'location' => 'Bowling Green'],
    ['name' => 'BPL Park Slope', 'base_url' => 'https://www.bklynlibrary.org/locations/park-slope', 'location' => 'BPL Park Slope'],
    ['name' => 'Brooklyn Made Store', 'base_url' => 'https://brooklynmadestore.com/', 'location' => 'Brooklyn Made Store'],
    ['name' => 'Canarsie Pier', 'base_url' => 'https://www.nps.gov/gate/learn/historyculture/canarsie-pier.htm', 'location' => 'Canarsie Pier'],
    ['name' => 'City College of New York', 'base_url' => 'https://www.ccny.cuny.edu/', 'location' => 'City College of New York'],
    ['name' => 'City Tech', 'base_url' => 'https://www.citytech.cuny.edu/', 'location' => 'City Tech'],
    ['name' => 'Clay Pit Ponds State Park', 'base_url' => 'https://parks.ny.gov/parks/166/details.aspx', 'location' => 'Clay Pit Ponds State Park'],
    ['name' => 'Columbia University Greenmarket', 'base_url' => 'https://www.grownyc.org/greenmarket/manhattan/columbia-th', 'location' => 'Columbia University Greenmarket'],
    ['name' => 'Crown Hill Theatre', 'base_url' => 'https://crownhilltheatre.com/', 'location' => 'Crown Hill Theatre'],
    ['name' => 'CUNY School of Law', 'base_url' => 'https://www.law.cuny.edu/', 'location' => 'CUNY School of Law'],
    ['name' => 'Dongan Hills Library', 'base_url' => 'https://www.nypl.org/locations/dongan-hills', 'location' => 'Dongan Hills Library'],
    ['name' => 'EVEN Hotel Midtown East', 'base_url' => 'https://www.ihg.com/evenhotels/hotels/us/en/new-york/nycev/hoteldetail', 'location' => 'EVEN Hotel Midtown East'],
    ['name' => 'Flushing Meadows Corona Park', 'base_url' => 'https://www.nycgovparks.org/parks/flushing-meadows-corona-park', 'location' => 'Flushing Meadows Corona Park'],
    ['name' => 'Forest Hills Greenmarket', 'base_url' => 'https://www.grownyc.org/greenmarket/queens/forest-hills', 'location' => 'Forest Hills Greenmarket'],
    ['name' => "Fred's", 'base_url' => 'https://fredsnyc.com/', 'location' => "Fred's"],
    ['name' => 'Golfzon Social', 'base_url' => 'https://golfzonsocial.com/', 'location' => 'Golfzon Social'],
    ['name' => 'Gramercy Ale House', 'base_url' => 'https://www.gramercyalehouse.com/', 'location' => 'Gramercy Ale House'],
    ['name' => 'Great Kills Library', 'base_url' => 'https://www.nypl.org/locations/great-kills', 'location' => 'Great Kills Library'],
    ['name' => 'Great Kills Park', 'base_url' => 'https://www.nps.gov/gate/learn/historyculture/great-kills-park.htm', 'location' => 'Great Kills Park'],
    ['name' => 'Hempstead Lake State Park', 'base_url' => 'https://parks.ny.gov/parks/hempsteadlake/details.aspx', 'location' => 'Hempstead Lake State Park'],
    ['name' => 'Inwood Library', 'base_url' => 'https://www.nypl.org/locations/inwood', 'location' => 'Inwood Library'],
    ['name' => 'Jerome L. Greene Science Center', 'base_url' => 'https://zuckermaninstitute.columbia.edu/jerome-l-greene-science-center', 'location' => 'Jerome L. Greene Science Center'],
    ['name' => 'Kaye Playhouse at Hunter College', 'base_url' => 'https://www.hunter.cuny.edu/the-kaye-playhouse/', 'location' => 'Kaye Playhouse at Hunter College'],
    ['name' => 'Kew & Willow Books', 'base_url' => 'https://kewandwillow.com/', 'location' => 'Kew & Willow Books'],
    ['name' => 'Longacre Theatre', 'base_url' => 'https://shubert.nyc/theatres/longacre/', 'location' => 'Longacre Theatre'],
    ['name' => 'Lower East Side Farmstand', 'base_url' => 'https://www.grownyc.org/farmstand/les', 'location' => 'Lower East Side Farmstand'],
    ['name' => 'Mad Dog & Beans', 'base_url' => 'https://www.maddogandbeans.com/', 'location' => 'Mad Dog & Beans'],
    ['name' => 'Marsha P. Johnson State Park', 'base_url' => 'https://parks.ny.gov/parks/marsha-p-johnson-state-park', 'location' => 'Marsha P. Johnson State Park'],
    ['name' => 'McGoldrick Library', 'base_url' => 'https://www.queenslibrary.org/about-us/locations/mcgoldrick', 'location' => 'McGoldrick Library'],
    ['name' => 'Motel No Tell', 'base_url' => 'https://www.motelnotellnyc.com/', 'location' => 'Motel No Tell'],
    ['name' => 'Muhlenberg Library', 'base_url' => 'https://www.nypl.org/locations/muhlenberg', 'location' => 'Muhlenberg Library'],
    ['name' => 'Murray Hill Farmers Market', 'base_url' => 'https://www.grownyc.org/greenmarket/ourmarkets', 'location' => 'Murray Hill Farmers Market'],
    ['name' => "Oliver\u{2019}s", 'base_url' => 'https://www.oliversastoria.com/', 'location' => "Oliver\u{2019}s"],
    ['name' => 'Penn Station', 'base_url' => 'https://moynihantrainhall.nyc/', 'location' => 'Penn Station'],
    ['name' => 'Philipse Manor Hall State Historic Site', 'base_url' => 'https://parks.ny.gov/parks/philipse-manor-hall-state-historic-site', 'location' => 'Philipse Manor Hall State Historic Site'],
    ['name' => 'Prospect Park', 'base_url' => 'https://www.nycgovparks.org/parks/prospect-park', 'location' => 'Prospect Park (Grand Army Plaza Entrance)'],
    ['name' => 'Ridgewood Farmstand', 'base_url' => 'https://www.grownyc.org/farmstand/ridgewood', 'location' => 'Ridgewood Farmstand'],
    ['name' => 'Ridgewood Reservoir', 'base_url' => 'https://www.nycgovparks.org/parks/highland-park', 'location' => 'Ridgewood Reservoir'],
    ['name' => 'Sara D. Roosevelt Park', 'base_url' => 'https://www.nycgovparks.org/parks/sara-d-roosevelt-park', 'location' => 'Sara D. Roosevelt Park'],
    ['name' => 'Shirley Chisholm State Park', 'base_url' => 'https://parks.ny.gov/parks/shirley-chisholm-state-park', 'location' => 'Shirley Chisholm State Park'],
    ['name' => 'Spicy Moon', 'base_url' => 'https://www.spicymoonnyc.com/', 'location' => 'Spicy Moon'],
    ['name' => 'St. James Recreation Center', 'base_url' => 'https://www.nycgovparks.org/parks/st-james-park', 'location' => 'St. James Recreation Center'],
    ['name' => 'Teachers College, Columbia University', 'base_url' => 'https://www.tc.columbia.edu/', 'location' => 'Teachers College, Columbia University'],
    ['name' => 'The Factory', 'base_url' => 'https://the-factory.shop/', 'location' => 'The Factory'],
    ['name' => 'The Garden by the Bay', 'base_url' => 'https://www.nycgovparks.org/opportunities/volunteer/group/the-garden-by-the-bay', 'location' => 'The Garden by the Bay'],
    ['name' => 'The Long Hall', 'base_url' => 'https://www.thelonghallnyc.com/', 'location' => 'The Long Hall'],
    ['name' => 'Thomas Jefferson Recreation Center', 'base_url' => 'https://www.nycgovparks.org/parks/thomas-jefferson-park', 'location' => 'Thomas Jefferson Recreation Center'],
    ['name' => 'Thomas Yoseloff Business Center', 'base_url' => 'https://www.nypl.org/locations/snfl', 'location' => 'Thomas Yoseloff Business Center'],
];

$new_websites = [
    // Final 9 venues added on 2026-03-09 (batch 4) — see git history
];

$done_partiful_venues = [
    [
        'name' => 'Hifi Provisions',
        'description' => 'Record store and vinyl listening lounge in Industry City hosting album listening parties, release events, and live performances.',
        'base_url' => 'https://hifiprovisions.com/',
        'urls' => ['https://hifiprovisions.com/pages/event-calendar'],
        'location' => 'Hifi Provisions',
    ],
    [
        'name' => 'Sparsa',
        'description' => 'Greenpoint wellness studio offering yoga, pilates, and massage, with community events including sound baths, workshops, and healing circles.',
        'base_url' => 'https://www.sparsabrooklyn.com/',
        'urls' => ['https://www.sparsabrooklyn.com/events'],
        'location' => 'Sparsa',
    ],
    // --- Informational only (no crawlable events page) ---
    [
        'name' => '110 Studios',
        'description' => 'Bushwick creative complex with event stages, recording studio, bar, and backyard hosting live showcases, open mics, and community arts events.',
        'base_url' => 'https://110studios.org/',
        'location' => '110 Studios',
    ],
    [
        'name' => 'Anaïs',
        'description' => 'Natural wine bar and all-day cafe in Boerum Hill hosting book events, collage nights, and community gatherings.',
        'base_url' => 'https://www.anaisbk.com/',
        'location' => 'Anaïs',
    ],
    [
        'name' => 'Bakline',
        'description' => 'Running apparel brand and community running club hosting group runs, book clubs, and marathon-related events from their Gowanus HQ.',
        'base_url' => 'https://www.bakline.nyc/',
        'location' => 'Bakline HQ',
    ],
    [
        'name' => 'Bedford Studio',
        'description' => 'West Village boutique coffee shop and co-working space hosting pop-ups, workshops, and networking events.',
        'base_url' => 'https://www.ourstudiocollective.com/',
        'location' => 'Bedford Studio',
    ],
    [
        'name' => 'Blazers Sports Bar',
        'description' => 'Women-owned Williamsburg sports bar focused on women\'s sports, hosting trivia nights, drag bingo, and watch parties.',
        'base_url' => 'https://www.blazerssportsbar.com/',
        'location' => 'Blazers Sports Bar',
    ],
    [
        'name' => 'Casanara',
        'description' => 'Clinton Hill cocktail bar hosting DJ nights, live music, and themed parties.',
        'base_url' => 'https://www.casanaranyc.com/',
        'location' => 'Casanara',
    ],
    [
        'name' => 'Color Me Mine UWS',
        'description' => 'Paint-your-own pottery studio on the Upper West Side hosting creative workshops, birthday parties, and special events.',
        'base_url' => 'https://upperwestside.colormemine.com/',
        'location' => 'Color Me Mine',
    ],
    [
        'name' => 'Fresh Salt',
        'description' => 'Bar and cafe in a historic Seaport smokehouse hosting bingo nights and social events.',
        'base_url' => 'https://www.freshsalt.com/',
        'location' => 'Fresh Salt',
    ],
    [
        'name' => "Honey's Brooklyn",
        'description' => 'East Williamsburg cocktail bar, dance floor, and event space doubling as a tasting room for Enlightenment Wines.',
        'base_url' => 'https://honeys.nyc/',
        'location' => "Honey's Brooklyn",
    ],
    [
        'name' => 'Ki Smith Gallery',
        'description' => 'Lower East Side contemporary art gallery with a performance stage hosting exhibitions, live music, and art events.',
        'base_url' => 'https://www.kismithgallery.com/',
        'location' => 'Ki Smith Gallery',
    ],
    [
        'name' => 'Knockout Cafe',
        'description' => 'East Village coffee shop with a downstairs gallery hosting rotating art exhibitions and creative events.',
        'base_url' => 'https://knockoutny.com/',
        'location' => 'Knockout Cafe',
    ],
    [
        'name' => 'Lips Cafe',
        'description' => 'Black-owned Flatbush cafe, art space, and Caribbean restaurant hosting poetry, comedy, open mics, and art showcases.',
        'base_url' => 'https://www.lipscafebk.com/',
        'location' => 'Lips Cafe',
    ],
    [
        'name' => 'Market Bar And Brewery',
        'description' => 'Black-owned Crown Heights bar and brewery with Haitian-inspired cocktails, hosting happy hours, Konpa nights, and karaoke.',
        'base_url' => 'https://www.marketbarbk.com/',
        'location' => 'Market Bar And Brewery',
    ],
    [
        'name' => "Miss Barb's",
        'description' => 'Crown Heights cafe by day and wine bar by night hosting Wine Down nights with DJs, game nights, and community events.',
        'base_url' => 'https://www.missbarbs.com/',
        'location' => "Miss Barb's",
    ],
    [
        'name' => 'Moshava Art',
        'description' => 'Greenwich Village coffee shop and art gallery hosting exhibitions, maker space sessions, and community creative events.',
        'base_url' => 'https://www.moshavaart.com/',
        'location' => 'Moshava Art',
    ],
    [
        'name' => "Paul's Casablanca",
        'description' => 'Moroccan-themed SoHo nightclub and lounge hosting DJ nights and late-night events.',
        'base_url' => 'https://paulscasablanca.com/',
        'location' => "Paul's Casablanca",
    ],
    [
        'name' => 'Revision Lounge & Gallery',
        'description' => 'East Village cocktail lounge and art gallery made from recycled materials, hosting music, comedy, and art exhibits.',
        'base_url' => 'http://revisionlounge.com/',
        'location' => 'Revision Lounge & Gallery',
    ],
    [
        'name' => 'Rough Draft',
        'description' => 'Hamilton Heights craft beer and whiskey bar hosting trivia, live music, and arts events.',
        'base_url' => 'https://www.instagram.com/roughdraftharlem/',
        'location' => 'Rough Draft',
    ],
    [
        'name' => "Somebody's Darling",
        'description' => 'Upper East Side bar with 90s-inspired decor hosting weekly trivia, live music, and creative workshops.',
        'base_url' => 'https://www.instagram.com/somebodys_darling_nyc/',
        'location' => "Somebody's Darling",
    ],
    [
        'name' => 'Studio 1514',
        'description' => "Bed-Stuy's queer-owned creative space and store hosting live music, mocktail mixers, and themed events.",
        'base_url' => 'https://www.welcometo1514.com/',
        'location' => 'Studio 1514',
    ],
    [
        'name' => 'Time Again Bar',
        'description' => 'Chinatown cocktail and natural wine bar with a courtyard, hosting BBQs, concerts, and social events.',
        'base_url' => 'https://www.instagram.com/timeagainbar/',
        'location' => 'Time Again Bar',
    ],
    [
        'name' => 'Unveiled',
        'description' => 'Subterranean Williamsburg nightclub beneath The William Vale hotel hosting electronic music events.',
        'base_url' => 'https://unveilednewyork.com/',
        'location' => 'Unveiled',
    ],
    [
        'name' => 'Village Loft',
        'description' => 'Greenwich Village loft event space hosting pop-up shops, tastings, and community gatherings.',
        'base_url' => 'https://www.chabadloft.com/',
        'location' => 'Village Loft',
    ],
];

/*
// Websites added on 2026-02-12 (Park Slope Walk venues) - see git history
// Judd Foundation added on 2026-02-12 - see git history
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
