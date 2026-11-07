"""Automatic 3D scene draft from the open AutoCAD plan.

Builds a complete, consistent customer scene in one call so quality does not
depend on the AI hand-writing hundreds of objects:
  wall lines -> walls, enclosed spaces -> per-room floors (material by room
  name), window lines -> windows (walls get openings), door leaf lines ->
  doors, furniture/fixture outlines -> extruded furniture with heights and
  materials by name (beds get a mattress), room names -> Korean labels,
  summary filled with measured areas. The AI then only polishes the text.
"""

from __future__ import annotations

import json
import math
import re
from datetime import date
from pathlib import Path

from acad import bridge

from .analysis import (ANALYSIS_TIMEOUT, FURNITURE_LAYERS, PYEONG_M2, _doc, _is_closed, _iter_space,
                       _match, _poly_points, _text_of, _units)
from .safety import HOME, OUT_DIR


KO = [  # (pattern, Korean)  - longest / most specific first
    (r"KITCHEN\s*/\s*DINING", "주방·식당"), (r"WASH\s*/\s*DRY", "세탁실"), (r"SHOE\s*STORAGE", "신발장"),
    (r"MASTER\s*BED(ROOM)?", "안방"), (r"BED\s*ROOM\s*(\d+)", r"침실 \1"), (r"BEDROOM", "침실"),
    (r"LIVING(\s*ROOM)?", "거실"), (r"KITCHEN", "주방"), (r"DINING", "식당"), (r"BATH(ROOM)?\s*(\d+)", r"욕실 \2"),
    (r"BATH(ROOM)?", "욕실"), (r"TOILET|WC", "화장실"), (r"BALCONY", "발코니"), (r"ENTRY|ENTRANCE", "현관"),
    (r"FOYER|HALL", "현관홀"), (r"CORRIDOR|PASSAGE", "복도"), (r"UTILITY|LAUNDRY", "다용도실"),
    (r"DRESS(\s*ROOM)?|WALK.?IN", "드레스룸"), (r"WARDROBE|CLOSET", "붙박이장"), (r"STUDY|OFFICE", "서재"),
    (r"PANTRY", "팬트리"), (r"STORAGE|STORE", "창고"), (r"QUEEN\s*BED", "퀸 침대"), (r"KING\s*BED", "킹 침대"),
    (r"SINGLE\s*BED", "싱글 침대"), (r"\bBED\b", "침대"), (r"SOFA", "소파"), (r"\bTV\b", "TV장"),
    (r"SINK", "싱크대"), (r"ISLAND", "아일랜드"), (r"FRIDGE|REFRIGERATOR", "냉장고"), (r"DESK", "책상"),
    (r"TABLE", "테이블"), (r"CHAIR", "의자"), (r"BATH\s*TUB|TUB", "욕조"), (r"SHOWER", "샤워부스"),
    (r"BASIN|LAV", "세면대"),
]
WET = ("욕실", "화장실", "주방", "식당", "현관", "발코니", "다용도", "세탁", "신발", "팬트리", "창고")


def to_korean(text: str) -> str:
    t = text.strip()
    if re.search(r"[가-힣]", t):
        return t
    up = t.upper()
    for pat, ko in KO:
        if re.search(pat, up):
            return re.sub(pat, ko, up, count=1).strip()
    return t


def _furniture_kind(name: str, layer: str) -> tuple[str, float, str]:
    """(display name, height mm, material) from the label inside the outline."""
    n = name.upper() + " " + layer.upper()
    rules = [
        (r"BED", "침대", 380, "목재"), (r"SOFA|COUCH", "소파", 420, "패브릭"), (r"\bTV\b", "TV장", 450, "목재"),
        (r"DINING|TABLE", "테이블", 720, "목재"), (r"DESK", "책상", 720, "목재"), (r"CHAIR|STOOL", "의자", 450, "패브릭"),
        (r"WARDROBE|CLOSET|DRESS|SHOE|STORAGE|CABINET|JOIN", "수납장", 2200, "화이트"),
        (r"FRIDGE|REFRIG", "냉장고", 1800, "스테인리스"), (r"SINK|COUNTER|KITCHEN|ISLAND", "주방 하부장", 850, "화이트"),
        (r"WASH|DRY|LAUNDRY", "세탁기·건조기", 1700, "화이트"), (r"TUB", "욕조", 550, "위생도기"),
        (r"SHOWER", "샤워부스", 2000, "유리"), (r"BASIN|LAV|VANITY", "세면대", 850, "위생도기"),
        (r"WC|TOILET|FIXT", "위생기구", 450, "위생도기"),
    ]
    for pat, ko, h, mat in rules:
        if re.search(pat, n):
            return ko, h, mat
    return "가구", 450, "목재"


