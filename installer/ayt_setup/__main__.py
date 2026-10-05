"""AYT 安装器 CLI：

    python -m installer.ayt_setup scan [--install-dir PATH] [--json]
    python -m installer.ayt_setup plan [--install-dir PATH] [--json]

scan 只做只读探测；plan 在 scan 的基础上给出「缺什么补什么」的安装步骤。
"""

from __future__ import annotations

import argparse
import json

from .plan import build_plan
from .scan import REQUIRED_PACKAGES, satisfies, scan

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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ayt_setup", description="AYT 环境扫描 / 安装计划")
    ap.add_argument("command", choices=("scan", "plan"), help="scan=只读扫描；plan=安装计划")
    ap.add_argument("--install-dir", default=None, help="安装目录（默认 %%LOCALAPPDATA%%\\AYT）")
    ap.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    args = ap.parse_args(argv)

    rep = scan(args.install_dir)

    if args.command == "scan":
        print(json.dumps(rep, ensure_ascii=False, indent=1) if args.json else _fmt_scan(rep))
        return 0

    plan = build_plan(rep)
    print(json.dumps(plan, ensure_ascii=False, indent=1) if args.json else _fmt_plan(plan))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
