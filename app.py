import threading
import time
import requests
import re
import hashlib
import os
import json
import bleach
import hmac
from datetime import datetime
from flask import Flask, render_template, jsonify, request, abort
from bs4 import BeautifulSoup, NavigableString, Tag
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from collections import deque

# --- FIREBASE SETUP ---
import firebase_admin
from firebase_admin import credentials, messaging

cred_json = os.environ.get('FIREBASE_CREDENTIALS')
if cred_json:
    try:
        cred_dict = json.loads(cred_json)
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
        print("✅ Firebase initialized successfully.")
    except Exception as e:
        print(f"⚠️ Firebase Error: {e}")
else:
    print("⚠️ WARNING: FIREBASE_CREDENTIALS missing!")

# --- LOGGING SETUP ---
log_buffer = deque(maxlen=100)

def custom_log(msg):
    timestamp = datetime.now().strftime("%H:%M:%S")
    formatted_msg = f"[{timestamp}] {msg}"
    print(formatted_msg)
    log_buffer.append(formatted_msg)

# --- MOODLE AUTHENTICATED SESSION ---
class MoodleSession:
    """Handles Moodle login and maintains an authenticated requests.Session."""

    LOGIN_URL = "https://elearning.univ-bejaia.dz/login/index.php"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'
        })
        self.username = os.environ.get('MOODLE_USERNAME', '')
        self.password = os.environ.get('MOODLE_PASSWORD', '')
        self.last_auth_time = 0
        self.is_authenticated = False
        self.enrolled_slugs = set()
        self._lock = threading.Lock()

    def authenticate(self):
        """Log in to Moodle and store the session cookies."""
        with self._lock:
            if not self.username or not self.password:
                custom_log("⚠️ MOODLE_USERNAME or MOODLE_PASSWORD not set — skipping login")
                return False

            try:
                login_page = self.session.get(self.LOGIN_URL, timeout=30)
                login_page.raise_for_status()

                soup = BeautifulSoup(login_page.text, 'html.parser')
                token_input = soup.find('input', {'name': 'logintoken'})
                logintoken = token_input['value'] if token_input else ''

                payload = {
                    'anchor': '',
                    'logintoken': logintoken,
                    'username': self.username,
                    'password': self.password,
                }
                resp = self.session.post(self.LOGIN_URL, data=payload, timeout=30)

                # Success if the final URL does NOT contain /login/index.php
                if '/login/index.php' not in resp.url:
                    self.is_authenticated = True
                    self.last_auth_time = time.time()
                    custom_log("✅ Moodle login successful")
                    return True
                else:
                    self.is_authenticated = False
                    custom_log("❌ Moodle login failed — check credentials")
                    return False

            except Exception as e:
                self.is_authenticated = False
                custom_log(f"❌ Moodle login exception: {type(e).__name__}: {e}")
                return False

    def re_authenticate(self):
        """Force a fresh login (e.g. after session expiry)."""
        custom_log("🔄 Re-authenticating Moodle session...")
        self.session.cookies.clear()
        return self.authenticate()

    def ensure_session(self):
        """Make sure we have a valid session, re-auth if older than 2 hours."""
        if not self.is_authenticated or (time.time() - self.last_auth_time > 7200):
            self.authenticate()

    def get(self, url, **kwargs):
        """GET a URL using the authenticated session. Retries once on auth failure."""
        self.ensure_session()
        kwargs.setdefault('timeout', 30)
        resp = self.session.get(url, **kwargs)

        if self._needs_reauth(resp):
            custom_log(f"⚠️ Session expired for {url} — retrying after re-auth")
            if self.re_authenticate():
                resp = self.session.get(url, **kwargs)
        return resp

    def _needs_reauth(self, resp):
        """Detect if the response indicates we need to log in again."""
        if '/login/index.php' in resp.url:
            return True
        lower_html = resp.text[:3000].lower()
        if 'loginform' in lower_html or 'id="login"' in lower_html:
            return True
        if 'guests cannot access' in lower_html:
            return True
        return False

    def ensure_enrolled(self, url, slug):
        """Check for and complete auto-enrollment if required, returning the final page response."""
        resp = self.get(url)

        if slug in self.enrolled_slugs:
            return resp

        soup = BeautifulSoup(resp.text, 'html.parser')
        
        enroll_form = None
        for form in soup.find_all('form'):
            action = form.get('action', '').lower()
            if 'enrol' in action:
                enroll_form = form
                break

        if not enroll_form:
            enroll_keywords = ["m'inscrire", "enrol me", "s'inscrire", "auto-inscription"]
            for keyword in enroll_keywords:
                btn = soup.find(lambda tag: tag.name in ['button', 'a', 'input'] and keyword in tag.get_text(strip=True).lower())
                if btn:
                    enroll_form = btn.find_parent('form')
                    break
                    
        if enroll_form:
            action_url = enroll_form.get('action')
            if not action_url:
                action_url = url
            
            payload = {}
            for input_tag in enroll_form.find_all('input'):
                name = input_tag.get('name')
                value = input_tag.get('value', '')
                if name:
                    payload[name] = value
                    
            try:
                enroll_resp = self.session.post(action_url, data=payload, timeout=30)
                enroll_resp.raise_for_status()
                custom_log(f"✅ [{slug}] Auto-enrolled successfully")
                self.enrolled_slugs.add(slug)
                return self.get(url)
            except Exception as e:
                custom_log(f"❌ [{slug}] Auto-enrollment failed: {e}")
                return resp
        else:
            custom_log(f"⚠️ [{slug}] No enrollment button found — already enrolled or access denied")
            self.enrolled_slugs.add(slug)
            return resp