def build_draft(ceiling_mm: float = 2300.0, wall_thickness_mm: float = 150.0, door_gap_mm: float = 950.0,
                wall_layers: str = "", window_layers: str = "", door_layers: str = "",
                furniture_layers: str = "", title: str = "") -> tuple[Path, dict]:
    from shapely.geometry import LineString, Point, Polygon
    from shapely.ops import unary_union

    wl = wall_layers or "*WALL*,*벽*,*COL*,*기둥*"
    winl = window_layers or "*WIN*,*창*,*GLAZ*"
    dl = door_layers or "*DOOR*,*문*"
    fl = furniture_layers or FURNITURE_LAYERS

    def work(acad):
        doc = _doc(acad)
        code, to_m = _units(doc)
        walls, wins, doors, furn, texts = [], [], [], [], []
        for e, kind, layer in _iter_space(acad):
            try:
                if kind in ("AcDbText", "AcDbMText"):
                    t = _text_of(e, kind)
                    if t and not re.fullmatch(r"[\d.,\s:+\-xX×㎡mM²]+", t) and not _match(layer, "*DIM*,*치수*"):
                        p = list(e.InsertionPoint)
                        texts.append((t, p[0], p[1], layer))
                    continue
                segs = []
                if kind == "AcDbLine":
                    s, t2 = list(e.StartPoint), list(e.EndPoint)
                    segs = [((s[0], s[1]), (t2[0], t2[1]))]
                elif kind in ("AcDbPolyline", "AcDb2dPolyline"):
                    pts = _poly_points(e, kind) or []
                    closed = _is_closed(e, kind)
                    if _match(layer, fl) and closed and len(pts) >= 3:
                        furn.append(("poly", pts, layer))
                        continue
                    if closed and pts:
                        pts = pts + [pts[0]]
                    segs = list(zip(pts, pts[1:]))
                elif kind == "AcDbCircle" and _match(layer, fl):
                    c = list(e.Center)
                    r = e.Radius
                    furn.append(("poly", [(c[0] + r * math.cos(a * math.pi / 12), c[1] + r * math.sin(a * math.pi / 12)) for a in range(24)], layer))
                    continue
                if not segs:
                    continue
                if _match(layer, winl):
                    wins += segs
                elif _match(layer, dl):
                    doors += segs
                elif _match(layer, wl):
                    walls += segs
            except Exception:  # noqa: BLE001
                continue
        return doc.Name, code, to_m, walls, wins, doors, furn, texts

    name, code, to_m, walls, wins, doors, furn, texts = bridge.run(work, ANALYSIS_TIMEOUT)
    if len(walls) < 3:
        raise ValueError(f"벽 선을 찾지 못했습니다 (레이어 조건 {wl}). cad_overview 로 벽 레이어를 확인해 wall_layers 로 지정하세요.")
    k = 1.0 / (to_m * 1000.0)  # drawing units per mm
    mm = lambda v: v / k  # noqa: E731  drawing units -> mm
    P = lambda p: [round(mm(p[0]), 1), round(mm(p[1]), 1)]  # noqa: E731

    # rooms = enclosed spaces between walls + windows (door gaps closed)
    r_close = (door_gap_mm / 2.0) * k
    lines = [LineString(s) for s in walls + wins if s[0] != s[1]]
    mass = unary_union(lines).buffer(r_close, cap_style="square", join_style="mitre")
    rooms = []
    for pg in (mass.geoms if hasattr(mass, "geoms") else [mass]):
        for hole in pg.interiors:
            room = Polygon(hole).buffer(r_close, join_style="mitre")
            if room.area * to_m * to_m >= 0.8:
                rooms.append(room)
    room_texts = [t for t in texts if not _match(t[3], fl)]

    objs, labels, summary_rows = [], [], []
    total = 0.0
    for room in rooms:
        inside = [t for t in room_texts if room.contains(Point(t[1], t[2]))]
        names = list(dict.fromkeys(to_korean(t[0]) for t in inside)) or ["공간"]
        nm = " · ".join(names[:3])
        area = room.area * to_m * to_m
        total += area
        # open plan (거실+주방+현관) is finished like the living room
        wet = any(w in nm for w in WET) and not any(d in nm for d in ("거실", "침실", "안방", "드레스", "서재"))
        mat = "타일" if wet else "강마루"
        color = "#b9c3bd" if "발코니" in nm else None
        poly = room.simplify(1.0 * k) if room.geom_type == "Polygon" else room
        if poly.geom_type != "Polygon":
            continue
        pts = [P(c) for c in list(poly.exterior.coords)[:-1]]
        o = {"kind": "prism", "layer": "floor", "name": f"{nm} 바닥", "points": pts, "z0": 0, "z1": 10,
             "material": mat, "spec": ("포세린 타일 600×600" if wet else "강마루 120×800×7.5") + f" · {area:.2f}㎡ ({area / PYEONG_M2:.2f}평)"}
        if color:
            o["color"] = color
        objs.append(o)
        c = poly.representative_point()
        labels.append({"kind": "label", "layer": "room", "text": names[0], "x": round(mm(c.x)), "y": round(mm(c.y)), "z": ceiling_mm + 300})
        summary_rows.append((nm, area))

    for a, b in walls:
        if a != b:
            objs.append({"kind": "wall", "layer": "wall", "name": "벽체", "path": [P(a), P(b)],
                         "thickness": wall_thickness_mm, "z0": 0, "z1": ceiling_mm, "material": "도장",
                         "spec": f"두께 {wall_thickness_mm:.0f} · 높이 {ceiling_mm:,.0f} mm"})
    for a, b in wins:
        L = math.dist(a, b) / k
        if L < 300:
            continue
        tall = L >= 1800  # wide openings = balcony / living windows
        sill, h = (100.0, min(2100.0, ceiling_mm - 150)) if tall else (900.0, 1350.0)
        objs.append({"kind": "window", "layer": "glass", "name": "창호", "a": P(a), "b": P(b), "sill": sill, "height": h,
                     "spec": f"창 폭 {L:,.0f} · 높이 {h:,.0f} mm"})
    for a, b in doors:
        L = math.dist(a, b) / k
        if not 550 <= L <= 1300:
            continue  # leaf lines only; skip arcs/frames/odd lines
        ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
        objs.append({"kind": "door", "layer": "door", "name": "도어", "x": P(a)[0], "y": P(a)[1],
                     "width": round(L), "height": 2100, "angle_deg": round(ang, 1),
                     "spec": f"도어 {L:,.0f} × 2,100 mm"})
    for _, pts, layer in furn:
        poly = Polygon(pts)
        if poly.area * to_m * to_m < 0.05:
            continue
        inside = [t[0] for t in texts if poly.contains(Point(t[1], t[2]))]
        label = inside[0] if inside else ""
        ko, h, mat = _furniture_kind(label, layer)
        disp = to_korean(label) if label else ko
        minx, miny, maxx, maxy = poly.bounds
        size = f"{mm(maxx - minx):,.0f} × {mm(maxy - miny):,.0f} × 높이 {h:,.0f} mm"
        ring = [P(c) for c in pts]
        if ko == "침대":
            objs.append({"kind": "prism", "layer": "furn", "name": disp + " 프레임", "points": ring, "z0": 10, "z1": 10 + h, "material": "목재", "spec": size})
            inner = poly.buffer(-40 * k, join_style="mitre")
            if inner.geom_type == "Polygon" and not inner.is_empty:
                objs.append({"kind": "prism", "layer": "furn", "name": "매트리스", "points": [P(c) for c in list(inner.exterior.coords)[:-1]],
                             "z0": 10 + h, "z1": 10 + h + 220, "material": "패브릭", "spec": size})
        else:
            layer_id = "fix" if mat in ("위생도기", "스테인리스") or ko in ("주방 하부장", "세탁기·건조기") else "furn"
            objs.append({"kind": "prism", "layer": layer_id, "name": disp, "points": ring, "z0": 10, "z1": 10 + h, "material": mat, "spec": size})
            if ko == "주방 하부장":
                objs.append({"kind": "prism", "layer": "fix", "name": "주방 상판", "points": ring, "z0": 10 + h, "z1": 10 + h + 30,
                             "material": "인조대리석", "spec": "인조대리석 상판 t30"})
    objs += labels

    wet_area = sum(a for n, a in summary_rows
                   if any(w in n for w in WET) and not any(d in n for d in ("거실", "침실", "안방", "드레스", "서재")))
    dry_area = total - wet_area
    scene = {
        "title": title or f"{Path(name).stem} 3D 공간 안내",
        "subtitle": f"도면 기준 3D · 천장고 {ceiling_mm:,.0f} mm",
        "date": date.today().isoformat(),
        "notes": ["도면에 그려진 벽·창·문·가구 위치 그대로 만든 3D입니다.",
                  "거실·침실은 강마루, 주방·욕실·현관·발코니는 타일 마감으로 표시했습니다.",
                  "마우스를 올리면 각 부분의 규격과 크기를 볼 수 있습니다.",
                  "가구와 마감은 협의 후 확정합니다."],
        "summary": [["실 면적 합계", f"{total:,.2f}㎡ ({total / PYEONG_M2:,.2f}평)"],
                    ["강마루 바닥", f"{dry_area:,.2f}㎡"], ["타일 바닥", f"{wet_area:,.2f}㎡"],
                    ["천장고", f"{ceiling_mm:,.0f} mm"]],
        "materials": [["거실·침실 바닥", "강마루 120×800×7.5"], ["주방·욕실·현관 바닥", "포세린 타일 600×600"],
                      ["벽체", "무광 수성 도장"], ["창호", "복층유리 + 알루미늄 프레임"], ["도어", "목재 도어 900×2,100"],
                      ["주방 상판", "인조대리석 t30"]],
        "badge": {"label": "치수 확인 필요", "text": "도면 기준 자동 생성 모델입니다. 실측 후 치수·마감·가구 규격을 확정합니다."},
        "layers": [{"id": "wall", "name": "벽체"}, {"id": "floor", "name": "바닥 마감"}, {"id": "glass", "name": "창호"},
                   {"id": "door", "name": "문"}, {"id": "furn", "name": "가구"}, {"id": "fix", "name": "주방·욕실"},
                   {"id": "room", "name": "공간명"}],
        "objects": objs,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r'[\\/:*?"<>|]+', "_", Path(name).stem)
    out = OUT_DIR / f"{stem}_3d_scene.json"
    n = 2
    while out.exists():
        out = OUT_DIR / f"{stem}_3d_scene ({n}).json"
        n += 1
    out.write_text(json.dumps(scene, ensure_ascii=False, indent=1), encoding="utf-8")
    stats = {"rooms": len(summary_rows), "walls": len(walls), "windows": sum(1 for o in objs if o["kind"] == "window"),
             "doors": sum(1 for o in objs if o["kind"] == "door"), "furniture": len(furn), "total_m2": round(total, 2)}
    return out, stats


