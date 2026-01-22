/* =========================================
ST AFFICHAGE - SYSTEM CORE SCRIPT
Build: 2026.1.6 (Smart Search)
========================================= */

let allAnnouncements = []; // Master list (All data)
let activeList = [];       // Current list (Filtered data)
let displayedCount = 0;
const BATCH_SIZE = 15;
let isLoading = false;

document.addEventListener("DOMContentLoaded", () => {
 // Theme & Notif Logic (Keep existing)
 const savedTheme = localStorage.getItem('theme');
 if (savedTheme === 'light') {
     document.body.classList.add('light-mode');
     updateThemeUI(true);
 }
 const notifState = localStorage.getItem('notifications');
 if (notifState === 'false') updateNotifUI(false);
 else updateNotifUI(true);

 // Init App
 initApp();

 // --- NEW: SEARCH LISTENER ---
 const searchInput = document.getElementById('search-input');
 if (searchInput) {
     searchInput.addEventListener('input', (e) => {
         const query = e.target.value.toLowerCase();
         handleSearch(query);
     });
 }
});

async function initApp() {
 try {
     const timestamp = new Date().getTime();
     const response = await fetch(`/api/announcements?t=${timestamp}`);
     allAnnouncements = await response.json();
     
     // Initially, the active list IS the full list
     activeList = [...allAnnouncements];

     const container = document.getElementById('cards-container');
     container.innerHTML = ''; 
     
     if (!allAnnouncements || allAnnouncements.length === 0) {
         container.innerHTML = '<div class="text-center text-[10px] font-mono text-muted mt-20 tracking-widest">SYSTEM: NO DATA RECEIVED</div>';
         return;
     }

     loadMore();
     window.addEventListener('scroll', handleScroll);

 } catch (error) {
     console.error("System Error:", error);
     document.getElementById('cards-container').innerHTML = 
         '<div class="text-center text-red-400 font-mono text-xs mt-10">CONNECTION FAILURE<br>Pull to refresh</div>';
 }
}

// --- SEARCH LOGIC ---
function handleSearch(query) {
 // 1. Filter the master list
 if (!query) {
     activeList = [...allAnnouncements]; // Reset
 } else {
     activeList = allAnnouncements.filter(item => 
         item.title.toLowerCase().includes(query) || 
         item.body.toLowerCase().includes(query) ||
         item.date.toLowerCase().includes(query)
     );
 }

 // 2. Reset Display
 displayedCount = 0;
 const container = document.getElementById('cards-container');
 container.innerHTML = ''; // Clear current cards
 
 // 3. Hide End Message initially
 document.getElementById('end-message').classList.add('hidden');

 // 4. Re-render
 if (activeList.length === 0) {
     container.innerHTML = '<div class="text-center text-gray-500 mt-10 text-sm">No results found.</div>';
 } else {
     loadMore();
 }
}

function loadMore() {
 // Note: We check activeList now, not allAnnouncements
 if (isLoading || displayedCount >= activeList.length) return;
 isLoading = true;

 const container = document.getElementById('cards-container');
 const nextBatch = activeList.slice(displayedCount, displayedCount + BATCH_SIZE);

 nextBatch.forEach((item, index) => {
     const card = document.createElement('div');
     card.className = 'glass-card';
     card.style.animationDelay = `${index * 0.05}s`;

     // 1. Attachment Links
     let linksHtml = '';
     if (item.links && item.links.length > 0) {
         item.links.forEach(link => {
             linksHtml += `
                 <a href="${link}" class="link-btn">
                     <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"></path></svg>
                     DOWNLOAD FILE
                 </a>`;
         });
     }

     // 2. Source Link (Centered)
     let sourceBtn = '';
     if (item.source) {
         sourceBtn = `
             <div class="source-link-container">
                 <a href="${item.source}" class="text-[10px] font-mono text-gray-500 hover:text-blue-400 flex items-center transition-colors gap-1">
                     OPEN ON UNIV-BEJAIA.DZ
                     <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"></path></svg>
                 </a>
             </div>
         `;
     }

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
         ${sourceBtn}
     `;
     container.appendChild(card);
 });

 displayedCount += nextBatch.length;
 isLoading = false;

 if (displayedCount >= activeList.length) {
     document.getElementById('end-message').classList.remove('hidden');
 }
}

function handleScroll() {
 if ((window.innerHeight + window.scrollY) >= document.body.offsetHeight - 500) {
     loadMore();
 }
}

// --- KEEP YOUR EXISTING SETTINGS/TOGGLE FUNCTIONS BELOW ---
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

function toggleNotifications() {
 const switchEl = document.getElementById('notif-switch');
 const isActive = switchEl.classList.contains('active');
 
 if (isActive) {
     switchEl.classList.remove('active');
     localStorage.setItem('notifications', 'false');
     window.location.href = "st-app://unsubscribe";
 } else {
     switchEl.classList.add('active');
     localStorage.setItem('notifications', 'true');
     window.location.href = "st-app://subscribe";
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