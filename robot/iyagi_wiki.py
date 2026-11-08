"""iyagi_wiki.py — 이야기 목록(카탈로그) 전체를 위키백과에서 한 번에 모아 기계적으로 정리 (토큰 0).

AI로 하나씩 쓰는 대신, 원문(위키백과 문서)을 크게 모아 둡니다.
  · 한국어 위키백과 문서가 있으면 그것을, 없으면 영어 문서를 씁니다.
  · 영어 문서는 --translate 를 주면 앞부분(첫 문단들)을 무료 번역 모델(NLLB, iyagi_translate.py 와 같은 모델)로 한국어로 옮깁니다.
  · 문서마다 최근 3달 조회수(pv)를 같이 적어 둡니다 → "많이 보는 이야기"만 AI 풀어쓰기(이야기 작가 루틴) 대상으로 고릅니다.

출력 (data/iyagi/wiki/)
  _index.json        [{id, o(목록 이름), t(문서 제목), l(언어), h(첫 문장), n(글자 수), pv, k(번역됨)}]  — 앱이 처음에 받는 작은 목록
  <catId>.json       {id, o, t, l, u(문서 주소), lead:[문단], secs:[{h, p:[문단]}], ko_lead:[번역 문단], pv, at, lic}
  _ai_queue.json     AI 풀어쓰기 후보 (조회수 높은 순, 아직 AI 이야기가 없는 것) — 작가 루틴이 여기서 고름

  python robot/iyagi_wiki.py --max-minutes 300            # 아직 안 모은 항목부터 (이어 하기)
  python robot/iyagi_wiki.py --refresh --limit 50         # 이미 모은 것도 다시
  python robot/iyagi_wiki.py --translate                  # 영어 문서 앞부분 기계번역까지
  python robot/iyagi_wiki.py --queue-only                 # 후보 목록만 다시 만들기
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from iyagi_tools import catalog, stories, norm  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data/iyagi/wiki"
KST = timezone(timedelta(hours=9))
UA = {"User-Agent": "vendingForMe-iyagi/1.0 (personal, non-commercial; +https://github.com/Jeffreryinko/vendingForMe)"}
SKIP_SEC = re.compile(r"^(각주|주석|참고 ?문헌|참고 ?자료|같이 보기|함께 보기|외부 링크|출처|관련 항목|References|Notes|See also|External links|Further reading|Bibliography|Sources|Citations|Footnotes|갤러리|Gallery)$", re.I)
S = requests.Session(); S.headers.update(UA)


def api(lang, **p):
    p.update(format="json", formatversion=2)
    for i in range(4):
        try:
            r = S.get(f"https://{lang}.wikipedia.org/w/api.php", params=p, timeout=30)
            if r.status_code in (429, 503): time.sleep(10 * (i + 1)); continue
            r.raise_for_status(); return r.json()
        except requests.RequestException:
            time.sleep(3 * (i + 1))
    return None


def clean_name(o):
    o = re.sub(r"\s*[\(（].*?[\)）]\s*", " ", o)          # 괄호 속 다른 이름은 빼고
    return re.sub(r"\s+", " ", o).strip(" ·-")


def alt_names(o):
    alts = re.findall(r"[\(（](.*?)[\)）]", o)
    return [a.strip() for a in alts if a.strip()]


def page(lang, title):
    """제목으로 문서 하나 (넘겨주기 따라감, 동음이의 문서는 버림)"""
    j = api(lang, action="query", titles=title, redirects=1, prop="extracts|pageprops|info", explaintext=1, exsectionformat="wiki", ppprop="disambiguation", inprop="url")
    if not j: return None
    pg = (j.get("query", {}).get("pages") or [{}])[0]
    if pg.get("missing") or "disambiguation" in (pg.get("pageprops") or {}) or len(pg.get("extract") or "") < 200: return None
    return pg


def search(lang, q):
    j = api(lang, action="query", list="search", srsearch=q, srlimit=3, srnamespace=0)
    return [x["title"] for x in (j or {}).get("query", {}).get("search", [])]


def ok_match(o, title):
    """검색 결과 제목이 목록 이름과 정말 같은 대상인지 (글자 겹침으로 대충 확인)"""
    a, b = norm(clean_name(o)), norm(title)
    if not a or not b: return False
    if a in b or b in a: return True
    common = len(set(a) & set(b)) / max(1, len(set(a)))
    return common >= 0.6


def find(o):
    names = [clean_name(o)] + alt_names(o)
    for n in names:                                       # 한국어: 제목 그대로 → 검색
        pg = page("ko", n)
        if pg: return "ko", pg
    for t in search("ko", clean_name(o))[:2]:
        if ok_match(o, t):
            pg = page("ko", t)
            if pg: return "ko", pg
    # 영어: 한국어 제목의 다른 언어 연결이 없으니 검색으로
    for t in search("en", clean_name(o))[:1]:
        pg = page("en", t)
        if pg: return "en", pg
    return None, None


def split(extract):
    """'== 제목 ==' 꼴 평문을 첫 부분(lead)과 절(secs)로"""
    lead, secs, cur = [], [], None
    for line in extract.splitlines():
        line = line.strip()
        if not line: continue
        m = re.match(r"^(=+)\s*(.*?)\s*=+$", line)
        if m:
            h = m.group(2); lvl = len(m.group(1))
            if lvl <= 2:
                cur = None if SKIP_SEC.match(h) else {"h": h, "p": []}
                if cur is not None: secs.append(cur)
            elif cur is not None and not SKIP_SEC.match(h):
                cur["p"].append(f"〔{h}〕")
            continue
        if cur is None:
            if not secs: lead.append(line)
            continue
        cur["p"].append(line)
    total, keep = sum(len(x) for x in lead), []
    for s in secs:
        s["p"] = [x for x in s["p"] if not (x.startswith("〔") and x.endswith("〕"))] or s["p"]
        if not s["p"]: continue
        if total > 9000: break
        keep.append(s); total += sum(len(x) for x in s["p"])
    return lead[:8], keep[:10]


def pageviews(lang, title):
    end = datetime.now(timezone.utc).replace(day=1) - timedelta(days=1)
    start = (end - timedelta(days=80)).replace(day=1)
    u = f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/{lang}.wikipedia/all-access/user/{quote(title.replace(' ', '_'), safe='')}/monthly/{start:%Y%m%d}/{end:%Y%m%d}"
    try:
        r = S.get(u, timeout=20)
        return sum(x.get("views", 0) for x in r.json().get("items", [])) if r.ok else 0
    except Exception:
        return 0


def first_sentence(t, n=90):
    t = re.sub(r"\s*\([^)]*\)", "", t or "")
    m = re.match(r"(.+?[.。!?다요])(\s|$)", t)
    s = (m.group(1) if m else t).strip()
    return s if len(s) <= n else s[:n - 1] + "…"


# ── 영어 앞부분 기계번역 (NLLB, 무료) ──
_tr = None
def nllb(paras):
    global _tr
    if _tr is None:
        import ctranslate2, transformers
        from iyagi_translate import ensure_model, MODEL_DIR, HF_MODEL, split_sentences
        ensure_model()
        tok = transformers.AutoTokenizer.from_pretrained(HF_MODEL, src_lang="eng_Latn")
        tr = ctranslate2.Translator(str(MODEL_DIR), device="cpu", compute_type="int8")
        _tr = (tok, tr, split_sentences)
    tok, tr, split_sentences = _tr
    out = []
    for p in paras:
        sents = split_sentences(p)
        if not sents: continue
        toks = [tok.convert_ids_to_tokens(tok.encode(x)) for x in sents]
        tgt = ["kor_Hang"]
        res = tr.translate_batch(toks, target_prefix=[tgt] * len(toks), beam_size=2, max_decoding_length=256)
        out.append(" ".join(tok.decode(tok.convert_tokens_to_ids(r.hypotheses[0][1:] if r.hypotheses[0][:1] == tgt else r.hypotheses[0]), skip_special_tokens=True).replace("⁇", "") for r in res))
    return out


def write_index():
    idx = []
    for f in sorted(OUT.glob("c*.json"), key=lambda p: int(re.sub(r"\D", "", p.stem) or 0)):
        d = json.loads(f.read_text(encoding="utf-8"))
        if not d.get("t"): continue
        lead = d.get("ko_lead") or d.get("lead") or []
        idx.append({"id": d["id"], "o": d["o"], "t": d["t"], "l": d["l"], "h": first_sentence(lead[0] if lead else ""),
                    "n": sum(len(x) for x in d.get("lead", [])) + sum(len(x) for s in d.get("secs", []) for x in s["p"]),
                    "pv": d.get("pv", 0), **({"k": 1} if d.get("ko_lead") else {})})
    (OUT / "_index.json").write_text(json.dumps(idx, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    # AI 풀어쓰기 후보: 조회수 높은 순, 아직 AI가 쓴 이야기가 없는 것
    have = {s.get("catId") for s in stories()} | {norm(s.get("orig")) for s in stories()}
    q = [{"catId": x["id"], "orig": x["o"], "wiki": x["t"], "lang": x["l"], "pv": x["pv"]} for x in sorted(idx, key=lambda x: -x["pv"])
         if x["id"] not in have and norm(x["o"]) not in have][:60]
    (OUT / "_ai_queue.json").write_text(json.dumps({"updatedAt": datetime.now(KST).isoformat(timespec="seconds"), "note": "조회수 높은 순. 작가 루틴은 여기 위에서부터(또는 data/requests 의 요청부터) 골라 씀", "queue": q}, ensure_ascii=False, indent=1), encoding="utf-8")
    return len(idx)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-minutes", type=float, default=300)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--translate", action="store_true")
    ap.add_argument("--queue-only", action="store_true")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if a.queue_only:
        print("목록", write_index(), "개"); return
    deadline = time.time() + a.max_minutes * 60
    done = miss = 0
    # 사용자 요청('풀어 주세요')이 들어온 이야기를 먼저 (클로드 작가 대신 위키백과 원문 정리로 답함, 토큰 0)
    try:
        from easy_tools import requests_, mark_done
        want = {str(r["id"]) for r in requests_("iyagi")}
    except Exception:
        want, mark_done = set(), None
    for c in sorted(catalog(), key=lambda c: c["catId"] not in want):
        if time.time() > deadline: print("시간 한도 — 다음 실행에서 이어서"); break
        if a.limit and done >= a.limit: break
        f = OUT / f"{c['catId']}.json"
        if f.exists() and not a.refresh:
            if a.translate:                                   # 이미 모은 영어 문서의 번역만 채우기
                d = json.loads(f.read_text(encoding="utf-8"))
                if d.get("l") == "en" and d.get("lead") and not d.get("ko_lead"):
                    try: d["ko_lead"] = nllb(d["lead"][:4]); f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8"); done += 1
                    except Exception as e: print("번역 실패", c["catId"], e)
            continue
        lang, pg = find(c["orig"])
        time.sleep(0.3)
        if not pg:
            f.write_text(json.dumps({"id": c["catId"], "o": c["orig"], "t": "", "miss": 1, "at": datetime.now(KST).isoformat(timespec="seconds")}, ensure_ascii=False), encoding="utf-8")
            miss += 1; continue
        lead, secs = split(pg["extract"])
        d = {"id": c["catId"], "o": c["orig"], "g": c["group"], "r": c["region"], "e": c["era"], "sh": c["shelf"], "t": pg["title"], "l": lang,
             "u": pg.get("fullurl") or f"https://{lang}.wikipedia.org/wiki/{quote(pg['title'].replace(' ', '_'))}",
             "lead": lead, "secs": secs, "pv": pageviews(lang, pg["title"]),
             "at": datetime.now(KST).isoformat(timespec="seconds"), "lic": "CC BY-SA 4.0 · 위키백과 기여자"}
        if a.translate and lang == "en" and lead:
            try: d["ko_lead"] = nllb(lead[:4])
            except Exception as e: print("번역 실패", c["catId"], e)
        f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        done += 1
        if done % 50 == 0: print(f"{done}개 · 못 찾음 {miss}", flush=True); write_index()
    for cid in want:
        f = OUT / f"{cid}.json"
        if mark_done and f.exists() and json.loads(f.read_text(encoding="utf-8")).get("t"): mark_done("iyagi", cid)
    n = write_index()
    print(f"끝: 이번에 {done}개 · 못 찾음 {miss} · 목록 {n}개")


if __name__ == "__main__":
    main()
