import threading
import time
import requests
import re
import hashlib
import os
import json
import bleach
from datetime import datetime
from flask import Flask, render_template, jsonify, request
from bs4 import BeautifulSoup, NavigableString, Tag
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# --- FIREBASE SETUP ---
import firebase_admin
from firebase_admin import credentials, messaging

cred_json = os.environ.get('FIREBASE_CREDENTIALS')
if cred_json:
    try:
        cred_dict = json.loads(cred_json)
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
    except Exception as e:
        print(f"⚠️ Firebase Error: {e}")
else:
    print("⚠️ WARNING: FIREBASE_CREDENTIALS missing!")

# --- CONFIG ---
AFFICHAGE_URL = 'https://elearning.univ-bejaia.dz/course/view.php?id=19989'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# Get Admin Password from Railway Variables (Fallback to default if missing)
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', '34362053')

latest_data = []
first_run = True
app = Flask(__name__)

# --- SECURITY ---
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["500 per day", "100 per hour"],
    storage_uri="memory://"
)

@app.after_request
def add_security_headers(response):
    # 1. Prevent clickjacking
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    
    # 2. Prevent MIME type sniffing
    response.headers['X-Content-Type-Options'] = 'nosniff'
    
    # 3. Content Security Policy (CSP)
    # Allows: Self, Tailwind, Google Fonts, and Google Analytics
    csp_policy = (
        "default-src 'self' https:; "
        "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://www.googletagmanager.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.tailwindcss.com; "
        "font-src 'self' https://fonts.gstatic.com;"
    )
    response.headers['Content-Security-Policy'] = csp_policy
    
    return response

# --- HELPERS ---

# Date Parsing for Sorting
FRENCH_MONTHS = {
    'janvier': 1, 'février': 2, 'mars': 3, 'avril': 4, 'mai': 5, 'juin': 6,
    'juillet': 7, 'août': 8, 'septembre': 9, 'octobre': 10, 'novembre': 11, 'décembre': 12,
    'jan': 1, 'fév': 2, 'mar': 3, 'avr': 4, 'mai': 5, 'jui': 6,
    'juil': 7, 'aoû': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'déc': 12
}

def parse_date_to_timestamp(date_str):
    """
    Converts string like "27 Janvier 2026 à 14h34" to a timestamp number.
    Returns 0 if no date found (so it drops to bottom of list).
    """
    try:
        # Regex to find: Day, Month, Year, Hour, Minute (handles "à" or ":")
        match = re.search(r'(\d{1,2})\s+([a-zA-Zéû]+)\s+(\d{4}).*?(\d{1,2})[h:](\d{1,2})', date_str, re.IGNORECASE)
        
        if match:
            day, month_str, year, hour, minute = match.groups()
            month = FRENCH_MONTHS.get(month_str.lower(), 1) # Default to Jan if unknown
            
            dt = datetime(int(year), int(month), int(day), int(hour), int(minute))
            return dt.timestamp()
            
    except Exception:
        pass
    
    return 0 # Default for "Général" or items with no specific date

def clean_html_text(tag):
    text_parts = []
    for child in tag.children:
        if isinstance(child, NavigableString): 
            text_parts.append(child.string)
        elif isinstance(child, Tag):
            child_text = clean_html_text(child)
            if child.name in ['b', 'strong']: text_parts.append(f"<b>{child_text}</b>")
            elif child.name in ['i', 'em']: text_parts.append(f"<i>{child_text}</i>")
            elif child.name == 'a': text_parts.append(child_text)
            elif child.name in ['p', 'div', 'li']: text_parts.append(f"\n{child_text}\n")
            elif child.name == 'br': text_parts.append("\n")
            else: text_parts.append(child_text)
    
    # Clean up structure
    full_text = "".join(text_parts)
    full_text = re.sub(r'\n\s*\n', '\n\n', full_text)
    
    # Sanitize tags (Only allow basic formatting)
    return bleach.clean(full_text.strip(), tags=['b', 'strong', 'i', 'em'], strip=True)

def extract_links(tag):
    links = []
    for a in tag.find_all("a", href=True):
        href = a.get('href')
        if href and "http" not in href:
             href = f"https://elearning.univ-bejaia.dz{href}" if href.startswith('/') else f"https://elearning.univ-bejaia.dz/{href}"
        if href and href.startswith('http'):
            links.append(href)
    return links

def send_fcm_notification(title, body_preview):
    try:
        android_config = messaging.AndroidConfig(
            priority='high',
            ttl=86400,
            notification=messaging.AndroidNotification(click_action='FLUTTER_NOTIFICATION_CLICK')
        )
        safe_title = bleach.clean(title, tags=[], strip=True)
        message = messaging.Message(
            notification=messaging.Notification(title="Nouvelle Annonce ST", body=safe_title),
            android=android_config,
            topic='announcements',
        )
        messaging.send(message)
        print(f"🚀 FCM Notification Sent")
    except Exception as e:
        print(f"❌ FCM Error: {e}")

