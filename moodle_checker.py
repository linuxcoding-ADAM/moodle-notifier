# The Definitive, Bulletproof Moodle Scraper (Final Version, Revised for Reliability)

import requests
import json
import time
import re
import os
import logging
import traceback
from bs4 import BeautifulSoup, NavigableString, Tag

# --- CONFIGURATION CLASS: All settings in one place ---
class Config:
    """Holds all configuration variables for the scraper."""
    LOGIN_URL = 'https://elearning.univ-bejaia.dz/login/index.php'
    AFFICHAGE_URL = 'https://elearning.univ-bejaia.dz/course/view.php?id=19989'
    
    # Environment variables are fetched once at startup for efficiency and clarity.
    MOODLE_USERNAME = os.getenv('MOODLE_USERNAME')
    MOODLE_PASSWORD = os.getenv('MOODLE_PASSWORD')
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
    USER_FULL_NAME = os.getenv('USER_FULL_NAME')

    # Data persistence file paths. Using /data/ is common in containerized environments like Railway.
    SEEN_IDS_FILE = '/data/seen_ids.json'
    SEEN_IDS_FILE_TMP = '/data/seen_ids.json.tmp' # Temporary file for atomic saves

    # Timing settings
    CHECK_INTERVAL = 600  # 10 minutes
    STARTUP_DELAY = 10    # A small delay to allow network to be ready on startup
    ERROR_RETRY_DELAY = 300 # 5 minutes

# --- LOGGING SETUP ---
# A clear and consistent logging format helps in debugging.
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# --- TELEGRAM NOTIFICATION FUNCTION ---
def send_telegram_message(message_text, parse_mode='Markdown'):
    """
    Sends a message to the configured Telegram chat.
    Automatically falls back to plain text if Markdown parsing fails.
    """
    if not all([Config.TELEGRAM_BOT_TOKEN, Config.TELEGRAM_CHAT_ID]):
        logging.error("Telegram credentials (BOT_TOKEN or CHAT_ID) are not set. Cannot send message.")
        return False
    
    # Telegram has a message size limit of 4096 characters.
    if len(message_text) > 4096:
        logging.warning("Message is too long. Truncating to 4096 characters.")
        message_text = message_text[:4090] + "\n\n...(message truncated)"
    
    url = f"https://api.telegram.org/bot{Config.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': Config.TELEGRAM_CHAT_ID,
        'text': message_text,
        'parse_mode': parse_mode,
        'disable_web_page_preview': True
    }
    
    try:
        response = requests.post(url, json=payload, timeout=30)
        if response.status_code == 200:
            logging.info(f"Successfully sent message (mode: {parse_mode or 'Plain Text'}).")
            return True
        
        # If Markdown parsing fails, try again with plain text.
        response_json = response.json()
        if (response.status_code == 400 and 
            'can\'t parse entities' in response_json.get('description', '') and 
            parse_mode):
            
            logging.warning("Markdown parsing failed. Retrying as plain text.")
            payload['parse_mode'] = None
            response_plain = requests.post(url, json=payload, timeout=30)
            
            if response_plain.status_code == 200:
                logging.info("Successfully sent message as plain text after Markdown failure.")
                return True
            else:
                logging.error(f"Failed to send message as plain text. Status: {response_plain.status_code}, Response: {response_plain.text}")
                return False
        else:
            logging.error(f"Failed to send message. Status: {response.status_code}, Response: {response.text}")
            return False
            
    except requests.exceptions.RequestException as e:
        logging.error(f"An exception occurred while sending Telegram message: {e}")
        return False

# --- DATA PERSISTENCE FUNCTIONS ---
def get_seen_ids():
    """Loads the set of seen announcement IDs from a JSON file."""
    try:
        with open(Config.SEEN_IDS_FILE, 'r') as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        logging.info("seen_ids.json not found or invalid. Starting with an empty set.")
        return set()

def save_seen_ids(ids):
    """
    Saves the set of seen IDs to a JSON file atomically.
    This prevents data corruption if the script crashes during a write.
    """
    try:
        os.makedirs(os.path.dirname(Config.SEEN_IDS_FILE), exist_ok=True)
        with open(Config.SEEN_IDS_FILE_TMP, 'w') as f:
            json.dump(list(ids), f, indent=2)
        os.rename(Config.SEEN_IDS_FILE_TMP, Config.SEEN_IDS_FILE)
    except Exception as e:
        logging.critical(f"FATAL: Could not save seen_ids.json! Error: {e}")

