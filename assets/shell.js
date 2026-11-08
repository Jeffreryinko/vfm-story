/* shell.js — 자판기 공통 껍데기 (시사·이야기·AI·역사·도구·첫 화면).
 *
 *  1) 앱 전환 막대: 화면 맨 위에 [홈] [시사 | 이야기 | AI | 역사 | 도구 | 뇌] [⋯] — 크게, 애플식 분할 버튼
 *  2) 뒤로가기 한 가지 규칙 (모든 앱 공통)
 *       · 앱 안에서 화면을 옮겨도 브라우저 기록은 쌓지 않는다 (각 앱이 replaceState 로 이동)
 *       · 휴대폰 뒤로가기 = "한 단계 위로": 열린 창 닫기 → 앞 화면 → 그 앱의 첫 화면 → 자판기 첫 화면(홈)
 *       · 앱끼리 옮겨 다닐 때도 기록을 쌓지 않음 → 뒤로가기가 다른 앱으로 튀지 않음
 *       · 홈에서 뒤로가기 = 자판기를 나감
 *     각 앱은 window.vfmApp = { back(): 처리했으면 true, go(hash): 그 화면으로 } 를 내놓는다.
 *  3) 설정 시트: 마지막 갱신, 기록 내보내기·불러오기, 출처 상태
 *  4) PWA 등록
 */