# Create the global Moodle session
moodle = MoodleSession()

# --- DEPARTMENTS CONFIG ---
DEPARTMENTS = {
    "technologie": {
        "name": "Département de Technologie (ST)",
        "short_name": "ST",
        "slug": "technologie",
        "moodle_url": "https://elearning.univ-bejaia.dz/course/view.php?id=19989",
        "fcm_topic": "dept_technologie",
        "icon": "",
        "cache_file": "cache_technologie.json"
    },
    "hydraulique": {
        "name": "Département d'Hydraulique",
        "short_name": "Hydraulique",
        "slug": "hydraulique",
        "moodle_url": "https://elearning.univ-bejaia.dz/course/view.php?id=19987",
        "fcm_topic": "dept_hydraulique",
        "icon": "",
        "cache_file": "cache_hydraulique.json"
    },
    "genie-civil": {
        "name": "Département de Génie Civil",
        "short_name": "Génie Civil",
        "slug": "genie-civil",
        "moodle_url": "https://elearning.univ-bejaia.dz/course/view.php?id=19984",
        "fcm_topic": "dept_genie_civil",
        "icon": "",
        "cache_file": "cache_genie_civil.json"
    },
    "genie-mecanique": {
        "name": "Département de Génie Mécanique",
        "short_name": "Génie Méca",
        "slug": "genie-mecanique",
        "moodle_url": "https://elearning.univ-bejaia.dz/course/view.php?id=19985",
        "fcm_topic": "dept_genie_mecanique",
        "icon": "",
        "cache_file": "cache_genie_mecanique.json"
    },
    "electrotechnique": {
        "name": "Département d'Électrotechnique",
        "short_name": "Électrotech",
        "slug": "electrotechnique",
        "moodle_url": "https://elearning.univ-bejaia.dz/course/view.php?id=19980",
        "fcm_topic": "dept_electrotechnique",
        "icon": "",
        "cache_file": "cache_electrotechnique.json"
    },
    "ate": {
        "name": "Automatique, Télécom et Électronique",
        "short_name": "ATE",
        "slug": "ate",
        "moodle_url": "https://elearning.univ-bejaia.dz/course/view.php?id=19983",
        "fcm_topic": "dept_ate",
        "icon": "",
        "cache_file": "cache_ate.json"
    }
}

ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', '34362053')

# --- IN-MEMORY DATA STORE (keyed by slug) ---
latest_data = {}
first_run_flags = {}
department_status = {}

# Load cached data for all departments on startup
custom_log("🚀 App Startup: Loading cache...")
for slug, dept in DEPARTMENTS.items():
    first_run_flags[slug] = True
    department_status[slug] = {"last_scraped": "Never", "item_count": 0, "status": "empty"}
    try:
        if os.path.exists(dept['cache_file']):
            with open(dept['cache_file'], 'r', encoding='utf-8') as f:
                latest_data[slug] = json.load(f)
            custom_log(f"📦 [{slug}] Loaded {len(latest_data[slug])} items from cache.")
            department_status[slug]["item_count"] = len(latest_data[slug])
            if latest_data[slug]:
                department_status[slug]["status"] = "ok"
        else:
            latest_data[slug] = []
    except Exception as e:
        custom_log(f"⚠️ [{slug}] Could not load cache: {e}")
        latest_data[slug] = []

