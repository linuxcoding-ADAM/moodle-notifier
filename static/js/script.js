/* =========================================
   ST AFFICHAGE - SYSTEM CORE SCRIPT
   Build: 2026.1.4.1 (Engineered)
   ========================================= */

   let allAnnouncements = [];
   let displayedCount = 0;
   const BATCH_SIZE = 15;
   let isLoading = false;
   
   // --- 1. INITIALIZATION SEQUENCE ---
   document.addEventListener("DOMContentLoaded", () => {
       // A. Apply Saved Theme
       const savedTheme = localStorage.getItem('theme');
       if (savedTheme === 'light') {
           document.body.classList.add('light-mode');
           updateThemeUI(true);
       }
       
       // B. Apply Saved Notification State
       const notifState = localStorage.getItem('notifications');
       // Default to true if null (first run)
       if (notifState === 'false') {
           updateNotifUI(false);
       } else {
           updateNotifUI(true);
           // Ensure Android is synced on start (optional redundancy)
           // window.location.href = "st-app://subscribe"; 
       }
   
       // C. Initialize Data Stream
       initApp();
   });
   
   // --- 2. DATA LAYER ---
   async function initApp() {
       try {
           const response = await fetch('/api/announcements');
           allAnnouncements = await response.json();
           
           const container = document.getElementById('cards-container');
           container.innerHTML = ''; // Clear loader
           
           if (!allAnnouncements || allAnnouncements.length === 0) {
               container.innerHTML = '<div class="text-center text-[10px] font-mono text-muted mt-20 tracking-widest">SYSTEM: NO DATA RECEIVED</div>';
               return;
           }
   
           // Initialize Feed
           loadMore();
           
           // Attach Infinite Scroll Listener
           window.addEventListener('scroll', handleScroll);
   
       } catch (error) {
           console.error("System Error:", error);
           document.getElementById('cards-container').innerHTML = 
               '<div class="text-center text-red-400 font-mono text-xs mt-10">CONNECTION FAILURE</div>';
       }
   }
   
   // --- 3. RENDER LOGIC (ENGINEERED LAYOUT) ---
   function loadMore() {
       if (isLoading || displayedCount >= allAnnouncements.length) return;
       isLoading = true;
   
       const container = document.getElementById('cards-container');
       const nextBatch = allAnnouncements.slice(displayedCount, displayedCount + BATCH_SIZE);
   
       nextBatch.forEach((item, index) => {
           const card = document.createElement('div');
           card.className = 'glass-card';
           // Staggered animation delay for mechanical feel
           card.style.animationDelay = `${index * 0.05}s`;
   
           // Generate Attachment Links (if any)
           let linksHtml = '';
           if (item.links && item.links.length > 0) {
               item.links.forEach(link => {
                   linksHtml += `
                       <a href="${link}" class="link-btn">
                           <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"></path></svg>
                           ACCESS DOCUMENT
                       </a>`;
               });
           }
   
           // Structural HTML (Matches the new Industrial Design)
           card.innerHTML = `
               <div class="announcement-meta-container">
                   <span class="announcement-date">:: ${item.date}</span>
               </div>
               
               <h3 class="announcement-title">${item.title}</h3>
               
               <div class="w-full h-px bg-white/5 my-4"></div>
               
               <div class="announcement-body">
                   ${item.body}
               </div>
               
               ${linksHtml}
           `;
           container.appendChild(card);
       });
   
       displayedCount += nextBatch.length;
       isLoading = false;
   
       // End of Stream Handling
       if (displayedCount >= allAnnouncements.length) {
           document.getElementById('end-message').classList.remove('hidden');
           window.removeEventListener('scroll', handleScroll);
       }
   }
   
   function handleScroll() {
       // Trigger when 500px from bottom
       if ((window.innerHeight + window.scrollY) >= document.body.offsetHeight - 500) {
           loadMore();
       }
   }
   
   // --- 4. NAVIGATION SUBSYSTEM ---
   function switchTab(tab) {
       const homePage = document.getElementById('page-home');
       const settingsPage = document.getElementById('page-settings');
       const btnHome = document.getElementById('tab-home');
       const btnSettings = document.getElementById('tab-settings');
   
       if (tab === 'home') {
           homePage.classList.remove('hidden');
           settingsPage.classList.add('hidden');
           
           btnHome.classList.add('active');
           btnSettings.classList.remove('active');
           
           window.scrollTo(0, 0);
       } else {
           homePage.classList.add('hidden');
           settingsPage.classList.remove('hidden');
           
           btnSettings.classList.add('active');
           btnHome.classList.remove('active');
       }
   }
   
   // --- 5. SETTINGS SUBSYSTEM ---
   
   /* A. Theme Toggle */
   function toggleTheme() {
       const isLight = document.body.classList.toggle('light-mode');
       localStorage.setItem('theme', isLight ? 'light' : 'dark');
       updateThemeUI(isLight);
   }
   
   function updateThemeUI(isLight) {
       const switchEl = document.getElementById('theme-switch');
       if (isLight) {
           switchEl.classList.add('active');
       } else {
           switchEl.classList.remove('active');
       }
   }
   
   /* B. Notifications Toggle (with Android Bridge) */
   function toggleNotifications() {
       const switchEl = document.getElementById('notif-switch');
       // Check current state by looking at the class
       const isActive = switchEl.classList.contains('active');
       
       if (isActive) {
           // TURN OFF
           switchEl.classList.remove('active');
           localStorage.setItem('notifications', 'false');
           // Bridge Signal -> Unsubscribe
           window.location.href = "st-app://unsubscribe";
       } else {
           // TURN ON
           switchEl.classList.add('active');
           localStorage.setItem('notifications', 'true');
           // Bridge Signal -> Subscribe
           window.location.href = "st-app://subscribe";
           
           // Browser fallback (if not in app)
           if ("Notification" in window) Notification.requestPermission();
       }
   }
   
   function updateNotifUI(isEnabled) {
       const switchEl = document.getElementById('notif-switch');
       if (isEnabled) {
           switchEl.classList.add('active');
       } else {
           switchEl.classList.remove('active');
       }
   }