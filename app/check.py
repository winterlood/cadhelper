"""CAD도우미 점검: double-clicked from the desktop. Prints, in plain Korean,
whether each part works, then waits for Enter."""

import os
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent
sys.path.insert(0, str(APP / "vendor"))
sys.path.insert(0, str(APP))
os.environ.setdefault("CADHELPER_HOME", str(Path.home() / "CadHelper"))
os.environ.setdefault("ACAD_MCP_SAVE_DIR", str(Path(os.environ["CADHELPER_HOME"]) / "output"))


def _desktop() -> str:
    try:
        import ctypes
        from ctypes import wintypes
        buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
        ctypes.windll.shell32.SHGetFolderPathW(None, 0x0010, None, 0, buf)  # CSIDL_DESKTOPDIRECTORY
        if buf.value:
            return buf.value
    except Exception:  # noqa: BLE001
        pass
    return str(Path.home() / "Desktop")


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    print("=" * 50)
    print("  CAD도우미 점검")
    print("=" * 50)
    ok = True
    try:
        import cadhelper_server
        cadhelper_server.build()
        print("[정상] CAD도우미 프로그램")
    except Exception as exc:  # noqa: BLE001
        ok = False
        print(f"[문제] CAD도우미 프로그램을 불러오지 못함: {exc}")

    try:
        from cadhelper import compat
        for line in compat.describe():
            print("[정보] " + line)
    except Exception as exc:  # noqa: BLE001
        print(f"[확인] 설치 프로그램 목록을 읽지 못함: {exc}")

    codex_cfg = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "config.toml"
    if codex_cfg.exists() and "[mcp_servers.cad-helper]" in codex_cfg.read_text(encoding="utf-8", errors="ignore"):
        print("[정상] Codex에 등록됨")
    else:
        ok = False
        print("[문제] Codex에 등록 안 됨 -> 설치하기를 다시 실행하세요")

    work = Path(os.environ.get("SystemDrive", "C:") + "\\") / "CAD작업"
    if not work.is_dir():
        work = Path(_desktop()) / "CAD작업"
    if work.is_dir():
        print(f"[정상] Codex 프로젝트 폴더: {work}  (Codex 앱에서 이 폴더를 프로젝트로 추가해 쓰세요)")
    else:
        print("[확인] C:\\CAD작업 폴더가 없음 -> 설치하기를 다시 실행하세요")

    try:
        from acad import bridge

        def work(acad):
            app = acad.connect(launch_if_missing=False)
            return app.Version, [d.Name for d in app.Documents]
        ver, docs = bridge.run(work, 20)
        print(f"[정상] AutoCAD 연결 (버전 {ver}) 열린 도면: {', '.join(docs) or '없음'}")
    except Exception as exc:  # noqa: BLE001
        print(f"[확인] AutoCAD가 꺼져 있거나 연결 안 됨 (켜고 도면을 열면 됩니다): {str(exc)[:120]}")

    try:
        from cadhelper import sketchup
        r = sketchup.call("ping", timeout=8)
        print(f"[정상] SketchUp 연결 (버전 {r['version']})")
    except Exception:  # noqa: BLE001
        print("[확인] SketchUp이 꺼져 있음 (쓸 때 켜면 됩니다. 켜져 있는데 안 되면 SketchUp을 껐다 켜세요)")

    print("-" * 50)
    print("결과: " + ("이상 없음. Codex를 열고 질문하세요." if ok else "문제가 있습니다. 위 내용을 사진 찍어 보내 주세요."))
    print()
    try:
        input("엔터를 누르면 닫힙니다...")
    except EOFError:
        pass


if __name__ == "__main__":
    main()
