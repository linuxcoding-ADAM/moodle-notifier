let allAnnouncements = [];
let displayedCount = 0;
const BATCH_SIZE = 15;
let isLoading = false;

// 1. Fetch Data
async function initApp() {
    try {
        const response = await fetch('/api/announcements');
        allAnnouncements = await response.json();
        
        const container = document.getElementById('cards-container');
        container.innerHTML = ''; // Clear loader
        
        if (allAnnouncements.length === 0) {
            container.innerHTML = '<div class="text-center text-gray-500 mt-20">Waiting for data...</div>';
            return;
        }

        // Load first batch
        loadMore();

        // Attach Scroll Listener for Infinite Scroll
        window.addEventListener('scroll', handleScroll);

    } catch (error) {
        console.error("Error:", error);
    }
}

// 2. Load More Logic (Lazy Loading)
function loadMore() {
    if (isLoading || displayedCount >= allAnnouncements.length) return;
    isLoading = true;

    const container = document.getElementById('cards-container');
    const nextBatch = allAnnouncements.slice(displayedCount, displayedCount + BATCH_SIZE);

    nextBatch.forEach((item, index) => {
        const card = document.createElement('div');
        card.className = 'glass-card';
        // Stagger animation slightly
        card.style.animationDelay = `${index * 0.05}s`;

        let linksHtml = '';
        if (item.links && item.links.length > 0) {
            linksHtml = `<div class="mt-2">`;
            item.links.forEach(link => {
                linksHtml += `
                    <a href="${link}" class="link-btn">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path></svg>
                        Attachment
                    </a>`;
            });
            linksHtml += `</div>`;
        }

        card.innerHTML = `
            <div class="flex justify-between items-start mb-3">
                <span class="card-tag">Academics</span>
                <span class="text-xs text-gray-500 font-medium">${item.date}</span>
            </div>
            <h3 class="text-[1.05rem] font-bold text-white mb-3 leading-snug">${item.title}</h3>
            <div class="announcement-body opacity-90">${item.body}</div>
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

// 3. Tab Switching
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

// 4. Notification Toggle (Visual Logic)
function toggleNotifications() {
    const switchBg = document.getElementById('notif-switch');
    const dot = document.getElementById('notif-dot');
    const isEnabled = switchBg.classList.contains('bg-green-500');

    if (isEnabled) {
        switchBg.classList.remove('bg-green-500');
        switchBg.classList.add('bg-gray-700');
        dot.style.transform = 'translateX(0)';
        localStorage.setItem('notifications', 'false');
    } else {
        switchBg.classList.remove('bg-gray-700');
        switchBg.classList.add('bg-green-500');
        dot.style.transform = 'translateX(20px)';
        localStorage.setItem('notifications', 'true');
        // Request permission if supported
        if ("Notification" in window) Notification.requestPermission();
    }
}

// Initialize Notification State
document.addEventListener("DOMContentLoaded", () => {
    initApp();
    if (localStorage.getItem('notifications') === 'true') {
        const switchBg = document.getElementById('notif-switch');
        const dot = document.getElementById('notif-dot');
        switchBg.classList.remove('bg-gray-700');
        switchBg.classList.add('bg-green-500');
        dot.style.transform = 'translateX(20px)';
    }
});
