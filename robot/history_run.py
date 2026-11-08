"""history_run.py — 역사 탭 로봇 (GitHub Actions). 토큰 0: 글을 '쓰지' 않고 위키백과 글을 '가져와 잘라 두기'만 한다.

한 번 돌면
  1. 종자   위키데이터에서 '역사 종류'(전투·혁명·조약·암살·스캔들·재난·옛 나라·시대·전설 … 90여 종류와 그 하위 종류 전부)에 속하고
            한국어 위키백과 글이 있는 것 '전부' + 역사 인물(죽었거나 1940년 전에 태어난 사람) '전부'
            + 한국어 위키백과 분류(한국사·일본사·중국사 등) + 영문 '핵심 문서' 목록  → 받을 차례(_state/queue.tsv)
            종자는 7일에 한 번만 다시 훑는다 (새로 생긴 글 찾기).
  2. 받기   받을 차례에서 점수(언어판 수 + 근현대 + 한국) 높은 순으로 50편씩: 본문(위키텍스트) → 단락으로 자르고,
            요약은 위키백과가 만든 깨끗한 첫 문단(TextExtracts)을 쓴다.
  3. 거르기 분류 종자·관계로 들어온 글은 위키데이터로 '역사 글인지' 확인해 아닌 것(운동 경기·요즘 연예인 등)은 뺀다 (_state/skip.tsv).
  4. 꼬리표 연도·시대·나라(지금 나라 + 당시 나라)·권역·테마·종류·야사·대명사를 표(history_tables.py)로 자동으로.
  5. 관계   이전·이후·원인·결과·참여자·관련 전쟁을 위키데이터에서 읽어 저장하고, 그 글들도 받을 차례에 넣는다(눈덩이).
  6. 저장   pages/xx/k<번호>.json 한 편씩. 용량 한도(HIST_BUDGET_MB)를 넘으면 그 뒤 글은 '요약판'(요약·소제목만,
            본문은 화면에서 위키백과로 바로 불러옴)으로 저장해 GitHub 무료 한도 1GB 를 지킨다.
  7. 색인   권역×시대·나라·연대·테마·검색·역사 속 오늘 색인을 새로 만든다 (화면은 필요한 조각만 불러옴).
  8. 갱신   받은 글 중 오래 확인 안 한 것부터 위키백과에서 고쳐졌는지 보고, 고쳐졌으면 다시 받는다. 지워진 글은 지운다.

시간(HIST_MAX_MINUTES)이나 편 수(HIST_MAX_PAGES) 한도에서 멈추고 다음 회차가 이어받는다. 중간중간(HIST_PUSH_EVERY 분) 저장소에 올린다.
    python robot/history_run.py                     # 보통
    python robot/history_run.py --quick --limit 60    # 빠른 확인 (종자 몇 개만)
    python robot/history_run.py --seeds-only         # 종자만
    python robot/history_run.py --no-seeds           # 종자 건너뛰고 받기만
    python robot/history_run.py --index-only         # 색인만 다시
출처: 한국어 위키백과 (CC BY-SA 4.0) · 위키데이터 (CC0). 화면과 글 파일에 출처를 남긴다.
"""
from __future__ import annotations

import json, math, os, re, shutil, signal, subprocess, sys, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import requests

try:
    import mwparserfromhell as mw
except Exception:  # pragma: no cover
    mw = None

sys.path.insert(0, str(Path(__file__).resolve().parent))
import history_tables as T

# ═══════════════════ 설정 ═══════════════════
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data/history"; ST = OUT / "_state"; PAGES = OUT / "pages"
KST = timezone(timedelta(hours=9))
UA = "vendingForMe-history-bot/2.0 (https://github.com/Jeffreryinko/vendingForMe; personal non-commercial history reader) python-requests"
API_KO = "https://ko.wikipedia.org/w/api.php"; API_EN = "https://en.wikipedia.org/w/api.php"; API_WD = "https://www.wikidata.org/w/api.php"
SPARQL_EPS = [("qlever", "https://qlever.dev/api/wikidata", 300), ("wdqs", "https://query.wikidata.org/sparql", 75)]
SPARQL_PFX = """PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX wikibase: <http://wikiba.se/ontology#>
PREFIX schema: <http://schema.org/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
"""
ARGS = sys.argv[1:]
def arg(name, default=None):
    if name in ARGS:
        i = ARGS.index(name); return ARGS[i + 1] if i + 1 < len(ARGS) else True
    return default
ENV = lambda k, d: os.environ.get(k) or d
MAX_MIN = float(ENV("HIST_MAX_MINUTES", "300"))
MAX_PAGES = int(arg("--limit", ENV("HIST_MAX_PAGES", "100000")))
BUDGET_MB = float(ENV("HIST_BUDGET_MB", "380"))          # 글 파일 전체 용량 한도 (넘으면 요약판으로)
FULL_CHARS = int(ENV("HIST_FULL_CHARS", "10000"))        # 한 편 본문 최대 글자 (넘으면 뒷부분은 화면에서 위키백과로)
RECHECK = int(ENV("HIST_RECHECK", "3000"))               # 회차마다 '고쳐졌나' 확인 편 수
VIEWS_BUDGET = int(ENV("HIST_VIEWS_BUDGET", "2500"))     # 회차마다 조회수 확인 편 수
SEED_EVERY = int(ENV("HIST_SEED_EVERY_DAYS", "7"))
PUSH_EVERY = float(ENV("HIST_PUSH_EVERY", "40"))         # 분. 0이면 중간 올리기 없음
GIT_PUSH = ENV("HIST_GIT_PUSH", "") == "1"
QUICK = "--quick" in ARGS; SEEDS_ONLY = "--seeds-only" in ARGS; NO_SEEDS = "--no-seeds" in ARGS or ENV("HIST_NO_SEEDS", "") == "1"
INDEX_ONLY = "--index-only" in ARGS; FORCE_SEEDS = "--force-seeds" in ARGS or ENV("HIST_FORCE_SEEDS", "") == "1"
SKIP_SECS = {"각주", "주석", "외부 링크", "같이 보기", "참고 문헌", "참고 자료", "출처", "관련 문서", "바깥 고리", "참조", "더 보기", "외부 연결", "참고 도서", "갤러리", "관련 항목",
             "참고", "주해", "각주 및 참고 문헌", "참고문헌", "출처 및 각주", "각주와 참고 문헌", "읽을거리", "더 읽어보기", "더 읽을거리", "외부 고리", "사진", "관련 링크", "링크", "같이보기", "참고 서적", "인용"}
SKIP_SECS_N = {x.replace(" ", "") for x in SKIP_SECS}

S = requests.Session(); S.headers.update({"User-Agent": UA, "Accept-Encoding": "gzip"})
T0 = time.time(); DEADLINE = T0 + MAX_MIN * 60
STOP = False
def _stop(sig, frm):                                     # 종료 신호(Actions 시간 초과 등) → 지금까지 받은 것 저장하고 끝
    global STOP; STOP = True; print("종료 신호 — 저장 후 끝냄", flush=True)
for _s in (signal.SIGTERM, signal.SIGINT): signal.signal(_s, _stop)
STAT = {"calls": 0, "pages": 0, "full": 0, "lite": 0, "skipped": 0, "seeds": 0, "err": 0, "r429": 0, "updated": 0, "removed": 0}
GAP = {"wiki": 0.25}                                     # 위키 요청 사이 쉬는 시간 (429 받으면 늘림)
LAST = {"wiki": 0.0}


def log(*a): print(datetime.now(KST).strftime("%H:%M:%S"), *a, flush=True)
def now_iso(): return datetime.now(KST).strftime("%Y-%m-%dT%H:%M:%S+09:00")
def today(): return datetime.now(KST).strftime("%Y-%m-%d")
def out_of_time(): return STOP or time.time() > DEADLINE
def rj(p, d=None):
    try: return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception: return d
def wj(p, o):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp"); tmp.write_text(json.dumps(o, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"); tmp.replace(p)
def dedupe(xs):
    seen, out = set(), []
    for x in xs:
        if x not in seen: seen.add(x); out.append(x)
    return out


# ═══════════════════ 상태 파일 (줄마다 하나, 정렬 → 저장소에 올릴 때 바뀐 줄만 늘어남) ═══════════════════
def read_tsv(p, ncol):
    out = []
    try:
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n")
                if not line: continue
                parts = line.split("\t")
                out.append(parts + [""] * (ncol - len(parts)))
    except FileNotFoundError: pass
    return out
def write_tsv(p, rows):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True); tmp = p.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows: f.write("\t".join("" if v is None else str(v).replace("\t", " ").replace("\n", " ") for v in r) + "\n")
    tmp.replace(p)
def _int(v, d=None):
    try: return int(v)
    except Exception: return d


class State:
    """pages: pid → {t, rev, at, chk, v, full, b, e}   queue: title → {q, n, y, th, kd, s, p, tr}   skip: title → (why, date)"""
    QCOLS = ["q", "n", "y", "th", "kd", "s", "p", "tr"]
    def __init__(self):
        self.pages = {}
        for r in read_tsv(ST / "pages.tsv", 9):
            try: e = json.loads(r[8]) if r[8] else None
            except Exception: e = None
            self.pages[r[0]] = {"t": r[1], "rev": _int(r[2], 0), "at": r[3], "chk": r[4], "v": _int(r[5], 0), "full": r[6] == "1", "b": _int(r[7], 0), "e": e}
        self.queue = {}
        for r in read_tsv(ST / "queue.tsv", 9):
            self.queue[r[0]] = {"q": r[1] or None, "n": _int(r[2], 0), "y": _int(r[3]), "th": r[4], "kd": r[5], "s": r[6], "p": _int(r[7], 0), "tr": _int(r[8], 0)}
        self.skip = {r[0]: (r[1], r[2]) for r in read_tsv(ST / "skip.tsv", 3)}
        self.by_title = {v["t"]: k for k, v in self.pages.items()}
        self.health = rj(ST / "health.json", {}); self.seeds = rj(ST / "seeds.json", {})
    def bytes_used(self): return sum(v["b"] for v in self.pages.values())
    def known(self, title): return title in self.by_title or title in self.skip or title in self.queue
    def enqueue(self, title, **h):
        title = (title or "").strip()
        if not title or len(title) < 2 or title in self.by_title or title in self.skip: return False
        if any(title.startswith(x) for x in ("분류:", "틀:", "파일:", "위키백과:", "포털:", "사용자:")): return False
        old = self.queue.get(title)
        if old:
            if h.get("p", 0) > old["p"]: old.update({k: v for k, v in h.items() if v not in (None, "")})
            return False
        self.queue[title] = {"q": h.get("q"), "n": h.get("n") or 0, "y": h.get("y"), "th": h.get("th") or "", "kd": h.get("kd") or "", "s": h.get("s") or "", "p": h.get("p") or 0, "tr": 0}
        return True
    def save(self):
        write_tsv(ST / "pages.tsv", [[k, v["t"], v["rev"], v["at"], v["chk"], v["v"], "1" if v["full"] else "0", v["b"], json.dumps(v["e"], ensure_ascii=False, separators=(",", ":")) if v["e"] else ""]
                                    for k, v in sorted(self.pages.items(), key=lambda kv: int(kv[0]))])
        write_tsv(ST / "queue.tsv", [[t, h["q"] or "", h["n"], "" if h["y"] is None else h["y"], h["th"], h["kd"], h["s"], h["p"], h["tr"]] for t, h in sorted(self.queue.items())])
        write_tsv(ST / "skip.tsv", [[t, w, d] for t, (w, d) in sorted(self.skip.items())])
        wj(ST / "health.json", self.health); wj(ST / "seeds.json", self.seeds)


