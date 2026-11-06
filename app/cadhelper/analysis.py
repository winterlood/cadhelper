"""Read-only AutoCAD analysis tools: overview, areas, lengths, rooms, blocks,
texts, the user's current selection, and plan export for 3D work.

Plus three gated editing tools (property change, bulk erase, raw command);
those only run after the user clicks 예 on the safety dialog.
"""

from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import config
from acad import AcadError, bridge

ANALYSIS_TIMEOUT = 600.0
PYEONG_M2 = 3.305785

UNIT_NAMES = {0: "단위없음(mm로 가정)", 1: "inch", 2: "feet", 4: "mm", 5: "cm", 6: "m"}
UNIT_TO_M = {0: 0.001, 1: 0.0254, 2: 0.3048, 4: 0.001, 5: 0.01, 6: 1.0}

AREA_TYPES = {"AcDbPolyline", "AcDb2dPolyline", "AcDbCircle", "AcDbEllipse",
              "AcDbHatch", "AcDbRegion", "AcDbSpline"}
# layers that hold furniture/fixtures, never room boundaries or room names
FURNITURE_LAYERS = "*FURN*,*가구*,*FIXT*,*위생*,*JOIN*,*EQUIP*,*설비*,*APPL*,*PLANT*,*조경*,*DIM*,*치수*"
LENGTH_TYPES = {"AcDbLine", "AcDbPolyline", "AcDb2dPolyline", "AcDbArc", "AcDbCircle"}
TYPE_KO = {
    "AcDbLine": "선", "AcDbPolyline": "폴리선", "AcDb2dPolyline": "폴리선(구형)",
    "AcDbCircle": "원", "AcDbArc": "호", "AcDbEllipse": "타원", "AcDbHatch": "해치",
    "AcDbRegion": "영역", "AcDbSpline": "스플라인", "AcDbText": "문자",
    "AcDbMText": "여러줄문자", "AcDbBlockReference": "블록",
    "AcDbRotatedDimension": "치수", "AcDbAlignedDimension": "치수",
}


# ---------------------------------------------------------------------------
# helpers (run on the COM thread)
# ---------------------------------------------------------------------------

def _doc(acad):
    """Active drawing WITHOUT launching AutoCAD or creating a new drawing."""
    app = acad.connect(launch_if_missing=False)
    if app.Documents.Count == 0:
        raise AcadError("AutoCAD에 열린 도면이 없습니다. 사용자에게 도면을 열어 달라고 하세요.")
    return app.ActiveDocument


def _units(doc) -> tuple[int, float]:
    try:
        code = int(doc.GetVariable("INSUNITS"))
    except Exception:  # noqa: BLE001
        code = 0
    return code, UNIT_TO_M.get(code, 0.001)


def _is_closed(e, kind: str) -> bool:
    if kind in ("AcDbCircle", "AcDbHatch", "AcDbRegion"):
        return True
    if kind == "AcDbEllipse":
        try:
            return abs((e.EndAngle - e.StartAngle) % (2 * math.pi)) < 1e-9
        except Exception:  # noqa: BLE001
            return True
    try:
        if bool(e.Closed):
            return True
    except Exception:  # noqa: BLE001
        return False
    if kind in ("AcDbPolyline", "AcDb2dPolyline"):
        pts = _poly_points(e, kind)
        if pts and len(pts) >= 4:
            (x0, y0), (x1, y1) = pts[0], pts[-1]
            return abs(x0 - x1) < 1e-6 * max(1.0, abs(x0)) + 1e-3 and abs(y0 - y1) < 1e-6 * max(1.0, abs(y0)) + 1e-3
    return False


def _area(e, kind: str):
    if kind not in AREA_TYPES or not _is_closed(e, kind):
        return None
    try:
        return float(e.Area)
    except Exception:  # noqa: BLE001
        return None


