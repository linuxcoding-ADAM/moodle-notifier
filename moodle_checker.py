# The Definitive, Bulletproof Moodle Scraper (Final Version, Final Formatting Fix, v2 - With Reliability Fixes)

import requests
import json
import time
import re
import os
import logging
import traceback
import hashlib # --- CHANGE: Import hashlib for content-based IDs
from bs4 import BeautifulSoup, NavigableString, Tag

# --- CONFIGURATION CLASS: All settings in one place ---
class Config:
    """Holds all configuration variables for the scraper."""
    LOGIN_URL = 'https://elearning.univ-bejaia.dz/login/index.php'
    AFFICHAGE_URL = 'https://elearning.univ-bejaia.dz/course/view.php?id=19989'
    
    MOODLE_USERNAME = os.getenv('MOODLE_USERNAME')
    MOODLE_PASSWORD = os.getenv('MOODLE_PASSWORD')
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
    USER_FULL_NAME = os.getenv('USER_FULL_NAME')

    SEEN_IDS_FILE = '/data/seen_hashes.json' # --- CHANGE: Renamed file to reflect content
    SEEN_IDS_FILE_TMP = '/data/seen_hashes.json.tmp'

    CHECK_INTERVAL = 600
    STARTUP_DELAY = 10
    ERROR_RETRY_DELAY = 300
    
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache'
    }

# --- LOGGING SETUP ---
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# --- TELEGRAM NOTIFICATION FUNCTION (No changes needed here) ---
def send_telegram_message(message_text, parse_mode='Markdown'):
    if not all([Config.TELEGRAM_BOT_TOKEN, Config.TELEGRAM_CHAT_ID]):
        logging.error("Telegram credentials are not set. Cannot send message.")
        return False
    
    if len(message_text) > 4096:
        logging.warning("Message is too long. Truncating.")
        message_text = message_text[:4090] + "\n\n...(message truncated)"
    
    url = f"https://api.telegram.org/bot{Config.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': Config.TELEGRAM_CHAT_ID,
        'text': message_text,
        'parse_mode': parse_mode,
        'disable_web_page_preview': True
    }
    
    if payload.get('parse_mode') is None:
        del payload['parse_mode']

    try:
        response = requests.post(url, json=payload, timeout=30)
        
        if response.status_code == 200:
            current_mode = parse_mode if 'parse_mode' in payload else 'Plain Text'
            logging.info(f"Successfully sent message (mode: {current_mode}).")
            return True
        
        response_json = response.json()
        if (response.status_code == 400 and 
            'can\'t parse entities' in response_json.get('description', '') and 
            parse_mode):
            
            logging.warning("Markdown parsing failed. Retrying as plain text.")
            return send_telegram_message(message_text, parse_mode=None)
        
        logging.error(f"Failed to send message. Status: {response.status_code}, Response: {response.text}")
        return False
            
    except requests.exceptions.RequestException as e:
        logging.error(f"An exception occurred while sending Telegram message: {e}")
        return False

# --- DATA PERSISTENCE FUNCTIONS ---
def get_seen_ids():
    try:
        with open(Config.SEEN_IDS_FILE, 'r') as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        logging.info(f"{Config.SEEN_IDS_FILE} not found or invalid. Starting with an empty set.")
        return set()

def save_seen_ids(ids):
    try:
        os.makedirs(os.path.dirname(Config.SEEN_IDS_FILE), exist_ok=True)
        with open(Config.SEEN_IDS_FILE_TMP, 'w') as f:
            json.dump(list(ids), f, indent=2)
        os.rename(Config.SEEN_IDS_FILE_TMP, Config.SEEN_IDS_FILE)
    except Exception as e:
        logging.critical(f"FATAL: Could not save seen_ids file! Error: {e}")

