# -*- coding: utf-8 -*-
"""js 桥端到端自测：evaluate_js → pywebview.api.win_* → LauncherWinAPI → 窗口方法。

避开鼠标注入（会被别的前台窗口挡住），直接测桥本身：
1) typeof window.pywebview / .api.win_min 检查注入；
2) verify 三方法可调用；3) win_close 后 webview.start() 正常返回。
"""
import sys
import threading
import time

sys.path.insert(0, 'E:/项目/Auto-yolo-training')

import webview  # noqa: E402

from src.launcher.app import LauncherWinAPI  # noqa: E402

api = LauncherWinAPI()
w = webview.create_window(
    'WAPI-TEST',
    html='<div id="d">wapi test</div>',
    width=500,
    height=300,
    frameless=True,
    js_api=api,
)
api._window = w


def job() -> None:
    time.sleep(3.5)
    t1 = w.evaluate_js('typeof window.pywebview')
    t2 = w.evaluate_js('typeof window.pywebview.api.win_min')
    t3 = w.evaluate_js('typeof window.pywebview.api.win_max')
    t4 = w.evaluate_js('typeof window.pywebview.api.win_close')
    print(f'typeof pywebview={t1} | win_min={t2} | win_max={t3} | win_close={t4}', flush=True)
    w.evaluate_js('pywebview.api.win_max()')
    time.sleep(0.8)
    w.evaluate_js('pywebview.api.win_close()')
    time.sleep(1.0)


threading.Thread(target=job, daemon=True).start()
webview.start(debug=False, private_mode=False)
print('EXITED-CLEAN', flush=True)
