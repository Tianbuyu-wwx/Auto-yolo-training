# -*- coding: utf-8 -*-
"""窗口尺寸时间线探测：探到「AYT 启动器」后每 0.15s 采样 GetWindowRect，打印变化。"""
import ctypes
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

TITLE = "AYT 启动器"
t0 = time.time()
hwnd = 0
while time.time() - t0 < 30:
    h = user32.FindWindowW(None, TITLE)
    if h and user32.IsWindowVisible(h):
        hwnd = h
        break
    time.sleep(0.2)
print("hwnd:", hwnd, "found after", round(time.time() - t0, 2), "s")
if hwnd:
    prev = None
    end = time.time() + 14
    while time.time() < end:
        r = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(r))
        cur = (r.left, r.top, r.right - r.left, r.bottom - r.top)
        if cur != prev:
            print(round(time.time() - t0, 2), "s  rect", cur)
            prev = cur
        time.sleep(0.15)
    print("final:", prev)
else:
    print("window not found")
