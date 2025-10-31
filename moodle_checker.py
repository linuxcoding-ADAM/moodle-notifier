# The Definitive, Bulletproof Moodle Scraper - PUBLIC BOT VERSION (v4 - Final)

import requests
import json
import time
import re
import os
import logging
import traceback
import hashlib
import sqlite3
import asyncio
from bs4 import BeautifulSoup, NavigableString, Tag
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.constants import ParseMode
from telegram.error import TelegramError, BadRequest

# --- CONFIGURATION CLASS: All settings in one place ---
class Config:
    """Holds all configuration variables for the scraper."""
    LOGIN_URL = 'https://elearning.univ-bejaia.dz/login/index.php'
    AFFICHAGE_URL = 'https://elearning.univ-bejaia.dz/course/view.php?id=19989'
    
    MOODLE_USERNAME = os.getenv('MOODLE_USERNAME')
    MOODLE_PASSWORD = os.getenv('MOODLE_PASSWORD')
    USER_FULL_NAME = os.getenv('USER_FULL_NAME')
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

    SEEN_HASHES_FILE = '/data/seen_hashes.json'
    SEEN_HASHES_FILE_TMP = '/data/seen_hashes.json.tmp'
    DB_FILE = '/data/subscribers.db'

    CHECK_INTERVAL_MINUTES = 10
    
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

# --- SUBSCRIBER DATABASE MANAGEMENT ---
def setup_database():
    """Creates the data directory and the subscribers table if they don't exist."""
    os.makedirs(os.path.dirname(Config.DB_FILE), exist_ok=True)
    
    con = sqlite3.connect(Config.DB_FILE)
    cur = con.cursor()
    cur.execute('CREATE TABLE IF NOT EXISTS subscribers (chat_id INTEGER PRIMARY KEY)')
    con.commit()
    con.close()
    logging.info("Database initialized successfully.")

def get_all_subscribers():
    """Returns a list of all subscriber chat_ids."""
    con = sqlite3.connect(Config.DB_FILE)
    cur = con.cursor()
    cur.execute("SELECT chat_id FROM subscribers")
    subscribers = [item[0] for item in cur.fetchall()]
    con.close()
    return subscribers

def add_subscriber(chat_id):
    """Adds a new subscriber to the database."""
    con = sqlite3.connect(Config.DB_FILE)
    cur = con.cursor()
    cur.execute("INSERT OR IGNORE INTO subscribers (chat_id) VALUES (?)", (chat_id,))
    con.commit()
    con.close()

def remove_subscriber(chat_id):
    """Removes a subscriber from the database."""
    con = sqlite3.connect(Config.DB_FILE)
    cur = con.cursor()
    cur.execute("DELETE FROM subscribers WHERE chat_id = ?", (chat_id,))
    con.commit()
    con.close()

# --- BOT COMMAND HANDLERS ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command."""
    user = update.effective_user
    chat_id = user.id
    add_subscriber(chat_id)
    logging.info(f"New subscriber: {user.username} ({chat_id})")
    await update.message.reply_text(
        "👋 Welcome!\n\n"
        "You are now subscribed to get announcements from the ST faculty.\n\n"
        "Type /stop at any time to unsubscribe."
    )

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /stop command."""
    user = update.effective_user
    chat_id = user.id
    remove_subscriber(chat_id)
    logging.info(f"User unsubscribed: {user.username} ({chat_id})")
    await update.message.reply_text("You have been unsubscribed. You will no longer receive notifications.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /help command."""
    await update.message.reply_text(
        "This bot automatically checks the Moodle announcement page for the ST faculty.\n\n"
        "Available commands:\n"
        "/start - Subscribe to notifications\n"
        "/stop - Unsubscribe from notifications"
    )

# --- ROBUST TELEGRAM BROADCASTING (THE ONLY CHANGED FUNCTION) ---
async def broadcast_message(message_text: str, context: ContextTypes.DEFAULT_TYPE):
    """Sends a message to all subscribers with a fallback for Markdown errors."""
    subscribers = get_all_subscribers()
    if not subscribers:
        logging.info("New announcement found, but no one is subscribed.")
        return

    logging.info(f"Broadcasting message to {len(subscribers)} subscriber(s)...")
    
    for chat_id in subscribers:
        try:
            # First, try to send with Markdown
            await context.bot.send_message(
                chat_id=chat_id, text=message_text, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True
            )
        except BadRequest as e:
            # If a BadRequest happens AND it's a parsing error, retry as plain text.
            if "can't parse entities" in e.message:
                logging.warning(f"Markdown failed for chat_id {chat_id}. Retrying as plain text.")
                try:
                    await context.bot.send_message(
                        chat_id=chat_id, text=message_text, disable_web_page_preview=True
                    )
                except TelegramError as e_plain:
                    logging.error(f"Failed to send plain text message to {chat_id}: {e_plain}")
            else:
                # The error was a different kind of bad request (e.g., chat not found)
                logging.error(f"A BadRequest error occurred for chat {chat_id}: {e.message}")
        except TelegramError as e:
            # Handle all other potential Telegram errors (network, etc.)
            logging.error(f"A Telegram error occurred for chat {chat_id}: {e.message}")
        
        await asyncio.sleep(0.1) # Small delay to avoid hitting rate limits
        
    logging.info("Broadcast complete.")