def _length(e, kind: str):
    try:
        if kind == "AcDbArc":
            return float(e.ArcLength)
        if kind == "AcDbCircle":
            return float(e.Circumference)
        if kind in ("AcDbLine", "AcDbPolyline", "AcDb2dPolyline"):
            return float(e.Length)
    except Exception:  # noqa: BLE001
        return None
    return None


def _clean_mtext(s: str) -> str:
    s = re.sub(r"\\[PpNn]", " ", s)
    s = re.sub(r"\\[A-Za-z][^;\\{}]*;", "", s)
    s = re.sub(r"\\[A-Za-z]", "", s)
    s = s.replace("{", "").replace("}", "")
    return re.sub(r"\s+", " ", s).strip()


def _text_of(e, kind: str) -> str:
    try:
        t = str(e.TextString)
    except Exception:  # noqa: BLE001
        return ""
    return _clean_mtext(t) if kind == "AcDbMText" else t.strip()


def _poly_points(e, kind: str):
    try:
        c = list(e.Coordinates)
    except Exception:  # noqa: BLE001
        return None
    step = 2 if kind == "AcDbPolyline" else 3
    return [(c[i], c[i + 1]) for i in range(0, len(c) - step + 1, step)]


def _inside(pt, poly) -> bool:
    x, y = pt
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def _match(value: str, wanted: str) -> bool:
    """Comma separated filter, case-insensitive, '*' wildcard, empty = all."""
    if not wanted:
        return True
    v = value.upper()
    for part in [p.strip().upper() for p in wanted.split(",") if p.strip()]:
        rx = "^" + re.escape(part).replace(r"\*", ".*") + "$"
        if re.match(rx, v):
            return True
    return False


def _iter_space(acad, layers: str = "", source: str = "model"):
    doc = _doc(acad)
    if source == "selection":
        try:
            ss = doc.PickfirstSelectionSet
            items = [ss.Item(i) for i in range(ss.Count)]
        except Exception as exc:  # noqa: BLE001
            raise AcadError(f"현재 선택을 읽지 못했습니다: {exc}") from exc
    else:
        items = doc.ModelSpace
    for e in items:
        try:
            kind = e.ObjectName
            layer = e.Layer
        except Exception:  # noqa: BLE001
            continue
        if not _match(layer, layers):
            continue
        yield e, kind, layer


def _fmt_area(a_units: float, to_m: float) -> str:
    m2 = a_units * to_m * to_m
    return f"{m2:,.2f}㎡ ({m2 / PYEONG_M2:,.2f}평)"


def _fmt_len(l_units: float, to_m: float) -> str:
    return f"{l_units * to_m:,.2f}m"


def _out_path(filename: str, ext: str) -> Path:
    name = re.sub(r'[\\/:*?"<>|]+', "_", filename.strip() or "export")
    if not name.lower().endswith(ext):
        name += ext
    config.SAVE_DIR.mkdir(parents=True, exist_ok=True)
    return config.SAVE_DIR / name


# ---------------------------------------------------------------------------
# tools
# ---------------------------------------------------------------------------

