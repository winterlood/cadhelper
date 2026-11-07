"""SketchUp tools. Talks to the CadHelper Ruby plugin (cadhelper_bridge.rb)
that the installer puts in SketchUp's Plugins folder. SketchUp has no COM
interface, so the plugin opens a localhost-only socket protected by a token.
"""

from __future__ import annotations

import json
import os
import secrets
import socket
from pathlib import Path

from mcp.server.fastmcp import Image

from .safety import HOME, OUT_DIR

PORT = int(os.environ.get("CADHELPER_SKETCHUP_PORT", "47811"))
TOKEN_FILE = HOME / "sketchup_token.txt"


class SketchUpError(RuntimeError):
    pass


def _token() -> str:
    if not TOKEN_FILE.exists():
        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(secrets.token_hex(16), encoding="utf-8")
    return TOKEN_FILE.read_text(encoding="utf-8").strip()


def call(op: str, timeout: float = 300.0, **payload) -> object:
    req = {"token": _token(), "op": op, **payload}
    try:
        with socket.create_connection(("127.0.0.1", PORT), timeout=5) as s:
            s.settimeout(timeout)
            s.sendall((json.dumps(req, ensure_ascii=False) + "\n").encode("utf-8"))
            buf = b""
            while not buf.endswith(b"\n"):
                chunk = s.recv(65536)
                if not chunk:
                    break
                buf += chunk
    except (ConnectionRefusedError, socket.timeout, OSError) as exc:
        raise SketchUpError(
            "SketchUp에 연결할 수 없습니다. SketchUp을 켜고 모델(새 파일이라도)을 연 상태인지 확인하세요. "
            "SketchUp을 켠 상태인데도 안 되면, 설치 후 SketchUp을 한 번 껐다 켜야 연결 플러그인이 로드됩니다. "
            f"({exc})"
        ) from exc
    resp = json.loads(buf.decode("utf-8") or "{}")
    if not resp.get("ok"):
        raise SketchUpError(f"SketchUp 오류: {resp.get('error')} {resp.get('trace') or ''}")
    return resp.get("result")


def register(mcp) -> None:

    @mcp.tool()
    def sketchup_status() -> str:
        """Check that SketchUp is running with the CadHelper plugin (read-only)."""
        r = call("ping", timeout=10)
        return f"SketchUp 연결됨. 버전 {r['version']}, 현재 모델: {r['title'] or '(제목 없음)'} {r['model'] or '(저장 안 됨)'}"

    @mcp.tool()
    def sketchup_model_info() -> str:
        """Summary of the open SketchUp model (read-only): size, tags, top-level
        groups/components with counts, and face AREA totals per material and per
        tag in ㎡ -- use these for finish quantities (tile, paint, flooring).
        Material totals count every face of a solid (a floor slab's top, bottom
        and edges); for flooring/countertops use the separate "위를 향한 면"
        totals, and for walls subtract what is not finished. Say which you used.
        """
        r = call("info", timeout=300)
        lines = [f"모델: {r['title']}  ({r['path'] or '저장 안 됨'})  SketchUp {r['version']}",
                 f"크기(m): 가로 {r['size_m'][0]} × 세로 {r['size_m'][1]} × 높이 {r['size_m'][2]}  면 {r['faces']}개, 선택된 것 {r['selection_count']}개",
                 "\n재질별 면적(㎡):"]
        lines += [f"- {k}: {v:,.2f}" for k, v in r["area_by_material_m2"]]
        if r.get("area_up_by_material_m2"):
            lines.append("\n위를 향한 면만 (바닥재·상판 물량용, ㎡):")
            lines += [f"- {k}: {v:,.2f}" for k, v in r["area_up_by_material_m2"]]
        lines.append("\n태그별 면적(㎡):")
        lines += [f"- {k}: {v:,.2f}" for k, v in r["area_by_tag_m2"]]
        if r["components_top_level"]:
            lines.append("\n그룹/컴포넌트 개수:")
            lines += [f"- {k}: {v}" for k, v in r["components_top_level"]]
        lines.append("\n태그: " + ", ".join(f"{n}{'' if vis else '(숨김)'}" for n, vis in r["tags"]))
        return "\n".join(lines)

    @mcp.tool()
    def sketchup_run_ruby(code: str, purpose: str) -> str:
        """Run SketchUp Ruby API code inside SketchUp (needs the user's approval
        on a dialog every time, because it can change the model). The code runs
        as one undoable operation; the value of the last expression is returned.
        purpose: one short Korean sentence telling the user what this does.
        For read-only questions prefer sketchup_model_info.
        """
        return str(call("eval", code=code, label="CadHelper: " + purpose[:40]))

    @mcp.tool()
    def sketchup_build_scene(scene_path: str) -> str:
        """Build a CadHelper scene JSON (see scene_build_html) as 3D geometry in
        the open SketchUp model, one tag per scene layer (needs approval).
        Open a NEW empty SketchUp file first unless the user wants it merged.
        """
        from .scene import write_expanded
        p = write_expanded(scene_path)  # validates; window/door/material -> plain prisms
        return str(call("build_scene", path=str(p.resolve()).replace("\\", "/")))

    @mcp.tool()
    def sketchup_capture(filename: str = "sketchup_view.png", birds_eye: bool = True) -> list:
        """Picture of the model so you can check your work. birds_eye=True moves
        the camera to a bird's-eye view of everything first; False keeps the
        user's current view."""
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        path = (OUT_DIR / Path(filename).name).with_suffix(".png")
        call("capture", path=str(path).replace("\\", "/"), iso=birds_eye, zoom=False, width=1400, height=900)
        return [f"저장: {path}", Image(path=str(path))]

    @mcp.tool()
    def sketchup_save_copy(filename: str) -> str:
        """Save a COPY of the open model as .skp in the output folder (the open
        file itself is not changed)."""
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        path = (OUT_DIR / Path(filename).name).with_suffix(".skp")
        call("save_copy", path=str(path).replace("\\", "/"))
        return f"사본 저장: {path}"
