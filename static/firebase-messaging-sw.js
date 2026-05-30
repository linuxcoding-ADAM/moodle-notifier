importScripts('https://www.gstatic.com/firebasejs/10.8.1/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/10.8.1/firebase-messaging-compat.js');

// User should add config here if they want the SW to fetch messages while in background.
// firebase.initializeApp({ ... });
// const messaging = firebase.messaging();

self.addEventListener('notificationclick', function(event) {
    event.notification.close();

    const data = event.notification.data || {};
    let url = '/';

    // Route to the correct department page
    if (data.click_action) {
        url = data.click_action;
    } else if (data.dept_slug) {
        url = '/' + data.dept_slug;
    }

    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then((windowClients) => {
            // Check if there is already a window/tab open with the target URL
            for (let i = 0; i < windowClients.length; i++) {
                const client = windowClients[i];
                if (client.url.includes(url) && 'focus' in client) {
                    return client.focus();
                }
            }
            // If not, open a new window
            if (clients.openWindow) {
                return clients.openWindow(url);
            }
        })
    );
});
