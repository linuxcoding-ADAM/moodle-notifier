import threading
import time
import requests
import re
import hashlib
import os
import json
import bleach  # NEW: For Security Sanitization
from flask import Flask, render_template, jsonify, request, Response
from bs4 import BeautifulSoup, NavigableString, Tag
from flask_limiter import Limiter # NEW: For Rate Limiting
from flask_limiter.util import get_remote_address

# --- FIREBASE ADMIN SETUP ---
import firebase_admin
from firebase_admin import credentials, messaging

# Load credentials
cred_json = os.environ.get('FIREBASE_CREDENTIALS')
if cred_json:
    try:
        cred_dict = json.loads(cred_json)
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
    except Exception as e:
        print(f"⚠️ Security Error: Invalid Firebase Credentials: {e}")
else:
    print("⚠️ WARNING: FIREBASE_CREDENTIALS variable missing!")

# --- CONFIG ---
AFFICHAGE_URL = 'https://elearning.univ-bejaia.dz/course/view.php?id=19989'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

latest_data = []
first_run = True
app = Flask(__name__)

# --- SECURITY: RATE LIMITING ---
# Limits API calls to prevent DDoS and spam
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

# --- SECURITY: HEADERS ---
@app.after_request
def add_security_headers(response):
    # Prevents Clickjacking
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    # Prevents MIME-sniffing
    response.headers['X-Content-Type-Options'] = 'nosniff'
    # strict HSTS (Force HTTPS)
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response

# --- HELPERS ---
def sanitize_html(html_content):
    """
    OWASP: Sanitize HTML to prevent XSS attacks.
    Only allow safe tags like <b>, <i>, <br>.
    """
    allowed_tags = ['b', 'strong', 'i', 'em', 'br', 'p', 'div', 'span']
    allowed_attributes = {} # No attributes like onclick allowed
    return bleach.clean(html_content, tags=allowed_tags, attributes=allowed_attributes, strip=True)

def clean_html_text(tag):
    """Extracts text and preserves structure securely"""
    text_parts = []
    for child in tag.children:
        if isinstance(child, NavigableString): 
            text_parts.append(str(child)) # Convert to string safely
        elif isinstance(child, Tag):
            # Recursively clean children
            child_text = clean_html_text(child)
            if child.name in ['b', 'strong']: text_parts.append(f"<b>{child_text}</b>")
            elif child.name in ['i', 'em']: text_parts.append(f"<i>{child_text}</i>")
            elif child.name == 'a': text_parts.append(child_text) # Extract text only from links here
            elif child.name in ['p', 'div', 'li', 'br']: text_parts.append(f"<br>{child_text}<br>")
            else: text_parts.append(child_text)
    
    raw_html = "".join(text_parts)
    # Sanitize the final string using Bleach before returning
    return sanitize_html(raw_html)

def extract_links(tag):
    links = []
    for a in tag.find_all("a", href=True):
        href = a.get('href')
        # Validate URL format (Basic Security)
        if href and "http" not in href:
             href = f"https://elearning.univ-bejaia.dz{href}" if href.startswith('/') else f"https://elearning.univ-bejaia.dz/{href}"
        
        # Ensure it's a valid URL structure
        if href and href.startswith('http'):
            links.append(href)
    return links

def send_fcm_notification(title, body_preview):
    try:
        android_config = messaging.AndroidConfig(
            priority='high',
            ttl=86400,
            notification=messaging.AndroidNotification(click_action='FLUTTER_NOTIFICATION_CLICK')
        )
        # Sanitize Title and Body before sending to Google
        safe_title = bleach.clean(title, tags=[], strip=True)
        
        message = messaging.Message(
            notification=messaging.Notification(title="Nouvelle Annonce ST", body=safe_title),
            android=android_config,
            topic='announcements',
        )
        messaging.send(message)
        print(f"🚀 FCM Notification Sent")
    except Exception as e:
        print(f"❌ FCM Error: {e}")

# --- SCRAPER ---
def background_scraper():
    global latest_data, first_run
    print("--- Scraper Thread Started ---")
    while True:
        try:
            print("Checking for updates...")
            session = requests.Session()
            session.headers.update(HEADERS)
            response = session.get(AFFICHAGE_URL, timeout=30)
            
            # Use 'lxml' if available, else 'html.parser'
            soup = BeautifulSoup(response.text, 'html.parser')
            cards = soup.select('li.activity.modtype_label .activity-altcontent')
            
            new_data = []
            
            for tag in cards:
                raw_text = tag.get_text(" ", strip=True)
                # Secure Hash Generation
                unique_id = hashlib.sha256(raw_text.encode('utf-8')).hexdigest()[:16]
                
                # Secure Cleaning
                body_html = clean_html_text(tag)
                
                # Title Extraction
                title = "Information"
                title_match = re.search(r'<b>(.*?)</b>', body_html)
                if title_match:
                    title = title_match.group(1).strip().replace(":", "")
                    body_html = body_html.replace(title_match.group(0), "", 1)

                # Date Extraction
                date_text = "Général"
                date_match = re.search(r'Affiché le\s*[:]?\s*([0-9/\-\w\s:]+)', raw_text, re.IGNORECASE)
                if date_match: 
                    date_text = date_match.group(1).strip()

                # Source Link
                parent_li = tag.find_parent('li', class_='activity')
                source_link = AFFICHAGE_URL
                if parent_li and parent_li.get('id'):
                    # Sanitize ID to ensure it contains only safe chars
                    safe_id = re.sub(r'[^a-zA-Z0-9-]', '', parent_li.get('id'))
                    source_link = f"{AFFICHAGE_URL}#{safe_id}"

                item = {
                    "id": unique_id,
                    "title": bleach.clean(title, tags=[], strip=True), # Pure text for title
                    "body": body_html, # Safe HTML for body
                    "links": extract_links(tag),
                    "date": bleach.clean(date_text, tags=[], strip=True),
                    "source": source_link
                }
                new_data.append(item)
            
            if new_data:
                if not first_run and latest_data:
                    old_ids = {item['id'] for item in latest_data}
                    for i in range(min(5, len(new_data))):
                        item = new_data[i]
                        if item['id'] not in old_ids:
                            print(f"🔔 NEW: {item['title']}")
                            send_fcm_notification(item['title'], item['body'][:50])