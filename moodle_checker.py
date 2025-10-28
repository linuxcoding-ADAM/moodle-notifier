# The Definitive, Bulletproof Moodle Scraper (Final Version)

import requests
import json
import time
import re
import os
import logging
import traceback
from bs4 import BeautifulSoup, NavigableString

# --- CONFIGURATION CLASS: All settings in one place ---
class Config:
    LOGIN_URL = 'https://elearning.univ-bejaia.dz/login/index.php'
    AFFICHAGE_URL = 'https://elearning.univ-bejaia.dz/course/view.php?id=19989'
    
    # Secrets read from the environment (Railway variables)
    MOODLE_USERNAME = os.getenv('MOODLE_USERNAME')
    MOODLE_PASSWORD = os.getenv('MOODLE_PASSWORD')
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
    USER_FULL_NAME = os.getenv('USER_FULL_NAME') # Your name as it appears on Moodle

    # File paths for persistent storage on Railway's volume
    SEEN_IDS_FILE = '/data/seen_ids.json'
    SEEN_IDS_FILE_TMP = '/data/seen_ids.json.tmp'

    # Timing settings (in seconds)
    CHECK_INTERVAL = 600  # 10 minutes
    STARTUP_DELAY = 10    # Wait 10s on startup for the volume to be ready
    ERROR_RETRY_DELAY = 300 # Wait 5 minutes after a major crash

# --- LOGGING SETUP ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# --- CORE UTILITY FUNCTIONS ---

def send_telegram_message(message, parse_mode='Markdown'):
    """
    Sends a message to your private Telegram chat.
    Intelligently falls back to plain text if Markdown parsing fails.
    """
    if not all([Config.TELEGRAM_BOT_TOKEN, Config.TELEGRAM_CHAT_ID]):
        logging.error("Telegram credentials are not set.")
        return False
        
    if len(message) > 4096:
        message = message[:4090] + "\n\n...(message truncated)"
    
    url = f"https://api.telegram.org/bot{Config.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {'chat_id': Config.TELEGRAM_CHAT_ID, 'text': message, 'parse_mode': parse_mode, 'disable_web_page_preview': True}
    
    try:
        response = requests.post(url, json=payload, timeout=30)
        if response.status_code == 200:
            logging.info(f"Successfully sent message.")
            return True
        else:
            logging.error(f"Failed to send message (mode: {parse_mode}): {response.text}")
            # If markdown parsing failed, retry automatically as plain text
            if "can't parse entities" in response.text and parse_mode:
                logging.warning("Markdown parsing failed. Retrying as plain text.")
                payload['parse_mode'] = None
                response_plain = requests.post(url, json=payload, timeout=30)
                if response_plain.status_code == 200:
                    logging.info("Successfully sent message as plain text.")
                    return True
            return False
    except Exception as e:
        logging.error(f"An exception occurred while sending Telegram message: {e}")
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

def html_to_markdown(tag):
    """Converts announcement HTML into a clean string with basic Markdown."""
    # This version is simpler and more robust, targeting the less strict 'Markdown' mode
    for br in tag.find_all("br"): br.replace_with("\n")
    for p in tag.find_all("p"): p.append("\n")
    for b in tag.find_all(['b', 'strong']): b.replace_with(f"*{b.get_text()}*")
    for i in tag.find_all(['i', 'em']): i.replace_with(f"_{i.get_text()}_")
    
    text = tag.get_text()
    lines = (line.strip() for line in text.splitlines())
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    return "\n".join(chunk for chunk in chunks if chunk)

def extract_links(tag):
    """Extracts all full hyperlinks from an HTML tag."""
    links = []
    for a in tag.find_all("a", href=True):
        href = a.get('href')
        if href:
            if not href.startswith('http'):
                href = 'https://elearning.univ-bejaia.dz' + href
            links.append(href)
    return links

# --- THE MAIN SCRAPER CLASS ---
class MoodleScraper:
    def __init__(self):
        self.session = requests.Session()
        self.seen_ids = get_seen_ids()
        self.logged_in = False

    def _login(self):
        """Performs a full login and verifies its success. Returns True on success."""
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

            # Paranoid login check
            if Config.USER_FULL_NAME and Config.USER_FULL_NAME.lower() in response.text.lower():
                logging.info("Login successful! User name confirmed.")
                self.logged_in = True
                return True
            else:
                logging.error("Login verification failed. User name not found on page.")
                send_telegram_message("🔴 *Login Verification Failed!*\nCould not find user name on the page. The bot will retry.", parse_mode='Markdown')
                self.logged_in = False
                return False
        except requests.exceptions.RequestException as e:
            logging.error(f"Network error during login: {e}")
            send_telegram_message(f"🔴 *Network error during login:*\n`{e}`", parse_mode='Markdown')
            self.logged_in = False
            return False
        except (TypeError, KeyError):
            logging.error("Failed to parse login page structure.")
            send_telegram_message("🔴 *Failed to parse Moodle login page.*\nThe page structure may have changed.", parse_mode='Markdown')
            self.logged_in = False
            return False

    def run_check(self):
        """Runs a single, complete check for new announcements."""
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
            logging.error(f"Network error fetching announcements: {e}")
            send_telegram_message(f"🔴 *Network error fetching announcements:*\n`{e}`", parse_mode='Markdown')
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
            for item_tag in new_items: # Send oldest new items first
                parent_li = item_tag.find_parent('li', class_='activity')
                item_id = parent_li.get('id') if parent_li else None

                content_text = html_to_markdown(item_tag)
                links = extract_links(item_tag)
                
                message = f"📣 *Nouvelle Affiche*\n================\n\n{content_text}"
                if links:
                    message += "\n\n----------------\n🔗 *Liens:*\n" + "\n".join(f"• {link}" for link in links)

                if send_telegram_message(message):
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
    required_vars = ['MOODLE_USERNAME', 'MOODLE_PASSWORD', 'TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID', 'USER_FULL_NAME']
    if not all(os.getenv(var) for var in required_vars):
        startup_error = "🔴 *BOT STARTUP FAILED:*\nOne or more essential environment variables are missing. Please check all 5 variables on the Railway dashboard."
        logging.critical(startup_error)
        send_telegram_message(startup_error, parse_mode='Markdown')
    else:
        logging.info("Script is starting up...")
        send_telegram_message("✅ *Bot has started/restarted* and is now monitoring.", parse_mode='Markdown')
        time.sleep(Config.STARTUP_DELAY)
        
        scraper = MoodleScraper()
        
        while True:
            try:
                scraper.run_check()
                logging.info(f"Check complete. Waiting for {Config.CHECK_INTERVAL // 60} minutes...")
                time.sleep(Config.CHECK_INTERVAL)
            except Exception as e:
                error_details = traceback.format_exc()
                error_message = f"🔴 *BOT CRITICAL ERROR:*\nThe main loop has crashed unexpectedly.\n\n*Error:*\n`{e}`\n\n*Traceback:*\n```{error_details}```\n\nThe bot will restart its loop in {Config.ERROR_RETRY_DELAY // 60} minutes."
                logging.critical(error_message)
                send_telegram_message(error_message, parse_mode='Markdown')
                time.sleep(Config.ERROR_RETRY_DELAY)
