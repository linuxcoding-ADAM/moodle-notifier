async function fetchAnnouncements() {
    const container = document.getElementById('cards-container');
    container.innerHTML = '<div class="loader"></div>';

    try {
        const response = await fetch('/api/announcements');
        const data = await response.json();

        container.innerHTML = '';

        if (data.length === 0) {
            container.innerHTML = `
                <div class="text-center mt-10 p-5 bg-white/5 rounded-xl">
                    <p class="text-gray-400 text-sm">Waiting for data...</p>
                    <p class="text-xs text-gray-600 mt-2">The scraper runs every 10 mins.</p>
                </div>`;
            return;
        }

        data.forEach(item => {
            // Build Links
            let linksHtml = '';
            if (item.links && item.links.length > 0) {
                linksHtml = `<div class="mt-4 pt-3 border-t border-white/5 space-y-2">`;
                item.links.forEach(link => {
                    linksHtml += `
                        <a href="${link}" class="link-btn">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"></path></svg>
                            Open Attachment
                        </a>`;
                });
                linksHtml += `</div>`;
            }

            // Build Card
            const card = `
                <div class="glass-card animate-fade-in">
                    <div class="flex justify-between items-start mb-3">
                        <span class="card-tag">Academics</span>
                        <span class="text-xs text-gray-500 font-medium">${item.date}</span>
                    </div>
                    
                    <h3 class="text-lg font-bold text-white mb-2 leading-tight">${item.title}</h3>
                    
                    <div class="text-gray-400 text-sm leading-relaxed opacity-90">
                        ${item.body}
                    </div>
                    
                    ${linksHtml}
                </div>
            `;
            container.innerHTML += card;
        });

    } catch (error) {
        console.error(error);
        container.innerHTML = `
            <div class="text-center mt-10">
                <p class="text-red-400 text-sm">Connection Failed</p>
                <button onclick="fetchAnnouncements()" class="text-xs text-blue-500 mt-2 underline">Try Again</button>
            </div>`;
    }
}

// Load on start
document.addEventListener("DOMContentLoaded", fetchAnnouncements);
