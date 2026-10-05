# AYT 安装器（Windows）

把「下载一个 exe → 装好完整训练环境 → 打开启动器」变成现实。
当前进度：**M1–M3 已完成——扫描 / 计划 / 执行 / 向导 / 单 EXE 打包全部可运行**。

## 快速开始（打包好的单文件）

```bash
python installer/build_setup.py --clean
# → installer/dist/AYT-Setup.exe（~12 MB，自包含）

# 双击 = 图形安装向导；也可当命令行工具用：
AYT-Setup.exe scan      # 只读扫描本机环境
AYT-Setup.exe plan      # 「缺什么补什么」计划
AYT-Setup.exe install   # 默认 dry-run；加 --execute 真正执行
```

## 用法（开发期，从源码跑）

```bash
python -m installer.ayt_setup scan                      # 只读扫描
python -m installer.ayt_setup plan                      # 安装计划
python -m installer.ayt_setup install                   # dry-run 展示动作
python -m installer.ayt_setup install --execute --yes   # 无人值守安装
python -m installer.ayt_setup gui                       # 图形向导
```

## 结构

```
installer/
├── entry_setup.py        # AYT-Setup.exe 入口（无参=GUI；scan/plan/install 透传；--selftest 自检）
├── build_setup.py        # 打包脚本（PyInstaller onefile + windowed，自动生成图标）
├── assets/ayt.ico        # 应用图标（构建时自动生成）
├── ayt_setup/
│   ├── scan.py           # 环境扫描（只读；子进程全部带超时 + 无窗口）
│   ├── plan.py           # 安装计划（纯函数：skip / action / warn）
│   ├── execute.py        # 执行器（命令构造纯函数 + 流式执行 + 桌面快捷方式）
│   ├── gui.py            # tkinter 四页向导（扫描 → 选项 → 执行 → 完成）
│   └── __main__.py       # CLI（scan / plan / install / gui）
└── dist/AYT-Setup.exe    # 构建产物（不入库）
```

## 里程碑

- [x] **M1** 环境扫描 + 安装计划
- [x] **M2** 执行器 + tkinter 向导（venv → pip → torch → AYT → 快捷方式）
- [x] **M3** 单 EXE 打包（PyInstaller onefile，~12 MB；CLI/GUI 双模式）
- [ ] **M4** GitHub Release 集成 + Actions 自动构建（产物 `AYT-Setup-*.exe`）

## 设计要点

- **只读先行**：任何安装动作之前，先扫描并让用户看到「将要做什么」；
- **补装而不是重装**：按检查项逐条判断（已有 venv → 只补缺包；系统环境已满足 → 提供
  「复用现有环境」与「隔离 venv」两个选项）；
- **不碰系统**：默认安装到 `%LOCALAPPDATA%\AYT`，全部改动在安装目录内；
- **可脚本化**：`install` 默认 dry-run，`--execute --yes` 无人值守；退出码 0/非 0；
- **安装器本身不装依赖**：exe 是纯 stdlib + tkinter（~12 MB），与训练依赖（~2.5 GB）解耦——
  后者由它装进目标 venv。
