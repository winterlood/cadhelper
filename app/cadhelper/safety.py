"""Hard safety gate: a human must click "예" on a Windows dialog before any
tool that changes a drawing or a SketchUp model is allowed to run.

This does not rely on the AI following instructions. The dialog is shown by
the MCP server process itself, on the user's desktop, and the tool body only
runs when the user approves. The dialog names the drawing that will change,
shows SketchUp code verbatim, and times out (= 아니요) before Codex gives up
on the call, so a late click can never run a stale change. Before the first
approved change to a saved AutoCAD drawing, the file is copied to backups.
"""

from __future__ import annotations

import ctypes
import functools
import json
import os
import re
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

HOME = Path(os.environ.get("CADHELPER_HOME") or Path.home() / "CadHelper")
BACKUP_DIR = HOME / "backups"
LOG_FILE = HOME / "logs" / "approvals.jsonl"
OUT_DIR = Path(os.environ.get("CADHELPER_OUTPUT") or HOME / "output")
_current_out: Path | None = None   # 지금 열린 프로젝트의 결과물 폴더 (projects.project_open 이 바꿈)


def out_dir() -> Path:
    """Where results go now: the open project's 결과물 folder, else the default."""
    return _current_out or OUT_DIR


def set_out_dir(p: Path | None) -> None:
    global _current_out
    _current_out = p
    try:  # vendor AutoCAD tools (capture_view, save_drawing ...) write to config.SAVE_DIR
        import config
        config.SAVE_DIR = p or OUT_DIR
        config.SAVE_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:  # noqa: BLE001
        pass

# Codex tool_timeout_sec is 900 (set by the installer); answer well before it.
DIALOG_TIMEOUT_S = int(os.environ.get("CADHELPER_DIALOG_TIMEOUT", "540"))

_MB_YESNO = 0x04
_MB_ICONWARNING = 0x30
_MB_TOPMOST = 0x40000
_MB_SETFOREGROUND = 0x10000
_MB_SYSTEMMODAL = 0x1000
_IDYES = 6
_MB_TIMEDOUT = 32000

_lock = threading.Lock()
_backed_up: set[str] = set()


class ChangeRefused(RuntimeError):
    """Raised when the user clicks 아니요 (or does not answer); nothing ran."""


def _log(entry: dict) -> None:
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        entry["at"] = datetime.now().isoformat(timespec="seconds")
        with LOG_FILE.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except Exception:  # noqa: BLE001 - logging must never block a decision
        pass


def ask_user(title: str, message: str, timeout_s: int | None = None) -> bool:
    """Topmost Yes/No dialog. True only for 예; 아니요 or no answer = False."""
    if os.environ.get("CADHELPER_AUTO_DENY") == "1":  # automated tests
        return False
    flags = _MB_YESNO | _MB_ICONWARNING | _MB_TOPMOST | _MB_SETFOREGROUND | _MB_SYSTEMMODAL
    timeout_ms = int((timeout_s or DIALOG_TIMEOUT_S) * 1000)
    user32 = ctypes.windll.user32
    with _lock:  # one dialog at a time
        try:
            fn = user32.MessageBoxTimeoutW
            fn.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_wchar_p,
                           ctypes.c_uint, ctypes.c_ushort, ctypes.c_uint]
            result = fn(None, message, title, flags, 0, timeout_ms)
        except AttributeError:  # very old Windows: no timeout available
            result = user32.MessageBoxW(None, message, title, flags)
    return result == _IDYES


def active_drawing() -> tuple[str, str]:
    """(name, full path) of the active AutoCAD drawing, without launching
    AutoCAD or creating a drawing. ("", "") when none."""
    try:
        from acad import bridge  # vendor module; imported lazily

        def work(acad):
            app = acad.connect(launch_if_missing=False)
            if app.Documents.Count == 0:
                return "", ""
            doc = app.ActiveDocument
            try:
                full = doc.FullName
            except Exception:  # noqa: BLE001
                full = ""
            return doc.Name, full

        return bridge.run(work, 20)
    except Exception:  # noqa: BLE001
        return "", ""


def backup_drawing(full: str) -> str:
    """Copy a saved drawing once per server session. Never raises."""
    if not full or not Path(full).exists():
        return "(저장된 적 없는 새 도면이라 파일 백업은 건너뜀)"
    if full in _backed_up:
        return ""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    target = BACKUP_DIR / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}_{Path(full).name}"
    try:
        shutil.copy2(full, target)
    except Exception as exc:  # noqa: BLE001
        return f"(백업 실패: {exc} -- 사용자에게 알릴 것)"
    _backed_up.add(full)
    _log({"event": "backup", "source": full, "copy": str(target)})
    return f"(변경 전 원본 백업: {target})"


def _short(value: Any, limit: int = 160) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return text if len(text) <= limit else text[:limit] + " …"


def _count(v) -> int:
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except Exception:  # noqa: BLE001
            return 0
    return len(v) if isinstance(v, (list, tuple)) else 0


# Ruby that can reach outside the SketchUp model is refused outright.
_RUBY_FORBIDDEN = re.compile(
    r"`|%x|\bsystem\b|\bexec\b|\bspawn\b|\bfork\b|\bopen\s*\(|IO\.|File\.|FileUtils|Dir\.|"
    r"\brequire\b|\bload\b|Open3|Process\.|Kernel\.|Net::|Socket|URI\.|ObjectSpace|"
    r"\beval\b|instance_eval|class_eval|send\s*\(|__send__|UI\.openURL|Sketchup\.send_action|"
    r"\.save\b|save_as|\.close\b|Sketchup\.quit|\bexit\b|ENV\["
)


