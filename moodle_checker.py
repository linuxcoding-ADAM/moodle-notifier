# The Definitive, Bulletproof Moodle Scraper

import requests
import json
import time
import re
import os
import logging
import traceback
from bs4 import BeautifulSoup, NavigableString

# --- CONFIGURATION CLASS ---
# All settings are neatly organized here.
class Config:
    LOGIN_URL = 'https://elearning.univ-bejaia.dz/login/index.php'
    AFFICHAGE_URL = 'https://elearning.univ-bejaia.dz/course/view.php?id=19989'
    
    MOODLE_USERNAME = os.getenv('MOODLE_USERNAME')
    MOODLE_PASSWORD = os.getenv('MOODLE_PASSWORD')
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
    USER_FULL_NAME = os.getenv('USER_FULL_NAME') # Your name as it appears on Moodle

    # File paths for persistent storage
    SEEN_IDS_FILE = '/data/seen_ids.json'
    SEEN_IDS_FILE_TMP = '/data/seen_ids.json.tmp'

    # Timing (in seconds)
    CHECK_INTERVAL = 600  # 10 minutes
    STARTUP_DELAY = 10    # Wait 10s on startup for volume mount
    ERROR_RETRY_DELAY = 300 # Wait 5 minutes after a major crash

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# --- TELEGRAM AND DATA FUNCTIONS ---

def send_telegram_message(message, chat_id, parse_mode='MarkdownV2'):
    """Sends a message to a specific chat ID with a specified parse mode."""
    if not all([Config.TELEGRAM_BOT_TOKEN, chat_id]):
        logging.error("Telegram token or chat ID is missing.")
        return False
    if len(message) > 4096:
        message = message[:4090] + "\n\n...(message truncated)"
    
    url = f"https://api.telegram.org/bot{Config.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {'chat_id': chat_id, 'text': message, 'parse_mode': parse_mode, 'disable_web_page_preview': True}
    
    try:
        response = requests.post(url, json=payload, timeout=30)
        if response.status_code == 200:
            logging.info(f"Successfully sent message to {chat_id}.")
            return True
        else:
            logging.error(f"Failed to send message to {chat_id}: {response.text}")
            # If markdown parsing failed, try sending as plain text
            if "can't parse entities" in response.text:
                logging.warning("Markdown parsing failed. Retrying as plain text.")
                payload['parse_mode'] = None
                requests.post(url, json=payload, timeout=30)
            return False
    except Exception as e:
        logging.error(f"Exception while sending message: {e}")
        return False

def get_seen_ids():
    """Loads the set of seen IDs from the persistent volume."""
    try:
        with open(Config.SEEN_IDS_FILE, 'r') as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()

def save_seen_ids(ids):
    """Atomically saves the set of IDs to the persistent volume."""
    os.makedirs(os.path.dirname(Config.SEEN_IDS_FILE), exist_ok=True)
    with open(Config.SEEN_IDS_FILE_TMP, 'w') as f:
        json.dump(list(ids), f)
    os.rename(Config.SEEN_IDS_FILE_TMP, Config.SEEN_IDS_FILE)

# --- ADVANCED HTML to MARKDOWNV2 CONVERTER ---
def html_to_markdown_v2(element):
    """
    Recursively and robustly converts a BeautifulSoup element into Telegram-compatible MarkdownV2.
    This handles nested tags and escapes special characters to prevent parsing errors.
    """
    def escape(text):
        # Escape characters that have special meaning in MarkdownV2
        return re.sub(r'([_{}\[\]()~`>#+\-=|.!])', r'\\\1', text)

    if isinstance(element, NavigableString):
        return escape(str(element))

    content = "".join(html_to_markdown_v2(child) for child in element.children)

    tag_name = element.name
    if tag_name in ['strong', 'b']:
        return f'*{content}*'
    if tag_name in ['em', 'i']:
        return f'_{content}_'
    if tag_name == 'u':
        return f'__{content}__'
    if tag_name == 'a' and element.get('href'):
        href = element['href']
        if not href.startswith('http'):
            href = 'https://elearning.univ-bejaia.dz' + href
        return f'[{content}]({escape(href)})'
    if tag_name in ['p', 'div', 'tr', 'h1', 'h2', 'h3', 'h4', 'li']:
        return f'{content}\n'
    if tag_name == 'br':
        return '\n'
    
    return content

