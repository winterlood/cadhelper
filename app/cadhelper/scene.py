"""Scene JSON -> self-contained 3D HTML (for customers), -> DXF, -> SketchUp.

All lengths in mm. x = right/east, y = up/north on the plan, z = height.

{
  "title": "봉담 44평 인테리어 제안", "subtitle": "기존 평면 기준 · 천장고 2,300",
  "org": "OO인테리어 · 3D PROPOSAL", "date": "2026-11-06",
  "notes": ["거실 아트월은 포세린 타일 600×1200", "..."],      # 고객 설명 3~6줄
  "summary": [["전용면적", "84.9㎡ (25.7평)"], ["천장고", "2,300 mm"]],
  "materials": [["거실·침실 바닥", "강마루 120×800×7.5"], ["욕실 벽", "포세린 300×600"]],
  "badge": {"label": "치수 확인 필요", "text": "도면 기준 개념 모델입니다. 실측 후 확정합니다."},
  "layers": [{"id": "wall", "name": "벽체"}, {"id": "floor", "name": "바닥 마감"},
             {"id": "glass", "name": "창호"}, {"id": "door", "name": "문"},
             {"id": "furn", "name": "가구"}, {"id": "fix", "name": "주방·욕실"}, {"id": "room", "name": "공간명"}],
  "grids": [{"label": "X1", "x": 0}, {"label": "Y1", "y": 0}],      # optional
  "objects": [
    {"kind": "wall", "layer": "wall", "name": "외벽", "path": [[0,0],[5000,0],[5000,4000]],
     "thickness": 200, "z0": 0, "z1": 2300, "material": "도장"},
    {"kind": "prism", "layer": "floor", "name": "거실 바닥", "spec": "강마루 120×800×7.5",
     "points": [[0,0],[5000,0],[5000,4000],[0,4000]], "z0": 0, "z1": 10, "material": "강마루"},
    {"kind": "box", "layer": "furn", "name": "3인 소파", "spec": "2,200×900×800",
     "x0": 1000, "y0": 300, "x1": 3200, "y1": 1200, "z0": 0, "z1": 800, "material": "패브릭"},
    {"kind": "window", "layer": "glass", "name": "거실 창", "a": [500,0], "b": [4500,0],
     "sill": 300, "height": 2000},                                   # 유리 + 위아래 프레임
    {"kind": "door", "layer": "door", "name": "침실1 도어", "x": 5000, "y": 1200,
     "width": 900, "height": 2100, "angle_deg": 120},                # 경첩점 x,y 에서 angle 방향으로 열린 문짝
    {"kind": "label", "layer": "room", "text": "거실", "x": 2500, "y": 2000}
  ]
}
Per object (optional): "material" preset - 강마루 원목 목재 타일 대리석 석재 도장 벽지
콘크리트 유리 거울 금속 스테인리스 프레임 패브릭 가죽 화이트 다크 위생도기 인조대리석
(sets colour/gloss/transparency); "color" "#rrggbb" overrides; "opacity" 0-1;
"spec" (규격, shown on hover); "info" (extra line); "edges": false.
Points may be [[x,y],...] (flat [x,y,x,y] is also accepted).
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from .safety import HOME

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
OUT_DIR = HOME / "output"


def _load(scene_path: str) -> dict:
    p = Path(scene_path)
    if not p.exists():
        raise FileNotFoundError(f"장면 파일이 없습니다: {p}")
    data = json.loads(p.read_text(encoding="utf-8-sig"))
    if not isinstance(data.get("objects"), list) or not data["objects"]:
        raise ValueError("장면에 objects 목록이 비어 있습니다.")
    for i, o in enumerate(data["objects"]):
        k = o.get("kind")
        need = {"box": ["x0", "y0", "x1", "y1", "z0", "z1"], "prism": ["points", "z0", "z1"],
                "wall": ["path", "z0", "z1"], "label": ["x", "y"], "window": ["a", "b"],
                "door": ["x", "y"]}.get(k)
        if need is None:
            raise ValueError(f"objects[{i}] kind={k!r} 는 지원하지 않습니다 (box, prism, wall, window, door, label).")
        miss = [n for n in need if n not in o]
        if miss:
            raise ValueError(f"objects[{i}] ({o.get('name', k)}) 에 {miss} 값이 없습니다.")
        if k == "prism":
            o["points"] = _pairs(o["points"], f"objects[{i}].points")
            if len(o["points"]) < 3:
                raise ValueError(f"objects[{i}] prism 은 점이 3개 이상이어야 합니다.")
        if k == "wall":
            o["path"] = _pairs(o["path"], f"objects[{i}].path")
        if k == "window":
            o["a"], o["b"] = _pairs([o["a"], o["b"]], f"objects[{i}].a/b")
        for key in ("x0", "y0", "x1", "y1", "z0", "z1", "x", "y", "z", "thickness", "opacity",
                    "sill", "height", "width", "angle_deg"):
            if key in o:
                try:
                    o[key] = float(o[key])
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"objects[{i}].{key} 는 숫자여야 합니다: {o[key]!r}") from exc
    return data


PRESET_COLOR = {"강마루": "#c8a27a", "원목": "#a87d55", "목재": "#9e7751", "타일": "#c9c5b9", "대리석": "#e8e4dc",
                "석재": "#cfcac0", "도장": "#ece8df", "벽지": "#eeeae2", "콘크리트": "#b9bcbc", "유리": "#77b4c4",
                "거울": "#cfd8dc", "금속": "#8a9399", "스테인리스": "#c3c8cc", "프레임": "#53656d", "패브릭": "#d9d1bf",
                "가죽": "#6b4a36", "화이트": "#f4f1e8", "다크": "#3a4143", "위생도기": "#f7f7f5", "인조대리석": "#efece6"}


def _rect_along(a, b, t, ext=0.0):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = (dx * dx + dy * dy) ** 0.5 or 1.0
    ux, uy = dx / L, dy / L
    nx, ny = -uy * t, ux * t
    A = (a[0] - ux * ext, a[1] - uy * ext)
    B = (b[0] + ux * ext, b[1] + uy * ext)
    return [[A[0] + nx, A[1] + ny], [B[0] + nx, B[1] + ny], [B[0] - nx, B[1] - ny], [A[0] - nx, A[1] - ny]]


def _wall_pieces(o: dict, windows: list) -> list:
    """Split a wall path into prisms; where a window lies on a segment, leave
    an opening (wall below the sill and above the head only)."""
    pts = [list(p) for p in o["path"]]
    if o.get("closed"):
        pts.append(pts[0])
    t = float(o.get("thickness") or 100) / 2
    z0, z1 = float(o["z0"]), float(o["z1"])
    base = {k: v for k, v in o.items() if k not in ("kind", "path", "closed", "thickness", "z0", "z1")}
    base["role"] = "wall"
    pieces = []
    for a, b in zip(pts, pts[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = (dx * dx + dy * dy) ** 0.5
        if L < 1:
            continue
        ux, uy = dx / L, dy / L
        ops = []
        for w in windows:
            s0 = (w["a"][0] - a[0]) * ux + (w["a"][1] - a[1]) * uy
            s1 = (w["b"][0] - a[0]) * ux + (w["b"][1] - a[1]) * uy
            d0 = abs(-(w["a"][0] - a[0]) * uy + (w["a"][1] - a[1]) * ux)
            d1 = abs(-(w["b"][0] - a[0]) * uy + (w["b"][1] - a[1]) * ux)
            lo, hi = sorted((s0, s1))
            if d0 <= t + 60 and d1 <= t + 60 and hi > 0 and lo < L and hi - lo > 50:
                sill = float(w.get("sill", 900.0))
                ops.append((max(lo, 0.0), min(hi, L), sill, sill + float(w.get("height", 1350.0))))
        ops.sort()

        def piece(s_a, s_b, za, zb):
            if s_b - s_a < 1 or zb - za < 1:
                return
            A = [a[0] + ux * s_a, a[1] + uy * s_a]
            B = [a[0] + ux * s_b, a[1] + uy * s_b]
            pieces.append({**base, "kind": "prism", "points": _rect_along(A, B, t), "z0": za, "z1": zb})

        cur = -t  # extend by half thickness at both ends so corners close
        for lo, hi, sill, head in ops:
            piece(cur, lo, z0, z1)
            piece(lo, hi, z0, min(sill, z1))
            piece(lo, hi, max(head, z0), z1)
            cur = max(cur, hi)
        piece(cur, L + t, z0, z1)
    return pieces


def expand(data: dict) -> dict:
    """window/door/wall -> plain prisms (walls get real window openings),
    material preset -> color, so HTML, DXF and SketchUp show the same model."""
    import math
    windows = [o for o in data["objects"] if o.get("kind") == "window"]
    out = []
    for o in data["objects"]:
        o = dict(o)
        if o.get("material") and not o.get("color"):
            o["color"] = PRESET_COLOR.get(o["material"], "#d4d8dc")
        if o.get("material") == "유리" and "opacity" not in o:
            o["opacity"] = 0.42
        k = o["kind"]
        if k == "window":
            sill, h = o.get("sill", 900.0), o.get("height", 1350.0)
            base = {"layer": o.get("layer"), "name": o.get("name") or "창호", "spec": o.get("spec", "")}
            out.append({**base, "kind": "prism", "points": _rect_along(o["a"], o["b"], 15), "z0": sill, "z1": sill + h,
                        "color": o.get("color", PRESET_COLOR["유리"]), "opacity": o.get("opacity", 0.42),
                        "material": o.get("material") or "유리"})
            for z in (sill - 30, sill + h - 30):
                out.append({**base, "kind": "prism", "name": base["name"] + " 프레임",
                            "points": _rect_along(o["a"], o["b"], 50), "z0": z, "z1": z + 60, "color": PRESET_COLOR["프레임"],
                            "material": "프레임"})
        elif k == "door":
            w, h, th = o.get("width", 900.0), o.get("height", 2100.0), o.get("thickness", 40.0)
            ang = math.radians(o.get("angle_deg", 0.0))
            a = (o["x"], o["y"])
            b = (o["x"] + math.cos(ang) * w, o["y"] + math.sin(ang) * w)
            z0 = o.get("z0", 0.0)
            out.append({"kind": "prism", "layer": o.get("layer"), "name": o.get("name") or "도어", "spec": o.get("spec", ""),
                        "points": _rect_along(a, b, th / 2), "z0": z0, "z1": z0 + h,
                        "color": o.get("color", PRESET_COLOR[o.get("material") or "목재"] if (o.get("material") or "목재") in PRESET_COLOR else "#9e7751"),
                        "material": o.get("material") or "목재"})
        elif k == "wall":
            out.extend(_wall_pieces(o, windows))
        else:
            out.append(o)
    return {**data, "objects": out}


def _pairs(v, what: str) -> list:
    """Accept [[x,y],...] or a flat [x,y,x,y,...]; return [[x,y],...] floats."""
    if isinstance(v, list) and v and all(isinstance(n, (int, float)) for n in v):
        if len(v) % 2:
            raise ValueError(f"{what}: 좌표 숫자 개수가 홀수입니다.")
        v = [v[j:j + 2] for j in range(0, len(v), 2)]
    try:
        return [[float(p[0]), float(p[1])] for p in v]
    except (TypeError, IndexError, ValueError) as exc:
        raise ValueError(f"{what}: 좌표는 [[x,y],[x,y],...] 형식이어야 합니다.") from exc


def _safe_name(name: str, ext: str) -> Path:
    stem = re.sub(r'[\\/:*?"<>|]+', "_", Path(name).stem or "scene")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUT_DIR / f"{stem}{ext}"


def build_html(scene_path: str, filename: str = "") -> Path:
    data = expand(_load(scene_path))
    data.setdefault("date", date.today().isoformat())
    html = (TEMPLATES / "viewer.html").read_text(encoding="utf-8")
    three = (TEMPLATES / "three.min.js").read_text(encoding="utf-8")
    orbit = (TEMPLATES / "OrbitControls.js").read_text(encoding="utf-8")
    scene_js = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    title = (data.get("title") or "3D 모델").replace("<", "").replace(">", "")
    html = (html.replace("/*__THREE__*/", lambda_safe(three))
                .replace("/*__ORBIT__*/", lambda_safe(orbit))
                .replace("/*__SCENE__*/null", scene_js)
                .replace("__TITLE__", title))
    out = _safe_name(filename or data.get("title") or "scene", ".html")
    out.write_text(html, encoding="utf-8")
    return out


def lambda_safe(js: str) -> str:
    return js.replace("</script", "<\\/script")


def build_dxf(scene_path: str, filename: str = "") -> Path:
    import ezdxf
    from ezdxf.render import MeshBuilder

    data = expand(_load(scene_path))
    doc = ezdxf.new("R2018", setup=True)
    doc.units = ezdxf.units.MM
    msp = doc.modelspace()
    layer_names = {}
    for l in data.get("layers") or []:
        nm = re.sub(r'[<>/\\":;?*|=`]', "_", l.get("name") or l["id"])
        layer_names[l["id"]] = nm
        if nm not in doc.layers:
            doc.layers.add(nm)

    def rgb(h):
        h = (h or "#cccccc").lstrip("#")
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

    def prism_faces(pts, z0, z1):
        if len(pts) > 2 and pts[0] == pts[-1]:
            pts = pts[:-1]
        bot = [(x, y, z0) for x, y in pts]
        top = [(x, y, z1) for x, y in pts]
        faces = [bot[::-1], top]
        for i in range(len(pts)):
            j = (i + 1) % len(pts)
            faces.append([bot[i], bot[j], top[j], top[i]])
        return faces

    for o in data["objects"]:
        lay = layer_names.get(o.get("layer"), o.get("layer") or "0")
        if lay not in doc.layers:
            doc.layers.add(lay)
        k = o["kind"]
        if k == "label":
            t = msp.add_text(o.get("text") or o.get("name") or "", height=250, dxfattribs={"layer": lay})
            t.set_placement((o["x"], o["y"], o.get("z", 0)))
            continue
        shapes = []
        if k == "box":
            shapes.append(([[o["x0"], o["y0"]], [o["x1"], o["y0"]], [o["x1"], o["y1"]], [o["x0"], o["y1"]]], o["z0"], o["z1"]))
        elif k == "prism":
            shapes.append((o["points"], o["z0"], o["z1"]))
        elif k == "wall":
            pts = o["path"] + ([o["path"][0]] if o.get("closed") else [])
            t = float(o.get("thickness") or 100) / 2
            for a, b in zip(pts, pts[1:]):
                dx, dy = b[0] - a[0], b[1] - a[1]
                L = (dx * dx + dy * dy) ** 0.5
                if L < 1:
                    continue
                ux, uy = dx / L * t, dy / L * t
                nx, ny = -uy, ux
                a2, b2 = (a[0] - ux, a[1] - uy), (b[0] + ux, b[1] + uy)  # extend so corners close
                shapes.append(([[a2[0] + nx, a2[1] + ny], [b2[0] + nx, b2[1] + ny], [b2[0] - nx, b2[1] - ny], [a2[0] - nx, a2[1] - ny]], o["z0"], o["z1"]))
        for pts, z0, z1 in shapes:
            # MESH keeps n-sided caps (POLYFACE only allows 4 vertices per face)
            mb = MeshBuilder()
            for face in prism_faces([tuple(p) for p in pts], float(z0), float(z1)):
                mb.add_face(face)
            mesh = mb.render_mesh(msp, dxfattribs={"layer": lay})
            mesh.rgb = rgb(o.get("color"))
    for g in data.get("grids") or []:
        if "x" in g:
            msp.add_line((g["x"], -5000), (g["x"], 5000), dxfattribs={"layer": "GRID", "color": 1})
        elif "y" in g:
            msp.add_line((-5000, g["y"]), (5000, g["y"]), dxfattribs={"layer": "GRID", "color": 1})
    out = _safe_name(filename or data.get("title") or "scene", ".dxf")
    doc.saveas(out, encoding="utf-8")
    return out


def write_expanded(scene_path: str) -> Path:
    """Validated + expanded copy of a scene for the SketchUp builder."""
    data = expand(_load(scene_path))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "_sketchup_scene.json"
    out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return out


def register(mcp) -> None:

    @mcp.tool()
    def scene_build_html(scene_path: str, filename: str = "") -> str:
        """Turn a scene JSON file into ONE self-contained 3D HTML page for the
        customer (works offline, open by double-click, can be emailed/KakaoTalk).

        Write the scene JSON first (format in this module's doc: kinds box /
        prism / wall / label, mm units, layers, notes, summary). Customer-facing
        text (title, notes, info) must be plain Korean without CAD jargon.
        Returns the HTML path; open it to check before handing it over.
        """
        out = build_html(scene_path, filename)
        return f"3D 설명 페이지 생성: {out}\n(더블클릭으로 열림. 인터넷 없이도 보임.)"

    @mcp.tool()
    def scene_build_dwg(scene_path: str, filename: str = "") -> str:
        """Write the same scene as a 3D DXF (opens in AutoCAD 2024 and later,
        layers kept, colours kept). Creates a NEW file; nothing existing is changed.
        Use open_file with the returned path to show it in AutoCAD.
        """
        out = build_dxf(scene_path, filename)
        return f"3D DXF 생성: {out}"

    @mcp.tool()
    def scene_format_help() -> str:
        """The scene JSON format with an example (read before writing a scene)."""
        return __doc__
