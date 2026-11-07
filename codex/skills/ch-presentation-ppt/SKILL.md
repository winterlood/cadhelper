---
name: ch-presentation-ppt
description: 고객용 PPT(파워포인트) 제안서·디자인 설명·시공 계획·견적 요약 발표자료를 만들 때 사용 (예: "고객한테 보여줄 PPT 만들어줘", "제안서 피피티로", "이 현장 발표자료")
---

# 고객용 PPT 만들기

## 순서
1. `learn_read` (회사명·연락처는 표지에 자동으로 들어감). 현장 얘기면 `project_open` 먼저 → 현장정보를 내용에 반영.
2. 들어갈 그림을 먼저 만든다 (모두 결과물 폴더에 png 로 저장됨):
   - 평면도: AutoCAD 에 도면을 열고 `capture_view` → 답 첫 줄의 "그림 파일로 저장됨: 경로" 를 image 에 그대로 쓴다 (PNGOUT 같은 명령 쓰지 않기)
   - 3D: SketchUp 모델이 있으면 `sketchup_capture(birds_eye=true)`, 없으면 3D 를 먼저 만들고(`ch-3d-presentation`) SketchUp 으로 만든 뒤 캡처
   - 현장 사진은 `project_add_file` 로 현장 `자료\` 에 복사해 두고 그 경로 사용
3. 숫자는 도구로 잰 값만: 면적은 `cad_room_areas`, 금액은 견적서(`excel_estimate`)를 만든 값.
4. `ppt_presentation(filename, title, slides, subtitle, client)` — 기본 구성:
   1) 현장 개요 (위치·면적·구성·공사 기간)
   2) 평면도 (image + 핵심 변경점 bullets)
   3) 3D 미리보기 (image, note 에 "실제 색상과 다를 수 있음")
   4) 실별 면적 (table: 실 / 면적㎡ / 평 / 바닥 마감)
   5) 자재·마감 제안 (table 또는 bullets)
   6) 시공 순서·일정 (bullets: 철거 → 설비·전기 → 목공 → 타일 → 도장·도배 → 마루 → 가구·마감)
   7) 견적 요약 (table: 공종 / 금액, 공급가액·부가세·합계 줄)
   8) 마무리 (연락처, 다음 단계)
   요청에 맞게 빼거나 더한다. 한 장에 글은 3~5줄, 쉬운 말.
5. `open_file` 로 열어 보여주고 경로를 알려준다. 고칠 점을 말하면 slides 를 고쳐 새 파일로 다시 만든다 (덮어쓰지 않음).

## 주의
- 추정 숫자는 "추정"이라고 적는다. 그림이 없으면 그 슬라이드는 빼고 만든다 (없는 그림 경로를 넣지 않는다).
- 사무소가 좋아하는 구성·문구는 `learn_note`, 두 번째 PPT 요청부터는 `learn_save_skill` 로 사무소 전용 PPT 절차를 저장한다.
