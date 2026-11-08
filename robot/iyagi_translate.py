"""iyagi_translate.py — 원문 읽기(영어 공공 영역 책)를 한국어로 기계번역 (토큰 0).

모델: 구글 TranslateGemma 4B (robot/tgemma.py, 공개 모델 GGUF, 문단 단위·중간 저장해서 여러 실행에 걸쳐 이어 번역)
      → 라이브러리가 없으면 예전 facebook/nllb-200-distilled-600M (CTranslate2 int8).
GitHub Actions 무료 러너(2코어)에서 1초에 약 300~500자. 한 번 실행에 한 권(또는 시간 한도까지)만 번역하고,
결과를 data/iyagi/orig/k<책id>-<부>.json 으로 저장합니다. 원문 문단(p 배열)과 1:1로 맞춥니다.

  python robot/iyagi_translate.py --max-minutes 300        # 아직 번역 안 된 책 중 짧은 것부터
  python robot/iyagi_translate.py --book g1727             # 특정 책
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ORIG = ROOT / "data/iyagi/orig"
MODEL_DIR = Path(os.environ.get("NLLB_CT2_DIR", "/tmp/nllb-600m-ct2"))
HF_MODEL = "facebook/nllb-200-distilled-600M"
SENT_SPLIT = re.compile(r"(?<=[.!?”\"’'])\s+(?=[A-Z“\"‘'\(\[])")


def ensure_model():
    if (MODEL_DIR / "model.bin").exists():
        return
    print("모델 변환 중 (처음 한 번, 몇 분 걸림)…", flush=True)
    import subprocess
    subprocess.run(["ct2-transformers-converter", "--model", HF_MODEL, "--output_dir", str(MODEL_DIR),
                    "--quantization", "int8", "--force"], check=True)


def split_sentences(par: str):
    par = re.sub(r"\s+", " ", par).strip()
    if not par:
        return []
    out = []
    for s in SENT_SPLIT.split(par):
        s = s.strip()
        while len(s) > 600:                       # 너무 긴 문장은 쉼표·세미콜론에서 자름
            cut = max(s.rfind(", ", 0, 600), s.rfind("; ", 0, 600))
            if cut < 100: cut = 600
            out.append(s[:cut + 1].strip()); s = s[cut + 1:].strip()
        if s: out.append(s)
    return out


def translate_book(book_id: str, deadline: float):
    import ctranslate2, transformers
    tok = transformers.AutoTokenizer.from_pretrained(HF_MODEL, src_lang="eng_Latn")
    tr = ctranslate2.Translator(str(MODEL_DIR), device="cpu", compute_type="int8", inter_threads=1, intra_threads=os.cpu_count() or 2)
    tgt = tok.convert_ids_to_tokens(tok.convert_tokens_to_ids(["kor_Hang"]))
    parts = sorted(ORIG.glob(f"{book_id}-*.json"), key=lambda p: int(p.stem.split("-")[1]))
    for part in parts:
        out = ORIG / f"k{part.name}"
        if out.exists():
            continue
        paras = json.loads(part.read_text(encoding="utf-8"))["p"]
        # 문장 단위로 펼침 (문단 경계는 기억)
        sents, owner = [], []
        for i, p in enumerate(paras):
            if p.strip().startswith("[Illustration"):
                continue
            for s in split_sentences(p):
                sents.append(s); owner.append(i)
        done = ["" for _ in paras]
        res = [""] * len(sents)
        order = sorted(range(len(sents)), key=lambda k: len(sents[k]))   # 비슷한 길이끼리 묶으면 빠름
        B = 24; t0 = time.time(); chars = 0
        for b in range(0, len(order), B):
            if time.time() > deadline:
                print(f"  시간 한도 — {part.name} 중단(다음 실행에 이어서)", flush=True); return False
            idxs = order[b:b + B]
            toks = [tok.convert_ids_to_tokens(tok.encode(sents[k])) for k in idxs]
            outs = tr.translate_batch(toks, target_prefix=[tgt] * len(toks), beam_size=2, max_decoding_length=512)
            for k, o in zip(idxs, outs):
                hyp = o.hypotheses[0][1:] if o.hypotheses[0][:1] == tgt else o.hypotheses[0]
                res[k] = tok.decode(tok.convert_tokens_to_ids(hyp), skip_special_tokens=True).replace("⁇", "")
                chars += len(sents[k])
            if (b // B) % 20 == 0:
                el = time.time() - t0; print(f"  {part.name} {b}/{len(sents)} 문장, {int(chars / max(el, 1))}자/초", flush=True)
        for k, i in enumerate(owner):
            done[i] = (done[i] + " " + res[k]).strip()
        for i, p in enumerate(paras):
            if p.strip().startswith("[Illustration"):
                done[i] = "[사진]"
        out.write_text(json.dumps({"p": done}, ensure_ascii=False), encoding="utf-8")
        print(f"  저장 {out.name} ({len(paras)} 문단)", flush=True)
    return True


def translate_book_tg(tg, book_id: str, deadline: float):
    """구글 TranslateGemma 로 한 권 — 문단(길면 문장 묶음) 단위, 중간 저장해서 다음 실행에 이어서."""
    parts = sorted(ORIG.glob(f"{book_id}-*.json"), key=lambda p: int(p.stem.split("-")[1]))
    for part in parts:
        out = ORIG / f"k{part.name}"
        if out.exists():
            continue
        paras = json.loads(part.read_text(encoding="utf-8"))["p"]
        prog_p = ORIG / f"_tg_{part.stem}.json"                      # 중간 저장 (끝나면 지움)
        prog = json.loads(prog_p.read_text(encoding="utf-8")) if prog_p.exists() else {}
        t0 = time.time(); chars = 0; last_save = time.time()
        for i, p in enumerate(paras):
            k = str(i)
            if k in prog:
                continue
            if p.strip().startswith("[Illustration"):
                prog[k] = "[사진]"; continue
            if time.time() > deadline or not tg.ok():
                prog_p.write_text(json.dumps(prog, ensure_ascii=False), encoding="utf-8")
                print(f"  시간 한도 — {part.name} {len(prog)}/{len(paras)} 문단에서 멈춤(다음 실행에 이어서)", flush=True)
                return False
            y = tg.tr(re.sub(r"\s+", " ", p).strip(), "en", "ko", deadline)
            if y is None:
                prog_p.write_text(json.dumps(prog, ensure_ascii=False), encoding="utf-8")
                return False
            prog[k] = y; chars += len(p)
            if time.time() - last_save > 120:
                prog_p.write_text(json.dumps(prog, ensure_ascii=False), encoding="utf-8"); last_save = time.time()
                el = time.time() - t0
                print(f"  {part.name} {len(prog)}/{len(paras)} 문단, {int(chars / max(el, 1))}자/초", flush=True)
        done = [prog.get(str(i), "") for i in range(len(paras))]
        out.write_text(json.dumps({"p": done, "eng": "translategemma-4b"}, ensure_ascii=False), encoding="utf-8")
        prog_p.unlink(missing_ok=True)
        print(f"  저장 {out.name} ({len(paras)} 문단, 구글 TranslateGemma)", flush=True)
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book")
    ap.add_argument("--max-minutes", type=int, default=300)
    a = ap.parse_args()
    deadline = time.time() + a.max_minutes * 60 - 120
    index_path = ORIG / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    todo = [o for o in index if not o.get("tr")]
    todo.sort(key=lambda o: o.get("chars", 0))
    if a.book:
        todo = [o for o in index if o["id"] == a.book]
    if not todo:
        print("번역할 책이 없어요"); return
    try:
        from tgemma import TG
        tg = TG.get()
    except Exception:
        tg = None
    if tg is None:
        ensure_model()
    # 구글 번역기로 하다 만 책을 먼저 (중간 저장이 있는 책)
    todo.sort(key=lambda o: (0 if any(ORIG.glob(f"_tg_{o['id']}-*.json")) else 1, o.get("chars", 0)))
    for o in todo:
        if time.time() > deadline: break
        print(f"책: {o['ko']} ({o['id']}, {o.get('chars', 0):,}자)", flush=True)
        ok = translate_book_tg(tg, o["id"], deadline) if tg is not None else translate_book(o["id"], deadline)
        parts_done = all((ORIG / f"k{o['id']}-{n}.json").exists() for n in range(1, o.get("parts", 1) + 1))
        if parts_done:
            o["tr"] = 1
            if tg is not None: o["eng"] = "translategemma-4b"
            index_path.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
            print(f"완료: {o['ko']}", flush=True)
        if not ok:
            break


if __name__ == "__main__":
    main()
