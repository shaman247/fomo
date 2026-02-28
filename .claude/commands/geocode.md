# Geocode Command

Geocode venue names to get their address and coordinates using Google Maps API. Results are automatically biased toward the NYC metro area.

## Instructions

Use this skill to look up coordinates for venues when adding locations. Just provide the venue name - no need to include "New York" or a full address.

### Basic Usage

```bash
php scripts/geocode.php "Culture House"
```

Output:
```
Name: Culture House
Address: 958 6th Ave, New York, NY 10001, USA
Lat: 40.75031
Lng: -73.98720
```

### JSON Output

For programmatic use (easier to parse):

```bash
php scripts/geocode.php --json "The Bell House"
```

Output:
```json
{"name":"The Bell House","address":"149 7th St, Brooklyn, NY 11215, USA","lat":40.67358,"lng":-73.98963}
```

### Examples

```bash
# Just the venue name - Google finds the right one in NYC
php scripts/geocode.php "Village Vanguard"
php scripts/geocode.php "Blue Note"
php scripts/geocode.php "The Tailor Public House"

# Works with partial names too
php scripts/geocode.php "Brooklyn Steel"
php scripts/geocode.php "Mercury Lounge"
```

### Batch Mode

Geocode multiple venues from a file:

```bash
php scripts/geocode.php --batch venues.txt
```

Where `venues.txt` contains one venue name per line.

### How It Works

The script automatically:
1. Biases results toward the NYC metro area (using Google's `bounds` parameter)
2. Prefers US results (using `region` parameter)
3. Returns the Google Maps canonical address and precise coordinates

This means you can just enter "Culture House" and get the correct NYC venue (958 6th Ave) rather than a different Culture House elsewhere.

### When to Use This

**Adding locations** - Get accurate coords for new venues:
```bash
php scripts/geocode.php --json "New Venue Name"
# Copy lat/lng into add_locations.php
```

**Verifying locations** - Check if a venue's stored coords are accurate:
```bash
php scripts/geocode.php "Existing Venue"
# Compare with database values
```

### Error Handling

The script will return error messages for:
- Missing API key (set `GOOGLE_MAPS_API_KEY` in `.env`)
- Venue not found
- API quota exceeded
- Network errors

### Environment Setup

The script requires `GOOGLE_MAPS_API_KEY` to be set. Add to `.env`:

```
GOOGLE_MAPS_API_KEY=your_api_key_here
```

### Tips

- **Just use the venue name** - Let Google figure out the address
- **Check the output** - Verify the returned address matches the venue you expect
- **Ambiguous names** - If results are wrong, try adding a neighborhood (e.g., "Blue Note Greenwich Village")
