/* trail.js — '배운 길' (세 자판기 공통, shell.js 가 불러요). 탭·사이트를 가리지 않고 본 것을 한 줄로 이어 기록해요.
 *  vfm.trail({ id, app, t, u, kw, kind })  : 지금 보는 것 하나를 기록 (같은 id 면 횟수·시각만 갱신)
 *      app  : sisa·deal·ai·learn·iyagi·history·brain·book·mental·baedat …   t: 제목   u: 다시 여는 주소(절대)   kw: 낱말 몇 개
 *  머문 시간(d, 초)은 화면이 보이는 동안만 셈 → 다른 걸 보거나 화면을 내리면 앞의 것에 더해요.
 *  vfm.trailList()  : 최근 순 목록      vfm.trailDeep(sec=40) : 오래(=제대로) 본 것만
 *  저장: localStorage 'vfm:trail' (최근 400개) — 같은 주소(jeffreryinko.github.io)라 이야기·사람 자판기·생각 지도(thinkingForMe)가 함께 읽고,
 *        로그인하면 sync.js 가 기기 사이로 맞춰요(목록은 id 기준으로 합쳐짐).
 */
(function () {
  "use strict";
  if (window.__vfmTrail) return; window.__vfmTrail = 1;
  var V = window.vfm = window.vfm || {}, KEY = "vfm:trail", MAX = 400;
  var load = function () { try { var a = JSON.parse(localStorage.getItem(KEY) || "[]"); return Array.isArray(a) ? a : []; } catch (e) { return []; } };
  var save = function (a) { a.sort(function (x, y) { return (y.at || 0) - (x.at || 0); }); try { localStorage.setItem(KEY, JSON.stringify(a.slice(0, MAX))); } catch (e) { } };
  var cur = null, t0 = 0;
  function flush() {
    if (!cur || !t0) return;
    var s = Math.min(600, Math.round((Date.now() - t0) / 1000)); t0 = document.hidden ? 0 : Date.now();
    if (s < 2) return;
    var a = load(), x = a.find(function (y) { return y.id === cur; });
    if (x) { x.d = (x.d || 0) + s; save(a); }
  }
  V.trail = function (o) {
    if (!o || !o.id || !o.t) return;
    var id = String(o.app || "x") + ":" + String(o.id).slice(0, 120);
    if (id === cur) return;
    flush();
    var a = load(), x = a.find(function (y) { return y.id === id; }), now = Date.now();
    var u = o.u || location.href;
    try { u = new URL(u, location.href).href; } catch (e) { }
    if (x) { x.n = (x.n || 1) + 1; x.at = now; x.t = String(o.t).slice(0, 140); x.u = u; }
    else a.push({ id: id, app: o.app || "x", kind: o.kind || "", t: String(o.t).slice(0, 140), u: u, kw: (o.kw || []).slice(0, 5), at: now, first: now, n: 1, d: 0 });
    save(a); cur = id; t0 = document.hidden ? 0 : now;
    try { document.dispatchEvent(new CustomEvent("vfm:trail", { detail: { id: id } })); } catch (e) { }
  };
  V.trailList = load;
  V.trailDeep = function (sec) { sec = sec || 40; return load().filter(function (x) { return (x.d || 0) >= sec || (x.n || 0) >= 3; }); };
  document.addEventListener("visibilitychange", function () { if (document.hidden) flush(); else if (cur) t0 = Date.now(); });
  addEventListener("pagehide", flush);
  addEventListener("hashchange", function () { setTimeout(function () { if (cur && !document.querySelector(".vdk-card")) { flush(); } }, 0); });
  // 넘겨보기 카드(deck.js)는 여기서 한꺼번에 기록 — 카드를 보여 줄 때마다 vfm:deckshow 가 와요
  document.addEventListener("vfm:deckshow", function (e) {
    var x = e.detail || {}; if (!x.key || !x.title) return;
    V.trail({ id: x.key, app: x.app || window.VFM_APP || "x", t: x.title, u: x.url, kind: "card" });
  });
  /* ── '이어서' 띠: 홈 화면들이 vfm.trailStrip() 으로 그려요 ── */
  var O = "https://jeffreryinko.github.io";
  var APPS = {
    "sisa": ["📰", "시사", "/vendingForMe/sisa/"], "deal": ["🤝", "딜", "/vendingForMe/deal/"], "ai": ["🤖", "AI", "/vendingForMe/ai/"],
    "sisa-learn": ["🌏", "세상 읽기 교실", "/vendingForMe/sisa/learn/"], "deal-learn": ["💼", "딜 교실", "/vendingForMe/deal/learn/"],
    "ai-learn": ["🎓", "AI 교실", "/vendingForMe/ai/learn/"], "gicho-learn": ["📘", "기초 교실", "/vendingForMe/gicho/"],
    "iyagi": ["📖", "이야기", "/vfm-story/iyagi/"], "history": ["🏛️", "세계사", "/vfm-story/history/#ts"], "brain": ["🧠", "뇌 실험·사례", "/vfm-story/brain/#st"],
    "book": ["📚", "책", "/vfm-story/book/"], "tools": ["🧰", "도구", "/vendingForMe/tools/"], "mental": ["🎩", "멘탈", "/vfm-mind/mental/"], "baedat": ["💬", "배댓", "/vfm-mind/baedat/"]
  };
  V.trailApps = APPS;
  var esc = function (x) { return String(x == null ? "" : x).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); };
  var css = document.createElement("style");
  css.textContent = ".vt{margin:14px 0 6px}.vt-k{display:flex;justify-content:space-between;align-items:baseline;margin:0 2px 8px;font-size:13px;font-weight:700;color:var(--ap-label2,#6e6e73)}.vt-k a{font-weight:600;color:var(--ap-blue,#0A6CFF);text-decoration:none;font-size:12.5px}" +
    ".vt-main{display:flex;gap:12px;align-items:center;padding:14px 14px;border-radius:16px;background:var(--ap-surface,#fff);box-shadow:inset 0 0 0 .5px var(--ap-sep,rgba(0,0,0,.1));text-decoration:none;color:inherit}" +
    ".vt-main .ic{flex:none;width:40px;height:40px;border-radius:12px;display:grid;place-items:center;font-size:21px;background:var(--ap-fill,rgba(120,120,128,.12))}.vt-main b{display:block;font-size:15.5px;line-height:1.35;letter-spacing:-.01em}.vt-main small{display:block;font-size:12px;color:var(--ap-label2,#6e6e73);margin-top:2px}.vt-main i{margin-left:auto;font-style:normal;color:var(--ap-label3,#aeaeb2);font-size:18px}" +
    ".vt-row{display:flex;gap:8px;overflow-x:auto;scrollbar-width:none;margin-top:8px}.vt-row a{flex:none;max-width:72%;display:flex;gap:6px;align-items:center;padding:8px 11px;border-radius:12px;background:var(--ap-fill,rgba(120,120,128,.1));text-decoration:none;color:inherit;font-size:13px;line-height:1.3}.vt-row a span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.vt-row a.new{background:color-mix(in srgb,var(--ap-blue,#0A6CFF) 12%,transparent);color:var(--ap-blue,#0A6CFF);font-weight:600}" +
    ".vt-st{display:flex;gap:12px;margin:8px 2px 0;font-size:12px;color:var(--ap-label2,#6e6e73)}.vt-st b{color:var(--ap-label,#111);font-variant-numeric:tabular-nums}";
  (document.head || document.documentElement).appendChild(css);
  var ago = function (t) { var m = Math.round((Date.now() - t) / 6e4); return m < 1 ? "방금" : m < 60 ? m + "분 전" : m < 1440 ? Math.round(m / 60) + "시간 전" : Math.round(m / 1440) + "일 전"; };
  V.trailStrip = function () {
    var a = load(), wk = Date.now() - 7 * 864e5, recent = a.filter(function (x) { return x.at > wk; });
    var seen = {}; recent.forEach(function (x) { seen[x.app] = 1; });
    var fresh = Object.keys(APPS).filter(function (k) { return !seen[k]; });
    var day = Math.floor((Date.now() + 9 * 3600e3) / 864e5); fresh = fresh.slice(day % Math.max(1, fresh.length)).concat(fresh.slice(0, day % Math.max(1, fresh.length))).slice(0, 2);
    var top = a[0], others = [], used = {};
    if (top) used[top.app] = 1;
    for (var i = 1; i < a.length && others.length < 3; i++) if (!used[a[i].app]) { used[a[i].app] = 1; others.push(a[i]); }
    var ap = function (k) { return APPS[k] || ["✦", k, "/vendingForMe/"]; };
    var h = '<div class="vt"><p class="vt-k"><span>이어서 보기</span><a href="' + O + '/thinkingForMe/">생각 지도에서 보기 ›</a></p>';
    if (top) h += '<a class="vt-main" href="' + esc(top.u) + '"><span class="ic">' + ap(top.app)[0] + "</span><span><b>" + esc(top.t) + "</b><small>" + esc(ap(top.app)[1]) + " · " + ago(top.at) + (top.d ? " · " + Math.max(1, Math.round(top.d / 60)) + "분 봄" : "") + '</small></span><i>›</i></a>';
    else h += '<a class="vt-main" href="' + O + '/vendingForMe/sisa/learn/"><span class="ic">🌱</span><span><b>첫 걸음을 기다려요</b><small>무엇이든 하나 읽으면 여기서 이어져요</small></span><i>›</i></a>';
    h += '<div class="vt-row">' + others.map(function (x) { return '<a href="' + esc(x.u) + '">' + ap(x.app)[0] + "<span>" + esc(x.t) + "</span></a>"; }).join("") +
      fresh.map(function (k) { return '<a class="new" href="' + O + APPS[k][2] + '">' + APPS[k][0] + "<span>" + esc(APPS[k][1]) + " 가 보기</span></a>"; }).join("") + "</div>";
    var deep = recent.filter(function (x) { return (x.d || 0) >= 40; }).length;
    h += '<p class="vt-st"><span>이번 주 <b>' + recent.length + "</b>개 봄</span><span>제대로 읽음 <b>" + deep + "</b></span><span>다녀간 곳 <b>" + Object.keys(seen).length + "</b>/" + Object.keys(APPS).length + "</span></p></div>";
    return h;
  };
  (window.__vfmTQ || []).splice(0).forEach(function (o) { V.trail(o); });          // 이 파일이 늦게 와도 먼저 본 것을 놓치지 않게
  try { document.dispatchEvent(new CustomEvent("vfm:trailready")); } catch (e) { }
})();
