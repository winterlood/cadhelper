---
name: ch-sketchup
description: SketchUp 모델을 확인·집계·수정할 때 사용 (예: "스케치업 모델 타일 면적", "스케치업에서 이거 바꿔줘", "스케치업 화면 보여줘")
---

# SketchUp 작업

1. `sketchup_status` 로 연결 확인. 연결 안 되면: "SketchUp을 켜고 파일을 열어 주세요. 그래도 안 되면 SketchUp을 껐다 다시 켜 주세요."
2. 질문(읽기만): `sketchup_model_info` — 재질별/태그별 면적(㎡), 그룹·컴포넌트 개수. 면 하나하나를 센 값이라 두께 있는 판은 양면이 다 들어갈 수 있음을 알린다.
3. 화면 확인: `sketchup_capture`
4. 수정: 반드시 대화로 먼저 무엇을 바꿀지 설명하고 동의 → `sketchup_run_ruby(code, purpose)` (확인창 뜸). purpose 는 아빠가 읽을 한 문장.
   - 코드는 짧게, 한 번에 한 가지 일. 길이 단위는 `.mm` 사용 (예: `100.mm`).
   - 결과는 `sketchup_capture` 로 확인. 잘못되면 SketchUp에서 Ctrl+Z 한 번으로 되돌릴 수 있다고 안내 (한 번의 실행 = 한 번의 실행취소).
5. 저장: 원본을 덮어쓰지 말고 `sketchup_save_copy` 로 사본 저장.