app = Flask(__name__)

# --- SECURITY ---
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["500 per day", "100 per hour"],
    storage_uri="memory://"
)

@app.after_request
def add_security_headers(response):
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response

# --- HELPERS ---
FRENCH_MONTHS = {
    'janvier': 1, 'février': 2, 'mars': 3, 'avril': 4, 'mai': 5, 'juin': 6,
    'juillet': 7, 'août': 8, 'septembre': 9, 'octobre': 10, 'novembre': 11, 'décembre': 12,
    'jan': 1, 'fév': 2, 'mar': 3, 'avr': 4, 'mai': 5, 'jui': 6,
    'juil': 7, 'aoû': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'déc': 12
}

def parse_date_to_timestamp(date_str):
    try:
        match = re.search(r'(\d{1,2})\s+([a-zA-Zéû]+)\s+(\d{4}).*?(\d{1,2})[h:](\d{1,2})', date_str, re.IGNORECASE)
        if match:
            day, month_str, year, hour, minute = match.groups()
            month = FRENCH_MONTHS.get(month_str.lower(), 1)
            return datetime(int(year), int(month), int(day), int(hour), int(minute)).timestamp()
    except Exception:
        pass
    return 0

def clean_html_text(tag):
    if not tag: return ""
    text_parts = []
    for child in tag.children:
        if isinstance(child, NavigableString): 
            text = child.string.strip()
            if text: text_parts.append(text)
        elif isinstance(child, Tag):
            if 'accesshide' in child.get('class', []): continue
            child_text = clean_html_text(child)
            if child_text:
                if child.name in ['b', 'strong', 'h3', 'h4', 'h5']: text_parts.append(f"<b>{child_text}</b>")
                elif child.name in ['i', 'em']: text_parts.append(f"<i>{child_text}</i>")
                elif child.name in ['p', 'div', 'li', 'br', 'ul']: text_parts.append(f"\n{child_text}\n")
                else: text_parts.append(child_text)
                    
    full_text = " ".join(text_parts)
    full_text = re.sub(r'\n\s*\n', '\n\n', full_text)
    return bleach.clean(re.sub(r' +', ' ', full_text).strip(), tags=['b', 'strong', 'i', 'em'], strip=True)

def extract_links(tag):
    links = []
    for a in tag.find_all("a", href=True):
        href = a.get('href')
        if 'user/view' in href or 'help.php' in href: continue
        if href and "http" not in href:
             href = f"https://elearning.univ-bejaia.dz{href}" if href.startswith('/') else f"https://elearning.univ-bejaia.dz/{href}"
        if href and href.startswith('http') and href not in links:
            links.append(href)
    return links

def extract_images(tag):
    images = []
    for img in tag.find_all("img", src=True):
        src = img.get('src')
        if 'theme/image.php' in src or '/pix/' in src or 'icon' in src.lower() or 'spacer' in src.lower(): continue
        if src and "http" not in src:
            src = f"https://elearning.univ-bejaia.dz{src}" if src.startswith('/') else f"https://elearning.univ-bejaia.dz/{src}"
        if src not in images:
            images.append(src)
    return images

# --- FCM NOTIFICATION (PER-DEPARTMENT) ---
def send_fcm_notification(title, body_preview, topic, dept_slug):
    """Send an FCM notification. Returns (success: bool, detail: str)."""
    try:
        android_config = messaging.AndroidConfig(
            priority='high',
            ttl=86400,
            notification=messaging.AndroidNotification(default_sound=True, default_vibrate_timings=True)
        )
        safe_title = bleach.clean(title, tags=[], strip=True)
        dept = DEPARTMENTS.get(dept_slug, {})
        dept_name = dept.get('name', 'Béjaïa Affichage')

        custom_log(f"📤 [{dept_slug}] Sending to topic: {topic}")

        message = messaging.Message(
            notification=messaging.Notification(
                title=dept_name,
                body=safe_title
            ),
            android=android_config,
            data={
                'dept_slug': dept_slug,
                'click_action': f'/{dept_slug}'
            },
            topic=topic,
        )
        response_id = messaging.send(message)
        if response_id and response_id.startswith('projects/'):
            custom_log(f"✅ [{dept_slug}] FCM confirmed delivery to topic: {topic} (ID: {response_id})")
        else:
            custom_log(f"✅ [{dept_slug}] FCM Response: {response_id}")
        return True, f"FCM Response: {response_id}"
    except Exception as e:
        error_detail = f"[{type(e).__name__}] {e}"
        custom_log(f"❌ [{dept_slug}] FCM Exception: {error_detail}")
        return False, f"FCM Exception: {error_detail}"

