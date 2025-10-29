# The Definitive, Bulletproof Moodle Scraper (FINAL VERSION - Selenium Powered)

import requests
import json
import time
import re
import os
import logging
import traceback
from bs4 import BeautifulSoup, NavigableString, Tag
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

# --- CONFIGURATION CLASS ---
class Config:
    LOGIN_URL = 'https://elearning.univ-bejaia.dz/login/index.php'
    AFFICHAGE_URL = 'https://elearning.univ-bejaia.dz/course/view.php?id=19989'
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

# --- UNCHANGED HELPER FUNCTIONS (Telegram, Data, Formatting) ---
def send_telegram_message(message_text, parse_mode='Markdown'):
    # This function remains the same
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
    except (FileNotFoundError, json.JSONDecodeError): return set()
def save_seen_ids(ids):
    try:
        os.makedirs(os.path.dirname(Config.SEEN_IDS_FILE), exist_ok=True)
        with open(Config.SEEN_IDS_FILE_TMP, 'w') as f: json.dump(list(ids), f)
        os.rename(Config.SEEN_IDS_FILE_TMP, Config.SEEN_IDS_FILE)
    except Exception as e: logging.critical(f"Could not save seen_ids.json: {e}")
def html_to_markdown(tag):
    text_parts = []
    for child in tag.children:
        if isinstance(child, NavigableString): text_parts.append(child.string)
        elif isinstance(child, Tag):
            child_text = html_to_markdown(child)
            if child.name in ['b', 'strong']: text_parts.append(f"*{child_text}*")
            elif child.name in ['i', 'em']: text_parts.append(f"_{child_text}_")
            elif child.name in ['p', 'div', 'li', 'br']: text_parts.append(f"\n{child_text}\n")
            else: text_parts.append(child_text)
    return re.sub(r'\n\s*\n', '\n\n', "".join(text_parts)).strip()
def extract_links(tag):
    links = []
    for a in tag.find_all("a", href=True):
        href = a.get('href')
        if href and href.strip() not in ['#', '']:
            if not href.startswith('http'): href = 'https://elearning.univ-bejaia.dz' + href
            links.append(href)
    return links
def format_announcement_text(text):
    pattern = r'(?s)\*(.*?):\*\s*(.*?)(?=\s*\*.*?\*:|\Z)'
    matches = re.findall(pattern, text)
    if not matches: return text
    return "\n\n".join([f"*{label.strip()} :*\n{value.strip()}" for label, value in matches])

# --- CORE SCRAPER CLASS (NOW USING SELENIUM) ---
class MoodleScraper:
    def __init__(self):
        self.seen_ids = get_seen_ids()
        self.driver = None

    def _initialize_driver(self):
        """Sets up the Selenium WebDriver."""
        logging.info("Initializing Selenium WebDriver...")
        try:
            chrome_options = webdriver.ChromeOptions()
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            self.driver = webdriver.Chrome(options=chrome_options)
            logging.info("WebDriver initialized successfully.")
            return True
        except Exception as e:
            logging.critical(f"Failed to initialize WebDriver: {e}")
            return False

    def _login(self):
        """Performs login using Selenium."""
        if not self.driver:
            if not self._initialize_driver():
                return False
        
        logging.info("Attempting login via Selenium...")
        try:
            self.driver.get(Config.LOGIN_URL)
            wait = WebDriverWait(self.driver, 15) # Wait up to 15 seconds

            # Wait for login fields to be ready and fill them
            wait.until(EC.presence_of_element_located((By.ID, "username"))).send_keys(Config.MOODLE_USERNAME)
            self.driver.find_element(By.ID, "password").send_keys(Config.MOODLE_PASSWORD)
            self.driver.find_element(By.ID, "loginbtn").click()

            # Wait for the user's name to appear on the next page to confirm login
            wait.until(EC.text_to_be_present_in_element((By.TAG_NAME, "body"), Config.USER_FULL_NAME))
            logging.info("Login successful! User name confirmed.")
            return True
        except (TimeoutException, WebDriverException) as e:
            logging.error(f"Failed to log in with Selenium: {e}")
            return False

    def run_check(self):
        logging.info("--- Starting new check cycle ---")
        
        if not self.driver:
            if not self._login():
                logging.error("Aborting check due to login failure.")
                # Destroy driver on failure to start fresh next time
                if self.driver: self.driver.quit()
                self.driver = None
                return

        try:
            logging.info(f"Navigating to announcements page: {Config.AFFICHAGE_URL}")
            self.driver.get(Config.AFFICHAGE_URL)
            
            # This is the crucial step: wait for the announcements to be loaded by JS
            wait = WebDriverWait(self.driver, 20)
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "li.activity.modtype_label")))
            
            # Now that the page is fully loaded, get the HTML
            page_html = self.driver.page_source

            if "login/index.php" in self.driver.current_url:
                logging.warning("Session expired or redirected to login. Re-authenticating.")
                self.driver.quit()
                self.driver = None
                return
        except (TimeoutException, WebDriverException) as e:
            logging.error(f"Error loading announcements page: {e}")
            self.driver.quit()
            self.driver = None
            return

        soup = BeautifulSoup(page_html, 'html.parser')
        announcement_tags = soup.select('li.activity.modtype_label .activity-altcontent')
        
        if not announcement_tags:
            logging.warning("Could not find any announcement tags on the page.")
            return

        new_items = [{'id': tag.find_parent('li', class_='activity').get('id'), 'tag': tag} 
                     for tag in announcement_tags if tag.find_parent('li', class_='activity')]
        
        new_items = [item for item in new_items if item['id'] and item['id'] not in self.seen_ids]

        if new_items:
            logging.info(f"Found {len(new_items)} new announcement(s)!")
            for item in reversed(new_items):
                item_id, item_tag = item['id'], item['tag']
                content_text = format_announcement_text(html_to_markdown(item_tag))
                links = extract_links(item_tag)
                message = f"📣 *Nouvelle Affiche*\n================\n\n{content_text}"
                if links:
                    message += "\n\n----------------\n🔗 *Liens:*\n" + "\n".join(f"• {link}" for link in sorted(list(set(links))))
                message += f"\n\n------------\nid : `{item_id}`"
                if send_telegram_message(message):
                    self.seen_ids.add(item_id)
                    save_seen_ids(self.seen_ids)
                    logging.info(f"Successfully processed and saved ID: {item_id}")
                else:
                    logging.warning(f"Failed to send notification for {item_id}. Retrying next cycle.")
                time.sleep(2)
        else:
            logging.info("No new announcements found.")
            
# --- MAIN EXECUTION BLOCK ---
if __name__ == "__main__":
    if not all(os.getenv(var) for var in ['MOODLE_USERNAME', 'MOODLE_PASSWORD', 'TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID', 'USER_FULL_NAME']):
        logging.critical("BOT STARTUP FAILED: One or more essential environment variables are missing.")
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
                if scraper.driver:
                    scraper.driver.quit()
                scraper.driver = None # Reset driver after a crash
                time.sleep(Config.ERROR_RETRY_DELAY)
