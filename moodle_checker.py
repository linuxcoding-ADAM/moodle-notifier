# FINAL, ROBUST RAILWAY SCRIPT (All fixes included)

import requests
import json
from bs4 import BeautifulSoup
import time
import re
import os
import logging

# --- CONFIGURATION: READS SECURELY FROM RAILWAY'S ENVIRONMENT ---
LOGIN_URL = 'https://elearning.univ-bejaia.dz/login/index.php'
AFFICHAGE_URL = 'https://elearning.univ-bejaia.dz/course/view.php?id=19989'

MOODLE_USERNAME = os.getenv('MOODLE_USERNAME')
MOODLE_PASSWORD = os.getenv('MOODLE_PASSWORD')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
# --- END OF SECURE CONFIGURATION ---

# Configure logging to see output in Railway's logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Paths for persistent storage on Railway
SEEN_IDS_FILE = '/data/seen_ids.json'
SEEN_IDS_FILE_TMP = '/data/seen_ids.json.tmp' # Temp file for safe saving

def get_seen_ids():
    """Loads the set of seen announcement IDs from the persistent volume."""
    try:
        with open(SEEN_IDS_FILE, 'r') as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        # If the file doesn't exist or is corrupted, start fresh.
        return set()

def save_seen_ids(ids):
    """Atomically saves the set of IDs to the persistent volume to prevent corruption."""
    os.makedirs(os.path.dirname(SEEN_IDS_FILE), exist_ok=True)
    # 1. Write to a temporary file first.
    with open(SEEN_IDS_FILE_TMP, 'w') as f:
        json.dump(list(ids), f)
    # 2. If the write was successful, rename the temp file to the real file.
    # This is an "atomic" operation and is much safer than writing directly.
    os.rename(SEEN_IDS_FILE_TMP, SEEN_IDS_FILE)

def html_to_plain_text_and_links(tag):
    """Converts announcement HTML into clean text and a list of links."""
    links = []
    for a in tag.find_all("a", href=True):
        href = a['href']
        if not href.startswith('http'):
            href = 'https://elearning.univ-bejaia.dz' + href
        links.append(href)
    
    # Replace line-breaking tags with newlines to preserve structure
    for br in tag.find_all("br"): br.replace_with("\n")
    for p in tag.find_all("p"): p.append("\n")
    for tr in tag.find_all("tr"): tr.append("\n")

    text = tag.get_text()
    
    # Clean up excessive whitespace for a tidy message
    lines = (line.strip() for line in text.splitlines())
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    clean_text = "\n".join(chunk for chunk in chunks if chunk)
    return clean_text, links

def send_telegram_message(message):
    """Sends a notification to your private Telegram chat."""
    if len(message) > 4096:
        message = message[:4090] + "\n\n...(message truncated)"
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': message, 'disable_web_page_preview': True}
    
    try:
        response = requests.post(url, json=payload, timeout=20)
        if response.status_code == 200:
            logging.info("Successfully sent notification.")
        else:
            logging.error(f"Failed to send notification: {response.text}")
    except Exception as e:
        logging.error(f"Error sending Telegram message: {e}")

def run_check():
    """Performs a single check of the Moodle page."""
    if not all([MOODLE_USERNAME, MOODLE_PASSWORD, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID]):
        logging.error("One or more environment variables are missing! Please check variables on the Railway dashboard.")
        return
        
    logging.info("Starting check...")
    seen_ids = get_seen_ids()
    
    with requests.Session() as s:
        try:
            login_page = s.get(LOGIN_URL, timeout=20)
            soup = BeautifulSoup(login_page.text, 'html.parser')
            logintoken = soup.find('input', {'name': 'logintoken'})['value']
            
            login_payload = {'username': MOODLE_USERNAME, 'password': MOODLE_PASSWORD, 'logintoken': logintoken}
            s.post(LOGIN_URL, data=login_payload, timeout=20)
            
            page = s.get(AFFICHAGE_URL, timeout=20)
            soup = BeautifulSoup(page.text, 'html.parser')
        except Exception as e:
            logging.error(f"Scraping error: {e}")
            return
            
    announcement_tags = soup.select('li.activity.modtype_label .activity-altcontent')
    if not announcement_tags:
        logging.warning("No announcements found on page.")
        return
        
    new_announcements = []
    for tag in announcement_tags:
        parent_li = tag.find_parent('li', class_='activity')
        item_id = parent_li.get('id') if parent_li else None
        
        if item_id and item_id not in seen_ids:
            plain_text, links = html_to_plain_text_and_links(tag)
            new_announcements.append({
                'id': item_id,
                'content': plain_text,
                'links': links
            })
    
    if new_announcements:
        logging.info(f"Found {len(new_announcements)} new announcements!")
        # Send notifications in reverse order so the newest appears first in Telegram
        for item in reversed(new_announcements):
            message = f"📣 Nouvelle Affiche\n================\n\n{item['content']}"
            if item['links']:
                message += "\n\n----------------\n🔗 Liens:\n" + "\n".join(f"- {link}" for link in item['links'])
                
            send_telegram_message(message)
            seen_ids.add(item['id'])
            time.sleep(1)
        
        # Save all the new IDs at once after the loop is finished
        save_seen_ids(seen_ids)
    else:
        logging.info("No new announcements found.")

if __name__ == "__main__":
    # Add a startup delay to give the persistent volume time to mount.
    # This prevents the "amnesia" bug.
    logging.info("Script started. Waiting 5 seconds for volume to mount...")
    time.sleep(5)
    logging.info("Entering main loop.")
    
    while True:
        try:
            run_check()
            # Wait for 10 minutes (600 seconds) before the next check
            logging.info("Check complete. Waiting for 10 minutes...")
            time.sleep(600) 
        except Exception as e:
            logging.critical(f"A major error occurred in the main loop: {e}")
            # If the script crashes, wait 5 minutes before trying again to avoid spamming logs.
            time.sleep(300)
