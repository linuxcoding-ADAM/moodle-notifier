# The Definitive, Moodle Scraper (v6 - Final Key Generation Fix)
# Message Formatting Enhanced by mila adem 
# St group C3 2025/2026

import requests
import json
import time
import re
import os
import logging
import traceback
import hashlib
from bs4 import BeautifulSoup, NavigableString, Tag

# --- CONFIGURATION CLASS ---
class Config:
    LOGIN_URL = 'https://elearning.univ-bejaia.dz/login/index.php'
    AFFICHAGE_URL = 'https://elearning.univ-bejaia.dz/course/view.php?id=19989'
    
    MOODLE_USERNAME = os.getenv('MOODLE_USERNAME')
    MOODLE_PASSWORD = os.getenv('MOODLE_PASSWORD')
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
    USER_FULL_NAME = os.getenv('USER_FULL_NAME')

    DATA_FILE = '/data/announcement_data.json'
    DATA_FILE_TMP = '/data/announcement_data.json.tmp'

    CHECK_INTERVAL = 600
    STARTUP_DELAY = 10
    ERROR_RETRY_DELAY = 300
    
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

# --- LOGGING SETUP ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- TELEGRAM NOTIFICATION FUNCTION ---
def send_telegram_message(message_text, parse_mode='Markdown'):
    if not all([Config.TELEGRAM_BOT_TOKEN, Config.TELEGRAM_CHAT_ID]): return False
    url = f"https://api.telegram.org/bot{Config.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {'chat_id': Config.TELEGRAM_CHAT_ID, 'text': message_text, 'parse_mode': parse_mode, 'disable_web_page_preview': True}
    if payload.get('parse_mode') is None: del payload['parse_mode']
    try:
        response = requests.post(url, json=payload, timeout=30)
        if response.status_code == 200: return True
        if response.status_code == 400 and 'can\'t parse entities' in response.json().get('description', '') and parse_mode:
            logging.warning("Markdown parsing failed. Retrying as plain text.")
            return send_telegram_message(message_text, parse_mode=None)
        logging.error(f"Failed to send message. Status: {response.status_code}, Response: {response.text}")
        return False
    except requests.exceptions.RequestException as e:
        logging.error(f"An exception occurred while sending Telegram message: {e}")
        return False

# --- DATA PERSISTENCE FUNCTIONS ---
def get_announcement_data():
    try:
        with open(Config.DATA_FILE, 'r') as f: return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        logging.info(f"{Config.DATA_FILE} not found or invalid. Starting with an empty dictionary.")
        return {}

def save_announcement_data(data):
    try:
        os.makedirs(os.path.dirname(Config.DATA_FILE), exist_ok=True)
        with open(Config.DATA_FILE_TMP, 'w') as f: json.dump(data, f, indent=2)
        os.rename(Config.DATA_FILE_TMP, Config.DATA_FILE)
    except Exception as e:
        logging.critical(f"FATAL: Could not save data file! Error: {e}")

# --- HTML CONVERSION AND FORMATTING ---
def html_to_markdown(tag):
    text_parts = []
    for child in tag.children:
        if isinstance(child, NavigableString): text_parts.append(child.string)
        elif isinstance(child, Tag):
            child_text = html_to_markdown(child)
            if child.name in ['b', 'strong']: text_parts.append(f"*{child_text}*")
            elif child.name in ['i', 'em']: text_parts.append(f"_{child_text}_")
            elif child.name == 'a': text_parts.append(child_text)
            elif child.name in ['p', 'div', 'li', 'br']: text_parts.append(f"\n{child_text}\n")
            else: text_parts.append(child_text)
    full_text = "".join(text_parts)
    return re.sub(r'\n\s*\n', '\n\n', full_text).strip()