def bad(st, key, e):
    err = f"{type(e).__name__}: {str(e)[:90]}"; h = st.health.setdefault(key, {"since": now_iso(), "n": 0}); h["n"] += 1; h["err"] = err; h["last"] = now_iso(); STAT["err"] += 1
    log(f"실패 {key}: {err}")
def good(st, key): st.health.pop(key, None)


# ═══════════════════ 요청 ═══════════════════
def get(url, params=None, retries=5, timeout=90, kind="wiki"):
    """위키 요청: 순서대로 하나씩, maxlag 존중, 429·5xx·끊김은 기다렸다 다시.
    maxlag(서버가 밀려 '잠깐 쉬었다 오라'는 신호)는 따로 세어 최대 약 10분까지 기다린다."""
    lagged = 0; i = -1
    while True:
        i += 1
        if i > retries: break
        wait = LAST[kind] + GAP[kind] - time.time()
        if wait > 0: time.sleep(wait)
        LAST[kind] = time.time(); STAT["calls"] += 1
        try:
            r = S.get(url, params=params, timeout=timeout)
        except (requests.ConnectionError, requests.Timeout) as e:
            if i >= retries: raise
            log(f"  연결 문제({type(e).__name__}) → {10 * (i + 1)}초 뒤 다시"); time.sleep(10 * (i + 1)); continue
        if r.status_code == 429 or r.status_code >= 500:
            if i >= retries: r.raise_for_status()
            if r.status_code == 429: STAT["r429"] += 1; GAP[kind] = min(5.0, GAP[kind] * 1.6 + 0.3)
            w = _int(r.headers.get("Retry-After"), 0) or 15 * (i + 1); w = min(w, 300)
            log(f"  {r.status_code} → {w}초 대기 (간격 {GAP[kind]:.2f}초)"); time.sleep(w); continue
        r.raise_for_status()
        if "json" in r.headers.get("content-type", ""):
            j = r.json()
            if isinstance(j, dict) and (j.get("error") or {}).get("code") == "maxlag" and lagged < 60:
                lagged += 1; i -= 1
                if lagged in (1, 10, 30): log(f"  서버가 밀려 있음(maxlag) → 기다렸다 다시 ({lagged}번째)")
                time.sleep(max(8, _int(r.headers.get("Retry-After"), 5))); continue
            if isinstance(j, dict) and j.get("error"): raise RuntimeError(f"API 오류 {j['error'].get('code')}: {str(j['error'].get('info'))[:80]}")
            if GAP[kind] > 0.25: GAP[kind] = max(0.25, GAP[kind] * 0.97)
            return j
        return r.text
    raise RuntimeError("재시도 초과")


def sparql(q, big=True):
    """위키데이터 질의. 큰 질의는 QLever(빠름, 시간 제한 넉넉) 먼저, 안 되면 공식 질의 서버(WDQS)."""
    eps = SPARQL_EPS if big else SPARQL_EPS[::-1]
    last = None
    for name, ep, tmo in eps:
        for i in range(2):
            try:
                STAT["calls"] += 1
                r = S.post(ep, data={"query": SPARQL_PFX + q}, headers={"Accept": "application/sparql-results+json"}, timeout=tmo)
                if r.status_code == 429: time.sleep(min(120, _int(r.headers.get("Retry-After"), 30))); continue
                r.raise_for_status()
                rows = json.loads(r.text, strict=False)["results"]["bindings"]       # 응답이 잘리면(시간 초과) 여기서 오류 → 다음 방법
                if not rows and name == "qlever" and len(eps) > 1: last = RuntimeError("QLever 빈 결과"); break   # 빈 결과는 공식 서버로 한 번 더 확인
                return rows
            except Exception as e:
                last = e; log(f"  질의 실패 [{name}] {type(e).__name__}: {str(e)[:70]}"); time.sleep(5 * (i + 1))
    raise last or RuntimeError("SPARQL 실패")
def bv(row, k, cast=str):
    v = (row.get(k) or {}).get("value")
    if v is None: return None
    try: return cast(v)
    except Exception: return None
qid_of = lambda v: v.rsplit("/", 1)[-1]
def year_lit(v):
    m = re.match(r"\s*(-?)(\d{1,6})", v or "")
    if not m: return None
    y = int(m.group(2)); return -y if m.group(1) else y


# ═══════════════════ 1. 종자 ═══════════════════
def seed_due(st, key, days=None):
    if FORCE_SEEDS: return True
    t = st.seeds.get(key)
    if not t: return True
    try: return (datetime.now(KST) - datetime.fromisoformat(t)).days >= (days or SEED_EVERY)
    except Exception: return True


def closure(st):
    """종류의 하위 종류 전부 (P279*) → {하위종류: 뿌리} · 막을 종류 · 뺄 직업. 30일에 한 번 새로."""
    sig = __import__("hashlib").md5(repr([(q, d) for q, _, _, _, d in T.SEED_CLASSES] + sorted(T.CLASS_BLOCK) + sorted(T.OCC_SKIP_ROOTS) + sorted(T.OCC_KEEP)).encode()).hexdigest()[:12]
    c = rj(ST / "closure.json", None)
    if c and c.get("sig") == sig and not seed_due(st, "closure", 30) and c.get("cls"): return c
    log("하위 종류 표 만들기 (P279*)…")
    cls, sizes = {}, {}
    for qid, memo, th, kd, deep in T.SEED_CLASSES:
        subs = [qid]
        if deep:
            try: subs = dedupe([qid] + [qid_of(bv(r, "s")) for r in sparql(f"SELECT ?s WHERE {{ ?s wdt:P279* wd:{qid} }}")])
            except Exception as e: bad(st, f"closure/{qid}", e)
        sizes[qid] = len(subs)
        for s in subs:
            if s in T.CLASS_BLOCK: continue
            if s not in cls or sizes[cls[s]] > len(subs): cls[s] = qid          # 여러 뿌리에 걸리면 더 좁은(구체적인) 뿌리
        time.sleep(0.5)
    def clos(roots):
        out = set(roots)
        for q in roots:
            try: out |= {qid_of(bv(r, "s")) for r in sparql(f"SELECT ?s WHERE {{ ?s wdt:P279* wd:{q} }}")}
            except Exception as e: bad(st, f"closure/{q}", e)
            time.sleep(0.5)
        return sorted(out)
    block = clos(sorted(T.CLASS_BLOCK)); occ = clos(sorted(T.OCC_SKIP_ROOTS)); keep = clos(sorted(T.OCC_KEEP))
    for b in block: cls.pop(b, None)
    c = {"sig": sig, "cls": cls, "block": block, "occ_skip": [o for o in occ if o not in set(keep)], "occ_keep": keep}
    wj(ST / "closure.json", c); st.seeds["closure"] = now_iso()
    log(f"  하위 종류 {len(cls):,}개 · 막을 종류 {len(block):,} · 뺄 직업 {len(c['occ_skip']):,}")
    return c


def seed_classes(st):
    """종류별: 그 종류(하위 포함)에 속하고 한국어 글이 있는 것 전부."""
    lst = T.SEED_CLASSES[:3] if QUICK else T.SEED_CLASSES
    for qid, memo, th, kd, deep in lst:
        if out_of_time(): return
        key = f"class/{qid}"
        if not seed_due(st, key): continue
        rows = None
        path = "wdt:P31/wdt:P279*" if deep else "wdt:P31"
        q = f"""SELECT ?item ?title ?n ?d WHERE {{ ?item {path} wd:{qid} .
          ?art schema:about ?item ; schema:isPartOf <https://ko.wikipedia.org/> ; schema:name ?title .
          OPTIONAL {{ ?item wikibase:sitelinks ?n }} OPTIONAL {{ ?item wdt:P585|wdt:P580|wdt:P571 ?d }} }}"""
        try: rows = sparql(q)
        except Exception as e:
            if deep:                                                           # 너무 큰 종류 → 바로 아래 종류로 나눠 받기
                rows = []
                try:
                    subs = [qid] + [qid_of(bv(r, "s")) for r in sparql(f"SELECT ?s WHERE {{ ?s wdt:P279 wd:{qid} }}", big=False)]
                    for s in subs:
                        if s in T.CLASS_BLOCK or out_of_time(): continue
                        try: rows += sparql(q.replace(f"{path} wd:{qid}", f"wdt:P31{'/wdt:P279*' if s != qid else ''} wd:{s}"))
                        except Exception as e2: bad(st, f"class/{qid}/{s}", e2)
                except Exception as e2: bad(st, key, e2); continue
            else: bad(st, key, e); continue
        got = {}
        for r in rows:
            t = bv(r, "title")
            if not t: continue
            y = year_lit(bv(r, "d")); g = got.setdefault(t, {"q": qid_of(bv(r, "item") or ""), "n": bv(r, "n", int) or 0, "y": y})
            if y is not None and (g["y"] is None or y < g["y"]): g["y"] = y
        n = sum(st.enqueue(t, q=g["q"], n=g["n"], y=g["y"], th=th, kd=kd, s="class:" + memo, p=T.priority(g["n"], g["y"], kind=kd)) for t, g in got.items())
        STAT["seeds"] += n; st.seeds[key] = now_iso(); good(st, key)
        log(f"종자 {memo}: {len(got):,}편 중 새로 {n:,}")
        time.sleep(1)


def seed_people(st):
    """역사 인물: 한국어 글 + 언어판 수 구간별 (질의가 너무 크면 구간을 쪼갬)."""
    lo_min = T.PEOPLE_MIN_LINKS
    bands = [(400, 100000), (200, 399), (120, 199), (80, 119), (60, 79), (45, 59), (35, 44), (28, 34), (22, 27), (18, 21), (15, 17), (12, 14), (10, 11), (8, 9), (7, 7), (6, 6), (5, 5), (4, 4), (3, 3), (2, 2), (1, 1)]
    if QUICK: bands = [(80, 119)]
    todo = [b for b in bands if b[1] >= lo_min]; fails = 0
    while todo:
        if out_of_time(): return
        lo, hi = todo.pop(0); lo = max(lo, lo_min); key = f"people/{lo}-{hi}"
        if not seed_due(st, key): continue
        q = f"""SELECT ?item ?title ?n ?b ?d WHERE {{ ?item wdt:P31 wd:Q5 ; wikibase:sitelinks ?n . FILTER(?n >= {lo} && ?n <= {hi})
          ?art schema:about ?item ; schema:isPartOf <https://ko.wikipedia.org/> ; schema:name ?title .
          OPTIONAL {{ ?item wdt:P569 ?b }} OPTIONAL {{ ?item wdt:P570 ?d }} }}"""
        try: rows = sparql(q)
        except Exception as e:
            fails += 1
            if fails >= 6: bad(st, "seed/people", e); log("  인물 질의가 계속 실패 → 이번엔 'N년 출생·사망' 분류로 대신 모음"); return
            if hi > lo: mid = (lo + hi) // 2; todo[:0] = [(lo, mid), (mid + 1, hi)]; log(f"  인물 {lo}~{hi} 나눠서 다시"); continue
            bad(st, key, e); continue
        got = {}
        for r in rows:
            t = bv(r, "title")
            if not t: continue
            g = got.setdefault(t, {"q": qid_of(bv(r, "item") or ""), "n": bv(r, "n", int) or 0, "b": None, "d": False})
            b = year_lit(bv(r, "b"))
            if b is not None and (g["b"] is None or b < g["b"]): g["b"] = b
            if r.get("d"): g["d"] = True
        n = 0
        for t, g in got.items():
            if not g["d"] and (g["b"] is None or g["b"] >= T.PEOPLE_RECENT_BIRTH): continue      # 살아 있는 요즘 사람은 역사 아님
            act = None if g["b"] is None else g["b"] + 40
            n += st.enqueue(t, q=g["q"], n=g["n"], y=g["b"], kd="person", s="people", p=T.priority(g["n"], act, kind="person"))
        STAT["seeds"] += n; st.seeds[key] = now_iso(); good(st, key)
        log(f"종자 인물 {lo}~{hi}개 언어: {len(got):,}명 중 새로 {n:,}")
        time.sleep(1)


