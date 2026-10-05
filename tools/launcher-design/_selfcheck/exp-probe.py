# -*- coding: utf-8 -*-
"""无边框对照探测：起实验窗 → 等 8s → 测 hung/尺寸/响应 → 杀 → 打印 JSON。argv[1]=配置名。"""
import ctypes
import json
import subprocess
import sys
import time
from ctypes import wintypes

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

user32 = ctypes.windll.user32
user32.FindWindowW.restype = ctypes.c_void_p
user32.FindWindowW.argtypes = (ctypes.c_wchar_p, ctypes.c_wchar_p)
user32.GetWindowRect.argtypes = (ctypes.c_void_p, ctypes.POINTER(wintypes.RECT))
user32.IsWindowVisible.argtypes = (ctypes.c_void_p,)
EnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)


def find(title):
    best = [0, -1]

    def cb(hwnd, _):
        n = user32.GetWindowTextLengthW(hwnd)
        if n:
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            if buf.value == title and user32.IsWindowVisible(hwnd):
                r = wintypes.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(r))
                area = (r.right - r.left) * (r.bottom - r.top)
                if area > best[1]:
                    best[0], best[1] = hwnd, area
        return True

    user32.EnumWindows(EnumProc(cb), 0)
    return best[0]


cfg = sys.argv[1]
title = 'EXP-WIN-' + cfg
proc = subprocess.Popen(
    ['C:/Python312/python.exe', 'exp-launch.py', cfg],
    cwd='E:/项目/Auto-yolo-training/tools/launcher-design/_selfcheck',
)

hwnd = 0
t0 = time.time()
for _ in range(40):
    hwnd = find(title)
    if hwnd:
        break
    time.sleep(0.4)

res = {'cfg': cfg, 'hwnd': hwnd, 'appear_s': round(time.time() - t0, 2)}
if hwnd:
    time.sleep(8)  # 模拟运行期（卡死窗口里 6-8 秒是关键时刻）
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    res['rect'] = [r.left, r.top, r.right - r.left, r.bottom - r.top]
    res['hung'] = bool(user32.IsHungAppWindow(hwnd))
    out = ctypes.c_void_p()
    res['responsive'] = bool(user32.SendMessageTimeoutW(hwnd, 0, 0, 0, 0x0002, 1500, ctypes.byref(out)))
proc.kill()
print(json.dumps(res, ensure_ascii=False))
