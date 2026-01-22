let allAnnouncements = [];
let displayedCount = 0;
const BATCH_SIZE = 15;
let isLoading = false;

// --- INITIALIZATION ---
document.addEventListener("DOMContentLoaded", () => {
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme === 'light') {
        document.body.classList.add('light-mode');
        updateThemeUI(true);
    }
    
    const notifState = localStorage.getItem('notifications');
    if (localStorage.getItem('notifications') === 'true') {
        updateNotifUI(true);
    }

    initApp();
});

// --- CORE LOGIC ---
async function initApp() {
    try {
        // FIX: Added timestamp to prevent caching old data
        const timestamp = new Date().getTime();
        const response = await fetch(`/api/announcements?t=${timestamp}`);
        allAnnouncements = await response.json();
        
        const container = document.getElementById('cards-container');
        container.innerHTML = ''; 
        
        if (allAnnouncements.length === 0) {
            container.innerHTML = '<div class="text-center text-gray-500 mt-20">Waiting for data...</div>';
            return;
        }

        loadMore();
        window.addEventListener('scroll', handleScroll);

    } catch (error) {
        console.error("Error:", error);
        // Better error message
        document.getElementById('cards-container').innerHTML = 
            '<div class="text-center text-red-400 mt-20 text-sm">Connection Error.<br>Pull down to refresh.</div>';
    }
}

function loadMore() {
    if (isLoading || displayedCount >= allAnnouncements.length) return;
    isLoading = true;

    const container = document.getElementById('cards-container');
    const nextBatch = allAnnouncements.slice(displayedCount, displayedCount + BATCH_SIZE);

    nextBatch.forEach((item, index) => {
        const card = document.createElement('div');
        card.className = 'glass-card';
        card.style.animationDelay = `${index * 0.05}s`;

        let linksHtml = '';
        if (item.links && item.links.length > 0) {
            item.links.forEach(link => {
                linksHtml += `
                    <a href="${link}" class="link-btn">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"></path></svg>
                        Open Attachment
                    </a>`;
            });
        }

        card.innerHTML = `
            <div class="flex flex-col items-center mb-4">
                <span class="announcement-date">📅 ${item.date}</span>
                <h3 class="announcement-title">${item.title}</h3>
                <div class="w-12 h-1 bg-blue-500/30 rounded-full mt-2"></div>
            </div>
            
            <div class="announcement-body">
                ${item.body}
            </div>
            
            ${linksHtml}
        `;
        container.appendChild(card);
    });

    displayedCount += nextBatch.length;
    isLoading = false;

    if (displayedCount >= allAnnouncements.length) {
        document.getElementById('end-message').classList.remove('hidden');
        window.removeEventListener('scroll', handleScroll);
    }
}

function handleScroll() {
    if ((window.innerHeight + window.scrollY) >= document.body.offsetHeight - 500) {
        loadMore();
    }
}

// --- NAVIGATION ---
function switchTab(tab) {
    const homePage = document.getElementById('page-home');
    const settingsPage = document.getElementById('page-settings');
    const btnHome = document.getElementById('tab-home');
    const btnSettings = document.getElementById('tab-settings');

    if (tab === 'home') {
        homePage.classList.remove('hidden');
        settingsPage.classList.add('hidden');
        btnHome.classList.add('active', 'text-blue-500');
        btnHome.classList.remove('text-gray-500');
        btnSettings.classList.remove('active', 'text-blue-500');
        btnSettings.classList.add('text-gray-500');
        window.scrollTo(0, 0);
    } else {
        homePage.classList.add('hidden');
        settingsPage.classList.remove('hidden');
        btnSettings.classList.add('active', 'text-blue-500');
        btnSettings.classList.remove('text-gray-500');
        btnHome.classList.remove('active', 'text-blue-500');
        btnHome.classList.add('text-gray-500');
    }
}

// --- SETTINGS LOGIC ---
function toggleTheme() {
    const isLight = document.body.classList.toggle('light-mode');
    localStorage.setItem('theme', isLight ? 'light' : 'dark');
    updateThemeUI(isLight);
}

function updateThemeUI(isLight) {
    const switchBg = document.getElementById('theme-switch');
    const dot = document.getElementById('theme-dot');
    
    if (isLight) {
        switchBg.classList.remove('bg-gray-700');
        switchBg.classList.add('bg-blue-600');
        dot.style.transform = 'translateX(20px)';
    } else {
        switchBg.classList.remove('bg-blue-600');
        switchBg.classList.add('bg-gray-700');
        dot.style.transform = 'translateX(0)';
    }
}

function toggleNotifications() {
    const current = localStorage.getItem('notifications') === 'true';
    const newState = !current;
    
    localStorage.setItem('notifications', newState.toString());
    updateNotifUI(newState);
    
    if (newState && "Notification" in window) {
        Notification.requestPermission();
    }
}

function updateNotifUI(isEnabled) {
    const switchBg = document.getElementById('notif-switch');
    const dot = document.getElementById('notif-dot');
    
    if (isEnabled) {
        switchBg.classList.remove('bg-gray-700');
        switchBg.classList.add('bg-green-500');
        dot.style.transform = 'translateX(20px)';
    } else {
        switchBg.classList.remove('bg-green-500');
        switchBg.classList.add('bg-gray-700');
        dot.style.transform = 'translateX(0)';
    }
}