def seed_people_cats(st):
    """예비 길 + 보충: 한국어 위키백과 'N년 출생'·'N년 사망' 분류를 해마다 훑어 사람을 전부 모은다
    (언어판이 1~2개뿐인 조선 문신 같은 한국사 인물까지). 30일에 한 번, 끊기면 이어서."""
    if QUICK or not seed_due(st, "pcat", 30): return
    years = [("출생", y) for y in range(-800, T.PEOPLE_RECENT_BIRTH)] + [("사망", y) for y in range(-800, datetime.now(KST).year + 1)]
    years += [("출생", f"{d}년대") for d in range(-800, T.PEOPLE_RECENT_BIRTH, 10)] + [("사망", f"{d}년대") for d in range(-800, datetime.now(KST).year + 1, 10)]   # 정확한 해를 모르는 사람
    pos = int(st.seeds.get("pcat_pos", 0)); got = 0
    while pos < len(years):
        if out_of_time(): break
        kind, y = years[pos]
        if isinstance(y, str):                                          # 'N년대'
            d = int(y[:-2]); cat = f"분류:{'기원전 ' + str(-d) if d < 0 else d}년대 {kind}"; y = d + 5
        else: cat = f"분류:{'기원전 ' + str(-y) if y < 0 else y}년 {kind}"
        if y == 0: pos += 1; continue
        cont = {}
        try:
            while True:
                j = get(API_KO, dict(action="query", format="json", formatversion=2, list="categorymembers", cmtitle=cat, cmlimit=500, cmprop="title", cmnamespace=0, maxlag=5, **cont))
                for m in (j.get("query") or {}).get("categorymembers", []):
                    act = (y + 40) if kind == "출생" else y
                    got += st.enqueue(m["title"], n=0, y=y if kind == "출생" else None, kd="person", s="pcat", p=max(1, T.priority(0, act, kind="person") - 2))
                cont = j.get("continue") or {}
                if not cont: break
        except Exception as e: bad(st, "seed/pcat", e); break
        pos += 1; st.seeds["pcat_pos"] = pos
        if pos % 400 == 0: log(f"  사람 분류 {pos:,}/{len(years):,}년 · 새로 {got:,}")
    if pos >= len(years): st.seeds["pcat"] = now_iso(); st.seeds["pcat_pos"] = 0; good(st, "seed/pcat")
    STAT["seeds"] += got; log(f"종자 사람 분류(N년 출생·사망): 새로 {got:,} ({pos:,}/{len(years):,}년)")


def seed_vital(st):
    """영문 위키백과 '핵심 문서(Vital articles)' 인물·역사 → 한국어 글이 있는 것. 30일에 한 번."""
    if not seed_due(st, "vital", 30) or QUICK: return
    try:
        lists = ["Wikipedia:Vital articles/Level/4/People", "Wikipedia:Vital articles/Level/4/History", "Wikipedia:Vital articles/Level 4/People", "Wikipedia:Vital articles/Level 4/History"]
        for pre in ("Vital articles/Level/5/People/", "Vital articles/Level/5/History"):
            j = get(API_EN, dict(action="query", format="json", formatversion=2, list="allpages", apnamespace=4, apprefix=pre, aplimit=200, maxlag=5))
            lists += [p["title"] for p in (j.get("query") or {}).get("allpages", [])]
        en = []
        for lt in dedupe(lists):
            if out_of_time(): break
            j = get(API_EN, dict(action="query", format="json", formatversion=2, titles=lt, prop="revisions", rvprop="content", rvslots="main", redirects=1, maxlag=5))
            for p in (j.get("query") or {}).get("pages", []):
                if not p.get("revisions"): continue
                for t in re.findall(r"\[\[([^\[\]|#]+)(?:\|[^\]]*)?\]\]", p["revisions"][0]["slots"]["main"]["content"]):
                    t = t.strip()
                    if ":" not in t and len(t) > 1: en.append(t)
        en = dedupe(en); got = 0
        for i in range(0, len(en), 50):
            if out_of_time(): break
            j = get(API_EN, dict(action="query", format="json", formatversion=2, titles="|".join(en[i:i + 50]), prop="langlinks", lllang="ko", lllimit="max", redirects=1, maxlag=5))
            for p in (j.get("query") or {}).get("pages", []):
                for l in p.get("langlinks", []):
                    got += st.enqueue(l.get("title"), n=60, s="vital", p=70)
        st.seeds["vital"] = now_iso(); good(st, "seed/vital"); STAT["seeds"] += got
        log(f"종자 핵심 문서: 영문 {len(en):,}편 → 한국어 새로 {got:,}")
    except Exception as e: bad(st, "seed/vital", e)


def seed_cats(st):
    """한국어 위키백과 분류를 깊이 제한으로 훑는다 (받을 때 '역사 글인지' 다시 확인)."""
    roots = [("분류:조선의 왕", 0)] if QUICK else T.SEED_CATS
    for root, depth in roots:
        if out_of_time(): return
        key = "cat/" + root.split(":", 1)[-1]
        if not seed_due(st, key): continue
        todo, done, got, n_sub = [(root, 0)], set(), 0, 0
        try:
            while todo and n_sub < 400:
                cat, d = todo.pop(0)
                if cat in done: continue
                done.add(cat); n_sub += 1; cont = {}
                while True:
                    j = get(API_KO, dict(action="query", format="json", formatversion=2, list="categorymembers", cmtitle=cat, cmlimit=500, cmprop="title|type", cmnamespace="0|14", maxlag=5, **cont))
                    for m in (j.get("query") or {}).get("categorymembers", []):
                        if m["type"] == "subcat":
                            name = m["title"].split(":", 1)[-1]
                            if d < depth and not any(k in name for k in T.CAT_SKIP): todo.append((m["title"], d + 1))
                        elif m["type"] == "page":
                            t = m["title"]
                            if any(x in t for x in T.CAT_PAGE_SKIP): continue
                            got += st.enqueue(t, n=0, s="cat:" + root.split(":", 1)[-1], p=12 + (15 if any(k in root for k in ("한국", "조선", "고려", "신라", "백제", "고구려", "발해", "가야", "대한", "일제")) else 0))
                    cont = j.get("continue") or {}
                    if not cont: break
            st.seeds[key] = now_iso(); good(st, key)
        except Exception as e: bad(st, key, e); continue
        STAT["seeds"] += got; log(f"종자 {root} (깊이 {depth}, 분류 {n_sub}개): 새로 {got:,}")


# ═══════════════════ 2. 본문 다듬기 ═══════════════════
FILE_NS = ("파일:", "file:", "그림:", "image:", "분류:", "category:", "미디어:", "media:")
RX_REF = re.compile(r"<ref[^>/]*/>|<ref[^>]*>.*?</ref>", re.S | re.I)
RX_TAGS = re.compile(r"<(gallery|timeline|imagemap|math|score|syntaxhighlight|source|pre|graph|mapframe|templatestyles|references)[^>]*>.*?</\1>|<(templatestyles|references)[^>]*/>", re.S | re.I)
RX_TABLE = re.compile(r"\{\|(?:(?!\{\|).)*?\|\}", re.S)
RX_HTML = re.compile(r"</?(br|div|span|small|big|sup|sub|center|font|nowiki|poem|blockquote|table|tr|td|th|p|b|i|u|s|abbr|cite|code|tt|ins|del|mark|q|var|ruby|rt|rp|onlyinclude|includeonly|noinclude|section)[^>]*/?>", re.I)
RX_EMPTY_PAREN = re.compile(r"\s*[\(（]\s*[,;·、:\-–\s]*[\)）]")
RX_SENT = re.compile(r"(?<=[다요음임됨])\.\s+|(?<=[.!?])\s+(?=[가-힣A-Z\"'“])")
LANG_T = {"lang", "llang", "언어", "lang2", "언어2", "transl", "음역", "lang-ko", "langx", "native name", "nihongo", "일본어", "중국어", "zh", "한자", "漢字", "hanja", "한자 병기", "한자병기", "고어", "nobr", "nowrap", "작은 글씨", "small", "큰 글씨", "big", "문단", "색", "color", "글자색", "글씨 색", "abbr", "약자", "강조", "u", "under", "밑줄", "취소선", "s", "강조2", "그늘", "highlight", "lang-en", "repetition", "nbsp", "정렬", "가운데"}
DATE_T = {"출생일", "사망일", "출생일과 나이", "사망일과 나이", "birth date", "death date", "birth date and age", "death date and age", "날짜", "date", "start date", "end date", "출생일 및 나이", "사망일 및 나이", "dts", "생년월일과 나이", "생년월일", "몰년월일과 향년", "사망 일자", "출생 일자", "birth year and age", "death year and age"}
FLAG_T = {"국기나라", "flagcountry", "깃발나라", "flag", "국기", "깃발", "나라", "country", "flagu", "국가명", "국기그림나라"}
QUOTE_T = {"인용문", "quote", "blockquote", "인용", "cquote", "인용구", "따옴표", "quotation", "시"}


def tpl_text(t):
    name = str(t.name).strip().lower().replace("_", " ")
    if name.startswith(("lang-", "llang", "lang ", "언어-")) : name = "lang"
    pos = [expand_str(str(p.value)) for p in t.params if not p.showkey]
    kw = {str(p.name).strip().lower(): p for p in t.params if p.showkey}
    if name in LANG_T: return pos[-1] if pos else ""
    if name in DATE_T:
        nums = [x.strip() for x in pos if x.strip().lstrip("-").isdigit()][:3]
        if not nums: return ""
        s = f"{nums[0]}년"
        if len(nums) > 1: s += f" {int(nums[1])}월"
        if len(nums) > 2: s += f" {int(nums[2])}일"
        return s
    if name in FLAG_T: return pos[0] if pos else ""
    if name in QUOTE_T: return (pos[0] if pos else expand_str(str(kw["text"].value)) if "text" in kw else "")
    if name in ("convert", "변환", "cvt"): return " ".join(pos[:2])
    if name in ("기원전", "bc", "bce"): return ("기원전 " + pos[0]) if pos else "기원전"
    if name in ("circa", "c.", "약", "대략"): return ("약 " + pos[0]) if pos else ""
    if name in ("ill", "interlanguage link", "링크", "lien", "외국어 링크", "ill2", "외부 언어 링크"): return pos[0] if pos else ""
    if name in ("한국어 표기", "ko", "korean"): return pos[0] if pos else ""
    return ""


