/* =========================================
   ST AFFICHAGE - SECURE CORE
   ========================================= */

let allAnnouncements = [];
let activeList = [];
let displayedCount = 0;
const BATCH_SIZE = 15;
let isLoading = false;

let currentLang = localStorage.getItem('target-language') || 'en';
let translatedCache = {}; 
let currentShareText = ""; 

const DOM = {};

document.addEventListener("DOMContentLoaded", () => {
    DOM.cardsContainer = document.getElementById('cards-container');
    DOM.endMessage = document.getElementById('end-message');
    DOM.searchInput = document.getElementById('search-input');
    DOM.searchBarContainer = document.getElementById('search-bar-container');
    DOM.headerCancelBtn = document.getElementById('header-cancel-btn');
    DOM.backToTop = document.getElementById('back-to-top');

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
        ? allAnnouncements.filter(item => item.title.toLowerCase().includes(query) || (item.description && item.description.toLowerCase().includes(query)) || item.date.toLowerCase().includes(query))
        : [...allAnnouncements];
        
    displayedCount = 0;
    DOM.cardsContainer.innerHTML = '';
    DOM.endMessage.classList.add('hidden');
    
    if (activeList.length === 0) DOM.cardsContainer.innerHTML = '<div class="text-center text-gray-500 mt-10 text-sm">No results.</div>';
    else loadMore();
}

// 🟢 NEW STRUCTURED UI RENDERER 🟢
function loadMore() {
    if (isLoading || displayedCount >= activeList.length) return;
    isLoading = true;
    
    const nextBatch = activeList.slice(displayedCount, displayedCount + BATCH_SIZE);
    const fragment = document.createDocumentFragment();

    // Map keys to pretty SVGs for the Grid
    const iconMap = {
        'Module': '<svg class="w-3.5 h-3.5 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"></path></svg>',
        'Type': '<svg class="w-3.5 h-3.5 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z"></path></svg>',
        'Date': '<svg class="w-3.5 h-3.5 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"></path></svg>',
        'Groupe': '<svg class="w-3.5 h-3.5 text-yellow-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"></path></svg>',
        'Salle': '<svg class="w-3.5 h-3.5 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z"></path></svg>'
    };

    nextBatch.forEach((item) => {
        const card = document.createElement('div');
        card.className = 'glass-card flex flex-col items-start w-full';

        // 1. Build Meta Grid
        let metaHtml = '';
        if (item.meta && Object.keys(item.meta).length > 0) {
            let rows = '';
            for (const [key, value] of Object.entries(item.meta)) {
                let icon = iconMap[key] || '<svg class="w-3.5 h-3.5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>';
                rows += `
                    <div class="meta-row">
                        <span class="meta-label">${icon} ${key}:</span>
                        <span class="meta-value">${value}</span>
                    </div>
                `;
            }
            metaHtml = `<div class="meta-grid">${rows}</div>`;
        }

        // 2. Buttons & Images
        let linksHtml = item.links.map(link => `
            <a href="${link}" target="_blank" rel="external" class="link-btn">
                <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" viewBox="0 0 24 24"><path d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path></svg>
                Télécharger le fichier
            </a>`).join('');

        let imagesHtml = item.images.map(img => `
            <div class="announcement-media relative mt-2 mb-2 w-full rounded-2xl overflow-hidden border border-white/5 shadow-md">
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

        // 3. Assemble Card
        card.innerHTML = `
            <div class="flex justify-between items-center w-full mb-3">
                <div class="flex items-center gap-2">
                    <span class="text-xs text-accent-color opacity-80">📢</span>
                    <h3 id="title-${item.id}" class="announcement-title w-full m-0">${item.title}</h3>
                </div>
                <div class="flex items-center gap-1.5 flex-shrink-0">
                    <button id="btn-trans-${item.id}" onclick="translateAnnouncement('${item.id}')" class="w-8 h-8 flex items-center justify-center rounded-full active:scale-90 transition-transform shadow-sm" style="background-color: var(--date-bg); color: var(--accent-color);">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" viewBox="0 0 24 24"><path d="M3 5h12M9 3v2m1.048 9.5A18.022 18.022 0 016.412 9m6.088 9h7M11 21l5-10 5 10M12.751 5C11.783 10.77 8.07 15.61 3 18.129"></path></svg>
                    </button>
                    <button onclick="shareAnnouncement('${item.id}')" class="w-8 h-8 flex items-center justify-center rounded-full active:scale-90 transition-transform shadow-sm" style="background-color: var(--date-bg); color: var(--accent-color);">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" viewBox="0 0 24 24"><circle cx="18" cy="5" r="3"></circle><circle cx="6" cy="12" r="3"></circle><circle cx="18" cy="19" r="3"></circle><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"></line><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"></line></svg>
                    </button>
                </div>
            </div>
            
            ${metaHtml}
            
            <div id="body-${item.id}" class="announcement-body w-full">${item.description}</div>
            
            <div class="announcement-footer w-full">
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                Affiché le : ${item.date}
            </div>
            
            ${imagesHtml}${linksHtml}${sourceBtn}
        `;
        fragment.appendChild(card);
    });

    DOM.cardsContainer.appendChild(fragment);
    displayedCount += nextBatch.length;
    isLoading = false;
    
    if (displayedCount >= activeList.length) DOM.endMessage.classList.remove('hidden');
}

// 🟢 GOOGLE TRANSLATION ENGINE (Translates Title and Pure Description) 🟢
function toggleLanguage() {
    currentLang = currentLang === 'en' ? 'ar' : 'en';
    localStorage.setItem('target-language', currentLang);
    updateLangIndicator();
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

    if (titleEl.hasAttribute('data-translated')) {
        titleEl.innerHTML = item.title;
        bodyEl.innerHTML = item.description;
        titleEl.removeAttribute('data-translated');
        titleEl.classList.remove('text-rtl');
        bodyEl.classList.remove('text-rtl');
        btnEl.style.opacity = '1';
        return;
    }

    btnEl.style.opacity = '0.5';

    if (!translatedCache[id]) {
        try {
            let safeTitle = item.title;
            let safeBody = item.description.replace(/<br\s*[\/]?>/gi, '\n');

            const resTitle = await fetch(`https://translate.googleapis.com/translate_a/single?client=gtx&sl=fr&tl=${currentLang}&dt=t&q=${encodeURIComponent(safeTitle)}`);
            const resBody = await fetch(`https://translate.googleapis.com/translate_a/single?client=gtx&sl=fr&tl=${currentLang}&dt=t&q=${encodeURIComponent(safeBody)}`);
            
            const dataTitle = await resTitle.json();
            const dataBody = await resBody.json();

            let translatedTitle = '';
            dataTitle[0].forEach(t => { if(t[0]) translatedTitle += t[0] });

            let translatedBody = '';
            dataBody[0].forEach(t => { if(t[0]) translatedBody += t[0] });

            translatedBody = translatedBody.replace(/\n/g, '<br>');
            translatedCache[id] = { title: translatedTitle, body: translatedBody };
        } catch (e) {
            showToast("Translation Failed. Check internet.");
            btnEl.style.opacity = '1';
            return;
        }
    }

    titleEl.innerHTML = translatedCache[id].title;
    bodyEl.innerHTML = translatedCache[id].body;
    titleEl.setAttribute('data-translated', 'true');
    btnEl.style.opacity = '1';

    if (currentLang === 'ar') {
        titleEl.classList.add('text-rtl');
        bodyEl.classList.add('text-rtl');
    }
}

// 🟢 HYBRID SHARE SYSTEM 🟢
async function shareAnnouncement(id) {
    const item = allAnnouncements.find(a => a.id === id);
    if (!item) return;

    let cleanBody = item.description.replace(/<[^>]*>?/gm, '').trim();
    currentShareText = `📢 *${item.title}*\n\n${cleanBody}\n\n🔗 *Lien E-learning :*\n${item.source || 'https://elearning.univ-bejaia.dz'}\n\n📱 *Téléchargez l'application ST Affichage :*\nhttps://stbejaia.up.railway.app/install`;

    try {
        if (navigator.share) await navigator.share({ title: item.title, text: currentShareText });
        else throw new Error("No navigator.share");
    } catch (err) {
        openShareSheet();
    }
}

function openShareSheet() {
    const sheet = document.getElementById('share-sheet');
    const overlay = document.getElementById('share-overlay');
    overlay.style.visibility = 'visible';
    setTimeout(() => { overlay.classList.remove('opacity-0'); sheet.classList.remove('translate-y-full'); }, 10);
}

function closeShareSheet() {
    const sheet = document.getElementById('share-sheet');
    const overlay = document.getElementById('share-overlay');
    sheet.classList.add('translate-y-full');
    overlay.classList.add('opacity-0');
    setTimeout(() => { overlay.style.visibility = 'hidden'; }, 400);
}

function shareTo(platform) {
    const encodedText = encodeURIComponent(currentShareText);
    if (platform === 'whatsapp') window.location.href = `https://api.whatsapp.com/send?text=${encodedText}`;
    else if (platform === 'telegram') window.location.href = `tg://msg?text=${encodedText}`;
    else if (platform === 'copy') {
        navigator.clipboard.writeText(currentShareText);
        showToast("Text copied to clipboard!");
    }
    closeShareSheet();
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