# --- INTELLIGENT SCRAPER ---
def scrape_department(moodle_url, slug):
    """Scrape a Moodle department page using the authenticated MoodleSession."""
    try:
        response = moodle.ensure_enrolled(moodle_url, slug)

        # Final check after potential re-auth retry
        lower_html = response.text[:3000].lower()
        if '/login/index.php' in response.url:
            custom_log(f"❌ [{slug}] Moodle requires login — cannot scrape without authentication")
            return []
        if 'guests cannot access' in lower_html:
            custom_log(f"❌ [{slug}] Moodle says 'Guests cannot access this course' — login may have failed")
            return []
        if 'loginform' in lower_html or 'id="login"' in lower_html:
            custom_log(f"❌ [{slug}] Moodle requires login — loginform found in HTML")
            return []

        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        # Remove navigation and unwanted elements before any parsing
        for unwanted in soup.select('header, nav, footer, .navbar, .breadcrumb, .block_navigation, .block_settings, #nav-drawer, #page-header, #page-footer'):
            unwanted.decompose()

        # Find main content region
        main_region = None
        for sel in ['[data-region="course-content"]', '#region-main', '.course-content', '#page-content']:
            main_region = soup.select_one(sel)
            if main_region: break
            
        if not main_region:
            main_region = soup

        # Extract candidates from the main region only
        candidates = []
        for sel in ['li.activity:not(.modtype_forum):not(.modtype_resource)', 'div.activity-wrapper', 'section.section li']:
            candidates = main_region.select(sel)
            if candidates: break
            
        new_data = []
        raw_count = len(candidates)
        passed_count = 0
        
        nav_words = {"suivant", "précédent", "accueil", "connexion", "home", "next", "previous", "login"}
        date_pattern_1 = r'(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})'
        date_pattern_2 = r'([0-9]{1,2}\s+[a-zA-Zéû]+\s+[0-9]{4})'

        for tag in candidates:
            raw_text = tag.get_text(" ", strip=True)
            if len(raw_text) < 15: continue
            
            lower_text = raw_text.lower()
            if any(w in lower_text.split() for w in nav_words) and len(raw_text) < 50:
                continue
                
            content_area = tag.select_one('.contentwithoutlink, .activity-altcontent, .no-overflow, .contentafterlink') or tag
            body_html = clean_html_text(content_area)
            clean_body = bleach.clean(body_html, tags=[], strip=True)
            
            has_date = bool(re.search(date_pattern_1, raw_text)) or bool(re.search(date_pattern_2, raw_text, re.IGNORECASE))
            
            if not has_date and len(clean_body) < 10:
                continue
                
            # Quality scoring
            score = 0
            if has_date: score += 1
            if len(clean_body) > 50: score += 1
            if tag.find(['a', 'img']): score += 1
            if tag.find(['b', 'strong']): score += 1
            
            if score >= 1:
                passed_count += 1
                unique_id = hashlib.sha256(raw_text.encode('utf-8')).hexdigest()[:16]
                
                title, title_match = "Information", re.search(r'<b>(.*?)</b>', body_html)
                instancename = tag.select_one('.instancename, .activityname')
                
                if title_match:
                    title = title_match.group(1).strip().replace(":", "")
                    body_html = body_html.replace(title_match.group(0), "", 1)
                elif instancename:
                    title = instancename.get_text(strip=True).replace(" Fichier", "").replace(" URL", "")
                
                date_text, timestamp = "Général", 0
                date_match = re.search(r'Affiché le\s*[:]?\s*([0-9]{1,2}\s+[a-zA-Zéû]+\s+[0-9]{4}.*?(\d{1,2}[h:]\d{1,2})?)', raw_text, re.IGNORECASE)
                
                if date_match:
                    date_text = date_match.group(1).strip()
                    timestamp = parse_date_to_timestamp(date_text)
                
                source_link = f"{moodle_url}#{re.sub(r'[^a-zA-Z0-9-]', '', tag.get('id'))}" if tag.get('id') else moodle_url

                new_data.append({
                    "id": unique_id,
                    "title": bleach.clean(title, tags=[], strip=True),
                    "body": body_html,
                    "links": extract_links(tag),
                    "images": extract_images(tag),
                    "date": bleach.clean(date_text, tags=[], strip=True),
                    "timestamp": timestamp,
                    "source": source_link
                })
        
        # Last resort fallback: <p> tags with dates
        if passed_count == 0:
            custom_log(f"⚠️ [{slug}] 0 items passed quality filter. Trying fallback paragraph scraper.")
            p_tags = main_region.find_all('p')
            for p in p_tags:
                text = p.get_text(" ", strip=True)
                if len(text) > 40 and (re.search(date_pattern_1, text) or re.search(date_pattern_2, text, re.IGNORECASE)):
                    unique_id = hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]
                    passed_count += 1
                    new_data.append({
                        "id": unique_id,
                        "title": "Annonce",
                        "body": clean_html_text(p),
                        "links": extract_links(p),
                        "images": extract_images(p),
                        "date": "Récemment",
                        "timestamp": 0,
                        "source": moodle_url
                    })
        
        if passed_count > 0:
            custom_log(f"✅ [{slug}] Scraped: {passed_count} passed / {raw_count} raw candidates.")
        else:
            page_title = soup.title.string if soup.title else "Unknown"
            main_text = main_region.get_text(" ", strip=True)[:500]
            custom_log(f"⚠️ [{slug}] 0 items found. Title: {page_title}. Content preview: {main_text}")

        new_data.sort(key=lambda x: x['timestamp'], reverse=True)
        return new_data

    except requests.exceptions.RequestException as e:
        custom_log(f"❌ [{slug}] Network Error: {e}")
    except Exception as e:
        custom_log(f"❌ [{slug}] Scraper Error: {type(e).__name__}: {e}")
    return None