def expand_str(s):
    if "{{" not in s: return mw.parse(s).strip_code(normalize=True, collapse=True)
    return plain(expand(mw.parse(s)))


def expand(code):
    for t in code.filter_templates(recursive=False):
        try: code.replace(t, tpl_text(t))
        except Exception:
            try: code.remove(t)
            except Exception: pass
    return code


def clean_wikitext(wt):
    wt = RX_REF.sub(" ", wt); wt = RX_TAGS.sub(" ", wt); wt = re.sub(r"<!--.*?-->", " ", wt, flags=re.S)
    for _ in range(4):
        n = RX_TABLE.sub(" ", wt)
        if n == wt: break
        wt = n
    code = mw.parse(wt)
    for l in list(code.filter_wikilinks()):
        if str(l.title).strip().lower().startswith(FILE_NS):
            try: code.remove(l)
            except Exception: pass
    return expand(code)


def plain(node):
    s = node.strip_code(normalize=True, collapse=True) if hasattr(node, "strip_code") else str(node)
    s = RX_HTML.sub(" ", s); s = RX_EMPTY_PAREN.sub("", s)
    s = re.sub(r"[ \t ]+", " ", s); s = re.sub(r" *\n *", "\n", s); s = re.sub(r"\n{2,}", "\n", s)
    s = re.sub(r"\s+([,.)])", r"\1", s); s = re.sub(r",(\s*,)+", ",", s); s = re.sub(r"\(\s*,\s*", "(", s); s = re.sub(r",\s*\)", ")", s)
    return s.strip()


def first_sentence(text, n=170):
    t = (text or "").split("\n")[0].strip()
    parts = RX_SENT.split(t)
    s = (parts[0] or t).strip()
    if len(parts) > 1 and not s.endswith((".", "!", "?")): s += "."
    return s[:n]


def norm_link(t):
    t = str(t).strip().split("#")[0].strip().replace("_", " ")
    return (t[0].upper() + t[1:]) if t and t[0].isascii() else t


def split_sections(code):
    secs = code.get_sections(include_lead=True, flat=True, include_headings=True)
    lead, out, heads, links = "", [], [], []
    for i, sec in enumerate(secs):
        hs = sec.filter_headings()
        if i == 0 and not hs: lead = plain(sec); _links(sec, links); continue
        if not hs: continue
        h = hs[0]; title = plain(h.title); lvl = int(h.level)
        if not title or title.replace(" ", "") in SKIP_SECS_N: continue
        body = mw.parse(str(sec))
        try: body.remove(body.filter_headings()[0])
        except Exception: pass
        txt = plain(body)
        heads.append([title, lvl])
        if len(txt) < 20: continue
        out.append({"h": title, "l": lvl, "t": txt})
        if len(out) <= 4: _links(sec, links)
    return lead, out, heads, dedupe(links)[:30]


RX_DATE_LINK = re.compile(r"^(기원전\s*)?\d+(년|년대|세기|월|월 \d+일|일)$|^\d+월 \d+일$|^음력|^율리우스력$|^그레고리력$")
def _links(node, links):
    for l in node.filter_wikilinks():
        t = norm_link(l.title)
        if not t or t.lower().startswith(FILE_NS) or ":" in t or RX_DATE_LINK.match(t): continue
        links.append(t)


def cap_sections(lead, secs, limit):
    total = len(lead); kept = []; cut = False
    for s in secs:
        if total + len(s["t"]) > limit:
            room = limit - total
            if room > 500: kept.append({"h": s["h"], "l": s["l"], "t": s["t"][:room].rsplit(" ", 1)[0] + " …"})
            cut = True; break
        total += len(s["t"]); kept.append(s)
    return kept, cut


# ═══════════════════ 3. 위키데이터 ═══════════════════
def wd_entities(qids, props="claims|labels|sitelinks|descriptions", extra=None):
    out = {}
    qids = [q for q in dedupe(qids) if q and re.match(r"^Q\d+$", q)]
    for i in range(0, len(qids), 50):
        p = {"action": "wbgetentities", "format": "json", "ids": "|".join(qids[i:i + 50]), "props": props, "languages": "ko|en", "languagefallback": 1, "maxlag": 10, **(extra or {})}
        try: out.update(get(API_WD, p).get("entities", {}))
        except Exception as e: log(f"  위키데이터 묶음 실패: {str(e)[:70]}")
    return out


def _end_year(c):
    """그 진술의 '끝난 때'(P582) 연도. 없으면 None (= 끝나지 않음, 죽을 때까지 유지)"""
    q = ((c.get("qualifiers") or {}).get("P582") or [{}])[0]
    t = ((q.get("datavalue") or {}).get("value") or {}).get("time", "") if isinstance(q, dict) else ""
    m = re.match(r"([+-])0*(\d+)", t or "")
    return (-1 if m.group(1) == "-" else 1) * int(m.group(2)) if m else None


def cv(e, p, latest=False):
    """속성 값들 (deprecated 빼고, preferred 먼저).
    latest=True(국적): 끝난 때가 없는 것(죽을 때의 나라) → 늦게 끝난 것 순 — 김일성이 일본 제국(1945년 끝)이 아니라 북한이 되게"""
    cs = [c for c in (e.get("claims") or {}).get(p, []) if c.get("rank") != "deprecated"]
    if latest:
        cs.sort(key=lambda c: (0 if c.get("rank") == "preferred" else 1, 0 if _end_year(c) is None else 1, -(_end_year(c) or 0)))
    else:
        cs.sort(key=lambda c: 0 if c.get("rank") == "preferred" else 1)
    out = []
    for c in cs:
        v = ((c.get("mainsnak") or {}).get("datavalue") or {}).get("value")
        if isinstance(v, dict) and "id" in v: out.append(v["id"])
        elif isinstance(v, dict) and "time" in v: out.append(v)
        elif isinstance(v, (str, int, float)): out.append(v)
    return out


def t_year(v):
    if not isinstance(v, dict): return None
    return year_lit(v.get("time", "").lstrip("+"))


def t_rough(e, p):
    """그 속성의 첫 날짜가 대략적인가? (정밀도가 연도보다 거칠거나, 출처가 '경'으로 단 날짜)"""
    cs = [c for c in (e.get("claims") or {}).get(p, []) if c.get("rank") != "deprecated"] if e else []
    if not cs: return False
    cs.sort(key=lambda c: 0 if c.get("rank") == "preferred" else 1); c = cs[0]
    v = ((c.get("mainsnak") or {}).get("datavalue") or {}).get("value")
    if isinstance(v, dict) and v.get("precision", 9) < 9: return True
    for q in (c.get("qualifiers") or {}).get("P1480", []):
        if (((q.get("datavalue") or {}).get("value")) or {}).get("id") == T.CIRCA: return True
    return False


def t_md(v):
    """정밀도가 '일'인 날짜 → 'MM-DD'"""
    if not isinstance(v, dict) or v.get("precision", 0) < 11: return ""
    m = re.match(r"[+-]?\d+-(\d\d)-(\d\d)", v.get("time", ""))
    return f"{m.group(1)}-{m.group(2)}" if m and m.group(1) != "00" and m.group(2) != "00" else ""


def label(e, lang="ko"):
    l = e.get("labels") or {}
    return ((l.get(lang) or l.get("en") or {}).get("value")) or ""


class Countries:
    """나라·장소 QID → (지금 나라 ISO, 권역, 당시 이름). 캐시 _state/countries.json"""
    def __init__(self): self.c = rj(ST / "countries.json", {})
    def ensure(self, qids):
        need = [q for q in dedupe(qids) if q and q not in self.c]
        for _ in range(3):
            if not need: break
            ents = wd_entities(need, "claims|labels")
            nxt = []
            for q in need:
                e = ents.get(q, {})
                rec = {"ko": label(e), "iso": (cv(e, "P297") or [None])[0], "cont": cv(e, "P30")[:2], "p17": [x for x in cv(e, "P17") if x != q][:2],
                       "succ": cv(e, "P1366")[:3], "adm": cv(e, "P131")[:1], "now": cv(e, "P3842")[:2]}
                self.c[q] = rec
                if not rec["iso"] and q not in T.HIST_ISO: nxt += rec["p17"] + rec["now"] + rec["adm"] + rec["succ"]
            need = [q for q in dedupe(nxt) if q not in self.c]
    def resolve(self, q, depth=0, seen=None):
        seen = seen if seen is not None else set()
        if not q or q in seen or depth > 5: return None, "", ""
        seen.add(q)
        if q in T.CONTINENT_REGION: return None, T.CONTINENT_REGION[q], ""          # 대륙·지역 자체 (유럽·중동 등)
        if q in T.HIST_ISO: iso = T.HIST_ISO[q]; return iso, T.ISO_REGION.get(iso, ""), (self.c.get(q) or {}).get("ko", "")
        r = self.c.get(q)
        if not r: return None, "", ""
        if r.get("iso"): return r["iso"], T.ISO_REGION.get(r["iso"], ""), ""
        for hop in r.get("p17", []) + r.get("now", []) + r.get("adm", []) + r.get("succ", []):
            iso, reg, _ = self.resolve(hop, depth + 1, seen)
            if iso: return iso, reg, r.get("ko", "")
        cont = next((T.CONTINENT_REGION.get(c) for c in r.get("cont", []) if T.CONTINENT_REGION.get(c)), "")
        return None, cont, r.get("ko", "")
    def iso_names(self):
        out = {}
        for r in self.c.values():
            if r.get("iso") and r.get("ko"): out.setdefault(r["iso"], r["ko"])
        return out
    def save(self): wj(ST / "countries.json", self.c)


class Labels:
    """QID → [한국어 라벨, 한국어 위키백과 제목] 캐시 _state/labels.json"""
    def __init__(self): self.c = rj(ST / "labels.json", {})
    def ensure(self, qids):
        need = [q for q in dedupe(qids) if q and q not in self.c]
        if not need: return
        ents = wd_entities(need, "labels|sitelinks", {"sitefilter": "kowiki"})
        for q in need:
            e = ents.get(q, {})
            self.c[q] = [label(e) or label(e, "en"), ((e.get("sitelinks") or {}).get("kowiki") or {}).get("title", "")]
    def name(self, q): return (self.c.get(q) or ["", ""])[0]
    def ko(self, q): return (self.c.get(q) or ["", ""])[1]
    def save(self):
        if len(self.c) > 400000: self.c = dict(list(self.c.items())[-300000:])
        wj(ST / "labels.json", self.c)


# ═══════════════════ 4. 거르기·분류 ═══════════════════
KCODE = {"person": "p", "event": "e", "state": "s", "period": "t", "lore": "l", "concept": "c", "other": "o"}
REL_PROPS = (("prev", "P155"), ("next", "P156"), ("part", "P361"), ("people", "P710"), ("effect", "P1542"), ("cause", "P828"), ("conf", "P607"), ("evt", "P793"), ("follows", "P1365"), ("followed", "P1366"))