# --- THE MAIN SCRAPER CLASS ---
class MoodleScraper:
    def __init__(self):
        self.session = requests.Session()
        self.seen_ids = get_seen_ids()
        self.logged_in = False

    def _login(self):
        """Performs a full login and verification. Returns True on success."""
        logging.info("Attempting a fresh login...")
        # Use a new session for every login attempt for maximum freshness
        self.session = requests.Session()
        
        try:
            login_page = self.session.get(Config.LOGIN_URL, timeout=30)
            login_page.raise_for_status()
            soup = BeautifulSoup(login_page.text, 'html.parser')
            logintoken = soup.find('input', {'name': 'logintoken'})['value']
            
            payload = {'username': Config.MOODLE_USERNAME, 'password': Config.MOODLE_PASSWORD, 'logintoken': logintoken}
            response = self.session.post(Config.LOGIN_URL, data=payload, timeout=30)
            response.raise_for_status()

            # The paranoid login check
            if Config.USER_FULL_NAME and Config.USER_FULL_NAME.lower() in response.text.lower():
                logging.info("Login successful! User name confirmed.")
                self.logged_in = True
                return True
            else:
                logging.error("Login verification failed. User name not found on page.")
                self.logged_in = False
                return False
        except requests.exceptions.RequestException as e:
            logging.error(f"Network error during login: {e}")
            send_telegram_message(f"🔴 Network error during login:\n`{e}`", Config.TELEGRAM_CHAT_ID, parse_mode='Markdown')
            self.logged_in = False
            return False
        except (TypeError, KeyError):
            logging.error("Failed to parse login page structure.")
            send_telegram_message("🔴 Failed to parse Moodle login page. The layout may have changed.", Config.TELEGRAM_CHAT_ID)
            self.logged_in = False
            return False

    def run_check(self):
        """Runs a single, complete check for new announcements."""
        logging.info("Starting check...")
        
        # If we aren't logged in, or the session might be stale, perform a full login.
        if not self.logged_in:
            if not self._login():
                logging.error("Aborting check due to login failure.")
                return

        try:
            page = self.session.get(Config.AFFICHAGE_URL, timeout=30)
            page.raise_for_status()

            # If we are redirected to the login page, our session has expired.
            if "login/index.php" in page.url or (Config.USER_FULL_NAME and Config.USER_FULL_NAME.lower() not in page.text.lower()):
                logging.warning("Session expired or invalid. Forcing re-login on next cycle.")
                self.logged_in = False
                return

        except requests.exceptions.RequestException as e:
            logging.error(f"Network error fetching announcements: {e}")
            send_telegram_message(f"🔴 Network error fetching announcements:\n`{e}`", Config.TELEGRAM_CHAT_ID, parse_mode='Markdown')
            return

        soup = BeautifulSoup(page.text, 'html.parser')
        announcement_tags = soup.select('li.activity.modtype_label .activity-altcontent')

        if not announcement_tags:
            logging.warning("No announcement tags found on the page.")
            return

        new_items = []
        for tag in announcement_tags:
            parent_li = tag.find_parent('li', class_='activity')
            item_id = parent_li.get('id') if parent_li else None
            if item_id and item_id not in self.seen_ids:
                new_items.append(tag)
        
        if new_items:
            logging.info(f"Found {len(new_items)} new announcements!")
            # Send oldest new announcements first by iterating through the list normally
            for item_tag in new_items:
                parent_li = item_tag.find_parent('li', class_='activity')
                item_id = parent_li.get('id') if parent_li else None

                markdown_content = html_to_markdown_v2(item_tag)
                clean_content = re.sub(r'\n{3,}', '\n\n', markdown_content).strip()
                
                # Find links separately for the footer
                _, links = html_to_plain_text_and_links(item_tag)
                
                message = f"📣 *Nouvelle Affiche*\n================\n\n{clean_content}"
                if links:
                    message += "\n\n----------------\n🔗 *Liens:*\n" + "\n".join(f"• {link}" for link in links)

                if send_telegram_message(message, Config.TELEGRAM_CHAT_ID):
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
    if not all([Config.MOODLE_USERNAME, Config.MOODLE_PASSWORD, Config.TELEGRAM_BOT_TOKEN, Config.TELEGRAM_CHAT_ID, Config.USER_FULL_NAME]):
        startup_error = "🔴 BOT STARTUP FAILED: One or more essential environment variables are missing. Please check `USER_FULL_NAME` on the Railway dashboard."
        logging.critical(startup_error)
        send_telegram_message(startup_error, Config.TELEGRAM_CHAT_ID)
    else:
        logging.info("Script is starting up...")
        send_telegram_message("✅ Bot has started/restarted and is now monitoring.", Config.TELEGRAM_CHAT_ID)
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
                send_telegram_message(error_message, Config.TELEGRAM_CHAT_ID, parse_mode='Markdown')
                time.sleep(Config.ERROR_RETRY_DELAY)
