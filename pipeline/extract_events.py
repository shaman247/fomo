"""
Event Extraction Script

This script uses Google's Gemini AI to extract structured event data from
crawled website content. It processes markdown files and generates tables
containing event information (name, date, time, location, description, etc.).

Features:
- Intelligent content chunking to handle large pages
- Parallel processing with rate limiting
- Automatic deduplication of table headers across chunks
- Preserves dated directory structure from crawled data

Configuration:
- Requires GEMINI_API_KEY in .env file
- Input: event_data/crawled/YYYYMMDD/*.md
- Output: event_data/extracted/YYYYMMDD/*.md
"""

import asyncio
import os
import re
import random
from datetime import datetime
from dotenv import load_dotenv
import google.generativeai as genai

# Get the directory where this script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Load Gemini API key from environment
load_dotenv()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable not set. Please add it to your .env file.")

def get_prompt(url, page_content, current_date_string, name, notes):
    """
    Generate the AI prompt for event extraction.

    Creates a detailed prompt instructing Gemini to extract event information
    and format it as a markdown table with specific columns.

    Args:
        url: Source URL of the content
        page_content: Markdown content to process
        current_date_string: Current date for context
        name: Name of the website/source
        notes: Optional additional instructions

    Returns:
        str: Formatted prompt for Gemini API
    """
    note_section = f"Note: {notes}" if notes else ""
    return f'''Today's date is {current_date_string}. We are assembling a database of upcoming events in New York City. To accomplish this, we are inspecting websites for details about upcoming events. Currently, we are looking at {name} ({url}). Based on the text content retrieved from the website {url}, please identify and list any upcoming events. If possible, include dates, times, locations, and descriptions (1-2 sentences) for each event. Format your output as a Markdown table with the following header:
  
  | name | location | sublocation | start_date | start_time | end_date | end_time | description | url | hashtags | emoji |

  Some pointers about these fields:

- "name" is the name of the event
- "location" is the name of the venue where the event is being held
- "sublocation" is optional and can be used to specify locations within the venue (e.g., rooftop, 5th floor, etc.)
- "start_date" is the date of the event in YYYY-MM-DD format.
- "start_time" is the time of the event (e.g., 4:00 PM)
- "end_date" and "end_time" are optional
- "description" should be 1-3 sentences.
- "url" should be a url for the specific event, if available. Otherwise, use {url}.
- "hashtags" are a set of 4-7 CamelCase tags to describe the event. Include a mix of high-level tags (e.g., #Comedy, #Music, #Outdoor) and more granular tags (e.g., #LatinJazz, #Ceramics, #Vegan). Avoid tags that are specific to a location or neighborhood.
- "emoji" is a single emoji that describes the event.

Only include events that take place in the NYC area within the next 3 months.

Output rows for any events that are present in the content below, which has been retrieved from the website. If no events were successfully retrieved, output an empty header. Only include events that take place in the NYC area. If an event has multiple dates or times, output a separate row for each instance.

{note_section}

Here is the content:

 {page_content}'''

