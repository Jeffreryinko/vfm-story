"""book_run.py — 책 탭 로봇 (토큰 0).

대학·기관 권장도서 목록을 모으고(교보 추천 목록 · 대학 도서관 · 손 정리 목록), 같은 책끼리 묶은 뒤
표지·소개·목차·전자책·분류를 붙여 data/book/ 에 저장합니다.

  python robot/book_run.py                 # 평소 (목록은 7일에 한 번 새로, 빈 정보는 매번 조금씩 채움)
  python robot/book_run.py --lists         # 목록 지금 새로 받기
  python robot/book_run.py --max-minutes 40

열쇠(GitHub 비밀 설정, 없으면 그 부분만 건너뜀):
  KAKAO_REST_KEY  카카오 책 검색 — ISBN 찾기·표지·소개
  YES24_API_KEY   YES24 Open API — 목차·큰 표지·쪽수·원제·전자책
  NLK_API_KEY     국립중앙도서관 — 십진분류·목차 파일·사서추천 30년치
"""
from __future__ import annotations

import argparse
import hashlib
import html as H
import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import book_sources as SRC  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data/book"
ST = OUT / "_state"
KST = timezone(timedelta(hours=9))
UA = "vfm-story-book-robot/1.0 (+https://jeffreryinko.github.io/vfm-story/)"
S = requests.Session()
S.headers["User-Agent"] = UA
KAKAO = os.environ.get("KAKAO_REST_KEY", "").strip()
YES24 = os.environ.get("YES24_API_KEY", "").strip()
NLK = os.environ.get("NLK_API_KEY", "").strip()
T0 = time.time()
MAX_MIN = float(os.environ.get("BOOK_MAX_MINUTES", "40"))
HEALTH: dict = {}
CALLS = {"kakao": 0, "yes24": 0, "nlk": 0, "wd": 0, "src": 0}
DOWN = set()          # 이번 실행에서 막힌 곳 (한도·고장) → 더 부르지 않고, '없음'으로 기록하지도 않음


def now():
    return datetime.now(KST)


def left():
    return MAX_MIN * 60 - (time.time() - T0)


def log(*a):
    print(*a, flush=True)


def jload(p: Path, d=None):
    try:
        return json.loads(p.read_text("utf-8"))
    except Exception:
        return d


def jsave(p: Path, obj, compact=True):
    p.parent.mkdir(parents=True, exist_ok=True)
    s = json.dumps(obj, ensure_ascii=False, separators=(",", ":") if compact else None, indent=None if compact else 1, sort_keys=not compact)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(s, "utf-8")
    tmp.replace(p)


def get(url, *, params=None, headers=None, kind="src", tries=3, timeout=25, as_json=True):
    for i in range(tries):
        try:
            CALLS[kind] = CALLS.get(kind, 0) + 1
            r = S.get(url, params=params, headers=headers, timeout=timeout)
            if r.status_code in (429, 502, 503, 504):
                time.sleep(3 * (i + 1)); continue
            if r.status_code == 404:
                return {"__404": 1} if as_json else ""
            r.raise_for_status()
            return r.json() if as_json else r.text
        except Exception as e:  # noqa: BLE001
            if i == tries - 1:
                log("  ! 실패", url[:90], type(e).__name__, str(e)[:120])
                return None
            time.sleep(2 * (i + 1))
    return None


# ───────────────────────── 글자 다듬기 ─────────────────────────
def clean(s):
    s = H.unescape(str(s or ""))
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def norm_title(t: str) -> str:
    t = unicodedata.normalize("NFKC", clean(t))
    t = re.sub(r"^\s*[\(\[][^)\]]{1,40}[\)\]]\s*", "", t)          # 앞 괄호 "(세계사를 바꾼)"
    t = re.split(r"\s*[:;=]\s*|\s+/\s*|\s-\s|\s—\s", t)[0]            # 부제·책임 표시
    t = re.sub(r"\[[^\]]*\]", "", t)
    t = re.sub(r"\((?:전\s*)?\d+\s*권?.*?\)|\(\s*\d+\s*,\s*\d+\s*권\s*\)|\((?:상|하|상\s*,\s*하)\)", "", t)
    t = re.sub(r"\s*(세트|SET|합본|완역본|완역판|개정판|개정증보판|양장|특별판|리커버|에디션)\s*$", "", t, flags=re.I)
    t = re.sub(r"(?<=\D)\s+(?:제?\s*\d{1,2}\s*권?|[1-9]\s*[,·~-]\s*[1-9]|[상중하])\s*$", "", t)        # 파우스트 1 → 파우스트
    return re.sub(r"[\s\W_]+", "", t).lower()


def disp_title(t: str) -> str:
    t = clean(t)
    t = re.sub(r"\s*(세트|SET|합본)\s*$", "", t, flags=re.I)
    t = re.sub(r"(?<=\D)\s+(?:제?\s*\d{1,2}\s*권?|[1-9]\s*[,·~-]\s*[1-9]|\([상하]\)|[상중하])\s*$", "", t)
    t = re.sub(r"\s*\((?:\d+\s*,\s*\d+\s*권|전\s*\d+\s*권)\)", "", t)
    return t.strip() or clean(t)


def first_author(a: str) -> str:
    a = clean(a)
    a = re.split(r"\s*(?:[,;·/|]|\s외\b| 외\d|\s&\s| and )\s*", a)[0] if a else ""
    a = re.sub(r"\s*\((?:지은이|글|저|옮긴이|역|편|엮음|원작)\)|\s*(지음|저|글|편저|엮음|옮김|역|원작|외)$", "", a).strip()
    return a


def author_key(a: str) -> str:
    a = first_author(a)
    if not a:
        return ""
    if re.search(r"[A-Za-z]", a) and not re.search(r"[가-힣]", a):
        a = a.split(",")[0] if "," in a else a.split()[-1]          # Kuhn, Thomas → kuhn / Thomas Kuhn → kuhn
        return re.sub(r"\W", "", a).lower()
    parts = re.sub(r"[^\w\s가-힣]", " ", a).split()
    return parts[-1] if parts else ""                                 # 토머스 쿤 → 쿤, 박경리 → 박경리


def same_author(a: str, b: str) -> bool:
    ka, kb = author_key(a), author_key(b)
    if not ka or not kb:
        return True
    if re.search(r"[a-z]", ka) != re.search(r"[a-z]", kb):           # 한글 이름 vs 영문 이름 → 비교 못 함
        return True
    if ka == kb or ka in kb or kb in ka:
        return True
    return bool(set(ka) & set(kb)) and len(ka) >= 3 and len(kb) >= 3 and len(set(ka) & set(kb)) >= 2


def wid(key: str) -> str:
    return "b" + hashlib.md5(key.encode("utf-8")).hexdigest()[:9]


def isbn13(s) -> str:
    for m in re.findall(r"97[89]\d{10}", str(s or "")):
        return m
    return ""


