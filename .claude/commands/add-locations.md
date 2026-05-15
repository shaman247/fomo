# Add Locations Command

Add new locations to the fomo.nyc database.

## Instructions

You are helping the user add new locations to the database. Follow these steps:

### Step 1: Gather Location Information

Ask the user for the locations they want to add. For each location, you need:
- **name** (required): Full venue name
- **address** (required): Full street address including city, state, zip
- **emoji** (required): A single emoji representing the venue type
- **tags** (required): Array of tags for categorization and search
- **description** (required): 1-2 sentence description of the venue and what it offers
- **short_name** (optional): Shorter display name
- **alt_emoji** (optional): Alternative emoji

If the user provides location names without coordinates, use the geocode script to get accurate coordinates. Just provide the venue name - the script automatically biases results toward NYC:

```bash
php scripts/geocode.php --json "Culture House"
```

Output:
```json
{"name":"Culture House","address":"958 6th Ave, New York, NY 10001, USA","lat":40.75031,"lng":-73.9872}
```

No need to add "New York" or the full address - Google will find the correct NYC venue.

You should also determine:
- An appropriate emoji based on venue type
- Appropriate tags (borough, neighborhood, venue type, etc.)
- A clear, concise description (1-2 sentences) about what the venue is and what types of events it hosts

### Description Guidelines

Write descriptions that are:
- **Concise**: 1-2 sentences maximum
- **Informative**: Explain what the venue is and what it offers
- **Specific**: Mention key event types, programming, or unique features
- **Audience-focused**: Help users understand what to expect

Examples:
- "Brooklyn-based community hub for experimental games, indie developers, and creative culture, hosting game showcases, film screenings, music performances, workshops, and LARPs."
- "World-renowned performing arts conservatory hosting over 700 annual public performances in music, dance, and drama at venues including Morse Hall, with most events free or under $50."
- "Historic Renaissance Revival building serving as a premier cultural center for Czech and Slovak communities, hosting festivals, concerts, art exhibitions, lectures, films, and dance events."

### Step 2: Edit the Script

Once you have all the location details, edit the `$new_locations` array in `scripts/add_locations.php`:

```php
$new_locations = [
    [
        'name' => 'Venue Name',
        'short_name' => 'Short Name',  // optional
        'description' => 'Brief description of venue and what it offers...',  // recommended
        'address' => '123 Main St, New York, NY 10001',
        'lat' => 40.7128,
        'lng' => -74.0060,
        'emoji' => '🎭',
        'alt_emoji' => '🎪',  // optional
        'tags' => ['Manhattan', 'Midtown', 'Theatre'],  // recommended tags
    ],
    // ... more locations
];
```

### Step 3: Dry Run

First, run a dry run to preview what will be added:

```bash
php scripts/add_locations.php --dry-run
```

Show the user the output and confirm they want to proceed.

### Step 4: Add to Local Database

```bash
php scripts/add_locations.php
```

### Step 5: Add to Production

Ask the user if they want to also add to production. If yes:

```bash
php scripts/add_locations.php --production
```

**Note**: Unlike websites, locations use auto-increment IDs in both databases. The IDs may differ between local and production.

### Step 6: Clean Up (REQUIRED)

After successfully adding locations, reset the `$new_locations` array back to empty. Do NOT leave previous entries, dated comments, or "see git history" trail markers behind — git is the source of truth for what was added when.

```php
$new_locations = [
];
```

## Emoji Guide

