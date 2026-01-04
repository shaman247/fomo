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

- `main.py` Main entry point - orchestrates the complete workflow
- `crawler.py` Crawls websites using Crawl4AI, stores content in database
- `extractor.py` Uses Gemini AI to extract structured event data
  - Requires `GEMINI_API_KEY` environment variable (set in `.env` file)
- `processor.py` Parses extracted data, enriches with location coordinates
- `merger.py` Deduplicates events into final events table
- `exporter.py` Generates JSON files for the website
- `uploader.py` Uploads data files to FTP server
- `db.py` Database operations (CRUD for crawl runs, results, events)
</details>

<details>
<summary><strong><code>/database/</code></strong> Database schema and setup scripts</summary>

- `schema.sql` Complete database schema
- `setup.py` Creates empty database tables
- `migrate_schema.py` Applies schema changes to existing database
- `/database/backups/` Database backup files
</details>

### Data Pipeline Flow

All data flows through the database (`crawl_runs` → `crawl_results` → `crawl_events` → `events`):

1. **Crawl** → Query `websites` table for due sites, crawl and store in `crawl_results.crawled_content`
2. **Extract** → Use Gemini AI to extract structured tables, store in `crawl_results.extracted_content`
3. **Process** → Parse tables, enrich with location data from `locations`, store in `crawl_events`
4. **Merge** → Deduplicate `crawl_events` into final `events` table
5. **Export** → Generate `public_html/data/*.json` from `events` table
6. **Upload** → Push JSON files to FTP server

## How You Can Help

- **📢 Share with your friends**

- **📍 Add events and places you know**

- **🫱🏾‍🫲🏼 Stay in touch**
  - This website is in active development, so keep visiting for regular updates!
  - You can reach out by email or join the [Discord server](https://discord.gg/Xn6wHegjVv)

## Database

The project uses a MariaDB/MySQL database to store locations, websites, and crawl data.

### Initial Setup

New developers should restore from a database backup rather than starting with an empty database:

```bash
# 1. Create the database
mysql -u root -e "CREATE DATABASE fomo CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"

# 2. Restore from backup
mysql -u root fomo < database/backups/fomo_backup_YYYYMMDD.sql
```

### Creating Backups

```bash
# Windows (XAMPP)
"C:/xampp/mysql/bin/mysqldump.exe" -u root fomo > database/backups/fomo_backup_YYYYMMDD.sql

# Linux/Mac
mysqldump -u root fomo > database/backups/fomo_backup_YYYYMMDD.sql
```

### Schema Updates

If the schema has changed since your backup, run migrations:

```bash
python database/migrate_schema.py
```

## Acknowledgements

- 🧭 Map library: [MapLibre GL JS](https://maplibre.org/)
- 🗺️ Map tiles: © [Protomaps](https://protomaps.com), © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors
- 📅 Date picker: [Flatpickr](https://flatpickr.js.org/)
- 🔠 Fonts: [Inter](https://rsms.me/inter/), [Noto Color Emoji](https://fonts.google.com/noto/specimen/Noto+Color+Emoji)
- 🚀 This project uses [Crawl4AI](https://github.com/unclecode/crawl4ai) for web data extraction
- 🤖 [Gemini](https://gemini.google.com) and [Claude](https://claude.ai) for data processing and vibe coding
- 💖 *All the amazing, creative, hard-working people who make the city shine with their light!* 🗽
