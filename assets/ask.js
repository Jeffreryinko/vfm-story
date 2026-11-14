/* ask.js — 모든 카드에 'AI에게 자세히 묻기' 단추 (세 자판기 공통, shell.js 가 불러요)
 *  누르면 카드의 모든 글 + "처음부터 알기 쉽게 설명해 줘"가 적힌 창이 열려요. 글은 고칠 수 있어요.
 *  보낼지 말지는 사용자가 정해요: [Claude에서 열기] [ChatGPT에서 열기] [Gemini(복사 후 열기)] [복사만]
 *  자동으로 어디에도 보내지 않아요. (자판기에는 AI 서버가 없어서, 각 AI 사이트를 새 창으로 열어 줘요)
 */
(function () {
  "use strict";
  if (window.__vfmAsk) return; window.__vfmAsk = 1;
  // 카드로 볼 모양들 — 겹쳐 있으면 가장 바깥 카드에 하나만 붙여요
  var SEL = [".vdk-body", ".lc", ".brf-it", ".brf-hero", ".dbf-it", ".dbf-hero", ".aib details", ".ts-art", ".tp-card", ".sheet", "article.card", ".card.acc", ".dp .lg", ".ev.op .evb", ".nwbox", "div.card", "div.box", "section.block", ".epc", "article.rcard", ".ev.op", ".mx-card"].join(",");
  var SKIP = ".vfm-sheet, .vfm-ask-back, nav, .tabs, #tpr";
  var Q = "위 내용을 처음부터 알기 쉽게 설명해 줘.\n- 배경지식이 없는 사람도 이해하게, 어려운 말은 풀어서\n- 실제 예시와 비유를 들어서\n- 왜 중요한지, 더 알아 두면 좋은 점까지";
  var css = document.createElement("style");
  css.textContent = ".vfm-ask{display:inline-flex;align-items:center;gap:4px;margin:8px 0 0;border:0;border-radius:999px;padding:5px 10px 5px 8px;background:var(--ap-fill,rgba(120,120,128,.1));color:var(--ap-label2,#6e6e73);font:inherit;font-size:12.5px;font-weight:600;letter-spacing:-.01em;cursor:pointer;transition:background .15s,color .15s,transform .15s}" +
    ".vfm-ask:hover{color:var(--ap-blue,#0A6CFF)}.vfm-ask:active{transform:scale(.96)}" +
".vfm-ask svg{width:13px;height:13px;color:#D97757}" +
    ".vfm-ask-back{position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,.4);display:flex;align-items:flex-end;justify-content:center}" +
    ".vfm-ask-sh{width:100%;max-width:560px;max-height:88vh;overflow:auto;background:var(--ap-surface,#fff);color:var(--ap-label,#000);border-radius:18px 18px 0 0;padding:16px 16px calc(env(safe-area-inset-bottom,0px) + 16px);box-sizing:border-box}" +
    ".vfm-ask-sh h3{margin:0 0 4px;font-size:18px}.vfm-ask-sh p{margin:0 0 10px;font-size:13px;color:var(--ap-label2,#666);line-height:1.5}" +
    ".vfm-ask-sh textarea{width:100%;box-sizing:border-box;min-height:220px;border:0;border-radius:12px;padding:10px 12px;background:var(--ap-fill,rgba(120,120,128,.12));color:inherit;font:inherit;font-size:14px;line-height:1.55;resize:vertical}" +
    ".vfm-ask-sh .row{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:10px}.vfm-ask-sh .row button{border:0;border-radius:12px;padding:12px 8px;font:inherit;font-size:14.5px;font-weight:700;background:var(--ap-fill,rgba(120,120,128,.14));color:inherit;cursor:pointer}" +
    ".vfm-ask-sh .row .pri{background:#D97757;color:#fff}.vfm-ask-sh .n{font-size:12px;color:var(--ap-label2,#888);margin-top:8px}";
  document.head.appendChild(css);
  var IC = '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M10 2.5l1.6 4.7a3 3 0 0 0 1.9 1.9L18.2 10.7l-4.7 1.6a3 3 0 0 0-1.9 1.9L10 18.9l-1.6-4.7a3 3 0 0 0-1.9-1.9L1.8 10.7l4.7-1.6a3 3 0 0 0 1.9-1.9z"/></svg>';

  function textOf(el) {
    var c = el.cloneNode(true);
    c.querySelectorAll("button, svg, script, style, input, textarea, select, .vfm-ask, iframe, .pg, .sizeb").forEach(function (x) { x.remove(); });
    c.querySelectorAll("details").forEach(function (d) { d.open = true; });
    c.querySelectorAll("[hidden]").forEach(function (x) { x.removeAttribute("hidden"); });
    var box = document.createElement("div");
    box.style.cssText = "position:fixed;left:-10000px;top:0;width:640px;opacity:0;pointer-events:none";
    box.appendChild(c); document.body.appendChild(box);
    var t = (c.innerText || c.textContent || "").replace(/[ \t]+\n/g, "\n").replace(/\n{3,}/g, "\n\n").trim();
    box.remove();
    return t;
  }
  function where() {
    var h = document.querySelector("h1.lt, .lt, h1"), t = document.title.replace(/ — .*$/, "");
    return [t, h && h.textContent.trim().slice(0, 40)].filter(Boolean).filter(function (x, i, a) { return a.indexOf(x) === i; }).join(" · ");
  }
  function copy(s) {
    try { if (navigator.clipboard) return navigator.clipboard.writeText(s); } catch (e) { }
    var ta = document.createElement("textarea"); ta.value = s; document.body.appendChild(ta); ta.select(); try { document.execCommand("copy"); } catch (e) { } ta.remove();
    return Promise.resolve();
  }
  function toast(m) { if (window.vfm && window.vfm.toast) return window.vfm.toast(m); var t = document.createElement("div"); t.textContent = m; t.style.cssText = "position:fixed;left:50%;bottom:90px;transform:translateX(-50%);background:#222;color:#fff;padding:9px 14px;border-radius:999px;font-size:14px;z-index:10000"; document.body.appendChild(t); setTimeout(function () { t.remove(); }, 2200); }

  function open(el) {
    var body = textOf(el);
    if (body.length > 6000) body = body.slice(0, 6000) + "\n…(이하 줄임)";
    var prompt = "[" + where() + "]\n\n" + body + "\n\n" + Q;
    var back = document.createElement("div"); back.className = "vfm-ask-back";
    back.innerHTML = '<div class="vfm-ask-sh" role="dialog" aria-label="AI에게 묻기"><h3>AI에게 자세히 묻기</h3><p>이 카드의 글과 질문을 아래에 적어 뒀어요. 고쳐도 되고, 보낼지 말지는 직접 골라요. 누르기 전엔 아무 데도 안 보내요.</p><textarea></textarea>' +
      '<div class="row"><button class="pri" data-to="claude">Claude에서 열기</button><button data-to="gpt">ChatGPT에서 열기</button><button data-to="gem">Gemini (복사 후 열기)</button><button data-to="copy">복사만 하기</button></div>' +
      '<div class="row" style="grid-template-columns:1fr"><button data-to="close">닫기</button></div><p class="n">긴 글은 주소에 다 안 담길 수 있어서, 열 때 늘 클립보드에도 복사해 둬요. 안 보이면 AI 입력칸에 붙여 넣으세요.</p></div>';
    var ta = back.querySelector("textarea"); ta.value = prompt;
    document.body.appendChild(back);
    back.addEventListener("click", function (e) {
      if (e.target === back) return back.remove();
      var b = e.target.closest("[data-to]"); if (!b) return;
      var to = b.getAttribute("data-to"), q = ta.value.trim();
      if (to === "close") return back.remove();
      copy(q).then(function () {
        var short = q.length <= 3500;   // 주소 길이 한도를 넘지 않게
        var url = to === "claude" ? "https://claude.ai/new" + (short ? "?q=" + encodeURIComponent(q) : "")
          : to === "gpt" ? "https://chatgpt.com/" + (short ? "?q=" + encodeURIComponent(q) : "")
          : to === "gem" ? "https://gemini.google.com/app" : "";
        if (url) window.open(url, "_blank", "noopener");
        toast(to === "copy" ? "복사했어요" : short && to !== "gem" ? "열었어요 (클립보드에도 복사)" : "복사했어요 — 붙여 넣기 하세요");
        if (to !== "copy") back.remove();
      });
    });
  }

  function scan() {
    var all = Array.prototype.slice.call(document.querySelectorAll(SEL));
    all.forEach(function (el) {
      if (el.querySelector(":scope > .vfm-ask") || el.closest(SKIP)) return;
      if (el.parentElement && el.parentElement.closest(SEL)) return;   // 카드 안의 작은 칸이면 바깥 카드에만 붙임
      if (el.tagName === "BUTTON" || (el.textContent || "").trim().length < 40) return;  // 단추 자체·너무 짧은 칸은 건너뜀
      var b = document.createElement("button"); b.type = "button"; b.className = "vfm-ask"; b.innerHTML = IC + "AI에게 묻기";
      el.appendChild(b);
    });
  }
  var tm;
  new MutationObserver(function () { clearTimeout(tm); tm = setTimeout(scan, 250); }).observe(document.body, { childList: true, subtree: true });
  document.addEventListener("click", function (e) {
    var b = e.target.closest(".vfm-ask"); if (!b) return;
    e.preventDefault(); e.stopPropagation();
    open(b.parentElement);
  }, true);
  scan();
})();