def register(mcp) -> None:

    @mcp.tool()
    def scene_draft_from_cad(ceiling_mm: float = 2300.0, wall_thickness_mm: float = 150.0, title: str = "",
                             wall_layers: str = "", window_layers: str = "", door_layers: str = "",
                             furniture_layers: str = "") -> str:
        """FIRST step for any 3D request from an AutoCAD plan (read-only on the
        drawing). Builds a complete scene JSON automatically: walls, per-room
        floors (강마루/타일 by room name), windows with wall openings, doors,
        furniture with heights/materials by name (beds with mattress), Korean
        room labels, measured area summary, materials table and badge.

        Then: read the JSON, improve only what needs judgement (title, notes in
        plain Korean, swap materials the user asked for, add missing furniture),
        and call scene_build_html. Layer filters use the same '*' syntax as
        cad_measure; leave empty for the defaults.
        """
        out, st = build_draft(ceiling_mm, wall_thickness_mm, 950.0, wall_layers, window_layers, door_layers,
                              furniture_layers, title)
        return (f"초안 장면 저장: {out}\n방 {st['rooms']}개 (합계 {st['total_m2']}㎡), 벽 선 {st['walls']}, 창 {st['windows']}, "
                f"문 {st['doors']}, 가구 외곽 {st['furniture']}\n다음: 필요한 부분만 고친 뒤 scene_build_html(scene_path=위 경로).")