def get_file_content(file_path):
    """
    Read content from a file.

    Args:
        file_path: Path to the file to read

    Returns:
        str: File content, or None if file not found
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        print(f"Error: File not found at {file_path}")
        return None


def chunk_content(page_content, chunk_size=90000, overlap=0):
    """
    Split long content into smaller chunks for API processing.

    Uses intelligent splitting to avoid breaking in the middle of events.
    Prioritizes splitting after headings (##, ###) or blank lines.

    Args:
        page_content: Full text content to split
        chunk_size: Maximum characters per chunk (default: 90000)
        overlap: Number of characters to overlap between chunks (default: 0)

    Returns:
        list: List of content chunks
    """
    chunks = []
    start = 0

    while start < len(page_content):
        end = start + chunk_size

        if end < len(page_content):
            # Try to split at a natural boundary to avoid cutting events
            split_pos = -1
            heading_search_pattern = r'\n###?'

            # Find the last heading in the chunk
            last_match = None
            for match in re.finditer(heading_search_pattern, page_content[start:end]):
                last_match = match
            if last_match:
                split_pos = start + last_match.start()

            # If no heading found, fall back to blank lines
            if split_pos != -1 and split_pos > start:
                end = split_pos
            else:
                # Search in last 10% of chunk for a blank line
                blank_line_pos = page_content.rfind('\n\n', start, end - (chunk_size // 10))
                if blank_line_pos != -1 and blank_line_pos > start:
                    end = blank_line_pos

        chunks.append(page_content[start:end])

        # Move to next chunk with optional overlap
        next_start = end - overlap
        if next_start <= start:  # Ensure forward progress
            next_start = end
        start = next_start

    return chunks

async def process_and_save_events(page_content, url, name, notes, source_filename):
    """
    Extract events from content using Gemini AI and save as markdown table.

    Processes content in chunks if needed, combines responses, and saves
    to the extracted/ directory with dated organization.

    Args:
        page_content: Markdown content to process
        url: Source URL
        name: Website/source name
        notes: Optional additional notes for the AI
        source_filename: Original filename for tracking
    """
    current_date_string = datetime.now().strftime('%Y-%m-%d')

    # Split content into manageable chunks
    chunks = chunk_content(page_content)
    all_responses = ""

    print(f"Parsing content from {name} ({url}) in {len(chunks)} chunk(s).")

    # Configure Gemini AI
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-2.5-flash-lite')

    # Process each chunk
    if chunks:
        for i, chunk in enumerate(chunks):
            print(f"  - Processing chunk {i+1}/{len(chunks)}... ({len(chunk)} characters)")
            prompt = get_prompt(url, chunk, current_date_string, name, notes)

            # Add random delay to respect API rate limits
            await asyncio.sleep(random.uniform(0, 5))

            try:
                response = await model.generate_content_async(prompt)
                response_text = response.text.strip()

                if i > 0:
                    # Skip header for subsequent chunks - only append table rows
                    table_body_start = re.search(r'\|---', response_text)
                    if table_body_start:
                        lines = response_text[table_body_start.end():].strip().split('\n')
                        # Filter out repeated headers or separators
                        table_rows = [line for line in lines if line.strip() and not line.strip().startswith('|---')]
                        all_responses += "\n" + "\n".join(table_rows)
                    else:
                        all_responses += "\n" + response_text
                else:
                    # First chunk includes the header
                    all_responses = response_text
            except Exception as e:
                print(f"An error occurred while calling the Gemini API for chunk {i+1}: {e}")

    # Handle empty responses
    if not all_responses or not all_responses.strip():
        print(f"Warning: Gemini returned an empty response for {source_filename}. Writing empty table.")
        all_responses = '''| name | location | sublocation | start_date | start_time | end_date | end_time | description | url | hashtags | emoji |
|---|---|---|---|---|---|---|---|---|---|---|'''

    try:
        # Extract date from source filename (e.g., '20250912_sitename.md')
        date_match = re.match(r'(\d{8})_', source_filename)
        if date_match:
            date_str = date_match.group(1)
        else:
            # Fallback to current date if filename doesn't have date prefix
            date_str = datetime.now().strftime('%Y%m%d')

        # Create dated output directory structure: extracted/YYYYMMDD/
        output_dir = os.path.join(SCRIPT_DIR, "..", "event_data", "extracted")
        dated_output_dir = os.path.join(output_dir, date_str)
        os.makedirs(dated_output_dir, exist_ok=True)

        # Remove date prefix from filename for cleaner organization
        basename = os.path.basename(source_filename)
        filename_without_date = re.sub(r'^\d{8}_', '', basename)
        output_filename = os.path.join(dated_output_dir, filename_without_date)

        # Write extracted events table to file
        with open(output_filename, 'w', encoding='utf-8') as f:
            f.write(all_responses)
        print(f"Saved Gemini response for {source_filename} to '{output_filename}'.")
    except Exception as e:
        print(f"Error saving file for {source_filename}: {e}")

async def main():
    """
    Main function to process all crawled files and extract events.

    Scans the crawled/ directory for markdown files, processes them in parallel
    with rate limiting (max 5 concurrent), and extracts event data using Gemini AI.
    Skips files that have already been processed.
    """
    crawled_dir = os.path.join(SCRIPT_DIR, '..', 'event_data', 'crawled')
    if not os.path.isdir(crawled_dir):
        print(f"Error: Directory '{crawled_dir}' not found.")
        return

    # Limit concurrent API calls to avoid rate limiting
    semaphore = asyncio.Semaphore(5)
    tasks = []

    async def process_file(date_str, filename):
        """Process a single crawled file with rate limiting."""
        async with semaphore:
            # Check if output already exists
            output_dir = os.path.join(SCRIPT_DIR, "..", "event_data", "extracted")
            filename_without_date = re.sub(r'^\d{8}_', '', filename)
            output_filename = os.path.join(output_dir, date_str, filename_without_date)

            if os.path.exists(output_filename):
                # Skip already processed files
                #print(f"Skipping {filename} - already extracted.")
                return

            # Read crawled content
            file_path = os.path.join(crawled_dir, date_str, filename)
            page_content = get_file_content(file_path)

            if not page_content:
                return

            # Extract URL from first line if present
            url = ""
            content_to_process = page_content

            if page_content.startswith('http'):
                first_newline = page_content.find('\n')
                if first_newline != -1:
                    url = page_content[:first_newline].strip()
                    content_to_process = page_content[first_newline+1:]

            # Generate friendly name from filename
            match = re.match(r'(.+)\.md', filename_without_date)
            if match:
                name = match.group(1).replace('_', ' ').title()
                source_filename_with_date = f"{date_str}_{filename_without_date}"
                await process_and_save_events(content_to_process, url, name, "", source_filename_with_date)
            else:
                print(f"Skipping file with unexpected name format: {filename}")

    # Iterate through dated subdirectories and create processing tasks
    for date_subdir in os.listdir(crawled_dir):
        date_path = os.path.join(crawled_dir, date_subdir)
        if os.path.isdir(date_path) and re.match(r'\d{8}', date_subdir):
            for filename in os.listdir(date_path):
                if filename.endswith(".md"):
                    task = asyncio.create_task(process_file(date_subdir, filename))
                    tasks.append(task)

    # Process all files in parallel (with semaphore limiting concurrency)
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