# --- DATA PERSISTENCE & HTML HELPERS (UNCHANGED) ---
def get_seen_ids():
    try:
        with open(Config.SEEN_HASHES_FILE, 'r') as f: return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError): return set()

def save_seen_ids(ids):
    try:
        os.makedirs(os.path.dirname(Config.SEEN_HASHES_FILE), exist_ok=True)
        with open(Config.SEEN_HASHES_FILE_TMP, 'w') as f: json.dump(list(ids), f, indent=2)
        os.rename(Config.SEEN_HASHES_FILE_TMP, Config.SEEN_HASHES_FILE)
    except Exception as e: logging.critical(f"FATAL: Could not save seen_hashes file! Error: {e}")

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
    if not matches: return text
    formatted_parts = [f"*{label.strip()} :*\n{value.strip()}" for label, value in matches]
    return "\n\n".join(formatted_parts)

def generate_content_hash(tag):
    text_content = tag.get_text(" ", strip=True) 
    links = sorted(extract_links(tag))
    stable_representation = text_content + "||".join(links)
    return hashlib.sha256(stable_representation.encode('utf-8')).hexdigest()

# --- CORE SCRAPER CLASS (UNCHANGED) ---
class MoodleScraper:
    def __init__(self, bot_context: ContextTypes.DEFAULT_TYPE):
        self.session = requests.Session()
        self.session.headers.update(Config.HEADERS)
        self.seen_ids = get_seen_ids()
        self.logged_in = False
        self.bot_context = bot_context

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
                return False
                
        except requests.exceptions.RequestException as e:
            logging.error(f"Network error during login: {e}")
            return False
        except (KeyError, AttributeError) as e:
            logging.error(f"Failed to parse login page. Error: {e}")
            return False

    async def run_check(self, context: ContextTypes.DEFAULT_TYPE):
        logging.info("--- Starting new check cycle ---")
        if not self.logged_in:
            if not self._login():
                logging.error("Aborting check due to login failure.")
                return

        try:
            page = self.session.get(Config.AFFICHAGE_URL, timeout=30)
            page.raise_for_status()
            if "login/index.php" in page.url or (Config.USER_FULL_NAME and Config.USER_FULL_NAME.lower() not in page.text.lower()):
                logging.warning("Session appears to be expired. Forcing re-login on the next cycle.")
                self.logged_in = False
                return
        except requests.exceptions.RequestException as e:
            logging.error(f"Network error fetching announcements: {e}")
            return
            
        soup = BeautifulSoup(page.text, 'html.parser')
        announcement_tags = soup.select('li.activity.modtype_label .activity-altcontent')
        if not announcement_tags:
            logging.warning("Could not find any announcement tags on the page.")
            return

        new_items = []
        for tag in announcement_tags:
            item_id = generate_content_hash(tag)
            if item_id and item_id not in self.seen_ids:
                new_items.append({'id': item_id, 'tag': tag})
        
        if new_items:
            logging.info(f"Found {len(new_items)} new announcement(s)!")
            for item in reversed(new_items):
                item_id, item_tag = item['id'], item['tag']
                raw_text = html_to_markdown(item_tag)
                content_text = format_announcement_text(raw_text)
                links = extract_links(item_tag)
                message = f"📣 *Nouvelle Affiche*\n================\n\n{content_text}"
                if links:
                    unique_links = sorted(list(set(links)))
                    message += "\n\n----------------\n🔗 *Liens:*\n" + "\n".join(f"• {link}" for link in unique_links)
                
                await broadcast_message(message, self.bot_context)
                
                self.seen_ids.add(item_id)
                save_seen_ids(self.seen_ids)
                logging.info(f"Successfully processed and saved hash: {item_id[:12]}")
                await asyncio.sleep(2)
        else:
            logging.info("No new announcements found.")


# --- MAIN EXECUTION BLOCK (UNCHANGED) ---
def main():
    # 1. Check for required environment variables
    required_vars = ['MOODLE_USERNAME', 'MOODLE_PASSWORD', 'TELEGRAM_BOT_TOKEN', 'USER_FULL_NAME']
    if any(not os.getenv(var) for var in required_vars):
        logging.critical("BOT STARTUP FAILED: Missing one or more required environment variables.")
        return

    # 2. Setup the database
    setup_database()

    # 3. Setup the Telegram bot application
    application = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()

    # 4. Create the scraper instance
    scraper = MoodleScraper(bot_context=application)

    # 5. Register the command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("stop", stop_command))
    application.add_handler(CommandHandler("help", help_command))

    # 6. Schedule the scraper to run periodically using the bot's job queue
    application.job_queue.run_repeating(scraper.run_check, interval=Config.CHECK_INTERVAL_MINUTES * 60, first=10)

    # 7. Start the bot
    logging.info("Bot is starting up and is now public.")
    application.run_polling()

if __name__ == "__main__":
    main()
