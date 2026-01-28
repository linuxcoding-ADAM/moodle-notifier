/* =========================================
   ST AFFICHAGE - SECURE CORE
   Build: 2026.1.13 (OWASP Compliant)
   ========================================= */

   let allAnnouncements = [];
   let activeList = [];
   let displayedCount = 0;
   const BATCH_SIZE = 15; // Keeps the app fast by loading 15 items at a time
   let isLoading = false;
   let lastScrollTop = 0;
   let ticking = false; 
   
   document.addEventListener("DOMContentLoaded", () => {
       // Theme
       const savedTheme = localStorage.getItem('theme');
       if (savedTheme === 'light') {
           document.body.classList.add('light-mode');
           updateThemeUI(true);
       }
   
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
       
       bar.classList.add('search-visible');
       bottomNav.classList.add('slide-down-hidden');

       const cancelBtn = document.getElementById('header-cancel-btn');
       if(cancelBtn) {
           cancelBtn.classList.remove('opacity-0', 'pointer-events-none', 'scale-90');
       }
       
       input.focus();
   }
   
   function hideSearchBarUI() {
       document.getElementById('search-bar-container').classList.remove('search-visible');
       document.getElementById('search-input').blur();
       document.getElementById('bottom-nav').classList.remove('slide-down-hidden');

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
           document.getElementById('cards-container').innerHTML = `
                <div class="flex flex-col items-center justify-center mt-20">
                    <div class="text-center text-red-400 font-mono text-xs mb-4">CONNECTION ERROR</div>
                    <button onclick="window.location.reload()" class="px-6 py-2 bg-blue-600 rounded-full text-white font-bold text-xs shadow-lg active:scale-95 transition-transform">
                        RETRY CONNECTION
                    </button>
                </div>`;
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
   
       nextBatch.forEach((item) => {
           const card = document.createElement('div');
           card.className = 'glass-card';
   
           let linksHtml = '';
           if (item.links && item.links.length > 0) {
               item.links.forEach(link => {
                   linksHtml += `
                       <a href="${link}" target="_blank" rel="external" class="link-btn" onclick="gtag('event', 'download_file', {'file_url': '${link}'})">
                           <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"></path></svg>
                           DOWNLOAD FILE
                       </a>`;
               });
           }
   
           let sourceBtn = '';
           if (item.source) {
               sourceBtn = `
                   <a href="${item.source}" target="_blank" rel="external" class="source-btn">
                       <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"></path></svg>
                       OPEN ON E-LEARNING
                   </a>
               `;
           }
   
           // UPDATED: Use ID for sharing to grab full content
           card.innerHTML = `
               <div class="flex flex-col items-center mb-4">
                   <span class="announcement-date">${item.date}</span>
                   <h3 class="announcement-title">${item.title}</h3>
                   <div class="w-12 h-1 bg-blue-500/30 rounded-full mt-2"></div>
               </div>
               <div class="announcement-body">${item.body}</div>
               
               ${linksHtml}

               <!-- SHARE BUTTON UPDATED -->
               <button onclick="triggerShare('${item.id}')" class="share-btn">
                   <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z"></path></svg>
                   SHARE INFO
               </button>

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

   // --- UPDATED SHARE LOGIC ---
   function triggerShare(id) {
       // Find the specific item from our data list
       const item = activeList.find(i => i.id === id);
       if (!item) return;

       // 1. Convert HTML body to plain text
       const tempDiv = document.createElement("div");
       tempDiv.innerHTML = item.body;
       let plainBody = tempDiv.innerText || tempDiv.textContent || "";
       
       // Clean up excessive newlines
       plainBody = plainBody.replace(/\n\s*\n/g, '\n').trim();

       // 2. Prepare Links
       let linksText = "";
       if(item.links && item.links.length > 0) {
           linksText = "\n\n🔗 Attachments:\n" + item.links.join("\n");
       }

       // 3. Construct the full message
       const shareText = `📅 *${item.date}*\n\n📢 *${item.title}*\n\n${plainBody}${linksText}\n\n📲 via ST Affichage App`;

       // 4. Send Analytics
       if(typeof gtag !== 'undefined') {
           gtag('event', 'share_click', {'content_type': 'announcement'});
       }

       // 5. Try Native Share, Fallback to Clipboard (for APK)
       if (navigator.share) {
           navigator.share({
               title: item.title,
               text: shareText
           }).catch(err => {
               // Fallback if user cancels or API fails
               copyToClipboard(shareText);
           });
       } else {
           // APK WebView usually goes here
           copyToClipboard(shareText);
       }
   }

   function copyToClipboard(text) {
       navigator.clipboard.writeText(text).then(() => {
           alert("Announcement copied! You can now paste it.");
       }).catch(err => {
           console.error('Clipboard failed', err);
       });
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
   
       if (currentScroll > 10 && searchBar.classList.contains('search-visible')) {
           searchBar.classList.remove('search-visible');
           document.getElementById('search-input').blur();
           document.getElementById('bottom-nav').classList.remove('slide-down-hidden');
       }
   
       if (currentScroll > lastScrollTop && currentScroll > 50) {
           header.classList.add('slide-up-hidden');
       } else {
           header.classList.remove('slide-up-hidden');
       }
       
       lastScrollTop = currentScroll <= 0 ? 0 : currentScroll;
   
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

   function hardReloadApp() {
       const btn = event.currentTarget;
       btn.style.opacity = '0.5';
       setTimeout(() => {
           window.location.reload(true);
       }, 300);
   }

   function contactDev() {
       window.location.href = "mailto:adammila92592@gmail.com?subject=ST%20Affichage%20Bug%20Report";
   }