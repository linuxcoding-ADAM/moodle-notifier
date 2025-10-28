# The Definitive, Two-Bot, Bulletproof Moodle Scraper (All bugs fixed)

import requests
import json
import time
import re
import os
import logging
import traceback
from bs4 import BeautifulSoup, NavigableString # <-- IMPORT IS NOW CORRECTLY AT THE TOP LEVEL

# --- CONFIGURATION CLASS ---
class Config:
    LOGIN_URL = 'https://elearning.univ-bejaia.dz/login/index.php'
    AFFICHAGE_URL = 'https://elearning.univ-bejaia.dz/course/view.php?id=19989'
    
    MOODLE_USERNAME = os.getenv('MOODLE_USERNAME')
    MOODLE_PASSWORD = os.getenv('MOODLE_PASSWORD')
    
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN') # For announcements
    TELEGRAM_ERROR_BOT_TOKEN = os.getenv('TELEGRAM_ERROR_BOT_TOKEN') # For errors
    
    TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
    USER_FULL_NAME = os.getenv('USER_FULL_NAME')

    SEEN_IDS_FILE = '/data/seen_ids.json'
    SEEN_IDS_FILE_TMP = '/data/seen_ids.json.tmp'

    CHECK_INTERVAL = 600
    STARTUP_DELAY = 10
    ERROR_RETRY_DELAY = 300

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# --- TELEGRAM AND DATA FUNCTIONS ---

def _send_telegram_message(token, chat_id, message, parse_mode='MarkdownV2'):
    """Generic internal function to send a message."""
    if not all([token, chat_id]):
        logging.error("Telegram token or chat ID is missing for a message.")
        return False
    if len(message) > 4096:
        message = message[:4090] + "\n\n...(message truncated)"
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {'chat_id': chat_id, 'text': message, 'parse_mode': parse_mode, 'disable_web_page_preview': True}
    
    try:
        response = requests.post(url, json=payload, timeout=30)
        if response.status_code == 200:
            logging.info(f"Successfully sent message to {chat_id}.")
            return True
        else:
            logging.error(f"Failed to send message to {chat_id}: {response.text}")
            if "can't parse entities" in response.text and parse_mode:
                logging.warning("Markdown parsing failed. Retrying as plain text.")
                payload['parse_mode'] = None
                requests.post(url, json=payload, timeout=30)
            return False
    except Exception as e:
        logging.error(f"Exception while sending message: {e}")
        return False

def send_announcement(message):
    """Sends a new announcement using the main bot."""
    return _send_telegram_message(Config.TELEGRAM_BOT_TOKEN, Config.TELEGRAM_CHAT_ID, message)

def send_error_alert(message):
    """Sends an error or health alert using the error bot."""
    return _send_telegram_message(Config.TELEGRAM_ERROR_BOT_TOKEN, Config.TELEGRAM_CHAT_ID, message, parse_mode='Markdown')

def get_seen_ids():
    try:
        with open(Config.SEEN_IDS_FILE, 'r') as f: return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError): return set()

def save_seen_ids(ids):
    os.makedirs(os.path.dirname(Config.SEEN_IDS_FILE), exist_ok=True)
    with open(Config.SEEN_IDS_FILE_TMP, 'w') as f: json.dump(list(ids), f)
    os.rename(Config.SEEN_IDS_FILE_TMP, Config.SEEN_IDS_FILE)

def html_to_markdown_v2(element):
    def escape(text): return re.sub(r'([_{}\[\]()~`>#+\-=|.!])', r'\\\1', text)
    if isinstance(element, NavigableString): return escape(str(element))
    content = "".join(html_to_markdown_v2(child) for child in element.children)
    tag_name = element.name
    if tag_name in ['strong', 'b']: return f'*{content}*'
    if tag_name in ['em', 'i']: return f'_{content}_'
    if tag_name == 'u': return f'__{content}__'
    if tag_name == 'a' and element.get('href'):
        href = element['href']
        if not href.startswith('http'): href = 'https://elearning.univ-bejaia.dz' + href
        return f'[{content}]({escape(href)})'
    if tag_name in ['p', 'div', 'tr', 'h1', 'h2', 'h3', 'h4', 'li']: return f'{content}\n'
    if tag_name == 'br': return '\n'
    return content

