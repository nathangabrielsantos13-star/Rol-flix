{% load static %}// Guarda só arquivos públicos do site. Páginas e fotos nunca entram no cache:
// são privadas e poderiam ficar expostas a outra pessoa no mesmo aparelho.
const CACHE = "roleflix-v8";
const OFFLINE_URL = "{% static 'offline.html' %}";
const STATIC_PREFIX = "{% get_static_prefix %}";

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE)
      // cache: "reload" evita copiar para cá uma versão velha do cache do navegador.
      .then((cache) => cache.addAll([OFFLINE_URL, "{% static 'css/style.css' %}", "{% static 'js/intro.js' %}", "{% static 'js/pwa.js' %}", "{% static 'js/nav.js' %}"].map((url) => new Request(url, { cache: "reload" }))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    const old = (await caches.keys()).filter((name) => name !== CACHE);
    await Promise.all(old.map((name) => caches.delete(name)));
    await self.clients.claim();
    if (!old.length) return;
    // Numa atualização, páginas abertas podem estar com CSS velho: recarrega para corrigir sozinho.
    // Não pode esperar a navegação aqui: ela só anda depois que esta ativação terminar.
    const pages = await self.clients.matchAll({ type: "window" });
    pages.forEach((page) => { page.navigate(page.url).catch(() => {}); });
  })());
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== location.origin) return;

  if (request.mode === "navigate") {
    event.respondWith(fetch(request).catch(() => caches.match(OFFLINE_URL)));
    return;
  }

  if (url.pathname.startsWith(STATIC_PREFIX)) {
    // Sempre confere o servidor, para visual e código nunca ficarem desencontrados.
    // O cache só responde quando não há internet.
    event.respondWith(caches.open(CACHE).then(async (cache) => {
      try {
        const response = await fetch(request, { cache: "no-cache" });
        // Respostas parciais (206) não podem ser guardadas no cache.
        if (response.status === 200) cache.put(request, response.clone());
        return response;
      } catch (error) {
        const cached = await cache.match(request);
        if (cached) return cached;
        throw error;
      }
    }));
  }
});
