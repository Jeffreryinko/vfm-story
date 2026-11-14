/* history/tongsa.js — '세계사 한 줄로' (Claude가 직접 쓴 세계사 통사, 고대 문명 → 오늘)
 *  글: history/tongsa-1.js … (window.VFM_TS_ADD([...장])) · 화면: 이 파일
 *  장 하나: { id, n 순서, t 제목, yrs "기원전 3500 ~ 1200", sum 짧게(3~4문장), secs:[[소제목, 글]…], people:[[이름, 한 줄]…], q 생각해 볼 질문 }
 *  깊이 세 단계: 짧게 = sum · 보통 = 앞의 소제목 3개 · 길게 = 전부 + 인물 + 질문
 *  주소: #ts (차례) · #ts=<id> (한 장).  읽은 장은 vfm:history:ts 에 저장 (자판기 동기화에 포함)
 */
(function () {
  "use strict";
  const CH = [];
  window.VFM_TS_ADD = list => { for (const c of list) if (!CH.some(x => x.id === c.id)) CH.push(c); CH.sort((a, b) => a.n - b.n); };
  const LSG = (k, d) => { try { const v = localStorage.getItem("vfm:history:" + k); return v ? JSON.parse(v) : d; } catch (e) { return d; } };
  const LSS = (k, v) => { try { localStorage.setItem("vfm:history:" + k, JSON.stringify(v)); } catch (e) { } };
  const R = LSG("ts", {});            // { id: 읽은 시각 }
  let DEP = LSG("tsdep", "mid");
  const e = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const P = t => e(t).split(/\n+/).map(x => `<p>${x}</p>`).join("");
  const css = document.createElement("style");
  css.textContent = `.ts-hero{display:block;width:100%;text-align:left;border:0;border-radius:20px;padding:18px;margin:4px 0 14px;color:#fff;background:linear-gradient(150deg,#9A7B55,#5E4527);font:inherit;cursor:pointer}
.ts-hero small{display:block;font-size:12.5px;font-weight:700;opacity:.85}.ts-hero b{display:block;font-size:22px;letter-spacing:-.02em;margin:3px 0 4px}.ts-hero span{display:block;font-size:14.5px;line-height:1.5;opacity:.92}
.ts-hero i{display:block;height:5px;border-radius:9px;background:rgba(255,255,255,.25);margin-top:12px;overflow:hidden;font-style:normal}.ts-hero i em{display:block;height:100%;background:#fff;border-radius:9px}
.ts-list{display:flex;flex-direction:column;gap:8px;margin:10px 0}.ts-li{display:grid;grid-template-columns:34px 1fr auto;gap:10px;align-items:center;width:100%;text-align:left;border:0;background:var(--surface);border-radius:14px;padding:12px 14px;font:inherit;color:inherit;cursor:pointer}
.ts-li .n{font-weight:800;color:var(--accent);font-size:17px;text-align:center}.ts-li b{display:block;font-size:16px}.ts-li small{color:var(--muted);font-size:12.5px}.ts-li .ok{color:var(--accent);font-weight:700}
.ts-era{margin:18px 4px 2px;font-size:13px;font-weight:700;color:var(--muted)}
.ts-art{background:var(--surface);border-radius:20px;padding:20px 18px;margin:6px 0 12px}.ts-art .k{font-size:12.5px;font-weight:700;color:var(--accent);margin:0}
.ts-art h1{font-size:26px;letter-spacing:-.03em;line-height:1.25;margin:4px 0 2px}.ts-art .y{color:var(--muted);font-size:13.5px;margin:0 0 14px}
.ts-art .sum{font-size:calc(17px*var(--fs,1));line-height:1.75;font-weight:500;margin:0 0 6px}.ts-art h2{font-size:18.5px;letter-spacing:-.02em;margin:22px 0 6px}
.ts-art p{font-size:calc(16.5px*var(--fs,1));line-height:1.8;margin:0 0 10px}.ts-dep{display:flex;gap:6px;margin:0 0 12px}.ts-dep button{flex:1;border:0;border-radius:10px;padding:9px;background:var(--sunk);font:inherit;font-size:14px;font-weight:600;color:var(--ink)}
.ts-dep button[aria-pressed=true]{background:var(--accent);color:var(--accent-ink)}.ts-pp{margin:18px 0 0;padding:12px 14px;border-radius:14px;background:var(--accent-soft)}.ts-pp p{margin:0 0 4px;font-size:15px;line-height:1.55}
.ts-q{margin:14px 0 0;padding:12px 14px;border-radius:14px;border:1px dashed var(--line);font-size:15.5px;line-height:1.6}.ts-nav{display:flex;gap:8px;margin:8px 0 24px}.ts-nav button{flex:1;border:0;border-radius:14px;padding:13px;background:var(--surface);font:inherit;font-size:14.5px;color:inherit;text-align:left}.ts-nav button b{display:block;font-size:15.5px}.ts-nav button:last-child{text-align:right}
.ts-more{display:block;width:100%;border:0;border-radius:12px;padding:12px;margin:12px 0 0;background:var(--sunk);font:inherit;font-weight:700;color:var(--accent)}`;
  document.head.appendChild(css);

  const ERA = n => n <= 4 ? "문명의 시작" : n <= 10 ? "고대 제국" : n <= 15 ? "중세" : n <= 20 ? "근세" : n <= 23 ? "근대" : "현대";
  const done = () => CH.filter(c => R[c.id]).length;
  const next = () => CH.find(c => !R[c.id]) || CH[0];

  window.VFM_TS = {
    count: () => CH.length,
    hero() {
      if (!CH.length) return "";
      const nx = next(), d = done();
      return `<button class="ts-hero" data-tsgo="${d ? "#ts=" + nx.id : "#ts"}"><small>세계사 한 줄로 · ${CH.length}장${d ? ` 중 ${d}장 읽음` : ""}</small><b>${d ? `${nx.n}장 「${e(nx.t)}」` : "고대 문명부터 오늘까지"}</b><span>${d ? e(nx.yrs) + " · 이어서 읽기" : "흩어진 사건을 하나의 이야기로 — 한 장 5분, 시대 순서대로 읽어요."}</span><i><em style="width:${Math.round(d / CH.length * 100)}%"></em></i></button>`;
    },
    list() {
      let h = "", era = "";
      for (const c of CH) {
        const er = ERA(c.n); if (er !== era) { era = er; h += `<p class="ts-era">${er}</p>`; }
        h += `<button class="ts-li" data-tsgo="#ts=${e(c.id)}"><span class="n">${c.n}</span><span><b>${e(c.t)}</b><small>${e(c.yrs)}</small></span><span class="${R[c.id] ? "ok" : ""}">${R[c.id] ? "✓" : "›"}</span></button>`;
      }
      return `<div class="top"><h1 class="lt">세계사 한 줄로</h1></div><p class="note" style="margin:0 4px 8px">Claude가 시대 순서대로 직접 쓴 세계사예요. 한 장을 읽으면 다음 장으로 이어져요. 깊이는 짧게·보통·길게 중에서 골라요.</p><div class="ts-list">${h}</div>`;
    },
    chapter(id) {
      const i = CH.findIndex(c => c.id === id), c = CH[i]; if (!c) return this.list();
      R[c.id] = Date.now(); LSS("ts", R);
      const secs = DEP === "short" ? [] : DEP === "mid" ? c.secs.slice(0, 3) : c.secs;
      const pv = CH[i - 1], nx = CH[i + 1];
      return `<div class="ts-art"><p class="k">세계사 한 줄로 · ${c.n}장 · ${ERA(c.n)}</p><h1>${e(c.t)}</h1><p class="y">${e(c.yrs)}</p>
        <div class="ts-dep">${[["short", "짧게"], ["mid", "보통"], ["long", "길게"]].map(d => `<button data-tsdep="${d[0]}" aria-pressed="${DEP === d[0]}">${d[1]}</button>`).join("")}</div>
        <p class="sum">${e(c.sum)}</p>
        ${secs.map(s => `<h2>${e(s[0])}</h2>${P(s[1])}`).join("")}
        ${DEP !== "long" && c.secs.length > secs.length ? `<button class="ts-more" data-tsdep="${DEP === "short" ? "mid" : "long"}">${DEP === "short" ? "보통으로 더 읽기" : `나머지 ${c.secs.length - secs.length}꼭지 더 읽기`} ↓</button>` : ""}
        ${DEP === "long" && c.people && c.people.length ? `<div class="ts-pp">${c.people.map(p => `<p><b>${e(p[0])}</b> — ${e(p[1])}</p>`).join("")}</div>` : ""}
        ${DEP === "long" && c.q ? `<p class="ts-q">🤔 ${e(c.q)}</p>` : ""}</div>
        <div class="ts-nav">${pv ? `<button data-tsgo="#ts=${e(pv.id)}"><small>‹ ${pv.n}장</small><b>${e(pv.t)}</b></button>` : `<button data-tsgo="#ts"><small>‹</small><b>차례</b></button>`}${nx ? `<button data-tsgo="#ts=${e(nx.id)}"><small>${nx.n}장 ›</small><b>${e(nx.t)}</b></button>` : `<button data-tsgo="#ts"><small>끝</small><b>차례로 ›</b></button>`}</div>`;
    },
    render(h) {
      const app = document.getElementById("app");
      app.innerHTML = h.startsWith("#ts=") ? this.chapter(decodeURIComponent(h.slice(4))) : this.list();
      scrollTo(0, 0);
    },
  };
  document.addEventListener("click", ev => {
    const g = ev.target.closest("[data-tsgo]"); if (g) { ev.preventDefault(); return window.vfmApp && window.vfmApp.push ? window.vfmApp.push(g.dataset.tsgo) : (location.hash = g.dataset.tsgo); }
    const d = ev.target.closest("[data-tsdep]"); if (d) { const y = scrollY; DEP = d.dataset.tsdep; LSS("tsdep", DEP); const h = location.hash; document.getElementById("app").innerHTML = window.VFM_TS.chapter(decodeURIComponent(h.slice(4))); scrollTo(0, y); }
  });
})();
