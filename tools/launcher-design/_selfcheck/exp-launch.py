# -*- coding: utf-8 -*-
"""无边框对照实验窗：argv[1] = 配置名 b0/b1/b2/b3。父进程（exp-probe.py）到点杀掉。"""
import sys

import webview

cfg = sys.argv[1] if len(sys.argv) > 1 else 'b1'

kw = dict(width=1440, height=900, min_size=(1024, 700))
if cfg in ('b1', 'b2', 'b3'):
    kw['frameless'] = True
if cfg in ('b2', 'b3'):
    kw['easy_drag'] = False
if cfg == 'b3':

    class API:
        def win_min(self):
            pass

        def win_max(self):
            pass

        def win_close(self):
            pass

    kw['js_api'] = API()

if cfg in ('b4', 'b5'):
    kw['frameless'] = True
    kw['easy_drag'] = False
    if cfg == 'b5':

        class API5:
            def win_min(self):
                pass

            def win_max(self):
                pass

            def win_close(self):
                pass

        kw['js_api'] = API5()

_TARGET = {
    'b4': 'file:///E:/%E9%A1%B9%E7%9B%AE/Auto-yolo-training/tools/launcher-design/AYT-Launcher-v8.html',
    'b5': 'file:///E:/%E9%A1%B9%E7%9B%AE/Auto-yolo-training/tools/launcher-design/AYT-Launcher-v8.html',
}
_HTML = '<html><body style="background:#e8e8ee"><h1 style="font-family:sans-serif">exp ' + cfg + '</h1></body></html>'
_target = _TARGET.get(cfg)

w = webview.create_window(
    'EXP-WIN-' + cfg,
    _target if _target else None,
    html=None if _target else _HTML,
    **kw,
)
webview.start(debug=False, private_mode=False)