def judge(page, ent, hint, CL):
    """이 글이 역사 글인가? → (kind 또는 None, 뺀 이유)"""
    p31 = cv(ent, "P31") if ent else []
    if any(x in T.PLACE_CLASSES for x in p31) and not any(x in CL["cls"] for x in p31): return None, "도시·마을·지금 나라"
    blk = set(CL["block"])
    if p31 and any(x in blk for x in p31) and not any(x in CL["cls"] for x in p31): return None, "운동경기·선거·행사"
    if "Q5" in p31:
        b = t_year((cv(ent, "P569") or [None])[0]); dead = bool(cv(ent, "P570"))
        if not dead and (b is None or b >= T.PEOPLE_RECENT_BIRTH): return None, "요즘 사람"
        n = len(ent.get("sitelinks") or {})
        occ = cv(ent, "P106")
        skip, keep = set(CL["occ_skip"]), set(CL["occ_keep"])
        if occ and n < T.PEOPLE_FAMOUS and b is not None and b >= T.SKIP_AFTER_BIRTH and all(o in skip for o in occ[:6]) and not any(o in keep for o in occ): return None, "근현대 운동선수·연예인"
        return "person", ""
    roots = [CL["cls"][x] for x in p31 if x in CL["cls"]]
    if roots: return T.CLASS_KIND.get(roots[0], "event"), ""
    if hint.get("kd"): return hint["kd"], ""                          # 종류 종자로 들어온 글 (하위 종류 표에 빠졌어도 믿음)
    cats = " ".join(c["title"] for c in page.get("cats", []))
    if any(w in cats for w in T.HIST_WORDS) or (hint.get("s", "").startswith(("cat:", "vital"))) and any(w in cats for w in ("역사", "사건", "인물", "전쟁", "시대")):
        y = None
        for p in ("P585", "P580", "P571", "P569"):
            y = t_year((cv(ent, p) or [None])[0]) if ent else None
            if y is not None: break
        if y is not None and y > 2005: return None, "최근 일"
        if ent and any(x in p31 for x in ("Q515", "Q1549591", "Q532", "Q3957", "Q486972", "Q6256", "Q3624078", "Q5119", "Q4830453", "Q43229", "Q783794", "Q891723", "Q11424", "Q7725634", "Q482994", "Q7889", "Q5398426")):
            return None, "도시·나라·회사·작품"          # 도시·마을·나라·수도·기업·조직·영화·책·앨범·게임·드라마 → 역사 '이야기'가 아님
        return ("period" if "시대" in page["title"] else "event"), ""
    return None, "역사 글 아님"


# 본문 첫 문단의 연도: '기원전 약 6000년', '기원전 6000년경' 도 기원전으로. '1만 년 전'(지금부터 몇 년 전)은 연도가 아님
LEAD_YEAR = re.compile(r"(기원전\s*(?:약|대략|무렵)?\s*)?(?<!\d)(?<!\d[,.])(\d{1,5})년(?!\s*전(?:[에의까부]|\s|,|\.|$))")
def role_places(e, kind):
    """classify 가 나라를 알아내려고 볼 장소 QID 들 (미리 Countries 에 받아 둠)"""
    out = cv(e, "P17") + cv(e, "P27") + cv(e, "P276") + cv(e, "P19") + cv(e, "P937") + cv(e, "P131")[:1] + cv(e, "P30")[:1] + ([e["id"]] if kind == "state" and e.get("id") else [])
    return [q for q in out if isinstance(q, str)]


def classify(page, ent, kind, C, L, hint, CL):
    p31 = cv(ent, "P31"); occ = cv(ent, "P106"); pos = cv(ent, "P39")
    md = ""; rough = False
    if kind not in ("person", "state") and set(p31) & T.CONCEPT_CLASSES: kind = "concept"
    if kind == "concept":
        y = y2 = ya = None
    elif kind == "person":
        bt = (cv(ent, "P569") or [None])[0]; dt = (cv(ent, "P570") or [None])[0]
        y, y2 = t_year(bt), t_year(dt); rough = t_rough(ent, "P569") if y is not None else t_rough(ent, "P570")
        ya = (min(y2, y + 40) if y2 is not None else y + 40) if y is not None else y2
    elif kind == "state":
        y, y2 = t_year((cv(ent, "P571") or cv(ent, "P580") or [None])[0]), t_year((cv(ent, "P576") or cv(ent, "P582") or [None])[0]); ya = y
        rough = t_rough(ent, "P571") if cv(ent, "P571") else t_rough(ent, "P580")
    else:
        d0 = (cv(ent, "P580") or cv(ent, "P585") or cv(ent, "P571") or [None])[0]   # 기간이 있으면 시작(P580) 먼저 — 1차 대전이 1918로 나오던 문제
        y = t_year(d0); y2 = t_year((cv(ent, "P582") or cv(ent, "P576") or [None])[0]); ya = y; md = t_md(d0) if kind == "event" else ""
        rough = next((t_rough(ent, p) for p in ("P580", "P585", "P571") if cv(ent, p)), False)
    if y is None and hint.get("y") is not None and kind not in ("person", "concept"): y = ya = hint["y"]
    if y is None and kind != "concept":                               # 본문 첫 문단에서 연도 찾기 (찾으면 '추정'으로 표시)
        m = LEAD_YEAR.search((page.get("lead") or "")[:400])
        if m: y = ya = -int(m.group(2)) if m.group(1) else int(m.group(2)); rough = True
        if kind == "person" and y is not None: ya = y + 40 if y < 1990 else y
    NOW_Y = datetime.now(KST).year                                   # 미래 연도(위키데이터 오류)는 버림
    if y is not None and y > NOW_Y + 1: y = ya = None; md = ""
    if y2 is not None and y2 > NOW_Y + 1: y2 = None
    if ya is not None and ya > NOW_Y + 1: ya = y
    if y2 is not None and y is not None and y2 < y: y2 = None
    # 역할별 나라: 인물 = 국적(속한 나라·왕조) → 활동지 → 출생지 / 사건 = 일어난 곳 → 나라 / 나라·왕조 = 그 나라
    # (출생지가 먼저면 백제 무령왕이 '일본'(섬에서 태어났다는 기록), 동로마 황제가 '튀르키예'가 되던 문제)
    if kind == "person": ROLE = (("nat", cv(ent, "P27", latest=True)[:3], 1), ("work", cv(ent, "P937")[:3], 0), ("born", cv(ent, "P19")[:1], 0))
    elif kind == "state": ROLE = (("at", [ent.get("id")] + cv(ent, "P17")[:2], 1), ("at", cv(ent, "P30")[:1], 0))
    else: ROLE = (("at", cv(ent, "P17")[:4], 1), ("at", cv(ent, "P276")[:6], 0), ("at", cv(ent, "P131")[:1], 0), ("side", [q for q in cv(ent, "P710")[:8] if q in C.c], 1))
    isos, thens, region, roles, at_regs, cont_reg = [], [], "", {}, [], ""
    for role, qs, pol in ROLE:                                        # pol = 나라(정치체)를 가리키는 속성 → '당시 이름'을 씀
        for q in qs:
            if not isinstance(q, str): continue
            iso, reg, then = C.resolve(q)
            then = then if pol else ""
            if (iso or then) and not any(r[0] == (iso or "") and (r[1] == then or not then) for r in roles.get(role, [])): roles.setdefault(role, []).append([iso or "", then])
            if iso and iso not in isos: isos.append(iso)
            if then and then not in thens: thens.append(then)
            if not region and reg: region = reg                       # 처음 권역이 나오는 곳 (대륙만 알아도)
            if role == "at" and reg and reg not in at_regs: at_regs.append(reg)
            if role == "at" and q in T.CONTINENT_REGION and not cont_reg: cont_reg = T.CONTINENT_REGION[q]
    if isos and not region: region = T.ISO_REGION.get(isos[0], "")
    if len(at_regs) >= 3 and cont_reg: region = cont_reg               # 여러 권역 사건은 위키데이터가 처음 적은 대륙(1차 대전 → 유럽)
    if (y if y is not None else ya if ya is not None else 9999) < 1948:    # 남북 분단 전 한반도 = '한국' (평양에서 있었던 고구려 일도 북한이 아님)
        fx = lambda l: [x for k, x in enumerate(["KR" if i == "KP" else i for i in l]) if x not in ["KR" if i == "KP" else i for i in l][:k]]
        isos = fx(isos)
        for r in roles.values():
            for x in r:
                if x[0] == "KP": x[0] = "KR"
    if not isos:                                                      # 위키데이터에 나라가 없으면 분류 이름으로 한국·일본·중국만이라도
        cats = " ".join(c["title"] for c in page.get("cats", []))
        for words, iso in ((("조선", "고려", "신라", "백제", "고구려", "발해", "가야", "대한제국", "한국", "대한민국", "일제강점기"), "KR"), (("일본",), "JP"), (("중국", "청나라", "명나라", "당나라", "송나라", "원나라", "한나라"), "CN")):
            if any(w in cats for w in words): isos = [iso]; region = T.ISO_REGION[iso]; break
    cats = [c["title"].split(":", 1)[-1] for c in page.get("cats", [])]
    desc = ((ent.get("descriptions") or {}).get("ko") or {}).get("value", "")
    words = " ".join(cats + [L.name(q) for q in p31[:4] + occ[:6] + pos[:4]] + [desc])
    roots = [CL["cls"][x] for x in p31 if x in CL["cls"]]
    theme = person_theme([L.name(q) for q in occ[:8] + pos[:6]], desc) if kind == "person" else ""
    for th, keys in ([] if theme else T.THEME_RULES):
        if th in T.SPECIFIC and any(k in words for k in keys): theme = th; break
    if not theme:
        for r in roots:
            if T.CLASS_THEME.get(r): theme = T.CLASS_THEME[r]; break
    if not theme and hint.get("th"): theme = hint["th"]
    if not theme:
        for th, keys in T.THEME_RULES:
            if any(k in words for k in keys): theme = th; break
    if not theme:                                                     # 마지막: 제목·첫 문단 낱말로
        w2 = page["title"] + " " + (page.get("lead") or "")[:300]
        for th, keys in T.THEME_RULES:
            if any(k in w2 for k in keys): theme = th; break
    if not theme: theme = {"state": "권력의 밀실", "period": "골목길 미시사", "lore": "믿음과 금기", "person": "권력의 밀실"}.get(kind, "")
    tags = ""
    if kind == "lore" or any(k in words or k in (page.get("lead") or "")[:300] for k in T.BACKSTAGE): tags += "B"
    if any(p in page["title"] for p in T.PRONOUN): tags += "P"
    if rough and y is not None: tags += "~"                            # 연도가 대략적 → 화면에 '~경'
    if len(at_regs) >= 3: tags += "W"                                 # 세 권역 넘게 걸친 사건 → '여러 권역'
    if kind == "concept": theme = theme or "문화와 예술"
    return {"k": kind, "y": y, "y2": y2, "ya": ya, "md": md, "e": T.era_index(ya if ya is not None else y), "r": region, "c": isos[:3], "s": thens[:2], "h": theme, "g": tags,
            "occ": [L.name(q) for q in occ[:4] if L.name(q)], "cls": [L.name(q) for q in p31[:3] if L.name(q)], "desc": desc,
            "korea": bool(set(isos) & T.KOREA_ISO), "roots": [T.CLASS_MEMO.get(r, "") for r in roots[:2]], "roles": roles}


