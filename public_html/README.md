# Fomo NYC

[fomo.nyc](https://fomo.nyc) is a free, community-built interactive map of upcoming events in the NYC area.

## About

It works by visiting the websites of parks, museums, music venues, etc., identifying any upcoming events, and displaying them on a map. My hope is that this becomes a useful resource for people to find events they are interested in and to engage with their local communities.

## Project Structure

### Main Directories

<details>
<summary><strong><code>/public_html/</code></strong> Website files served to users</summary>

- `/public_html/data/` Event and location data files
- Frontend HTML, CSS, and JavaScript files
</details>

<details>
<summary><strong><code>/pipeline/</code></strong> Python scripts for data processing pipeline</summary>

- `crawl_sites.py` Crawls event websites and saves content to markdown
- `extract_events.py` Uses Gemini AI to extract structured event data from crawled content
  - Requires `GEMINI_API_KEY` environment variable (set in `.env` file)
- `process_responses.py` Processes extracted events, enriches with location data, creates short names
- `export_events.py` Deduplicates events and exports to public_html/data/ for the website
- `upload_data.py` Uploads exported data files to server
- `process_locations.py` Processes location data from raw format
- `/pipeline/data/` Configuration and reference data
  - `websites.json` List of websites to crawl with crawl settings
  - `locations.json` Processed location data with coordinates and tags
  - `tags.json` Tag rewriting rules and filters
</details>

<details>
<summary><strong><code>/event_data/</code></strong> Intermediate data generated during processing (not included in repository)</summary>

- `/event_data/crawled/` Raw markdown content from websites (organized by date YYYYMMDD/)
- `/event_data/extracted/` Structured event tables extracted by Gemini (organized by date)
- `/event_data/processed/` Processed event JSON files with enriched data (organized by date)
- `/event_data/archived/` Old versions of files moved during re-crawling
</details>

### Data Pipeline Flow

1. **Crawl** (`crawl_sites.py`) → Websites → `event_data/crawled/YYYYMMDD/*.md`
2. **Extract** (`extract_events.py`) → Crawled markdown → `event_data/extracted/YYYYMMDD/*.md` (structured tables)
3. **Process** (`process_responses.py`) → Extracted tables → `event_data/processed/YYYYMMDD/*.json` (enriched events)
4. **Export** (`export_events.py`) → Processed events → `public_html/data/*.json` (website data)
5. **Upload** (`upload_data.py`) → Upload event and location data to FTP server

## How You Can Help

- **📢 Share with your friends**

- **📍 Add events and places you know**

- **🫱🏾‍🫲🏼 Stay in touch**
  - This website is in active development, so keep visiting for regular updates!
  - You can reach out by email or join the [Discord server](https://discord.gg/Xn6wHegjVv)

## Acknowledgements

- 🌱 Map library: [Leaflet](https://leafletjs.com/)
- 🗺️ Maps © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors, © [CARTO](https://carto.com/attributions)
- 📅 Date picker: [Flatpickr](https://flatpickr.js.org/)
- 🔠 Fonts: [Inter](https://rsms.me/inter/), [Noto Color Emoji](https://fonts.google.com/noto/specimen/Noto+Color+Emoji)
- 🚀 This project uses [Crawl4AI](https://github.com/unclecode/crawl4ai) for web data extraction
- 🤖 [Gemini](https://gemini.google.com) and [Claude](https://claude.ai) for data processing and vibe coding
- 💖 *All the amazing, creative, hard-working people who make the city shine with their light!* 🗽
