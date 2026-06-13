// 데일리 플래너 서비스워커 — 앱 셸 캐시 (오프라인 시 화면 골격 유지)
const CACHE = "planner-v22";
const SHELL = ["/", "/static/style.css", "/static/app.js", "/static/icon-192.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).catch(() => {}));
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
  );
  self.clients.claim();
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET") return;        // 쓰기 요청은 그대로 통과
  if (url.pathname.startsWith("/api/")) return;   // API는 항상 네트워크
  // 정적 셸: 네트워크 우선, 실패 시 캐시
  e.respondWith(
    fetch(e.request)
      .then((r) => {
        if (r.ok && (url.pathname === "/" || url.pathname.startsWith("/static/"))) {
          const copy = r.clone();
          caches.open(CACHE).then((c) => c.put(e.request, copy));
        }
        return r;
      })
      .catch(() => caches.match(e.request))
  );
});

// 웹푸시 수신 → 알림 표시
self.addEventListener("push", (e) => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch (err) {}
  const title = d.title || "Daymate";
  e.waitUntil(self.registration.showNotification(title, {
    body: d.body || "",
    icon: "/static/icon-192.png",
    badge: "/static/icon-192.png",
    data: { url: d.url || "/" },
  }));
});

// 알림 클릭 → 앱 열기/포커스
self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || "/";
  e.waitUntil(
    self.clients.matchAll({ type: "window" }).then((cl) => {
      for (const c of cl) { if ("focus" in c) return c.focus(); }
      if (self.clients.openWindow) return self.clients.openWindow(url);
    })
  );
});
