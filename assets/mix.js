/* mix.js — 자판기 홈의 "랜덤 넘겨보기" + 한 번에 찾기 + 섞는 비율. 토큰 0.
 *  재료: 시사 이야기·단신 / 나라별 오늘 / 트렌드(22개국 검색어·영상) / 레딧·밈 / AI 새 기능 / 도구·오픈소스 / 이야기·역사(가끔)
 *  · 새 것 위주로 섞음(최근 것이 앞쪽에 몰리게 섞은 뒤, 종류는 비율대로 뽑음)
 *  · 본 카드는 그 앱의 본 기록에도 남음 → 앱에 들어가도 다시 안 나옴
 *  · 비율은 종류마다 많이·보통·적게·끄기 (폰에 저장)
 */
(function () {
  "use strict";
  var D = window.VfmDeck, T = window.VfmTrend, esc = D.esc, flag = T.flag;
  var KINDS = [["sisa", "시사 이야기·단신"], ["trend", "트렌드 (검색어·영상)"], ["meme", "레딧·밈"], ["ai", "AI 새 기능"], ["tool", "도구·오픈소스"], ["nation", "나라별 오늘"], ["story", "이야기·역사"]];
  if (window.VFM_KINDS) KINDS = KINDS.filter(function (k) { return window.VFM_KINDS.indexOf(k[0]) >= 0; });
  var DEF = { sisa: 3, trend: 3, meme: 2, ai: 2, tool: 2, nation: 2, story: 1 };
  var WNAME = ["끄기", "적게", "보통", "많이"];
  var W = Object.assign({}, DEF, (function () { try { return JSON.parse(localStorage.getItem("vfm:mix:w") || "{}"); } catch (e) { return {}; } })());
  var POOL = { sisa: [], trend: [], meme: [], ai: [], tool: [], nation: [], story: [] };
  var CAT = { war: "전쟁·안보", pol: "정치·외교", eco: "경제·시장", tech: "기술·과학", dis: "재난·사고", soc: "사회", spo: "스포츠", cul: "문화" };
  var RK = null; try { RK = new Intl.DisplayNames(["ko"], { type: "region" }); } catch (e) { }
  var cname = function (c) { if (c === "WW") return "세계"; try { return RK ? RK.of(c) : c; } catch (e) { return c; } };
  var HAN = /[가-힣]/;
  // 영문 원제목에서 고유명사(대문자로 시작) 뽑기 — 번역문보다 원문이 정확 (나무위키 링크용 키워드)
  function KWOF(ko, en) { return D.keywords ? D.keywords({ title: en || "", text: "" }).concat(D.keywords({ title: ko || "", text: "" })) : []; }
  // 글자 수로 잘린 요약을 낱말 끝에서 다시 자르고 … 를 붙임 (예: '저장공' → '…')
  function tidy(t, cut) {
    t = String(t || "").trim(); if (!t) return "";
    if (/[.!?。」”"')\]다요음함됨임]$/.test(t) && !cut) return t;
    var i = Math.max(t.lastIndexOf(". "), t.lastIndexOf("다. "), t.lastIndexOf("요. "));
    if (i > t.length * 0.6) return t.slice(0, i + 1).trim();
    var sp = t.lastIndexOf(" "); return (sp > t.length * 0.7 ? t.slice(0, sp) : t).replace(/[,·\s]+$/, "") + "…";
  }
  var go = function (h) { return ' data-mixgo="' + esc(h) + '"'; };
  // 사진 한 장: 유튜브면 눌러서 바로 재생, 아니면 로봇이 받아 둔 대표 사진 (shell.js 의 vfm.pic)
  function media(p) {
    if (p.vid) return '<span class="vdk-img vdk-play" data-yt="' + esc(p.vid) + '"' + (p.short || p.kind === "쇼츠" || /#shorts?\b/i.test(p.title || "") || /\/shorts\//.test(p.url || "") ? " data-short" : "") + ' role="button" aria-label="여기서 영상 재생"><img src="https://i.ytimg.com/vi/' + esc(p.vid) + '/hqdefault.jpg" alt="" loading="lazy" referrerpolicy="no-referrer"><i>▶</i></span>';
    if (p.img && window.vfm && vfm.pic) return '<span class="vdk-img vfm-picw' + (/opengraph\.githubassets/.test(p.img) ? " gh" : "") + '">' + vfm.pic(p.img, 820) + "</span>";
    return "";
  }
  var cmts = function (p) { return p.cm && window.vfm && vfm.ytComments ? vfm.ytComments(p.cm) : ""; };
  // 처음 자료를 다 받을 때까지(최대 6초) 카드를 고르지 않음 → 홈에 돌아오면 보던 카드가 그대로 나옴
  var READY = false, pending = 0;
  function ready() { if (READY) return; READY = true; D.stale("mix"); var d = D.get("mix-home"); if (d && !(document.getElementById("mxq") || {}).value) d.paint(); }
  setTimeout(ready, 6000);
  function j(p) {
    pending++;
    return fetch(p, { cache: "no-cache" }).then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; })
      .then(function (x) { pending--; setTimeout(function () { if (pending === 0) ready(); }, 0); return x; });
  }
  // 새 것 위주 섞기: 앞쪽(새 것) 절반을 섞고, 뒤쪽을 섞어 이어 붙임
  function freshShuffle(a) {
    var sh = function (x) { for (var i = x.length - 1; i > 0; i--) { var k = Math.floor(Math.random() * (i + 1)); var t = x[i]; x[i] = x[k]; x[k] = t; } return x; };
    var n = Math.max(1, Math.ceil(a.length * 0.4));
    return sh(a.slice(0, n)).concat(sh(a.slice(n)));
  }
  function add(kind, list) {
    if (kind === "trend" || kind === "meme") {                     // 여러 나라가 따로 도착하니, 순위대(1~3위, 4~6위…)끼리 나라를 섞어서
      list.forEach(function (x) { x._b = Math.floor((x.rank || 0) / 3); x._r = Math.random(); });
      POOL[kind] = POOL[kind].concat(list).sort(function (a, b) { return a._b - b._b || a._r - b._r; });
    } else POOL[kind] = POOL[kind].concat(freshShuffle(list));
    D.stale("mix");
    var d = D.get("mix-home"); var el = d && d.el(); if (el && !document.getElementById("mxq").value.trim() && el.querySelector(".vdk-end")) d.paint();   // 읽던 카드는 건드리지 않음 (빈 화면일 때만 다시 그림)
  }

  /* ── 재료 받기 ── */
  // 시사: 최신 판 하나만 (이야기·단신·나라별 오늘)
  j("data/sisa/_meta.json").then(function (m) {
    if (!m || !m.edition) return;
    return j("data/sisa/editions/" + m.edition + ".json").then(function (ed) {
      if (!ed) return;
      var st = (ed.stories || []).filter(function (s) { return s.title && (s.key || s.sum); });
      var rank = function (s) { return (s.top ? 0 : 2) + (s.delta === "new" ? 0 : 1) + (s.kind === "brief" ? 2 : 0); };
      st.sort(function (a, b) { return rank(a) - rank(b); });
      add("sisa", st.map(function (s) {
        var brief = s.kind === "brief", key = brief ? "b:" + (s.items[0] || s.id) : "i:" + s.title, cs = s.countries || [];
        return { key: key, sa: "sisa", kind: "sisa", kw: (s.terms || []).map(function (t) { return t.t; }), title: s.title, url: location.origin + location.pathname + "sisa/#issue-" + s.id, shareText: s.title + (s.key ? "\n" + s.key : ""),
          q: s.title + " " + (s.key || ""), s: s, ed: m.edition, html: function () {
            var w3 = s.why3 || {}, li = function (a) { return a.map(function (b) { return "<li>" + b + "</li>"; }).join(""); }, n = 0;
            var sec = function (t, body) { if (!body) return ""; n++; return '<p class="mx-ih"><span>' + n + "</span>" + t + "</p>" + body; };
            var its = (s.first || []).concat((s.items || []).filter(function (x) { return (s.first || []).indexOf(x) < 0; })).map(function (x) { return FEEDBY && FEEDBY[x]; }).filter(Boolean);
            var seenT = {}, tl = its.filter(function (i) { return i.p && i.k !== "trend"; }).sort(function (a, b) { return String(a.p).localeCompare(String(b.p)); }).filter(function (i) { var k = i.ko || i.t; if (seenT[k]) return false; seenT[k] = 1; return true; });
            var ops = its.filter(function (i) { return CM[i.id] && CM[i.id].picks && CM[i.id].picks.length; }).slice(0, 4);
            var when = function (p) { var d = new Date(p); return (d.getMonth() + 1) + "/" + d.getDate() + " " + String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0"); };
            var art = function (i) { return '<a href="' + esc(D.koUrl(i.u, i.l)) + '" target="_blank" rel="noopener">' + esc(i.ko || i.t) + "<small>" + flag(i.c) + " " + esc(cname(i.c)) + (i.p ? " · " + when(i.p) : "") + "</small></a>"; };
            return '<div class="vdk-body"><div class="vdk-k"><span class="mx-tag sisa">시사</span>' + (CAT[s.cat] ? "<span>" + CAT[s.cat] + "</span>" : "") + "<span>" + cs.slice(0, 6).map(flag).join("") + "</span><span>" + (brief ? "단신" : cs.length + "개국 · 기사 " + (s.items || []).length) + "</span>" + (s.delta === "new" ? '<b class="new">새 소식</b>' : "") + "</div>" +
              '<h2 class="vdk-t">' + esc(s.title) + "</h2>" +
              (s.ph && s.ph.u ? '<figure class="mx-ph"><img src="' + esc("https://wsrv.nl/?url=" + encodeURIComponent(String(s.ph.u).replace(/(ichef\.bbci\.co\.uk\/(?:ace\/standard|ace\/ws|news))\/\d{2,3}\//, "$1/976/")) + "&w=820&output=webp&q=72") + '" data-orig="' + esc(s.ph.u) + '" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer" onerror="if(this.dataset.orig&&this.src!==this.dataset.orig){this.src=this.dataset.orig}else{this.parentNode.remove()}"><figcaption>대표 기사 사진</figcaption></figure>' : "") +
              sec("무슨 일이 있었나", '<p class="vdk-p">' + esc(s.key || s.sum) + "</p>" + ((s.since || []).length ? '<p class="vdk-note mx-since">이 해설을 쓴 뒤 새 기사 ' + s.since.length + "개가 붙었어요 · 지금 상황과 다를 수 있어요 (아래 ‘어떻게 흘러왔나’의 최신 글 확인)</p>" : "")) +
              sec("왜 중요한가", (w3.link ? '<p class="vdk-p"><b>어떤 연결이 있나요?</b><br>' + esc(w3.link) + "</p>" : "") + (w3.now ? '<p class="vdk-p"><b>지금 확인된 영향</b><br>' + esc(w3.now) + "</p>" : "") + (s.why && !w3.now ? '<p class="vdk-p">' + esc(s.why) + "</p>" : "") + (w3.korea ? '<p class="vdk-p"><b>한국과는?</b><br>' + esc(w3.korea) + "</p>" : "")) +
              sec("이해하려면 알아야 할 것", ((s.bg || []).length ? '<ol class="vdk-ol">' + li(s.bg.map(esc)) + "</ol>" : "") + ((s.terms || []).length ? '<ol class="vdk-ol">' + li(s.terms.map(function (t) { return "<b>" + esc(t.t) + "</b> — " + esc(t.d); })) + "</ol>" : "") + ((s.qa || []).length ? s.qa.map(function (x) { return '<details class="mx-sec"><summary>' + esc(x.q) + '</summary><p class="vdk-p">' + esc(x.a) + "</p></details>"; }).join("") : "")) +
              sec("어떻게 흘러왔나", tl.length >= 2 ? '<ol class="vdk-ol">' + li(tl.slice(-8).map(function (i) { return "<small>" + when(i.p) + "</small> " + flag(i.c) + " " + esc(i.ko || i.t); })) + "</ol>" : "") +
              sec("나라별 매체가 강조한 점", (s.angles || []).length ? '<ol class="vdk-ol">' + li(s.angles.map(function (a) { return flag(a.c) + " <b>" + esc(cname(a.c)) + " 매체 " + Math.max(1, its.filter(function (i) { return i.c === a.c; }).map(function (i) { return i.s; }).filter(function (v, k, arr) { return arr.indexOf(v) === k; }).length) + "곳</b>" + (a.f ? " [" + esc(a.f) + "]" : "") + " " + esc(a.t); })) + "</ol>" : "") +
              sec("수집한 커뮤니티 반응", ops.length ? ops.map(function (i) { var c = CM[i.id], pk = c.picks.filter(function (x) { return x.type === "top"; })[0] || c.picks[0]; return '<p class="vdk-p">' + flag(i.c) + " <b>" + esc(cname(i.c)) + "</b> " + esc(c.mood || "") + "<br>“" + esc(pk.ko || pk.raw || pk.orig) + "”</p>"; }).join("") : "") +
              sec("기사", its.length ? '<div class="vdk-links">' + its.slice(0, 12).map(art).join("") + "</div>" + (its.length > 12 ? '<p class="vdk-note">기사 ' + its.length + "개 중 12개</p>" : "") : FEEDBY ? "" : '<p class="vdk-note">기사 목록을 불러오는 중…</p>') +
              sec("앞으로 지켜볼 것", s.watch ? '<p class="vdk-p">' + esc(s.watch) + "</p>" : "") +
              '<button type="button" class="vdk-more"' + go("sisa/#issue-" + s.id) + ">지도와 함께 시사에서 보기 ›</button></div>";
          } };
      }));
      // 본 이슈에 새 기사가 3개 넘게 붙으면 '지난번 이후 바뀐 점' 카드로 한 번 더 (본 것 전체를 다시 보여 주진 않음)
      var again = st.filter(function (s) { var k = "i:" + s.title, n = SI[k]; return s.kind !== "brief" && n && D.Seen.has("sisa", k) && (s.items || []).length - n >= 3; }).map(function (s) {
        var k = "i:" + s.title, n0 = SI[k], add = (s.items || []).length - n0;
        return { key: k + "@" + s.items.length, base: k, nItems: s.items.length, sa: "sisa", kind: "sisa", kw: (s.terms || []).map(function (t) { return t.t; }), title: "바뀐 점 · " + s.title, url: location.origin + location.pathname + "sisa/#issue-" + s.id, shareText: s.title, q: s.title, s: s, ed: m.edition,
          html: function () {
            var its = (s.items || []).map(function (x) { return FEEDBY && FEEDBY[x]; }).filter(Boolean).sort(function (a, b) { return String(b.p || "").localeCompare(String(a.p || "")); }).slice(0, Math.min(add, 8));
            return '<div class="vdk-body"><div class="vdk-k"><span class="mx-tag sisa">시사</span><b class="new">지난번 이후 새 기사 ' + add + '개</b></div><h2 class="vdk-t">' + esc(s.title) + "</h2>" +
              '<p class="vdk-h">지금 해설</p><p class="vdk-p">' + esc(s.key || s.sum || "") + "</p>" + ((s.since || []).length ? '<p class="vdk-note mx-since">해설을 쓴 뒤 붙은 기사도 ' + s.since.length + "개 있어요 · 해설이 지금 상황과 다를 수 있어요</p>" : "") +
              '<p class="vdk-h">새로 붙은 기사</p>' + (its.length ? '<div class="vdk-links">' + its.map(function (i) { return '<a href="' + esc(D.koUrl(i.u, i.l)) + '" target="_blank" rel="noopener">' + esc(i.ko || i.t) + "<small>" + flag(i.c) + " " + esc(cname(i.c)) + "</small></a>"; }).join("") + "</div>" : FEEDBY ? "" : '<p class="vdk-note">기사 목록을 불러오는 중…</p>') +
              '<button type="button" class="vdk-more"' + go("sisa/#issue-" + s.id) + ">시사에서 전부 보기 ›</button></div>";
          } };
      });
      if (again.length) add("sisa", again);
      var dg = ed.countryDigest || {};
      var natPh = function (c) { var s = (ed.stories || []).filter(function (x) { return x.ph && (x.where || []).indexOf(c) >= 0; })[0]; return s ? s.ph.u : ""; };
      add("nation", Object.keys(dg).map(function (c) {
        return { key: "n:" + c + ":" + dg[c].slice(0, 24), sa: "sisa", kind: "nation", kw: [cname(c)], title: cname(c) + "의 오늘", url: location.origin + location.pathname + "sisa/#nation", shareText: cname(c) + "의 오늘\n" + dg[c], q: cname(c) + " " + dg[c],
          html: function () { return '<div class="vdk-body"><div class="vdk-k"><span class="mx-tag nation">나라별 오늘</span><span>' + esc(ed.label || "") + '</span></div><h2 class="vdk-t">' + flag(c) + " " + esc(cname(c)) + '의 오늘</h2>' + media({ img: natPh(c) }) + '<p class="vdk-p">' + esc(dg[c]) + '</p><button type="button" class="vdk-more"' + go("sisa/#nation-" + c) + ">이 나라 뉴스 넘겨 보기 ›</button></div>"; } };
      }));
    });
  });
  // 트렌드·레딧·밈: 22개국
  j("data/trends/_index.json").then(function (idx) {
    if (!idx) return;
    var memes = (idx.memes || []).map(function (it, r) {
      return { key: "t:WW:memes:" + it.kw, sa: "sisa", kind: "meme", rank: r, title: it.ko || it.kw, url: it.url, shareText: it.ko || it.kw, q: (it.ko || "") + " " + it.kw,
        html: function () { return T.card({ cc: "WW", cname: "세계 밈", src: "memes", srcName: "레딧 밈", it: it, rank: r }); } };
    });
    if (memes.length) add("meme", memes);
    (idx.countries || []).forEach(function (cn) {
      var cc = cn[0];
      j("data/trends/" + cc + ".json").then(function (d) {
        if (!d) return;
        var tr = [], mm = [];
        T.items(d).forEach(function (x) {
          var item = { key: "t:" + cc + ":" + x.src + ":" + x.it.kw, kw: x.src === "yt" || x.src === "ytfun" || x.src === "reddit" ? KWOF(x.it.ko || x.it.kw, x.it.kw) : [x.it.ko || x.it.kw], sa: "sisa", kind: x.src === "reddit" || x.src === "ytfun" ? "meme" : "trend", title: x.it.ko || x.it.kw,
            url: x.it.url, rank: x.rank, shareText: flag(cc) + " " + d.name + " " + x.srcName + " " + (x.rank + 1) + "위 · " + (x.it.ko || x.it.kw), q: (x.it.ko || "") + " " + x.it.kw + " " + d.name, src: x.src, it: x.it,
            html: function () { return T.card({ cc: cc, cname: d.name, src: x.src, srcName: x.srcName, it: x.it, rank: x.rank, country: d }); } };
          item.ready = !!(x.it.ko || HAN.test(x.it.kw) || /^[\x00-\x7F\u00C0-\u024F\s]+$/.test(x.it.kw));
          (item.kind === "meme" ? mm : tr).push(item);
        });
        add("trend", tr); if (mm.length) add("meme", mm);
      });
    });
  });
  // AI 새 기능 (+ 정리된 '어떻게 써 보나')
  Promise.all([j("data/ai/feed.json"), j("data/ai/feat.json")]).then(function (r) {
    var F = r[0] || {}, FE = r[1] || {};
    var list = (F.posts || []).concat(F.news || [], F.vids || []).sort(function (a, b) { return (FE[b.id] ? 1 : 0) - (FE[a.id] ? 1 : 0) || String(b.date || "").localeCompare(String(a.date || "")); });
    add("ai", list.map(function (p) {
      var f = FE[p.id], vid = !!p.vid, ks = p.ksum || (HAN.test(p.sum || "") ? p.sum : ""), one = tidy((f && f.one) || ks, !(f && f.one) && (p.sum || "").length >= 290);
      var enOnly = !ks && !!p.sum && !(f && f.one);
      return { key: p.id, kw: KWOF(p.ko, p.title), sa: "ai", kind: "ai", ready: !!(p.ko || HAN.test(p.title)), title: p.ko || p.title, url: p.url, shareText: (p.ko || p.title) + "\n" + p.url, q: (p.ko || "") + " " + p.title + " " + (p.name || ""),
        html: function () {
          return '<div class="vdk-body"><div class="vdk-k"><span class="mx-tag ai">AI</span><span>' + esc(p.name || p.ch || "") + "</span><span>" + esc(p.date || "") + "</span></div>" + media(p) + cmts(p) +
            '<h2 class="vdk-t">' + esc(p.ko || p.title) + "</h2>" + (p.ko ? '<p class="vdk-note" style="margin:-6px 0 10px">' + esc(p.title) + "</p>" : "") +
            (one ? '<p class="vdk-h">뭐가 생겼나</p><p class="vdk-p">' + esc(one) + "</p>" : "") + (f && f.one && ks ? '<p class="vdk-h">발표 내용</p><p class="vdk-p">' + esc(tidy(ks)) + "</p>" : "") + (enOnly ? '<p class="vdk-note">발표 요약은 아직 영어로만 있어요 · 아래 ‘원문 보기’는 번역해서 열려요.</p>' : "") + (f && f.how ? '<p class="vdk-h">나는 어떻게 써 보나</p><p class="vdk-p">' + esc(f.how) + "</p>" : "") +
            '<a class="vdk-more" href="' + esc(vid ? p.url : D.koUrl(p.url)) + '" target="_blank" rel="noopener">' + (vid ? "유튜브에서 보기 ↗" : "원문 보기 ↗") + "</a>" +
            '<button type="button" class="vdk-more"' + go("ai/#f=" + encodeURIComponent(p.id)) + ">AI 탭에서 이 카드부터 보기 ›</button></div>";
        } };
    }));
  });
  // 도구·오픈소스 (data/tools/now.json, 도구 로봇): 지금 뜨는 것 먼저, 그다음 출처를 번갈아
  j("data/tools/now.json").then(function (N) {
    if (!N || !N.sec) return;
    var SN = { gh: "GitHub 급상승", gn: "긱뉴스", hn: "해커뉴스", yt: "유튜브 해설", ye: "영어 유튜브", list: "모음집", hf: "AI 앱", rd: "레딧" }, by = {}, out = [], used = {};
    Object.keys(N.sec).forEach(function (k) { N.sec[k].forEach(function (p) { p.sec = p.sec || k; by[p.id] = p; }); });
    (N.hot || []).forEach(function (id) { if (by[id]) { out.push(by[id]); used[id] = 1; } });
    var lists = ["gh", "gn", "hn", "yt", "ye", "list", "hf"].map(function (k) { return (N.sec[k] || []).filter(function (p) { return !used[p.id] && p.new; }).slice(0, 12); }), more = true;
    while (more) { more = false; lists.forEach(function (l) { if (l.length) { out.push(l.shift()); more = true; } }); }
    var n = function (x) { x = +x || 0; return x >= 10000 ? (x / 1e4).toFixed(1).replace(/\.0$/, "") + "만" : x.toLocaleString(); };
    POOL.tool = out.map(function (p) {
      var ko = p.sec === "gh" ? "" : (p.ko && p.ko !== p.title ? p.ko : ""), sum = p.ksum || p.sum || "";
      var m = p.sec === "gh" ? "★ " + n(p.stars) + (p.gain ? " · 하루 +" + n(p.gain) : "") : p.pts ? "▲ " + n(p.pts) : p.views ? "조회 " + n(p.views) + " · " + (p.ch || "") : p.likes ? "♥ " + n(p.likes) : "";
      return { key: p.id, kw: p.sec === "gh" ? [p.title] : KWOF(ko, p.title), sa: "tools", kind: "tool", title: ko || p.title, url: p.url, shareText: (ko || p.title) + "\n" + p.url, q: [p.title, ko, sum, p.owner, p.ch].join(" "),
        html: function () {
          return '<div class="vdk-body"><div class="vdk-k"><span class="mx-tag tool">도구</span><span>' + esc(SN[p.sec] || "") + "</span>" + (m ? "<span>" + esc(m) + "</span>" : "") + "</div>" + media(p) + cmts(p) +
            (p.sec === "gh" && p.owner ? '<p class="vdk-note" style="margin:0">' + esc(p.owner) + " /</p>" : "") +
            '<h2 class="vdk-t">' + (p.sec === "gh" ? "<span>" + esc(p.title) + "</span>" : esc(ko || p.title)) + "</h2>" + (ko ? '<p class="vdk-note" style="margin:-6px 0 10px">' + esc(p.title) + "</p>" : "") +   // 저장소 이름은 자동 번역 안 함
            (sum ? '<p class="vdk-h">' + (p.sec === "yt" || p.sec === "ye" ? "영상 설명" : "무엇인가") + '</p><p class="vdk-p">' + esc(sum.slice(0, 360)) + "</p>" : "") +
            '<a class="vdk-more" href="' + esc(p.url) + '" target="_blank" rel="noopener">' + (p.sec === "gh" ? "GitHub에서 보기 ↗" : p.sec === "yt" || p.sec === "ye" ? "유튜브에서 보기 ↗" : p.sec === "hf" ? "바로 써 보기 ↗" : "원문 보기 ↗") + "</a>" +
            '<button type="button" class="vdk-more"' + go("tools/#f=" + encodeURIComponent(p.id)) + ">도구 탭에서 이 카드부터 보기 ›</button></div>";
        } };
    });
    add("tool", []);
  });
  // 이야기·역사 (가끔): 첫 카드가 뜬 다음에 받음
  (function () {
    j("data/iyagi/stories/_index.json").then(function (a) {
      if (!Array.isArray(a)) return;
      add("story", a.map(function (s) {
        var d1 = ((s.depths || {}).d1 || {}).body || [];
        return { key: s.id, kw: [s.orig || s.title].concat((s.tags || []).slice(-2)), sa: "iyagi", kind: "story", title: s.title, url: location.origin + location.pathname + "iyagi/#read-" + s.id, shareText: s.title + (s.hook ? "\n" + s.hook : ""), q: s.title + " " + (s.orig || "") + " " + (s.hook || ""),
          html: function () {
            var wt = ""; (s.sources || []).some(function (x) { var m = /^https?:\/\/([a-z-]+)\.(?:m\.)?wikipedia\.org\/wiki\/([^#?]+)/.exec(x.u || ""); if (m) { try { wt = m[1] + ":" + decodeURIComponent(m[2]).replace(/_/g, " "); } catch (e) { } } return !!wt; });
            return '<div class="vdk-body">' + (wt ? '<span class="vdk-img vfm-picw"><img data-wt="' + esc(wt) + '" alt="" loading="lazy"></span>' : "") + '<div class="vdk-k"><span class="mx-tag story">이야기</span><span>' + esc(s.kind || "") + "</span><span>" + esc(s.region || "") + '</span></div><h2 class="vdk-t">' + esc(s.title) + '</h2><p class="vdk-note">' + esc(s.orig || "") + "</p>" +
              d1.filter(function (x) { return typeof x === "string"; }).map(function (x) { return '<p class="vdk-p">' + esc(x) + "</p>"; }).join("") +
              ((s.parts || []).length ? '<p class="vdk-h">요즘 이렇게 써요</p><ol class="vdk-ol">' + s.parts.map(function (x) { return "<li><b>" + esc(x.t) + "</b> — " + esc(x.b) + "</li>"; }).join("") + "</ol>" : "") +
              '<button type="button" class="vdk-more"' + go("iyagi/#read-" + s.id) + ">" + ((s.depths || {}).d2 ? "더 자세한 이야기 읽기 ›" : "이야기 화면으로 ›") + "</button></div>";
          } };
      }));
    });
    j("data/history/top.json").then(function (h) {
      if (!h || !h.all) return;
      add("story", h.all.slice(0, 400).map(function (r) {
        var id = r[0], title = r[1], y = r[2], sum = (window.vfmClean || String)(r[14] || "");
        return { key: "h:" + id, kw: [title], sa: "history", kind: "story", hid: id, title: title, url: location.origin + location.pathname + "history/#p=" + id, shareText: title, q: title + " " + sum,
          html: function () {
            var hd = HD[id];
            return '<div class="vdk-body">' + (r[12] ? '<span class="vdk-img vfm-picw"><img data-wt="ko:' + esc(title) + '" alt="" loading="lazy"></span>' : "") + '<div class="vdk-k"><span class="mx-tag story">역사</span>' + (y != null ? "<span>" + (y < 0 ? "기원전 " + (-y) : y) + "년" + (String(r[9] || "").indexOf("~") >= 0 ? "경" : "") + "</span>" : "") + "<span>" + (r[6] || []).slice(0, 4).map(flag).join("") + '</span></div><h2 class="vdk-t">' + esc(title) + "</h2>" +
              (hd ? (hd.desc ? '<p class="vdk-note">' + esc(hd.desc) + "</p>" : "") + '<p class="vdk-p">' + esc((window.vfmClean || String)(hd.lead || sum)) + "</p>" + (hd.secs || []).map(function (x, i) {
                return '<details class="mx-sec"' + (i < 2 ? " open" : "") + "><summary>" + esc(x.h) + "</summary><p class=\"vdk-p\">" + esc(x.t) + "</p></details>"; }).join("") + '<p class="vdk-note">위키백과(한국어) 글을 정리했어요 · CC BY-SA</p>'
                : '<p class="vdk-p">' + esc(tidy(sum, true)) + '</p><p class="vdk-note">글을 불러오는 중…</p>') +
              '<button type="button" class="vdk-more"' + go("history/#p=" + id) + ">역사에서 이어 읽기 ›</button></div>";
          } };
      }));
    });
  })();

  /* ── 카드가 보일 때만 더 받아 오기: 시사 기사 목록(그 판), 역사 글 전체 ── */
  var FEEDBY = null, feedP = null, HD = {}, CM = {};
  var SI = (function () { try { return JSON.parse(localStorage.getItem("vfm:mix:si") || "{}"); } catch (e) { return {}; } })();   // 이슈를 볼 때 붙어 있던 기사 수
  function markItems(x) {
    var k = x.base || (x.kind === "sisa" && x.s && x.s.kind !== "brief" ? x.key : null); if (!k) return;
    SI[k] = x.nItems || (x.s.items || []).length;
    var ks = Object.keys(SI); if (ks.length > 400) ks.slice(0, ks.length - 300).forEach(function (q) { delete SI[q]; });
    try { localStorage.setItem("vfm:mix:si", JSON.stringify(SI)); } catch (e) { }
    if (x.base) D.Seen.add("sisa", x.key);
  }
  function loadFeedOf(ed) {
    if (!feedP) feedP = j("data/sisa/feed/_index.json").then(function (ids) {
      return Promise.all((ids || []).filter(function (x) { return x.indexOf(ed + "__") === 0; }).map(function (x) { return j("data/sisa/feed/" + x + ".json"); }));
    }).then(function (docs) {
      return j("data/sisa/brief/" + ed + "__cm.json").then(function (cm) { CM = (cm && cm.map) || {}; return docs; });
    }).then(function (docs) {
      FEEDBY = {};
      (docs || []).forEach(function (d) { (d && d.items || []).forEach(function (it) { FEEDBY[it.id] = { id: it.id, s: it.s, t: it.t, ko: it.ko || (d.lang === "ko" ? it.t : ""), u: it.u, c: it.c, l: d.lang, p: it.p, k: it.k }; }); });
    });
    return feedP;
  }
  function loadHist(id) {
    if (HD[id]) return Promise.resolve(HD[id]);
    var pid = id.slice(1);
    return j("data/history/pages/" + pid.slice(0, 2).padStart(2, "0") + "/" + id + ".json").then(function (d) { if (d) HD[id] = d; return d; });
  }
  function more(x) {
    markItems(x);
    var again = function () { ["mix-home", "mix-search"].forEach(function (id) { var d = D.get(id); if (d && d.el() && d.curKey() === x.key) d.paint(); }); };
    if (x.kind === "sisa" && !FEEDBY && x.ed) loadFeedOf(x.ed).then(again);
    if (x.hid && !HD[x.hid]) loadHist(x.hid).then(again);
    if (x.src === "wiki" && T.WK[x.it.url] === undefined) T.wikiFor(x.it.url).then(again);
  }

  /* ── 비율대로 섞기 ── */
  function mixed() {
    if (!READY) return [];
    var ptr = {}, out = [], used = {};
    KINDS.forEach(function (k) { ptr[k[0]] = 0; });
    for (;;) {
      var live = KINDS.map(function (k) { return k[0]; }).filter(function (k) { return W[k] > 0 && ptr[k] < POOL[k].length; });
      if (!live.length) break;
      var tot = live.reduce(function (a, k) { return a + W[k] * W[k]; }, 0), r = Math.random() * tot, pick = live[0];   // 많이(3)=9, 보통(2)=4, 적게(1)=1 배
      for (var i = 0; i < live.length; i++) { r -= W[live[i]] * W[live[i]]; if (r <= 0) { pick = live[i]; break; } }
      var it = POOL[pick][ptr[pick]++];
      if (it.ready === false) continue;                               // 한국어로 못 읽는 카드는 넘겨보기에서 뺌 (찾기에는 나옴)
      if (!used[it.key]) { used[it.key] = 1; out.push(it); }
    }
    return out;
  }
  var deck = D.create({ id: "mix-home", app: "mix", emptyTitle: "불러오는 중이에요", emptyNote: "잠시만요. 시사·트렌드·AI를 모으고 있어요.", items: mixed,
    onShow: more });
  var sdeck = null;

  /* ── 화면 ── */
  var host = document.getElementById("mix");
  function ratioHtml() {
    return '<div class="mx-ratio" id="mxRatio" hidden><p class="mx-rh">섞는 비율 <small>종류마다 고르세요 · 바꾸면 바로 다시 섞어요</small></p>' + KINDS.map(function (k) {
      return '<div class="mx-row"><span>' + k[1] + '</span><div class="mx-seg">' + [3, 2, 1, 0].map(function (v) { return '<button type="button" data-mxw="' + k[0] + "|" + v + '" aria-pressed="' + (W[k[0]] === v) + '">' + WNAME[v] + "</button>"; }).join("") + "</div></div>";
    }).join("") + '<button type="button" class="mx-reset" data-mxw="reset">처음 비율로</button></div>';
  }
  host.innerHTML = '<div class="mx-top"><input id="mxq" type="search" placeholder="전부에서 찾기 (예: 트럼프, 임진왜란)" aria-label="한 번에 찾기"><button type="button" id="mxRatioBtn" aria-label="섞는 비율">비율</button></div>' +
    ratioHtml() + '<p class="mx-note" id="mxNote">시사·트렌드·밈·AI를 섞어서 한 장씩 · 옆으로 밀면 다음 · 본 것은 다시 안 나와요</p><div id="mxDeck">' + deck.html() + "</div>";
  var q = document.getElementById("mxq"), qT = null, HT = null, htP = null, NOTE0 = "시사·트렌드·밈·AI를 섞어서 한 장씩 · 옆으로 밀면 다음 · 본 것은 다시 안 나와요";
  // 역사 8만 편 제목 전부 (첫 찾기 때 한 번만 받음, 약 1MB)
  function histTitles() {
    if (!htP) htP = j("data/history/_index.json").then(function (ix) {
      return Promise.all(((ix && ix.searchBuckets) || []).map(function (b) { return j("data/history/s/" + b + ".json"); }));
    }).then(function (ls) { HT = []; (ls || []).forEach(function (l) { if (Array.isArray(l)) HT = HT.concat(l); }); return HT; });
    return htP;
  }
  function histItem(r) {                                               // 제목 색인 한 줄 [제목, id, 연도, 종류, 권역] → 카드 (본문은 보일 때 받음)
    var id = r[1], title = r[0], y = r[2];
    return { key: "h:" + id, kw: [title], sa: "history", kind: "story", hid: id, title: title, url: location.origin + location.pathname + "history/#p=" + id, shareText: title, q: title,
      html: function () {
        var hd = HD[id];
        return '<div class="vdk-body"><div class="vdk-k"><span class="mx-tag story">역사</span>' + (y != null && y !== "" ? "<span>" + (y < 0 ? "기원전 " + (-y) : y) + "년</span>" : "") + '</div><h2 class="vdk-t">' + esc(title) + "</h2>" +
          (hd ? (hd.desc ? '<p class="vdk-note">' + esc(hd.desc) + "</p>" : "") + '<p class="vdk-p">' + esc((window.vfmClean || String)(hd.lead || hd.one || "")) + "</p>" + (hd.secs || []).slice(0, 4).map(function (x, i) {
            return '<details class="mx-sec"' + (i < 1 ? " open" : "") + "><summary>" + esc(x.h) + '</summary><p class="vdk-p">' + esc(x.t) + "</p></details>"; }).join("") + '<p class="vdk-note">위키백과(한국어) 글을 정리했어요 · CC BY-SA</p>'
            : '<p class="vdk-note">글을 불러오는 중…</p>') +
          '<button type="button" class="vdk-more"' + go("history/#p=" + id) + ">역사에서 이어 읽기 ›</button></div>";
      } };
  }
  function runSearch() {
    var raw = q.value.trim(), v = raw.toLowerCase(), box = document.getElementById("mxDeck"), note = document.getElementById("mxNote");
    if (v.length < 2) { note.textContent = NOTE0; if (sdeck) { sdeck = null; box.innerHTML = deck.html(); var k = deck.curKey(); if (k && deck.map[k]) more(deck.map[k]); } return; }
    var all = [];
    KINDS.forEach(function (k) { all = all.concat(POOL[k[0]]); });
    var seen = {}, hits = all.filter(function (x) { if (seen[x.key] || String(x.q || x.title).toLowerCase().indexOf(v) < 0) return false; seen[x.key] = 1; return true; });
    var hh = HT ? HT.filter(function (r) { return !seen["h:" + r[1]] && String(r[0]).toLowerCase().indexOf(v) >= 0; }) : [];
    hh.sort(function (a, b) { return (String(a[0]).toLowerCase().indexOf(v) === 0 ? 0 : 1) - (String(b[0]).toLowerCase().indexOf(v) === 0 ? 0 : 1) || a[0].length - b[0].length; });
    hits = hits.concat(hh.slice(0, 300).map(histItem));
    note.textContent = "‘" + raw + "’ 찾은 것 " + hits.length + "장" + (hh.length > 300 ? " (역사는 " + hh.length.toLocaleString() + "편 중 제목이 짧은 300편)" : "") + " · 본 것도 나와요" + (HT ? "" : " · 역사 제목을 받는 중…");
    sdeck = D.create({ id: "mix-search", app: "mix", noSeen: true, emptyTitle: HT ? "찾은 게 없어요" : "찾는 중이에요", emptyNote: HT ? "다른 낱말로 찾아보세요. 시사·트렌드·AI는 지금 판, 역사는 8만 편 제목에서 찾아요." : "역사 제목 8만 편을 받고 있어요.", items: function () { return hits; }, onShow: more });
    sdeck.queue = null; sdeck.hist = []; sdeck.pos = -1;
    box.innerHTML = sdeck.html();
    var k0 = sdeck.curKey(); if (k0 && sdeck.map[k0]) more(sdeck.map[k0]);
    if (!HT) histTitles().then(function () { if (q.value.trim().toLowerCase() === v) runSearch(); });
  }
  q.addEventListener("input", function () { clearTimeout(qT); qT = setTimeout(runSearch, 250); });
  q.addEventListener("search", function () { clearTimeout(qT); runSearch(); });   // 폰 키보드의 ✕·검색 단추
  document.addEventListener("click", function (e) {
    var t = e.target.closest("[data-mxw],#mxRatioBtn,[data-mixgo]"); if (!t) return;
    if (t.id === "mxRatioBtn") { var r = document.getElementById("mxRatio"); r.hidden = !r.hidden; return; }
    if (t.hasAttribute("data-mixgo")) {
      var to = t.getAttribute("data-mixgo");
      try { sessionStorage.setItem("vfm:fromHome", "1"); sessionStorage.setItem("vfm:fromCard", "#" + (to.split("#")[1] || "")); } catch (x) { }
      location.href = to; return;
    }
    var v = t.getAttribute("data-mxw");
    if (v === "reset") W = Object.assign({}, DEF);
    else { var p = v.split("|"); W[p[0]] = +p[1]; }
    try { localStorage.setItem("vfm:mix:w", JSON.stringify(W)); } catch (x) { }
    document.getElementById("mxRatio").outerHTML = ratioHtml().replace(" hidden", "");
    deck.refresh();
    if (window.vfm && window.vfm.toast) window.vfm.toast("비율을 바꿨어요");
  });
  var k0 = deck.curKey(); if (k0 && deck.map[k0]) more(deck.map[k0]);
  var css = document.createElement("style");
  css.textContent = ".mx-top{display:flex;gap:8px;margin:0 0 8px}.mx-top input{flex:1;min-width:0;border:0;border-radius:12px;padding:11px 14px;font:inherit;font-size:16px;background:var(--ap-fill);color:var(--ap-label)}" +
    ".mx-top button{flex:none;border:0;border-radius:12px;padding:0 14px;font:inherit;font-weight:600;background:var(--ap-fill);color:var(--ap-label)}" +
    ".mx-note{margin:0 4px 4px;font-size:12.5px;color:var(--ap-label2)}" +
    ".mx-ratio{background:var(--ap-surface);border-radius:14px;padding:12px;margin:0 0 10px}.mx-rh{margin:0 0 8px;font-weight:700}.mx-rh small{font-weight:400;color:var(--ap-label2);font-size:12px;display:block}" +
    ".mx-row{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:6px 0;border-top:.5px solid var(--ap-sep);font-size:14px}.mx-row:first-of-type{border-top:0}" +
    ".mx-seg{display:flex;gap:2px;background:var(--ap-fill);border-radius:9px;padding:2px;flex:none}.mx-seg button{border:0;border-radius:7px;padding:6px 8px;font:inherit;font-size:12.5px;background:none;color:var(--ap-label)}.mx-seg button[aria-pressed=true]{background:var(--ap-seg-on);font-weight:700;box-shadow:0 1px 4px rgba(0,0,0,.12)}" +
    ".mx-reset{margin-top:8px;border:0;background:none;color:var(--ap-blue);font:inherit;font-size:14px;padding:4px 0}" +
    ".mx-ih{display:flex;align-items:center;gap:8px;margin:18px 0 6px;font-weight:700;font-size:16px}.mx-ih span{width:24px;height:24px;border-radius:50%;background:var(--ap-blue);color:#fff;display:grid;place-items:center;font-size:13px}" +
    ".mx-sec{margin:6px 0;border-top:.5px solid var(--ap-sep)}.mx-sec summary{padding:8px 0;font-weight:700;font-size:14px;cursor:pointer}" +
    ".mx-tag{font-weight:700;padding:2px 8px;border-radius:999px;font-size:12px}.mx-tag.sisa{background:color-mix(in srgb,var(--ap-blue) 15%,transparent);color:var(--ap-blue-t)}" +
    ".mx-tag.nation{background:color-mix(in srgb,var(--ap-teal) 18%,transparent);color:var(--ap-teal)}.mx-tag.ai{background:color-mix(in srgb,var(--ap-purple) 15%,transparent);color:var(--ap-purple-t)}" +
    ".mx-tag.story{background:color-mix(in srgb,var(--ap-orange) 16%,transparent);color:var(--ap-orange-t)}.mx-tag.tool{background:color-mix(in srgb,#30B0C7 18%,transparent);color:#0A7A8C}.vdk .new{color:var(--ap-blue-t)}";
  document.head.appendChild(css);
})();
