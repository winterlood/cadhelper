# CAD도우미 (CadHelper)

인테리어 사무소에서 **Codex(AI)에게 말로 AutoCAD · SketchUp · 엑셀 작업을 시키기** 위한 원클릭 설치 키트입니다.
컴퓨터가 서툰 실무자도 쓸 수 있도록, 설치는 더블클릭 한 번이고 도면을 바꾸는 작업은 항상 사람이 확인창에서 허락해야 실행됩니다.

> Windows 10/11 전용 · AutoCAD 정식판(COM 지원, LT 제외) · SketchUp 2017 이상(데스크톱) · OpenAI Codex 데스크톱/CLI

## 할 수 있는 일

| 기능 | 예시 질문 |
|---|---|
| 도면 수치 | "지금 열린 도면 실별 면적이랑 전체 평수 알려줘" · "이거 선택했는데 면적 얼마야?" |
| 엑셀 | "바닥 강마루랑 도배 견적서 엑셀로 만들어줘" (수식 살아 있는 견적서) · 면적표 · 물량표 |
| 고객용 3D | "고객한테 보여줄 3D 만들어줘, 천장고 2300" → 도면에서 **자동 초안**(벽·실별 바닥 마감·창 개구부·문·가구·한글 실명·면적 요약)을 만든 뒤 인터넷 없이 열리는 HTML 한 파일로 (마우스 올리면 규격·크기 표시) |
| SketchUp | 같은 장면을 SketchUp 모델로 생성 · 재질별/윗면 면적 집계(바닥재 물량) · 캡처 |
| AutoCAD 3D | 같은 장면을 레이어 유지한 3D DXF로 |
| 도면 수정 | 그리기·레이어 정리·삭제 — **항상 Windows 확인창에서 '예'를 눌러야 실행** |
| 쓸수록 똑똑해짐 | 단가·회사 정보·고쳐준 점을 기억, 반복되는 작업은 스스로 스킬로 저장 |

## 설치

1. [Releases](../../releases)에서 `CadHelper-*.zip` 을 받아 **바탕화면 등 아무 곳에** 압축을 풉니다. (`C:\work` 안에는 풀지 마세요)
2. `설치하기.cmd` 더블클릭 → 5~10분 기다림 (Python이 없으면 자동 설치, 인터넷 필요)
3. Codex를 완전히 껐다 켭니다. SketchUp도 껐다 켭니다.
4. 처음 한 번만: Codex 데스크톱 앱에서 **프로젝트 추가 → `C:\work`** 폴더 선택 (이후 이 프로젝트에서 대화)
5. `C:\work\CAD도우미 점검` 으로 상태 확인

자세한 사용법은 함께 들어 있는 **`CAD도우미 사용설명서.pdf`**, AI를 처음 쓰는 분은 **`AI 사용 안내서.pdf`** 를 보세요.
제거는 `제거하기.cmd` (결과물·백업·배운 내용은 남겨 둠).

## 설치하면 바뀌는 것

모든 것이 **`C:\work` 프로젝트 폴더 안**에 설치됩니다. (C:\ 에 폴더를 만들 수 없는 PC면 바탕화면 `work`)

