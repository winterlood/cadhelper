"""Find which CAD programs are installed (and which can be automated).

Reads the Windows "installed programs" registry (both 64/32-bit views and the
per-user list), so it works whatever drive or folder the programs were put in.
"""

from __future__ import annotations

import re
import winreg

_UNINSTALL = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
_ROOTS = [
    (winreg.HKEY_LOCAL_MACHINE, _UNINSTALL, winreg.KEY_WOW64_64KEY),
    (winreg.HKEY_LOCAL_MACHINE, _UNINSTALL, winreg.KEY_WOW64_32KEY),
    (winreg.HKEY_CURRENT_USER, _UNINSTALL, 0),
]


def _installed_programs():
    seen = set()
    for hive, path, view in _ROOTS:
        try:
            root = winreg.OpenKey(hive, path, 0, winreg.KEY_READ | view)
        except OSError:
            continue
        for i in range(winreg.QueryInfoKey(root)[0]):
            try:
                sub = winreg.OpenKey(root, winreg.EnumKey(root, i))
                name = str(winreg.QueryValueEx(sub, "DisplayName")[0])
            except OSError:
                continue

            def val(key, default=""):
                try:
                    return str(winreg.QueryValueEx(sub, key)[0])
                except OSError:
                    return default
            item = (name, val("DisplayVersion"), val("InstallLocation"))
            if item not in seen:
                seen.add(item)
                yield item


def detect() -> dict:
    autocad, sketchup, others = [], [], []
    for name, ver, loc in _installed_programs():
        n = name.strip()
        # main product entries only (skip language packs, updates, add-ons)
        if re.fullmatch(r"AutoCAD( LT)? 20\d\d( - [A-Za-z가-힣 ()]+)?", n):
            autocad.append({"name": n, "version": ver, "location": loc, "lt": " LT " in f" {n} ",
                            "year": int(re.search(r"20\d\d", n).group())})
        elif re.fullmatch(r"AutoCAD (Architecture|Mechanical|Electrical|MEP|Map 3D|Plant 3D|Civil 3D) 20\d\d.*", n):
            autocad.append({"name": n, "version": ver, "location": loc, "lt": False,
                            "year": int(re.search(r"20\d\d", n).group())})
        elif re.fullmatch(r"(Trimble )?SketchUp( Pro| Make)? ?20\d\d.*", n) and "Viewer" not in n and "LayOut" not in n:
            sketchup.append({"name": n, "version": ver, "location": loc, "year": int(re.search(r"20\d\d", n).group())})
        elif re.match(r"(ZWCAD|GstarCAD|BricsCAD|ZW3D)\b", n):
            others.append({"name": n, "version": ver, "location": loc})
    def uniq(items):  # same product listed twice (MSI + bootstrapper): keep the one with a folder
        best = {}
        for it in items:
            if it["name"] not in best or (it.get("location") and not best[it["name"]].get("location")):
                best[it["name"]] = it
        return list(best.values())
    autocad, sketchup, others = uniq(autocad), uniq(sketchup), uniq(others)
    autocad.sort(key=lambda d: -d["year"])
    sketchup.sort(key=lambda d: -d["year"])
    return {"autocad": autocad, "sketchup": sketchup, "other_cad": others}


def describe() -> list[str]:
    """Plain-Korean lines for status screens."""
    d = detect()
    lines = []
    full = [a for a in d["autocad"] if not a["lt"]]
    lt = [a for a in d["autocad"] if a["lt"]]
    if full:
        lines.append("설치된 AutoCAD: " + ", ".join(a["name"] for a in full) + "  (자동 조작 가능)")
    if lt:
        lines.append("설치된 AutoCAD LT: " + ", ".join(a["name"] for a in lt)
                     + "  (LT는 외부 연결이 막혀 있어 도면 자동 조작 불가 — 도면 파일(DXF) 처리와 엑셀·3D는 가능)")
    if not d["autocad"]:
        lines.append("AutoCAD 설치 정보를 찾지 못함 (설치 목록에 없는 방식으로 깔렸어도, 켜져 있으면 연결을 시도합니다)")
    if d["other_cad"]:
        lines.append("호환 CAD: " + ", ".join(o["name"] for o in d["other_cad"]) + "  (AutoCAD와 같은 방식으로 연결 시도 — 일부 기능 제한 가능)")
    if d["sketchup"]:
        lines.append("설치된 SketchUp: " + ", ".join(s["name"] for s in d["sketchup"])
                     + ("" if all(s["year"] >= 2017 for s in d["sketchup"]) else "  (2016 이하는 지원하지 않음)"))
    else:
        lines.append("SketchUp 설치 정보를 찾지 못함")
    return lines
