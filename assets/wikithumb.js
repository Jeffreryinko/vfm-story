/* wikithumb.js — 위키백과 대표 사진을 카드에 붙이기 (토큰 0, 서버 0)
 *  <img data-wt="ko:문서 제목"> 처럼 써 두면, 화면에 보일 때 위키백과에 50개씩 묶어 물어 작은 사진(썸네일)을 채움
 *  · 사진이 없거나 못 받으면 그 img 를 지움 (원래 그림·자리 그대로)
 *  · 한 번 알아낸 결과는 이 폰에 기억 (vfm:wt, 최대 4,000개) → 다시 물어보지 않음
 *  · 사진 크기는 500px: 위키미디어가 미리 만들어 두는 크기. (640px 로 물으면 960px 짜리를 줘서 3배 무거웠음)
 *  · 위키백과 사진은 대부분 위키미디어 공용의 자유 이용 사진
 */
(function () {
  "use strict";
  if (window.WT) return;                              // 두 번 실려도 한 번만
  var KEY = "vfm:wt", MEM = {};
  try { MEM = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) { MEM = {}; }
  var saveT = null;
  function save() {
    clearTimeout(saveT); saveT = setTimeout(function () {
      var ks = Object.keys(MEM); if (ks.length > 4000) ks.slice(0, ks.length - 3000).forEach(function (k) { delete MEM[k]; });
      try { localStorage.setItem(KEY, JSON.stringify(MEM)); } catch (e) { }
    }, 500);
  }
  var queue = {}, timer = null, WANT = [];           // queue[lang] = Set(제목)
  function apply(img) {
    var k = img.getAttribute("data-wt"), v = MEM[k];
    if (v === undefined) return false;
    /* 예전에 기억한 큰 사진 주소(640·960px)는 500px 로 바꿔 씀 */
    if (v) { img.decoding = "async"; img.src = v.replace(/(\/thumb\/.+\/)(?:640|960)px-/, function (m, a) { return a + "500px-"; }); img.removeAttribute("data-wt"); img.classList.add("wt-on"); }
    else { var p = img.parentElement; img.remove(); if (p) p.classList.add("wt-none"); }
    return true;
  }
  function flush() {
    timer = null;
    Object.keys(queue).forEach(function (lang) {
      var titles = Array.from(queue[lang]); delete queue[lang];
      for (var i = 0; i < titles.length; i += 50) ask(lang, titles.slice(i, i + 50));
    });
  }
  function ask(lang, titles) {
    var u = "https://" + lang + ".wikipedia.org/w/api.php?action=query&prop=pageimages&piprop=thumbnail&pithumbsize=500&redirects=1&format=json&formatversion=2&origin=*&titles=" + encodeURIComponent(titles.join("|"));
    fetch(u).then(function (r) { return r.json(); }).then(function (j) {
      var q = j.query || {}, map = {};
      (q.normalized || []).forEach(function (n) { map[n.to] = (map[n.to] || []).concat([n.from]); });
      (q.redirects || []).forEach(function (n) { map[n.to] = (map[n.to] || []).concat([n.from], map[n.from] || []); });
      var got = {};
      (q.pages || []).forEach(function (p) {
        var src = p.thumbnail && p.thumbnail.source || "";
        [p.title].concat(map[p.title] || []).forEach(function (t) { got[t] = src; });
      });
      titles.forEach(function (t) { var k = lang + ":" + t; MEM[k] = got[t] || ""; if (WARM[k] && MEM[k]) preload(MEM[k]); });
      save(); paint();
    }).catch(function () { });                       // 실패하면 그대로 (다음에 다시)
  }
  var WARM = {};
  function preload(u) { var p = new Image(); p.decoding = "async"; p.src = u.replace(/(\/thumb\/.+\/)(?:640|960)px-/, function (m, a) { return a + "500px-"; }); }
  function warm(k) {                                   // 아직 화면에 없는 카드의 위키 사진을 미리 (다음 카드용)
    if (!k || WARM[k]) return; WARM[k] = 1;
    var v = MEM[k]; if (v) return preload(v); if (v === "") return;
    var i = k.indexOf(":"); if (i < 1) return;
    (queue[k.slice(0, i)] = queue[k.slice(0, i)] || new Set()).add(k.slice(i + 1));
    if (!timer) timer = setTimeout(flush, 120);
  }
  function want(img) {
    if (apply(img)) return;
    var k = img.getAttribute("data-wt"), i = k.indexOf(":"); if (i < 1) return;
    var lang = k.slice(0, i), t = k.slice(i + 1);
    (queue[lang] = queue[lang] || new Set()).add(t);
    if (!timer) timer = setTimeout(flush, 120);
  }
  var io = "IntersectionObserver" in window ? new IntersectionObserver(function (es) {
    es.forEach(function (e) {
      if (!e.isIntersecting) return; io.unobserve(e.target);
      var t = e.target; if (t.tagName === "IMG") return want(t);
      t._wtObs = 0; Array.prototype.forEach.call(t.querySelectorAll("img[data-wt]"), want);
    });
  }, { rootMargin: "600px 0px" }) : null;
  function paint() {
    document.querySelectorAll("img[data-wt]").forEach(function (img) {
      if (apply(img)) return;
      if (img._wtSeen) return; img._wtSeen = 1;
      if (!io) return want(img);
      if (img.getClientRects().length) return io.observe(img);
      var par = img.parentElement; while (par && !par.getClientRects().length) par = par.parentElement;   // 숨겨진 사진 → 보이는 부모 칸
      if (!par) { img._wtSeen = 0; return; }
      if (!par._wtObs) { par._wtObs = 1; io.observe(par); }
    });
  }
  new MutationObserver(function () { clearTimeout(paint._t); paint._t = setTimeout(paint, 60); }).observe(document.documentElement, { childList: true, subtree: true });
  document.addEventListener("error", function (e) { var t = e.target; if (t && t.classList && t.classList.contains("wt-on")) { var p = t.parentElement; t.remove(); if (p) p.classList.add("wt-none"); } }, true);
  window.WT = { paint: paint, warm: warm, wikiOf: function (url) {             // 위키백과 주소 → "ko:제목"
    var m = /^https?:\/\/([a-z\-]+)\.(?:m\.)?wikipedia\.org\/wiki\/([^#?]+)/.exec(url || ""); if (!m) return "";
    try { return m[1] + ":" + decodeURIComponent(m[2]).replace(/_/g, " "); } catch (e) { return ""; }
  } };
  if (document.readyState !== "loading") paint(); else document.addEventListener("DOMContentLoaded", paint);
})();