# --- HTML CONVERSION AND FORMATTING (No changes needed here) ---
def html_to_markdown(tag):
    text_parts = []
    for child in tag.children:
        if isinstance(child, NavigableString):
            text_parts.append(child.string)
        elif isinstance(child, Tag):
            child_text = html_to_markdown(child)
            
            if child.name in ['b', 'strong']:
                text_parts.append(f"*{child_text}*")
            elif child.name in ['i', 'em']:
                text_parts.append(f"_{child_text}_")
            elif child.name == 'a':
                text_parts.append(child_text)
            elif child.name in ['p', 'div', 'li', 'br']:
                text_parts.append(f"\n{child_text}\n")
            else:
                text_parts.append(child_text)

    full_text = "".join(text_parts)
    return re.sub(r'\n\s*\n', '\n\n', full_text).strip()

def extract_links(tag):
    links = []
    for a in tag.find_all("a", href=True):
        href = a.get('href')
        if href and href.strip() not in ['#', '']:
            if not href.startswith('http'):
                base_url = 'https://elearning.univ-bejaia.dz'
                href = f"{base_url}{href}" if href.startswith('/') else f"{base_url}/{href}"
            links.append(href)
    return links

def format_announcement_text(text):
    pattern = r'(?s)\*(.*?):\*\s*(.*?)(?=\s*\*.*?\*:|\Z)'
    matches = re.findall(pattern, text)
    if not matches:
        return text
    formatted_parts = []
    for label, value in matches:
        clean_label = label.strip()
        clean_value = value.strip()
        formatted_parts.append(f"*{clean_label} :*\n{clean_value}")
    return "\n\n".join(formatted_parts)
    
# --- CHANGE: NEW FUNCTION TO CREATE RELIABLE, CONTENT-BASED IDs ---
def generate_content_hash(tag):
    """Creates a stable SHA256 hash from the content of an announcement tag."""
    # Normalize content to ensure the hash is consistent
    text_content = tag.get_text(" ", strip=True) 
    links = sorted(extract_links(tag)) # Sort links to ensure consistent order
    
    # Combine text and links into a single string
    stable_representation = text_content + "||".join(links)
    
    # Create and return the hash
    return hashlib.sha256(stable_representation.encode('utf-8')).hexdigest()

