"""tgemma.py — 구글 TranslateGemma 4B 무료 번역기 (공개 모델을 로봇 안에서 직접 돌림 · 토큰 0 · 횟수 한도 없음).

구글 번역 연구팀이 2026-01 공개한 번역 전용 모델(Gemma 3 기반, 55개 언어)을 4비트로 줄인 GGUF 파일을
llama.cpp(llama-cpp-python)로 CPU에서 돌립니다. 한도는 '시간'뿐 → TG_MINUTES(기본 20분) 안에서만 쓰고,
넘으면 None 을 돌려줘서 부르는 쪽이 예전 NLLB 로 이어 번역합니다 (번역이 빠지는 일 없음).

  from tgemma import TG
  tg = TG.get()                     # 모델·라이브러리가 없으면 None
  ko = tg.tr("Hello world", "en")   # 예산이 다 됐거나 실패하면 None

  TG_OFF=1        끄기 (예전 NLLB 만)
  TG_MINUTES=20   이번 실행에서 이 번역기에 쓸 분
  TG_GGUF=경로     모델 파일 위치 (기본 /tmp/tgemma/…gguf, 워크플로가 캐시)

같은 파일이 vendingForMe·vfm-story 두 저장소에 있음 — 고치면 둘 다.
"""
from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path

MODEL_URL = "https://huggingface.co/bullerwins/translategemma-4b-it-GGUF/resolve/main/translategemma-4b-it-Q4_K_M.gguf"
GGUF = Path(os.environ.get("TG_GGUF", "/tmp/tgemma/translategemma-4b-it-Q4_K_M.gguf"))

# 모델 안내문에 쓰는 언어 이름 (TranslateGemma 55개 언어 중 자판기에서 쓰는 것)
NAMES = {"en": "English", "ko": "Korean", "ja": "Japanese", "zh": "Chinese", "zh-tw": "Chinese", "zh-cn": "Chinese", "es": "Spanish",
         "fr": "French", "de": "German", "ru": "Russian", "ar": "Arabic", "pt": "Portuguese", "id": "Indonesian", "hi": "Hindi",
         "bn": "Bengali", "tr": "Turkish", "vi": "Vietnamese", "th": "Thai", "it": "Italian", "pl": "Polish", "nl": "Dutch",
         "uk": "Ukrainian", "fa": "Persian", "he": "Hebrew", "sv": "Swedish", "cs": "Czech", "el": "Greek", "ro": "Romanian",
         "hu": "Hungarian", "da": "Danish", "fi": "Finnish", "no": "Norwegian", "ms": "Malay", "tl": "Filipino", "sw": "Swahili"}
CODE = {"zh-tw": "zh-TW", "zh-cn": "zh"}
SENT = re.compile(r"(?<=[.!?。！？])\s+")


def log(*a):
    print("[번역기]", *a, flush=True)


def _download():
    import requests
    GGUF.parent.mkdir(parents=True, exist_ok=True)
    tmp = GGUF.with_suffix(".part")
    log("모델 받는 중 (처음 한 번, 약 2.5GB)…")
    with requests.get(MODEL_URL, stream=True, timeout=60, headers={"User-Agent": "vfm-robot/1.0"}) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 22):
                f.write(chunk)
    tmp.replace(GGUF)


def chunks(text: str, n: int = 1100):
    """긴 글은 문장 경계에서 n자 안쪽으로 나눔 (모델 문맥 2K 토큰)."""
    text = re.sub(r"[ \t]+", " ", text or "").strip()
    if len(text) <= n:
        return [text] if text else []
    out, cur = [], ""
    for s in SENT.split(text):
        while len(s) > n:                                            # 문장 하나가 너무 길면 쉼표에서
            cut = max(s.rfind(", ", 0, n), s.rfind("; ", 0, n), s.rfind("、", 0, n))
            cut = cut if cut > n // 3 else n
            if cur:
                out.append(cur); cur = ""
            out.append(s[:cut + 1].strip()); s = s[cut + 1:].strip()
        if len(cur) + len(s) + 1 > n and cur:
            out.append(cur); cur = s
        else:
            cur = (cur + " " + s).strip()
    if cur:
        out.append(cur)
    return out


class TG:
    _inst = None
    _tried = False

    @classmethod
    def get(cls):
        if cls._tried:
            return cls._inst
        cls._tried = True
        if os.environ.get("TG_OFF") or "--no-translate" in sys.argv:
            return None
        try:
            from llama_cpp import Llama
        except Exception as e:  # noqa: BLE001
            log(f"llama-cpp 없음 → 예전 번역기(NLLB)로 ({e})"); return None
        try:
            if not GGUF.exists():
                _download()
            t = time.time()
            llm = Llama(model_path=str(GGUF), n_ctx=3072, n_threads=os.cpu_count() or 2, n_batch=512, verbose=False)
            log(f"TranslateGemma 4B 준비 ({time.time() - t:.0f}초, CPU {os.cpu_count()}개)")
        except Exception as e:  # noqa: BLE001
            log(f"모델을 못 열었음 → 예전 번역기(NLLB)로 ({e})"); return None
        cls._inst = cls(llm)
        return cls._inst

    def __init__(self, llm):
        self.llm = llm
        self.t0 = time.time()
        self.budget = float(os.environ.get("TG_MINUTES", "20")) * 60
        self.n = 0
        self.chars = 0
        self.spent = 0.0
        self.warned = False

    def ok(self):
        if time.time() - self.t0 < self.budget:
            return True
        if not self.warned:
            self.warned = True
            log(f"시간 예산 {self.budget / 60:.0f}분을 다 씀 → 나머지는 예전 번역기로 · 이번에 {self.n}건 {self.chars:,}자")
        return False

    def _prompt(self, text, src, tgt):
        s, t = NAMES[src], NAMES[tgt]
        sc, tc = CODE.get(src, src), CODE.get(tgt, tgt)
        return (f"<start_of_turn>user\nYou are a professional {s} ({sc}) to {t} ({tc}) translator. Your goal is to accurately convey the meaning "
                f"and nuances of the original {s} text while adhering to {t} grammar, vocabulary, and cultural sensitivities.\n"
                f"Produce only the {t} translation, without any additional explanations or commentary. Please translate the following {s} text "
                f"into {t}:\n\n\n{text.strip()}<end_of_turn>\n<start_of_turn>model\n")

    def tr(self, text, src="en", tgt="ko", deadline=None):
        """글 하나 → 번역 (None = 못 함: 예산 끝·지원 안 하는 언어·실패)."""
        src = (src or "en").lower()
        if src == tgt or src not in NAMES or tgt not in NAMES:
            return None
        parts = chunks(text)
        if not parts:
            return ""
        out = []
        for p in parts:
            if not self.ok() or (deadline and time.time() > deadline):
                return None
            t = time.time()
            try:
                r = self.llm(self._prompt(p, src, tgt), max_tokens=min(1400, int(len(p) * 1.6) + 64), temperature=0.0,
                             top_k=1, repeat_penalty=1.05, stop=["<end_of_turn>", "<start_of_turn>"])
                y = r["choices"][0]["text"].strip()
            except Exception as e:  # noqa: BLE001
                log(f"실패: {e}"); return None
            self.spent += time.time() - t
            if not y:
                return None
            out.append(y)
        self.n += 1
        self.chars += len(text)
        return " ".join(out)

    def many(self, texts, src="en", tgt="ko", deadline=None):
        """[글] → [번역 또는 None] (예산 다 되면 그 뒤는 None)."""
        res = []
        for x in texts:
            res.append(self.tr(x, src, tgt, deadline) if x else x)
        return res
