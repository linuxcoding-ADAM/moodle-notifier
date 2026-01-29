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
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    csp_policy = (
        "default-src 'self' https:; "
        "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://www.googletagmanager.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.tailwindcss.com; "
        "font-src 'self' https://fonts.gstatic.com;"
    )
    response.headers['Content-Security-Policy'] = csp_policy
    return response

# --- HELPERS ---
FRENCH_MONTHS = {
    'janvier': 1, 'février': 2, 'mars': 3, 'avril': 4, 'mai': 5, 'juin': 6,
    'juillet': 7, 'août': 8, 'septembre': 9, 'octobre': 10, 'novembre': 11, 'décembre': 12,
    'jan': 1, 'fév': 2, 'mar': 3, 'avr': 4, 'mai': 5, 'jui': 6,
    'juil': 7, 'aoû': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'déc': 12
}

def parse_date_to_timestamp(date_str):
    try:
        match = re.search(r'(\d{1,2})\s+([a-zA-Zéû]+)\s+(\d{4}).*?(\d{1,2})[h:](\d{1,2})', date_str, re.IGNORECASE)
        if match:
            day, month_str, year, hour, minute = match.groups()
            month = FRENCH_MONTHS.get(month_str.lower(), 1)
            dt = datetime(int(year), int(month), int(day), int(hour), int(minute))
            return dt.timestamp()
    except Exception:
        pass
    return 0

def clean_html_text(tag):
    if not tag: return ""
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
    full_text = "".join(text_parts)
    full_text = re.sub(r'\n\s*\n', '\n\n', full_text)
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

# --- SCRAPER LOGIC (AGGRESSIVE MODE) ---
def scrape_task():
    try:
        print("Checking for updates...")
        session = requests.Session()
        session.headers.update(HEADERS)
        response = session.get(AFFICHAGE_URL, timeout=30)
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Select ALL activities, ignoring the 'News Forum' which is usually system junk
        cards = soup.select('li.activity:not(.modtype_forum)')
        
        new_data = []
        for tag in cards:
            # 1. Base Extraction
            raw_text = tag.get_text(" ", strip=True)
            if not raw_text: continue # Skip completely empty tags

            unique_id = hashlib.sha256(raw_text.encode('utf-8')).hexdigest()[:16]
            
            # 2. Identify the "Body" content
            # Try finding the text box first
            content_div = tag.select_one('.activity-altcontent, .contentwithoutlink, .no-overflow')
            
            body_html = ""
            is_file = False
            
            if content_div:
                body_html = clean_html_text(content_div)
            else:
                # If no text box, check if it's a File/Resource
                instancename = tag.select_one('.instancename')
                if instancename:
                    # It's likely a file link
                    body_html = f"Document: {instancename.get_text(strip=True)}"
                    is_file = True

            # 3. Title Extraction
            title = "Information"
            title_match = re.search(r'<b>(.*?)</b>', body_html)
            
            if title_match:
                title = title_match.group(1).strip().replace(":", "")
                body_html = body_html.replace(title_match.group(0), "", 1) # Remove title from body
            elif is_file:
                 # If it's a file, the title is usually the first line or the link name
                 title = "Fichier / Ressource"
                 if tag.select_one('.instancename'):
                     title = tag.select_one('.instancename').get_text(strip=True).replace(" Fichier", "")

            # 4. Date Extraction
            date_text = "Général"
            timestamp = 0 
            date_match_str = re.search(r'Affiché le\s*[:]?\s*([0-9/\-\w\s:àh]+)', raw_text, re.IGNORECASE)
            if date_match_str: 
                date_text = date_match_str.group(1).strip()
                timestamp = parse_date_to_timestamp(date_text)

            # 5. Link Extraction
            links = extract_links(tag)
            
            # Special check: If it's a Resource (PDF), the main click is the link
            if is_file or 'modtype_resource' in tag.get('class', []):
                main_a = tag.select_one('a')
                if main_a and main_a.get('href'):
                    full_href = main_a.get('href')
                    if full_href not in links:
                        links.insert(0, full_href) # Put main download link first

            # 6. Source ID
            source_link = AFFICHAGE_URL
            if tag.get('id'):
                safe_id = re.sub(r'[^a-zA-Z0-9-]', '', tag.get('id'))
                source_link = f"{AFFICHAGE_URL}#{safe_id}"

            item = {
                "id": unique_id,
                "title": bleach.clean(title, tags=[], strip=True),
                "body": body_html,
                "links": links,
                "date": bleach.clean(date_text, tags=[], strip=True),
                "timestamp": timestamp,
                "source": source_link
            }
            new_data.append(item)
        
        # Sort: Newest dates first. Items with timestamp 0 (no date) go to bottom.
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
                for i in range(min(5, len(scraped_items))):
                    item = scraped_items[i]
                    if item['id'] not in old_ids:
                        print(f"🔔 NEW: {item['title']}")
                        send_fcm_notification(item['title'], "New announcement")
                        break 
            latest_data = scraped_items
            first_run = False
            print(f"✅ Loaded {len(latest_data)} items.")
        time.sleep(600)

# --- ROUTES ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/announcements')
def api_data():
    response = jsonify(latest_data)
    response.headers['Cache-Control'] = 'public, max-age=60'
    return response

@app.route('/install')
def install_page():
    return render_template('download.html')

@app.route('/robots.txt')
def robots():
    return "User-agent: *\nDisallow: /api/\nDisallow: /test-notification-railway"

@app.route('/test-notification-railway', methods=['GET', 'POST'])
@limiter.limit("5 per minute") 
def manual_test():
    if request.method == 'POST':
        password = request.form.get('password')
        if password == ADMIN_PASSWORD:
            try:
                send_fcm_notification("Security Test", "Secure System Operational.")
                return "<h1>✅ Success</h1><p>Secure Notification Sent!</p>"
            except Exception as e:
                return f"<h1>Error</h1><p>{str(e)}</p>"
        else:
            return "<h1>❌ Access Denied</h1>"
    return """
    <form method="POST">
        <input type="password" name="password" placeholder="Password" required>
        <button type="submit">SEND</button>
    </form>
    """

threading.Thread(target=background_loop, daemon=True).start()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)