(function () {
  "use strict";
  var APP = (window.vfm && window.vfm.app) || window.VFM_APP || "sisa";
  var HOME = APP === "home";
  var ROOT = HOME ? "./" : "../";
  var APPS = [["iyagi","이야기"],["history","역사"],["brain","뇌"]];
  var NAME = { home: "홈", sisa: "시사", iyagi: "이야기", ai: "AI", history: "역사", tools: "도구", brain: "뇌", baedat: "배댓", mental: "맨탈", box: "보관함" };
  try { if (!HOME) localStorage.setItem("vfm:tab", APP); } catch (e) { }

  /* ── 글 다듬기: 첫 문단 괄호 속 외국어 표기(조지아어·벵골어 등)는 폰에서 □□□ 로 깨지고 앞부분을 다 차지함 → 뺌.
       '(영어: …, 1848년 11월 10일 ~ 1925년)' 이면 날짜 부분만 남김. 한자·로마자 짧은 표기는 그대로. */
  var RARE = /[\u0370-\u03FF\u0400-\u052F\u0530-\u058F\u0590-\u05FF\u0600-\u06FF\u0700-\u08FF\u0900-\u0DFF\u0E00-\u0FFF\u1000-\u109F\u10A0-\u10FF\u1200-\u139F\u1780-\u18AF\u2C80-\u2CFF\uA500-\uA6FF\uD800-\uDFFF\u25A0-\u25FF\u2580-\u259F]/;
  var LBL = /^\s*(?:[가-힣]+\s)?[가-힣]+(?:어|문자|자|음|표기|명)\s*:/;
  function cleanText(t) {
    if (!t) return t || "";
    return String(t).replace(/\(([^()]*(?:\([^()]*\)[^()]*)*)\)/g, function (all, inner) {
      if (!LBL.test(inner) && !RARE.test(inner)) return all;
      var out = [], drop = false;
      inner.split(/\s*[;,]\s*(?![^()]*\))/).forEach(function (seg) {
        if (!seg.trim()) return;
        if (LBL.test(seg) || RARE.test(seg)) { drop = true; return; }
        if (drop && !/[가-힣\d]/.test(seg)) return;                  // 앞 표기에 이어진 영문 조각
        drop = false; out.push(seg.trim());
      });
      return out.length ? "(" + out.join(", ") + ")" : "";
    }).replace(/\s+([,.])/g, "$1").replace(/ {2,}/g, " ");
  }
  window.vfmClean = cleanText;

  /* ── 모양 (애플식, apple.css 의 색 변수를 씀) ── */
  var css = document.createElement("style");
  css.textContent =
    ".vfm-bar{position:relative;z-index:30;display:flex;align-items:center;gap:8px;max-width:720px;margin:0 auto;" +
    "padding:10px 0 6px;" +
    "font:600 15px/1 var(--ap-font);-webkit-user-select:none;user-select:none}" +
    ".vfm-bar .h{flex:none;width:40px;height:40px;border-radius:12px;border:0;background:var(--ap-fill);display:grid;place-items:center;color:var(--ap-label);cursor:pointer}" +
    ".vfm-bar .h svg{width:20px;height:20px}" +
    ".vfm-bar .h.home{width:auto;padding:0 12px 0 10px;display:flex;gap:5px;align-items:center;font:inherit;font-size:15px;font-weight:700}" +
    ".vfm-seg{flex:1;min-width:0;display:grid;grid-template-columns:repeat(" + APPS.length + ",auto);gap:1px;padding:3px;border-radius:12px;background:var(--ap-fill);height:40px}" +
    ".vfm-seg button{padding:0 4px;min-width:0}" +
    "@media (max-width:440px){.vfm-bar .h.home{width:40px;padding:0;justify-content:center;font-size:0;gap:0}.vfm-seg button{font-size:13.5px;gap:3px}}" +
    ".vfm-seg button{border:0;border-radius:9px;background:transparent;color:var(--ap-label);font:inherit;font-size:14px;letter-spacing:-.03em;white-space:nowrap;cursor:pointer;display:flex;align-items:center;justify-content:center;gap:6px;-webkit-tap-highlight-color:transparent}" +
    ".vfm-seg button i{width:8px;height:8px;border-radius:50%;display:inline-block}" +
    ".vfm-seg button[aria-current=page]{background:var(--ap-seg-on);box-shadow:0 3px 8px rgba(0,0,0,.12),0 1px 1px rgba(0,0,0,.04);font-weight:700}" +
    ".vfm-dot{width:7px;height:7px;border-radius:50%;background:var(--ap-green);display:inline-block}.vfm-dot.old{background:var(--ap-orange)}.vfm-dot.none{background:var(--ap-label3)}" +
    ".vfm-back{position:fixed;inset:0;background:rgba(0,0,0,.4);z-index:9700;display:flex;align-items:flex-end;justify-content:center;animation:vfmFade .18s ease}" +
    ".vfm-sheet{width:100%;max-width:560px;max-height:88vh;overflow:auto;background:var(--ap-bg);color:var(--ap-label);border-radius:14px 14px 0 0;" +
    "padding:8px 16px calc(env(safe-area-inset-bottom,0px) + 20px);font:15px/1.45 var(--ap-font);animation:vfmUp .26s cubic-bezier(.2,.8,.2,1)}" +
    ".vfm-sheet .grab{width:36px;height:5px;border-radius:3px;background:var(--ap-label3);margin:0 auto 10px}" +
    ".vfm-sheet h3{margin:4px 4px 14px;font-size:22px;font-weight:700;letter-spacing:-.02em}" +
    ".vfm-sheet .cap{margin:18px 16px 6px;font-size:13px;color:var(--ap-label2);text-transform:none}" +
    ".vfm-sheet .grp{background:var(--ap-surface);border-radius:12px;overflow:hidden}" +
    ".vfm-sheet .grp>*{display:flex;align-items:center;justify-content:space-between;gap:10px;width:100%;min-height:46px;padding:11px 16px;border:0;background:none;color:inherit;font:inherit;text-align:left;position:relative;cursor:pointer}" +
    ".vfm-sheet .grp>*+*::before{content:'';position:absolute;left:16px;right:0;top:0;height:.5px;background:var(--ap-sep)}" +
    ".vfm-sheet .grp .v{color:var(--ap-label2)}.vfm-sheet .grp .tint{color:var(--ap-tint)}" +
    ".vfm-sheet .foot{margin:6px 16px 0;font-size:12.5px;color:var(--ap-label2)}" +
    ".vfm-toast{position:fixed;left:50%;bottom:calc(env(safe-area-inset-bottom,0px) + 96px);transform:translateX(-50%);background:rgba(30,30,30,.92);color:#fff;" +
    "padding:10px 16px;border-radius:14px;font:500 14px/1.3 var(--ap-font);z-index:9800;-webkit-backdrop-filter:blur(20px);backdrop-filter:blur(20px)}" +
    "@keyframes vfmUp{from{transform:translateY(40px);opacity:.4}to{transform:none;opacity:1}}@keyframes vfmFade{from{opacity:0}to{opacity:1}}" +
    ".vfm-pill{display:none!important}";
  document.head.appendChild(css);
  (function () { var l = document.createElement("link"); l.rel = "stylesheet"; l.href = ROOT + "assets/polish.css?v=7"; document.head.appendChild(l); })();   // 전체 마감 (assets/polish.css)

  function toast(msg) { var t = document.createElement("div"); t.className = "vfm-toast"; t.textContent = msg; document.body.appendChild(t); setTimeout(function () { t.remove(); }, 2200); }
  function ago(iso) {
    if (!iso) return "기록 없음";
    var m = Math.round((Date.now() - Date.parse(iso)) / 60000);
    if (m < 1) return "방금"; if (m < 60) return m + "분 전";
    var h = Math.floor(m / 60); if (h < 48) return h + "시간 전";
    return Math.floor(h / 24) + "일 전";
  }
  function getJ(p) { if (p.indexOf("data/baedat/") === 0) p = "/vendingForMe/" + p;   // 배댓 자료는 시사 자판기 저장소에
    return fetch((p.charAt(0) === "/" ? "" : ROOT) + p, { cache: "no-cache" }).then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; }); }

  /* ── 앱 사이 이동: 기록을 쌓지 않음 ── */
  function openApp(a) {
    if (a === APP) { if (window.vfmApp && window.vfmApp.top) window.vfmApp.top(); window.scrollTo({ top: 0, behavior: "smooth" }); return; }
    if (a === "home") return goHome();
    var to = ROOT + a + "/";
    // 이 앱이 깔아 둔 뒤로가기 칸(top)을 먼저 걷고 바꿔 끼움 → 뒤로가기가 옛 앱으로 튀지 않음
    if (!HOME && history.state && history.state.vfm === "top") { switching = to; leaving = true; history.back(); setTimeout(function () { if (switching) location.replace(switching); }, 600); }
    else location.replace(to);
  }
  var switching = null;
  var homeTimer = null;
  function goHome() {
    // 홈에서 들어왔으면 진짜 뒤로(홈 화면이 그대로 남아 있음), 아니면 홈으로 바꿔 끼움
    var fromHome = false; try { fromHome = sessionStorage.getItem("vfm:fromHome") === "1"; } catch (e) { }
    if (fromHome && history.length > 1) {
      var st = history.state && history.state.vfm;
      leaving = true;
      history.go(st === "top" ? -2 : -1);
      homeTimer = setTimeout(function () { location.replace(ROOT); }, 800);   // 혹시 안 넘어가면
    } else location.replace(ROOT);
  }
  var leaving = false;
  window.addEventListener("pagehide", function () { clearTimeout(homeTimer); leaving = false; });
  // 홈이 아닌 바깥에서 바로 들어왔으면 '홈에서 왔음' 표시를 지움
  if (!HOME) {
    try {
      var ref = document.referrer || "", base = new URL(ROOT, location.href).href;
      if (!ref || ref.indexOf(base) !== 0) sessionStorage.removeItem("vfm:fromHome");
    } catch (e) { }
  }

  /* ── 위쪽 앱 전환 막대 ── */
  var meta = null, bar = null;
  if (!HOME) {
    bar = document.createElement("div"); bar.className = "vfm-bar"; bar.setAttribute("role", "navigation"); bar.setAttribute("aria-label", "자판기 앱");
    bar.innerHTML =
      '<button class="h home" type="button" data-vfm="home" aria-label="자판기 홈"><svg viewBox="0 0 24 24" fill="currentColor"><rect x="3" y="3" width="7.5" height="7.5" rx="2.2"/><rect x="13.5" y="3" width="7.5" height="7.5" rx="2.2"/><rect x="3" y="13.5" width="7.5" height="7.5" rx="2.2"/><rect x="13.5" y="13.5" width="7.5" height="7.5" rx="2.2"/></svg>홈</button>' +
      '<div class="vfm-seg">' + APPS.map(function (a) {
        return '<button type="button" data-vfm="' + a[0] + '"' + (a[0] === APP ? ' aria-current="page"' : "") + ">" + (a[0] === APP ? '<span class="vfm-dot none"></span>' : "") + a[1] + "</button>";
      }).join("") + "</div>" +
      '<button class="h" type="button" data-vfm="settings" aria-label="설정"><svg viewBox="0 0 24 24" fill="currentColor"><circle cx="5" cy="12" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="19" cy="12" r="2"/></svg></button>';
    document.body.insertBefore(bar, document.body.firstChild);
    bar.addEventListener("click", function (e) {
      var b = e.target.closest("[data-vfm]"); if (!b) return;
      var a = b.getAttribute("data-vfm");
      if (a === "settings") return openSheet();
      openApp(a);
    });
  }
  function paintDot() {
    var dot = document.querySelector(".vfm-seg .vfm-dot"); if (!dot) return;
    dot.className = "vfm-dot " + (!meta || !meta.updatedAt ? "none" : (Date.now() - Date.parse(meta.updatedAt) > (APP === "sisa" ? 6 : APP === "tools" ? 12 : APP === "brain" ? 18 : 30) * 3600e3 ? "old" : ""));
    dot.title = meta && meta.updatedAt ? "마지막 갱신 " + ago(meta.updatedAt) : "갱신 기록 없음";
  }
  function loadMeta() { if (HOME) return; return getJ("data/" + APP + "/_meta.json").then(function (m) { meta = m; paintDot(); }); }

  /* ── 뒤로가기 (한 단계 위로) ── */
  var touched = false;
  function arm() {
    try { if (!(history.state && (history.state.vfm === "top" || history.state.vfm === "ov"))) history.pushState({ vfm: "top" }, "", location.href); } catch (e) { }
  }
  // 지금 보이는 화면 주소를 늘 기억 (뒤로가기 때 브라우저가 옛 주소로 되돌려 놓는 것을 바로잡으려고)
  var curUrl = location.href;
  ["pushState", "replaceState"].forEach(function (k) {
    var orig = history[k];
    history[k] = function () { var r = orig.apply(history, arguments); curUrl = location.href; return r; };
  });
  window.addEventListener("hashchange", function () { curUrl = location.href; });
  // 홈 랜덤 카드에서 '자세히'로 들어온 첫 화면 (assets/mix.js 가 적어 둠)
  var entryHash = null;
  if (!HOME) { try { if (sessionStorage.getItem("vfm:fromHome") === "1" && sessionStorage.getItem("vfm:fromCard") === (location.hash || "")) entryHash = location.hash; sessionStorage.removeItem("vfm:fromCard"); } catch (e) { } }
  function backToCard(h) {
    if (!entryHash || (h === undefined ? location.hash : h) !== entryHash) return false;
    entryHash = null; goHome(); return true;
  }
  window.vfm = window.vfm || {}; window.vfm.backToCard = function () { return backToCard(); };
  // 화면 안의 '뒤로'·'닫기' 단추도 같은 규칙
  if (!HOME) document.addEventListener("click", function (e) {
    var b = e.target.closest && e.target.closest("[data-close],[data-act='back']"); if (!b) return;
    if (backToCard()) { e.preventDefault(); e.stopPropagation(); }
  }, true);
  if (!HOME) {
    try { if (!(history.state && (history.state.vfm === "top" || history.state.vfm === "base"))) history.replaceState({ vfm: "base" }, "", location.href); } catch (e) { }
    // 브라우저는 사람이 화면을 누른 뒤에 만든 기록만 뒤로가기에서 인정함 → 첫 터치 때 한 칸 깔아 둠
    var onTouch = function () { touched = true; arm(); };
    document.addEventListener("click", onTouch, true);
    document.addEventListener("touchend", onTouch, { capture: true, passive: true });
    window.addEventListener("popstate", function (e) {
      var st = e.state && e.state.vfm;
      if (switching) { var to = switching; switching = null; location.replace(to); return; }
      if (leaving) return;                              // 홈으로 가는 중
      if (st === "top") return;
      if (st !== "base") { if (window.vfmApp && window.vfmApp.route) window.vfmApp.route(); return; }
      if (location.href !== curUrl) { var shown = curUrl; try { history.replaceState({ vfm: "base" }, "", shown); } catch (x) { } }
      // 홈 카드의 '자세히'로 들어온 화면이면, 뒤로가기 = 그 홈 카드로
      if (backToCard(new URL(curUrl).hash)) return;
      var done = false;
      var sh = document.querySelector(".vfm-back"); if (sh) { sh.remove(); done = true; }
      if (!done && window.vfmApp && window.vfmApp.back) { try { done = !!window.vfmApp.back(); } catch (x) { done = false; } }
      if (done) { if (touched) arm(); return; }
      goHome();                                         // 앱 첫 화면에서 뒤로 → 자판기 홈
    });
  }

  /* ── 창(시트) 관리: 열면 기록 한 칸 → 뒤로가기·뒤로 스와이프 = 창 닫기 / 끌어내려 닫기 / 뒤 화면 스크롤 잠금 ──
       대상: 설정·생각 남기기(.vfm-back), 앱의 낱말·메뉴 창(body > .back), 이야기 #sheet. 시사 기사 창은 주소(#item-)로 이미 됨 */
  var OV = { n: 0, skip: 0 };
  function ovList() { return [].slice.call(document.querySelectorAll("body > .vfm-back, body > .back, #sheet.sheet:not([hidden])")).filter(function (el) { return !el.classList.contains("vfm-closing"); }); }
  function ovPanel(el) { return el.querySelector(".vfm-sheet, .sheet, [role=dialog]") || el.firstElementChild; }
  function ovClose(el, anim) {
    if (!el) return;
    var done = function () { if (el.id === "sheet") { el.hidden = true; el.innerHTML = ""; el.classList.remove("vfm-closing"); } else el.remove(); };
    var pn = ovPanel(el);
    if (anim && pn && pn.animate) {
      el.classList.add("vfm-closing");
      var cur = getComputedStyle(pn).transform; pn.style.transition = "none";
      pn.animate([{ transform: cur === "none" ? "translateY(0)" : cur }, { transform: "translateY(105%)" }], { duration: 220, easing: "cubic-bezier(.3,0,.8,.15)", fill: "forwards" });
      el.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 220, fill: "forwards" }).onfinish = done;
    } else done();
  }
  function ovSync() {
    var l = ovList(), n = l.length;
    document.documentElement.classList.toggle("vfm-ovl", n > 0);
    if (n > OV.n) { for (var i = OV.n; i < n; i++) { try { history.pushState({ vfm: "ov" }, "", location.href); } catch (e) { } } l.forEach(ovDrag); }
    else if (n < OV.n && history.state && history.state.vfm === "ov") { OV.skip++; history.back(); }   // 단추·바깥 눌러 닫았으면 그 기록 칸도 지움
    OV.n = n;
  }
  new MutationObserver(function () { clearTimeout(OV.t); OV.t = setTimeout(ovSync, 0); }).observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["hidden"] });
  window.addEventListener("popstate", function (e) {
    if (OV.skip) { OV.skip--; e.stopImmediatePropagation(); return; }
    var l = ovList();
    if (!l.length) { if (e.state && e.state.vfm === "ov") { e.stopImmediatePropagation(); OV.skip++; history.back(); } return; }   // 이미 닫힌 창의 남은 칸은 건너뜀
    e.stopImmediatePropagation();                                     // 앱의 뒤로가기(화면 이동)는 하지 않음
    OV.n = l.length - 1; ovClose(l[l.length - 1], true);
    setTimeout(function () { document.documentElement.classList.toggle("vfm-ovl", ovList().length > 0); }, 240);
  }, true);
  // 끌어내려 닫기: 손잡이·제목을 잡거나, 창 안이 맨 위일 때 아래로 끌기
  function ovDrag(el) {
    var pn = ovPanel(el); if (!pn || pn.__vfmDrag) return; pn.__vfmDrag = 1;
    if (!pn.querySelector(".grab")) { var g = document.createElement("div"); g.className = "grab vfm-grab"; pn.insertBefore(g, pn.firstChild); }
    var y0 = 0, x0 = 0, dy = 0, t0 = 0, top = false, lock = null, sc = null, last = 0, vy = 0;
    function scroller(t) { for (var n = t; n && n !== el; n = n.parentElement) { if (n.scrollHeight > n.clientHeight + 2 && /auto|scroll/.test(getComputedStyle(n).overflowY)) return n; } return pn; }
    pn.addEventListener("touchstart", function (e) {
      if (e.touches.length !== 1) { lock = "no"; return; }
      var t = e.target; if (t.closest("input,textarea,select,[contenteditable],iframe")) { lock = "no"; return; }
      sc = scroller(t); top = sc.scrollTop <= 0 || !!t.closest(".grab,h3");
      y0 = last = e.touches[0].clientY; x0 = e.touches[0].clientX; dy = 0; vy = 0; t0 = Date.now(); lock = null;
      pn.getAnimations && pn.getAnimations().forEach(function (a) { a.finish(); });   // 올라오는 중이면 끝내 놓고 시작
    }, { passive: true });
    pn.addEventListener("touchmove", function (e) {
      if (lock === "no") return;
      var y = e.touches[0].clientY, d = y - y0, dx = e.touches[0].clientX - x0;
      if (lock === null) {
        if (Math.abs(d) < 2 && Math.abs(dx) < 2) return;
        lock = top && d > 0 && Math.abs(d) >= Math.abs(dx) ? "y" : "no";            // 맨 위에서 아래로 = 창 끌기, 그 밖 = 보통 스크롤
        if (lock === "no") return;
        sc.style.overflowY = "hidden"; pn.style.transition = "none"; y0 = y;     // 끄는 동안 안쪽 스크롤 멈춤
      }
      e.preventDefault();
      var now = Date.now(); vy = (y - last) / Math.max(1, now - t0); last = y; t0 = now;
      d = y - y0; dy = d > 0 ? d : d / 4;                                            // 위로 당기면 살짝만 따라옴
      pn.style.transform = "translateY(" + dy + "px)";
      el.style.backgroundColor = "rgba(0,0,0," + Math.max(0, .42 - Math.max(0, dy) / 900) + ")";
    }, { passive: false });
    function end() {
      if (lock !== "y") { lock = null; return; } lock = null;
      if (sc) sc.style.overflowY = "";
      if (dy > Math.min(150, pn.offsetHeight * .28) || (vy > .5 && dy > 20)) {
        if (history.state && history.state.vfm === "ov") history.back(); else ovClose(el, true);
      } else { pn.style.transition = "transform .32s cubic-bezier(.2,.9,.3,1.1)"; pn.style.transform = ""; el.style.backgroundColor = ""; }
    }
    pn.addEventListener("touchend", end); pn.addEventListener("touchcancel", end);
  }
  css.textContent += "html.vfm-ovl,html.vfm-ovl body{overflow:hidden;overscroll-behavior:none}" +
    ".vfm-back .vfm-sheet,body>.back>.sheet,#sheet.sheet>*{overscroll-behavior:contain;-webkit-overflow-scrolling:touch;will-change:transform}" +
    ".vfm-sheet .grab,.vfm-grab,.vfm-sheet h3,body>.back>.sheet>h3{touch-action:none}.vfm-sheet .grab,.vfm-grab{box-sizing:content-box;padding:8px 40px;background-clip:content-box!important}" +
    ".vfm-grab{width:36px;height:5px;border-radius:3px;background:var(--ap-label3,rgba(60,60,67,.3));margin:-4px auto 10px;flex:none}";

  /* ── 바깥 링크 갔다 오면 그 자리로 (앱이 go 를 내놓으면 기록 없이 이동) ── */
  window.vfm = window.vfm || {};
  window.vfm.goHash = function (h) {
    if (window.vfmApp && window.vfmApp.go) return window.vfmApp.go(h);
    try { history.replaceState(history.state, "", location.pathname + location.search + h); } catch (e) { }
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  };

  /* ── 설정 시트 ── */
  function openSheet() {
    var back = document.createElement("div"); back.className = "vfm-back";
    var kb = window.vfm && window.vfm.storageBytes ? Math.round(window.vfm.storageBytes() / 1024) : 0;
    back.innerHTML =
      '<div class="vfm-sheet" role="dialog" aria-label="자판기 설정"><div class="grab"></div><h3>설정</h3>' +
      '<div class="cap">마지막 갱신</div><div class="grp" id="vfmUpd">' + APPS.map(function (a) { return '<div data-u="' + a[0] + '"><span>' + a[1] + '</span><span class="v">…</span></div>'; }).join("") + "</div>" +
      '<div class="cap">폰·PC 이어 보기</div><div class="grp" id="vfmSync">' + syncHtml() + "</div>" +
      '<div class="cap">유튜브 내 계정으로 보기</div><div class="grp">' +
      '<button type="button" data-act="ytlogin"><span class="tint">크롬에서 유튜브 로그인</span><span class="v">한 번만 ↗</span></button></div>' +
      '<p class="foot">크롬에서 유튜브에 로그인해 두면, 카드 안에서 영상을 틀 때도 내 계정으로 재생돼요(프리미엄이면 광고 없음 · 시청 기록 남음). 아이폰 사파리는 안 돼요.</p>' +
      '<div class="cap">다른 자판기</div><div class="grp">' +'<button type="button" data-act="go" data-go="/vendingForMe/"><span class="tint">시사 자판기</span><span class="v">세계 뉴스 · AI · 도구 ↗</span></button>' +'<button type="button" data-act="go" data-go="/vfm-mind/"><span class="tint">사람 자판기</span><span class="v">배댓 · 맨탈 ↗</span></button>' +'</div>' +
      '<div class="cap">내 기록</div><div class="grp">' +
      '<button type="button" data-act="box"><span class="tint">보관함 — 모든 앱에서 저장한 것 · 내 질문 · 이번 주 생각</span><span class="v">›</span></button>' +
      '<button type="button" data-act="export"><span class="tint">기록 내보내기</span><span class="v">파일 하나로</span></button>' +
      '<button type="button" data-act="import"><span class="tint">기록 불러오기</span><span class="v">›</span></button>' +
      "<div><span>이 폰에 저장된 양</span><span class=\"v\">" + kb.toLocaleString() + " KB / 약 5,000 KB</span></div></div>" +
      '<p class="foot">읽은 기록·별표·메모는 이 폰 브라우저 안에만 있어요. 폰을 바꾸거나 PC로 옮길 땐 내보내기 → 새 기기에서 불러오기.</p>' +
      '<div class="cap">출처 상태</div><div class="grp" id="vfmHealth"><div><span>확인 중…</span></div></div>' +
      '<div class="cap"></div><div class="grp"><button type="button" data-act="reload"><span class="tint">새로고침</span></button>' +
      (HOME ? "" : '<button type="button" data-act="home"><span class="tint">자판기 홈으로</span></button>') + "</div>" +
      '<input type="file" accept="application/json" hidden></div>';
    document.body.appendChild(back);
    APPS.forEach(function (a) {
      getJ("data/" + a[0] + "/_meta.json").then(function (m) { var el = back.querySelector('[data-u="' + a[0] + '"] .v'); if (el) el.textContent = m && m.updatedAt ? ago(m.updatedAt) + (m.label ? " · " + m.label : "") : "기록 없음"; });
    });
    var HL = [["trends", "트렌드", "sisa"], ["ai", "AI", "ai"], ["history", "역사", "history"], ["tools", "도구", "tools"], ["brain", "뇌", "brain"]].filter(function (h) { return APPS.some(function (a) { return a[0] === h[2]; }); });   // 이 사이트 앱의 출처만
    Promise.all(HL.map(function (h) { return getJ("data/" + h[0] + "/_index.json"); })).then(function (r) {
      var el = back.querySelector("#vfmHealth"); if (!el) return;
      if (!HL.length) { el.innerHTML = '<div><span>자동 수집 출처</span><span class="v">이 사이트는 매월 한 번만 모아요</span></div>'; return; }
      var rows = HL.map(function (h, i) { return [h[1], r[i]]; }).map(function (x) {
        var ks = Object.keys((x[1] && x[1].broken) || {});
        return "<div><span>" + x[0] + '</span><span class="v">' + (x[1] ? (ks.length ? "고장 " + ks.length + "곳: " + ks.slice(0, 3).join(", ") : "모두 정상") : "자료 없음") + "</span></div>";
      });
      el.innerHTML = rows.join("");
    });
    var input = back.querySelector("input");
    back.addEventListener("click", function (e) {
      if (e.target === back) return back.remove();
      var b = e.target.closest("[data-act]"); if (!b) return;
      var act = b.getAttribute("data-act");
      if (act === "go") { location.href = b.getAttribute("data-go"); return; }
      if (act === "box") { location.href = ROOT + "box/"; return; }
      if (act === "ytlogin") { var yu = "https://accounts.google.com/ServiceLogin?service=youtube&continue=" + encodeURIComponent("https://www.youtube.com/"); if (!openInChrome(yu)) window.open(yu, "_blank", "noopener"); return; }
      if (act === "login") { window.vfmSync.login().catch(function (x) { toast(x.message || "로그인 실패"); }); return; }
      if (act === "logout") { if (confirm("로그아웃할까요? 이 기기의 기록은 그대로 남아요.")) window.vfmSync.logout(); return; }
      if (act === "syncnow") { window.vfmSync.now(); return; }
      if (act === "reload") location.reload();
      else if (act === "home") { back.remove(); goHome(); }
      else if (act === "export") {
        var data = JSON.stringify(window.vfm.exportAll());
        var a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([data], { type: "application/json" }));
        a.download = "vendingForMe-기록-" + new Date().toISOString().slice(0, 10) + ".json"; a.click();
        setTimeout(function () { URL.revokeObjectURL(a.href); }, 5000); toast("내보냈어요");
      } else if (act === "import") input.click();
    });
    input.addEventListener("change", function () {
      var f = input.files[0]; if (!f) return;
      var r = new FileReader();
      r.onload = function () {
        try { var n = window.vfm.importAll(JSON.parse(r.result)); toast(n + "개 항목을 불러왔어요"); setTimeout(function () { location.reload(); }, 900); }
        catch (e) { toast("불러오기 실패: " + e.message); }
      };
      r.readAsText(f);
    });
  }
  window.vfm.openSettings = openSheet;
  window.vfm.openApp = openApp;
  window.vfm.toast = toast;

  /* ── 생각 남기기 (모든 앱 공통, 토큰 0) — 보관함(box/)에서 질문별로 모아 봄
       vfm:box:qs    = [{id, t, at}]                       내가 붙잡고 있는 질문
       vfm:box:think = [{id, at, app, key, title, url, q, f, a, x}]   f=발견 · a=내 일에 적용 · x=틀렸다는 증거 */
  var BOX = {
    g: function (k, d) { try { var v = JSON.parse(localStorage.getItem("vfm:box:" + k)); return v == null ? d : v; } catch (e) { return d; } },
    s: function (k, v) { try { localStorage.setItem("vfm:box:" + k, JSON.stringify(v)); return true; } catch (e) { toast("저장 공간이 꽉 찼어요"); return false; } },
    id: function () { return Date.now().toString(36) + Math.random().toString(36).slice(2, 6); }
  };
  BOX.qs = function () { return BOX.g("qs", []); };
  BOX.thinks = function () { return BOX.g("think", []); };
  function escH(t) { return String(t == null ? "" : t).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function think(info, edit) {
    info = info || {}; var old = edit || {}, qs = BOX.qs(), pick = old.q || BOX.g("lastQ", "");
    if (pick && !qs.some(function (q) { return q.id === pick; })) pick = "";
    var back = document.createElement("div"); back.className = "vfm-back";
    back.innerHTML = '<div class="vfm-sheet vfm-think" role="dialog" aria-label="생각 남기기"><div class="grab"></div><h3>생각 남기기</h3>' +
      (info.title ? '<p class="vfm-tk-src">' + escH(info.title) + "</p>" : "") +
      '<div class="cap">어느 질문에 붙일까요?</div><div class="vfm-tk-qs">' +
      '<button type="button" data-q="" aria-pressed="' + (!pick) + '">질문 없이</button>' +
      qs.map(function (q) { return '<button type="button" data-q="' + q.id + '" aria-pressed="' + (q.id === pick) + '">' + escH(q.t) + "</button>"; }).join("") +
      '<button type="button" data-q="+">+ 새 질문</button></div>' +
      '<input class="vfm-tk-newq" placeholder="예: 사람들이 편해져도 계속 돈을 쓰는 불편은?" hidden>' +
      '<label class="vfm-tk-l">내가 발견한 점<textarea data-f="f" rows="2" placeholder="이 글에서 새로 보인 것">' + escH(old.f) + "</textarea></label>" +
      '<label class="vfm-tk-l">내 일에 적용한다면<textarea data-f="a" rows="2" placeholder="내 일·생활에 어떻게 쓸까">' + escH(old.a) + "</textarea></label>" +
      '<label class="vfm-tk-l">이 생각이 틀렸다는 증거는<textarea data-f="x" rows="2" placeholder="무엇이 나오면 생각을 바꿀까">' + escH(old.x) + "</textarea></label>" +
      '<p class="vfm-tk-err" hidden>한 칸은 적어 주세요</p>' +
      '<div class="vfm-tk-btns"><button type="button" class="ghost" data-tk="cancel">닫기</button><button type="button" data-tk="save">저장</button></div></div>';
    document.body.appendChild(back);
    var nq = back.querySelector(".vfm-tk-newq");
    back.addEventListener("click", function (e) {
      if (e.target === back) { back.remove(); return; }
      var qb = e.target.closest("[data-q]");
      if (qb) {
        back.querySelectorAll("[data-q]").forEach(function (b) { b.setAttribute("aria-pressed", String(b === qb)); });
        nq.hidden = qb.getAttribute("data-q") !== "+"; if (!nq.hidden) nq.focus(); return;
      }
      var b = e.target.closest("[data-tk]"); if (!b) return;
      if (b.getAttribute("data-tk") === "cancel") { back.remove(); return; }
      var v = {}; back.querySelectorAll("[data-f]").forEach(function (t) { v[t.getAttribute("data-f")] = t.value.trim(); });
      if (!v.f && !v.a && !v.x) { back.querySelector(".vfm-tk-err").hidden = false; return; }
      var on = back.querySelector('[data-q][aria-pressed="true"]'), q = on ? on.getAttribute("data-q") : "";
      if (q === "+") {
        var t = nq.value.trim(); if (!t) { nq.focus(); return; }
        var list = BOX.qs(); q = BOX.id(); list.push({ id: q, t: t, at: Date.now() }); BOX.s("qs", list);
      }
      var all = BOX.thinks(), rec = { id: old.id || BOX.id(), at: old.at || Date.now(), ed: old.id ? Date.now() : undefined, app: info.app || old.app || APP, key: info.key || old.key || "", title: info.title || old.title || "", url: info.url || old.url || "", q: q, f: v.f, a: v.a, x: v.x };
      all = all.filter(function (r) { return r.id !== rec.id; }); all.unshift(rec);
      if (BOX.s("think", all)) { BOX.s("lastQ", q); back.remove(); toast("생각을 남겼어요 · 보관함에서 모아 봐요"); if (info.onSave) info.onSave(rec); }
    });
  }
  window.vfm.think = think; window.vfm.box = BOX;

  /* ── X(트위터) 링크는 X 앱 말고 크롬으로 ──
       안드로이드: intent 주소로 크롬을 지정해 열기 (크롬이 없으면 원래 주소)
       아이폰: googlechromes:// 로 크롬 열기, 1.2초 안에 안 넘어가면(크롬 없음) 원래 주소
       PC: 그대로 (원래 브라우저 탭으로 열림) */
  var UA = navigator.userAgent || "", ANDROID = /Android/i.test(UA), IOS = /iPhone|iPad|iPod/i.test(UA) || (/Macintosh/.test(UA) && navigator.maxTouchPoints > 1);
  var XRE = /^https?:\/\/(?:www\.|mobile\.)?(?:x|twitter)\.com\//i;
  function openInChrome(u) {
    if (ANDROID) { location.href = "intent://" + u.replace(/^https?:\/\//, "") + "#Intent;scheme=https;package=com.android.chrome;S.browser_fallback_url=" + encodeURIComponent(u) + ";end"; return true; }
    if (IOS && !/CriOS/.test(UA)) {
      var gone = false, t = setTimeout(function () { if (!gone) location.href = u; }, 1200);
      var off = function () { if (document.hidden) { gone = true; clearTimeout(t); document.removeEventListener("visibilitychange", off); } };
      document.addEventListener("visibilitychange", off);
      location.href = "googlechromes://" + u.replace(/^https?:\/\//, ""); return true;
    }
    return false;                                                     // PC·아이폰 크롬 안: 그대로
  }
  document.addEventListener("click", function (e) {
    var a = e.target.closest && e.target.closest("a[href]"); if (!a || !XRE.test(a.href)) return;
    if (openInChrome(a.href)) e.preventDefault();
  }, true);
  window.vfm.openX = openInChrome;

  /* ── 유튜브: 썸네일([data-yt])을 누르면 유튜브로 나가지 않고 그 자리에서 재생 (영상은 유튜브 서버 → 폰, 토큰·서버 0) ── */
  document.addEventListener("click", function (e) {
    var t = e.target.closest && e.target.closest("[data-yt]"); if (!t || t.classList.contains("vfm-yt-on")) return;
    var id = t.getAttribute("data-yt"); if (!/^[\w-]{11}$/.test(id)) return;
    e.preventDefault(); e.stopPropagation();
    var box = document.createElement("div"); box.className = "vfm-yt vfm-yt-on" + (t.hasAttribute("data-short") ? " short" : "");   // 쇼츠는 세로 화면
    box.innerHTML = '<iframe src="https://www.youtube.com/embed/' + id + '?autoplay=1&playsinline=1&rel=0&modestbranding=1" title="유튜브 영상" allow="autoplay; encrypted-media; picture-in-picture; fullscreen" allowfullscreen></iframe>' +
      '<a class="vfm-yt-out" href="https://www.youtube.com/watch?v=' + id + '" target="_blank" rel="noopener">재생이 안 되면 유튜브에서 보기 ↗</a>';
    t.replaceWith(box);
  }, true);
  css.textContent += ".vfm-yt{margin:2px 0 12px}.vfm-yt iframe{display:block;width:100%;aspect-ratio:16/9;border:0;border-radius:12px;background:#000}" +
    ".vfm-yt-out{display:inline-block;margin-top:6px;font-size:12.5px;color:var(--ap-label2);text-decoration:none}" +
    /* 쇼츠(세로 9:16): 가로 상자에 넣으면 작게 찌그러지므로, 가운데 세로 상자로 (화면 높이의 64%까지) */
    ".vfm-yt.short{text-align:center}.vfm-yt.short iframe{aspect-ratio:9/16;width:min(100%,calc(72vh*9/16));margin:0 auto}" +
    "[data-yt][data-short].vdk-yt,[data-yt][data-short].vdk-thumb{aspect-ratio:9/16;width:min(62%,calc(52vh*9/16),240px);margin-left:auto;margin-right:auto}";

  /* ── 나무위키 바로가기 ── 제목·이름·낱말 어디서든. namu.wiki/Go 는 문서가 있으면 바로, 없으면 찾기 결과로 감 (긁어오지 않음, 링크만) */
  function namu(q) { q = String(q || "").replace(/^(바뀐 점|이번 주) · /, "").replace(/\s*[\(（][^)）]*[\)）]\s*$/, "").trim(); return "https://namu.wiki/Go?q=" + encodeURIComponent(q); }
  window.vfm.namu = namu;
  /* ── 사진 공용 도우미 (모든 탭) ──
     vfm.pic(원본, 가로, 세로?, class) : 무료 축소 서비스로 작게 받아 데이터 절약, 안 되면 원본, 그래도 안 되면 사라짐
     vfm.logo(글 주소, class)          : 사진이 없는 글은 그 사이트 로고(파비콘 128px)
     <img data-wt="ko:제목">            : 위키백과 대표 사진 (assets/wikithumb.js) */
  var bigUrl = function (u) { return String(u || "").replace(/(ichef\.bbci\.co\.uk\/(?:ace\/standard|ace\/ws|news))\/\d{2,3}\//, "$1/976/"); };   // BBC 240px 사진 → 976px 판
  var picUrl = function (u, w, h) { u = bigUrl(u); return "https://wsrv.nl/?url=" + encodeURIComponent(u) + "&w=" + w + (h ? "&h=" + h + "&fit=cover" : "") + "&output=webp&q=72"; };
  window.vfm.pic = function (u, w, h, cls) {
    if (!u) return "";
    var e = function (x) { return String(x).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); };
    return '<img class="vfm-pic ' + (cls || "") + '" src="' + e(picUrl(u, w, h)) + '" data-orig="' + e(u) + '" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer">';
  };
  // 유튜브 베스트 댓글 5개 (로봇이 받아 둔 cm: [{a 글쓴이, t 원문, ko 번역, l 좋아요}])
  window.vfm.ytComments = function (cm) {
    if (!cm || !cm.length) return "";
    var e = function (x) { return String(x || "").replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); };
    var n = function (x) { x = +x || 0; return x >= 10000 ? (x / 1e4).toFixed(1).replace(/\.0$/, "") + "만" : x >= 1000 ? (x / 1e3).toFixed(1).replace(/\.0$/, "") + "천" : String(x); };
    return '<p class="vdk-h">💬 베스트 댓글</p><ol class="vfm-cm">' + cm.slice(0, 5).map(function (c) {
      return "<li><p>" + e(c.ko || c.t) + "</p>" + (c.ko && c.ko !== c.t ? '<details><summary>원문</summary><p>' + e(c.t) + "</p></details>" : "") +
        '<small>👍 ' + n(c.l) + (c.a ? " · " + e(c.a) : "") + (c.ko && c.ko !== c.t ? " · 기계번역" : "") + "</small></li>";
    }).join("") + "</ol>";
  };
  window.vfm.logo = function (url, cls) {
    var m = /^https?:\/\/([^/]+)/.exec(url || ""); if (!m) return "";
    return '<img class="vfm-pic vfm-logo ' + (cls || "") + '" src="https://www.google.com/s2/favicons?domain=' + m[1] + '&sz=128" alt="" loading="lazy" decoding="async">';
  };
  document.addEventListener("error", function (ev) {
    var t = ev.target; if (!t || t.tagName !== "IMG" || !t.classList.contains("vfm-pic")) return;
    if (t.dataset.orig && t.src !== t.dataset.orig) { t.src = t.dataset.orig; return; }
    var w = t.closest(".vfm-picw"); (w || t).remove();
  }, true);
  if (!window.WT) { var wt = document.createElement("script"); wt.src = ROOT + "assets/wikithumb.js"; wt.defer = true; document.head.appendChild(wt); }
  window.vfm.kwChips = function (list) {                              // 중요 키워드(최대 3개) → 나무위키 칩
    var seen = {}, k = (list || []).map(function (w) { return String(w || "").replace(/\s*[\(（][^)）]*[\)）]/g, "").trim(); }).filter(function (w) { var l = w.toLowerCase(); if (w.length < 2 || w.length > 24 || seen[l]) return false; seen[l] = 1; return true; }).slice(0, 3);
    return k.length ? '<div class="vdk-kw">' + k.map(function (w) { return '<a href="' + escH(namu(w)) + '" target="_blank" rel="noopener">' + escH(w) + "</a>"; }).join("") + "</div>" : "";
  };
  // 글자를 길게 눌러(또는 끌어서) 고르면 그 근처에 '나무위키 ↗' — 1~40자, 한 줄일 때만
  var npill = document.createElement("a"); npill.className = "vfm-namu"; npill.target = "_blank"; npill.rel = "noopener"; npill.textContent = "나무위키 ↗"; npill.hidden = true;
  document.addEventListener("DOMContentLoaded", function () { document.body.appendChild(npill); });
  css.textContent += ".vfm-namu{position:absolute;z-index:9998;transform:translate(-50%,0);background:#00A495;color:#fff;font:700 14px/1 var(--ap-font);padding:9px 13px;border-radius:999px;box-shadow:0 6px 18px rgba(0,0,0,.22);text-decoration:none;white-space:nowrap}" +
    ".vdk-kw{display:flex;flex-wrap:wrap;gap:6px;margin:12px 0 0}.vdk-kw a{font-size:13.5px;font-weight:600;padding:6px 11px;border-radius:999px;text-decoration:none;color:#00897B;background:rgba(0,164,149,.12)}.vdk-kw a::after{content:'\\00a0↗';font-size:11px;opacity:.7}" +
    "@media (prefers-color-scheme:dark){.vdk-kw a{color:#5FD3C4;background:rgba(0,164,149,.2)}}";
  var nT = null;
  function placeNamu() {
    var sel = window.getSelection && window.getSelection(), t = sel ? String(sel).trim() : "";
    if (!t || t.length > 40 || /\n/.test(t) || !sel.rangeCount || (document.activeElement && /^(INPUT|TEXTAREA)$/.test(document.activeElement.tagName))) { npill.hidden = true; return; }
    var r = sel.getRangeAt(0).getBoundingClientRect(); if (!r.width && !r.height) { npill.hidden = true; return; }
    npill.href = namu(t); npill.hidden = false;
    var below = r.bottom + 54 < window.innerHeight;                  // 폰은 위쪽에 시스템 메뉴가 뜨니 아래에
    npill.style.left = Math.max(60, Math.min(window.innerWidth - 60, r.left + r.width / 2)) + window.scrollX + "px";
    npill.style.top = (below ? r.bottom + 10 : r.top - 46) + window.scrollY + "px";
  }
  document.addEventListener("selectionchange", function () { clearTimeout(nT); nT = setTimeout(placeNamu, 250); });
  npill.addEventListener("click", function () { setTimeout(function () { npill.hidden = true; try { window.getSelection().removeAllRanges(); } catch (e) { } }, 100); });

  /* ── 구글 로그인 (assets/sync.js) — 설정(sync-config.js)이 있을 때만 보임 ── */
  function syncHtml() {
    var S = window.vfmSync;
    if (!S || !S.ready) return '<div><span>구글 로그인</span><span class="v">준비 중</span></div>';
    var u = S.user();
    if (!u) return '<button type="button" data-act="login"><span class="tint">구글로 로그인</span><span class="v">폰과 PC에서 같은 기록</span></button>';
    return '<div><span>' + escH((u.user_metadata && (u.user_metadata.name || u.user_metadata.full_name)) || u.email || "로그인됨") + '</span><span class="v">' + escH(S.status || "") + "</span></div>" +
      '<button type="button" data-act="syncnow"><span class="tint">지금 맞추기</span><span class="v">›</span></button><button type="button" data-act="logout"><span>로그아웃</span><span class="v">›</span></button>';
  }
  // 설정 파일은 늘 새로 받음 (브라우저가 10분 묵혀 두지 않게)
  [ROOT + "assets/sync-config.js?t=" + Math.floor(Date.now() / 60000), ROOT + "assets/sync.js?v=4"].reduce(function (p, src) {
    return p.then(function () { return new Promise(function (ok) { var sc = document.createElement("script"); sc.src = src; sc.onload = sc.onerror = ok; document.head.appendChild(sc); }); });
  }, Promise.resolve()).then(function () { if (window.vfmSync) { window.vfmSync.render = syncHtml; gate(); } });

  /* ── 로그인해야 쓸 수 있게 (가족·지인 전용) — 구글 '테스트 사용자'에 등록한 계정만 들어옴 ──
       로그인 기록(sb-…-auth-token)이 이 기기에 있으면 바로 열고, 서버가 '로그인 아님'이라 하면 다시 잠금 */
  var LOCK = document.createElement("style");
  LOCK.textContent = "html.vfm-locked,html.vfm-locked body{overflow:hidden}html.vfm-locked body>*:not(.vfm-gate){visibility:hidden}" +
    ".vfm-gate{position:fixed;inset:0;z-index:99999;background:var(--ap-bg,#F2F2F7);color:var(--ap-label,#000);display:flex;align-items:center;justify-content:center;padding:24px;font:16px/1.5 var(--ap-font,system-ui)}" +
    ".vfm-gate .in{width:100%;max-width:340px;text-align:center}.vfm-gate h2{font-size:34px;font-weight:800;letter-spacing:-.03em;margin:0 0 6px}.vfm-gate p{margin:0 0 22px;color:var(--ap-label2,#6E6E73);font-size:15px}" +
    ".vfm-gate button{width:100%;border:0;border-radius:14px;padding:15px;font:inherit;font-weight:700;font-size:17px;background:var(--ap-blue,#007AFF);color:#fff;display:flex;gap:10px;align-items:center;justify-content:center}" +
    ".vfm-gate button svg{width:20px;height:20px;background:#fff;border-radius:50%;padding:2px}.vfm-gate small{display:block;margin-top:14px;color:var(--ap-label2,#6E6E73);font-size:12.5px;line-height:1.5}.vfm-gate .err{color:var(--ap-red,#d33);margin:14px 0 0;font-size:14px}";
  document.head.appendChild(LOCK);
  function hasToken() { try { for (var i = 0; i < localStorage.length; i++) if (/^sb-.+-auth-token$/.test(localStorage.key(i))) return true; } catch (e) { } return false; }
  var gateEl = null;
  function showGate(msg, busy) {
    document.documentElement.classList.add("vfm-locked");
    if (!gateEl) { gateEl = document.createElement("div"); gateEl.className = "vfm-gate"; document.body.appendChild(gateEl); }
    gateEl.innerHTML = '<div class="in"><h2>자판기</h2><p>가족·지인만 쓰는 자판기예요.<br>구글 계정으로 들어와 주세요.</p>' +
      (busy ? '<p style="margin:0">로그인하는 중…</p>' : '<button type="button" data-gate="login"><svg viewBox="0 0 24 24"><path fill="#4285F4" d="M21.6 12.2c0-.7-.1-1.4-.2-2H12v3.8h5.4a4.6 4.6 0 0 1-2 3v2.5h3.2c1.9-1.7 3-4.3 3-7.3z"/><path fill="#34A853" d="M12 22c2.7 0 5-.9 6.6-2.4l-3.2-2.5c-.9.6-2 1-3.4 1-2.6 0-4.8-1.8-5.6-4.1H3.1v2.6A10 10 0 0 0 12 22z"/><path fill="#FBBC05" d="M6.4 14a6 6 0 0 1 0-3.9V7.5H3.1a10 10 0 0 0 0 9z"/><path fill="#EA4335" d="M12 6c1.5 0 2.8.5 3.8 1.5l2.8-2.8A10 10 0 0 0 3.1 7.5L6.4 10C7.2 7.8 9.4 6 12 6z"/></svg>구글로 로그인</button>') +
      (msg ? '<p class="err">' + escH(msg) + "</p>" : "") +
      "<small>등록된 구글 계정만 들어올 수 있어요. 처음이면 주현에게 메일 주소를 알려 주세요.<br>로그인하면 폰과 PC에서 같은 기록을 봐요.</small></div>";
  }
  function hideGate() { document.documentElement.classList.remove("vfm-locked"); if (gateEl) { gateEl.remove(); gateEl = null; } }
  var REQ = function () { return !!(window.VFM_SYNC && window.VFM_SYNC.required); };   // sync-config.js 의 required: true 일 때만 잠금 (지금은 선택)
  function gate() {
    var S = window.vfmSync; if (!S || !S.ready || !REQ()) return;
    var cb = /[?&#](code|access_token)=/.test(location.href), err = /[?&#]error(_description)?=([^&#]*)/.exec(location.href);
    if (err) return showGate("로그인이 안 됐어요. 등록된 계정인지 확인해 주세요.");
    if (cb) return showGate("", true);
    if (!hasToken()) showGate("");
  }
  window.vfmGate = { show: function (m) { if (REQ()) showGate(m || ""); }, hide: hideGate };
  document.addEventListener("click", function (e) {
    if (!e.target.closest("[data-gate=login]")) return;
    showGate("", true);
    window.vfmSync.login().catch(function (x) { showGate((x && x.message) || "로그인을 시작하지 못했어요"); });
  });
  css.textContent += ".vfm-tk-src{margin:-6px 4px 10px;color:var(--ap-label2);font-size:14px}.vfm-tk-qs{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 10px}" +
    ".vfm-tk-qs button{border:0;border-radius:999px;padding:8px 12px;background:var(--ap-fill);color:var(--ap-label);font:inherit;font-size:14px}.vfm-tk-qs button[aria-pressed=true]{background:var(--ap-blue);color:#fff;font-weight:700}" +
    ".vfm-think input,.vfm-think textarea{width:100%;box-sizing:border-box;border:0;border-radius:12px;padding:10px 12px;background:var(--ap-fill);color:var(--ap-label);font:inherit;font-size:16px;margin:4px 0 10px;resize:vertical}" +
    ".vfm-tk-l{display:block;font-weight:700;font-size:14px;margin:0 2px}.vfm-tk-err{color:var(--ap-red,#d33);font-size:13px;margin:0 4px 8px}" +
    ".vfm-tk-btns{display:flex;gap:8px}.vfm-tk-btns button{flex:1;border:0;border-radius:12px;padding:13px;font:inherit;font-weight:700;font-size:16px;background:var(--ap-blue);color:#fff}.vfm-tk-btns .ghost{background:var(--ap-fill);color:var(--ap-label)}";

  /* ── PWA ── */
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", function () { navigator.serviceWorker.register(ROOT + "sw.js", { scope: ROOT }).catch(function () { }); });
  }
  if (!document.querySelector('link[rel="manifest"]')) {
    var l = document.createElement("link"); l.rel = "manifest"; l.href = ROOT + "manifest.webmanifest"; document.head.appendChild(l);
  }
  loadMeta();
  setInterval(loadMeta, 15 * 60 * 1000);
})();
