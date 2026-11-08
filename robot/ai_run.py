"""ai_run.py — AI 탭 로봇 (GitHub Actions, 매일 새벽 4시 30분). 토큰 0.

무엇을 모으나
  hf     : Hugging Face Daily Papers (추천수 있음 → 맨 위 정렬)              공식 API
  arxiv  : arXiv 신규 (cs.AI·CL·CV·LG·RO, 하루 1,000편 넘음) → '더 보기'      공식 RSS
  posts  : 회사 발표 — OpenAI·구글·앤트로픽·메타·딥마인드·엔비디아·네이버·카카오   RSS 또는 페이지
  repos  : GitHub에서 최근 2주 안에 생겨 별이 많이 붙은 AI 저장소                공식 검색 API
  news   : 한국어 AI 매체 (AI타임스·THE AI)                                   RSS
  yt     : 논문 제목으로 유튜브 해설 영상 검색 — YOUTUBE_API_KEY 있을 때만 (하루 60편)

번역 (NLLB, 토큰 0): 제목은 전부, 초록은 추천순 상위 100편만. 번역 기억(_tr.json)으로 다시 안 함.
용어 밑줄: data/ai/terms.json 목록으로 제목+초록에서 찾아 terms 칸에 기록.

출력 (data/ai/)
  _index.json          날짜 목록·출처 건강·개수
  days/<날짜>.json      그날 전부 (hf 전체 + arXiv 상위 + 발표·코드·소식)
  days/<날짜>_more.json  arXiv 나머지 (영문 초록, 제목만 번역)
  archive/<날짜>.json   7일 지난 것은 제목·링크만
  _tr.json / _yt.json / _health.json / _meta.json

  python robot/ai_run.py --no-translate     # 번역 없이 빨리 (확인용)
"""
from __future__ import annotations

import hashlib, html, json, os, re, sys, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote_plus
import xml.etree.ElementTree as ET

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data/ai"; DAYS = OUT / "days"; ARCH = OUT / "archive"
KST = timezone(timedelta(hours=9))
UA = "vendingForMe-bot/1.0 (personal, non-commercial; +https://github.com/Jeffreryinko/vendingForMe)"
NO_TR = "--no-translate" in sys.argv
TOP_ABS = int(os.environ.get("AI_TOP_ABSTRACTS", "100"))        # 초록까지 번역하는 편 수
YT_BUDGET = int(os.environ.get("AI_YT_BUDGET", "60"))           # 하루 유튜브 검색 편 수 (1편 = 100단위, 무료 10,000/일)
KEEP_DAYS = 7
ARXIV_CATS = "cs.AI+cs.CL+cs.CV+cs.LG+cs.RO"
MODEL_DIR = Path(os.environ.get("NLLB_CT2_DIR", "/tmp/nllb-600m-ct2"))
HF_MODEL = "facebook/nllb-200-distilled-600M"

AI_WORDS = re.compile(r"\b(AI|LLM|LLMs|GPT|agent|agents|agentic|model|models|neural|transformer|diffusion|machine learning|deep learning|RAG|embedding|inference|fine-?tun|vision|speech|robot|reinforcement|language model|multimodal|generative|Claude|Gemini|Llama|Qwen|DeepSeek|Mistral|OpenAI|Anthropic|copilot|chatbot|MCP|token)\b", re.I)


def log(*a): print(datetime.now(KST).strftime("%H:%M:%S"), *a, flush=True)
def rj(p, d=None):
    try: return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception: return d
