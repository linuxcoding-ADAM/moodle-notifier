# The Definitive, Bulletproof Moodle Scraper (FINAL VERSION - Environment Variable Path)

# ... (all imports and config are the same)
# ... (all helper functions are the same)

# --- CORE SCRAPER CLASS (MODIFIED INITIALIZE DRIVER) ---
class MoodleScraper:
    def __init__(self):
        self.seen_ids = get_seen_ids()
        self.driver = None

    def _initialize_driver(self):
        """Sets up the Selenium WebDriver using the system-installed chromedriver."""
        logging.info("Initializing Selenium WebDriver...")
        try:
            chrome_options = webdriver.ChromeOptions()
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            
            # --- THIS IS THE FIX ---
            # Get the correct path from the environment variable set in nixpacks.toml
            driver_path = os.getenv('CHROMEDRIVER_PATH')
            if not driver_path:
                logging.critical("CHROMEDRIVER_PATH environment variable not set!")
                return False
                
            logging.info(f"Found chromedriver at: {driver_path}")
            service = ChromeService(executable_path=driver_path)
            
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            logging.info("WebDriver initialized successfully.")
            return True
        except Exception as e:
            logging.critical(f"Failed to initialize WebDriver: {e}", exc_info=True)
            return False

    # ... (the rest of the script is exactly the same)
    def _login(self):
        # ... (Login function is unchanged)
        if not self.driver:
            if not self._initialize_driver():
                return False
        logging.info("Attempting login via Selenium...")
        try:
            self.driver.get(Config.LOGIN_URL)
            wait = WebDriverWait(self.driver, 15)
            wait.until(EC.presence_of_element_located((By.ID, "username"))).send_keys(Config.MOODLE_USERNAME)
            self.driver.find_element(By.ID, "password").send_keys(Config.MOODLE_PASSWORD)
            self.driver.find_element(By.ID, "loginbtn").click()
            wait.until(EC.text_to_be_present_in_element((By.TAG_NAME, "body"), Config.USER_FULL_NAME))
            logging.info("Login successful! User name confirmed.")
            return True
        except (TimeoutException, WebDriverException) as e:
            logging.error(f"Failed to log in with Selenium: {e}")
            return False
            
    def run_check(self):
        # ... (run_check function is unchanged)
        logging.info("--- Starting new check cycle ---")
        if not self.driver:
            if not self._login():
                logging.error("Aborting check due to login failure.")
                if self.driver: self.driver.quit()
                self.driver = None
                return
        try:
            logging.info(f"Navigating to announcements page: {Config.AFFICHAGE_URL}")
            self.driver.get(Config.AFFICHAGE_URL)
            wait = WebDriverWait(self.driver, 20)
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "li.activity.modtype_label")))
            page_html = self.driver.page_source
            if "login/index.php" in self.driver.current_url:
                logging.warning("Session expired. Re-authenticating.")
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
            logging.warning("No announcement tags found.")
            return
        new_items = [{'id': tag.find_parent('li', class_='activity').get('id'), 'tag': tag} for tag in announcement_tags if tag.find_parent('li', class_='activity')]
        new_items = [item for item in new_items if item['id'] and item['id'] not in self.seen_ids]
        if new_items:
            logging.info(f"Found {len(new_items)} new announcement(s)!")
            for item in reversed(new_items):
                item_id, item_tag = item['id'], item['tag']
                content_text = format_announcement_text(html_to_markdown(item_tag))
                links = extract_links(item_tag)
                message = f"📣 *Nouvelle Affiche*\n================\n\n{content_text}"
                if links: message += "\n\n----------------\n🔗 *Liens:*\n" + "\n".join(f"• {link}" for link in sorted(list(set(links))))
                message += f"\n\n------------\nid : `{item_id}`"
                if send_telegram_message(message):
                    self.seen_ids.add(item_id)
                    save_seen_ids(self.seen_ids)
                    logging.info(f"Successfully processed and saved ID: {item_id}")
                else: logging.warning(f"Failed to send notification for {item_id}. Retrying next cycle.")
                time.sleep(2)
        else: logging.info("No new announcements found.")
            
if __name__ == "__main__":
    if not all(os.getenv(var) for var in ['MOODLE_USERNAME', 'MOODLE_PASSWORD', 'TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID', 'USER_FULL_NAME']):
        logging.critical("BOT STARTUP FAILED: Missing environment variables.")
    else:
        logging.info("Script is starting up.")
        send_telegram_message("✅ *Bot started/restarted* and is monitoring.", parse_mode='Markdown')
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
                if scraper.driver: scraper.driver.quit()
                scraper.driver = None
                time.sleep(Config.ERROR_RETRY_DELAY)
