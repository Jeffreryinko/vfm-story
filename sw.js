/* sw.js — 홈화면 앱(PWA)용. 앱 껍데기는 미리 저장, 데이터는 네트워크 우선 + 실패하면 마지막 저장본. */
const VER = "vfm-v70-joy";
const SHELL = ["./", "./index.html", "./iyagi/", "./iyagi/index.html", "./history/", "./history/index.html", "./brain/", "./brain/index.html", "./book/", "./book/index.html", "./box/", "./box/index.html",
  "./assets/claude-shim.js", "./assets/deck.js", "./assets/trendcard.js", "./assets/mix.js", "./assets/shell.js", "./assets/wikigal.js", "./assets/polish.css", "./assets/sync.js", "./assets/sync-config.js", "./assets/apple.css", "./assets/hot.js", "./assets/history-player.js", "./assets/history-player.css", "./assets/wikithumb.js", "./manifest.webmanifest"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(VER).then(c => c.addAll(SHELL).catch(() => {})).then(() => self.skipWaiting()));
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== VER).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET" || new URL(req.url).origin !== location.origin) return;
  // 원문(orig)은 크니까 저장하지 않고 그대로
  if (req.url.includes("/data/iyagi/orig/") || req.url.includes("_more.json") || req.url.includes("/data/history/s/") || req.url.includes("/data/book/w/") || req.url.includes("/data/book/src/")) return;
  // 라디오 소리 파일은 저장하지 않고 그대로 (이어 듣기·되감기가 되게)
  if (req.url.includes("/data/radio/") && req.url.endsWith(".mp3")) return;
  // 화면(HTML)은 브라우저 저장본(최대 10분)을 건너뛰고 늘 서버에 새로 확인 — 올린 직후에도 바로 바뀌게
  const fresh = req.mode === "navigate" || req.url.endsWith(".html") || req.url.endsWith("/") || req.url.includes("/data/");
  e.respondWith(
    fetch(req, fresh ? { cache: "no-cache" } : undefined).then(res => {
      if (res.ok) caches.open(VER).then(c => c.put(req, res.clone()));
      return res;
    }).catch(() => caches.match(req).then(hit => hit || caches.match("./index.html")))
  );
});
