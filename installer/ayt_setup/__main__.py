"""AYT 安装器 CLI：

    python -m installer.ayt_setup scan    [--install-dir PATH] [--json]
    python -m installer.ayt_setup plan    [--install-dir PATH] [--json]
    python -m installer.ayt_setup install [--install-dir PATH] [--execute] [--yes]
                                          [--gpu|--cpu] [--mirror] [--reuse] [--wheel PATH]
    python -m installer.ayt_setup gui     [--install-dir PATH]

scan 只做只读探测；plan 给出「缺什么补什么」步骤；install 默认 dry-run 展示
将执行的动作，加 --execute 才真正执行；gui 启动 tkinter 安装向导。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .execute import InstallOptions, build_actions, run_actions
from .plan import build_plan
from .scan import REQUIRED_PACKAGES, default_install_dir, satisfies, scan

STATUS_ICON = {"skip": "[·]", "action": "[+]", "warn": "[!]"}


def _fmt_scan(rep: dict) -> str:
    lines = [
        f"══ AYT 环境扫描（{rep['generated_at']}） ══",
        f"安装目录   {rep['install_dir']}",
        f"操作系统   {rep['os']}",
        "",
    ]

    interps = rep.get("interpreters") or []
    if interps:
        for it in interps[:4]:
            is312 = (it.get("version") or "").startswith("3.12")
            note = "满足" if is312 else "非 3.12（不采用）"
            lines.append(
                f"{'[✓]' if is312 else '[!]'} Python      {it['path']}（{it['version']} · {it['source']}）{note}"
            )
    else:
        lines.append("[×] Python      未找到可用解释器（需要 3.12）")

    gpu = rep.get("gpu") or {}
    if gpu.get("present"):
        for g in (gpu.get("gpus") or [])[:2]:
            lines.append(f"[✓] GPU         {g['name']} · {g['memory']} · 驱动 {g['driver']}")
    else:
        lines.append("[!] GPU         未检测到 NVIDIA 显卡")

    wv = rep.get("webview2") or {}
    wv_txt = f"{wv.get('version')}（{wv.get('source', '')}）" if wv.get("present") else "未安装"
    lines.append(f"{'[✓]' if wv.get('present') else '[×]'} WebView2    {wv_txt}")

    disk = rep.get("disk") or {}
    if disk.get("free_gb") is not None:
        lines.append(f"[✓] 磁盘        {disk['path']} 可用 {disk['free_gb']} GB / {disk['total_gb']} GB")

    net = rep.get("network") or {}
    netline = " · ".join(f"{k} {'✓' if v.get('ok') else '×'}" for k, v in net.items())
    lines.append(f"[·] 网络        {netline}")

    sel = rep.get("selected_python")
    if sel:
        lines += ["", f"选定解释器：{sel}"]
        pkgs = rep.get("packages") or {}
        for name, minimum in REQUIRED_PACKAGES.items():
            v = pkgs.get(name)
            mark = "[✓]" if satisfies(v, minimum) else "[×]"
            lines.append(f"  {mark} {name:<18}{v or '未安装'}")
        tc = rep.get("torch_cuda") or {}
        if tc.get("installed"):
            lines.append(
                f"      torch CUDA：{tc.get('cuda') or 'CPU 版'} · available={tc.get('available')}"
            )

    lines += ["", f"（耗时 {rep.get('elapsed_s')}s，只读扫描，未改动任何东西）"]
    return "\n".join(lines)


def _fmt_plan(plan: dict) -> str:
    lines = ["══ 安装计划 ══", ""]
    for s in plan["steps"]:
        icon = STATUS_ICON.get(s["status"], "[?]")
        lines.append(f"{icon} {s['title']}：{s['detail']}")
        if s.get("action"):
            lines.append(f"       → {s['action']}")
    lines += ["", f"结论：{plan['summary']['note']}"]
    return "\n".join(lines)


def _cmd_install(args: argparse.Namespace) -> int:
    rep = scan(args.install_dir)
    install_dir = Path(args.install_dir) if args.install_dir else default_install_dir()
    gpu = args.gpu if args.gpu is not None else bool((rep.get("gpu") or {}).get("present"))
    opt = InstallOptions(
        install_dir=install_dir,
        mode="reuse" if args.reuse else "venv",
        gpu=gpu,
        mirror=args.mirror,
        ayt_source=args.wheel,
        make_shortcut=True,
    )
    actions = build_actions(rep, opt)
    if not actions:
        print("没有需要执行的动作。")
        return 0

    if not args.execute:
        print("=== 将执行的动作（dry-run；加 --execute 真正执行）===")
        for a in actions:
            line = " ".join(a["cmd"]) if a.get("cmd") else a.get("note", "")
            print(f"  [{a['id']}] {a['title']}")
            if line:
                print(f"        {line}")
        print(f"\n共 {len(actions)} 个动作 · 安装目录：{install_dir}")
        return 0

    if not args.yes:
        try:
            ans = input("确认执行以上动作？[y/N] ").strip().lower()
        except EOFError:
            ans = ""
        if ans not in ("y", "yes"):
            print("已取消。")
            return 1

    total = len(actions)
    print(f"=== 开始执行（{total} 个动作）===")

    def _on_step(i: int, act: dict) -> None:
        print(f"\n--- [{i + 1}/{total}] {act['title']} ---")

    results = run_actions(
        actions, install_dir=install_dir, on_line=lambda s: print("   ", s), on_step=_on_step
    )
    ok = all(r.get("ok") for r in results)
    print()
    for r in results:
        print(f"{'✓' if r.get('ok') else '×'} {r['title']} {r.get('detail', '')}")
    print("\n安装完成 ✓" if ok else "\n安装中途失败 ×（详见上方输出）")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ayt_setup", description="AYT 环境扫描 / 安装计划 / 安装器")
    ap.add_argument("command", choices=("scan", "plan", "install", "gui"))
    ap.add_argument("--install-dir", default=None, help="安装目录（默认 %%LOCALAPPDATA%%\\AYT）")
    ap.add_argument("--json", action="store_true", help="输出机器可读 JSON（scan/plan）")
    ap.add_argument("--execute", action="store_true", help="install：真正执行（默认 dry-run）")
    ap.add_argument("--yes", action="store_true", help="install：跳过确认")
    ap.add_argument("--gpu", dest="gpu", action="store_true", default=None, help="install：强制 GPU 版")
    ap.add_argument("--cpu", dest="gpu", action="store_false", help="install：强制 CPU 版")
    ap.add_argument("--mirror", action="store_true", help="install：依赖走清华镜像")
    ap.add_argument("--reuse", action="store_true", help="install：复用现有环境（跳过安装）")
    ap.add_argument("--wheel", default="", help="install：AYT wheel 路径（留空=从 PyPI 装）")
    args = ap.parse_args(argv)

    if args.command == "install":
        return _cmd_install(args)

    if args.command == "gui":
        from .gui import main as gui_main

        return gui_main(args.install_dir)

    rep = scan(args.install_dir)
    if args.command == "scan":
        print(json.dumps(rep, ensure_ascii=False, indent=1) if args.json else _fmt_scan(rep))
        return 0

    plan = build_plan(rep)
    print(json.dumps(plan, ensure_ascii=False, indent=1) if args.json else _fmt_plan(plan))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
