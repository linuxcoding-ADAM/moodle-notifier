import threading
import time
import requests
import re
import hashlib
import os
import json
from flask import Flask, render_template, jsonify
from bs4 import BeautifulSoup, NavigableString, Tag

# --- CONFIG ---
AFFICHAGE_URL = 'https://elearning.univ-bejaia.dz/course/view.php?id=19989'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# --- ONESIGNAL CONFIG (LOADED FROM RAILWAY VARIABLES) ---
ONESIGNAL_APP_ID = os.environ.get('ONESIGNAL_APP_ID')
ONESIGNAL_API_KEY = os.environ.get('ONESIGNAL_API_KEY')

latest_data = []
first_run = True # Prevents sending 20 notifications when you restart the server
app = Flask(__name__)

# --- HELPERS ---
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

def send_notification(title, message):
    """Sends Push Notification via OneSignal"""
    if not ONESIGNAL_APP_ID or "PASTE" in ONESIGNAL_APP_ID:
        print("⚠️ OneSignal Keys not set.")
        return

    header = {"Content-Type": "application/json; charset=utf-8",
              "Authorization": f"Basic {ONESIGNAL_API_KEY}"}

    payload = {
        "app_id": ONESIGNAL_APP_ID,
        "included_segments": ["All"],
        "headings": {"en": "Nouvelle Annonce ST"},
        "contents": {"en": title}, # Shows the title of the announcement
        "small_icon": "ic_stat_onesignal_default"
    }
    
    try:
        req = requests.post("https://onesignal.com/api/v1/notifications", headers=header, data=json.dumps(payload))
        print("🚀 Notification Sent:", req.status_code)
    except Exception as e:
        print(f"❌ Notification Error: {e}")

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
            cards = soup.select('li.activity.modtype_label .activity-altcontent')
            
            new_data = []
            for tag in cards:
                raw_text = tag.get_text()
                unique_id = hashlib.sha256(raw_text.encode()).hexdigest()[:16]
                body_html = clean_html_text(tag)
                
                title = "Information"
                title_match = re.search(r'<b>(.*?)</b>', body_html)
                if title_match:
                    title = title_match.group(1).strip().replace(":", "")
                    body_html = body_html.replace(title_match.group(0), "", 1)

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
            
            # CHECK FOR NEW ITEMS
            if new_data:
                # If this is NOT the first run, and the top item is different...
                if not first_run and latest_data and new_data[0]['id'] != latest_data[0]['id']:
                    print("🔔 New Item Detected! Sending Notification...")
                    send_notification(new_data[0]['title'], "Click to see details")
                
                latest_data = new_data
                first_run = False
                print(f"✅ Updated {len(new_data)} items.")
            else:
                print("⚠️ No items found.")

        except Exception as e:
            print(f"❌ Scraper Error: {e}")
        
        time.sleep(600) # 10 Minutes

# --- ROUTES ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/announcements')
def api_data():
    return jsonify(latest_data)

threading.Thread(target=background_scraper, daemon=True).start()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
