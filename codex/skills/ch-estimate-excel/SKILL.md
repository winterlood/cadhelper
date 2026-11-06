---
name: ch-estimate-excel
description: 견적서·물량표·자재표를 엑셀로 만들 때 사용 (예: "이 도면으로 견적서 뽑아줘", "도배 물량 엑셀로", "견적 다시 만들어줘")
---

# 엑셀 견적서 만들기

1. `learn_read` 로 회사 정보와 저장된 단가를 확인한다. 회사 정보가 없으면 처음 한 번 물어보고 `learn_set_profile` 로 저장 (company, ceo, phone, address, estimate_footer).
2. 수량은 반드시 도구로 잰다.
   - 바닥재: `cad_room_areas` 실 면적 (발코니·욕실 포함 여부를 물어볼 것)
   - 벽 마감(도배·도장·타일): 벽 길이(`cad_measure` 벽 레이어 길이) × 천장고(profile의 default_wall_height_mm, 없으면 물어보기) − 창·문 면적. 계산식을 note에 적는다.
   - 걸레받이·몰딩: 실 둘레 길이
   - SketchUp 모델이 있으면 `sketchup_model_info` 의 재질별 면적
   - 개수: `cad_blocks`
3. 로스율(할증)은 사용자가 정한 값만 쓴다. 정한 적 없으면 물어보고 `learn_note`(규칙)로 저장.
4. `excel_estimate` 호출. unit_price를 모르면 비워 두면 저장된 단가가 들어가고, 없으면 0원 + 경고가 나온다 → 사용자에게 단가를 물어 `learn_set_prices` 로 저장 후 다시 만든다.
5. `open_file` 로 열어 보여주고, 총액과 "단가가 0원인 항목"을 한 줄로 알려준다.
6. 사용자가 양식·항목 순서·문구를 고쳐달라고 하면 반영하고 `learn_note`(선호)로 남긴다. 두 번째 견적부터는 같은 방식으로 만든다.

엑셀 수식이 살아 있으므로 사용자가 엑셀에서 수량·단가를 고치면 합계가 자동으로 바뀐다고 안내한다.
