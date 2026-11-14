/* joy.js — 작은 보상 (세 자판기 공통, shell.js 가 불러요). 집중이 흩어지기 쉬운 사람도 '하나 했다'가 바로 느껴지게.
 *  vfm.tick(kind)  : 한 일을 셈 — card(카드 넘김) · quiz(문제 맞힘) · done(한 단위 끝냄). 화면 아래에 '+1' 알약이 잠깐 뜨고,
 *                    5·10·20·30·50장째엔 꽃가루 + 진동.
 *  vfm.cheer(big)  : 꽃가루(작게/크게) + 짧은 진동. 움직임 줄이기(prefers-reduced-motion)면 꽃가루 없이 알약만.
 *  vfm.joyToday()  : 오늘 셈 {card, quiz, done} · vfm.joyStreak() : 연속 일수
 *  기록: localStorage vfm:joy (최근 60일) — 구글 동기화에 포함
 */
(function () {
  "use strict";
  if (window.__vfmJoy) return; window.__vfmJoy = 1;
  var V = window.vfm = window.vfm || {};
  var day = function (o) { return new Date(Date.now() + 9 * 3600e3 + (o || 0) * 864e5).toISOString().slice(0, 10); };
  var load = function () { try { return JSON.parse(localStorage.getItem("vfm:joy") || "{}") || {}; } catch (e) { return {}; } };
  var save = function (m) { var ks = Object.keys(m).sort(); while (ks.length > 60) delete m[ks.shift()]; try { localStorage.setItem("vfm:joy", JSON.stringify(m)); } catch (e) { } };
  var calm = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;

  var css = document.createElement("style");
  css.textContent = ".vfm-joy{position:fixed;left:50%;bottom:calc(env(safe-area-inset-bottom,0px) + 84px);transform:translate(-50%,12px) scale(.9);opacity:0;z-index:9998;pointer-events:none;" +
    "padding:8px 14px;border-radius:999px;background:rgba(28,28,30,.92);color:#fff;font:600 13.5px/1 -apple-system,BlinkMacSystemFont,'Pretendard Variable',Pretendard,system-ui,sans-serif;letter-spacing:-.01em;" +
    "box-shadow:0 6px 24px rgba(0,0,0,.18);transition:transform .32s cubic-bezier(.2,1.4,.4,1),opacity .2s;white-space:nowrap;font-variant-numeric:tabular-nums}" +
    ".vfm-joy.on{transform:translate(-50%,0) scale(1);opacity:1}.vfm-joy b{color:#FFD60A;font-weight:700;margin-right:6px}" +
    ".vfm-fx{position:fixed;inset:0;z-index:9997;pointer-events:none}";
  document.head.appendChild(css);

  var pill, pt;
  function show(html, ms) {
    if (!pill) { pill = document.createElement("div"); pill.className = "vfm-joy"; pill.setAttribute("aria-live", "polite"); document.body.appendChild(pill); }
    pill.innerHTML = html; void pill.offsetWidth; pill.classList.add("on");
    clearTimeout(pt); pt = setTimeout(function () { pill.classList.remove("on"); }, ms || 1300);
  }
  function buzz(p) { try { navigator.vibrate && navigator.vibrate(p); } catch (e) { } }

  /* 꽃가루: 캔버스 한 장, 0.9~1.4초 뒤 스스로 사라짐 */
  function confetti(big) {
    if (calm) return;
    var c = document.createElement("canvas"); c.className = "vfm-fx"; var d = Math.min(2, window.devicePixelRatio || 1);
    c.width = innerWidth * d; c.height = innerHeight * d; document.body.appendChild(c);
    var x = c.getContext("2d"); x.scale(d, d);
    var col = ["#FF9F0A", "#FFD60A", "#30D158", "#64D2FF", "#0A84FF", "#BF5AF2", "#FF375F"], n = big ? 110 : 36, P = [];
    for (var i = 0; i < n; i++) {
      var a = -Math.PI / 2 + (Math.random() - .5) * (big ? 2.2 : 1.3), v = (big ? 9 : 6) + Math.random() * (big ? 9 : 5);
      P.push({ x: innerWidth / 2 + (Math.random() - .5) * (big ? 120 : 40), y: innerHeight * (big ? .62 : .82), vx: Math.cos(a) * v, vy: Math.sin(a) * v, r: 3 + Math.random() * 4, c: col[i % col.length], t: Math.random() * 6, s: Math.random() < .5 });
    }
    var t0 = performance.now(), life = big ? 1500 : 950;
    (function f(now) {
      var k = (now - t0) / life; if (k >= 1) { c.remove(); return; }
      x.clearRect(0, 0, innerWidth, innerHeight);
      P.forEach(function (p) {
        p.vy += .32; p.vx *= .985; p.x += p.vx; p.y += p.vy; p.t += .25;
        x.globalAlpha = Math.max(0, 1 - k * k); x.fillStyle = p.c; x.save(); x.translate(p.x, p.y); x.rotate(p.t);
        if (p.s) x.fillRect(-p.r, -p.r * .5, p.r * 2, p.r); else { x.beginPath(); x.arc(0, 0, p.r * .7, 0, 6.3); x.fill(); }
        x.restore();
      });
      requestAnimationFrame(f);
    })(t0);
  }

  var NAME = { card: "장", quiz: "문제", done: "개" }, WORD = { card: "오늘 본 카드", quiz: "오늘 맞힌 문제", done: "오늘 끝낸 것" }, MILE = { 5: 1, 10: 1, 20: 1, 30: 1, 50: 1, 75: 1, 100: 1 };
  V.cheer = function (big, msg) { confetti(!!big); buzz(big ? [14, 40, 22] : 10); if (msg) show(msg, big ? 2200 : 1500); };
  V.tick = function (kind, quiet) {
    var m = load(), d = day(), t = m[d] = m[d] || {}; t[kind] = (t[kind] || 0) + 1; save(m);
    var n = t[kind];
    if (MILE[n]) { V.cheer(n >= 20, "<b>" + n + NAME[kind] + "</b>" + (kind === "card" ? "째! 잘 보고 있어요" : kind === "quiz" ? " 맞혔어요!" : " 끝냈어요!")); }
    else if (!quiet) { show("<b>+1</b>" + WORD[kind] + " " + n + NAME[kind], 1100); if (kind !== "card") buzz(8); }
    try { document.dispatchEvent(new CustomEvent("vfm:joy", { detail: { kind: kind, n: n } })); } catch (e) { }
    return n;
  };
  V.joyToday = function () { return load()[day()] || {}; };
  V.joyStreak = function () { var m = load(), n = 0; for (var i = 0; i < 400; i++) { var t = m[day(-i)]; if (t && (t.card || t.quiz || t.done)) n++; else if (i) break; } return n; };
})();
