"""桌面启动器：把管理面后端 + pywebview 壳 + 启动器 UI 合成一个应用。

模块划分（见 launcher-plan-2026-10-04.md §2）：

- ``backend``：进程内 uvicorn 线程（**复用** src.api.admin 的整套 API/WS，零重造）；
- ``app``：``ayt-launcher`` 入口（单实例 → 内嵌后端 → 窗口 → 生命周期）；
- ``static/``：启动器 UI（Phase 1 为过渡页；方向 D 设计评审通过后进入 Phase 2）。

训练是独立子进程（TrainingService use_subprocess=True），启动器退出不影响训练。
"""