# --- THE MAIN SCRAPER CLASS ---
class MoodleScraper:
    def __init__(self):
        self.session = requests.Session()
        self.seen_ids = get_seen_ids()
        self.logged_in = False

    def _login(self):
        logging.info("Attempting a fresh login...")
        self.session = requests.Session()
        try:
            login_page = self.session.get(Config.LOGIN_URL, timeout=30)
            login_page.raise_for_status()
            soup = BeautifulSoup(login_page.text, 'html.parser')
            logintoken = soup.find('input', {'name': 'logintoken'})['value']
            
            payload = {'username': Config.MOODLE_USERNAME, 'password': Config.MOODLE_PASSWORD, 'logintoken': logintoken}
            response = self.session.post(Config.LOGIN_URL, data=payload, timeout=30)
            response.raise_for_status()

            if Config.USER_FULL_NAME and Config.USER_FULL_NAME.lower() in response.text.lower():
                logging.info("Login successful! User name confirmed.")
                self.logged_in = True
                return True
            else:
                error_msg = "🔴 Login Verification Failed!\nCould not find user name on the page. Bot will retry."
                logging.error(error_msg)
                send_error_alert(error_msg)
                self.logged_in = False
                return False
        except requests.exceptions.RequestException as e:
            error_msg = f"🔴 Network error during login:\n`{e}`"
            logging.error(error_msg)
            send_error_alert(error_msg)
            self.logged_in = False
            return False
        except (TypeError, KeyError):
            error_msg = "🔴 Failed to parse Moodle login page. Page structure may have changed."
            logging.error(error_msg)
            send_error_alert(error_msg)
            self.logged_in = False
            return False

    def run_check(self):
        logging.info("Starting check...")
        if not self.logged_in:
            if not self._login():
                logging.error("Aborting check due to login failure.")
                return

        try:
            page = self.session.get(Config.AFFICHAGE_URL, timeout=30)
            page.raise_for_status()
            if "login/index.php" in page.url:
                logging.warning("Session expired. Forcing re-login on next cycle.")
                self.logged_in = False
                return
        except requests.exceptions.RequestException as e:
            error_msg = f"🔴 Network error fetching announcements:\n`{e}`"
            logging.error(error_msg)
            send_error_alert(error_msg)
            return

        soup = BeautifulSoup(page.text, 'html.parser')
        announcement_tags = soup.select('li.activity.modtype_label .activity-altcontent')

        if not announcement_tags:
            logging.warning("No announcement tags found.")
            return

        new_items = []
        for tag in announcement_tags:
            parent_li = tag.find_parent('li', class_='activity')
            item_id = parent_li.get('id') if parent_li else None
            if item_id and item_id not in self.seen_ids:
                new_items.append(tag)
        
        if new_items:
            logging.info(f"Found {len(new_items)} new announcements!")
            for item_tag in reversed(new_items):
                parent_li = item_tag.find_parent('li', class_='activity')
                item_id = parent_li.get('id') if parent_li else None
                markdown_content = html_to_markdown_v2(item_tag)
                clean_content = re.sub(r'\n{3,}', '\n\n', markdown_content).strip()
                message = f"📣 *Nouvelle Affiche*\n================\n\n{clean_content}"

                if send_announcement(message):
                    self.seen_ids.add(item_id)
                    save_seen_ids(self.seen_ids)
                    logging.info(f"Successfully processed and saved ID: {item_id}")
                else:
                    logging.warning(f"Failed to send notification for {item_id}. It will be retried.")
                time.sleep(2)
        else:
            logging.info("No new announcements found.")

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    required_vars = ['MOODLE_USERNAME', 'MOODLE_PASSWORD', 'TELEGRAM_BOT_TOKEN', 'TELEGRAM_ERROR_BOT_TOKEN', 'TELEGRAM_CHAT_ID', 'USER_FULL_NAME']
    if not all(os.getenv(var) for var in required_vars):
        startup_error = "🔴 BOT STARTUP FAILED: One or more essential environment variables are missing. Please check all 6 variables on the Railway dashboard."
        logging.critical(startup_error)
        send_error_alert(startup_error) # CORRECTED: Uses the error bot
    else:
        logging.info("Script is starting up...")
        send_error_alert("✅ Bot has started/restarted and is now monitoring.") # CORRECTED: Uses the error bot
        time.sleep(Config.STARTUP_DELAY)
        
        scraper = MoodleScraper()
        
        while True:
            try:
                scraper.run_check()
                logging.info(f"Check complete. Waiting for {Config.CHECK_INTERVAL // 60} minutes...")
                time.sleep(Config.CHECK_INTERVAL)
            except Exception as e:
                error_details = traceback.format_exc()
                error_message = f"🔴 BOT CRITICAL ERROR: The main loop has crashed.\n\n*Error:*\n`{e}`\n\n*Traceback:*\n```{error_details}```\n\nThe bot will restart its loop in {Config.ERROR_RETRY_DELAY // 60} minutes."
                logging.critical(error_message)
                send_error_alert(error_message) # CORRECTED: Uses the error bot
                time.sleep(Config.ERROR_RETRY_DELAY)