def extract_links(tag):
    links = [];
    for a in tag.find_all("a", href=True):
        href = a.get('href')
        if href and href.strip() not in ['#', '']:
            if not href.startswith('http'): href = f"https://elearning.univ-bejaia.dz{href}" if href.startswith('/') else f"https://elearning.univ-bejaia.dz/{href}"
            links.append(href)
    return links

def format_announcement_text(text):
    pattern = r'(?s)\*(.*?):\*\s*(.*?)(?=\s*\*.*?\*:|\Z)'
    matches = re.findall(pattern, text)
    if not matches: return text
    return "\n\n".join([f"*{label.strip()} :*\n{value.strip()}" for label, value in matches])

# --- IDENTIFIER FUNCTIONS ---
def generate_content_hash(tag):
    text_content = tag.get_text(" ", strip=True) 
    links = sorted(extract_links(tag))
    stable_representation = text_content + "||".join(links)
    return hashlib.sha256(stable_representation.encode('utf-8')).hexdigest()

def generate_stable_key(tag):
    """Creates a more unique stable key by combining title and content."""
    title_text = ""
    # Find all bold/strong tags and join their text
    title_tags = tag.find_all(['b', 'strong'])
    if title_tags:
        title_text = " ".join(t.get_text(" ", strip=True) for t in title_tags)

    # Get the first 50 characters of the announcement's plain text content
    content_preview = tag.get_text(" ", strip=True)[:50]
    
    # Combine them to create a unique source string for the key
    key_source = title_text + "||" + content_preview
    
    # Return a hash of the combined string
    return hashlib.sha256(key_source.encode('utf-8')).hexdigest()[:16]

