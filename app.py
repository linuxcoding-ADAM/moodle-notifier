import threading
import time
import requests
import re
import hashlib
import os
import json
from flask import Flask, render_template, jsonify
from bs4 import BeautifulSoup, NavigableString, Tag

# --- FIREBASE ADMIN SETUP ---
import firebase_admin
from firebase_admin import credentials, messaging

# Load credentials from Railway Variable
cred_json = os.environ.get('FIREBASE_CREDENTIALS')
if cred_json:
    cred_dict = json.loads(cred_json)
    cred = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(cred)
else:
    print("⚠️ WARNING: FIREBASE_CREDENTIALS variable missing!")

# --- CONFIG ---
AFFICHAGE_URL = 'https://elearning.univ-bejaia.dz/course/view.php?id=19989'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

latest_data = []
first_run = True
app = Flask(__name__)

# --- HELPERS ---
def clean_html_text(tag):
    text_parts = []
    for child in tag.children:
        if isinstance(child, NavigableString): text_parts.append(child.string)
        elif isinstance(child, Tag):
            child_text = clean_html_text(child)
            if child.name in ['b', 'strong']: text_parts.append(f"<b>{child_text}</b>")
            elif child.name in ['i', 'em']: text_parts.append(f"<i>{child_text}</i>")
            elif child.name == 'a': text_parts.append(child_text)
            elif child.name in ['p', 'div', 'li', 'br']: text_parts.append(f"<br>{child_text}<br>")
            else: text_parts.append(child_text)
    return re.sub(r'<br>\s*<br>', '<br>', "".join(text_parts)).strip()

def extract_links(tag):
    links = []
    for a in tag.find_all("a", href=True):
        href = a.get('href')
        if href and "http" not in href:
             href = f"https://elearning.univ-bejaia.dz{href}" if href.startswith('/') else f"https://elearning.univ-bejaia.dz/{href}"
        if href: links.append(href)
    return links

def send_fcm_notification(title, body_preview):
    """Sends to FCM with High Priority and 24h TTL"""
    try:
        android_config = messaging.AndroidConfig(
            priority='high',
            ttl=86400,
            notification=messaging.AndroidNotification(click_action='FLUTTER_NOTIFICATION_CLICK')
        )
        message = messaging.Message(
            notification=messaging.Notification(title="Nouvelle Annonce ST", body=title),
            android=android_config,
            topic='announcements',
        )
        messaging.send(message)
        print(f"🚀 FCM Notification Sent")
    except Exception as e:
        print(f"❌ FCM Error: {e}")

# --- SCRAPER ---
def background_scraper():
    global latest_data, first_run
    print("--- Scraper Thread Started ---")
    while True:
        try:
            print("Checking for updates...")
            session = requests.Session()
            session.headers.update(HEADERS)
            response = session.get(AFFICHAGE_URL, timeout=30)
            soup = BeautifulSoup(response.text, 'html.parser')
            # Select the content DIV
            cards = soup.select('li.activity.modtype_label .activity-altcontent')
            
            new_data = []
            
            for tag in cards:
                raw_text = tag.get_text(" ", strip=True)
                unique_id = hashlib.sha256(raw_text.encode()).hexdigest()[:16]
                body_html = clean_html_text(tag)
                
                # 1. Title Extraction
                title = "Information"
                title_match = re.search(r'<b>(.*?)</b>', body_html)
                if title_match:
                    title = title_match.group(1).strip().replace(":", "")
                    body_html = body_html.replace(title_match.group(0), "", 1)

                # 2. Date Extraction (IMPROVED REGEX)
                date_text = "Général"
                date_match = re.search(r'Affiché le\s*[:]?\s*([0-9/\-\w\s:]+)', raw_text, re.IGNORECASE)
                if date_match: 
                    date_text = date_match.group(1).strip()

                # 3. Source Link Extraction (THE BRUTAL FEATURE)
                parent_li = tag.find_parent('li', class_='activity')
                source_link = AFFICHAGE_URL
                if parent_li and parent_li.get('id'):
                    source_link = f"{AFFICHAGE_URL}#{parent_li.get('id')}"

                item = {
                    "id": unique_id,
                    "title": title,
                    "body": body_html,
                    "links": extract_links(tag),
                    "date": date_text,
                    "source": source_link
                }
                new_data.append(item)
            
            if new_data:
                if not first_run and latest_data:
                    old_ids = {item['id'] for item in latest_data}
                    # Check top 5 for new items (fixes Pinned Post issue)
                    for i in range(min(5, len(new_data))):
                        item = new_data[i]
                        if item['id'] not in old_ids:
                            print(f"🔔 NEW: {item['title']}")
                            send_fcm_notification(item['title'], item['body'][:50])
                            break 
                
                latest_data = new_data
                first_run = False
                print(f"✅ Updated {len(new_data)} items.")
            else:
                print("⚠️ No items found.")

        except Exception as e:
            print(f"❌ Scraper Error: {e}")
        
        time.sleep(600)

# --- ROUTES ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/announcements')
def api_data():
    return jsonify(latest_data)

# --- DOWNLOAD PAGE ---
@app.route('/install')
def install_page():
    return render_template('download.html')

# --- MANUAL TEST ROUTE (RESTORED) ---
@app.route('/test-notification-railway')
def manual_test():
    try:
        # Calls the function that talks to Google
        send_fcm_notification("Test Manual", "System is working perfectly.")
        return "<h1>Notification Sent!</h1><p>Check your phone now.</p>"
    except Exception as e:
        return f"<h1>Error</h1><p>{str(e)}</p>"

# --- MAIN ---
threading.Thread(target=background_scraper, daemon=True).start()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