# --- BACKGROUND LOOP (ALL DEPARTMENTS) ---
def background_loop():
    global latest_data, first_run_flags, department_status
    custom_log("--- Background Loop Started (All Departments) ---")

    # Authenticate once at startup before any scraping
    moodle.authenticate()

    while True:
        for slug, dept in DEPARTMENTS.items():
            scraped_items = scrape_department(dept['moodle_url'], slug)
            
            department_status[slug]["last_scraped"] = datetime.now().strftime("%H:%M:%S")
            
            if scraped_items is not None:
                department_status[slug]["item_count"] = len(scraped_items)
                department_status[slug]["status"] = "ok" if scraped_items else "empty"
                
                # Save to department-specific cache file
                try:
                    with open(dept['cache_file'], 'w', encoding='utf-8') as f:
                        json.dump(scraped_items, f, ensure_ascii=False)
                except Exception as e:
                    custom_log(f"⚠️ [{slug}] Could not write to cache: {e}")

                # Detect new announcements (skip on first run)
                if not first_run_flags[slug] and latest_data.get(slug):
                    old_ids = {item['id'] for item in latest_data[slug]}
                    for item in scraped_items[:5]:
                        if item['id'] not in old_ids:
                            custom_log(f"🔔 [{slug}] NEW: {item['title']}")
                            send_fcm_notification(item['title'], "Nouvelle annonce", dept['fcm_topic'], slug)
                            break 
                            
                latest_data[slug] = scraped_items
                first_run_flags[slug] = False
            else:
                department_status[slug]["status"] = "error"
                custom_log(f"⚠️ [{slug}] Scrape returned None, keeping cached data.")
            
            # Small delay between departments
            time.sleep(5)
        
        custom_log("💤 All departments scraped. Sleeping 10 minutes...")
        time.sleep(600)

# --- ROUTES ---

@app.route('/')
def landing():
    return render_template('landing.html', departments=DEPARTMENTS)

@app.route('/select')
def select_dept():
    return render_template('select.html', departments=DEPARTMENTS)

@app.route('/<slug>')
def department_page(slug):
    dept = DEPARTMENTS.get(slug)
    if not dept:
        abort(404)
    return render_template('department.html', dept=dept, departments=DEPARTMENTS)

