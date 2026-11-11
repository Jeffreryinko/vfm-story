/* 위키백과 사진 모음 — 화면에 <div data-gal="ko:문서 제목"></div> 이 생기면 그 문서에 실린 그림들을 가로로 넘겨 보는 띠로 채워요.
   로봇·토큰 0 (보는 사람의 브라우저가 위키백과에서 바로 받아요). 그림이 2장보다 적으면 자리 없이 사라져요.
   아이콘·깃발·로고·소리·영상은 빼고, 많아야 12장. 사진을 누르면 위키백과의 그 그림 설명(저작권 표시)으로 가요. */
(function () {
  "use strict";
  var MEM = {}, JUNK = /(Flag_of|Coat_of_arms|[Ii]con|[Ll]ogo|Commons|Wikisource|Wiktionary|Wikiquote|Wikidata|Ambox|Question_book|Symbol_|Edit-|Padlock|Disambig|Stub|Crystal_|Nuvola|OOjs|_pog\.|Location_dot|Loudspeaker|Speaker_|Gnome-|Emblem-|Text_document|Folder_|Portal-|Increase|Decrease|Steady)|\.svg$/;
  var esc = function (s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]; }); };
  var css = ".wgal{margin:14px 0 6px}.wgal .wgs{display:flex;gap:8px;overflow-x:auto;scroll-snap-type:x mandatory;padding:2px 0 8px;-webkit-overflow-scrolling:touch}" +
    ".wgal a{flex:none;width:min(68vw,260px);scroll-snap-align:start;text-decoration:none;color:inherit}.wgal img{width:100%;height:170px;object-fit:cover;border-radius:10px;display:block;background:rgba(127,127,127,.15)}" +
    ".wgal span{display:block;font-size:12px;line-height:1.4;opacity:.75;margin-top:4px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}.wgal .wgn{font-size:11.5px;opacity:.6;margin:0}";
  var st = document.createElement("style"); st.textContent = css; document.head.appendChild(st);
  function load(key) {
    if (MEM[key]) return MEM[key];
    var i = key.indexOf(":"), lang = key.slice(0, i), t = key.slice(i + 1);
    return MEM[key] = fetch("https://" + lang + ".wikipedia.org/api/rest_v1/page/media-list/" + encodeURIComponent(t.replace(/ /g, "_")))
      .then(function (r) { return r.ok ? r.json() : { items: [] }; })
      .then(function (d) {
        return (d.items || []).filter(function (x) { return x.type === "image" && x.showInGallery !== false && x.srcset && x.srcset.length && !JUNK.test(x.title || ""); }).slice(0, 12).map(function (x) {
          var src = x.srcset[0].src; if (src.indexOf("//") === 0) src = "https:" + src;
          return { src: src, cap: x.caption && x.caption.text || "", href: "https://" + lang + ".wikipedia.org/wiki/" + encodeURIComponent(x.title) };
        });
      }).catch(function () { delete MEM[key]; return []; });
  }
  function fill(el) {
    if (el._gal) return; el._gal = 1; var key = el.getAttribute("data-gal"); if (!key || key.indexOf(":") < 1) return;
    load(key).then(function (a) {
      if (!el.isConnected) return;
      if (a.length < 2) { el.remove(); return; }
      el.className = "wgal";
      el.innerHTML = '<div class="wgs">' + a.map(function (x) { return '<a href="' + esc(x.href) + '" target="_blank" rel="noopener"><img src="' + esc(x.src) + '" alt="" loading="lazy" decoding="async">' + (x.cap ? "<span>" + esc(x.cap) + "</span>" : "") + "</a>"; }).join("") +
        '</div><p class="wgn">사진 ' + a.length + "장 · 위키백과 「" + esc(key.slice(key.indexOf(":") + 1)) + "」 문서에 실린 그림 · 누르면 출처와 저작권 표시</p>";
    });
  }
  function scan() { document.querySelectorAll("[data-gal]").forEach(fill); }
  new MutationObserver(function () { clearTimeout(scan._t); scan._t = setTimeout(scan, 80); }).observe(document.documentElement, { childList: true, subtree: true });
  if (document.readyState !== "loading") scan(); else document.addEventListener("DOMContentLoaded", scan);
})();
