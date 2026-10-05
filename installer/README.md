# AYT 安装器（Windows）

把「下载一个 exe → 装好完整训练环境 → 打开启动器」变成现实。
当前进度：**M1 已完成——环境扫描器 + 安装计划器可运行**（只读，不改动本机）。

## 用法（开发期）

```bash
# 只读扫描本机环境（Python / GPU / WebView2 / 磁盘 / 网络 / 依赖版本）
python -m installer.ayt_setup scan

# 生成「缺什么补什么」的安装计划（skip / action / warn 三级）
python -m installer.ayt_setup plan

# 机器可读输出（供后续 GUI 与执行器消费）
python -m installer.ayt_setup scan --json
```

## 结构

```
installer/
├── ayt_setup/
│   ├── scan.py      # 环境扫描（只读；子进程全部带超时 + 无窗口）
│   ├── plan.py      # 安装计划（纯函数：每步给出 skip / action / warn）
│   └── __main__.py  # CLI（scan / plan，--json）
└── （M2 起新增）execute.py（pip 执行器） / gui.py（向导） / build.py（PyInstaller）
```

## 里程碑（详见 `docs/archive/exe-packaging-plan.md`）

- [x] **M1** 环境扫描 + 安装计划
- [ ] **M2** 执行器 + 向导 UI（Python 自举 → 建 venv → pip 安装 → 快捷方式）
- [ ] **M3** GPU/镜像/断点重试打磨
- [ ] **M4** GitHub Release 集成 + Actions 自动构建（产物 `AYT-Setup-*.exe`）

## 设计要点

- **只读先行**：任何安装动作之前，先扫描并让用户看到「将要做什么」；
- **补装而不是重装**：按检查项逐条判断（已有 venv → 只补缺包；系统环境已满足 → 提供
  「复用现有环境」与「隔离 venv」两个选项）；
- **不碰系统**：默认安装到 `%LOCALAPPDATA%\AYT`，全部改动在安装目录内；
- **退出码**：0 成功；非 0 失败（便于脚本/CI 判断）。
