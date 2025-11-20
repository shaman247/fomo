import asyncio
import os
import re
import random
from datetime import datetime
from dotenv import load_dotenv
import google.generativeai as genai

# Get the directory where this script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

load_dotenv()  # Load environment variables from .env file
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable not set.")

def get_prompt(url, page_content, current_date_string, name, notes):
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
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        print("Error: content.txt not found.")
        return

def chunk_content(page_content, chunk_size=90000, overlap=0):
    """Splits content into chunks, trying to not cut in the middle of an event."""
    chunks = []
    start = 0
    while start < len(page_content):
        end = start + chunk_size
        if end < len(page_content):
            # Find a good split point. Prioritize splitting after a heading (## or ###).
            split_pos = -1
            heading_search_pattern = r'\n###?'
            
            # Find the last heading in the chunk to split on
            last_match = None
            for match in re.finditer(heading_search_pattern, page_content[start:end]):
                last_match = match
            if last_match:
                split_pos = start + last_match.start()

            # If no heading found, fall back to splitting on a blank line
            if split_pos != -1 and split_pos > start:
                end = split_pos
            else:
                blank_line_pos = page_content.rfind('\n\n', start, end - (chunk_size // 10)) # Search in last 10%
                if blank_line_pos != -1 and blank_line_pos > start:
                    end = blank_line_pos
        
        chunks.append(page_content[start:end])
        
        # Move to the next chunk, with some overlap to maintain context
        next_start = end - overlap
        if next_start <= start: # Ensure we always move forward
            next_start = end
        start = next_start

    return chunks

async def process_and_save_events(page_content, url, name, notes, source_filename):
    """
    Processes content to extract events using Gemini, then saves the result.
    """
    current_date_string = datetime.now().strftime('%Y-%m-%d')

    chunks = chunk_content(page_content)
    all_responses = ""

    print(f"Parsing content from {name} ({url}) in {len(chunks)} chunk(s).")

    # Call Gemini with the prompt and print the output
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-2.5-flash-lite')

    if chunks:
        for i, chunk in enumerate(chunks):
            print(f"  - Processing chunk {i+1}/{len(chunks)}... ({len(chunk)} characters)")
            prompt = get_prompt(url, chunk, current_date_string, name, notes)
            await asyncio.sleep(random.uniform(0, 5))
            try:
                response = await model.generate_content_async(prompt)
                # We will just append the table rows, skipping headers on subsequent chunks
                response_text = response.text.strip()
                if i > 0:
                    # Find where the table body starts
                    table_body_start = re.search(r'\|---', response_text)
                    if table_body_start:
                        lines = response_text[table_body_start.end():].strip().split('\n')
                        # Filter out any potential repeated headers or separators
                        table_rows = [line for line in lines if line.strip() and not line.strip().startswith('|---')]
                        all_responses += "\n" + "\n".join(table_rows)
                    else:
                         all_responses += "\n" + response_text # Append whatever we got
                else:
                    all_responses = response_text
            except Exception as e:
                print(f"An error occurred while calling the Gemini API for chunk {i+1}: {e}")

    # Save the combined response
    if not all_responses or not all_responses.strip():
        print(f"Warning: Gemini returned an empty response for {source_filename}. Writing an empty header.")
        all_responses = '''| name | location | sublocation | start_date | start_time | end_date | end_time | description | url | hashtags | emoji |
|---|---|---|---|---|---|---|---|---|---|---|'''

    try:
        # Extract date from source_filename (e.g., '20250912_sitename.md')
        date_match = re.match(r'(\d{8})_', source_filename)
        if date_match:
            date_str = date_match.group(1)
        else:
            # Fallback to current date if filename doesn't have date prefix
            date_str = datetime.now().strftime('%Y%m%d')

        # Create the 'extracted/YYYYMMDD' directory structure
        output_dir = os.path.join(SCRIPT_DIR, "..", "event_data", "extracted")
        dated_output_dir = os.path.join(output_dir, date_str)
        os.makedirs(dated_output_dir, exist_ok=True)

        # Remove date prefix from filename: '20250912_sitename.md' -> 'sitename.md'
        basename = os.path.basename(source_filename)
        filename_without_date = re.sub(r'^\d{8}_', '', basename)
        output_filename = os.path.join(dated_output_dir, filename_without_date)

        with open(output_filename, 'w', encoding='utf-8') as f:
            f.write(all_responses)
        print(f"Saved Gemini response for {source_filename} to '{output_filename}'.")
    except Exception as e:
        print(f"Error saving file for {source_filename}: {e}")

async def main():
    crawled_dir = os.path.join(SCRIPT_DIR, '..', 'event_data', 'crawled')
    if not os.path.isdir(crawled_dir):
        print(f"Error: Directory '{crawled_dir}' not found.")
        return

    semaphore = asyncio.Semaphore(5)
    tasks = []

    async def process_file(date_str, filename):
        async with semaphore:
            # Check if the output file already exists in the 'extracted/YYYYMMDD' directory
            output_dir = os.path.join(SCRIPT_DIR, "..", "event_data", "extracted")
            filename_without_date = re.sub(r'^\d{8}_', '', filename)
            output_filename = os.path.join(output_dir, date_str, filename_without_date)
            if os.path.exists(output_filename):
                #print(f"Skipping {filename} as output file '{output_filename}' already exists.")
                return

            file_path = os.path.join(crawled_dir, date_str, filename)
            page_content = get_file_content(file_path)

            if not page_content:
                return

            url = ""
            content_to_process = page_content

            if page_content.startswith('http'):
                first_newline = page_content.find('\n')
                if first_newline != -1:
                    url = page_content[:first_newline].strip()
                    content_to_process = page_content[first_newline+1:]

            # Extract name from filename like 'nyc_events.md' (date prefix already removed)
            match = re.match(r'(.+)\.md', filename_without_date)
            if match:
                name = match.group(1).replace('_', ' ').title()
                # Pass original filename with date for tracking purposes
                source_filename_with_date = f"{date_str}_{filename_without_date}"
                await process_and_save_events(content_to_process, url, name, "", source_filename_with_date)
            else:
                print(f"Skipping file with unexpected name format: {filename}")

    # Iterate through dated subdirectories
    for date_subdir in os.listdir(crawled_dir):
        date_path = os.path.join(crawled_dir, date_subdir)
        if os.path.isdir(date_path) and re.match(r'\d{8}', date_subdir):
            for filename in os.listdir(date_path):
                if filename.endswith(".md"):
                    task = asyncio.create_task(process_file(date_subdir, filename))
                    tasks.append(task)

    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())
