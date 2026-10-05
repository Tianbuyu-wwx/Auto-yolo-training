# -*- coding: utf-8 -*-
"""fix10：文案去 AI 味（破折号节制 + 真实细节）"""
import io, sys

P = "AYT-Launcher-v1.html"
s = io.open(P, encoding="utf-8", newline="").read()

def rep(old, new, expect, tag):
    global s
    n = s.count(old)
    if n != expect:
        print("ABORT [%s] count=%d expected=%d" % (tag, n, expect)); sys.exit(1)
    s = s.replace(old, new)
    print("  %d  %s" % (n, tag))

# 破折号节制：23 处 → 保留 ~6 处（真停顿），其余改标点
rep("模型库 —— 项目的全部界面，都在这一个页面里。", "模型库：项目的全部界面，都在这一个页面里。", 2, "hero-desc")
rep("1 注意 —— 完整报告在「", "1 注意 · 完整报告在「", 1, "inst-note")
rep("显存 15.9 GB —— 大模型", "显存 15.9 GB；大模型", 1, "env-vram")
rep("JSON 说明 —— 启动器", "JSON 说明；启动器", 1, "env-dist")
rep("Slack）—— 在「设置", "Slack）；在「设置", 1, "env-webhook")
rep("1.4 GB —— 删除后不可恢复", "1.4 GB；删除后不可恢复", 1, "maint-recycle")
rep("运行环境 —— 缺什么", "运行环境：缺什么", 1, "wz-sub")
rep("显存 —— 预期比 CPU", "显存 · 预期比 CPU", 1, "wz-gpu")
rep("下一步 —— 启动控制台", "下一步：启动控制台", 1, "wz-next")
rep("压缩包 —— 导入后", "压缩包；导入后", 1, "drop-note")
rep("警告 2 —— val 集中", "警告 2；val 集中", 1, "toast-validate")
rep("04:55 —— 也可能是", "04:55；也可能是", 1, "toast-port")
rep("</span> —— 真实版本将上传", "</span>；真实版本将上传", 1, "toast-drop")
rep("127.0.0.1:8080 —— 打开浏览器", "127.0.0.1:8080；打开浏览器", 1, "js-running")

# 真实细节：补 commit 短哈希（仓库实测 9e05411）
rep("v0.1.0 · Python 3.12.7 · 界面构建 2026-10-04 · MIT License",
    "v0.1.0 · 9e05411 · Python 3.12.7 · 界面构建 2026-10-04 · MIT License", 1, "about-commit")

io.open(P, "w", encoding="utf-8", newline="").write(s)
left = s.count("——")
print("OK fix10 applied · 剩余 —— 共 %d 处（含注释，可见文案已收敛）" % left)
