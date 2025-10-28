# FINAL, BULLETPROOF RAILWAY SCRIPT (All fixes included + Paranoid Login Check)

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

# NEW: Add your name as it appears on the Moodle site (e.g., "Adam Smith")
# This is used to verify that the login was successful.
USER_FULL_NAME = os.getenv('USER_FULL_NAME')
# --- END OF CONFIGURATION ---

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

SEEN_IDS_FILE = '/data/seen_ids.json'
SEEN_IDS_FILE_TMP = '/data/seen_ids.json.tmp'

# --- CORE FUNCTIONS ---

def get_seen_ids():
    try:
        with open(SEEN_IDS_FILE, 'r') as f: return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()

def save_seen_ids(ids):
    os.makedirs(os.path.dirname(SEEN_IDS_FILE), exist_ok=True)
    with open(SEEN_IDS_FILE_TMP, 'w') as f: json.dump(list(ids), f)
    os.rename(SEEN_IDS_FILE_TMP, SEEN_IDS_FILE)

def send_telegram_message(message, chat_id):
    """Sends a message to a specific chat ID."""
    if not all([TELEGRAM_BOT_TOKEN, chat_id]):
        logging.error("Telegram token or chat ID is missing.")
        return False
    if len(message) > 4096: message = message[:4090] + "\n\n...(msg truncated)"
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {'chat_id': chat_id, 'text': message, 'disable_web_page_preview': True}
    
    try:
        response = requests.post(url, json=payload, timeout=20)
        if response.status_code == 200:
            logging.info(f"Successfully sent message to {chat_id}.")
            return True
        else:
            logging.error(f"Failed to send message to {chat_id}: {response.text}")
            return False
    except Exception as e:
        logging.error(f"Exception while sending message: {e}")
        return False

def perform_login(session):
    """Logs into Moodle and verifies the login was successful."""
    logging.info("Attempting to log in...")
    try:
        # Step 1: Get the login page to retrieve the logintoken
        login_page = session.get(LOGIN_URL, timeout=30)
        login_page.raise_for_status() # Raise an error for bad status codes
        soup = BeautifulSoup(login_page.text, 'html.parser')
        logintoken = soup.find('input', {'name': 'logintoken'})['value']
        
        # Step 2: Post the login credentials
        login_payload = {'username': MOODLE_USERNAME, 'password': MOODLE_PASSWORD, 'logintoken': logintoken}
        response = session.post(LOGIN_URL, data=login_payload, timeout=30)
        response.raise_for_status()

        # Step 3: PARANOID LOGIN CHECK - Verify login by looking for the user's name or a logout link
        if USER_FULL_NAME and USER_FULL_NAME.lower() in response.text.lower():
            logging.info("Login successful! User name found on page.")
            return True
        elif 'action="logout"' in response.text:
            logging.info("Login successful! Logout link found on page.")
            return True
        else:
            logging.error("Login failed! Could not find user name or logout link on the page after login post.")
            return False
            
    except requests.exceptions.RequestException as e:
        logging.error(f"A network error occurred during login: {e}")
        return False
    except (TypeError, KeyError):
        logging.error("Failed to parse login page. The page structure may have changed.")
        return False

def fetch_and_process_announcements(session, seen_ids):
    """Fetches the announcements page and processes new items."""
    try:
        logging.info(f"Accessing announcements page: {AFFICHAGE_URL}")
        page = session.get(AFFICHAGE_URL, timeout=30)
        page.raise_for_status()
        soup = BeautifulSoup(page.text, 'html.parser')
    except requests.exceptions.RequestException as e:
        logging.error(f"A network error occurred while fetching announcements: {e}")
        return

    announcement_tags = soup.select('li.activity.modtype_label .activity-altcontent')
    if not announcement_tags:
        logging.warning("No announcement tags found. This could indicate a login failure or a change in the page layout.")
        return

    new_items_found = False
    for tag in announcement_tags:
        parent_li = tag.find_parent('li', class_='activity')
        item_id = parent_li.get('id') if parent_li else None
        
        if item_id and item_id not in seen_ids:
            new_items_found = True
            logging.info(f"Found new announcement: {item_id}")
            
            plain_text, links = html_to_plain_text_and_links(tag)
            message = f"📣 Nouvelle Affiche\n================\n\n{plain_text}"
            if links:
                message += "\n\n----------------\n🔗 Liens:\n" + "\n".join(f"- {link}" for link in links)
            
            if send_telegram_message(message, TELEGRAM_CHAT_ID):
                seen_ids.add(item_id)
                save_seen_ids(seen_ids)
                logging.info(f"Successfully processed and saved ID: {item_id}")
            else:
                logging.warning(f"Failed to send notification for {item_id}. It will be retried on the next check.")
            
            time.sleep(1) # Stagger notifications
    
    if not new_items_found:
        logging.info("No new announcements found.")

def html_to_plain_text_and_links(tag):
    """Helper function to convert HTML to text and extract links."""
    links = [a['href'] for a in tag.find_all("a", href=True) if a.get('href')]
    for a_link in links:
        if not a_link.startswith('http'): a_link = 'https://elearning.univ-bejaia.dz' + a_link
    for br in tag.find_all("br"): br.replace_with("\n")
    for p in tag.find_all("p"): p.append("\n")
    text = tag.get_text()
    lines = (line.strip() for line in text.splitlines())
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    return "\n".join(chunk for chunk in chunks if chunk), links

# --- MAIN EXECUTION LOOP ---

def main_check():
    """The main logic for a single check, designed to be called in a loop."""
    if not all([MOODLE_USERNAME, MOODLE_PASSWORD, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, USER_FULL_NAME]):
        logging.error("CRITICAL: One or more environment variables are missing! Check USER_FULL_NAME.")
        # Send a startup failure notification if possible
        send_telegram_message("🔴 BOT STARTUP FAILED: Missing essential credentials. Please check Railway variables.", TELEGRAM_CHAT_ID)
        return

    session = requests.Session()
    if perform_login(session):
        seen_ids = get_seen_ids()
        fetch_and_process_announcements(session, seen_ids)

if __name__ == "__main__":
    logging.info("Script is starting up...")
    
    # NEW: Send a startup/restart notification to confirm the bot is alive.
    send_telegram_message("✅ Bot has started/restarted and is now monitoring for announcements.", TELEGRAM_CHAT_ID)
    
    time.sleep(5) # Wait for volume to mount
    
    while True:
        try:
            main_check()
            logging.info("Check complete. Waiting for 10 minutes...")
            time.sleep(600)
        except Exception as e:
            logging.critical(f"A critical, unexpected error occurred in the main loop: {e}")
            send_telegram_message(f"🔴 BOT CRITICAL ERROR: The script has crashed. Error: {e}. It will restart in 5 minutes.", TELEGRAM_CHAT_ID)
            time.sleep(300)