# --- HTML TO MARKDOWN CONVERSION ---
def escape_markdown(text):
    """Escapes special characters for Telegram Markdown V2."""
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)

def html_to_markdown(tag):
    """
    A more robust HTML to Markdown converter that handles nested tags
    and escapes special characters properly.
    """
    text = ''
    # Use .children to iterate through direct children, including text nodes
    for child in tag.children:
        if isinstance(child, NavigableString):
            # If it's just a string, append its text.
            text += child.string
        elif isinstance(child, Tag):
            # If it's a tag, process it based on its name.
            child_text = html_to_markdown(child) # Recursive call
            
            if child.name in ['b', 'strong']:
                text += f"*{child_text}*"
            elif child.name in ['i', 'em']:
                text += f"_{child_text}_"
            elif child.name == 'a':
                # For links, we will handle them separately. Just get the text for now.
                text += child_text
            elif child.name == 'br':
                text += '\n'
            elif child.name == 'p':
                text += f"\n{child_text}\n"
            else:
                # For any other tags, just get their text content.
                text += child_text
                
    # Clean up excessive newlines and whitespace
    text = re.sub(r'\n\s*\n', '\n\n', text).strip()
    return text

def extract_links(tag):
    """Extracts all hyperlinks from a BeautifulSoup tag."""
    links = []
    for a in tag.find_all("a", href=True):
        href = a.get('href')
        if href and href.strip() != '#':
            # Ensure the link is absolute
            if not href.startswith('http'):
                base_url = 'https://elearning.univ-bejaia.dz'
                if href.startswith('/'):
                    href = base_url + href
                else:
                    href = f"{base_url}/{href}"
            links.append(href)
    return links

# --- CORE SCRAPER CLASS ---
class MoodleScraper:
    def __init__(self):
        self.session = requests.Session()
        self.seen_ids = get_seen_ids()
        self.logged_in = False

    def _login(self):
        """Establishes a new session and logs into Moodle."""
        logging.info("Attempting a fresh login...")
        # Start with a new session to ensure no old cookies interfere
        self.session = requests.Session()
        self.logged_in = False
        
        try:
            # 1. Get the login page to retrieve the logintoken
            login_page_res = self.session.get(Config.LOGIN_URL, timeout=30)
            login_page_res.raise_for_status()
            
            soup = BeautifulSoup(login_page_res.text, 'html.parser')
            logintoken_input = soup.find('input', {'name': 'logintoken'})
            if not logintoken_input:
                logging.error("Could not find the 'logintoken' field on the login page. The page structure may have changed.")
                send_telegram_message("🔴 *Login Error*\nCould not find the login token on the Moodle page. The scraper might need an update.", parse_mode='Markdown')
                return False
            logintoken = logintoken_input['value']

            # 2. Send the POST request with credentials
            payload = {
                'username': Config.MOODLE_USERNAME,
                'password': Config.MOODLE_PASSWORD,
                'logintoken': logintoken
            }
            response = self.session.post(Config.LOGIN_URL, data=payload, timeout=30)
            response.raise_for_status()

            # 3. Verify successful login by checking for the user's name
            if Config.USER_FULL_NAME and Config.USER_FULL_NAME.lower() in response.text.lower():
                logging.info("Login successful! User name confirmed on the page.")
                self.logged_in = True
                return True
            else:
                logging.error("Login verification failed. The user's full name was not found on the page after login.")
                send_telegram_message("🔴 *Login Verification Failed!*\nCould not find the user's name on the page after attempting to log in.", parse_mode='Markdown')
                return False
                
        except requests.exceptions.RequestException as e:
            logging.error(f"A network error occurred during login: {e}")
            send_telegram_message(f"🔴 *Network Error During Login*\n`{e}`", parse_mode='Markdown')
            return False
        except (KeyError, AttributeError) as e:
            logging.error(f"Failed to parse the Moodle login page structure. Error: {e}")
            send_telegram_message("🔴 *Parsing Error*\nFailed to parse the Moodle login page. The website structure may have changed.", parse_mode='Markdown')
            return False

    def run_check(self):
        """The main logic for checking for new announcements."""
        logging.info("--- Starting new check cycle ---")
        
        if not self.logged_in:
            if not self._login():
                logging.error("Aborting check due to login failure.")
                return

        try:
            # Fetch the announcements page
            page = self.session.get(Config.AFFICHAGE_URL, timeout=30)
            page.raise_for_status()
            
            # Check if the session has expired and we were redirected to the login page
            if "login/index.php" in page.url:
                logging.warning("Session appears to have expired. Forcing re-login on the next cycle.")
                self.logged_in = False
                return

        except requests.exceptions.RequestException as e:
            logging.error(f"Network error while fetching announcements: {e}")
            # We don't send a telegram message here to avoid spam on temporary network issues.
            # The script will retry automatically.
            return

        soup = BeautifulSoup(page.text, 'html.parser')
        # This selector is specific to finding the announcement content.
        announcement_tags = soup.select('li.activity.modtype_label .activity-altcontent')
        
        if not announcement_tags:
            logging.warning("Could not find any announcement tags on the page. The selector might be outdated or the page is empty.")
            return

        new_items = []
        for tag in announcement_tags:
            parent_li = tag.find_parent('li', class_='activity')
            item_id = parent_li.get('id') if parent_li else None
            
            if item_id and item_id not in self.seen_ids:
                new_items.append({'id': item_id, 'tag': tag})
        
        if new_items:
            logging.info(f"Found {len(new_items)} new announcement(s)!")
            
            # By reversing the list, we process the OLDEST of the new items first,
            # ensuring they appear in chronological order in the Telegram chat.
            for item in reversed(new_items):
                item_id = item['id']
                item_tag = item['tag']
                
                content_text = html_to_markdown(item_tag)
                links = extract_links(item_tag)
                
                message = f"📣 *Nouvelle Affiche*\n================\n\n{content_text}"
                
                if links:
                    message += "\n\n----------------\n🔗 *Liens:*\n" + "\n".join(f"• {link}" for link in links)
                
                # The send_telegram_message function now handles the fallback internally.
                if send_telegram_message(message):
                    self.seen_ids.add(item_id)
                    save_seen_ids(self.seen_ids)
                    logging.info(f"Successfully processed and saved ID: {item_id}")
                else:
                    logging.warning(f"Failed to send notification for {item_id}, even after retrying as plain text. It will be attempted again in the next cycle.")
                
                time.sleep(2) # A small delay between messages to avoid rate limiting.
        else:
            logging.info("No new announcements found.")

