/* =========================================
   ST AFFICHAGE - SECURE CORE
   ========================================= */

let allAnnouncements = [];
let activeList = [];
let displayedCount = 0;
const BATCH_SIZE = 15;
let isLoading = false;
let lastScrollTop = 0;
let ticking = false; 

document.addEventListener("DOMContentLoaded", () => {
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme === 'light') {
        document.body.classList.add('light-mode');
        updateThemeUI(true);
    }
    initApp();

    const searchInput = document.getElementById('search-input');
    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            const raw = e.target.value.toLowerCase();
            const safeQuery = raw.replace(/[<>{}\"\'\/]/g, ''); 
            handleSearch(safeQuery);
        });
    }
});

function toggleSearch() {
    document.getElementById('search-bar-container').classList.add('search-visible');
    const cancelBtn = document.getElementById('header-cancel-btn');
    if(cancelBtn) cancelBtn.classList.remove('opacity-0', 'pointer-events-none', 'scale-90');
    document.getElementById('search-input').focus();
}

function hideSearchBarUI() {
    document.getElementById('search-bar-container').classList.remove('search-visible');
    document.getElementById('search-input').blur();
    const cancelBtn = document.getElementById('header-cancel-btn');
    if(cancelBtn) cancelBtn.classList.add('opacity-0', 'pointer-events-none', 'scale-90');
}

function cancelSearch() {
    hideSearchBarUI();
    document.getElementById('search-input').value = '';
    handleSearch('');
}

async function initApp() {
    try {
        const timestamp = new Date().getTime();
        const response = await fetch(`/api/announcements?t=${timestamp}`);
        if (!response.ok) throw new Error("API Limit");
        allAnnouncements = await response.json();
        activeList = [...allAnnouncements];
        document.getElementById('cards-container').innerHTML = ''; 
        if (!allAnnouncements || allAnnouncements.length === 0) {
            document.getElementById('cards-container').innerHTML = '<div class="text-center text-[10px] font-mono text-muted mt-20">SYSTEM: NO DATA</div>';
            return;
        }
        loadMore();
    } catch (error) {
        document.getElementById('cards-container').innerHTML = `
            <div class="flex flex-col items-center justify-center mt-20">
                <div class="text-center text-red-400 font-mono text-xs mb-4">CONNECTION ERROR</div>
                <button onclick="window.location.reload()" class="px-6 py-2 bg-blue-600 rounded-full text-white font-bold text-xs shadow-lg active:scale-95">RETRY</button>
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
    if (activeList.length === 0) document.getElementById('cards-container').innerHTML = '<div class="text-center text-gray-500 mt-10 text-sm">No results.</div>';
    else loadMore();
}

function loadMore() {
    if (isLoading || displayedCount >= activeList.length) return;
    isLoading = true;
    const container = document.getElementById('cards-container');
    const nextBatch = activeList.slice(displayedCount, displayedCount + BATCH_SIZE);
    const fragment = document.createDocumentFragment();

    nextBatch.forEach((item) => {
        const card = document.createElement('div');
        card.className = 'glass-card flex flex-col items-start w-full';

        // Links
        let linksHtml = '';
        if (item.links && item.links.length > 0) {
            item.links.forEach(link => {
                linksHtml += `
                    <a href="${link}" target="_blank" rel="external" class="link-btn">
                        <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" viewBox="0 0 24 24"><path d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path></svg>
                        Télécharger le fichier
                    </a>`;
            });
        }

        // Images 
        let imagesHtml = '';
        if (item.images && item.images.length > 0) {
            item.images.forEach(img => {
                imagesHtml += `
                    <div class="relative mt-4 mb-2 w-full rounded-2xl overflow-hidden border border-white/5 shadow-md">
                        <img src="${img}" alt="Announcement Image" class="w-full h-auto object-cover" loading="lazy">
                        <a href="${img}" download="ST_Affichage_Image" target="_blank" rel="noopener noreferrer" class="absolute top-3 right-3 w-10 h-10 flex items-center justify-center rounded-full bg-black/50 backdrop-blur-md border border-white/20 text-white transition-transform active:scale-90 shadow-lg z-10">
                            <svg class="w-5 h-5" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" viewBox="0 0 24 24">
                                <path d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path>
                            </svg>
                        </a>
                    </div>
                `;
            });
        }

        // Source E-learning Button
        let sourceBtn = '';
        if (item.source) {
            sourceBtn = `
                <a href="${item.source}" target="_blank" rel="external" class="source-btn">
                    <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" viewBox="0 0 24 24"><path d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"></path></svg>
                    Ouvrir sur e-learning
                </a>`;
        }

        card.innerHTML = `
            <!-- 🟢 HEADER WITH DATE AND SHARE BUTTON 🟢 -->
            <div class="flex justify-between items-start w-full mb-1">
                <span class="announcement-date" style="margin-bottom: 0;">${item.date}</span>
                
                <button onclick="shareAnnouncement('${item.id}')" class="w-8 h-8 flex items-center justify-center rounded-full bg-white/5 border border-white/10 text-gray-400 hover:text-white active:scale-90 transition-all shadow-sm" aria-label="Partager">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" viewBox="0 0 24 24">
                        <path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"></path>
                        <polyline points="16 6 12 2 8 6"></polyline>
                        <line x1="12" y1="2" x2="12" y2="15"></line>
                    </svg>
                </button>
            </div>

            <h3 class="announcement-title w-full">${item.title}</h3>
            <div class="announcement-body mt-2 w-full">${item.body}</div>
            
            ${imagesHtml} 
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

// 🟢 NEW SHARE FUNCTION 🟢
async function shareAnnouncement(id) {
    const item = allAnnouncements.find(a => a.id === id);
    if (!item) return;

    // Create a clean preview of the text (strip HTML tags if any sneaked through, limit length)
    let cleanBody = item.body.replace(/<[^>]*>?/gm, '');
    if(cleanBody.length > 150) cleanBody = cleanBody.substring(0, 150) + "...";

    const shareData = {
        title: item.title,
        text: `📢 ${item.title}\n\n${cleanBody}\n\nVoir plus sur ST Affichage :`,
        url: item.source || window.location.origin
    };

    try {
        if (navigator.share) {
            await navigator.share(shareData);
        } else {
            // Fallback if browser doesn't support native share (e.g. older desktop)
            navigator.clipboard.writeText(`${shareData.text} ${shareData.url}`);
            alert("Lien copié dans le presse-papier !");
        }
    } catch (err) {
        console.log("Share canceled or failed", err);
    }
}

// Infinite Scroll
window.addEventListener('scroll', () => {
    if ((window.innerHeight + window.scrollY) >= document.body.offsetHeight - 800) {
        loadMore();
    }
}, { passive: true });

function toggleTheme() {
    const isLight = document.body.classList.toggle('light-mode');
    localStorage.setItem('theme', isLight ? 'light' : 'dark');
    updateThemeUI(isLight);
}

function updateThemeUI(isLight) {
    const switchEl = document.getElementById('theme-switch');
    if(switchEl) {
        isLight ? switchEl.classList.add('active') : switchEl.classList.remove('active');
    }
}

function hardReloadApp() {
    setTimeout(() => { window.location.reload(true); }, 200);
}

function contactDev() {
    window.location.href = "mailto:adam.mila.dev@gmail.com?subject=ST%20Affichage%20Bug%20Report";
}
