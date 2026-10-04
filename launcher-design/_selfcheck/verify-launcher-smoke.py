# -*- coding: utf-8 -*-
"""启动器冒烟验证：窗口探测 → 截图 → 健康检查 → 等自关 → 出 JSON 结果。"""
import ctypes
import json
import sys
import time
import urllib.request
from ctypes import wintypes
from pathlib import Path

SKILL_SCRIPTS = r"C:\Users\Tianbuyu\AppData\Local\hermes\skills\software-development\python-desktop-app-packaging\scripts"
sys.path.insert(0, SKILL_SCRIPTS)
import win_shot  # noqa: E402

TITLE = "AYT 启动器"
REPO = Path(r"E:\项目\Auto-yolo-training")
OUT_SHOT = REPO / "launcher-design" / "shots" / "phase1" / "launcher-window.png"
RESULT_PATH = Path(r"C:\Users\Tianbuyu\AppData\Local\hermes\cache\scratch\launcher_smoke_result.json")

win_shot.be_dpi_aware()
user32 = ctypes.windll.user32
user32.FindWindowW.restype = ctypes.c_void_p
user32.FindWindowW.argtypes = (ctypes.c_wchar_p, ctypes.c_wchar_p)
user32.IsWindowVisible.argtypes = (ctypes.c_void_p,)
user32.GetWindowRect.argtypes = (ctypes.c_void_p, ctypes.POINTER(wintypes.RECT))
user32.PostMessageW.argtypes = (ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p)

result = {"title": TITLE}

EnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
user32.EnumWindows.restype = ctypes.c_bool


def find_main_window():
    """收集所有「AYT 启动器」可见窗，取面积最大者。

    pywebview/WinForms 会带一个同标题的小辅助窗（~170x47），
    FindWindowW 命中哪个不确定——必须按面积挑主窗（实测踩坑）。
    """
    best = [0, -1]

    def cb(hwnd, _lp):
        n = user32.GetWindowTextLengthW(hwnd)
        if n == 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        if buf.value != TITLE or not user32.IsWindowVisible(hwnd):
            return True
        r = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(r))
        area = (r.right - r.left) * (r.bottom - r.top)
        if area > best[1]:
            best[0], best[1] = hwnd, area
        return True

    user32.EnumWindows(EnumProc(cb), 0)
    return best[0]


# 1) 等主窗出现（最多 ~20s），并等尺寸稳定（宽 ≥ 900 且连续 3 次不变）
hwnd = 0
for _ in range(50):
    h = find_main_window()
    if h:
        hwnd = h
        break
    time.sleep(0.4)
if hwnd:
    prev = None
    stable = 0
    for _ in range(50):
        r = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(r))
        cur = (r.right - r.left, r.bottom - r.top)
        if cur[0] >= 900 and cur == prev:
            stable += 1
            if stable >= 3:
                break
        else:
            stable = 0
        prev = cur
        time.sleep(0.4)
result["hwnd"] = int(hwnd) if hwnd else 0
result["window_visible"] = bool(hwnd)

# 2) 端口文件 + health
port_file = REPO / "logs" / "launcher-port.txt"
port = None
for _ in range(20):
    if port_file.exists():
        port = port_file.read_text(encoding="utf-8").strip()
        break
    time.sleep(0.3)
result["port"] = port
if port:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=3) as r:
            result["health"] = json.loads(r.read())
    except Exception as e:
        result["health_error"] = str(e)

# 3) 截图（PrintWindow；若近空白（WebView2 合成窗口的已知风险）改用屏幕抓取兜底）
if hwnd:
    OUT_SHOT.parent.mkdir(parents=True, exist_ok=True)
    try:
        w, h = win_shot.capture(hwnd, OUT_SHOT)
        from PIL import Image, ImageStat

        tmp = Image.open(OUT_SHOT).convert("L")
        result["capture"] = {"path": str(OUT_SHOT), "size": [w, h]}
        result["capture_stdev"] = round(ImageStat.Stat(tmp).stddev[0], 2)
        if ImageStat.Stat(tmp).stddev[0] < 5:
            from PIL import ImageGrab

            rect = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            grab = ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom))
            grab.save(OUT_SHOT)
            result["capture_fallback"] = True
            result["capture_stdev"] = round(
                ImageStat.Stat(Image.open(OUT_SHOT).convert("L")).stddev[0], 2
            )
    except Exception as e:  # noqa: BLE001
        result["capture_error"] = repr(e)

# 3.5) 模拟点击 UI 自绘「关闭」按钮（.wctl 第 3 键；无边框 → 内容坐标即窗口坐标）
#      先点窗口中部激活，再点右上关闭；未关则补一击（首击被激活吃掉时兜底）
if hwnd:
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    win_w = rect.right - rect.left
    win_h = rect.bottom - rect.top

    def _click(x, y):
        user32.SetCursorPos(x, y)
        time.sleep(0.2)
        user32.mouse_event(0x0002, 0, 0, 0, 0)  # LEFTDOWN
        time.sleep(0.08)
        user32.mouse_event(0x0004, 0, 0, 0, 0)  # LEFTUP

    _click(rect.left + win_w // 2, rect.top + win_h // 2)  # 激活窗（点在内容上，无害）
    time.sleep(0.5)
    cx = rect.right - 28   # 按钮宽 46 CSS ≈ 57.5 物理，贴右缘 → 中心 ≈ right-29
    cy = rect.top + 27     # 顶栏高 44 CSS ≈ 55 物理 → 中心 ≈ top+27
    _click(cx, cy)
    time.sleep(0.6)
    if find_main_window():  # 未关 → 再补一击
        _click(cx, cy)
        time.sleep(1.5)
    result["close_via_click"] = not find_main_window()
    result["close_click_at"] = [cx, cy]

# 4) 等窗口自动关闭（--smoke）；超时则发 WM_CLOSE 兜底
gone = False
for _ in range(80):
    if not find_main_window():
        gone = True
        break
    time.sleep(0.5)
if not gone and hwnd:
    user32.PostMessageW(hwnd, 0x0010, 0, 0)
    time.sleep(3)
    gone = not find_main_window()
    result["forced_close"] = True
result["window_closed"] = gone

RESULT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=1))
