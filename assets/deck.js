/* deck.js — 자판기 공통 "넘겨보기" 부품 (시사·이야기·AI가 같이 씀).
 *
 *  · 카드 한 장씩 보여 주고, 옆으로 밀면 다음 카드. 위아래로는 그냥 화면이 움직임(카드 안 글을 끝까지 읽기).
 *  · 이미 본 카드는 다시 안 나옴 — 본 기록은 이 폰 저장소(localStorage "vfm:seen:<앱>")에 남김.
 *  · 감도: 손가락이 16px 넘게 움직였을 때 방향을 정하고(가로가 세로보다 조금만 커도 가로 — 엄지는 휘어서 밀기 때문),
 *    화면 너비의 30%(최소 100px) 넘게 밀거나, 80px 넘게 빠르게 밀었을 때 넘어감.
 *  · 외국어 글은 카드가 보일 때 자동으로 한국어로 번역(구글 번역 무료 주소, 폰에 기억). '원문 보기'로 되돌림.
 *    화면 가장자리 28px 안에서 시작한 손가락은 폰 뒤로가기 제스처라서 무시.
 *  · 카드마다 좋아요(♡)·공유 — 좋아요는 "vfm:likes" 하나에 모든 앱 것을 같이 저장.
 *
 * 앱 쪽 사용법:
 *   const d = VfmDeck.create({ id:"sisa-today", app:"sisa", items:()=>[{key, title, url, html:()=>"…"}], onList(){…} });
 *   화면 문자열 안에 d.html() 을 넣으면 됨. 화면을 다시 그려도 보던 카드가 그대로 나옴.
 *   d.refresh() — 자료가 바뀌었을 때(새 판 등) 대기열을 다시 만듦.
 */
