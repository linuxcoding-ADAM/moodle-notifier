# FINAL, DEFINITIVE RAILWAY SCRIPT (All fixes included + Indentation Fix)

import requests
import json
from bs4 import BeautifulSoup
import time
import re
import os
import logging
import traceback

# --- CONFIGURATION ---
LOGIN_URL = 'https://elearning.univ-bejaia.dz/login/index.php'
AFFICHAGE_URL = 'https://elearning.univ-bejaia.dz/course/view.php?id=19989'

MOODLE_USERNAME = os.getenv('MOODLE_USERNAME')
MOODLE_PASSWORD = os.getenv('MOODLE_PASSWORD')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

USER_FULL_NAME = os.getenv('USER_FULL_NAME')
# --- END OF CONFIGURATION ---

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

SEEN_IDS_FILE = '/data/seen_ids.json'
SEEN_IDS_FILE_TMP = '/data/seen_ids.json.tmp'

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
    if not all([TELEGRAM_BOT_TOKEN, chat_id]):
        logging.error("Telegram token or chat ID is missing.")
        return False
    if len(message) > 4096: message = message[:4090] + "\n\n...(msg truncated)"
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {'chat_id': chat_id, 'text': message, 'parse_mode': 'Markdown', 'disable_web_page_preview': True}
    
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
    logging.info("Attempting to log in...")
    try:
        login_page = session.get(LOGIN_URL, timeout=30)
        login_page.raise_for_status()
        soup = BeautifulSoup(login_page.text, 'html.parser')
        logintoken = soup.find('input', {'name': 'logintoken'})['value']
        
        login_payload = {'username': MOODLE_USERNAME, 'password': MOODLE_PASSWORD, 'logintoken': logintoken}
        response = session.post(LOGIN_URL, data=login_payload, timeout=30)
        response.raise_for_status()

        if USER_FULL_NAME and USER_FULL_NAME.lower() in response.text.lower():
            logging.info("Login successful! User name found.")
            return True
        elif 'action="logout"' in response.text:
            logging.info("Login successful! Logout link found.")
            return True
        else:
            error_message = "🔴 Login Verification Failed!\n\nCould not find user name or logout link after posting credentials. The Moodle site might have changed, or the session is invalid. The bot will retry in 10 minutes."
            logging.error(error_message)
            send_telegram_message(error_message, TELEGRAM_CHAT_ID)
            return False
            
    except requests.exceptions.RequestException as e:
        error_message = f"🔴 A network error occurred during login:\n\n`{e}`\n\nThe Moodle site may be down. The bot will retry in 10 minutes."
        logging.error(error_message)
        send_telegram_message(error_message, TELEGRAM_CHAT_ID)
        return False
    except (TypeError, KeyError):
        error_message = "🔴 Failed to parse Moodle login page.\n\nThe page structure has likely changed. The bot will retry in 10 minutes."
        logging.error(error_message)
        send_telegram_message(error_message, TELEGRAM_CHAT_ID)
        return False

def fetch_and_process_announcements(session, seen_ids):
    try:
        logging.info(f"Accessing announcements page...")
        page = session.get(AFFICHAGE_URL, timeout=30)
        page.raise_for_status()
        soup = BeautifulSoup(page.text, 'html.parser')
    except requests.exceptions.RequestException as e:
        error_message = f"🔴 A network error occurred while fetching announcements:\n\n`{e}`\n\nThe Moodle site may be down. The bot will retry in 10 minutes."
        logging.error(error_message)
        send_telegram_message(error_message, TELEGRAM_CHAT_ID)
        return

    announcement_tags = soup.select('li.activity.modtype_label .activity-altcontent')
    if not announcement_tags:
        logging.warning("No announcement tags found on page. This is unusual and could indicate a silent login failure.")
        return

    new_announcements = []
    for tag in announcement_tags:
        parent_li = tag.find_parent('li', class_='activity')
        item_id = parent_li.get('id') if parent_li else None
        if item_id and item_id not in seen_ids:
            plain_text, links = html_to_plain_text_and_links(tag)
            new_announcements.append({'id': item_id, 'content': plain_text, 'links': links})
    
    if new_announcements:
        logging.info(f"Found {len(new_announcements)} new announcements!")
        for item in new_announcements: # Corrected order
            message = f"📣 Nouvelle Affiche\n================\n\n{item['content']}"
            if item['links']:
                message += "\n\n----------------\n🔗 Liens:\n" + "\n".join(f"- {link}" for link in item['links'])
            
            if send_telegram_message(message, TELEGRAM_CHAT_ID):
                seen_ids.add(item['id'])
                save_seen_ids(seen_ids)
                logging.info(f"Successfully processed and saved ID: {item['id']}")
            else:
                logging.warning(f"Failed to send notification for {item['id']}. It will be retried on the next check.")
            
            time.sleep(1)
    else:
        logging.info("No new announcements found.")

def html_to_plain_text_and_links(tag):
    links = [a['href'] for a in tag.find_all("a", href=True) if a.get('href')]
    full_links = []
    for link in links:
        if not link.startswith('http'):
            full_links.append('https://elearning.univ-bejaia.dz' + link)
        else:
            full_links.append(link)
    for br in tag.find_all("br"): br.replace_with("\n")
    for p in tag.find_all("p"): p.append("\n")
    text = tag.get_text()
    lines = (line.strip() for line in text.splitlines())
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    return "\n".join(chunk for chunk in chunks if chunk), full_links

def main_check():
    if not all([MOODLE_USERNAME, MOODLE_PASSWORD, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, USER_FULL_NAME]):
        error_msg = "🔴 BOT STARTUP FAILED: One or more essential credentials (like USER_FULL_NAME) are missing. Please check Railway variables."
        logging.critical(error_msg)
        send_telegram_message(error_msg, TELEGRAM_CHAT_ID)
        time.sleep(3600)
        return

    session = requests.Session()
    if perform_login(session):
        seen_ids = get_seen_ids()
        fetch_and_process_announcements(session, seen_ids)

if __name__ == "__main__":
    logging.info("Script is starting up...")
    
    send_telegram_message("✅ Bot has started/restarted and is now monitoring for announcements.", TELEGRAM_CHAT_ID)
    
    time.sleep(5)
    
    while True:
        try:
            main_check()
            logging.info("Check complete. Waiting for 10 minutes...")
            time.sleep(600)
        except Exception as e:
            # --- THIS IS THE CORRECTED BLOCK ---
            # Format the full error traceback for debugging
            error_details = traceback.format_exc()
            # Note the use of Markdown for code blocks
            error_message = f"🔴 BOT CRITICAL ERROR: The script has crashed unexpectedly.\n\n*Error:*\n`{e}`\n\n*Full Traceback:*\n```{error_details}```\n\nThe bot will restart in 5 minutes."
            logging.critical(error_message)
            send_telegram_message(error_message, TELEGRAM_CHAT_ID)
            time.sleep(300)`