RULES = dict(T.THEME_RULES)
def person_theme(occ_labels, desc=""):
    """사람: 직업·관직 라벨을 정해진 순서로 (정치·군주 > 군사 > 첩보 > 혁명 > 종교 > 과학 > 돈 > 문화)"""
    words = " ".join(occ_labels) + " " + (desc or "")
    if not words.strip(): return ""
    for th in T.PERSON_THEME_ORDER:
        if any(k in words for k in RULES.get(th, ())): return th
    return ""


def retheme_people(st):
    """한 번만: 예전 규칙으로 테마가 붙은 사람 글을 글 파일의 직업·관직으로 다시 매김."""
    if st.seeds.get("retheme") == "v2": return
    n = 0
    for pid, rec in st.pages.items():
        e = rec.get("e")
        if not e or e[8] != "p": continue
        doc = rj(page_path(pid))
        if not doc: continue
        th = person_theme((doc.get("occ") or []) + (doc.get("cls") or []), doc.get("desc", ""))
        if th and th in T.THEMES and T.THEMES.index(th) != e[7]:
            e[7] = T.THEMES.index(th); doc["h"] = th; wj(page_path(pid), doc); n += 1
    st.seeds["retheme"] = "v2"; log(f"사람 테마 다시 매김: {n:,}편")


RECLASS = "reclass7"          # 분류 규칙을 바꾸면 이름을 올림 → 받은 글 전부를 위키데이터로 다시 분류 (본문은 안 받음, 토큰 0)
def reclass(st, C, L, CL, cp):
    """받은 글 전부 다시 분류: 개념 종류 · 대략 연도(~경) · 역할별 나라 · 권역. 끊겨도 다음 회차에 이어서."""
    if st.seeds.get(RECLASS) == "done": return
    pids = sorted(st.pages, key=lambda k: int(k)); pos = int(st.seeds.get(RECLASS) or 0)
    log(f"다시 분류: {pos:,}/{len(pids):,}편부터")
    changed = 0
    while pos < len(pids) and not out_of_time():
        chunk = pids[pos:pos + 50]; docs = {}
        for pid in chunk:
            try: docs[pid] = rj(page_path(pid))
            except Exception: pass
        ents = wd_entities([d.get("qid") for d in docs.values() if d and d.get("qid")])
        if docs and not ents and any(d and d.get("qid") for d in docs.values()):
            log("  위키데이터를 못 받아 다음 회차에 이어서"); break
        where, lab = [], []
        for d in docs.values():
            e = ents.get((d or {}).get("qid") or "", {})
            where += role_places(e, d.get("k")); lab += cv(e, "P31")[:4] + cv(e, "P106")[:6] + cv(e, "P39")[:4]
            for _, p in REL_PROPS: lab += [q for q in cv(e, p)[:10] if isinstance(q, str)]
        C.ensure(where); L.ensure([q for q in lab if isinstance(q, str)])
        for pid, d in docs.items():
            if not d: continue
            e = ents.get(d.get("qid") or "", {})
            if d.get("qid") and not e: continue
            page = {"title": d["title"], "lead": d.get("lead") or "", "cats": [{"title": "분류:" + c} for c in d.get("cats") or []]}
            info = classify(page, e, d.get("k") if d.get("k") != "concept" else "event", C, L, {}, CL)
            new = {"k": info["k"], "y": info["y"], "y2": info["y2"], "ya": info["ya"], "md": info["md"], "e": info["e"], "r": info["r"], "c": info["c"], "s": info["s"],
                   "roles": info["roles"], "h": info["h"], "g": info["g"], "occ": info["occ"], "cls": info["cls"], "desc": info["desc"] or d.get("desc", "")}
            if e: new["rel"] = relations(e, L)
            if all(d.get(k) == v for k, v in new.items()): continue
            d.update(new); wj(page_path(pid), d); changed += 1
            rec = st.pages.get(pid)
            if rec and rec.get("e") and len(rec["e"]) >= 16:
                o = rec["e"]
                rec["e"] = [o[0], o[1], info["y"], info["y2"], info["e"], T.REGION_CODE.get(info["r"], "xx"), info["c"], T.THEMES.index(info["h"]) if info["h"] in T.THEMES else -1,
                            KCODE.get(info["k"], "o"), info["g"], o[10], o[11], o[12], info["md"], o[14], info["ya"]]
        pos += len(chunk); st.seeds[RECLASS] = pos
        if pos % 2000 < 50: log(f"  다시 분류 {pos:,}/{len(pids):,} · 바뀜 {changed:,}"); cp()
    if pos >= len(pids): st.seeds[RECLASS] = "done"; log(f"다시 분류 끝 · 바뀜 {changed:,}편")
    cp(force=True) if GIT_PUSH else cp.save()


def upgrade_lite(st):
    """용량이 남았는데 요약판으로 저장된 글(예전 버그 등) → 유명한 순으로 다시 받을 차례에 (전문으로)."""
    room = BUDGET_MB * 1024 * 1024 * 0.97 - st.bytes_used()
    if room <= 0: return
    lite = sorted([(k, v) for k, v in st.pages.items() if not v.get("full")], key=lambda kv: -((kv[1].get("e") or [0] * 11)[10] or 0))
    n = 0
    for k, v in lite:
        if room <= 0: break
        if v["t"] in st.queue: continue
        e = v.get("e") or [0] * 11
        st.queue[v["t"]] = {"q": None, "n": e[10] or 0, "y": None, "th": "", "kd": "", "s": "upgrade", "p": 900 + (e[10] or 0), "tr": 0}
        room -= 9000; n += 1
    if n: log(f"용량이 남아 요약판 {n:,}편을 전문으로 다시 받을 차례에")


def relations(ent, L):
    out = {}
    for key, p in REL_PROPS:
        items = [[L.name(q), L.ko(q)] for q in cv(ent, p)[:10] if isinstance(q, str) and L.name(q)]
        if items: out[key] = items
    return out


# ═══════════════════ 5. 받기 ═══════════════════
def fetch_batch(titles):
    j = get(API_KO, dict(action="query", format="json", formatversion=2, titles="|".join(titles), redirects=1, prop="revisions|pageprops|categories|pageimages|info",
                         rvprop="ids|content|timestamp", rvslots="main", ppprop="wikibase_item|disambiguation", cllimit="max", clshow="!hidden", piprop="thumbnail", pithumbsize=480, maxlag=5))
    q = j.get("query") or {}
    back = {}
    for n in q.get("normalized", []): back[n["to"]] = n["from"]
    for r in q.get("redirects", []): back[r["to"]] = back.get(r["from"], r["from"])
    return q.get("pages", []), back


def fetch_leads(titles):
    """위키백과가 만든 깨끗한 첫 문단 (틀·각주가 정리된 글자). 20편씩."""
    out = {}
    for i in range(0, len(titles), 20):
        try:
            j = get(API_KO, dict(action="query", format="json", formatversion=2, titles="|".join(titles[i:i + 20]), prop="extracts", exintro=1, explaintext=1, exlimit=20, redirects=1, maxlag=5))
            for p in (j.get("query") or {}).get("pages", []):
                if p.get("extract"): out[p["title"]] = p["extract"].strip()
        except Exception as e: log(f"  첫 문단 실패: {str(e)[:60]}")
    return out


def page_path(pid): return PAGES / str(pid)[:2].rjust(2, "0") / f"k{pid}.json"


def process_batch(batch, st, C, L, CL, budget_left):
    titles = [t for t, _ in batch]; hints = dict(batch)
    try: pages, back = fetch_batch(titles); good(st, "fetch/kowiki")
    except Exception as e:
        bad(st, "fetch/kowiki", e)
        for t in titles:
            if t in st.queue: st.queue[t]["tr"] = st.queue[t].get("tr", 0) + 1
        time.sleep(10); return 0, budget_left
    handled, rows = set(), []
    def done(asked, why=None):
        handled.add(asked)
        if why: st.skip[asked] = (why, today()); STAT["skipped"] += 1
    for p in pages:
        t = p.get("title", ""); asked = back.get(t, t)
        if asked not in hints: asked = t if t in hints else asked
        if p.get("invalid"): done(asked, "잘못된 제목"); continue
        if p.get("missing"): done(asked, "없는 글"); continue
        if p.get("ns") != 0: done(asked, "글 아님"); continue
        if not p.get("revisions"):                                   # 응답이 커서 잘림 → 다음 묶음에서 다시 (3번까지)
            h = st.queue.get(asked)
            if h: h["tr"] = h.get("tr", 0) + 1
            if not h or h["tr"] >= 3: done(asked, "본문 못 받음")
            continue
        pid = str(p["pageid"]); rev = p["revisions"][0]["revid"]; hint = hints.get(asked) or {}
        if pid in st.pages and st.pages[pid]["rev"] == rev and hint.get("s") not in ("update", "upgrade"): done(asked); st.queue.pop(t, None); continue   # 넘겨주기로 이미 받은 글
        if "disambiguation" in (p.get("pageprops") or {}): done(asked, "동음이의"); continue
        wt = p["revisions"][0]["slots"]["main"]["content"]
        if re.match(r"\s*#(REDIRECT|넘겨주기)", wt, re.I): done(asked, "넘겨주기"); continue
        try: code = clean_wikitext(wt); lead_wt, secs, heads, links = split_sections(code)
        except Exception as e: log(f"  다듬기 실패 {t}: {str(e)[:50]}"); done(asked, "다듬기 실패"); continue
        rows.append({"asked": asked, "pid": pid, "title": t, "rev": rev, "ts": p["revisions"][0].get("timestamp", "")[:10], "qid": (p.get("pageprops") or {}).get("wikibase_item"),
                     "cats": p.get("categories", []), "img": (p.get("thumbnail") or {}).get("source"), "lead": lead_wt, "secs": secs, "heads": heads, "links": links, "hint": hint})
    for t in titles:                                                   # 응답에 아예 안 나온 제목 (드묾)
        if t not in handled and not any(r["asked"] == t for r in rows):
            h = st.queue.get(t)
            if h:
                h["tr"] = h.get("tr", 0) + 1
                if h["tr"] >= 3: done(t, "응답 없음")
    ents = wd_entities([r["qid"] for r in rows if r["qid"]])
    keep = []
    for r in rows:
        if r["qid"] and r["qid"] not in ents:                          # 위키데이터를 못 받음 → 저장하지 않고 다음에 다시
            h = st.queue.get(r["asked"])
            if h:
                h["tr"] = h.get("tr", 0) + 1
                if h["tr"] < 5: handled.discard(r["asked"]); continue
        e = ents.get(r["qid"] or "", {})
        kind, why = judge(r, e, r["hint"], CL)
        if not kind: done(r["asked"], why); continue
        r["kind"] = kind; r["ent"] = e; keep.append(r)
    if not keep:
        for t in handled: st.queue.pop(t, None)
        return 0, budget_left
    leads = fetch_leads([r["title"] for r in keep])
    where, lab = [], []
    for r in keep:
        e = r["ent"]
        where += role_places(e, r["kind"])
        lab += cv(e, "P31")[:4] + cv(e, "P106")[:6] + cv(e, "P39")[:4]
        for _, p in REL_PROPS: lab += [q for q in cv(e, p)[:10] if isinstance(q, str)]
    C.ensure([q for q in where if isinstance(q, str)]); L.ensure([q for q in lab if isinstance(q, str)])
    n = full_n = 0
    for r in keep:
        e = r["ent"]; hint = r["hint"]
        lead = leads.get(r["title"]) or r["lead"]
        lead = re.sub(r"\n{2,}", "\n", lead).strip()
        if len(lead) < 40 and not r["secs"]: done(r["asked"], "너무 짧음"); continue
        r["lead"] = lead
        info = classify(r, e, r["kind"], C, L, hint, CL)
        nlinks = len(e.get("sitelinks") or {}) or hint.get("n") or 0
        en = ((e.get("sitelinks") or {}).get("enwiki") or {}).get("title")
        pid = r["pid"]; old = st.pages.get(pid) or {}
        full = budget_left > 0 or (old.get("full", False) and hint.get("s") != "upgrade")
        secs, cut = cap_sections(lead, r["secs"], FULL_CHARS) if full else ([], bool(r["secs"]))
        one = first_sentence(lead)
        doc = {"id": "k" + pid, "qid": r["qid"], "title": r["title"], "en": en, "desc": info["desc"], "k": info["k"], "y": info["y"], "y2": info["y2"], "ya": info["ya"], "md": info["md"],
               "e": info["e"], "r": info["r"], "c": info["c"], "s": info["s"], "roles": info["roles"], "h": info["h"], "g": info["g"], "n": nlinks, "img": r["img"], "one": one, "lead": lead[:4000],
               "secs": secs, "heads": r["heads"], "full": full, "cut": cut, "links": r["links"], "rel": relations(e, L), "occ": info["occ"], "cls": info["cls"],
               "cats": [c["title"].split(":", 1)[-1] for c in r["cats"]][:10],
               "src": {"site": "ko.wikipedia.org", "title": r["title"], "url": "https://ko.wikipedia.org/wiki/" + quote(r["title"].replace(" ", "_")), "rev": r["rev"], "edited": r["ts"], "license": "CC BY-SA 4.0"}, "at": today()}
        path = page_path(pid); wj(path, doc); size = path.stat().st_size
        if full: budget_left -= size; full_n += 1
        entry = [doc["id"], r["title"], info["y"], info["y2"], info["e"], T.REGION_CODE.get(info["r"], "xx"), info["c"], T.THEMES.index(info["h"]) if info["h"] in T.THEMES else -1,
                 KCODE.get(info["k"], "o"), info["g"], nlinks, old.get("v", 0), 1 if r["img"] else 0, info["md"], one[:110] if (nlinks >= 12 or info["g"] or info["korea"]) else "", info["ya"]]
        if old.get("t") and old["t"] != r["title"]: st.by_title.pop(old["t"], None)
        st.pages[pid] = {"t": r["title"], "rev": r["rev"], "at": old.get("at") or today(), "chk": today(), "v": old.get("v", 0), "full": full, "b": size, "e": entry}
        st.by_title[r["title"]] = pid
        if hint.get("s") == "update": STAT["updated"] += 1
        done(r["asked"]); n += 1
        base = T.priority(nlinks, info["ya"], info["korea"], info["k"])
        for lst in doc["rel"].values():                                # 눈덩이: 관계된 사건·인물도 받을 차례에 (부모보다 조금 낮게)
            for name, ko in lst:
                if ko and not st.known(ko): st.enqueue(ko, n=max(1, nlinks - 10), s="rel", p=max(1, base - 12))
    for t in handled: st.queue.pop(t, None)
    STAT["pages"] += n; STAT["full"] += full_n; STAT["lite"] += n - full_n
    return n, budget_left


