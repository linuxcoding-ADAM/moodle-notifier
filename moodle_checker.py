# The Definitive, Bulletproof Moodle Scraper (FINAL VERSION - API Based)

import requests
import json
import time
import re
import os
import logging
import traceback
from bs4 import BeautifulSoup, NavigableString, Tag

# --- CONFIGURATION CLASS ---
class Config:
    BASE_URL = 'https://elearning.univ-bejaia.dz'
    LOGIN_URL = f'{BASE_URL}/login/index.php'
    # This is the Moodle Web Service API endpoint
    API_URL = f'{BASE_URL}/webservice/rest/server.php'
    # The ID of the course page we want to check
    COURSE_ID = 19989 
    
    MOODLE_USERNAME = os.getenv('MOODLE_USERNAME')
    MOODLE_PASSWORD = os.getenv('MOODLE_PASSWORD')
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
    USER_FULL_NAME = os.getenv('USER_FULL_NAME')

    SEEN_IDS_FILE = '/data/seen_ids.json'
    SEEN_IDS_FILE_TMP = '/data/seen_ids.json.tmp'

    CHECK_INTERVAL = 600
    STARTUP_DELAY = 10
    ERROR_RETRY_DELAY = 300

# --- LOGGING SETUP ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- UNCHANGED HELPER FUNCTIONS ---
def send_telegram_message(message_text, parse_mode='Markdown'):
    if not all([Config.TELEGRAM_BOT_TOKEN, Config.TELEGRAM_CHAT_ID]): return False
    if len(message_text) > 4096: message_text = message_text[:4090] + "\n\n...(truncated)"
    url = f"https://api.telegram.org/bot{Config.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {'chat_id': Config.TELEGRAM_CHAT_ID, 'text': message_text, 'parse_mode': parse_mode, 'disable_web_page_preview': True}
    if payload.get('parse_mode') is None: del payload['parse_mode']
    try:
        response = requests.post(url, json=payload, timeout=30)
        if response.status_code == 200:
            logging.info(f"Successfully sent message (mode: {payload.get('parse_mode', 'Plain Text')}).")
            return True
        if response.status_code == 400 and 'can\'t parse entities' in response.json().get('description', '') and parse_mode:
            logging.warning("Markdown parsing failed. Retrying as plain text.")
            return send_telegram_message(message_text, parse_mode=None)
        logging.error(f"Failed to send message: {response.text}")
        return False
    except requests.exceptions.RequestException as e:
        logging.error(f"Exception in send_telegram_message: {e}")
        return False
def get_seen_ids():
    try:
        with open(Config.SEEN_IDS_FILE, 'r') as f: return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        logging.info("seen_ids.json not found or invalid. Starting with an empty set.")
        return set()
def save_seen_ids(ids):
    try:
        os.makedirs(os.path.dirname(Config.SEEN_IDS_FILE), exist_ok=True)
        with open(Config.SEEN_IDS_FILE_TMP, 'w') as f: json.dump(list(ids), f, indent=2)
        os.rename(Config.SEEN_IDS_FILE_TMP, Config.SEEN_IDS_FILE)
    except Exception as e: logging.critical(f"FATAL: Could not save seen_ids.json! Error: {e}")
def html_to_markdown(html_content):
    if not html_content: return ""
    soup = BeautifulSoup(html_content, 'html.parser')
    text_parts = []
    for element in soup.recursiveChildGenerator():
        if isinstance(element, NavigableString):
            text_parts.append(element.string)
        elif isinstance(element, Tag):
            if element.name in ['b', 'strong']:
                text_parts.append(f"*{element.get_text()}*")
            elif element.name in ['i', 'em']:
                text_parts.append(f"_{element.get_text()}_")
            elif element.name in ['p', 'div', 'br']:
                text_parts.append("\n")
    full_text = "".join(text_parts)
    return re.sub(r'\n\s*\n', '\n\n', full_text).strip()
def format_announcement_text(text):
    pattern = r'(?s)\*(.*?):\*\s*(.*?)(?=\s*\*.*?\*:|\Z)'
    matches = re.findall(pattern, text)
    if not matches: return text
    return "\n\n".join([f"*{label.strip()} :*\n{value.strip()}" for label, value in matches])

