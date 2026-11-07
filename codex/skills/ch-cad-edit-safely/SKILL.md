---
name: ch-cad-edit-safely
description: AutoCAD 도면에 무언가를 그리거나, 고치거나, 지우거나, 레이어를 정리할 때 반드시 사용 (예: "이 선 지워줘", "레이어 정리해줘", "치수 넣어줘", "문 그려줘")
---

# 도면을 안전하게 고치기

1. 고치기 전에 `cad_overview` / `list_entities` / `get_entity_info` 로 대상을 정확히 찾는다 (핸들 확인).
2. **대화로 먼저 설명하고 허락받기**: "○○ 레이어의 선 12개를 지우려고 합니다. 해도 될까요?" — 동의 전에는 어떤 변경 도구도 부르지 않는다.
3. 동의를 받으면 변경 도구 실행 → 화면에 Windows 확인창이 뜬다 → 아빠가 '예'를 눌러야 실행된다.
   - 첫 변경 전에 원본 DWG가 자동으로 `work\.cadhelper\backups` 에 복사된다 (저장된 도면인 경우).
   - '아니요'를 누르면 같은 변경을 다시 시도하지 않는다.
4. 여러 개를 고칠 때는 한 번에 묶어서(`draw_batch`, `cad_set_properties`, `cad_erase_many`) 확인창이 여러 번 뜨지 않게 한다.
5. 끝나면 `capture_view` 로 결과를 보여주고, 되돌리는 법(AutoCAD에서 U 또는 Ctrl+Z, 또는 backups 폴더의 원본)을 알려준다.
6. 저장은 사용자가 원할 때만. `save_drawing` 은 `결과물` 폴더에 새 이름으로 저장한다. 원본 덮어쓰기는 사용자가 AutoCAD에서 직접 Ctrl+S 하도록 안내.
