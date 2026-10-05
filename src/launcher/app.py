"""``ayt-launcher`` 入口：单实例 → 内嵌后端 → pywebview 窗口 → 生命周期。

Phase 1 验收（launcher-plan-2026-10-04.md）：

- 双击/命令行启动 → 窗口出现且加载启动器 UI；第二次启动唤起已有窗口、不双开；
- 关窗 → 进程干净退出（训练子进程不受影响——它本就独立）。
"""

from __future__ import annotations

import argparse
import contextlib
import ctypes
import ctypes.wintypes
import inspect
import os
import sys
import threading
import time
from pathlib import Path

from src.launcher.backend import DEFAULT_TITLE, LauncherBackend

_IS_WINDOWS = sys.platform == "win32"

# 窗口设计尺寸（逻辑像素）——create_window 与 frameless 尺寸校正共用
WINDOW_SIZE = (1440, 900)

# 单实例互斥体：Local\ = 每个登录会话一个（不跨用户抢占）。
# 句柄必须活到进程结束，所以模块级持有（进程退出由系统回收）。
MUTEX_NAME = "Local\\AYT-Launcher-Single-Instance"
_MUTEX_HANDLE: int | None = None
_ERROR_ALREADY_EXISTS = 183


def acquire_single_instance(name: str = MUTEX_NAME) -> tuple[bool, int | None]:
    """返回 ``(already_running, handle)``；非 Windows 恒 ``(False, None)``。

    ``CreateMutexW`` 的返回值必须设 restype（默认 c_int 会在 64 位截断句柄），
    且要**立即**读 ``GetLastError``。

    """
    global _MUTEX_HANDLE
    if not _IS_WINDOWS:
        return False, None
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CreateMutexW.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p)
    kernel32.GetLastError.restype = ctypes.c_uint32
    kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
    handle = kernel32.CreateMutexW(None, 0, name)
    error = kernel32.GetLastError()
    if error == _ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        return True, None
    _MUTEX_HANDLE = handle
    return False, handle


def focus_existing_window(title: str = DEFAULT_TITLE) -> bool:
    """把已运行的启动器窗口带到前台（单实例第二次启动时调用）。"""
    if not _IS_WINDOWS:
        return False
    user32 = ctypes.windll.user32
    user32.FindWindowW.restype = ctypes.c_void_p
    user32.FindWindowW.argtypes = (ctypes.c_wchar_p, ctypes.c_wchar_p)
    user32.ShowWindow.argtypes = (ctypes.c_void_p, ctypes.c_int)
    user32.SetForegroundWindow.argtypes = (ctypes.c_void_p,)
    hwnd = user32.FindWindowW(None, title)
    if not hwnd:
        return False
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    user32.SetForegroundWindow(hwnd)
    return True


def default_static_dir() -> Path:
    """启动器 UI 目录（Phase 1 为过渡页；Phase 2 换方向 D 正式 UI）。"""
    return Path(__file__).resolve().parent / "static"