# --- CORE SCRAPER CLASS (API BASED) ---
class MoodleScraper:
    def __init__(self):
        self.session = requests.Session()
        self.seen_ids = get_seen_ids()
        self.api_token = None

    def _login_and_get_token(self):
        """Logs in via the web page to get a session, then uses the session to get an API token."""
        logging.info("Attempting login to get session cookie...")
        try:
            # Step 1: Get the logintoken from the login page
            login_page = self.session.get(Config.LOGIN_URL, timeout=30)
            login_page.raise_for_status()
            soup = BeautifulSoup(login_page.text, 'html.parser')
            logintoken = soup.find('input', {'name': 'logintoken'})['value']

            # Step 2: Perform the login to establish a session
            payload = {'username': Config.MOODLE_USERNAME, 'password': Config.MOODLE_PASSWORD, 'logintoken': logintoken}
            response = self.session.post(Config.LOGIN_URL, data=payload, timeout=30)
            response.raise_for_status()
            if Config.USER_FULL_NAME.lower() not in response.text.lower():
                logging.error("Login verification failed. User name not found on page.")
                return False
            
            logging.info("Login successful. Session established.")
            
            # Step 3: Extract the sesskey from the page, which is needed for the API token call
            sesskey_match = re.search(r'"sesskey":"(.*?)"', response.text)
            if not sesskey_match:
                logging.error("Could not find sesskey on the page after login.")
                return False
            sesskey = sesskey_match.group(1)
            
            # Step 4: Use the session and sesskey to request an API token
            api_token_payload = {
                'sesskey': sesskey,
                'info': 'core_course_get_contents'
            }
            # This is a special endpoint that generates tokens for the mobile API
            token_response = self.session.post(f"{Config.BASE_URL}/lib/ajax/service.php", json=[{"index":0, "methodname":"core_course_get_contents", "args":api_token_payload}])
            token_response.raise_for_status()
            
            # Moodle AJAX API is weird, it returns an array of responses. We expect one.
            self.api_token = self.session.cookies.get('MoodleSession')
            if not self.api_token:
                 logging.error("Failed to get API token after login.")
                 return False

            logging.info("Successfully obtained API token.")
            return True
            
        except Exception as e:
            logging.error(f"An error occurred during login/token fetch: {e}", exc_info=True)
            return False

    def run_check(self):
        logging.info("--- Starting new check cycle ---")
        if not self.api_token:
            if not self._login_and_get_token():
                logging.error("Aborting check due to login/token failure.")
                return

        try:
            # Use the API to get course contents directly
            params = {
                'wstoken': self.api_token,
                'wsfunction': 'core_course_get_contents',
                'moodlewsrestformat': 'json',
                'courseid': Config.COURSE_ID
            }
            response = self.session.get(Config.API_URL, params=params, timeout=30)
            response.raise_for_status()
            course_data = response.json()

            if isinstance(course_data, dict) and course_data.get("exception"):
                logging.error(f"API returned an error: {course_data.get('message')}")
                if course_data.get('errorcode') == 'invalidtoken':
                    logging.warning("API token is invalid. Forcing re-login on next cycle.")
                    self.api_token = None
                return

            new_items = []
            for section in course_data:
                for module in section.get('modules', []):
                    # Announcements are usually of type 'label'
                    if module.get('modname') == 'label' and 'id' in module:
                        item_id = module['id']
                        if item_id not in self.seen_ids:
                            new_items.append(module)

            if new_items:
                logging.info(f"Found {len(new_items)} new announcement(s) via API!")
                # The API returns items in chronological order, so we don't need to reverse
                for item in new_items:
                    item_id = item['id']
                    content_text = ""
                    if 'description' in item:
                        content_text = format_announcement_text(html_to_markdown(item['description']))
                    
                    message = f"📣 *Nouvelle Affiche*\n================\n\n{content_text}"
                    message += f"\n\n------------\nid : `{item_id}`"

                    if send_telegram_message(message):
                        self.seen_ids.add(item_id)
                        save_seen_ids(self.seen_ids)
                        logging.info(f"Successfully processed and saved ID: {item_id}")
                    else:
                        logging.warning(f"Failed to send notification for {item_id}. It will be retried.")
                    time.sleep(2)
            else:
                logging.info("No new announcements found via API.")

        except requests.exceptions.RequestException as e:
            logging.error(f"Network error during API check: {e}")
        except json.JSONDecodeError:
            logging.error("Failed to decode JSON response from API.")
        except Exception as e:
            logging.critical(f"An unexpected error occurred in run_check: {e}", exc_info=True)

# --- MAIN EXECUTION BLOCK ---
if __name__ == "__main__":
    if not all(os.getenv(var) for var in ['MOODLE_USERNAME', 'MOODLE_PASSWORD', 'TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID', 'USER_FULL_NAME']):
        logging.critical("BOT STARTUP FAILED: Missing environment variables.")
    else:
        logging.info("Script is starting up.")
        send_telegram_message("✅ *Bot started/restarted* and is now monitoring.", parse_mode='Markdown')
        time.sleep(Config.STARTUP_DELAY)
        scraper = MoodleScraper()
        while True:
            try:
                scraper.run_check()
                logging.info(f"Check complete. Waiting {Config.CHECK_INTERVAL // 60} minutes...")
                time.sleep(Config.CHECK_INTERVAL)
            except Exception as e:
                error_details = traceback.format_exc()
                error_message = f"🔴 *BOT CRITICAL ERROR*\nCrashed with:\n`{e}`\n```{error_details}```\nRestarting in {Config.ERROR_RETRY_DELAY // 60} minutes."
                logging.critical(f"Unexpected error in main loop: {e}", exc_info=True)
                send_telegram_message(error_message, parse_mode='Markdown')
                time.sleep(Config.ERROR_RETRY_DELAY)