| 위치 | 내용 |
|---|---|
| `C:\work\AGENTS.md` | Codex 규칙 (안전 규칙·학습 규칙). 표시된 블록만 관리하고 직접 쓴 내용은 보존 |
| `C:\work\.codex\config.toml` | CAD도우미 연결 (stdio MCP 서버 — Codex가 직접 실행, 포트·별도 창 없음). 표시된 블록만 관리 |
| `C:\work\.codex\skills\ch-*` | 기본 스킬 6개 + 사용하며 생기는 `ch-learned-*` |
| `C:\work\.cadhelper\` | 프로그램(app), Python 가상환경(venv), 백업(backups), 배운 내용(knowledge), 기록(logs) |
| `C:\work\결과물\` | 엑셀·3D·사진 결과물 |
| `C:\work\` | `CAD도우미 점검` 바로가기, PDF 설명서 |

work 밖에는 꼭 필요한 것만 둡니다:

| 위치 | 내용 |
|---|---|
| `~/.codex/config.toml` | `C:\work` 신뢰 등록 블록 하나 (Codex는 신뢰한 폴더의 `.codex` 설정만 읽음). 처음 설치 전 원본은 `config.toml.bak-cadhelper` |
| `%APPDATA%\SketchUp\SketchUp 20xx\SketchUp\Plugins\cadhelper_bridge.rb` | SketchUp 연결 플러그인 — SketchUp이 이 폴더에서만 읽어서 work 밖에 둠 (127.0.0.1 전용, 토큰 인증) |
| 바탕화면 | `work` 바로가기 |

도면 파일(내 문서·바탕화면 등)은 읽기만 합니다. 도면 열기·수정은 CAD도우미 도구가 확인창을 거쳐서 하고, Codex 셸에는 work 밖 쓰기 권한을 주지 않습니다.
v1.0.0(사용자 폴더 설치)에서 업데이트하면 결과물·백업·배운 내용·배운 스킬을 work로 옮기고 예전 전역 설정을 정리합니다.

## 안전장치

AI가 지시를 무시해도 막히도록 **MCP 서버 자체가** 강제합니다.

- 도면·모델을 바꾸는 도구(그리기, 삭제, 속성 변경, 명령 실행, 저장, SketchUp 코드 실행·생성)는 실행 직전 **Windows 확인창**이 뜨고 '예'일 때만 실행. 확인창에는 **대상 도면 이름**과 변경 내용(SketchUp은 실행할 코드 원문)이 표시됩니다.
- 9분 안에 답하지 않으면 '아니요'로 처리 (AI가 포기한 뒤 늦게 눌러 실행되는 일 방지). 확인 중 활성 도면이 바뀌면 실행 취소.
- 첫 변경 전 원본 DWG 자동 백업. 결과물은 항상 새 파일(덮어쓰기 없음).
- SketchUp 코드에서 파일·프로세스·네트워크 접근, 저장·종료는 차단.
- 모든 확인 요청과 응답은 `CadHelper\logs\approvals.jsonl` 에 기록.
- 읽기 도구는 AutoCAD를 몰래 켜거나 빈 도면을 만들지 않으며, 화면 캡처·PDF 출력 후 출력 설정을 원래대로 되돌립니다.

## 구조

```
설치하기.cmd / 제거하기.cmd     더블클릭 실행 (PowerShell 5.1)
app/
  cadhelper_server.py           MCP 서버 (stdio, FastMCP)
  cadhelper/
    safety.py                   확인창 게이트 + 백업
    analysis.py                 면적·길이·실별 면적(폴리선 / 벽선 기반)·블록·문자·평면 추출
    excel.py                    견적서(수식) / 표
    draft.py                    열린 도면 → 3D 장면 자동 초안
    scene.py                    장면 JSON → 3D HTML / DXF / SketchUp (창 개구부 자동 처리)
    sketchup.py                 SketchUp 플러그인 클라이언트
    learn.py                    학습 메모리 + 스킬 저장
  sketchup_plugin/cadhelper_bridge.rb
  templates/viewer.html         오프라인 3D 뷰어 (three.js r128 내장)
  vendor/                       AutoCAD 2D 작도 도구 (Erfouni/AutoCAD-AI, MIT)
codex/AGENTS.md, codex/skills/  Codex 규칙과 스킬
docs/                           설명서 원본(HTML) → PDF
```

## 호환성

- **AutoCAD**: 2018 ~ 2027 정식판(및 Architecture 등 버티컬). 여러 버전이 깔려 있거나 COM 등록이 꼬여 있어도, 버전 무관 ProgID → 버전별 ProgID(26 ~ 22) 순서로 **지금 켜져 있는 AutoCAD**를 찾아 연결합니다. ZWCAD · GstarCAD · BricsCAD도 같은 방식으로 연결을 시도합니다(미검증).
- **AutoCAD LT**: 외부 자동화(COM)가 막혀 있어 도면 직접 조작은 불가. 설치 시 자동으로 알려 줍니다.
- **SketchUp**: 2017 이상 데스크톱판(Pro/Make). Windows 설치 목록과 Program Files, `%APPDATA%` 를 모두 확인해 설치 위치·드라이브와 무관하게 플러그인을 넣습니다. 웹판(SketchUp Free)은 불가.
- 설치 시 감지된 프로그램과 버전을 화면에 보여 주고, `C:\work\CAD도우미 점검` 에서도 확인할 수 있습니다.

## 확인된 환경

Windows 11 · AutoCAD 2027 · SketchUp 2027 · Codex CLI 0.167 · Python 3.14 에서 설치·실전 테스트(면적 질의, 3D 생성, SketchUp 생성, 확인창 승인/거부).
AutoCAD COM과 SketchUp Ruby API는 버전 간 호환되므로 AutoCAD 2024 / SketchUp 2024 등에서도 동작하도록 만들었지만, 해당 버전에서 직접 테스트하지는 않았습니다.

## 라이선스

MIT. `app/vendor/` 는 [Erfouni/AutoCAD-AI](https://github.com/Erfouni/AutoCAD-AI) (MIT) 코드이며 원 라이선스는 `app/vendor/LICENSE`, three.js는 MIT.