# --- SCRAPER LOGIC ---
def scrape_task():
    try:
        print("Checking for updates...")
        session = requests.Session()
        session.headers.update(HEADERS)
        response = session.get(AFFICHAGE_URL, timeout=30)
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # FIX: Broad selector to catch all labels, not just 'activity-altcontent'
        cards = soup.select('li.activity.modtype_label > div')
        
        new_data = []
        for tag in cards:
            # Skip if it's just a section wrapper (mod-indent-outer) unless it has content
            # If it's the wrapper, we look inside for the content div
            if 'mod-indent-outer' in tag.get('class', []):
                 # Try to find the inner content div
                 content_div = tag.select_one('.contentwithoutlink') or tag.select_one('.no-overflow') or tag
            else:
                 content_div = tag
            
            raw_text = content_div.get_text(" ", strip=True)
            
            # Filter out very short/empty elements (noise)
            if len(raw_text) < 3:
                continue

            unique_id = hashlib.sha256(raw_text.encode('utf-8')).hexdigest()[:16]
            body_html = clean_html_text(content_div)
            
            # Title Extraction
            title = "Information"
            # Try to grab the first bold text as the title
            title_match = re.search(r'<b>(.*?)</b>', body_html)
            if title_match:
                title = title_match.group(1).strip().replace(":", "")
                # Optional: Remove title from body to avoid duplication
                # body_html = body_html.replace(title_match.group(0), "", 1)

            # Date Extraction & Sorting Logic
            date_text = "Général"
            timestamp = 0 # Default (Oldest possible)
            
            # Clean "Affiché le" from the body so it doesn't look repetitive
            clean_body_html = re.sub(r'Affiché le\s*[:]?\s*[0-9/\-\w\s:àh]+', '', body_html, flags=re.IGNORECASE)

            date_match_str = re.search(r'Affiché le\s*[:]?\s*([0-9/\-\w\s:àh]+)', raw_text, re.IGNORECASE)
            if date_match_str: 
                date_text = date_match_str.group(1).strip()
                timestamp = parse_date_to_timestamp(date_text)

            # Source ID
            parent_li = tag.find_parent('li', class_='activity')
            source_link = AFFICHAGE_URL
            if parent_li and parent_li.get('id'):
                safe_id = re.sub(r'[^a-zA-Z0-9-]', '', parent_li.get('id'))
                source_link = f"{AFFICHAGE_URL}#{safe_id}"

            item = {
                "id": unique_id,
                "title": bleach.clean(title, tags=[], strip=True),
                "body": clean_body_html,
                "links": extract_links(content_div),
                "date": bleach.clean(date_text, tags=[], strip=True),
                "timestamp": timestamp, # Used for sorting
                "source": source_link
            }
            new_data.append(item)
        
        # Sort by Timestamp Descending (Newest First)
        new_data.sort(key=lambda x: x['timestamp'], reverse=True)
        
        return new_data

    except Exception as e:
        print(f"❌ Scraper Error: {e}")
        return None

# --- BACKGROUND LOOP ---
def background_loop():
    global latest_data, first_run
    print("--- Background Loop Started ---")
    while True:
        scraped_items = scrape_task()
        
        if scraped_items:
            if not first_run and latest_data:
                old_ids = {item['id'] for item in latest_data}
                # Check top 5 items for new ones
                for i in range(min(5, len(scraped_items))):
                    item = scraped_items[i]
                    if item['id'] not in old_ids:
                        print(f"🔔 NEW: {item['title']}")
                        send_fcm_notification(item['title'], "New announcement")
                        break 
            
            latest_data = scraped_items
            first_run = False
            print(f"✅ Loaded {len(latest_data)} items.")
        
        time.sleep(600) # 10 Minutes

# --- ROUTES ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/announcements')
def api_data():
    response = jsonify(latest_data)
    # Cache Control: Tell the browser/phone to keep this data for 60 seconds
    response.headers['Cache-Control'] = 'public, max-age=60'
    return response

@app.route('/install')
def install_page():
    return render_template('download.html')

@app.route('/robots.txt')
def robots():
    # Helper to prevent Google from indexing admin pages
    return "User-agent: *\nDisallow: /api/\nDisallow: /test-notification-railway"

@app.route('/test-notification-railway', methods=['GET', 'POST'])
@limiter.limit("5 per minute") 
def manual_test():
    # 1. If User submits the password (POST request)
    if request.method == 'POST':
        password = request.form.get('password')
        
        # Use the Environment Variable for comparison
        if password == ADMIN_PASSWORD:
            try:
                send_fcm_notification("Security Test", "Secure System Operational.")
                return """
                <div style="font-family: sans-serif; text-align: center; margin-top: 50px; color: green;">
                    <h1>✅ Success</h1>
                    <p>Secure Notification Sent!</p>
                    <a href="/test-notification-railway">Back</a>
                </div>
                """
            except Exception as e:
                return f"<h1>Error</h1><p>{str(e)}</p>"
        else:
            return """
            <div style="font-family: sans-serif; text-align: center; margin-top: 50px; color: red;">
                <h1>❌ Access Denied</h1>
                <p>Incorrect Password.</p>
                <a href="/test-notification-railway">Try Again</a>
            </div>
            """

    # 2. If User opens the page (GET request), show the form
    return """
    <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body { background: #0B1121; color: white; font-family: sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
                form { background: #1E293B; padding: 30px; border-radius: 12px; border: 1px solid #334155; text-align: center; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
                input { padding: 10px; border-radius: 6px; border: none; width: 200px; margin-bottom: 10px; text-align: center; }
                button { background: #3b82f6; color: white; border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer; font-weight: bold; width: 100%; }
                button:hover { background: #2563eb; }
                h2 { margin-top: 0; }
            </style>
        </head>
        <body>
            <form method="POST">
                <h2>Admin Access</h2>
                <input type="password" name="password" placeholder="Enter Password" required autofocus>
                <br>
                <button type="submit">SEND NOTIFICATION</button>
            </form>
        </body>
    </html>
    """

# --- ENTRY POINT ---
threading.Thread(target=background_loop, daemon=True).start()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)