# ───────────────────────── 1. 목록 모으기 ─────────────────────────
def entry(src, title, author="", isbn="", pub="", year="", label="", field="", nation="", callno="", cat="", cover=""):
    return {"src": src, "t": clean(title), "a": clean(author), "isbn": isbn13(isbn), "pub": clean(pub), "y": str(year or "")[:4],
            "lb": clean(label), "f": field, "n": nation, "cn": clean(callno), "cat": clean(cat), "cv": cover}


def from_kyobo(menu, sid):
    meta = get("https://store.kyobobook.co.kr/api/gw/store/recommend/category", params={"dsplMenuNum": menu})
    cats = ((meta or {}).get("data") or {}).get("detailCategory") or [] if isinstance((meta or {}).get("data"), dict) else []
    if not cats:
        raise RuntimeError("교보 분류 정보 없음")
    out = []
    for c in cats:
        page = 1
        while True:
            d = get("https://store.kyobobook.co.kr/api/gw/store/recommend/category/books",
                    params={"rcmnDvsnCode": c["rcmnDvsnCode"], "rcmnFldCode": c["rcmnFldCode"], "page": page, "per": 100})
            b = (d or {}).get("data") or {}
            rows = b.get("rcmnBook") or []
            for x in rows:
                if (x.get("saleLmttAge") or 0) >= 19:
                    continue
                out.append(entry(sid, x.get("cmdtName"), x.get("chrcName"), x.get("cmdtCode"), x.get("pbcmName"),
                                 (x.get("rlseDate") or "")[:4], re.sub(r"년$", "", x.get("rcmnSlcnYr") or ""),
                                 cat=(x.get("saleCmdtClstName") or "") + (" " + c.get("rcmnFldName", "") if len(cats) > 1 else "")))
            if not rows or page * 100 >= (b.get("total") or 0) or page >= 40:
                break
            if left() < MAX_MIN * 60 * 0.35:
                raise TimeoutError("시간 부족 — 다음 실행에 처음부터")
            page += 1
            time.sleep(0.3)
    return out


def from_pyxis(host, root, sid):
    def node(i):
        d = get(f"https://{host}/pyxis-api/1/special-collections/{i}", params={"showDepth": 1})
        return (d or {}).get("data")
    top = node(root)
    if not top:
        raise RuntimeError("컬렉션 없음")
    kids = [(k["id"], k.get("name") or "") for k in (top.get("c8n") or [])] or [(root, "")]
    out = []
    for kid, name in kids:
        off = 0
        while True:
            d = get(f"https://{host}/pyxis-api/1/collections/1/search",
                    params={"sc": kid, "facet": "false", "fuzzy": "false", "max": 100, "offset": off, "isForPyxis3": "true"})
            x = (d or {}).get("data") or {}
            rows = x.get("list") or []
            for r in rows:
                pub = r.get("publication") or ""
                yr = (re.findall(r"(1[5-9]\d\d|20\d\d)", pub) or [""])[-1]
                cn = ""
                for bv in r.get("branchVolumes") or []:
                    if bv.get("volume"):
                        cn = bv["volume"]; break
                lab = name if re.fullmatch(r"\d{4}", name or "") or 1 < len(kids) <= 30 else ""
                out.append(entry(sid, r.get("titleStatement"), r.get("author"), r.get("isbn"), re.sub(r",?\s*\d{4}\.?$", "", pub.split(":")[-1]),
                                 yr, lab, callno=cn, cover=r.get("thumbnailUrl") or ""))
            off += len(rows)
            if not rows or off >= (x.get("totalCount") or 0) or off > 2000:
                break
            time.sleep(0.3)
        time.sleep(0.2)
    return out


def from_postech():
    sid, url, _, _ = SRC.POSTECH
    s = get(url, as_json=False)
    if not s:
        raise RuntimeError("페이지 못 읽음")
    out = []
    for m in re.finditer(r'<a class="book-item"(.*?)</a>', s, re.S):
        blk = m.group(1)
        t = re.search(r"<h5>(.*?)</h5>", blk, re.S)
        if not t:
            continue
        au = re.search(r'item-author">(.*?)</div>', blk, re.S)
        img = re.search(r'<img src="([^"]+)"', blk)
        out.append(entry(sid, t.group(1), au.group(1) if au else "", cover=H.unescape(img.group(1)) if img else ""))
    if len(out) < 50:
        raise RuntimeError(f"너무 적음 {len(out)}")
    return out


