"""brain_stories.py — '생각·주의력 이야기' 카드 75장 만들기 (토큰 0, 손으로 한 번 돌림)

원본: robot/brain_stories_src.md (주현이 정리한 《생각의 탄생》·《ADHD 2.0》 등 인물 일화 카드 아카이브)
결과: data/brain/stories.json  →  뇌 탭 '이야기' + 홈 랜덤 카드

    python robot/brain_stories.py

카드마다: 번호·제목·책·장·인물 및 분야·상세 스토리·핵심 통찰 + 이야기에 나온 뇌 부위(부위 표 낱말로 찾음)
원본을 고치면 이 명령만 다시 돌리면 됩니다.
"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "robot"))
from brain_run import regions_of  # noqa: E402

SRC = ROOT / "robot/brain_stories_src.md"
OUT = ROOT / "data/brain/stories.json"

BOOK = {1: "생각의 탄생", 2: "ADHD 2.0 · 뇌과학", 3: "확장 에피소드"}
# 3부(확장)는 카드마다 어느 책 쪽인지 낱말로 가름
ADHD_W = re.compile(r"ADHD|주의력|할로웰|레이티|실행 기능|도파민|뇌|소뇌|난독증|임상|진단|환자|약물|BDNF|운동")


def clean(s):
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", s or "")
    return re.sub(r"\s+", " ", s).strip()


def main():
    part, ch, cards, cur = 0, "", [], None
    for line in SRC.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^## PART (\d)", line)
        if m: part = int(m.group(1)); ch = ""; continue
        m = re.match(r"^### (.+)", line)
        if m: ch = clean(m.group(1)); continue
        m = re.match(r"^#### \**Card (\d+)\.\s*(.+?)\**\s*$", line)
        if m:
            cur = {"n": int(m.group(1)), "title": clean(m.group(2)), "part": part, "ch": ch}; cards.append(cur); continue
        m = re.match(r"^\*\s+\*\*(인물 및 분야|상세 스토리|핵심 통찰):\*\*\s*(.*)", line)
        if m and cur is not None:
            cur[{"인물 및 분야": "who", "상세 스토리": "story", "핵심 통찰": "insight"}[m.group(1)]] = clean(m.group(2))
    out = []
    for c in cards:
        who = c.get("who", "")
        person, field = (who.rsplit(" / ", 1) + [""])[:2] if " / " in who else (who, "")
        book = c["part"] if c["part"] in (1, 2) else (2 if ADHD_W.search(c["title"] + " " + who) else 1)
        ch = c["ch"]
        if ch:   # "[1장 & 2장] 생각 다시 생각하기 & 상상력 교육 (Rethinking…)" → "1~2장 · 생각 다시 생각하기 & 상상력 교육"
            m2 = re.match(r"\[([^\]]+)\]\s*(.*)", ch)
            num = re.sub(r"\s*(&|~)\s*", "~", m2.group(1)).replace("장~", "~") if m2 else ""
            name = re.split(r"\s+\(|\s+—", m2.group(2) if m2 else ch)[0].strip()
            ch = f"{num} · {name}" if num else name
        else:
            ch = "확장 에피소드" if c["part"] == 3 else ""
        out.append({"id": f"c{c['n']:03d}", "n": c["n"], "title": c["title"], "book": BOOK[book] if c["part"] != 3 else BOOK[book],
                    "ext": c["part"] == 3, "ch": ch, "who": person.strip(), "field": field.strip(),
                    "story": c.get("story", ""), "insight": c.get("insight", ""),
                    "rs": regions_of(c["title"] + " " + c.get("story", "") + " " + c.get("insight", ""))})
    miss = [c["id"] for c in out if not (c["story"] and c["insight"])]
    OUT.write_text(json.dumps({"v": 1, "src": "주현 정리 · 《생각의 탄생》(로버트·미셸 루트번스타인), 《ADHD 2.0》(에드워드 할로웰·존 레이티) 외",
                               "items": out}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"카드 {len(out)}장 → {OUT.relative_to(ROOT)} ({OUT.stat().st_size // 1024}KB) · 부위 붙은 카드 {sum(1 for c in out if c['rs'])}장 · 빈 칸 {miss}")


if __name__ == "__main__":
    main()
