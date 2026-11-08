# 이야기 자판기 (vfm-story)

**이야기 · 역사 · 뇌** — 자판기를 세 사이트로 나눈 것 중 하나예요 (2026-11-08). 서버 없이 GitHub 하나로 돌아가요 (카드 결제 0원, 유지 토큰 0).
- 주소: https://jeffreryinko.github.io/vfm-story/
- 다른 자판기: [시사 자판기](https://jeffreryinko.github.io/vendingForMe/) (시사·도구·AI) · [사람 자판기](https://jeffreryinko.github.io/vfm-mind/) (배댓·맨탈)
- 같은 주소(jeffreryinko.github.io)라서 폰에 저장된 별표·메모·보관함은 세 사이트가 함께 써요.

| 로봇 | 무엇 | 언제 |
|---|---|---|
| 역사 로봇 `robot/history_run.py` | 한국어 위키백과 역사 글 전부 받아 자르고 분류 | 매일 05:00 (`history.yml`) |
| 이야기 위키 로봇 `robot/iyagi_wiki.py` | 이야기 목록 약 1,500개를 위키백과에서 모아 정리, 영어 문서는 무료 번역(NLLB). **예전 클로드 '작가' 예약 작업 대신** · 요청 들어온 이야기 먼저 | 매일 03:40 (`iyagi-wiki.yml`) |
| 원문 번역 로봇 `robot/iyagi_translate.py` | 고전 원문 기계번역 | 주 2회 (`iyagi-orig.yml`) |
| 뇌 로봇 `robot/brain_run.py` | 뇌과학 소식 + 부위 찾기 | 07:20 · 19:20 (`brain.yml`) |

## 역사 탭 자료 (`data/history/`)
본문은 한국어 위키백과(CC BY-SA 4.0), 속성은 위키데이터(CC0). 색인 한 줄은 배열 — 칸 순서는 `_index.json` 의 `cols`.
- `pages/xx/k<번호>.json` 글 한 편 (요약·단락·연도·나라·테마·관계·출처). 용량 한도(`HIST_BUDGET_MB`, 380MB)를 넘은 뒤 받은 글은 요약판(`full:false`) — 화면이 본문을 위키백과에서 바로 불러옴
- `idx/<권역>-<시대>.json` 권역×시대 목록 · `cty/<나라>.json` 나라별(연도순) · `dec/<연대>.json` 같은 시기 · `th/<테마>.json` · `tag/B|P.json` 야사·대명사 · `s/<첫 글자>.json` 제목 찾기 · `days/MM-DD.json` 역사 속 오늘 · `top.json` 첫 화면
- `_state/` 로봇 기억: `pages.tsv` 받은 글 · `queue.tsv` 받을 차례 · `skip.tsv` 뺀 글(이유) · `closure.json` 하위 종류 표 · `countries.json`·`labels.json` 위키데이터 캐시 · `seeds.json` 종자 시각 · `health.json` 출처 건강
- 처음 큰 수확: Actions → 역사 로봇 → Run workflow (기본값). 한 회차 약 5시간, 남으면 스스로 다음 회차(최대 30회). 그 뒤 매일 새벽 5시

## 도구 탭 자료 (`data/tools/`)
- `now.json` 지금 화면 — `sec.<구역>` 목록(gh·gn·hn·yt·list·hf·rd) + `hot`('지금 뜨는 것' id 18개)
- `days/<날짜>.json` 그날 처음 본 것 (찾기용, 30일) · `lists/<id>.json` 모음집 전체(번역 포함)
- `_state/stars.tsv` 저장소별 지난 별 수(하루 +N 계산) · `_state/awesome.json` 모음 목록에 이미 있던 줄(처음 돌 때 있던 건 `0` = 새 항목 아님) · `_state/yt.json` 하루 한 번 검색 결과
- 유튜브 채널 더하기: 채널 주소(@이름)에서 UC로 시작하는 ID를 찾아 `robot/tools_sources.py` 의 `CHANNELS` 에 한 줄

## 뇌 탭 자료 (`data/brain/`)
- `regions.json` 부위 52개(1단계 12 + 2단계 40): 이름·영어·뜻풀이·한 줄·하는 일·비유·어디쯤·다치면·짝·기사 낱말. 원본은 `robot/brain_regions.py` → `python robot/brain_build.py --text`
- `atlas.json` + `img/*.webp` 평면 그림 6면(옆면·안쪽 면·아래 면 = 입체 음영 / 앞 단면·해마 단면·가로 단면 = MRI) — 조각(atom)별 SVG 경로와 넓이. `mesh.bin`·`mesh.json` 3D 조각 92개(약 1MB)
  - 재료: MNI152 표준 뇌 1mm, AAL·Harvard-Oxford 피질하·JHU 백질(neuroparc 저장소), 배경 MRI 는 nilearn 내장 MNI152 2009. 작은 핵(시상하부·흑질·복측피개영역·청반·솔기핵·뇌하수체·송과선)은 논문 좌표에 대략 크기로
  - 다시 만들기: neuroparc 를 받아 `python robot/brain_build.py --atlas <neuroparc 경로>` (nibabel·nilearn·scikit-image·trimesh·fast-simplification 필요)
- `news.json` 소식 30일치(부위 `rs` 붙음) · `_index.json` 부위별 기사 수·출처 상태 · `wiki.json` 위키백과 첫 문단
- 외우기 기록은 폰 `vfm:brain:*` (srs = 부위별 상자·다음 복습일). 구글 로그인하면 기기끼리 맞춤
- 가족 점수판: Supabase 표 `brain_board` — 만드는 SQL 은 `robot/brain_board.sql` (한 번만 실행)
