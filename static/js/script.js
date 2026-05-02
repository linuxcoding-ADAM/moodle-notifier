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

// 🟢 NEW STRICT TEXT ARCHITECTURE RENDERER 🟢
function loadMore() {
    if (isLoading || displayedCount >= activeList.length) return;
    isLoading = true;
    
    const nextBatch = activeList.slice(displayedCount, displayedCount + BATCH_SIZE);
    const fragment = document.createDocumentFragment();

    nextBatch.forEach((item) => {
        const card = document.createElement('div');
        card.className = 'glass-card flex flex-col items-start w-full relative';

        // 1. Build Meta Info (Aligned text without icons)
        let metaHtml = '';
        if (item.meta && Object.keys(item.meta).length > 0) {
            let rows = '';
            for (const [key, value] of Object.entries(item.meta)) {
                rows += `
                    <div class="flex text-[0.85rem] mb-1.5 leading-snug">
                        <span class="w-20 flex-shrink-0" style="color: var(--text-muted);">${key}:</span>
                        <span class="font-semibold text-white">${value}</span>
                    </div>
                `;
            }
            metaHtml = `<div class="w-full pt-4 pb-2">${rows}</div>`;
        } else {
            // Add a small spacer if there's no meta to keep things clean
            metaHtml = `<div class="h-4"></div>`;
        }

        // 2. Links & Images
        let linksHtml = item.links.map(link => `
            <a href="${link}" target="_blank" rel="external" class="link-btn mt-4">
                Télécharger le fichier
            </a>`).join('');

        let imagesHtml = item.images.map(img => `
            <div class="w-full rounded-xl overflow-hidden border border-white/5 mt-4">
                <img src="${img}" alt="Announcement Image" class="w-full h-auto object-cover" loading="lazy">
            </div>`).join('');

        let sourceBtn = item.source ? `
            <a href="${item.source}" target="_blank" rel="external" class="source-btn mt-2">
                Ouvrir sur e-learning
            </a>` : '';

        // 3. Assemble Card Structure (Strict layout)
        card.innerHTML = `
            <!-- Action Buttons (Translate & Share floating top right) -->
            <div class="absolute top-5 right-5 flex items-center gap-1.5 z-10">
                <button id="btn-trans-${item.id}" onclick="translateAnnouncement('${item.id}')" class="w-7 h-7 flex items-center justify-center rounded-full bg-white/5 border border-white/10 active:scale-90 transition-transform">
                    <svg class="w-3.5 h-3.5 text-gray-300" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M3 5h12M9 3v2m1.048 9.5A18.022 18.022 0 016.412 9m6.088 9h7M11 21l5-10 5 10M12.751 5C11.783 10.77 8.07 15.61 3 18.129"></path></svg>
                </button>
                <button onclick="shareAnnouncement('${item.id}')" class="w-7 h-7 flex items-center justify-center rounded-full bg-white/5 border border-white/10 active:scale-90 transition-transform">
                    <svg class="w-3.5 h-3.5 text-gray-300" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="18" cy="5" r="3"></circle><circle cx="6" cy="12" r="3"></circle><circle cx="18" cy="19" r="3"></circle><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"></line><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"></line></svg>
                </button>
            </div>

            <!-- TITLE BLOCK (Thick Top & Bottom Borders) -->
            <div class="w-full border-t-2 border-white/20 pt-4 pb-4 mt-8 border-b-2">
                <h3 id="title-${item.id}" class="announcement-title m-0 pr-16">${item.title}</h3>
            </div>

            <!-- META BLOCK -->
            ${metaHtml}

            <!-- DESCRIPTION BLOCK (Thin Top & Bottom Borders) -->
            <div class="w-full border-t border-white/10 pt-4 pb-4 border-b mb-4">
                <div id="body-${item.id}" class="announcement-body">${item.description}</div>
            </div>

            <!-- FOOTER BLOCK -->
            <div class="text-[0.75rem] font-mono text-gray-400 mt-2">
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

// 🟢 GOOGLE TRANSLATION ENGINE 🟢
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

// 🟢 HYBRID SHARE SYSTEM (FORMATTED TEXT) 🟢
async function shareAnnouncement(id) {
    const item = allAnnouncements.find(a => a.id === id);
    if (!item) return;

    // Build the Meta Text nicely for sharing
    let metaText = '';
    if (item.meta && Object.keys(item.meta).length > 0) {
        for (const [key, value] of Object.entries(item.meta)) {
            // Adds padding to make keys align perfectly in text format
            metaText += `${key.padEnd(10, ' ')} : ${value}\n`;
        }
        metaText += '\n──────────────────────\n';
    }

    let cleanBody = item.description.replace(/<[^>]*>?/gm, '').trim();
    
    // Exact requested text formatting!
    currentShareText = `━━━━━━━━━━━━━━━━━━━━━━\n${item.title}\n━━━━━━━━━━━━━━━━━━━━━━\n\n${metaText}${cleanBody}\n\n──────────────────────\nAffiché le : ${item.date}\n\n[ 🔗 Lien : ${item.source || 'https://elearning.univ-bejaia.dz'} ]\n[ 📱 App : https://stbejaia.up.railway.app/install ]`;

    try {
        if (navigator.share) await navigator.share({ text: currentShareText });
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
        showToast("Texte copié !");
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
