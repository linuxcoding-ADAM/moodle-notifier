# FINAL, ROBUST RAILWAY SCRIPT (Fixes the "Amnesia" and the "item" Bug)

import requests
import json
from bs4 import BeautifulSoup
import time
import re
import os
import logging

# --- CONFIGURATION ---
LOGIN_URL = 'https://elearning.univ-bejaia.dz/login/index.php'
AFFICHAGE_URL = 'https://elearning.univ-bejaia.dz/course/view.php?id=19989'

MOODLE_USERNAME = os.getenv('MOODLE_USERNAME')
MOODLE_PASSWORD = os.getenv('MOODLE_PASSWORD')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
# --- END OF CONFIGURATION ---

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

SEEN_IDS_FILE = '/data/seen_ids.json'
SEEN_IDS_FILE_TMP = '/data/seen_ids.json.tmp' # Temp file for safe saving

def get_seen_ids():
    try:
        with open(SEEN_IDS_FILE, 'r') as f: return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()

def save_seen_ids(ids):
    os.makedirs(os.path.dirname(SEEN_IDS_FILE), exist_ok=True)
    with open(SEEN_IDS_FILE_TMP, 'w') as f:
        json.dump(list(ids), f)
    os.rename(SEEN_IDS_FILE_TMP, SEEN_IDS_FILE)

def html_to_plain_text_and_links(tag):
    links = []
    for a in tag.find_all("a", href=True):
        href = a['href']
        if not href.startswith('http'): href = 'https://elearning.univ-bejaia.dz' + href
        links.append(href)
    for br in tag.find_all("br"): br.replace_with("\n")
    for p in tag.find_all("p"): p.append("\n")
    text = tag.get_text()
    lines = (line.strip() for line in text.splitlines())
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    return "\n".join(chunk for chunk in chunks if chunk), links

def send_telegram_message(message):
    if len(message) > 4096: message = message[:4090] + "\n\n...(msg truncated)"
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': message, 'disable_web_page_preview': True}
    try:
        response = requests.post(url, json=payload, timeout=20)
        if response.status_code == 200: logging.info("Successfully sent notification.")
        else: logging.error(f"Failed to send notification: {response.text}")
    except Exception as e:
        logging.error(f"Error sending Telegram message: {e}")

def run_check():
    if not all([MOODLE_USERNAME, MOODLE_PASSWORD, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID]):
        logging.error("One or more environment variables are missing!")
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
        
    found_new = False
    for tag in announcement_tags:
        parent_li = tag.find_parent('li', class_='activity')
        item_id = parent_li.get('id') if parent_li else None
        if item_id and item_id not in seen_ids:
            if not found_new:
                logging.info("Found new announcements!")
                found_new = True
                
            plain_text, links = html_to_plain_text_and_links(tag)
            
            # --- THIS IS THE CORRECTED LINE ---
            message = f"📣 Nouvelle Affiche\n================\n\n{plain_text}"
            
            if links: message += "\n\n----------------\n🔗 Liens:\n" + "\n".join(f"- {link}" for link in links)
            send_telegram_message(message)
            seen_ids.add(item_id)
            time.sleep(1)

    if found_new:
        save_seen_ids(seen_ids)
    else:
        logging.info("No new announcements found.")

if __name__ == "__main__":
    logging.info("Script started. Waiting 5 seconds for volume to mount...")
    time.sleep(5)
    logging.info("Entering main loop.")
    
    while True:
        try:
            run_check()
            logging.info("Check complete. Waiting for 10 minutes...")
            time.sleep(600) 
        except Exception as e:
            logging.critical(f"A major error occurred in the main loop: {e}")
            time.sleep(300)
