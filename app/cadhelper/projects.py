"""현장(프로젝트)별 폴더: C:\\work\\projects\\<현장 이름>\\

    도면\\    DWG·DXF·SKP (카톡으로 받은 파일 등을 여기로 복사해 둠)
    자료\\    사진·PDF·참고 이미지
    결과물\\  이 현장에서 만든 엑셀·3D·PPT·사진 (현장을 열면 자동으로 여기로 저장)
    현장정보.md  고객·주소·평수·메모 (대화가 바뀌어도 이어지는 현장 기억)

한 대화 안에서 여러 현장을 오갈 수 있다: project_open 으로 바꾸면 그때부터
결과물이 그 현장 폴더로 간다. 아무 현장도 안 열었으면 work\\결과물 로 간다.
파일은 복사만 하고 지우거나 덮어쓰지 않는다.
"""

from __future__ import annotations

import os
import re
import shutil
from datetime import date, datetime
from pathlib import Path

from . import safety
from .safety import HOME

WORK = HOME.parent
PROJECTS = Path(os.environ.get("CADHELPER_PROJECTS") or WORK / "projects")
SUBDIRS = ("도면", "자료", "결과물")
INFO = "현장정보.md"
DRAWING_EXT = {".dwg", ".dxf", ".skp", ".dwf", ".rvt", ".3dm", ".layout"}
_current: Path | None = None


def _clean(name: str) -> str:
    n = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', " ", str(name or "")).strip().strip(".")
    n = re.sub(r"\s+", " ", n)
    if not n:
        raise ValueError("현장 이름이 비어 있습니다.")
    return n[:60]


def _all() -> list[Path]:
    if not PROJECTS.exists():
        return []
    return sorted((p for p in PROJECTS.iterdir() if p.is_dir() and not p.name.startswith(".")),
                  key=lambda p: p.stat().st_mtime, reverse=True)


def _find(name: str) -> Path:
    want = _clean(name)
    items = _all()
    for p in items:
        if p.name == want:
            return p
    key = re.sub(r"\s+", "", want).lower()
    hits = [p for p in items if key in re.sub(r"\s+", "", p.name).lower()]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        names = ", ".join(p.name for p in items[:15]) or "(아직 현장이 없음)"
        raise FileNotFoundError(f"'{want}' 현장을 찾지 못했습니다. 있는 현장: {names}")
    raise ValueError("이름이 비슷한 현장이 여러 개입니다: " + ", ".join(p.name for p in hits) + " — 정확한 이름으로 다시 알려 주세요.")


def current() -> Path | None:
    return _current


def _files(d: Path, limit: int = 30) -> list[str]:
    if not d.exists():
        return []
    fs = sorted((f for f in d.rglob("*") if f.is_file()), key=lambda f: f.stat().st_mtime, reverse=True)
    out = [f"{f.relative_to(d)} ({datetime.fromtimestamp(f.stat().st_mtime):%m-%d %H:%M})" for f in fs[:limit]]
    if len(fs) > limit:
        out.append(f"... 외 {len(fs) - limit}개")
    return out


def _describe(p: Path) -> str:
    lines = [f"현장: {p.name}", f"폴더: {p}"]
    info = p / INFO
    if info.exists():
        lines += ["", info.read_text(encoding="utf-8-sig").strip()]
    for sd in SUBDIRS:
        fs = _files(p / sd)
        lines += ["", f"[{sd}] {len(fs)}개" + ("" if fs else " (비어 있음)")] + [f"  - {x}" for x in fs]
    return "\n".join(lines)


def _unique(dst: Path) -> Path:
    n = 2
    out = dst
    while out.exists():
        out = dst.with_name(f"{dst.stem} ({n}){dst.suffix}")
        n += 1
    return out