@app.route('/api/announcements/<slug>')
def api_dept_data(slug):
    if slug not in DEPARTMENTS:
        return jsonify({"error": "Department not found"}), 404
    data = latest_data.get(slug, [])
    response = jsonify(data)
    response.headers['Cache-Control'] = 'public, max-age=60'
    return response

@app.route('/api/subscribe', methods=['POST'])
@limiter.limit("30 per minute")
def api_subscribe():
    data = request.get_json(silent=True)
    if not data: return jsonify({"error": "Invalid JSON"}), 400
    token, topic = data.get('token'), data.get('topic')
    if not token or not topic: return jsonify({"error": "Missing token or topic"}), 400
    
    valid_topics = {dept['fcm_topic'] for dept in DEPARTMENTS.values()}
    if topic not in valid_topics: return jsonify({"error": "Invalid topic"}), 400
    
    try:
        response = messaging.subscribe_to_topic([token], topic)
        return jsonify({"success": True, "topic": topic})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/unsubscribe', methods=['POST'])
@limiter.limit("30 per minute")
def api_unsubscribe():
    data = request.get_json(silent=True)
    if not data: return jsonify({"error": "Invalid JSON"}), 400
    token, topic = data.get('token'), data.get('topic')
    if not token or not topic: return jsonify({"error": "Missing token or topic"}), 400
    
    valid_topics = {dept['fcm_topic'] for dept in DEPARTMENTS.values()}
    if topic not in valid_topics: return jsonify({"error": "Invalid topic"}), 400
    
    try:
        response = messaging.unsubscribe_from_topic([token], topic)
        return jsonify({"success": True, "topic": topic})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/install')
def install_page():
    return render_template('download.html')

@app.route('/robots.txt')
def robots():
    return "User-agent: *\nDisallow: /api/\nDisallow: /test-notification-railway"

# --- ADMIN API ENDPOINTS ---
@app.route('/api/logs')
def api_logs():
    pwd = request.args.get('pwd', '')
    if not hmac.compare_digest(pwd, ADMIN_PASSWORD):
        return jsonify({"error": "Unauthorized"}), 403
    return jsonify({"logs": list(log_buffer)})

@app.route('/api/status')
def api_status():
    pwd = request.args.get('pwd', '')
    if not hmac.compare_digest(pwd, ADMIN_PASSWORD):
        return jsonify({"error": "Unauthorized"}), 403
    return jsonify(department_status)

@app.route('/api/fcm-test-topic/<slug>')
@limiter.limit("5 per minute")
def api_fcm_test_topic(slug):
    pwd = request.args.get('pwd', '')
    if not hmac.compare_digest(pwd, ADMIN_PASSWORD):
        return jsonify({"error": "Unauthorized"}), 403
        
    dept = DEPARTMENTS.get(slug)
    if not dept:
        return jsonify({"error": "Department not found"}), 404
        
    success, detail = send_fcm_notification("API Test", "This is a direct API test.", dept['fcm_topic'], slug)
    return jsonify({"success": success, "detail": detail})

@app.route('/test-notification-railway', methods=['GET', 'POST'])
@limiter.limit("20 per minute") 
def manual_test():
    status = None
    message = None
    if request.method == 'POST':
        password = request.form.get('password', '')
        dept_slug = request.form.get('department', 'technologie')
        title = request.form.get('title', 'Security Test')
        body = request.form.get('body', 'Secure System Operational.')
        
        if dept_slug not in DEPARTMENTS:
            dept_slug = 'technologie'
        
        dept = DEPARTMENTS[dept_slug]
        
        if hmac.compare_digest(password, ADMIN_PASSWORD):
            success, detail = send_fcm_notification(title, body, dept['fcm_topic'], dept_slug)
            if success:
                status = 'success'
                message = f"Sent to {dept['name']} (topic: {dept['fcm_topic']}). {detail}"
            else:
                status = 'error'
                message = detail
            return jsonify({"status": status, "message": message})
        else:
            return jsonify({"status": "denied", "message": "Invalid password"}), 403
            
    return render_template('test_notification.html', status=status, message=message, departments=DEPARTMENTS)

# Start background scraping for ALL departments
threading.Thread(target=background_loop, daemon=True).start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
