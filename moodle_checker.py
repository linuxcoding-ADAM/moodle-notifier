import requests
import json
from bs4 import BeautifulSoup
import time
import re
import os # <-- IMPORTANT: Make sure this line is here

# --- CONFIGURATION: READS SECURELY FROM GITHUB SECRETS ---
LOGIN_URL = 'https://elearning.univ-bejaia.dz/login/index.php'
AFFICHAGE_URL = 'https://elearning.univ-bejaia.dz/course/view.php?id=19989'

# These lines securely read the secrets you created in your GitHub repository settings
MOODLE_USERNAME = os.getenv('MOODLE_USERNAME')
MOODLE_PASSWORD = os.getenv('MOODLE_PASSWORD')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
# --- END OF SECURE CONFIGURATION ---


SEEN_IDS_FILE = 'seen_ids.json'

def get_seen_ids():
    """Loads seen announcement IDs from the JSON file."""
    try:
        with open(SEEN_IDS_FILE, 'r') as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()

def save_seen_ids(ids):
    """Saves announcement IDs to the JSON file."""
    with open(SEEN_IDS_FILE, 'w') as f:
        json.dump(list(ids), f)

def html_to_plain_text_and_links(tag):
    """Converts a BeautifulSoup tag into clean plain text AND extracts all hyperlinks."""
    links = []
    for a in tag.find_all("a", href=True):
        href = a['href']
        if not href.startswith('http'):
            href = 'https://elearning.univ-bejaia.dz' + href
        links.append(href)
    
    for br in tag.find_all("br"): br.replace_with("\n")
    for p in tag.find_all("p"): p.append("\n")
    for tr in tag.find_all("tr"): tr.append("\n")
    for li in tag.find_all("li"): li.insert(0, "\n- ")

    text = tag.get_text()
    lines = (line.strip() for line in text.splitlines())
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    clean_text = "\n".join(chunk for chunk in chunks if chunk)
    return clean_text, links

def send_telegram_message(message):
    """Sends a plain text message to your private chat."""
    if len(message) > 4096:
        message = message[:4090] + "\n\n...(message truncated)"
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message,
        'disable_web_page_preview': True
    }
    try:
        response = requests.post(url, json=payload, timeout=20)
        if response.status_code == 200:
            print("Successfully sent private notification.")
        else:
            if "chat not found" in response.text:
                 print("!!! FAILED TO SEND: 'Chat not found'. Have you started a conversation with your bot on Telegram? Find your bot and press START.")
            else:
                print(f"Failed to send notification: {response.text}")

    except Exception as e:
        print(f"Error sending Telegram message: {e}")

def main():
    """Main function to run the scraper and send notifications."""
    print("Starting check for new announcements...")
    seen_ids = get_seen_ids()
    
    with requests.Session() as s:
        print("Fetching login page...")
        try:
            login_page = s.get(LOGIN_URL, timeout=15)
            soup = BeautifulSoup(login_page.text, 'html.parser')
            logintoken = soup.find('input', {'name': 'logintoken'})['value']
        except (requests.RequestException, TypeError) as e:
            print(f"!!! Error fetching login page or finding token: {e}")
            return
        
        login_payload = {'username': MOODLE_USERNAME, 'password': MOODLE_PASSWORD, 'logintoken': logintoken}
        print("Logging in...")
        try:
            response = s.post(LOGIN_URL, data=login_payload, timeout=15)
        except requests.RequestException as e:
            print(f"!!! Error during login: {e}")
            return

        if "Invalid login" in response.text or "loginerrors" in response.text:
            print("!!! Login Failed! Check credentials.")
            return
        print("Login successful.")
        
        print(f"Accessing page: {AFFICHAGE_URL}")
        try:
            page = s.get(AFFICHAGE_URL, timeout=15)
        except requests.RequestException as e:
            print(f"!!! Error fetching page: {e}")
            return
        
        soup = BeautifulSoup(page.text, 'html.parser')
        announcement_tags = soup.select('li.activity.modtype_label .activity-altcontent')
        
        if not announcement_tags:
            print("!!! Could not find any announcements.")
            return

        print(f"Found {len(announcement_tags)} total announcements.")
        
        new_announcements = []
        
        for tag in announcement_tags:
            parent_li = tag.find_parent('li', class_='activity')
            item_id = parent_li.get('id') if parent_li else None
            
            if item_id and item_id not in seen_ids:
                plain_text_content, links = html_to_plain_text_and_links(tag)
                new_announcements.append({
                    'id': item_id,
                    'content': plain_text_content,
                    'links': links
                })
        
        if new_announcements:
            print(f"Found {len(new_announcements)} new announcements!")
            for item in reversed(new_announcements):
                message = (
                    f"📣 Nouvelle Affiche sur E-learning\n"
                    f"================================\n\n"
                    f"{item['content']}"
                )
                
                if item['links']:
                    message += "\n\n--------------------------------\n"
                    message += "🔗 Liens dans l'annonce:\n"
                    for link in item['links']:
                        message += f"- {link}\n"
                
                send_telegram_message(message)
                
                seen_ids.add(item['id'])
                save_seen_ids(seen_ids)
                time.sleep(1) # a small delay between messages
        else:
            print("No new announcements found.")

if __name__ == '__main__':
    main()