def harvest(st, C, L, CL, limit, checkpoint):
    order = sorted(st.queue.items(), key=lambda kv: (-(kv[1].get("p") or 0), kv[0]))
    budget_left = BUDGET_MB * 1024 * 1024 - st.bytes_used()
    if budget_left <= 0: log(f"용량 한도({BUDGET_MB:.0f}MB) 도달 → 새 글은 요약판으로 저장")
    got = 0; batch = []; t_last = time.time(); n_last = 0; total = min(limit, len(order))
    for title, hint in order:
        if got >= limit or out_of_time(): break
        if title not in st.queue: continue
        batch.append((title, hint))
        if len(batch) < (20 if hint.get("tr") else 50): continue
        n, budget_left = process_batch(batch, st, C, L, CL, budget_left); got += n; batch = []
        if got - n_last >= 500 or time.time() - t_last > 300:
            el = time.time() - T0; rate = got / max(1, el - 0) * 60
            log(f"  받음 {got:,}편 / 차례 남음 {len(st.queue):,} · 분당 {rate:.0f}편 · 남은 용량 {max(0, budget_left) / 1048576:.0f}MB · 호출 {STAT['calls']:,} · 429 {STAT['r429']}")
            t_last = time.time(); n_last = got
        checkpoint()
    if batch and got < limit and not out_of_time():
        n, budget_left = process_batch(batch, st, C, L, CL, budget_left); got += n
    return got


# ═══════════════════ 6. 갱신·조회수·역사 속 오늘 ═══════════════════
def recheck(st):
    items = sorted(st.pages.items(), key=lambda kv: kv[1].get("chk", ""))[:RECHECK]
    items = [kv for kv in items if kv[1].get("chk") != today()]
    if not items: return
    changed = removed = 0
    for i in range(0, len(items), 50):
        if out_of_time(): break
        chunk = items[i:i + 50]
        try: j = get(API_KO, dict(action="query", format="json", formatversion=2, pageids="|".join(k for k, _ in chunk), prop="info", maxlag=5)); good(st, "recheck")
        except Exception as e: bad(st, "recheck", e); break
        for p in (j.get("query") or {}).get("pages", []):
            k = str(p.get("pageid")); rec = st.pages.get(k)
            if not rec: continue
            rec["chk"] = today()
            if p.get("missing") or p.get("ns", 0) != 0:
                st.by_title.pop(rec["t"], None); st.pages.pop(k, None); removed += 1
                try: page_path(k).unlink()
                except Exception: pass
                continue
            if p.get("title") and p["title"] != rec["t"]:                 # 제목이 바뀜(옮겨짐)
                st.by_title.pop(rec["t"], None); rec["t"] = p["title"]; st.by_title[p["title"]] = k
            if p.get("lastrevid") and p["lastrevid"] != rec.get("rev"):
                e = rec.get("e") or []
                st.queue[rec["t"]] = {"q": None, "n": e[10] if len(e) > 10 else 0, "y": None, "th": "", "kd": "", "s": "update", "p": 1000 + (e[10] if len(e) > 10 else 0), "tr": 0}; changed += 1
    STAT["removed"] += removed
    log(f"고쳐졌나 확인 {len(items):,}편 → 고쳐진 글 {changed:,} · 지워진 글 {removed}")


def pageviews(st):
    if VIEWS_BUDGET <= 0: return
    cand = sorted([(k, v) for k, v in st.pages.items() if not v.get("v")], key=lambda kv: -((kv[1].get("e") or [0] * 11)[10] or 0))[:VIEWS_BUDGET]
    end = datetime.now(timezone.utc) - timedelta(days=3); start = (end - timedelta(days=180)).replace(day=1)
    n = 0
    for k, rec in cand:
        if out_of_time(): break
        t = quote(rec["t"].replace(" ", "_"), safe="")
        url = f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/ko.wikipedia/all-access/user/{t}/monthly/{start:%Y%m%d}00/{end:%Y%m%d}00"
        try:
            STAT["calls"] += 1; r = S.get(url, timeout=30)
            if r.status_code == 404: v = 1
            elif r.status_code == 429: time.sleep(min(60, _int(r.headers.get("Retry-After"), 10))); continue
            else: r.raise_for_status(); v = sum(it.get("views", 0) for it in r.json().get("items", [])) or 1
            rec["v"] = v
            if rec.get("e") and len(rec["e"]) > 11: rec["e"][11] = v
            n += 1; good(st, "views")
        except Exception as e:
            bad(st, "views", e)
            if st.health.get("views", {}).get("n", 0) > 30: break
        time.sleep(0.08)
    log(f"조회수 {n:,}편")


def days_of_year(st):
    """'M월 D일' 문서의 '사건' 단락 → _state/days_raw.json. 7일에 한 번."""
    if not seed_due(st, "days", 7) or QUICK: return rj(ST / "days_raw.json", {})
    titles = [f"{m}월 {d}일" for m in range(1, 13) for d in range(1, 32) if not (m == 2 and d > 29) and not (m in (4, 6, 9, 11) and d > 30)]
    days = {}
    try:
        for i in range(0, len(titles), 25):
            if out_of_time(): return rj(ST / "days_raw.json", {})
            pages, _ = fetch_batch(titles[i:i + 25])
            for p in pages:
                if not p.get("revisions"): continue
                m = re.match(r"(\d+)월 (\d+)일", p["title"]); key = f"{int(m.group(1)):02d}-{int(m.group(2)):02d}"
                code = mw.parse(RX_REF.sub(" ", p["revisions"][0]["slots"]["main"]["content"])); rows = []; inside = False
                for sec in code.get_sections(include_lead=False, flat=True, include_headings=True):
                    hs = sec.filter_headings()
                    if not hs: continue
                    if int(hs[0].level) <= 2: inside = plain(hs[0].title).replace(" ", "") in ("사건", "사건·사고", "역사")
                    if not inside: continue
                    for line in str(sec).split("\n"):
                        if not line.startswith("*"): continue
                        ln = expand(mw.parse(line.lstrip("*: ").strip())); links = []; _links(ln, links); txt = plain(ln)
                        mm = re.match(r"(기원전\s*)?(\d{1,4})년\s*[-–—:：]?\s*(.*)", txt)
                        if not mm or len(mm.group(3)) < 4: continue
                        rows.append({"y": -int(mm.group(2)) if mm.group(1) else int(mm.group(2)), "t": mm.group(3).strip()[:180], "l": dedupe(links)[:5]})
                days[key] = rows
        wj(ST / "days_raw.json", days); st.seeds["days"] = now_iso(); good(st, "days")
        log(f"역사 속 오늘: {len(days)}일치")
    except Exception as e: bad(st, "days", e); return rj(ST / "days_raw.json", {})
    return days


