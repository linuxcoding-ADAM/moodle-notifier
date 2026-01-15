import threading
import time
import requests
import re
import hashlib
import os
from flask import Flask, render_template, jsonify
from bs4 import BeautifulSoup, NavigableString, Tag

# --- CONFIGURATION ---
AFFICHAGE_URL = 'https://elearning.univ-bejaia.dz/course/view.php?id=19989'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# Store data in RAM (No database needed for this)
latest_data = []

app = Flask(__name__)

# --- HELPER FUNCTIONS ---
def clean_html_text(tag):
    """Converts Moodle HTML to clean HTML for the app"""
    text_parts = []
    for child in tag.children:
        if isinstance(child, NavigableString): 
            text_parts.append(child.string)
        elif isinstance(child, Tag):
            child_text = clean_html_text(child)
            if child.name in ['b', 'strong']: text_parts.append(f"<b>{child_text}</b>")
            elif child.name in ['i', 'em']: text_parts.append(f"<i>{child_text}</i>")
            elif child.name == 'a': text_parts.append(child_text)
            elif child.name in ['p', 'div', 'li', 'br']: text_parts.append(f"<br>{child_text}<br>")
            else: text_parts.append(child_text)
    
    full_text = "".join(text_parts)
    return re.sub(r'<br>\s*<br>', '<br>', full_text).strip()

def extract_links(tag):
    links = []
    for a in tag.find_all("a", href=True):
        href = a.get('href')
        if href and "http" not in href:
             href = f"https://elearning.univ-bejaia.dz{href}" if href.startswith('/') else f"https://elearning.univ-bejaia.dz/{href}"
        if href: links.append(href)
    return links

# --- SCRAPER THREAD ---
def background_scraper():
    global latest_data
    print("--- Scraper Thread Started ---")
    while True:
        try:
            print("Checking for updates...")
            session = requests.Session()
            session.headers.update(HEADERS)
            response = session.get(AFFICHAGE_URL, timeout=30)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Selector for public page
            cards = soup.select('li.activity.modtype_label .activity-altcontent')
            
            new_data = []
            for tag in cards:
                # Generate ID
                raw_text = tag.get_text()
                unique_id = hashlib.sha256(raw_text.encode()).hexdigest()[:16]
                
                # Format Body
                body_html = clean_html_text(tag)
                
                # Extract Title
                title = "Information"
                title_match = re.search(r'<b>(.*?)</b>', body_html)
                if title_match:
                    title = title_match.group(1).strip().replace(":", "")
                    body_html = body_html.replace(title_match.group(0), "", 1) # Remove title from body

                # Extract Date
                date = "Recently"
                date_match = re.search(r'Affiché le\s*([0-9/\-\w]+\s*à\s*[\d:Hh]+)', raw_text)
                if date_match: date = date_match.group(1).strip()

                new_data.append({
                    "id": unique_id,
                    "title": title,
                    "body": body_html,
                    "links": extract_links(tag),
                    "date": date
                })
            
            if new_data:
                latest_data = new_data
                print(f"✅ Updated {len(new_data)} items.")
            else:
                print("⚠️ No items found (Check selectors).")

        except Exception as e:
            print(f"❌ Scraper Error: {e}")
        
        time.sleep(600) # Sleep 10 minutes

# --- FLASK ROUTES ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/announcements')
def api_data():
    return jsonify(latest_data)

# Start scraper in background
threading.Thread(target=background_scraper, daemon=True).start()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