# --- MAIN EXECUTION BLOCK ---
if __name__ == "__main__":
    # Check for all required environment variables at startup.
    required_vars = ['MOODLE_USERNAME', 'MOODLE_PASSWORD', 'TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID', 'USER_FULL_NAME']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        error_msg = f"🔴 BOT STARTUP FAILED: The following essential environment variables are missing: {', '.join(missing_vars)}"
        logging.critical(error_msg)
        # Try to send a message to Telegram if credentials are partially available
        if all([os.getenv('TELEGRAM_BOT_TOKEN'), os.getenv('TELEGRAM_CHAT_ID')]):
            send_telegram_message(error_msg, parse_mode='Markdown')
    else:
        logging.info("Script is starting up with all required configurations.")
        send_telegram_message("✅ *Bot has started/restarted* and is now monitoring for new announcements.", parse_mode='Markdown')
        time.sleep(Config.STARTUP_DELAY)
        
        scraper = MoodleScraper()
        
        while True:
            try:
                scraper.run_check()
                logging.info(f"Check complete. Waiting for {Config.CHECK_INTERVAL // 60} minutes until the next check...")
                time.sleep(Config.CHECK_INTERVAL)
            except Exception as e:
                # This is a catch-all for any other unexpected errors in the main loop.
                error_details = traceback.format_exc()
                error_message = (f"🔴 *BOT CRITICAL ERROR*\n"
                                 f"The main loop has crashed unexpectedly.\n\n"
                                 f"*Error:*\n`{e}`\n\n"
                                 f"*Traceback:*\n```{error_details}```\n\n"
                                 f"The bot will attempt to restart in {Config.ERROR_RETRY_DELAY // 60} minutes.")
                logging.critical(f"An unexpected error occurred in the main loop: {e}", exc_info=True)
                send_telegram_message(error_message, parse_mode='Markdown')
                time.sleep(Config.ERROR_RETRY_DELAY)