Use these emojis based on venue type:
- 🎭 Theatre/Performance venue
- 🎤 Cabaret/Comedy club
- 🎷 Jazz club
- 🎸 Rock venue
- 🪩 Nightclub/Dance club
- 🍹 Bar/Lounge
- 🍺 Beer bar/Brewery
- 🍻 Sports bar/Pub
- ☕ Coffee shop
- 🍱 Restaurant (Asian)
- 🌮 Restaurant (Mexican)
- 🥩 Steakhouse
- 🏛️ Museum
- 🎨 Art gallery
- 📷 Photography gallery
- 🎓 University/College
- 🏫 School
- 📚 Library
- ⛪ Church
- 🕍 Synagogue
- ☸️ Buddhist temple/center
- 🛕 Hindu/Jain temple
- 🙏 Sikh gurdwara/Interfaith center
- 🕊️ Quaker meetinghouse
- 🏢 Office building
- 🏨 Hotel
- 🏥 Hospital/Health center
- 🫱🏾‍🫲🏼 Community Center
- 🌳 Park
- 🌱 Garden
- 🏃 Running/Track venue
- 🏋️ Gym/Fitness
- 🎾 Tennis
- 🏊 Pool/Rec center
- 🚂 Train station
- 📍 Neighborhood
- 🎬 Film/Studio
- 💻 Tech/Coworking space

## Tag Guidelines

Always include relevant tags from these categories:
- **Borough**: Manhattan, Brooklyn, Queens, Bronx, Staten Island
- **Neighborhood**: e.g., Greenwich Village, Williamsburg, Astoria, SoHo, Downtown Brooklyn
- **Venue Type**: e.g., Jazz, Live Music, Theatre, Art, Museum, Tech, Education
- **Features**: e.g., Outdoor, Rooftop, Free, Community Space

Tags will be created if they don't exist, but prefer using existing tags when possible.

## Linking Websites to Locations

After adding a location, you may want to link an existing website to it. Use the `website_locations` table:

```bash
# Local db
mysql -u root fomo -e "INSERT INTO website_locations (website_id, location_id) VALUES (<website_id>, <location_id>)"
```

Alternatively, when adding a website via `/add-websites`, use the `location` field to auto-link.

## Adding Instagram Accounts

If a venue has an Instagram account, add it to the database for social media tracking:

### Step 1: Add the Instagram Account

```bash
mysql -u root fomo -e "INSERT INTO instagram_accounts (handle, name) VALUES ('venuehandle', 'Venue Name');"
```

The handle should be without the `@` symbol (e.g., `bluenote` not `@bluenote`).

### Step 2: Link to the Location

```bash
# Get the instagram account ID
mysql -u root fomo -e "SELECT id FROM instagram_accounts WHERE handle = 'venuehandle';"

# Link to location
mysql -u root fomo -e "INSERT INTO location_instagram (location_id, instagram_id) VALUES (<location_id>, <instagram_id>);"
```

### Batch Insert Example

For multiple accounts at once:

```sql
-- Add accounts
INSERT IGNORE INTO instagram_accounts (handle, name) VALUES
('bluenote', 'Blue Note'),
('villagevanguard', 'Village Vanguard');

-- Link to locations (get IDs first)
INSERT INTO location_instagram (location_id, instagram_id) VALUES
(123, (SELECT id FROM instagram_accounts WHERE handle = 'bluenote')),
(124, (SELECT id FROM instagram_accounts WHERE handle = 'villagevanguard'));
```

## Example Usage

User: "Add the Blue Note jazz club and Village Vanguard"

You would:
1. Look up addresses and coordinates
2. Edit the script with entries like:
```php
$new_locations = [
    [
        'name' => 'Blue Note',
        'description' => 'Legendary jazz club in Greenwich Village featuring world-class musicians and intimate performances.',
        'address' => '131 W 3rd St, New York, NY 10012',
        'lat' => 40.7308,
        'lng' => -74.0005,
        'emoji' => '🎷',
        'tags' => ['Manhattan', 'Greenwich Village', 'Jazz', 'Live Music'],
    ],
    [
        'name' => 'Village Vanguard',
        'description' => 'Iconic underground jazz club hosting nightly performances by renowned jazz artists since 1935.',
        'address' => '178 7th Ave S, New York, NY 10014',
        'lat' => 40.7360,
        'lng' => -74.0018,
        'emoji' => '🎷',
        'tags' => ['Manhattan', 'Greenwich Village', 'Jazz', 'Live Music'],
    ],
];
```
3. Run dry-run, then add to local db
