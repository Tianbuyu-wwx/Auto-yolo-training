"""根据扫描报告生成「缺什么补什么」的安装计划（纯函数，无副作用）。

step.status:
  - skip   —— 检查项已满足，无需动作
  - action —— 需要执行的安装/修复动作
  - warn   —— 需用户注意（可继续，但影响体验）
"""

from __future__ import annotations

from .scan import MIN_DISK_GB_CPU, MIN_DISK_GB_GPU, REQUIRED_PACKAGES, satisfies


def build_plan(rep: dict) -> dict:
    steps: list[dict] = []

    def add(sid: str, title: str, status: str, detail: str, action: str = "") -> None:
        steps.append(
            {"id": sid, "title": title, "status": status, "detail": detail, "action": action}
        )

    # ---- 1) Python 解释器 ----
    interps = rep.get("interpreters") or []
    p312 = [i for i in interps if (i.get("version") or "").startswith("3.12")]
    python_path: str | None = None
    if p312:
        best = p312[0]
        python_path = best["path"]
        add("python", "Python 3.12", "skip", f"已找到 {best['path']}（{best['version']} · {best['source']}）")
    elif interps:
        add(
            "python",
            "Python 3.12",
            "action",
            f"只找到 {interps[0]['version']}（{interps[0]['path']}）；AYT 需要 3.12",
            "下载官方 python-embeddable 3.12 到安装目录",
        )
    else:
        add(
            "python",
            "Python 3.12",
            "action",
            "未找到任何 Python",
            "下载官方 python-embeddable 3.12 到安装目录",
        )

    # ---- 2) 虚拟环境 ----
    install = rep.get("install") or {}
    venv_ready = bool(install.get("venv_present"))
    if venv_ready:
        add("venv", "虚拟环境", "skip", f"已存在：{install.get('venv_python')}")
    else:
        add(
            "venv",
            "虚拟环境",
            "action",
            f"在 {install.get('install_dir')} 创建独立 venv（避免污染系统环境）",
            "python -m venv venv",
        )

    # ---- 3) 依赖（缺啥补啥）----
    pkgs = rep.get("packages") or {}
    missing = [n for n, m in REQUIRED_PACKAGES.items() if not pkgs.get(n)]
    outdated = [
        f"{n} {pkgs.get(n)}（需 ≥{m}）"
        for n, m in REQUIRED_PACKAGES.items()
        if pkgs.get(n) and not satisfies(pkgs.get(n), m)
    ]
    ok_count = len(REQUIRED_PACKAGES) - len(missing) - len(outdated)

    if venv_ready:
        if missing or outdated:
            brief = "、".join(
                missing[:6] + [o.split("（")[0] for o in outdated[:3]]
            )
            add(
                "deps",
                "依赖",
                "action",
                f"venv 内缺 {len(missing)} 个、过旧 {len(outdated)} 个（{brief}）",
                "在 venv 中 pip install auto-yolo-training[launcher]（补齐缺口）",
            )
        else:
            add("deps", "依赖", "skip", f"全部 {ok_count} 个已满足（venv 内）")
    elif not missing and not outdated and python_path:
        # 系统解释器已完整满足 → 给出「复用 or 隔离」二选一
        add(
            "deps",
            "依赖",
            "warn",
            f"现有解释器已满足全部 {ok_count} 个依赖；两种装法："
            "① 隔离 venv（推荐：环境干净、可随时卸载）"
            "② 直接复用现有环境（跳过安装，最快）",
            "推荐：python -m venv venv && venv 内安装",
        )
    else:
        brief = "、".join(missing[:6]) + ("…" if len(missing) > 6 else "")
        add(
            "deps",
            "依赖",
            "action",
            f"目标环境缺 {len(missing)} 个包（{brief}）；torch 按 GPU/CPU 分支",
            "pip install auto-yolo-training[launcher]",
        )

    # ---- 4) CUDA 分支 ----
    gpu = rep.get("gpu") or {}
    tc = rep.get("torch_cuda") or {}
    if gpu.get("present"):
        gpus = gpu.get("gpus") or []
        gpu_name = gpus[0]["name"] if gpus else "NVIDIA GPU"
        driver = gpus[0].get("driver", "?") if gpus else "?"
        if tc.get("installed") and tc.get("available"):
            add("cuda", "CUDA 分支", "skip", f"{gpu_name} · torch CUDA 可用（{tc.get('cuda')}）")
        else:
            add(
                "cuda",
                "CUDA 分支",
                "skip",
                f"{gpu_name}（驱动 {driver}）→ 将安装 torch cu128（GPU 训练）",
                "",
            )
    else:
        add(
            "cuda",
            "CUDA 分支",
            "warn",
            "未检测到 NVIDIA GPU → 将安装 CPU 版 torch",
            "训练可运行但较慢；有 N 卡时可重装 cu128 版",
        )

    # ---- 5) WebView2 ----
    wv = rep.get("webview2") or {}
    if wv.get("present"):
        add("webview2", "WebView2 Runtime", "skip", f"已安装（{wv.get('version')}）")
    else:
        add(
            "webview2",
            "WebView2 Runtime",
            "action",
            "未检测到（桌面启动器的窗口渲染依赖它）",
            "从微软官网安装 Evergreen Runtime（免费，约 2MB 引导）",
        )

    # ---- 6) 磁盘空间 ----
    disk = rep.get("disk") or {}
    need = MIN_DISK_GB_GPU if gpu.get("present") else MIN_DISK_GB_CPU
    free = disk.get("free_gb")
    if free is None:
        add("disk", "磁盘空间", "warn", "无法读取磁盘信息")
    elif free < need:
        add(
            "disk",
            "磁盘空间",
            "warn",
            f"{disk.get('path')} 可用 {free} GB < 建议 {need} GB",
            "清理磁盘或更换安装位置",
        )
    else:
        add("disk", "磁盘空间", "skip", f"{disk.get('path')} 可用 {free} GB（≥ 建议 {need} GB）")

    # ---- 7) 网络/下载源 ----
    net = rep.get("network") or {}
    pypi_ok = bool((net.get("pypi") or {}).get("ok"))
    tuna_ok = bool((net.get("tuna") or {}).get("ok"))
    torch_ok = bool((net.get("pytorch_cu128") or {}).get("ok"))
    if pypi_ok:
        add("network", "下载源", "skip", f"PyPI 直连可用（PyTorch 源 {'✓' if torch_ok else '×'}）")
    elif tuna_ok:
        add("network", "下载源", "skip", "PyPI 直连不可用 → 自动使用清华镜像")
    else:
        add("network", "下载源", "warn", "PyPI 与镜像均不可达", "检查网络/代理后重试")

    # ---- 结论 ----
    actions = [s for s in steps if s["status"] == "action"]
    warns = [s for s in steps if s["status"] == "warn"]
    return {
        "steps": steps,
        "summary": {
            "action_count": len(actions),
            "warn_count": len(warns),
            "ready_now": not actions,
            "note": (
                "所有检查项均已满足，可直接启动"
                if not actions
                else f"需要执行 {len(actions)} 个安装/修复步骤"
                + (f"（另有 {len(warns)} 条提醒）" if warns else "")
            ),
        },
    }