def register(mcp) -> None:

    @mcp.tool()
    def cad_overview() -> str:
        """FIRST call for any question about the open AutoCAD drawing (read-only).

        Returns the drawing name and path, units, overall size, and every layer
        with how many objects of each kind it holds and its total closed area /
        line length, plus the most used blocks. Use it to decide which layers
        hold rooms, walls, furniture, etc. before measuring anything.
        """
        def work(acad):
            doc = _doc(acad)
            code, to_m = _units(doc)
            per = defaultdict(lambda: {"count": defaultdict(int), "area": 0.0, "len": 0.0})
            blocks = defaultdict(int)
            total = 0
            for e, kind, layer in _iter_space(acad):
                total += 1
                rec = per[layer]
                rec["count"][kind] += 1
                a = _area(e, kind)
                if a:
                    rec["area"] += a
                ln = _length(e, kind)
                if ln:
                    rec["len"] += ln
                if kind == "AcDbBlockReference":
                    try:
                        blocks[e.EffectiveName] += 1
                    except Exception:  # noqa: BLE001
                        blocks[e.Name] += 1
            try:
                ext = (list(doc.GetVariable("EXTMIN")), list(doc.GetVariable("EXTMAX")))
            except Exception:  # noqa: BLE001
                ext = None
            layer_state = {}
            for lay in doc.Layers:
                try:
                    layer_state[lay.Name] = ("꺼짐" if not lay.LayerOn else "") + (" 동결" if lay.Freeze else "")
                except Exception:  # noqa: BLE001
                    pass
            return {"name": doc.Name, "path": getattr(doc, "FullName", ""), "units": code, "to_m": to_m,
                    "total": total, "per": per, "blocks": blocks, "ext": ext, "layer_state": layer_state}

        r = bridge.run(work, ANALYSIS_TIMEOUT)
        to_m = r["to_m"]
        lines = [f"도면: {r['name']}  경로: {r['path'] or '(저장 안 됨)'}",
                 f"단위: {UNIT_NAMES.get(r['units'], r['units'])}  모형공간 객체 수: {r['total']}"]
        if r["ext"]:
            (x0, y0, *_), (x1, y1, *_) = r["ext"]
            lines.append(f"전체 범위: 가로 {(x1 - x0) * to_m:,.2f}m × 세로 {(y1 - y0) * to_m:,.2f}m")
        lines.append("\n레이어별 (객체 종류: 개수 | 닫힌 도형 면적 합 | 선 길이 합):")
        for layer in sorted(r["per"], key=lambda k: -sum(r["per"][k]["count"].values())):
            rec = r["per"][layer]
            kinds = ", ".join(f"{TYPE_KO.get(k, k)} {n}" for k, n in sorted(rec["count"].items(), key=lambda kv: -kv[1]))
            extra = []
            if rec["area"]:
                extra.append("면적 " + _fmt_area(rec["area"], to_m))
            if rec["len"]:
                extra.append("길이 " + _fmt_len(rec["len"], to_m))
            state = r["layer_state"].get(layer, "").strip()
            lines.append(f"- {layer}{' [' + state + ']' if state else ''}: {kinds}" + (" | " + " | ".join(extra) if extra else ""))
        if r["blocks"]:
            top = sorted(r["blocks"].items(), key=lambda kv: -kv[1])[:25]
            lines.append("\n많이 쓰인 블록: " + ", ".join(f"{n} {c}개" for n, c in top))
        lines.append("\n주의: 블록 내부와 외부참조(Xref) 안의 도형은 면적/길이 합계에 포함되지 않음. "
                     "면적은 '닫힌' 폴리선·원·해치 등만 계산함.")
        return "\n".join(lines)

    @mcp.tool()
    def cad_measure(layers: str = "", object_types: str = "", source: str = "model",
                    list_items: bool = False, limit: int = 200) -> str:
        """Total areas (closed shapes) and lengths, grouped by layer (read-only).

        layers: comma separated layer names, '*' wildcard allowed ("A-ROOM*,바닥").
                Empty = all layers.
        object_types: optional filter, e.g. "AcDbPolyline,AcDbHatch".
        source: "model" = whole model space, "selection" = what the user has
                selected in AutoCAD right now (ask them to select, then call).
        list_items: also list each shape with its handle and own area/length.
        Results are in ㎡ / 평 / m using the drawing's INSUNITS.
        """
        def work(acad):
            code, to_m = _units(_doc(acad))
            groups = defaultdict(lambda: {"n_area": 0, "area": 0.0, "n_len": 0, "len": 0.0})
            items = []
            for e, kind, layer in _iter_space(acad, layers, source):
                if object_types and not _match(kind, object_types):
                    continue
                a = _area(e, kind)
                ln = _length(e, kind)
                if a is None and ln is None:
                    continue
                g = groups[layer]
                if a:
                    g["n_area"] += 1
                    g["area"] += a
                if ln:
                    g["n_len"] += 1
                    g["len"] += ln
                if list_items and len(items) < limit:
                    items.append((e.Handle, layer, TYPE_KO.get(kind, kind), a, ln))
            return code, to_m, groups, items

        code, to_m, groups, items = bridge.run(work, ANALYSIS_TIMEOUT)
        if not groups:
            where = "선택한 객체" if source == "selection" else "지정한 레이어"
            return f"{where}에서 면적/길이를 잴 수 있는 도형을 찾지 못했습니다. cad_overview로 레이어 이름을 확인하세요."
        out = [f"단위: {UNIT_NAMES.get(code, code)}" + (" (선택 객체 기준)" if source == "selection" else "")]
        ta = tl = 0.0
        for layer, g in sorted(groups.items()):
            parts = []
            if g["n_area"]:
                parts.append(f"닫힌 도형 {g['n_area']}개 면적 {_fmt_area(g['area'], to_m)}")
                ta += g["area"]
            if g["n_len"]:
                parts.append(f"선 {g['n_len']}개 길이 {_fmt_len(g['len'], to_m)}")
                tl += g["len"]
            out.append(f"- {layer}: " + " / ".join(parts))
        out.append(f"\n합계: 면적 {_fmt_area(ta, to_m)}, 길이 {_fmt_len(tl, to_m)}")
        out.append("주의: 겹치는 도형(예: 같은 방을 폴리선과 해치로 둘 다 그린 경우)은 두 번 더해질 수 있음.")
        if items:
            out.append("\n개별 목록 (핸들 | 레이어 | 종류 | 면적 | 길이):")
            for h, layer, k, a, ln in items:
                out.append(f"{h} | {layer} | {k} | {_fmt_area(a, to_m) if a else '-'} | {_fmt_len(ln, to_m) if ln else '-'}")
        return "\n".join(out)

    @mcp.tool()
    def cad_room_areas(method: str = "auto", text_layers: str = "", boundary_layers: str = "",
                       wall_layers: str = "", door_gap_mm: float = 950.0, min_area_m2: float = 0.5) -> str:
        """Room schedule (실별 면적표) in ㎡ and 평 (read-only).

        method:
          "polyline" - each room-name text paired with the smallest closed
                       polyline around it (drawings that have room outlines).
                       Furniture/fixture/joinery layers are skipped by default.
          "walls"    - rooms are found from the WALL LINES themselves: gaps up to
                       door_gap_mm (door openings) are closed, every enclosed
                       space becomes a room, named by the texts inside it.
                       Use this when walls are drawn as separate lines.
          "auto"     - polyline if it finds room outlines, otherwise walls.
        wall_layers default: layers containing WALL/벽/WIN/창/COL/기둥.
        Areas from "walls" are measured to the inner wall faces; open-plan
        spaces (거실+주방) come out as one room with both names. Always tell
        the user which method and layers were used.
        """
        if method == "walls":
            return _rooms_from_walls(text_layers, wall_layers, door_gap_mm, min_area_m2)
        if method == "polyline":
            return _rooms_from_polylines(text_layers, boundary_layers, min_area_m2)
        try:
            walls_res = _rooms_from_walls(text_layers, wall_layers, door_gap_mm, min_area_m2)
        except Exception as exc:  # noqa: BLE001
            walls_res = f"벽 선 방식 실패: {exc}"
        try:
            poly_res = _rooms_from_polylines(text_layers, boundary_layers, min_area_m2)
        except Exception as exc:  # noqa: BLE001
            poly_res = f"폴리선 방식 실패: {exc}"
        if method == "auto":
            if poly_res.startswith("실명 |") and "벽 선" not in walls_res[:40]:
                return "[방법: 닫힌 폴리선]\n" + poly_res + "\n\n[참고 - 벽 선으로 계산한 결과]\n" + walls_res
            return "[방법: 벽 선으로 방 찾기 (방 경계 폴리선이 없음)]\n" + walls_res
        return poly_res

    def _rooms_from_walls(text_layers, wall_layers, door_gap_mm, min_area_m2):
        from shapely.geometry import LineString, Point, Polygon
        from shapely.ops import unary_union

        wl = wall_layers or "*WALL*,*벽*,*WIN*,*창*,*COL*,*기둥*"

        def work(acad):
            code, to_m = _units(_doc(acad))
            segs, texts = [], []
            for e, kind, layer in _iter_space(acad):
                if kind in ("AcDbText", "AcDbMText"):
                    if _match(layer, text_layers) and not _match(layer, FURNITURE_LAYERS):
                        t = _text_of(e, kind)
                        if t and not re.fullmatch(r"[\d.,\s:+\-xX×㎡mM²]+", t):
                            p = list(e.InsertionPoint)
                            texts.append((t, p[0], p[1], layer))
                    continue
                if not _match(layer, wl):
                    continue
                if kind == "AcDbLine":
                    s, t = list(e.StartPoint), list(e.EndPoint)
                    segs.append(((s[0], s[1]), (t[0], t[1])))
                elif kind in ("AcDbPolyline", "AcDb2dPolyline"):
                    pts = _poly_points(e, kind) or []
                    if _is_closed(e, kind) and pts:
                        pts = pts + [pts[0]]
                    segs += list(zip(pts, pts[1:]))
                elif kind == "AcDbArc":
                    c, r = list(e.Center), e.Radius
                    a0, a1 = e.StartAngle, e.EndAngle
                    if a1 < a0:
                        a1 += 2 * math.pi
                    n = max(4, int((a1 - a0) / (math.pi / 18)))
                    pts = [(c[0] + r * math.cos(a0 + (a1 - a0) * i / n), c[1] + r * math.sin(a0 + (a1 - a0) * i / n)) for i in range(n + 1)]
                    segs += list(zip(pts, pts[1:]))
            return code, to_m, segs, texts

        code, to_m, segs, texts = bridge.run(work, ANALYSIS_TIMEOUT)
        if len(segs) < 4:
            return f"벽 선을 찾지 못했습니다 (레이어 조건: {wl}). cad_overview로 벽 레이어 이름을 확인해 wall_layers로 지정하세요."
        r = (door_gap_mm / 1000.0) / 2.0 / to_m
        lines = [LineString(s) for s in segs if s[0] != s[1]]
        mass = unary_union(lines).buffer(r, cap_style="square", join_style="mitre")
        polys = list(mass.geoms) if hasattr(mass, "geoms") else [mass]
        rooms = []
        outer_area = 0.0
        for pg in polys:
            outer_area += Polygon(pg.exterior).buffer(-r, join_style="mitre").area
            for hole in pg.interiors:
                room = Polygon(hole).buffer(r, join_style="mitre")
                if room.area * to_m * to_m >= min_area_m2:
                    rooms.append(room)
        if not rooms:
            return "벽 선으로 둘러싸인 공간을 찾지 못했습니다. door_gap_mm를 키워 보거나 벽 레이어를 확인하세요."
        named = []
        for room in rooms:
            names = [t for t, x, y, l in texts if room.contains(Point(x, y))]
            named.append((names, room.area * to_m * to_m))
        named.sort(key=lambda x: -x[1])
        out = ["실명 | 면적(㎡) | 평"]
        total = 0.0
        for names, m2 in named:
            total += m2
            out.append(f"{' / '.join(dict.fromkeys(names)) or '(이름 없음)'} | {m2:,.2f} | {m2 / PYEONG_M2:,.2f}")
        out.append(f"\n실 면적 합계 {len(named)}개: {total:,.2f}㎡ ({total / PYEONG_M2:,.2f}평)")
        if outer_area:
            m2 = outer_area * to_m * to_m
            out.append(f"외벽 바깥선 기준 전체 면적(추정): {m2:,.2f}㎡ ({m2 / PYEONG_M2:,.2f}평)")
        out.append(f"(벽 선 {len(segs)}개 사용, 레이어 조건 '{wl}', 문 틈 {door_gap_mm:.0f}mm 이하는 막힌 것으로 계산. "
                   "벽 안쪽 면 기준이며 모서리는 직각으로 가정. 폭이 문 틈보다 좁은 공간(좁은 수납장·샤프트·좁은 복도)은 "
                   "빠질 수 있으니 필요하면 door_gap_mm를 줄여 다시 계산)")
        return "\n".join(out)

    def _rooms_from_polylines(text_layers, boundary_layers, min_area_m2):
        def work(acad):
            code, to_m = _units(_doc(acad))
            polys, texts = [], []
            for e, kind, layer in _iter_space(acad):
                if kind in ("AcDbText", "AcDbMText") and _match(layer, text_layers) and (text_layers or not _match(layer, FURNITURE_LAYERS)):
                    t = _text_of(e, kind)
                    if t and not re.fullmatch(r"[\d.,\s:+\-xX×㎡mM²]+", t):
                        p = list(e.InsertionPoint)
                        texts.append((t, (p[0], p[1]), layer))
                elif kind in ("AcDbPolyline", "AcDb2dPolyline") and _match(layer, boundary_layers) and (boundary_layers or not _match(layer, FURNITURE_LAYERS)):
                    if _is_closed(e, kind):
                        pts = _poly_points(e, kind)
                        a = _area(e, kind)
                        if pts and a and a * to_m * to_m >= min_area_m2:
                            polys.append((a, pts, e.Handle, layer))
            polys.sort(key=lambda p: p[0])
            rows = []
            for t, pt, tl in texts:
                hit = next((p for p in polys if _inside(pt, p[1])), None)
                if hit:
                    rows.append((t, hit[0], hit[2], hit[3], tl))
            return code, to_m, rows, len(texts), len(polys)

        code, to_m, rows, nt, npoly = bridge.run(work, ANALYSIS_TIMEOUT)
        if not rows:
            return (f"실 이름 문자 {nt}개, 닫힌 폴리선 {npoly}개를 찾았지만 서로 짝이 맞는 것이 없습니다. "
                    "실 경계가 닫힌 폴리선으로 그려져 있지 않을 수 있습니다. cad_overview로 레이어를 확인하거나, "
                    "사용자에게 방을 선택하게 한 뒤 cad_measure(source='selection')를 쓰세요.")
        seen = {}
        for t, a, h, bl, tl in rows:
            seen.setdefault(h, []).append(t)
        out = ["실명 | 면적(㎡) | 평 | 경계 핸들 | 경계 레이어"]
        total = 0.0
        done = set()
        for t, a, h, bl, tl in rows:
            if h in done:
                continue
            done.add(h)
            m2 = a * to_m * to_m
            total += m2
            name = " / ".join(seen[h])
            out.append(f"{name} | {m2:,.2f} | {m2 / PYEONG_M2:,.2f} | {h} | {bl}")
        out.append(f"\n합계 {len(done)}개 실: {total:,.2f}㎡ ({total / PYEONG_M2:,.2f}평)")
        out.append(f"(검색: 문자 {nt}개, 닫힌 경계 {npoly}개. 한 경계 안에 문자가 여러 개면 이름을 ' / '로 묶음)")
        return "\n".join(out)

    @mcp.tool()
    def cad_blocks(name_filter: str = "", with_attributes: bool = True, limit: int = 300) -> str:
        """Count block references (doors, windows, furniture, fixtures…) and
        summarise their attribute values (read-only). name_filter: comma list,
        '*' wildcard, matched against the block's effective name.
        """
        def work(acad):
            counts = defaultdict(int)
            layers = defaultdict(set)
            attrs = defaultdict(lambda: defaultdict(int))
            for e, kind, layer in _iter_space(acad):
                if kind != "AcDbBlockReference":
                    continue
                try:
                    name = e.EffectiveName
                except Exception:  # noqa: BLE001
                    name = e.Name
                if not _match(name, name_filter):
                    continue
                counts[name] += 1
                layers[name].add(layer)
                if with_attributes:
                    try:
                        if e.HasAttributes:
                            vals = [f"{a.TagString}={a.TextString}" for a in e.GetAttributes()]
                            if vals:
                                attrs[name][", ".join(vals)] += 1
                    except Exception:  # noqa: BLE001
                        pass
            return counts, layers, attrs

        counts, layers, attrs = bridge.run(work, ANALYSIS_TIMEOUT)
        if not counts:
            return "조건에 맞는 블록이 없습니다."
        out = ["블록 이름 | 개수 | 레이어"]
        for n, c in sorted(counts.items(), key=lambda kv: -kv[1])[:limit]:
            out.append(f"{n} | {c} | {', '.join(sorted(layers[n]))}")
            for combo, k in sorted(attrs[n].items(), key=lambda kv: -kv[1])[:15]:
                out.append(f"    속성 [{combo}] × {k}")
        out.append(f"\n블록 종류 {len(counts)}개, 총 {sum(counts.values())}개")
        return "\n".join(out)

    @mcp.tool()
    def cad_texts(layers: str = "", contains: str = "", limit: int = 300) -> str:
        """List text/mtext strings with their position and layer (read-only).
        Use to find room names, notes, finish specs, title block info.
        """
        def work(acad):
            code, to_m = _units(_doc(acad))
            rows = []
            for e, kind, layer in _iter_space(acad, layers):
                if kind not in ("AcDbText", "AcDbMText"):
                    continue
                t = _text_of(e, kind)
                if not t or (contains and contains.lower() not in t.lower()):
                    continue
                p = list(e.InsertionPoint)
                rows.append((t, p[0], p[1], layer, e.Handle))
                if len(rows) >= limit:
                    break
            return rows

        rows = bridge.run(work, ANALYSIS_TIMEOUT)
        if not rows:
            return "조건에 맞는 문자가 없습니다."
        return "문자 | X | Y | 레이어 | 핸들\n" + "\n".join(
            f"{t} | {x:,.0f} | {y:,.0f} | {l} | {h}" for t, x, y, l, h in rows)

    @mcp.tool()
    def cad_export_plan(filename: str = "plan", layers: str = "") -> str:
        """Export the plan geometry to a JSON file for 3D work (read-only on the
        drawing). Writes closed/open polylines, lines, circles, arcs, texts and
        block inserts in drawing units, plus units info, to the output folder.
        Use it as the source when authoring a scene for scene_build_html /
        sketchup_build_scene. Returns the file path and a short summary.
        """
        def work(acad):
            code, to_m = _units(_doc(acad))
            data = {"drawing": _doc(acad).Name, "units": UNIT_NAMES.get(code, code), "unit_to_m": to_m,
                    "polylines": [], "lines": [], "circles": [], "arcs": [], "texts": [], "blocks": []}
            for e, kind, layer in _iter_space(acad, layers):
                try:
                    if kind in ("AcDbPolyline", "AcDb2dPolyline"):
                        pts = _poly_points(e, kind)
                        if pts:
                            data["polylines"].append({"h": e.Handle, "layer": layer, "closed": _is_closed(e, kind),
                                                      "pts": [[round(x, 1), round(y, 1)] for x, y in pts],
                                                      "area": round(_area(e, kind) or 0, 1)})
                    elif kind == "AcDbLine":
                        s, t = list(e.StartPoint), list(e.EndPoint)
                        data["lines"].append({"layer": layer, "a": [round(s[0], 1), round(s[1], 1)], "b": [round(t[0], 1), round(t[1], 1)]})
                    elif kind == "AcDbCircle":
                        c = list(e.Center)
                        data["circles"].append({"layer": layer, "c": [round(c[0], 1), round(c[1], 1)], "r": round(e.Radius, 1)})
                    elif kind == "AcDbArc":
                        c = list(e.Center)
                        data["arcs"].append({"layer": layer, "c": [round(c[0], 1), round(c[1], 1)], "r": round(e.Radius, 1),
                                             "start_deg": round(math.degrees(e.StartAngle), 2), "end_deg": round(math.degrees(e.EndAngle), 2)})
                    elif kind in ("AcDbText", "AcDbMText"):
                        p = list(e.InsertionPoint)
                        data["texts"].append({"layer": layer, "text": _text_of(e, kind), "p": [round(p[0], 1), round(p[1], 1)]})
                    elif kind == "AcDbBlockReference":
                        p = list(e.InsertionPoint)
                        try:
                            name = e.EffectiveName
                        except Exception:  # noqa: BLE001
                            name = e.Name
                        data["blocks"].append({"layer": layer, "name": name, "p": [round(p[0], 1), round(p[1], 1)],
                                               "rot_deg": round(math.degrees(e.Rotation), 2),
                                               "scale": [round(e.XScaleFactor, 4), round(e.YScaleFactor, 4)]})
                except Exception:  # noqa: BLE001
                    continue
            return data

        data = bridge.run(work, ANALYSIS_TIMEOUT)
        path = _out_path(filename, ".json")
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        counts = ", ".join(f"{k} {len(v)}" for k, v in data.items() if isinstance(v, list))
        return f"저장: {path}\n단위: {data['units']}\n{counts}"

    # ------------------------------------------------------------------
    # Editing tools -- every one is behind the approval dialog (safety.py)
    # ------------------------------------------------------------------

    @mcp.tool()
    def cad_set_properties(handles: list, changes: dict, purpose: str = "") -> str:
        """CHANGE objects (needs the user's approval on a dialog).

        handles: entity handles. changes: any of {"layer": "NAME",
        "color": ACI number 1-255 or 256 for ByLayer, "linetype": "DASHED"}.
        purpose: one short Korean sentence shown to the user in the dialog.
        """
        def work(acad):
            done = 0
            for h in handles:
                e = acad.entity_by_handle(str(h))
                if "layer" in changes:
                    _doc(acad).Layers.Add(str(changes["layer"]))
                    e.Layer = str(changes["layer"])
                if "color" in changes:
                    e.Color = int(changes["color"])
                if "linetype" in changes:
                    e.Linetype = str(changes["linetype"])
                done += 1
            return done

        n = bridge.run(work, config.COM_TIMEOUT)
        return f"{n}개 객체 속성을 변경했습니다: {json.dumps(changes, ensure_ascii=False)}"

    @mcp.tool()
    def cad_erase_many(handles: list, purpose: str = "") -> str:
        """DELETE objects (needs the user's approval on a dialog).
        purpose: one short Korean sentence shown to the user in the dialog.
        """
        def work(acad):
            n = 0
            for h in handles:
                acad.entity_by_handle(str(h)).Delete()
                n += 1
            return n

        n = bridge.run(work, config.COM_TIMEOUT)
        return f"{n}개 객체를 삭제했습니다. 되돌리려면 AutoCAD에서 U(명령 취소)를 쓰거나 백업 파일을 여세요."

    @mcp.tool()
    def cad_run_command(command: str, purpose: str = "") -> str:
        """Send a raw AutoCAD command line, e.g. "_-PURGE _A * _N " (needs the
        user's approval on a dialog). End with a space or newline to press Enter.
        Prefer the dedicated tools; use this only when none fits.
        purpose: one short Korean sentence shown to the user in the dialog.
        """
        def work(acad):
            _doc(acad).SendCommand(command if command.endswith((" ", "\n")) else command + " ")
            return True

        bridge.run(work, config.COM_TIMEOUT)
        return f"명령을 보냈습니다: {command!r}. 결과는 capture_view나 cad_overview로 확인하세요."