def wj(p, o): Path(p).parent.mkdir(parents=True, exist_ok=True); Path(p).write_text(json.dumps(o, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
def now_iso(): return datetime.now(KST).strftime("%Y-%m-%dT%H:%M:%S+09:00")
def today(): return datetime.now(KST).strftime("%Y-%m-%d")
def clean(s, n=4000): return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", str(s or "")))).strip()[:n]
def hid(s): return hashlib.sha1(s.encode()).hexdigest()[:10]


def get(url, retries=1, **kw):
    hdr = {"User-Agent": UA}; hdr.update(kw.pop("headers", {}))
    for i in range(retries + 1):
        r = requests.get(url, headers=hdr, timeout=40, **kw)
        if r.status_code in (429, 503) and i < retries: time.sleep(20 * (i + 1)); continue
        r.raise_for_status(); return r


def rss_items(url, limit=40):
    """RSS/Atom 공통 읽기 → [{title, url, date, sum}]"""
    x = ET.fromstring(get(url).content)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    out = []
    for it in x.iter("item"):                                   # RSS 2.0
        link = (it.findtext("link") or "").strip()
        out.append({"title": clean(it.findtext("title"), 200), "url": link, "date": clean(it.findtext("pubDate") or it.findtext("{http://purl.org/dc/elements/1.1/}date"), 40),
                    "sum": clean(it.findtext("description") or it.findtext("{http://purl.org/rss/1.0/modules/content/}encoded"), 400)})
    if not out:
        for e in x.findall("a:entry", ns):                     # Atom
            l = e.find("a:link[@rel='alternate']", ns)
            if l is None: l = e.find("a:link", ns)
            out.append({"title": clean(e.findtext("a:title", namespaces=ns), 200), "url": (l.get("href") if l is not None else "") or "",
                        "date": clean(e.findtext("a:updated", namespaces=ns) or e.findtext("a:published", namespaces=ns), 40),
                        "sum": clean(e.findtext("a:summary", namespaces=ns) or e.findtext("a:content", namespaces=ns), 400)})
    return [o for o in out if o["title"] and o["url"]][:limit]


def parse_date(s):
    from email.utils import parsedate_to_datetime
    for f in (lambda v: parsedate_to_datetime(v), lambda v: datetime.fromisoformat(v.replace("Z", "+00:00"))):
        try: return f(s).astimezone(KST).strftime("%Y-%m-%d")
        except Exception: pass
    return ""


# ───────── 논문 ─────────
def src_hf():
    j = get("https://huggingface.co/api/daily_papers?limit=100").json()
    out = []
    for it in j:
        p = it.get("paper") or {}
        pid = p.get("id") or ""
        if not pid: continue
        out.append({"id": pid, "src": "hf", "title": clean(it.get("title") or p.get("title"), 300), "abs": clean(p.get("summary"), 4000),
                    "sum": clean(p.get("ai_summary"), 600) or None, "kw": (p.get("ai_keywords") or [])[:8],
                    "up": int(p.get("upvotes") or 0), "cm": int(it.get("numComments") or 0),
                    "authors": [a.get("name") for a in (p.get("authors") or [])[:4] if a.get("name")],
                    "url": f"https://arxiv.org/abs/{pid}", "hf": f"https://huggingface.co/papers/{pid}", "pdf": f"https://arxiv.org/pdf/{pid}",
                    "code": p.get("githubRepo") or None, "stars": int(p.get("githubStars") or 0) or None, "page": p.get("projectPage") or None,
                    "img": it.get("thumbnail") or None, "pub": (p.get("publishedAt") or "")[:10], "daily": (p.get("submittedOnDailyAt") or "")[:10]})
    keep = sorted({o["daily"] for o in out if o["daily"]}, reverse=True)[:2]   # 가장 최근 이틀치 (미국 시간 기준 하루가 새벽에 바뀜)
    out = [o for o in out if o["daily"] in keep]
    out.sort(key=lambda o: -o["up"])
    return out


def src_arxiv():
    x = ET.fromstring(get(f"https://rss.arxiv.org/rss/{ARXIV_CATS}").content)
    NS = {"arxiv": "http://arxiv.org/schemas/atom", "dc": "http://purl.org/dc/elements/1.1/"}
    out = []
    for it in x.iter("item"):
        typ = (it.findtext("arxiv:announce_type", namespaces=NS) or "").strip()
        if typ not in ("new", "cross"): continue                                   # 수정본(replace)은 뺌
        link = (it.findtext("link") or "").strip(); pid = link.rsplit("/", 1)[-1]
        desc = it.findtext("description") or ""
        m = re.search(r"Abstract:\s*(.*)", desc, re.S)
        out.append({"id": pid, "src": "arxiv", "title": clean(it.findtext("title"), 300), "abs": clean(m.group(1) if m else desc, 4000),
                    "cats": [c.text for c in it.findall("category") if c.text][:4], "cross": typ == "cross",
                    "authors": [a.strip() for a in (it.findtext("dc:creator", namespaces=NS) or "").split(",")[:4] if a.strip()],
                    "url": link, "pdf": link.replace("/abs/", "/pdf/")})
    return out


# ───────── 회사 발표 ─────────
POSTS = [  # (출처 id, 이름, 종류, 주소)
    ("openai", "OpenAI", "rss", "https://openai.com/news/rss.xml"),
    ("google", "구글 AI", "rss", "https://blog.google/technology/ai/rss/"),
    ("anthropic", "앤트로픽", "anthropic", "https://www.anthropic.com/news"),
    ("meta", "메타 AI", "meta", "https://ai.meta.com/blog/"),
    ("deepmind", "딥마인드", "rss", "https://deepmind.google/blog/rss.xml"),
    ("nvidia", "엔비디아", "rss", "https://blogs.nvidia.com/blog/category/generative-ai/feed/"),
    ("naver", "네이버 D2", "rss-ai", "https://d2.naver.com/d2.atom"),
    ("kakao", "카카오 테크", "rss-ai", "https://tech.kakao.com/feed/"),
    # AI 서비스 새 기능 (일반 사용자용 앱 회사)
    ("gemini", "구글 제미나이", "rss", "https://blog.google/products/gemini/rss/"),
    ("microsoft", "마이크로소프트(코파일럿)", "rss-ai", "https://blogs.microsoft.com/feed/"),
    ("apple", "애플 머신러닝", "rss", "https://machinelearning.apple.com/rss.xml"),
    ("samsung", "삼성 뉴스룸", "rss-ai", "https://news.samsung.com/global/feed"),
    ("huggingface", "허깅페이스 블로그", "rss", "https://huggingface.co/blog/feed.xml"),
]
NEWS = [
    ("aitimes", "AI타임스", "rss", "https://www.aitimes.com/rss/allArticle.xml"),
    ("theai", "THE AI", "rss", "https://www.newstheai.com/rss/allArticle.xml"),
]
POST_HOME = {k: u for k, _, _, u in POSTS + NEWS}


def src_anthropic(url):
    h = get(url).text
    out, seen = [], set()
    for u, t in re.findall(r'<a[^>]+href="(/news/[a-z0-9-]+)"[^>]*>(.*?)</a>', h, re.S):
        t = clean(t, 200)
        if u in seen or u.endswith("/announcements") or len(t) < 12: continue
        seen.add(u); out.append({"title": t[:160], "url": "https://www.anthropic.com" + u, "date": "", "sum": ""})
    return out[:30]


def src_meta(url):
    h = get(url).text
    slugs = []
    for s in re.findall(r"ai\.meta\.com/blog/([a-z0-9-]{8,})", h):
        if s not in slugs: slugs.append(s)
    out = []
    for s in slugs[:25]:
        out.append({"title": s.replace("-", " ").capitalize(), "url": f"https://ai.meta.com/blog/{s}/", "date": "", "sum": ""})
    return out


def post_title_fix(items, known):
    """제목이 주소에서 만든 가짜(메타)인 새 글은 페이지 제목을 가져옴 (한 번에 6개까지)"""
    n = 0
    for it in items:
        if it["url"] in known or n >= 6: continue
        try:
            h = get(it["url"]).text; n += 1
            m = re.search(r'property="og:title" content="([^"]+)"', h) or re.search(r"<title>([^<]+)</title>", h)
            if m: it["title"] = clean(m.group(1), 200).split(" | ")[0]
        except Exception: pass
    return items


def collect_posts(kind_list, prev_items, health, which):
    out = []
    for sid, name, kind, url in kind_list:
        key = f"{which}/{sid}"
        old = [p for p in prev_items if p.get("sid") == sid]
        try:
            if kind == "anthropic": items = src_anthropic(url)
            elif kind == "meta": items = post_title_fix(src_meta(url), {p["url"]: 1 for p in old})
            else: items = rss_items(url)
            if kind == "rss-ai": items = [i for i in items if AI_WORDS.search(i["title"] + " " + i["sum"])]
            if not items: raise RuntimeError("0개")
            health.pop(key, None)
            rows = [{"id": "p" + hid(i["url"]), "sid": sid, "name": name, "title": i["title"], "url": i["url"], "date": parse_date(i["date"]) or "", "sum": i["sum"][:300]} for i in items]
        except Exception as e:
            err = f"{type(e).__name__}: {str(e)[:80]}"
            h = health.setdefault(key, {"since": now_iso(), "n": 0}); h["n"] += 1; h["err"] = err; h["last"] = now_iso()
            log(f"실패 {key}: {err}")
            rows = [dict(p, stale=True) for p in old]                                  # 직전 성공본 유지
        out += rows
        time.sleep(0.3)
    return out


# ───────── GitHub ─────────
def src_repos():
    since = (datetime.now(timezone.utc) - timedelta(days=14)).strftime("%Y-%m-%d")
    hdr = {"Accept": "application/vnd.github+json"}
    tok = os.environ.get("GITHUB_TOKEN")
    if tok: hdr["Authorization"] = f"Bearer {tok}"
    seen, out = set(), []
    for q in (f"topic:llm created:>{since}", f"topic:ai created:>{since}", f"topic:machine-learning created:>{since}", f"(topic:agents OR topic:rag OR topic:diffusion) created:>{since}"):
        try:
            j = get("https://api.github.com/search/repositories", params={"q": q + " stars:>30", "sort": "stars", "order": "desc", "per_page": 30}, headers=hdr).json()
        except Exception as e:
            log(f"github 검색 실패 ({q[:20]}): {str(e)[:60]}"); continue
        for r in j.get("items", []):
            if r["full_name"] in seen: continue
            seen.add(r["full_name"])
            out.append({"id": "g" + hid(r["html_url"]), "name": r["full_name"], "url": r["html_url"], "stars": r.get("stargazers_count", 0), "lang": r.get("language") or "",
                        "sum": clean(r.get("description"), 300), "topics": (r.get("topics") or [])[:6], "created": (r.get("created_at") or "")[:10]})
        time.sleep(2)
    out.sort(key=lambda o: -o["stars"])
    return out[:40]


# ───────── 유튜브 ─────────
STOP = set("a an the of for and or in on with to via from by using towards toward is are as at its into over under learning model models language large".split())
def sig_words(t): return {w for w in re.findall(r"[a-z0-9]{3,}", t.lower()) if w not in STOP}

def youtube_links(papers, cache):
    key = os.environ.get("YOUTUBE_API_KEY")
    if not key: return 0
    n = 0
    for p in papers:
        if p["id"] in cache: p["yt"] = cache[p["id"]]; continue
        if n >= YT_BUDGET: break
        try:
            r = requests.get("https://www.googleapis.com/youtube/v3/search", params={"part": "snippet", "q": p["title"][:100], "type": "video", "maxResults": 3, "key": key, "relevanceLanguage": "en", "safeSearch": "strict"}, timeout=30)
            r.raise_for_status(); n += 1
            sw = sig_words(p["title"]); vids = []
            for it in r.json().get("items", []):
                t = clean(it["snippet"]["title"], 120)
                need = max(2, -(-len(sw) * 2 // 5))                                    # 제목 핵심어의 40% 이상 겹쳐야 (엉뚱한 영상 거름)
                if len(sig_words(t) & sw) >= need or (len(sw) <= 2 and sig_words(t) & sw):
                    vids.append({"t": t, "u": f"https://www.youtube.com/watch?v={it['id']['videoId']}", "ch": clean(it["snippet"]["channelTitle"], 40)})
            cache[p["id"]] = vids[:2]; p["yt"] = vids[:2]
        except Exception as e:
            log(f"유튜브 실패 {p['id']}: {str(e)[:60]}")
            if "quota" in str(e).lower() or getattr(e, "response", None) is not None and e.response.status_code == 403: break
    return n


# ───────── 용어 밑줄 ─────────
def ai_feature_videos(prev):
    key = os.environ.get("YOUTUBE_API_KEY")
    if not key: return prev
    out, seen = [], set()
    after = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    for q in ("AI 새 기능", "챗GPT 제미나이 클로드 업데이트"):
        try:
            r = requests.get("https://www.googleapis.com/youtube/v3/search", params={"part": "snippet", "q": q, "type": "video", "maxResults": 12, "key": key,
                             "relevanceLanguage": "ko", "regionCode": "KR", "order": "viewCount", "publishedAfter": after, "safeSearch": "strict"}, timeout=30)
            r.raise_for_status()
            for v in r.json().get("items", []):
                vid = v["id"].get("videoId")
                if not vid or vid in seen: continue
                seen.add(vid); sn = v["snippet"]
                out.append({"id": "y" + vid, "vid": vid, "title": clean(sn["title"], 140), "ch": clean(sn["channelTitle"], 60), "sum": clean(sn.get("description"), 300),
                            "url": f"https://www.youtube.com/watch?v={vid}", "date": (sn.get("publishedAt") or "")[:10]})
        except Exception as e:
            log(f"유튜브 AI 영상 검색 실패: {e}")
    log(f"유튜브 AI 새 기능 영상 {len(out)}개")
    return out[:20] or prev


def term_matcher():
    terms = rj(OUT / "terms.json", [])
    pats = []
    for t in terms:
        for a in t["aliases"]:
            esc = re.escape(a).replace(r"\ ", r"[\s\-]")                                   # 띄어쓰기·하이픈 둘 다
            flags = 0 if re.match(r"^[A-Z][A-Za-z0-9\-\.]{0,5}$", a) else re.I            # 짧은 약어는 대소문자 구분
            pats.append((re.compile(r"(?<![\w-])" + esc + r"(?![\w-])", flags), t["id"]))
    def find(text):
        hit = {}
        for rx, tid in pats:
            c = len(rx.findall(text))
            if c: hit[tid] = hit.get(tid, 0) + c
        return sorted(hit.items(), key=lambda kv: -kv[1])[:12]
    return find


# ───────── 번역 (NLLB) ─────────
SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\(\[\"“])")

def nllb():
    if NO_TR: return None
    try:
        import ctranslate2, transformers
    except Exception as e:
        log(f"번역 라이브러리 없음 → 번역 건너뜀 ({e})"); return None
    if not (MODEL_DIR / "model.bin").exists():
        log("번역 모델 변환 중 (처음 한 번)…")
        import subprocess
        subprocess.run(["ct2-transformers-converter", "--model", HF_MODEL, "--output_dir", str(MODEL_DIR), "--quantization", "int8", "--force"], check=True)
    tok = transformers.AutoTokenizer.from_pretrained(HF_MODEL, src_lang="eng_Latn")
    tr = ctranslate2.Translator(str(MODEL_DIR), device="cpu", compute_type="int8", inter_threads=1, intra_threads=os.cpu_count() or 2)
    tgt = tok.convert_ids_to_tokens(tok.convert_tokens_to_ids(["kor_Hang"]))
    def run(sents):
        res = [""] * len(sents)
        order = sorted(range(len(sents)), key=lambda k: len(sents[k]))
        for b in range(0, len(order), 24):
            idxs = order[b:b + 24]
            toks = [tok.convert_ids_to_tokens(tok.encode(sents[k][:1200])) for k in idxs]
            outs = tr.translate_batch(toks, target_prefix=[tgt] * len(toks), beam_size=2, max_decoding_length=400)
            for k, o in zip(idxs, outs):
                hyp = o.hypotheses[0][1:] if o.hypotheses[0][:1] == tgt else o.hypotheses[0]
                res[k] = tok.decode(tok.convert_tokens_to_ids(hyp), skip_special_tokens=True).replace("⁇", "")
        return res
    return run


def translate_texts(run, texts, mem, deadline):
    """texts: 영문 목록 → 한국어 목록 (기억에 있으면 재사용). 긴 글은 문장 단위로."""
    out = [None] * len(texts)
    need = []
    for i, t in enumerate(texts):
        if not t: continue
        k = hid(t)
        if k in mem: out[i] = mem[k]
        else: need.append(i)
    # 1) 구글 TranslateGemma (시간 예산 안에서, 글 통째로)
    if need:
        try:
            from tgemma import TG
            tg = TG.get()
        except Exception:
            tg = None
        if tg is not None:
            rest = []
            for i in need:
                y = tg.tr(texts[i], "en", "ko", deadline) if tg.ok() and time.time() < deadline else None
                if y: out[i] = y; mem[hid(texts[i])] = y
                else: rest.append(i)
            if len(rest) < len(need): log(f"TranslateGemma 번역 {len(need) - len(rest)}건")
            need = rest
    # 2) 남은 것은 예전 NLLB (문장 단위)
    if run is None or not need: return out
    sents, owner = [], []
    for i in need:
        parts = [s for s in SENT_SPLIT.split(texts[i]) if s.strip()] or [texts[i]]
        for s in parts: sents.append(s.strip()); owner.append(i)
    log(f"번역 {len(need)}건 / {len(sents)}문장 / {sum(map(len, sents)):,}자")
    done = {}
    for b in range(0, len(sents), 240):
        if time.time() > deadline: log("번역 시간 한도 — 나머지는 다음 날"); break
        chunk = sents[b:b + 240]; t0 = time.time()
        res = run(chunk)
        for k, r in enumerate(res): done.setdefault(owner[b + k], []).append(r)
        log(f"  {min(b + 240, len(sents))}/{len(sents)} 문장 ({int(sum(map(len, chunk)) / max(time.time() - t0, 1))}자/초)")
    for i, parts in done.items():
        n_exp = len([s for s in SENT_SPLIT.split(texts[i]) if s.strip()] or [texts[i]])
        if len(parts) < n_exp: continue                                                      # 중간에 끊긴 글은 저장 안 함
        out[i] = " ".join(parts).strip(); mem[hid(texts[i])] = out[i]
    return out


# ───────── 보관 정리 ─────────
def write_feed(data):
    """AI 탭 첫 화면과 자판기 홈 랜덤이 쓰는 가벼운 파일 (논문 초록 없이): 새 기능 소식·국내 소식·해설 영상·인기 논문 2편"""
    keep = ("id", "sid", "name", "title", "ko", "ksum", "sum", "url", "date", "new", "ch", "vid", "img", "cm", "short")
    try:                                                          # 대표 사진 (og:image, 토큰 0, 한 번 본 글은 기억)
        sys.path.insert(0, str(Path(__file__).resolve().parent)); from ogimg import Photos
        ph = Photos(OUT / "_img.json", budget=150)
        for lst in (data["posts"][:60], data["news"][:25], data["papers"]):
            for p in lst:
                if not p.get("img"): p["img"] = ph.get(p.get("url"))
            Photos.drop_logos(lst)
        ph.save()
    except Exception as e: print("대표 사진 실패 — 건너뜀:", e)
    slim = lambda lst, n: [{k: p[k] for k in keep if p.get(k)} for p in lst[:n]]
    hf = sorted([p for p in data["papers"] if p.get("src") == "hf"], key=lambda p: -(p.get("up") or 0))[:2]
    papers = [{k: p[k] for k in ("id", "title", "ko", "ksum", "one", "url", "up", "src", "img") if p.get(k)} for p in hf]
    wj(OUT / "feed.json", {"day": data["day"], "at": data["at"], "posts": slim(data["posts"], 60), "news": slim(data["news"], 25),
                           "vids": slim(data.get("vids", []), 20), "papers": papers})


def archive():
    cutoff = (datetime.now(KST) - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")
    for f in sorted(DAYS.glob("????-??-??.json")):
        day = f.stem
        if day >= cutoff: continue
        d = rj(f, {}); slim = {"day": day, "papers": [], "posts": [], "repos": [], "news": []}
        for p in d.get("papers", []): slim["papers"].append({k: p.get(k) for k in ("id", "src", "title", "ko", "up", "url", "code", "terms") if p.get(k) is not None})
        for col in ("posts", "news"):
            for p in d.get(col, []): slim[col].append({k: p.get(k) for k in ("id", "name", "title", "ko", "url", "date") if p.get(k)})
        for r in d.get("repos", []): slim["repos"].append({k: r.get(k) for k in ("id", "name", "url", "stars", "sum", "ko") if r.get(k)})
        wj(ARCH / f"{day}.json", slim); f.unlink()
        mf = DAYS / f"{day}_more.json"
        if mf.exists(): mf.unlink()
        log(f"보관: {day} → 제목·링크만")


# ───────── 본체 ─────────
def main():
    t0 = time.time(); deadline = t0 + int(os.environ.get("AI_MAX_MINUTES", "150")) * 60
    OUT.mkdir(parents=True, exist_ok=True); DAYS.mkdir(exist_ok=True); ARCH.mkdir(exist_ok=True)
    if not (OUT / "terms.json").exists():
        import subprocess; subprocess.run([sys.executable, str(ROOT / "robot/ai_terms.py")], check=True)
    health = rj(OUT / "_health.json", {}); day = today()
    prev_day = rj(DAYS / f"{day}.json", {})
    days = sorted({f.stem for f in DAYS.glob("????-??-??.json")} - {day})
    prev = rj(DAYS / f"{days[-1]}.json", {}) if days else {}

    # 1. 수집
    data = {"day": day, "at": now_iso(), "papers": [], "posts": [], "repos": [], "news": []}
    for key, fn in (("hf", src_hf), ("arxiv", src_arxiv)):
        try:
            items = fn(); health.pop(f"paper/{key}", None); log(f"{key}: {len(items)}편")
        except Exception as e:
            err = f"{type(e).__name__}: {str(e)[:80]}"; h = health.setdefault(f"paper/{key}", {"since": now_iso(), "n": 0}); h["n"] += 1; h["err"] = err; h["last"] = now_iso()
            log(f"실패 paper/{key}: {err}")
            items = [p for p in (prev_day or prev).get("papers", []) + rj(DAYS / f"{(prev_day or prev).get('day', '')}_more.json", {}).get("papers", []) if p.get("src") == key]
            for p in items: p["stale"] = True
        if key == "hf": hf = items
        else: arx = items
    hf_ids = {p["id"] for p in hf}
    arx = [p for p in arx if p["id"] not in hf_ids]                                     # HF에 있는 건 HF 쪽만
    data["posts"] = collect_posts(POSTS, prev.get("posts", []), health, "post")
    data["news"] = collect_posts(NEWS, prev.get("news", []), health, "news")
    try:
        data["repos"] = src_repos(); health.pop("repos/github", None); log(f"github: {len(data['repos'])}개")
    except Exception as e:
        h = health.setdefault("repos/github", {"since": now_iso(), "n": 0}); h["n"] += 1; h["err"] = str(e)[:80]; h["last"] = now_iso(); data["repos"] = prev.get("repos", [])
    # 오늘 새로 나온 발표·소식만 (10일 안쪽, 날짜 없는 건 '처음 본 날' 기준)
    seen = rj(OUT / "_seen.json", {}); cut14 = (datetime.now(KST) - timedelta(days=14)).strftime("%Y-%m-%d")
    seen = {k: v for k, v in seen.items() if v >= cut14}
    for lst in (data["posts"], data["news"], data["repos"]):
        for p in lst:
            p["first"] = seen.setdefault(p["id"], day)
            if not p.get("date"): p["date"] = p["first"]
            p["new"] = p["first"] == day
    cut10 = (datetime.now(KST) - timedelta(days=10)).strftime("%Y-%m-%d")
    data["posts"] = [p for p in data["posts"] if (p.get("date") or day) >= cut10]
    data["news"] = [p for p in data["news"] if (p.get("date") or day) >= cut10][:40]
    wj(OUT / "_seen.json", seen)

    # 2. 용어 밑줄
    find = term_matcher()
    for p in hf + arx: p["terms"] = find(p["title"] + ". " + p["abs"])
    for p in data["posts"] + data["news"] + data["repos"]: p["terms"] = find(p.get("title", "") + ". " + p.get("sum", ""))

    # 3. 번역 — 제목 전부, 초록은 상위 TOP_ABS편
    mem = rj(OUT / "_tr.json", {}); run = nllb()
    top = hf + arx[:max(0, TOP_ABS - len(hf))]
    rest = arx[len(top) - len(hf):]
    en_posts = [p for p in data["posts"] if p.get("sid") not in ("naver", "kakao")]
    titles = [p["title"] for p in hf + arx] + [p["title"] for p in en_posts] + [p.get("sum") or "" for p in data["repos"]]
    kos = translate_texts(run, titles, mem, deadline)
    i = 0
    for p in hf + arx: p["ko"] = kos[i]; i += 1
    for p in en_posts: p["ko"] = kos[i]; i += 1
    for p in data["repos"]: p["ksum"] = kos[i]; i += 1
    # 회사 발표 요약을 먼저 번역 (몇십 편뿐인데, 뒤에 두면 시간이 모자라 영어로 남았음)
    kpost = translate_texts(run, [(p.get("sum") or "")[:400] for p in en_posts], mem, deadline)
    for p, v in zip(en_posts, kpost):
        if v: p["ksum"] = v
    kabs = translate_texts(run, [p["abs"] for p in top] + [p.get("sum") or "" for p in hf], mem, deadline)
    for k, p in enumerate(top): p["kabs"] = kabs[k]
    for k, p in enumerate(hf): p["ksum"] = kabs[len(top) + k]
    # 용어카드의 영문 위키 문단 → 한국어 (한국어판이 없는 용어만)
    terms = rj(OUT / "terms.json", [])
    en_terms = [t for t in terms if t.get("wiki") and t.get("wiki_lang") == "en" and not t.get("wiki_ko_text")]
    if en_terms:
        kw = translate_texts(run, [t["wiki"] for t in en_terms], mem, deadline)
        for t, k in zip(en_terms, kw):
            if k: t["wiki_ko_text"] = k
        wj(OUT / "terms.json", terms); log(f"용어 위키 문단 번역 {sum(1 for k in kw if k)}/{len(en_terms)}")
    if len(mem) > 60000: mem = dict(list(mem.items())[-45000:])
    if run is not None: wj(OUT / "_tr.json", mem)

    # 4. 유튜브
    ytc = rj(OUT / "_yt.json", {})
    n = youtube_links(top, ytc)
    if len(ytc) > 3000: ytc = dict(list(ytc.items())[-2500:])
    wj(OUT / "_yt.json", ytc); log(f"유튜브 검색 {n}편")

    # 4-2. 유튜브: AI 새 기능 해설 영상 (한국어, 최근 3일, 조회수 순)
    data["vids"] = ai_feature_videos(prev.get("vids", []))
    try:                                                          # 해설 영상마다 유튜브 베스트 댓글 5개 (할당량 1, 12시간 기억)
        from ytcomments import Comments
        CM = Comments(OUT / "_cm.json", os.environ.get("YOUTUBE_API_KEY"), budget=40)
        for v in data["vids"]:
            v["cm"] = CM.get(v.get("vid"))
            if CM.short(v.get("vid")): v["short"] = 1
        CM.save()
    except Exception as e: print("베스트 댓글 실패 — 건너뜀:", e)

    # 5. 저장
    for p in top: p["one"] = (p.get("ksum") or p.get("kabs") or "").split(". ")[0][:160] or None
    data["papers"] = top; data["counts"] = {"hf": len(hf), "arxiv": len(arx), "posts": len(data["posts"]), "repos": len(data["repos"]), "news": len(data["news"]), "more": len(rest)}
    data["translated"] = run is not None
    wj(DAYS / f"{day}.json", data)
    wj(DAYS / f"{day}_more.json", {"day": day, "papers": rest})
    archive()
    broken = {k: v for k, v in health.items() if v.get("n", 0) >= 3}                         # 3일 넘게 계속 실패
    idx = {"at": now_iso(), "today": day, "days": sorted(f.stem for f in DAYS.glob("????-??-??.json")), "archive": sorted(f.stem for f in ARCH.glob("*.json")),
           "broken": broken, "counts": data["counts"], "ytKey": bool(os.environ.get("YOUTUBE_API_KEY")), "sources": {k: POST_HOME[k] for k in POST_HOME}}
    wj(OUT / "_index.json", idx); wj(OUT / "_health.json", health)
    write_feed(data)
    wj(OUT / "_meta.json", {"updatedAt": now_iso(), "by": "ai-robot", "label": f"{day} 새벽판"})
    log(f"끝 {round(time.time() - t0)}초 · HF {len(hf)} · arXiv {len(arx)} · 고장 {len(broken)}개")


if __name__ == "__main__":
    main()
