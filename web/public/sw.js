// no caching: the app and api always come from the network
self.addEventListener('install', () => self.skipWaiting())
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()))

self.addEventListener('push', (e) => {
  let d = {}
  try {
    d = e.data ? e.data.json() : {}
  } catch {
    d = { title: 'Somnia', body: e.data ? e.data.text() : '' }
  }
  e.waitUntil(
    (async () => {
      const wins = await self.clients.matchAll({ type: 'window', includeUncontrolled: true })
      if (!d.force && wins.some((w) => w.focused && w.visibilityState === 'visible')) return
      await self.registration.showNotification(d.title || 'Somnia', {
        body: d.body || '',
        icon: d.icon || '/icons/icon-180.png',
        badge: '/icons/badge-96.png',
        image: d.image || undefined,
        tag: d.tag || 'somnia',
        renotify: true,
        data: { url: d.url || '/' },
      })
    })(),
  )
})

self.addEventListener('notificationclick', (e) => {
  e.notification.close()
  const url = new URL((e.notification.data && e.notification.data.url) || '/', self.location.origin).href
  e.waitUntil(
    (async () => {
      const wins = await self.clients.matchAll({ type: 'window', includeUncontrolled: true })
      for (const w of wins) {
        if (new URL(w.url).origin !== self.location.origin) continue
        await w.focus()
        return
      }
      await self.clients.openWindow(url)
    })(),
  )
})
