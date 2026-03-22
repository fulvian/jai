/**
 * PersAn jAI Service Worker
 * 
 * Gestisce le notifiche push in background.
 */

self.addEventListener('push', function (event) {
    if (!event.data) return;

    try {
        const payload = event.data.json();
        const title = payload.title || 'Nuovo messaggio da jAI';
        const options = {
            body: payload.body,
            icon: payload.icon || '/logo.png', // Assicurati che esista
            badge: '/badge.png',
            data: payload.data || {},
        };

        event.waitUntil(
            self.registration.showNotification(title, options)
        );
    } catch (e) {
        console.error('Failed to handle push event:', e);
    }
});

self.addEventListener('notificationclick', function (event) {
    event.notification.close();

    // Apri l'app e naviga alla sessione se presente
    const sessionId = event.notification.data?.sessionId;
    const urlToOpen = sessionId ? `/?sessionId=${sessionId}` : '/';

    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (clientList) {
            for (let i = 0; i < clientList.length; i++) {
                const client = clientList[i];
                if (client.url.includes(location.origin) && 'focus' in client) {
                    return client.focus();
                }
            }
            if (clients.openWindow) {
                return clients.openWindow(urlToOpen);
            }
        })
    );
});