(function () {
  "use strict";
  var LS = {
    g: function (k, d) { try { var v = localStorage.getItem(k); return v ? JSON.parse(v) : d; } catch (e) { return d; } },
    s: function (k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { } }
  };
  var esc = function (s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); };

  /* ── 본 기록 ── */
  var seenCache = {};
  function seenMap(app) {
    if (!seenCache[app]) {
      var m = LS.g("vfm:seen:" + app, {}), cut = Date.now() - 60 * 864e5, n = 0;
      Object.keys(m).forEach(function (k) { if (m[k] < cut) delete m[k]; else n++; });
      if (n > 6000) { Object.keys(m).sort(function (a, b) { return m[a] - m[b]; }).slice(0, n - 5000).forEach(function (k) { delete m[k]; }); }
      seenCache[app] = m;
    }
    return seenCache[app];
  }
  var Seen = {
    has: function (app, key) { return !!seenMap(app)[key]; },
    add: function (app, key) { var m = seenMap(app); if (!m[key]) { m[key] = Date.now(); LS.s("vfm:seen:" + app, m); } },
    remove: function (app, keys) { var m = seenMap(app); keys.forEach(function (k) { delete m[k]; }); LS.s("vfm:seen:" + app, m); },
    count: function (app) { return Object.keys(seenMap(app)).length; }
  };

  /* ── 좋아요·공유 ── */
  var likes = LS.g("vfm:likes", {});
  var Like = {
    has: function (app, key) { return !!likes[app + ":" + key]; },
    toggle: function (app, key, info) {
      var k = app + ":" + key;
      if (likes[k]) delete likes[k];
      else likes[k] = { app: app, key: key, t: (info && info.title) || key, u: (info && info.url) || "", h: (info && info.hash) || "", at: Date.now() };
      LS.s("vfm:likes", likes);
      return !!likes[k];
    },
    list: function (app) { return Object.keys(likes).map(function (k) { return likes[k]; }).filter(function (x) { return !app || x.app === app; }).sort(function (a, b) { return b.at - a.at; }); },
    remove: function (app, key) { delete likes[app + ":" + key]; LS.s("vfm:likes", likes); }
  };
  function toast(m) { if (window.vfm && window.vfm.toast) return window.vfm.toast(m); }
  function share(info) {
    var url = info.url || location.href;
    var text = info.text || info.title || "";
    if (navigator.share) return navigator.share({ title: info.title || "", text: text, url: url }).catch(function () { });
    var s = (text ? text + "\n" : "") + url;
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(s).then(function () { toast("복사했어요 — 카톡 등에 붙여넣기"); }, function () { toast("공유하지 못했어요"); });
    else toast("공유하지 못했어요");
  }
  // 좋아요·공유 단추 (카드 밖에서도 씀: 이슈 해설·이야기 읽기 화면 등)
  /* ── 중요 키워드 3개 → 나무위키 (규칙으로 뽑음, 토큰 0) ──
       1) 앱이 준 kw(시사 '꼭 알 낱말', 역사 제목 등)  2) 따옴표 안 말  3) 영문 고유명사(대문자로 시작·줄임말)  4) 짧은 한글 제목 */
  var STOPW = /^(Did|Has|Have|Had|Was|Were|Been|Get|Got|Just|Really|Very|The|A|An|How|Why|What|When|This|That|These|Those|I|It|Is|Are|We|You|My|Our|Your|New|Best|Top|And|Or|For|With|From|In|On|Of|To|At|By|Just|Now|Do|Does|Can|Will|Use|Using|Make|Get|Full|Free|Guide|Tutorial|Video|Videos|Part|Latest|Full|Movie|Movies|Official|Trailer|Episode|Music|Live|Shorts|Short|Funny|Comedy|Song|News|Watch|Must|See|Season|Film|Ft|Feat|Inc|Ltd|Co|Corp|LLC|Day|Week|Year|Here|Why|Who|Not|No|Yes|All|Every|One|Two|Three|Ep|Vs|Hot|Amazing|Insane|Ultimate|Complete)$/;
  // 이름 사전(시사 로봇이 매시간 모으는 인물·기관·지역·용어 600여 개)으로 한글 제목 속 이름 찾기
  var ENTS = null, ENT_RX = null;
  try {
    var base = (document.currentScript && document.currentScript.src) || location.href;
    fetch(new URL("../data/sisa/brief/ents.json", base).href).then(function (r) { return r.ok ? r.json() : null; }).then(function (j) {
      if (!j || !j.map) return; ENTS = {}; var names = [];
      Object.keys(j.map).forEach(function (k) { var e = j.map[k] || {}; if (e.t === "org" && /신문|일간|방송|통신|매체|언론|잡지|주간지|뉴스|채널|TV|라디오/.test(e.r || "")) return; [k].concat(e.a || []).forEach(function (n) { n = String(n).trim(); if (n.length >= 2 && !ENTS[n]) { ENTS[n] = k; names.push(n.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")); } }); });
      names.sort(function (x, y) { return y.length - x.length; });
      ENT_RX = new RegExp(names.join("|"), "g");
    }).catch(function () { });
  } catch (e) { }
  var BRAND = /^(Claude|Anthropic|OpenAI|ChatGPT|GPT[-\d.o]*|Gemini|Google|Microsoft|Apple|Meta|Nvidia|NVIDIA|Tesla|Amazon|AWS|Azure|GitHub|Cursor|Copilot|DeepSeek|Llama|Mistral|Grok|Perplexity|Python|JavaScript|TypeScript|React|Rust|Linux|Windows|Android|iPhone|Samsung|YouTube|TikTok|Netflix|Reddit|Figma|Notion|Supabase|Vercel|Docker|Kubernetes|Excel|Codex|Sora|Midjourney|Bitcoin|Ethereum|SpaceX|Starlink|Trump|Musk|Altman|Zuckerberg)$/;
  function keywords(info) {
    var out = [], seen = {}, add = function (w) { w = String(w || "").replace(/\s*[\(（][^)）]*[\)）]/g, "").replace(/^[#\s'"‘’“”·]+|[\s'"‘’“”·,.!?:]+$/g, "").trim(); var k = w.toLowerCase(); if (w.length < 2 || w.length > 24 || seen[k] || out.some(function (o) { return o.toLowerCase().indexOf(k) >= 0; }) || /[%↓↑→←~$€£¥]/.test(w) || /["“”'‘’!?#|…\u3040-\u30ff\u4e00-\u9fff\uff00-\uffef\u{1F000}-\u{1FAFF}]/u.test(w)) return; seen[k] = 1; out.push(w); };
    (info.kw || []).forEach(add);
    var t = (String(info.title || "") + " " + String(info.text || "").split("\n").slice(0, 2).join(" "))
      .replace(/#\S+/g, " ").replace(/https?:\/\/\S+/g, " ").replace(/[\u{1F000}-\u{1FAFF}\u2600-\u27BF]/gu, " ");
    var tt = String(info.title || "");
    [tt, t].forEach(function (src) { if (out.length < 3 && ENT_RX) { var m; ENT_RX.lastIndex = 0; while ((m = ENT_RX.exec(src)) && out.length < 3) { if (/^[A-Za-z0-9 .&-]+$/.test(m[0]) && (/[A-Za-z0-9]/.test(src.charAt(m.index - 1)) || /[A-Za-z0-9]/.test(src.charAt(m.index + m[0].length)))) continue; add(ENTS[m[0]] || m[0]); } } });   // 제목 먼저, 그다음 본문 · 영문 이름은 낱말 경계에서만
    if (out.length < 3) (t.match(/['‘"“]([^'’"”]{2,18})['’"”]/g) || []).forEach(function (q) { add(q.slice(1, -1)); });
    // 영문 고유명사 — 제목에서만. 제목이 '단어마다 대문자'(Title Case)면 이름 사전·잘 알려진 이름·약어만
    var words = tt.match(/[\p{Script=Latin}]+/gu) || [], caps = words.filter(function (w) { return /^\p{Lu}/u.test(w); }).length, titleCase = words.length >= 3 && caps / words.length > 0.6;
    if (out.length < 3) (tt.match(/(?<![\p{L}\p{N}])\p{Lu}[\p{Script=Latin}\p{N}.+#-]*(?:\s\p{Lu}[\p{Script=Latin}\p{N}.+#-]*){0,2}/gu) || []).forEach(function (w) {
      w = w.trim(); if (STOPW.test(w) || w.length < 2) return;
      if (/^[\p{Lu}\p{N} .+#-]+$/u.test(w) && (w.length > 6 || /\s/.test(w))) return;      // 대문자만 이어진 긴 덩어리(외침)는 버림
      if (titleCase) { w.split(" ").forEach(function (x) { if (BRAND.test(x) || /^[\p{Lu}]{2,5}\d*$/u.test(x) || /\p{Ll}\p{Lu}/u.test(x)) add(x); }); return; }
      add(w);
    });
    if (out.length < 1 && info.title && info.title.length <= 14 && !/[#!?]/.test(info.title)) add(info.title);
    return out.slice(0, 3);
  }
  function kwRow(info) {
    var k = keywords(info); if (!k.length) return "";
    var nm = window.vfm && window.vfm.namu ? window.vfm.namu : function (q) { return "https://namu.wiki/Go?q=" + encodeURIComponent(q); };
    return '<div class="vdk-kw">' + k.map(function (w) { return '<a href="' + esc(nm(w)) + '" target="_blank" rel="noopener">' + esc(w) + "</a>"; }).join("") + "</div>";
  }
  function bar(app, key, info) {
    var on = Like.has(app, key);
    return kwRow(info) + '<div class="vdk-react"><button type="button" class="vdk-like' + (on ? " on" : "") + '" data-vdk-like="' + esc(app + "|" + key) + '" data-vdk-t="' + esc(info.title || "") + '" data-vdk-u="' + esc(info.url || "") + '" data-vdk-h="' + esc(info.hash || "") + '" aria-pressed="' + on + '">' +
      '<span aria-hidden="true">' + (on ? "♥" : "♡") + "</span> 좋아요</button>" +
      '<button type="button" class="vdk-share" data-vdk-think="' + esc(app + "|" + key) + '" data-vdk-t="' + esc(info.title || "") + '" data-vdk-u="' + esc(info.url || "") + '"><span aria-hidden="true">✎</span> 생각</button>' +
      '<button type="button" class="vdk-share" data-vdk-share="1" data-vdk-t="' + esc(info.title || "") + '" data-vdk-u="' + esc(info.url || "") + '" data-vdk-x="' + esc(info.text || "") + '"><span aria-hidden="true">↗</span> 공유</button></div>';
  }

  /* ── 덱 ── */
  var decks = {};
  function Deck(o) {
    this.o = o; this.id = o.id; this.app = o.app;
    var st = LS.g("vfm:deck:" + o.id, {});
    this.cur = st.cur || null;          // 보던 카드 (다시 열면 이 카드부터)
    this.hist = [];                     // 이번에 넘겨 본 순서 (이전 카드로 돌아가기용)
    this.pos = -1;
    this.map = {};
    this.queue = null;
    decks[o.id] = this;
  }
  Deck.prototype.sa = function (k) { var it = this.map[k]; return (it && it.sa) || this.app; };
  Deck.prototype.seen = function (k) { return !this.o.noSeen && Seen.has(this.sa(k), k); };
  Deck.prototype.build = function () {
    var self = this, all = this.o.items() || [];
    this.map = {}; all.forEach(function (it) { self.map[it.key] = it; });
    this.total = all.length;
    this.queue = all.filter(function (it) { return !self.seen(it.key); }).map(function (it) { return it.key; });
    this.hist = this.hist.filter(function (k) { return self.map[k]; });
    if (this.pos >= this.hist.length) this.pos = this.hist.length - 1;
    if (this.pos < 0) {
      var start = this.cur && this.map[this.cur] ? this.cur : this.queue[0];
      if (start) { this.hist = [start]; this.pos = 0; }
    }
  };
  Deck.prototype.refresh = function () { this.queue = null; this.hist = []; this.pos = -1; this.paint(); };
  Deck.prototype.ensure = function () { if (!this.queue) this.build(); };
  Deck.prototype.curKey = function () { this.ensure(); return this.pos >= 0 ? this.hist[this.pos] : null; };
  Deck.prototype.left = function () {   // 아직 안 본 카드 수 (지금 카드 제외)
    var self = this, k = this.curKey(), used = {};
    this.hist.forEach(function (x) { used[x] = 1; });
    return this.queue.filter(function (x) { return !used[x] && !self.seen(x) && x !== k; }).length;
  };
  Deck.prototype.save = function () { LS.s("vfm:deck:" + this.id, { cur: this.curKey() }); };
  Deck.prototype.markCur = function () { var k = this.curKey(); if (k) Seen.add(this.sa(k), k); };
  Deck.prototype.next = function () {
    this.ensure();
    var self = this, k = this.curKey();
    if (!k && this.pos >= this.hist.length) return false;
    this.markCur();
    if (this.pos < this.hist.length - 1) { this.pos++; }
    else {
      var used = {}; this.hist.forEach(function (x) { used[x] = 1; });
      var nx = this.queue.filter(function (x) { return !used[x] && !self.seen(x); })[0];
      if (!nx) { this.pos = this.hist.length; this.save(); return true; }   // 끝 카드
      this.hist.push(nx); this.pos++;
      try { window.vfm && window.vfm.tick && window.vfm.tick("card", true); } catch (e) { }   // 새 카드 한 장 (assets/joy.js)
    }
    this.save(); return true;
  };
  // 다음에 나올 카드 n장 (넘기기 전에 사진을 미리 받아 두려고)
  Deck.prototype.upcoming = function (n) {
    this.ensure();
    var self = this, out = [], used = {};
    this.hist.forEach(function (x) { used[x] = 1; });
    for (var i = this.pos + 1; i < this.hist.length && out.length < n; i++) out.push(this.hist[i]);
    for (var j = 0; j < this.queue.length && out.length < n; j++) { var x = this.queue[j]; if (!used[x] && !self.seen(x) && x !== this.curKey()) out.push(x); }
    return out;
  };
  // 다음 카드 3장의 사진을 미리 받아 둠 → 넘기면 바로 보임 (사진 서버가 처음 받는 사진은 줄이는 데 1~2초 걸려서)
  var WARMED = {};
  Deck.prototype.warm = function () {
    var self = this;
    clearTimeout(this.warmT);
    this.warmT = setTimeout(function () {
      self.upcoming(3).forEach(function (k) {
        if (WARMED[self.id + "|" + k]) return; WARMED[self.id + "|" + k] = 1;
        var it = self.map[k], h = ""; if (!it) return;
        try { h = it.html(); } catch (e) { return; }
        var box = document.createElement("template"); box.innerHTML = h;            // template 안은 그리지도 받지도 않음 → 주소만 뽑음
        box.content.querySelectorAll("img").forEach(function (im) {
          var src = im.getAttribute("src"), wt = im.getAttribute("data-wt");
          if (src && !/^data:/.test(src)) { var p = new Image(); p.decoding = "async"; p.referrerPolicy = "no-referrer"; p.src = src; }
          else if (wt && window.WT && window.WT.warm) window.WT.warm(wt);
        });
        box.content.querySelectorAll("[data-yt]").forEach(function (sp) { var p = new Image(); p.src = "https://i.ytimg.com/vi/" + sp.getAttribute("data-yt") + "/hqdefault.jpg"; });
      });
    }, 250);
  };
  Deck.prototype.prev = function () {
    this.ensure();
    if (this.pos <= 0) { toast("첫 카드예요"); return false; }
    if (this.pos < this.hist.length) this.markCur();
    this.pos--; this.save(); return true;
  };
  Deck.prototype.resetSeen = function () {
    var self = this, by = {};
    Object.keys(this.map).forEach(function (k) { (by[self.sa(k)] = by[self.sa(k)] || []).push(k); });
    Object.keys(by).forEach(function (a) { Seen.remove(a, by[a]); });
    this.cur = null; LS.s("vfm:deck:" + this.id, {});
    this.refresh();
  };
  Deck.prototype.cardHtml = function () {
    var k = this.curKey(), it = k && this.map[k];
    if (!it) {
      var n = this.total || 0;
      return '<div class="vdk-card vdk-end"><p class="vdk-big">' + (n ? "다 봤어요" : esc(this.o.emptyTitle || "아직 카드가 없어요")) + "</p>" +
        '<p class="vdk-note">' + (n ? "여기 있는 " + n + "장을 모두 봤어요. 새 자료가 들어오면 안 본 것만 다시 나와요." : esc(this.o.emptyNote || "")) + "</p>" +
        '<div class="vdk-endbtn">' + (this.o.onList ? '<button type="button" class="vdk-btn" data-vdk-act="list" data-vdk="' + esc(this.id) + '">목록으로 보기</button>' : "") +
        (n ? '<button type="button" class="vdk-btn ghost" data-vdk-act="reset" data-vdk="' + esc(this.id) + '">본 기록 지우고 처음부터</button>' : "") +
        (this.pos > 0 ? '<button type="button" class="vdk-btn ghost" data-vdk-act="prev" data-vdk="' + esc(this.id) + '">‹ 방금 본 카드</button>' : "") + "</div></div>";
    }
    var body = ""; try { body = it.html(); } catch (e) { body = '<p class="vdk-note">이 카드를 그리지 못했어요.</p>'; }
    var left = this.left();
    return '<div class="vdk-card" data-vdk-card="' + esc(this.id) + '">' + body +
      bar(this.sa(k), k, { title: it.title, url: it.url, hash: it.hash, text: it.shareText, kw: it.kw }) +
      '<div class="vdk-nav"><button type="button" data-vdk-act="prev" data-vdk="' + esc(this.id) + '" ' + (this.pos <= 0 ? "disabled" : "") + ' aria-label="이전 카드">‹</button>' +
      '<span class="vdk-left">' + (left ? "안 본 카드 " + left + "장 남음" : "마지막 카드") + '<small>옆으로 밀면 다음</small></span>' +
      '<button type="button" data-vdk-act="next" data-vdk="' + esc(this.id) + '" aria-label="다음 카드">›</button></div></div>';
  };
  Deck.prototype.html = function () {
    this.ensure();
    this.armDwell(); this.warm();
    var head = this.o.head ? this.o.head() : "";
    return '<div class="vdk" data-vdk-host="' + esc(this.id) + '">' + head + this.cardHtml() + "</div>";
  };
  Deck.prototype.el = function () {   // 숨겨진 옛 화면에 남은 같은 덱은 빼고, 지금 보이는 것
    var all = document.querySelectorAll('[data-vdk-host="' + this.id + '"]');
    for (var i = 0; i < all.length; i++) if (all[i].offsetParent !== null) return all[i];
    return all[0] || null;
  };
  Deck.prototype.paint = function (dir) {
    var host = this.el(); if (!host) return;
    this.ensure();
    var old = host.querySelector(".vdk-card");
    var tmp = document.createElement("div"); tmp.innerHTML = this.cardHtml();
    var card = tmp.firstChild;
    if (old) old.replaceWith(card); else host.appendChild(card);
    if (dir) { card.classList.add(dir > 0 ? "in-r" : "in-l"); requestAnimationFrame(function () { requestAnimationFrame(function () { card.classList.remove("in-r", "in-l"); }); }); }
    var top = host.getBoundingClientRect().top;
    if (dir && (top < 0 || top > window.innerHeight * 0.6)) window.scrollTo({ top: Math.max(0, window.scrollY + top - 8), behavior: dir ? "auto" : "smooth" });
    this.armDwell(); this.warm();
    if (this.o.onShow) { var k = this.curKey(); if (k && this.map[k]) try { this.o.onShow(this.map[k]); } catch (e) { } }
    var k2 = this.curKey(), it = k2 && this.map[k2];                                     // 배운 길(trail.js)에 알림
    if (it) try { document.dispatchEvent(new CustomEvent("vfm:deckshow", { detail: { key: k2, title: it.title, url: it.url, app: it.sa || this.app } })); } catch (e) { }
  };
  // 한 카드를 4초 넘게 보고 있으면 본 것으로 (앱을 껐다 켜도 다시 안 나오게. 보던 카드는 cur 로 남아 그대로 보임)
  Deck.prototype.armDwell = function () {
    var self = this, k = this.curKey();
    clearTimeout(this.dwellT);
    if (!k) return;
    this.dwellT = setTimeout(function () { if (self.curKey() === k && self.el()) { Seen.add(self.sa(k), k); self.save(); } }, 4000);
  };
  Deck.prototype.step = function (dir) {
    var ok = dir > 0 ? this.next() : this.prev();
    if (ok) this.paint(dir);
  };

  /* ── 손가락 밀기 ── */
  var g = null;
  var EDGE = 28;
  document.addEventListener("touchstart", function (e) {
    g = null;
    if (e.touches.length !== 1) return;
    var card = e.target.closest && e.target.closest(".vdk-card[data-vdk-card]"); if (!card) return;
    if (e.target.closest("input,textarea,select,.vdk-noswipe,details[open] .vdk-noswipe")) return;
    var x = e.touches[0].clientX, W = window.innerWidth;
    if (x < EDGE || x > W - EDGE) return;                              // 폰 뒤로가기 제스처 자리
    // 가로로 스크롤되는 줄(칩 줄 등) 위에서는 카드를 넘기지 않음
    for (var n = e.target; n && n !== card; n = n.parentElement) {
      if (n.scrollWidth > n.clientWidth + 2) { var ox = getComputedStyle(n).overflowX; if (ox === "auto" || ox === "scroll") return; }
    }
    g = { card: card, id: card.getAttribute("data-vdk-card"), x0: x, y0: e.touches[0].clientY, t0: Date.now(), dx: 0, lock: null, lastX: x, lastT: Date.now(), v: 0 };
  }, { passive: true });
  document.addEventListener("touchmove", function (e) {
    if (!g) return;
    var x = e.touches[0].clientX, y = e.touches[0].clientY, dx = x - g.x0, dy = y - g.y0;
    // 방향 정하기: 엄지로 밀면 살짝 휘어지므로 가로가 세로보다 조금만 커도 '옆으로'.
    // 세로로 시작했어도 0.35초 안에 확실히 옆으로 가면(가로 60px 이상, 세로의 1.5배) 옆으로 바꿔 줌
    if (g.lock === null || g.lock === "v") {
      if (Math.abs(dx) < 16 && Math.abs(dy) < 16) return;
      if (g.lock === null) g.lock = Math.abs(dx) > Math.abs(dy) * 1.1 ? "h" : "v";
      else if (Date.now() - g.t0 < 350 && Math.abs(dx) >= 60 && Math.abs(dx) > Math.abs(dy) * 1.5) g.lock = "h";
      if (g.lock === "v") { if (Date.now() - g.t0 > 350) g = null; return; }   // 세로 = 그냥 스크롤
    }
    if (e.cancelable) e.preventDefault();                                   // 옆으로 미는 동안 화면이 위아래로 흔들리지 않게
    var now = Date.now(); if (now > g.lastT) { g.v = (x - g.lastX) / (now - g.lastT); g.lastX = x; g.lastT = now; }
    g.dx = dx;
    g.card.style.transition = "none";
    g.card.style.transform = "translateX(" + (dx * 0.85) + "px) rotate(" + (dx / 60).toFixed(2) + "deg)";
  }, { passive: false });
  function settle(card) { card.style.transition = "transform .2s ease-out"; card.style.transform = ""; }
  document.addEventListener("touchcancel", function () { if (g) settle(g.card); g = null; }, { passive: true });
  document.addEventListener("touchend", function () {
    if (!g) return; var s = g; g = null;
    if (s.lock !== "h") return;
    // 중간 감도: 화면 너비의 30%(최소 100px) 넘게 밀거나, 80px 넘게 '쓱' 빠르게 밀면 넘어감
    var W = window.innerWidth, need = Math.max(100, W * 0.3);
    var fling = Math.abs(s.dx) >= 80 && Math.abs(s.v) >= 0.6 && (s.v < 0) === (s.dx < 0);
    var d = decks[s.id];
    if (!d || (Math.abs(s.dx) < need && !fling)) return settle(s.card);
    var dir = s.dx < 0 ? 1 : -1;                                          // 왼쪽으로 밀면 다음
    if (dir < 0 && d.pos <= 0) { toast("첫 카드예요"); return settle(s.card); }
    s.card.style.transition = "transform .16s ease-in, opacity .16s";
    s.card.style.transform = "translateX(" + (dir > 0 ? -W : W) + "px) rotate(" + (dir > 0 ? -6 : 6) + "deg)";
    s.card.style.opacity = "0";
    setTimeout(function () { d.step(dir); }, 150);
  });
  // 컴퓨터: ← → 키
  document.addEventListener("keydown", function (e) {
    if (e.target.closest && e.target.closest("input,textarea,select")) return;
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    var host = [].filter.call(document.querySelectorAll("[data-vdk-host]"), function (h) { return h.offsetParent !== null; })[0]; if (!host) return;
    var d = decks[host.getAttribute("data-vdk-host")]; if (!d) return;
    e.preventDefault(); d.step(e.key === "ArrowRight" ? 1 : -1);
  });

  /* ── 단추 ── */
  document.addEventListener("click", function (e) {
    var t = e.target.closest && e.target.closest("[data-vdk-act],[data-vdk-like],[data-vdk-share],[data-vdk-mode],[data-vdk-think]"); if (!t) return;
    if (t.hasAttribute("data-vdk-think")) { var tk = t.getAttribute("data-vdk-think").split("|"); if (window.vfm && window.vfm.think) window.vfm.think({ app: tk[0], key: tk.slice(1).join("|"), title: t.getAttribute("data-vdk-t"), url: t.getAttribute("data-vdk-u") }); return; }
    if (t.hasAttribute("data-vdk-like")) {
      var p = t.getAttribute("data-vdk-like").split("|"), app = p[0], key = p.slice(1).join("|");
      var on = Like.toggle(app, key, { title: t.getAttribute("data-vdk-t"), url: t.getAttribute("data-vdk-u"), hash: t.getAttribute("data-vdk-h") });
      t.classList.toggle("on", on); t.setAttribute("aria-pressed", on); t.firstChild.textContent = on ? "♥" : "♡";
      toast(on ? "좋아요 — 내 기록에 모아 둬요" : "좋아요를 취소했어요"); return;
    }
    if (t.hasAttribute("data-vdk-share")) { share({ title: t.getAttribute("data-vdk-t"), url: t.getAttribute("data-vdk-u"), text: t.getAttribute("data-vdk-x") }); return; }
    if (t.hasAttribute("data-vdk-mode")) {
      var pm = t.getAttribute("data-vdk-mode").split("|");
      LS.s("vfm:mode:" + pm[0], pm[1]);
      var cb = modeCb[pm[0]]; if (cb) cb(pm[1]); return;
    }
    var d = decks[t.getAttribute("data-vdk")]; if (!d) return;
    var act = t.getAttribute("data-vdk-act");
    if (act === "next") d.step(1);
    else if (act === "prev") d.step(-1);
    else if (act === "reset") { d.resetSeen(); toast("본 기록을 지웠어요"); }
    else if (act === "list" && d.o.onList) d.o.onList();
  });

  /* ── 외국어 자동 번역 (카드가 화면에 나올 때만, 한 번 번역한 글은 폰에 기억) ── */
  var TRC = LS.g("vfm:trc", {}), trFail = 0, trStop = 0, trQ = Promise.resolve();
  function needTr(t) {
    t = (t || "").trim(); if (t.length < 6) return false;
    var h = (t.match(/[가-힣]/g) || []).length, l = (t.match(/[A-Za-zÀ-ɏЀ-ӿ぀-ヿ一-鿿؀-ۿ฀-๿]/g) || []).length;
    return l >= 5 && l > h * 3;
  }
  function tr1(t) {
    if (TRC[t]) return Promise.resolve(TRC[t]);
    if (Date.now() < trStop) return Promise.resolve(null);
    trQ = trQ.then(function () {
      if (TRC[t]) return TRC[t];
      return fetch("https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=ko&dt=t&q=" + encodeURIComponent(t.slice(0, 1800)))
        .then(function (r) { if (!r.ok) throw 0; return r.json(); })
        .then(function (j) {
          var ko = (j[0] || []).map(function (x) { return x[0]; }).join("").trim(); trFail = 0;
          if (ko) { TRC[t] = ko; var ks = Object.keys(TRC); if (ks.length > 900) ks.slice(0, 300).forEach(function (k) { delete TRC[k]; }); LS.s("vfm:trc", TRC); }
          return ko || null;
        }, function () { if (++trFail >= 3) { trStop = Date.now() + 10 * 60e3; trFail = 0; } return null; });
    });
    return trQ;
  }
  var TR_SEL = ".vdk-t,.vdk-p,.vdk-ol li,.vdk-links a,.vdk-links button,.vdk-links small";
  function autoTr(card) {
    if (!card || card.getAttribute("data-trd")) return;
    card.setAttribute("data-trd", "1");
    var jobs = [];
    [].forEach.call(card.querySelectorAll(TR_SEL), function (el) {
      [].forEach.call(el.childNodes, function (n) {
        if (n.nodeType === 3 && needTr(n.nodeValue) && jobs.length < 14) jobs.push(n);
      });
    });
    if (!jobs.length) return;
    var done = 0;
    jobs.forEach(function (n) {
      var orig = n.nodeValue;
      tr1(orig.trim()).then(function (ko) {
        if (!ko || !n.parentNode) return;
        n.__orig = orig; n.__ko = ko; n.nodeValue = ko; done++;
        if (done === 1) {
          var b = document.createElement("button"); b.type = "button"; b.className = "vdk-trnote"; b.textContent = "외국어는 자동 번역했어요 · 원문 보기";
          b.addEventListener("click", function () {
            var showOrig = b.getAttribute("data-o") !== "1"; b.setAttribute("data-o", showOrig ? "1" : "0");
            jobs.forEach(function (x) { if (x.__ko) x.nodeValue = showOrig ? x.__orig : x.__ko; });
            b.textContent = showOrig ? "원문을 보고 있어요 · 번역 보기" : "외국어는 자동 번역했어요 · 원문 보기";
          });
          var react = card.querySelector(".vdk-react"); card.insertBefore(b, react || null);
        }
      });
    });
  }
  // 앱이 화면을 새로 그려 카드가 생기면 번역
  var trT = null;
  new MutationObserver(function () { clearTimeout(trT); trT = setTimeout(function () { [].forEach.call(document.querySelectorAll(".vdk-card[data-vdk-card]:not([data-trd])"), function (c) { if (c.offsetParent !== null) autoTr(c); }); }, 120); })
    .observe(document.documentElement, { childList: true, subtree: true });

  /* ── 넘겨보기 / 목록 고르기 ── */
  var modeCb = {};
  function mode(id) { return LS.g("vfm:mode:" + id, "deck"); }
  function modeSwitch(id, onChange) {
    modeCb[id] = onChange;
    var m = mode(id);
    return '<div class="vdk-mode" role="group" aria-label="보기 방식"><button type="button" data-vdk-mode="' + esc(id) + '|deck" aria-pressed="' + (m === "deck") + '">넘겨보기</button>' +
      '<button type="button" data-vdk-mode="' + esc(id) + '|list" aria-pressed="' + (m === "list") + '">목록</button></div>';
  }

  /* ── 원문 주소 (예전엔 구글 번역 프록시로 열었지만 한국에서 막혀서 지금은 원래 주소 그대로) ── */
  // 구글 번역 프록시(*.translate.goog)는 한국에서 막혀 있어(“이 지역에서는 쓸 수 없어요”) 원래 페이지로 바로 연결
  function koUrl(u, lang) {
    return u;
    if (!u) return u;
    if (lang === "ko") return u;
    try {
      var x = new URL(u);
      if (!/^https?:$/.test(x.protocol) || /\.translate\.goog$/.test(x.hostname)) return u;
      if (/(^|\.)(youtube\.com|youtu\.be|x\.com|twitter\.com|naver\.com|daum\.net|google\.[a-z.]+)$/.test(x.hostname) && lang !== "force") return u;
      if (/\.(kr)$/.test(x.hostname) && lang === undefined) return u;
      var host = x.hostname.replace(/-/g, "--").replace(/\./g, "-") + ".translate.goog";
      var q = x.search ? x.search + "&" : "?";
      return "https://" + host + x.pathname + q + "_x_tr_sl=auto&_x_tr_tl=ko&_x_tr_hl=ko" + x.hash;
    } catch (e) { return u; }
  }

  /* ── 모양 ── */
  var css = document.createElement("style");
  css.textContent =
    ".vdk{margin:6px 0 18px}" +
    ".vdk-card{position:relative;background:var(--surface,var(--ap-surface,#fff));color:var(--ink,var(--ap-label,#111));border-radius:18px;padding:18px 16px 12px;" +
    "box-shadow:0 1px 2px rgba(0,0,0,.06),0 8px 24px rgba(0,0,0,.06);touch-action:pan-y;transition:transform .2s ease-out,opacity .2s;will-change:transform;min-height:52vh;display:flex;flex-direction:column}" +
    ".vdk-card.in-r{transform:translateX(40px);opacity:0}.vdk-card.in-l{transform:translateX(-40px);opacity:0}" +
    ".vdk-card>.vdk-body{flex:1}" +
    ".vdk-end{align-items:center;justify-content:center;text-align:center;gap:6px}" +
    ".vdk-big{font-size:24px;font-weight:700;margin:0}.vdk-note{color:var(--muted,var(--ap-label2,#666));font-size:14px;line-height:1.5;margin:4px 0}" +
    ".vdk-endbtn{display:flex;flex-direction:column;gap:8px;margin-top:12px;width:100%;max-width:300px}" +
    ".vdk-btn{border:0;border-radius:12px;padding:12px 14px;font:inherit;font-weight:600;background:var(--ap-tint,#0A84FF);color:#fff;cursor:pointer}" +
    ".vdk-btn.ghost{background:var(--ap-fill,rgba(118,118,128,.12));color:var(--ink,var(--ap-label,#111))}" +
    ".vdk-react{display:flex;gap:8px;margin:14px 0 4px}" +
    ".vdk-kw{display:flex;flex-wrap:wrap;gap:6px;margin:12px 0 0}.vdk-kw a{font-size:13.5px;font-weight:600;padding:6px 11px;border-radius:999px;text-decoration:none;color:#00897B;background:rgba(0,164,149,.12)}.vdk-kw a::after{content:'\\00a0↗';font-size:11px;opacity:.7}" +
    "@media (prefers-color-scheme:dark){.vdk-kw a{color:#5FD3C4;background:rgba(0,164,149,.2)}}.vdk-react button{flex:1;border:0;border-radius:12px;padding:10px 8px;font:inherit;font-size:14.5px;font-weight:600;background:var(--ap-fill,rgba(118,118,128,.12));color:var(--ink,var(--ap-label,#111));cursor:pointer}" +
    ".vdk-like.on{color:var(--ap-pink,#FF2D55);background:color-mix(in srgb,var(--ap-pink,#FF2D55) 13%,transparent)}" +
    ".vdk-nav{display:flex;align-items:center;gap:8px;margin-top:8px;padding-top:8px;border-top:.5px solid var(--ap-sep,rgba(60,60,67,.29))}" +
    ".vdk-nav button{flex:none;width:48px;height:44px;border:0;border-radius:12px;background:var(--ap-fill,rgba(118,118,128,.12));font-size:24px;line-height:1;color:var(--ink,var(--ap-label,#111));cursor:pointer}" +
    ".vdk-nav button:disabled{opacity:.35}" +
    ".vdk-left{flex:1;text-align:center;font-size:13px;color:var(--muted,var(--ap-label2,#666));display:flex;flex-direction:column;gap:1px}.vdk-left small{font-size:11.5px;opacity:.8}" +
    ".vdk-mode{display:grid;grid-template-columns:1fr 1fr;gap:2px;padding:3px;border-radius:11px;background:var(--ap-fill,rgba(118,118,128,.12));margin:4px 0 10px}" +
    ".vdk-mode button{border:0;border-radius:8px;padding:8px 0;font:inherit;font-size:14px;font-weight:600;background:transparent;color:var(--ink,var(--ap-label,#111));cursor:pointer}" +
    ".vdk-mode button[aria-pressed=true]{background:var(--ap-seg-on,#fff);box-shadow:0 2px 6px rgba(0,0,0,.12)}" +
    ".vdk-k{display:flex;flex-wrap:wrap;gap:6px;align-items:center;font-size:12.5px;color:var(--muted,var(--ap-label2,#666));margin-bottom:6px}" +
    ".vdk-t{font-size:21px;line-height:1.35;font-weight:700;margin:2px 0 10px;letter-spacing:-.01em}" +
    ".vdk-p{font-size:16px;line-height:1.65;margin:0 0 10px}" +
    ".vdk-h{font-size:13px;font-weight:700;color:var(--muted,var(--ap-label2,#666));margin:16px 0 6px}" +
    ".vdk-ol{margin:0;padding-left:20px;font-size:15px;line-height:1.6}.vdk-ol li{margin-bottom:4px}" +
    ".vdk-links{display:flex;flex-direction:column;gap:2px}" +
    ".vdk-links a,.vdk-links button{display:block;text-align:left;width:100%;border:0;background:none;padding:9px 0;font:inherit;font-size:14.5px;line-height:1.45;color:inherit;text-decoration:none;border-top:.5px solid var(--ap-sep,rgba(60,60,67,.2));cursor:pointer}" +
    ".vdk-links small{display:block;color:var(--muted,var(--ap-label2,#666));font-size:12px}" +
    ".vdk-trnote{display:block;width:100%;margin:10px 0 0;border:0;background:none;padding:4px 0;text-align:left;font:inherit;font-size:12.5px;color:var(--muted,var(--ap-label2,#666));cursor:pointer}" +
    ".vdk-more{display:block;text-align:left;margin-top:6px;font-weight:600;color:var(--ap-tint-t,var(--accent,#0066D6));background:none;border:0;padding:6px 0;font:inherit;cursor:pointer;text-decoration:none}";
  document.head.appendChild(css);

  window.VfmDeck = { stale: function (app) { Object.keys(decks).forEach(function (k) { if (decks[k].app === app) decks[k].queue = null; }); }, create: function (o) { if (decks[o.id]) { decks[o.id].o = o; return decks[o.id]; } return new Deck(o); }, get: function (id) { return decks[id]; }, mode: mode, modeSwitch: modeSwitch, bar: bar, kwRow: kwRow, keywords: keywords, share: share, koUrl: koUrl, Seen: Seen, Like: Like, esc: esc };
})();