# --- CORE SCRAPER CLASS ---
class MoodleScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(Config.HEADERS)
        self.announcement_data = get_announcement_data()
        self.logged_in = False

    def _login(self):
        logging.info("Attempting a fresh login...")
        self.session = requests.Session(); self.session.headers.update(Config.HEADERS); self.logged_in = False
        try:
            soup = BeautifulSoup(self.session.get(Config.LOGIN_URL, timeout=30).text, 'html.parser')
            logintoken = soup.find('input', {'name': 'logintoken'})['value']
            payload = {'username': Config.MOODLE_USERNAME, 'password': Config.MOODLE_PASSWORD, 'logintoken': logintoken}
            response = self.session.post(Config.LOGIN_URL, data=payload, timeout=30)
            if Config.USER_FULL_NAME and Config.USER_FULL_NAME.lower() in response.text.lower():
                logging.info("Login successful!"); self.logged_in = True; return True
            else:
                logging.error("Login verification failed."); return False
        except Exception as e:
            logging.error(f"Error during login: {e}"); return False

    def run_check(self):
        logging.info("--- Starting new check cycle ---")
        if not self.logged_in and not self._login(): return

        try:
            page = self.session.get(Config.AFFICHAGE_URL, timeout=30)
            if "login/index.php" in page.url or (Config.USER_FULL_NAME and Config.USER_FULL_NAME.lower() not in page.text.lower()):
                logging.warning("Session expired. Forcing re-login."); self.logged_in = False; return
        except requests.exceptions.RequestException as e:
            logging.error(f"Network error: {e}"); return

        soup = BeautifulSoup(page.text, 'html.parser')
        announcement_tags = soup.select('li.activity.modtype_label .activity-altcontent')
        if not announcement_tags:
            logging.warning("Could not find any announcement tags."); return
        
        items_to_process = []
        current_page_keys = set()

        for tag in announcement_tags:
            key = generate_stable_key(tag)
            content_hash = generate_content_hash(tag)
            current_page_keys.add(key)
            
            if key not in self.announcement_data:
                items_to_process.append({'tag': tag, 'key': key, 'hash': content_hash, 'status': 'new'})
            elif self.announcement_data[key] != content_hash:
                items_to_process.append({'tag': tag, 'key': key, 'hash': content_hash, 'status': 'updated'})

        if items_to_process:
            logging.info(f"Found {len(items_to_process)} new or updated announcement(s)!")
            
            for item in reversed(items_to_process):
                # --- *** MESSAGE FORMATTING LOGIC HAS BEEN UPDATED HERE *** ---
                tag, key, content_hash, status = item['tag'], item['key'], item['hash'], item['status']
                
                # Determine header based on status
                if status == 'new':
                    message_header = "📣 *Nouvelle Affiche*"
                else:
                    message_header = "✏️ *Affiche Mise à Jour*"

                # Extract and format the main content
                content_text = format_announcement_text(html_to_markdown(tag))

                # Try to find the title (often the first bolded line)
                title_search = re.search(r'^\s*\*([^*]+)\*\s*', content_text)
                if title_search:
                    announcement_title = title_search.group(1).strip()
                    # Remove the title from the main body to avoid showing it twice
                    main_body = content_text.replace(title_search.group(0), '', 1).strip()
                else:
                    # Fallback if no clear title is found
                    announcement_title = "Information Importante"
                    main_body = content_text

                # Assemble the beautiful message
                message = f"{message_header}\n"
                message += "========================\n\n"
                message += f"📄 *Titre:* __{announcement_title}__\n\n"
                message += f"{main_body}\n"

                # Add links if they exist
                links = extract_links(tag)
                if links:
                    message += "\n------------------------------------\n"
                    message += "🔗 *Liens et Documents Attachés:*\n"
                    for link in sorted(list(set(links))):
                        # Make the link clickable with a clean name
                        message += f"  • [Cliquer ici pour ouvrir]({link})\n"

                # Add a clean footer with the ID
                message += f"\n------------------------------------\n"
                
                # Try to extract the date it was posted
                posted_on_match = re.search(r'Affiché le\s*([0-9/-\w]+\s*à\s*[\d:Hh]+)', tag.get_text())
                if posted_on_match:
                    posted_date = posted_on_match.group(1).strip()
                    message += f"🗓️ *Publié le:* {posted_date}\n"

                message += f"🔑 *ID:* `{key[:12]}`"
                # --- *** END OF MESSAGE FORMATTING CHANGES *** ---

                if send_telegram_message(message):
                    self.announcement_data[key] = content_hash
                    logging.info(f"Successfully processed and saved key: {key[:8]} (Status: {status})")
                else:
                    logging.warning(f"Failed to send notification for key {key[:8]}. It will be retried.")
                time.sleep(2)
        else:
            logging.info("No new or updated announcements found.")

        removed_keys = set(self.announcement_data.keys()) - current_page_keys
        if removed_keys:
            logging.info(f"Removing {len(removed_keys)} old/deleted announcement(s).")
            for key in removed_keys:
                del self.announcement_data[key]
        
        if items_to_process or removed_keys:
            save_announcement_data(self.announcement_data)

# --- MAIN EXECUTION BLOCK ---
if __name__ == "__main__":
    if not all(os.getenv(var) for var in ['MOODLE_USERNAME', 'MOODLE_PASSWORD', 'TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID', 'USER_FULL_NAME']):
        logging.critical("FATAL: Missing one or more environment variables.")
    else:
        logging.info("Script starting up.")
        send_telegram_message("✅ *Bot started/restarted* and is now monitoring.")
        time.sleep(Config.STARTUP_DELAY)
        scraper = MoodleScraper()
        while True:
            try:
                scraper.run_check()
                logging.info(f"Check complete. Waiting for {Config.CHECK_INTERVAL // 60} minutes.")
                time.sleep(Config.CHECK_INTERVAL)
            except Exception as e:
                error_details = traceback.format_exc()
                error_message = f"🔴 *BOT CRITICAL ERROR*\n`{e}`\n\n```{error_details}```"
                logging.critical(f"Unexpected error in main loop: {e}", exc_info=True)
                send_telegram_message(error_message)
                time.sleep(Config.ERROR_RETRY_DELAY)
