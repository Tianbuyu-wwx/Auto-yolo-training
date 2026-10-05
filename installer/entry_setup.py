# AYT-Setup.exe 入口。
#
#   AYT-Setup.exe                    → 图形安装向导（默认，双击即此）
#   AYT-Setup.exe scan|plan|install  → 命令行模式（透传给安装器 CLI）
#   AYT-Setup.exe --selftest         → 打包自检：只读扫描并写 %TEMP%\ayt-selftest.json
#
# 窗口版 exe 没有控制台：命令行模式在无 stdout 时把输出落盘到
# %TEMP%\ayt-setup-out.txt，便于脚本/排障取用。

from __future__ import annotations

import contextlib
import sys
from pathlib import Path

if not hasattr(sys, "_MEIPASS"):  # 开发模式运行需要项目根在 sys.path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _has_console() -> bool:
    return sys.stdout is not None and sys.stderr is not None


def main() -> int:
    # 兜底：任何未捕获异常都写进 %TEMP%\ayt-setup-error.txt（窗口版无控制台）
    def _hook(exc_type, exc, tb):
        import os
        import tempfile
        import traceback

        path = os.path.join(tempfile.gettempdir(), "ayt-setup-error.txt")
        with open(path, "w", encoding="utf-8") as fh:
            traceback.print_exception(exc_type, exc, tb, file=fh)

    sys.excepthook = _hook
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            with contextlib.suppress(Exception):
                stream.reconfigure(encoding="utf-8", errors="replace")

    argv = sys.argv[1:]

    if "--selftest" in argv:
        import json
        import os
        import tempfile

        from installer.ayt_setup.scan import scan

        out = os.path.join(tempfile.gettempdir(), "ayt-selftest.json")
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(scan(None), fh, ensure_ascii=False, indent=1)
        if _has_console():
            print("selftest ok ->", out)
        return 0

    from installer.ayt_setup.__main__ import main as cli_main

    if not argv:
        return cli_main(["gui"])

    if _has_console():
        return cli_main(argv)

    # 窗口版没有控制台 → 输出落盘
    import os
    import tempfile

    log_path = os.path.join(tempfile.gettempdir(), "ayt-setup-out.txt")
    with open(log_path, "w", encoding="utf-8") as fh:
        sys.stdout = fh
        try:
            return cli_main(argv)
        finally:
            fh.flush()
            sys.stdout = None  # type: ignore[assignment]  # 窗口版无控制台


if __name__ == "__main__":
    raise SystemExit(main())