def check_ruby(code: str) -> None:
    m = _RUBY_FORBIDDEN.search(code or "")
    if m:
        raise ChangeRefused(
            f"보안상 SketchUp 코드에서 '{m.group(0)}' 는 쓸 수 없습니다 (파일·프로그램·네트워크 접근, 저장/종료 금지). "
            "모델 안의 형상·재질·태그만 다루는 코드로 다시 작성하세요. 저장은 sketchup_save_copy 를 쓰세요."
        )


def _save_precheck(kwargs: dict) -> None:
    name = re.sub(r'[\\/:*?"<>|]+', "_", str(kwargs.get("filename", "")).strip())
    if not name:
        return
    stem = Path(name).stem
    if (out_dir() / f"{stem}.dwg").exists():
        raise ChangeRefused(f"결과물 폴더에 '{stem}.dwg' 가 이미 있어 덮어쓰지 않았습니다. 다른 이름을 쓰세요.")


# tool -> (target, describe(kwargs), precheck(kwargs) or None)
GATED: dict[str, tuple[str, Callable[[dict], str], Callable[[dict], None] | None]] = {
    # vendor AutoCAD tools
    "draw_batch": ("autocad", lambda a: f"도면에 객체 {_count(a.get('operations'))}개를 새로 그립니다.", None),
    "draw_hatch": ("autocad", lambda a: f"해치(채우기)를 추가합니다. 대상={a.get('boundary_handle')}", None),
    "dim_linear": ("autocad", lambda a: "치수선을 추가합니다.", None),
    "dim_aligned": ("autocad", lambda a: "치수선을 추가합니다.", None),
    "create_layer": ("autocad", lambda a: f"레이어 '{a.get('name')}'를 만듭니다.", None),
    "erase_entity": ("autocad", lambda a: f"객체 {a.get('handle')}를 ※삭제※합니다.", None),
    "save_drawing": ("autocad", lambda a: (
        f"도면을 결과물 폴더에 '{a.get('filename')}' 이름으로 저장합니다.\n"
        "※ 저장 후 AutoCAD에 열린 도면은 이 새 파일이 됩니다. 원본에 저장하려면 원본을 다시 여세요."), _save_precheck),
    "close_autocad": ("autocad", lambda a: "AutoCAD를 종료합니다." + (
        " 저장하지 않은 내용이 사라집니다!" if a.get("discard_changes") else ""), None),
    # CadHelper tools
    "cad_set_properties": ("autocad", lambda a: f"객체 {_count(a.get('handles'))}개의 속성을 바꿉니다: {_short(a.get('changes'))}", None),
    "cad_erase_many": ("autocad", lambda a: f"객체 {_count(a.get('handles'))}개를 ※삭제※합니다.", None),
    "cad_run_command": ("autocad", lambda a: f"AutoCAD 명령을 실행합니다:\n  {_short(a.get('command'), 300)}", None),
    "sketchup_run_ruby": ("sketchup", lambda a: "SketchUp 모델에 아래 코드를 실행합니다:\n\n" + _short(a.get("code"), 700),
                          lambda a: check_ruby(a.get("code", ""))),
    "sketchup_build_scene": ("sketchup", lambda a: "현재 SketchUp 모델에 3D 형상을 새로 추가합니다.", None),
}

_TARGET_NAME = {"autocad": "AutoCAD 도면", "sketchup": "SketchUp 모델"}


def gate(fn: Callable) -> Callable:
    """Wrap a synchronous tool so it only runs after the user approves."""
    name = fn.__name__
    if name not in GATED:
        return fn
    target, describe, precheck = GATED[name]

    @functools.wraps(fn)
    def guarded(*args, **kwargs):
        if precheck:
            precheck(kwargs)
        try:
            what = describe(kwargs)
        except Exception:  # noqa: BLE001
            what = name
        where, full = ("", "")
        if target == "autocad":
            where, full = active_drawing()
            if not where and name != "close_autocad":
                raise ChangeRefused("AutoCAD에 열린 도면이 없어 아무것도 바꾸지 않았습니다. 사용자에게 도면을 열어 달라고 하세요.")
        reason = kwargs.get("purpose") or ""
        message = (
            f"AI가 {_TARGET_NAME[target]}을(를) 바꾸려고 합니다.\n\n"
            + (f"대상 도면: {where}\n\n" if where else "")
            + f"{what}\n"
            + (f"\n이유: {_short(reason, 200)}\n" if reason else "")
            + "\n허락하시겠습니까?\n\n  예 = 이번 한 번 실행\n  아니요 = 실행하지 않음\n"
            + f"  ({DIALOG_TIMEOUT_S // 60}분 동안 누르지 않으면 '아니요'로 처리)"
        )
        started = time.monotonic()
        approved = ask_user("CAD도우미 - 변경 확인", message)
        _log({"event": "ask", "tool": name, "approved": approved, "drawing": where,
              "args": {k: _short(v, 300) for k, v in kwargs.items()},
              "seconds": round(time.monotonic() - started, 1)})
        if not approved:
            raise ChangeRefused(
                "사용자가 확인창에서 '아니요'를 눌렀거나 응답하지 않아 변경이 실행되지 않았습니다. 도면/모델은 그대로입니다. "
                "다시 시도하지 말고, 무엇을 바꾸려 했는지 쉬운 말로 설명한 뒤 사용자가 원하는지 대화로 물어보세요."
            )
        if target == "autocad":
            now, full2 = active_drawing()
            if now != where:
                raise ChangeRefused(f"확인하는 동안 활성 도면이 '{where}'에서 '{now}'(으)로 바뀌어 실행하지 않았습니다. 다시 확인받으세요.")
            note = backup_drawing(full2)
        else:
            note = ""
        result = fn(*args, **kwargs)
        if note and isinstance(result, str):
            result = f"{result}\n{note}"
        return result

    return guarded
