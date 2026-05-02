import threading
import time
import requests
import re
import hashlib
import os
import json
import bleach
import hmac
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
        print("✅ Firebase initialized successfully.")
    except Exception as e:
        print(f"⚠️ Firebase Error: {e}")

# --- CONFIG ---
AFFICHAGE_URL = 'https://elearning.univ-bejaia.dz/course/view.php?id=19989'
HEADERS = {'User-Agent': 'Mozilla/5.0'}
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', '34362053')
CACHE_FILE = 'moodle_cache.json'

latest_data = []
first_run = True
moodle_status = "online"  # 🟢 NEW: Tracks if Moodle is up or down

try:
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            latest_data = json.load(f)
except Exception:
    pass

app = Flask(__name__)
limiter = Limiter(get_remote_address, app=app, default_limits=["500 per day", "100 per hour"], storage_uri="memory://")

@app.after_request
def add_security_headers(response):
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['Content-Security-Policy'] = "default-src 'self' https:; script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://www.googletagmanager.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src * data:;"
    return response

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
            return datetime(int(year), int(month), int(day), int(hour), int(minute)).timestamp()
    except Exception: pass
    return 0

def clean_html_text(tag):
    if not tag: return ""
    text_parts = []
    for child in tag.children:
        if isinstance(child, NavigableString): 
            text = child.string.strip()
            if text: text_parts.append(text)
        elif isinstance(child, Tag):
            if 'accesshide' in child.get('class', []): continue
            child_text = clean_html_text(child)
            if child_text:
                if child.name in ['b', 'strong']: text_parts.append(f"<b>{child_text}</b>")
                elif child.name in ['p', 'div', 'li', 'br', 'ul']: text_parts.append(f"\n{child_text}\n")
                else: text_parts.append(child_text)
    full_text = " ".join(text_parts)
    return re.sub(r'\n\s*\n', '\n\n', full_text).strip()

def extract_links(tag):
    links = []
    for a in tag.find_all("a", href=True):
        href = a.get('href')
        if 'user/view' in href or 'help.php' in href: continue
        if href and "http" not in href: href = f"https://elearning.univ-bejaia.dz/{href.lstrip('/')}"
        if href and href.startswith('http') and href not in links: links.append(href)
    return links

def extract_images(tag):
    images = []
    for img in tag.find_all("img", src=True):
        src = img.get('src')
        if 'theme/image.php' in src or '/pix/' in src or 'icon' in src.lower() or 'spacer' in src.lower(): continue
        if src and "http" not in src: src = f"https://elearning.univ-bejaia.dz/{src.lstrip('/')}"
        if src not in images: images.append(src)
    return images

def send_fcm_notification(title, body_preview):
    try:
        android_config = messaging.AndroidConfig(priority='high', ttl=86400, notification=messaging.AndroidNotification(default_sound=True, default_vibrate_timings=True))
        safe_title = bleach.clean(title, tags=[], strip=True)
        message = messaging.Message(notification=messaging.Notification(title="Nouvelle Annonce ST", body=safe_title), android=android_config, topic='announcements')
        messaging.send(message)
    except Exception as e: print(f"❌ FCM Error: {e}")

def scrape_task():
    global moodle_status
    try:
        with requests.Session() as session:
            session.headers.update(HEADERS)
            response = session.get(AFFICHAGE_URL, timeout=30)
            response.raise_for_status()
            
        moodle_status = "online" # 🟢 Moodle is working
        soup = BeautifulSoup(response.text, 'html.parser')
        cards = soup.select('li.activity')
        
        new_data = []
        for tag in cards:
            if 'modtype_forum' in tag.get('class', []): continue
            raw_text = tag.get_text(" ", strip=True)
            if not raw_text or len(raw_text) < 3: continue 

            unique_id = hashlib.sha256(raw_text.encode('utf-8')).hexdigest()[:16]
            content_area = tag.select_one('.contentwithoutlink, .activity-altcontent, .no-overflow') or tag
            body_html = clean_html_text(content_area)
            
            title, title_match = "Information", re.search(r'<b>(.*?)</b>', body_html)
            instancename = tag.select_one('.instancename')
            
            if title_match:
                title = title_match.group(1).strip().replace(":", "")
                body_html = body_html.replace(title_match.group(0), "", 1)
            elif instancename:
                title = instancename.get_text(strip=True).replace(" Fichier", "").replace(" URL", "").replace(" Dossier", "")
            
            pure_description = bleach.clean(body_html, tags=[], strip=True)
            
            date_text, timestamp = "Général", 0
            date_match = re.search(r'Affiché le\s*[:]?\s*([0-9]{1,2}\s+[a-zA-Zéû]+\s+[0-9]{4}.*?(\d{1,2}[h:]\d{1,2})?)', raw_text, re.IGNORECASE)
            if date_match:
                date_text = date_match.group(1).strip()
                timestamp = parse_date_to_timestamp(date_text)
            
            source_link = f"{AFFICHAGE_URL}#{re.sub(r'[^a-zA-Z0-9-]', '', tag.get('id'))}" if tag.get('id') else AFFICHAGE_URL

            new_data.append({
                "id": unique_id,
                "title": bleach.clean(title, tags=[], strip=True),
                "description": pure_description.replace('\n', '<br>'),
                "links": extract_links(tag),
                "images": extract_images(tag),
                "date": bleach.clean(date_text, tags=[], strip=True),
                "timestamp": timestamp,
                "source": source_link
            })
        
        new_data.sort(key=lambda x: x['timestamp'], reverse=True)
        return new_data

    except requests.exceptions.RequestException as e:
        moodle_status = "offline" # 🔴 Moodle crashed
        print(f"❌ Moodle is Down: {e}")
        return None
    except Exception as e:
        print(f"❌ Scraper Error: {e}")
        return None

def background_loop():
    global latest_data, first_run
    while True:
        scraped_items = scrape_task()
        if scraped_items is not None:
            try:
                with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                    json.dump(scraped_items, f, ensure_ascii=False)
            except Exception: pass

            if not first_run and latest_data:
                old_ids = {item['id'] for item in latest_data}
                for item in scraped_items[:5]:
                    if item['id'] not in old_ids:
                        send_fcm_notification(item['title'], "New announcement")
                        break 
            latest_data = scraped_items
            first_run = False
        time.sleep(600)

@app.route('/')
def index(): return render_template('index.html')

@app.route('/api/announcements')
def api_data():
    # 🟢 NEW: Send the data AND the server status to the frontend
    response_payload = {
        "status": moodle_status,
        "data": latest_data
    }
    response = jsonify(response_payload)
    response.headers['Cache-Control'] = 'public, max-age=60'
    return response

@app.route('/install')
def install_page(): return render_template('download.html')

@app.route('/robots.txt')
def robots(): return "User-agent: *\nDisallow: /api/"

@app.route('/test-notification-railway', methods=['GET', 'POST'])
@limiter.limit("5 per minute") 
def manual_test():
    if request.method == 'POST':
        password = request.form.get('password', '')
        if hmac.compare_digest(password, ADMIN_PASSWORD):
            try:
                send_fcm_notification("Security Test", "Secure System Operational.")
                return "<h1>✅ Success</h1>"
            except Exception as e: return f"<h1>Error</h1><p>{str(e)}</p>"
        else: return "<h1>❌ Access Denied</h1>", 403
    return '<form method="POST"><input type="password" name="password" required><button type="submit">SEND</button></form>'

threading.Thread(target=background_loop, daemon=True).start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