class LauncherWinAPI:
    """无边框窗口控制桥：前端 .wctl 三键 → pywebview 窗口方法。

    js_api 对象须先于 ``create_window`` 传入，窗口创建后再由主流程 ``bind``
    （js_api 调用发生在 pywebview 自己的线程；方法保持无状态、只转发）。

    ⚠️ window 引用必须放**下划线私有属性**：pywebview 的 ``get_functions``
    注入 JS 桥时会递归遍历 js_api 对象的公开属性，若遇到 Window→.NET 对象
    会无限递归（实测 UI 线程 hung、健康检查全超时）。
    """

    def __init__(self) -> None:
        self._window = None  # 私有：下划线前缀被 get_functions 跳过

    def win_min(self) -> None:
        print("[win] minimize", flush=True)
        if self._window is not None:
            self._window.minimize()

    def win_max(self) -> None:
        print("[win] toggle-max", flush=True)
        if self._window is None:
            return
        if getattr(self._window, "maximized", False):
            self._window.restore()
        else:
            self._window.maximize()

    def win_close(self) -> None:
        print("[win] close", flush=True)
        if self._window is not None:
            self._window.destroy()

    # ---------- 文件对话框 / 下载另存（供前端按钮接线，零 UI 改动） ----------

    @staticmethod
    def _first_path(result: object) -> str:
        if not result:
            return ""
        if isinstance(result, (str, Path)):
            return str(result)
        return str(result[0]) if result else ""

    def pick_dir(self) -> str:
        """目录选择对话框；取消返回空串。"""
        import webview as _wv

        if self._window is None:
            return ""
        return self._first_path(self._window.create_file_dialog(_wv.FOLDER_DIALOG, allow_multiple=False))

    def pick_file(self, zip_only: bool = False) -> str:
        """文件选择对话框（zip_only=True 时过滤 .zip）；取消返回空串。"""
        import webview as _wv

        if self._window is None:
            return ""
        file_types = ("ZIP 压缩包 (*.zip)",) if zip_only else ("所有文件 (*.*)",)
        return self._first_path(
            self._window.create_file_dialog(_wv.OPEN_DIALOG, allow_multiple=False, file_types=file_types)
        )

    def save_from_url(self, url: str, suggested: str = "download.bin") -> str:
        """从本机后端 GET 下载并弹「另存为」写入；返回保存路径（取消为空串）。"""
        import urllib.request as _ur

        import webview as _wv

        if self._window is None:
            return ""
        try:
            with _ur.urlopen(url, timeout=60) as resp:
                payload = resp.read()
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"下载失败：{exc}") from exc
        path = self._first_path(self._window.create_file_dialog(_wv.SAVE_DIALOG, save_filename=suggested))
        if not path:
            return ""
        Path(path).write_bytes(payload)
        return path

    def save_text(self, text: str, suggested: str = "export.csv") -> str:
        """弹「另存为」保存文本（CSV/JSON 清单等）；返回保存路径（取消为空串）。"""
        import webview as _wv

        if self._window is None:
            return ""
        path = self._first_path(self._window.create_file_dialog(_wv.SAVE_DIALOG, save_filename=suggested))
        if not path:
            return ""
        Path(path).write_text(text, encoding="utf-8")
        return path

    def upload_zip(self, zip_path: str, api_base: str, name: str = "") -> dict:
        """把本地 zip 上传到本地后端（/api/datasets/upload）。供「上传数据集」按钮。"""
        from src.launcher.features import upload_zip as _upload

        return _upload(zip_path, api_base, name=name)


