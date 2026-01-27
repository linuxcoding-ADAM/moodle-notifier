/* =========================================
   ST AFFICHAGE - 
   Build: 2026.1.13 
   ========================================= */

   let allAnnouncements = [];
   let activeList = [];
   let displayedCount = 0;
   const BATCH_SIZE = 15;
   let isLoading = false;
   let lastScrollTop = 0;
   let ticking = false; 
   
   document.addEventListener("DOMContentLoaded", () => {
       // Theme & Notif
       const savedTheme = localStorage.getItem('theme');
       if (savedTheme === 'light') {
           document.body.classList.add('light-mode');
           updateThemeUI(true);
       }
       const notifState = localStorage.getItem('notifications');
       if (notifState === 'false') updateNotifUI(false);
       else updateNotifUI(true);
   
       initApp();
   
       const searchInput = document.getElementById('search-input');
       if (searchInput) {
           searchInput.addEventListener('input', (e) => {
               // SECURITY: Sanitize Input (Remove dangerous chars)
               const raw = e.target.value.toLowerCase();
               const safeQuery = raw.replace(/[<>{}\"\'\/]/g, ''); 
               handleSearch(safeQuery);
           });
       }
   });
   
   // --- SEARCH UX ---
   function toggleSearch() {
       const bar = document.getElementById('search-bar-container');
       const input = document.getElementById('search-input');
       const bottomNav = document.getElementById('bottom-nav'); 
       
       // Show Search Bar
       bar.classList.add('search-visible');
       bottomNav.classList.add('slide-down-hidden');

       // Show the Cancel Button in the Header
       const cancelBtn = document.getElementById('header-cancel-btn');
       if(cancelBtn) {
           cancelBtn.classList.remove('opacity-0', 'pointer-events-none', 'scale-90');
       }
       
       input.focus();
   }
   
   // This function completely resets the search mode (Hides bar AND button)
   function hideSearchBarUI() {
       document.getElementById('search-bar-container').classList.remove('search-visible');
       document.getElementById('search-input').blur();
       document.getElementById('bottom-nav').classList.remove('slide-down-hidden');

       // Hide the Cancel Button in the Header
       const cancelBtn = document.getElementById('header-cancel-btn');
       if(cancelBtn) {
           cancelBtn.classList.add('opacity-0', 'pointer-events-none', 'scale-90');
       }
   }
   
   function cancelSearch() {
       hideSearchBarUI();
       document.getElementById('search-input').value = '';
       handleSearch('');
   }
   
   // --- DATA ---
   async function initApp() {
       try {
           const timestamp = new Date().getTime();
           const response = await fetch(`/api/announcements?t=${timestamp}`);
           
           if (!response.ok) throw new Error("API Limit Reached");
   
           allAnnouncements = await response.json();
           activeList = [...allAnnouncements];
   
           const container = document.getElementById('cards-container');
           container.innerHTML = ''; 
           
           if (!allAnnouncements || allAnnouncements.length === 0) {
               container.innerHTML = '<div class="text-center text-[10px] font-mono text-muted mt-20 tracking-widest">SYSTEM: NO DATA</div>';
               return;
           }
   
           loadMore();
           window.addEventListener('scroll', onScroll, { passive: true });
   
       } catch (error) {
           document.getElementById('cards-container').innerHTML = 
               '<div class="text-center text-red-400 font-mono text-xs mt-10">CONNECTION SECURE<br>Rate Limit or Network Error</div>';
       }
   }
   
   function handleSearch(query) {
       if (!query) activeList = [...allAnnouncements];
       else {
           activeList = allAnnouncements.filter(item => 
               item.title.toLowerCase().includes(query) || 
               item.body.toLowerCase().includes(query) ||
               item.date.toLowerCase().includes(query)
           );
       }
       displayedCount = 0;
       document.getElementById('cards-container').innerHTML = '';
       document.getElementById('end-message').classList.add('hidden');
       
       if (activeList.length === 0) {
           document.getElementById('cards-container').innerHTML = '<div class="text-center text-gray-500 mt-10 text-sm">No results.</div>';
       } else {
           loadMore();
       }
   }
   
   function loadMore() {
       if (isLoading || displayedCount >= activeList.length) return;
       isLoading = true;
   
       const container = document.getElementById('cards-container');
       const nextBatch = activeList.slice(displayedCount, displayedCount + BATCH_SIZE);
       const fragment = document.createDocumentFragment();
   
       nextBatch.forEach((item, index) => {
           const card = document.createElement('div');
           card.className = 'glass-card';
   
           let linksHtml = '';
           if (item.links && item.links.length > 0) {
               item.links.forEach(link => {
                   linksHtml += `
                       <a href="${link}" target="_blank" rel="noopener noreferrer" class="link-btn">
                           <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"></path></svg>
                           DOWNLOAD FILE
                       </a>`;
               });
           }
   
           let sourceBtn = '';
           if (item.source) {
               sourceBtn = `
                   <div class="source-link-container">
                       <a href="${item.source}" target="_blank" rel="noopener noreferrer" class="text-[10px] font-mono text-gray-500 hover:text-blue-400 flex items-center transition-colors gap-1">
                           OPEN ON UNIV-BEJAIA.DZ
                           <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"></path></svg>
                       </a>
                   </div>
               `;
           }
   
           card.innerHTML = `
               <div class="flex flex-col items-center mb-4">
                   <span class="announcement-date">📅 ${item.date}</span>
                   <h3 class="announcement-title">${item.title}</h3>
                   <div class="w-12 h-1 bg-blue-500/30 rounded-full mt-2"></div>
               </div>
               <div class="announcement-body">${item.body}</div>
               ${linksHtml}
               ${sourceBtn}
           `;
           fragment.appendChild(card);
       });
   
       container.appendChild(fragment);
       displayedCount += nextBatch.length;
       isLoading = false;
   
       if (displayedCount >= activeList.length) {
           document.getElementById('end-message').classList.remove('hidden');
       }
   }
   
   // --- OPTIMIZED SCROLL HANDLER ---
   function onScroll() {
       if (!ticking) {
           window.requestAnimationFrame(() => {
               performScrollLogic();
               ticking = false;
           });
           ticking = true;
       }
   }
   
   function performScrollLogic() {
       const currentScroll = window.scrollY;
       const header = document.getElementById('main-header');
       const searchBar = document.getElementById('search-bar-container');
   
       // --- FIXED LOGIC HERE ---
       // If scrolling down, hide the INPUT BAR, but DO NOT call hideSearchBarUI().
       // We want the Cancel Button to remain in the header if it was already there.
       if (currentScroll > 10 && searchBar.classList.contains('search-visible')) {
           searchBar.classList.remove('search-visible');
           document.getElementById('search-input').blur();
           document.getElementById('bottom-nav').classList.remove('slide-down-hidden');
           // Note: We deliberately do NOT hide the #header-cancel-btn here.
       }
   
       // Header Slide Up/Down logic
       if (currentScroll > lastScrollTop && currentScroll > 50) {
           header.classList.add('slide-up-hidden');
       } else {
           header.classList.remove('slide-up-hidden');
       }
       
       lastScrollTop = currentScroll <= 0 ? 0 : currentScroll;
   
       // Infinite Scroll
       if ((window.innerHeight + window.scrollY) >= document.body.offsetHeight - 800) {
           loadMore();
       }
   }
   
   // --- SYSTEM ---
   function switchTab(tab) {
       const home = document.getElementById('page-home');
       const settings = document.getElementById('page-settings');
       const btnHome = document.getElementById('tab-home');
       const btnSet = document.getElementById('tab-settings');
   
       if (tab === 'home') {
           home.classList.remove('hidden'); settings.classList.add('hidden');
           btnHome.classList.add('active'); btnSet.classList.remove('active');
           window.scrollTo(0,0);
       } else {
           home.classList.add('hidden'); settings.classList.remove('hidden');
           btnSet.classList.add('active'); btnHome.classList.remove('active');
       }
   }
   
   function toggleTheme() {
       const isLight = document.body.classList.toggle('light-mode');
       localStorage.setItem('theme', isLight ? 'light' : 'dark');
       updateThemeUI(isLight);
   }
   
   function updateThemeUI(isLight) {
       const switchEl = document.getElementById('theme-switch');
       isLight ? switchEl.classList.add('active') : switchEl.classList.remove('active');
   }
   
   function toggleNotifications() {
       const switchEl = document.getElementById('notif-switch');
       if (switchEl.classList.contains('active')) {
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
       isEnabled ? switchEl.classList.add('active') : switchEl.classList.remove('active');
   }