def from_tsv(sid, fname):
    out = []
    for line in (ROOT / "robot/book_lists" / fname).read_text("utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        c = line.split("\t") + ["", "", "", ""]
        g, t, a, y = c[0], c[1], c[2], c[3]
        out.append(entry(sid, t, a, year=y, label=g, field=SRC.GROUP_FIELD.get(g, ""), nation=SRC.GROUP_NATION.get(g, "")))
        if any(w[0] == sid for w in SRC.WAYBACK):
            out.append(entry(sid, t, a, year=y, label=str(now().year), field=SRC.GROUP_FIELD.get(g, ""), nation=SRC.GROUP_NATION.get(g, "")))
    return out


def from_nlk_saseo():
    """국립중앙도서관 사서추천도서 — 열쇠가 있을 때만. 2006년부터 다달이."""
    out, page = [], 1
    while page < 80:
        s = get("https://nl.go.kr/NL/search/openApi/saseoApi.do", params={"key": NLK, "startRowNumApi": (page - 1) * 100 + 1,
                "endRowNumApi": page * 100, "start_date": "19960101", "end_date": now().strftime("%Y%m%d")}, kind="nlk", as_json=False)
        if not s or "<item>" not in s:
            break
        for it in re.findall(r"<item>(.*?)</item>", s, re.S):
            tags = {k.lower(): clean(v) for k, v in re.findall(r"<(\w+)>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</\1>", it, re.S)}
            yr = next((m for k, v in tags.items() if re.search(r"year|date|ym", k) for m in re.findall(r"(?:19|20)\d\d", v)), "")
            out.append(entry("nlk2", tags.get("recomtitle"), tags.get("recomauthor"), tags.get("recomisbn"), tags.get("recompublisher"),
                             tags.get("publishyear", "")[:4], yr, cat=tags.get("drcodename", "")))
        page += 1
        time.sleep(0.3)
    return out


def from_wayback(sid, urls, shape, groups=None):
    """웨이백 머신에 남은 옛 페이지 → 연도별 목록.
    · 그해 저장이 안 된 하위 페이지는 '그 전 마지막 모습'으로 채움 (일부만 저장된 해가 '빠진 책'으로 잘못 보이지 않게)
    · 옛 페이지 제목 표기가 손 목록과 조금 달라도(켄터베리/캔터베리) 같은 책으로 맞춤"""
    import difflib
    tsv = next((t for t in SRC.TSV if t[0] == sid), None)
    cur = from_tsv(sid, tsv[1]) if tsv else []
    cur = [e for e in cur if not re.fullmatch(r"\d{4}", e.get("lb") or "")]
    keys = [(norm_title(e["t"]) + author_key(e["a"]), e) for e in cur]

    def canon(t, a, g=None):
        pool = [e for e in cur if not g or e.get("lb") == g] or cur
        nt = norm_title(t)
        for e in pool:
            if norm_title(e["t"]) == nt:
                return e
        best = max(pool, key=lambda e: difflib.SequenceMatcher(None, norm_title(e["t"]), nt).ratio(), default=None)
        if best and difflib.SequenceMatcher(None, norm_title(best["t"]), nt).ratio() >= (0.5 if g else 0.7):
            return best
        return None
    snaps = {}                                                        # 주소 → {연도: [(제목, 지은이)]}
    for u in urls:
        cdx = get("https://web.archive.org/cdx/search/cdx", params={"url": u, "output": "json", "collapse": "timestamp:4", "fl": "timestamp,statuscode", "limit": 60}, timeout=60)
        if cdx is None or isinstance(cdx, dict):
            continue
        for ts, code in cdx[1:]:
            if code != "200":
                continue
            page = get(f"https://web.archive.org/web/{ts}id_/http://{u}", as_json=False, timeout=60, tries=2)
            time.sleep(1.0)
            items = []
            if page and shape == "slash":
                for m in re.findall(r">([^<>]{2,80}) / ([^<>]{1,40})<", page):
                    t, a = H.unescape(m[0]).strip(), H.unescape(m[1]).strip()
                    if "분야" not in t:
                        items.append((t, "" if a == "-" else a))
            if items:
                snaps.setdefault(u, {})[ts[:4]] = items
    years = sorted({y for d in snaps.values() for y in d})
    out, report = [], []
    this_year = str(now().year)
    for y in years:
        if y >= this_year:
            continue
        n = 0
        for u in urls:
            d = snaps.get(u) or {}
            past = [yy for yy in d if yy <= y]
            if not past:
                g = groups[urls.index(u)] if groups and not d else None   # 한 번도 기록이 없는 페이지 → 지금 목록으로 (바뀐 적 모름)
                for e in cur:
                    if g and e.get("lb") == g:
                        out.append(entry(sid, e["t"], e["a"], label=y, field=e.get("f", ""), nation=e.get("n", ""))); n += 1
                continue
            for t, a in d[max(past)]:
                e = canon(t, a, groups[urls.index(u)] if groups else None)
                out.append(entry(sid, e["t"] if e else t, e["a"] if e else a, label=y, field=(e or {}).get("f", ""), nation=(e or {}).get("n", ""))); n += 1
        report.append(f"{y}년 {n}권")
    # 어느 해에도 기록이 없는 하위 페이지가 있으면, 그 해 목록 크기가 들쭉날쭉 → 가장 많이 남은 해들만 남김
    cnt = {}
    for e in out:
        cnt[e["lb"]] = cnt.get(e["lb"], 0) + 1
    if cnt:
        top = max(cnt.values())
        keep = {y for y, c in cnt.items() if c >= top * 0.85}
        out = [e for e in out if e["lb"] in keep]
    log(f"  웨이백 {sid}: " + ", ".join(report) + f" → 쓰는 해 {sorted(set(e['lb'] for e in out))}")
    return out


def collect(force: bool):
    raw = jload(ST / "raw.json", {}) or {}
    meta = jload(ST / "raw_meta.json", {}) or {}
    jobs = [(k[1], (lambda k=k: from_kyobo(k[0], k[1]))) for k in SRC.KYOBO]
    jobs += [(p[0], (lambda p=p: from_pyxis(p[1], p[2], p[0]))) for p in SRC.PYXIS]
    jobs += [(SRC.POSTECH[0], from_postech)]
    jobs += [(t[0], (lambda t=t: from_tsv(t[0], t[1]))) for t in SRC.TSV]
    if NLK:
        jobs += [("nlk2", from_nlk_saseo)]
    for wb in SRC.WAYBACK:
        jobs += [("wb_" + wb[0], (lambda wb=wb: from_wayback(*wb)))]
    for sid, fn in jobs:
        old = meta.get(sid) or {}
        fresh = old.get("ok") and (time.time() - old.get("ok", 0) < (30 if sid.startswith("wb_") else 6.5) * 86400)
        if sid in raw and fresh and not force and not sid.startswith(("yonsei", "korea")):
            continue
        if left() < MAX_MIN * 60 * 0.5:
            log(f"목록 {sid}: 시간이 모자라 다음 실행에"); continue
        try:
            log(f"목록 {sid} 받는 중…")
            rows = fn()
            if not rows:
                raise RuntimeError("0권")
            raw[sid] = rows
            meta[sid] = {"ok": time.time(), "n": len(rows), "fail": 0}
            log(f"목록 {sid}: {len(rows)}권")
            jsave(ST / "raw.json", raw); jsave(ST / "raw_meta.json", meta, compact=False)
        except TimeoutError as e:
            log(f"목록 {sid}: {e}")
        except Exception as e:  # noqa: BLE001
            meta[sid] = {**old, "fail": old.get("fail", 0) + 1, "err": str(e)[:120]}
            log(f"목록 {sid} 실패 (직전 것 유지): {e}")
    jsave(ST / "raw.json", raw)
    jsave(ST / "raw_meta.json", meta, compact=False)
    for sid, m in meta.items():
        if m.get("fail", 0) >= 3:
            HEALTH[sid] = m.get("err", "실패")
    return raw


# ───────────────────────── 2. 같은 책끼리 묶기 ─────────────────────────
SRCINFO = {}
for _m, _id, _nm, _k, _s in SRC.KYOBO:
    SRCINFO[_id] = {"name": _nm, "kind": _k, "short": _s, "via": "교보문고 추천도서"}
for _id, _h, _r, _nm, _s in SRC.PYXIS:
    SRCINFO[_id] = {"name": _nm, "kind": "univ", "short": _s, "via": _h}
SRCINFO[SRC.POSTECH[0]] = {"name": SRC.POSTECH[2], "kind": "univ", "short": SRC.POSTECH[3], "via": "library.postech.ac.kr"}
for _id, _f, _nm, _k, _s in SRC.TSV:
    SRCINFO[_id] = {"name": _nm, "kind": _k, "short": _s, "via": "도서관 페이지 (한 번 정리)"}
SRCINFO["nlk2"] = {"name": "국립중앙도서관 사서 추천도서", "kind": "org", "short": "국립중앙도서관", "via": "국립중앙도서관 Open API"}


def group(raw):
    by_isbn, by_title, works = {}, {}, {}
    alias = jload(ST / "isbn_of.json", {}) or {}                  # 손 목록(ISBN 없음) 제목 → 찾아 둔 ISBN
    for sid, rows in raw.items():
        for e in rows:
            if not e.get("t"):
                continue
            isbn = e.get("isbn") or alias.get(norm_title(e["t"]) + "|" + author_key(e["a"]), "")
            tk = norm_title(e["t"])
            if not tk:
                continue
            w = None
            if isbn and isbn in by_isbn:
                w = by_isbn[isbn]
            if w is None:
                for cand in by_title.get(tk, []):
                    if same_author(cand["a"], e["a"]):
                        w = cand; break
            if w is None:
                key = tk + "|" + author_key(e["a"])
                w = {"id": wid(key), "t": e["t"], "a": e["a"], "tk": tk, "ent": [], "isbns": []}
                works[w["id"]] = w
                by_title.setdefault(tk, []).append(w)
            w["ent"].append(e)
            if isbn and isbn not in w["isbns"]:
                w["isbns"].append(isbn); by_isbn[isbn] = w
            if not w["a"] and e["a"]:
                w["a"] = e["a"]
            if len(e["t"]) < len(w["t"]) and norm_title(e["t"]) == tk and not re.search(r"[A-Za-z]{4}", e["t"]):
                w["t"] = e["t"]
    return works


# ───────────────────────── 3. 정보 붙이기 (열쇠·한도 안에서) ─────────────────────────
class Cache:
    def __init__(self, name):
        self.p = ST / f"{name}.json"
        self.d = jload(self.p, {}) or {}
        self.dirty = False

    def get(self, k):
        return self.d.get(k)

    def put(self, k, v):
        self.d[k] = v; self.dirty = True

    def save(self):
        if self.dirty:
            jsave(self.p, self.d); self.dirty = False


def kakao_search(q, target=None, size=10):
    if not KAKAO:
        return []
    p = {"query": q, "size": size}
    if target:
        p["target"] = target
    if "kakao" in DOWN:
        return None
    d = get("https://dapi.kakao.com/v3/search/book", params=p, headers={"Authorization": f"KakaoAK {KAKAO}"}, kind="kakao")
    time.sleep(0.12)
    if d is None:
        DOWN.add("kakao"); log("  카카오가 막혀 이번엔 그만"); return None
    return d.get("documents") or []


def kakao_slim(doc):
    isb = [x for x in (doc.get("isbn") or "").split() if len(x) == 13]
    return {"t": doc.get("title"), "a": doc.get("authors") or [], "tr": doc.get("translators") or [], "pub": doc.get("publisher"),
            "d": (doc.get("datetime") or "")[:10], "c": (doc.get("contents") or "")[:420], "img": doc.get("thumbnail") or "",
            "url": doc.get("url") or "", "st": doc.get("status") or "", "isbn": isb[0] if isb else ""}


def find_isbn(w, kc: Cache):
    """ISBN 없는 책(손 목록·포스텍) → 카카오에서 제목+지은이로 찾기. 판매 중인 판을 먼저."""
    key = "q:" + w["tk"] + "|" + author_key(w["a"])
    hit = kc.get(key)
    if hit is not None:
        return hit
    if not KAKAO:
        return ""
    title = re.split(r"\s*[:(]", w["t"])[0].strip()
    docs = kakao_search(title, "title", 20)
    if docs is None:
        return ""
    best, bs = "", -1
    for d in docs:
        s = kakao_slim(d)
        if not s["isbn"]:
            continue
        sc = 0
        if norm_title(s["t"]) == w["tk"]:
            sc += 5
        elif w["tk"] in norm_title(s["t"]):
            sc += 2
        else:
            continue
        if w["a"] and any(same_author(w["a"], a) and author_key(w["a"]) and author_key(w["a"]) in re.sub(r"\s", "", a) for a in s["a"]):
            sc += 4
        elif w["a"] and s["a"] and not any(same_author(w["a"], a) for a in s["a"]):
            sc -= 3
        if s["st"] == "정상판매":
            sc += 1
        if re.search(r"만화|요약|청소년을 위한|어린이|읽기\b|해설|논술", s["t"]):
            sc -= 3
        if sc > bs:
            best, bs = s["isbn"], sc
    best = best if bs >= 5 else ""
    kc.put(key, best)
    return best


def deep(x, out=None):
    """응답이 몇 겹으로 싸여 있든 키를 찾음 (먼저 나온 값)."""
    if out is None:
        out = {}
    if isinstance(x, dict):
        for k, v in x.items():
            if isinstance(v, (dict, list)):
                deep(v, out)
            elif k not in out and v not in (None, ""):
                out[k] = v
    elif isinstance(x, list):
        for v in x[:3]:
            deep(v, out)
    return out


def y24(path, isbn):
    d = get(f"https://apis.yes24.com/v1/goods/{path}", params={"searchType": "ISBN13", "query": isbn, "detail": "Y"},
            headers={"X-Api-Key": YES24}, kind="yes24")
    time.sleep(0.25)                                                  # 초당 5회 한도
    if d is None:
        DOWN.add("yes24"); log("  YES24가 막혀 이번엔 그만 (열쇠·한도 확인)"); return None
    if d.get("__404") or not d.get("success"):
        return {}
    smp = ST / f"y24_sample_{path}.json"                              # 응답 모양 기록 (열쇠는 안 들어감) — 고칠 때 보려고
    if not smp.exists():
        jsave(smp, d, compact=False)
    out = deep(d.get("data"))
    cd = None

    def find_cd(x):
        if isinstance(x, dict):
            if isinstance(x.get("contentDetail"), dict):
                return x["contentDetail"]
            for v in x.values():
                r = find_cd(v)
                if r: return r
        if isinstance(x, list):
            for v in x:
                r = find_cd(v)
                if r: return r
        return None
    cd = find_cd(d.get("data"))
    if cd:
        out["contentDetail"] = cd
    return out


def yes24_info(isbn, yc: Cache):
    hit = yc.get(isbn)
    if hit is not None and not hit.get("_redo"):
        return hit
    if not YES24 or "yes24" in DOWN:
        return None
    g = y24("itemDetail", isbn)
    if g is None:
        return None
    out = {}
    if hit and hit.get("_redo"):                                      # 상세만 다시 (목차는 이미 있음)
        old_toc = hit.get("toc", "")
    else:
        old_toc = None
    if g:
        cd = g.get("contentDetail") or {}
        out = {"cv": g.get("cover") or g.get("coverLarge") or g.get("image") or "", "url": g.get("link") or g.get("mobileLink") or "", "pg": g.get("pages") or g.get("page"),
               "ot": g.get("originalTitle") or "", "cat": g.get("categoryFullPath") or g.get("goodsSortNm") or g.get("categoryName") or "",
               "eb": g.get("eBookLink") or g.get("ebookLink") or "", "ebid": g.get("ebookId"),
               "star": g.get("starScore"), "intro": clean(cd.get("introduce") or cd.get("intro") or cd.get("summary") or "")[:900],
               "toc": (cd.get("toc") or cd.get("contents") or "")}
        if not out["toc"] and old_toc:
            out["toc"] = old_toc
        if not out["toc"] and old_toc is None:
            c = y24("content", isbn)
            if c is None:
                return None
            out["toc"] = c.get("contents") or ""
        out["toc"] = clean_toc(out["toc"])
    elif hit and hit.get("_redo"):
        out = {k: v for k, v in hit.items() if k != "_redo"}
    yc.put(isbn, out)
    return out


def nlk_info(isbn, nc: Cache):
    hit = nc.get(isbn)
    if hit is not None:
        return hit
    if not NLK:
        return None
    d = get("https://www.nl.go.kr/seoji/SearchApi.do", params={"cert_key": NLK, "result_style": "json", "page_no": 1, "page_size": 1, "isbn": isbn}, kind="nlk")
    doc = ((d or {}).get("docs") or [{}])[0] if d else {}
    out = {"kdc": doc.get("KDC") or doc.get("DDC") or "", "pg": doc.get("PAGE") or "", "img": doc.get("TITLE_URL") or "", "toc": ""}
    tu = doc.get("BOOK_TB_CNT_URL") or ""
    if tu:
        txt = get(tu, as_json=False, kind="nlk", tries=1)
        out["toc"] = clean_toc(txt or "")
    nc.put(isbn, out)
    time.sleep(0.2)
    return out


def clean_toc(t):
    t = H.unescape(str(t or ""))
    t = re.sub(r"<br\s*/?>|</p>|</li>|</div>", "\n", t, flags=re.I)
    t = re.sub(r"<[^>]+>", "", t)
    lines = [re.sub(r"[ \t　]+", " ", x).strip() for x in t.splitlines()]
    lines = [x for x in lines if x and not re.fullmatch(r"[-=_·.\s]+", x)]
    return "\n".join(lines)[:6000]


# 위키데이터 지은이 (나라·태어난 해·세상 떠난 해·영문 이름)
def wd_author(name, wc: Cache):
    name = first_author(name)
    if not name or len(name) < 2 or re.search(r"위원회|연구회|제작팀|편집부|재단|출판|협회", name):
        return None
    hit = wc.get(name)
    if hit is not None:
        return hit or None
    if "wd" in DOWN:
        return None
    lang = "en" if re.fullmatch(r"[A-Za-z .,'-]+", name) else "ko"
    q = name
    if lang == "en" and "," in name:
        q = " ".join(reversed([x.strip() for x in name.split(",", 1)]))
    s = get("https://www.wikidata.org/w/api.php", params={"action": "wbsearchentities", "search": q, "language": lang, "uselang": "ko", "type": "item", "limit": 6, "format": "json"}, kind="wd")
    if s is None:
        DOWN.add("wd"); log("  위키데이터가 막혀 이번엔 그만 (다음 실행에 이어서)"); return None
    ids = [x["id"] for x in s.get("search") or []]
    q2 = re.sub(r"\s+[A-Z]\.?\s+", " ", q).replace("  ", " ")
    if not ids and q2 != q:
        s2 = get("https://www.wikidata.org/w/api.php", params={"action": "wbsearchentities", "search": q2, "language": lang, "uselang": "ko", "type": "item", "limit": 6, "format": "json"}, kind="wd")
        ids = [x["id"] for x in (s2 or {}).get("search") or []]
    res = {}
    if ids:
        e = get("https://www.wikidata.org/w/api.php", params={"action": "wbgetentities", "ids": "|".join(ids), "props": "claims|labels|sitelinks", "languages": "ko|en", "sitefilter": "enwiki|kowiki", "format": "json"}, kind="wd")
        if e is None:
            DOWN.add("wd"); return None
        ents = e.get("entities") or {}
        for i in ids:
            x = ents.get(i) or {}
            cl = x.get("claims") or {}
            if not any(((c.get("mainsnak") or {}).get("datavalue") or {}).get("value", {}).get("id") == "Q5" for c in cl.get("P31", [])):
                continue

            def yr(p):
                for c in cl.get(p, []):
                    v = ((c.get("mainsnak") or {}).get("datavalue") or {}).get("value") or {}
                    m = re.match(r"([+-])(\d+)", v.get("time", ""))
                    if m:
                        return int(m.group(2)) * (-1 if m.group(1) == "-" else 1)
                return None
            ctry = [((c.get("mainsnak") or {}).get("datavalue") or {}).get("value", {}).get("id") for c in cl.get("P27", [])][:3]
            res = {"q": i, "b": yr("P569"), "d": yr("P570"), "c": [c for c in ctry if c], "ko": (x.get("labels", {}).get("ko") or {}).get("value", ""),
                   "en": (x.get("labels", {}).get("en") or {}).get("value", ""), "kw": (x.get("sitelinks", {}).get("kowiki") or {}).get("title", "")}
            break
    wc.put(name, res)
    time.sleep(0.4)
    return res or None


def wd_labels(qids, lc: Cache):
    need = [q for q in qids if q and lc.get(q) is None]
    for i in range(0, len(need), 40):
        e = get("https://www.wikidata.org/w/api.php", params={"action": "wbgetentities", "ids": "|".join(need[i:i + 40]), "props": "labels", "languages": "ko|en", "format": "json"}, kind="wd")
        for q, x in ((e or {}).get("entities") or {}).items():
            lb = x.get("labels") or {}
            lc.put(q, (lb.get("ko") or lb.get("en") or {}).get("value", ""))


# 고전 원문 (저작권 끝난 책): 한국어 위키문헌 · 구텐베르크
def wikisource(title, sc: Cache):
    k = "ws:" + title
    hit = sc.get(k)
    if hit is not None:
        return hit
    if "ws" in DOWN:
        return ""
    d = get("https://ko.wikisource.org/w/api.php", params={"action": "opensearch", "search": title, "limit": 5, "namespace": 0, "format": "json"}, kind="wd")
    if d is None:
        DOWN.add("ws"); return ""
    best = ""
    for t in (d[1] if isinstance(d, list) and len(d) > 1 else []):
        if norm_title(t) == norm_title(title):
            best = t; break
    sc.put(k, best)
    return best


def gutenberg(en_title, en_author, sc: Cache):
    if not en_title:
        return None
    k = "gb:" + en_title + "|" + en_author
    hit = sc.get(k)
    if hit is not None:
        return hit or None
    if "gb" in DOWN:
        return None
    d = get("https://gutendex.com/books/", params={"search": f"{en_title} {en_author.split()[-1] if en_author else ''}".strip(), "languages": "en"}, kind="wd")
    if d is None:
        DOWN.add("gb"); return None
    res = {}
    for b in d.get("results") or []:
        if norm_title(b.get("title", "")).startswith(norm_title(en_title)[:12]) and not b.get("copyright"):
            fm = b.get("formats") or {}
            txt = next((v for kk, v in fm.items() if kk.startswith("text/plain") and not v.endswith(".zip")), "")
            res = {"id": b["id"], "t": b["title"], "txt": txt, "dl": b.get("download_count", 0)}
            break
    sc.put(k, res)
    return res or None


# ───────────────────────── 4. 분류 ─────────────────────────
def field_of(w, info):
    votes = {}

    def v(f, n=1):
        if f:
            votes[f] = votes.get(f, 0) + n
    for e in w["ent"]:
        v(e.get("f"), 3)
        cn = (e.get("cn") or "").strip()
        if cn[:1] in SRC.CALLNO and re.match(r"\d{3}", cn):
            v(SRC.CALLNO[cn[0]], 2)
        v(word_field(e.get("cat")), 2)
    kdc = (info.get("kdc") or "")[:1]
    if kdc:
        v({"0": "언어·교양", "1": "철학·사상", "2": "종교", "3": "사회·정치", "4": "자연과학", "5": "기술·의학", "6": "예술", "7": "언어·교양", "8": "문학", "9": "역사·지리"}.get(kdc), 3)
    v(word_field(info.get("ycat")), 2)
    if not votes:
        t = w["t"]
        if re.search(r"소설|시집|이야기|전$|기행|문집|희곡|선집", t):
            v("문학")
    if "경제·경영" in votes and "사회·정치" in votes and votes["사회·정치"] >= votes["경제·경영"]:
        pass
    return max(votes.items(), key=lambda kv: kv[1])[0] if votes else "언어·교양"


def word_field(cat):
    cat = (cat or "").strip()
    if not cat:
        return ""
    first = cat.split()[0]
    if first in SRC.CAT_EXACT:
        return SRC.CAT_EXACT[first]
    toks = [t for t in re.split(r"[\s/>·,]+", cat) if t]
    for f, words in SRC.FIELD_WORDS:
        for t in toks:
            if t.endswith("인문학"):
                continue
            if any(t == w or (len(w) >= 2 and t.endswith(w)) or (len(w) >= 2 and t.startswith(w)) for w in words):
                return f
    return ""


def nation_of(w, au, lc: Cache):
    for e in w["ent"]:
        if e.get("n"):
            return e["n"]
    if au and au.get("c"):
        for q in au["c"]:
            lab = lc.get(q) or ""
            for n, words in SRC.NATION_WORDS:
                if any(x in lab for x in words):
                    return n
    a = w["a"] or ""
    if w.get("kk") and not w.get("trans") and re.fullmatch(r"[가-힣]{2,3}", first_author(a)):
        return "한국"                                                # 카카오에 옮긴이가 없고 이름이 한국식 2~3자
    return "미상"


def era_of(au, w):
    b = au.get("b") if au else None
    if b is None and au and au.get("d") is not None:
        b = au["d"] - 50
    if b is None:
        return "미상"
    for name, lo, hi in SRC.ERAS:
        if lo <= b < hi:
            return name
    return "미상"


def level_of(field, pages, era):
    sc = 0
    try:
        p = int(re.sub(r"\D", "", str(pages or "")) or 0)
    except ValueError:
        p = 0
    if p > 500: sc += 1
    if p > 850: sc += 1
    if p and p < 230: sc -= 1
    if field in ("철학·사상", "자연과학", "사회·정치", "경제·경영") : sc += 1
    if era in ("고대", "중세") and field != "문학": sc += 1
    return "쉽게" if sc <= 0 else "보통" if sc == 1 else "어렵게"


# ───────────────────────── 5. 다른 앱과 잇기 ─────────────────────────
def load_history_titles():
    m = {}
    for f in sorted((ROOT / "data/history/s").glob("*.json")):
        for row in jload(f, []) or []:
            try:
                t, i, y, kind = row[0], row[1], row[2], row[3]
            except Exception:
                continue
            m.setdefault(re.sub(r"\s", "", t), (i, kind, t))
    return m


def load_iyagi():
    out = {}
    for x in jload(ROOT / "data/iyagi/orig/index.json", []) or []:
        out["o:" + norm_title(x.get("ko", ""))] = ("orig-" + x["id"], x.get("ko"), x.get("tr"))
        out["g:" + str(x["id"])] = ("orig-" + x["id"], x.get("ko"), x.get("tr"))
    for x in jload(ROOT / "data/iyagi/stories/_index.json", []) or []:
        for k in [x.get("orig"), x.get("title")]:
            if k:
                out.setdefault("s:" + norm_title(k), ("read-" + x["id"], x.get("title"), 1))
    return out


# ───────────────────────── 6. 원문을 이야기 앱 '원문 읽기'에 보내기 ─────────────────────────
def add_iyagi_orig(gb, ko_title, en_author, shelf="세계 고전 소설"):
    idx_p = ROOT / "data/iyagi/orig/index.json"
    idx = jload(idx_p, []) or []
    gid = "g" + str(gb["id"])
    if any(x["id"] == gid for x in idx):
        return gid
    txt = get(gb["txt"], as_json=False, timeout=60) if gb.get("txt") else None
    if not txt or len(txt) < 20000:
        return ""
    s = re.split(r"\*\*\* ?START OF (?:THE|THIS) PROJECT GUTENBERG[^\n]*\n", txt, maxsplit=1)
    body = s[1] if len(s) > 1 else txt
    body = re.split(r"\*\*\* ?END OF (?:THE|THIS) PROJECT GUTENBERG", body)[0]
    if len(body) > 1_300_000:
        return ""
    pars = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", body.replace("\r", ""))]
    pars = [p for p in pars if p]
    parts, cur, n = [], [], 0
    for p in pars:
        cur.append(p); n += len(p)
        if n > 260_000:
            parts.append(cur); cur, n = [], 0
    if cur:
        parts.append(cur)
    for i, ps in enumerate(parts, 1):
        jsave(ROOT / f"data/iyagi/orig/{gid}-{i}.json", {"p": ps})
    idx.append({"id": gid, "ko": ko_title, "shelf": shelf, "title": gb.get("t", ""), "author": en_author, "lang": "en",
                "chars": sum(len(p) for p in pars), "parts": len(parts), "url": f"https://www.gutenberg.org/ebooks/{gb['id']}", "tr": 0, "via": "book"})
    jsave(idx_p, idx)
    log(f"  + 이야기 원문 읽기에 추가: {ko_title} ({gid}, {len(parts)}부)")
    return gid


# ───────────────────────── 7. 저장 ─────────────────────────
def links_for(w, isbn, title, author):
    q = quote(f"{title} {first_author(author)}".strip())
    qt = quote(title)
    return {
        "google": f"https://www.google.com/search?q={quote(chr(34) + title + chr(34) + ' ' + first_author(author))}",
        "lib": f"https://www.data4library.kr/srch?srchText={quote(isbn) if isbn else qt}",
        "millie": f"https://www.millie.co.kr/v3/search/result?keyword={qt}",
        "ridi": f"https://ridibooks.com/search?q={qt}",
        "welaaa": f"https://www.welaaa.com/search?keyword={qt}",
        "kyobo": f"https://search.kyobobook.co.kr/search?keyword={quote(isbn) if isbn else q}",
        "yes24": f"https://www.yes24.com/product/search?query={quote(isbn) if isbn else q}",
        "elib": f"https://www.google.com/search?q={quote(title + ' 전자책 도서관')}",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lists", action="store_true")
    ap.add_argument("--max-minutes", type=float, default=None)
    ap.add_argument("--no-net-enrich", action="store_true", help="목록만 (정보 붙이기 건너뜀)")
    ap.add_argument("--offline", action="store_true", help="저장된 목록으로 화면 자료만 다시 만들기 (시험용)")
    a = ap.parse_args()
    global MAX_MIN
    if a.max_minutes:
        MAX_MIN = a.max_minutes
    ST.mkdir(parents=True, exist_ok=True)
    log(f"열쇠: 카카오 {'O' if KAKAO else 'X'} · YES24 {'O' if YES24 else 'X'} · 국립중앙도서관 {'O' if NLK else 'X'}")

    raw = (jload(ST / "raw.json", {}) or {}) if a.offline else collect(a.lists)
    if a.offline:
        a.no_net_enrich = True
    works = group(raw)
    log(f"묶은 책 {len(works)}권 (목록 줄 {sum(len(v) for v in raw.values())})")

    kc, yc, nc, wc, lc, sc = Cache("kakao"), Cache("yes24"), Cache("nlk"), Cache("wd_author"), Cache("wd_label"), Cache("fulltext")
    alias = jload(ST / "isbn_of.json", {}) or {}

    # 여러 곳이 추천한 책부터 정보 채우기
    def nrec(w):
        return len({SRCINFO.get(e["src"], {}).get("short", e["src"]) for e in w["ent"]})
    order = sorted(works.values(), key=lambda w: (-nrec(w), w["t"]))
    budget = {"kakao": 9000, "yes24": 4200, "nlk": 3000, "wd": 2500}
    done_info = 0
    for w in order:
        if left() < 120 or a.no_net_enrich:
            break
        # ISBN
        if not w["isbns"] and KAKAO and CALLS["kakao"] < budget["kakao"]:
            isb = find_isbn(w, kc)
            if isb:
                w["isbns"].append(isb)
                alias[w["tk"] + "|" + author_key(w["a"])] = isb
        isbn = w["isbns"][0] if w["isbns"] else ""
        if isbn and KAKAO and kc.get(isbn) is None and CALLS["kakao"] < budget["kakao"]:
            docs = kakao_search(isbn, "isbn", 1)
            if docs is not None:
                kc.put(isbn, kakao_slim(docs[0]) if docs else {})
        if isbn and YES24 and (yc.get(isbn) is None or (yc.get(isbn) or {}).get("_redo")) and CALLS["yes24"] < budget["yes24"]:
            yes24_info(isbn, yc)
            # 목차가 없으면 같은 책 다른 판에서
            if not (yc.get(isbn) or {}).get("toc"):
                for other in w["isbns"][1:3]:
                    if yc.get(other) is None and CALLS["yes24"] < budget["yes24"]:
                        yes24_info(other, yc)
        if isbn and NLK and nc.get(isbn) is None and CALLS["nlk"] < budget["nlk"]:
            nlk_info(isbn, nc)
        if w["a"] and CALLS["wd"] < budget["wd"]:
            wd_author(w["a"], wc)
        done_info += 1
        if done_info % 300 == 0:
            for c in (kc, yc, nc, wc):
                c.save()
            jsave(ST / "isbn_of.json", alias)
            log(f"  … {done_info}권 · 호출 {CALLS} · 남은 {int(left() // 60)}분")
    if not a.offline:
        wd_labels(sorted({q for v in wc.d.values() if v for q in (v.get("c") or [])}), lc)
    for c in (kc, yc, nc, wc, lc):
        c.save()
    jsave(ST / "isbn_of.json", alias)

    # ── 화면용 자료 만들기
    hist = load_history_titles()
    iy = load_iyagi()
    rows, details, links_h, links_i = [], {}, {}, {}
    fulltext_added = 0
    prev_ids = set(jload(OUT / "_index.json", {}).get("ids_sample", []) or [])
    first_seen = jload(ST / "first_seen.json", {}) or {}
    today = now().strftime("%Y-%m-%d")
    for w in works.values():
        isbns = w["isbns"]
        isbn = isbns[0] if isbns else ""
        k = kc.get(isbn) or {}
        y = {}
        for i2 in isbns[:4]:
            yy = yc.get(i2) or {}
            if yy and (not y or (yy.get("toc") and not y.get("toc"))):
                y = yy
        nl = nc.get(isbn) or {}
        au = wc.get(first_author(w["a"])) or {}
        info = {"kdc": nl.get("kdc", ""), "ycat": y.get("cat", "")}
        fld = field_of(w, info)
        w["trans"] = bool(k.get("tr")); w["kk"] = bool(k)
        nat = nation_of(w, au, lc)
        era = era_of(au, w)
        pages = y.get("pg") or nl.get("pg") or ""
        lvl = level_of(fld, pages, era)
        srcs = sorted({e["src"] for e in w["ent"]})
        shorts = sorted({SRCINFO.get(s, {}).get("short", s) for s in srcs})
        univ = sorted({SRCINFO[s]["short"] for s in srcs if SRCINFO.get(s, {}).get("kind") == "univ"})
        recs = []
        seen = set()
        for e in w["ent"]:
            kk = (e["src"], e.get("lb", ""))
            if kk in seen:
                continue
            seen.add(kk)
            recs.append([e["src"], e.get("lb", "")])
        years = sorted({int(e["lb"]) for e in w["ent"] if re.fullmatch(r"(19|20)\d\d", e.get("lb", ""))})
        cover = y.get("cv") or ""
        cover2 = f"https://contents.kyobobook.co.kr/sih/fit-in/300x0/pdt/{isbn}.jpg" if isbn else ""
        if not cover:
            cover, cover2 = cover2, (k.get("img") or next((e["cv"] for e in w["ent"] if e.get("cv")), "") or nl.get("img", ""))
        toc = y.get("toc") or nl.get("toc") or ""
        intro = y.get("intro") or k.get("c") or ""
        pd = bool(au and au.get("d") is not None and au["d"] <= SRC.PD_DEATH_MAX) or (era in ("고대", "중세"))
        full = {}
        if pd:
            ws = sc.get("ws:" + w["t"])
            if ws is None and CALLS["wd"] < budget["wd"] + 800 and left() > 60 and not a.offline:
                ws = wikisource(re.split(r"\s*[:(]", w["t"])[0], sc)
            if ws:
                full["ws"] = ws
            ot = y.get("ot") or ""
            if ot and re.search(r"[A-Za-z]", ot) and left() > 60 and not a.offline:
                gb = gutenberg(re.split(r"\s*[:(]", ot)[0], au.get("en", ""), sc)
                if gb:
                    full["gb"] = gb["id"]
                    hit = iy.get("g:" + str(gb["id"]))
                    if hit:
                        full["iy"] = hit[0]
                    elif fulltext_added < 2 and len(shorts) >= 2 and left() > 300:
                        g = add_iyagi_orig(gb, w["t"], au.get("en", ""))
                        if g:
                            full["iy"] = "orig-" + g; fulltext_added += 1
        rel = []
        hk = re.sub(r"\s", "", re.split(r"\s*[:(]", w["t"])[0])
        if hk in hist and len(hk) >= 2:
            rel.append(["h", hist[hk][0], hist[hk][2]])
            links_h.setdefault(hist[hk][0], []).append([w["id"], w["t"], first_author(w["a"])])
        an = re.sub(r"\s", "", au.get("kw") or au.get("ko") or first_author(w["a"]))
        if an in hist and hist[an][1] == "p" and len(an) >= 2:
            rel.append(["h", hist[an][0], hist[an][2]])
            links_h.setdefault(hist[an][0], []).append([w["id"], w["t"], first_author(w["a"])])
        for pre in ("o:", "s:"):
            hit = iy.get(pre + w["tk"])
            if hit:
                rel.append(["i", hit[0], hit[1]])
                links_i.setdefault(hit[0], []).append([w["id"], w["t"], first_author(w["a"])])
                if pre == "o:":
                    full.setdefault("iy", hit[0])
        eb = []
        if y.get("eb"):
            eb.append(["YES24 eBook", y["eb"]])
        flags = ("t" if toc else "") + ("e" if eb else "") + ("o" if full else "") + ("i" if intro else "")
        if w["id"] not in first_seen:
            first_seen[w["id"]] = today
        pub_year = (k.get("d") or "")[:4] or next((e["y"] for e in w["ent"] if e.get("y")), "")
        title = disp_title(w["t"])
        rows.append([w["id"], title, first_author(w["a"]) or w["a"], cover, cover2, fld, nat, era, lvl, len(shorts), srcs, pub_year,
                     flags, str(pages or ""), len(univ), (years[0] if years else 0), (years[-1] if years else 0), first_seen[w["id"]]])
        details[w["id"]] = {
            "id": w["id"], "t": title, "a": w["a"], "tr": k.get("tr") or [], "pub": k.get("pub") or next((e["pub"] for e in w["ent"] if e.get("pub")), ""),
            "y": pub_year, "isbn": isbn, "isbns": isbns[:8], "cv": cover, "cv2": cover2, "f": fld, "n": nat, "e": era, "l": lvl, "pg": str(pages or ""),
            "ot": y.get("ot", ""), "intro": intro, "toc": toc, "recs": recs, "shorts": shorts, "univ": univ,
            "au": {k2: au.get(k2) for k2 in ("b", "d", "kw", "en") if au.get(k2)} if au else {},
            "eb": eb, "full": full, "rel": rel[:6], "star": y.get("star"), "y24": y.get("url", ""), "daum": k.get("url", ""),
            "links": links_for(w, isbn, re.split(r"\s*[:(]", title)[0], w["a"]),
        }
    sc.save()
    jsave(ST / "first_seen.json", first_seen)

    # 순위: 추천한 곳 수 → 대학 수 → 목차 있음
    rows.sort(key=lambda r: (-r[9], -r[14], 0 if "t" in r[12] else 1, r[1]))
    cols = ["id", "t", "a", "cv", "cv2", "f", "n", "e", "l", "r", "s", "y", "x", "pg", "u", "y0", "y1", "new"]
    KP = "https://contents.kyobobook.co.kr/sih/fit-in/300x0/pdt/"
    short = lambda u: ("k:" + u[len(KP):-4]) if isinstance(u, str) and u.startswith(KP) and u.endswith(".jpg") else u  # noqa: E731
    jsave(OUT / "all.json", {"cols": cols, "kp": KP, "rows": [r[:3] + [short(r[3]), short(r[4])] + r[5:] for r in rows]})
    jsave(OUT / "top.json", {"cols": cols, "rows": rows[:400]})
    # 상세: id 앞 두 글자로 나눠 저장 (256 조각)
    shards = {}
    for d in details.values():
        shards.setdefault(d["id"][1:3], {})[d["id"]] = d
    for sh, obj in shards.items():
        jsave(OUT / f"w/{sh}.json", obj)
    jsave(OUT / "link.json", {"h": links_h, "i": links_i})
    # 학교·기관별 목록 (연도·판별로 어떻게 바뀌었나 보기용): src/<id>.json = {eds:[판…], items:[[책id,[판…]]…]}
    per = {}
    for w in works.values():
        for e in w["ent"]:
            per.setdefault(e["src"], {}).setdefault(w["id"], set()).add(e.get("lb") or "")
    for sid, m in per.items():
        eds = sorted({lb for s in m.values() for lb in s}, key=lambda x: (not re.fullmatch(r"\d{4}", x), x))
        jsave(OUT / f"src/{sid}.json", {"id": sid, "eds": eds, "items": [[k, sorted(v)] for k, v in m.items()]})

    # 출처표 (화면 '출처')
    srcs = []
    allents = {}
    for rows_ in raw.values():
        for e in rows_:
            allents.setdefault(e["src"], []).append(e)
    for sid, info in SRCINFO.items():
        ents = allents.get(sid) or []
        if not ents:
            continue
        eds = {}
        for e in ents:
            eds[e.get("lb") or ""] = eds.get(e.get("lb") or "", 0) + 1
        srcs.append({"id": sid, **info, "n": len(ents), "eds": eds, "bad": sid in HEALTH})
    cnt = lambda i: {k: sum(1 for r in rows if r[i] == k) for k in sorted({r[i] for r in rows})}  # noqa: E731
    index = {
        "at": now().strftime("%Y-%m-%dT%H:%M:%S+09:00"), "total": len(rows), "new": sum(1 for r in rows if r[17] == today),
        "withToc": sum(1 for r in rows if "t" in r[12]), "withCover": sum(1 for r in rows if r[3]), "withFull": sum(1 for r in rows if "o" in r[12]),
        "sources": srcs, "todoUniv": SRC.TODO_UNIV, "fields": cnt(5), "nations": cnt(6), "eras": cnt(7), "levels": cnt(8),
        "fieldOrder": SRC.FIELDS, "nationOrder": SRC.NATIONS, "eraOrder": [e[0] for e in SRC.ERAS] + ["미상"],
        "keys": {"kakao": bool(KAKAO), "yes24": bool(YES24), "nlk": bool(NLK)}, "broken": HEALTH,
        "calls": CALLS, "cols": cols,
        "pending": {"isbn": sum(1 for w in works.values() if not w["isbns"]),
                    "toc": sum(1 for r in rows if "t" not in r[12])},
    }
    jsave(OUT / "_index.json", index, compact=False)
    jsave(OUT / "_meta.json", {"updatedAt": index["at"], "label": f"{len(rows):,}권 · 목차 {index['withToc']:,}"})
    log(f"끝: {len(rows)}권 · 목차 {index['withToc']} · 표지 {index['withCover']} · 원문 {index['withFull']} · 호출 {CALLS} · {int((time.time() - T0) // 60)}분")


if __name__ == "__main__":
    main()