def default_state_dir() -> Path:
    """WebView 的 localStorage/缓存目录（放用户目录，不进仓库）。"""
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    path = Path(base) / "AYTLauncher"
    path.mkdir(parents=True, exist_ok=True)
    return path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="ayt-launcher",
        description="AYT 桌面启动器：内嵌管理面后端 + pywebview 窗口",
    )
    parser.add_argument("--port", type=int, default=0, help="后端端口（默认 0 = 自动挑空闲端口）")
    parser.add_argument("--base-dir", default=None, help="工作目录（dataset/ runs/ logs/ 所在；默认仓库根）")
    parser.add_argument("--debug", action="store_true", help="WebView 开启 devtools")
    parser.add_argument("--browser", action="store_true", help="不开 WebView，用系统默认浏览器打开（降级/调试）")
    parser.add_argument("--smoke", type=float, default=0, help="冒烟模式：窗口显示 N 秒后自动关闭（自动化验收用）")
    parser.add_argument("--allow-multi", action="store_true", help="跳过单实例检查（开发调试用）")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        import webview  # noqa: F401 —— 桌面壳依赖（pyproject extra: [launcher]）
    except ImportError:
        print(
            "缺少 pywebview：桌面启动器需要它。\n"
            '安装：pip install "auto-yolo-training[launcher]"（或 pip install "pywebview>=6.2"）',
            file=sys.stderr,
        )
        return 1

    already, _ = acquire_single_instance()
    if already and not args.allow_multi:
        if focus_existing_window():
            print("启动器已在运行 —— 已唤起现有窗口。")
        else:
            print("启动器已在运行。")
        return 0

    base_dir = args.base_dir
    if base_dir is None:
        from src.runtime_env import is_frozen, project_root

        if is_frozen():
            # 打包态：默认工作目录 = 探测到的项目根（训练产物写进项目内）
            base_dir = project_root()

    backend = LauncherBackend(
        base_dir=base_dir, port=args.port, frontend_dist=default_static_dir()
    )
    try:
        backend.start()
    except Exception as exc:
        print(f"[launcher] 后端启动失败：{exc}", file=sys.stderr)
        return 1

    print(f"[launcher] 后端就绪：{backend.url}（工作目录 {backend.base_dir}）")

    try:
        if args.browser:
            import webbrowser

            webbrowser.open(backend.url)
            if args.smoke:
                time.sleep(args.smoke)
            else:
                print("[launcher] 浏览器模式：Ctrl+C 退出。")
                while True:
                    time.sleep(3600)
            return 0

        try:
            import webview
        except ImportError:
            print(
                '[launcher] 未安装 pywebview。安装：pip install "auto-yolo-training[launcher]"'
                "（或 pip install pywebview）",
                file=sys.stderr,
            )
            return 2

        win_api = LauncherWinAPI()
        # 窗口居中主屏（逻辑坐标；物理换算在 _post_start 的 SetWindowPos 兜底校正）
        user32 = ctypes.windll.user32
        work = ctypes.wintypes.RECT()
        user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(work), 0)  # SPI_GETWORKAREA
        _sys_scale = user32.GetDpiForSystem() / 96
        win_x = int(((work.right - work.left) / _sys_scale - WINDOW_SIZE[0]) / 2)
        win_y = int(((work.bottom - work.top) / _sys_scale - WINDOW_SIZE[1]) / 2)
        window = webview.create_window(
            DEFAULT_TITLE,
            backend.url,
            width=WINDOW_SIZE[0],
            height=WINDOW_SIZE[1],
            min_size=(1024, 700),
            x=win_x,
            y=win_y,
            frameless=True,   # 无边框：UI 自带顶栏（.tbar）即窗口标题栏
            easy_drag=False,  # 拖动走 .tbar 的 drag-region；全窗拖动会抢页面交互
            js_api=win_api,   # .wctl 三键 → win_min / win_max / win_close
        )
        win_api._window = window

        def _post_start() -> None:
            # frameless 收尾三件套（实测踩坑）：
            # ① 尺寸校正：pywebview 先按「含装饰」建窗再剥边框，客户区少一圈；
            #    且 window.resize() 走 WinForms AutoScale，在不同 DPI 下会再乘一次
            #    （实测 150% 缩放时变成 2160×1350）。改 win32 SetWindowPos 物理直设。
            # ② 去 DWM 残留边框：Win11 给无边框窗画 1px 描边，深色下呈「黑边」；
            #    34 = DWMWA_BORDER_COLOR，0xFFFFFFFE = DWMWA_COLOR_NONE；33 = 圆角(2)。
            # ③ 双轮校正：pywebview 在窗口显示后还会再设一遍 Location/Size，
            #    首轮（1.3s）抢在它前、二轮（3.5s）盖过它，位置才稳定（实测 y 差 64px）。
            def _find_own_hwnd() -> int:
                """按标题从系统枚举自己的主窗。

                不用 ``window.native``：跨线程访问 pythonnet 的 Form 属性可能静默
                失败/异常（实测整个校正循环从未真正执行），win32 枚举才是可靠路径。
                同名辅助小窗（pywebview 会带一个 ~170×47）按面积取最大。
                """
                u32 = ctypes.windll.user32
                enum_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
                best = [0, -1]

                def cb(h, _lp):
                    if u32.GetWindowTextLengthW(h):
                        buf = ctypes.create_unicode_buffer(256)
                        u32.GetWindowTextW(h, buf, 256)
                        if buf.value == DEFAULT_TITLE and u32.IsWindowVisible(h):
                            r = ctypes.wintypes.RECT()
                            u32.GetWindowRect(h, ctypes.byref(r))
                            area = (r.right - r.left) * (r.bottom - r.top)
                            if area > best[1]:
                                best[0], best[1] = h, area
                    return True

                u32.EnumWindows(enum_proc(cb), 0)
                return int(best[0])

            def _work_area(hwnd: int) -> tuple[int, int, int, int]:
                """当前显示器的工作区（物理像素）。

                不用 SPI_GETWORKAREA：在跨线程调用下返回过荒谬值（实测 bottom=1528
                > 屏高 1440，居中因此算出 y=89）。GetMonitorInfo 是每显示器口径的
                正确路径；兜底与屏幕取 min，杜绝越界值。
                """
                u32 = ctypes.windll.user32
                u32.MonitorFromWindow.restype = ctypes.c_void_p
                u32.MonitorFromWindow.argtypes = (ctypes.c_void_p, ctypes.c_ulong)

                class _MI(ctypes.Structure):
                    _fields_ = [
                        ("cbSize", ctypes.c_ulong),
                        ("rcMonitor", ctypes.wintypes.RECT),
                        ("rcWork", ctypes.wintypes.RECT),
                        ("dwFlags", ctypes.c_ulong),
                    ]

                mi = _MI()
                mi.cbSize = ctypes.sizeof(_MI)
                try:
                    u32.GetMonitorInfoW(u32.MonitorFromWindow(hwnd, 2), ctypes.byref(mi))
                    w = (mi.rcWork.left, mi.rcWork.top, mi.rcWork.right, mi.rcWork.bottom)
                except Exception:  # noqa: BLE001
                    w = (0, 0, u32.GetSystemMetrics(0), u32.GetSystemMetrics(1))
                sw, sh = u32.GetSystemMetrics(0), u32.GetSystemMetrics(1)
                return (
                    max(0, min(w[0], sw)),
                    max(0, min(w[1], sh)),
                    max(0, min(w[2], sw)),
                    max(0, min(w[3], sh)),
                )

            def _fix_window() -> None:
                hwnd = _find_own_hwnd()
                if not hwnd:
                    return
                try:
                    user32 = ctypes.windll.user32
                    dpi = user32.GetDpiForWindow(hwnd)
                    phys_w = int(WINDOW_SIZE[0] * dpi / 96)
                    phys_h = int(WINDOW_SIZE[1] * dpi / 96)
                    wl, wt, wr, wb = _work_area(hwnd)
                    pos_x = wl + (wr - wl - phys_w) // 2
                    pos_y = wt + (wb - wt - phys_h) // 2
                    # SWP_NOZORDER(0x4) | SWP_NOACTIVATE(0x10)：尺寸 + 居中位直设
                    user32.SetWindowPos(hwnd, 0, pos_x, pos_y, phys_w, phys_h, 0x0004 | 0x0010)
                except Exception:  # noqa: BLE001
                    pass
                try:
                    dwmapi = ctypes.windll.dwmapi
                    none = ctypes.c_int(0xFFFFFFFE)
                    dwmapi.DwmSetWindowAttribute(hwnd, 34, ctypes.byref(none), ctypes.sizeof(none))
                    round_pref = ctypes.c_int(2)  # DWMWCP_ROUND
                    dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(round_pref), ctypes.sizeof(round_pref))
                except Exception:  # noqa: BLE001
                    pass

            # ③ 位置/尺寸的「监控-纠正」循环：pywebview + WinForms 在 frameless 下
            #    会反复把位置再换算一遍（实测最终偏 +64 物理像素、且晚于任何单次调用），
            #    任何一次性校正都会被打回；改成持续对冲：每 0.5s 检查一次，
            #    偏离目标（工作区居中）即 SetWindowPos 拉回，连续 3s 正确后退出（最长 ~18s）。
            def _steady_fix() -> None:
                stable = 0
                for _ in range(36):
                    _fix_window()
                    time.sleep(0.5)
                    try:
                        hwnd2 = _find_own_hwnd()
                        if not hwnd2:
                            stable = 0
                            continue
                        r = ctypes.wintypes.RECT()
                        ctypes.windll.user32.GetWindowRect(hwnd2, ctypes.byref(r))
                        dpi2 = ctypes.windll.user32.GetDpiForWindow(hwnd2)
                        ww = int(WINDOW_SIZE[0] * dpi2 / 96)
                        wh = int(WINDOW_SIZE[1] * dpi2 / 96)
                        wl2, wt2, wr2, wb2 = _work_area(hwnd2)
                        tx = wl2 + (wr2 - wl2 - ww) // 2
                        ty = wt2 + (wb2 - wt2 - wh) // 2
                        if (r.left, r.top, r.right - r.left) == (tx, ty, ww):
                            stable += 1
                            if stable >= 6:
                                break
                        else:
                            stable = 0
                    except Exception:  # noqa: BLE001
                        pass

            time.sleep(1.3)
            threading.Thread(target=_steady_fix, name="frameless-steady-fix", daemon=True).start()
            if args.smoke:
                time.sleep(args.smoke)
                with contextlib.suppress(Exception):  # 用户已手关时 destroy 幂等兜底
                    window.destroy()

        start_kwargs: dict = {
            "func": _post_start,
            "debug": args.debug,
            "private_mode": False,  # localStorage 持久化（主题/偏好）
            "storage_path": str(default_state_dir()),
        }
        supported = set(inspect.signature(webview.start).parameters)
        start_kwargs = {k: v for k, v in start_kwargs.items() if k in supported}
        try:
            webview.start(**start_kwargs)
        except TypeError:
            # 版本差异兜底：退回最小参数面，宁可丢持久化也要能开窗
            webview.start(debug=args.debug)
        return 0
    finally:
        backend.stop()
        print("[launcher] 已退出（训练子进程不受影响）。")


if __name__ == "__main__":
    raise SystemExit(main())
