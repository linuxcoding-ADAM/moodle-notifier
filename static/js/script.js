/* =========================================
   ST AFFICHAGE - SECURE CORE
   ========================================= */

let allAnnouncements = [];
let activeList = [];
let displayedCount = 0;
const BATCH_SIZE = 15;
let isLoading = false;

// 🟢 NEW: TRANSLATION CACHE & STATE 🟢
let currentLang = localStorage.getItem('target-language') || 'en'; // default English
let translatedCache = {}; // Stores { id: { title: "...", body: "..." } }

const DOM = {};

document.addEventListener("DOMContentLoaded", () => {
    DOM.cardsContainer = document.getElementById('cards-container');
    DOM.endMessage = document.getElementById('end-message');
    DOM.searchInput = document.getElementById('search-input');
    DOM.searchBarContainer = document.getElementById('search-bar-container');
    DOM.headerCancelBtn = document.getElementById('header-cancel-btn');
    DOM.backToTop = document.getElementById('back-to-top');

    // Init Language Indicator
    updateLangIndicator();
    initApp();

    if (DOM.searchInput) {
        DOM.searchInput.addEventListener('input', (e) => {
            const raw = e.target.value.toLowerCase();
            handleSearch(raw.replace(/[<>{}\"\'\/]/g, '')); 
        });
    }
});

function toggleSearch() {
    DOM.searchBarContainer.classList.add('search-visible');
    DOM.headerCancelBtn.classList.remove('opacity-0', 'pointer-events-none', 'scale-90');
    DOM.searchInput.focus();
}

function hideSearchBarUI() {
    DOM.searchBarContainer.classList.remove('search-visible');
    DOM.searchInput.blur();
    DOM.headerCancelBtn.classList.add('opacity-0', 'pointer-events-none', 'scale-90');
}

function cancelSearch() {
    hideSearchBarUI();
    DOM.searchInput.value = '';
    handleSearch('');
}

async function initApp() {
    try {
        const response = await fetch(`/api/announcements?t=${Date.now()}`);
        if (!response.ok) throw new Error("API Limit");
        
        allAnnouncements = await response.json();
        activeList = [...allAnnouncements];
        DOM.cardsContainer.innerHTML = ''; 
        
        if (!allAnnouncements.length) {
            DOM.cardsContainer.innerHTML = '<div class="text-center text-[10px] font-mono text-muted mt-20">SYSTEM: NO DATA</div>';
            return;
        }
        loadMore();
    } catch (error) {
        DOM.cardsContainer.innerHTML = `
            <div class="flex flex-col items-center justify-center mt-20">
                <div class="text-center text-red-400 font-mono text-xs mb-4">CONNECTION ERROR</div>
                <button onclick="window.location.reload()" class="px-6 py-2 bg-blue-600 rounded-full text-white font-bold text-xs shadow-lg active:scale-95">RETRY</button>
            </div>`;
    }
}

function handleSearch(query) {
    activeList = query 
        ? allAnnouncements.filter(item => item.title.toLowerCase().includes(query) || item.body.toLowerCase().includes(query) || item.date.toLowerCase().includes(query))
        : [...allAnnouncements];
        
    displayedCount = 0;
    DOM.cardsContainer.innerHTML = '';
    DOM.endMessage.classList.add('hidden');
    
    if (activeList.length === 0) DOM.cardsContainer.innerHTML = '<div class="text-center text-gray-500 mt-10 text-sm">No results.</div>';
    else loadMore();
}

function loadMore() {
    if (isLoading || displayedCount >= activeList.length) return;
    isLoading = true;
    
    const nextBatch = activeList.slice(displayedCount, displayedCount + BATCH_SIZE);
    const fragment = document.createDocumentFragment();

    nextBatch.forEach((item) => {
        const card = document.createElement('div');
        card.className = 'glass-card flex flex-col items-start w-full';

        let linksHtml = item.links.map(link => `
            <a href="${link}" target="_blank" rel="external" class="link-btn">
                <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" viewBox="0 0 24 24"><path d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path></svg>
                Télécharger le fichier
            </a>`).join('');

        let imagesHtml = item.images.map(img => `
            <div class="announcement-media relative mt-4 mb-2 w-full rounded-2xl overflow-hidden border border-white/5 shadow-md">
                <img src="${img}" alt="Announcement Image" class="w-full h-auto object-cover" loading="lazy">
                <a href="${img}" download="ST_Affichage_Image" target="_blank" rel="noopener noreferrer" class="absolute top-3 right-3 w-10 h-10 flex items-center justify-center rounded-full bg-black/50 backdrop-blur-md border border-white/20 text-white transition-transform active:scale-90 shadow-lg z-10">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" viewBox="0 0 24 24"><path d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path></svg>
                </a>
            </div>`).join('');

        let sourceBtn = item.source ? `
            <a href="${item.source}" target="_blank" rel="external" class="source-btn">
                <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" viewBox="0 0 24 24"><path d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"></path></svg>
                Ouvrir sur e-learning
            </a>` : '';

        // 🟢 ADDED TRANSLATE BUTTON NEXT TO SHARE 🟢
        card.innerHTML = `
            <div class="flex justify-between items-center w-full mb-3">
                <span class="announcement-date" style="margin-bottom: 0;">${item.date}</span>
                
                <div class="flex items-center gap-2">
                    <button id="btn-trans-${item.id}" onclick="translateAnnouncement('${item.id}')" class="w-8 h-8 flex items-center justify-center rounded-full active:scale-90 transition-transform shadow-sm" style="background-color: var(--date-bg); color: var(--accent-color);" aria-label="Translate">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" viewBox="0 0 24 24">
                            <path d="M3 5h12M9 3v2m1.048 9.5A18.022 18.022 0 016.412 9m6.088 9h7M11 21l5-10 5 10M12.751 5C11.783 10.77 8.07 15.61 3 18.129"></path>
                        </svg>
                    </button>
                    <button onclick="shareAnnouncement('${item.id}')" class="w-8 h-8 flex items-center justify-center rounded-full active:scale-90 transition-transform shadow-sm" style="background-color: var(--date-bg); color: var(--accent-color);" aria-label="Partager">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" viewBox="0 0 24 24"><circle cx="18" cy="5" r="3"></circle><circle cx="6" cy="12" r="3"></circle><circle cx="18" cy="19" r="3"></circle><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"></line><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"></line></svg>
                    </button>
                </div>
            </div>
            
            <h3 id="title-${item.id}" class="announcement-title w-full">${item.title}</h3>
            <div id="body-${item.id}" class="announcement-body mt-1 w-full">${item.body}</div>
            
            ${imagesHtml}${linksHtml}${sourceBtn}
        `;
        fragment.appendChild(card);
    });

    DOM.cardsContainer.appendChild(fragment);
    displayedCount += nextBatch.length;
    isLoading = false;
    
    if (displayedCount >= activeList.length) DOM.endMessage.classList.remove('hidden');
}

// 🟢 NEW TRANSLATION ENGINE 🟢
function toggleLanguage() {
    currentLang = currentLang === 'en' ? 'ar' : 'en';
    localStorage.setItem('target-language', currentLang);
    updateLangIndicator();
    
    // Clear translation cache so if they click translate again, it translates to the new language
    translatedCache = {}; 
    showToast(`Language set to ${currentLang === 'en' ? 'English' : 'Arabic'}`);
}

function updateLangIndicator() {
    const indicator = document.getElementById('lang-indicator');
    if (indicator) indicator.innerText = currentLang === 'en' ? 'ENG' : 'عرب';
}

async function translateAnnouncement(id) {
    const item = allAnnouncements.find(a => a.id === id);
    if (!item) return;

    const titleEl = document.getElementById(`title-${id}`);
    const bodyEl = document.getElementById(`body-${id}`);
    const btnEl = document.getElementById(`btn-trans-${id}`);

    // If already translated, revert to French
    if (titleEl.hasAttribute('data-translated')) {
        titleEl.innerHTML = item.title;
        bodyEl.innerHTML = item.body;
        titleEl.removeAttribute('data-translated');
        titleEl.classList.remove('text-rtl');
        bodyEl.classList.remove('text-rtl');
        btnEl.style.opacity = '1';
        return;
    }

    // Loading State
    btnEl.style.opacity = '0.5';

    // If we already fetched it in this language, use cache
    if (!translatedCache[id]) {
        try {
            // Clean text for API, replacing <br> with newlines so formatting doesn't break
            let safeTitle = item.title.replace(/<[^>]*>?/gm, '').trim();
            let safeBody = item.body.replace(/<br\s*[\/]?>/gi, '\n').replace(/<[^>]*>?/gm, '').trim();

            const resTitle = await fetch(`https://translate.googleapis.com/translate_a/single?client=gtx&sl=fr&tl=${currentLang}&dt=t&q=${encodeURIComponent(safeTitle)}`);
            const resBody = await fetch(`https://translate.googleapis.com/translate_a/single?client=gtx&sl=fr&tl=${currentLang}&dt=t&q=${encodeURIComponent(safeBody)}`);
            
            const dataTitle = await resTitle.json();
            const dataBody = await resBody.json();

            let translatedTitle = '';
            dataTitle[0].forEach(t => { if(t[0]) translatedTitle += t[0] });

            let translatedBody = '';
            dataBody[0].forEach(t => { if(t[0]) translatedBody += t[0] });

            // Restore newlines to HTML <br>
            translatedBody = translatedBody.replace(/\n/g, '<br>');

            translatedCache[id] = { title: translatedTitle, body: translatedBody };
        } catch (e) {
            console.error("Translation failed", e);
            showToast("Translation Failed. Check internet.");
            btnEl.style.opacity = '1';
            return;
        }
    }

    // Apply Translation
    titleEl.innerHTML = translatedCache[id].title;
    bodyEl.innerHTML = translatedCache[id].body;
    titleEl.setAttribute('data-translated', 'true');
    btnEl.style.opacity = '1';

    // Right-To-Left Support for Arabic
    if (currentLang === 'ar') {
        titleEl.classList.add('text-rtl');
        bodyEl.classList.add('text-rtl');
    }
}

// 🟢 HYBRID SHARE SYSTEM 🟢
async function shareAnnouncement(id) {
    const item = allAnnouncements.find(a => a.id === id);
    if (!item) return;

    let cleanBody = item.body.replace(/<[^>]*>?/gm, '').trim();
    let shareText = `📢 *${item.title}*\n\n${cleanBody}\n\n🔗 *Lien E-learning :*\n${item.source || 'https://elearning.univ-bejaia.dz'}\n\n📱 *Téléchargez l'application ST Affichage :*\nhttps://stbejaia.up.railway.app/install`;

    try {
        if (navigator.share) {
            await navigator.share({ title: item.title, text: shareText });
        } else {
            throw new Error("No navigator.share");
        }
    } catch (err) {
        // Fallback for APK / Desktop
        const isAndroid = /android/i.test(navigator.userAgent);
        if (isAndroid) {
            window.location.href = `intent:#Intent;action=android.intent.action.SEND;type=text/plain;S.android.intent.extra.TEXT=${encodeURIComponent(shareText)};end`;
            setTimeout(() => { navigator.clipboard.writeText(shareText); showToast("Annonce copiée !"); }, 500);
        } else {
            navigator.clipboard.writeText(shareText);
            showToast("Annonce copiée dans le presse-papier !");
        }
    }
}

function showToast(message) {
    const toast = document.createElement('div');
    toast.className = 'fixed bottom-20 left-1/2 transform -translate-x-1/2 bg-white text-black px-5 py-3 rounded-full shadow-2xl z-[100] text-sm font-bold transition-all duration-300 opacity-0 translate-y-4 text-center w-max max-w-[90%]';
    toast.style.fontFamily = "'Syne', sans-serif";
    toast.innerText = message;
    document.body.appendChild(toast);
    
    setTimeout(() => toast.classList.remove('opacity-0', 'translate-y-4'), 10);
    setTimeout(() => {
        toast.classList.add('opacity-0', 'translate-y-4');
        setTimeout(() => toast.remove(), 300);
    }, 2500);
}

// OPTIMIZED SCROLL
let scrollTimeout;
window.addEventListener('scroll', () => {
    if (!scrollTimeout) {
        scrollTimeout = setTimeout(() => {
            if (window.scrollY > 300) DOM.backToTop.classList.add('visible');
            else DOM.backToTop.classList.remove('visible');
            
            if ((window.innerHeight + window.scrollY) >= document.body.offsetHeight - 800) loadMore();
            scrollTimeout = null;
        }, 100);
    }
}, { passive: true });

function hardReloadApp() { setTimeout(() => window.location.reload(true), 200); }
function contactDev() { window.location.href = "mailto:adam.mila.dev@gmail.com?subject=ST%20Affichage%20Bug%20Report"; }
