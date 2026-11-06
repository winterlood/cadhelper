#!/usr/bin/env python3
"""CAD도우미 MCP server (stdio). Codex launches this itself -- no window,
no port, no shortcut to click.

Tools: AutoCAD drafting (vendored AutoCAD-AI, MIT) + analysis/areas,
SketchUp bridge, 3D scene -> HTML/DWG, Excel 견적서/표, learning memory.
Every tool that changes a drawing or model is behind a Windows Yes/No dialog.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent
HOME = Path(os.environ.get("CADHELPER_HOME") or Path.home() / "CadHelper")
os.environ.setdefault("CADHELPER_HOME", str(HOME))
os.environ.setdefault("ACAD_MCP_SAVE_DIR", str(HOME / "output"))
os.environ.pop("ACAD_MCP_ENABLE_SEND_COMMAND", None)  # raw commands only via the gated cad_run_command
sys.path.insert(0, str(APP / "vendor"))
sys.path.insert(0, str(APP))

import config  # noqa: E402  (vendor)
config.LOG_DIR = HOME / "logs"
import server as vendor_server  # noqa: E402
import tools as vendor_tools  # noqa: E402
from mcp.server.fastmcp import FastMCP  # noqa: E402

from cadhelper import analysis, draft, excel, learn, safety, scene, sketchup  # noqa: E402

INSTRUCTIONS = """\
CAD도우미: 인테리어 사무소용 AutoCAD·SketchUp·엑셀 도우미. 사용자는 컴퓨터가 서툰 실무자다.

반드시 지킬 것
1. 새 대화에서 CAD/SketchUp/견적 일을 시작하면 먼저 learn_read를 호출해 사무소 정보·단가·배운 점을 확인한다.
2. 도면 질문은 cad_overview로 단위와 레이어를 먼저 확인한 뒤 cad_measure / cad_room_areas / cad_blocks로 잰다.
   답에는 숫자의 근거(어느 레이어, 몇 개 도형, 무엇을 뺐는지)를 한 줄로 붙인다. 추정이면 추정이라고 말한다.
3. 도면·모델을 바꾸는 도구는 실행 전에 Windows 확인창이 뜬다. 그 전에 대화에서도 무엇을 바꿀지 쉬운 말로 설명하고 동의를 받는다.
   사용자가 '아니요'를 누르면 같은 변경을 다시 시도하지 않는다.
4. 새 파일(엑셀, HTML, DXF, PNG)은 항상 출력 폴더에 새로 만든다. 기존 파일을 덮어쓰지 않는다.
5. 사용자가 고쳐주거나 선호를 말하면 learn_note로 저장한다. 같은 종류의 요청이 두 번째로 오면 learn_save_skill로 절차를 저장한다.
6. 답은 짧은 한국어로, 전문용어 대신 쉬운 말로. 파일을 만들었으면 open_file로 열어 보여준다.
"""


_LAYOUT_PROPS = ("ConfigName", "CanonicalMediaName", "PlotType", "UseStandardScale",
                 "StandardScale", "CenterPlot", "PlotRotation")


def preserve_layout(fn):
    """capture_view / export_pdf change the active layout's plot settings to
    render; put every one of them back afterwards so the user's page setup
    is untouched."""
    import functools

    from acad import bridge

    @functools.wraps(fn)
    def wrapped(*args, **kwargs):
        def snap(acad):
            lay = acad.connect(launch_if_missing=False).ActiveDocument.ActiveLayout
            out = {}
            for p in _LAYOUT_PROPS:
                try:
                    out[p] = getattr(lay, p)
                except Exception:  # noqa: BLE001
                    pass
            return out

        try:
            saved = bridge.run(snap, 20)
        except Exception:  # noqa: BLE001
            saved = None
        try:
            return fn(*args, **kwargs)
        finally:
            if saved:
                def restore(acad):
                    lay = acad.connect(launch_if_missing=False).ActiveDocument.ActiveLayout
                    for p in _LAYOUT_PROPS:
                        if p in saved:
                            try:
                                setattr(lay, p, saved[p])
                            except Exception:  # noqa: BLE001
                                pass
                try:
                    bridge.run(restore, 20)
                except Exception:  # noqa: BLE001
                    pass

    return wrapped


class GatedRegistrar(vendor_server.LoggingRegistrar):
    """Logging + thread offload (vendor) with the approval gate inside."""

    def tool(self, *args, **kwargs):
        inner = super().tool(*args, **kwargs)

        def register(fn):
            if fn.__name__ in ("capture_view", "export_pdf"):
                fn = preserve_layout(fn)
            return inner(safety.gate(fn))
        return register


def build() -> FastMCP:
    config.ensure_dirs()
    mcp = FastMCP(name="CAD도우미", instructions=INSTRUCTIONS)
    reg = GatedRegistrar(mcp)
    vendor_tools.register(reg)
    analysis.register(reg)
    sketchup.register(reg)
    scene.register(reg)
    draft.register(reg)
    excel.register(reg)
    learn.register(reg)

    @reg.tool()
    def cadhelper_status() -> str:
        """Health check of everything (read-only): AutoCAD, SketchUp, folders."""
        lines = [f"CAD도우미 폴더: {HOME}", f"결과물 폴더: {HOME / 'output'}", f"백업 폴더: {safety.BACKUP_DIR}"]
        try:
            from cadhelper import compat
            lines += compat.describe()
        except Exception as exc:  # noqa: BLE001
            lines.append(f"(설치 프로그램 목록 확인 실패: {exc})")
        try:
            from acad import bridge

            def work(acad):
                app = acad.connect(launch_if_missing=False)
                docs = [d.Name for d in app.Documents]
                return app.Version, docs
            ver, docs = bridge.run(work, 20)
            lines.append(f"AutoCAD: 연결됨 (버전 {ver}), 열린 도면: {', '.join(docs) or '없음'}")
        except Exception as exc:  # noqa: BLE001
            lines.append(f"AutoCAD: 연결 안 됨 - {exc}")
        try:
            r = sketchup.call("ping", timeout=8)
            lines.append(f"SketchUp: 연결됨 (버전 {r['version']}), 모델: {r['title'] or '제목 없음'}")
        except Exception as exc:  # noqa: BLE001
            lines.append(f"SketchUp: 연결 안 됨 - {str(exc)[:160]}")
        return "\n".join(lines)

    @reg.tool()
    def open_file(path: str) -> str:
        """Open a result file for the user with its normal program (Excel,
        browser, AutoCAD, SketchUp, image viewer). Only opens; never edits."""
        p = Path(path)
        allowed = {".xlsx", ".html", ".pdf", ".png", ".jpg", ".dxf", ".dwg", ".skp", ".csv", ".txt"}
        if not p.exists():
            raise FileNotFoundError(f"파일이 없습니다: {p}")
        if p.suffix.lower() not in allowed:
            raise ValueError(f"이 종류의 파일은 열지 않습니다: {p.suffix}")
        os.startfile(str(p))  # noqa: S606 - opening a document for the user
        return f"열었습니다: {p}"

    @reg.tool()
    def open_output_folder() -> str:
        """Open the folder where all results are saved (in Windows Explorer)."""
        out = HOME / "output"
        out.mkdir(parents=True, exist_ok=True)
        os.startfile(str(out))  # noqa: S606
        return f"결과물 폴더를 열었습니다: {out}"

    return mcp


if __name__ == "__main__":
    build().run(transport="stdio")
