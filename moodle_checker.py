# The Definitive, Bulletproof Moodle Scraper (FINAL VERSION - Correct API Authentication)

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
    TOKEN_URL = f'{BASE_URL}/login/token.php'  # <-- URL to get the real token
    API_URL = f'{BASE_URL}/webservice/rest/server.php'
    COURSE_ID = 19989
    
    MOODLE_USERNAME = os.getenv('MOODLE_USERNAME')
    MOODLE_PASSWORD = os.getenv('MOODLE_PASSWORD')
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

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
    text = soup.get_text(separator='\n', strip=True)
    text = re.sub(r'\n\s*\n', '\n\n', text)
    return text
def format_announcement_text(text):
    # This simplified version should be more robust
    return text

# --- CORE SCRAPER CLASS (CORRECT API AUTH) ---
class MoodleScraper:
    def __init__(self):
        self.session = requests.Session()
        self.seen_ids = get_seen_ids()
        self.api_token = None

    def _get_api_token(self):
        """Gets a proper Moodle Web Service API token."""
        logging.info("Attempting to get Moodle API token...")
        try:
            params = {
                'username': Config.MOODLE_USERNAME,
                'password': Config.MOODLE_PASSWORD,
                'service': 'moodle_mobile_app'  # Standard service for the official app
            }
            response = self.session.post(Config.TOKEN_URL, data=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            if 'token' in data:
                self.api_token = data['token']
                logging.info("Successfully obtained Moodle API token.")
                return True
            elif 'error' in data:
                logging.error(f"Failed to get API token. Moodle error: {data['error']}")
                return False

        except requests.exceptions.RequestException as e:
            logging.error(f"Network error while getting API token: {e}")
        except json.JSONDecodeError:
            logging.error("Failed to decode JSON response when getting API token.")
        except Exception as e:
            logging.critical(f"An unexpected error occurred in _get_api_token: {e}", exc_info=True)
        
        return False

    def run_check(self):
        logging.info("--- Starting new check cycle ---")
        if not self.api_token:
            if not self._get_api_token():
                logging.error("Aborting check due to token failure.")
                return

        try:
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
                    if module.get('modname') == 'label' and 'id' in module:
                        item_id = module['id']
                        if item_id not in self.seen_ids:
                            new_items.append(module)

            if new_items:
                logging.info(f"Found {len(new_items)} new announcement(s) via API!")
                for item in new_items:
                    item_id = item['id']
                    content_text = ""
                    if 'description' in item:
                        content_text = html_to_markdown(item['description'])
                    
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
            if e.response and e.response.status_code == 403:
                logging.warning("Got a 403 Forbidden error. The token may be invalid. Forcing re-login.")
                self.api_token = None
        except json.JSONDecodeError:
            logging.error("Failed to decode JSON response from API.")
        except Exception as e:
            logging.critical(f"An unexpected error occurred in run_check: {e}", exc_info=True)

# --- MAIN EXECUTION BLOCK ---
if __name__ == "__main__":
    if not all(os.getenv(var) for var in ['MOODLE_USERNAME', 'MOODLE_PASSWORD', 'TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID']):
        logging.critical("BOT STARTUP FAILED: Missing essential environment variables.")
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