# ═══════════════════ 7. 색인 (화면용 조각들) ═══════════════════
CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"; CHO_MERGE = {"ㄲ": "ㄱ", "ㄸ": "ㄷ", "ㅃ": "ㅂ", "ㅆ": "ㅅ", "ㅉ": "ㅈ"}
def sbucket(title):
    ch = (title or "?")[0]
    if "가" <= ch <= "힣": c = CHO[(ord(ch) - 0xAC00) // 588]; return "h" + str("ㄱㄴㄷㄹㅁㅂㅅㅇㅈㅊㅋㅌㅍㅎ".index(CHO_MERGE.get(c, c)))
    if ch.isascii() and ch.isalpha(): return "a" + ch.lower()
    if ch.isdigit(): return "d"
    return "x"
def dbucket(y):
    if y is None: return None
    if y >= 1500: return str(y // 10 * 10)
    if y >= 0: return str(y // 50 * 50)
    return str(-((-y + 99) // 100) * 100)                                  # 기원전은 100년 단위
def score(e): return (e[10] or 0) + 12 * math.log10(1 + (e[11] or 0)) + (8 if e[15] is not None and 1750 <= (e[15] or 0) <= 1991 else 0) + (12 if set(e[6] or []) & T.KOREA_ISO else 0)


def build_index(st, C, days_raw):
    ents = [v["e"] for v in st.pages.values() if v.get("e") and len(v["e"]) >= 16]
    log(f"색인 만드는 중… {len(ents):,}편")
    for d in ("idx", "cty", "dec", "th", "s", "days", "tag"):
        p = OUT / d
        if p.exists(): shutil.rmtree(p)
    for old in ("days.json", "_queue.json", "_seen.json", "_countries.json", "_classes.json", "_health.json", "_seeds_done.json"):
        try: (OUT / old).unlink()
        except Exception: pass
    sc = {e[0]: score(e) for e in ents}
    slim = lambda e: e[:14] + ["", e[15]]                               # 목록용 (한 줄 요약은 비움 — 칸 위치는 같게)
    withone = lambda e: e[:16]
    groups = {}
    for e in ents: groups.setdefault(f"{e[5]}-{e[4] if e[4] >= 0 else 'n'}", []).append(e)
    shards = {}
    for k, lst in groups.items():
        lst.sort(key=lambda e: -sc[e[0]]); wj(OUT / "idx" / f"{k}.json", [slim(e) for e in lst]); shards[k] = len(lst)
    ctys = {}
    for e in ents:
        for c in (e[6] or [])[:2]: ctys.setdefault(c, []).append(e)
    for c, lst in ctys.items():
        lst.sort(key=lambda e: (e[15] if e[15] is not None else 99999, -sc[e[0]])); wj(OUT / "cty" / f"{c}.json", [slim(e) for e in lst])
    decs = {}
    for e in ents:
        b = dbucket(e[15] if e[15] is not None else e[2])
        if b is not None: decs.setdefault(b, []).append(e)
    for b, lst in decs.items():
        lst.sort(key=lambda e: -sc[e[0]]); wj(OUT / "dec" / f"{b}.json", [withone(e) for e in lst[:500]])
    for i, th in enumerate(T.THEMES):
        lst = sorted([e for e in ents if e[7] == i], key=lambda e: -sc[e[0]]); wj(OUT / "th" / f"{i}.json", [withone(e) for e in lst[:2000]])
    for tg in ("B", "P"):
        lst = sorted([e for e in ents if tg in (e[9] or "")], key=lambda e: -sc[e[0]]); wj(OUT / "tag" / f"{tg}.json", [withone(e) for e in lst[:3000]])
    sb = {}
    for e in ents: sb.setdefault(sbucket(e[1]), []).append([e[1], e[0], e[2], e[8], e[5]])
    for b, lst in sb.items(): lst.sort(key=lambda x: x[0]); wj(OUT / "s" / f"{b}.json", lst)
    by_title = {e[1]: e[0] for e in ents}
    # 역사 속 오늘: 위키백과 날짜 문서 + 우리 글 중 날짜가 정확한 사건
    own = {}
    for e in ents:
        if e[13] and e[8] == "e": own.setdefault(e[13], []).append(e)
    for key in sorted(set(days_raw) | set(own)):
        rows = []
        for r in days_raw.get(key, []):
            rows.append({"y": r["y"], "t": r["t"], "id": next((by_title[l] for l in r.get("l", []) if l in by_title), None)})
        have = {r["id"] for r in rows if r["id"]}
        for e in sorted(own.get(key, []), key=lambda e: -sc[e[0]])[:30]:
            if e[0] not in have: rows.append({"y": e[2], "t": e[1], "id": e[0], "own": 1})
        rows.sort(key=lambda r: (r["y"] if r["y"] is not None else 0))
        wj(OUT / "days" / f"{key}.json", rows)
    allsorted = sorted(ents, key=lambda e: -sc[e[0]])
    recent = sorted(st.pages.values(), key=lambda v: v.get("at", ""), reverse=True)[:80]
    top = {"all": [withone(e) for e in allsorted[:400]], "region": {}, "back": [withone(e) for e in allsorted if "B" in (e[9] or "")][:100],
           "pron": [withone(e) for e in allsorted if "P" in (e[9] or "")][:200], "recent": [withone(v["e"]) for v in recent if v.get("e")],
           "korea": [withone(e) for e in allsorted if set(e[6] or []) & T.KOREA_ISO][:150]}
    for e in allsorted:
        lst = top["region"].setdefault(e[5], [])
        if len(lst) < 40: lst.append(withone(e))
    wj(OUT / "top.json", top)
    counts = {"total": len(ents), "full": sum(1 for v in st.pages.values() if v.get("full")), "region": {}, "era": {}, "theme": {}, "kind": {}, "tag": {"B": 0, "P": 0}, "country": {c: len(l) for c, l in ctys.items()}}
    for e in ents:
        counts["region"][e[5]] = counts["region"].get(e[5], 0) + 1; counts["era"][str(e[4])] = counts["era"].get(str(e[4]), 0) + 1
        counts["theme"][str(e[7])] = counts["theme"].get(str(e[7]), 0) + 1; counts["kind"][e[8]] = counts["kind"].get(e[8], 0) + 1
        for tg in (e[9] or ""): counts["tag"][tg] = counts["tag"].get(tg, 0) + 1
    names = {**C.iso_names(), **T.COUNTRY_KO}
    broken = {k: v for k, v in st.health.items() if v.get("n", 0) >= 3}
    used = st.bytes_used()
    wj(OUT / "_index.json", {"ver": 2, "at": now_iso(), "counts": counts, "shards": shards, "decades": sorted(decs, key=int), "searchBuckets": sorted(sb),
                             "regions": [[T.REGION_CODE[r], r] for r in T.REGIONS] + [["xx", "기타"]], "themes": T.THEMES, "eras": [n for _, n, _ in T.ERAS], "eraShort": [s for _, _, s in T.ERAS],
                             "countryKo": {c: names.get(c, c) for c in ctys}, "queue": len(st.queue), "skipped": len(st.skip), "broken": broken,
                             "budget": {"usedMB": round(used / 1048576, 1), "limitMB": BUDGET_MB}, "stat": STAT,
                             "cols": "id,title,y,y2,era,region,countries,theme,kind,tags,langs,views,img,md,one,ya", "license": "본문: 한국어 위키백과 (CC BY-SA 4.0) · 속성: 위키데이터 (CC0)"})
    wj(OUT / "_meta.json", {"updatedAt": now_iso(), "by": "history-robot", "label": f"{len(ents):,}편" + (f" · 받는 중 {len(st.queue):,}" if len(st.queue) >= 200 else "")})
    log(f"색인 끝: {len(ents):,}편 · 권역×시대 {len(shards)}조각 · 나라 {len(ctys)} · 연대 {len(decs)} · 글 용량 {used / 1048576:.0f}MB")


# ═══════════════════ 8. 중간 저장·올리기 ═══════════════════
class Checkpoint:
    def __init__(self, st, C, L): self.st, self.C, self.L = st, C, L; self.last = time.time(); self.last_save = time.time()
    def save(self): self.C.save(); self.L.save(); self.st.save()
    def __call__(self, force=False):
        if time.time() - self.last_save > 300 or force: self.save(); self.last_save = time.time()
        if GIT_PUSH and PUSH_EVERY > 0 and (time.time() - self.last > PUSH_EVERY * 60 or force):
            self.save(); build_index(self.st, self.C, rj(ST / "days_raw.json", {})); git_push(f"역사: 중간 저장 {len(self.st.pages):,}편 (대기 {len(self.st.queue):,})"); self.last = time.time()


def git_push(msg):
    try:
        subprocess.run(["git", "add", "-A", "data/history"], cwd=ROOT, check=True)
        if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode == 0: return
        subprocess.run(["git", "commit", "-q", "-m", msg], cwd=ROOT, check=True)
        for i in range(5):
            if subprocess.run(["git", "pull", "--rebase", "-q", "-X", "theirs"], cwd=ROOT).returncode == 0 and subprocess.run(["git", "push", "-q"], cwd=ROOT).returncode == 0:
                log(f"저장소에 올림: {msg}"); return
            time.sleep(15 * (i + 1))
        log("올리기 실패 (다음에 다시)")
    except Exception as e: log(f"올리기 오류: {e}")


# ═══════════════════ 본체 ═══════════════════
def main():
    if mw is None: print("mwparserfromhell 이 필요해요: pip install mwparserfromhell"); sys.exit(1)
    OUT.mkdir(parents=True, exist_ok=True); ST.mkdir(parents=True, exist_ok=True); PAGES.mkdir(exist_ok=True)
    st = State(); C, L = Countries(), Labels()
    log(f"시작: 받은 글 {len(st.pages):,} · 받을 차례 {len(st.queue):,} · 뺀 글 {len(st.skip):,} · 글 용량 {st.bytes_used() / 1048576:.0f}/{BUDGET_MB:.0f}MB · 한도 {MAX_PAGES:,}편/{MAX_MIN:.0f}분")
    memos = {"class:" + m for _, m, _, _, _ in T.SEED_CLASSES}            # 표에서 뺀 종류로 들어온 받을 차례는 버림
    gone = [t for t, h in st.queue.items() if h.get("s", "").startswith("class:") and h["s"] not in memos]
    for t in gone: st.queue.pop(t, None)
    if gone: log(f"표에서 뺀 종류의 받을 차례 {len(gone):,}편 버림")
    cp = Checkpoint(st, C, L)
    retheme_people(st)
    upgrade_lite(st)
    if INDEX_ONLY: build_index(st, C, rj(ST / "days_raw.json", {})); return
    try:
        CL = closure(st)
        reclass(st, C, L, CL, cp)
        if not NO_SEEDS:
            seed_classes(st); cp(); seed_people(st); cp(); seed_vital(st); cp(); seed_cats(st); cp(); seed_people_cats(st); cp()
            log(f"종자 끝: 받을 차례 {len(st.queue):,} (새로 {STAT['seeds']:,})")
        if SEEDS_ONLY: return
        if st.pages: recheck(st)
        n = harvest(st, C, L, CL, MAX_PAGES, cp)
        log(f"받기 끝: {n:,}편 (전문 {STAT['full']:,} · 요약판 {STAT['lite']:,} · 뺀 글 {STAT['skipped']:,})")
    finally:
        cp.save()
    global DEADLINE
    if not STOP: DEADLINE = time.time() + 15 * 60                         # 마무리(역사 속 오늘·조회수·색인)에 15분
    days = days_of_year(st)
    pageviews(st)
    cp.save()
    build_index(st, C, days)
    wj(ST / "run.json", {"at": now_iso(), "minutes": round((time.time() - T0) / 60), "stat": STAT, "queue": len(st.queue), "pages": len(st.pages)})
    log(f"끝 {round((time.time() - T0) / 60)}분 · 호출 {STAT['calls']:,} · 글 {len(st.pages):,} · 받을 차례 {len(st.queue):,} · 오류 {STAT['err']} · 429 {STAT['r429']}")
    if os.environ.get("GITHUB_OUTPUT"):
        # 다음 회차는 '받을 게 아직 많을 때'만 (꼬리에 붙는 몇 편은 매일 새벽 회차가 처리)
        progress = 1 if st.seeds.get(RECLASS) != "done" else 1 if (len(st.queue) >= 200 and (STAT["pages"] >= 200 or STAT["seeds"] >= 200 or STAT["updated"] >= 200)) else 0
        with open(os.environ["GITHUB_OUTPUT"], "a") as f: f.write(f"queue={len(st.queue)}\nharvested={STAT['pages']}\npages={len(st.pages)}\nprogress={progress}\n")


if __name__ == "__main__":
    main()