# --- CORE SCRAPER CLASS ---
class MoodleScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(Config.HEADERS)
        self.seen_ids = get_seen_ids()
        self.logged_in = False

    def _login(self):
        logging.info("Attempting a fresh login...")
        self.session = requests.Session()
        self.session.headers.update(Config.HEADERS)
        self.logged_in = False
        
        try:
            login_page_res = self.session.get(Config.LOGIN_URL, timeout=30)
            login_page_res.raise_for_status()
            
            soup = BeautifulSoup(login_page_res.text, 'html.parser')
            logintoken_input = soup.find('input', {'name': 'logintoken'})
            if not logintoken_input:
                logging.error("Could not find 'logintoken' field.")
                send_telegram_message("🔴 *Login Error*\nCould not find login token.", parse_mode='Markdown')
                return False
            logintoken = logintoken_input['value']

            payload = {
                'username': Config.MOODLE_USERNAME,
                'password': Config.MOODLE_PASSWORD,
                'logintoken': logintoken
            }
            response = self.session.post(Config.LOGIN_URL, data=payload, timeout=30)
            response.raise_for_status()

            if Config.USER_FULL_NAME and Config.USER_FULL_NAME.lower() in response.text.lower():
                logging.info("Login successful! User name confirmed.")
                self.logged_in = True
                return True
            else:
                logging.error("Login verification failed. User's name not found.")
                send_telegram_message("🔴 *Login Verification Failed!*\nCould not verify login.", parse_mode='Markdown')
                return False
                
        except requests.exceptions.RequestException as e:
            logging.error(f"Network error during login: {e}")
            send_telegram_message(f"🔴 *Network Error During Login*\n`{e}`", parse_mode='Markdown')
            return False
        except (KeyError, AttributeError) as e:
            logging.error(f"Failed to parse login page. Error: {e}")
            send_telegram_message("🔴 *Parsing Error*\nFailed to parse Moodle login page.", parse_mode='Markdown')
            return False

    def run_check(self):
        logging.info("--- Starting new check cycle ---")
        
        if not self.logged_in:
            if not self._login():
                logging.error("Aborting check due to login failure.")
                return

        try:
            page = self.session.get(Config.AFFICHAGE_URL, timeout=30)
            page.raise_for_status()
            
            # --- CHANGE: STRONGER SESSION VALIDATION ---
            # Don't just check for a redirect, actively confirm we are logged in.
            if "login/index.php" in page.url or (Config.USER_FULL_NAME and Config.USER_FULL_NAME.lower() not in page.text.lower()):
                logging.warning("Session appears to be expired. Forcing re-login on the next cycle.")
                self.logged_in = False
                return

        except requests.exceptions.RequestException as e:
            logging.error(f"Network error fetching announcements: {e}")
            return

        soup = BeautifulSoup(page.text, 'html.parser')
        # --- CHANGE: More general selector to be less fragile ---
        # This looks for any list item with 'activity' and 'modtype_label' classes, then finds the content within.
        announcement_tags = soup.select('li.activity.modtype_label .activity-altcontent')
        
        if not announcement_tags:
            logging.warning("Could not find any announcement tags on the page.")
            return

        new_items = []
        for tag in announcement_tags:
            # --- CHANGE: Use the new content hash as the ID ---
            item_id = generate_content_hash(tag)
            
            if item_id and item_id not in self.seen_ids:
                new_items.append({'id': item_id, 'tag': tag})
        
        if new_items:
            logging.info(f"Found {len(new_items)} new announcement(s)!")
            
            for item in reversed(new_items): # Process oldest first
                item_id, item_tag = item['id'], item['tag']
                
                raw_text = html_to_markdown(item_tag)
                content_text = format_announcement_text(raw_text)
                links = extract_links(item_tag)
                
                message = f"📣 *Nouvelle Affiche*\n================\n\n{content_text}"
                
                if links:
                    unique_links = sorted(list(set(links)))
                    message += "\n\n----------------\n🔗 *Liens:*\n" + "\n".join(f"• {link}" for link in unique_links)
                
                # We show the first 12 chars of the hash as a debug ID
                message += f"\n\n------------\nid : `{item_id[:12]}`"

                if send_telegram_message(message):
                    self.seen_ids.add(item_id)
                    save_seen_ids(self.seen_ids) # Save after every successful send
                    logging.info(f"Successfully processed and saved hash: {item_id[:12]}")
                else:
                    logging.warning(f"Failed to send notification for hash {item_id[:12]}. It will be retried next cycle.")
                
                time.sleep(2) # Prevent rate-limiting
        else:
            logging.info("No new announcements found.")

# --- MAIN EXECUTION BLOCK (No changes needed here) ---
if __name__ == "__main__":
    required_vars = ['MOODLE_USERNAME', 'MOODLE_PASSWORD', 'TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID', 'USER_FULL_NAME']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        error_msg = f"🔴 BOT STARTUP FAILED: Missing variables: {', '.join(missing_vars)}"
        logging.critical(error_msg)
        if all([os.getenv('TELEGRAM_BOT_TOKEN'), os.getenv('TELEGRAM_CHAT_ID')]):
            send_telegram_message(error_msg, parse_mode='Markdown')
    else:
        logging.info("Script is starting up with all required configurations.")
        send_telegram_message("✅ *Bot started/restarted* and is now monitoring.", parse_mode='Markdown')
        time.sleep(Config.STARTUP_DELAY)
        
        scraper = MoodleScraper()
        
        while True:
            try:
                scraper.run_check()
                logging.info(f"Check complete. Waiting for {Config.CHECK_INTERVAL // 60} minutes...")
                time.sleep(Config.CHECK_INTERVAL)
            except Exception as e:
                error_details = traceback.format_exc()
                error_message = (f"🔴 *BOT CRITICAL ERROR*\n"
                                 f"The main loop crashed.\n\n"
                                 f"*Error:*\n`{e}`\n\n"
                                 f"*Traceback:*\n```{error_details}```\n\n"
                                 f"Restarting in {Config.ERROR_RETRY_DELAY // 60} minutes.")
                logging.critical(f"Unexpected error in main loop: {e}", exc_info=True)
                send_telegram_message(error_message, parse_mode='Markdown')
                time.sleep(Config.ERROR_RETRY_DELAY)