def register(mcp) -> None:

    @mcp.tool()
    def project_list() -> str:
        """List the 현장(project) folders under C:\\work\\projects, most recent
        first, with their memo line and file counts. Read-only."""
        items = _all()
        if not items:
            return f"아직 현장 폴더가 없습니다. ({PROJECTS})  project_create 로 만드세요."
        cur = _current.name if _current else "(없음 — 결과물은 work\\결과물)"
        lines = [f"현장 폴더: {PROJECTS}", f"지금 열린 현장: {cur}", ""]
        for p in items:
            counts = ", ".join(f"{sd} {len(list((p / sd).glob('*'))) if (p / sd).exists() else 0}" for sd in SUBDIRS)
            memo = ""
            info = p / INFO
            if info.exists():
                m = re.search(r"^- 고객: (.+)$", info.read_text(encoding="utf-8-sig"), re.M)
                memo = f" / 고객 {m.group(1).strip()}" if m else ""
            lines.append(f"- {p.name}{memo}  ({counts}, 최근 {datetime.fromtimestamp(p.stat().st_mtime):%Y-%m-%d})")
        return "\n".join(lines)

    @mcp.tool()
    def project_create(name: str, client: str = "", address: str = "", size: str = "", memo: str = "") -> str:
        """Create a new 현장 folder (도면/자료/결과물 + 현장정보.md) and open it.
        name: short site name the user uses, e.g. "신부평 32평 김철수".
        Creating folders changes no drawing, so no approval dialog. Never
        overwrites: if the name exists, it is just opened."""
        p = PROJECTS / _clean(name)
        existed = p.exists()
        for sd in SUBDIRS:
            (p / sd).mkdir(parents=True, exist_ok=True)
        info = p / INFO
        if not info.exists():
            info.write_text(
                f"# {p.name}\n\n- 고객: {client}\n- 주소: {address}\n- 규모: {size}\n- 만든 날: {date.today()}\n"
                + (f"- 메모: {memo}\n" if memo else "") + "\n## 기록\n", encoding="utf-8")
        global _current
        _current = p
        safety.set_out_dir(p / "결과물")
        head = "이미 있는 현장이라 열기만 했습니다." if existed else "새 현장을 만들고 열었습니다."
        return head + " 이제 결과물은 이 현장의 결과물 폴더에 저장됩니다.\n\n" + _describe(p)

    @mcp.tool()
    def project_open(name: str) -> str:
        """Switch to a 현장 (partial names work, e.g. "신부평"). From now on in
        this conversation every result (엑셀·3D·PPT·사진·DWG 사본) is saved in
        that 현장's 결과물 folder. Returns the 현장 memo and file lists, so read it
        before answering. Use project_list if unsure of the name."""
        p = _find(name)
        global _current
        _current = p
        safety.set_out_dir(p / "결과물")
        for sd in SUBDIRS:
            (p / sd).mkdir(parents=True, exist_ok=True)
        return "현장을 열었습니다. 결과물은 이 현장 폴더에 저장됩니다.\n\n" + _describe(p)

    @mcp.tool()
    def project_close() -> str:
        """Leave the current 현장; results go to C:\\work\\결과물 again."""
        global _current
        was = _current.name if _current else None
        _current = None
        safety.set_out_dir(None)
        return f"'{was}' 현장을 닫았습니다." if was else "열린 현장이 없었습니다."

    @mcp.tool()
    def project_note(text: str) -> str:
        """Add a dated line to the open 현장's 현장정보.md (고객 요청, 결정사항,
        치수, 일정...). This is the 현장's memory across conversations."""
        if not _current:
            raise RuntimeError("열린 현장이 없습니다. project_open 으로 먼저 여세요.")
        info = _current / INFO
        with info.open("a", encoding="utf-8") as fh:
            fh.write(f"- {date.today()} {text.strip()}\n")
        return f"'{_current.name}' 현장 기록에 추가했습니다."

    @mcp.tool()
    def project_add_file(source_path: str, subfolder: str = "") -> str:
        """COPY a file the user has elsewhere (카카오톡 받은 파일, 다운로드, 바탕화면,
        USB...) into the open 현장. DWG/DXF/SKP go to 도면, others to 자료 unless
        subfolder is given. The original is left untouched; an existing file
        with the same name is never overwritten (a number is added)."""
        if not _current:
            raise RuntimeError("열린 현장이 없습니다. project_open 또는 project_create 를 먼저 하세요.")
        src = Path(source_path.strip().strip('"'))
        if not src.is_file():
            raise FileNotFoundError(f"파일이 없습니다: {src}")
        sd = subfolder.strip() or ("도면" if src.suffix.lower() in DRAWING_EXT else "자료")
        if sd not in SUBDIRS:
            raise ValueError(f"subfolder 는 {', '.join(SUBDIRS)} 중 하나")
        dst = _unique(_current / sd / src.name)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        return f"복사했습니다: {dst}  (원본은 그대로 있음)"

    @mcp.tool()
    def project_find_files(pattern: str = "*.dwg", where: str = "") -> str:
        """Find files the user may mean, read-only. where: "" = the usual places
        (open 현장, 카카오톡 받은 파일, 다운로드, 바탕화면, 문서); or a folder path.
        pattern like "*.dwg", "*신부평*". Newest first."""
        roots: list[Path] = []
        if where.strip():
            roots = [Path(where.strip().strip('"'))]
        else:
            if _current:
                roots.append(_current)
            home = Path(os.environ.get("USERPROFILE") or Path.home())
            for sub in ("Documents\\카카오톡 받은 파일", "Downloads", "Desktop", "Documents",
                        "OneDrive\\바탕 화면", "OneDrive\\문서", "OneDrive\\Desktop", "OneDrive\\Documents"):
                d = home / sub
                if d.exists() and d not in roots:
                    roots.append(d)
        found: list[Path] = []
        for r in roots:
            try:
                it = r.rglob(pattern) if r == _current else list(r.glob(pattern)) + list(r.glob("*/" + pattern))
                found += [f for f in it if f.is_file()]
            except Exception:  # noqa: BLE001
                continue
        seen, uniq = set(), []
        for f in sorted(found, key=lambda f: f.stat().st_mtime, reverse=True):
            if str(f).lower() not in seen:
                seen.add(str(f).lower())
                uniq.append(f)
        if not uniq:
            return "찾지 못했습니다. 찾은 곳: " + ", ".join(str(r) for r in roots)
        return "\n".join(f"- {f}  ({datetime.fromtimestamp(f.stat().st_mtime):%Y-%m-%d %H:%M})" for f in uniq[:40])

    @mcp.tool()
    def project_open_drawing(filename: str) -> str:
        """Open a drawing from the open 현장's 도면 folder (or a full path) in
        AutoCAD (DWG/DXF) or SketchUp (SKP). Opening changes nothing. If that
        DWG is already open, AutoCAD just switches to it."""
        p = Path(filename.strip().strip('"'))
        if not p.is_absolute():
            if not _current:
                raise RuntimeError("열린 현장이 없습니다. 전체 경로를 주거나 project_open 을 먼저 하세요.")
            cands = [_current / "도면" / p.name] + list((_current / "도면").glob(f"*{p.stem}*"))
            cands = [c for c in cands if c.is_file()]
            if not cands:
                raise FileNotFoundError(f"도면 폴더에 '{p.name}' 이 없습니다.")
            p = cands[0]
        if not p.is_file():
            raise FileNotFoundError(f"파일이 없습니다: {p}")
        ext = p.suffix.lower()
        if ext in (".dwg", ".dxf"):
            from acad import bridge

            def work(acad):
                app = acad.connect(launch_if_missing=True)
                app.Visible = True
                want = str(p).lower()
                for doc in app.Documents:
                    try:
                        if doc.FullName and doc.FullName.lower() == want:
                            doc.Activate()
                            return doc.Name, True
                    except Exception:  # noqa: BLE001
                        continue
                return app.Documents.Open(str(p)).Name, False
            name, already = bridge.run(work, 240)
            return f"AutoCAD에서 {'이미 열려 있던 ' if already else ''}{name} 을(를) 열었습니다."
        if ext in (".skp", ".layout"):
            os.startfile(str(p))  # noqa: S606
            return f"SketchUp으로 열었습니다: {p.name} (켜지는 데 시간이 걸릴 수 있습니다)"
        raise ValueError("DWG, DXF, SKP 파일만 열 수 있습니다.")

    @mcp.tool()
    def project_open_folder(subfolder: str = "") -> str:
        """Show the open 현장's folder (or its 도면/자료/결과물) in Explorer."""
        base = _current or PROJECTS
        d = base / subfolder if subfolder and _current else base
        d.mkdir(parents=True, exist_ok=True)
        os.startfile(str(d))  # noqa: S606
        return f"폴더를 열었습니다: {d}"
