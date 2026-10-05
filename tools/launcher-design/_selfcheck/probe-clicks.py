# -*- coding: utf-8 -*-
"""三连点击诊断：最小化（可观测）→ 还原 → 关闭；附带 DPI 体系输出。"""
import ctypes
import json
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
EnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)


def find():
    best = [0, -1]

    def cb(hwnd, _):
        n = user32.GetWindowTextLengthW(hwnd)
        if n:
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            if buf.value == 'AYT 启动器' and user32.IsWindowVisible(hwnd):
                r = wintypes.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(r))
                a = (r.right - r.left) * (r.bottom - r.top)
                if a > best[1]:
                    best[0], best[1] = hwnd, a
        return True

    user32.EnumWindows(EnumProc(cb), 0)
    return best[0]


hwnd = find()
res = {'hwnd': hwnd, 'dpi_system': user32.GetDpiForSystem()}
if hwnd:
    res['dpi_win'] = user32.GetDpiForWindow(hwnd)

    def rect():
        r = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(r))
        return (r.left, r.top, r.right - r.left, r.bottom - r.top)

    def click(x, y):
        user32.SetCursorPos(x, y)
        time.sleep(0.2)
        user32.mouse_event(0x0002, 0, 0, 0, 0)
        time.sleep(0.08)
        user32.mouse_event(0x0004, 0, 0, 0, 0)

    l, t, w, h = rect()
    res['rect0'] = [l, t, w, h]
    click(l + w // 2, t + h - 60)  # 激活窗（底部空白）
    time.sleep(0.4)
    scale = res['dpi_win'] / 96
    bw = int(46 * scale)
    half = bw // 2
    y = t + int(22 * scale)
    cx_min = l + w - bw * 3 + half
    cx_close = l + w - half
    res['geometry'] = {'scale': scale, 'bw': bw, 'y': y, 'cx_min': cx_min, 'cx_close': cx_close}
    # ① 最小化
    click(cx_min, y)
    time.sleep(1.2)
    res['minimized'] = bool(user32.IsIconic(hwnd))
    # 还原
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    time.sleep(0.8)
    res['restored'] = not bool(user32.IsIconic(hwnd))
    # ② 关闭
    click(cx_close, y)
    time.sleep(1.5)
    res['closed_after_click'] = find() == 0
print(json.dumps(res, ensure_ascii=False))
